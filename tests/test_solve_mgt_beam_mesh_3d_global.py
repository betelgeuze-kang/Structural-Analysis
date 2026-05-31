#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))

from parse_mgt_section_material_properties import load_mgt_section_material_properties  # noqa: E402
from solve_mgt_beam_mesh_3d_global import solve_mgt_beam_mesh_3d_global  # noqa: E402

MGT = REPO_ROOT / "implementation/phase1/open_data/midas/midas_generator_33.optimized.mgt"


def test_mgt_beam_mesh_3d_linear_tangent_fallback_converges() -> None:
    npz = REPO_ROOT / "implementation/phase1/open_data/midas/midas_generator_33.optimized.roundtrip.npz"
    with np.load(npz, allow_pickle=False) as archive:
        payload = solve_mgt_beam_mesh_3d_global(
            node_xyz=np.asarray(archive["node_xyz"], dtype=np.float64),
            edge_index=np.asarray(archive["edge_index"], dtype=np.int64),
            elem_id=np.asarray(archive["elem_id"], dtype=np.int64),
            elem_type_code=np.asarray(archive["elem_type_code"], dtype=np.int32),
            elem_section_id=np.asarray(archive["elem_section_id"], dtype=np.int32),
            max_elements=120,
            load_scale=1.0,
        )
    assert payload.get("converged") is True
    assert payload.get("solve_mode") in {
        "mgt_npz_beam_mesh_3d_global_newton",
        "mgt_npz_beam_mesh_3d_linear_tangent",
    }
    assert payload.get("used_real_section_properties") is not True


def test_mgt_beam_mesh_3d_real_section_properties_stable() -> None:
    npz = REPO_ROOT / "implementation/phase1/open_data/midas/midas_generator_33.optimized.roundtrip.npz"
    bundle = load_mgt_section_material_properties(MGT)
    payload: dict = {}
    with np.load(npz, allow_pickle=False) as archive:
        common = dict(
            node_xyz=np.asarray(archive["node_xyz"], dtype=np.float64),
            edge_index=np.asarray(archive["edge_index"], dtype=np.int64),
            elem_id=np.asarray(archive["elem_id"], dtype=np.int64),
            elem_type_code=np.asarray(archive["elem_type_code"], dtype=np.int32),
            elem_section_id=np.asarray(archive["elem_section_id"], dtype=np.int32),
            elem_material_id=np.asarray(archive["elem_material_id"], dtype=np.int32),
            section_props=bundle["sections"],
            material_props=bundle["materials"],
            max_elements=420,
        )
        for scale in (1.0, 0.5, 0.25, 0.1):
            payload = solve_mgt_beam_mesh_3d_global(load_scale=float(scale), **common)
            if payload.get("converged"):
                break
    assert payload.get("status") != "blocked"
    assert payload.get("used_real_section_properties") is True
    assert float(payload.get("real_section_property_coverage_pct") or 0.0) > 0.0
    assert payload.get("converged") is True
    assert payload.get("solve_mode") in {
        "mgt_npz_beam_mesh_3d_real_section",
        "mgt_npz_beam_mesh_3d_real_section_linear_tangent",
    }
    metrics = payload.get("response_metrics") if isinstance(payload.get("response_metrics"), dict) else {}
    assert np.isfinite(float(metrics.get("max_drift_ratio_pct") or 0.0))


def test_mgt_beam_mesh_3d_improved_newton_real_section_convergence() -> None:
    """I3: improved Newton should converge geometrically or document fallback with iteration count."""
    npz = REPO_ROOT / "implementation/phase1/open_data/midas/midas_generator_33.optimized.roundtrip.npz"
    bundle = load_mgt_section_material_properties(MGT)
    common = dict(
        section_props=bundle["sections"],
        material_props=bundle["materials"],
        max_elements=420,
        use_improved_newton=True,
    )
    legacy_first_residual: float | None = None
    improved: dict = {}
    legacy: dict = {}
    with np.load(npz, allow_pickle=False) as archive:
        archive_kw = dict(
            node_xyz=np.asarray(archive["node_xyz"], dtype=np.float64),
            edge_index=np.asarray(archive["edge_index"], dtype=np.int64),
            elem_id=np.asarray(archive["elem_id"], dtype=np.int64),
            elem_type_code=np.asarray(archive["elem_type_code"], dtype=np.int32),
            elem_section_id=np.asarray(archive["elem_section_id"], dtype=np.int32),
            elem_material_id=np.asarray(archive["elem_material_id"], dtype=np.int32),
        )
        applied_scale = 1.0
        for scale in (1.0, 0.5, 0.25, 0.1):
            applied_scale = float(scale)
            improved = solve_mgt_beam_mesh_3d_global(**archive_kw, **common, load_scale=applied_scale)
            if improved.get("converged"):
                break
        legacy = solve_mgt_beam_mesh_3d_global(
            **archive_kw,
            section_props=bundle["sections"],
            material_props=bundle["materials"],
            max_elements=420,
            load_scale=applied_scale,
            use_improved_newton=False,
        )
        for row in legacy.get("newton_iteration_log") or []:
            if isinstance(row, dict) and row.get("solver_mode") == "global_beam_newton":
                legacy_first_residual = float(row.get("residual_inf") or 0.0)
                break

    assert improved.get("converged") is True
    assert improved.get("use_improved_newton") is True
    newton_at = improved.get("newton_converged_at_load_step")
    newton_iters = int(improved.get("newton_iterations_total") or 0)
    fell_back = bool(improved.get("fell_back_to_linear_tangent"))
    nonlinear = bool(improved.get("nonlinear_equilibrium"))
    improved_first_residual: float | None = None
    for row in improved.get("newton_iteration_log") or []:
        if isinstance(row, dict) and row.get("solver_mode") == "global_beam_newton":
            improved_first_residual = float(row.get("residual_inf") or 0.0)
            break

    geometric_ok = nonlinear and newton_at is not None and float(newton_at) >= 0.5
    fallback_documented = fell_back and newton_iters > 0
    if fallback_documented and legacy_first_residual is not None and improved_first_residual is not None:
        fallback_documented = improved_first_residual < legacy_first_residual
    improved_metrics = improved.get("response_metrics") if isinstance(improved.get("response_metrics"), dict) else {}
    legacy_metrics = legacy.get("response_metrics") if isinstance(legacy.get("response_metrics"), dict) else {}
    if fallback_documented:
        fallback_documented = float(improved_metrics.get("residual_inf") or 1.0) <= float(
            legacy_metrics.get("residual_inf") or 1.0
        )

    assert geometric_ok or fallback_documented, (
        f"expected geometric Newton at load>=0.5 or documented fallback; "
        f"newton_at={newton_at}, nonlinear={nonlinear}, fell_back={fell_back}, iters={newton_iters}, "
        f"improved_r0={improved_first_residual}, legacy_r0={legacy_first_residual}"
    )
