"""Causal original-byte binding, unavailable counters and unchanged defaults."""

from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from structural_analysis.benchmark import rc_control_seed_runtime as runtime
from structural_analysis.benchmark.rc_control_design import _bytes, _sha
from structural_analysis.benchmark.rc_control_prior_work import (
    make_rc_control_prior_work_binding,
    make_rc_control_prior_work_record,
    validate_rc_control_prior_work,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash


def synthetic_prior_context(*, retries=0, assembly=True):
    """Pure authored codec fixture, never a solver observation or training input."""
    problem, predecessor, current = (
        _sha(v) for v in (b"problem", b"predecessor", b"current")
    )
    context = runtime.RCControlSeedContext(
        problem, 7, 0, 0.2, (0.0, 0.1), ((0.0, 0.0), (0.1, 0.2))
    )
    parent = {
        "schema_version": "stateful-fiber-frame2d-checkpoint.v1",
        "role": "committed",
        "case_id": "authored-codec-only",
        "problem_contract_hash": problem,
        "epoch": 0,
        "step_index": 0,
        "state_hash": predecessor,
        "parent_state_hash": None,
        "global_displacements": [0.0] * 9,
        "load_factor": 0.0,
        "element_states": [],
    }
    child = {
        **parent,
        "epoch": 1,
        "step_index": 1,
        "state_hash": current,
        "parent_state_hash": predecessor,
    }
    binding = make_rc_control_prior_work_binding(
        context,
        accepted_checkpoint=SimpleNamespace(
            state_hash=current, parent_state_hash=predecessor, epoch=1, step_index=1
        ),
        arm_identity=_sha(b"own-arm"),
        request_hash=_sha(b"request"),
        solver_config_hash=_sha(b"solver-config"),
        source_binding_hash=_sha(b"sources"),
    )
    originals = []
    for ordinal in range(1, retries + 2):
        committed = ordinal == retries + 1
        metrics = {"iteration_count": ordinal + 1, "linear_solve_count": ordinal}
        step = {
            "schema_version": "small-displacement-rc-fiber-control-step.v1",
            "status": "ready" if committed else "blocked",
            "committed": committed,
            "parent_checkpoint": parent,
            "accepted_checkpoint": child if committed else parent,
            "trial_solution": {
                "metrics": metrics,
                "augmented_coordinates_m": [0.1, 0.2],
            },
            "metrics": {
                "control_global_dof": 7,
                "config_hash": binding["solver_config_hash"],
                "target_control_displacement_m": 0.1,
                "rollback_exact": None if committed else True,
            },
            "trial_assembly": {},
            "claim_boundary": "authored codec fixture, no solver authority",
        }
        step["step_hash"] = canonical_hash(step)
        outcome = {
            "ordinal": ordinal,
            "status": "returned",
            "unknown_work": False,
            "committed": committed,
            "rollback_exact": None if committed else True,
            "work": {
                "core_calls": 1,
                "newton_iterations": ordinal + 1,
                "linear_solves": ordinal,
            },
        }
        if assembly:
            phases = ("primary_iteration", "line_search", "terminal_refinement")
            outcome["newton_assembly_work"] = {
                "schema_version": "vector-newton-assembly-dispatch-work.v1",
                "scope": "vector_newton_problem_assembly_dispatches_only",
                "calls": [
                    {"ordinal": i, "phase": phase, "status": "returned"}
                    for i, phase in enumerate(phases, 1)
                ],
                "call_count": 3,
                "returned_count": 3,
                "exception_count": 0,
                "in_flight_count": 0,
            }
        originals.append((_bytes(outcome), _bytes(step)))
    record = make_rc_control_prior_work_record(binding, originals)
    return replace(
        context, prior_work_binding=binding, prior_accepted_transition_work=record
    )


def _change_original(context, name, mutate):
    import json

    record = deepcopy(context.prior_accepted_transition_work)
    row = record["invocations"][-1]
    value = json.loads(row[name + "_json"])
    mutate(value)
    if name == "step":
        value["step_hash"] = canonical_hash(
            {k: v for k, v in value.items() if k != "step_hash"}
        )
    raw = _bytes(value)
    row[name + "_json"], row[name + "_sha256"] = raw.decode(), _sha(raw)
    return replace(context, prior_accepted_transition_work=record)


def test_all_rejected_attempts_are_charged_before_accepted_parent():
    context = synthetic_prior_context(retries=2)
    work = validate_rc_control_prior_work(context)
    assert (work.core_calls, work.newton_iterations, work.linear_solves) == (3, 9, 6)
    assert (
        work.assembly_dispatches,
        work.line_search_dispatches,
        work.terminal_refinement_dispatches,
    ) == (9, 3, 3)
    assert work.parent_state_hash == context.prior_work_binding["current_parent_hash"]
    with pytest.raises(Exception):
        work.core_calls = 0


def test_unrecorded_dispatches_remain_unavailable():
    work = validate_rc_control_prior_work(synthetic_prior_context(assembly=False))
    assert work.core_calls == 1
    assert (
        work.assembly_dispatches
        is work.line_search_dispatches
        is work.terminal_refinement_dispatches
        is None
    )


def test_dropping_a_rejected_original_invocation_cannot_refund_its_work():
    context = synthetic_prior_context(retries=1)
    record = deepcopy(context.prior_accepted_transition_work)
    record["invocations"].pop(0)
    with pytest.raises(ValueError):
        validate_rc_control_prior_work(
            replace(context, prior_accepted_transition_work=record)
        )


def test_missing_original_at_supplied_parent_declines_before_callback(tmp_path):
    context = replace(synthetic_prior_context(), prior_accepted_transition_work=None)

    def unexpected(_):
        raise AssertionError("missing prior work must not call the guard")

    outcome = runtime._guard_decision(
        context, unexpected, tmp_path, 0, require_prior_work=True
    )
    assert outcome["status"] == "returned" and outcome["allow_proposal"] is False
    assert outcome["decline_reason"] == "causal_prior_work_unavailable"


@pytest.mark.parametrize(
    "key",
    [
        "arm_identity",
        "request_hash",
        "solver_config_hash",
        "source_binding_hash",
        "current_parent_hash",
        "current_parent_predecessor_hash",
        "problem_contract_hash",
    ],
)
def test_foreign_receipt_fails_independently_of_its_own_binding(key):
    context = synthetic_prior_context()
    record = deepcopy(context.prior_accepted_transition_work)
    record["binding"][key] = _sha(b"foreign")
    with pytest.raises(ValueError):
        validate_rc_control_prior_work(
            replace(context, prior_accepted_transition_work=record)
        )


@pytest.mark.parametrize(
    "key,value",
    [
        ("current_parent_epoch", 2),
        ("current_parent_epoch", True),
        ("previous_target_index", 1),
        ("previous_target_index", 0.0),
        ("control_global_dof", True),
    ],
)
def test_future_or_inexact_binding_rejects_even_when_receipt_resealed(key, value):
    context = synthetic_prior_context()
    binding = dict(context.prior_work_binding, **{key: value})
    record = deepcopy(context.prior_accepted_transition_work)
    record["binding"] = binding
    with pytest.raises(ValueError):
        validate_rc_control_prior_work(
            replace(
                context,
                prior_work_binding=binding,
                prior_accepted_transition_work=record,
            )
        )


@pytest.mark.parametrize("value", [True, 1.0, -1, None])
def test_counter_types_cannot_be_coerced(value):
    context = _change_original(
        synthetic_prior_context(),
        "outcome",
        lambda v: v["work"].update(newton_iterations=value),
    )
    with pytest.raises(ValueError):
        validate_rc_control_prior_work(context)


@pytest.mark.parametrize(
    "kind",
    [
        "unknown",
        "missing",
        "metric",
        "rollback",
        "unfinished_assembly",
        "child_epoch",
        "coordinates",
    ],
)
def test_unknown_missing_and_false_original_work_reject(kind):
    context = synthetic_prior_context(retries=1)
    if kind == "unknown":
        context = _change_original(
            context, "outcome", lambda v: v.update(unknown_work=True)
        )
    elif kind == "missing":
        context = _change_original(
            context, "outcome", lambda v: v["work"].pop("linear_solves")
        )
    elif kind == "metric":
        context = _change_original(
            context,
            "step",
            lambda v: v["trial_solution"]["metrics"].update(iteration_count=99),
        )
    elif kind == "rollback":
        record = deepcopy(context.prior_accepted_transition_work)
        record["invocations"][0] = record["invocations"][-1]
        context = replace(context, prior_accepted_transition_work=record)
    elif kind == "unfinished_assembly":
        context = _change_original(
            context,
            "outcome",
            lambda v: v["newton_assembly_work"]["calls"][0].update(status="started"),
        )
    elif kind == "child_epoch":
        context = _change_original(
            context, "step", lambda v: v["accepted_checkpoint"].update(epoch=2)
        )
    else:
        context = _change_original(
            context,
            "step",
            lambda v: v["trial_solution"].update(augmented_coordinates_m=[9.0, 9.0]),
        )
    with pytest.raises(ValueError):
        validate_rc_control_prior_work(context)


def test_original_bytes_digest_and_duplicate_keys_are_checked():
    context = synthetic_prior_context()
    record = deepcopy(context.prior_accepted_transition_work)
    record["invocations"][0]["step_json"] += " "
    with pytest.raises(ValueError):
        validate_rc_control_prior_work(
            replace(context, prior_accepted_transition_work=record)
        )
    row = record["invocations"][0]
    raw = b'{"ordinal":1,"ordinal":1}'
    row["outcome_json"], row["outcome_sha256"] = raw.decode(), _sha(raw)
    with pytest.raises(ValueError):
        validate_rc_control_prior_work(
            replace(context, prior_accepted_transition_work=record)
        )


def test_legacy_context_bytes_are_exactly_unchanged():
    context = runtime.RCControlSeedContext(
        _sha(b"problem"), 7, 0, 0.2, (0.0, 0.1), ((0.0, 0.0), (0.1, 0.2))
    )
    legacy = {
        "problem_contract_hash": context.problem_contract_hash,
        "control_global_dof": 7,
        "control_free_index": 0,
        "target_m": 0.2,
        "accepted_targets_m": (0.0, 0.1),
        "accepted_augmented_coordinates_m": ((0.0, 0.0), (0.1, 0.2)),
    }
    assert _bytes(context.to_dict()) == _bytes(legacy)
    with pytest.raises(ValueError, match="unavailable"):
        validate_rc_control_prior_work(context)


@pytest.mark.parametrize("value", [0, 1, None, "true"])
def test_opt_in_requires_boolean_before_any_output(tmp_path, value):
    with pytest.raises(ValueError, match="boolean"):
        runtime.benchmark_rc_control_seed_paths(
            None,
            None,
            source_revision="a" * 40,
            output_directory=tmp_path / "out",
            record_prior_accepted_transition_work=value,
        )
    assert not (tmp_path / "out").exists()


def test_small_actual_guard_uses_own_prior_originals_before_material_capture(
    tmp_path, monkeypatch
):
    import json
    from structural_analysis.api.rc_fiber_frame_direct_control_request import (
        BoundedRCFiberDirectControlRequest,
    )
    from structural_analysis.benchmark import rc_control_material_features as material
    from structural_analysis.io.neutral.loader import load_neutral_json

    # Checked-in authored input, not measurement/training/heldout original data.
    model = load_neutral_json(
        Path("examples/public_rc_fiber_frame_l_frame_material_history.json")
    )
    request = BoundedRCFiberDirectControlRequest(7, (-1e-7, -2e-7))
    observed, captures = [], []
    original_capture = material.committed_material_snapshot

    def capture(problem, parent):
        captures.append(parent.state_hash)
        return original_capture(problem, parent)

    def guard(context):
        observed.append(validate_rc_control_prior_work(context))
        return True

    monkeypatch.setattr(material, "committed_material_snapshot", capture)
    root = tmp_path / "actual"
    report = runtime.benchmark_rc_control_seed_paths(
        model,
        request,
        source_revision="a" * 40,
        output_directory=root,
        proposal=runtime.secant_seed,
        proposal_identity=_sha(b"secant-proposal"),
        proposal_guard=guard,
        proposal_guard_identity=_sha(b"authored-guard"),
        proposal_abstention_strategy="secant",
        capture_material_state=True,
        material_capture_scope="proposal-only",
        record_assembly_work=True,
        record_prior_accepted_transition_work=True,
    )
    assert report["reference_repeat_exact"] and report["all_execution_work_reported"]
    assert all(c["full_history_pass"] for c in report["comparisons"].values())
    assert len(observed) == len(captures) == 1
    assert captures == [observed[0].parent_state_hash]
    assert (
        report["arms"]["proposal"]["entries"][0]["proposal_guard"]["decline_reason"]
        == "causal_prior_work_unavailable"
    )
    assert "committed_material_capture" not in report["arms"]["proposal"]["entries"][0]
    assert report["prior_work_source_setup_cost"]["wall_ns"] >= 0
    for arm in ("reference", "secant", "proposal", "fresh-reference"):
        raw = json.loads((root / arm / "001-context.json").read_bytes())
        context = runtime.RCControlSeedContext(**raw)
        work = validate_rc_control_prior_work(context)
        prior = context.prior_accepted_transition_work["invocations"][0]
        assert (
            prior["outcome_json"].encode()
            == (root / arm / "000-1-outcome.json").read_bytes()
        )
        assert (
            prior["step_json"].encode() == (root / arm / "000-1-step.json").read_bytes()
        )
        assert work.core_calls == 1 and work.assembly_dispatches is not None
        assert (
            report["arms"].get(arm, report["fresh_reference"])["entries"][1][
                "prior_work_binding_cost"
            ]["wall_ns"]
            >= 0
        )
    native_step = json.loads((root / "proposal" / "000-1-step.json").read_bytes())
    raw_context = json.loads((root / "proposal" / "001-context.json").read_bytes())
    supplied_context = replace(
        runtime.RCControlSeedContext(**raw_context),
        committed_material_state_json=None,
        prior_work_binding=None,
        prior_accepted_transition_work=None,
    )
    supplied = runtime.benchmark_rc_control_seed_paths(
        model,
        request,
        source_revision="a" * 40,
        output_directory=tmp_path / "supplied",
        proposal=runtime.secant_seed,
        proposal_identity=_sha(b"secant-proposal"),
        proposal_guard=guard,
        proposal_guard_identity=_sha(b"authored-guard"),
        proposal_abstention_strategy="secant",
        capture_material_state=True,
        material_capture_scope="proposal-only",
        record_assembly_work=True,
        record_prior_accepted_transition_work=True,
        parent_checkpoint_bytes=_bytes(native_step["accepted_checkpoint"]),
        accepted_context=supplied_context,
    )
    assert supplied["reference_repeat_exact"]
    assert all(c["step_response_pass"] for c in supplied["comparisons"].values())
    assert len(observed) == len(captures) == 1
    assert (
        supplied["arms"]["proposal"]["entries"][0]["proposal_guard"]["allow_proposal"]
        is False
    )
    assert not supplied["claims"]["causal_training_dataset_admitted"]
    assert not report["claims"]["independent_validation"]
