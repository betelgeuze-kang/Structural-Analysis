"""Independent small-displacement reference for the authored RC portal.

The reference assembles textbook Euler--Bernoulli frame matrices directly from
the request, without importing production stiffness/section/assembly functions.
The bending matrix is documented at TU Delft:
https://teachbooks.tudelft.nl/computational-modelling/structural_linear/euler_bernouilli.html

This is an elastic-limit software comparison, not an OpenSees execution, an
independent operator review, or qualification of nonlinear/physical RC behavior.
The actual corotational response retains gravity and finite-geometry effects;
the fixed comparison tolerances allow their small effect at the declared drift.
"""

import json
from pathlib import Path

import numpy as np
import pytest

from structural_analysis.api.rc_corotational_control import (
    analyze_rc_corotational_control,
)
from structural_analysis.execution.rc_corotational_job_request import (
    validate_rc_corotational_job_request,
)


REQUEST_PATH = (
    Path(__file__).parents[1]
    / "examples/public_rc_portal_frame_corotational_request.json"
)
# Declared before measurement: the reference omits finite-geometry terms.
ELASTIC_LIMIT_RTOL = 5e-4
DISPLACEMENT_ATOL = 2e-10  # m or rad
FORCE_ATOL = 2e-7  # kN or kN m
EQUILIBRIUM_ATOL = 5e-8  # kN or kN m


def _rigidities(model):
    """Discrete midpoint concrete plus added steel; no gross-I substitution."""
    (section,) = model["sections"]
    materials = {row["id"]: row for row in model["materials"]}
    concrete = materials[section["concrete_material"]]
    steel = materials[section["steel_material"]]
    assert section["top_bar_count"] == section["bottom_bar_count"]
    width, depth = section["width_m"], section["depth_m"]
    layers = section["concrete_layer_count"]
    steel_area = (section["top_bar_count"] + section["bottom_bar_count"]) * section[
        "bar_area_m2"
    ]
    bar_y = depth / 2 - section["cover_m"]
    concrete_e = concrete["elastic_modulus_mpa"] * 1000
    steel_e = steel["elastic_modulus_mpa"] * 1000
    ea = concrete_e * width * depth + steel_e * steel_area
    # Sum of equally spaced midpoint y**2, not continuous rectangular I.
    ei = (
        concrete_e * width * depth**3 / 12 * (1 - 1 / layers**2)
        + steel_e * steel_area * bar_y**2
    )
    return ea, ei


