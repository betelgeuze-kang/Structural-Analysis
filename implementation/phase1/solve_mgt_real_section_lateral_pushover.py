#!/usr/bin/env python3
"""Cantilever Euler-Bernoulli beam FE lateral pushover (aggregated EI, real MGT sections)."""

from __future__ import annotations

import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from assemble_mgt_mesh_condensed_story import assemble_story_model_from_mgt_npz
from extract_midas_wind_same_mesh_result import (
    DEFAULT_WIND_PARAMS_PATH,
    LATERAL_MIN_HEIGHT_FRACTION,
    _load_wind_params,
    _total_nodal_mass_ton,
)
from parse_mgt_section_material_properties import (
    load_mgt_section_material_properties,
    parse_mgt_material_properties,
    parse_mgt_section_properties,
)
from solve_mgt_beam_mesh_3d_global import _beam_props
from wind_workflow import run_wind_workflow

STEEL_E_PA = 210000.0e6
REGULARIZATION_EPS = 1.0e-9
# Wind story forces are generated on this reference mesh and resampled to the FE mesh so
# lateral drift converges with structural refinement (N) rather than load discretization.
WIND_FORCE_REFERENCE_STORIES = 48


def _collect_full_height_column_lines(
    npz_path: Path,
    *,
    section_props: dict[int, dict[str, Any]],
    material_props: dict[int, dict[str, Any]],
) -> tuple[float, list[tuple[int, int, bool]]]:
    """Return building height and (section_id, material_id, used_real_section) per column line."""
    with np.load(npz_path, allow_pickle=False) as archive:
        xyz = np.asarray(archive["node_xyz"], dtype=np.float64)
        edge_index = np.asarray(archive["edge_index"], dtype=np.int64)
        elem_type_code = np.asarray(archive["elem_type_code"], dtype=np.int64)
        elem_section_id = np.asarray(archive["elem_section_id"], dtype=np.int64)
        elem_material_id = np.asarray(archive["elem_material_id"], dtype=np.int64)

    building_height_m = float(xyz[:, 2].max() - xyz[:, 2].min())
    min_column_height_m = LATERAL_MIN_HEIGHT_FRACTION * building_height_m

    columns: dict[tuple[float, float], list[tuple[float, float, int, int]]] = defaultdict(list)
    beam_idx = np.where(elem_type_code == 1)[0]
    n_cols = edge_index.shape[1]
    for idx in beam_idx:
        if idx >= n_cols:
            continue
        i = int(edge_index[0, idx])
        j = int(edge_index[1, idx])
        if i < 0 or j < 0 or i >= xyz.shape[0] or j >= xyz.shape[0]:
            continue
        pi = xyz[i]
        pj = xyz[j]
        dz = abs(pj[2] - pi[2])
        plan = float(np.hypot(pj[0] - pi[0], pj[1] - pi[1]))
        length = float(np.hypot(plan, dz))
        if length < 0.2 or dz / max(length, 1e-9) <= 0.7:
            continue
        key = (
            round((pi[0] + pj[0]) / 2.0, 1),
            round((pi[1] + pj[1]) / 2.0, 1),
        )
        columns[key].append(
            (
                min(pi[2], pj[2]),
                max(pj[2], pi[2]),
                int(elem_section_id[idx]),
                int(elem_material_id[idx]),
            )
        )

    lines: list[tuple[int, int, bool]] = []
    for segments in columns.values():
        z_min = min(s[0] for s in segments)
        z_max = max(s[1] for s in segments)
        height_raw = z_max - z_min
        if height_raw < min_column_height_m:
            continue
        med_section = int(np.median([s[2] for s in segments]))
        med_material = int(np.median([s[3] for s in segments]))
        used_real = med_section in section_props and med_material in material_props
        lines.append((med_section, med_material, used_real))

    return building_height_m, lines


def _column_ei_knm2(
    *,
    section_id: int,
    material_id: int,
    section_props: dict[int, dict[str, Any]],
    material_props: dict[int, dict[str, Any]],
) -> tuple[float, bool]:
    sec = section_props.get(section_id)
    mat = material_props.get(material_id)
    if sec is not None and mat is not None:
        iy = float(min(sec["Iy_m4"], sec["Iz_m4"]))
        e_knm2 = float(mat["E_kN_per_m2"])
        return e_knm2 * iy, True
    props = _beam_props(length_m=1.0, section_id=section_id)
    e_knm2 = STEEL_E_PA / 1000.0
    return e_knm2 * props.iy_m4, False


