"""Complete checkpoint-ancestry projection into MaterialStateBundle history.

This module composes the pairwise checkpoint projection adapter over one exact
``StatefulFiberFrame2DCheckpointChain``. The resulting chain binds every
checkpoint, solver-state hash, trial/commit bundle transition, and terminal
material bundle without granting numerical or engineering result authority.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
import re
from types import MappingProxyType
from typing import Any

from structural_analysis.assembly.stateful_fiber_frame2d import (
    StatefulFiberFrame2DProblem,
)
from structural_analysis.assembly.stateful_fiber_frame2d_checkpoint_chain_io import (
    StatefulFiberFrame2DCheckpointChain,
    validate_stateful_fiber_frame2d_checkpoint_chain,
)
from structural_analysis.assembly.stateful_fiber_frame2d_material_state_bundle import (
    FiberFrameMaterialStateProjection,
    FiberFrameMaterialStateProjectionError,
    advance_fiber_frame_material_state_projection,
    create_initial_fiber_frame_material_state_projection,
    validate_fiber_frame_material_state_projection,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash


FIBER_FRAME_MATERIAL_STATE_PROJECTION_CHAIN_SCHEMA_VERSION = (
    "stateful-fiber-frame2d-material-state-projection-chain.v1"
)
FIBER_FRAME_MATERIAL_STATE_PROJECTION_CHAIN_AUTHORITY_PROFILE = (
    "non_authoritative_checkpoint_chain_material_state_projection.v1"
)
FIBER_FRAME_MATERIAL_STATE_PROJECTION_CHAIN_CLAIM_BOUNDARY = MappingProxyType(
    {
        "complete_epoch_zero_rooted_checkpoint_chain_bound": True,
        "checkpoint_chain_hash_bound": True,
        "one_solver_state_hash_per_checkpoint_bound": True,
        "all_material_bundle_transitions_replayed": True,
        "constitutive_transition_replayed": False,
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


@dataclass(frozen=True)
class FiberFrameMaterialStateProjectionChain:
    schema_version: str
    chain_hash: str
    authority_profile: str
    checkpoint_chain_hash: str
    problem_contract_hash: str
    model_ir_content_hash: str
    execution_plan_hash: str
    projection_count: int
    root_checkpoint_state_hash: str
    terminal_checkpoint_state_hash: str
    terminal_material_state_bundle_hash: str
    projections: tuple[FiberFrameMaterialStateProjection, ...]
    extensions: Mapping[str, Any]

    def to_manifest(self) -> dict[str, Any]:
        validate_fiber_frame_material_state_projection_chain_shape(self)
        return _chain_payload(self, include_chain_hash=True)


def create_fiber_frame_material_state_projection_chain(
    problem: StatefulFiberFrame2DProblem,
    checkpoint_chain: StatefulFiberFrame2DCheckpointChain,
    *,
    model_ir_content_hash: str,
    execution_plan_hash: str,
    solver_state_hashes: Sequence[str],
) -> FiberFrameMaterialStateProjectionChain:
    """Project one complete checkpoint chain into exact material-state history."""

    validate_stateful_fiber_frame2d_checkpoint_chain(problem, checkpoint_chain)
    if isinstance(solver_state_hashes, (str, bytes, bytearray)) or not isinstance(
        solver_state_hashes,
        Sequence,
    ):
        raise FiberFrameMaterialStateProjectionError(
            "fiber_frame_projection_chain_solver_hashes_invalid",
            "/solver_state_hashes",
            "Solver state hashes must be a non-string sequence.",
        )
    normalized_solver_hashes = tuple(str(value).strip() for value in solver_state_hashes)
    if len(normalized_solver_hashes) != len(checkpoint_chain.checkpoints):
        raise FiberFrameMaterialStateProjectionError(
            "fiber_frame_projection_chain_solver_hash_count_mismatch",
            "/solver_state_hashes",
            "Exactly one solver state hash is required per checkpoint.",
        )
    for index, value in enumerate(normalized_solver_hashes):
        _require_hash(value, f"/solver_state_hashes/{index}")

    checkpoints = checkpoint_chain.checkpoints
    projections: list[FiberFrameMaterialStateProjection] = [
        create_initial_fiber_frame_material_state_projection(
            problem,
            checkpoints[0],
            model_ir_content_hash=model_ir_content_hash,
            execution_plan_hash=execution_plan_hash,
            solver_state_hash=normalized_solver_hashes[0],
        )
    ]
    for index in range(1, len(checkpoints)):
        projections.append(
            advance_fiber_frame_material_state_projection(
                problem,
                checkpoints[index - 1],
                checkpoints[index],
                projections[index - 1],
                solver_state_hash=normalized_solver_hashes[index],
            )
        )

    projection_tuple = tuple(projections)
    provisional = FiberFrameMaterialStateProjectionChain(
        schema_version=FIBER_FRAME_MATERIAL_STATE_PROJECTION_CHAIN_SCHEMA_VERSION,
        chain_hash=_HASH_ZERO,
        authority_profile=(
            FIBER_FRAME_MATERIAL_STATE_PROJECTION_CHAIN_AUTHORITY_PROFILE
        ),
        checkpoint_chain_hash=checkpoint_chain.chain_hash,
        problem_contract_hash=problem.contract_hash,
        model_ir_content_hash=projection_tuple[0].bundle.model_ir_content_hash,
        execution_plan_hash=projection_tuple[0].bundle.execution_plan_hash,
        projection_count=len(projection_tuple),
        root_checkpoint_state_hash=checkpoint_chain.root_checkpoint.state_hash,
        terminal_checkpoint_state_hash=(
            checkpoint_chain.terminal_checkpoint.state_hash
        ),
        terminal_material_state_bundle_hash=(
            projection_tuple[-1].bundle.bundle_hash
        ),
        projections=projection_tuple,
        extensions=MappingProxyType({}),
    )
    projected_chain = replace(
        provisional,
        chain_hash=canonical_hash(
            _chain_payload(provisional, include_chain_hash=False)
        ),
    )
    return validate_fiber_frame_material_state_projection_chain(
        problem,
        checkpoint_chain,
        projected_chain,
    )


def validate_fiber_frame_material_state_projection_chain_shape(
    projected_chain: FiberFrameMaterialStateProjectionChain,
) -> FiberFrameMaterialStateProjectionChain:
    """Validate self-contained chain metadata and canonical hash."""

    if type(projected_chain) is not FiberFrameMaterialStateProjectionChain:
        raise FiberFrameMaterialStateProjectionError(
            "fiber_frame_projection_chain_type_invalid",
            "/",
            "Expected FiberFrameMaterialStateProjectionChain.",
        )
    if (
        projected_chain.schema_version
        != FIBER_FRAME_MATERIAL_STATE_PROJECTION_CHAIN_SCHEMA_VERSION
    ):
        raise FiberFrameMaterialStateProjectionError(
            "fiber_frame_projection_chain_schema_invalid",
            "/schema_version",
            "Unsupported material-state projection-chain schema.",
        )
    if (
        projected_chain.authority_profile
        != FIBER_FRAME_MATERIAL_STATE_PROJECTION_CHAIN_AUTHORITY_PROFILE
    ):
        raise FiberFrameMaterialStateProjectionError(
            "fiber_frame_projection_chain_authority_profile_invalid",
            "/authority_profile",
            "Projection chain cannot acquire result authority.",
        )
    for path, value in (
        ("/chain_hash", projected_chain.chain_hash),
        ("/checkpoint_chain_hash", projected_chain.checkpoint_chain_hash),
        ("/problem_contract_hash", projected_chain.problem_contract_hash),
        ("/model_ir_content_hash", projected_chain.model_ir_content_hash),
        ("/execution_plan_hash", projected_chain.execution_plan_hash),
        (
            "/root_checkpoint_state_hash",
            projected_chain.root_checkpoint_state_hash,
        ),
        (
            "/terminal_checkpoint_state_hash",
            projected_chain.terminal_checkpoint_state_hash,
        ),
        (
            "/terminal_material_state_bundle_hash",
            projected_chain.terminal_material_state_bundle_hash,
        ),
    ):
        _require_hash(value, path)
    count = _require_index(projected_chain.projection_count, "/projection_count")
    if count < 1:
        raise FiberFrameMaterialStateProjectionError(
            "fiber_frame_projection_chain_count_invalid",
            "/projection_count",
            "Projection chain must retain at least one projection.",
        )
    if (
        type(projected_chain.projections) is not tuple
        or len(projected_chain.projections) != count
        or not all(
            type(value) is FiberFrameMaterialStateProjection
            for value in projected_chain.projections
        )
    ):
        raise FiberFrameMaterialStateProjectionError(
            "fiber_frame_projection_chain_projection_set_invalid",
            "/projections",
            "Projection tuple does not match the declared chain count.",
        )
    first = projected_chain.projections[0]
    last = projected_chain.projections[-1]
    if (
        first.receipt.checkpoint_state_hash
        != projected_chain.root_checkpoint_state_hash
        or last.receipt.checkpoint_state_hash
        != projected_chain.terminal_checkpoint_state_hash
        or last.bundle.bundle_hash
        != projected_chain.terminal_material_state_bundle_hash
    ):
        raise FiberFrameMaterialStateProjectionError(
            "fiber_frame_projection_chain_terminal_binding_mismatch",
            "/projections",
            "Root or terminal projection bindings do not match the chain envelope.",
        )
    if not isinstance(projected_chain.extensions, MappingProxyType) or (
        projected_chain.extensions
    ):
        raise FiberFrameMaterialStateProjectionError(
            "fiber_frame_projection_chain_extensions_invalid",
            "/extensions",
            "Projection-chain v1 requires immutable empty extensions.",
        )
    expected_hash = canonical_hash(
        _chain_payload(projected_chain, include_chain_hash=False)
    )
    if projected_chain.chain_hash != expected_hash:
        raise FiberFrameMaterialStateProjectionError(
            "fiber_frame_projection_chain_hash_mismatch",
            "/chain_hash",
            "Projection-chain hash does not match canonical content.",
        )
    return projected_chain


def validate_fiber_frame_material_state_projection_chain(
    problem: StatefulFiberFrame2DProblem,
    checkpoint_chain: StatefulFiberFrame2DCheckpointChain,
    projected_chain: FiberFrameMaterialStateProjectionChain,
) -> FiberFrameMaterialStateProjectionChain:
    """Replay every checkpoint-to-bundle transition against the complete chain."""

    validate_stateful_fiber_frame2d_checkpoint_chain(problem, checkpoint_chain)
    validate_fiber_frame_material_state_projection_chain_shape(projected_chain)
    if projected_chain.checkpoint_chain_hash != checkpoint_chain.chain_hash:
        raise FiberFrameMaterialStateProjectionError(
            "fiber_frame_projection_chain_checkpoint_hash_mismatch",
            "/checkpoint_chain_hash",
            "Projection chain does not bind the supplied checkpoint ancestry.",
        )
    if projected_chain.problem_contract_hash != problem.contract_hash:
        raise FiberFrameMaterialStateProjectionError(
            "fiber_frame_projection_chain_problem_mismatch",
            "/problem_contract_hash",
            "Projection chain does not bind the supplied frame problem.",
        )
    if len(projected_chain.projections) != len(checkpoint_chain.checkpoints):
        raise FiberFrameMaterialStateProjectionError(
            "fiber_frame_projection_chain_count_mismatch",
            "/projection_count",
            "Projection count does not match checkpoint ancestry count.",
        )

    for index, (checkpoint, projection) in enumerate(
        zip(
            checkpoint_chain.checkpoints,
            projected_chain.projections,
            strict=True,
        )
    ):
        if index == 0:
            validate_fiber_frame_material_state_projection(
                problem,
                checkpoint,
                projection,
            )
        else:
            validate_fiber_frame_material_state_projection(
                problem,
                checkpoint,
                projection,
                parent_checkpoint=checkpoint_chain.checkpoints[index - 1],
                accepted_projection=projected_chain.projections[index - 1],
            )
        if (
            projection.bundle.model_ir_content_hash
            != projected_chain.model_ir_content_hash
            or projection.bundle.execution_plan_hash
            != projected_chain.execution_plan_hash
        ):
            raise FiberFrameMaterialStateProjectionError(
                "fiber_frame_projection_chain_plan_binding_mismatch",
                f"/projections/{index}",
                "Every material projection must share one model and execution plan.",
            )
        if projection.bundle.epoch != index:
            raise FiberFrameMaterialStateProjectionError(
                "fiber_frame_projection_chain_epoch_mismatch",
                f"/projections/{index}/material_state_bundle/epoch",
                "Material bundle epoch does not match checkpoint-chain position.",
            )
    return projected_chain


def _chain_payload(
    projected_chain: FiberFrameMaterialStateProjectionChain,
    *,
    include_chain_hash: bool,
) -> dict[str, Any]:
    payload = {
        "schema_version": projected_chain.schema_version,
        "chain_hash": projected_chain.chain_hash,
        "authority_profile": projected_chain.authority_profile,
        "bindings": {
            "checkpoint_chain_hash": projected_chain.checkpoint_chain_hash,
            "problem_contract_hash": projected_chain.problem_contract_hash,
            "model_ir_content_hash": projected_chain.model_ir_content_hash,
            "execution_plan_hash": projected_chain.execution_plan_hash,
            "root_checkpoint_state_hash": (
                projected_chain.root_checkpoint_state_hash
            ),
            "terminal_checkpoint_state_hash": (
                projected_chain.terminal_checkpoint_state_hash
            ),
            "terminal_material_state_bundle_hash": (
                projected_chain.terminal_material_state_bundle_hash
            ),
        },
        "projection_count": projected_chain.projection_count,
        "projections": [
            projection.to_manifest() for projection in projected_chain.projections
        ],
        "claim_boundary": dict(
            FIBER_FRAME_MATERIAL_STATE_PROJECTION_CHAIN_CLAIM_BOUNDARY
        ),
        "extensions": dict(projected_chain.extensions),
    }
    if not include_chain_hash:
        payload.pop("chain_hash")
    return payload


def _require_hash(value: Any, path: str) -> str:
    normalized = str(value).strip()
    if not _HASH_PATTERN.fullmatch(normalized):
        raise FiberFrameMaterialStateProjectionError(
            "fiber_frame_projection_chain_hash_invalid",
            path,
            "Expected a lowercase sha256:<hex> hash.",
        )
    return normalized


def _require_index(value: Any, path: str) -> int:
    if type(value) is not int or value < 0 or value > _MAX_INDEX:
        raise FiberFrameMaterialStateProjectionError(
            "fiber_frame_projection_chain_index_invalid",
            path,
            "Expected a non-negative 32-bit integer.",
        )
    return value


__all__ = [
    "FIBER_FRAME_MATERIAL_STATE_PROJECTION_CHAIN_AUTHORITY_PROFILE",
    "FIBER_FRAME_MATERIAL_STATE_PROJECTION_CHAIN_CLAIM_BOUNDARY",
    "FIBER_FRAME_MATERIAL_STATE_PROJECTION_CHAIN_SCHEMA_VERSION",
    "FiberFrameMaterialStateProjectionChain",
    "create_fiber_frame_material_state_projection_chain",
    "validate_fiber_frame_material_state_projection_chain",
    "validate_fiber_frame_material_state_projection_chain_shape",
]
