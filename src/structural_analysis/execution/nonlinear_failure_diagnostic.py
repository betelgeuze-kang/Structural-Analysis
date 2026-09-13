"""Attempt-bound diagnostic transport; no publication or numerical authority.

The caller must derive the expected binding from its authorized job claim and
validated request, never from an incoming diagnostic. Persistence and lease
validation remain responsibilities of the job service.
"""

from __future__ import annotations

import base64
import binascii
from dataclasses import asdict, dataclass
import hashlib
import json
import re
from typing import Any

from structural_analysis.api.frame3d_direct_control_request import (
    strict_json_object_bytes,
)
from structural_analysis.api.nonlinear_frame import (
    _blocked_authority,
    validate_nonlinear_frame_manifest,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash

SCHEMA = "nonlinear-frame-failure-diagnostic.v1"
MAX_RESULT_BYTES = 8 * 1024 * 1024
MAX_DIAGNOSTIC_BYTES = 12 * 1024 * 1024
_HASH = re.compile(r"sha256:[0-9a-f]{64}")


@dataclass(frozen=True)
class NonlinearFailureBinding:
    job_id: str
    request_hash: str
    attempt: int
    source_revision: str
    input_checksum: str
    configuration_hash: str

    def __post_init__(self) -> None:
        if type(self.job_id) is not str or not re.fullmatch(
            r"job_[0-9a-f]{32}", self.job_id
        ):
            raise ValueError("invalid diagnostic job binding")
        if type(self.attempt) is not int or self.attempt < 1:
            raise ValueError("invalid diagnostic attempt binding")
        if type(self.source_revision) is not str or not re.fullmatch(
            r"[0-9a-f]{40}", self.source_revision
        ):
            raise ValueError("invalid diagnostic source binding")
        for value in (self.request_hash, self.input_checksum, self.configuration_hash):
            if type(value) is not str or _HASH.fullmatch(value) is None:
                raise ValueError("invalid diagnostic hash binding")


def _sha(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _count(value: Any) -> int:
    if type(value) is not int or value < 0:
        raise ValueError("diagnostic count must be a nonnegative exact integer")
    return value


def _observed_path(source: dict[str, Any]) -> None:
    observed = source["metrics"].get("observed_load_path")
    if observed is None:
        return  # Unavailable execution is not zero work.
    keys = {
        "scope",
        "total_api_work_accounted",
        "attempted_step_count",
        "committed_step_count",
        "replayed_prefix_step_count",
        "newly_attempted_step_count",
        "convergence_history_row_count",
        "steps",
    }
    if type(observed) is not dict or set(observed) != keys:
        raise ValueError("invalid observed path fields")
    if (
        observed["scope"] != "returned_load_path_including_replayed_prefix"
        or observed["total_api_work_accounted"] is not False
    ):
        raise ValueError("invalid observed path scope")
    attempted, committed, prefix, new, history = (
        _count(observed[key])
        for key in (
            "attempted_step_count",
            "committed_step_count",
            "replayed_prefix_step_count",
            "newly_attempted_step_count",
            "convergence_history_row_count",
        )
    )
    steps = observed["steps"]
    targets = source["configuration"].get("target_load_factors")
    if type(targets) is not list or not 2 <= len(targets) <= 64:
        raise ValueError("observed path requires configured targets")
    if (
        type(steps) is not list
        or len(steps) != attempted
        or attempted > len(targets)
        or prefix + new != attempted
        or prefix > committed
    ):
        raise ValueError("inconsistent observed path counts")
    step_keys = {
        "target_load_factor",
        "committed",
        "terminal_reason",
        "convergence_history_row_count",
        "failed_step_rollback_exact",
    }
    actual_committed = actual_history = 0
    for index, step in enumerate(steps):
        if type(step) is not dict or set(step) != step_keys:
            raise ValueError("invalid observed step fields")
        target = step["target_load_factor"]
        if type(target) not in (int, float) or target != targets[index]:
            raise ValueError("observed target differs from configured path")
        if type(step["committed"]) is not bool:
            raise ValueError("invalid observed commit disposition")
        reason = step["terminal_reason"]
        if reason is not None and (
            type(reason) is not str or not reason or len(reason) > 512
        ):
            raise ValueError("invalid observed terminal reason")
        actual_history += _count(step["convergence_history_row_count"])
        if step["committed"]:
            actual_committed += 1
            if step["failed_step_rollback_exact"] is not None:
                raise ValueError("committed step cannot claim failed rollback")
        elif (
            index != len(steps) - 1
            or type(step["failed_step_rollback_exact"]) is not bool
        ):
            raise ValueError("invalid failed step disposition")
    if actual_committed != committed or actual_history != history:
        raise ValueError("observed path totals differ from step records")
    if prefix and source["configuration"].get("restart_supplied") is not True:
        raise ValueError("observed replay requires a restart")


def _validate_source(raw: bytes, binding: NonlinearFailureBinding) -> dict[str, Any]:
    source = validate_nonlinear_frame_manifest(
        strict_json_object_bytes(raw, maximum_bytes=MAX_RESULT_BYTES)
    )
    if (
        source["status"] != "blocked"
        or source["contract_pass"] is not False
        or source["profile"]
        not in ("corotational_one_bay_portal.v1", "corotational_connected_frame2d.v1")
    ):
        raise ValueError("diagnostic requires a blocked corotational result")
    if (
        source["input_checksum"] != binding.input_checksum
        or canonical_hash(source["configuration"]) != binding.configuration_hash
    ):
        raise ValueError("diagnostic result differs from expected input/configuration")
    if (
        source["checkpoint"] != {"available": False}
        or source["engineering_result_ir"] is not None
        or source["source_result_hash"] is not None
        or source["authority"] != dict(_blocked_authority())
    ):
        raise ValueError("failure diagnostic cannot expose accepted result authority")
    for field in (
        "node_displacements",
        "support_reactions",
        "member_end_forces",
        "section_results",
        "fiber_results",
        "convergence_history",
    ):
        if source[field] != []:
            raise ValueError("failure diagnostic cannot expose accepted numerical rows")
    _observed_path(source)
    return source


def build_nonlinear_failure_diagnostic(
    result_bytes: bytes,
    *,
    binding: NonlinearFailureBinding,
) -> bytes:
    """Preserve exact source bytes; this does not transition or publish a job."""
    if type(binding) is not NonlinearFailureBinding:
        raise ValueError("expected a validated diagnostic binding")
    source = _validate_source(result_bytes, binding)
    payload = {
        "schema_version": SCHEMA,
        "binding": asdict(binding),
        "result_bytes_base64": base64.b64encode(result_bytes).decode("ascii"),
        "result_artifact_hash": _sha(result_bytes),
        "result_byte_length": len(result_bytes),
        "source_result_hash": source["result_hash"],
        "authority": "diagnostic_only_no_numerical_design_or_release_authority",
    }
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


def validate_nonlinear_failure_diagnostic(
    diagnostic_bytes: bytes,
    *,
    expected_binding: NonlinearFailureBinding,
) -> bytes:
    """Return validated original result bytes; caller owns authorization and lease."""
    if type(expected_binding) is not NonlinearFailureBinding:
        raise ValueError("expected a validated diagnostic binding")
    payload = strict_json_object_bytes(
        diagnostic_bytes, maximum_bytes=MAX_DIAGNOSTIC_BYTES
    )
    if set(payload) != {
        "schema_version",
        "binding",
        "result_bytes_base64",
        "result_artifact_hash",
        "result_byte_length",
        "source_result_hash",
        "authority",
    }:
        raise ValueError("invalid diagnostic fields")
    if (
        payload["schema_version"] != SCHEMA
        or payload["binding"] != asdict(expected_binding)
        or type(payload["binding"]) is not dict
        or type(payload["binding"].get("attempt")) is not int
    ):
        raise ValueError("diagnostic binding mismatch")
    if type(payload["result_bytes_base64"]) is not str:
        raise ValueError("diagnostic source encoding invalid")
    try:
        raw = base64.b64decode(payload["result_bytes_base64"], validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("diagnostic source encoding invalid") from exc
    # Rebuilding also checks every scalar identity, exact type and authority value.
    expected = strict_json_object_bytes(
        build_nonlinear_failure_diagnostic(raw, binding=expected_binding),
        maximum_bytes=MAX_DIAGNOSTIC_BYTES,
    )
    if type(payload["result_byte_length"]) is not int or payload != expected:
        raise ValueError("diagnostic source identity or authority mismatch")
    return raw