def _aggregate_ei_knm2(
    column_lines: list[tuple[int, int, bool]],
    *,
    section_props: dict[int, dict[str, Any]],
    material_props: dict[int, dict[str, Any]],
) -> tuple[float, float]:
    ei_sum = 0.0
    real_lines = 0
    for section_id, material_id, _ in column_lines:
        ei, used_real = _column_ei_knm2(
            section_id=section_id,
            material_id=material_id,
            section_props=section_props,
            material_props=material_props,
        )
        ei_sum += ei
        if used_real:
            real_lines += 1
    coverage = 100.0 * float(real_lines) / float(len(column_lines)) if column_lines else 0.0
    return ei_sum, coverage


def _euler_bernoulli_beam_stiffness(*, ei_knm2: float, element_length_m: float) -> np.ndarray:
    le = max(float(element_length_m), 1.0e-6)
    ei = float(ei_knm2)
    c = ei / le**3
    return c * np.array(
        [
            [12.0, 6.0 * le, -12.0, 6.0 * le],
            [6.0 * le, 4.0 * le**2, -6.0 * le, 2.0 * le**2],
            [-12.0, -6.0 * le, 12.0, -6.0 * le],
            [6.0 * le, 2.0 * le**2, -6.0 * le, 4.0 * le**2],
        ],
        dtype=np.float64,
    )


def _assemble_global_stiffness(*, n_elements: int, ei_knm2: float, building_height_m: float) -> np.ndarray:
    n_nodes = n_elements + 1
    ndof = 2 * n_nodes
    k_global = np.zeros((ndof, ndof), dtype=np.float64)
    le = max(building_height_m, 1.0e-6) / float(n_elements)
    ke = _euler_bernoulli_beam_stiffness(ei_knm2=ei_knm2, element_length_m=le)
    for elem in range(n_elements):
        dofs = np.array(
            [2 * elem, 2 * elem + 1, 2 * elem + 2, 2 * elem + 3],
            dtype=np.int64,
        )
        for a, i in enumerate(dofs):
            for b, j in enumerate(dofs):
                k_global[i, j] += ke[a, b]
    return k_global


def _free_dofs_for_boundary(*, n_elements: int, boundary: str) -> np.ndarray:
    n_nodes = int(n_elements) + 1
    ndof = 2 * n_nodes
    constrained = {0, 1}
    if boundary == "fixed_guided":
        constrained.add(2 * n_elements + 1)
    elif boundary != "cantilever":
        raise ValueError(f"unsupported boundary: {boundary}")
    return np.array([i for i in range(ndof) if i not in constrained], dtype=np.int64)


def _solve_mode_for_boundary(boundary: str) -> str:
    if boundary == "fixed_guided":
        return "fixed_guided_beam_fe_real_section"
    if boundary == "cantilever":
        return "cantilever_beam_fe_real_section"
    raise ValueError(f"unsupported boundary: {boundary}")


