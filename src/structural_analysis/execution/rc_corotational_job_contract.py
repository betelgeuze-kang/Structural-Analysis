"""Pure durable receipts for experimental corotational RC execution.

These checks bind retained trusted-worker declarations to immutable requests,
native continuations and exact durable invocation outcomes. They perform no
numerical replay and do not independently authenticate execution or physics.
Invocation reservations, including crashed or unknown work, are never refunded.
"""

from __future__ import annotations

import base64
import binascii
from dataclasses import asdict
import hashlib
import json
import re
from typing import Any, Mapping

from structural_analysis.api.rc_corotational_control import SCHEMA as API_SCHEMA
from structural_analysis.api.rc_corotational_control_model import (
    compile_rc_corotational_control_model,
)
from structural_analysis.api.strict_json import strict_json_object_bytes
from structural_analysis.assembly.stateful_corotational_fiber_frame2d import (
    initial_stateful_corotational_fiber_frame2d_checkpoint,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_control_subdivision import (
    _decode_continuation,
)
from structural_analysis.execution.rc_corotational_job_request import (
    ISOLATED_RC_COROTATIONAL_JOB_REQUEST_SCHEMA_VERSION,
    RC_COROTATIONAL_JOB_PROFILE,
    RC_COROTATIONAL_JOB_RESULT_SCHEMA_VERSION,
    RCCorotationalJobRequest,
    rc_corotational_job_canonical_bytes,
    validate_rc_corotational_job_request,
)


RC_COROTATIONAL_JOB_CHECKPOINT_SCHEMA_VERSION = (
    "bounded-rc-corotational-job-checkpoint.v1"
)
RC_COROTATIONAL_JOB_INVOCATION_SCHEMA_VERSION = (
    "bounded-rc-corotational-job-invocation.v1"
)
ISOLATED_RC_COROTATIONAL_JOB_INVOCATION_SCHEMA_VERSION = (
    "bounded-rc-corotational-job-invocation.v2"
)
RC_COROTATIONAL_PHASE_SUPERVISION_SCHEMA_VERSION = (
    "bounded-rc-corotational-phase-supervision.v1"
)
RC_COROTATIONAL_JOB_VALIDATOR_ID = "structural_analysis.execution.rc_corotational_job_contract.validate_rc_corotational_job_result"
RC_COROTATIONAL_JOB_MAX_BYTES = 96 * 1024 * 1024
_MAX_CONTINUATION_BYTES = 16 * 1024 * 1024
_MAX_API_BYTES = 64 * 1024 * 1024
RC_COROTATIONAL_JOB_AUTHORITY = {
    "experimental_corotational_rc_control": True,
    "trusted_worker_verification_attestation": True,
    "service_numerical_verification_performed": False,
    "independent_execution_authentication": False,
    "independent_physical_validation": False,
    "design_authority": False,
    "release_approved": False,
    "production_promotion_eligible": False,
}
RC_COROTATIONAL_JOB_CLAIM_BOUNDARY = (
    "Pure transport and trusted-worker replay attestations for experimental RC "
    "control. Control attempts and reserved API invocations are distinct units. "
    "Crashed, abandoned or unknown reservations remain spent. Hashes establish "
    "artifact integrity, not independent execution, physical, design or release authority."
)
_HASH = re.compile(r"sha256:[0-9a-f]{64}\Z")
_BARE_HASH = re.compile(r"[0-9a-f]{64}\Z")
_OUTCOME_KEYS = {
    "schema_version",
    "phase",
    "status",
    "job_request_hash",
    "chunk_request_hash",
    "completed_before",
    "completed_after",
    "restart_input_sha256",
    "timing",
    "api_result",
    "checkpoint_artifact_base64",
    "verification_report",
    "error",
    "unavailable_execution_work",
}
_PHASE_SUPERVISION_KEYS = {
    "schema_version",
    "phase",
    "job_request_hash",
    "chunk_request_hash",
    "completed_before",
    "planned_after",
    "restart_input_sha256",
    "policy",
    "status",
    "supervisor",
    "cleanup",
}
_MEASURED_SUPERVISOR_KEYS = {
    "wall_ns",
    "child_pid",
    "child_returncode",
    "direct_child_reaped",
    "stderr_byte_count",
    "stderr_retained_bytes",
    "stderr_truncated",
    "scope",
}
_MEASURED_SUPERVISOR_SCOPE = (
    "parent launch/request/import/API/export/IPC/reap; contains child API scope"
)
_UNACCOUNTED_SUPERVISOR_SCOPE = "parent phase failure; child CPU unavailable"
_STDERR_RETAINED_MAX_BYTES = 64 * 1024
_API_KEYS = {
    "schema",
    "request",
    "status",
    "terminal_reason",
    "contract_pass",
    "completed_target_count",
    "total_control_attempts",
    "continuation_sha256",
    "work",
    "responses",
    "claims",
}
_WORK_KEYS = {
    "preload_solver_calls",
    "restart_replay_solver_calls",
    "control_solver_calls",
    "unavailable_execution_work",
}
_REPORT_KEYS = {
    "artifact_contract_pass",
    "physical_path_complete",
    "fresh_source_execution_invoked",
    "solver_replay_performed",
    "replay_work",
    "independent_physical_validation",
    "contract_pass",
}
_RECEIPT_KEYS = {
    "receipt_hash",
    "job_request_hash",
    "chunk_request_hash",
    "completed_before",
    "planned_after",
    "actual_after",
    "completed_target_count",
    "api_status",
    "api_contract_pass",
    "restart_input_sha256",
    "result_artifact_sha256",
    "checkpoint_sha256",
    "checkpoint_byte_length",
    "checkpoint_state_hash",
    "api_request",
    "validation_report",
    "analysis_ordinal",
    "verification_ordinal",
    "analysis_timing",
    "verification_timing",
    "analysis_work",
    "verification_work",
}
_PAYLOAD_KEYS = {
    "schema_version",
    "profile",
    "status",
    "contract_pass",
    "request_hash",
    "resume_contract_hash",
    "case_id",
    "source_revision",
    "source_revision_is_attestation",
    "progress_completed",
    "progress_total",
    "progress_unit",
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


def _mapping(
    value: Any, maximum: int = RC_COROTATIONAL_JOB_MAX_BYTES
) -> dict[str, Any]:
    raw = value if type(value) is bytes else rc_corotational_job_canonical_bytes(value)
    return strict_json_object_bytes(raw, maximum_bytes=maximum)


def _typed(request: Any) -> RCCorotationalJobRequest:
    return (
        request
        if type(request) is RCCorotationalJobRequest
        else validate_rc_corotational_job_request(request)
    )


def _sha(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _hash(value: Any) -> str:
    return _sha(rc_corotational_job_canonical_bytes(value))


def _api_bytes(value: Any) -> bytes:
    # The numerical API's exact artifact encoding uses ASCII escapes.
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


def _same(left: Any, right: Any) -> bool:
    return rc_corotational_job_canonical_bytes(
        left
    ) == rc_corotational_job_canonical_bytes(right)


def _integer(value: Any, lower: int, upper: int, name: str) -> int:
    if type(value) is not int or not lower <= value <= upper:
        raise ValueError(f"invalid corotational {name}")
    return value


def _hash_field(value: Any, *, nullable: bool = False):
    if nullable and value is None:
        return
    if type(value) is not str or not _HASH.fullmatch(value):
        raise ValueError("invalid corotational artifact hash")


def _self_hash(value: dict[str, Any], key: str):
    if value.get(key) != _hash(
        {name: item for name, item in value.items() if name != key}
    ):
        raise ValueError(f"corotational {key} mismatch")


def _base64(raw: Any) -> bytes:
    if type(raw) is not str or len(raw) > 4 * ((_MAX_CONTINUATION_BYTES + 2) // 3):
        raise ValueError("invalid corotational continuation encoding")
    try:
        decoded = base64.b64decode(raw, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("invalid corotational continuation encoding") from exc
    if (
        not decoded
        or len(decoded) > _MAX_CONTINUATION_BYTES
        or base64.b64encode(decoded).decode("ascii") != raw
    ):
        raise ValueError("invalid corotational continuation bytes")
    return decoded


def _timing(value: Any):
    if type(value) is not dict or set(value) != {"wall_ns", "process_cpu_ns"}:
        raise ValueError("invalid corotational invocation timing")
    for count in value.values():
        _integer(count, 0, 2**63 - 1, "timing counter")


def _phase_supervision(value, typed, binding):
    """Bind worker supervision declarations without authenticating child execution."""
    supervision = value["phase_supervision"]
    policy = typed.execution_config.phase_execution_policy
    if (
        type(supervision) is not dict
        or set(supervision) != _PHASE_SUPERVISION_KEYS
        or supervision["schema_version"]
        != RC_COROTATIONAL_PHASE_SUPERVISION_SCHEMA_VERSION
        or policy is None
        or not _same(supervision["policy"], policy.to_dict())
        or supervision["phase"] != value["phase"]
        or supervision["job_request_hash"] != typed.request_hash
        or supervision["chunk_request_hash"] != binding["chunk_request_hash"]
        or type(supervision["completed_before"]) is not int
        or supervision["completed_before"] != binding["completed_before"]
        or type(supervision["planned_after"]) is not int
        or supervision["planned_after"] != binding["planned_after"]
        or supervision["restart_input_sha256"] != binding["restart_input_sha256"]
        or type(supervision["status"]) is not str
        or supervision["status"] not in ("returned", "raised", "unaccounted")
        or type(supervision["supervisor"]) is not dict
        or type(supervision["cleanup"]) is not dict
    ):
        raise ValueError("corotational phase supervision request/span/policy mismatch")
    summary, timing = supervision["supervisor"], value["timing"]
    if supervision["status"] == "unaccounted":
        if (
            value["status"] != "raised"
            or set(summary) != {"wall_ns", "scope"}
            or summary["scope"] != _UNACCOUNTED_SUPERVISOR_SCOPE
            or type(timing) is not dict
            or set(timing) != {"wall_ns", "process_cpu_ns"}
            or timing["process_cpu_ns"] is not None
        ):
            raise ValueError("invalid unaccounted corotational phase supervision")
        _integer(summary["wall_ns"], 0, 2**63 - 1, "supervisor wall timing")
        _integer(timing["wall_ns"], 0, 2**63 - 1, "parent failure wall timing")
        if timing["wall_ns"] != summary["wall_ns"]:
            raise ValueError("corotational parent failure timing mismatch")
        # Cleanup diagnostics, including incomplete cleanup, are retained as audit
        # evidence. The outer raised status forbids an accepted receipt.
        return
    _timing(timing)
    if (
        supervision["status"] != value["status"]
        or set(summary) != _MEASURED_SUPERVISOR_KEYS
        or summary["scope"] != _MEASURED_SUPERVISOR_SCOPE
        or type(summary["child_returncode"]) is not int
        or summary["child_returncode"] != 0
        or summary["direct_child_reaped"] is not True
        or type(summary["stderr_truncated"]) is not bool
        or supervision["cleanup"]
    ):
        raise ValueError(
            "corotational measured phase requires a reaped successful child"
        )
    _integer(summary["child_pid"], 1, 2**63 - 1, "supervisor child pid")
    _integer(summary["wall_ns"], 0, 2**63 - 1, "supervisor wall timing")
    _integer(summary["stderr_byte_count"], 0, 2**63 - 1, "stderr byte count")
    _integer(
        summary["stderr_retained_bytes"],
        0,
        _STDERR_RETAINED_MAX_BYTES,
        "retained stderr byte count",
    )
    timeout_ms = (
        policy.analysis_timeout_ms
        if value["phase"] == "analysis"
        else policy.verification_timeout_ms
    )
    if (
        not timing["wall_ns"] <= summary["wall_ns"] <= timeout_ms * 1_000_000
        or summary["stderr_retained_bytes"]
        != min(summary["stderr_byte_count"], _STDERR_RETAINED_MAX_BYTES)
        or summary["stderr_truncated"]
        != (summary["stderr_byte_count"] > summary["stderr_retained_bytes"])
    ):
        raise ValueError("corotational supervisor timing/stderr bounds mismatch")


def _work(value: Any):
    if type(value) is not dict or set(value) != _WORK_KEYS:
        raise ValueError("invalid corotational work fields")
    for key in _WORK_KEYS - {"unavailable_execution_work"}:
        _integer(value[key], 0, 4096, "solver-call counter")
    if type(value["unavailable_execution_work"]) is not bool:
        raise ValueError("invalid corotational unavailable work flag")


def _budget(value: Any, typed: RCCorotationalJobRequest) -> dict[str, Any]:
    maximum = typed.execution_config.maximum_api_invocations
    if type(value) is not dict or set(value) != {
        "maximum_attempts",
        "reserved_attempts",
        "remaining_attempts",
    }:
        raise ValueError("invalid corotational invocation budget")
    if (
        any(type(count) is not int for count in value.values())
        or value["maximum_attempts"] != maximum
    ):
        raise ValueError("corotational invocation budget maximum mismatch")
    _integer(value["reserved_attempts"], 0, maximum, "reserved invocation count")
    if value["remaining_attempts"] != maximum - value["reserved_attempts"]:
        raise ValueError("corotational invocation budget refund or remainder mismatch")
    return value


def rc_corotational_chunk_binding(request, before: int, restart_bytes: bytes | None):
    """Bind the immutable whole history, planned attempt span and restart bytes."""
    typed = _typed(request)
    _integer(before, 0, typed.progress_total - 1, "completed-before counter")
    if (before == 0) != (restart_bytes is None):
        raise ValueError(
            "initial invocation has no restart; later invocations require one"
        )
    if restart_bytes is not None and (
        type(restart_bytes) is not bytes
        or not 1 <= len(restart_bytes) <= _MAX_CONTINUATION_BYTES
    ):
        raise ValueError("restart must contain bounded immutable bytes")
    return _chunk_from_hash(
        typed, before, None if restart_bytes is None else _sha(restart_bytes)
    )


def _chunk_from_hash(typed, before, restart_hash):
    _integer(before, 0, typed.progress_total - 1, "completed-before counter")
    _hash_field(restart_hash, nullable=True)
    if (before == 0) != (restart_hash is None):
        raise ValueError("corotational restart/progress binding mismatch")
    binding = {
        "schema_version": "bounded-rc-corotational-job-chunk.v1",
        "job_request_hash": typed.request_hash,
        "completed_before": before,
        "planned_after": min(
            before + typed.execution_config.attempt_limit_per_call, typed.progress_total
        ),
        "restart_input_sha256": restart_hash,
    }
    return dict(binding, chunk_request_hash=_hash(binding))


def _expected_api_request(typed, before, restart_hash, source_identity):
    if type(source_identity) is not str or not _BARE_HASH.fullmatch(source_identity):
        raise ValueError("invalid corotational API source identity")
    cfg = typed.config
    node_ids = [row["id"] for row in typed.model.nodes]
    return json.loads(
        _api_bytes(
            {
                "model_checksum": typed.source_model_checksum,
                "input_checksum": typed.source_input_checksum,
                "problem_hash": typed.problem_contract_hash,
                "source_identity": source_identity,
                "targets_m": typed.targets_m,
                "control_global_dof": 3 * node_ids.index(cfg.control_node_id)
                + (cfg.control_component == "UY"),
                "config": asdict(cfg.solver_config),
                "preload_config": asdict(cfg.preload_config),
                "maximum_attempt_count": cfg.maximum_attempt_count,
                "maximum_subdivision_depth": cfg.maximum_subdivision_depth,
                "attempt_limit_per_call": typed.execution_config.attempt_limit_per_call,
                "restart_sha256": None
                if restart_hash is None
                else restart_hash.removeprefix("sha256:"),
            }
        )
    )


def _native(raw, typed, api_request):
    if type(raw) is not bytes or not 1 <= len(raw) <= _MAX_CONTINUATION_BYTES:
        raise ValueError("invalid corotational native continuation bytes")
    envelope = _mapping(raw, _MAX_CONTINUATION_BYTES)
    if _api_bytes(envelope) != raw:
        raise ValueError("native continuation must retain its canonical exact bytes")
    compiled = compile_rc_corotational_control_model(
        typed.model,
        fixed_nodal_loads=typed.config.fixed_nodal_loads,
        experimental_pin_roller_beam=typed.config.experimental_pin_roller_beam,
        experimental_fixed_guided_axial=typed.config.experimental_fixed_guided_axial,
    )
    context = hashlib.sha256(
        _api_bytes(
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
    decoded = _decode_continuation(
        raw,
        compiled.problem,
        context,
        typed.targets_m,
        typed.progress_total,
        typed.config.maximum_subdivision_depth,
    )
    first, accepted, _pending, completed, spent, _terminal = decoded
    initial = initial_stateful_corotational_fiber_frame2d_checkpoint(compiled.problem)
    if (
        first.epoch != 1
        or first.load_factor != 0.0
        or first.parent_state_hash != initial.state_hash
    ):
        raise ValueError("corotational native initial-load checkpoint binding mismatch")
    if not completed <= accepted.epoch - first.epoch <= spent:
        raise ValueError(
            "corotational native accepted epochs exceed target/attempt counts"
        )
    return decoded


def _response_history(rows, typed, first, accepted):
    if len(rows) != accepted.epoch - first.epoch + 1:
        raise ValueError(
            "corotational cumulative response/accepted epoch count mismatch"
        )
    model = typed.model
    node_ids = [row["id"] for row in model.nodes]
    member_ids = [row["id"] for row in model.elements]
    parent, hashes = first.parent_state_hash, set()
    for index, row in enumerate(rows):
        if type(row) is not dict or set(row) != {
            "phase",
            "checkpoint_hash",
            "parent_checkpoint_hash",
            "load_factor",
            "nodes",
            "members",
        }:
            raise ValueError("invalid corotational response row fields")
        if (
            row["phase"] != ("preload" if index == 0 else "control")
            or row["parent_checkpoint_hash"] != parent
        ):
            raise ValueError("corotational response checkpoint ancestry mismatch")
        _hash_field(row["checkpoint_hash"])
        if row["checkpoint_hash"] in hashes or (
            index == 0 and row["checkpoint_hash"] != first.state_hash
        ):
            raise ValueError("corotational response checkpoint history was rewritten")
        hashes.add(row["checkpoint_hash"])
        parent = row["checkpoint_hash"]
        if type(row["load_factor"]) not in (int, float):
            raise ValueError("invalid corotational response load factor")
        if type(row["nodes"]) is not list or len(row["nodes"]) != len(node_ids):
            raise ValueError("corotational response node count mismatch")
        for node_id, node in zip(node_ids, row["nodes"], strict=True):
            if (
                type(node) is not dict
                or set(node)
                != {
                    "node_id",
                    "displacements_m_rad",
                    "external_loads_kn_knm",
                    "reactions_kn_knm",
                }
                or node["node_id"] != node_id
            ):
                raise ValueError("corotational response node identity mismatch")
            for key in (
                "displacements_m_rad",
                "external_loads_kn_knm",
                "reactions_kn_knm",
            ):
                if (
                    type(node[key]) is not list
                    or len(node[key]) != 3
                    or any(type(v) not in (int, float) for v in node[key])
                ):
                    raise ValueError("invalid corotational response vector")
        if (
            type(row["members"]) is not list
            or len(row["members"]) != len(member_ids)
            or any(
                type(member) is not dict or member.get("member_id") != expected
                for member, expected in zip(row["members"], member_ids, strict=True)
            )
        ):
            raise ValueError("corotational response member identity mismatch")
    if (
        parent != accepted.state_hash
        or not _same(rows[-1]["load_factor"], accepted.load_factor)
        or not _same(
            [v for node in rows[-1]["nodes"] for v in node["displacements_m_rad"]],
            list(accepted.global_displacements),
        )
    ):
        raise ValueError(
            "corotational terminal response detached from accepted checkpoint"
        )


def _api(value, typed, before, planned_after, restart_hash, continuation=None):
    if (
        type(value) is not dict
        or set(value) != _API_KEYS
        or value["schema"] != API_SCHEMA
    ):
        raise ValueError("invalid corotational API artifact fields")
    if len(_api_bytes(value)) > _MAX_API_BYTES:
        raise ValueError("corotational API artifact exceeds byte bound")
    api_request = value["request"]
    if type(api_request) is not dict or not _same(
        api_request,
        _expected_api_request(
            typed, before, restart_hash, api_request.get("source_identity")
        ),
    ):
        raise ValueError(
            "corotational API artifact input/source/policy binding mismatch"
        )
    if (
        value["status"] not in ("ready", "paused", "blocked")
        or type(value["status"]) is not str
    ):
        raise ValueError("invalid corotational API status")
    if type(value["terminal_reason"]) is not str or not value["terminal_reason"]:
        raise ValueError("invalid corotational API terminal reason")
    count = _integer(
        value["total_control_attempts"], 0, typed.progress_total, "actual progress"
    )
    targets = _integer(
        value["completed_target_count"],
        0,
        min(len(typed.targets_m), count),
        "completed target count",
    )
    if type(value["contract_pass"]) is not bool or value["contract_pass"] != (
        value["status"] == "ready" and targets == len(typed.targets_m)
    ):
        raise ValueError("corotational API completion claim mismatch")
    if value["status"] == "paused" and (
        targets == len(typed.targets_m)
        or value["terminal_reason"] != "cooperative_pause"
    ):
        raise ValueError("invalid corotational paused artifact")
    if (
        value["status"] == "ready"
        and value["terminal_reason"] != "all_authored_targets_reached"
    ):
        raise ValueError("invalid corotational ready artifact")
    _work(value["work"])
    if value["work"]["preload_solver_calls"] != 1:
        raise ValueError("corotational API must account for initial-load execution")
    if not _same(
        value["claims"],
        {
            "independent_physical_validation": False,
            "managed_budget_authority": False,
            "design_authority": False,
        },
    ):
        raise ValueError("corotational API authority claims mismatch")
    if type(value["responses"]) is not list or len(value["responses"]) > count + 1:
        raise ValueError("corotational API response history is not bounded")
    if value["status"] in ("ready", "paused"):
        if (
            not before < count <= planned_after
            or value["work"]["unavailable_execution_work"]
        ):
            raise ValueError(
                "corotational accepted API progress exceeds planned attempts"
            )
        if (
            value["work"]["restart_replay_solver_calls"] != before
            or value["work"]["control_solver_calls"] != count - before
        ):
            raise ValueError("corotational API replay/control work mismatch")
        if type(value["continuation_sha256"]) is not str or not _BARE_HASH.fullmatch(
            value["continuation_sha256"]
        ):
            raise ValueError("invalid corotational API continuation hash")
    elif value["continuation_sha256"] is not None and (
        type(value["continuation_sha256"]) is not str
        or not _BARE_HASH.fullmatch(value["continuation_sha256"])
    ):
        raise ValueError("invalid corotational blocked continuation hash")
    if continuation is not None:
        if value["continuation_sha256"] != hashlib.sha256(continuation).hexdigest():
            raise ValueError("corotational API/continuation hash mismatch")
        first, accepted, pending, completed, spent, terminal = _native(
            continuation, typed, api_request
        )
        if spent != count or completed != targets:
            raise ValueError("corotational native continuation progress mismatch")
        if value["status"] in ("ready", "paused") and (
            terminal or bool(pending) != (value["status"] == "paused")
        ):
            raise ValueError("corotational native continuation completion mismatch")
        if accepted.epoch < first.epoch or accepted.epoch > first.epoch + spent:
            raise ValueError("corotational accepted state epoch exceeds attempted work")
        if value["status"] in ("ready", "paused"):
            _response_history(value["responses"], typed, first, accepted)
        return accepted
    return None


def _report(value):
    if type(value) is not dict or set(value) != _REPORT_KEYS:
        raise ValueError("invalid corotational verification report")
    for key in _REPORT_KEYS - {"replay_work"}:
        if type(value[key]) is not bool:
            raise ValueError("invalid corotational verification flag")
    if (
        not value["fresh_source_execution_invoked"]
        or not value["solver_replay_performed"]
        or value["independent_physical_validation"]
    ):
        raise ValueError("corotational verification source/authority flags mismatch")
    if value["physical_path_complete"] != value["contract_pass"] or (
        value["contract_pass"] and not value["artifact_contract_pass"]
    ):
        raise ValueError("corotational verification completion mismatch")
    _work(value["replay_work"])


def validate_rc_corotational_invocation_outcome(outcome, request, request_hash):
    """Return canonical validated outcome; raised/blocked records remain audit evidence."""
    typed, value = _typed(request), _mapping(outcome)
    isolated = (
        typed.to_dict()["schema_version"]
        == ISOLATED_RC_COROTATIONAL_JOB_REQUEST_SCHEMA_VERSION
    )
    outcome_keys = _OUTCOME_KEYS | {"phase_supervision"} if isolated else _OUTCOME_KEYS
    schema = (
        ISOLATED_RC_COROTATIONAL_JOB_INVOCATION_SCHEMA_VERSION
        if isolated
        else RC_COROTATIONAL_JOB_INVOCATION_SCHEMA_VERSION
    )
    if (
        request_hash != typed.request_hash
        or set(value) != outcome_keys
        or value["schema_version"] != schema
    ):
        raise ValueError("corotational invocation request/schema mismatch")
    if (
        type(value["phase"]) is not str
        or value["phase"] not in ("analysis", "verification")
        or type(value["status"]) is not str
        or value["status"] not in ("returned", "raised")
    ):
        raise ValueError("invalid corotational invocation phase/status")
    binding = _chunk_from_hash(
        typed, value["completed_before"], value["restart_input_sha256"]
    )
    if (
        value["job_request_hash"] != typed.request_hash
        or value["chunk_request_hash"] != binding["chunk_request_hash"]
        or type(value["completed_after"]) is not int
        or value["completed_after"] != binding["planned_after"]
    ):
        raise ValueError("corotational invocation planned span mismatch")
    if isolated:
        _phase_supervision(value, typed, binding)
    else:
        _timing(value["timing"])
    if type(value["unavailable_execution_work"]) is not bool:
        raise ValueError("invalid corotational invocation unavailable-work flag")
    if value["phase"] == "verification" and (
        value["api_result"] is not None
        or value["checkpoint_artifact_base64"] is not None
    ):
        raise ValueError("verification cannot duplicate analysis artifacts")
    if value["phase"] == "analysis" and value["verification_report"] is not None:
        raise ValueError("analysis cannot attest its own verification")
    raw = (
        None
        if value["checkpoint_artifact_base64"] is None
        else _base64(value["checkpoint_artifact_base64"])
    )
    if value["status"] == "raised":
        if (
            type(value["error"]) is not dict
            or not value["error"]
            or not value["unavailable_execution_work"]
        ):
            raise ValueError(
                "raised corotational invocation must retain error and unknown work"
            )
        if (
            value["api_result"] is not None
            or value["verification_report"] is not None
            or raw is not None
        ):
            raise ValueError(
                "raised corotational invocation cannot claim returned artifacts"
            )
        return value
    if value["error"] is not None:
        raise ValueError("returned corotational invocation cannot retain an exception")
    if value["phase"] == "analysis":
        _api(
            value["api_result"],
            typed,
            value["completed_before"],
            binding["planned_after"],
            value["restart_input_sha256"],
            raw,
        )
        if value["api_result"]["status"] in ("ready", "paused") and raw is None:
            raise ValueError(
                "accepted corotational analysis requires native continuation"
            )
        if (value["api_result"]["continuation_sha256"] is None) != (raw is None):
            raise ValueError("corotational returned continuation custody mismatch")
        unknown = value["api_result"]["work"]["unavailable_execution_work"]
    else:
        _report(value["verification_report"])
        unknown = value["verification_report"]["replay_work"][
            "unavailable_execution_work"
        ]
    if unknown and not value["unavailable_execution_work"]:
        raise ValueError("unknown corotational work cannot be reported fully accounted")
    return value


def build_rc_corotational_job_receipt(
    request,
    completed_before,
    analysis_ordinal,
    verification_ordinal,
    analysis_outcome,
    verification_outcome,
):
    """Build compact receipt from a returned analysis and its fresh verification."""
    typed = _typed(request)
    analysis = validate_rc_corotational_invocation_outcome(
        analysis_outcome, typed, typed.request_hash
    )
    verification = validate_rc_corotational_invocation_outcome(
        verification_outcome, typed, typed.request_hash
    )
    if (
        analysis["phase"] != "analysis"
        or verification["phase"] != "verification"
        or analysis["status"] != "returned"
        or verification["status"] != "returned"
    ):
        raise ValueError(
            "accepted corotational receipt requires returned analysis/verification pair"
        )
    if any(value["unavailable_execution_work"] for value in (analysis, verification)):
        raise ValueError(
            "unknown execution work cannot produce accepted corotational receipt"
        )
    for field in (
        "job_request_hash",
        "chunk_request_hash",
        "completed_before",
        "completed_after",
        "restart_input_sha256",
    ):
        if not _same(analysis[field], verification[field]):
            raise ValueError(
                "corotational phase pair binds different planned invocation"
            )
    if (
        type(completed_before) is not int
        or completed_before != analysis["completed_before"]
    ):
        raise ValueError("corotational receipt progress differs from invocation")
    _integer(
        analysis_ordinal,
        1,
        typed.execution_config.maximum_api_invocations,
        "analysis ordinal",
    )
    _integer(
        verification_ordinal,
        analysis_ordinal + 1,
        typed.execution_config.maximum_api_invocations,
        "verification ordinal",
    )
    api, report = analysis["api_result"], verification["verification_report"]
    if (
        api["status"] not in ("ready", "paused")
        or not report["artifact_contract_pass"]
        or report["contract_pass"] != api["contract_pass"]
        or not _same(api["work"], report["replay_work"])
    ):
        raise ValueError(
            "corotational receipt requires matching fresh accepted artifact verification"
        )
    raw = _base64(analysis["checkpoint_artifact_base64"])
    accepted = _api(
        api,
        typed,
        completed_before,
        analysis["completed_after"],
        analysis["restart_input_sha256"],
        raw,
    )
    receipt = {
        "job_request_hash": typed.request_hash,
        "chunk_request_hash": analysis["chunk_request_hash"],
        "completed_before": completed_before,
        "planned_after": analysis["completed_after"],
        "actual_after": api["total_control_attempts"],
        "completed_target_count": api["completed_target_count"],
        "api_status": api["status"],
        "api_contract_pass": api["contract_pass"],
        "restart_input_sha256": analysis["restart_input_sha256"],
        "result_artifact_sha256": _sha(_api_bytes(api)),
        "checkpoint_sha256": _sha(raw),
        "checkpoint_byte_length": len(raw),
        "checkpoint_state_hash": "sha256:"
        + accepted.state_hash.removeprefix("sha256:"),
        "api_request": api["request"],
        "validation_report": report,
        "analysis_ordinal": analysis_ordinal,
        "verification_ordinal": verification_ordinal,
        "analysis_timing": analysis["timing"],
        "verification_timing": verification["timing"],
        "analysis_work": api["work"],
        "verification_work": report["replay_work"],
    }
    receipt["receipt_hash"] = _hash(receipt)
    return _mapping(receipt)


def _receipt(row, typed, before, restart_hash, prior_ordinal, reserved):
    if type(row) is not dict or set(row) != _RECEIPT_KEYS:
        raise ValueError("invalid corotational compact receipt fields")
    _self_hash(row, "receipt_hash")
    binding = _chunk_from_hash(typed, before, restart_hash)
    expected = {
        "job_request_hash": typed.request_hash,
        "chunk_request_hash": binding["chunk_request_hash"],
        "completed_before": before,
        "planned_after": binding["planned_after"],
        "restart_input_sha256": restart_hash,
    }
    if not _same({key: row[key] for key in expected}, expected):
        raise ValueError("corotational receipt prefix/planned binding mismatch")
    actual = _integer(
        row["actual_after"],
        before + 1,
        binding["planned_after"],
        "actual receipt progress",
    )
    targets = _integer(
        row["completed_target_count"],
        0,
        min(len(typed.targets_m), actual),
        "receipt target progress",
    )
    if (
        row["api_status"] not in ("ready", "paused")
        or type(row["api_status"]) is not str
        or type(row["api_contract_pass"]) is not bool
        or row["api_contract_pass"]
        != (row["api_status"] == "ready" and targets == len(typed.targets_m))
    ):
        raise ValueError("corotational receipt completion mismatch")
    if row["api_status"] == "paused" and targets == len(typed.targets_m):
        raise ValueError("corotational paused receipt already completed all targets")
    for key in ("result_artifact_sha256", "checkpoint_sha256", "checkpoint_state_hash"):
        _hash_field(row[key])
    _integer(
        row["checkpoint_byte_length"],
        1,
        _MAX_CONTINUATION_BYTES,
        "checkpoint byte length",
    )
    api_request = row["api_request"]
    if type(api_request) is not dict or not _same(
        api_request,
        _expected_api_request(
            typed, before, restart_hash, api_request.get("source_identity")
        ),
    ):
        raise ValueError("corotational receipt API request mismatch")
    for key in ("analysis_ordinal", "verification_ordinal"):
        prior_ordinal = _integer(
            row[key], prior_ordinal + 1, reserved, "receipt invocation ordinal"
        )
    _timing(row["analysis_timing"])
    _timing(row["verification_timing"])
    _work(row["analysis_work"])
    work = row["analysis_work"]
    if (
        work["unavailable_execution_work"]
        or work["preload_solver_calls"] != 1
        or work["restart_replay_solver_calls"] != before
        or work["control_solver_calls"] != actual - before
    ):
        raise ValueError("corotational receipt solver work mismatch")
    _report(row["validation_report"])
    report = row["validation_report"]
    if (
        not report["artifact_contract_pass"]
        or report["contract_pass"] != row["api_contract_pass"]
        or not _same(work, report["replay_work"])
        or not _same(row["verification_work"], report["replay_work"])
    ):
        raise ValueError("corotational receipt fresh replay work/report mismatch")
    return actual, targets, prior_ordinal


def bind_rc_corotational_receipts(
    receipts, outcomes_by_ordinal: Mapping[int, Any], request
):
    """Match exact pairs, including hashes/timing/work; usable on a single receipt."""
    typed = _typed(request)
    if (
        type(receipts) not in (list, tuple)
        or not receipts
        or len(receipts) > typed.progress_total
    ):
        raise ValueError("invalid corotational receipt binding count")
    seen, bound = set(), []
    for supplied in receipts:
        row = _mapping(supplied)
        _receipt(
            row,
            typed,
            row.get("completed_before"),
            row.get("restart_input_sha256"),
            0,
            typed.execution_config.maximum_api_invocations,
        )
        pair = row["analysis_ordinal"], row["verification_ordinal"]
        if any(
            ordinal in seen or ordinal not in outcomes_by_ordinal for ordinal in pair
        ):
            raise ValueError(
                "corotational receipt missing or reused durable outcome ordinal"
            )
        expected = build_rc_corotational_job_receipt(
            typed,
            row["completed_before"],
            *pair,
            outcomes_by_ordinal[pair[0]],
            outcomes_by_ordinal[pair[1]],
        )
        if not _same(row, expected):
            raise ValueError(
                "corotational receipt differs from exact durable phase outcomes"
            )
        seen.update(pair)
        bound.append(row)
    return tuple(bound)


def build_rc_corotational_job_payload(
    request,
    receipts,
    execution_budget,
    terminal_checkpoint,
    api_result=None,
    complete=False,
):
    typed = _typed(request)
    if (
        type(complete) is not bool
        or type(receipts) not in (list, tuple)
        or not receipts
    ):
        raise ValueError(
            "corotational payload requires accepted receipts and explicit completion"
        )
    if (api_result is None) == complete:
        raise ValueError(
            "only final corotational result retains one cumulative API artifact"
        )
    if type(terminal_checkpoint) is not bytes or not terminal_checkpoint:
        raise ValueError("corotational terminal continuation must be immutable bytes")
    rows = [_mapping(row) for row in receipts]
    last = rows[-1]
    payload = {
        "schema_version": RC_COROTATIONAL_JOB_RESULT_SCHEMA_VERSION
        if complete
        else RC_COROTATIONAL_JOB_CHECKPOINT_SCHEMA_VERSION,
        "profile": RC_COROTATIONAL_JOB_PROFILE,
        "status": "ready" if complete else "checkpointed",
        "contract_pass": True,
        "request_hash": typed.request_hash,
        "resume_contract_hash": typed.resume_contract_hash,
        "case_id": typed.case_id,
        "source_revision": typed.source_revision,
        "source_revision_is_attestation": False,
        "progress_completed": last["actual_after"],
        "progress_total": typed.progress_total,
        "progress_unit": typed.progress_unit,
        "control_targets": list(typed.targets_m),
        "total_target_count": len(typed.targets_m),
        "completed_target_count": last["completed_target_count"],
        "receipts": rows,
        "execution_budget": dict(execution_budget),
        "execution_budget_unit": "reserved_api_invocations",
        "terminal_checkpoint_artifact_base64": base64.b64encode(
            terminal_checkpoint
        ).decode("ascii"),
        "authority": dict(RC_COROTATIONAL_JOB_AUTHORITY),
        "claim_boundary": RC_COROTATIONAL_JOB_CLAIM_BOUNDARY,
    }
    if complete:
        payload["api_result"] = _mapping(api_result, _MAX_API_BYTES)
    payload["result_hash" if complete else "checkpoint_hash"] = _hash(payload)
    return _validate_payload(payload, typed, execution_budget, complete)


def _validate_payload(payload, typed, execution_budget, complete):
    value = _mapping(payload)
    self_key = "result_hash" if complete else "checkpoint_hash"
    if set(value) != _PAYLOAD_KEYS | {self_key} | (
        {"api_result"} if complete else set()
    ):
        raise ValueError("invalid corotational durable wrapper fields")
    _self_hash(value, self_key)
    expected = {
        "schema_version": RC_COROTATIONAL_JOB_RESULT_SCHEMA_VERSION
        if complete
        else RC_COROTATIONAL_JOB_CHECKPOINT_SCHEMA_VERSION,
        "profile": RC_COROTATIONAL_JOB_PROFILE,
        "status": "ready" if complete else "checkpointed",
        "contract_pass": True,
        "request_hash": typed.request_hash,
        "resume_contract_hash": typed.resume_contract_hash,
        "case_id": typed.case_id,
        "source_revision": typed.source_revision,
        "source_revision_is_attestation": False,
        "progress_total": typed.progress_total,
        "progress_unit": typed.progress_unit,
        "control_targets": list(typed.targets_m),
        "total_target_count": len(typed.targets_m),
        "execution_budget_unit": "reserved_api_invocations",
        "authority": RC_COROTATIONAL_JOB_AUTHORITY,
        "claim_boundary": RC_COROTATIONAL_JOB_CLAIM_BOUNDARY,
    }
    if not _same({key: value[key] for key in expected}, expected):
        raise ValueError("corotational wrapper request/progress/authority mismatch")
    stored, current = (
        _budget(value["execution_budget"], typed),
        _budget(dict(execution_budget), typed),
    )
    if (complete and not _same(stored, current)) or current[
        "reserved_attempts"
    ] < stored["reserved_attempts"]:
        raise ValueError("corotational durable invocation budget was rewound")
    rows = value["receipts"]
    if type(rows) is not list or not 1 <= len(rows) <= typed.progress_total:
        raise ValueError("invalid corotational durable receipt count")
    actual = targets = prior_ordinal = 0
    restart_hash, source = None, None
    for row in rows:
        if actual >= typed.progress_total:
            raise ValueError(
                "corotational receipts exceed immutable control attempt cap"
            )
        previous_targets = targets
        actual, targets, prior_ordinal = _receipt(
            row, typed, actual, restart_hash, prior_ordinal, stored["reserved_attempts"]
        )
        if targets < previous_targets:
            raise ValueError("corotational completed target count was rewound")
        if source is not None and source != row["api_request"]["source_identity"]:
            raise ValueError("corotational receipt source identity changed")
        source = row["api_request"]["source_identity"]
        restart_hash = row["checkpoint_sha256"]
        if row is not rows[-1] and row["api_contract_pass"]:
            raise ValueError("corotational receipt followed completed path")
    if (
        type(value["progress_completed"]) is not int
        or value["progress_completed"] != actual
        or type(value["completed_target_count"]) is not int
        or value["completed_target_count"] != targets
    ):
        raise ValueError("corotational wrapper progress differs from accepted receipts")
    if complete and (
        not rows[-1]["api_contract_pass"] or targets != len(typed.targets_m)
    ):
        raise ValueError("corotational final result requires complete authored path")
    raw = _base64(value["terminal_checkpoint_artifact_base64"])
    first, accepted, pending, native_targets, spent, terminal = _native(
        raw, typed, rows[-1]["api_request"]
    )
    if (
        _sha(raw) != restart_hash
        or len(raw) != rows[-1]["checkpoint_byte_length"]
        or "sha256:" + accepted.state_hash.removeprefix("sha256:")
        != rows[-1]["checkpoint_state_hash"]
        or spent != actual
        or native_targets != targets
    ):
        raise ValueError(
            "corotational terminal continuation detached from receipt progress/state"
        )
    if (
        terminal
        or bool(pending) != (rows[-1]["api_status"] == "paused")
        or accepted.epoch < first.epoch
        or accepted.epoch > first.epoch + spent
    ):
        raise ValueError("corotational terminal continuation accepted path mismatch")
    if complete:
        api = value["api_result"]
        _api(
            api,
            typed,
            rows[-1]["completed_before"],
            rows[-1]["planned_after"],
            rows[-1]["restart_input_sha256"],
            raw,
        )
        if _sha(_api_bytes(api)) != rows[-1]["result_artifact_sha256"]:
            raise ValueError(
                "corotational cumulative API artifact differs from final receipt"
            )
    return value


def _preserve_prefix(value, checkpoint, typed, execution_budget):
    if checkpoint is None:
        return
    prior = _validate_payload(checkpoint, typed, execution_budget, False)
    if (
        prior["progress_completed"] > value["progress_completed"]
        or prior["execution_budget"]["reserved_attempts"]
        > value["execution_budget"]["reserved_attempts"]
        or not _same(prior["receipts"], value["receipts"][: len(prior["receipts"])])
    ):
        raise ValueError("corotational retained checkpoint prefix was rewritten")
    if (
        len(prior["receipts"]) == len(value["receipts"])
        and prior["terminal_checkpoint_artifact_base64"]
        != value["terminal_checkpoint_artifact_base64"]
    ):
        raise ValueError("corotational unchanged prefix replaced terminal continuation")


def _validation_report(value, complete):
    key = "result_hash" if complete else "checkpoint_hash"
    report = {
        "schema_version": "bounded-rc-corotational-job-validation-report.v1",
        "contract_pass": True,
        "request_hash": value["request_hash"],
        key: value[key],
        "resume_contract_hash": value["resume_contract_hash"],
        "progress_completed": value["progress_completed"],
        "progress_total": value["progress_total"],
        "progress_unit": value["progress_unit"],
        "completed_target_count": value["completed_target_count"],
        "execution_budget": value["execution_budget"],
        "execution_budget_unit": value["execution_budget_unit"],
        "terminal_checkpoint_sha256": value["receipts"][-1]["checkpoint_sha256"],
        "receipt_hashes": [row["receipt_hash"] for row in value["receipts"]],
        "authority": value["authority"],
        "claim_boundary": RC_COROTATIONAL_JOB_CLAIM_BOUNDARY,
    }
    if not complete:
        report["payload"] = value
    return report


def validate_rc_corotational_job_checkpoint(
    payload,
    request,
    progress_completed,
    resume_contract_hash,
    execution_budget,
    checkpoint=None,
):
    """Return compact validation report plus canonical payload under ``payload``."""
    typed = _typed(request)
    value = _validate_payload(payload, typed, execution_budget, False)
    if (
        type(progress_completed) is not int
        or progress_completed != value["progress_completed"]
        or resume_contract_hash != typed.resume_contract_hash
    ):
        raise ValueError(
            "corotational checkpoint differs from durable progress/resume contract"
        )
    _preserve_prefix(value, checkpoint, typed, execution_budget)
    return _validation_report(value, False)


def validate_rc_corotational_job_result(
    payload, request, execution_budget, checkpoint=None
):
    """Return a compact validation report without duplicating cumulative responses."""
    typed = _typed(request)
    value = _validate_payload(payload, typed, execution_budget, True)
    _preserve_prefix(value, checkpoint, typed, execution_budget)
    return _validation_report(value, True)
