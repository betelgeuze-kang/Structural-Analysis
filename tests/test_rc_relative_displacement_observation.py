"""Analytic observation and actual transactional workflow evidence, not specimen proof."""

from copy import deepcopy
from dataclasses import replace
import json
import math
from pathlib import Path

import numpy as np
import pytest

from structural_analysis.api.rc_corotational_control import (
    analyze_rc_corotational_control,
    compile_rc_control_observation,
    RCCorotationalControlExecutionError,
)
from structural_analysis.api.rc_corotational_control_model import (
    compile_rc_corotational_control_model,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d import (
    StatefulCorotationalFiberFrame2DProblem,
    initial_stateful_corotational_fiber_frame2d_checkpoint,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_control_subdivision import (
    run_corotational_control_subdivision,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_displacement_control import (
    LinearPhysicalDisplacementObservation,
    LINEAR_DISPLACEMENT_OBSERVATION_PROFILE,
    STATEFUL_COROTATIONAL_FIBER_FRAME2D_DISPLACEMENT_CONTROL_FORMULA_HASH,
    StatefulCorotationalFiberFrame2DDisplacementControlConfig,
    StatefulCorotationalFiberFrame2DDisplacementControlStepProblem,
    solve_stateful_corotational_fiber_frame2d_displacement_control_step,
    run_stateful_corotational_fiber_frame2d_displacement_control_path,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_solver import (
    solve_stateful_corotational_fiber_frame2d_load_step,
)
from structural_analysis.execution.job_worker import execute_job_claim
from structural_analysis.execution.rc_corotational_job_request import (
    validate_rc_corotational_job_request,
)
from structural_analysis.io.neutral.loader import load_neutral_json
from .test_stateful_corotational_fiber_frame2d_displacement_control import (
    _member,
    _nonlinear_fixed_axial_problem,
)
from .test_rc_corotational_durable_worker import (
    request,
    service_at,
    TENANT,
    WORKER,
    SECOND,
)


MODEL = (
    Path(__file__).parents[1]
    / "examples/public_rc_fiber_frame_l_frame_material_history.json"
)
DEFINITION = {
    "schema_version": "linear-physical-displacement-observation.v1",
    "terms": [
        {"node_id": "N3", "component": "UY", "coefficient": 1.0},
        {"node_id": "N1", "component": "UY", "coefficient": -1.0},
        {"node_id": "N1", "component": "RZ", "coefficient": -0.5},
    ],
}


def moving_cantilever():
    coordinates = ((0.0, 0.0), (1.0, 0.0))
    return StatefulCorotationalFiberFrame2DProblem(
        case_id="moving-support-observation-oracle",
        node_coordinates_m=coordinates,
        members=(_member(coordinates, "beam", 0, 1),),
        fixed_global_dofs=(0, 1, 2),
        prescribed_displacements=((0, 0.03), (1, -0.02), (2, 0.01)),
        reference_external_loads=((4, 1.0),),
        rotation_coordinate_scale_m=0.17,
    )


def test_physical_observation_gradient_and_prescribed_motion_against_independent_fd():
    problem = moving_cantilever()
    observation = LinearPhysicalDisplacementObservation(
        ((4, 1), (1, -1), (2, -0.7), (5, 0.2))
    )
    parent = initial_stateful_corotational_fiber_frame2d_checkpoint(problem)
    step = StatefulCorotationalFiberFrame2DDisplacementControlStepProblem(
        problem,
        parent,
        None,
        1e-5,
        StatefulCorotationalFiberFrame2DDisplacementControlConfig(),
        observation,
    )
    x = step.initial_augmented_coordinates_m()
    x[:-1] = (2e-6, -4e-6, 3e-7)
    x[-1] = 2e-5  # eta, not lambda
    assembled = step.assemble(x)
    physical = assembled.frame_assembly.global_displacements
    expected = physical[4] - physical[1] - 0.7 * physical[2] + 0.2 * physical[5]
    assert assembled.control_error_m == pytest.approx(expected - 1e-5, abs=1e-18)
    weight = assembled.control_equation_scale_kn_per_m
    beta = step.config.load_factor_coordinate_scale_m
    expected_gradient = np.array([0.0, 1.0, 0.2 / 0.17, (0.02 - 0.7 * 0.01) / beta])
    assert np.allclose(
        assembled.augmented_jacobian_kn_per_m[-1] / weight,
        expected_gradient,
        rtol=8 * np.finfo(float).eps,
        atol=8 * np.finfo(float).eps,
    )
    for index in range(len(x)):
        h = 1e-8 if index < len(x) - 1 else 1e-9
        xp, xm = x.copy(), x.copy()
        xp[index] += h
        xm[index] -= h
        finite = (
            step.assemble(xp).control_error_m - step.assemble(xm).control_error_m
        ) / (2 * h)
        assert finite == pytest.approx(expected_gradient[index], rel=1e-9, abs=1e-10)
    assert (
        parent.canonical_bytes()
        == initial_stateful_corotational_fiber_frame2d_checkpoint(
            problem
        ).canonical_bytes()
    )


def test_relative_cantilever_control_matches_euler_bernoulli_elastic_limit():
    problem = moving_cantilever()
    observation = LinearPhysicalDisplacementObservation(((4, 1), (1, -1), (2, -1)))
    parent = initial_stateful_corotational_fiber_frame2d_checkpoint(problem)
    target = 1e-6
    step = solve_stateful_corotational_fiber_frame2d_displacement_control_step(
        problem,
        parent,
        control_observation=observation,
        target_control_displacement_m=target,
    )
    assert step.committed
    section = problem.members[0].element.section
    ei_kn_m2 = math.fsum(
        200000.0 * 1000.0 * f.area_m2 * f.y_m**2 for f in section.fibers
    )
    expected_lambda = 3 * ei_kn_m2 * target  # F_ref=1 kN, L=1 m
    assert step.accepted_checkpoint.load_factor == pytest.approx(
        expected_lambda, rel=2e-5
    )
    u = step.accepted_checkpoint.global_displacements
    assert u[4] - u[1] - u[2] == pytest.approx(target, abs=1e-12)
    assert u[1] == pytest.approx(-0.02 * expected_lambda, rel=2e-5)
    # Absolute tip control is a different observable under moving supports.
    assert abs(u[4] - target) > 1e-10


def test_relative_linear_rigid_motion_oracle_does_not_claim_finite_rotation_drift():
    # Coordinates represent a support at x=L and center x=0, and two node RZs.
    length = 0.762
    observation = LinearPhysicalDisplacementObservation(((1, 1), (4, -1), (2, length)))
    for translation, theta in ((0.01, 0.02), (-0.03, -0.07)):
        u = [0.0, translation, theta, 0.0, translation + length * theta, theta]
        assert observation.evaluate(u) == pytest.approx(0.0, abs=1e-17)
        finite = [
            0.0,
            translation,
            theta,
            0.0,
            translation + length * math.sin(theta),
            theta,
        ]
        assert observation.evaluate(finite) == pytest.approx(
            length * (theta - math.sin(theta)), abs=8 * np.finfo(float).eps
        )
        assert abs(observation.evaluate(finite)) > 0


@pytest.mark.parametrize(
    "terms",
    [
        (),
        ((True, 1),),
        ((-1, 1),),
        ((4, True),),
        ((4, "1"),),
        ((4, 0),),
        ((4, float("nan")),),
        ((4, float("inf")),),
        ((4, 1), (4, -1)),
        ((4, 10**1000),),
    ],
)
def test_invalid_operator_terms_are_rejected(terms):
    with pytest.raises(ValueError):
        LinearPhysicalDisplacementObservation(terms)


@pytest.mark.parametrize("terms", [((6, 1),), ((1, 1), (2, -1)), ((4, 5e-324),)])
def test_out_of_range_and_no_free_gradient_rejection(terms):
    problem = moving_cantilever()
    if terms == ((4, 5e-324),):
        # Rotational scaling can underflow an otherwise nonzero raw coefficient.
        problem = replace(problem, rotation_coordinate_scale_m=1e308)
        terms = ((5, 5e-324),)
    with pytest.raises(ValueError):
        LinearPhysicalDisplacementObservation(terms).validate(problem)


def test_operator_identity_is_order_independent_and_changed_lever_is_distinct():
    a = LinearPhysicalDisplacementObservation(((4, 1), (1, -1), (2, -0.762)))
    b = LinearPhysicalDisplacementObservation(tuple(reversed(a.terms)))
    assert a.to_dict() == b.to_dict()
    assert a.identity_hash == b.identity_hash
    assert (
        a.identity_hash
        != LinearPhysicalDisplacementObservation(
            ((4, 1), (1, -1), (2, -0.761))
        ).identity_hash
    )


def test_unit_operator_preserves_legacy_numerics_and_material_state_at_same_source():
    p = moving_cantilever()
    parent = initial_stateful_corotational_fiber_frame2d_checkpoint(p)
    legacy = solve_stateful_corotational_fiber_frame2d_displacement_control_step(
        p, parent, control_global_dof=4, target_control_displacement_m=1e-6
    )
    selected = solve_stateful_corotational_fiber_frame2d_displacement_control_step(
        p,
        parent,
        control_observation=LinearPhysicalDisplacementObservation(((4, 1),)),
        target_control_displacement_m=1e-6,
    )
    assert legacy.committed and selected.committed
    assert (
        legacy.accepted_checkpoint.canonical_bytes()
        == selected.accepted_checkpoint.canonical_bytes()
    )
    assert (
        legacy.trial_solution.convergence_history
        == selected.trial_solution.convergence_history
    )
    assert (
        legacy.metrics["augmented_formula_hash"]
        == STATEFUL_COROTATIONAL_FIBER_FRAME2D_DISPLACEMENT_CONTROL_FORMULA_HASH
    )
    assert "control_observation" not in legacy.metrics
    assert selected.metrics["profile"] == LINEAR_DISPLACEMENT_OBSERVATION_PROFILE


def test_relative_observation_nonlinear_reversal_restart_failure_exact_rollback():
    p = _nonlinear_fixed_axial_problem()
    seed = initial_stateful_corotational_fiber_frame2d_checkpoint(p)
    pre = solve_stateful_corotational_fiber_frame2d_load_step(
        p, seed, target_load_factor=0
    )
    assert pre.committed
    # Support term is explicit even though this fixture's support displacement is zero.
    observation = LinearPhysicalDisplacementObservation(((3, 1), (0, -1), (2, -0.2)))
    targets = (0.005, 0.01, -0.005, -0.01, 0.005)
    kwargs = dict(
        control_observation=observation, initial_checkpoint=pre.accepted_checkpoint
    )
    full = run_corotational_control_subdivision(p, targets, **kwargs)
    assert full.contract_pass
    assert len(full.attempts) > len(targets)
    pause = run_corotational_control_subdivision(
        p, targets, attempt_limit_per_call=2, **kwargs
    )
    assert pause.status == "paused"
    resumed = run_corotational_control_subdivision(
        p, targets, continuation=pause.continuation, **kwargs
    )
    assert resumed.continuation == full.continuation
    assert (
        resumed.final_checkpoint.canonical_bytes()
        == full.final_checkpoint.canonical_bytes()
    )
    maxima = {"plastic_strain": 0.0, "tensile_damage": 0.0, "compressive_damage": 0.0}

    def visit(value):
        if type(value) is dict:
            for key, child in value.items():
                if key in maxima:
                    maxima[key] = max(maxima[key], abs(child))
                visit(child)
        elif type(value) is list:
            for child in value:
                visit(child)

    visit(full.final_checkpoint.to_dict())
    assert all(value > 0 for value in maxima.values())
    changed = LinearPhysicalDisplacementObservation(((3, 1), (0, -1), (2, -0.3)))
    with pytest.raises(ValueError, match="input, policy or source mismatch"):
        run_corotational_control_subdivision(
            p,
            targets,
            control_observation=changed,
            initial_checkpoint=pre.accepted_checkpoint,
            continuation=pause.continuation,
        )
    parent = pause.final_checkpoint
    raw = parent.canonical_bytes()
    failed = solve_stateful_corotational_fiber_frame2d_displacement_control_step(
        p,
        parent,
        control_observation=observation,
        target_control_displacement_m=-0.02,
        config=StatefulCorotationalFiberFrame2DDisplacementControlConfig(
            maximum_iterations=0
        ),
    )
    assert not failed.committed
    assert failed.accepted_checkpoint is parent
    assert failed.metrics["rollback_exact"] is True
    assert parent.canonical_bytes() == raw


def test_selected_public_api_request_restart_and_edited_operator_rejection():
    model = load_neutral_json(MODEL)
    compiled = compile_rc_corotational_control_model(model)
    operator = compile_rc_control_observation(compiled, DEFINITION)
    assert operator.terms == ((1, -1.0), (2, -0.5), (7, 1.0))
    targets = (-1e-6, -2e-6, -1.5e-6)
    options = dict(
        control_observation=DEFINITION, fixed_nodal_loads=(("N3", "FX", -0.01),)
    )
    paused = analyze_rc_corotational_control(
        model, targets, attempt_limit_per_call=1, **options
    )
    result = json.loads(paused.result_bytes)
    assert result["request"]["control_observation_hash"] == operator.identity_hash
    resumed = analyze_rc_corotational_control(
        model, targets, restart=paused.continuation_bytes, **options
    )
    assert json.loads(resumed.result_bytes)["contract_pass"]
    changed = deepcopy(DEFINITION)
    changed["terms"][2]["coefficient"] = -0.6
    with pytest.raises(RCCorotationalControlExecutionError) as caught:
        analyze_rc_corotational_control(
            model,
            targets,
            restart=paused.continuation_bytes,
            **dict(options, control_observation=changed),
        )
    assert "fresh complete-prefix replay" in str(caught.value.__cause__)
    with pytest.raises(ValueError, match="choose node/component"):
        analyze_rc_corotational_control(model, targets, control_node_id="N3", **options)


def observation_request():
    payload = request()
    payload["config"].pop("control_node_id")
    payload["config"].pop("control_component")
    payload["config"]["control_observation"] = deepcopy(DEFINITION)
    payload["execution_config"].update(
        attempt_limit_per_call=2, maximum_api_invocations=6
    )
    return payload


def test_durable_selected_operator_pause_reopen_report_and_integrity(
    tmp_path, monkeypatch
):
    payload = observation_request()
    typed = validate_rc_corotational_job_request(payload)
    assert typed.config.control_observation == (
        ("N3", "UY", 1.0),
        ("N1", "UY", -1.0),
        ("N1", "RZ", -0.5),
    )
    detached = typed.config.observation_dict()
    detached["terms"][0]["coefficient"] = 99
    assert typed.config.observation_dict()["terms"][0]["coefficient"] == 1
    service = service_at(tmp_path / "store")
    job = service.submit_job(
        **TENANT, idempotency_key="relative-control", request=payload
    )
    first = service.claim_next(**WORKER, lease_seconds=300)
    assert first is not None
    assert service.claim_next(**SECOND, lease_seconds=300) is None
    saved = execute_job_claim(service, first, **WORKER)
    assert saved.status == "checkpointed" and saved.progress_completed == 2
    reopened = service_at(tmp_path / "store")
    second = reopened.claim_next(**SECOND, lease_seconds=300)
    assert second is not None
    complete = execute_job_claim(reopened, second, **SECOND)
    assert complete.status == "succeeded" and complete.progress_completed == 3
    assert reopened.validate_integrity(job.job_id, **TENANT)["contract_pass"]
    observed = json.loads(reopened.read_result(job.job_id, **TENANT))
    assert observed["execution_budget"]["reserved_attempts"] == 4

    # The saved report consumer must not rerun analysis/replay or current source hashing.
    def forbidden(*args, **kwargs):
        pytest.fail("saved report invoked numerical or source work")

    monkeypatch.setattr(
        "structural_analysis.api.rc_corotational_control._source_identity", forbidden
    )
    monkeypatch.setattr(
        "structural_analysis.api.rc_corotational_control.analyze_rc_corotational_control",
        forbidden,
    )
    raw = reopened.read_rc_corotational_report(
        job.job_id,
        **TENANT,
        expected_request_hash=complete.request.content_hash,
        expected_result_artifact_hash=complete.result.content_hash,
        expected_evidence_artifact_hash=complete.evidence.content_hash,
    )
    report = json.loads(raw)
    assert report["declarations"]["control"]["observation"] == DEFINITION
    assert (
        report["declarations"]["control"]["operator"]
        == observed["api_result"]["request"]["control_observation"]
    )
    assert report["declarations"]["control"]["finite_rotation_drift"] is False
    for row in report["responses"]:
        u = row["nodes"]
        assert row["control_displacement_m"] == math.fsum(
            (
                u[2]["displacements_m_rad"][1],
                -u[0]["displacements_m_rad"][1],
                -0.5 * u[0]["displacements_m_rad"][2],
            )
        )
    from jsonschema import Draft202012Validator

    schema = json.loads(
        (
            Path(__file__).parents[1]
            / "src/structural_analysis/schemas/rc_corotational_report_v1.schema.json"
        ).read_bytes()
    )
    Draft202012Validator(schema).validate(report)


def test_selected_direct_path_has_reversal_and_target_cap_without_reduction():
    problem = moving_cantilever()
    observation = LinearPhysicalDisplacementObservation(((4, 1), (1, -1), (2, -1)))
    targets = (1e-6, -1e-6, 2e-6)
    path = run_stateful_corotational_fiber_frame2d_displacement_control_path(
        problem, targets, control_observation=observation, allow_reversal=True
    )
    assert path.contract_pass and len(path.steps) == len(targets)
    assert path.to_dict()["control_observation_hash"] == observation.identity_hash
    assert "not finite-rotation drift" in path.to_dict()["claim_boundary"]
    for target, step in zip(targets, path.steps, strict=True):
        assert observation.evaluate(
            step.accepted_checkpoint.global_displacements
        ) == pytest.approx(target, abs=1e-12)
    with pytest.raises(ValueError, match="bounded path length"):
        run_stateful_corotational_fiber_frame2d_displacement_control_path(
            problem,
            tuple(1e-6 * i for i in range(1, 257)),
            control_observation=observation,
        )


@pytest.mark.parametrize(
    "change",
    ["bool", "zero", "duplicate", "unknown", "support_only", "extra", "mixed_legacy"],
)
def test_selected_public_admission_rejects_malformed_operator_before_solving(
    change, monkeypatch
):
    payload = observation_request()
    definition = payload["config"]["control_observation"]
    if change == "bool":
        definition["terms"][0]["coefficient"] = True
    if change == "zero":
        definition["terms"][0]["coefficient"] = 0
    if change == "duplicate":
        definition["terms"].append(deepcopy(definition["terms"][0]))
    if change == "unknown":
        definition["terms"][0]["node_id"] = "missing"
    if change == "support_only":
        definition["terms"] = definition["terms"][1:]
    if change == "extra":
        definition["unit"] = "m"
    if change == "mixed_legacy":
        payload["config"]["control_node_id"] = "N3"

    def forbidden(*args, **kwargs):
        pytest.fail("invalid operator invoked preload")

    monkeypatch.setattr(
        "structural_analysis.api.rc_corotational_control.solve_stateful_corotational_fiber_frame2d_load_step",
        forbidden,
    )
    with pytest.raises(ValueError):
        validate_rc_corotational_job_request(payload)
    if change != "mixed_legacy":
        with pytest.raises(ValueError):
            analyze_rc_corotational_control(
                load_neutral_json(MODEL), (-1e-6,), control_observation=definition
            )


@pytest.mark.parametrize("coefficient", [2**53, 2**53 + 1, -(2**53), -(2**53 + 1)])
def test_exact_integer_boundary_rejects_native_direct_public_and_durable_aliases(
    coefficient, monkeypatch
):
    with pytest.raises(ValueError, match="finite number"):
        LinearPhysicalDisplacementObservation(((7, coefficient),))
    model = load_neutral_json(MODEL)
    compiled = compile_rc_corotational_control_model(model)
    definition = {
        "schema_version": "linear-physical-displacement-observation.v1",
        "terms": [{"node_id": "N3", "component": "UY", "coefficient": coefficient}],
    }
    with pytest.raises(ValueError, match="finite number"):
        compile_rc_control_observation(compiled, definition)

    def forbidden(*args, **kwargs):
        pytest.fail("unsafe integer observation invoked preload")

    monkeypatch.setattr(
        "structural_analysis.api.rc_corotational_control.solve_stateful_corotational_fiber_frame2d_load_step",
        forbidden,
    )
    with pytest.raises(ValueError, match="finite number"):
        analyze_rc_corotational_control(model, (-1e-6,), control_observation=definition)
    payload = observation_request()
    payload["config"]["control_observation"] = definition
    with pytest.raises(ValueError, match="safe finite JSON number"):
        validate_rc_corotational_job_request(payload)


def test_largest_safe_integer_coefficient_is_preserved_losslessly():
    raw = 2**53 - 1
    operator = LinearPhysicalDisplacementObservation(((7, raw),))
    assert int(operator.terms[0][1]) == raw
    assert operator.terms[0][1] == raw
    # A deliberately authored binary64 float retains its own exact float type.
    assert LinearPhysicalDisplacementObservation(((7, float(2**53)),)).terms[0][
        1
    ] == float(2**53)


@pytest.mark.parametrize("released_tip", [False, True])
def test_selected_native_member_load_column_fd_and_independent_cantilever_limit(
    released_tip,
):
    from structural_analysis.assembly.corotational_frame2d_member_features import (
        CorotationalFrame2DMemberFeatures,
    )

    base = moving_cantilever()
    member = replace(
        base.members[0],
        features=CorotationalFrame2DMemberFeatures(
            uniform_load_local_kn_per_m=(0.0, 1.0), release_j_rz=released_tip
        ),
    )
    problem = replace(
        base,
        members=(member,),
        reference_external_loads=(),
        prescribed_displacements=(),
        fixed_global_dofs=(0, 1, 2, 5) if released_tip else (0, 1, 2),
    )
    observation = LinearPhysicalDisplacementObservation(((4, 1), (1, -1), (2, -1)))
    parent = initial_stateful_corotational_fiber_frame2d_checkpoint(problem)
    cfg = StatefulCorotationalFiberFrame2DDisplacementControlConfig()
    step_problem = StatefulCorotationalFiberFrame2DDisplacementControlStepProblem(
        problem, parent, None, 1e-6, cfg, observation
    )
    x = step_problem.initial_augmented_coordinates_m()
    assembly = step_problem.assemble(x)
    assert np.linalg.norm(assembly.load_factor_residual_derivative_kn, ord=np.inf) > 0
    h_lambda = 1e-6
    forward, backward = x.copy(), x.copy()
    forward[-1] += h_lambda * cfg.load_factor_coordinate_scale_m
    backward[-1] -= h_lambda * cfg.load_factor_coordinate_scale_m
    finite = (
        step_problem.assemble(forward).frame_assembly.residual_kn
        - step_problem.assemble(backward).frame_assembly.residual_kn
    ) / (2 * h_lambda)
    assert np.allclose(
        finite, assembly.load_factor_residual_derivative_kn, rtol=1e-6, atol=1e-8
    )
    step = solve_stateful_corotational_fiber_frame2d_displacement_control_step(
        problem,
        parent,
        control_observation=observation,
        target_control_displacement_m=1e-6,
    )
    assert step.committed
    section = problem.members[0].element.section
    ei_kn_m2 = math.fsum(
        200000.0 * 1000.0 * f.area_m2 * f.y_m**2 for f in section.fibers
    )
    # UDL q=1 kN/m; independent Euler-Bernoulli tip deflection qL^4/(8EI), L=1m.
    assert step.accepted_checkpoint.load_factor == pytest.approx(
        8 * ei_kn_m2 * 1e-6, rel=2e-5
    )
    assert observation.evaluate(
        step.accepted_checkpoint.global_displacements
    ) == pytest.approx(1e-6, abs=1e-12)