def _solve_beam_fe_pushover(
    *,
    n_elements: int,
    ei_knm2: float,
    building_height_m: float,
    story_forces_kN: np.ndarray,
    boundary: str,
    blockers: list[str],
) -> dict[str, Any]:
    n = max(int(n_elements), 1)
    le = max(building_height_m, 1.0e-6) / float(n)
    k_global = _assemble_global_stiffness(
        n_elements=n,
        ei_knm2=ei_knm2,
        building_height_m=building_height_m,
    )

    free_dofs = _free_dofs_for_boundary(n_elements=n, boundary=boundary)
    k_ff = k_global[np.ix_(free_dofs, free_dofs)]

    f_global = np.zeros(k_global.shape[0], dtype=np.float64)
    forces = np.asarray(story_forces_kN, dtype=np.float64).reshape(-1)
    if forces.size != n:
        forces = np.asarray(
            _resample_story_forces(forces.tolist(), n, building_height_m=building_height_m),
            dtype=np.float64,
        )
    for story in range(n):
        node = story + 1
        f_global[2 * node] = forces[story]

    f_free = f_global[free_dofs]

    try:
        cond = float(np.linalg.cond(k_ff))
        if not np.isfinite(cond) or cond > 1.0e14:
            reg = REGULARIZATION_EPS * max(float(np.max(np.abs(np.diag(k_ff)))), 1.0)
            k_ff = k_ff + reg * np.eye(k_ff.shape[0])
            blockers.append("stiffness_matrix_ill_conditioned_regularized")
        u_free = np.linalg.solve(k_ff, f_free)
    except np.linalg.LinAlgError:
        reg = REGULARIZATION_EPS * max(float(np.max(np.abs(np.diag(k_ff)))), 1.0)
        k_ff = k_ff + reg * np.eye(k_ff.shape[0])
        blockers.append("stiffness_matrix_singular_regularized")
        u_free = np.linalg.solve(k_ff, f_free)

    u_global = np.zeros(k_global.shape[0], dtype=np.float64)
    u_global[free_dofs] = u_free

    floor_displacements_m: list[float] = []
    interstory_drift_ratio: list[float] = []
    v_prev = 0.0
    for story in range(1, n + 1):
        v_k = float(u_global[2 * story])
        floor_displacements_m.append(v_k)
        interstory_drift_ratio.append((v_k - v_prev) / le)
        v_prev = v_k

    max_drift_ratio = max(interstory_drift_ratio) if interstory_drift_ratio else 0.0
    return {
        "floor_displacements_m": floor_displacements_m,
        "interstory_drift_ratio": interstory_drift_ratio,
        "max_story_drift_ratio_pct": float(max_drift_ratio * 100.0),
        "top_displacement_m": float(u_global[2 * n]),
        "element_length_m": le,
    }


def _build_wind_payload(
    *,
    mgt_path: Path,
    roundtrip_npz: Path,
    n_stories: int,
    wind_params: dict[str, Any],
    basic_wind_speed_mps: float,
    exposure: str,
) -> dict[str, Any]:
    with np.load(roundtrip_npz, allow_pickle=False) as archive:
        xyz = np.asarray(archive["node_xyz"], dtype=np.float64)
    plan_dim_x_m = float(xyz[:, 0].max() - xyz[:, 0].min())
    plan_dim_y_m = float(xyz[:, 1].max() - xyz[:, 1].min())
    height_m = float(xyz[:, 2].max() - xyz[:, 2].min())

    mgt_text = mgt_path.read_text(encoding="utf-8", errors="ignore") if mgt_path.is_file() else ""
    total_mass_ton = _total_nodal_mass_ton(mgt_text)

    story = assemble_story_model_from_mgt_npz(roundtrip_npz=roundtrip_npz)
    micro_h = np.asarray(story["story_h_m"], dtype=np.float64)
    micro_k = np.asarray(story["story_k_n_per_m"], dtype=np.float64) / 1000.0
    micro_m = np.asarray(story["story_mass_kg"], dtype=np.float64)
    n_micro = micro_h.size

    n_st = max(2, min(int(n_stories), n_micro))
    bins = np.array_split(np.arange(n_micro), n_st)
    heights: list[float] = []
    stiffness: list[float] = []
    mass_weights: list[float] = []
    for idx_group in bins:
        if idx_group.size == 0:
            continue
        heights.append(float(np.sum(micro_h[idx_group])))
        inv = np.sum(1.0 / np.clip(micro_k[idx_group], 1e-9, None))
        stiffness.append(float(1.0 / inv) if inv > 0 else float(np.mean(micro_k[idx_group])))
        mass_weights.append(float(np.sum(micro_m[idx_group])))

    mass_weights_arr = np.asarray(mass_weights, dtype=np.float64)
    mass_share = mass_weights_arr / max(float(np.sum(mass_weights_arr)), 1e-9)
    story_masses_t = (mass_share * max(total_mass_ton, 1.0)).tolist()
    period_s = max(0.1, 0.05 * height_m)

    return {
        "site": {
            "basic_wind_speed_mps": basic_wind_speed_mps,
            "exposure": exposure,
            "topographic_factor": float(wind_params.get("topographic_factor", 1.0)),
            "directionality_factor": float(wind_params.get("directionality_factor", 0.85)),
            "importance_factor": float(wind_params.get("importance_factor", 1.0)),
            "gust_factor": float(wind_params.get("gust_factor", 0.85)),
        },
        "building": {
            "name": mgt_path.stem,
            "plan_dim_x_m": max(plan_dim_x_m, 1.0),
            "plan_dim_y_m": max(plan_dim_y_m, 1.0),
            "story_heights_m": heights,
            "story_masses_t": story_masses_t,
            "story_stiffness_kNpm": stiffness,
            "fundamental_period_s": period_s,
            "damping_ratio": float(wind_params.get("damping_ratio", 0.02)),
            "force_coefficient": float(wind_params.get("force_coefficient", 1.3)),
            "across_wind_factor": float(wind_params.get("across_wind_factor", 1.2)),
        },
    }


