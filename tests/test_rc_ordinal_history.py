"""Authored native software oracles, not actual CC material/specimen validation."""

from dataclasses import replace
import json
import time

import numpy as np
import pytest

from structural_analysis.assembly.stateful_corotational_fiber_frame2d import (
    StatefulCorotationalFiberFrame2DProblem,
    StatefulCorotationalFiberFrame2DMember,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_displacement_control import (
    LinearPhysicalDisplacementObservation,
    StatefulCorotationalFiberFrame2DDisplacementControlConfig,
    StatefulCorotationalFiberFrame2DDisplacementControlStepProblem,
    solve_stateful_corotational_fiber_frame2d_displacement_control,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_ordinal_history import (
    HistoryRow,
    OrdinalHistoryPlan,
    ScheduledFrameProblem,
    ScheduledControlStepProblem,
    initial_mechanical_checkpoint,
    assemble_scheduled_frame,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_ordinal_driver import (
    run_ordinal_history,
    dump_ordinal_continuation,
    load_ordinal_continuation,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.elements import StatefulCorotationalFiberBeam2D
from structural_analysis.materials.stateful_fiber_section import (
    StatefulRCFiberSection,
    StatefulSectionFiber,
)
from structural_analysis.materials import (
    BilinearCombinedHardeningSteel,
    AsymmetricConcreteDamageMaterial,
)
from .test_stateful_corotational_fiber_frame2d_displacement_control import (
    _nonlinear_fixed_axial_problem,
)
from .test_rc_relative_displacement_observation import moving_cantilever

CONFIG = StatefulCorotationalFiberFrame2DDisplacementControlConfig(
    load_factor_increment_tolerance=1e-8, increment_tolerance_m=1e-10
)
SHA = "sha256:" + "1" * 64


def axial_problem(*, fixed_load=0.0):
    coordinates = ((0.0, 0.0), (1.0, 0.0))
    section = StatefulRCFiberSection(
        fibers=(
            StatefulSectionFiber("s", -0.01, 0.0001, "steel"),
            StatefulSectionFiber("c", 0.01, 0.0001, "concrete"),
        ),
        steel=BilinearCombinedHardeningSteel(
            elastic_modulus_mpa=200000.0,
            yield_stress_mpa=1e12,
            isotropic_hardening_modulus_mpa=0.0,
            kinematic_hardening_modulus_mpa=0.0,
        ),
        concrete=AsymmetricConcreteDamageMaterial(
            elastic_modulus_mpa=200000.0,
            tensile_strength_mpa=1e12,
            compressive_strength_mpa=1e12,
            tensile_softening_rate=1.0,
            compressive_softening_rate=1.0,
        ),
        section_id="authored-two-fiber-elastic",
    )
    member = StatefulCorotationalFiberFrame2DMember(
        "axial",
        0,
        1,
        StatefulCorotationalFiberBeam2D(
            coordinates, section, integration_order=2, element_id="axial"
        ),
    )
    frame = StatefulCorotationalFiberFrame2DProblem(
        case_id="authored-axial-schedule",
        node_coordinates_m=coordinates,
        members=(member,),
        fixed_global_dofs=(0, 1, 2, 4, 5),
        reference_external_loads=((3, 1.0),),
        fixed_external_loads=() if fixed_load == 0.0 else ((3, fixed_load),),
        rotation_coordinate_scale_m=1.0,
    )
    return ScheduledFrameProblem(
        frame, LinearPhysicalDisplacementObservation(((3, 1.0), (0, -1.0))), ((3, 1.0),)
    )


def plan(values):
    rows = tuple(
        HistoryRow(i, i, canonical_hash({"raw": i, "values": (g, p)}), g, p)
        for i, (g, p) in enumerate(values)
    )
    return OrdinalHistoryPlan(
        rows,
        "authored-software-oracle",
        SHA,
        canonical_hash({"mapping": "explicit g(m), independent P(kN)"}),
    )


def run_all(problem, path, budget, **kwargs):
    continuation = None
    events = []
    while True:
        result = run_ordinal_history(
            problem,
            path,
            maximum_solver_attempts=budget,
            config=CONFIG,
            continuation=continuation,
            **kwargs,
        )
        events.extend(result.events)
        continuation = result.continuation
        if result.status != "paused":
            return result, events


def test_independent_dead_load_equilibrium_reaction_and_same_g_new_p():
    problem = axial_problem()
    path = plan(((1e-5, 0.1), (1e-5, 0.25), (1e-5, 0.25), (-2e-5, -0.2)))
    first = run_ordinal_history(
        problem, path, maximum_solver_attempts=4, config=CONFIG, per_call_record_limit=1
    )
    second = run_ordinal_history(
        problem,
        path,
        maximum_solver_attempts=4,
        config=CONFIG,
        continuation=first.continuation,
        per_call_record_limit=1,
    )
    assert first.continuation.mechanical.frame_checkpoint.load_factor == pytest.approx(
        0.4 - 0.1, abs=1e-10
    )
    assert second.continuation.mechanical.frame_checkpoint.load_factor == pytest.approx(
        0.4 - 0.25, abs=1e-10
    )
    assert second.continuation.mechanical.frame_checkpoint.epoch == 2
    parent = second.continuation.mechanical
    before = parent.canonical_bytes()
    held = run_ordinal_history(
        problem,
        path,
        maximum_solver_attempts=4,
        config=CONFIG,
        continuation=second.continuation,
        per_call_record_limit=1,
    )
    assert held.events[0]["kind"] == "verified_hold"
    assert held.continuation.mechanical is parent and parent.canonical_bytes() == before
    assert (
        held.continuation.mechanical.last_mechanical_ordinal == 1
        and held.continuation.next_ordinal == 3
    )
    assert (
        held.continuation.reserved_attempts == 2 and held.continuation.hold_records == 1
    )
    final = run_ordinal_history(
        problem,
        path,
        maximum_solver_attempts=4,
        config=CONFIG,
        continuation=held.continuation,
    )
    assert (
        final.status == "complete"
        and final.continuation.mechanical.frame_checkpoint.epoch == 3
    )
    state = final.continuation.mechanical
    assembled = assemble_scheduled_frame(
        problem,
        state,
        state.context_hash,
        target_axial_load_kn=state.axial_load_kn,
        target_load_factor=state.frame_checkpoint.load_factor,
        trial_free_coordinates_m=np.array([-2e-5]),
    )
    assert assembled.external_loads_global[3] == pytest.approx(-0.8, abs=1e-10)
    assert assembled.reactions_global[0] == pytest.approx(0.8, abs=1e-10)
    assert np.max(np.abs(assembled.residual_kn)) < 1e-10


def test_scheduled_lambda_column_and_control_gradient_match_independent_fd_with_moving_supports():
    base = moving_cantilever()
    problem = ScheduledFrameProblem(
        base,
        LinearPhysicalDisplacementObservation(
            ((4, 1.0), (1, -1.0), (2, -0.7), (5, 0.2))
        ),
        ((3, -1.0), (0, 1.0)),
    )
    context = SHA
    parent = initial_mechanical_checkpoint(problem, context)
    step = ScheduledControlStepProblem(problem, parent, context, 1e-5, -0.25, CONFIG)
    x = np.array([2e-6, -4e-6, 3e-7, 2e-5])
    assembly = step.assemble(x)
    for i in range(len(x)):
        h = 1e-8 if i < len(x) - 1 else 1e-9
        xp = x.copy()
        xm = x.copy()
        xp[i] += h
        xm[i] -= h
        fd = (
            step.assemble(xp).augmented_residual_kn
            - step.assemble(xm).augmented_residual_kn
        ) / (2 * h)
        assert np.allclose(
            fd, assembly.augmented_jacobian_kn_per_m[:, i], rtol=2e-5, atol=2e-4
        )
    base_external = assembly.frame_assembly.constitutive_trial.external_loads_global
    assert np.array_equal(
        assembly.frame_assembly.external_loads_global,
        base_external + problem.pattern() * -0.25,
    )
    assert (
        parent.canonical_bytes()
        == initial_mechanical_checkpoint(problem, context).canonical_bytes()
    )


def test_genesis_zero_target_with_fixed_force_is_solved_and_never_held():
    problem = axial_problem(fixed_load=0.2)
    result, _ = run_all(problem, plan(((0.0, 0.0), (0.0, 0.0))), 2)
    assert result.status == "complete"
    assert result.continuation.mechanical.frame_checkpoint.load_factor == pytest.approx(
        -0.2, abs=1e-12
    )
    assert (
        result.continuation.reserved_attempts == 1
        and result.continuation.hold_records == 1
    )


@pytest.mark.parametrize("count", [254, 255, 256])
def test_whole_history_attempt_budget_cannot_reset_at_batch_boundary(count):
    problem = axial_problem()
    path = plan(
        tuple(((1 if i % 2 == 0 else -1) * 1e-5, i * 0.001) for i in range(count))
    )
    result, events = run_all(
        problem, path, count, per_call_attempt_limit=17, per_call_record_limit=19
    )
    assert (
        result.status == "complete" and result.continuation.reserved_attempts == count
    )
    assert len(events) == count and [e["ordinal"] for e in events] == list(range(count))
    if count == 256:
        limited = run_ordinal_history(
            problem, path, maximum_solver_attempts=255, config=CONFIG
        )
        exhausted = run_ordinal_history(
            problem,
            path,
            maximum_solver_attempts=255,
            config=CONFIG,
            continuation=limited.continuation,
        )
        assert (
            exhausted.status == "budget_exhausted"
            and exhausted.continuation.next_ordinal == 255
        )
        with pytest.raises(ValueError, match="identity"):
            run_ordinal_history(
                problem,
                path,
                maximum_solver_attempts=256,
                config=CONFIG,
                continuation=exhausted.continuation,
            )


def test_restart_codec_and_complete_identity_reject_edits_without_numerical_replay():
    problem = axial_problem()
    path = plan(((1e-5, 0.1), (-2e-5, 0.2), (3e-5, -0.1)))
    first = run_ordinal_history(
        problem, path, maximum_solver_attempts=9, config=CONFIG, per_call_record_limit=1
    )
    raw = dump_ordinal_continuation(
        problem, path, first.continuation, maximum_solver_attempts=9, config=CONFIG
    )
    restored = load_ordinal_continuation(
        raw, problem, path, maximum_solver_attempts=9, config=CONFIG
    )
    assert (
        restored.mechanical.canonical_bytes()
        == first.continuation.mechanical.canonical_bytes()
    )
    resumed = run_ordinal_history(
        problem, path, maximum_solver_attempts=9, config=CONFIG, continuation=restored
    )
    uninterrupted, _ = run_all(problem, path, 9)
    assert (
        resumed.continuation.mechanical.canonical_bytes()
        == uninterrupted.continuation.mechanical.canonical_bytes()
    )
    assert resumed.continuation.ledger_hash == uninterrupted.continuation.ledger_hash
    assert (
        resumed.replay_solver_invocations == 0
        and resumed.preload_solver_invocations == 0
    )
    for edited in (
        replace(path, source_sha256="sha256:" + "2" * 64),
        replace(
            path,
            rows=(replace(path.rows[0], source_row_sha256="sha256:" + "3" * 64),)
            + path.rows[1:],
        ),
        replace(path, rows=path.rows[:-1]),
    ):
        with pytest.raises(ValueError, match="identity"):
            load_ordinal_continuation(
                raw, problem, edited, maximum_solver_attempts=9, config=CONFIG
            )
    for edited in (
        replace(problem, axial_load_pattern=((3, -1.0),)),
        replace(
            problem, observation=LinearPhysicalDisplacementObservation(((3, 2.0),))
        ),
    ):
        with pytest.raises(ValueError, match="identity"):
            load_ordinal_continuation(
                raw, edited, path, maximum_solver_attempts=9, config=CONFIG
            )
    with pytest.raises(ValueError):
        run_ordinal_history(
            problem,
            path,
            maximum_solver_attempts=9,
            config=CONFIG,
            continuation=restored.mechanical.frame_checkpoint,
        )
    parsed = json.loads(raw)
    for key, value in (
        ("reserved_attempts", 0),
        ("next_ordinal", 3),
        ("solver_invocations", True),
    ):
        edited = dict(parsed)
        edited[key] = value
        edited.pop("artifact_hash")
        edited["artifact_hash"] = canonical_hash(edited)
        with pytest.raises(ValueError):
            load_ordinal_continuation(
                json.dumps(
                    edited, sort_keys=True, separators=(",", ":"), ensure_ascii=False
                ).encode(),
                problem,
                path,
                maximum_solver_attempts=9,
                config=CONFIG,
            )
    with pytest.raises(ValueError):
        load_ordinal_continuation(
            raw.replace(
                b'"reserved_attempts":1', b'"reserved_attempts":1,"reserved_attempts":1'
            ),
            problem,
            path,
            maximum_solver_attempts=9,
            config=CONFIG,
        )


def test_authored_hold_uses_prescribed_target_not_rounded_accepted_observation():
    problem = axial_problem()
    path = plan(((5e-17, 0.0), (5e-17, 0.0), (6e-17, 0.0)))
    first = run_ordinal_history(
        problem, path, maximum_solver_attempts=3, config=CONFIG, per_call_record_limit=1
    )
    assert (
        first.continuation.mechanical.frame_checkpoint.global_displacements[3]
        != path.rows[0].target_m
    )
    result = run_ordinal_history(
        problem,
        path,
        maximum_solver_attempts=3,
        config=CONFIG,
        continuation=first.continuation,
    )
    assert [e["kind"] for e in result.events] == ["verified_hold", "mechanical_commit"]
    assert result.continuation.reserved_attempts == 2


def test_same_target_load_only_failure_subdivides_both_declared_components_and_rolls_back():
    problem = axial_problem()
    path = plan(((0.0, 0.0), (0.0, 1.0)))
    coarse = replace(CONFIG, maximum_iterations=0)
    first = run_ordinal_history(
        problem, path, maximum_solver_attempts=9, config=coarse, per_call_record_limit=1
    )
    assert (
        first.status == "paused"
        and first.continuation.mechanical.frame_checkpoint.epoch == 1
    )
    before = first.continuation.mechanical.canonical_bytes()
    failed = run_ordinal_history(
        problem,
        path,
        maximum_solver_attempts=9,
        config=coarse,
        continuation=first.continuation,
        per_call_attempt_limit=1,
    )
    assert failed.events[0]["rollback_exact"] is True
    assert failed.continuation.mechanical.canonical_bytes() == before
    assert failed.continuation.pending_positions == ((1, 1), (1, 0))
    subdivided = run_ordinal_history(
        problem,
        path,
        maximum_solver_attempts=9,
        config=coarse,
        continuation=failed.continuation,
        per_call_attempt_limit=1,
    )
    assert (
        subdivided.events[0]["target_m"] == 0.0
        and subdivided.events[0]["axial_load_kn"] == 0.5
    )
    assert (
        subdivided.continuation.reserved_attempts == 3
        and subdivided.continuation.next_ordinal == 1
    )
    raw = dump_ordinal_continuation(
        problem, path, subdivided.continuation, maximum_solver_attempts=9, config=coarse
    )
    restored = load_ordinal_continuation(
        raw, problem, path, maximum_solver_attempts=9, config=coarse
    )
    assert restored.pending_positions == ((1, 2), (1, 1), (1, 0))
    for positions in (((2, 2), (1, 0)), ((1, 1), (1, 1), (1, 0)), ((1, 2), (1, 0))):
        with pytest.raises(ValueError):
            run_ordinal_history(
                problem,
                path,
                maximum_solver_attempts=9,
                config=coarse,
                continuation=replace(restored, pending_positions=positions),
            )


def test_nonlinear_reversal_carries_constitutive_states_and_failed_trial_exact_rollback():
    base = _nonlinear_fixed_axial_problem()
    problem = ScheduledFrameProblem(
        base, LinearPhysicalDisplacementObservation(((3, 1.0),)), ((4, -1.0),)
    )
    path = plan(
        ((0.0005, 0.0), (0.001, 2.0), (0.0002, 2.0), (-0.0003, 1.0), (0.0004, 0.0))
    )
    result, events = run_all(problem, path, 60, per_call_record_limit=1)
    assert result.status == "complete" and result.continuation.next_ordinal == 5
    assert (
        len(
            {
                e["mechanical_state_hash"]
                for e in events
                if e["kind"] == "mechanical_commit"
            }
        )
        >= 5
    )
    first = run_ordinal_history(
        problem,
        path,
        maximum_solver_attempts=60,
        config=CONFIG,
        per_call_record_limit=2,
    )
    prefix = dump_ordinal_continuation(
        problem, path, first.continuation, maximum_solver_attempts=60, config=CONFIG
    )
    restored = load_ordinal_continuation(
        prefix, problem, path, maximum_solver_attempts=60, config=CONFIG
    )
    resumed = run_ordinal_history(
        problem, path, maximum_solver_attempts=60, config=CONFIG, continuation=restored
    )
    assert resumed.status == "complete"
    assert (
        resumed.continuation.mechanical.canonical_bytes()
        == result.continuation.mechanical.canonical_bytes()
    )
    assert resumed.continuation.ledger_hash == result.continuation.ledger_hash
    raw = dump_ordinal_continuation(
        problem, path, result.continuation, maximum_solver_attempts=60, config=CONFIG
    )
    assert (
        load_ordinal_continuation(
            raw, problem, path, maximum_solver_attempts=60, config=CONFIG
        ).mechanical.canonical_bytes()
        == result.continuation.mechanical.canonical_bytes()
    )
    # Existing nonlinear material laws must carry actual non-virgin history.
    initial = initial_mechanical_checkpoint(problem, result.continuation.context_hash)
    assert (
        result.continuation.mechanical.frame_checkpoint.element_states[
            0
        ].canonical_bytes()
        != initial.frame_checkpoint.element_states[0].canonical_bytes()
    )


def test_singular_first_linear_solve_still_reserves_and_reports_work():
    original = axial_problem()
    base = replace(original.frame_problem, reference_external_loads=((0, 1.0),))
    problem = ScheduledFrameProblem(
        base, original.observation, original.axial_load_pattern
    )
    result = run_ordinal_history(
        problem,
        plan(((1e-5, 0.2),)),
        maximum_solver_attempts=1,
        maximum_subdivision_depth=0,
        config=CONFIG,
    )
    assert result.status == "blocked" and result.continuation.reserved_attempts == 1
    assert (
        result.continuation.linear_solve_attempts == 1
        and result.continuation.failed_assembly_attempts == 2
    )
    assert result.continuation.mechanical.frame_checkpoint.epoch == 0
    assert result.events[0]["rollback_exact"] is True


def test_nonlinear_failed_step_preserves_all_parent_material_bytes():
    base = _nonlinear_fixed_axial_problem()
    problem = ScheduledFrameProblem(
        base, LinearPhysicalDisplacementObservation(((3, 1.0),)), ((4, -1.0),)
    )
    path = plan(((1e-5, 0.0), (0.3, 10.0)))
    config = replace(CONFIG, maximum_iterations=4)
    first = run_ordinal_history(
        problem,
        path,
        maximum_solver_attempts=2,
        maximum_subdivision_depth=0,
        config=config,
        per_call_record_limit=1,
    )
    assert first.continuation.next_ordinal == 1
    before = first.continuation.mechanical.canonical_bytes()
    failed = run_ordinal_history(
        problem,
        path,
        maximum_solver_attempts=2,
        maximum_subdivision_depth=0,
        config=config,
        continuation=first.continuation,
    )
    assert failed.status == "blocked" and failed.continuation.next_ordinal == 1
    assert failed.events[0]["rollback_exact"] is True
    assert failed.continuation.mechanical is first.continuation.mechanical
    assert failed.continuation.mechanical.canonical_bytes() == before


def test_large_unload_canonical_equilibrium_is_identical_across_hold_chunk_restart():
    problem = axial_problem()
    path = plan(((1e-5, 1e6), (1e-5, 0.0), (1e-5, 0.0)))
    tight = replace(CONFIG, residual_tolerance=1e-13)
    whole = run_ordinal_history(problem, path, maximum_solver_attempts=3, config=tight)
    assert whole.status == "complete" and whole.continuation.hold_records == 1
    assert whole.events[1]["linear_solve_attempts"] >= 3
    first = run_ordinal_history(
        problem, path, maximum_solver_attempts=3, config=tight, per_call_record_limit=1
    )
    raw = dump_ordinal_continuation(
        problem, path, first.continuation, maximum_solver_attempts=3, config=tight
    )
    restored = load_ordinal_continuation(
        raw, problem, path, maximum_solver_attempts=3, config=tight
    )
    second = run_ordinal_history(
        problem,
        path,
        maximum_solver_attempts=3,
        config=tight,
        continuation=restored,
        per_call_record_limit=1,
    )
    assert second.continuation.next_ordinal == 2
    state = second.continuation.mechanical
    trial = assemble_scheduled_frame(
        problem,
        state,
        state.context_hash,
        target_axial_load_kn=0.0,
        target_load_factor=state.frame_checkpoint.load_factor,
        trial_free_coordinates_m=np.asarray(
            [state.frame_checkpoint.global_displacements[3]]
        ),
    )
    assert abs(trial.residual_kn[0]) <= tight.residual_tolerance
    final = run_ordinal_history(
        problem,
        path,
        maximum_solver_attempts=3,
        config=tight,
        continuation=second.continuation,
    )
    assert final.status == "complete" and final.events[0]["kind"] == "verified_hold"
    assert (
        final.continuation.mechanical.canonical_bytes()
        == whole.continuation.mechanical.canonical_bytes()
    )
    assert final.continuation.ledger_hash == whole.continuation.ledger_hash


def test_codec_rejects_redundant_signed_zero_and_noncanonical_numeric_representation():
    problem = axial_problem()
    path = plan(((0.0, 0.0),))
    result = run_ordinal_history(
        problem, path, maximum_solver_attempts=1, config=CONFIG
    )
    frame = replace(
        result.continuation.mechanical.frame_checkpoint, load_factor=-0.0, state_hash=""
    )
    state = replace(result.continuation.mechanical, frame_checkpoint=frame)
    continuation = replace(result.continuation, mechanical=state)
    raw = dump_ordinal_continuation(
        problem, path, continuation, maximum_solver_attempts=1, config=CONFIG
    )
    assert np.signbit(
        load_ordinal_continuation(
            raw, problem, path, maximum_solver_attempts=1, config=CONFIG
        ).mechanical.frame_checkpoint.load_factor
    )
    parsed = json.loads(raw)
    parsed["mechanical"]["load_context"]["lambda"] = 0.0
    parsed.pop("artifact_hash")
    parsed["artifact_hash"] = canonical_hash(parsed)
    changed = json.dumps(
        parsed, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    with pytest.raises(ValueError, match="lambda"):
        load_ordinal_continuation(
            changed, problem, path, maximum_solver_attempts=1, config=CONFIG
        )
    ordinary = dump_ordinal_continuation(
        problem, path, result.continuation, maximum_solver_attempts=1, config=CONFIG
    )
    parsed = json.loads(ordinary)
    parsed["mechanical"]["load_context"]["lambda"] = 0
    parsed.pop("artifact_hash")
    parsed["artifact_hash"] = canonical_hash(parsed)
    changed = json.dumps(
        parsed, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    with pytest.raises(ValueError, match="round-trip"):
        load_ordinal_continuation(
            changed, problem, path, maximum_solver_attempts=1, config=CONFIG
        )


def test_coherently_rehashed_impossible_hold_commit_prefix_and_pending_are_rejected():
    problem = axial_problem()
    path = plan(((1e-5, 0.1), (1e-5, 0.1)))
    whole = run_ordinal_history(problem, path, maximum_solver_attempts=3, config=CONFIG)
    impossible = replace(
        whole.continuation,
        mechanical=replace(whole.continuation.mechanical, last_mechanical_ordinal=1),
    )
    with pytest.raises(ValueError, match="hold row"):
        run_ordinal_history(
            problem,
            path,
            maximum_solver_attempts=3,
            config=CONFIG,
            continuation=impossible,
        )
    alternate = run_ordinal_history(
        problem,
        plan(((1.1e-5, 0.1), (1e-5, 0.1))),
        maximum_solver_attempts=3,
        config=CONFIG,
    )
    impossible = replace(
        whole.continuation,
        hold_records=0,
        hold_assembly_attempts=0,
        completed_solve_records=2,
        mechanical_commits=2,
        reserved_attempts=2,
        solver_invocations=2,
        assembly_attempts=alternate.continuation.assembly_attempts,
        linear_solve_attempts=alternate.continuation.linear_solve_attempts,
        mechanical=replace(
            whole.continuation.mechanical,
            frame_checkpoint=alternate.continuation.mechanical.frame_checkpoint,
        ),
    )
    with pytest.raises(ValueError, match="authored prefix"):
        run_ordinal_history(
            problem,
            path,
            maximum_solver_attempts=3,
            config=CONFIG,
            continuation=impossible,
        )
    first = run_ordinal_history(
        problem, path, maximum_solver_attempts=3, config=CONFIG, per_call_record_limit=1
    )
    with pytest.raises(ValueError, match="hold row"):
        run_ordinal_history(
            problem,
            path,
            maximum_solver_attempts=3,
            config=CONFIG,
            continuation=replace(first.continuation, pending_positions=((1, 0),)),
        )


def test_legacy_public_exact_type_guard_and_same_source_old_profile_numeric_path():
    problem = axial_problem()
    parent = initial_mechanical_checkpoint(problem, SHA)
    legacy = StatefulCorotationalFiberFrame2DDisplacementControlStepProblem(
        problem.frame_problem, parent.frame_checkpoint, 3, 1e-5, CONFIG
    )
    solution = solve_stateful_corotational_fiber_frame2d_displacement_control(legacy)
    scheduled = run_ordinal_history(
        problem, plan(((1e-5, 0.0),)), maximum_solver_attempts=1, config=CONFIG
    )
    assert scheduled.status == "complete"
    assert np.array_equal(
        solution.free_displacements_m,
        np.asarray(
            scheduled.continuation.mechanical.frame_checkpoint.global_displacements
        )[list(problem.frame_problem.free_global_dofs)],
    )
    assert (
        solution.load_factor
        == scheduled.continuation.mechanical.frame_checkpoint.load_factor
    )
    assert "independent_dead" not in solution.metrics.get("profile", "")
    with pytest.raises(ValueError, match="type"):
        solve_stateful_corotational_fiber_frame2d_displacement_control(
            ScheduledControlStepProblem(problem, parent, SHA, 1e-5, 0.0, CONFIG)
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("ordinal", True),
        ("source_row", -1),
        ("target_m", float("nan")),
        ("axial_load_kn", 2**53 + 1),
    ],
)
def test_history_admission_rejects_invalid_authored_values(field, value):
    with pytest.raises(ValueError):
        replace(HistoryRow(0, 0, SHA, 0.0, 0.0), **{field: value})


def test_full_30574_distinct_target_variable_dead_load_real_native_loop():
    """All 30574 mechanical solves: independent axial oracle, no mocks/holds/CC fit."""
    count = 30574
    problem = axial_problem()
    path = plan(
        tuple(
            ((1 if i % 2 == 0 else -1) * (1e-5 + (i % 13) * 1e-7), (i % 17 - 8) * 0.01)
            for i in range(count)
        )
    )
    continuation = None
    started = time.monotonic()
    observed = 0
    peak_events = 0
    calls = 0
    while True:
        result = run_ordinal_history(
            problem,
            path,
            maximum_solver_attempts=count,
            config=CONFIG,
            continuation=continuation,
        )
        continuation = result.continuation
        calls += 1
        peak_events = max(peak_events, len(result.events))
        for event in result.events:
            assert event["kind"] == "mechanical_commit" and event["ordinal"] == observed
            row = path.rows[observed]
            assert event["source_row_sha256"] == row.source_row_sha256
            assert (
                event["target_m"] == row.target_m
                and event["axial_load_kn"] == row.axial_load_kn
            )
            observed += 1
        state = continuation.mechanical
        row = path.rows[observed - 1]
        # EA/L=40000 kN/m independently from E=200000 MPa,A=.0002m2,L=1m.
        assert state.frame_checkpoint.load_factor == pytest.approx(
            40000 * row.target_m - row.axial_load_kn, abs=2e-10
        )
        assert (
            abs(state.frame_checkpoint.global_displacements[3] - row.target_m)
            <= CONFIG.control_tolerance_m
        )
        print(
            json.dumps(
                {
                    "rows": observed,
                    "attempts": continuation.reserved_attempts,
                    "assemblies": continuation.assembly_attempts,
                    "linear_solve_attempts": continuation.linear_solve_attempts,
                    "elapsed_s": round(time.monotonic() - started, 3),
                    "status": result.status,
                }
            ),
            flush=True,
        )
        if result.status != "paused":
            break
    assert result.status == "complete" and observed == count
    assert (
        continuation.next_ordinal
        == continuation.mechanical_commits
        == continuation.reserved_attempts
        == count
    )
    assert (
        continuation.failed_attempts == continuation.hold_records == 0
        and continuation.hold_assembly_attempts == 0
    )
    assert peak_events <= 255 and calls == (count + 254) // 255
    assert result.preload_solver_invocations == result.replay_solver_invocations == 0
    print(
        json.dumps(
            {
                "software_fixture_full_rows": count,
                "independent_physical_validation": False,
                "held_records": 0,
                "maximum_returned_events": peak_events,
                "plan_hash": path.hash,
                "final_state_hash": continuation.mechanical.state_hash,
                "source_identity": continuation.source_identity,
            }
        ),
        flush=True,
    )