def _elastic_reference(payload):
    """12-DOF matrix assembled solely from authored geometry and material data."""
    model = payload["model"]
    node_ids = [row["id"] for row in model["nodes"]]
    coordinates = np.array([row["coordinates"][:2] for row in model["nodes"]])
    offsets = {node: 3 * index for index, node in enumerate(node_ids)}
    size = 3 * len(node_ids)
    stiffness = np.zeros((size, size))
    ea, ei = _rigidities(model)
    for element in model["elements"]:
        node_i, node_j = element["nodes"]
        i, j = node_ids.index(node_i), node_ids.index(node_j)
        delta = coordinates[j] - coordinates[i]
        length = np.linalg.norm(delta)
        c, s = delta / length
        axial = ea / length
        a, b = 12 * ei / length**3, 6 * ei / length**2
        d, e = 4 * ei / length, 2 * ei / length
        local = np.array(
            [
                [axial, 0, 0, -axial, 0, 0],
                [0, a, b, 0, -a, b],
                [0, b, d, 0, -b, e],
                [-axial, 0, 0, axial, 0, 0],
                [0, -a, -b, 0, a, -b],
                [0, b, e, 0, -b, d],
            ]
        )
        rotation = np.array([[c, s, 0], [-s, c, 0], [0, 0, 1]])
        transform = np.zeros((6, 6))
        transform[:3, :3] = transform[3:, 3:] = rotation
        dofs = [offsets[node] + k for node in (node_i, node_j) for k in range(3)]
        stiffness[np.ix_(dofs, dofs)] += transform.T @ local @ transform

    components = {"FX": 0, "FY": 1, "MZ": 2}
    reference_load = np.zeros(size)
    gravity = np.zeros(size)
    for load in model["loads"]:
        for component, offset in components.items():
            reference_load[offsets[load["node"]] + offset] += load["components"].get(
                component, 0
            )
    for node, component, value in payload["config"]["fixed_nodal_loads"]:
        gravity[offsets[node] + components[component]] += value
    support_components = {"UX": 0, "UY": 1, "RZ": 2}
    fixed = sorted(
        offsets[row["node"]] + support_components[component]
        for row in model["supports"]
        for component in row["dofs"]
    )
    free = sorted(set(range(size)) - set(fixed))
    reduced = stiffness[np.ix_(free, free)]
    gravity_u, reference_u = np.zeros(size), np.zeros(size)
    gravity_u[free] = np.linalg.solve(reduced, gravity[free])
    reference_u[free] = np.linalg.solve(reduced, reference_load[free])
    control = (
        offsets[payload["config"]["control_node_id"]]
        + support_components[payload["config"]["control_component"]]
    )
    return {
        "node_ids": node_ids,
        "coordinates": coordinates,
        "stiffness": stiffness,
        "free": free,
        "fixed": fixed,
        "gravity": gravity,
        "reference_load": reference_load,
        "gravity_u": gravity_u,
        "reference_u": reference_u,
        "control": control,
        "ea": ea,
        "ei": ei,
    }


@pytest.fixture(scope="module")
def portal_result():
    payload = json.loads(REQUEST_PATH.read_bytes())
    request = validate_rc_corotational_job_request(payload)
    options = request.api_kwargs()
    # Same physical path, one invocation. Pause/restart equivalence is exercised
    # by the separate public portal API tests, rather than repeating it here.
    options["attempt_limit_per_call"] = None
    artifacts = analyze_rc_corotational_control(
        request.model, request.targets_m, **options
    )
    result = json.loads(artifacts.result_bytes)
    assert result["contract_pass"], result["terminal_reason"]
    assert result["status"] == "ready"
    assert result["completed_target_count"] == 3
    assert result["work"] == {
        "preload_solver_calls": 1,
        "restart_replay_solver_calls": 0,
        "control_solver_calls": 3,
        "unavailable_execution_work": False,
    }
    return payload, result


def test_independent_portal_matrix_matches_symmetric_gravity_closed_form():
    payload = json.loads(REQUEST_PATH.read_bytes())
    reference = _elastic_reference(payload)
    assert reference["ea"] == pytest.approx(7_819_200)
    assert reference["ei"] == pytest.approx(200_700)
    assert payload["model"]["elements"][-1]["nodes"] == ["N4", "N2"]
    np.testing.assert_allclose(reference["stiffness"], reference["stiffness"].T)
    eigenvalues = np.linalg.eigvalsh(
        reference["stiffness"][np.ix_(reference["free"], reference["free"])]
    )
    assert eigenvalues.min() > 0
    expected_u = np.zeros(12)
    expected_u[[7, 10]] = -3 / reference["ea"]
    np.testing.assert_allclose(reference["gravity_u"], expected_u, atol=1e-20)
    expected_reactions = np.zeros(12)
    expected_reactions[[1, 4]] = 1
    np.testing.assert_allclose(
        reference["stiffness"] @ reference["gravity_u"] - reference["gravity"],
        expected_reactions,
        atol=1e-12,
    )