def _resample_story_forces(
    forces: list[float],
    target_n: int,
    *,
    building_height_m: float,
) -> list[float]:
    """Resample lumped story forces by height-band overlap (preserves total base shear)."""
    src = np.asarray(forces, dtype=np.float64)
    n_src = int(src.size)
    n_tgt = max(int(target_n), 1)
    if n_src == n_tgt:
        return [float(v) for v in src]
    if n_src == 0:
        return [0.0] * n_tgt

    height = max(float(building_height_m), 1.0e-6)
    h_src = height / float(n_src)
    h_tgt = height / float(n_tgt)
    out = np.zeros(n_tgt, dtype=np.float64)
    for j in range(n_tgt):
        z0 = j * h_tgt
        z1 = (j + 1) * h_tgt
        for i in range(n_src):
            zs0 = i * h_src
            zs1 = (i + 1) * h_src
            overlap = max(0.0, min(z1, zs1) - max(z0, zs0))
            if overlap > 0.0:
                out[j] += src[i] * (overlap / h_src)
    return [float(v) for v in out]


def _governing_strength_x_story_forces_kN(
    wind_report: dict[str, Any],
) -> list[float]:
    cases = wind_report.get("load_cases") if isinstance(wind_report.get("load_cases"), list) else []
    strength_x = [
        c
        for c in cases
        if isinstance(c, dict)
        and c.get("limit_state") == "strength"
        and str(c.get("direction", "")).upper() == "X"
        and int(c.get("sign", 1)) >= 0
    ]
    if not strength_x:
        strength_x = [
            c
            for c in cases
            if isinstance(c, dict) and c.get("limit_state") == "strength"
        ]
    if not strength_x:
        return []

    governing = max(
        strength_x,
        key=lambda row: float(row.get("base_shear_kN") or sum(abs(f) for f in row.get("story_forces_kN", []))),
    )
    return [float(f) for f in governing.get("story_forces_kN", [])]


def _rel_error(native: float, reference: float) -> float:
    if abs(reference) <= 1.0e-9:
        return 0.0 if abs(native) <= 1.0e-9 else 1.0
    return abs(native - reference) / abs(reference)


def evaluate_wind_drift_bracket(
    *,
    lumped_drift_pct: float,
    fixed_guided_drift_pct: float,
    cantilever_drift_pct: float,
    drift_tol_ratio: float = 0.60,
) -> dict[str, Any]:
    """Classify lumped drift vs native FE bounds (fixed-guided stiff, cantilever soft)."""
    stiff_bound = min(float(fixed_guided_drift_pct), float(cantilever_drift_pct))
    soft_bound = max(float(fixed_guided_drift_pct), float(cantilever_drift_pct))
    lumped = float(lumped_drift_pct)
    ordering_ok = float(fixed_guided_drift_pct) <= float(cantilever_drift_pct)
    bracketed = ordering_ok and stiff_bound <= lumped <= soft_bound
    aligned_rel = _rel_error(stiff_bound, lumped) if ordering_ok else _rel_error(fixed_guided_drift_pct, lumped)
    aligned = ordering_ok and aligned_rel <= drift_tol_ratio
    return {
        "lumped_drift_pct": lumped,
        "fixed_guided_drift_pct": float(fixed_guided_drift_pct),
        "cantilever_drift_pct": float(cantilever_drift_pct),
        "stiff_bound_drift_pct": stiff_bound,
        "soft_bound_drift_pct": soft_bound,
        "ordering_ok": ordering_ok,
        "lumped_bracketed_between_bounds": bracketed,
        "aligned_with_fixed_guided": aligned,
        "fixed_guided_vs_lumped_rel_error": aligned_rel,
        "drift_tol_ratio": drift_tol_ratio,
    }


