from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import numpy as np
import pytest

from tests.native_oracles.nonlinear_static_story_frame import (
    NonlinearStaticOracleConfig,
    solve_case,
    solve_nonlinear_static_oracle,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = ROOT / "native/tests/fixtures/solver_cpu"
PRODUCT_FIXTURES = (
    FIXTURE_ROOT / "nonlinear_static_one_story_elastic_python_c1.json",
    FIXTURE_ROOT / "nonlinear_static_one_story_pdelta_backtrack_python_c1.json",
    FIXTURE_ROOT / "nonlinear_static_elastic_pdelta_python_c1.json",
    FIXTURE_ROOT / "nonlinear_static_plastic_python_c1.json",
    FIXTURE_ROOT / "nonlinear_static_mixed_sign_python_c1.json",
)
LEGACY_FIXTURE = (
    ROOT / "native/tests/fixtures/legacy_runtime_v3/nonlinear_static.json"
)


@pytest.mark.parametrize("fixture", PRODUCT_FIXTURES, ids=lambda path: path.stem)
def test_dense_python_oracle_matches_the_complete_product_c1_matrix(
    fixture: Path,
) -> None:
    case = json.loads(fixture.read_text(encoding="utf-8"))
    actual = solve_case(case)
    expected = case["result"]

    assert actual.converged is expected["converged"] is True
    assert actual.iterations == expected["iterations"]
    assert actual.plastic_story_count == expected["plastic_story_count"]
    assert actual.line_search_backtracks == expected["line_search_backtracks"]
    np.testing.assert_allclose(
        actual.displacement_m,
        expected["u_story_m"],
        rtol=0.0,
        atol=1.0e-12,
    )
    for field in ("max_abs_displacement_m", "top_displacement_m"):
        assert getattr(actual, field) == pytest.approx(
            expected[field],
            rel=0.0,
            abs=1.0e-12,
        )
    for field in ("residual_inf", "residual_l2"):
        assert getattr(actual, field) == pytest.approx(
            expected[field],
            rel=0.0,
            abs=1.0e-7,
        )
    assert actual.base_shear_kn == pytest.approx(
        expected["base_shear_kn"],
        rel=0.0,
        abs=1.0e-10,
    )


def test_product_c1_matrix_covers_topology_material_load_pdelta_and_globalization() -> None:
    cases = [json.loads(path.read_text(encoding="utf-8")) for path in PRODUCT_FIXTURES]
    assert {case["config"]["story_count"] for case in cases} == {1, 3}
    assert {case["result"]["plastic_story_count"] for case in cases} == {0, 2, 3}
    assert {case["config"]["pdelta_factor"] for case in cases} == {0.0, 1.0}
    assert any(
        any(value < 0.0 for value in case["inputs"]["floor_load_n"])
        for case in cases
    )
    assert any(case["result"]["line_search_backtracks"] > 0 for case in cases)


def test_python_oracle_and_native_error_contract_share_the_nonconvergence_case() -> None:
    case = json.loads(PRODUCT_FIXTURES[2].read_text(encoding="utf-8"))
    config = case["config"]
    inputs = case["inputs"]
    oracle_config = NonlinearStaticOracleConfig(
        tolerance=config["tolerance"],
        max_iter=config["max_iter"],
        hardening_ratio=config["hardening_ratio"],
        line_search_decay=config["line_search_decay"],
        line_search_min=config["line_search_min"],
        pdelta_factor=config["pdelta_factor"],
    )
    actual = solve_nonlinear_static_oracle(
        config=replace(oracle_config, max_iter=1),
        story_stiffness_n_per_m=inputs["story_k_n_per_m"],
        story_height_m=inputs["story_h_m"],
        story_axial_n=inputs["story_axial_n"],
        story_yield_drift_m=inputs["story_yield_drift_m"],
        floor_load_n=inputs["floor_load_n"],
    )

    assert actual.converged is False
    assert actual.iterations == 1
    assert actual.residual_inf > oracle_config.tolerance


def test_product_elastic_pdelta_case_is_a_python_owned_copy_of_the_legacy_case() -> None:
    product = json.loads(PRODUCT_FIXTURES[2].read_text(encoding="utf-8"))
    legacy = json.loads(LEGACY_FIXTURE.read_text(encoding="utf-8"))

    assert product == legacy
    assert solve_case(product).converged is True


def test_nonlinear_static_cpu_capability_is_bounded_at_c1() -> None:
    capabilities = json.loads(
        (ROOT / "native/capabilities.json").read_text(encoding="utf-8")
    )
    row = capabilities["capabilities"]["nonlinear_static_cpu"]
    assert row["cutover_gate"] == "C1"
    assert "Python C1 oracle parity" in row["claim"]
    assert "five-case" in row["claim"]
    assert "broader nonlinear input-space parity" in row["claim"]
    assert "HIP C2" in row["claim"]
