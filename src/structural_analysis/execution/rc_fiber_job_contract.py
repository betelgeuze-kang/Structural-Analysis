"""Pure durable transport checks for the experimental RC direct-control API.

Numerical verification belongs to the worker, outside service transactions. These
checks bind its retained attestations to immutable inputs and artifacts; hashes
and internally consistent reports do not authenticate an independent execution.
Each checkpoint stores compact receipts and one native restart artifact. Only a
completed result also stores the latest cumulative API result, exactly once.
"""

from __future__ import annotations

import base64
import binascii
from dataclasses import replace
import hashlib
import json
import re
from typing import Any, Mapping

from structural_analysis.api.frame3d_direct_control_request import (
    strict_json_object_bytes,
)
from structural_analysis.api.nonlinear_fiber_frame import (
    PUBLIC_RC_FIBER_FRAME_COMPILER_PROFILE,
    _compile,
)
from structural_analysis.api.rc_fiber_frame_direct_control import (
    BOUNDED_RC_FIBER_DIRECT_CONTROL_RESULT_MAX_BYTES,
    BOUNDED_RC_FIBER_DIRECT_CONTROL_SCHEMA_VERSION,
    _CLAIMS as _API_CLAIMS,
)
from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    BoundedRCFiberDirectControlRequest,
    decode_bounded_rc_fiber_direct_control_request,
)
from structural_analysis.assembly.stateful_fiber_frame2d import (
    initial_stateful_fiber_frame2d_checkpoint,
)
from structural_analysis.assembly.stateful_fiber_frame2d_control_path import (
    CONTROL_PATH_SCHEMA,
    CONTROL_RESTART_MAX_BYTES,
    _CLAIMS as _PATH_CLAIMS,
    _decode_restart,
    _directions,
    _scope,
)
from structural_analysis.assembly.stateful_fiber_frame2d_displacement_control import (
    StatefulFiberFrame2DDisplacementControlStepAdapter,
)
from structural_analysis.io.neutral.loader import load_neutral_json_bytes
from structural_analysis.model.schema import CanonicalModel


RC_FIBER_JOB_REQUEST_SCHEMA_VERSION = "structural-analysis-job-request.v3"
RC_FIBER_JOB_OPERATION = "bounded_rc_fiber_direct_control"
RC_FIBER_JOB_CHECKPOINT_SCHEMA_VERSION = "bounded-rc-fiber-job-checkpoint.v1"
RC_FIBER_JOB_RESULT_SCHEMA_VERSION = "bounded-rc-fiber-job-result.v1"
RC_FIBER_JOB_VALIDATOR_ID = (
    "structural_analysis.execution.rc_fiber_job_contract.validate_rc_fiber_job_result"
)
RC_FIBER_JOB_PROFILE = "bounded_rc_fiber_durable_chunk_execution.v1"
RC_FIBER_JOB_MAX_BYTES = 576 * 1024 * 1024
RC_FIBER_JOB_AUTHORITY = {
    "experimental_small_displacement_rc_control": True,
    "trusted_worker_verification_attestation": True,
    "service_numerical_verification_performed": False,
    "independent_execution_authentication": False,
    "public_j1_j5_authority": False,
    "workbench_execution": False,
    "independent_physical_validation": False,
    "design_authority": False,
    "production_promotion_eligible": False,
    "release_approved": False,
}
RC_FIBER_JOB_CLAIM_BOUNDARY = (
    "Experimental RC control with trusted-worker fresh replay attestations. "
    "Service validation checks structural and artifact bindings without numerical "
    "execution. Reserved API invocations include retries or abandoned work and "
    "are not solver-attempt counts. Hashes do not authenticate source execution; "
    "no independent physical, public J1-J5, Workbench, design, or release authority."
)
_REQUEST_KEYS = {
    "schema_version",
    "operation",
    "case_id",
    "model",
    "config",
    "source_revision",
    "result_contract",
    "execution_config",
}
_COMMON_KEYS = {
    "schema_version",
    "profile",
    "status",
    "contract_pass",
    "request_hash",
    "resume_contract_hash",
    "case_id",
    "source_revision",
    "source_revision_is_attestation",
    "control_targets",
    "total_target_count",
    "completed_target_count",
    "receipts",
    "execution_budget",
    "execution_budget_unit",
    "terminal_checkpoint_artifact_base64",
    "authority",
    "claim_boundary",
}
_RECEIPT_KEYS = {
    "receipt_hash",
    "job_request_hash",
    "chunk_request_hash",
    "completed_before",
    "completed_after",
    "restart_input_sha256",
    "result_hash",
    "result_artifact_sha256",
    "checkpoint_sha256",
    "checkpoint_byte_length",
    "checkpoint_state_hash",
    "path_hash",
    "api_request",
    "model_binding",
    "control",
    "validation_report",
    "analysis_ordinal",
    "verification_ordinal",
    "analysis_timing",
    "verification_timing",
    "analysis_metrics",
    "verification_metrics",
}
_WORK_KEYS = {
    "attempted_step_count",
    "known_linear_solve_count",
    "known_newton_iteration_count",
    "unknown_solver_work_attempt_count",
}
_METRIC_KEYS = {
    "control_work",
    "response_reassembly_attempts",
    "response_reassembly_verified_count",
    "current_epoch",
    "response_history_scope",
    "whole_accepted_history_recovered",
    "explicit_validation_solver_replay_performed",
}
_REPORT_KEYS = {
    "schema_version",
    "status",
    "artifact_contract_pass",
    "contract_pass",
    "physical_path_complete",
    "fresh_source_execution_invoked",
    "solver_replay_performed",
    "unavailable_execution_work",
    "replay_control_work",
    "response_reassembly_attempts",
    "response_reassembly_verified_count",
    "verified_result_hash",
    "errors",
    "claims",
    "verification_scope",
}
_RESULT_KEYS = {
    "schema_version",
    "status",
    "contract_pass",
    "model",
    "request",
    "control",
    "path",
    "response_history",
    "terminal_response",
    "checkpoint",
    "unsupported_features",
    "warnings",
    "failure",
    "claims",
    "metrics",
    "result_hash",
}
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
_REVISION = re.compile(r"(?:[0-9a-f]{40}|sha256:[0-9a-f]{64})\Z")
_HASH = re.compile(r"sha256:[0-9a-f]{64}\Z")