def _prepare_lateral_pushover_inputs(
    *,
    roundtrip_npz: Path,
    mgt_path: Path,
    n_stories: int,
    basic_wind_speed_mps: float | None,
    exposure: str | None,
    wind_params_json: Path | None,
) -> tuple[dict[str, Any], list[str]]:
    blockers: list[str] = []
    npz = Path(roundtrip_npz)
    mgt = Path(mgt_path)
    if not npz.is_file():
        return (
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "status": "blocked",
                "blockers": ["roundtrip_npz_missing"],
            },
            blockers,
        )

    parsed_props = (
        load_mgt_section_material_properties(mgt) if mgt.is_file() else {"sections": {}, "materials": {}}
    )
    section_props = parsed_props.get("sections") if isinstance(parsed_props.get("sections"), dict) else {}
    material_props = parsed_props.get("materials") if isinstance(parsed_props.get("materials"), dict) else {}
    if not section_props and mgt.is_file():
        mgt_text = mgt.read_text(encoding="utf-8", errors="ignore")
        section_props = parse_mgt_section_properties(mgt_text)
        material_props = parse_mgt_material_properties(mgt_text)

    n = max(2, int(n_stories))
    building_height_m, column_lines = _collect_full_height_column_lines(
        npz,
        section_props=section_props,
        material_props=material_props,
    )
    if len(column_lines) < 4:
        blockers.append("insufficient_full_height_column_lines")

    ei_aggregate_knm2, real_section_coverage_pct = _aggregate_ei_knm2(
        column_lines,
        section_props=section_props,
        material_props=material_props,
    )

    wind_params = _load_wind_params(wind_params_json)
    resolved_wind_speed = (
        float(basic_wind_speed_mps)
        if basic_wind_speed_mps is not None
        else float(wind_params.get("basic_wind_speed_mps", 30.0))
    )
    resolved_exposure = str(exposure if exposure else wind_params.get("exposure", "B")).upper()

    story = assemble_story_model_from_mgt_npz(roundtrip_npz=npz)
    n_micro = int(np.asarray(story["story_h_m"], dtype=np.float64).size)
    wind_n = max(2, min(max(n, WIND_FORCE_REFERENCE_STORIES), n_micro))

    wind_payload = _build_wind_payload(
        mgt_path=mgt,
        roundtrip_npz=npz,
        n_stories=wind_n,
        wind_params=wind_params,
        basic_wind_speed_mps=resolved_wind_speed,
        exposure=resolved_exposure,
    )
    wind_report = run_wind_workflow(wind_payload)
    ref_forces = _governing_strength_x_story_forces_kN(wind_report)
    story_forces = _resample_story_forces(ref_forces, n, building_height_m=building_height_m)
    base_shear_kn = float(sum(story_forces))

    return (
        {
            "n": n,
            "building_height_m": building_height_m,
            "column_lines": column_lines,
            "ei_aggregate_knm2": ei_aggregate_knm2,
            "real_section_coverage_pct": real_section_coverage_pct,
            "story_forces": story_forces,
            "base_shear_kn": base_shear_kn,
            "wind_n": wind_n,
            "resolved_wind_speed": resolved_wind_speed,
            "resolved_exposure": resolved_exposure,
            "wind_params": wind_params,
        },
        blockers,
    )


def solve_real_section_lateral_pushover(
    *,
    roundtrip_npz: Path,
    mgt_path: Path,
    n_stories: int = 12,
    boundary: str = "cantilever",
    basic_wind_speed_mps: float | None = None,
    exposure: str | None = None,
    wind_params_json: Path | None = None,
) -> dict[str, Any]:
    boundary_norm = str(boundary).strip().lower()
    if boundary_norm == "both":
        return solve_wind_native_lateral_dual(
            roundtrip_npz=roundtrip_npz,
            mgt_path=mgt_path,
            n_stories=n_stories,
            basic_wind_speed_mps=basic_wind_speed_mps,
            exposure=exposure,
            wind_params_json=wind_params_json,
        )

    blockers: list[str] = []
    prepared, prep_blockers = _prepare_lateral_pushover_inputs(
        roundtrip_npz=roundtrip_npz,
        mgt_path=mgt_path,
        n_stories=n_stories,
        basic_wind_speed_mps=basic_wind_speed_mps,
        exposure=exposure,
        wind_params_json=wind_params_json,
    )
    blockers.extend(prep_blockers)
    if prepared.get("status") == "blocked":
        return prepared

    n = int(prepared["n"])
    pushover = _solve_beam_fe_pushover(
        n_elements=n,
        ei_knm2=float(prepared["ei_aggregate_knm2"]),
        building_height_m=float(prepared["building_height_m"]),
        story_forces_kN=np.asarray(prepared["story_forces"], dtype=np.float64),
        boundary=boundary_norm,
        blockers=blockers,
    )

    if pushover["max_story_drift_ratio_pct"] > 100.0:
        blockers.append("drift_implausible")

    wind_params = prepared["wind_params"]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready",
        "boundary": boundary_norm,
        "solve_mode": _solve_mode_for_boundary(boundary_norm),
        "n_stories": n,
        "per_element_count": n,
        "building_height_m": float(prepared["building_height_m"]),
        "full_height_column_line_count": len(prepared["column_lines"]),
        "ei_aggregate_kNm2": float(prepared["ei_aggregate_knm2"]),
        "story_forces_kN": prepared["story_forces"],
        "wind_force_reference_stories": prepared["wind_n"],
        "real_section_coverage_pct": float(prepared["real_section_coverage_pct"]),
        "base_shear_kn": float(prepared["base_shear_kn"]),
        "resolved_basic_wind_speed_mps": prepared["resolved_wind_speed"],
        "resolved_exposure": prepared["resolved_exposure"],
        "wind_params_source": str(
            wind_params.get("_path")
            or os.environ.get("PHASE1_KDS_WIND_PARAMS_JSON")
            or DEFAULT_WIND_PARAMS_PATH
        ),
        "blockers": blockers,
        **pushover,
    }


