#!/usr/bin/env python3
"""Build Phase 2 linear reference-path artifacts for the core API."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from typing import Any, Iterator

import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
for candidate in (SCRIPT_DIR, SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from release_evidence_metadata import git_head, input_checksums  # noqa: E402
from structural_analysis import (  # noqa: E402
    ANALYSIS_ENGINE_VERSION,
    CLAIM_BOUNDARY_VERSION,
    AnalysisConfig,
    analyze,
    load_model,
    validate,
)
from structural_analysis.assembly.linear_static import DOF_LABELS, assemble_linear_static  # noqa: E402
from structural_analysis.solvers.linear.static import (  # noqa: E402
    linear_static_residual,
    linear_static_tangent_jacobian,
)


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_ANALYTIC_MODEL_OUT = PRODUCTIZATION / "phase2_linear_reference_axial_bar_model.json"
DEFAULT_ANALYTIC_RESULT_OUT = PRODUCTIZATION / "phase2_linear_reference_axial_bar_result.json"
DEFAULT_ANALYTIC_REPORT_OUT = PRODUCTIZATION / "phase2_linear_reference_axial_bar_report.json"
DEFAULT_MECHANISM_MODEL_OUT = PRODUCTIZATION / "phase2_linear_reference_mechanism_model.json"
DEFAULT_MECHANISM_RESULT_OUT = PRODUCTIZATION / "phase2_linear_reference_mechanism_result.json"
DEFAULT_RIGID_BODY_MODEL_OUT = PRODUCTIZATION / "phase2_linear_reference_rigidbody_model.json"
DEFAULT_RIGID_BODY_RESULT_OUT = PRODUCTIZATION / "phase2_linear_reference_rigidbody_result.json"
DEFAULT_CONVERGENCE_OUT = PRODUCTIZATION / "phase2_linear_reference_convergence_suite.json"
DEFAULT_TANGENT_JACOBIAN_OUT = PRODUCTIZATION / "phase2_linear_reference_tangent_jacobian.json"
DEFAULT_SPARSE_BACKEND_OUT = PRODUCTIZATION / "phase2_linear_reference_sparse_backend.json"
DEFAULT_SUMMARY_OUT = PRODUCTIZATION / "phase2_linear_reference_summary.json"
SCHEMA_VERSION = "phase2-linear-reference-artifacts.v1"


def analytic_axial_bar_payload() -> dict[str, Any]:
    return {
        "schema_version": "structural-analysis-canonical-model.v1",
        "units": {"length": "m", "force": "kN"},
        "coordinate_system": {"axis_order": ["X", "Y", "Z"], "up_axis": "Z"},
        "nodes": [
            {"id": "N1", "coordinates": [0.0, 0.0, 0.0]},
            {"id": "N2", "coordinates": [2.0, 0.0, 0.0]},
        ],
        "elements": [
            {
                "id": "E1",
                "type": "truss",
                "nodes": ["N1", "N2"],
                "section": "S1",
                "material": "M1",
            }
        ],
        "materials": [{"id": "M1", "type": "elastic", "elastic_modulus": 200000.0}],
        "sections": [{"id": "S1", "type": "bar", "area": 0.01}],
        "loads": [{"id": "P1", "node": "N2", "components": [100.0, 0.0, 0.0]}],
        "supports": [
            {"id": "SUP1", "node": "N1", "dofs": "all"},
            {"id": "SUP2", "node": "N2", "dofs": ["UY", "UZ"]},
        ],
        "unsupported_features": [],
        "warnings": [],
        "metadata": {
            "case_id": "phase2_analytic_axial_bar",
            "truth_class": "analytic_truth",
            "expected_n2_ux": 0.1,
            "expected_reaction_n1_ux": -100.0,
            "claim_boundary": "single_linear_axial_bar_reference_path_only",
        },
    }


def mechanism_payload() -> dict[str, Any]:
    payload = analytic_axial_bar_payload()
    payload["supports"] = [{"id": "SUP1", "node": "N1", "dofs": "all"}]
    payload["metadata"] = {
        "case_id": "phase2_axial_bar_mechanism_guard",
        "truth_class": "negative_mechanism_guard",
        "claim_boundary": "mechanism_must_block_not_regularize_or_pass",
    }
    return payload


def rigid_body_payload() -> dict[str, Any]:
    payload = analytic_axial_bar_payload()
    payload["supports"] = [
        {"id": "SUP1", "node": "N1", "dofs": ["UY", "UZ"]},
        {"id": "SUP2", "node": "N2", "dofs": ["UY", "UZ"]},
    ]
    payload["metadata"] = {
        "case_id": "phase2_axial_bar_rigid_body_translation_guard",
        "truth_class": "negative_rigid_body_guard",
        "claim_boundary": "rigid_body_mode_must_block_not_regularize_or_pass",
    }
    return payload


def axial_chain_payload(*, element_count: int, load_fx: float) -> dict[str, Any]:
    if element_count <= 0:
        raise ValueError("element_count must be positive.")
    length = 2.0
    nodes = [
        {
            "id": f"N{index + 1}",
            "coordinates": [length * index / element_count, 0.0, 0.0],
        }
        for index in range(element_count + 1)
    ]
    elements = [
        {
            "id": f"E{index + 1}",
            "type": "truss",
            "nodes": [f"N{index + 1}", f"N{index + 2}"],
            "section": "S1",
            "material": "M1",
        }
        for index in range(element_count)
    ]
    supports = [{"id": "SUP1", "node": "N1", "dofs": "all"}]
    supports.extend(
        {
            "id": f"SUP{index + 1}",
            "node": f"N{index + 1}",
            "dofs": ["UY", "UZ"],
        }
        for index in range(1, element_count + 1)
    )
    return {
        "schema_version": "structural-analysis-canonical-model.v1",
        "units": {"length": "m", "force": "kN"},
        "coordinate_system": {"axis_order": ["X", "Y", "Z"], "up_axis": "Z"},
        "nodes": nodes,
        "elements": elements,
        "materials": [{"id": "M1", "type": "elastic", "elastic_modulus": 200000.0}],
        "sections": [{"id": "S1", "type": "bar", "area": 0.01}],
        "loads": [
            {
                "id": "P1",
                "node": f"N{element_count + 1}",
                "components": [load_fx, 0.0, 0.0],
            }
        ],
        "supports": supports,
        "unsupported_features": [],
        "warnings": [],
        "metadata": {
            "case_id": f"phase2_axial_chain_e{element_count}_load_{load_fx:g}",
            "truth_class": "analytic_truth",
            "expected_tip_ux": load_fx * length / (200000.0 * 0.01),
            "expected_base_reaction_ux": -load_fx,
            "claim_boundary": "linear_axial_mesh_load_scaling_reference_only",
        },
    }


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _payload_checksum(payload: dict[str, Any]) -> str:
    digest = hashlib.sha256(_json_text(payload).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _analyze_payload(payload: dict[str, Any], *, solver: str, tolerance: float) -> dict[str, Any]:
    with TemporaryDirectory() as tmp_dir:
        tmp_model = Path(tmp_dir) / "model.json"
        tmp_model.write_text(_json_text(payload), encoding="utf-8")
        model = load_model(tmp_model)
        result = analyze(
            model,
            AnalysisConfig(
                analysis_type="linear_static",
                solver=solver,
                tolerance=tolerance,
            ),
        )
    return result.to_dict()


def build_convergence_suite() -> dict[str, Any]:
    specs = [
        {"case_id": "mesh_e1_load_100", "element_count": 1, "load_fx": 100.0},
        {"case_id": "mesh_e2_load_100", "element_count": 2, "load_fx": 100.0},
        {"case_id": "mesh_e4_load_100", "element_count": 4, "load_fx": 100.0},
        {"case_id": "load_e4_load_50", "element_count": 4, "load_fx": 50.0},
    ]
    rows: list[dict[str, Any]] = []
    for spec in specs:
        payload = axial_chain_payload(
            element_count=int(spec["element_count"]),
            load_fx=float(spec["load_fx"]),
        )
        result = _analyze_payload(
            payload,
            solver=f"phase2_linear_reference_convergence_{spec['case_id']}",
            tolerance=1.0e-8,
        )
        metrics = result.get("metrics", {})
        tip_node = f"N{spec['element_count'] + 1}"
        expected_tip_ux = float(payload["metadata"]["expected_tip_ux"])
        expected_reaction_ux = float(payload["metadata"]["expected_base_reaction_ux"])
        actual_tip_ux = float(metrics["displacements"][tip_node]["UX"])
        actual_reaction_ux = float(metrics["reactions"]["N1"]["UX"])
        row_pass = (
            result["status"] == "ready"
            and abs(actual_tip_ux - expected_tip_ux) <= 1.0e-12
            and abs(actual_reaction_ux - expected_reaction_ux) <= 1.0e-12
            and float(metrics["relative_residual"]) <= 1.0e-8
            and float(metrics["energy_balance_error"]) <= 1.0e-10
            and metrics["regularization_used"] is False
            and metrics["fallback_used"] is False
            and metrics["residual_formula"] == "F_internal_minus_F_external"
            and metrics["stiffness_storage"] == "dense_numpy"
            and metrics["matrix_backend"] == "numpy_linalg_solve_dense"
            and metrics["sparse_backend_used"] is False
        )
        rows.append(
            {
                "case_id": spec["case_id"],
                "element_count": spec["element_count"],
                "load_fx": spec["load_fx"],
                "status": result["status"],
                "pass": row_pass,
                "model_checksum": _payload_checksum(payload),
                "expected_tip_ux": expected_tip_ux,
                "actual_tip_ux": actual_tip_ux,
                "tip_ux_abs_error": abs(actual_tip_ux - expected_tip_ux),
                "expected_base_reaction_ux": expected_reaction_ux,
                "actual_base_reaction_ux": actual_reaction_ux,
                "base_reaction_abs_error": abs(actual_reaction_ux - expected_reaction_ux),
                "relative_residual": metrics["relative_residual"],
                "energy_balance_error": metrics["energy_balance_error"],
                "regularization_used": metrics["regularization_used"],
                "fallback_used": metrics["fallback_used"],
                "residual_formula": metrics["residual_formula"],
                "stiffness_storage": metrics["stiffness_storage"],
                "matrix_backend": metrics["matrix_backend"],
                "sparse_backend_used": metrics["sparse_backend_used"],
            }
        )

    load_100_rows = [row for row in rows if row["load_fx"] == 100.0]
    mesh_tip_values = [float(row["actual_tip_ux"]) for row in load_100_rows]
    mesh_refinement_max_delta = max(mesh_tip_values) - min(mesh_tip_values)
    load_50 = next(row for row in rows if row["case_id"] == "load_e4_load_50")
    load_100_e4 = next(row for row in rows if row["case_id"] == "mesh_e4_load_100")
    load_scaling_ratio = float(load_50["actual_tip_ux"]) / float(load_100_e4["actual_tip_ux"])
    mesh_refinement_gate_passed = abs(mesh_refinement_max_delta) <= 1.0e-12
    load_step_scaling_gate_passed = abs(load_scaling_ratio - 0.5) <= 1.0e-12
    contract_pass = (
        all(bool(row["pass"]) for row in rows)
        and mesh_refinement_gate_passed
        and load_step_scaling_gate_passed
    )
    return {
        "schema_version": "phase2-linear-convergence-suite.v1",
        "status": "ready" if contract_pass else "blocked",
        "contract_pass": contract_pass,
        "case_count": len(rows),
        "truth_class": "analytic_truth",
        "residual_contract": "F_internal_minus_F_external",
        "mesh_refinement_gate_passed": mesh_refinement_gate_passed,
        "mesh_refinement_max_tip_delta": mesh_refinement_max_delta,
        "load_step_scaling_gate_passed": load_step_scaling_gate_passed,
        "load_scaling_ratio": load_scaling_ratio,
        "rows": rows,
        "claim_boundary": (
            "This is a deterministic axial-chain mesh/load scaling reference suite. "
            "It does not close general frame/shell/material nonlinear convergence."
        ),
    }


def _flatten_node_vector_rows(rows: dict[str, dict[str, float]]) -> list[float]:
    flattened: list[float] = []
    for node_id in sorted(rows):
        for label in DOF_LABELS:
            flattened.append(float(rows[node_id][label]))
    return flattened


def build_sparse_backend_verification(
    payload: dict[str, Any],
    mechanism_guard_payload: dict[str, Any],
    rigid_body_guard_payload: dict[str, Any],
    *,
    equivalence_tolerance: float = 1.0e-12,
) -> dict[str, Any]:
    with TemporaryDirectory() as tmp_dir:
        tmp_model = Path(tmp_dir) / "model.json"
        tmp_model.write_text(_json_text(payload), encoding="utf-8")
        model = load_model(tmp_model)

    dense_solution = analyze(
        model,
        AnalysisConfig(
            analysis_type="linear_static",
            solver="phase2_linear_reference_dense_api",
            tolerance=1.0e-8,
            matrix_backend="numpy_linalg_solve_dense",
        ),
    )
    sparse_solution = analyze(
        model,
        AnalysisConfig(
            analysis_type="linear_static",
            solver="phase2_linear_reference_sparse_api",
            tolerance=1.0e-8,
            matrix_backend="scipy_sparse_spsolve_cpu",
        ),
    )
    with TemporaryDirectory() as tmp_dir:
        mechanism_model_path = Path(tmp_dir) / "mechanism.json"
        rigid_body_model_path = Path(tmp_dir) / "rigid_body.json"
        mechanism_model_path.write_text(_json_text(mechanism_guard_payload), encoding="utf-8")
        rigid_body_model_path.write_text(_json_text(rigid_body_guard_payload), encoding="utf-8")
        mechanism_sparse_solution = analyze(
            load_model(mechanism_model_path),
            AnalysisConfig(
                analysis_type="linear_static",
                solver="phase2_linear_reference_sparse_mechanism_guard_api",
                tolerance=1.0e-8,
                matrix_backend="scipy_sparse_spsolve_cpu",
            ),
        )
        rigid_body_sparse_solution = analyze(
            load_model(rigid_body_model_path),
            AnalysisConfig(
                analysis_type="linear_static",
                solver="phase2_linear_reference_sparse_rigid_body_guard_api",
                tolerance=1.0e-8,
                matrix_backend="scipy_sparse_spsolve_cpu",
            ),
        )
    dense_metrics = dense_solution.metrics
    sparse_metrics = sparse_solution.metrics
    mechanism_kinds = {
        str(row.get("kind", "unsupported_feature"))
        for row in mechanism_sparse_solution.unsupported_features
    }
    rigid_body_kinds = {
        str(row.get("kind", "unsupported_feature"))
        for row in rigid_body_sparse_solution.unsupported_features
    }
    sparse_mechanism_blocked_without_regularization = (
        mechanism_sparse_solution.status == "blocked"
        and "linear_static_singular_stiffness" in mechanism_kinds
        and mechanism_sparse_solution.metrics["regularization_used"] is False
        and mechanism_sparse_solution.metrics["fallback_used"] is False
        and mechanism_sparse_solution.metrics["sparse_backend_used"] is True
    )
    sparse_rigid_body_blocked_without_regularization = (
        rigid_body_sparse_solution.status == "blocked"
        and "linear_static_singular_stiffness" in rigid_body_kinds
        and rigid_body_sparse_solution.metrics["regularization_used"] is False
        and rigid_body_sparse_solution.metrics["fallback_used"] is False
        and rigid_body_sparse_solution.metrics["sparse_backend_used"] is True
    )

    if dense_solution.status != "ready" or sparse_solution.status != "ready":
        return {
            "schema_version": "phase2-linear-sparse-backend-seed.v1",
            "status": "blocked",
            "contract_pass": False,
            "case_id": str(payload.get("metadata", {}).get("case_id", "unknown")),
            "truth_class": "analytic_truth",
            "residual_contract": "F_internal_minus_F_external",
            "dense_status": dense_solution.status,
            "sparse_status": sparse_solution.status,
            "claim_boundary": (
                "Sparse CPU backend seed verification is scoped to the canonical single-bar "
                "axial linear_static preview only. It does not close general frame/shell/"
                "material coupling, full-mesh/full-load nonlinear equilibrium, production "
                "sparse matrix backends, ROCm/HIP parity, or G1."
            ),
        }

    dense_displacements = _flatten_node_vector_rows(dense_metrics["displacements"])
    sparse_displacements = _flatten_node_vector_rows(sparse_metrics["displacements"])
    dense_reactions = _flatten_node_vector_rows(dense_metrics["reactions"])
    sparse_reactions = _flatten_node_vector_rows(sparse_metrics["reactions"])
    displacement_error = float(
        np.linalg.norm(
            np.asarray(dense_displacements) - np.asarray(sparse_displacements),
            ord=np.inf,
        )
    )
    reaction_error = float(
        np.linalg.norm(
            np.asarray(dense_reactions) - np.asarray(sparse_reactions),
            ord=np.inf,
        )
    )
    residual_error = abs(
        float(dense_metrics["residual_norm"]) - float(sparse_metrics["residual_norm"])
    )
    equivalence_gate_passed = (
        displacement_error <= equivalence_tolerance
        and reaction_error <= equivalence_tolerance
        and residual_error <= equivalence_tolerance
        and float(sparse_metrics["relative_residual"]) <= 1.0e-8
        and float(sparse_metrics["energy_balance_error"]) <= 1.0e-10
        and sparse_metrics["regularization_used"] is False
        and sparse_metrics["fallback_used"] is False
        and dense_metrics["regularization_used"] is False
        and dense_metrics["fallback_used"] is False
    )
    contract_pass = (
        equivalence_gate_passed
        and dense_metrics["stiffness_storage"] == "dense_numpy"
        and dense_metrics["matrix_backend"] == "numpy_linalg_solve_dense"
        and dense_metrics["sparse_backend_used"] is False
        and sparse_metrics["stiffness_storage"] == "scipy_sparse_csr"
        and sparse_metrics["matrix_backend"] == "scipy_sparse_spsolve_cpu"
        and sparse_metrics["sparse_backend_used"] is True
        and sparse_mechanism_blocked_without_regularization
        and sparse_rigid_body_blocked_without_regularization
    )
    return {
        "schema_version": "phase2-linear-sparse-backend-seed.v1",
        "status": "ready" if contract_pass else "blocked",
        "contract_pass": contract_pass,
        "case_id": str(payload.get("metadata", {}).get("case_id", "unknown")),
        "truth_class": "analytic_truth",
        "residual_contract": "F_internal_minus_F_external",
        "dense_stiffness_storage": dense_metrics["stiffness_storage"],
        "dense_matrix_backend": dense_metrics["matrix_backend"],
        "dense_sparse_backend_used": dense_metrics["sparse_backend_used"],
        "sparse_stiffness_storage": sparse_metrics["stiffness_storage"],
        "sparse_matrix_backend": sparse_metrics["matrix_backend"],
        "sparse_backend_used": sparse_metrics["sparse_backend_used"],
        "api_config_matrix_backend": "scipy_sparse_spsolve_cpu",
        "api_config_solver": "phase2_linear_reference_sparse_api",
        "canonical_api_sparse_route_used": True,
        "equivalence_gate_passed": equivalence_gate_passed,
        "displacement_inf_norm_error": displacement_error,
        "reaction_inf_norm_error": reaction_error,
        "residual_inf_norm_error": residual_error,
        "dense_relative_residual": dense_metrics["relative_residual"],
        "sparse_relative_residual": sparse_metrics["relative_residual"],
        "dense_energy_balance_error": dense_metrics["energy_balance_error"],
        "sparse_energy_balance_error": sparse_metrics["energy_balance_error"],
        "sparse_mechanism_blocked_without_regularization": (
            sparse_mechanism_blocked_without_regularization
        ),
        "sparse_rigid_body_blocked_without_regularization": (
            sparse_rigid_body_blocked_without_regularization
        ),
        "sparse_mechanism_unsupported_kinds": sorted(mechanism_kinds),
        "sparse_rigid_body_unsupported_kinds": sorted(rigid_body_kinds),
        "regularization_used": False,
        "fallback_used": False,
        "g1_closure_claim": False,
        "blockers_remaining": [
            "full_mesh_full_load_nonlinear_equilibrium_not_closed",
            "consistent_tangent_jacobian_newton_not_closed",
            "frame_shell_material_coupling_not_closed",
            "mesh_load_step_convergence_suite_not_closed",
            "sparse_matrix_backend_not_closed",
            "production_rocm_hip_parity_not_closed",
        ],
        "claim_boundary": (
            "This verifies a deterministic scipy CSR assembly and scipy.sparse.linalg.spsolve "
            "CPU backend for the canonical axial linear_static preview, with dense-vs-sparse "
            "displacement/reaction/residual equivalence on the analytic single-bar reference. "
            "It does not close general frame/shell/material coupling, full-mesh/full-load "
            "nonlinear equilibrium, production sparse matrix backends, ROCm/HIP parity, or G1."
        ),
    }


def build_tangent_jacobian_verification(
    payload: dict[str, Any],
    *,
    finite_difference_epsilon: float = 1.0e-8,
    finite_difference_tolerance: float = 1.0e-6,
) -> dict[str, Any]:
    with TemporaryDirectory() as tmp_dir:
        tmp_model = Path(tmp_dir) / "model.json"
        tmp_model.write_text(_json_text(payload), encoding="utf-8")
        model = load_model(tmp_model)
    assembly, unsupported = assemble_linear_static(model)
    if assembly is None or unsupported:
        return {
            "schema_version": "phase2-linear-tangent-jacobian.v1",
            "status": "blocked",
            "contract_pass": False,
            "case_id": str(payload.get("metadata", {}).get("case_id", "unknown")),
            "truth_class": "analytic_truth",
            "residual_contract": "F_internal_minus_F_external",
            "unsupported_features": unsupported,
            "claim_boundary": (
                "Tangent/Jacobian verification is scoped to the canonical single-bar "
                "axial linear_static preview only. It does not close nonlinear Newton, "
                "frame/shell/material coupling, sparse production backends, or G1."
            ),
        }

    constrained = set(assembly.constrained_dofs)
    all_dofs = set(range(assembly.loads.shape[0]))
    free = sorted(all_dofs - constrained)
    free_stiffness = assembly.stiffness[np.ix_(free, free)]
    try:
        free_displacements = np.linalg.solve(free_stiffness, assembly.loads[free])
    except np.linalg.LinAlgError as exc:
        return {
            "schema_version": "phase2-linear-tangent-jacobian.v1",
            "status": "blocked",
            "contract_pass": False,
            "case_id": str(payload.get("metadata", {}).get("case_id", "unknown")),
            "truth_class": "analytic_truth",
            "residual_contract": "F_internal_minus_F_external",
            "detail": str(exc),
            "claim_boundary": (
                "Tangent/Jacobian verification is scoped to the canonical single-bar "
                "axial linear_static preview only. It does not close nonlinear Newton, "
                "frame/shell/material coupling, sparse production backends, or G1."
            ),
        }

    displacements = np.zeros(assembly.loads.shape[0], dtype=float)
    displacements[free] = free_displacements
    tangent = linear_static_tangent_jacobian(assembly)
    residual_at_equilibrium = linear_static_residual(assembly, displacements)
    free_residual_norm = (
        float(np.linalg.norm(residual_at_equilibrium[free], ord=np.inf)) if free else 0.0
    )
    tangent_equals_stiffness_error = float(
        np.linalg.norm(tangent - assembly.stiffness, ord=np.inf)
    )
    tangent_free_block_error = float(
        np.linalg.norm(tangent[np.ix_(free, free)] - free_stiffness, ord=np.inf)
    )

    fd_rows: list[dict[str, Any]] = []
    max_fd_column_error = 0.0
    for free_dof in free:
        perturbed = displacements.copy()
        perturbed[free_dof] += finite_difference_epsilon
        fd_column = (
            linear_static_residual(assembly, perturbed)
            - linear_static_residual(assembly, displacements)
        ) / finite_difference_epsilon
        analytic_column = tangent[:, free_dof]
        column_error = float(np.linalg.norm(fd_column - analytic_column, ord=np.inf))
        max_fd_column_error = max(max_fd_column_error, column_error)
        fd_rows.append(
            {
                "free_dof_index": free_dof,
                "finite_difference_epsilon": finite_difference_epsilon,
                "column_inf_norm_error": column_error,
                "pass": column_error <= finite_difference_tolerance,
            }
        )

    tangent_equals_stiffness_gate_passed = tangent_equals_stiffness_error <= 1.0e-15
    tangent_free_block_gate_passed = tangent_free_block_error <= 1.0e-15
    finite_difference_gate_passed = max_fd_column_error <= finite_difference_tolerance
    equilibrium_residual_gate_passed = free_residual_norm <= 1.0e-12
    contract_pass = (
        tangent_equals_stiffness_gate_passed
        and tangent_free_block_gate_passed
        and finite_difference_gate_passed
        and equilibrium_residual_gate_passed
        and len(free) > 0
    )
    return {
        "schema_version": "phase2-linear-tangent-jacobian.v1",
        "status": "ready" if contract_pass else "blocked",
        "contract_pass": contract_pass,
        "case_id": str(payload.get("metadata", {}).get("case_id", "unknown")),
        "truth_class": "analytic_truth",
        "residual_contract": "F_internal_minus_F_external",
        "residual_formula": "F_internal_minus_F_external",
        "tangent_jacobian_definition": "dR_du_equals_assembled_dense_stiffness",
        "stiffness_storage": assembly.stiffness_storage,
        "stiffness_order": int(assembly.stiffness.shape[0]),
        "free_dof_count": len(free),
        "free_dof_indices": free,
        "equilibrium_free_residual_inf_norm": free_residual_norm,
        "equilibrium_residual_gate_passed": equilibrium_residual_gate_passed,
        "tangent_equals_stiffness_inf_norm_error": tangent_equals_stiffness_error,
        "tangent_equals_stiffness_gate_passed": tangent_equals_stiffness_gate_passed,
        "tangent_free_block_inf_norm_error": tangent_free_block_error,
        "tangent_free_block_gate_passed": tangent_free_block_gate_passed,
        "finite_difference_epsilon": finite_difference_epsilon,
        "finite_difference_tolerance": finite_difference_tolerance,
        "finite_difference_free_dof_count": len(fd_rows),
        "finite_difference_max_column_inf_norm_error": max_fd_column_error,
        "finite_difference_gate_passed": finite_difference_gate_passed,
        "finite_difference_rows": fd_rows,
        "regularization_used": False,
        "fallback_used": False,
        "sparse_backend_used": False,
        "g1_closure_claim": False,
        "nonlinear_newton_closure_claim": False,
        "claim_boundary": (
            "This verifies that the canonical axial linear_static preview uses "
            "R(u)=F_internal(u)-F_external with tangent dR/du equal to the assembled "
            "dense stiffness matrix, checked by finite-difference perturbations over "
            "free DOFs. It does not close general nonlinear Newton/Jacobian gates, "
            "frame/shell/material coupling, sparse production backends, or G1."
        ),
    }


@contextmanager
def _payload_path(
    *,
    repo_root: Path,
    out_path: Path,
    payload: dict[str, Any],
    write_model: bool,
) -> Iterator[Path]:
    if write_model:
        resolved = out_path if out_path.is_absolute() else repo_root / out_path
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(_json_text(payload), encoding="utf-8")
        yield resolved
        return
    with TemporaryDirectory() as tmp_dir:
        tmp_model = Path(tmp_dir) / out_path.name
        tmp_model.write_text(_json_text(payload), encoding="utf-8")
        yield tmp_model


def build_linear_reference_artifacts(
    *,
    repo_root: Path = ROOT,
    analytic_model_out: Path = DEFAULT_ANALYTIC_MODEL_OUT,
    analytic_result_out: Path = DEFAULT_ANALYTIC_RESULT_OUT,
    analytic_report_out: Path = DEFAULT_ANALYTIC_REPORT_OUT,
    mechanism_model_out: Path = DEFAULT_MECHANISM_MODEL_OUT,
    mechanism_result_out: Path = DEFAULT_MECHANISM_RESULT_OUT,
    rigid_body_model_out: Path = DEFAULT_RIGID_BODY_MODEL_OUT,
    rigid_body_result_out: Path = DEFAULT_RIGID_BODY_RESULT_OUT,
    convergence_out: Path = DEFAULT_CONVERGENCE_OUT,
    tangent_jacobian_out: Path = DEFAULT_TANGENT_JACOBIAN_OUT,
    sparse_backend_out: Path = DEFAULT_SPARSE_BACKEND_OUT,
    summary_out: Path = DEFAULT_SUMMARY_OUT,
    write_models: bool = False,
) -> dict[str, dict[str, Any]]:
    repo_root = repo_root.resolve()
    analytic_payload = analytic_axial_bar_payload()
    mechanism_guard_payload = mechanism_payload()
    rigid_body_guard_payload = rigid_body_payload()

    with _payload_path(
        repo_root=repo_root,
        out_path=analytic_model_out,
        payload=analytic_payload,
        write_model=write_models,
    ) as analytic_path:
        analytic_model = load_model(analytic_path)
        analytic_result = analyze(
            analytic_model,
            AnalysisConfig(
                analysis_type="linear_static",
                solver="phase2_linear_reference_axial_bar",
                tolerance=1.0e-8,
            ),
        )
        analytic_report = validate(
            analytic_result,
            {
                "residual_formula": "F_internal_minus_F_external",
                "regularization_used": False,
                "fallback_used": False,
            },
        )

    with _payload_path(
        repo_root=repo_root,
        out_path=mechanism_model_out,
        payload=mechanism_guard_payload,
        write_model=write_models,
    ) as mechanism_path:
        mechanism_model = load_model(mechanism_path)
        mechanism_result = analyze(
            mechanism_model,
            AnalysisConfig(
                analysis_type="linear_static",
                solver="phase2_linear_reference_mechanism_guard",
                tolerance=1.0e-8,
            ),
        )

    with _payload_path(
        repo_root=repo_root,
        out_path=rigid_body_model_out,
        payload=rigid_body_guard_payload,
        write_model=write_models,
    ) as rigid_body_path:
        rigid_body_model = load_model(rigid_body_path)
        rigid_body_result = analyze(
            rigid_body_model,
            AnalysisConfig(
                analysis_type="linear_static",
                solver="phase2_linear_reference_rigid_body_guard",
                tolerance=1.0e-8,
            ),
        )

    analytic_result_payload = analytic_result.to_dict()
    analytic_report_payload = analytic_report.to_dict()
    mechanism_result_payload = mechanism_result.to_dict()
    rigid_body_result_payload = rigid_body_result.to_dict()
    convergence_payload = build_convergence_suite()
    tangent_jacobian_payload = build_tangent_jacobian_verification(analytic_payload)
    sparse_backend_payload = build_sparse_backend_verification(
        analytic_payload,
        mechanism_guard_payload,
        rigid_body_guard_payload,
    )
    metrics = analytic_result_payload["metrics"]
    unsupported_kinds = {
        str(row.get("kind", "unsupported_feature"))
        for row in mechanism_result_payload.get("unsupported_features", [])
    }
    rigid_body_unsupported_kinds = {
        str(row.get("kind", "unsupported_feature"))
        for row in rigid_body_result_payload.get("unsupported_features", [])
    }
    expected_displacement = float(analytic_payload["metadata"]["expected_n2_ux"])
    actual_displacement = float(metrics["displacements"]["N2"]["UX"])
    expected_reaction = float(analytic_payload["metadata"]["expected_reaction_n1_ux"])
    actual_reaction = float(metrics["reactions"]["N1"]["UX"])
    displacement_error = abs(actual_displacement - expected_displacement)
    reaction_error = abs(actual_reaction - expected_reaction)
    residual_gate_passed = (
        analytic_result_payload["status"] == "ready"
        and float(metrics["relative_residual"]) <= 1.0e-8
    )
    energy_gate_passed = float(metrics["energy_balance_error"]) <= 1.0e-10
    mechanism_blocked = (
        mechanism_result_payload["status"] == "blocked"
        and "linear_static_singular_stiffness" in unsupported_kinds
        and mechanism_result_payload["metrics"]["regularization_used"] is False
        and mechanism_result_payload["metrics"]["fallback_used"] is False
        and mechanism_result_payload["metrics"]["sparse_backend_used"] is False
    )
    rigid_body_blocked = (
        rigid_body_result_payload["status"] == "blocked"
        and "linear_static_singular_stiffness" in rigid_body_unsupported_kinds
        and rigid_body_result_payload["metrics"]["regularization_used"] is False
        and rigid_body_result_payload["metrics"]["fallback_used"] is False
        and rigid_body_result_payload["metrics"]["sparse_backend_used"] is False
        and rigid_body_result_payload["metrics"].get("free_stiffness_order") == 2
    )
    matrix_backend_gate_passed = (
        metrics["stiffness_storage"] == "dense_numpy"
        and metrics["matrix_backend"] == "numpy_linalg_solve_dense"
        and metrics["sparse_backend_used"] is False
    )
    contract_pass = (
        bool(analytic_report_payload["contract_pass"])
        and residual_gate_passed
        and energy_gate_passed
        and displacement_error <= 1.0e-12
        and reaction_error <= 1.0e-12
        and mechanism_blocked
        and rigid_body_blocked
        and matrix_backend_gate_passed
        and bool(convergence_payload["contract_pass"])
        and bool(tangent_jacobian_payload["contract_pass"])
        and bool(sparse_backend_payload["contract_pass"])
        and metrics["residual_formula"] == "F_internal_minus_F_external"
        and metrics["regularization_used"] is False
        and metrics["fallback_used"] is False
    )
    summary_payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit_sha": git_head(repo_root),
        "engine_version": ANALYSIS_ENGINE_VERSION,
        "input_checksums": input_checksums(
            [
                Path("src/structural_analysis/assembly/linear_static.py"),
                Path("src/structural_analysis/solvers/linear/static.py"),
                Path("src/structural_analysis/api/core.py"),
                Path("src/structural_analysis/schemas/result.schema.json"),
            ],
            repo_root=repo_root,
        ),
        "status": "ready" if contract_pass else "blocked",
        "contract_pass": contract_pass,
        "claim_boundary_version": CLAIM_BOUNDARY_VERSION,
        "g1_closure_claim": False,
        "analysis_type": "linear_static",
        "truth_class": "analytic_truth",
        "residual_contract": "F_internal_minus_F_external",
        "residual_gate_passed": residual_gate_passed,
        "energy_gate_passed": energy_gate_passed,
        "mechanism_blocked_without_regularization": mechanism_blocked,
        "rigid_body_blocked_without_regularization": rigid_body_blocked,
        "matrix_backend_gate_passed": matrix_backend_gate_passed,
        "stiffness_storage": metrics["stiffness_storage"],
        "matrix_backend": metrics["matrix_backend"],
        "sparse_backend_used": metrics["sparse_backend_used"],
        "linear_axial_convergence_suite_ready": bool(convergence_payload["contract_pass"]),
        "linear_axial_convergence_case_count": convergence_payload["case_count"],
        "mesh_refinement_gate_passed": convergence_payload["mesh_refinement_gate_passed"],
        "load_step_scaling_gate_passed": convergence_payload["load_step_scaling_gate_passed"],
        "linear_axial_tangent_jacobian_verification_ready": bool(
            tangent_jacobian_payload["contract_pass"]
        ),
        "tangent_jacobian_gate_passed": bool(tangent_jacobian_payload["contract_pass"]),
        "tangent_jacobian_finite_difference_gate_passed": bool(
            tangent_jacobian_payload["finite_difference_gate_passed"]
        ),
        "tangent_jacobian_equals_stiffness_gate_passed": bool(
            tangent_jacobian_payload["tangent_equals_stiffness_gate_passed"]
        ),
        "sparse_backend_seed_verification_ready": bool(sparse_backend_payload["contract_pass"]),
        "sparse_backend_api_path_verification_ready": bool(
            sparse_backend_payload.get("canonical_api_sparse_route_used")
            and sparse_backend_payload["contract_pass"]
        ),
        "sparse_backend_api_config_matrix_backend": sparse_backend_payload[
            "api_config_matrix_backend"
        ],
        "sparse_backend_api_config_solver": sparse_backend_payload["api_config_solver"],
        "sparse_backend_equivalence_gate_passed": bool(
            sparse_backend_payload["equivalence_gate_passed"]
        ),
        "sparse_mechanism_blocked_without_regularization": bool(
            sparse_backend_payload["sparse_mechanism_blocked_without_regularization"]
        ),
        "sparse_rigid_body_blocked_without_regularization": bool(
            sparse_backend_payload["sparse_rigid_body_blocked_without_regularization"]
        ),
        "sparse_backend_seed_stiffness_storage": sparse_backend_payload["sparse_stiffness_storage"],
        "sparse_backend_seed_matrix_backend": sparse_backend_payload["sparse_matrix_backend"],
        "regularization_used": metrics["regularization_used"],
        "fallback_used": metrics["fallback_used"],
        "expected": {
            "n2_ux": expected_displacement,
            "n1_reaction_ux": expected_reaction,
            "analytic_model_checksum": _payload_checksum(analytic_payload),
        },
        "actual": {
            "n2_ux": actual_displacement,
            "n1_reaction_ux": actual_reaction,
            "relative_residual": metrics["relative_residual"],
            "energy_balance_error": metrics["energy_balance_error"],
        },
        "errors": {
            "n2_ux_abs": displacement_error,
            "n1_reaction_ux_abs": reaction_error,
        },
        "blockers_remaining": [
            "full_mesh_full_load_nonlinear_equilibrium_not_closed",
            "consistent_tangent_jacobian_newton_not_closed",
            "frame_shell_material_coupling_not_closed",
            "mesh_load_step_convergence_suite_not_closed",
            "sparse_matrix_backend_not_closed",
            "production_rocm_hip_parity_not_closed",
        ],
        "artifacts": {
            "analytic_model": str(analytic_model_out),
            "analytic_result": str(analytic_result_out),
            "analytic_validation_report": str(analytic_report_out),
            "mechanism_model": str(mechanism_model_out),
            "mechanism_result": str(mechanism_result_out),
            "rigid_body_model": str(rigid_body_model_out),
            "rigid_body_result": str(rigid_body_result_out),
            "convergence_suite": str(convergence_out),
            "tangent_jacobian": str(tangent_jacobian_out),
            "sparse_backend": str(sparse_backend_out),
            "summary": str(summary_out),
        },
        "claim_boundary": (
            "This proves the canonical API has a deterministic single-bar axial "
            "linear reference path with residual R=F_internal-F_external, energy "
            "balance, dense-numpy matrix backend metadata, a singular-mechanism/"
            "rigid-body translation guard that blocks without regularization, a small "
            "axial mesh/load scaling convergence scorecard, a narrow tangent/Jacobian "
            "verification showing that dR/du equals the assembled dense stiffness for the "
            "axial linear preview with finite-difference checks over free DOFs, and a narrow "
            "CPU scipy sparse CSR assembly/spsolve seed that is selectable through the canonical "
            "AnalysisConfig matrix_backend path with dense-vs-sparse equivalence on the analytic "
            "single-bar reference. It does not close G1 full-mesh/full-load nonlinear "
            "equilibrium, material Newton breadth, general frame-shell convergence, production "
            "sparse matrix backends, or production GPU/HIP gates."
        ),
    }
    return {
        "analytic_model": analytic_payload,
        "analytic_result": analytic_result_payload,
        "analytic_report": analytic_report_payload,
        "mechanism_model": mechanism_guard_payload,
        "mechanism_result": mechanism_result_payload,
        "rigid_body_model": rigid_body_guard_payload,
        "rigid_body_result": rigid_body_result_payload,
        "convergence_suite": convergence_payload,
        "tangent_jacobian": tangent_jacobian_payload,
        "sparse_backend": sparse_backend_payload,
        "summary": summary_payload,
    }


def _strip_volatile(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {
            key: _strip_volatile(value)
            for key, value in payload.items()
            if key not in {"generated_at"}
        }
    if isinstance(payload, list):
        return [_strip_volatile(item) for item in payload]
    return payload


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object.")
    return payload


def check_linear_reference_artifacts(
    *,
    repo_root: Path = ROOT,
    analytic_model_out: Path = DEFAULT_ANALYTIC_MODEL_OUT,
    analytic_result_out: Path = DEFAULT_ANALYTIC_RESULT_OUT,
    analytic_report_out: Path = DEFAULT_ANALYTIC_REPORT_OUT,
    mechanism_model_out: Path = DEFAULT_MECHANISM_MODEL_OUT,
    mechanism_result_out: Path = DEFAULT_MECHANISM_RESULT_OUT,
    rigid_body_model_out: Path = DEFAULT_RIGID_BODY_MODEL_OUT,
    rigid_body_result_out: Path = DEFAULT_RIGID_BODY_RESULT_OUT,
    convergence_out: Path = DEFAULT_CONVERGENCE_OUT,
    tangent_jacobian_out: Path = DEFAULT_TANGENT_JACOBIAN_OUT,
    sparse_backend_out: Path = DEFAULT_SPARSE_BACKEND_OUT,
    summary_out: Path = DEFAULT_SUMMARY_OUT,
) -> tuple[bool, str]:
    expected = build_linear_reference_artifacts(
        repo_root=repo_root,
        analytic_model_out=analytic_model_out,
        analytic_result_out=analytic_result_out,
        analytic_report_out=analytic_report_out,
        mechanism_model_out=mechanism_model_out,
        mechanism_result_out=mechanism_result_out,
        rigid_body_model_out=rigid_body_model_out,
        rigid_body_result_out=rigid_body_result_out,
        convergence_out=convergence_out,
        tangent_jacobian_out=tangent_jacobian_out,
        sparse_backend_out=sparse_backend_out,
        summary_out=summary_out,
        write_models=False,
    )
    targets = {
        "analytic_model": analytic_model_out,
        "analytic_result": analytic_result_out,
        "analytic_report": analytic_report_out,
        "mechanism_model": mechanism_model_out,
        "mechanism_result": mechanism_result_out,
        "rigid_body_model": rigid_body_model_out,
        "rigid_body_result": rigid_body_result_out,
        "convergence_suite": convergence_out,
        "tangent_jacobian": tangent_jacobian_out,
        "sparse_backend": sparse_backend_out,
        "summary": summary_out,
    }
    for key, path in targets.items():
        resolved = path if path.is_absolute() else repo_root / path
        if not resolved.exists():
            return False, f"phase2_linear_reference_missing:{path.as_posix()}"
        try:
            existing = _read_json(resolved)
        except Exception as exc:
            return False, (
                f"phase2_linear_reference_unreadable:{path.as_posix()}:"
                f"{exc.__class__.__name__}"
            )
        if _strip_volatile(existing) != _strip_volatile(expected[key]):
            return False, f"phase2_linear_reference_mismatch:{key}"
    return True, "phase2_linear_reference_consistent"


def write_linear_reference_artifacts(
    *,
    repo_root: Path = ROOT,
    analytic_model_out: Path = DEFAULT_ANALYTIC_MODEL_OUT,
    analytic_result_out: Path = DEFAULT_ANALYTIC_RESULT_OUT,
    analytic_report_out: Path = DEFAULT_ANALYTIC_REPORT_OUT,
    mechanism_model_out: Path = DEFAULT_MECHANISM_MODEL_OUT,
    mechanism_result_out: Path = DEFAULT_MECHANISM_RESULT_OUT,
    rigid_body_model_out: Path = DEFAULT_RIGID_BODY_MODEL_OUT,
    rigid_body_result_out: Path = DEFAULT_RIGID_BODY_RESULT_OUT,
    convergence_out: Path = DEFAULT_CONVERGENCE_OUT,
    tangent_jacobian_out: Path = DEFAULT_TANGENT_JACOBIAN_OUT,
    sparse_backend_out: Path = DEFAULT_SPARSE_BACKEND_OUT,
    summary_out: Path = DEFAULT_SUMMARY_OUT,
) -> dict[str, dict[str, Any]]:
    artifacts = build_linear_reference_artifacts(
        repo_root=repo_root,
        analytic_model_out=analytic_model_out,
        analytic_result_out=analytic_result_out,
        analytic_report_out=analytic_report_out,
        mechanism_model_out=mechanism_model_out,
        mechanism_result_out=mechanism_result_out,
        rigid_body_model_out=rigid_body_model_out,
        rigid_body_result_out=rigid_body_result_out,
        convergence_out=convergence_out,
        tangent_jacobian_out=tangent_jacobian_out,
        sparse_backend_out=sparse_backend_out,
        summary_out=summary_out,
        write_models=True,
    )
    for key, path in {
        "analytic_result": analytic_result_out,
        "analytic_report": analytic_report_out,
        "mechanism_result": mechanism_result_out,
        "rigid_body_result": rigid_body_result_out,
        "convergence_suite": convergence_out,
        "tangent_jacobian": tangent_jacobian_out,
        "sparse_backend": sparse_backend_out,
        "summary": summary_out,
    }.items():
        resolved = path if path.is_absolute() else repo_root / path
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(_json_text(artifacts[key]), encoding="utf-8")
    return artifacts


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analytic-model-out", type=Path, default=DEFAULT_ANALYTIC_MODEL_OUT)
    parser.add_argument("--analytic-result-out", type=Path, default=DEFAULT_ANALYTIC_RESULT_OUT)
    parser.add_argument("--analytic-report-out", type=Path, default=DEFAULT_ANALYTIC_REPORT_OUT)
    parser.add_argument("--mechanism-model-out", type=Path, default=DEFAULT_MECHANISM_MODEL_OUT)
    parser.add_argument("--mechanism-result-out", type=Path, default=DEFAULT_MECHANISM_RESULT_OUT)
    parser.add_argument("--rigid-body-model-out", type=Path, default=DEFAULT_RIGID_BODY_MODEL_OUT)
    parser.add_argument("--rigid-body-result-out", type=Path, default=DEFAULT_RIGID_BODY_RESULT_OUT)
    parser.add_argument("--convergence-out", type=Path, default=DEFAULT_CONVERGENCE_OUT)
    parser.add_argument("--tangent-jacobian-out", type=Path, default=DEFAULT_TANGENT_JACOBIAN_OUT)
    parser.add_argument("--sparse-backend-out", type=Path, default=DEFAULT_SPARSE_BACKEND_OUT)
    parser.add_argument("--summary-out", type=Path, default=DEFAULT_SUMMARY_OUT)
    parser.add_argument("--check", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.check:
        ok, message = check_linear_reference_artifacts(
            analytic_model_out=args.analytic_model_out,
            analytic_result_out=args.analytic_result_out,
            analytic_report_out=args.analytic_report_out,
            mechanism_model_out=args.mechanism_model_out,
            mechanism_result_out=args.mechanism_result_out,
            rigid_body_model_out=args.rigid_body_model_out,
            rigid_body_result_out=args.rigid_body_result_out,
            convergence_out=args.convergence_out,
            tangent_jacobian_out=args.tangent_jacobian_out,
            sparse_backend_out=args.sparse_backend_out,
            summary_out=args.summary_out,
        )
        print(f"Phase 2 linear reference check: {message}")
        return 0 if ok else 1
    artifacts = write_linear_reference_artifacts(
        analytic_model_out=args.analytic_model_out,
        analytic_result_out=args.analytic_result_out,
        analytic_report_out=args.analytic_report_out,
        mechanism_model_out=args.mechanism_model_out,
        mechanism_result_out=args.mechanism_result_out,
        rigid_body_model_out=args.rigid_body_model_out,
        rigid_body_result_out=args.rigid_body_result_out,
        convergence_out=args.convergence_out,
        tangent_jacobian_out=args.tangent_jacobian_out,
        sparse_backend_out=args.sparse_backend_out,
        summary_out=args.summary_out,
    )
    summary = artifacts["summary"]
    print(
        "Phase 2 linear reference: "
        f"{summary['status']} | residual_gate={summary['residual_gate_passed']} | "
        f"mechanism_blocked={summary['mechanism_blocked_without_regularization']} | "
        f"convergence_suite={summary['linear_axial_convergence_suite_ready']} | "
        f"tangent_jacobian={summary['linear_axial_tangent_jacobian_verification_ready']} | "
        f"sparse_backend_seed={summary['sparse_backend_seed_verification_ready']}"
    )
    return 0 if summary["contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
