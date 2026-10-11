"""Circular bar area integration, public transport, and restart identity."""

import json
import math
from pathlib import Path

import numpy as np
import pytest

from structural_analysis.api.nonlinear_fiber_frame import _compile
from structural_analysis.api.rc_fiber_frame_direct_control import (
    analyze_bounded_rc_fiber_direct_control,
)
from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    BoundedRCFiberDirectControlRequest,
)
from structural_analysis.execution.rc_fiber_quantities import (
    calculate_fiber_frame_member_quantities,
)
from structural_analysis.io.neutral.loader import load_neutral_json_bytes

ROOT = Path(__file__).parents[1]


def authored(points=8):
    data = json.loads(
        (ROOT / "examples/public_rc_fiber_frame_explicit_layers.json").read_text()
    )
    for layer in data["sections"][0]["steel_layers"]:
        layer["circular_integration_points"] = points
    return data


def model(data):
    return load_neutral_json_bytes(json.dumps(data).encode())


@pytest.mark.parametrize("points", [2, 8, 32, 64])
def test_circular_geometry_preserves_area_centroid_and_intrinsic_inertia(points):
    data = authored(points)
    compiled, blockers, _ = _compile(model(data))
    assert not blockers
    section = compiled.problem.members[0].element.section
    for layer in data["sections"][0]["steel_layers"]:
        fibers = [
            f
            for f in section.fibers
            if f.fiber_id.startswith(f"steel-circular-{layer['id']}-")
        ]
        area = layer["bar_count"] * layer["bar_area_m2"]
        radius = math.sqrt(layer["bar_area_m2"] / math.pi)
        assert len(fibers) == points
        assert math.fsum(f.area_m2 for f in fibers) == pytest.approx(area, rel=1e-13)
        assert math.fsum(f.area_m2 * f.y_m for f in fibers) == pytest.approx(
            area * layer["y_m"], rel=1e-13
        )
        assert math.fsum(
            f.area_m2 * (f.y_m - layer["y_m"]) ** 2 for f in fibers
        ) == pytest.approx(area * radius**2 / 4, rel=1e-12)
    q = calculate_fiber_frame_member_quantities(model(data))
    assert q["totals"]["longitudinal_rebar_volume_m3"] == pytest.approx(0.0012 * 3)


@pytest.mark.parametrize("value", [True, 1, 65, 3.5, None, "8"])
def test_bad_integration_counts_are_rejected_before_solve(value):
    compiled, blockers, _ = _compile(model(authored(value)))
    assert compiled is None and blockers


def test_circular_extent_is_checked_not_just_centroid():
    data = authored()
    data["sections"][0]["steel_layers"][0]["y_m"] = -0.299
    compiled, blockers, _ = _compile(model(data))
    assert compiled is None
    assert any(
        b["kind"] == "rc_fiber_frame_circular_bar_extent_invalid" for b in blockers
    )


def test_circular_material_points_have_independent_cyclic_states_and_tangent():
    compiled, blockers, _ = _compile(model(authored()))
    assert not blockers
    section = compiled.problem.members[0].element.section
    state = section.initial_state()
    for strain in [(0.003, 0.02), (-0.002, -0.015), (0.004, -0.01)]:
        old = state.state_hash
        section.integrate((strain[0] + 0.001, strain[1]), state)
        assert state.state_hash == old
        response = section.integrate(strain, state)
        fd = []
        for j in range(2):
            delta = np.zeros(2)
            delta[j] = 1e-8
            plus = section.integrate(np.array(strain) + delta, state)
            minus = section.integrate(np.array(strain) - delta, state)
            fd.append(
                (
                    np.array([plus.axial_force_kn, plus.moment_z_kn_m])
                    - np.array([minus.axial_force_kn, minus.moment_z_kn_m])
                )
                / 2e-8
            )
        np.testing.assert_allclose(
            np.column_stack(fd), response.consistent_tangent, rtol=1e-5, atol=1e-4
        )
        state = response.state
    indices = [
        i
        for i, f in enumerate(section.fibers)
        if f.fiber_id.startswith("steel-circular-")
    ]
    assert len({state.fiber_states[i].state_hash for i in indices}) > 3


def test_public_restart_preserves_points_and_rejects_changed_quadrature():
    data = authored(4)
    source = model(data)
    config = BoundedRCFiberDirectControlRequest(4, (-1e-6, -2e-6))
    whole = analyze_bounded_rc_fiber_direct_control(
        source, config.targets_m, **config.api_kwargs()
    )
    prefix = analyze_bounded_rc_fiber_direct_control(
        source, (-1e-6,), **config.api_kwargs()
    )
    resumed = analyze_bounded_rc_fiber_direct_control(
        source,
        (-2e-6,),
        restart=prefix.checkpoint_artifact_bytes(),
        **config.api_kwargs(),
    )
    assert whole.to_dict()["contract_pass"] and resumed.to_dict()["contract_pass"]
    assert whole.checkpoint_artifact_bytes() == resumed.checkpoint_artifact_bytes()
    changed = model(authored(8))
    with pytest.raises(
        ValueError, match="restart source/configuration/control/budget mismatch"
    ):
        analyze_bounded_rc_fiber_direct_control(
            changed,
            (-2e-6,),
            restart=prefix.checkpoint_artifact_bytes(),
            **config.api_kwargs(),
        )
