from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from track_lf_solver import TrackLFConfig, make_point_load_vector, solve_track_static


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "native/tests/fixtures/legacy_runtime_v3/track_point_load.json"


def test_python_oracle_boundary_keeps_track_cpu_capability_at_c0() -> None:
    case = json.loads(FIXTURE.read_text(encoding="utf-8"))
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

    assert actual.iterations == expected["iterations"]
    assert actual.residual_inf == expected["residual_inf"]
    np.testing.assert_array_equal(actual.displacement_m, expected["displacement_m"])
    np.testing.assert_array_equal(actual.rotation_rad[1:-1], expected["rotation_rad"][1:-1])
    endpoint_delta = abs(actual.rotation_rad[0] - expected["rotation_rad"][0])
    assert endpoint_delta == pytest.approx(3.436580346133486e-5, abs=1.0e-18)
    assert actual.rotation_rad[-1] - expected["rotation_rad"][-1] == pytest.approx(
        endpoint_delta,
        abs=1.0e-18,
    )

    capabilities = json.loads(
        (ROOT / "native/capabilities.json").read_text(encoding="utf-8")
    )
    row = capabilities["capabilities"]["track_point_load_cpu"]
    assert row["cutover_gate"] == "C0"
    assert "endpoint-rotation convention blocks C1" in row["claim"]
