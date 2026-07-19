from __future__ import annotations

import json
import re
from typing import Any

import pytest

from structural_analysis.benchmark.geometric_nonlinear_corpus import (
    GEOMETRIC_NONLINEAR_FIVE_CASE_CLAIM_BOUNDARY,
    GEOMETRIC_NONLINEAR_FIVE_CASE_CORPUS_SCHEMA_VERSION,
    GEOMETRIC_NONLINEAR_FIVE_CASE_ORDER,
    build_geometric_nonlinear_five_case_corpus,
)


@pytest.fixture(scope="module")
def replayed_corpus() -> tuple[dict[str, Any], dict[str, Any]]:
    return (
        build_geometric_nonlinear_five_case_corpus(),
        build_geometric_nonlinear_five_case_corpus(),
    )


def test_five_case_corpus_is_deterministic_complete_and_partial(
    replayed_corpus: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    first, second = replayed_corpus

    assert first == second
    assert first["schema_version"] == (
        GEOMETRIC_NONLINEAR_FIVE_CASE_CORPUS_SCHEMA_VERSION
    )
    assert first["status"] == "partial"
    assert first["contract_pass"] is True
    assert first["case_count"] == 5
    assert tuple(first["required_case_order"]) == (GEOMETRIC_NONLINEAR_FIVE_CASE_ORDER)
    assert tuple(first["cases"]) == GEOMETRIC_NONLINEAR_FIVE_CASE_ORDER
    assert first["ordered_case_keys_exact"] is True
    assert all(row["contract_pass"] is True for row in first["cases"].values())


def test_roadmap_coverage_is_exactly_the_five_bounded_case_types(
    replayed_corpus: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    result = replayed_corpus[0]
    coverage = result["roadmap_coverage"]

    assert tuple(coverage) == (
        "euler_column",
        "pdelta_frame",
        "shallow_arch",
        "cantilever_large_rotation",
        "lee_frame_snapthrough",
    )
    assert all(row["bounded_case_present"] is True for row in coverage.values())
    assert result["roadmap_coverage_contract_pass"] is True
    assert result["truth_level_counts"] == {
        "level_1_analytic": 4,
        "level_2_code_to_code": 0,
        "level_3_published_benchmark": 1,
        "level_4_experimental": 0,
        "level_5_customer_shadow": 0,
    }


def test_case_capsules_retain_high_signal_metrics_and_unique_receipt_hashes(
    replayed_corpus: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    cases = replayed_corpus[0]["cases"]
    euler = cases["euler_column"]["key_metrics"]
    portal = cases["portal_frame_pdelta"]["key_metrics"]
    arch = cases["shallow_arch_arc_length"]["key_metrics"]
    cantilever = cases["cantilever_large_rotation"]["key_metrics"]
    lee = cases["lee_frame_snapthrough_snapback"]["key_metrics"]

    assert euler["finest_relative_error"] <= 3.0e-6
    assert euler["minimum_observed_convergence_order"] >= 3.7
    assert euler["minimum_mode_mac"] >= 1.0 - 1.0e-12
    assert portal["critical_load_relative_error"] <= 1.0e-10
    assert portal["maximum_verified_load_ratio"] == 0.95
    assert portal["maximum_lateral_amplification"] >= 19.0
    assert arch["first_limit_load_relative_error"] <= 0.01
    assert arch["rollback_exact"] is True
    assert arch["checkpoint_restart_exact"] is True
    assert arch["descending_branch_observed"] is True
    assert arch["negative_branch_observed"] is True
    assert arch["rehardening_branch_observed"] is True
    assert cantilever["tip_rotation_rad"] > 1.0
    assert cantilever["minimum_observed_convergence_order"] >= 1.9
    assert cantilever["maximum_finest_mesh_abs_error"] <= 5.0e-5
    assert lee["reference_doi"] == "10.12989/sem.2011.38.6.767"
    assert lee["published_path_point_count"] == 23
    assert lee["maximum_displacement_path_distance_m"] <= 0.004
    assert lee["maximum_load_factor_absolute_error"] <= 0.35
    assert lee["checkpoint_restart_exact"] is True

    hashes = [row["source_receipt_hash"] for row in cases.values()]
    assert len(set(hashes)) == 5
    assert all(re.fullmatch(r"sha256:[0-9a-f]{64}", value) for value in hashes)


def test_corpus_promotes_only_bounded_breadth_claims(
    replayed_corpus: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    result = replayed_corpus[0]
    claims = result["claims"]

    assert claims["bounded_five_case_geometric_nonlinear_corpus"] is True
    assert claims["roadmap_five_case_coverage"] is True
    assert claims["analytic_truth_present"] is True
    assert claims["published_truth_present"] is True
    assert claims["arc_length_path_following_cases_present"] is True
    assert claims["energy_consistent_frame_cases_present"] is True
    assert claims["continuum_large_rotation_case_present"] is True

    assert claims["general_2d_3d_production_frame_or_shell"] is False
    assert claims["finite_displacement_portal_pdelta_load_path"] is False
    assert claims["member_p_small_delta_stability_functions"] is False
    assert claims["material_geometric_coupling"] is False
    assert claims["level_2_code_to_code_coverage"] is False
    assert claims["level_4_experimental_validation"] is False
    assert claims["level_5_customer_shadow_validation"] is False
    assert claims["production_sparse_or_rocm_hip"] is False
    assert claims["full_building_equilibrium"] is False
    assert claims["g1_closure"] is False
    assert result["blockers_remaining"]
    assert result["claim_boundary"] == (GEOMETRIC_NONLINEAR_FIVE_CASE_CLAIM_BOUNDARY)


def test_compact_corpus_is_strict_json(
    replayed_corpus: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    json.dumps(replayed_corpus[0], allow_nan=False, sort_keys=True)
