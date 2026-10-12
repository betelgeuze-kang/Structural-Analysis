"""Synthetic transport records: no solver, source authentication or physics claim."""

import base64
from copy import deepcopy
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path

import pytest

from structural_analysis.api.rc_corotational_control_model import (
    compile_rc_corotational_control_model,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d import (
    initial_stateful_corotational_fiber_frame2d_checkpoint,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_control_subdivision import (
    _encode_continuation,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_displacement_control import (
    StatefulCorotationalFiberFrame2DDisplacementControlConfig,
)
from structural_analysis.execution import rc_corotational_job_contract as contract
from structural_analysis.execution.rc_corotational_job_request import (
    RC_COROTATIONAL_JOB_OPERATION,
    RC_COROTATIONAL_JOB_REQUEST_SCHEMA_VERSION,
    RC_COROTATIONAL_JOB_RESULT_SCHEMA_VERSION,
    rc_corotational_job_canonical_bytes,
    validate_rc_corotational_job_request,
)
from structural_analysis.solvers.nonlinear.newton import NewtonRaphsonConfig


@pytest.fixture(autouse=True)
def no_numerical_execution_or_source_identity(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("synthetic pure transport fixture invoked solver/source execution")

    for module, names in (
        (
            "structural_analysis.api.rc_corotational_control",
            (
                "analyze_rc_corotational_control",
                "validate_rc_corotational_control_artifacts",
                "solve_stateful_corotational_fiber_frame2d_load_step",
                "run_corotational_control_subdivision",
                "_source_identity",
            ),
        ),
        (
            "structural_analysis.assembly.stateful_corotational_fiber_frame2d_control_subdivision",
            (
                "solve_stateful_corotational_fiber_frame2d_displacement_control_step",
                "_source_identity",
            ),
        ),
    ):
        for name in names:
            monkeypatch.setattr(f"{module}.{name}", forbidden)


def request():
    return json.loads(
        json.dumps(
            {
                "schema_version": RC_COROTATIONAL_JOB_REQUEST_SCHEMA_VERSION,
                "operation": RC_COROTATIONAL_JOB_OPERATION,
                "case_id": "synthetic-durable-contract",
                "model": json.loads(
                    (
                        Path(__file__).parents[1]
                        / "examples/public_rc_fiber_frame_l_frame_material_history.json"
                    ).read_bytes()
                ),
                "source_revision": "b" * 40,
                "result_contract": RC_COROTATIONAL_JOB_RESULT_SCHEMA_VERSION,
                "config": {
                    "control_node_id": "N3",
                    "control_component": "UY",
                    "targets_m": [-1e-6, -2e-6],
                    "fixed_nodal_loads": [],
                    "config": asdict(
                        StatefulCorotationalFiberFrame2DDisplacementControlConfig()
                    ),
                    "preload_config": asdict(NewtonRaphsonConfig()),
                    "maximum_attempt_count": 10,
                    "maximum_subdivision_depth": 8,
                    "experimental_pin_roller_beam": False,
                    "experimental_fixed_guided_axial": False,
                },
                "execution_config": {
                    "attempt_limit_per_call": 2,
                    "maximum_api_invocations": 20,
                },
            }
        )
    )


def budget(reserved=2):
    return {
        "maximum_attempts": 20,
        "reserved_attempts": reserved,
        "remaining_attempts": 20 - reserved,
    }


def zero_child(parent):
    """Manufacture only zero-state transport ancestry, without constitutive integration."""
    step = parent.step_index + 1
    elements = []
    for state in parent.element_states:
        basic = replace(
            state.basic_beam_state,
            step_index=step,
            integration_point_states=tuple(
                replace(section, step_index=step)
                for section in state.basic_beam_state.integration_point_states
            ),
        )
        elements.append(replace(state, step_index=step, basic_beam_state=basic))
    return replace(
        parent,
        epoch=step,
        step_index=step,
        parent_state_hash=parent.state_hash,
        element_states=tuple(elements),
        state_hash="",
    )


def pair(payload, *, before=0, after=1, ready=False, restart=None):
    typed = validate_rc_corotational_job_request(payload)
    compiled = compile_rc_corotational_control_model(typed.model)
    binding = contract.rc_corotational_chunk_binding(typed, before, restart)
    api_request = contract._expected_api_request(
        typed, before, binding["restart_input_sha256"], "a" * 64
    )
    initial = initial_stateful_corotational_fiber_frame2d_checkpoint(compiled.problem)
    first = zero_child(initial)
    checkpoints = [first]
    targets = len(typed.targets_m) if ready else 0
    for _ in range(targets):
        checkpoints.append(zero_child(checkpoints[-1]))
    pending = (
        []
        if ready
        else [(v, 0, i) for i, v in reversed(tuple(enumerate(typed.targets_m)))]
    )
    context = hashlib.sha256(
        contract._api_bytes(
            {
                "case": compiled.problem.case_id,
                "problem": typed.problem_contract_hash,
                "source": api_request["source_identity"],
                "targets": typed.targets_m,
                "control": api_request["control_global_dof"],
                "budget": typed.progress_total,
                "depth": typed.config.maximum_subdivision_depth,
                "config": asdict(typed.config.solver_config),
            }
        )
    ).hexdigest()
    continuation = _encode_continuation(
        compiled.problem, context, first, checkpoints[-1], pending, targets, after, ""
    )
    work = {
        "preload_solver_calls": 1,
        "restart_replay_solver_calls": before,
        "control_solver_calls": after - before,
        "unavailable_execution_work": False,
    }
    responses = [
        {
            "phase": "preload" if i == 0 else "control",
            "checkpoint_hash": checkpoint.state_hash,
            "parent_checkpoint_hash": checkpoint.parent_state_hash,
            "load_factor": checkpoint.load_factor,
            "nodes": [
                {
                    "node_id": node,
                    "displacements_m_rad": [0.0, 0.0, 0.0],
                    "external_loads_kn_knm": [0.0, 0.0, 0.0],
                    "reactions_kn_knm": [0.0, 0.0, 0.0],
                }
                for node in compiled.node_ids
            ],
            "members": [
                {"member_id": member.member_id} for member in compiled.problem.members
            ],
        }
        for i, checkpoint in enumerate(checkpoints)
    ]
    api = {
        "schema": contract.API_SCHEMA,
        "request": api_request,
        "status": "ready" if ready else "paused",
        "terminal_reason": "all_authored_targets_reached"
        if ready
        else "cooperative_pause",
        "contract_pass": ready,
        "completed_target_count": targets,
        "total_control_attempts": after,
        "continuation_sha256": hashlib.sha256(continuation).hexdigest(),
        "work": work,
        "responses": responses,
        "claims": {
            "independent_physical_validation": False,
            "managed_budget_authority": False,
            "design_authority": False,
        },
    }
    common = {
        "schema_version": contract.RC_COROTATIONAL_JOB_INVOCATION_SCHEMA_VERSION,
        "status": "returned",
        "job_request_hash": typed.request_hash,
        "chunk_request_hash": binding["chunk_request_hash"],
        "completed_before": before,
        "completed_after": binding["planned_after"],
        "restart_input_sha256": binding["restart_input_sha256"],
        "timing": {"wall_ns": 11, "process_cpu_ns": 7},
        "error": None,
        "unavailable_execution_work": False,
    }
    analysis = dict(
        common,
        phase="analysis",
        api_result=api,
        checkpoint_artifact_base64=base64.b64encode(continuation).decode(),
        verification_report=None,
    )
    report = {
        "artifact_contract_pass": True,
        "physical_path_complete": ready,
        "fresh_source_execution_invoked": True,
        "solver_replay_performed": True,
        "replay_work": deepcopy(work),
        "independent_physical_validation": False,
        "contract_pass": ready,
    }
    verification = dict(
        common,
        phase="verification",
        api_result=None,
        checkpoint_artifact_base64=None,
        verification_report=report,
    )
    return analysis, verification, continuation


def receipt(payload, analysis, verification, ordinals=(1, 2)):
    return contract.build_rc_corotational_job_receipt(
        payload, analysis["completed_before"], *ordinals, analysis, verification
    )


def rehash(value, field):
    value[field] = (
        "sha256:"
        + hashlib.sha256(
            rc_corotational_job_canonical_bytes(
                {k: v for k, v in value.items() if k != field}
            )
        ).hexdigest()
    )


def test_checkpoint_actual_attempts_distinct_from_planned_or_successful_targets():
    payload = request()
    a, v, raw = pair(payload)
    row = receipt(payload, a, v)
    assert row["planned_after"] == 2 and row["actual_after"] == 1
    assert row["completed_target_count"] == 0
    assert "responses" not in json.dumps(row)
    wrapper = contract.build_rc_corotational_job_payload(payload, [row], budget(), raw)
    assert "api_result" not in wrapper
    typed = validate_rc_corotational_job_request(payload)
    validated = contract.validate_rc_corotational_job_checkpoint(
        wrapper, payload, 1, typed.resume_contract_hash, budget(3)
    )
    assert validated["payload"] == wrapper
    assert validated["progress_completed"] == 1 and validated["progress_total"] == 10
    assert validated["progress_unit"] == "control_solver_attempts"
    assert contract.bind_rc_corotational_receipts([row], {1: a, 2: v}, payload) == (
        row,
    )


def test_resume_complete_before_cap_preserves_checkpoint_and_unknown_reservations():
    payload = request()
    a1, v1, raw1 = pair(payload)
    row1 = receipt(payload, a1, v1)
    checkpoint = contract.build_rc_corotational_job_payload(
        payload, [row1], budget(), raw1
    )
    a2, v2, raw2 = pair(payload, before=1, after=3, ready=True, restart=raw1)
    # Reservation 3 represents abandoned/unknown execution, not a completed pair.
    row2 = receipt(payload, a2, v2, (4, 5))
    final = contract.build_rc_corotational_job_payload(
        payload, [row1, row2], budget(5), raw2, a2["api_result"], True
    )
    report = contract.validate_rc_corotational_job_result(
        final, payload, budget(5), checkpoint=checkpoint
    )
    assert (
        report["contract_pass"]
        and report["progress_completed"] == 3 < report["progress_total"]
    )
    assert report["completed_target_count"] == 2
    assert report["execution_budget"]["reserved_attempts"] == 5
    assert "payload" not in report and "api_result" not in report
    assert final["api_result"] == a2["api_result"]
    assert all(
        not report["authority"][flag]
        for flag in (
            "independent_physical_validation",
            "release_approved",
            "independent_execution_authentication",
            "service_numerical_verification_performed",
        )
    )
    assert contract.bind_rc_corotational_receipts([row2], {4: a2, 5: v2}, payload) == (
        row2,
    )
    complete_checkpoint = contract.build_rc_corotational_job_payload(
        payload, [row1, row2], budget(5), raw2
    )
    typed = validate_rc_corotational_job_request(payload)
    assert contract.validate_rc_corotational_job_checkpoint(
        complete_checkpoint,
        payload,
        3,
        typed.resume_contract_hash,
        budget(6),
        checkpoint=checkpoint,
    )["contract_pass"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("completed_after", 1),
        ("completed_before", True),
        ("job_request_hash", "sha256:" + "c" * 64),
        ("chunk_request_hash", "sha256:" + "c" * 64),
        ("restart_input_sha256", "sha256:" + "c" * 64),
        ("timing", {"wall_ns": True, "process_cpu_ns": 1}),
        ("unavailable_execution_work", 0),
        ("checkpoint_artifact_base64", "%%%"),
        ("schema_version", "old"),
    ],
)
def test_invocation_binding_timing_and_custody_rejection(field, value):
    payload = request()
    a, _v, _raw = pair(payload)
    a[field] = value
    with pytest.raises(ValueError):
        contract.validate_rc_corotational_invocation_outcome(
            a, payload, validate_rc_corotational_job_request(payload).request_hash
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("total_control_attempts", True),
        ("total_control_attempts", 3),
        ("completed_target_count", 2),
        ("contract_pass", True),
        ("continuation_sha256", "c" * 64),
        (
            "claims",
            {
                "independent_physical_validation": True,
                "managed_budget_authority": False,
                "design_authority": False,
            },
        ),
        (
            "work",
            {
                "preload_solver_calls": 1,
                "restart_replay_solver_calls": 0,
                "control_solver_calls": 0,
                "unavailable_execution_work": False,
            },
        ),
        ("responses", []),
    ],
)
def test_api_artifact_semantic_bindings_rejected(field, value):
    payload = request()
    a, _v, _raw = pair(payload)
    a["api_result"][field] = value
    with pytest.raises(ValueError):
        contract.validate_rc_corotational_invocation_outcome(
            a, payload, validate_rc_corotational_job_request(payload).request_hash
        )


def test_report_and_exact_outcome_pair_cannot_be_rewritten():
    payload = request()
    a, v, raw = pair(payload)
    row = receipt(payload, a, v)
    for field, value in (
        ("artifact_contract_pass", False),
        ("fresh_source_execution_invoked", False),
        ("independent_physical_validation", True),
        ("contract_pass", True),
    ):
        changed = deepcopy(v)
        changed["verification_report"][field] = value
        with pytest.raises(ValueError):
            receipt(payload, a, changed)
    changed = deepcopy(row)
    changed["analysis_timing"]["wall_ns"] += 1
    rehash(changed, "receipt_hash")
    with pytest.raises(ValueError, match="exact durable phase outcomes"):
        contract.bind_rc_corotational_receipts([changed], {1: a, 2: v}, payload)
    for outcomes in ({1: a}, {1: a, 2: a}):
        with pytest.raises(ValueError):
            contract.bind_rc_corotational_receipts([row], outcomes, payload)
    with pytest.raises(ValueError, match="reused"):
        contract.bind_rc_corotational_receipts([row, row], {1: a, 2: v}, payload)
    changed = deepcopy(a)
    changed["api_result"]["responses"][0]["nodes"][0]["reactions_kn_knm"][0] = 123.0
    # The transport does not infer physics from this value; exact retained outcomes bind it.
    with pytest.raises(ValueError, match="exact durable phase outcomes"):
        contract.bind_rc_corotational_receipts([row], {1: changed, 2: v}, payload)
    with pytest.raises(ValueError):
        contract.build_rc_corotational_job_payload(
            payload, [row], budget(), raw, a["api_result"], complete=True
        )


def test_raised_and_blocked_invocations_are_audit_records_not_accepted_receipts():
    payload = request()
    a, v, _raw = pair(payload)
    typed = validate_rc_corotational_job_request(payload)
    raised = dict(
        a,
        status="raised",
        api_result=None,
        checkpoint_artifact_base64=None,
        error={"type": "SyntheticError", "code": "synthetic"},
        unavailable_execution_work=True,
    )
    assert (
        contract.validate_rc_corotational_invocation_outcome(
            raised, payload, typed.request_hash
        )["status"]
        == "raised"
    )
    with pytest.raises(ValueError):
        receipt(payload, raised, v)
    raised["unavailable_execution_work"] = False
    with pytest.raises(ValueError):
        contract.validate_rc_corotational_invocation_outcome(
            raised, payload, typed.request_hash
        )
    blocked = deepcopy(a)
    blocked["api_result"].update(
        status="blocked",
        terminal_reason="preload_failed",
        contract_pass=False,
        total_control_attempts=0,
        completed_target_count=0,
        continuation_sha256=None,
        responses=[],
    )
    blocked["api_result"]["work"]["control_solver_calls"] = 0
    blocked["checkpoint_artifact_base64"] = None
    assert (
        contract.validate_rc_corotational_invocation_outcome(
            blocked, payload, typed.request_hash
        )["api_result"]["status"]
        == "blocked"
    )
    with pytest.raises(ValueError):
        receipt(payload, blocked, v)


def test_native_corruption_source_changes_and_durable_progress_refunds_rejected():
    payload = request()
    a, v, raw = pair(payload)
    row = receipt(payload, a, v)
    wrapper = contract.build_rc_corotational_job_payload(payload, [row], budget(), raw)
    typed = validate_rc_corotational_job_request(payload)
    for cursor, resume, current in (
        (True, typed.resume_contract_hash, budget()),
        (2, typed.resume_contract_hash, budget()),
        (1, "sha256:" + "c" * 64, budget()),
        (1, typed.resume_contract_hash, budget(1)),
    ):
        with pytest.raises(ValueError):
            contract.validate_rc_corotational_job_checkpoint(
                wrapper, payload, cursor, resume, current
            )
    changed = deepcopy(payload)
    changed["source_revision"] = "c" * 40
    with pytest.raises(ValueError):
        contract.validate_rc_corotational_job_checkpoint(
            wrapper, changed, 1, typed.resume_contract_hash, budget()
        )
    native = json.loads(raw)
    native["payload"]["spent"] = 0
    native["sha256"] = hashlib.sha256(
        contract._api_bytes(native["payload"])
    ).hexdigest()
    bad_raw = contract._api_bytes(native)
    changed = deepcopy(a)
    changed["checkpoint_artifact_base64"] = base64.b64encode(bad_raw).decode()
    changed["api_result"]["continuation_sha256"] = hashlib.sha256(bad_raw).hexdigest()
    with pytest.raises(ValueError, match="progress mismatch"):
        contract.validate_rc_corotational_invocation_outcome(
            changed, payload, typed.request_hash
        )
    changed = deepcopy(wrapper)
    changed["authority"]["independent_execution_authentication"] = True
    rehash(changed, "checkpoint_hash")
    with pytest.raises(ValueError):
        contract.validate_rc_corotational_job_checkpoint(
            changed, payload, 1, typed.resume_contract_hash, budget()
        )


def test_final_cumulative_artifact_and_retained_prefix_integrity():
    payload = request()
    a1, v1, raw1 = pair(payload)
    row1 = receipt(payload, a1, v1)
    prior = contract.build_rc_corotational_job_payload(payload, [row1], budget(), raw1)
    a2, v2, raw2 = pair(payload, before=1, after=3, ready=True, restart=raw1)
    row2 = receipt(payload, a2, v2, (4, 5))
    final = contract.build_rc_corotational_job_payload(
        payload, [row1, row2], budget(5), raw2, a2["api_result"], True
    )
    changed = deepcopy(final)
    changed["api_result"]["responses"][0]["nodes"][0]["reactions_kn_knm"][0] = 123.0
    rehash(changed, "result_hash")
    with pytest.raises(ValueError, match="differs from final receipt"):
        contract.validate_rc_corotational_job_result(
            changed, payload, budget(5), checkpoint=prior
        )
    changed = deepcopy(final)
    changed["receipts"][0]["analysis_timing"]["wall_ns"] += 1
    rehash(changed["receipts"][0], "receipt_hash")
    rehash(changed, "result_hash")
    with pytest.raises(ValueError, match="prefix was rewritten"):
        contract.validate_rc_corotational_job_result(
            changed, payload, budget(5), checkpoint=prior
        )
    with pytest.raises(ValueError, match="budget was rewound"):
        contract.validate_rc_corotational_job_result(
            final, payload, budget(4), checkpoint=prior
        )


def test_transport_extra_fields_nonfinite_and_chunk_bounds_fail_closed():
    payload = request()
    a, _v, _raw = pair(payload)
    typed = validate_rc_corotational_job_request(payload)
    for changed in (dict(a, extra=1), b'{"x":NaN}', b'{"x":1,"x":2}', b"[]"):
        with pytest.raises(ValueError):
            contract.validate_rc_corotational_invocation_outcome(
                changed, payload, typed.request_hash
            )
    for before, restart in (
        (True, None),
        (10, b"a"),
        (1, None),
        (0, b"a"),
        (1, bytearray(b"a")),
    ):
        with pytest.raises(ValueError):
            contract.rc_corotational_chunk_binding(payload, before, restart)
    with pytest.raises(ValueError):
        contract.rc_corotational_chunk_binding(
            payload, 1, b"a" * (16 * 1024 * 1024 + 1)
        )