def test_portal_gravity_and_reversing_lateral_path_match_independent_elastic_limit(
    portal_result,
):
    payload, result = portal_result
    reference = _elastic_reference(payload)
    assert payload["config"]["targets_m"] == [1e-5, -1e-5, 2e-5]
    assert [row["phase"] for row in result["responses"]] == [
        "preload",
        "control",
        "control",
        "control",
    ]
    for index, response in enumerate(result["responses"]):
        nodes = {row["node_id"]: row for row in response["nodes"]}
        actual_u = np.array(
            [nodes[node]["displacements_m_rad"] for node in reference["node_ids"]]
        ).ravel()
        actual_reactions = np.array(
            [nodes[node]["reactions_kn_knm"] for node in reference["node_ids"]]
        ).ravel()
        actual_loads = np.array(
            [nodes[node]["external_loads_kn_knm"] for node in reference["node_ids"]]
        ).ravel()
        factor = 0.0
        if index:
            target = payload["config"]["targets_m"][index - 1]
            factor = (target - reference["gravity_u"][reference["control"]]) / (
                reference["reference_u"][reference["control"]]
            )
            assert actual_u[reference["control"]] == pytest.approx(target, abs=1e-12)
        expected_u = reference["gravity_u"] + factor * reference["reference_u"]
        expected_reactions = (
            reference["stiffness"] @ expected_u
            - reference["gravity"]
            - factor * reference["reference_load"]
        )
        np.testing.assert_allclose(
            actual_u, expected_u, rtol=ELASTIC_LIMIT_RTOL, atol=DISPLACEMENT_ATOL
        )
        np.testing.assert_allclose(
            actual_reactions,
            expected_reactions,
            rtol=ELASTIC_LIMIT_RTOL,
            atol=FORCE_ATOL,
        )
        assert response["load_factor"] == pytest.approx(
            factor, rel=ELASTIC_LIMIT_RTOL, abs=FORCE_ATOL
        )
        np.testing.assert_allclose(
            actual_loads,
            reference["gravity"]
            + response["load_factor"] * reference["reference_load"],
            atol=1e-14,
        )
        # Rigid-body balance belongs to the current, deformed coordinates.
        forces = (actual_loads + actual_reactions).reshape(-1, 3)
        current_xy = reference["coordinates"] + actual_u.reshape(-1, 3)[:, :2]
        moment = np.sum(
            current_xy[:, 0] * forces[:, 1]
            - current_xy[:, 1] * forces[:, 0]
            + forces[:, 2]
        )
        np.testing.assert_allclose(forces[:, :2].sum(axis=0), 0, atol=EQUILIBRIUM_ATOL)
        assert abs(moment) < EQUILIBRIUM_ATOL


def test_portal_reference_comparison_stays_in_declared_initial_material_tangents(
    portal_result,
):
    payload, result = portal_result
    ea, ei = _rigidities(payload["model"])
    materials = {row["id"]: row for row in payload["model"]["materials"]}
    concrete, steel = materials["concrete"], materials["steel"]
    (section,) = payload["model"]["sections"]
    layers = section["concrete_layer_count"]
    assert result["claims"]["independent_physical_validation"] is False
    for response in result["responses"]:
        for member in response["members"]:
            beam = member["element_response"]["fiber_beam_response"]
            assert beam["yielded_integration_point_count"] == 0
            assert beam["damaged_integration_point_count"] == 0
            assert beam["dissipated_energy_mj"] == 0
            for point in beam["section_responses"]:
                assert point["yielded_steel_fiber_count"] == 0
                assert point["damaged_concrete_fiber_count"] == 0
                assert point["dissipated_energy_mj_per_m"] == 0
                np.testing.assert_allclose(
                    point["consistent_tangent"],
                    np.diag([ea, ei]),
                    rtol=2e-12,
                    atol=1e-7,
                )
                strains = np.asarray(point["fiber_strains"])
                assert np.max(strains[:layers]) < (
                    concrete["tensile_strength_mpa"] / concrete["elastic_modulus_mpa"]
                )
                assert np.min(strains[:layers]) > (
                    -concrete["compressive_strength_mpa"]
                    / concrete["elastic_modulus_mpa"]
                )
                assert np.max(np.abs(strains[layers:])) < (
                    steel["yield_stress_mpa"] / steel["elastic_modulus_mpa"]
                )
