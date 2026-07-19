"""Compact receipt over the five bounded geometric-nonlinear roadmap cases.

This module composes existing independently verified case receipts without
changing their claim boundaries.  It establishes case breadth only: it does
not turn the five narrow kernels into a general production frame/shell solver.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from structural_analysis.benchmark.cantilever_elastica import (
    cantilever_elastica_large_rotation_benchmark,
)
from structural_analysis.benchmark.geometric_nonlinear import (
    euler_column_buckling_benchmark,
)
from structural_analysis.benchmark.lee_frame import (
    build_lee_frame_snapthrough_benchmark,
)
from structural_analysis.benchmark.portal_frame_pdelta import (
    portal_frame_pdelta_benchmark,
)
from structural_analysis.benchmark.shallow_arch_arc_length import (
    build_shallow_arch_arc_length_benchmark_seed,
)


GEOMETRIC_NONLINEAR_FIVE_CASE_CORPUS_SCHEMA_VERSION = (
    "phase2-geometric-nonlinear-five-case-corpus.v1"
)
GEOMETRIC_NONLINEAR_FIVE_CASE_ORDER = (
    "euler_column",
    "portal_frame_pdelta",
    "shallow_arch_arc_length",
    "cantilever_large_rotation",
    "lee_frame_snapthrough_snapback",
)
GEOMETRIC_NONLINEAR_FIVE_CASE_CLAIM_BOUNDARY = (
    "This compact receipt proves that five bounded geometric-nonlinear roadmap "
    "case types have passing, deterministic source receipts: Euler column, "
    "portal-frame P-Delta tangent, shallow-arch arc length, cantilever large "
    "rotation, and published Lee-frame snap-through/snap-back. It does not "
    "validate a general 2D/3D production frame or shell, a finite-displacement "
    "portal load path, member P-small-delta stability functions, "
    "material-geometric coupling, experimental validation, sparse or ROCm/HIP "
    "execution, full-building equilibrium, or G1 closure."
)


def _canonical_receipt_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _euler_capsule(payload: dict[str, Any]) -> dict[str, Any]:
    rows = payload["mesh_rows"]
    return {
        "roadmap_case": "Euler column",
        "case_id": payload["case_id"],
        "source_module": "structural_analysis.benchmark.geometric_nonlinear",
        "source_schema_version": "unversioned_case_receipt",
        "truth_level": "level_1_analytic",
        "truth_basis": payload["truth_basis"],
        "bounded_scope": "pinned_pinned_elastic_column_buckling",
        "contract_pass": payload["contract_pass"],
        "source_receipt_hash": _canonical_receipt_hash(payload),
        "key_metrics": {
            "exact_critical_load_kn": payload["exact_critical_load_kn"],
            "finest_relative_error": payload["finest_relative_error"],
            "minimum_observed_convergence_order": min(
                payload["observed_convergence_orders"]
            ),
            "minimum_mode_mac": min(row["mode_mac"] for row in rows),
            "maximum_generalized_eigen_residual_relative_inf": max(
                row["generalized_eigen_residual_relative_inf"] for row in rows
            ),
        },
    }


def _portal_capsule(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "roadmap_case": "P-Delta frame",
        "case_id": payload["benchmark_id"],
        "source_module": "structural_analysis.benchmark.portal_frame_pdelta",
        "source_schema_version": payload["schema_version"],
        "truth_level": "level_1_analytic",
        "truth_basis": payload["reference"]["type"],
        "bounded_scope": "gravity_prestressed_three_member_portal_sway_tangent",
        "contract_pass": payload["contract_pass"],
        "source_receipt_hash": _canonical_receipt_hash(payload),
        "key_metrics": {
            "analytic_critical_total_gravity_load_kn": payload["critical_sway_load"][
                "analytic_total_gravity_load_kn"
            ],
            "critical_load_relative_error": payload["critical_sway_load"][
                "relative_error"
            ],
            "maximum_verified_load_ratio": payload["path_shape"]["maximum_load_ratio"],
            "maximum_lateral_amplification": payload["path_shape"][
                "maximum_assembled_lateral_amplification"
            ],
            "maximum_tangent_relative_inf_error": payload["error_summary"][
                "maximum_tangent_relative_inf_error"
            ],
        },
        "source_claim_boundary": payload["claim_boundary"],
    }


def _shallow_arch_capsule(payload: dict[str, Any]) -> dict[str, Any]:
    metrics = payload["solver_result"]["metrics"]
    verification = payload["verification"]
    return {
        "roadmap_case": "shallow arch",
        "case_id": payload["case_id"],
        "source_module": "structural_analysis.benchmark.shallow_arch_arc_length",
        "source_schema_version": payload["schema_version"],
        "truth_level": "level_1_analytic",
        "truth_basis": payload["truth_basis"],
        "bounded_scope": "scalar_two_bar_spherical_arc_length_path",
        "contract_pass": payload["contract_pass"],
        "source_receipt_hash": _canonical_receipt_hash(payload),
        "key_metrics": {
            "exact_first_limit_load_kn": payload["exact_first_limit_point"]["load_kn"],
            "first_limit_load_relative_error": payload["computed_first_limit_bracket"][
                "first_limit_load_relative_error"
            ],
            "accepted_step_count": metrics["accepted_step_count"],
            "rejected_step_count": metrics["rejected_step_count"],
            "descending_branch_observed": metrics["descending_load_branch_observed"],
            "negative_branch_observed": metrics["negative_load_branch_observed"],
            "rehardening_branch_observed": metrics["rehardening_branch_observed"],
            "rollback_exact": verification["rollback_evidence_passed"],
            "checkpoint_restart_exact": verification["checkpoint_restart_exact"],
        },
        "source_claim_boundary": payload["claim_boundary"],
    }


def _cantilever_capsule(payload: dict[str, Any]) -> dict[str, Any]:
    reference = payload["reference"]
    return {
        "roadmap_case": "cantilever large rotation",
        "case_id": payload["benchmark_id"],
        "source_module": "structural_analysis.benchmark.cantilever_elastica",
        "source_schema_version": payload["schema_version"],
        "truth_level": "level_1_analytic",
        "truth_basis": "continuum_elastica_and_independent_energy_discretization",
        "bounded_scope": "terminal_dead_load_planar_cantilever_elastica",
        "contract_pass": payload["contract_pass"],
        "source_receipt_hash": _canonical_receipt_hash(payload),
        "key_metrics": {
            "dimensionless_load": reference["dimensionless_load"],
            "tip_rotation_rad": reference["tip_rotation_rad"],
            "tip_x_over_length": reference["tip_x_over_length"],
            "tip_downward_y_over_length": reference["tip_downward_y_over_length"],
            "minimum_observed_convergence_order": payload[
                "minimum_observed_convergence_order"
            ],
            "maximum_finest_mesh_abs_error": max(
                payload["finest_mesh_abs_errors"].values()
            ),
        },
    }


def _lee_capsule(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "roadmap_case": "Lee frame snap-through",
        "case_id": payload["benchmark_id"],
        "source_module": "structural_analysis.benchmark.lee_frame",
        "source_schema_version": payload["schema_version"],
        "truth_level": "level_3_published_benchmark",
        "truth_basis": payload["reference"]["table"],
        "bounded_scope": "elastic_planar_two_member_lee_frame_path",
        "contract_pass": payload["contract_pass"],
        "source_receipt_hash": _canonical_receipt_hash(payload),
        "key_metrics": {
            "reference_doi": payload["reference"]["doi"],
            "published_path_point_count": payload["reference"][
                "published_path_point_count"
            ],
            "first_limit_load_factor_absolute_error": payload["path_shape"][
                "first_limit_load_factor_absolute_error"
            ],
            "maximum_displacement_path_distance_m": payload[
                "published_path_error_summary"
            ]["maximum_displacement_path_distance_m"],
            "maximum_load_factor_absolute_error": payload[
                "published_path_error_summary"
            ]["maximum_load_factor_absolute_error"],
            "accepted_step_count": payload["solver"]["accepted_step_count"],
            "checkpoint_restart_exact": payload["solver"]["checkpoint_restart_exact"],
        },
        "source_claim_boundary": payload["claim_boundary"],
    }


def build_geometric_nonlinear_five_case_corpus() -> dict[str, Any]:
    """Run the five bounded cases and return a compact deterministic corpus."""

    euler = euler_column_buckling_benchmark()
    portal = portal_frame_pdelta_benchmark()
    shallow_arch = build_shallow_arch_arc_length_benchmark_seed()
    cantilever = cantilever_elastica_large_rotation_benchmark()
    lee = build_lee_frame_snapthrough_benchmark()
    cases = {
        "euler_column": _euler_capsule(euler),
        "portal_frame_pdelta": _portal_capsule(portal),
        "shallow_arch_arc_length": _shallow_arch_capsule(shallow_arch),
        "cantilever_large_rotation": _cantilever_capsule(cantilever),
        "lee_frame_snapthrough_snapback": _lee_capsule(lee),
    }
    ordered_keys_exact = tuple(cases) == GEOMETRIC_NONLINEAR_FIVE_CASE_ORDER
    all_cases_pass = bool(
        ordered_keys_exact
        and len(cases) == 5
        and all(case["contract_pass"] is True for case in cases.values())
    )
    roadmap_coverage = {
        "euler_column": {
            "bounded_case_present": cases["euler_column"]["contract_pass"],
            "case_key": "euler_column",
        },
        "pdelta_frame": {
            "bounded_case_present": cases["portal_frame_pdelta"]["contract_pass"],
            "case_key": "portal_frame_pdelta",
        },
        "shallow_arch": {
            "bounded_case_present": cases["shallow_arch_arc_length"]["contract_pass"],
            "case_key": "shallow_arch_arc_length",
        },
        "cantilever_large_rotation": {
            "bounded_case_present": cases["cantilever_large_rotation"]["contract_pass"],
            "case_key": "cantilever_large_rotation",
        },
        "lee_frame_snapthrough": {
            "bounded_case_present": cases["lee_frame_snapthrough_snapback"][
                "contract_pass"
            ],
            "case_key": "lee_frame_snapthrough_snapback",
        },
    }
    coverage_pass = bool(
        len(roadmap_coverage) == 5
        and all(
            row["bounded_case_present"] is True for row in roadmap_coverage.values()
        )
    )
    truth_level_counts = {
        "level_1_analytic": sum(
            case["truth_level"] == "level_1_analytic" for case in cases.values()
        ),
        "level_2_code_to_code": 0,
        "level_3_published_benchmark": sum(
            case["truth_level"] == "level_3_published_benchmark"
            for case in cases.values()
        ),
        "level_4_experimental": 0,
        "level_5_customer_shadow": 0,
    }
    contract_pass = bool(all_cases_pass and coverage_pass)
    return {
        "schema_version": GEOMETRIC_NONLINEAR_FIVE_CASE_CORPUS_SCHEMA_VERSION,
        "corpus_id": "geometric-nonlinear-five-case-roadmap-corpus-v1",
        "status": "partial" if contract_pass else "blocked",
        "contract_pass": contract_pass,
        "case_count": len(cases),
        "required_case_order": list(GEOMETRIC_NONLINEAR_FIVE_CASE_ORDER),
        "ordered_case_keys_exact": ordered_keys_exact,
        "cases": cases,
        "roadmap_coverage": roadmap_coverage,
        "roadmap_coverage_contract_pass": coverage_pass,
        "truth_level_counts": truth_level_counts,
        "claims": {
            "bounded_five_case_geometric_nonlinear_corpus": contract_pass,
            "roadmap_five_case_coverage": coverage_pass,
            "analytic_truth_present": truth_level_counts["level_1_analytic"] > 0,
            "published_truth_present": (
                truth_level_counts["level_3_published_benchmark"] > 0
            ),
            "arc_length_path_following_cases_present": bool(
                shallow_arch["contract_pass"] and lee["contract_pass"]
            ),
            "energy_consistent_frame_cases_present": bool(
                portal["contract_pass"] and lee["contract_pass"]
            ),
            "continuum_large_rotation_case_present": cantilever["contract_pass"],
            "general_2d_3d_production_frame_or_shell": False,
            "finite_displacement_portal_pdelta_load_path": False,
            "member_p_small_delta_stability_functions": False,
            "material_geometric_coupling": False,
            "level_2_code_to_code_coverage": False,
            "level_4_experimental_validation": False,
            "level_5_customer_shadow_validation": False,
            "production_sparse_or_rocm_hip": False,
            "full_building_equilibrium": False,
            "g1_closure": False,
        },
        "blockers_remaining": [
            "general_2d_3d_production_frame_shell_not_validated",
            "finite_displacement_portal_pdelta_path_not_verified",
            "member_p_small_delta_stability_functions_not_implemented",
            "material_geometric_coupling_not_verified",
            "level_2_code_to_code_geometric_corpus_not_attached",
            "level_4_experimental_geometric_validation_not_attached",
            "level_5_customer_shadow_geometric_validation_not_attached",
            "production_sparse_rocm_hip_path_not_connected",
            "full_building_equilibrium_not_closed",
            "g1_not_closed",
        ],
        "claim_boundary": GEOMETRIC_NONLINEAR_FIVE_CASE_CLAIM_BOUNDARY,
    }


__all__ = [
    "GEOMETRIC_NONLINEAR_FIVE_CASE_CLAIM_BOUNDARY",
    "GEOMETRIC_NONLINEAR_FIVE_CASE_CORPUS_SCHEMA_VERSION",
    "GEOMETRIC_NONLINEAR_FIVE_CASE_ORDER",
    "build_geometric_nonlinear_five_case_corpus",
]
