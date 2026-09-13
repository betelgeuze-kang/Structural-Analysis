"""Counterfactual attribution preserves original parents and checks real replays."""

from decimal import Decimal, localcontext
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    BoundedRCFiberDirectControlRequest,
)
from structural_analysis.benchmark.rc_control_seed_runtime import (
    benchmark_rc_control_seed_paths,
)
from structural_analysis.io.neutral.loader import load_neutral_json
from structural_analysis.materials import make_rectangular_stateful_rc_fiber_section

SPEC = importlib.util.spec_from_file_location(
    "rc_section_error",
    Path(__file__).parents[1] / "scripts/diagnose_rc_control_section_error.py",
)
diag = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(diag)


def test_exact_finite_coordinate_strain_matches_independent_decimal_hermite():
    u = [1e8, 0.018, 0.012, 1e8 + 0.0003, 0.036000000000000004, 0.012]
    length, xi = 1.5, 0.7745966692414834
    with localcontext() as ctx:
        ctx.prec = 100
        v = list(map(Decimal.from_float, u))
        L = Decimal.from_float(length)
        ratio = (Decimal.from_float(xi) + 1) / 2
        expected = [
            (v[3] - v[0]) / L,
            (-6 + 12 * ratio) * v[1] / L**2
            + (-4 + 6 * ratio) * v[2] / L
            + (6 - 12 * ratio) * v[4] / L**2
            + (-2 + 6 * ratio) * v[5] / L,
        ]
    assert np.array_equal(
        diag.exact_coordinate_strain(u, length, xi), list(map(float, expected))
    )
    # Exactly representable rigid translation/rotation vanishes without clamping.
    assert np.array_equal(
        diag.exact_coordinate_strain([2, 3, 0.25, 2, 3.5, 0.25], 2, 0.5), [0, 0]
    )


@pytest.mark.parametrize(
    "length,xi", [(0, 0), (-1, 0), (1, 2), (float("inf"), 0), (True, 0)]
)
def test_invalid_kinematic_domain_is_rejected(length, xi):
    with pytest.raises(ValueError):
        diag.exact_coordinate_strain([0.0] * 6, length, xi)


def test_same_strain_different_plastic_history_is_retained_in_both_orders():
    section = make_rectangular_stateful_rc_fiber_section()
    initial = section.initial_state()
    damaged = section.integrate([-0.004, 0.02], initial).state
    before = [p.to_dict() for p in [initial, damaged]]
    g = np.array([-0.0001, 0.001])
    result = diag.attribute_section(section, initial, damaged, g, g, g, g)
    assert result["section_integrations"] == 8
    assert result["fiber_integrations"] == 8 * len(section.fibers)
    assert any(abs(v) > 1 for v in result["difference_N_Nm"])
    for order in result["orders"].values():
        components = order["components_N_Nm"]
        assert components["parent_history_difference"] == result["difference_N_Nm"]
        assert all(
            components[k] == [0.0, 0.0]
            for k in components
            if k != "parent_history_difference"
        )
        assert order["serialized_sum_residual_N_Nm"] == [0.0, 0.0]
    assert before == [p.to_dict() for p in [initial, damaged]]


def test_real_cyclic_step_replays_and_tampered_original_is_rejected(tmp_path):
    study = tmp_path / "study"
    benchmark_rc_control_seed_paths(
        load_neutral_json(
            Path("examples/public_rc_fiber_frame_l_frame_material_history.json")
        ),
        BoundedRCFiberDirectControlRequest(
            7, (-1e-5, -2e-5, -1e-5), allow_reversals=True, maximum_reversals=1
        ),
        source_revision="0" * 40,
        output_directory=study,
    )
    result = diag.diagnose(study, "secant")
    assert result["target_count"] == 3 and len(result["rows"]) == 18
    assert result["work"]["original_section_responses_verified"] == 36
    assert result["work"]["section_integrations"] == 144
    assert result["work"]["newton_solves"] == result["work"]["state_commits"] == 0
    for row in result["rows"]:
        for order in row["orders"].values():
            np.testing.assert_allclose(
                order["serialized_sum_residual_N_Nm"], 0, atol=1e-20, rtol=0
            )
    file = study / "secant/001-1-step.json"
    payload = json.loads(file.read_text())
    payload["trial_assembly"]["member_assemblies"][0]["element_response"][
        "section_responses"
    ][0]["resultants"]["axial_force_kn"] += 1
    file.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="original section replay differs"):
        diag.diagnose(study, "secant")


def test_nonlinear_interaction_makes_attribution_order_explicit():
    section = make_rectangular_stateful_rc_fiber_section()
    initial = section.initial_state()
    damaged = section.integrate([-0.004, 0.02], initial).state
    result = diag.attribute_section(
        section,
        initial,
        damaged,
        [-0.0001, 0.001],
        [0.0004, -0.002],
        [-0.00011, 0.0011],
        [0.00041, -0.0021],
    )
    first, second = result["orders"].values()
    assert (
        first["components_N_Nm"]["parent_history_difference"]
        != second["components_N_Nm"]["parent_history_difference"]
    )
    for order in [first, second]:
        total = np.sum(list(order["components_N_Nm"].values()), axis=0)
        np.testing.assert_allclose(
            total, result["difference_N_Nm"], rtol=2e-15, atol=1e-10
        )
