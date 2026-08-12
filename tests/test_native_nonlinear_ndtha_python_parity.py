from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import numpy as np
import pytest

from tests.native_oracles.nonlinear_ndtha_story_frame import (
    NonlinearNdthaOracleConfig,
    solve_case,
    solve_nonlinear_ndtha_oracle,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = ROOT / "native/tests/fixtures/solver_cpu"
PRODUCT_FIXTURES = (
    FIXTURE_ROOT / "nonlinear_ndtha_one_story_elastic_python_c1.json",
    FIXTURE_ROOT / "nonlinear_ndtha_elastic_pdelta_python_c1.json",
    FIXTURE_ROOT / "nonlinear_ndtha_plastic_backtrack_python_c1.json",
    FIXTURE_ROOT / "nonlinear_ndtha_adaptive_retry_python_c1.json",
    FIXTURE_ROOT / "nonlinear_ndtha_collapse_python_c1.json",
)
LEGACY_FIXTURE = ROOT / "native/tests/fixtures/legacy_runtime_v3/nonlinear_ndtha.json"


def _assert_float(actual: float, expected: float, *, absolute: float) -> None:
    assert actual == pytest.approx(expected, rel=0.0, abs=absolute)


@pytest.mark.parametrize("fixture", PRODUCT_FIXTURES, ids=lambda path: path.stem)
def test_dense_python_oracle_matches_every_product_result_channel(
    fixture: Path,
) -> None:
    case = json.loads(fixture.read_text(encoding="utf-8"))
    actual = solve_case(case)
    expected = case["result"]

    for field in (
        "converged_all_steps",
        "collapsed",
        "collapse_step",
        "step_count_completed",
        "max_plastic_story_count",
        "total_line_search_backtracks",
    ):
        assert getattr(actual, field) == expected[field]
    for field in (
        "collapse_time_s",
        "collapse_drift_ratio_pct",
        "collapse_top_displacement_m",
        "max_drift_ratio_pct",
        "avg_step_iterations",
        "residual_top_displacement_m",
        "residual_drift_ratio_pct",
    ):
        _assert_float(getattr(actual, field), expected[field], absolute=1.0e-12)

    response = actual.response
    expected_response = expected["response"]
    for field in (
        "step_converged",
        "step_iterations",
        "step_plastic_story_count",
    ):
        assert getattr(response, field) == tuple(expected_response[field])
    for field in (
        "top_displacement_m",
        "drift_ratio_pct",
        "base_shear_kn",
        "core_drift_pct",
        "core_shear_kn",
        "step_residual_inf",
        "story_drift_envelope_pct",
        "final_story_drift_pct",
    ):
        np.testing.assert_allclose(
            getattr(response, field),
            expected_response[field],
            rtol=0.0,
            atol=1.0e-12,
        )
    assert expected["execution_backend"] == "cpu"
    assert expected["fallback_count"] == 0


def test_product_c1_matrix_covers_dynamic_constitutive_and_termination_axes() -> None:
    cases = [json.loads(path.read_text(encoding="utf-8")) for path in PRODUCT_FIXTURES]

    assert {case["config"]["story_count"] for case in cases} == {1, 2, 3}
    assert {case["config"]["step_count"] for case in cases} == {3, 5, 6}
    assert {case["config"]["pdelta_factor"] for case in cases} == {0.0, 1.0}
    assert {case["config"]["newmark_beta"] for case in cases} == {0.25, 0.3025}
    assert {case["config"]["newmark_gamma"] for case in cases} == {0.5, 0.6}
    assert {case["config"]["damping_force_cap_ratio"] for case in cases} == {
        0.2,
        0.6,
    }
    assert {case["result"]["max_plastic_story_count"] for case in cases} == {
        0,
        1,
        2,
        3,
    }
    assert any(
        any(value < 0.0 for value in case["inputs"]["ag_g"]) for case in cases
    )
    assert any(
        max(case["result"]["response"]["step_iterations"]) > 1 for case in cases
    )
    assert any(case["result"]["total_line_search_backtracks"] > 0 for case in cases)
    assert {case["result"]["collapsed"] for case in cases} == {False, True}


def test_python_oracle_models_nonconvergence_without_committing_partial_state() -> None:
    case = json.loads(PRODUCT_FIXTURES[1].read_text(encoding="utf-8"))
    config = case["config"]
    inputs = case["inputs"]
    oracle_config = NonlinearNdthaOracleConfig(
        story_count=config["story_count"],
        step_count=config["step_count"],
        dt_s=config["dt_s"],
        newmark_beta=config["newmark_beta"],
        newmark_gamma=config["newmark_gamma"],
        tolerance=config["tolerance"],
        max_step_iterations=config["max_step_iterations"],
        adaptive_load_decay=config["adaptive_load_decay"],
        damping_force_cap_ratio=config["damping_force_cap_ratio"],
        newton_max_iter=config["newton_max_iter"],
        line_search_decay=config["line_search_decay"],
        line_search_min=config["line_search_min"],
        hardening_ratio=config["hardening_ratio"],
        pdelta_factor=config["pdelta_factor"],
        collapse_drift_threshold_pct=config["collapse_drift_threshold_pct"],
    )
    actual = solve_nonlinear_ndtha_oracle(
        config=replace(
            oracle_config,
            tolerance=1.0e-30,
            max_step_iterations=1,
            newton_max_iter=1,
        ),
        story_stiffness_n_per_m=inputs["story_k_n_per_m"],
        story_height_m=inputs["story_h_m"],
        story_axial_n=inputs["story_axial_n"],
        story_yield_drift_m=inputs["story_yield_drift_m"],
        story_mass_kg=inputs["story_mass_kg"],
        story_damping_n_s_per_m=inputs["story_damping_n_s_per_m"],
        floor_load_base_n=inputs["floor_load_base_n"],
        acceleration_g=inputs["ag_g"],
    )

    assert actual.converged_all_steps is False
    assert actual.collapsed is False
    assert actual.step_count_completed == 1
    assert actual.response.step_converged[0] is False
    assert actual.residual_top_displacement_m == 0.0
    assert actual.residual_drift_ratio_pct == 0.0


def test_product_elastic_pdelta_inputs_are_a_neutral_copy_of_the_legacy_case() -> None:
    product = json.loads(PRODUCT_FIXTURES[1].read_text(encoding="utf-8"))
    legacy = json.loads(LEGACY_FIXTURE.read_text(encoding="utf-8"))

    assert product["config"] == legacy["config"]
    assert product["inputs"] == legacy["inputs"]
    for field, value in legacy["result"].items():
        if field not in {"rust_backend_all_steps", "status_code"}:
            assert product["result"][field] == value


def test_nonlinear_ndtha_cpu_capability_is_bounded_at_c1() -> None:
    capabilities = json.loads(
        (ROOT / "native/capabilities.json").read_text(encoding="utf-8")
    )
    row = capabilities["capabilities"]["nonlinear_ndtha_cpu"]
    assert row["cutover_gate"] == "C1"
    assert "independent dense-matrix Python C1" in row["claim"]
    assert "five-case" in row["claim"]
    assert "broader dynamic input-space parity" in row["claim"]
    assert "HIP C2" in row["claim"]
