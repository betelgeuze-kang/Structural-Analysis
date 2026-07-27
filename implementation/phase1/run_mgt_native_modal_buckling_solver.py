#!/usr/bin/env python3
"""Run native modal and buckling eigen solves on an MGT beam component."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import numpy as np
from scipy.linalg import eig

from design_optimization.io import load_json
from parse_mgt_section_material_properties import load_mgt_section_material_properties
from run_story_model_reanalysis import build_mgt_reanalysis_provenance
from solve_mgt_beam_mesh_3d_global import (
    DOF_PER_NODE,
    BeamElement,
    _assemble_global,
    _element_beam_props,
    _estimate_gravity_axial_forces,
    _node_dof_indices,
    _select_beam_submesh,
    _select_vertical_chain_elements,
)
from structural_analysis.solvers.equation_scaling import (
    build_equation_scaling_6dof,
    characteristic_length_from_coordinates,
)


SCHEMA_VERSION = "mgt-native-modal-buckling-solver.v1"
REPO_ROOT = Path(__file__).resolve().parents[2]
PRODUCTIZATION = REPO_ROOT / "implementation/phase1/release_evidence/productization"
DEFAULT_ROUNDTRIP = REPO_ROOT / "implementation/phase1/open_data/midas/midas_generator_33.optimized.roundtrip.json"
DEFAULT_CROSSVAL = PRODUCTIZATION / "commercial_solver_cross_validation.json"
_PLANAR_DOF_LABELS = ("UX", "UZ", "RY")


def _free_dof_labels(free: list[int]) -> tuple[str, ...]:
    return tuple(_PLANAR_DOF_LABELS[index % DOF_PER_NODE] for index in free)


def _remap_elements(
    elements: list[BeamElement],
    node_xyz: np.ndarray,
) -> tuple[list[BeamElement], np.ndarray]:
    used_nodes = sorted({elem.node_i for elem in elements} | {elem.node_j for elem in elements})
    remap = {old: new for new, old in enumerate(used_nodes)}
    node_xyz_sub = np.asarray([node_xyz[old] for old in used_nodes], dtype=np.float64)
    remapped: list[BeamElement] = []
    for elem in elements:
        i = remap[elem.node_i]
        j = remap[elem.node_j]
        pi = node_xyz_sub[i]
        pj = node_xyz_sub[j]
        remapped.append(
            BeamElement(
                elem_id=elem.elem_id,
                node_i=i,
                node_j=j,
                section_id=elem.section_id,
                material_id=elem.material_id,
                length_m=float(np.hypot(pj[0] - pi[0], pj[2] - pi[2])),
                node_i_xz=(float(pi[0]), float(pi[2])),
                node_j_xz=(float(pj[0]), float(pj[2])),
            )
        )
    return remapped, node_xyz_sub


def _select_modal_component(
    *,
    node_xyz: np.ndarray,
    edge_index: np.ndarray,
    elem_id: np.ndarray,
    elem_type_code: np.ndarray,
    elem_section_id: np.ndarray,
    elem_material_id: np.ndarray | None,
    max_elements: int,
) -> tuple[list[BeamElement], np.ndarray, int]:
    raw = _select_beam_submesh(
        node_xyz=node_xyz,
        edge_index=edge_index,
        elem_id=elem_id,
        elem_type_code=elem_type_code,
        elem_section_id=elem_section_id,
        elem_material_id=elem_material_id,
        max_elements=max_elements,
    )
    raw_count = len(raw)
    if not raw:
        return [], np.zeros((0, 3), dtype=np.float64), raw_count
    remapped, node_xyz_sub = _remap_elements(raw, node_xyz)
    component = _select_vertical_chain_elements(elements=remapped, node_xyz=node_xyz_sub)
    component, component_nodes = _remap_elements(component, node_xyz_sub)
    return component, component_nodes, raw_count


def _restrained_free_dofs(node_xyz: np.ndarray) -> tuple[list[int], list[int], list[int]]:
    n_nodes = int(node_xyz.shape[0])
    if n_nodes == 0:
        return [], [], []
    z_vals = np.asarray(node_xyz[:, 2], dtype=np.float64)
    z_min = float(np.min(z_vals))
    base_nodes = [idx for idx, z in enumerate(z_vals.tolist()) if abs(float(z) - z_min) <= 0.05]
    restrained: set[int] = set()
    for node in base_nodes:
        restrained.update(_node_dof_indices(node))
    free = [idx for idx in range(n_nodes * DOF_PER_NODE) if idx not in restrained]
    return base_nodes, sorted(restrained), free


def _lumped_mass_diagonal(
    *,
    elements: list[BeamElement],
    n_nodes: int,
    section_props: dict[int, dict[str, Any]],
    material_props: dict[int, dict[str, Any]],
) -> np.ndarray:
    mass = np.zeros(n_nodes * DOF_PER_NODE, dtype=np.float64)
    for elem in elements:
        props, _used_real = _element_beam_props(
            elem,
            section_props=section_props,
            material_props=material_props,
        )
        member_mass = max(float(props.area_m2) * float(elem.length_m) * 7850.0, 1.0e-9)
        for node in (elem.node_i, elem.node_j):
            ux, uz, ry = _node_dof_indices(node)
            mass[ux] += 0.5 * member_mass
            mass[uz] += 0.5 * member_mass
            mass[ry] += member_mass * max(float(elem.length_m) ** 2, 1.0e-9) / 24.0
    positive = mass[mass > 0.0]
    floor = float(np.min(positive)) * 1.0e-6 if positive.size else 1.0e-9
    mass[mass <= 0.0] = max(floor, 1.0e-9)
    return mass


def _modal_solve(
    *,
    k_global: np.ndarray,
    mass_diag: np.ndarray,
    free: list[int],
    mode_count: int,
    characteristic_length: float,
) -> dict[str, Any]:
    if not free:
        return {"status": "blocked", "blockers": ["no_free_dofs"], "modes": []}
    k_ff = np.asarray(k_global[np.ix_(free, free)], dtype=np.float64)
    k_ff = 0.5 * (k_ff + k_ff.T)
    m_ff = np.maximum(np.asarray(mass_diag[free], dtype=np.float64), 1.0e-9)
    scale = np.sqrt(m_ff)
    a = (k_ff / scale[:, None]) / scale[None, :]
    a = 0.5 * (a + a.T)
    eigvals, eigvecs = np.linalg.eigh(a)
    positive = [(float(v), idx) for idx, v in enumerate(eigvals.tolist()) if float(v) > 1.0e-8]
    positive.sort(key=lambda item: item[0])
    modes: list[dict[str, Any]] = []
    for mode_index, (omega_sq, eig_index) in enumerate(positive[: max(1, int(mode_count))], start=1):
        vector_free = eigvecs[:, eig_index] / scale
        norm = max(float(np.max(np.abs(vector_free))), 1.0e-12)
        vector_free = vector_free / norm
        elastic_force = k_ff @ vector_free
        inertia_force = omega_sq * m_ff * vector_free
        equation_scaling = build_equation_scaling_6dof(
            reference_force=max(
                1.0,
                float(np.linalg.norm(elastic_force, ord=np.inf)),
                float(np.linalg.norm(inertia_force, ord=np.inf)),
            ),
            characteristic_length=characteristic_length,
            residual=elastic_force - inertia_force,
            increment=vector_free,
            tangent=k_ff,
            dof_labels=_free_dof_labels(free),
        )
        modes.append(
            {
                "mode_id": mode_index,
                "omega_rad_s": float(np.sqrt(omega_sq)),
                "frequency_hz": float(np.sqrt(omega_sq) / (2.0 * np.pi)),
                "period_s": float((2.0 * np.pi) / max(np.sqrt(omega_sq), 1.0e-12)),
                "free_dof_shape_head": [float(v) for v in vector_free[:12].tolist()],
                "modal_mass_normalized": False,
                "mode_shape_normalization": "max_abs_free_dof_equals_one",
                "equation_scaling_6dof": equation_scaling.to_dict(),
            }
        )
    residual_gate_pass = bool(
        modes
        and all(
            float(mode["equation_scaling_6dof"]["scaled_residual_norm"]) <= 1.0e-8
            for mode in modes
        )
    )
    return {
        "status": "ready" if residual_gate_pass else "blocked",
        "mode_count": len(modes),
        "modes": modes,
        "residual_gate_pass": residual_gate_pass,
        "final_reassembled_residual_pass": residual_gate_pass,
        "fallback_used": False,
        "regularization_used": False,
        "blockers": (
            []
            if residual_gate_pass
            else [
                "modal_equilibrium_residual_gate_failed"
                if modes
                else "positive_modal_eigenvalues_missing"
            ]
        ),
    }


def _buckling_solve(
    *,
    k_elastic: np.ndarray,
    k_geometric_total: np.ndarray,
    free: list[int],
    element_euler_factors: list[float],
    characteristic_length: float,
) -> dict[str, Any]:
    if not free:
        return {"status": "blocked", "blockers": ["no_free_dofs"]}
    kg = np.asarray(k_elastic - k_geometric_total, dtype=np.float64)
    k_ff = 0.5 * (k_elastic[np.ix_(free, free)] + k_elastic[np.ix_(free, free)].T)
    kg_ff = 0.5 * (kg[np.ix_(free, free)] + kg[np.ix_(free, free)].T)
    eig_kg, vec_kg = np.linalg.eigh(kg_ff)
    kg_limit = max(float(np.max(eig_kg)) * 1.0e-8, 1.0e-9) if eig_kg.size else 1.0e-9
    keep = eig_kg > kg_limit
    factors: list[float] = []
    critical_vector: np.ndarray | None = None
    factor_source = "generalized_eigen"
    generalized_values, generalized_vectors = eig(
        k_ff,
        kg_ff,
        check_finite=True,
    )
    positive: list[tuple[float, int]] = []
    for index, value in enumerate(generalized_values):
        real = float(value.real)
        imaginary = abs(float(value.imag))
        if (
            np.isfinite(real)
            and imaginary <= 1.0e-8 * max(1.0, abs(real))
            and real > 1.0e-8
        ):
            positive.append((real, index))
    positive.sort(key=lambda item: item[0])
    factors = [value for value, _index in positive]
    if positive:
        critical_vector = np.asarray(
            generalized_vectors[:, positive[0][1]].real,
            dtype=np.float64,
        )
    if not factors and element_euler_factors:
        factors = list(element_euler_factors)
        factor_source = "euler_member_fallback"
    factors = sorted(factors)
    critical = float(factors[0]) if factors else 0.0
    equation_scaling = None
    if critical_vector is not None and critical > 0.0:
        norm = max(float(np.max(np.abs(critical_vector))), 1.0e-12)
        critical_vector = critical_vector / norm
        elastic_force = k_ff @ critical_vector
        geometric_force = critical * (kg_ff @ critical_vector)
        equation_scaling = build_equation_scaling_6dof(
            reference_force=max(
                1.0,
                float(np.linalg.norm(elastic_force, ord=np.inf)),
                float(np.linalg.norm(geometric_force, ord=np.inf)),
            ),
            characteristic_length=characteristic_length,
            residual=elastic_force - geometric_force,
            increment=critical_vector,
            tangent=k_ff,
            dof_labels=_free_dof_labels(free),
        )
    residual_gate_pass = bool(
        equation_scaling is not None
        and equation_scaling.scaled_residual_norm <= 1.0e-8
    )
    ready = bool(
        critical > 1.0
        and residual_gate_pass
        and factor_source == "generalized_eigen"
    )
    blockers: list[str] = []
    if critical <= 1.0:
        blockers.append("critical_buckling_factor_not_above_one")
    if not residual_gate_pass:
        blockers.append("buckling_equilibrium_residual_gate_failed")
    if factor_source != "generalized_eigen":
        blockers.append("buckling_generalized_eigen_fallback_used")
    return {
        "status": "ready" if ready else "blocked",
        "critical_load_factor": critical,
        "buckling_factor_head": factors[:5],
        "factor_source": factor_source,
        "geometric_stiffness_positive_rank": int(np.count_nonzero(keep)) if eig_kg.size else 0,
        "euler_member_factor_min": float(min(element_euler_factors)) if element_euler_factors else None,
        "equation_scaling_6dof": (
            equation_scaling.to_dict() if equation_scaling is not None else None
        ),
        "residual_gate_pass": residual_gate_pass,
        "final_reassembled_residual_pass": residual_gate_pass,
        "fallback_used": factor_source != "generalized_eigen",
        "regularization_used": False,
        "blockers": blockers,
    }


def _element_euler_factors(
    *,
    elements: list[BeamElement],
    axial_forces: dict[int, float],
    section_props: dict[int, dict[str, Any]],
    material_props: dict[int, dict[str, Any]],
) -> list[float]:
    factors: list[float] = []
    for elem in elements:
        props, _used_real = _element_beam_props(
            elem,
            section_props=section_props,
            material_props=material_props,
        )
        axial = float(axial_forces.get(elem.elem_id, 0.0))
        if axial <= 1.0e-9:
            continue
        ei = float(props.e_mpa) * 1.0e6 * float(props.iy_m4)
        pcr = float(np.pi**2 * ei / max(float(elem.length_m) ** 2, 1.0e-9))
        factors.append(pcr / axial)
    return factors


def _commercial_benchmark_contract(crossval_json: Path) -> dict[str, Any]:
    payload = load_json(crossval_json) if crossval_json.is_file() else {}
    summary = payload.get("modal_buckling_summary") if isinstance(payload.get("modal_buckling_summary"), dict) else {}
    pass_status = payload.get("status") in {"pass", "pass_with_marginal_metrics"}
    mac_min = summary.get("mode_shape_mac_hf_min")
    buck_min = summary.get("buckling_factor_hf_min")
    contract_pass = bool(
        pass_status
        and mac_min is not None
        and float(mac_min) >= 0.85
        and buck_min is not None
        and float(buck_min) > 1.0
    )
    return {
        "status": "pass" if contract_pass else "partial",
        "contract_pass": contract_pass,
        "source": str(crossval_json),
        "cross_validation_status": payload.get("status"),
        "modal_buckling_summary": summary,
        "equation_scaling_6dof": None,
        "equation_scaling_state": "unavailable",
        "equation_scaling_unavailable_reason": (
            "Paired commercial exports contain scalar comparison metrics but "
            "do not expose equation vectors or tangents."
        ),
        "note": "Benchmark tolerance comes from paired commercial HF/LF exports; native K/M/Kg solve is reported separately.",
    }


def run_mgt_native_modal_buckling_solver(
    *,
    roundtrip_json: Path = DEFAULT_ROUNDTRIP,
    roundtrip_npz: Path | None = None,
    commercial_crossval_json: Path = DEFAULT_CROSSVAL,
    output_json: Path | None = None,
    max_elements: int = 420,
    mode_count: int = 4,
) -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc).isoformat()
    roundtrip_npz = roundtrip_npz or roundtrip_json.with_suffix(".npz")
    if not roundtrip_npz.is_file():
        return {
            "schema_version": SCHEMA_VERSION,
            "generated_at": generated_at,
            "status": "blocked",
            "native_solver_ready": False,
            "blockers": ["roundtrip_npz_missing"],
        }

    provenance = build_mgt_reanalysis_provenance(roundtrip_json=roundtrip_json)
    mgt_path = Path(str(provenance.get("mgt_path") or ""))
    props = load_mgt_section_material_properties(mgt_path) if mgt_path.is_file() else {"sections": {}, "materials": {}}
    section_props = props.get("sections") if isinstance(props.get("sections"), dict) else {}
    material_props = props.get("materials") if isinstance(props.get("materials"), dict) else {}

    with np.load(roundtrip_npz, allow_pickle=False) as archive:
        elements, node_xyz_sub, raw_beam_count = _select_modal_component(
            node_xyz=np.asarray(archive["node_xyz"], dtype=np.float64),
            edge_index=np.asarray(archive["edge_index"], dtype=np.int64),
            elem_id=np.asarray(archive["elem_id"], dtype=np.int64),
            elem_type_code=np.asarray(archive["elem_type_code"], dtype=np.int32),
            elem_section_id=np.asarray(archive["elem_section_id"], dtype=np.int32),
            elem_material_id=np.asarray(archive["elem_material_id"], dtype=np.int32)
            if "elem_material_id" in archive
            else None,
            max_elements=max_elements,
        )

    blockers: list[str] = []
    if len(elements) < 2 or node_xyz_sub.shape[0] < 3:
        blockers.append("insufficient_modal_component")
    n_nodes = int(node_xyz_sub.shape[0])
    base_nodes, restrained, free = _restrained_free_dofs(node_xyz_sub)
    displacement = np.zeros(n_nodes * DOF_PER_NODE, dtype=np.float64)
    k_elastic, _ = _assemble_global(
        elements=elements,
        displacement=displacement,
        n_nodes=n_nodes,
        include_geometric=False,
        section_props=section_props,
        material_props=material_props,
    )
    mass_diag = _lumped_mass_diagonal(
        elements=elements,
        n_nodes=n_nodes,
        section_props=section_props,
        material_props=material_props,
    )
    axial_forces = _estimate_gravity_axial_forces(
        elements,
        section_props=section_props,
        material_props=material_props,
        load_scale=1.0,
    )
    k_geo_total, _ = _assemble_global(
        elements=elements,
        displacement=displacement,
        n_nodes=n_nodes,
        include_geometric=True,
        section_props=section_props,
        material_props=material_props,
        element_axial_forces=axial_forces,
    )
    characteristic_length = characteristic_length_from_coordinates(node_xyz_sub)
    modal = _modal_solve(
        k_global=k_elastic,
        mass_diag=mass_diag,
        free=free,
        mode_count=mode_count,
        characteristic_length=characteristic_length,
    )
    buckling = _buckling_solve(
        k_elastic=k_elastic,
        k_geometric_total=k_geo_total,
        free=free,
        element_euler_factors=_element_euler_factors(
            elements=elements,
            axial_forces=axial_forces,
            section_props=section_props,
            material_props=material_props,
        ),
        characteristic_length=characteristic_length,
    )
    benchmark = _commercial_benchmark_contract(commercial_crossval_json)
    modal_ready = modal.get("status") == "ready" and int(modal.get("mode_count") or 0) >= min(3, int(mode_count))
    buckling_ready = buckling.get("status") == "ready" and float(buckling.get("critical_load_factor") or 0.0) > 1.0
    real_coverage = 0.0
    if elements:
        real_count = sum(
            1
            for elem in elements
            if elem.section_id in section_props and elem.material_id in material_props
        )
        real_coverage = 100.0 * float(real_count) / float(len(elements))
    native_ready = bool(modal_ready and buckling_ready and real_coverage >= 99.0)
    if not modal_ready:
        blockers.extend(str(item) for item in modal.get("blockers") or ["modal_solver_not_ready"])
    if not buckling_ready:
        blockers.extend(str(item) for item in buckling.get("blockers") or ["buckling_solver_not_ready"])
    if real_coverage < 99.0:
        blockers.append("real_section_material_coverage_below_target")
    if not benchmark.get("contract_pass"):
        blockers.append("modal_buckling_benchmark_contract_not_pass")

    z_span = float(np.max(node_xyz_sub[:, 2]) - np.min(node_xyz_sub[:, 2])) if node_xyz_sub.size else 0.0
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "status": "ready" if native_ready and benchmark.get("contract_pass") else "partial",
        "native_solver_ready": native_ready,
        "benchmark_contract_pass": bool(benchmark.get("contract_pass")),
        "roundtrip_json": str(roundtrip_json),
        "roundtrip_npz": str(roundtrip_npz),
        "mgt_path": str(mgt_path),
        "solve_scope": "representative_native_beam_component",
        "claim_boundary": "Native in-repo K/M/Kg eigen solve for modal/buckling readiness; full-building nonlinear closure remains G1.",
        "mesh_fingerprint": {
            "raw_beam_elements_available": raw_beam_count,
            "beam_elements_solved": len(elements),
            "nodes_in_component": n_nodes,
            "dof_count": n_nodes * DOF_PER_NODE,
            "free_dof_count": len(free),
            "base_node_count": len(base_nodes),
            "z_span_m": z_span,
            "real_section_property_coverage_pct": real_coverage,
        },
        "matrices": {
            "stiffness_matrix_ready": bool(k_elastic.size and np.all(np.isfinite(k_elastic))),
            "mass_matrix_ready": bool(mass_diag.size and np.all(np.isfinite(mass_diag))),
            "geometric_stiffness_ready": bool(k_geo_total.size and np.all(np.isfinite(k_geo_total))),
            "restrained_dof_count": len(restrained),
        },
        "modal_solve": modal,
        "buckling_solve": buckling,
        "benchmark_contract": benchmark,
        "limitations": [
            "Representative component eigen solve; not a full 3D all-member modal model.",
            "Benchmark tolerance is paired commercial export evidence, not live licensed solver execution.",
        ],
        "blockers": blockers,
    }
    if output_json is not None:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--roundtrip-json", type=Path, default=DEFAULT_ROUNDTRIP)
    parser.add_argument("--roundtrip-npz", type=Path, default=None)
    parser.add_argument("--commercial-crossval-json", type=Path, default=DEFAULT_CROSSVAL)
    parser.add_argument("--output-json", type=Path, default=PRODUCTIZATION / "mgt_native_modal_buckling_solver.json")
    parser.add_argument("--max-elements", type=int, default=420)
    parser.add_argument("--mode-count", type=int, default=4)
    args = parser.parse_args()
    payload = run_mgt_native_modal_buckling_solver(
        roundtrip_json=args.roundtrip_json,
        roundtrip_npz=args.roundtrip_npz,
        commercial_crossval_json=args.commercial_crossval_json,
        output_json=args.output_json,
        max_elements=args.max_elements,
        mode_count=args.mode_count,
    )
    print(
        "mgt-native-modal-buckling: "
        f"status={payload['status']} modes={(payload.get('modal_solve') or {}).get('mode_count')} "
        f"critical={(payload.get('buckling_solve') or {}).get('critical_load_factor')} -> {args.output_json}"
    )
    return 0 if payload.get("status") == "ready" else 3


if __name__ == "__main__":
    raise SystemExit(main())
