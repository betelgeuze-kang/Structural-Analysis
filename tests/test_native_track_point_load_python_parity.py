from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from track_lf_solver import TrackLFConfig, make_point_load_vector, solve_track_static


ROOT = Path(__file__).resolve().parents[1]
PRODUCT_FIXTURES = (
    ROOT / "native/tests/fixtures/solver_cpu/track_point_load_python_c1.json",
    ROOT
    / "native/tests/fixtures/solver_cpu/track_point_load_pinned_timoshenko_python_c1.json",
    ROOT / "native/tests/fixtures/solver_cpu/track_point_load_fixed_euler_python_c1.json",
    ROOT
    / "native/tests/fixtures/solver_cpu/track_point_load_fixed_timoshenko_python_c1.json",
)
LEGACY_FIXTURE = ROOT / "native/tests/fixtures/legacy_runtime_v3/track_point_load.json"


def _solve(case: dict[str, object]):
    config = case["config"]
    expected = case["result"]
    python_config = TrackLFConfig(
        length_m=config["length_m"],
        node_count=config["node_count"],
        support_type=config["support_type"],
        theory=config["theory"],
        bending_stiffness_n_m2=config["bending_stiffness_n_m2"],
        shear_stiffness_n=config["shear_stiffness_n"],
        winkler_k_n_per_m2=config["winkler_k_n_per_m2"],
        pasternak_g_n=config["pasternak_g_n"],
        tolerance=config["tolerance"],
        cg_max_iter=config["cg_max_iter"],
    )
    load = make_point_load_vector(
        config["node_count"],
        config["length_m"],
        config["point_force_n"],
        config["point_position_m"],
    )
    actual = solve_track_static(python_config, load)

    return actual, expected


@pytest.mark.parametrize("fixture", PRODUCT_FIXTURES, ids=lambda path: path.stem)
def test_python_oracle_matches_the_complete_product_c1_matrix(fixture: Path) -> None:
    case = json.loads(fixture.read_text(encoding="utf-8"))
    actual, expected = _solve(case)

    assert actual.iterations == expected["iterations"]
    assert actual.residual_inf == expected["residual_inf"]
    np.testing.assert_array_equal(actual.displacement_m, expected["displacement_m"])
    np.testing.assert_array_equal(actual.rotation_rad, expected["rotation_rad"])


def test_product_c1_matrix_covers_both_supports_and_theories() -> None:
    cases = [json.loads(path.read_text(encoding="utf-8")) for path in PRODUCT_FIXTURES]
    assert {
        (case["config"]["support_type"], case["config"]["theory"])
        for case in cases
    } == {
        ("pinned", "euler"),
        ("pinned", "timoshenko"),
        ("fixed", "euler"),
        ("fixed", "timoshenko"),
    }
    assert {case["config"]["node_count"] for case in cases} == {9}
    assert {case["config"]["point_position_m"] for case in cases} == {5.0}


def test_product_c1_golden_freezes_the_legacy_endpoint_only_divergence() -> None:
    case = json.loads(PRODUCT_FIXTURES[0].read_text(encoding="utf-8"))
    legacy = json.loads(LEGACY_FIXTURE.read_text(encoding="utf-8"))
    expected = case["result"]
    assert case["config"] == legacy["config"]

    np.testing.assert_array_equal(
        expected["displacement_m"], legacy["result"]["displacement_m"]
    )
    np.testing.assert_array_equal(
        expected["rotation_rad"][1:-1], legacy["result"]["rotation_rad"][1:-1]
    )
    endpoint_delta = abs(
        expected["rotation_rad"][0] - legacy["result"]["rotation_rad"][0]
    )
    assert endpoint_delta == pytest.approx(3.436580346133486e-5, abs=1.0e-18)
    assert expected["rotation_rad"][-1] - legacy["result"]["rotation_rad"][-1] == pytest.approx(
        endpoint_delta,
        abs=1.0e-18,
    )


def test_track_cpu_capability_is_bounded_at_c1() -> None:
    capabilities = json.loads((ROOT / "native/capabilities.json").read_text(encoding="utf-8"))
    row = capabilities["capabilities"]["track_point_load_cpu"]
    assert row["cutover_gate"] == "C1"
    assert "Python C1 oracle parity" in row["claim"]
    assert "9-node midpoint-load support/theory matrix" in row["claim"]
    assert "broader input-space parity" in row["claim"]
    assert "HIP C2" in row["claim"]
