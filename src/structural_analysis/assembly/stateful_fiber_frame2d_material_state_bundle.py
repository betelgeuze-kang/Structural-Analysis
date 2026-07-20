"""One-way MaterialStateBundle projection for bounded fiber-frame checkpoints."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from types import MappingProxyType
from typing import Literal

from structural_analysis.assembly.stateful_fiber_frame2d import (
    StatefulFiberFrame2DProblem,
    initial_stateful_fiber_frame2d_checkpoint,
    validate_stateful_fiber_frame2d_checkpoint,
)
from structural_analysis.assembly.stateful_fiber_frame2d_state import (
    StatefulFiberFrame2DCheckpoint,
)
from structural_analysis.engine_v2.contracts.material_state_bundle import (
    MaterialStateBundle,
    MaterialStateBundleError,
    MaterialStateInput,
    commit_trial_material_state_bundle,
    create_initial_material_state_bundle,
    open_trial_material_state_bundle,
    rollback_trial_material_state_bundle,
    validate_material_state_bundle,
    validate_material_state_entry_bytes,
)
from structural_analysis.materials.concrete_damage import (
    STATE_SCHEMA_VERSION as CONCRETE_DAMAGE_STATE_SCHEMA_VERSION,
    ConcreteDamageState,
)
from structural_analysis.materials.stateful_fiber_section import (
    StatefulFiberSectionState,
    StatefulRCFiberSection,
)
from structural_analysis.materials.uniaxial_plasticity import (
    STATE_SCHEMA_VERSION as STEEL_STATE_SCHEMA_VERSION,
    UniaxialPlasticityState,
)


STATEFUL_FIBER_FRAME2D_MATERIAL_STATE_ADAPTER_PROFILE = (
    "stateful-fiber-frame2d-material-state-bundle-adapter.v1"
)
STATEFUL_FIBER_FRAME2D_MATERIAL_STATE_ADAPTER_AUTHORITY_PROFILE = (
    "non_authoritative_one_way_material_state_projection.v1"
)
STATEFUL_FIBER_FRAME2D_MATERIAL_STATE_ADAPTER_CLAIM_BOUNDARY = MappingProxyType(
    {
        "exact_checkpoint_identity_bound": True,
        "exact_fiber_state_bytes_bound": True,
        "material_entry_order_bound": True,
        "accepted_trial_commit_lineage_bound": True,
        "model_ir_equivalence_verified": False,
        "constitutive_transition_verified": False,
        "checkpoint_restoration_authority": False,
        "solver_convergence_authority": False,
        "numerical_result_authority": False,
        "engineering_result_authority": False,
        "release_readiness": False,
        "commercial_use": False,
    }
)

_IDENTITY_HASH_DOMAIN = (
    b"structural-analysis/stateful-fiber-frame2d-material-entry-identity/v1\0"
)


class StatefulFiberFrame2DMaterialStateAdapterError(MaterialStateBundleError):
    """Stable fail-closed error for the bounded one-way adapter."""


@dataclass(frozen=True)
class StatefulFiberFrame2DMaterialStateBundleTransition:
    """One accepted-to-trial-to-committed bundle transition for a checkpoint."""

    accepted_bundle_hash: str
    parent_checkpoint_state_hash: str
    checkpoint_state_hash: str
    trial_bundle: MaterialStateBundle
    committed_bundle: MaterialStateBundle
    adapter_profile: Literal[
        "stateful-fiber-frame2d-material-state-bundle-adapter.v1"
    ] = "stateful-fiber-frame2d-material-state-bundle-adapter.v1"
    authority_profile: Literal[
        "non_authoritative_one_way_material_state_projection.v1"
    ] = "non_authoritative_one_way_material_state_projection.v1"


def create_initial_stateful_fiber_frame2d_material_state_bundle(
    problem: StatefulFiberFrame2DProblem,
    checkpoint: StatefulFiberFrame2DCheckpoint,
    *,
    model_ir_content_hash: str,
    execution_plan_hash: str,
    solver_state_hash: str,
) -> MaterialStateBundle:
    """Project the exact epoch-zero checkpoint into a descriptor-first bundle."""

    _validate_checkpoint(problem, checkpoint, path="/checkpoint")
    expected_initial = initial_stateful_fiber_frame2d_checkpoint(problem)
    if (
        checkpoint.state_hash != expected_initial.state_hash
        or checkpoint.canonical_bytes() != expected_initial.canonical_bytes()
    ):
        _fail(
            "fiber_frame_material_initial_checkpoint_mismatch",
            "/checkpoint",
            "Initial projection requires the exact problem genesis checkpoint.",
        )
    try:
        bundle = create_initial_material_state_bundle(
            bundle_id=_bundle_id("committed", checkpoint),
            model_ir_content_hash=model_ir_content_hash,
            execution_plan_hash=execution_plan_hash,
            solver_state_hash=solver_state_hash,
            entries=_material_state_inputs(problem, checkpoint),
        )
    except MaterialStateBundleError as exc:
        _fail(
            "fiber_frame_material_initial_bundle_invalid",
            "/material_state_bundle",
            "Initial MaterialStateBundle construction failed.",
            cause=exc,
        )
    return validate_stateful_fiber_frame2d_material_state_bundle_projection(
        problem,
        checkpoint,
        bundle,
        expected_role="committed",
        model_ir_content_hash=model_ir_content_hash,
        execution_plan_hash=execution_plan_hash,
        solver_state_hash=solver_state_hash,
    )


def adapt_stateful_fiber_frame2d_checkpoint_to_material_state_bundle(
    problem: StatefulFiberFrame2DProblem,
    parent_checkpoint: StatefulFiberFrame2DCheckpoint,
    checkpoint: StatefulFiberFrame2DCheckpoint,
    accepted_bundle: MaterialStateBundle,
    *,
    trial_solver_state_hash: str,
    committed_solver_state_hash: str,
) -> StatefulFiberFrame2DMaterialStateBundleTransition:
    """Project one exact successor through MaterialStateBundle trial and commit."""

    _validate_checkpoint_transition(problem, parent_checkpoint, checkpoint)
    accepted_bundle = _require_material_state_bundle(
        accepted_bundle,
        path="/accepted_bundle",
    )
    validate_stateful_fiber_frame2d_material_state_bundle_projection(
        problem,
        parent_checkpoint,
        accepted_bundle,
        expected_role="committed",
        model_ir_content_hash=accepted_bundle.model_ir_content_hash,
        execution_plan_hash=accepted_bundle.execution_plan_hash,
        solver_state_hash=accepted_bundle.solver_state_hash,
    )
    try:
        trial_bundle = open_trial_material_state_bundle(
            accepted_bundle,
            solver_state_hash=trial_solver_state_hash,
            entries=_material_state_inputs(problem, checkpoint),
            bundle_id=_bundle_id("trial", checkpoint),
        )
        committed_bundle = commit_trial_material_state_bundle(
            accepted_bundle,
            trial_bundle,
            solver_state_hash=committed_solver_state_hash,
            bundle_id=_bundle_id("committed", checkpoint),
        )
    except MaterialStateBundleError as exc:
        _fail(
            "fiber_frame_material_transition_bundle_invalid",
            "/material_state_bundle",
            "MaterialStateBundle trial or commit construction failed.",
            cause=exc,
        )
    transition = StatefulFiberFrame2DMaterialStateBundleTransition(
        accepted_bundle_hash=accepted_bundle.bundle_hash,
        parent_checkpoint_state_hash=parent_checkpoint.state_hash,
        checkpoint_state_hash=checkpoint.state_hash,
        trial_bundle=trial_bundle,
        committed_bundle=committed_bundle,
    )
    return validate_stateful_fiber_frame2d_material_state_bundle_transition(
        problem,
        parent_checkpoint,
        checkpoint,
        accepted_bundle,
        transition,
    )


def validate_stateful_fiber_frame2d_material_state_bundle_projection(
    problem: StatefulFiberFrame2DProblem,
    checkpoint: StatefulFiberFrame2DCheckpoint,
    bundle: MaterialStateBundle,
    *,
    expected_role: Literal["committed", "trial"],
    model_ir_content_hash: str,
    execution_plan_hash: str,
    solver_state_hash: str,
) -> MaterialStateBundle:
    """Validate exact fiber bytes and caller-supplied Engine v2 bindings."""

    _validate_checkpoint(problem, checkpoint, path="/checkpoint")
    bundle = _require_material_state_bundle(bundle, path="/material_state_bundle")
    try:
        validate_material_state_bundle(bundle)
    except MaterialStateBundleError as exc:
        _fail(
            "fiber_frame_material_bundle_invalid",
            "/material_state_bundle",
            "MaterialStateBundle validation failed.",
            cause=exc,
        )
    if bundle.role != expected_role:
        _fail(
            "fiber_frame_material_bundle_role_mismatch",
            "/material_state_bundle/role",
            "Bundle role does not match the requested checkpoint projection.",
        )
    if bundle.epoch != checkpoint.epoch:
        _fail(
            "fiber_frame_material_bundle_epoch_mismatch",
            "/material_state_bundle/epoch",
            "Bundle epoch does not match the checkpoint epoch.",
        )
    if bundle.bundle_id != _bundle_id(expected_role, checkpoint):
        _fail(
            "fiber_frame_material_bundle_checkpoint_binding_mismatch",
            "/material_state_bundle/bundle_id",
            "Bundle ID does not bind the exact checkpoint state hash.",
        )
    for path, actual, expected in (
        (
            "/material_state_bundle/bindings/model_ir_content_hash",
            bundle.model_ir_content_hash,
            model_ir_content_hash,
        ),
        (
            "/material_state_bundle/bindings/execution_plan_hash",
            bundle.execution_plan_hash,
            execution_plan_hash,
        ),
        (
            "/material_state_bundle/bindings/solver_state_hash",
            bundle.solver_state_hash,
            solver_state_hash,
        ),
    ):
        if actual != expected:
            _fail(
                "fiber_frame_material_bundle_engine_binding_mismatch",
                path,
                "Bundle Engine v2 binding does not match the expected hash.",
            )

    expected_inputs = _material_state_inputs(problem, checkpoint)
    if bundle.entry_count != len(expected_inputs):
        _fail(
            "fiber_frame_material_bundle_entry_count_mismatch",
            "/material_state_bundle/entry_count",
            "Bundle entry count does not match the checkpoint fiber states.",
        )
    for index, (descriptor, expected) in enumerate(
        zip(bundle.entries, expected_inputs, strict=True)
    ):
        actual_identity = (
            descriptor.entity_id,
            descriptor.integration_point_id,
            descriptor.material_type_id,
            descriptor.material_schema_version,
            descriptor.artifact_uri,
        )
        expected_identity = (
            expected.entity_id,
            expected.integration_point_id,
            expected.material_type_id,
            expected.material_schema_version,
            expected.artifact_uri,
        )
        if actual_identity != expected_identity:
            _fail(
                "fiber_frame_material_bundle_entry_identity_mismatch",
                f"/material_state_bundle/entries/{index}",
                "Bundle entry identity does not match checkpoint fiber order.",
            )
        try:
            validate_material_state_entry_bytes(
                bundle,
                index=index,
                state_bytes=expected.state_bytes,
            )
        except MaterialStateBundleError as exc:
            _fail(
                "fiber_frame_material_bundle_entry_bytes_mismatch",
                f"/material_state_bundle/entries/{index}",
                "Bundle entry bytes do not match the checkpoint fiber state.",
                cause=exc,
            )
    return bundle


def validate_stateful_fiber_frame2d_material_state_bundle_transition(
    problem: StatefulFiberFrame2DProblem,
    parent_checkpoint: StatefulFiberFrame2DCheckpoint,
    checkpoint: StatefulFiberFrame2DCheckpoint,
    accepted_bundle: MaterialStateBundle,
    transition: StatefulFiberFrame2DMaterialStateBundleTransition,
) -> StatefulFiberFrame2DMaterialStateBundleTransition:
    """Validate the checkpoint link and complete accepted/trial/commit lineage."""

    if type(transition) is not StatefulFiberFrame2DMaterialStateBundleTransition:
        _fail(
            "fiber_frame_material_transition_type_invalid",
            "/transition",
            "Expected a fiber-frame MaterialStateBundle transition.",
        )
    accepted_bundle = _require_material_state_bundle(
        accepted_bundle,
        path="/accepted_bundle",
    )
    trial_bundle = _require_material_state_bundle(
        transition.trial_bundle,
        path="/transition/trial_bundle",
    )
    committed_bundle = _require_material_state_bundle(
        transition.committed_bundle,
        path="/transition/committed_bundle",
    )
    _validate_checkpoint_transition(problem, parent_checkpoint, checkpoint)
    validate_stateful_fiber_frame2d_material_state_bundle_projection(
        problem,
        parent_checkpoint,
        accepted_bundle,
        expected_role="committed",
        model_ir_content_hash=accepted_bundle.model_ir_content_hash,
        execution_plan_hash=accepted_bundle.execution_plan_hash,
        solver_state_hash=accepted_bundle.solver_state_hash,
    )
    if (
        transition.adapter_profile
        != STATEFUL_FIBER_FRAME2D_MATERIAL_STATE_ADAPTER_PROFILE
    ):
        _fail(
            "fiber_frame_material_adapter_profile_invalid",
            "/transition/adapter_profile",
            "Transition adapter profile is invalid.",
        )
    if (
        transition.authority_profile
        != STATEFUL_FIBER_FRAME2D_MATERIAL_STATE_ADAPTER_AUTHORITY_PROFILE
    ):
        _fail(
            "fiber_frame_material_authority_profile_invalid",
            "/transition/authority_profile",
            "One-way material projection cannot acquire result authority.",
        )
    for path, actual, expected in (
        (
            "/transition/accepted_bundle_hash",
            transition.accepted_bundle_hash,
            accepted_bundle.bundle_hash,
        ),
        (
            "/transition/parent_checkpoint_state_hash",
            transition.parent_checkpoint_state_hash,
            parent_checkpoint.state_hash,
        ),
        (
            "/transition/checkpoint_state_hash",
            transition.checkpoint_state_hash,
            checkpoint.state_hash,
        ),
    ):
        if actual != expected:
            _fail(
                "fiber_frame_material_transition_binding_mismatch",
                path,
                "Transition does not bind the expected checkpoint or bundle.",
            )
    validate_stateful_fiber_frame2d_material_state_bundle_projection(
        problem,
        checkpoint,
        trial_bundle,
        expected_role="trial",
        model_ir_content_hash=accepted_bundle.model_ir_content_hash,
        execution_plan_hash=accepted_bundle.execution_plan_hash,
        solver_state_hash=trial_bundle.solver_state_hash,
    )
    validate_stateful_fiber_frame2d_material_state_bundle_projection(
        problem,
        checkpoint,
        committed_bundle,
        expected_role="committed",
        model_ir_content_hash=accepted_bundle.model_ir_content_hash,
        execution_plan_hash=accepted_bundle.execution_plan_hash,
        solver_state_hash=committed_bundle.solver_state_hash,
    )
    try:
        if (
            rollback_trial_material_state_bundle(
                accepted_bundle,
                trial_bundle,
            )
            is not accepted_bundle
        ):
            _fail(
                "fiber_frame_material_transition_rollback_mismatch",
                "/transition/trial_bundle",
                "Trial rollback did not return the exact accepted bundle.",
            )
        expected_committed = commit_trial_material_state_bundle(
            accepted_bundle,
            trial_bundle,
            solver_state_hash=committed_bundle.solver_state_hash,
            bundle_id=committed_bundle.bundle_id,
        )
    except MaterialStateBundleError as exc:
        _fail(
            "fiber_frame_material_transition_lineage_invalid",
            "/transition",
            "Accepted, trial, and committed bundle lineage is invalid.",
            cause=exc,
        )
    if expected_committed.to_manifest() != committed_bundle.to_manifest() or tuple(
        expected_committed.state_bytes(index)
        for index in range(expected_committed.entry_count)
    ) != tuple(
        committed_bundle.state_bytes(index)
        for index in range(committed_bundle.entry_count)
    ):
        _fail(
            "fiber_frame_material_transition_commit_mismatch",
            "/transition/committed_bundle",
            "Committed bundle is not the exact commit of the supplied trial.",
        )
    for index, (accepted_entry, trial_entry, committed_entry) in enumerate(
        zip(
            accepted_bundle.entries,
            trial_bundle.entries,
            committed_bundle.entries,
            strict=True,
        )
    ):
        if (
            trial_entry.parent_state_data_hash != accepted_entry.data_hash
            or committed_entry.parent_state_data_hash != accepted_entry.data_hash
        ):
            _fail(
                "fiber_frame_material_transition_entry_parent_mismatch",
                f"/transition/entries/{index}/parent_state_data_hash",
                "Projected fiber entry does not bind the accepted fiber bytes.",
            )
    return transition


def _require_material_state_bundle(
    value: object,
    *,
    path: str,
) -> MaterialStateBundle:
    if type(value) is not MaterialStateBundle:
        _fail(
            "fiber_frame_material_bundle_type_invalid",
            path,
            "Expected a MaterialStateBundle instance.",
        )
    return value


def _validate_checkpoint_transition(
    problem: StatefulFiberFrame2DProblem,
    parent_checkpoint: StatefulFiberFrame2DCheckpoint,
    checkpoint: StatefulFiberFrame2DCheckpoint,
) -> None:
    _validate_checkpoint(problem, parent_checkpoint, path="/parent_checkpoint")
    _validate_checkpoint(problem, checkpoint, path="/checkpoint")
    if checkpoint.epoch != parent_checkpoint.epoch + 1:
        _fail(
            "fiber_frame_material_checkpoint_epoch_mismatch",
            "/checkpoint/epoch",
            "Checkpoint epoch must be exactly one greater than its parent.",
        )
    if checkpoint.parent_state_hash != parent_checkpoint.state_hash:
        _fail(
            "fiber_frame_material_checkpoint_parent_mismatch",
            "/checkpoint/parent_state_hash",
            "Checkpoint does not bind the supplied parent checkpoint.",
        )


def _validate_checkpoint(
    problem: StatefulFiberFrame2DProblem,
    checkpoint: StatefulFiberFrame2DCheckpoint,
    *,
    path: str,
) -> None:
    if type(problem) is not StatefulFiberFrame2DProblem:
        _fail(
            "fiber_frame_material_problem_type_invalid",
            "/problem",
            "Expected a StatefulFiberFrame2DProblem.",
        )
    if type(checkpoint) is not StatefulFiberFrame2DCheckpoint:
        _fail(
            "fiber_frame_material_checkpoint_type_invalid",
            path,
            "Expected a StatefulFiberFrame2DCheckpoint.",
        )
    try:
        validate_stateful_fiber_frame2d_checkpoint(problem, checkpoint)
    except ValueError as exc:
        _fail(
            "fiber_frame_material_checkpoint_invalid",
            path,
            "Checkpoint does not validate against the supplied problem.",
            cause=exc,
        )


def _material_state_inputs(
    problem: StatefulFiberFrame2DProblem,
    checkpoint: StatefulFiberFrame2DCheckpoint,
) -> tuple[MaterialStateInput, ...]:
    inputs: list[MaterialStateInput] = []
    for member_index, (member, element_state) in enumerate(
        zip(problem.members, checkpoint.element_states, strict=True)
    ):
        section = member.element.section
        if type(section) is not StatefulRCFiberSection:
            _fail(
                "fiber_frame_material_section_type_unsupported",
                f"/problem/members/{member_index}/section",
                "Only the built-in StatefulRCFiberSection is supported.",
            )
        entity_id = _stable_identity(
            "frame.member",
            member_index,
            (
                member.member_id,
                element_state.element_id,
                element_state.element_contract_hash,
            ),
        )
        for integration_point_index, section_state in enumerate(
            element_state.integration_point_states
        ):
            if type(section_state) is not StatefulFiberSectionState:
                _fail(
                    "fiber_frame_material_section_state_type_unsupported",
                    (
                        f"/checkpoint/element_states/{member_index}/"
                        f"integration_point_states/{integration_point_index}"
                    ),
                    "Only the built-in StatefulFiberSectionState is supported.",
                )
            for fiber_index, (fiber, fiber_state) in enumerate(
                zip(section.fibers, section_state.fiber_states, strict=True)
            ):
                if type(fiber_state) is UniaxialPlasticityState:
                    material_type_id = "steel.combined-hardening"
                    material_schema_version = STEEL_STATE_SCHEMA_VERSION
                elif type(fiber_state) is ConcreteDamageState:
                    material_type_id = "concrete.asymmetric-damage"
                    material_schema_version = CONCRETE_DAMAGE_STATE_SCHEMA_VERSION
                else:
                    _fail(
                        "fiber_frame_material_fiber_state_type_unsupported",
                        (
                            f"/checkpoint/element_states/{member_index}/"
                            f"integration_point_states/{integration_point_index}/"
                            f"fiber_states/{fiber_index}"
                        ),
                        "Fiber state type is outside the bounded adapter profile.",
                    )
                integration_point_id = _stable_identity(
                    f"section.ip{integration_point_index}.fiber",
                    fiber_index,
                    (
                        section_state.section_id,
                        section_state.section_contract_hash,
                        fiber.fiber_id,
                        fiber.material_kind,
                    ),
                )
                inputs.append(
                    MaterialStateInput(
                        entity_id=entity_id,
                        integration_point_id=integration_point_id,
                        material_type_id=material_type_id,
                        material_schema_version=material_schema_version,
                        state_bytes=fiber_state.canonical_bytes(),
                    )
                )
    return tuple(inputs)


def _bundle_id(
    role: Literal["committed", "trial"],
    checkpoint: StatefulFiberFrame2DCheckpoint,
) -> str:
    checkpoint_digest = checkpoint.state_hash.removeprefix("sha256:")
    return f"fiber-frame.{role}.e{checkpoint.epoch}.{checkpoint_digest}"


def _stable_identity(
    prefix: str,
    index: int,
    values: tuple[str, ...],
) -> str:
    digest = hashlib.sha256()
    digest.update(_IDENTITY_HASH_DOMAIN)
    digest.update(prefix.encode("ascii"))
    digest.update(b"\0")
    digest.update(str(index).encode("ascii"))
    for value in values:
        digest.update(b"\0")
        digest.update(str(value).encode("utf-8"))
    return f"{prefix}.{index}.{digest.hexdigest()}"


def _fail(
    code: str,
    path: str,
    message: str,
    *,
    cause: Exception | None = None,
) -> None:
    error = StatefulFiberFrame2DMaterialStateAdapterError(code, path, message)
    if cause is not None:
        raise error from cause
    raise error


__all__ = [
    "STATEFUL_FIBER_FRAME2D_MATERIAL_STATE_ADAPTER_AUTHORITY_PROFILE",
    "STATEFUL_FIBER_FRAME2D_MATERIAL_STATE_ADAPTER_CLAIM_BOUNDARY",
    "STATEFUL_FIBER_FRAME2D_MATERIAL_STATE_ADAPTER_PROFILE",
    "StatefulFiberFrame2DMaterialStateAdapterError",
    "StatefulFiberFrame2DMaterialStateBundleTransition",
    "adapt_stateful_fiber_frame2d_checkpoint_to_material_state_bundle",
    "create_initial_stateful_fiber_frame2d_material_state_bundle",
    "validate_stateful_fiber_frame2d_material_state_bundle_projection",
    "validate_stateful_fiber_frame2d_material_state_bundle_transition",
]
