"""Job-bound transport for the existing experimental Frame3D candidate API.

The wrapper retains each one-target API result unchanged. Its authored-target
cursor and durable reservation counters are orchestration facts, not additional
numerical authority or independently authenticated execution evidence.
"""

from __future__ import annotations

import base64
import binascii
from dataclasses import fields, replace
import hashlib
import json
import re
from typing import Any, Mapping

from structural_analysis.adapters.bounded_frame3d_direct_control_model_ir import (
    adapt_bounded_frame3d_direct_control_model_ir_v2,
)
from structural_analysis.api.frame3d_direct_control import (
    BOUNDED_FRAME3D_DIRECT_CONTROL_CHECKPOINT_MAX_BYTES,
    BoundedFrame3DDirectControlConfig,
    BoundedFrame3DDirectControlResult,
    _load_checkpoint_artifact,
    _mutable_json_copy,
    _validate_target_direction,
    validate_bounded_frame3d_direct_control_result,
)
from structural_analysis.assembly.stateful_corotational_frame3d_displacement_control import (
    STATEFUL_COROTATIONAL_FRAME3D_DISPLACEMENT_CONTROL_TARGET_CHAIN_SCHEMA_VERSION,
    _target_chain_genesis_hash,
)
from structural_analysis.api.frame3d_direct_control_request import (
    decode_bounded_frame3d_direct_control_request,
    strict_json_object_bytes,
)
from structural_analysis.assembly.stateful_corotational_frame3d_sparse import (
    initial_stateful_corotational_frame3d_sparse_checkpoint,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.model_ir import parse_model_ir_v2
from structural_analysis.model_ir.types import ModelIRDocument


FRAME3D_JOB_REQUEST_SCHEMA_VERSION = "structural-analysis-job-request.v2"
FRAME3D_JOB_CHECKPOINT_SCHEMA_VERSION = "bounded-frame3d-job-checkpoint.v1"
FRAME3D_JOB_RESULT_SCHEMA_VERSION = "bounded-frame3d-job-result.v1"
FRAME3D_JOB_VALIDATOR_ID = (
    "structural_analysis.execution.frame3d_job_contract.validate_frame3d_job_result"
)
FRAME3D_JOB_PROFILE = "bounded_frame3d_durable_authored_target_execution.v1"
FRAME3D_JOB_OPERATION = "bounded_frame3d_direct_control"
FRAME3D_JOB_MAX_BYTES = 128 * 1024 * 1024
FRAME3D_JOB_AUTHORITY = {
    "candidate_api_exposed": True,
    "capability_registry_public": False,
    "workbench_execution": False,
    "numerical_authority": "bounded_candidate",
    "recovery_authority": "node_and_support_candidate",
    "external_vv_level": 0,
    "independent_operator_attached": False,
    "design_authority": False,
    "formal_verification_level_2": False,
    "release_eligible": False,
}
FRAME3D_JOB_CLAIM_BOUNDARY = (
    "Durable authored-target progress and exact retained candidate API artifacts; "
    "per-target result requests remain local to their executed targets. Reserved "
    "attempts may include abandoned work and are not an exact completed-work count. "
    "Internal consistency is not independent execution authentication, full-history "
    "replay verification, public/Workbench/design authority, external validation, "
    "or source attestation."
)
_REVISION = re.compile(r"(?:[0-9a-f]{40}|sha256:[0-9a-f]{64})\Z")
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
_REQUEST_KEYS = {
    "schema_version",
    "operation",
    "case_id",
    "model",
    "config",
    "source_revision",
    "result_contract",
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
    "terminal_checkpoint_artifact_base64",
    "authority",
    "claim_boundary",
}
_RECEIPT_KEYS = {
    "receipt_hash",
    "target_index",
    "authored_target",
    "request_hash",
    "api_request_hash",
    "restart_checkpoint_sha256",
    "result_hash",
    "api_result",
    "checkpoint_artifact_base64",
    "checkpoint_sha256",
    "reserved_attempt_ordinals",
    "target_chain_proof",
}


def frame3d_job_canonical_bytes(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _mapping(payload: Mapping[str, Any] | bytes) -> dict[str, Any]:
    raw = payload if type(payload) is bytes else frame3d_job_canonical_bytes(payload)
    return strict_json_object_bytes(raw, maximum_bytes=FRAME3D_JOB_MAX_BYTES)


def _sha256(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def frame3d_job_request_hash(request: Mapping[str, Any]) -> str:
    return _sha256(frame3d_job_canonical_bytes(request))


def frame3d_job_resume_contract_hash(request: Mapping[str, Any]) -> str:
    return canonical_hash(
        {
            "profile": FRAME3D_JOB_PROFILE,
            "request_hash": frame3d_job_request_hash(request),
        }
    )


def validate_frame3d_job_request(
    request: Mapping[str, Any],
) -> tuple[ModelIRDocument, BoundedFrame3DDirectControlConfig]:
    payload = _mapping(request)
    if (
        set(payload) != _REQUEST_KEYS
        or payload["schema_version"] != FRAME3D_JOB_REQUEST_SCHEMA_VERSION
        or payload["operation"] != FRAME3D_JOB_OPERATION
        or payload["result_contract"] != FRAME3D_JOB_RESULT_SCHEMA_VERSION
        or type(payload["case_id"]) is not str
        or not _ID.fullmatch(payload["case_id"])
        or type(payload["source_revision"]) is not str
        or not _REVISION.fullmatch(payload["source_revision"])
        or type(payload["model"]) is not dict
        or type(payload["config"]) is not dict
    ):
        raise ValueError("invalid bounded Frame3D durable request")
    document = parse_model_ir_v2(payload["model"])
    config = decode_bounded_frame3d_direct_control_request(
        frame3d_job_canonical_bytes(payload["config"])
    )
    # Compile the actual source projection before leasing/executing a request;
    # this validates the candidate subset without requesting a nonlinear solve.
    adapter = adapt_bounded_frame3d_direct_control_model_ir_v2(document)
    if (
        adapter.global_dof(config.control_node_id, config.control_dof)
        not in adapter.model.free_dofs
    ):
        raise ValueError("bounded Frame3D job control coordinate must be free")
    _validate_target_direction(
        config.control_targets,
        accepted_coordinate=0.0,
        bound_direction=None,
        allow_direction_reversal=config.solver_config.allow_direction_reversal,
        maximum_direction_reversals=config.solver_config.maximum_direction_reversals,
        prior_cumulative_reversal_count=0,
    )
    return document, config


def _budget(payload: Any, maximum: int) -> dict[str, int]:
    if (
        type(payload) is not dict
        or set(payload)
        != {"maximum_attempts", "reserved_attempts", "remaining_attempts"}
        or any(type(value) is not int for value in payload.values())
        or payload["maximum_attempts"] != maximum
        or not 0 <= payload["reserved_attempts"] <= maximum
        or payload["remaining_attempts"] != maximum - payload["reserved_attempts"]
    ):
        raise ValueError("bounded Frame3D durable execution budget mismatch")
    return dict(payload)


def frame3d_job_checkpoint_artifact(payload: Mapping[str, Any]) -> bytes:
    encoded = payload.get("terminal_checkpoint_artifact_base64")
    return _decode_artifact(encoded)


def _decode_artifact(encoded: Any) -> bytes:
    if type(encoded) is not str or len(encoded) > 4 * (
        (BOUNDED_FRAME3D_DIRECT_CONTROL_CHECKPOINT_MAX_BYTES + 2) // 3
    ):
        raise ValueError("invalid bounded Frame3D checkpoint encoding or size")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as error:
        raise ValueError("invalid bounded Frame3D checkpoint base64") from error
    if (
        not raw
        or len(raw) > BOUNDED_FRAME3D_DIRECT_CONTROL_CHECKPOINT_MAX_BYTES
        or base64.b64encode(raw).decode("ascii") != encoded
    ):
        raise ValueError("noncanonical bounded Frame3D checkpoint base64")
    return raw


def build_frame3d_job_receipt(
    request: Mapping[str, Any],
    *,
    target_index: int,
    result: BoundedFrame3DDirectControlResult,
    restart_checkpoint: bytes | None,
    reserved_attempt_ordinals: list[int],
) -> dict[str, Any]:
    raw = result.checkpoint_artifact_bytes()
    payload = {
        "target_index": target_index,
        "authored_target": result.control["control_targets"][0],
        "request_hash": frame3d_job_request_hash(request),
        "api_request_hash": result.control["request_hash"],
        "restart_checkpoint_sha256": None
        if restart_checkpoint is None
        else _sha256(restart_checkpoint),
        "result_hash": result.result_hash,
        "api_result": result.to_dict(),
        "checkpoint_artifact_base64": base64.b64encode(raw).decode("ascii"),
        "checkpoint_sha256": _sha256(raw),
        "reserved_attempt_ordinals": list(reserved_attempt_ordinals),
        "target_chain_proof": (
            _mutable_json_copy(result._target_chain_proofs[0])
            if len(result._target_chain_proofs) == 1
            else None
        ),
    }
    payload["receipt_hash"] = canonical_hash(payload)
    return payload


def build_frame3d_job_payload(
    request: Mapping[str, Any],
    *,
    receipts: list[dict[str, Any]],
    execution_budget: Mapping[str, int],
    complete: bool,
) -> dict[str, Any]:
    _, config = validate_frame3d_job_request(request)
    payload = {
        "schema_version": FRAME3D_JOB_RESULT_SCHEMA_VERSION
        if complete
        else FRAME3D_JOB_CHECKPOINT_SCHEMA_VERSION,
        "profile": FRAME3D_JOB_PROFILE,
        "status": "ready" if complete else "checkpointed",
        "contract_pass": True,
        "request_hash": frame3d_job_request_hash(request),
        "resume_contract_hash": frame3d_job_resume_contract_hash(request),
        "case_id": request["case_id"],
        "source_revision": request["source_revision"],
        "source_revision_is_attestation": False,
        "control_targets": list(config.control_targets),
        "total_target_count": len(config.control_targets),
        "completed_target_count": len(receipts),
        "receipts": receipts,
        "execution_budget": dict(execution_budget),
        "terminal_checkpoint_artifact_base64": receipts[-1][
            "checkpoint_artifact_base64"
        ],
        "authority": dict(FRAME3D_JOB_AUTHORITY),
        "claim_boundary": FRAME3D_JOB_CLAIM_BOUNDARY,
    }
    payload["result_hash" if complete else "checkpoint_hash"] = canonical_hash(payload)
    return _mapping(payload)


def _validate_payload(
    payload: Mapping[str, Any] | bytes,
    *,
    request: Mapping[str, Any],
    complete: bool,
    execution_budget: Mapping[str, int] | None,
) -> dict[str, Any]:
    value = _mapping(payload)
    document, config = validate_frame3d_job_request(request)
    adapter = adapt_bounded_frame3d_direct_control_model_ir_v2(document)
    total = len(config.control_targets)
    hash_key = "result_hash" if complete else "checkpoint_hash"
    if set(value) != _COMMON_KEYS | {hash_key}:
        raise ValueError("bounded Frame3D job wrapper fields mismatch")
    unhashed = {key: item for key, item in value.items() if key != hash_key}
    expected = {
        "schema_version": FRAME3D_JOB_RESULT_SCHEMA_VERSION
        if complete
        else FRAME3D_JOB_CHECKPOINT_SCHEMA_VERSION,
        "profile": FRAME3D_JOB_PROFILE,
        "status": "ready" if complete else "checkpointed",
        "contract_pass": True,
        "request_hash": frame3d_job_request_hash(request),
        "resume_contract_hash": frame3d_job_resume_contract_hash(request),
        "case_id": request["case_id"],
        "source_revision": request["source_revision"],
        "source_revision_is_attestation": False,
        "control_targets": list(config.control_targets),
        "total_target_count": total,
        "authority": FRAME3D_JOB_AUTHORITY,
        "claim_boundary": FRAME3D_JOB_CLAIM_BOUNDARY,
    }
    if value[hash_key] != canonical_hash(unhashed) or canonical_hash(
        {key: value[key] for key in expected}
    ) != canonical_hash(expected):
        raise ValueError("bounded Frame3D job wrapper identity mismatch")
    completed = value["completed_target_count"]
    if (
        type(completed) is not int
        or not 1 <= completed <= total
        or (complete and completed != total)
        or (not complete and completed >= total)
        or type(value["receipts"]) is not list
        or len(value["receipts"]) != completed
    ):
        raise ValueError("bounded Frame3D authored-target progress mismatch")
    budget = _budget(
        value["execution_budget"], config.solver_config.maximum_path_solve_attempts
    )
    if execution_budget is not None:
        current = _budget(
            dict(execution_budget), config.solver_config.maximum_path_solve_attempts
        )
        if (complete and current != budget) or current["reserved_attempts"] < budget[
            "reserved_attempts"
        ]:
            raise ValueError("bounded Frame3D wrapper detached from durable budget")
    prior_raw = None
    prior_checkpoint = initial_stateful_corotational_frame3d_sparse_checkpoint(
        adapter.model,
        config=config.solver_config.frame_config,
    )
    previous_chain = _target_chain_genesis_hash(
        model=adapter.model,
        config=config.solver_config,
        control_global_dof=adapter.global_dof(
            config.control_node_id, config.control_dof
        ),
        checkpoint=prior_checkpoint,
    )
    last_ordinal = 0
    previous_direction = None
    reversal_count = 0
    previous_authored_target = 0.0
    result_keys = {
        field.name
        for field in fields(BoundedFrame3DDirectControlResult)
        if not field.name.startswith("_")
    }
    for index, receipt in enumerate(value["receipts"], start=1):
        if type(receipt) is not dict or set(receipt) != _RECEIPT_KEYS:
            raise ValueError("bounded Frame3D per-target receipt fields mismatch")
        unbound = {key: item for key, item in receipt.items() if key != "receipt_hash"}
        target = config.control_targets[index - 1]
        target_config = replace(config, control_targets=(target,))
        if (
            receipt["receipt_hash"] != canonical_hash(unbound)
            or type(receipt["target_index"]) is not int
            or receipt["target_index"] != index
            or canonical_hash(receipt["authored_target"]) != canonical_hash(target)
            or receipt["request_hash"] != value["request_hash"]
            or receipt["api_request_hash"] != target_config.request_hash
            or receipt["restart_checkpoint_sha256"]
            != (None if prior_raw is None else _sha256(prior_raw))
        ):
            raise ValueError(
                "bounded Frame3D per-target request/restart binding mismatch"
            )
        raw = _decode_artifact(receipt["checkpoint_artifact_base64"])
        if receipt["checkpoint_sha256"] != _sha256(raw):
            raise ValueError("bounded Frame3D checkpoint bytes/hash mismatch")
        result_payload = receipt["api_result"]
        if type(result_payload) is not dict or set(result_payload) != result_keys:
            raise ValueError("bounded Frame3D raw API result fields mismatch")
        result = BoundedFrame3DDirectControlResult(
            **result_payload, _checkpoint_artifact_bytes=raw
        )
        validate_bounded_frame3d_direct_control_result(result)
        expected_control = {
            **target_config.to_dict(),
            "request_hash": target_config.request_hash,
            "control_global_dof": adapter.global_dof(
                config.control_node_id, config.control_dof
            ),
        }
        expected_source = {
            "model_ir_content_hash": document.content_hash,
            "model_ir_semantic_hash": document.semantic_hash,
            "model_ir_provenance_hash": document.provenance_hash,
            "adapter_hash": adapter.adapter_hash,
            "adapter_profile": adapter.adapter_profile,
            "load_pattern_id": adapter.load_pattern_id,
            "entity_mapping_hash": adapter.entity_mapping_hash,
            "node_ids": list(adapter.node_ids),
            "member_ids": list(adapter.member_ids),
            "member_material_ids": [
                material.material_id for material in adapter.model.axial_materials
            ],
        }
        expected_source["recovery_identity_hash"] = canonical_hash(
            {
                key: expected_source[key]
                for key in (
                    "entity_mapping_hash",
                    "node_ids",
                    "member_ids",
                    "member_material_ids",
                )
            }
        )
        if (
            result.status != "ready"
            or result.contract_pass is not True
            or receipt["result_hash"] != result.result_hash
            or result.model_hash != adapter.model_hash
            or canonical_hash(result_payload["control"])
            != canonical_hash(expected_control)
            or canonical_hash(result_payload["source_binding"])
            != canonical_hash(expected_source)
            or canonical_hash(result_payload["authority"])
            != canonical_hash(FRAME3D_JOB_AUTHORITY)
            or result.metrics["requested_target_count"] != 1
            or result.metrics["completed_requested_target_count"] != 1
        ):
            raise ValueError(
                "bounded Frame3D raw API result detached from actual target/source"
            )
        checkpoint, binding = _load_checkpoint_artifact(
            raw,
            adapter=adapter,
            config=target_config,
            control_global_dof=expected_control["control_global_dof"],
        )
        accepted = result.metrics["accepted_checkpoint_count"]
        if (
            type(accepted) is not int
            or accepted < 1
            or checkpoint.step_index != prior_checkpoint.step_index + accepted
            or (
                accepted == 1
                and checkpoint.parent_checkpoint_hash
                != prior_checkpoint.checkpoint_hash
            )
        ):
            raise ValueError(
                "bounded Frame3D accepted-step/checkpoint linkage mismatch"
            )
        ordinals = receipt["reserved_attempt_ordinals"]
        attempt_count = result.metrics["solve_attempt_count"]
        if (
            type(ordinals) is not list
            or not ordinals
            or type(attempt_count) is not int
            or attempt_count != len(ordinals)
            or accepted > attempt_count
        ):
            raise ValueError("bounded Frame3D solve attempts lack durable reservations")
        for ordinal in ordinals:
            if (
                type(ordinal) is not int
                or not last_ordinal < ordinal <= budget["reserved_attempts"]
            ):
                raise ValueError(
                    "bounded Frame3D reservation ordinals must increase within budget"
                )
            last_ordinal = ordinal
        direction = 1 if target > previous_authored_target else -1
        reversal = previous_direction is not None and direction != previous_direction
        reversal_count += int(reversal)
        if config.solver_config.allow_direction_reversal:
            proof = receipt["target_chain_proof"]
            if type(proof) is not dict or set(proof) != {"preimage", "cutback_history"}:
                raise ValueError("bounded Frame3D cyclic target-chain preimage missing")
            preimage, cutbacks = proof["preimage"], proof["cutback_history"]
            hashes = (
                preimage.get("accepted_step_hashes") if type(preimage) is dict else None
            )
            if (
                type(hashes) is not list
                or len(hashes) != accepted
                or any(
                    type(item) is not str
                    or re.fullmatch(r"sha256:[0-9a-f]{64}", item) is None
                    for item in hashes
                )
                or len(set(hashes)) != len(hashes)
                or type(cutbacks) is not list
                or type(result.metrics["target_cutback_attempt_count"]) is not int
                or len(cutbacks) != result.metrics["target_cutback_attempt_count"]
                or any(
                    type(row) is not dict
                    or row.get("cumulative_target_index") != index
                    or row.get("leg_direction_sign") != direction
                    or row.get("reversal_from_previous_leg") is not reversal
                    or row.get("parent_state_immutable") is not True
                    or row.get("requested_target_control_coordinate") != target
                    for row in cutbacks
                )
            ):
                raise ValueError(
                    "bounded Frame3D cyclic preimage steps/cutbacks mismatch"
                )
            expected_preimage = {
                "schema_version": STATEFUL_COROTATIONAL_FRAME3D_DISPLACEMENT_CONTROL_TARGET_CHAIN_SCHEMA_VERSION,
                "entry_kind": "completed_authored_target",
                "previous_chain_hash": previous_chain,
                "cumulative_target_index": index,
                "authored_target": target,
                "leg_direction_sign": direction,
                "reversal_from_previous_leg": reversal,
                "requested_boundary_checkpoint_hash": checkpoint.checkpoint_hash,
                "accepted_step_hashes": hashes,
                "cutback_history_hash": canonical_hash(cutbacks),
            }
            if canonical_hash(preimage) != canonical_hash(expected_preimage):
                raise ValueError(
                    "bounded Frame3D target-chain preimage detached from its prefix"
                )
            previous_chain = canonical_hash(expected_preimage)
            if (
                getattr(binding, "cumulative_completed_target_count", None) != index
                or getattr(binding, "cumulative_reversal_count", None) != reversal_count
                or getattr(binding, "last_completed_leg_direction_sign", None)
                != direction
                or getattr(binding, "accepted_target_chain_hash", None)
                != result.metrics["accepted_target_chain_hash"]
                or getattr(binding, "accepted_target_chain_hash", None)
                != previous_chain
                or result.metrics["cumulative_completed_target_count"] != index
                or result.metrics["cumulative_direction_reversal_count"]
                != reversal_count
            ):
                raise ValueError(
                    "bounded Frame3D cyclic authored cursor/chain mismatch"
                )
        elif receipt["target_chain_proof"] is not None:
            raise ValueError("monotonic Frame3D receipt must not claim a cyclic proof")
        prior_raw, prior_checkpoint = raw, checkpoint
        previous_authored_target, previous_direction = target, direction
    if (
        value["terminal_checkpoint_artifact_base64"]
        != value["receipts"][-1]["checkpoint_artifact_base64"]
    ):
        raise ValueError("bounded Frame3D terminal artifact detached from receipt tail")
    return value


def validate_frame3d_job_checkpoint(
    payload: Mapping[str, Any] | bytes,
    *,
    request: Mapping[str, Any],
    progress_completed: int | None = None,
    execution_budget: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    value = _validate_payload(
        payload, request=request, complete=False, execution_budget=execution_budget
    )
    if progress_completed is not None and (
        type(progress_completed) is not int
        or value["completed_target_count"] != progress_completed
    ):
        raise ValueError(
            "bounded Frame3D checkpoint cursor differs from durable progress"
        )
    return value


def validate_frame3d_job_result(
    payload: Mapping[str, Any] | bytes,
    *,
    request: Mapping[str, Any],
    execution_budget: Mapping[str, int] | None = None,
    checkpoint: Mapping[str, Any] | bytes | None = None,
) -> dict[str, Any]:
    value = _validate_payload(
        payload, request=request, complete=True, execution_budget=execution_budget
    )
    if checkpoint is not None:
        prefix = validate_frame3d_job_checkpoint(
            checkpoint, request=request, execution_budget=execution_budget
        )
        if canonical_hash(prefix["receipts"]) != canonical_hash(
            value["receipts"][: prefix["completed_target_count"]]
        ):
            raise ValueError(
                "bounded Frame3D result changed its durable receipt prefix"
            )
    return {
        "schema_version": "bounded-frame3d-job-validation-report.v1",
        "contract_pass": True,
        "request_hash": value["request_hash"],
        "result_hash": value["result_hash"],
        "completed_target_count": value["completed_target_count"],
        "total_target_count": value["total_target_count"],
        "execution_budget": value["execution_budget"],
        "terminal_checkpoint_sha256": value["receipts"][-1]["checkpoint_sha256"],
        "receipt_hashes": [row["receipt_hash"] for row in value["receipts"]],
        "authority": value["authority"],
        "claim_boundary": FRAME3D_JOB_CLAIM_BOUNDARY,
    }
