"""Bounded ModelIR-facing candidate API for Frame3D direct control."""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib import resources
import json
import math
from types import MappingProxyType
from typing import Any, Literal, Mapping, NoReturn

from jsonschema import Draft202012Validator

from structural_analysis.adapters.bounded_frame3d_direct_control_model_ir import (
    BoundedFrame3DDirectControlModelIRAdapter,
    BoundedFrame3DDirectControlModelIRAdapterError,
    adapt_bounded_frame3d_direct_control_model_ir_v2,
)
from structural_analysis.assembly.stateful_corotational_frame3d_displacement_control import (
    STATEFUL_COROTATIONAL_FRAME3D_DISPLACEMENT_CONTROL_CYCLIC_RESUME_BINDING_SCHEMA_VERSION,
    STATEFUL_COROTATIONAL_FRAME3D_DISPLACEMENT_CONTROL_RESUME_BINDING_SCHEMA_VERSION,
    StatefulCorotationalFrame3DDisplacementControlConfig,
    StatefulCorotationalFrame3DDisplacementControlCyclicResumeBinding,
    StatefulCorotationalFrame3DDisplacementControlError,
    StatefulCorotationalFrame3DDisplacementControlResumeBinding,
    run_stateful_corotational_frame3d_displacement_control_path,
    validate_stateful_corotational_frame3d_displacement_control_resume_binding,
)
from structural_analysis.assembly.stateful_corotational_frame3d_sparse import (
    StatefulCorotationalFrame3DSparseCheckpoint,
    StatefulCorotationalFrame3DSparseError,
    assemble_stateful_corotational_frame3d_sparse,
    stateful_corotational_frame3d_equation_scaling_6dof,
    validate_stateful_corotational_frame3d_sparse_checkpoint,
)
from structural_analysis.elements.frame3d import FRAME_DOF_LABELS
from structural_analysis.engine_v2.contracts._canonical import (
    canonical_hash,
    canonical_json_bytes,
)
from structural_analysis.materials.uniaxial_plasticity import (
    STATE_SCHEMA_VERSION as UNIAXIAL_PLASTICITY_STATE_SCHEMA_VERSION,
    UniaxialPlasticityState,
)
from structural_analysis.model_ir.types import ModelIRDocument
from structural_analysis.solvers.equation_scaling_6dof import (
    scaled_residual_metrics_6dof,
)


BOUNDED_FRAME3D_DIRECT_CONTROL_API_PROFILE = (
    "bounded_frame3d_direct_displacement_control_model_ir_api.v1"
)
BOUNDED_FRAME3D_DIRECT_CONTROL_RESULT_SCHEMA_VERSION = (
    "bounded-frame3d-direct-control-result.v2"
)
BOUNDED_FRAME3D_DIRECT_CONTROL_CHECKPOINT_SCHEMA_VERSION = (
    "bounded-frame3d-direct-control-checkpoint-artifact.v1"
)
BOUNDED_FRAME3D_DIRECT_CONTROL_CYCLIC_CHECKPOINT_SCHEMA_VERSION = (
    "bounded-frame3d-direct-control-checkpoint-artifact.v2"
)
BOUNDED_FRAME3D_DIRECT_CONTROL_RESULT_SCHEMA_PATH = (
    "bounded_frame3d_direct_control_result_v2.schema.json"
)
BOUNDED_FRAME3D_DIRECT_CONTROL_CHECKPOINT_SCHEMA_PATH = (
    "bounded_frame3d_direct_control_checkpoint_v1.schema.json"
)
BOUNDED_FRAME3D_DIRECT_CONTROL_CYCLIC_CHECKPOINT_SCHEMA_PATH = (
    "bounded_frame3d_direct_control_checkpoint_v2.schema.json"
)
BOUNDED_FRAME3D_DIRECT_CONTROL_CHECKPOINT_MAX_BYTES = 8 * 1024 * 1024
BOUNDED_FRAME3D_DIRECT_CONTROL_CLAIM_BOUNDARY = (
    "This candidate API executes the source-bound bounded ModelIR v2 Frame3D "
    "single-coordinate direct displacement-control profile and returns node "
    "kinematics, support reactions, material-state summaries, and an exact "
    "checkpoint/resume artifact when the internal boundary permits it. The API "
    "optionally admits bounded reversal paths only for exact bilinear "
    "combined-hardening steel and uses a v2 rolling target-chain artifact; the v1 "
    "artifact remains monotonic-only. This is not a general cyclic-material claim. "
    "Persisted artifacts require finite repository-canonical JSON bytes and a "
    "deterministic unloaded checkpoint genesis/parent contract, complete ordered "
    "entity identities, and raw-to-typed checkpoint, resume-binding, and "
    "top-level artifact-envelope numeric identity. "
    "The API remains experimental and non-public in the capability registry. It "
    "does not "
    "support prescribed supports, offsets, releases, multiple controls, arc length, "
    "or Workbench execution. Same-operator OpenSees direct-control comparisons are "
    "internal supplemental evidence only. Artifact hashes are unsigned internal "
    "consistency checks, not authentication against an actor who recomputes them. "
    "Independent review, design authority, formal Level 2, and release authority "
    "remain absent."
)
_HASH_ZERO = "sha256:" + "0" * 64


class BoundedFrame3DDirectControlError(ValueError):
    """Stable candidate API error carrying a code and JSON-pointer path."""

    def __init__(self, code: str, path: str, detail: str) -> None:
        self.code = code
        self.path = path
        self.detail = detail
        super().__init__(f"{code}@{path}: {detail}")

    def to_blocker(self) -> dict[str, str]:
        return {"kind": self.code, "path": self.path, "detail": self.detail}


@dataclass(frozen=True)
class BoundedFrame3DDirectControlConfig:
    control_node_id: str
    control_dof: Literal["UX", "UY", "UZ", "RX", "RY", "RZ"]
    control_targets: tuple[float, ...]
    solver_config: StatefulCorotationalFrame3DDisplacementControlConfig = field(
        default_factory=StatefulCorotationalFrame3DDisplacementControlConfig
    )

    def __post_init__(self) -> None:
        if not isinstance(self.control_node_id, str) or not self.control_node_id:
            raise ValueError("control_node_id must be a non-empty stable identifier")
        if self.control_dof not in FRAME_DOF_LABELS:
            raise ValueError(f"control_dof must be one of {list(FRAME_DOF_LABELS)}")
        if type(self.solver_config) is not (
            StatefulCorotationalFrame3DDisplacementControlConfig
        ):
            raise ValueError("solver_config must be an exact Frame3D direct config")
        targets = tuple(self.control_targets)
        if not targets:
            raise ValueError("control_targets must not be empty")
        if len(targets) > self.solver_config.maximum_path_targets:
            raise ValueError("control_targets exceeds the bounded path length")
        normalized: list[float] = []
        for index, value in enumerate(targets):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"control_targets[{index}] must be finite")
            target = float(value)
            if not math.isfinite(target):
                raise ValueError(f"control_targets[{index}] must be finite")
            normalized.append(target)
        object.__setattr__(self, "control_targets", tuple(normalized))

    @property
    def control_unit(self) -> str:
        return "m" if self.control_dof.startswith("U") else "rad"

    @property
    def resume_contract_hash(self) -> str:
        return canonical_hash(
            {
                "profile": BOUNDED_FRAME3D_DIRECT_CONTROL_API_PROFILE,
                "control_node_id": self.control_node_id,
                "control_dof": self.control_dof,
                "control_unit": self.control_unit,
                "solver_contract_hash": self.solver_config.contract_hash,
            }
        )

    @property
    def request_hash(self) -> str:
        return canonical_hash(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": BOUNDED_FRAME3D_DIRECT_CONTROL_API_PROFILE,
            "control_node_id": self.control_node_id,
            "control_dof": self.control_dof,
            "control_unit": self.control_unit,
            "control_targets": list(self.control_targets),
            "solver_config": self.solver_config.to_manifest(),
            "resume_contract_hash": self.resume_contract_hash,
        }


