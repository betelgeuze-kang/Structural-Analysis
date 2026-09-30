"""Finite-coordinate arithmetic and original authority under an explicit profile."""

from dataclasses import replace
from decimal import Decimal, localcontext
import json
import importlib.util
from pathlib import Path

import numpy as np
import pytest

from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    BoundedRCFiberDirectControlRequest,
)
from structural_analysis.benchmark.rc_control_seed_runtime import (
    benchmark_rc_control_seed_paths,
)
from structural_analysis.elements import StatefulFiberBeam2D
from structural_analysis.elements.fiber_beam2d_strain import exact_fiber_beam2d_strain
from structural_analysis.io.neutral.loader import load_neutral_json
from structural_analysis.materials import make_rectangular_stateful_rc_fiber_section


@pytest.mark.parametrize("length", [1.5, 2.0, 3.7])
@pytest.mark.parametrize("xi", [-0.7745966692414834, 0.0, 0.7745966692414834])
def test_exact_profile_matches_independent_decimal_polynomial(length, xi):
    u = [1e8, 0.018, 0.012, 1e8 + 0.0003, 0.036000000000000004, 0.012]
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
    result = exact_fiber_beam2d_strain(u, length, xi)
    assert np.array_equal(result, list(map(float, expected)))
    assert not result.flags.writeable


@pytest.mark.parametrize(
    "local,length,xi",
    [
        ([0.0] * 5, 2, 0),
        ([False, 0, 0, 0, 0, 0], 2, 0),
        ([0, 0, np.nan, 0, 0, 0], 2, 0),
        ([0.0] * 6, True, 0),
        ([0.0] * 6, 0, 0),
        ([0.0] * 6, 1, 2),
        ([0, 0, 0, 1e300, 0, 0], 1e-300, 0),
    ],
)
def test_invalid_or_unrepresentable_kinematics_are_rejected(local, length, xi):
    with pytest.raises(ValueError):
        exact_fiber_beam2d_strain(local, length, xi)


def test_profile_binds_parents_and_exact_strain_state_without_changing_default():
    default = StatefulFiberBeam2D(
        make_rectangular_stateful_rc_fiber_section(), length_m=1.5
    )
    matrix = replace(default, strain_evaluation="matrix")
    exact = replace(default, strain_evaluation="exact-rational")
    assert default.contract_hash == matrix.contract_hash != exact.contract_hash
    u = np.array([0, 0.018, 0.012, 0.0003, 0.036000000000000004, 0.012])
    a = default.integrate(u, default.initial_state())
    b = matrix.integrate(u, matrix.initial_state())
    assert (
        a.to_dict() == b.to_dict()
        and a.state.canonical_bytes() == b.state.canonical_bytes()
    )
    assert "strain_evaluation" not in a.to_dict()
    with pytest.raises(ValueError, match="element_contract_hash"):
        exact.integrate(u, default.initial_state())
    parent = exact.initial_state()
    before = parent.canonical_bytes()
    response = exact.integrate(u, parent)
    assert parent.canonical_bytes() == before
    assert response.to_dict()["strain_evaluation"] == "exact-rational"
    exact.validate_state(response.state)
    for xi, g in zip(exact.quadrature[0], response.generalized_strains, strict=True):
        assert np.array_equal(g, exact_fiber_beam2d_strain(u, exact.length_m, xi))
    section = response.state.integration_point_states[0]
    tampered = replace(
        response.state,
        integration_point_states=(
            replace(section, curvature_z_per_m=section.curvature_z_per_m + 1e-16),
            *response.state.integration_point_states[1:],
        ),
    )
    with pytest.raises(ValueError, match="generalized strain"):
        exact.validate_state(tampered)


def test_consistent_tangent_remains_derivative_of_exact_profile_response():
    element = StatefulFiberBeam2D(
        make_rectangular_stateful_rc_fiber_section(), strain_evaluation="exact-rational"
    )
    parent = element.initial_state()
    u = np.array([0, 0, 0, -0.0002, 0.0001, 0.00003])
    response = element.integrate(u, parent)
    columns = []
    for i in range(6):
        du = np.zeros(6)
        du[i] = 1e-8
        columns.append(
            (
                element.integrate(u + du, parent).internal_force_local
                - element.integrate(u - du, parent).internal_force_local
            )
            / (2e-8)
        )
    np.testing.assert_allclose(
        np.column_stack(columns),
        response.consistent_tangent_local,
        rtol=2e-7,
        atol=1e-5,
    )


def test_complete_cyclic_paths_recover_with_the_selected_contract(tmp_path):
    model = load_neutral_json(
        Path("examples/public_rc_fiber_frame_l_frame_material_history.json")
    )
    request = BoundedRCFiberDirectControlRequest(
        7,
        (-1e-5, -2e-5, -1e-5, 1e-5, 0, -0.5e-5),
        allow_reversals=True,
        maximum_reversals=2,
    )
    root = tmp_path / "study"
    report = benchmark_rc_control_seed_paths(
        model,
        request,
        source_revision="0" * 40,
        output_directory=root,
        strain_evaluation="exact-rational",
    )
    assert (
        report["strain_evaluation"] == "exact-rational"
        and report["reference_repeat_exact"]
    )
    assert report["all_execution_work_reported"]
    for arm in ["reference", "secant", "fresh-reference"]:
        path = json.loads((root / arm / "path.json").read_text())
        assert path["status"] == "complete" and path["accepted_target_count"] == 6
        for i in range(6):
            step = json.loads((root / arm / f"{i:03d}-1-step.json").read_text())
            assert step["committed"]
            assert (
                step["parent_checkpoint"]["problem_contract_hash"]
                == report["compiled_problem_contract_hash"]
            )
            assert step["metrics"]["solver_assembly_coordinate_residual_binding_passed"]
            assert all(
                m["element_response"]["strain_evaluation"] == "exact-rational"
                for m in step["trial_assembly"]["member_assemblies"]
            )
    spec = importlib.util.spec_from_file_location(
        "profile_diagnostic", Path("scripts/diagnose_rc_control_section_error.py")
    )
    diagnostic = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(diagnostic)
    audit = diagnostic.diagnose(root, "secant")
    assert audit["strain_evaluation"] == "exact-rational"
    for row in audit["rows"]:
        for order in row["orders"].values():
            assert order["components_N_Nm"]["reference_kinematic_evaluation"] == [0, 0]
            assert order["components_N_Nm"]["candidate_kinematic_evaluation"] == [0, 0]
    with pytest.raises(ValueError, match="unsupported fiber beam strain evaluation"):
        benchmark_rc_control_seed_paths(
            model,
            request,
            source_revision="0" * 40,
            output_directory=tmp_path / "invalid",
            strain_evaluation="adaptive",
        )
    assert not (tmp_path / "invalid").exists()
