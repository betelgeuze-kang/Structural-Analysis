"""Exact persisted validation receipt for bounded Frame3D durable results."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from importlib import resources
import json
from typing import Any, Literal, Mapping, NoReturn

from jsonschema import Draft202012Validator, validators

from structural_analysis.adapters.bounded_frame3d_load_control_model_ir import (
    BOUNDED_FRAME3D_LOAD_CONTROL_MODEL_IR_ADAPTER_PROFILE,
)
from structural_analysis.api.frame3d_load_control import (
    BOUNDED_FRAME3D_LOAD_CONTROL_API_PROFILE,
    BOUNDED_FRAME3D_LOAD_CONTROL_RESULT_SCHEMA_VERSION,
    BoundedFrame3DLoadControlConfig,
    BoundedFrame3DLoadControlResult,
    bounded_frame3d_load_control_resume_contract_hash,
    validate_bounded_frame3d_load_control_result_manifest,
)
from structural_analysis.assembly.corotational_frame3d_global import (
    COROTATIONAL_FRAME3D_GLOBAL_PROFILE,
)
from structural_analysis.engine_v2.contracts._canonical import (
    canonical_hash,
    canonical_json_bytes,
)
from structural_analysis.model_ir.types import ModelIRDocument


FRAME3D_LOAD_CONTROL_VALIDATION_REPORT_SCHEMA_VERSION = (
    "bounded-frame3d-load-control-validation-report.v1"
)
FRAME3D_LOAD_CONTROL_VALIDATION_REPORT_SCHEMA_PATH = (
    "bounded_frame3d_load_control_validation_report_v1.schema.json"
)
FRAME3D_LOAD_CONTROL_VALIDATOR_ID = (
    "structural_analysis.api.frame3d_load_control."
    "validate_bounded_frame3d_load_control_result_manifest"
)
FRAME3D_LOAD_CONTROL_BACKEND_ROLE = "cpu_reference"

_STRICT_JSON_TYPE_CHECKER = Draft202012Validator.TYPE_CHECKER.redefine(
    "integer", lambda _checker, value: type(value) is int
).redefine("number", lambda _checker, value: type(value) in (int, float))
_StrictDraft202012Validator = validators.extend(
    Draft202012Validator,
    type_checker=_STRICT_JSON_TYPE_CHECKER,
)


class Frame3DLoadControlValidationError(ValueError):
    """Stable fail-closed validation-report error."""

    def __init__(self, code: str, path: str, detail: str) -> None:
        self.code = code
        self.path = path
        self.detail = detail
        super().__init__(f"{code}@{path}: {detail}")


@dataclass(frozen=True)
class Frame3DLoadControlValidationReport:
    schema_version: str
    status: Literal["ready"]
    contract_pass: bool
    result_schema_version: str
    profile: str
    source_adapter_profile: str
    solver_profile: str
    backend_role: str
    validator_id: str
    result_hash: str
    result_artifact_sha256: str
    job_request_artifact_sha256: str
    model_ir_content_hash: str
    model_ir_semantic_hash: str
    model_ir_provenance_hash: str
    adapter_hash: str
    compiled_model_hash: str
    api_request_hash: str
    resume_contract_hash: str
    source_solver_receipt_hash: str
    numerical_result_ir_hash: str
    resume_checkpoint_artifact_sha256: str | None
    terminal_checkpoint_hash: str
    terminal_checkpoint_artifact_hash: str
    terminal_checkpoint_artifact_sha256: str
    recovery_hash: str
    full_node_equilibrium_hash: str
    equilibrium_scaling_hash: str
    final_load_factor: float
    total_load_factor_count: int
    resume_completed_prefix_count: int
    accepted_suffix_step_count: int
    completed_prefix_count: int
    remaining_load_factor_count: int
    terminal_checkpoint_embedded: bool
    exact_result_manifest_replay: bool
    exact_source_solver_replay: bool
    exact_resume_checkpoint_binding: bool
    exact_terminal_checkpoint_replay: bool
    exact_numerical_result_ir_replay: bool
    exact_recovery_replay: bool
    residual_gate_pass: bool
    increment_gate_pass: bool
    line_search_pass: bool
    terminal_reassembled_equilibrium_pass: bool
    full_node_equilibrium_pass: bool
    unsupported_feature_count: int
    fallback_count: int
    regularization_count: int
    external_vv_level: int
    workbench_execution: bool
    public_product_promotion: bool
    release_eligible: bool
    claim_boundary: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "contract_pass": self.contract_pass,
            "result_schema_version": self.result_schema_version,
            "profile": self.profile,
            "source_adapter_profile": self.source_adapter_profile,
            "solver_profile": self.solver_profile,
            "backend_role": self.backend_role,
            "validator_id": self.validator_id,
            "result_hash": self.result_hash,
            "result_artifact_sha256": self.result_artifact_sha256,
            "job_request_artifact_sha256": self.job_request_artifact_sha256,
            "model_ir_content_hash": self.model_ir_content_hash,
            "model_ir_semantic_hash": self.model_ir_semantic_hash,
            "model_ir_provenance_hash": self.model_ir_provenance_hash,
            "adapter_hash": self.adapter_hash,
            "compiled_model_hash": self.compiled_model_hash,
            "api_request_hash": self.api_request_hash,
            "resume_contract_hash": self.resume_contract_hash,
            "source_solver_receipt_hash": self.source_solver_receipt_hash,
            "numerical_result_ir_hash": self.numerical_result_ir_hash,
            "resume_checkpoint_artifact_sha256": (
                self.resume_checkpoint_artifact_sha256
            ),
            "terminal_checkpoint_hash": self.terminal_checkpoint_hash,
            "terminal_checkpoint_artifact_hash": (
                self.terminal_checkpoint_artifact_hash
            ),
            "terminal_checkpoint_artifact_sha256": (
                self.terminal_checkpoint_artifact_sha256
            ),
            "recovery_hash": self.recovery_hash,
            "full_node_equilibrium_hash": self.full_node_equilibrium_hash,
            "equilibrium_scaling_hash": self.equilibrium_scaling_hash,
            "final_load_factor": self.final_load_factor,
            "total_load_factor_count": self.total_load_factor_count,
            "resume_completed_prefix_count": self.resume_completed_prefix_count,
            "accepted_suffix_step_count": self.accepted_suffix_step_count,
            "completed_prefix_count": self.completed_prefix_count,
            "remaining_load_factor_count": self.remaining_load_factor_count,
            "terminal_checkpoint_embedded": self.terminal_checkpoint_embedded,
            "exact_result_manifest_replay": self.exact_result_manifest_replay,
            "exact_source_solver_replay": self.exact_source_solver_replay,
            "exact_resume_checkpoint_binding": (
                self.exact_resume_checkpoint_binding
            ),
            "exact_terminal_checkpoint_replay": (
                self.exact_terminal_checkpoint_replay
            ),
            "exact_numerical_result_ir_replay": (
                self.exact_numerical_result_ir_replay
            ),
            "exact_recovery_replay": self.exact_recovery_replay,
            "residual_gate_pass": self.residual_gate_pass,
            "increment_gate_pass": self.increment_gate_pass,
            "line_search_pass": self.line_search_pass,
            "terminal_reassembled_equilibrium_pass": (
                self.terminal_reassembled_equilibrium_pass
            ),
            "full_node_equilibrium_pass": self.full_node_equilibrium_pass,
            "unsupported_feature_count": self.unsupported_feature_count,
            "fallback_count": self.fallback_count,
            "regularization_count": self.regularization_count,
            "external_vv_level": self.external_vv_level,
            "workbench_execution": self.workbench_execution,
            "public_product_promotion": self.public_product_promotion,
            "release_eligible": self.release_eligible,
            "claim_boundary": self.claim_boundary,
        }


def build_frame3d_load_control_validation_report(
    *,
    result: BoundedFrame3DLoadControlResult,
    result_bytes: bytes | bytearray | memoryview,
    document: ModelIRDocument,
    config: BoundedFrame3DLoadControlConfig,
    checkpoint_artifact_bytes: bytes | bytearray | memoryview,
    job_request_artifact_bytes: bytes | bytearray | memoryview,
    resume_checkpoint_artifact_bytes: bytes | bytearray | memoryview | None,
    resume_completed_prefix_count: int,
    validator_id: str,
) -> Frame3DLoadControlValidationReport:
    """Replay exact persisted bytes and bind every candidate authority boundary."""

    if type(result) is not BoundedFrame3DLoadControlResult:
        _fail("validation_result_type_invalid", "/result", "Exact result required.")
    if type(document) is not ModelIRDocument:
        _fail("validation_document_type_invalid", "/model", "Exact ModelIR required.")
    if type(config) is not BoundedFrame3DLoadControlConfig:
        _fail("validation_config_type_invalid", "/config", "Exact config required.")
    if validator_id != FRAME3D_LOAD_CONTROL_VALIDATOR_ID:
        _fail(
            "validation_validator_identity_mismatch",
            "/validator_id",
            "The persisted validator identity is not allowlisted.",
        )
    persisted_result_bytes = _bytes(result_bytes, "/result")
    persisted_job_request_bytes = _bytes(
        job_request_artifact_bytes,
        "/job_request_artifact",
    )
    persisted_checkpoint_bytes = _bytes(
        checkpoint_artifact_bytes,
        "/checkpoint_artifact",
    )
    persisted_resume_checkpoint_bytes = (
        None
        if resume_checkpoint_artifact_bytes is None
        else _bytes(
            resume_checkpoint_artifact_bytes,
            "/resume_checkpoint_artifact",
        )
    )
    resume_checkpoint_artifact_sha256 = (
        _sha256(persisted_resume_checkpoint_bytes)
        if persisted_resume_checkpoint_bytes is not None
        else None
    )
    if (
        type(resume_completed_prefix_count) is not int
        or not 0 <= resume_completed_prefix_count < len(config.load_factors)
    ):
        _fail(
            "validation_resume_progress_invalid",
            "/resume_completed_prefix_count",
            "Resume prefix progress must be an integer before terminal completion.",
        )
    replayed = validate_bounded_frame3d_load_control_result_manifest(
        persisted_result_bytes,
        document=document,
        config=config,
        checkpoint_artifact_bytes=persisted_checkpoint_bytes,
    )
    if (
        persisted_result_bytes != result.manifest_bytes()
        or replayed.to_dict() != result.to_dict()
    ):
        _fail(
            "validation_result_replay_mismatch",
            "/result",
            "Persisted result bytes differ from the in-memory validated result.",
        )
    if persisted_checkpoint_bytes != result.checkpoint_artifact_bytes():
        _fail(
            "validation_checkpoint_replay_mismatch",
            "/checkpoint_artifact",
            "Persisted checkpoint bytes differ from the terminal result binding.",
        )

    source_binding = result.source_binding
    source_receipt = result.solver["source_receipt"]
    execution = result.solver["execution"]
    equilibrium_summary = result.solver["full_node_equilibrium"]
    numerical_result_ir = result.numerical_result_ir
    checkpoint_artifact = result.checkpoint_artifact
    terminal_checkpoint = checkpoint_artifact["checkpoint"]
    metrics = result.metrics
    authority = result.authority
    expected_resume_contract_hash = (
        bounded_frame3d_load_control_resume_contract_hash(document, config)
    )
    unsupported_features = document.to_dict()["unsupported_features"]
    start_checkpoint = execution["start_checkpoint"]
    accepted_steps = source_receipt["steps"]

    if (
        result.schema_version != BOUNDED_FRAME3D_LOAD_CONTROL_RESULT_SCHEMA_VERSION
        or result.profile != BOUNDED_FRAME3D_LOAD_CONTROL_API_PROFILE
        or source_binding["adapter_profile"]
        != BOUNDED_FRAME3D_LOAD_CONTROL_MODEL_IR_ADAPTER_PROFILE
        or source_receipt["profile"] != COROTATIONAL_FRAME3D_GLOBAL_PROFILE
        or numerical_result_ir["backend"]["role"]
        != FRAME3D_LOAD_CONTROL_BACKEND_ROLE
    ):
        _fail(
            "validation_execution_identity_mismatch",
            "/",
            "Result execution identities are not the exact allowlisted tuple.",
        )
    if (
        source_binding["model_ir_content_hash"] != document.content_hash
        or source_binding["model_ir_semantic_hash"] != document.semantic_hash
        or source_binding["model_ir_provenance_hash"] != document.provenance_hash
        or source_binding["request_hash"] != config.request_hash
        or source_binding["model_hash"] != source_receipt["model_hash"]
        or checkpoint_artifact["resume_contract_hash"]
        != expected_resume_contract_hash
    ):
        _fail(
            "validation_source_binding_mismatch",
            "/source_binding",
            "Model, API request, or resume-contract binding drifted.",
        )
    if (
        type(accepted_steps) is not tuple
        or type(metrics["accepted_step_count"]) is not int
        or metrics["accepted_step_count"] != len(accepted_steps)
        or metrics["accepted_step_count"]
        != len(config.load_factors) - resume_completed_prefix_count
        or source_receipt["start_checkpoint_hash"]
        != start_checkpoint["checkpoint_hash"]
        or terminal_checkpoint["load_factor"] != config.load_factors[-1]
    ):
        _fail(
            "validation_suffix_lineage_mismatch",
            "/solver",
            "Accepted suffix, start checkpoint, or terminal factor drifted.",
        )
    if persisted_resume_checkpoint_bytes is None:
        if (
            resume_completed_prefix_count != 0
            or start_checkpoint["load_factor"] != 0.0
        ):
            _fail(
                "validation_initial_checkpoint_binding_mismatch",
                "/solver/execution/start_checkpoint",
                "An uninterrupted result must begin at the exact initial state.",
            )
    else:
        resume_checkpoint = _parse_canonical_json_object(
            persisted_resume_checkpoint_bytes,
            "/resume_checkpoint_artifact",
        )
        resume_checkpoint_logical_payload = dict(resume_checkpoint)
        resume_checkpoint_logical_payload.pop("artifact_hash", None)
        if resume_completed_prefix_count <= 0:
            _fail(
                "validation_resume_checkpoint_progress_mismatch",
                "/resume_completed_prefix_count",
                "A persisted resume checkpoint requires positive prefix progress.",
            )
        expected_resume_factor = config.load_factors[
            resume_completed_prefix_count - 1
        ]
        if (
            resume_checkpoint.get("artifact_hash")
            != canonical_hash(resume_checkpoint_logical_payload)
            or canonical_json_bytes(resume_checkpoint.get("checkpoint"))
            != canonical_json_bytes(start_checkpoint)
            or resume_checkpoint.get("model_ir_content_hash")
            != document.content_hash
            or resume_checkpoint.get("adapter_hash") != source_binding["adapter_hash"]
            or resume_checkpoint.get("request_hash") != config.request_hash
            or resume_checkpoint.get("resume_contract_hash")
            != expected_resume_contract_hash
            or resume_checkpoint.get("public_product_promotion") is not False
            or resume_checkpoint.get("release_eligible") is not False
            or start_checkpoint["load_factor"] != expected_resume_factor
            or accepted_steps[0]["checkpoint"]["parent_checkpoint_hash"]
            != start_checkpoint["checkpoint_hash"]
        ):
            _fail(
                "validation_resume_checkpoint_binding_mismatch",
                "/resume_checkpoint_artifact",
                "Prior durable checkpoint does not bind the replayed suffix start.",
            )
    if (
        type(metrics["completed_prefix_count"]) is not int
        or metrics["completed_prefix_count"] != len(config.load_factors)
        or metrics["remaining_load_factor_count"] != 0
        or metrics["final_load_factor"] != config.load_factors[-1]
        or metrics["fallback_count"] != 0
        or metrics["regularization_count"] != 0
    ):
        _fail(
            "validation_terminal_progress_mismatch",
            "/metrics",
            "Only a complete zero-fallback terminal schedule may be published.",
        )
    if (
        equilibrium_summary["contract_pass"] is not True
        or authority["external_vv_level"] != 0
        or authority["workbench_execution"] is not False
        or authority["public_product_promotion"] is not False
        or authority["release_eligible"] is not False
        or type(unsupported_features) is not list
        or unsupported_features
    ):
        _fail(
            "validation_authority_boundary_mismatch",
            "/authority",
            "Equilibrium or candidate authority boundary is not exact.",
        )

    report = Frame3DLoadControlValidationReport(
        schema_version=FRAME3D_LOAD_CONTROL_VALIDATION_REPORT_SCHEMA_VERSION,
        status="ready",
        contract_pass=True,
        result_schema_version=result.schema_version,
        profile=result.profile,
        source_adapter_profile=source_binding["adapter_profile"],
        solver_profile=source_receipt["profile"],
        backend_role=numerical_result_ir["backend"]["role"],
        validator_id=validator_id,
        result_hash=result.result_hash,
        result_artifact_sha256=_sha256(persisted_result_bytes),
        job_request_artifact_sha256=_sha256(persisted_job_request_bytes),
        model_ir_content_hash=source_binding["model_ir_content_hash"],
        model_ir_semantic_hash=source_binding["model_ir_semantic_hash"],
        model_ir_provenance_hash=source_binding["model_ir_provenance_hash"],
        adapter_hash=source_binding["adapter_hash"],
        compiled_model_hash=source_binding["model_hash"],
        api_request_hash=source_binding["request_hash"],
        resume_contract_hash=expected_resume_contract_hash,
        source_solver_receipt_hash=source_receipt["result_hash"],
        numerical_result_ir_hash=numerical_result_ir["result_hash"],
        resume_checkpoint_artifact_sha256=resume_checkpoint_artifact_sha256,
        terminal_checkpoint_hash=terminal_checkpoint["checkpoint_hash"],
        terminal_checkpoint_artifact_hash=checkpoint_artifact["artifact_hash"],
        terminal_checkpoint_artifact_sha256=_sha256(persisted_checkpoint_bytes),
        recovery_hash=canonical_hash(
            {
                "node_displacements": result.node_displacements,
                "support_reactions": result.support_reactions,
                "member_recovery": result.member_recovery,
            }
        ),
        full_node_equilibrium_hash=canonical_hash(
            {
                "summary": equilibrium_summary,
                "nodes": result.full_node_equilibrium,
            }
        ),
        equilibrium_scaling_hash=equilibrium_summary["equilibrium_scaling_hash"],
        final_load_factor=metrics["final_load_factor"],
        total_load_factor_count=len(config.load_factors),
        resume_completed_prefix_count=resume_completed_prefix_count,
        accepted_suffix_step_count=metrics["accepted_step_count"],
        completed_prefix_count=metrics["completed_prefix_count"],
        remaining_load_factor_count=0,
        terminal_checkpoint_embedded=True,
        exact_result_manifest_replay=True,
        exact_source_solver_replay=True,
        exact_resume_checkpoint_binding=True,
        exact_terminal_checkpoint_replay=True,
        exact_numerical_result_ir_replay=True,
        exact_recovery_replay=True,
        residual_gate_pass=all(
            step["residual_gate_passed"] is True for step in accepted_steps
        ),
        increment_gate_pass=all(
            step["increment_gate_passed"] is True for step in accepted_steps
        ),
        line_search_pass=all(
            step["line_search_valid"] is True for step in accepted_steps
        ),
        terminal_reassembled_equilibrium_pass=all(
            step["final_reassembled_equilibrium_passed"] is True
            for step in accepted_steps
        ),
        full_node_equilibrium_pass=True,
        unsupported_feature_count=0,
        fallback_count=0,
        regularization_count=0,
        external_vv_level=0,
        workbench_execution=False,
        public_product_promotion=False,
        release_eligible=False,
        claim_boundary=result.claim_boundary,
    )
    return validate_frame3d_load_control_validation_report(report)


def validate_frame3d_load_control_validation_report(
    report: Frame3DLoadControlValidationReport | Mapping[str, Any],
) -> Frame3DLoadControlValidationReport:
    """Validate and rehydrate the exact report shape."""

    if isinstance(report, Frame3DLoadControlValidationReport):
        payload = report.to_dict()
        restored = report
    elif isinstance(report, Mapping):
        payload = dict(report)
        try:
            restored = Frame3DLoadControlValidationReport(**payload)
        except TypeError as error:
            raise Frame3DLoadControlValidationError(
                "validation_report_shape_invalid",
                "/",
                "Validation report fields are not exact.",
            ) from error
    else:
        _fail(
            "validation_report_type_invalid",
            "/",
            "Validation report must be a mapping or exact report type.",
        )
    with (
        resources.files("structural_analysis.schemas")
        .joinpath(FRAME3D_LOAD_CONTROL_VALIDATION_REPORT_SCHEMA_PATH)
        .open("r", encoding="utf-8") as handle
    ):
        schema = json.load(handle)
    Draft202012Validator.check_schema(schema)
    errors = sorted(
        _StrictDraft202012Validator(schema).iter_errors(payload),
        key=lambda row: list(row.path),
    )
    if errors:
        error = errors[0]
        path = "/" + "/".join(str(part) for part in error.path)
        _fail("validation_report_schema_invalid", path, error.message)
    return restored


def _bytes(value: bytes | bytearray | memoryview, path: str) -> bytes:
    if not isinstance(value, (bytes, bytearray, memoryview)):
        _fail("validation_bytes_invalid", path, "Expected bytes-like content.")
    return bytes(value)


def _parse_canonical_json_object(value: bytes, path: str) -> dict[str, Any]:
    def pairs(rows: list[tuple[str, Any]]) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        for key, item in rows:
            if key in payload:
                raise ValueError(f"duplicate JSON key: {key}")
            payload[key] = item
        return payload

    def constant(raw: str) -> NoReturn:
        raise ValueError(f"non-finite JSON constant: {raw}")

    try:
        payload = json.loads(
            value.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_constant=constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise Frame3DLoadControlValidationError(
            "validation_checkpoint_json_invalid",
            path,
            "Checkpoint artifact is not finite duplicate-free UTF-8 JSON.",
        ) from error
    if type(payload) is not dict or canonical_json_bytes(payload) + b"\n" != value:
        _fail(
            "validation_checkpoint_canonical_invalid",
            path,
            "Checkpoint artifact must use exact repository-canonical bytes.",
        )
    return payload


def _sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _fail(code: str, path: str, detail: str) -> NoReturn:
    raise Frame3DLoadControlValidationError(code, path, detail)


__all__ = [
    "FRAME3D_LOAD_CONTROL_BACKEND_ROLE",
    "FRAME3D_LOAD_CONTROL_VALIDATION_REPORT_SCHEMA_PATH",
    "FRAME3D_LOAD_CONTROL_VALIDATION_REPORT_SCHEMA_VERSION",
    "FRAME3D_LOAD_CONTROL_VALIDATOR_ID",
    "Frame3DLoadControlValidationError",
    "Frame3DLoadControlValidationReport",
    "build_frame3d_load_control_validation_report",
    "validate_frame3d_load_control_validation_report",
]
