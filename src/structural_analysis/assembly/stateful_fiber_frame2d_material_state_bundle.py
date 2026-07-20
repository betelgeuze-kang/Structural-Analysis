"""Fail-closed projection of fiber-frame checkpoints into MaterialStateBundle.

The persisted ``StatefulFiberFrame2DCheckpoint`` remains the bounded restart
artifact. This adapter projects its ordered member -> beam integration point ->
section fiber constitutive states into the backend-neutral Engine v2
``MaterialStateBundle`` contract.

The projection is one-way and non-authoritative. It binds exact problem,
checkpoint, solver-state, source-identity, order, and byte hashes, but it does
not prove solver convergence, recompute constitutive laws, or grant numerical,
engineering, design, release, or commercial authority.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
import hashlib
import math
import re
from types import MappingProxyType
from typing import Any

from structural_analysis.assembly.stateful_fiber_frame2d import (
    StatefulFiberFrame2DProblem,
    initial_stateful_fiber_frame2d_checkpoint,
    validate_stateful_fiber_frame2d_checkpoint,
)
from structural_analysis.assembly.stateful_fiber_frame2d_state import (
    STATEFUL_FIBER_FRAME2D_CHECKPOINT_SCHEMA_VERSION,
    StatefulFiberFrame2DCheckpoint,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.engine_v2.contracts.material_state_bundle import (
    MaterialStateBundle,
    MaterialStateInput,
    commit_trial_material_state_bundle,
    create_initial_material_state_bundle,
    open_trial_material_state_bundle,
    validate_material_state_bundle,
)
from structural_analysis.materials.concrete_damage import (
    STATE_SCHEMA_VERSION as CONCRETE_DAMAGE_STATE_SCHEMA_VERSION,
)
from structural_analysis.materials.concrete_damage import ConcreteDamageState
from structural_analysis.materials.stateful_fiber_section import (
    StatefulFiberSectionState,
    StatefulRCFiberSection,
)
from structural_analysis.materials.uniaxial_plasticity import (
    STATE_SCHEMA_VERSION as STEEL_PLASTICITY_STATE_SCHEMA_VERSION,
)
from structural_analysis.materials.uniaxial_plasticity import (
    UniaxialPlasticityState,
)


FIBER_FRAME_MATERIAL_STATE_PROJECTION_SCHEMA_VERSION = (
    "stateful-fiber-frame2d-material-state-projection.v1"
)
FIBER_FRAME_MATERIAL_STATE_PROJECTION_MANIFEST_SCHEMA_VERSION = (
    "stateful-fiber-frame2d-material-state-projection-manifest.v1"
)
FIBER_FRAME_MATERIAL_STATE_ADAPTER_PROFILE = "member_beam_ip_section_fiber_order.v1"
FIBER_FRAME_MATERIAL_STATE_AUTHORITY_PROFILE = (
    "non_authoritative_checkpoint_material_state_projection.v1"
)
FIBER_FRAME_MATERIAL_STATE_CLAIM_BOUNDARY = MappingProxyType(
    {
        "checkpoint_problem_contract_bound": True,
        "checkpoint_state_hash_bound": True,
        "checkpoint_parent_hash_bound": True,
        "solver_state_hash_bound": True,
        "member_integration_point_fiber_order_bound": True,
        "constituent_state_bytes_bound": True,
        "constitutive_law_replayed": False,
        "solver_convergence_authority": False,
        "numerical_result_authority": False,
        "reaction_or_member_force_authority": False,
        "design_or_code_authority": False,
        "release_readiness": False,
        "commercial_use": False,
    }
)

_HASH_ZERO = "sha256:" + "0" * 64
_HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_MAX_INDEX = 2**31 - 1


class FiberFrameMaterialStateProjectionError(ValueError):
    """Stable fail-closed checkpoint projection error."""

    def __init__(self, code: str, path: str, message: str) -> None:
        self.code = code
        self.path = path
        self.message = message
        super().__init__(f"{code}@{path}: {message}")


@dataclass(frozen=True)
class FiberFrameMaterialStateProjectionReceipt:
    schema_version: str
    receipt_hash: str
    authority_profile: str
    adapter_profile: str
    problem_contract_hash: str
    checkpoint_schema_version: str
    checkpoint_state_hash: str
    parent_checkpoint_state_hash: str | None
    checkpoint_epoch: int
    checkpoint_step_index: int
    checkpoint_load_factor: float
    model_ir_content_hash: str
    execution_plan_hash: str
    solver_state_hash: str
    material_state_bundle_hash: str
    trial_bundle_hash: str | None
    integration_point_order_hash: str
    source_identity_hash: str
    member_count: int
    beam_integration_point_count: int
    fiber_state_count: int
    total_state_byte_length: int
    extensions: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return _receipt_payload(self, include_receipt_hash=True)


@dataclass(frozen=True)
class FiberFrameMaterialStateProjection:
    receipt: FiberFrameMaterialStateProjectionReceipt
    bundle: MaterialStateBundle

    def to_manifest(self) -> dict[str, Any]:
        validate_fiber_frame_material_state_projection_receipt(self.receipt)
        validate_material_state_bundle(self.bundle)
        if self.receipt.material_state_bundle_hash != self.bundle.bundle_hash:
            _fail(
                "fiber_frame_projection_bundle_hash_mismatch",
                "/material_state_bundle/bundle_hash",
                "Projection receipt does not bind the retained material bundle.",
            )
        return {
            "schema_version": (
                FIBER_FRAME_MATERIAL_STATE_PROJECTION_MANIFEST_SCHEMA_VERSION
            ),
            "receipt": self.receipt.to_dict(),
            "material_state_bundle": self.bundle.to_manifest(),
            "claim_boundary": dict(FIBER_FRAME_MATERIAL_STATE_CLAIM_BOUNDARY),
        }


@dataclass(frozen=True)
class _FlattenedCheckpointState:
    entries: tuple[MaterialStateInput, ...]
    source_identity_hash: str
    member_count: int
    beam_integration_point_count: int
    fiber_state_count: int
    total_state_byte_length: int


def create_initial_fiber_frame_material_state_projection(
    problem: StatefulFiberFrame2DProblem,
    checkpoint: StatefulFiberFrame2DCheckpoint,
    *,
    model_ir_content_hash: str,
    execution_plan_hash: str,
    solver_state_hash: str,
) -> FiberFrameMaterialStateProjection:
    """Project an exact epoch-zero frame checkpoint into a committed bundle."""

    validate_stateful_fiber_frame2d_checkpoint(problem, checkpoint)
    if checkpoint.epoch != 0:
        _fail(
            "fiber_frame_projection_initial_epoch_invalid",
            "/checkpoint/epoch",
            "Initial projection requires the epoch-zero checkpoint.",
        )
    expected_initial = initial_stateful_fiber_frame2d_checkpoint(problem)
    if (
        checkpoint.state_hash != expected_initial.state_hash
        or checkpoint.canonical_bytes() != expected_initial.canonical_bytes()
    ):
        _fail(
            "fiber_frame_projection_initial_checkpoint_mismatch",
            "/checkpoint",
            "Initial projection requires the exact problem genesis checkpoint.",
        )
    flattened = _flatten_checkpoint(problem, checkpoint)
    bundle = create_initial_material_state_bundle(
        bundle_id=_bundle_id("initial", problem, checkpoint),
        model_ir_content_hash=model_ir_content_hash,
        execution_plan_hash=execution_plan_hash,
        solver_state_hash=solver_state_hash,
        entries=flattened.entries,
    )
    receipt = _build_receipt(
        problem=problem,
        checkpoint=checkpoint,
        bundle=bundle,
        flattened=flattened,
        trial_bundle_hash=None,
    )
    projection = FiberFrameMaterialStateProjection(receipt=receipt, bundle=bundle)
    return validate_fiber_frame_material_state_projection(
        problem,
        checkpoint,
        projection,
    )


def advance_fiber_frame_material_state_projection(
    problem: StatefulFiberFrame2DProblem,
    parent_checkpoint: StatefulFiberFrame2DCheckpoint,
    checkpoint: StatefulFiberFrame2DCheckpoint,
    accepted_projection: FiberFrameMaterialStateProjection,
    *,
    solver_state_hash: str,
) -> FiberFrameMaterialStateProjection:
    """Project one exact committed child checkpoint from an accepted projection."""

    validate_fiber_frame_material_state_projection(
        problem,
        parent_checkpoint,
        accepted_projection,
    )
    validate_stateful_fiber_frame2d_checkpoint(problem, checkpoint)
    _validate_checkpoint_transition(parent_checkpoint, checkpoint)
    flattened = _flatten_checkpoint(problem, checkpoint)
    trial = open_trial_material_state_bundle(
        accepted_projection.bundle,
        solver_state_hash=solver_state_hash,
        entries=flattened.entries,
        bundle_id=_bundle_id("trial", problem, checkpoint),
    )
    committed = commit_trial_material_state_bundle(
        accepted_projection.bundle,
        trial,
        solver_state_hash=solver_state_hash,
        bundle_id=_bundle_id("committed", problem, checkpoint),
    )
    receipt = _build_receipt(
        problem=problem,
        checkpoint=checkpoint,
        bundle=committed,
        flattened=flattened,
        trial_bundle_hash=trial.bundle_hash,
    )
    projection = FiberFrameMaterialStateProjection(
        receipt=receipt,
        bundle=committed,
    )
    return validate_fiber_frame_material_state_projection(
        problem,
        checkpoint,
        projection,
        parent_checkpoint=parent_checkpoint,
        accepted_projection=accepted_projection,
    )


def validate_fiber_frame_material_state_projection_receipt(
    receipt: FiberFrameMaterialStateProjectionReceipt,
) -> FiberFrameMaterialStateProjectionReceipt:
    if type(receipt) is not FiberFrameMaterialStateProjectionReceipt:
        _fail(
            "fiber_frame_projection_receipt_type_invalid",
            "/receipt",
            "Expected FiberFrameMaterialStateProjectionReceipt.",
        )
    if receipt.schema_version != FIBER_FRAME_MATERIAL_STATE_PROJECTION_SCHEMA_VERSION:
        _fail(
            "fiber_frame_projection_schema_invalid",
            "/receipt/schema_version",
            "Unsupported fiber-frame material-state projection schema.",
        )
    if receipt.authority_profile != FIBER_FRAME_MATERIAL_STATE_AUTHORITY_PROFILE:
        _fail(
            "fiber_frame_projection_authority_profile_invalid",
            "/receipt/authority_profile",
            "Checkpoint projection cannot acquire result authority.",
        )
    if receipt.adapter_profile != FIBER_FRAME_MATERIAL_STATE_ADAPTER_PROFILE:
        _fail(
            "fiber_frame_projection_adapter_profile_invalid",
            "/receipt/adapter_profile",
            "Unsupported fiber-frame material-state adapter profile.",
        )
    if (
        receipt.checkpoint_schema_version
        != STATEFUL_FIBER_FRAME2D_CHECKPOINT_SCHEMA_VERSION
    ):
        _fail(
            "fiber_frame_projection_checkpoint_schema_invalid",
            "/receipt/checkpoint_schema_version",
            "Unsupported checkpoint schema.",
        )
    for path, value in (
        ("/receipt/receipt_hash", receipt.receipt_hash),
        ("/receipt/problem_contract_hash", receipt.problem_contract_hash),
        ("/receipt/checkpoint_state_hash", receipt.checkpoint_state_hash),
        ("/receipt/model_ir_content_hash", receipt.model_ir_content_hash),
        ("/receipt/execution_plan_hash", receipt.execution_plan_hash),
        ("/receipt/solver_state_hash", receipt.solver_state_hash),
        (
            "/receipt/material_state_bundle_hash",
            receipt.material_state_bundle_hash,
        ),
        (
            "/receipt/integration_point_order_hash",
            receipt.integration_point_order_hash,
        ),
        ("/receipt/source_identity_hash", receipt.source_identity_hash),
    ):
        _require_hash(value, path)
    if receipt.parent_checkpoint_state_hash is not None:
        _require_hash(
            receipt.parent_checkpoint_state_hash,
            "/receipt/parent_checkpoint_state_hash",
        )
    if receipt.trial_bundle_hash is not None:
        _require_hash(receipt.trial_bundle_hash, "/receipt/trial_bundle_hash")
    epoch = _require_index(receipt.checkpoint_epoch, "/receipt/checkpoint_epoch")
    step = _require_index(
        receipt.checkpoint_step_index,
        "/receipt/checkpoint_step_index",
    )
    if step != epoch:
        _fail(
            "fiber_frame_projection_step_epoch_mismatch",
            "/receipt/checkpoint_step_index",
            "Checkpoint step index must equal its epoch.",
        )
    if (
        isinstance(receipt.checkpoint_load_factor, bool)
        or type(receipt.checkpoint_load_factor) not in (int, float)
        or not math.isfinite(float(receipt.checkpoint_load_factor))
    ):
        _fail(
            "fiber_frame_projection_load_factor_invalid",
            "/receipt/checkpoint_load_factor",
            "Checkpoint load factor must be finite.",
        )
    for path, value in (
        ("/receipt/member_count", receipt.member_count),
        (
            "/receipt/beam_integration_point_count",
            receipt.beam_integration_point_count,
        ),
        ("/receipt/fiber_state_count", receipt.fiber_state_count),
        (
            "/receipt/total_state_byte_length",
            receipt.total_state_byte_length,
        ),
    ):
        normalized = _require_index(value, path)
        if normalized < 1:
            _fail(
                "fiber_frame_projection_count_invalid",
                path,
                "Projection counts and byte lengths must be positive.",
            )
    if epoch == 0:
        if (
            receipt.parent_checkpoint_state_hash is not None
            or receipt.trial_bundle_hash is not None
        ):
            _fail(
                "fiber_frame_projection_initial_lineage_invalid",
                "/receipt",
                "Epoch-zero projection cannot identify checkpoint or trial parents.",
            )
    elif (
        receipt.parent_checkpoint_state_hash is None
        or receipt.trial_bundle_hash is None
    ):
        _fail(
            "fiber_frame_projection_parent_missing",
            "/receipt",
            "Positive-epoch projection requires checkpoint and trial parents.",
        )
    if not isinstance(receipt.extensions, MappingProxyType) or receipt.extensions:
        _fail(
            "fiber_frame_projection_extensions_invalid",
            "/receipt/extensions",
            "Projection v1 requires immutable empty extensions.",
        )
    expected_hash = canonical_hash(
        _receipt_payload(receipt, include_receipt_hash=False)
    )
    if receipt.receipt_hash != expected_hash:
        _fail(
            "fiber_frame_projection_receipt_hash_mismatch",
            "/receipt/receipt_hash",
            "Projection receipt hash does not match canonical content.",
        )
    return receipt


def validate_fiber_frame_material_state_projection(
    problem: StatefulFiberFrame2DProblem,
    checkpoint: StatefulFiberFrame2DCheckpoint,
    projection: FiberFrameMaterialStateProjection,
    *,
    parent_checkpoint: StatefulFiberFrame2DCheckpoint | None = None,
    accepted_projection: FiberFrameMaterialStateProjection | None = None,
) -> FiberFrameMaterialStateProjection:
    """Validate checkpoint bytes, source order, bundle bytes, and optional lineage."""

    if type(projection) is not FiberFrameMaterialStateProjection:
        _fail(
            "fiber_frame_projection_type_invalid",
            "/",
            "Expected FiberFrameMaterialStateProjection.",
        )
    validate_stateful_fiber_frame2d_checkpoint(problem, checkpoint)
    receipt = validate_fiber_frame_material_state_projection_receipt(projection.receipt)
    bundle = validate_material_state_bundle(projection.bundle)
    flattened = _flatten_checkpoint(problem, checkpoint)

    expected_receipt_values = {
        "problem_contract_hash": problem.contract_hash,
        "checkpoint_state_hash": checkpoint.state_hash,
        "parent_checkpoint_state_hash": checkpoint.parent_state_hash,
        "checkpoint_epoch": checkpoint.epoch,
        "checkpoint_step_index": checkpoint.step_index,
        "checkpoint_load_factor": checkpoint.load_factor,
        "model_ir_content_hash": bundle.model_ir_content_hash,
        "execution_plan_hash": bundle.execution_plan_hash,
        "solver_state_hash": bundle.solver_state_hash,
        "material_state_bundle_hash": bundle.bundle_hash,
        "integration_point_order_hash": bundle.integration_point_order_hash,
        "source_identity_hash": flattened.source_identity_hash,
        "member_count": flattened.member_count,
        "beam_integration_point_count": (flattened.beam_integration_point_count),
        "fiber_state_count": flattened.fiber_state_count,
        "total_state_byte_length": flattened.total_state_byte_length,
    }
    for name, expected in expected_receipt_values.items():
        if getattr(receipt, name) != expected:
            _fail(
                "fiber_frame_projection_receipt_binding_mismatch",
                f"/receipt/{name}",
                "Projection receipt does not match the exact problem, checkpoint, or bundle.",
            )
    if bundle.role != "committed" or bundle.epoch != checkpoint.epoch:
        _fail(
            "fiber_frame_projection_bundle_role_epoch_invalid",
            "/material_state_bundle",
            "Projection requires a committed material bundle at the checkpoint epoch.",
        )
    expected_bundle_id = _bundle_id(
        "initial" if checkpoint.epoch == 0 else "committed",
        problem,
        checkpoint,
    )
    if bundle.bundle_id != expected_bundle_id:
        _fail(
            "fiber_frame_projection_bundle_id_mismatch",
            "/material_state_bundle/bundle_id",
            "Material bundle ID does not bind the exact problem and checkpoint.",
        )
    _validate_bundle_entries_against_checkpoint(bundle, flattened)

    if checkpoint.epoch == 0:
        if parent_checkpoint is not None or accepted_projection is not None:
            _fail(
                "fiber_frame_projection_initial_parent_supplied",
                "/",
                "Epoch-zero projection cannot accept parent projection inputs.",
            )
        expected_bundle = create_initial_material_state_bundle(
            bundle_id=expected_bundle_id,
            model_ir_content_hash=bundle.model_ir_content_hash,
            execution_plan_hash=bundle.execution_plan_hash,
            solver_state_hash=bundle.solver_state_hash,
            entries=flattened.entries,
        )
        _require_exact_bundle(bundle, expected_bundle)
    else:
        if bundle.parent_bundle_hash != receipt.trial_bundle_hash:
            _fail(
                "fiber_frame_projection_trial_parent_mismatch",
                "/material_state_bundle/parent_bundle_hash",
                "Committed material bundle is not parented by the recorded trial.",
            )
        if (parent_checkpoint is None) != (accepted_projection is None):
            _fail(
                "fiber_frame_projection_parent_inputs_incomplete",
                "/",
                "Parent checkpoint and accepted projection must be supplied together.",
            )
        if parent_checkpoint is not None and accepted_projection is not None:
            validate_fiber_frame_material_state_projection(
                problem,
                parent_checkpoint,
                accepted_projection,
            )
            _validate_checkpoint_transition(parent_checkpoint, checkpoint)
            if (
                accepted_projection.receipt.checkpoint_state_hash
                != parent_checkpoint.state_hash
            ):
                _fail(
                    "fiber_frame_projection_accepted_checkpoint_mismatch",
                    "/accepted_projection/receipt/checkpoint_state_hash",
                    "Accepted projection does not bind the supplied parent checkpoint.",
                )
            trial = open_trial_material_state_bundle(
                accepted_projection.bundle,
                solver_state_hash=bundle.solver_state_hash,
                entries=flattened.entries,
                bundle_id=_bundle_id("trial", problem, checkpoint),
            )
            if trial.bundle_hash != receipt.trial_bundle_hash:
                _fail(
                    "fiber_frame_projection_trial_hash_mismatch",
                    "/receipt/trial_bundle_hash",
                    "Recorded trial hash does not match the accepted material parent.",
                )
            expected_bundle = commit_trial_material_state_bundle(
                accepted_projection.bundle,
                trial,
                solver_state_hash=bundle.solver_state_hash,
                bundle_id=expected_bundle_id,
            )
            _require_exact_bundle(bundle, expected_bundle)
        elif any(row.parent_state_data_hash is None for row in bundle.entries):
            _fail(
                "fiber_frame_projection_entry_parent_missing",
                "/material_state_bundle/entries",
                "Positive-epoch constituent states require parent data hashes.",
            )
    return projection


def _flatten_checkpoint(
    problem: StatefulFiberFrame2DProblem,
    checkpoint: StatefulFiberFrame2DCheckpoint,
) -> _FlattenedCheckpointState:
    validate_stateful_fiber_frame2d_checkpoint(problem, checkpoint)
    entries: list[MaterialStateInput] = []
    source_rows: list[dict[str, Any]] = []
    integration_point_count = 0
    checkpoint_digest = checkpoint.state_hash.split(":", 1)[1]

    for member_index, (member, element_state) in enumerate(
        zip(problem.members, checkpoint.element_states, strict=True)
    ):
        section = member.element.section
        if type(section) is not StatefulRCFiberSection:
            _fail(
                "fiber_frame_projection_section_type_unsupported",
                f"/problem/members/{member_index}/section",
                "Adapter v1 supports exact StatefulRCFiberSection only.",
            )
        points = member.element.quadrature[0]
        if len(points) != len(element_state.integration_point_states):
            _fail(
                "fiber_frame_projection_integration_point_count_mismatch",
                f"/checkpoint/element_states/{member_index}",
                "Element quadrature and checkpoint integration-point counts differ.",
            )
        for integration_point_index, (xi, section_state) in enumerate(
            zip(points, element_state.integration_point_states, strict=True)
        ):
            integration_point_count += 1
            if type(section_state) is not StatefulFiberSectionState:
                _fail(
                    "fiber_frame_projection_section_state_type_unsupported",
                    (
                        f"/checkpoint/element_states/{member_index}/"
                        f"integration_point_states/{integration_point_index}"
                    ),
                    "Adapter v1 supports exact StatefulFiberSectionState only.",
                )
            section.validate_state(section_state)
            for fiber_index, (fiber, fiber_state) in enumerate(
                zip(section.fibers, section_state.fiber_states, strict=True)
            ):
                if fiber.material_kind == "steel":
                    if type(fiber_state) is not UniaxialPlasticityState:
                        _fail(
                            "fiber_frame_projection_material_state_type_mismatch",
                            _fiber_path(
                                member_index,
                                integration_point_index,
                                fiber_index,
                            ),
                            "Steel fiber does not retain UniaxialPlasticityState.",
                        )
                    material_type_id = section.steel.material_id
                    material_schema_version = STEEL_PLASTICITY_STATE_SCHEMA_VERSION
                else:
                    if type(fiber_state) is not ConcreteDamageState:
                        _fail(
                            "fiber_frame_projection_material_state_type_mismatch",
                            _fiber_path(
                                member_index,
                                integration_point_index,
                                fiber_index,
                            ),
                            "Concrete fiber does not retain ConcreteDamageState.",
                        )
                    material_type_id = section.concrete.material_id
                    material_schema_version = CONCRETE_DAMAGE_STATE_SCHEMA_VERSION
                state_bytes = fiber_state.canonical_bytes()
                if _data_hash(state_bytes) != fiber_state.state_hash:
                    _fail(
                        "fiber_frame_projection_material_state_hash_mismatch",
                        _fiber_path(
                            member_index,
                            integration_point_index,
                            fiber_index,
                        ),
                        "Fiber state hash does not match its canonical bytes.",
                    )
                entries.append(
                    MaterialStateInput(
                        entity_id=f"member.{member_index:04d}",
                        integration_point_id=(
                            f"ip.{integration_point_index:04d}.fiber.{fiber_index:04d}"
                        ),
                        material_type_id=material_type_id,
                        material_schema_version=material_schema_version,
                        state_bytes=state_bytes,
                        artifact_uri=(
                            "artifact://stateful-fiber-frame2d-material-state/"
                            f"{checkpoint_digest}/member/{member_index}/"
                            f"ip/{integration_point_index}/fiber/{fiber_index}.bin"
                        ),
                    )
                )
                source_rows.append(
                    {
                        "member_index": member_index,
                        "member_id": member.member_id,
                        "element_contract_hash": member.element.contract_hash,
                        "integration_point_index": integration_point_index,
                        "integration_point_xi": float(xi),
                        "section_id": section.section_id,
                        "section_contract_hash": section.contract_hash,
                        "fiber_index": fiber_index,
                        "fiber_id": fiber.fiber_id,
                        "fiber_y_m": fiber.y_m,
                        "fiber_area_m2": fiber.area_m2,
                        "material_kind": fiber.material_kind,
                        "material_type_id": material_type_id,
                        "material_schema_version": material_schema_version,
                    }
                )
    if not entries:
        _fail(
            "fiber_frame_projection_entries_empty",
            "/checkpoint/element_states",
            "Checkpoint does not contain any supported constituent states.",
        )
    return _FlattenedCheckpointState(
        entries=tuple(entries),
        source_identity_hash=canonical_hash(source_rows),
        member_count=len(problem.members),
        beam_integration_point_count=integration_point_count,
        fiber_state_count=len(entries),
        total_state_byte_length=sum(len(row.state_bytes) for row in entries),
    )


def _build_receipt(
    *,
    problem: StatefulFiberFrame2DProblem,
    checkpoint: StatefulFiberFrame2DCheckpoint,
    bundle: MaterialStateBundle,
    flattened: _FlattenedCheckpointState,
    trial_bundle_hash: str | None,
) -> FiberFrameMaterialStateProjectionReceipt:
    provisional = FiberFrameMaterialStateProjectionReceipt(
        schema_version=FIBER_FRAME_MATERIAL_STATE_PROJECTION_SCHEMA_VERSION,
        receipt_hash=_HASH_ZERO,
        authority_profile=FIBER_FRAME_MATERIAL_STATE_AUTHORITY_PROFILE,
        adapter_profile=FIBER_FRAME_MATERIAL_STATE_ADAPTER_PROFILE,
        problem_contract_hash=problem.contract_hash,
        checkpoint_schema_version=(STATEFUL_FIBER_FRAME2D_CHECKPOINT_SCHEMA_VERSION),
        checkpoint_state_hash=checkpoint.state_hash,
        parent_checkpoint_state_hash=checkpoint.parent_state_hash,
        checkpoint_epoch=checkpoint.epoch,
        checkpoint_step_index=checkpoint.step_index,
        checkpoint_load_factor=checkpoint.load_factor,
        model_ir_content_hash=bundle.model_ir_content_hash,
        execution_plan_hash=bundle.execution_plan_hash,
        solver_state_hash=bundle.solver_state_hash,
        material_state_bundle_hash=bundle.bundle_hash,
        trial_bundle_hash=trial_bundle_hash,
        integration_point_order_hash=bundle.integration_point_order_hash,
        source_identity_hash=flattened.source_identity_hash,
        member_count=flattened.member_count,
        beam_integration_point_count=flattened.beam_integration_point_count,
        fiber_state_count=flattened.fiber_state_count,
        total_state_byte_length=flattened.total_state_byte_length,
        extensions=MappingProxyType({}),
    )
    receipt = replace(
        provisional,
        receipt_hash=canonical_hash(
            _receipt_payload(provisional, include_receipt_hash=False)
        ),
    )
    return validate_fiber_frame_material_state_projection_receipt(receipt)


def _receipt_payload(
    receipt: FiberFrameMaterialStateProjectionReceipt,
    *,
    include_receipt_hash: bool,
) -> dict[str, Any]:
    payload = {
        "schema_version": receipt.schema_version,
        "receipt_hash": receipt.receipt_hash,
        "authority_profile": receipt.authority_profile,
        "adapter_profile": receipt.adapter_profile,
        "bindings": {
            "problem_contract_hash": receipt.problem_contract_hash,
            "checkpoint_schema_version": receipt.checkpoint_schema_version,
            "checkpoint_state_hash": receipt.checkpoint_state_hash,
            "parent_checkpoint_state_hash": (receipt.parent_checkpoint_state_hash),
            "model_ir_content_hash": receipt.model_ir_content_hash,
            "execution_plan_hash": receipt.execution_plan_hash,
            "solver_state_hash": receipt.solver_state_hash,
            "material_state_bundle_hash": receipt.material_state_bundle_hash,
            "trial_bundle_hash": receipt.trial_bundle_hash,
            "integration_point_order_hash": (receipt.integration_point_order_hash),
            "source_identity_hash": receipt.source_identity_hash,
        },
        "checkpoint": {
            "epoch": receipt.checkpoint_epoch,
            "step_index": receipt.checkpoint_step_index,
            "load_factor": receipt.checkpoint_load_factor,
        },
        "counts": {
            "member_count": receipt.member_count,
            "beam_integration_point_count": (receipt.beam_integration_point_count),
            "fiber_state_count": receipt.fiber_state_count,
            "total_state_byte_length": receipt.total_state_byte_length,
        },
        "claim_boundary": dict(FIBER_FRAME_MATERIAL_STATE_CLAIM_BOUNDARY),
        "extensions": dict(receipt.extensions),
    }
    if not include_receipt_hash:
        payload.pop("receipt_hash")
    return payload


def _validate_bundle_entries_against_checkpoint(
    bundle: MaterialStateBundle,
    flattened: _FlattenedCheckpointState,
) -> None:
    if bundle.entry_count != len(flattened.entries):
        _fail(
            "fiber_frame_projection_entry_count_mismatch",
            "/material_state_bundle/entry_count",
            "Material bundle entry count does not match checkpoint constituent states.",
        )
    for index, (source, descriptor) in enumerate(
        zip(flattened.entries, bundle.entries, strict=True)
    ):
        expected_identity = (
            source.entity_id,
            source.integration_point_id,
            source.material_type_id,
            source.material_schema_version,
            source.artifact_uri,
        )
        actual_identity = (
            descriptor.entity_id,
            descriptor.integration_point_id,
            descriptor.material_type_id,
            descriptor.material_schema_version,
            descriptor.artifact_uri,
        )
        if actual_identity != expected_identity:
            _fail(
                "fiber_frame_projection_entry_identity_mismatch",
                f"/material_state_bundle/entries/{index}",
                "Material entry identity does not match checkpoint source order.",
            )
        if descriptor.data_hash != _data_hash(source.state_bytes):
            _fail(
                "fiber_frame_projection_entry_data_hash_mismatch",
                f"/material_state_bundle/entries/{index}/data_hash",
                "Material entry data hash does not match checkpoint bytes.",
            )
        if bundle.state_bytes(index) != source.state_bytes:
            _fail(
                "fiber_frame_projection_entry_bytes_mismatch",
                f"/material_state_bundle/entries/{index}",
                "Retained material bytes do not match checkpoint fiber state.",
            )


def _require_exact_bundle(
    actual: MaterialStateBundle,
    expected: MaterialStateBundle,
) -> None:
    if actual.to_manifest() != expected.to_manifest() or tuple(
        actual.state_bytes(index) for index in range(actual.entry_count)
    ) != tuple(expected.state_bytes(index) for index in range(expected.entry_count)):
        _fail(
            "fiber_frame_projection_bundle_replay_mismatch",
            "/material_state_bundle",
            "Material bundle does not replay exactly from the checkpoint projection.",
        )


def _validate_checkpoint_transition(
    parent: StatefulFiberFrame2DCheckpoint,
    child: StatefulFiberFrame2DCheckpoint,
) -> None:
    if child.epoch != parent.epoch + 1 or child.step_index != parent.step_index + 1:
        _fail(
            "fiber_frame_projection_checkpoint_epoch_transition_invalid",
            "/checkpoint/epoch",
            "Child checkpoint must advance exactly one epoch and step.",
        )
    if child.parent_state_hash != parent.state_hash:
        _fail(
            "fiber_frame_projection_checkpoint_parent_mismatch",
            "/checkpoint/parent_state_hash",
            "Child checkpoint is not parented by the supplied accepted checkpoint.",
        )
    if (
        child.case_id != parent.case_id
        or child.problem_contract_hash != parent.problem_contract_hash
    ):
        _fail(
            "fiber_frame_projection_checkpoint_problem_mismatch",
            "/checkpoint/problem_contract_hash",
            "Parent and child checkpoints do not belong to the same problem.",
        )


def _bundle_id(
    role: str,
    problem: StatefulFiberFrame2DProblem,
    checkpoint: StatefulFiberFrame2DCheckpoint,
) -> str:
    if role not in {"initial", "trial", "committed"}:
        _fail(
            "fiber_frame_projection_bundle_role_invalid",
            "/material_state_bundle/bundle_id",
            "Unknown projection bundle role.",
        )
    problem_digest = problem.contract_hash.split(":", 1)[1][:16]
    checkpoint_digest = checkpoint.state_hash.split(":", 1)[1][:16]
    return f"ffms.{role}.e{checkpoint.epoch}.p{problem_digest}.c{checkpoint_digest}"


def _fiber_path(
    member_index: int,
    integration_point_index: int,
    fiber_index: int,
) -> str:
    return (
        f"/checkpoint/element_states/{member_index}/"
        f"integration_point_states/{integration_point_index}/"
        f"fiber_states/{fiber_index}"
    )


def _data_hash(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _require_hash(value: Any, path: str) -> str:
    normalized = str(value).strip()
    if not _HASH_PATTERN.fullmatch(normalized):
        _fail(
            "fiber_frame_projection_hash_invalid",
            path,
            "Expected a lowercase sha256:<hex> hash.",
        )
    return normalized


def _require_index(value: Any, path: str) -> int:
    if type(value) is not int or value < 0 or value > _MAX_INDEX:
        _fail(
            "fiber_frame_projection_index_invalid",
            path,
            "Expected a non-negative 32-bit integer.",
        )
    return value


def _fail(code: str, path: str, message: str) -> None:
    raise FiberFrameMaterialStateProjectionError(code, path, message)


__all__ = [
    "FIBER_FRAME_MATERIAL_STATE_ADAPTER_PROFILE",
    "FIBER_FRAME_MATERIAL_STATE_AUTHORITY_PROFILE",
    "FIBER_FRAME_MATERIAL_STATE_CLAIM_BOUNDARY",
    "FIBER_FRAME_MATERIAL_STATE_PROJECTION_MANIFEST_SCHEMA_VERSION",
    "FIBER_FRAME_MATERIAL_STATE_PROJECTION_SCHEMA_VERSION",
    "FiberFrameMaterialStateProjection",
    "FiberFrameMaterialStateProjectionError",
    "FiberFrameMaterialStateProjectionReceipt",
    "advance_fiber_frame_material_state_projection",
    "create_initial_fiber_frame_material_state_projection",
    "validate_fiber_frame_material_state_projection",
    "validate_fiber_frame_material_state_projection_receipt",
]