@dataclass(frozen=True)
class BoundedFrame3DDirectControlResult:
    schema_version: str
    profile: str
    status: Literal["ready", "blocked"]
    contract_pass: bool
    result_hash: str
    source_binding: Mapping[str, Any]
    control: Mapping[str, Any]
    model_hash: str
    solver_result_hash: str
    terminal_reason_code: str | None
    metrics: Mapping[str, Any]
    node_displacements: tuple[Mapping[str, Any], ...]
    support_reactions: tuple[Mapping[str, Any], ...]
    material_states: tuple[Mapping[str, Any], ...]
    checkpoint_artifact: Mapping[str, Any]
    authority: Mapping[str, Any]
    warnings: tuple[str, ...]
    claim_boundary: str = BOUNDED_FRAME3D_DIRECT_CONTROL_CLAIM_BOUNDARY
    _checkpoint_artifact_bytes: bytes | None = field(
        default=None,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        for name in (
            "source_binding",
            "control",
            "metrics",
            "node_displacements",
            "support_reactions",
            "material_states",
            "checkpoint_artifact",
            "authority",
            "warnings",
        ):
            object.__setattr__(self, name, _deep_freeze_json(getattr(self, name)))

    def checkpoint_artifact_bytes(self) -> bytes:
        if self._checkpoint_artifact_bytes is None:
            raise ValueError("no exact checkpoint artifact is available")
        return self._checkpoint_artifact_bytes

    def to_dict(self) -> dict[str, Any]:
        return _result_payload(self, include_result_hash=True)


def analyze_bounded_frame3d_direct_control_model_ir(
    document: ModelIRDocument,
    config: BoundedFrame3DDirectControlConfig,
    *,
    restart_checkpoint_artifact: bytes | bytearray | memoryview | None = None,
) -> BoundedFrame3DDirectControlResult:
    """Run one source-bound bounded Frame3D direct-control request."""

    if type(document) is not ModelIRDocument:
        _fail(
            "bounded_frame3d_api_document_type_invalid",
            "/",
            "document must be an exact ModelIRDocument",
        )
    if type(config) is not BoundedFrame3DDirectControlConfig:
        _fail(
            "bounded_frame3d_api_config_type_invalid",
            "/config",
            "config must be an exact bounded Frame3D direct-control config",
        )
    if restart_checkpoint_artifact is not None and not isinstance(
        restart_checkpoint_artifact,
        (bytes, bytearray, memoryview),
    ):
        _fail(
            "bounded_frame3d_checkpoint_artifact_type_invalid",
            "/restart_checkpoint_artifact",
            "restart checkpoint artifact must be bytes-like",
        )
    try:
        adapter = adapt_bounded_frame3d_direct_control_model_ir_v2(document)
    except BoundedFrame3DDirectControlModelIRAdapterError as error:
        _fail(error.code, error.path, error.detail)
    model = adapter.model
    control_global_dof = adapter.global_dof(
        config.control_node_id,
        config.control_dof,
    )
    if control_global_dof not in model.free_dofs:
        _fail(
            "bounded_frame3d_control_dof_restrained",
            "/config/control_dof",
            "The controlled coordinate must be a free equation.",
        )

    resume_from: StatefulCorotationalFrame3DSparseCheckpoint | None = None
    resume_binding: (
        StatefulCorotationalFrame3DDisplacementControlResumeBinding
        | StatefulCorotationalFrame3DDisplacementControlCyclicResumeBinding
        | None
    ) = None
    if restart_checkpoint_artifact is not None:
        resume_from, resume_binding = _load_checkpoint_artifact(
            bytes(restart_checkpoint_artifact),
            adapter=adapter,
            config=config,
            control_global_dof=control_global_dof,
        )
    accepted_coordinate = (
        0.0
        if resume_from is None
        else float(resume_from.displacement[control_global_dof])
    )
    prior_cumulative_target_count = (
        resume_binding.cumulative_completed_target_count
        if type(resume_binding)
        is StatefulCorotationalFrame3DDisplacementControlCyclicResumeBinding
        else 0
    )
    if (
        config.solver_config.allow_direction_reversal
        and prior_cumulative_target_count + len(config.control_targets)
        > config.solver_config.maximum_path_targets
    ):
        _fail(
            "bounded_frame3d_control_cumulative_target_limit_exceeded",
            "/config/control_targets",
            "Exact cyclic continuation exceeds the configured cumulative target limit.",
        )
    _validate_target_direction(
        config.control_targets,
        accepted_coordinate=accepted_coordinate,
        bound_direction=(
            None
            if resume_binding is None
            else _resume_binding_last_direction_sign(resume_binding)
        ),
        allow_direction_reversal=(
            config.solver_config.allow_direction_reversal
        ),
        maximum_direction_reversals=(
            config.solver_config.maximum_direction_reversals
        ),
        prior_cumulative_reversal_count=(
            resume_binding.cumulative_reversal_count
            if type(resume_binding)
            is StatefulCorotationalFrame3DDisplacementControlCyclicResumeBinding
            else 0
        ),
    )
    try:
        solver_result = (
            run_stateful_corotational_frame3d_displacement_control_path(
                model,
                config.control_targets,
                control_global_dof=control_global_dof,
                config=config.solver_config,
                resume_from=resume_from,
                resume_binding=resume_binding,
            )
        )
        final_checkpoint = solver_result.final_checkpoint
        final_assembly = assemble_stateful_corotational_frame3d_sparse(
            model,
            final_checkpoint,
            target_load_factor=final_checkpoint.load_factor,
            trial_displacement=final_checkpoint.displacement,
        )
        equation_scaling = stateful_corotational_frame3d_equation_scaling_6dof(
            model,
            config=config.solver_config.frame_config,
        )
        residual_metrics = scaled_residual_metrics_6dof(
            final_assembly.residual_free,
            model.free_dofs,
            equation_scaling,
        )
        scaled_residual_tolerance = (
            config.solver_config.frame_config.residual_relative_tolerance
            + config.solver_config.frame_config.residual_absolute_tolerance_kn
            / equation_scaling.reference_force_kn
        )
    except (
        StatefulCorotationalFrame3DDisplacementControlError,
        StatefulCorotationalFrame3DSparseError,
        TypeError,
        ValueError,
    ) as error:
        reason_code = getattr(error, "reason_code", "bounded_frame3d_solver_error")
        _fail(str(reason_code), "/solver", str(error))

    artifact_bytes = _make_checkpoint_artifact(
        solver_result.resume_binding,
        checkpoint=final_checkpoint,
        adapter=adapter,
        config=config,
        control_global_dof=control_global_dof,
    )
    artifact_payload = (
        None if artifact_bytes is None else _strict_json_object(artifact_bytes)
    )
    source_binding = MappingProxyType(
        {
            "model_ir_content_hash": adapter.model_ir_content_hash,
            "model_ir_semantic_hash": adapter.model_ir_semantic_hash,
            "model_ir_provenance_hash": adapter.model_ir_provenance_hash,
            "adapter_hash": adapter.adapter_hash,
            "adapter_profile": adapter.adapter_profile,
            "load_pattern_id": adapter.load_pattern_id,
            "entity_mapping_hash": adapter.entity_mapping_hash,
            "node_ids": list(adapter.node_ids),
            "member_ids": list(adapter.member_ids),
            "member_material_ids": [
                material.material_id for material in adapter.model.axial_materials
            ],
            "recovery_identity_hash": canonical_hash(
                {
                    "entity_mapping_hash": adapter.entity_mapping_hash,
                    "node_ids": list(adapter.node_ids),
                    "member_ids": list(adapter.member_ids),
                    "member_material_ids": [
                        material.material_id
                        for material in adapter.model.axial_materials
                    ],
                }
            ),
        }
    )
    control = MappingProxyType(
        {
            **config.to_dict(),
            "request_hash": config.request_hash,
            "control_global_dof": control_global_dof,
        }
    )
    node_displacements = _node_displacement_rows(adapter, final_checkpoint)
    support_reactions = _support_reaction_rows(adapter, final_assembly.reactions)
    material_states = _material_state_rows(adapter, final_checkpoint)
    metrics = MappingProxyType(
        {
            "requested_target_count": len(config.control_targets),
            "completed_requested_target_count": (
                solver_result.completed_requested_target_count
            ),
            "solve_attempt_count": solver_result.solve_attempt_count,
            "accepted_checkpoint_count": len(solver_result.checkpoints) - 1,
            "target_cutback_attempt_count": len(
                solver_result.target_cutback_history
            ),
            "requested_direction_reversal_count": (
                solver_result.requested_direction_reversal_count
            ),
            "completed_direction_reversal_count": (
                solver_result.completed_direction_reversal_count
            ),
            "resumed_with_direction_reversal": (
                solver_result.resumed_with_direction_reversal
            ),
            "path_mode": solver_result.path_mode,
            "cumulative_completed_target_count": (
                solver_result.cumulative_completed_target_count
            ),
            "cumulative_direction_reversal_count": (
                solver_result.cumulative_direction_reversal_count
            ),
            "accepted_target_chain_hash": (
                solver_result.accepted_target_chain_hash
            ),
            "adaptive_target_cutback_used": (
                solver_result.adaptive_target_cutback_used
            ),
            "final_checkpoint_at_requested_target_boundary": (
                solver_result.final_checkpoint_at_requested_target_boundary
            ),
            "exact_checkpoint_resume_supported": (
                solver_result.exact_checkpoint_resume_supported
            ),
            "final_load_factor": final_checkpoint.load_factor,
            "final_control_coordinate": final_checkpoint.displacement[
                control_global_dof
            ],
            "raw_translational_residual_inf_norm_kn": residual_metrics[
                "translation"
            ],
            "raw_rotational_residual_inf_norm_kn_m": residual_metrics["rotation"],
            "scaled_residual_inf_norm": residual_metrics["scaled"],
            "scaled_residual_tolerance": scaled_residual_tolerance,
            "equation_scaling_hash": equation_scaling.scaling_hash,
            "maximum_accumulated_plastic_strain": max(
                (
                    float(row["accumulated_plastic_strain"])
                    for row in material_states
                ),
                default=0.0,
            ),
            "regularization_used": solver_result.regularization_used,
            "fallback_used": solver_result.fallback_used,
        }
    )
    checkpoint_descriptor = MappingProxyType(
        {
            "available": artifact_payload is not None,
            "schema_version": (
                None
                if artifact_payload is None
                else artifact_payload["schema_version"]
            ),
            "artifact_hash": (
                None if artifact_payload is None else artifact_payload["artifact_hash"]
            ),
            "byte_length": 0 if artifact_bytes is None else len(artifact_bytes),
            "checkpoint_hash": final_checkpoint.checkpoint_hash,
            "exact_resume_supported": (
                solver_result.exact_checkpoint_resume_supported
                and artifact_payload is not None
            ),
        }
    )
    authority = MappingProxyType(
        {
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
    )
    provisional = BoundedFrame3DDirectControlResult(
        schema_version=BOUNDED_FRAME3D_DIRECT_CONTROL_RESULT_SCHEMA_VERSION,
        profile=BOUNDED_FRAME3D_DIRECT_CONTROL_API_PROFILE,
        status="ready" if solver_result.contract_pass else "blocked",
        contract_pass=solver_result.contract_pass,
        result_hash=_HASH_ZERO,
        source_binding=source_binding,
        control=control,
        model_hash=model.model_hash,
        solver_result_hash=solver_result.result_hash,
        terminal_reason_code=solver_result.terminal_reason_code,
        metrics=metrics,
        node_displacements=node_displacements,
        support_reactions=support_reactions,
        material_states=material_states,
        checkpoint_artifact=checkpoint_descriptor,
        authority=authority,
        warnings=(
            "same_operator_opensees_direct_control_evidence_is_internal_only",
            "cyclic_reversal_same_operator_external_comparison_internal_only",
            "checkpoint_artifact_unsigned_self_hash_not_authenticated",
            "engineering_design_review_required",
        ),
        _checkpoint_artifact_bytes=artifact_bytes,
    )
    result = BoundedFrame3DDirectControlResult(
        **{
            **provisional.__dict__,
            "result_hash": canonical_hash(
                _result_payload(provisional, include_result_hash=False)
            ),
        }
    )
    return validate_bounded_frame3d_direct_control_result(result)


def validate_bounded_frame3d_direct_control_result(
    result: BoundedFrame3DDirectControlResult,
) -> BoundedFrame3DDirectControlResult:
    if type(result) is not BoundedFrame3DDirectControlResult:
        _fail(
            "bounded_frame3d_result_type_invalid",
            "/",
            "Expected an exact bounded Frame3D result.",
        )
    payload = result.to_dict()
    schema = _load_schema(BOUNDED_FRAME3D_DIRECT_CONTROL_RESULT_SCHEMA_PATH)
    errors = sorted(
        Draft202012Validator(schema).iter_errors(payload),
        key=lambda error: list(error.absolute_path),
    )
    if errors:
        first = errors[0]
        path = "/" + "/".join(str(value) for value in first.absolute_path)
        _fail("bounded_frame3d_result_schema_invalid", path, first.message)
    expected_hash = canonical_hash(
        _result_payload(result, include_result_hash=False)
    )
    if result.result_hash != expected_hash:
        _fail(
            "bounded_frame3d_result_hash_mismatch",
            "/result_hash",
            "Result hash does not match the canonical result payload.",
        )
    identity_payload = {
        "entity_mapping_hash": result.source_binding.get("entity_mapping_hash"),
        "node_ids": list(result.source_binding.get("node_ids", ())),
        "member_ids": list(result.source_binding.get("member_ids", ())),
        "member_material_ids": list(
            result.source_binding.get("member_material_ids", ())
        ),
    }
    if (
        result.source_binding.get("recovery_identity_hash")
        != canonical_hash(identity_payload)
    ):
        _fail(
            "bounded_frame3d_result_recovery_identity_hash_mismatch",
            "/source_binding/recovery_identity_hash",
            "Recovery entity identities do not match their source-bound hash.",
        )
    if result.contract_pass is not (result.status == "ready"):
        _fail(
            "bounded_frame3d_result_status_invalid",
            "/status",
            "Ready status and contract_pass must agree.",
        )
    requested_target_count = int(result.metrics["requested_target_count"])
    completed_target_count = int(
        result.metrics["completed_requested_target_count"]
    )
    control_target_count = len(result.control["control_targets"])
    if (
        requested_target_count != control_target_count
        or completed_target_count > requested_target_count
    ):
        _fail(
            "bounded_frame3d_result_target_count_invalid",
            "/metrics/completed_requested_target_count",
            "Requested/completed counts must agree with the bound control path.",
        )
    requested_reversal_count = int(
        result.metrics["requested_direction_reversal_count"]
    )
    completed_reversal_count = int(
        result.metrics["completed_direction_reversal_count"]
    )
    cumulative_completed_target_count = int(
        result.metrics["cumulative_completed_target_count"]
    )
    cumulative_reversal_count = int(
        result.metrics["cumulative_direction_reversal_count"]
    )
    path_mode = str(result.metrics["path_mode"])
    solver_manifest = result.control.get("solver_config")
    if not isinstance(solver_manifest, Mapping):
        _fail(
            "bounded_frame3d_result_solver_config_invalid",
            "/control/solver_config",
            "Solver config must be an object.",
        )
    direction_policy = solver_manifest.get("path_direction")
    if (
        not isinstance(direction_policy, Mapping)
        or type(direction_policy.get("allow_direction_reversal")) is not bool
        or type(direction_policy.get("maximum_direction_reversals")) is not int
    ):
        _fail(
            "bounded_frame3d_result_direction_policy_invalid",
            "/control/solver_config/path_direction",
            "Solver direction policy is incomplete or invalid.",
        )
    reversal_allowed = bool(direction_policy["allow_direction_reversal"])
    target_chain_hash = result.metrics["accepted_target_chain_hash"]
    if (
        completed_reversal_count > requested_reversal_count
        or requested_reversal_count > requested_target_count
        or cumulative_completed_target_count < completed_target_count
        or cumulative_reversal_count < completed_reversal_count
    ):
        _fail(
            "bounded_frame3d_result_direction_count_invalid",
            "/metrics/requested_direction_reversal_count",
            "Direction-reversal counts do not match the completed target path.",
        )
    if reversal_allowed:
        if (
            path_mode != "cyclic_reversal"
            or not isinstance(target_chain_hash, str)
            or not target_chain_hash.startswith("sha256:")
        ):
            _fail(
                "bounded_frame3d_result_cyclic_lineage_invalid",
                "/metrics/accepted_target_chain_hash",
                "Cyclic results require a rolling target-chain hash.",
            )
    elif (
        path_mode != "monotonic_v1"
        or requested_reversal_count != 0
        or completed_reversal_count != 0
        or cumulative_reversal_count != 0
        or result.metrics["resumed_with_direction_reversal"] is not False
        or target_chain_hash is not None
    ):
        _fail(
            "bounded_frame3d_result_monotonic_lineage_invalid",
            "/metrics/path_mode",
            "Monotonic v1 results cannot claim cyclic lineage.",
        )
    if result.status == "ready":
        if (
            result.terminal_reason_code is not None
            or completed_target_count != requested_target_count
            or completed_reversal_count != requested_reversal_count
        ):
            _fail(
                "bounded_frame3d_result_ready_contract_invalid",
                "/terminal_reason_code",
                "Ready results must complete every requested target without a terminal reason.",
            )
    elif (
        not isinstance(result.terminal_reason_code, str)
        or not result.terminal_reason_code
        or completed_target_count >= requested_target_count
    ):
        _fail(
            "bounded_frame3d_result_blocked_contract_invalid",
            "/terminal_reason_code",
            "Blocked results require a terminal reason before all targets complete.",
        )
    checkpoint_boundary = bool(
        result.metrics["final_checkpoint_at_requested_target_boundary"]
    )
    metric_exact_resume = bool(
        result.metrics["exact_checkpoint_resume_supported"]
    )
    artifact_available = bool(result.checkpoint_artifact["available"])
    descriptor_exact_resume = bool(
        result.checkpoint_artifact["exact_resume_supported"]
    )
    if not (
        checkpoint_boundary
        == metric_exact_resume
        == artifact_available
        == descriptor_exact_resume
    ):
        _fail(
            "bounded_frame3d_result_checkpoint_coherence_invalid",
            "/checkpoint_artifact",
            "Boundary, exact-resume, and checkpoint availability claims must agree.",
        )
    if (
        result.status == "ready"
        and not checkpoint_boundary
    ):
        _fail(
            "bounded_frame3d_result_ready_checkpoint_missing",
            "/checkpoint_artifact",
            "Ready results require an exact requested-boundary checkpoint.",
        )
    expected_control_unit = (
        "m" if str(result.control["control_dof"]).startswith("U") else "rad"
    )
    expected_dof_offset = FRAME_DOF_LABELS.index(result.control["control_dof"])
    if (
        result.control["control_unit"] != expected_control_unit
        or int(result.control["control_global_dof"]) % 6 != expected_dof_offset
    ):
        _fail(
            "bounded_frame3d_result_control_binding_invalid",
            "/control",
            "Control unit and global equation must agree with the control DOF.",
        )
    control_payload = _mutable_json_copy(result.control)
    request_hash = str(control_payload.pop("request_hash"))
    control_payload.pop("control_global_dof")
    if request_hash != canonical_hash(control_payload):
        _fail(
            "bounded_frame3d_result_request_hash_mismatch",
            "/control/request_hash",
            "Request hash does not match the bound control request.",
        )
    solver_contract_hash = canonical_hash(result.control["solver_config"])
    expected_resume_contract_hash = canonical_hash(
        {
            "profile": BOUNDED_FRAME3D_DIRECT_CONTROL_API_PROFILE,
            "control_node_id": result.control["control_node_id"],
            "control_dof": result.control["control_dof"],
            "control_unit": result.control["control_unit"],
            "solver_contract_hash": solver_contract_hash,
        }
    )
    if result.control["resume_contract_hash"] != expected_resume_contract_hash:
        _fail(
            "bounded_frame3d_result_resume_contract_hash_mismatch",
            "/control/resume_contract_hash",
            "Resume contract hash does not match the control and solver contract.",
        )
    if (
        float(result.metrics["scaled_residual_inf_norm"])
        > float(result.metrics["scaled_residual_tolerance"])
    ):
        _fail(
            "bounded_frame3d_result_residual_gate_invalid",
            "/metrics/scaled_residual_inf_norm",
            "The retained requested-boundary checkpoint must pass the scaled residual gate.",
        )
    if result.claim_boundary != BOUNDED_FRAME3D_DIRECT_CONTROL_CLAIM_BOUNDARY:
        _fail(
            "bounded_frame3d_result_claim_boundary_invalid",
            "/claim_boundary",
            "Result claim boundary does not match the candidate API contract.",
        )
    if (
        result.authority["capability_registry_public"] is not False
        or result.authority["external_vv_level"] != 0
        or result.authority["formal_verification_level_2"] is not False
        or result.authority["release_eligible"] is not False
    ):
        _fail(
            "bounded_frame3d_result_authority_promotion_forbidden",
            "/authority",
            "Candidate API output cannot promote public, Level 2, or release authority.",
        )
    if result.checkpoint_artifact["available"]:
        if result._checkpoint_artifact_bytes is None:
            _fail(
                "bounded_frame3d_checkpoint_artifact_bytes_missing",
                "/checkpoint_artifact",
                "Available checkpoint descriptor lacks artifact bytes.",
            )
        artifact = _validate_checkpoint_artifact_envelope(
            result._checkpoint_artifact_bytes
        )
        if (
            artifact["artifact_hash"]
            != result.checkpoint_artifact["artifact_hash"]
            or len(result._checkpoint_artifact_bytes)
            != result.checkpoint_artifact["byte_length"]
            or artifact["checkpoint"]["checkpoint_hash"]
            != result.checkpoint_artifact["checkpoint_hash"]
        ):
            _fail(
                "bounded_frame3d_checkpoint_artifact_descriptor_mismatch",
                "/checkpoint_artifact",
                "Checkpoint descriptor does not match the retained artifact.",
            )
        if result.checkpoint_artifact["schema_version"] != artifact["schema_version"]:
            _fail(
                "bounded_frame3d_checkpoint_artifact_descriptor_schema_mismatch",
                "/checkpoint_artifact/schema_version",
                "Checkpoint descriptor schema version does not match its bytes.",
            )
        solver_config = result.control["solver_config"]
        if not isinstance(solver_config, Mapping) or not isinstance(
            solver_config.get("frame_config"), Mapping
        ):
            _fail(
                "bounded_frame3d_result_solver_config_invalid",
                "/control/solver_config",
                "Solver config must contain its bounded Frame3D frame contract.",
            )
        artifact_binding = {
            "model_ir_content_hash": result.source_binding["model_ir_content_hash"],
            "adapter_hash": result.source_binding["adapter_hash"],
            "model_hash": result.model_hash,
            "resume_contract_hash": result.control["resume_contract_hash"],
            "control_node_id": result.control["control_node_id"],
            "control_dof": result.control["control_dof"],
            "control_global_dof": result.control["control_global_dof"],
            "control_unit": result.control["control_unit"],
            "entity_mapping_hash": result.source_binding[
                "entity_mapping_hash"
            ],
            "node_ids": list(result.source_binding["node_ids"]),
            "member_ids": list(result.source_binding["member_ids"]),
            "member_material_ids": list(
                result.source_binding["member_material_ids"]
            ),
        }
        if any(
            artifact[key] != expected
            for key, expected in artifact_binding.items()
        ):
            _fail(
                "bounded_frame3d_checkpoint_artifact_result_binding_mismatch",
                "/checkpoint_artifact",
                "Checkpoint artifact does not match the result source/control binding.",
            )
        if (
            artifact["checkpoint"]["solver_contract_hash"]
            != canonical_hash(solver_config["frame_config"])
            or artifact["resume_binding"]["direct_control_contract_hash"]
            != solver_contract_hash
        ):
            _fail(
                "bounded_frame3d_checkpoint_artifact_solver_binding_mismatch",
                "/checkpoint_artifact",
                "Checkpoint artifact does not match the result solver contracts.",
            )
        if reversal_allowed:
            if (
                artifact["schema_version"]
                != BOUNDED_FRAME3D_DIRECT_CONTROL_CYCLIC_CHECKPOINT_SCHEMA_VERSION
                or artifact.get("path_mode") != path_mode
                or artifact.get("cumulative_completed_target_count")
                != cumulative_completed_target_count
                or artifact.get("cumulative_reversal_count")
                != cumulative_reversal_count
                or artifact.get("accepted_target_chain_hash")
                != target_chain_hash
            ):
                _fail(
                    "bounded_frame3d_result_cyclic_artifact_lineage_mismatch",
                    "/checkpoint_artifact",
                    "Cyclic result metrics and v2 artifact lineage do not agree.",
                )
        elif (
            artifact["schema_version"]
            != BOUNDED_FRAME3D_DIRECT_CONTROL_CHECKPOINT_SCHEMA_VERSION
        ):
            _fail(
                "bounded_frame3d_result_monotonic_artifact_schema_mismatch",
                "/checkpoint_artifact/schema_version",
                "Monotonic v1 results require a v1 checkpoint artifact.",
            )
        checkpoint = artifact["checkpoint"]
        checkpoint_displacement = tuple(
            float(value) for value in checkpoint["displacement"]
        )
        recovered_displacement = tuple(
            float(row[key])
            for row in result.node_displacements
            for key in (
                "UX_m",
                "UY_m",
                "UZ_m",
                "RX_rad",
                "RY_rad",
                "RZ_rad",
            )
        )
        control_node_index = int(result.control["control_global_dof"]) // 6
        if (
            recovered_displacement != checkpoint_displacement
            or control_node_index >= len(result.node_displacements)
            or result.node_displacements[control_node_index]["node_id"]
            != result.control["control_node_id"]
            or float(result.metrics["final_load_factor"])
            != float(checkpoint["load_factor"])
            or float(result.metrics["final_control_coordinate"])
            != checkpoint_displacement[int(result.control["control_global_dof"])]
        ):
            _fail(
                "bounded_frame3d_result_checkpoint_kinematics_mismatch",
                "/node_displacements",
                "Recovered node/control values do not match the retained checkpoint.",
            )
        checkpoint_states = tuple(
            (
                float(row["plastic_strain"]),
                float(row["backstress_mpa"]),
                float(row["accumulated_plastic_strain"]),
                float(row["dissipated_energy_density_mj_per_m3"]),
                str(row["state_hash"]),
            )
            for row in checkpoint["material_states"]
        )
        recovered_states = tuple(
            (
                float(row["plastic_strain"]),
                float(row["backstress_mpa"]),
                float(row["accumulated_plastic_strain"]),
                float(row["dissipated_energy_density_mj_per_m3"]),
                str(row["state_hash"]),
            )
            for row in result.material_states
        )
        expected_node_ids = tuple(result.source_binding["node_ids"])
        recovered_node_ids = tuple(
            str(row["node_id"]) for row in result.node_displacements
        )
        expected_member_material_ids = tuple(
            zip(
                result.source_binding["member_ids"],
                result.source_binding["member_material_ids"],
                strict=True,
            )
        )
        recovered_member_material_ids = tuple(
            (str(row["member_id"]), str(row["material_id"]))
            for row in result.material_states
        )
        maximum_accumulated_plastic_strain = max(
            (row[2] for row in checkpoint_states),
            default=0.0,
        )
        if (
            recovered_states != checkpoint_states
            or recovered_node_ids != expected_node_ids
            or recovered_member_material_ids != expected_member_material_ids
            or float(result.metrics["maximum_accumulated_plastic_strain"])
            != maximum_accumulated_plastic_strain
        ):
            _fail(
                "bounded_frame3d_result_checkpoint_material_state_mismatch",
                "/material_states",
                "Recovered entity identities or material states do not match the source-bound checkpoint.",
            )
    elif result._checkpoint_artifact_bytes is not None:
        _fail(
            "bounded_frame3d_checkpoint_artifact_unexpected",
            "/checkpoint_artifact",
            "Unavailable checkpoint descriptor retains unexpected bytes.",
        )
    return result


def _resume_binding_last_direction_sign(
    binding: (
        StatefulCorotationalFrame3DDisplacementControlResumeBinding
        | StatefulCorotationalFrame3DDisplacementControlCyclicResumeBinding
    ),
) -> int | None:
    if type(binding) is StatefulCorotationalFrame3DDisplacementControlResumeBinding:
        return binding.direction_sign
    if type(binding) is (
        StatefulCorotationalFrame3DDisplacementControlCyclicResumeBinding
    ):
        return binding.last_completed_leg_direction_sign
    _fail(
        "bounded_frame3d_checkpoint_resume_binding_type_invalid",
        "/resume_binding",
        "Unsupported resume binding type.",
    )


def _make_checkpoint_artifact(
    binding: (
        StatefulCorotationalFrame3DDisplacementControlResumeBinding
        | StatefulCorotationalFrame3DDisplacementControlCyclicResumeBinding
        | None
    ),
    *,
    checkpoint: StatefulCorotationalFrame3DSparseCheckpoint,
    adapter: BoundedFrame3DDirectControlModelIRAdapter,
    config: BoundedFrame3DDirectControlConfig,
    control_global_dof: int,
) -> bytes | None:
    if binding is None:
        return None
    common_payload = {
        "profile": BOUNDED_FRAME3D_DIRECT_CONTROL_API_PROFILE,
        "model_ir_content_hash": adapter.model_ir_content_hash,
        "adapter_hash": adapter.adapter_hash,
        "model_hash": adapter.model_hash,
        "resume_contract_hash": config.resume_contract_hash,
        "control_node_id": config.control_node_id,
        "control_dof": config.control_dof,
        "control_global_dof": control_global_dof,
        "control_unit": config.control_unit,
        "entity_mapping_hash": adapter.entity_mapping_hash,
        "node_ids": list(adapter.node_ids),
        "member_ids": list(adapter.member_ids),
        "member_material_ids": [
            material.material_id for material in adapter.model.axial_materials
        ],
        "checkpoint": checkpoint.to_dict(),
        "resume_binding": binding.to_dict(),
    }
    if type(binding) is StatefulCorotationalFrame3DDisplacementControlResumeBinding:
        payload = {
            "schema_version": (
                BOUNDED_FRAME3D_DIRECT_CONTROL_CHECKPOINT_SCHEMA_VERSION
            ),
            **common_payload,
            "direction_sign": binding.direction_sign,
        }
        schema_path = BOUNDED_FRAME3D_DIRECT_CONTROL_CHECKPOINT_SCHEMA_PATH
    elif type(binding) is (
        StatefulCorotationalFrame3DDisplacementControlCyclicResumeBinding
    ):
        payload = {
            "schema_version": (
                BOUNDED_FRAME3D_DIRECT_CONTROL_CYCLIC_CHECKPOINT_SCHEMA_VERSION
            ),
            **common_payload,
            "path_mode": binding.path_mode,
            "last_completed_leg_direction_sign": (
                binding.last_completed_leg_direction_sign
            ),
            "cumulative_reversal_count": binding.cumulative_reversal_count,
            "cumulative_completed_target_count": (
                binding.cumulative_completed_target_count
            ),
            "accepted_target_chain_hash": (
                binding.accepted_target_chain_hash
            ),
        }
        schema_path = (
            BOUNDED_FRAME3D_DIRECT_CONTROL_CYCLIC_CHECKPOINT_SCHEMA_PATH
        )
    else:  # pragma: no cover - exact binding type invariant
        _fail(
            "bounded_frame3d_checkpoint_resume_binding_type_invalid",
            "/resume_binding",
            "Unsupported resume binding type.",
        )
    payload["artifact_hash"] = canonical_hash(payload)
    schema = _load_schema(schema_path)
    Draft202012Validator(schema).validate(payload)
    artifact_bytes = canonical_json_bytes(payload) + b"\n"
    _validate_checkpoint_artifact_envelope(artifact_bytes)
    return artifact_bytes


def _load_checkpoint_artifact(
    artifact_bytes: bytes,
    *,
    adapter: BoundedFrame3DDirectControlModelIRAdapter,
    config: BoundedFrame3DDirectControlConfig,
    control_global_dof: int,
) -> tuple[
    StatefulCorotationalFrame3DSparseCheckpoint,
    StatefulCorotationalFrame3DDisplacementControlResumeBinding
    | StatefulCorotationalFrame3DDisplacementControlCyclicResumeBinding,
]:
    payload = _validate_checkpoint_artifact_envelope(artifact_bytes)
    if (
        payload["model_ir_content_hash"] != adapter.model_ir_content_hash
        or payload["adapter_hash"] != adapter.adapter_hash
        or payload["model_hash"] != adapter.model_hash
        or payload["resume_contract_hash"] != config.resume_contract_hash
        or payload["control_node_id"] != config.control_node_id
        or payload["control_dof"] != config.control_dof
        or payload["control_global_dof"] != control_global_dof
        or payload["control_unit"] != config.control_unit
        or payload["entity_mapping_hash"] != adapter.entity_mapping_hash
        or tuple(payload["node_ids"]) != adapter.node_ids
        or tuple(payload["member_ids"]) != adapter.member_ids
        or tuple(payload["member_material_ids"])
        != tuple(
            material.material_id for material in adapter.model.axial_materials
        )
    ):
        _fail(
            "bounded_frame3d_checkpoint_artifact_contract_mismatch",
            "/",
            "Checkpoint artifact does not match the source model or control contract.",
        )
    checkpoint = _checkpoint_from_dict(payload["checkpoint"])
    binding = _resume_binding_from_dict(payload["resume_binding"])
    try:
        validate_stateful_corotational_frame3d_sparse_checkpoint(
            checkpoint,
            model=adapter.model,
            config=config.solver_config.frame_config,
            require_equilibrium=True,
        )
        validate_stateful_corotational_frame3d_displacement_control_resume_binding(
            binding,
            checkpoint=checkpoint,
            model=adapter.model,
            config=config.solver_config,
            control_global_dof=control_global_dof,
        )
    except (
        StatefulCorotationalFrame3DDisplacementControlError,
        StatefulCorotationalFrame3DSparseError,
        TypeError,
        ValueError,
    ) as error:
        if (
            isinstance(error, StatefulCorotationalFrame3DSparseError)
            and error.reason_code == "material_state_admissibility_failed"
        ):
            _fail(
                "bounded_frame3d_checkpoint_material_state_admissibility_failed",
                "/checkpoint/material_states",
                str(error),
            )
        _fail(
            "bounded_frame3d_checkpoint_artifact_validation_failed",
            "/checkpoint",
            str(error),
        )
    if type(binding) is StatefulCorotationalFrame3DDisplacementControlResumeBinding:
        if payload["direction_sign"] != binding.direction_sign:
            _fail(
                "bounded_frame3d_checkpoint_artifact_direction_mismatch",
                "/direction_sign",
                "Artifact direction does not match its internal resume binding.",
            )
    else:
        for field in (
            "path_mode",
            "last_completed_leg_direction_sign",
            "cumulative_reversal_count",
            "cumulative_completed_target_count",
            "accepted_target_chain_hash",
        ):
            if payload[field] != getattr(binding, field):
                _fail(
                    "bounded_frame3d_checkpoint_artifact_cyclic_binding_mismatch",
                    f"/{field}",
                    "Cyclic artifact lineage does not match its resume binding.",
                )
    return checkpoint, binding


def _checkpoint_from_dict(payload: Mapping[str, Any]) -> StatefulCorotationalFrame3DSparseCheckpoint:
    states: list[UniaxialPlasticityState] = []
    for index, row in enumerate(payload["material_states"]):
        if row["schema_version"] != UNIAXIAL_PLASTICITY_STATE_SCHEMA_VERSION:
            _fail(
                "bounded_frame3d_checkpoint_material_state_unsupported",
                f"/checkpoint/material_states/{index}",
                "Candidate API checkpoints support only bilinear steel state rows.",
            )
        state = UniaxialPlasticityState(
            plastic_strain=float(row["plastic_strain"]),
            backstress_mpa=float(row["backstress_mpa"]),
            accumulated_plastic_strain=float(row["accumulated_plastic_strain"]),
            dissipated_energy_density_mj_per_m3=float(
                row["dissipated_energy_density_mj_per_m3"]
            ),
        )
        if state.state_hash != row["state_hash"]:
            _fail(
                "bounded_frame3d_checkpoint_material_state_hash_mismatch",
                f"/checkpoint/material_states/{index}/state_hash",
                "Material-state hash does not match its numeric state.",
            )
        states.append(state)
    return StatefulCorotationalFrame3DSparseCheckpoint(
        schema_version=str(payload["schema_version"]),
        profile=str(payload["profile"]),
        model_hash=str(payload["model_hash"]),
        solver_contract_hash=str(payload["solver_contract_hash"]),
        step_index=int(payload["step_index"]),
        load_factor=float(payload["load_factor"]),
        displacement=tuple(float(value) for value in payload["displacement"]),
        material_states=tuple(states),
        converged_iterations=int(payload["converged_iterations"]),
        residual_inf_norm_kn=float(payload["residual_inf_norm_kn"]),
        parent_checkpoint_hash=(
            None
            if payload["parent_checkpoint_hash"] is None
            else str(payload["parent_checkpoint_hash"])
        ),
        checkpoint_hash=str(payload["checkpoint_hash"]),
    )


def _resume_binding_from_dict(
    payload: Mapping[str, Any],
) -> (
    StatefulCorotationalFrame3DDisplacementControlResumeBinding
    | StatefulCorotationalFrame3DDisplacementControlCyclicResumeBinding
):
    schema_version = str(payload["schema_version"])
    common = {
        "schema_version": schema_version,
        "profile": str(payload["profile"]),
        "model_hash": str(payload["model_hash"]),
        "frame_solver_contract_hash": str(
            payload["frame_solver_contract_hash"]
        ),
        "direct_control_contract_hash": str(
            payload["direct_control_contract_hash"]
        ),
        "control_global_dof": int(payload["control_global_dof"]),
        "control_unit": str(payload["control_unit"]),
        "accepted_control_target": float(payload["accepted_control_target"]),
        "accepted_step_index": int(payload["accepted_step_index"]),
        "accepted_checkpoint_hash": str(payload["accepted_checkpoint_hash"]),
        "binding_hash": str(payload["binding_hash"]),
    }
    if (
        schema_version
        == STATEFUL_COROTATIONAL_FRAME3D_DISPLACEMENT_CONTROL_RESUME_BINDING_SCHEMA_VERSION
    ):
        return StatefulCorotationalFrame3DDisplacementControlResumeBinding(
            **common,
            direction_sign=int(payload["direction_sign"]),
        )
    if (
        schema_version
        == STATEFUL_COROTATIONAL_FRAME3D_DISPLACEMENT_CONTROL_CYCLIC_RESUME_BINDING_SCHEMA_VERSION
    ):
        return (
            StatefulCorotationalFrame3DDisplacementControlCyclicResumeBinding(
                **common,
                path_mode=str(payload["path_mode"]),
                last_completed_leg_direction_sign=(
                    None
                    if payload["last_completed_leg_direction_sign"] is None
                    else int(payload["last_completed_leg_direction_sign"])
                ),
                cumulative_reversal_count=int(
                    payload["cumulative_reversal_count"]
                ),
                cumulative_completed_target_count=int(
                    payload["cumulative_completed_target_count"]
                ),
                accepted_target_chain_hash=str(
                    payload["accepted_target_chain_hash"]
                ),
            )
        )
    _fail(
        "bounded_frame3d_checkpoint_resume_binding_schema_unsupported",
        "/resume_binding/schema_version",
        "Resume binding schema version is unsupported.",
    )


def _validate_target_direction(
    targets: tuple[float, ...],
    *,
    accepted_coordinate: float,
    bound_direction: int | None,
    allow_direction_reversal: bool,
    maximum_direction_reversals: int,
    prior_cumulative_reversal_count: int,
) -> None:
    direction_signs: list[int] = []
    previous = accepted_coordinate
    for index, target in enumerate(targets):
        delta = target - previous
        if delta == 0.0:
            _fail(
                "bounded_frame3d_control_target_not_advancing",
                f"/config/control_targets/{index}",
                "Each target must advance from the preceding accepted coordinate.",
            )
        direction_signs.append(1 if delta > 0.0 else -1)
        previous = target
    previous_direction = (
        direction_signs[0]
        if bound_direction is None
        else bound_direction
    )
    reversal_count = 0
    for direction in direction_signs:
        if direction != previous_direction:
            reversal_count += 1
        previous_direction = direction
    resumed_with_reversal = bool(
        bound_direction is not None
        and direction_signs[0] != bound_direction
    )
    if not allow_direction_reversal:
        if resumed_with_reversal:
            _fail(
                "bounded_frame3d_control_resume_direction_mismatch",
                "/config/control_targets/0",
                "Resumed targets must continue the checkpoint-bound direction.",
            )
        if reversal_count:
            first_reversal_index = next(
                index
                for index in range(1, len(direction_signs))
                if direction_signs[index] != direction_signs[index - 1]
            )
            _fail(
                "bounded_frame3d_control_targets_nonmonotonic",
                f"/config/control_targets/{first_reversal_index}",
                "Control targets must advance strictly in one direction.",
            )
    elif (
        prior_cumulative_reversal_count + reversal_count
        > maximum_direction_reversals
    ):
        _fail(
            "bounded_frame3d_control_direction_reversal_limit_exceeded",
            "/config/control_targets",
            "The requested path exceeds the configured cumulative reversal limit.",
        )


def _node_displacement_rows(
    adapter: BoundedFrame3DDirectControlModelIRAdapter,
    checkpoint: StatefulCorotationalFrame3DSparseCheckpoint,
) -> tuple[Mapping[str, Any], ...]:
    rows: list[Mapping[str, Any]] = []
    for node_index, node_id in enumerate(adapter.node_ids):
        values = checkpoint.displacement[6 * node_index : 6 * node_index + 6]
        rows.append(
            MappingProxyType(
                {
                    "node_id": node_id,
                    "UX_m": values[0],
                    "UY_m": values[1],
                    "UZ_m": values[2],
                    "RX_rad": values[3],
                    "RY_rad": values[4],
                    "RZ_rad": values[5],
                }
            )
        )
    return tuple(rows)


def _support_reaction_rows(
    adapter: BoundedFrame3DDirectControlModelIRAdapter,
    reactions: Any,
) -> tuple[Mapping[str, Any], ...]:
    restrained = set(adapter.model.elastic_model.restrained_dofs)
    rows: list[Mapping[str, Any]] = []
    for global_dof in sorted(restrained):
        node_index, component_index = divmod(global_dof, 6)
        component = FRAME_DOF_LABELS[component_index]
        rows.append(
            MappingProxyType(
                {
                    "node_id": adapter.node_ids[node_index],
                    "dof": component,
                    "value": float(reactions[global_dof]),
                    "unit": "kN" if component_index < 3 else "kN_m",
                }
            )
        )
    return tuple(rows)


def _material_state_rows(
    adapter: BoundedFrame3DDirectControlModelIRAdapter,
    checkpoint: StatefulCorotationalFrame3DSparseCheckpoint,
) -> tuple[Mapping[str, Any], ...]:
    rows: list[Mapping[str, Any]] = []
    for member_id, material_id, state in zip(
        adapter.member_ids,
        (
            material.material_id
            for material in adapter.model.axial_materials
        ),
        checkpoint.material_states,
        strict=True,
    ):
        if type(state) is not UniaxialPlasticityState:
            _fail(
                "bounded_frame3d_result_material_state_unsupported",
                "/material_states",
                "Candidate API recovery supports only bilinear steel state rows.",
            )
        rows.append(
            MappingProxyType(
                {
                    "member_id": member_id,
                    "material_id": material_id,
                    "plastic_strain": state.plastic_strain,
                    "backstress_mpa": state.backstress_mpa,
                    "accumulated_plastic_strain": (
                        state.accumulated_plastic_strain
                    ),
                    "dissipated_energy_density_mj_per_m3": (
                        state.dissipated_energy_density_mj_per_m3
                    ),
                    "state_hash": state.state_hash,
                }
            )
        )
    return tuple(rows)


def _result_payload(
    result: BoundedFrame3DDirectControlResult,
    *,
    include_result_hash: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": result.schema_version,
        "profile": result.profile,
        "status": result.status,
        "contract_pass": result.contract_pass,
        "source_binding": _mutable_json_copy(result.source_binding),
        "control": _mutable_json_copy(result.control),
        "model_hash": result.model_hash,
        "solver_result_hash": result.solver_result_hash,
        "terminal_reason_code": result.terminal_reason_code,
        "metrics": _mutable_json_copy(result.metrics),
        "node_displacements": _mutable_json_copy(result.node_displacements),
        "support_reactions": _mutable_json_copy(result.support_reactions),
        "material_states": _mutable_json_copy(result.material_states),
        "checkpoint_artifact": _mutable_json_copy(result.checkpoint_artifact),
        "authority": _mutable_json_copy(result.authority),
        "warnings": _mutable_json_copy(result.warnings),
        "claim_boundary": result.claim_boundary,
    }
    if include_result_hash:
        payload["result_hash"] = result.result_hash
    return payload


def _deep_freeze_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {
                str(key): _deep_freeze_json(item)
                for key, item in value.items()
            }
        )
    if isinstance(value, (tuple, list)):
        return tuple(_deep_freeze_json(item) for item in value)
    return value


def _mutable_json_copy(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _mutable_json_copy(item)
            for key, item in value.items()
        }
    if isinstance(value, (tuple, list)):
        return [_mutable_json_copy(item) for item in value]
    return value


def _strict_json_object(value: bytes) -> dict[str, Any]:
    try:
        payload = json.loads(
            value.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_json_constant,
        )
        nonfinite_path = _nonfinite_json_number_path(payload)
        if nonfinite_path is not None:
            raise ValueError(f"non-finite JSON number at {nonfinite_path}")
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        _fail(
            "bounded_frame3d_checkpoint_artifact_json_invalid",
            "/restart_checkpoint_artifact",
            str(error),
        )
    if not isinstance(payload, dict):
        _fail(
            "bounded_frame3d_checkpoint_artifact_root_invalid",
            "/restart_checkpoint_artifact",
            "Checkpoint artifact root must be an object.",
        )
    return payload


def _validate_checkpoint_artifact_envelope(
    artifact_bytes: bytes,
) -> dict[str, Any]:
    if not artifact_bytes:
        _fail(
            "bounded_frame3d_checkpoint_artifact_empty",
            "/restart_checkpoint_artifact",
            "Checkpoint artifact must not be empty.",
        )
    if len(artifact_bytes) > BOUNDED_FRAME3D_DIRECT_CONTROL_CHECKPOINT_MAX_BYTES:
        _fail(
            "bounded_frame3d_checkpoint_artifact_too_large",
            "/restart_checkpoint_artifact",
            "Checkpoint artifact exceeds the bounded byte limit.",
        )
    payload = _strict_json_object(artifact_bytes)
    schema_version = payload.get("schema_version")
    schema_path = {
        BOUNDED_FRAME3D_DIRECT_CONTROL_CHECKPOINT_SCHEMA_VERSION: (
            BOUNDED_FRAME3D_DIRECT_CONTROL_CHECKPOINT_SCHEMA_PATH
        ),
        BOUNDED_FRAME3D_DIRECT_CONTROL_CYCLIC_CHECKPOINT_SCHEMA_VERSION: (
            BOUNDED_FRAME3D_DIRECT_CONTROL_CYCLIC_CHECKPOINT_SCHEMA_PATH
        ),
    }.get(schema_version)
    if schema_path is None:
        _fail(
            "bounded_frame3d_checkpoint_artifact_schema_version_unsupported",
            "/schema_version",
            "Checkpoint artifact schema version is unsupported.",
        )
    schema = _load_schema(schema_path)
    errors = sorted(
        Draft202012Validator(schema).iter_errors(payload),
        key=lambda error: list(error.absolute_path),
    )
    if errors:
        first = errors[0]
        path = "/" + "/".join(str(value) for value in first.absolute_path)
        _fail("bounded_frame3d_checkpoint_artifact_schema_invalid", path, first.message)
    integer_fields = ["control_global_dof"]
    if schema_version == BOUNDED_FRAME3D_DIRECT_CONTROL_CHECKPOINT_SCHEMA_VERSION:
        integer_fields.append("direction_sign")
    else:
        integer_fields.extend(
            (
                "cumulative_reversal_count",
                "cumulative_completed_target_count",
            )
        )
        last_direction = payload["last_completed_leg_direction_sign"]
        if last_direction is not None and type(last_direction) is not int:
            _fail(
                "bounded_frame3d_checkpoint_artifact_numeric_domain_mismatch",
                "/last_completed_leg_direction_sign",
                "Artifact lineage integers must remain exact JSON integers.",
            )
    for integer_field in integer_fields:
        if type(payload[integer_field]) is not int:
            _fail(
                "bounded_frame3d_checkpoint_artifact_numeric_domain_mismatch",
                f"/{integer_field}",
                "Artifact control and lineage integers must remain exact JSON integers.",
            )
    artifact_hash = str(payload["artifact_hash"])
    hash_payload = dict(payload)
    hash_payload.pop("artifact_hash")
    if artifact_hash != canonical_hash(hash_payload):
        _fail(
            "bounded_frame3d_checkpoint_artifact_hash_mismatch",
            "/artifact_hash",
            "Checkpoint artifact hash does not match its canonical payload.",
        )
    canonical_bytes = canonical_json_bytes(payload) + b"\n"
    if artifact_bytes != canonical_bytes:
        _fail(
            "bounded_frame3d_checkpoint_artifact_noncanonical",
            "/restart_checkpoint_artifact",
            "Checkpoint artifact bytes are not the canonical JSON encoding.",
        )
    raw_checkpoint_payload = dict(payload["checkpoint"])
    raw_checkpoint_hash = str(raw_checkpoint_payload.pop("checkpoint_hash"))
    if raw_checkpoint_hash != canonical_hash(raw_checkpoint_payload):
        _fail(
            "bounded_frame3d_checkpoint_hash_mismatch",
            "/checkpoint/checkpoint_hash",
            "Checkpoint hash does not match its raw canonical payload.",
        )
    try:
        checkpoint = _checkpoint_from_dict(payload["checkpoint"])
    except BoundedFrame3DDirectControlError:
        raise
    except (KeyError, TypeError, ValueError, OverflowError) as error:
        _fail(
            "bounded_frame3d_checkpoint_value_invalid",
            "/checkpoint",
            str(error),
        )
    checkpoint_payload = checkpoint.to_dict()
    checkpoint_hash = str(checkpoint_payload.pop("checkpoint_hash"))
    if checkpoint_hash != canonical_hash(checkpoint_payload):
        _fail(
            "bounded_frame3d_checkpoint_hash_mismatch",
            "/checkpoint/checkpoint_hash",
            "Checkpoint hash does not match its canonical payload.",
        )
    if canonical_json_bytes(raw_checkpoint_payload) != canonical_json_bytes(
        checkpoint_payload
    ):
        _fail(
            "bounded_frame3d_checkpoint_numeric_domain_mismatch",
            "/checkpoint",
            "Raw checkpoint numbers do not round-trip through the binary64 contract.",
        )
    try:
        binding = _resume_binding_from_dict(payload["resume_binding"])
        typed_binding_payload = binding.to_dict()
    except BoundedFrame3DDirectControlError:
        raise
    except (
        StatefulCorotationalFrame3DDisplacementControlError,
        KeyError,
        OverflowError,
        TypeError,
        ValueError,
    ) as error:
        _fail(
            "bounded_frame3d_checkpoint_resume_binding_invalid",
            "/resume_binding",
            str(error),
        )
    raw_binding_payload = dict(payload["resume_binding"])
    if canonical_json_bytes(raw_binding_payload) != canonical_json_bytes(
        typed_binding_payload
    ):
        _fail(
            "bounded_frame3d_checkpoint_resume_binding_numeric_domain_mismatch",
            "/resume_binding",
            "Raw resume-binding numbers do not round-trip through the binary64 contract.",
        )
    raw_binding_hash = str(raw_binding_payload.pop("binding_hash"))
    if raw_binding_hash != canonical_hash(raw_binding_payload):
        _fail(
            "bounded_frame3d_checkpoint_resume_binding_hash_mismatch",
            "/resume_binding/binding_hash",
            "Resume-binding hash does not match its raw canonical payload.",
        )
    control_global_dof = int(payload["control_global_dof"])
    if control_global_dof >= len(checkpoint.displacement):
        _fail(
            "bounded_frame3d_checkpoint_control_dof_out_of_range",
            "/control_global_dof",
            "Control equation is outside the checkpoint displacement vector.",
        )
    expected_control_unit = (
        "m" if str(payload["control_dof"]).startswith("U") else "rad"
    )
    expected_dof_offset = FRAME_DOF_LABELS.index(payload["control_dof"])
    common_binding_mismatch = bool(
        payload["control_unit"] != expected_control_unit
        or control_global_dof % 6 != expected_dof_offset
        or checkpoint.model_hash != payload["model_hash"]
        or binding.model_hash != payload["model_hash"]
        or binding.frame_solver_contract_hash != checkpoint.solver_contract_hash
        or binding.control_global_dof != control_global_dof
        or binding.control_unit != payload["control_unit"]
        or binding.accepted_checkpoint_hash != checkpoint.checkpoint_hash
        or binding.accepted_step_index != checkpoint.step_index
        or binding.accepted_control_target
        != checkpoint.displacement[control_global_dof]
    )
    lineage_schema_mismatch = False
    if type(binding) is StatefulCorotationalFrame3DDisplacementControlResumeBinding:
        lineage_schema_mismatch = bool(
            schema_version
            != BOUNDED_FRAME3D_DIRECT_CONTROL_CHECKPOINT_SCHEMA_VERSION
        )
        if not lineage_schema_mismatch and binding.direction_sign != payload.get(
            "direction_sign"
        ):
            _fail(
                "bounded_frame3d_checkpoint_artifact_direction_mismatch",
                "/direction_sign",
                "Artifact direction does not match its internal resume binding.",
            )
    elif type(binding) is (
        StatefulCorotationalFrame3DDisplacementControlCyclicResumeBinding
    ):
        lineage_schema_mismatch = bool(
            schema_version
            != BOUNDED_FRAME3D_DIRECT_CONTROL_CYCLIC_CHECKPOINT_SCHEMA_VERSION
        )
        if not lineage_schema_mismatch:
            for lineage_field in (
                "path_mode",
                "last_completed_leg_direction_sign",
                "cumulative_reversal_count",
                "cumulative_completed_target_count",
                "accepted_target_chain_hash",
            ):
                if payload.get(lineage_field) != getattr(binding, lineage_field):
                    _fail(
                        "bounded_frame3d_checkpoint_artifact_cyclic_binding_mismatch",
                        f"/{lineage_field}",
                        "Cyclic artifact lineage does not match its resume binding.",
                    )
    if common_binding_mismatch or lineage_schema_mismatch:
        _fail(
            "bounded_frame3d_checkpoint_internal_binding_mismatch",
            "/",
            "Checkpoint, resume binding, and artifact envelope do not agree.",
        )
    return payload


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key, value in pairs:
        if key in payload:
            raise ValueError(f"duplicate JSON key: {key}")
        payload[key] = value
    return payload


def _reject_json_constant(value: str) -> NoReturn:
    raise ValueError(f"non-finite JSON token: {value}")


def _nonfinite_json_number_path(value: Any) -> str | None:
    stack: list[tuple[str, Any]] = [("", value)]
    while stack:
        path, item = stack.pop()
        if type(item) is float and not math.isfinite(item):
            return path or "/"
        if isinstance(item, dict):
            stack.extend(
                (
                    f"{path}/{str(key).replace('~', '~0').replace('/', '~1')}",
                    child,
                )
                for key, child in item.items()
            )
        elif isinstance(item, list):
            stack.extend(
                (f"{path}/{index}", child)
                for index, child in enumerate(item)
            )
    return None


def _load_schema(name: str) -> dict[str, Any]:
    path = resources.files("structural_analysis.schemas").joinpath(name)
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):  # pragma: no cover - package invariant
        raise TypeError(f"schema {name} must be an object")
    Draft202012Validator.check_schema(payload)
    return payload


def _fail(code: str, path: str, detail: str) -> NoReturn:
    raise BoundedFrame3DDirectControlError(code, path, detail)


__all__ = [
    "BOUNDED_FRAME3D_DIRECT_CONTROL_API_PROFILE",
    "BOUNDED_FRAME3D_DIRECT_CONTROL_CHECKPOINT_MAX_BYTES",
    "BOUNDED_FRAME3D_DIRECT_CONTROL_CHECKPOINT_SCHEMA_VERSION",
    "BOUNDED_FRAME3D_DIRECT_CONTROL_CLAIM_BOUNDARY",
    "BOUNDED_FRAME3D_DIRECT_CONTROL_RESULT_SCHEMA_VERSION",
    "BoundedFrame3DDirectControlConfig",
    "BoundedFrame3DDirectControlError",
    "BoundedFrame3DDirectControlResult",
    "StatefulCorotationalFrame3DDisplacementControlConfig",
    "analyze_bounded_frame3d_direct_control_model_ir",
    "validate_bounded_frame3d_direct_control_result",
]