def rc_fiber_job_canonical_bytes(payload: Any) -> bytes:
    # Reject key coercion, tuples, arbitrary objects, and unbounded nesting before
    # json.dumps can silently turn a non-JSON request into a different identity.
    stack = [(payload, 0)]
    while stack:
        value, depth = stack.pop()
        if depth > 64:
            raise ValueError("RC durable JSON nesting exceeds bound")
        if type(value) is dict:
            if any(type(key) is not str for key in value):
                raise ValueError("RC durable JSON keys must be strings")
            stack.extend((item, depth + 1) for item in value.values())
        elif type(value) is list:
            stack.extend((item, depth + 1) for item in value)
        elif type(value) not in (str, int, float, bool, type(None)):
            raise ValueError("RC durable transport requires JSON values")
    try:
        return json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (ValueError, UnicodeError, OverflowError, RecursionError) as error:
        raise ValueError("invalid RC durable JSON") from error


def _mapping(value: Mapping[str, Any] | bytes, maximum=RC_FIBER_JOB_MAX_BYTES):
    raw = value if type(value) is bytes else rc_fiber_job_canonical_bytes(value)
    return strict_json_object_bytes(raw, maximum_bytes=maximum)


def _sha(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _hash(value: Any) -> str:
    return _sha(rc_fiber_job_canonical_bytes(value))


def _same(left: Any, right: Any) -> bool:
    return rc_fiber_job_canonical_bytes(left) == rc_fiber_job_canonical_bytes(right)


def _self_hash(value, key):
    if type(value) is not dict or value.get(key) != _hash(
        {name: item for name, item in value.items() if name != key}
    ):
        raise ValueError(f"RC durable {key} mismatch")


def rc_fiber_job_request_hash(request: Mapping[str, Any]) -> str:
    return _hash(request)


def rc_fiber_job_resume_contract_hash(request: Mapping[str, Any]) -> str:
    return _hash({"profile": RC_FIBER_JOB_PROFILE, "request_hash": _hash(request)})


def validate_rc_fiber_job_request(
    request: Mapping[str, Any],
) -> tuple[CanonicalModel, BoundedRCFiberDirectControlRequest]:
    value = _mapping(request, 16 * 1024 * 1024)
    if (
        set(value) != _REQUEST_KEYS
        or value["schema_version"] != RC_FIBER_JOB_REQUEST_SCHEMA_VERSION
        or value["operation"] != RC_FIBER_JOB_OPERATION
        or value["result_contract"] != RC_FIBER_JOB_RESULT_SCHEMA_VERSION
        or type(value["case_id"]) is not str
        or not _ID.fullmatch(value["case_id"])
        or type(value["source_revision"]) is not str
        or not _REVISION.fullmatch(value["source_revision"])
        or type(value["model"]) is not dict
        or type(value["config"]) is not dict
    ):
        raise ValueError("invalid bounded RC durable request")
    execution = value["execution_config"]
    if (
        type(execution) is not dict
        or set(execution) != {"chunk_target_count", "maximum_api_invocations"}
        or type(execution["chunk_target_count"]) is not int
        or not 1 <= execution["chunk_target_count"] <= 255
        or type(execution["maximum_api_invocations"]) is not int
        or not 2 <= execution["maximum_api_invocations"] <= 4096
    ):
        raise ValueError("invalid RC durable execution configuration")
    config = decode_bounded_rc_fiber_direct_control_request(value["config"])
    if not config.targets_m or not _same(config.to_dict(), value["config"]):
        raise ValueError("RC durable config must be the complete canonical request")
    _, reversals = _directions(config.targets_m)
    if reversals > config.maximum_reversals or (
        reversals and not config.allow_reversals
    ):
        raise ValueError("RC durable whole target path exceeds reversal budget")
    model = load_neutral_json_bytes(
        rc_fiber_job_canonical_bytes(value["model"]), source_path="<durable-rc-model>"
    )
    compiled, unsupported, _ = _compile(model.detached_analysis_snapshot())
    if compiled is None or unsupported:
        raise ValueError("RC durable request uses an unsupported canonical model")
    StatefulFiberFrame2DDisplacementControlStepAdapter(
        compiled.problem,
        initial_stateful_fiber_frame2d_checkpoint(compiled.problem),
        config.control_global_dof,
        config.targets_m[0],
        config.solver_config,
    )
    return model, config


def _context(request):
    model, config = validate_rc_fiber_job_request(request)
    compiled, _, _ = _compile(model.detached_analysis_snapshot())
    scope = _scope(
        compiled.problem,
        config.solver_config,
        config.control_global_dof,
        config.allow_reversals,
        config.maximum_reversals,
        config.maximum_targets,
    )
    binding = {
        "canonical_model_checksum": model.canonical_model_checksum,
        "input_checksum": model.input_checksum,
        "source_format": model.source_format,
        "compiler_profile": PUBLIC_RC_FIBER_FRAME_COMPILER_PROFILE,
        "problem_contract_hash": compiled.problem.contract_hash,
    }
    control = {
        "global_dof": config.control_global_dof,
        "node_id": compiled.node_ids[config.control_global_dof // 3],
        "component": ("UX", "UY", "RZ")[config.control_global_dof % 3],
        "unit": "m",
    }
    return config, compiled, scope, binding, control


def _chunk(config, request, before):
    total = len(config.targets_m)
    size = request["execution_config"]["chunk_target_count"]
    if type(before) is not int or not 0 <= before < total or before % size:
        raise ValueError("RC durable chunk must start at its fixed authored boundary")
    after = min(before + size, total)
    return after, replace(config, targets_m=config.targets_m[before:after])


def _api_request(config, restart_hash):
    return {
        "targets_m": list(config.targets_m),
        "control_global_dof": config.control_global_dof,
        "configuration": config.solver_config.to_manifest(),
        "configuration_hash": config.solver_config.contract_hash,
        "allow_reversals": config.allow_reversals,
        "maximum_reversals": config.maximum_reversals,
        "maximum_targets": config.maximum_targets,
        "restart_input_sha256": restart_hash,
    }


def _budget(value, request):
    maximum = request["execution_config"]["maximum_api_invocations"]
    if (
        type(value) is not dict
        or set(value) != {"maximum_attempts", "reserved_attempts", "remaining_attempts"}
        or any(type(item) is not int for item in value.values())
        or value["maximum_attempts"] != maximum
        or not 0 <= value["reserved_attempts"] <= maximum
        or value["remaining_attempts"] != maximum - value["reserved_attempts"]
    ):
        raise ValueError("RC durable API invocation budget mismatch")
    return value


def _timing(value):
    if (
        type(value) is not dict
        or set(value) != {"wall_ns", "process_cpu_ns"}
        or any(type(item) is not int or item < 0 for item in value.values())
    ):
        raise ValueError(
            "RC durable phase timing must contain nonnegative integer nanoseconds"
        )


def _work(value, count):
    if (
        type(value) is not dict
        or set(value) != _WORK_KEYS
        or any(type(item) is not int or item < 0 for item in value.values())
        or value["attempted_step_count"] != count
        or value["unknown_solver_work_attempt_count"] != 0
    ):
        raise ValueError("RC successful receipt work accounting mismatch")


def _metrics(value, completed):
    if type(value) is not dict or set(value) != _METRIC_KEYS:
        raise ValueError("RC successful API metrics fields mismatch")
    _work(value["control_work"], completed)
    expected = {
        "response_reassembly_attempts": completed,
        "response_reassembly_verified_count": completed,
        "current_epoch": None,
        "response_history_scope": "cumulative_accepted_prefix",
        "whole_accepted_history_recovered": True,
        "explicit_validation_solver_replay_performed": False,
    }
    if not _same({key: value[key] for key in expected}, expected):
        raise ValueError("RC cumulative response recovery metrics mismatch")


def _verification_metrics(report):
    return {
        key: report[key]
        for key in (
            "replay_control_work",
            "response_reassembly_attempts",
            "response_reassembly_verified_count",
        )
    }


def _report(report, result_hash, completed):
    if type(report) is not dict or set(report) != _REPORT_KEYS:
        raise ValueError("RC successful verification report fields mismatch")
    expected = {
        "schema_version": "bounded-rc-fiber-direct-control-validation.v1",
        "status": "valid_artifact",
        "artifact_contract_pass": True,
        "contract_pass": True,
        "physical_path_complete": True,
        "fresh_source_execution_invoked": True,
        "solver_replay_performed": True,
        "unavailable_execution_work": False,
        "response_reassembly_attempts": completed,
        "response_reassembly_verified_count": completed,
        "verified_result_hash": result_hash,
        "errors": [],
        "claims": _API_CLAIMS,
        "verification_scope": "fresh_complete_request_solver_and_original_transition_replay",
    }
    if not _same({key: report[key] for key in expected}, expected):
        raise ValueError(
            "RC receipt requires an exact successful fresh replay attestation"
        )
    _work(report["replay_control_work"], completed)


def _decode_artifact(encoded):
    if type(encoded) is not str or len(encoded) > 4 * (
        (CONTROL_RESTART_MAX_BYTES + 2) // 3
    ):
        raise ValueError("RC durable restart encoding exceeds byte bound")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as error:
        raise ValueError("invalid RC durable restart base64") from error
    if (
        not raw
        or len(raw) > CONTROL_RESTART_MAX_BYTES
        or base64.b64encode(raw).decode("ascii") != encoded
    ):
        raise ValueError("noncanonical RC durable restart encoding")
    return raw


def _native(raw, compiled, scope, targets):
    native, prefix, terminal = _decode_restart(raw, compiled.problem, scope)
    if not _same(list(prefix), list(targets)):
        raise ValueError("RC native restart changed its authored target prefix")
    return native, terminal


def _validate_api(value, raw, receipt, config, compiled, scope, native, terminal):
    if len(raw) > BOUNDED_RC_FIBER_DIRECT_CONTROL_RESULT_MAX_BYTES:
        raise ValueError("RC cumulative API artifact exceeds byte bound")
    if type(value) is not dict or set(value) != _RESULT_KEYS:
        raise ValueError("RC cumulative API result fields mismatch")
    _self_hash(value, "result_hash")
    expected = {
        "schema_version": BOUNDED_RC_FIBER_DIRECT_CONTROL_SCHEMA_VERSION,
        "status": "ready",
        "contract_pass": True,
        "request": receipt["api_request"],
        "model": receipt["model_binding"],
        "control": receipt["control"],
        "claims": _API_CLAIMS,
        "unsupported_features": [],
        "failure": None,
        "metrics": receipt["analysis_metrics"],
        "checkpoint": {
            "sha256": receipt["checkpoint_sha256"],
            "byte_length": receipt["checkpoint_byte_length"],
        },
        "result_hash": receipt["result_hash"],
    }
    if (
        not _same({key: value[key] for key in expected}, expected)
        or _sha(raw) != receipt["result_artifact_sha256"]
        or raw != rc_fiber_job_canonical_bytes(value)
        or type(value["warnings"]) is not list
        or any(type(item) is not str for item in value["warnings"])
    ):
        raise ValueError("RC cumulative API artifact identity mismatch")
    before, after = receipt["completed_before"], receipt["completed_after"]
    path = value["path"]
    _self_hash(path, "path_hash")
    directions, reversals = _directions(config.targets_m[:after])
    expected_path = {
        "schema_version": CONTROL_PATH_SCHEMA,
        "status": "ready",
        "scope": scope,
        "targets_m": list(config.targets_m[before:after]),
        "accepted_target_prefix_m": list(config.targets_m[:after]),
        "unattempted_targets_m": [],
        "requested_directions": list(directions),
        "requested_reversal_count": reversals,
        "accepted_direction": directions[-1],
        "accepted_reversal_count": reversals,
        "restart_input_sha256": receipt["restart_input_sha256"],
        "restart_artifact_hash": native["artifact_hash"],
        "claims": _PATH_CLAIMS,
        "path_hash": receipt["path_hash"],
        "final_checkpoint": terminal.to_dict(),
    }
    if not _same({key: path.get(key) for key in expected_path}, expected_path):
        raise ValueError("RC API path source/target/restart identity mismatch")
    initial = path.get("initial_checkpoint")
    if before == 0:
        initial_matches = _same(
            initial,
            initial_stateful_fiber_frame2d_checkpoint(compiled.problem).to_dict(),
        )
    else:
        initial_identity = {
            "epoch": before,
            "step_index": before,
            "state_hash": native["accepted_step_bindings"][before - 1][
                "accepted_checkpoint_hash"
            ],
        }
        initial_matches = type(initial) is dict and _same(
            {key: initial.get(key) for key in initial_identity}, initial_identity
        )
    if not initial_matches:
        raise ValueError("RC API initial checkpoint detached from accepted prefix")
    counts = path.get("metrics", {})
    if type(counts) is not dict:
        raise ValueError("RC API path metrics must be an object")
    expected_counts = {
        "requested_target_count": after - before,
        "attempted_target_count": after - before,
        "accepted_target_count": after - before,
        "failed_target_count": 0,
        "unattempted_target_count": 0,
        "cumulative_accepted_target_count": after,
        "prefix_replayed_step_count": before,
        "hidden_retries_or_cutbacks": 0,
        "restart_verification_scope": "full_genesis_prefix_solver_replay"
        if before
        else "not_requested",
    }
    if (
        not _same({key: counts.get(key) for key in expected_counts}, expected_counts)
        or type(path.get("attempts")) is not list
        or len(path["attempts"]) != after - before
        or type(path.get("replay_attempts")) is not list
        or len(path["replay_attempts"]) != before
    ):
        raise ValueError("RC API path work/progress mismatch")
    _work(counts.get("prefix_replay_work"), before)
    _work(counts.get("suffix_work"), after - before)
    _work(counts.get("total_work"), after)
    if not _same(counts["total_work"], value["metrics"]["control_work"]) or any(
        counts["total_work"][key]
        != counts["prefix_replay_work"][key] + counts["suffix_work"][key]
        for key in _WORK_KEYS
    ):
        raise ValueError("RC API path phase work totals mismatch")
    history = value["response_history"]
    if (
        type(history) is not list
        or len(history) != after
        or not _same(value["terminal_response"], history[-1])
    ):
        raise ValueError("RC cumulative response history count/terminal mismatch")
    for index, (row, binding) in enumerate(
        zip(history, native["accepted_step_bindings"], strict=True), 1
    ):
        expected_row = {
            "epoch": index,
            "step_index": index,
            "parent_checkpoint_hash": binding["parent_checkpoint_hash"],
            "checkpoint_hash": binding["accepted_checkpoint_hash"],
            "source_step_hash": binding["step_hash"],
            "recovery_scope": "exact_previous_parent_original_newton_coordinates_constitutive_transition",
        }
        if type(row) is not dict or not _same(
            {key: row.get(key) for key in expected_row}, expected_row
        ):
            raise ValueError(
                "RC response history is detached from ordered accepted transitions"
            )


def build_rc_fiber_job_receipt(
    request,
    *,
    completed_before,
    result,
    verification_report,
    restart_checkpoint,
    analysis_ordinal,
    verification_ordinal,
    analysis_timing,
    verification_timing,
):
    config, compiled, scope, model, control = _context(request)
    after, chunk = _chunk(config, request, completed_before)
    if (completed_before == 0) != (restart_checkpoint is None):
        raise ValueError(
            "RC initial chunk must have no restart; later chunks require one"
        )
    if restart_checkpoint is not None:
        _native(
            restart_checkpoint, compiled, scope, config.targets_m[:completed_before]
        )
    value = result.to_dict() if hasattr(result, "to_dict") else _mapping(result)
    raw = (
        result.result_artifact_bytes()
        if hasattr(result, "result_artifact_bytes")
        else rc_fiber_job_canonical_bytes(value)
    )
    checkpoint_raw = result.checkpoint_artifact_bytes()
    native, terminal = _native(
        checkpoint_raw, compiled, scope, config.targets_m[:after]
    )
    report = (
        verification_report.to_dict()
        if hasattr(verification_report, "to_dict")
        else _mapping(verification_report)
    )
    receipt = {
        "job_request_hash": _hash(request),
        "chunk_request_hash": chunk.request_hash,
        "completed_before": completed_before,
        "completed_after": after,
        "restart_input_sha256": None
        if restart_checkpoint is None
        else _sha(restart_checkpoint),
        "result_hash": value["result_hash"],
        "result_artifact_sha256": _sha(raw),
        "checkpoint_sha256": _sha(checkpoint_raw),
        "checkpoint_byte_length": len(checkpoint_raw),
        "checkpoint_state_hash": terminal.state_hash,
        "path_hash": value["path"]["path_hash"],
        "api_request": value["request"],
        "model_binding": value["model"],
        "control": value["control"],
        "validation_report": report,
        "analysis_ordinal": analysis_ordinal,
        "verification_ordinal": verification_ordinal,
        "analysis_timing": analysis_timing,
        "verification_timing": verification_timing,
        "analysis_metrics": value["metrics"],
        "verification_metrics": _verification_metrics(report),
    }
    receipt["receipt_hash"] = _hash(receipt)
    _validate_receipt(
        receipt,
        request,
        config,
        model,
        control,
        completed_before,
        None if restart_checkpoint is None else _sha(restart_checkpoint),
        0,
        request["execution_config"]["maximum_api_invocations"],
    )
    _validate_api(value, raw, receipt, config, compiled, scope, native, terminal)
    return _mapping(receipt)


def _validate_receipt(
    receipt,
    request,
    config,
    model,
    control,
    before,
    restart_hash,
    prior_ordinal,
    reserved,
):
    if type(receipt) is not dict or set(receipt) != _RECEIPT_KEYS:
        raise ValueError("RC compact receipt fields mismatch")
    _self_hash(receipt, "receipt_hash")
    after, chunk = _chunk(config, request, before)
    expected = {
        "job_request_hash": _hash(request),
        "chunk_request_hash": chunk.request_hash,
        "completed_before": before,
        "completed_after": after,
        "restart_input_sha256": restart_hash,
        "api_request": _api_request(chunk, restart_hash),
        "model_binding": model,
        "control": control,
    }
    if not _same({key: receipt[key] for key in expected}, expected):
        raise ValueError("RC compact receipt request/source/restart mismatch")
    for key in (
        "result_hash",
        "result_artifact_sha256",
        "checkpoint_sha256",
        "checkpoint_state_hash",
        "path_hash",
    ):
        if type(receipt[key]) is not str or not _HASH.fullmatch(receipt[key]):
            raise ValueError("RC compact receipt artifact hash invalid")
    if (
        type(receipt["checkpoint_byte_length"]) is not int
        or not 1 <= receipt["checkpoint_byte_length"] <= CONTROL_RESTART_MAX_BYTES
    ):
        raise ValueError("RC compact receipt checkpoint length invalid")
    for key in ("analysis_ordinal", "verification_ordinal"):
        ordinal = receipt[key]
        if type(ordinal) is not int or not prior_ordinal < ordinal <= reserved:
            raise ValueError(
                "RC API invocation ordinals must increase within durable budget"
            )
        prior_ordinal = ordinal
    _timing(receipt["analysis_timing"])
    _timing(receipt["verification_timing"])
    _metrics(receipt["analysis_metrics"], after)
    _report(receipt["validation_report"], receipt["result_hash"], after)
    if not _same(
        receipt["verification_metrics"],
        _verification_metrics(receipt["validation_report"]),
    ):
        raise ValueError("RC verification metrics detached from retained report")
    if not _same(
        receipt["validation_report"]["replay_control_work"],
        receipt["analysis_metrics"]["control_work"],
    ):
        raise ValueError("RC fresh replay work differs from its verified API result")
    return after, prior_ordinal


def build_rc_fiber_job_payload(
    request,
    *,
    receipts,
    execution_budget,
    terminal_checkpoint,
    api_result=None,
    complete=False,
):
    _, config = validate_rc_fiber_job_request(request)
    if type(complete) is not bool or not receipts:
        raise ValueError(
            "RC durable payload requires completed receipts and boolean completion"
        )
    if (api_result is None) == complete:
        raise ValueError("RC final payload alone must retain one cumulative API result")
    raw = bytes(terminal_checkpoint)
    payload = {
        "schema_version": RC_FIBER_JOB_RESULT_SCHEMA_VERSION
        if complete
        else RC_FIBER_JOB_CHECKPOINT_SCHEMA_VERSION,
        "profile": RC_FIBER_JOB_PROFILE,
        "status": "ready" if complete else "checkpointed",
        "contract_pass": True,
        "request_hash": _hash(request),
        "resume_contract_hash": rc_fiber_job_resume_contract_hash(request),
        "case_id": request["case_id"],
        "source_revision": request["source_revision"],
        "source_revision_is_attestation": False,
        "control_targets": list(config.targets_m),
        "total_target_count": len(config.targets_m),
        "completed_target_count": receipts[-1]["completed_after"],
        "receipts": receipts,
        "execution_budget": dict(execution_budget),
        "execution_budget_unit": "reserved_api_invocations",
        "terminal_checkpoint_artifact_base64": base64.b64encode(raw).decode("ascii"),
        "authority": dict(RC_FIBER_JOB_AUTHORITY),
        "claim_boundary": RC_FIBER_JOB_CLAIM_BOUNDARY,
    }
    if complete:
        payload["api_result"] = (
            api_result.to_dict() if hasattr(api_result, "to_dict") else api_result
        )
    payload["result_hash" if complete else "checkpoint_hash"] = _hash(payload)
    return _validate_payload(
        payload, request=request, complete=complete, execution_budget=execution_budget
    )


def _validate_payload(payload, *, request, complete, execution_budget):
    value = _mapping(payload)
    config, compiled, scope, model, control = _context(request)
    key = "result_hash" if complete else "checkpoint_hash"
    if set(value) != _COMMON_KEYS | {key} | ({"api_result"} if complete else set()):
        raise ValueError("RC durable wrapper fields mismatch")
    _self_hash(value, key)
    expected = {
        "schema_version": RC_FIBER_JOB_RESULT_SCHEMA_VERSION
        if complete
        else RC_FIBER_JOB_CHECKPOINT_SCHEMA_VERSION,
        "profile": RC_FIBER_JOB_PROFILE,
        "status": "ready" if complete else "checkpointed",
        "contract_pass": True,
        "request_hash": _hash(request),
        "resume_contract_hash": rc_fiber_job_resume_contract_hash(request),
        "case_id": request["case_id"],
        "source_revision": request["source_revision"],
        "source_revision_is_attestation": False,
        "control_targets": list(config.targets_m),
        "total_target_count": len(config.targets_m),
        "execution_budget_unit": "reserved_api_invocations",
        "authority": RC_FIBER_JOB_AUTHORITY,
        "claim_boundary": RC_FIBER_JOB_CLAIM_BOUNDARY,
    }
    if not _same({name: value[name] for name in expected}, expected):
        raise ValueError("RC durable wrapper request/authority identity mismatch")
    completed = value["completed_target_count"]
    total = len(config.targets_m)
    if (
        type(completed) is not int
        or not 1 <= completed <= total
        or (complete and completed != total)
        or (not complete and completed >= total)
        or type(value["receipts"]) is not list
        or not value["receipts"]
        or len(value["receipts"]) > total
    ):
        raise ValueError("RC durable authored progress mismatch")
    budget = _budget(value["execution_budget"], request)
    current = _budget(dict(execution_budget), request)
    if (complete and current != budget) or current["reserved_attempts"] < budget[
        "reserved_attempts"
    ]:
        raise ValueError("RC durable wrapper is detached from reservation budget")
    raw = _decode_artifact(value["terminal_checkpoint_artifact_base64"])
    native, terminal = _native(raw, compiled, scope, config.targets_m[:completed])
    before, last_ordinal, restart_hash = 0, 0, None
    for receipt in value["receipts"]:
        before, last_ordinal = _validate_receipt(
            receipt,
            request,
            config,
            model,
            control,
            before,
            restart_hash,
            last_ordinal,
            budget["reserved_attempts"],
        )
        if (
            before > completed
            or receipt["checkpoint_state_hash"]
            != native["accepted_step_bindings"][before - 1]["accepted_checkpoint_hash"]
        ):
            raise ValueError("RC chunk receipt endpoint detached from accepted prefix")
        restart_hash = receipt["checkpoint_sha256"]
    tail = value["receipts"][-1]
    if (
        before != completed
        or tail["checkpoint_sha256"] != _sha(raw)
        or tail["checkpoint_byte_length"] != len(raw)
        or tail["checkpoint_state_hash"] != terminal.state_hash
    ):
        raise ValueError(
            "RC terminal restart artifact detached from compact receipt tail"
        )
    if complete:
        _validate_api(
            value["api_result"],
            rc_fiber_job_canonical_bytes(value["api_result"]),
            tail,
            config,
            compiled,
            scope,
            native,
            terminal,
        )
    return value


def _preserve_prefix(value, checkpoint, request, execution_budget):
    if checkpoint is None:
        return
    prior = _validate_payload(
        checkpoint, request=request, complete=False, execution_budget=execution_budget
    )
    # A receipt represents a chunk, not one target. In particular the final
    # chunk can be shorter; slicing by completed_target_count would be wrong.
    if (
        prior["completed_target_count"] > value["completed_target_count"]
        or prior["execution_budget"]["reserved_attempts"]
        > value["execution_budget"]["reserved_attempts"]
        or not _same(prior["receipts"], value["receipts"][: len(prior["receipts"])])
    ):
        raise ValueError("RC durable payload changed its retained receipt prefix")


def validate_rc_fiber_job_checkpoint(
    payload,
    *,
    request,
    progress_completed=None,
    execution_budget,
    checkpoint=None,
):
    value = _validate_payload(
        payload, request=request, complete=False, execution_budget=execution_budget
    )
    if progress_completed is not None and (
        type(progress_completed) is not int
        or progress_completed != value["completed_target_count"]
    ):
        raise ValueError("RC checkpoint cursor differs from durable progress")
    _preserve_prefix(value, checkpoint, request, execution_budget)
    return value


def validate_rc_fiber_job_result(
    payload, *, request, execution_budget, checkpoint=None
):
    value = _validate_payload(
        payload, request=request, complete=True, execution_budget=execution_budget
    )
    _preserve_prefix(value, checkpoint, request, execution_budget)
    return {
        "schema_version": "bounded-rc-fiber-job-validation-report.v1",
        "contract_pass": True,
        "request_hash": value["request_hash"],
        "result_hash": value["result_hash"],
        "completed_target_count": value["completed_target_count"],
        "total_target_count": value["total_target_count"],
        "execution_budget": value["execution_budget"],
        "execution_budget_unit": "reserved_api_invocations",
        "terminal_checkpoint_sha256": value["receipts"][-1]["checkpoint_sha256"],
        "receipt_hashes": [row["receipt_hash"] for row in value["receipts"]],
        "authority": value["authority"],
        "claim_boundary": RC_FIBER_JOB_CLAIM_BOUNDARY,
    }