def solve_wind_native_lateral_dual(
    *,
    roundtrip_npz: Path,
    mgt_path: Path,
    n_stories: int = 12,
    basic_wind_speed_mps: float | None = None,
    exposure: str | None = None,
    wind_params_json: Path | None = None,
) -> dict[str, Any]:
    """Run fixed-guided and cantilever beam FE under identical story forces."""
    blockers: list[str] = []
    prepared, prep_blockers = _prepare_lateral_pushover_inputs(
        roundtrip_npz=roundtrip_npz,
        mgt_path=mgt_path,
        n_stories=n_stories,
        basic_wind_speed_mps=basic_wind_speed_mps,
        exposure=exposure,
        wind_params_json=wind_params_json,
    )
    blockers.extend(prep_blockers)
    if prepared.get("status") == "blocked":
        return prepared

    n = int(prepared["n"])
    forces = np.asarray(prepared["story_forces"], dtype=np.float64)
    modes: dict[str, dict[str, Any]] = {}
    for boundary in ("fixed_guided", "cantilever"):
        mode_blockers: list[str] = []
        pushover = _solve_beam_fe_pushover(
            n_elements=n,
            ei_knm2=float(prepared["ei_aggregate_knm2"]),
            building_height_m=float(prepared["building_height_m"]),
            story_forces_kN=forces,
            boundary=boundary,
            blockers=mode_blockers,
        )
        blockers.extend(mode_blockers)
        modes[boundary] = {
            "boundary": boundary,
            "solve_mode": _solve_mode_for_boundary(boundary),
            **pushover,
        }

    fg_drift = float(modes["fixed_guided"]["max_story_drift_ratio_pct"])
    cv_drift = float(modes["cantilever"]["max_story_drift_ratio_pct"])
    wind_params = prepared["wind_params"]

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready",
        "schema": "wind_native_lateral_dual.v1",
        "boundary": "both",
        "n_stories": n,
        "per_element_count": n,
        "building_height_m": float(prepared["building_height_m"]),
        "full_height_column_line_count": len(prepared["column_lines"]),
        "ei_aggregate_kNm2": float(prepared["ei_aggregate_knm2"]),
        "story_forces_kN": prepared["story_forces"],
        "wind_force_reference_stories": prepared["wind_n"],
        "real_section_coverage_pct": float(prepared["real_section_coverage_pct"]),
        "base_shear_kn": float(prepared["base_shear_kn"]),
        "fixed_guided_drift_pct": fg_drift,
        "cantilever_drift_pct": cv_drift,
        "max_story_drift_ratio_pct": fg_drift,
        "boundary_modes": modes,
        "resolved_basic_wind_speed_mps": prepared["resolved_wind_speed"],
        "resolved_exposure": prepared["resolved_exposure"],
        "wind_params_source": str(
            wind_params.get("_path")
            or os.environ.get("PHASE1_KDS_WIND_PARAMS_JSON")
            or DEFAULT_WIND_PARAMS_PATH
        ),
        "blockers": blockers,
    }
