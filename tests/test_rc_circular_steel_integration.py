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


@pytest.mark.parametrize("yield_radius_fraction", [0.25, 0.5])
@pytest.mark.parametrize("unload_ratio", [None, 0.0, -0.5, -1.0])
def test_partial_yield_circular_bar_converges_to_closed_form(
    yield_radius_fraction, unload_ratio
):
    """Compare chord quadrature against the elastic-perfectly-plastic disk integral."""
    radius, modulus, yield_stress = 0.01, 200000.0, 250.0
    elastic_radius = yield_radius_fraction * radius
    curvature = yield_stress / (modulus * elastic_radius)
    theta = math.asin(yield_radius_fraction)
    elastic_integral = radius**4 * (theta - math.sin(4 * theta) / 4) / 8
    plastic_integral = (radius**2 - elastic_radius**2) ** 1.5 / 3
    exact_moment = 4 * (
        modulus * curvature * elastic_integral + yield_stress * plastic_integral
    )
    if unload_ratio is not None:
        # EPP unloading has M(k) = M(k0) - 2 M_monotonic((k0-k)/2).
        # This continuum disk identity is independent of fiber state updates.
        half_reversal = curvature * (1 - unload_ratio) / 2
        core_radius = yield_stress / (modulus * half_reversal)
        if core_radius >= radius:
            reverse_moment = modulus * half_reversal * math.pi * radius**4 / 4
        else:
            angle = math.asin(core_radius / radius)
            elastic = radius**4 * (angle - math.sin(4 * angle) / 4) / 8
            plastic = (radius**2 - core_radius**2)**1.5 / 3
            reverse_moment = 4 * (
                modulus * half_reversal * elastic + yield_stress * plastic
            )
        exact_moment -= 2 * reverse_moment
    errors = []
    for points in [2, 8, 32, 64]:
        data = authored(points)
        data["materials"] = [m for m in data["materials"] if m["id"] != "hanger"]
        steel = next(m for m in data["materials"] if m["id"] == "steel")
        steel["isotropic_hardening_modulus_mpa"] = 0.0
        steel["kinematic_hardening_modulus_mpa"] = 0.0
        data["sections"][0]["steel_layers"] = [{
            "id": "central", "y_m": 0.0, "bar_count": 1,
            "bar_area_m2": math.pi * radius**2, "steel_material": "steel",
            "circular_integration_points": points,
        }]
        compiled, blockers, _ = _compile(model(data))
        assert not blockers
        section = compiled.problem.members[0].element.section
        # Isolate steel so concrete damage cannot mask bar integration error.
        terms = []
        for fiber in section.fibers:
            if fiber.material_kind != "steel":
                continue
            law = section.steel_material_for(fiber.fiber_id)
            response = law.integrate(curvature * fiber.y_m, law.initial_state())
            if unload_ratio is not None:
                committed = response.state
                before = committed.state_hash
                # An abandoned trial must not change the state used to unload.
                law.integrate(0.3 * curvature * fiber.y_m, committed)
                assert committed.state_hash == before
                response = law.integrate(
                    unload_ratio * curvature * fiber.y_m, committed
                )
            terms.append(fiber.area_m2 * fiber.y_m * response.stress_mpa)
        moment = math.fsum(terms)
        errors.append(abs(moment / exact_moment - 1))
    assert errors[-1] < 1e-3
    assert errors[-1] < errors[0] / 20
