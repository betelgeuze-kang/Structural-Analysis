"""Compose scaled fiber-frame execution, kinematic, and material state.

This module closes the non-authoritative design gate between the bounded
fiber-frame checkpoint ancestry and Engine v2 contracts.  It binds the J1
nonlinear execution topology, J2 physical ``EquationScaling``, J3 kinematic
state chain, and the material-state projection chain without emitting or
promoting ``StateIR v1``.

The binding transports exact identities and lifecycle links only.  It does not
prove convergence, constitutive correctness, numerical results, recovery,
engineering outputs, design compliance, release readiness, or commercial use.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
import math
import re
from types import MappingProxyType
from typing import Any

from structural_analysis.assembly.stateful_fiber_frame2d import (
    StatefulFiberFrame2DProblem,
)
from structural_analysis.assembly.stateful_fiber_frame2d_checkpoint_chain_io import (
    STATEFUL_FIBER_FRAME2D_CHECKPOINT_CHAIN_MAX_CHECKPOINTS,
    STATEFUL_FIBER_FRAME2D_CHECKPOINT_CHAIN_SCHEMA_VERSION,
    StatefulFiberFrame2DCheckpointChain,
    validate_stateful_fiber_frame2d_checkpoint_chain,
)
from structural_analysis.assembly.stateful_fiber_frame2d_execution_topology import (
    FIBER_FRAME_EXECUTION_TOPOLOGY_SCHEMA_VERSION,
    FiberFrameNonlinearExecutionTopologyPlan,
    validate_fiber_frame_execution_topology_against_problem,
    validate_fiber_frame_execution_topology_plan,
)
from structural_analysis.assembly.stateful_fiber_frame2d_kinematic_state_chain import (
    FIBER_FRAME_NONLINEAR_KINEMATIC_STATE_CHAIN_SCHEMA_VERSION,
    FIBER_FRAME_STATE_IR_USAGE_PROFILE,
    FiberFrameNonlinearKinematicStateChain,
    validate_fiber_frame_nonlinear_kinematic_state_chain,
)
from structural_analysis.assembly.stateful_fiber_frame2d_material_state_projection_chain import (
    FIBER_FRAME_MATERIAL_STATE_PROJECTION_CHAIN_SCHEMA_VERSION,
    FiberFrameMaterialStateProjectionChain,
    validate_fiber_frame_material_state_projection_chain,
)
from structural_analysis.assembly.stateful_fiber_frame2d_physical_equation_scaling import (
    FIBER_FRAME_PHYSICAL_EQUATION_SCALING_SCHEMA_VERSION,
    FiberFramePhysicalEquationScalingBinding,
    validate_fiber_frame_physical_equation_scaling_against_problem,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.engine_v2.contracts.equation_scaling import (
    EQUATION_SCALING_SCHEMA_VERSION,
)


FIBER_FRAME_NONLINEAR_EXECUTION_STATE_EPOCH_BINDING_SCHEMA_VERSION = (
    "stateful-fiber-frame2d-nonlinear-execution-state-epoch-binding.v1"
)
FIBER_FRAME_NONLINEAR_EXECUTION_STATE_BINDING_SCHEMA_VERSION = (
    "stateful-fiber-frame2d-nonlinear-execution-state-binding.v1"
)
FIBER_FRAME_NONLINEAR_EXECUTION_STATE_BINDING_AUTHORITY_PROFILE = (
    "non_authoritative_scaled_kinematic_material_state_binding.v1"
)

FIBER_FRAME_NONLINEAR_EXECUTION_STATE_EPOCH_CLAIM_BOUNDARY = MappingProxyType(
    {
        "checkpoint_state_bound": True,
        "committed_kinematic_state_bound": True,
        "material_projection_receipt_bound": True,
        "committed_material_state_bundle_bound": True,
        "solver_state_hash_equality_bound": True,
        "complete_checkpoint_chain_bound": False,
        "physical_equation_scaling_bound": True,
        "constitutive_transition_replayed": False,
        "solver_convergence_authority": False,
        "nonlinear_numerical_result_authority": False,
        "result_ir_authority": False,
        "reaction_member_force_or_fiber_recovery_authority": False,
        "design_or_code_authority": False,
        "release_readiness": False,
        "commercial_use": False,
    }
)
FIBER_FRAME_NONLINEAR_EXECUTION_STATE_BINDING_CLAIM_BOUNDARY = MappingProxyType(
    {
        "execution_topology_plan_bound": True,
        "solver_coordinate_scaling_bound": True,
        "physical_equation_scaling_bound": True,
        "engine_equation_scaling_v1_bound": True,
        "engine_source_commitment_replay_bound": True,
        "exact_scale_vector_bound": True,
        "checkpoint_chain_bound": True,
        "kinematic_state_chain_bound": True,
        "material_state_projection_chain_bound": True,
        "one_epoch_binding_per_checkpoint": True,
        "solver_state_hash_sequence_exact_match": True,
        "terminal_material_state_bundle_bound": True,
        "kinematic_lifecycle_replayed": True,
        "material_bundle_lifecycle_replayed": True,
        "constitutive_transition_replayed": False,
        "state_ir_v1_emitted": False,
        "state_ir_v1_authority_overridden": False,
        "solver_convergence_authority": False,
        "nonlinear_numerical_result_authority": False,
        "result_ir_authority": False,
        "reaction_member_force_or_fiber_recovery_authority": False,
        "design_or_code_authority": False,
        "release_readiness": False,
        "commercial_use": False,
    }
)

_SOURCE_SCHEMA_VERSIONS = MappingProxyType(
    {
        "checkpoint_chain": STATEFUL_FIBER_FRAME2D_CHECKPOINT_CHAIN_SCHEMA_VERSION,
        "execution_topology": FIBER_FRAME_EXECUTION_TOPOLOGY_SCHEMA_VERSION,
        "physical_equation_scaling_binding": (
            FIBER_FRAME_PHYSICAL_EQUATION_SCALING_SCHEMA_VERSION
        ),
        "engine_equation_scaling": EQUATION_SCALING_SCHEMA_VERSION,
        "kinematic_state_chain": (
            FIBER_FRAME_NONLINEAR_KINEMATIC_STATE_CHAIN_SCHEMA_VERSION
        ),
        "material_state_projection_chain": (
            FIBER_FRAME_MATERIAL_STATE_PROJECTION_CHAIN_SCHEMA_VERSION
        ),
    }
)

_HASH_ZERO = "sha256:" + "0" * 64
_HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_STABLE_ID_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,127}$")
_MAX_INDEX = 2**31 - 1


class FiberFrameNonlinearExecutionStateBindingError(ValueError):
    """Stable fail-closed error for the final J4 binding envelope."""

    def __init__(self, code: str, path: str, message: str) -> None:
        self.code = code
        self.path = path
        self.message = message
        super().__init__(f"{code}@{path}: {message}")


@dataclass(frozen=True)
class FiberFrameNonlinearExecutionStateEpochBinding:
    """Append-stable link between one checkpoint and both committed states."""

    schema_version: str
    epoch_binding_hash: str
    authority_profile: str
    state_ir_usage_profile: str
    problem_contract_hash: str
    model_ir_content_hash: str
    execution_topology_plan_hash: str
    physical_equation_scaling_binding_hash: str
    case_id: str
    epoch: int
    step_index: int
    load_factor: float
    checkpoint_state_hash: str
    parent_checkpoint_state_hash: str | None
    accepted_kinematic_state_hash: str | None
    trial_kinematic_state_hash: str | None
    committed_kinematic_state_hash: str
    material_projection_receipt_hash: str
    material_solver_state_hash: str
    accepted_material_state_bundle_hash: str | None
    trial_material_state_bundle_hash: str | None
    committed_material_state_bundle_hash: str
    extensions: Mapping[str, Any]

    def to_manifest(self) -> dict[str, Any]:
        validate_fiber_frame_nonlinear_execution_state_epoch_binding(self)
        return _epoch_payload(self, include_epoch_binding_hash=True)


@dataclass(frozen=True)
class FiberFrameNonlinearExecutionStateBinding:
    """One deterministic scaled execution/kinematic/material-state envelope."""

    schema_version: str
    binding_hash: str
    authority_profile: str
    state_ir_usage_profile: str
    checkpoint_chain_hash: str
    problem_contract_hash: str
    model_ir_content_hash: str
    execution_topology_plan_id: str
    execution_topology_plan_hash: str
    execution_topology_hash: str
    execution_operator_hash: str
    execution_numeric_buffer_hash: str
    solver_coordinate_scaling_hash: str
    physical_equation_scaling_binding_hash: str
    engine_equation_scaling_hash: str
    engine_equation_scaling_source_commitment_hash: str
    physical_equation_order_hash: str
    physical_equation_free_dofs_content_hash: str
    physical_equation_scale_vector_content_hash: str
    kinematic_state_chain_hash: str
    material_state_projection_chain_hash: str
    case_id: str
    node_ids: tuple[str, ...]
    epoch_count: int
    root_checkpoint_state_hash: str
    terminal_checkpoint_state_hash: str
    root_kinematic_state_hash: str
    terminal_kinematic_state_hash: str
    root_material_state_bundle_hash: str
    terminal_material_state_bundle_hash: str
    epoch_bindings: tuple[FiberFrameNonlinearExecutionStateEpochBinding, ...]
    extensions: Mapping[str, Any]

    @property
    def solver_state_hashes(self) -> tuple[str, ...]:
        """Return the exact shared kinematic/material solver-state sequence."""

        return tuple(row.committed_kinematic_state_hash for row in self.epoch_bindings)

    @property
    def material_state_bundle_hashes(self) -> tuple[str, ...]:
        return tuple(
            row.committed_material_state_bundle_hash for row in self.epoch_bindings
        )

    def to_manifest(self) -> dict[str, Any]:
        validate_fiber_frame_nonlinear_execution_state_binding_shape(self)
        return _binding_payload(self, include_binding_hash=True)


def create_fiber_frame_nonlinear_execution_state_binding(
    problem: StatefulFiberFrame2DProblem,
    topology_plan: FiberFrameNonlinearExecutionTopologyPlan,
    physical_scaling: FiberFramePhysicalEquationScalingBinding,
    checkpoint_chain: StatefulFiberFrame2DCheckpointChain,
    kinematic_chain: FiberFrameNonlinearKinematicStateChain,
    material_chain: FiberFrameMaterialStateProjectionChain,
) -> FiberFrameNonlinearExecutionStateBinding:
    """Bind exact J1-J3 and material-chain artifacts into one J4 envelope."""

    _validate_source_artifacts(
        problem,
        topology_plan,
        physical_scaling,
        checkpoint_chain,
        kinematic_chain,
        material_chain,
    )
    candidate = _build_binding(
        topology_plan,
        physical_scaling,
        checkpoint_chain,
        kinematic_chain,
        material_chain,
    )
    return validate_fiber_frame_nonlinear_execution_state_binding(
        problem,
        topology_plan,
        physical_scaling,
        checkpoint_chain,
        kinematic_chain,
        material_chain,
        candidate,
    )


def validate_fiber_frame_nonlinear_execution_state_epoch_binding(
    row: FiberFrameNonlinearExecutionStateEpochBinding,
) -> FiberFrameNonlinearExecutionStateEpochBinding:
    """Validate one self-contained checkpoint/kinematic/material link."""

    if type(row) is not FiberFrameNonlinearExecutionStateEpochBinding:
        _fail(
            "fiber_frame_nonlinear_epoch_binding_type_invalid",
            "/",
            "Expected FiberFrameNonlinearExecutionStateEpochBinding.",
        )
    if (
        row.schema_version
        != FIBER_FRAME_NONLINEAR_EXECUTION_STATE_EPOCH_BINDING_SCHEMA_VERSION
    ):
        _fail(
            "fiber_frame_nonlinear_epoch_binding_schema_invalid",
            "/schema_version",
            "Unsupported nonlinear execution-state epoch-binding schema.",
        )
    _validate_profiles(row.authority_profile, row.state_ir_usage_profile)
    for path, value in (
        ("/epoch_binding_hash", row.epoch_binding_hash),
        ("/bindings/problem_contract_hash", row.problem_contract_hash),
        ("/bindings/model_ir_content_hash", row.model_ir_content_hash),
        (
            "/bindings/execution_topology_plan_hash",
            row.execution_topology_plan_hash,
        ),
        (
            "/bindings/physical_equation_scaling_binding_hash",
            row.physical_equation_scaling_binding_hash,
        ),
        ("/bindings/checkpoint_state_hash", row.checkpoint_state_hash),
        (
            "/bindings/committed_kinematic_state_hash",
            row.committed_kinematic_state_hash,
        ),
        (
            "/bindings/material_projection_receipt_hash",
            row.material_projection_receipt_hash,
        ),
        ("/bindings/material_solver_state_hash", row.material_solver_state_hash),
        (
            "/bindings/committed_material_state_bundle_hash",
            row.committed_material_state_bundle_hash,
        ),
    ):
        _require_hash(value, path)
    for path, value in (
        (
            "/bindings/parent_checkpoint_state_hash",
            row.parent_checkpoint_state_hash,
        ),
        (
            "/bindings/accepted_kinematic_state_hash",
            row.accepted_kinematic_state_hash,
        ),
        (
            "/bindings/trial_kinematic_state_hash",
            row.trial_kinematic_state_hash,
        ),
        (
            "/bindings/accepted_material_state_bundle_hash",
            row.accepted_material_state_bundle_hash,
        ),
        (
            "/bindings/trial_material_state_bundle_hash",
            row.trial_material_state_bundle_hash,
        ),
    ):
        _optional_hash(value, path)
    _nonempty_string(row.case_id, "/bindings/case_id")
    epoch = _index(row.epoch, "/coordinates/epoch")
    step_index = _index(row.step_index, "/coordinates/step_index")
    if epoch != step_index:
        _fail(
            "fiber_frame_nonlinear_epoch_binding_position_invalid",
            "/coordinates",
            "Epoch and step index must be identical.",
        )
    _finite_float(row.load_factor, "/coordinates/load_factor")
    root_optionals = (
        row.parent_checkpoint_state_hash,
        row.accepted_kinematic_state_hash,
        row.trial_kinematic_state_hash,
        row.accepted_material_state_bundle_hash,
        row.trial_material_state_bundle_hash,
    )
    if epoch == 0:
        if any(value is not None for value in root_optionals):
            _fail(
                "fiber_frame_nonlinear_epoch_binding_genesis_invalid",
                "/bindings",
                "Epoch zero must be unparented in both state lifecycles.",
            )
        if row.load_factor != 0.0:
            _fail(
                "fiber_frame_nonlinear_epoch_binding_genesis_load_invalid",
                "/coordinates/load_factor",
                "Epoch-zero load factor must be exact zero.",
            )
    elif any(value is None for value in root_optionals):
        _fail(
            "fiber_frame_nonlinear_epoch_binding_lifecycle_invalid",
            "/bindings",
            "Positive epochs require parent, accepted, and trial hashes.",
        )
    if row.material_solver_state_hash != row.committed_kinematic_state_hash:
        _fail(
            "fiber_frame_nonlinear_epoch_binding_solver_state_mismatch",
            "/bindings/material_solver_state_hash",
            "Material solver-state hash must equal the committed kinematic state.",
        )
    if epoch > 0:
        kinematic_lifecycle = {
            row.accepted_kinematic_state_hash,
            row.trial_kinematic_state_hash,
            row.committed_kinematic_state_hash,
        }
        material_lifecycle = {
            row.accepted_material_state_bundle_hash,
            row.trial_material_state_bundle_hash,
            row.committed_material_state_bundle_hash,
        }
        if (
            row.parent_checkpoint_state_hash == row.checkpoint_state_hash
            or len(kinematic_lifecycle) != 3
            or len(material_lifecycle) != 3
        ):
            _fail(
                "fiber_frame_nonlinear_epoch_binding_lifecycle_invalid",
                "/bindings",
                "Accepted, trial, and committed lifecycle hashes must be distinct.",
            )
    if not isinstance(row.extensions, MappingProxyType) or row.extensions:
        _fail(
            "fiber_frame_nonlinear_epoch_binding_extensions_invalid",
            "/extensions",
            "Epoch-binding v1 requires immutable empty extensions.",
        )
    expected_hash = canonical_hash(
        _epoch_payload(row, include_epoch_binding_hash=False)
    )
    if row.epoch_binding_hash != expected_hash:
        _fail(
            "fiber_frame_nonlinear_epoch_binding_hash_mismatch",
            "/epoch_binding_hash",
            "Epoch-binding hash does not match canonical content.",
        )
    return row


def validate_fiber_frame_nonlinear_execution_state_binding_shape(
    binding: FiberFrameNonlinearExecutionStateBinding,
) -> FiberFrameNonlinearExecutionStateBinding:
    """Validate self-contained J4 metadata, cross-epoch links, and hash."""

    if type(binding) is not FiberFrameNonlinearExecutionStateBinding:
        _fail(
            "fiber_frame_nonlinear_binding_type_invalid",
            "/",
            "Expected FiberFrameNonlinearExecutionStateBinding.",
        )
    if (
        binding.schema_version
        != FIBER_FRAME_NONLINEAR_EXECUTION_STATE_BINDING_SCHEMA_VERSION
    ):
        _fail(
            "fiber_frame_nonlinear_binding_schema_invalid",
            "/schema_version",
            "Unsupported nonlinear execution-state binding schema.",
        )
    _validate_profiles(binding.authority_profile, binding.state_ir_usage_profile)
    for path, value in (
        ("/binding_hash", binding.binding_hash),
        ("/bindings/checkpoint_chain_hash", binding.checkpoint_chain_hash),
        ("/bindings/problem_contract_hash", binding.problem_contract_hash),
        ("/bindings/model_ir_content_hash", binding.model_ir_content_hash),
        (
            "/bindings/execution_topology_plan_hash",
            binding.execution_topology_plan_hash,
        ),
        ("/bindings/execution_topology_hash", binding.execution_topology_hash),
        ("/bindings/execution_operator_hash", binding.execution_operator_hash),
        (
            "/bindings/execution_numeric_buffer_hash",
            binding.execution_numeric_buffer_hash,
        ),
        (
            "/bindings/solver_coordinate_scaling_hash",
            binding.solver_coordinate_scaling_hash,
        ),
        (
            "/bindings/physical_equation_scaling_binding_hash",
            binding.physical_equation_scaling_binding_hash,
        ),
        (
            "/bindings/engine_equation_scaling_hash",
            binding.engine_equation_scaling_hash,
        ),
        (
            "/bindings/engine_equation_scaling_source_commitment_hash",
            binding.engine_equation_scaling_source_commitment_hash,
        ),
        (
            "/bindings/physical_equation_order_hash",
            binding.physical_equation_order_hash,
        ),
        (
            "/bindings/physical_equation_free_dofs_content_hash",
            binding.physical_equation_free_dofs_content_hash,
        ),
        (
            "/bindings/physical_equation_scale_vector_content_hash",
            binding.physical_equation_scale_vector_content_hash,
        ),
        (
            "/bindings/kinematic_state_chain_hash",
            binding.kinematic_state_chain_hash,
        ),
        (
            "/bindings/material_state_projection_chain_hash",
            binding.material_state_projection_chain_hash,
        ),
        (
            "/bindings/root_checkpoint_state_hash",
            binding.root_checkpoint_state_hash,
        ),
        (
            "/bindings/terminal_checkpoint_state_hash",
            binding.terminal_checkpoint_state_hash,
        ),
        (
            "/bindings/root_kinematic_state_hash",
            binding.root_kinematic_state_hash,
        ),
        (
            "/bindings/terminal_kinematic_state_hash",
            binding.terminal_kinematic_state_hash,
        ),
        (
            "/bindings/root_material_state_bundle_hash",
            binding.root_material_state_bundle_hash,
        ),
        (
            "/bindings/terminal_material_state_bundle_hash",
            binding.terminal_material_state_bundle_hash,
        ),
    ):
        _require_hash(value, path)
    _stable_id(
        binding.execution_topology_plan_id,
        "/bindings/execution_topology_plan_id",
    )
    _nonempty_string(binding.case_id, "/bindings/case_id")
    node_ids = _stable_id_tuple(binding.node_ids, "/bindings/node_ids")
    if len(set(node_ids)) != len(node_ids):
        _fail(
            "fiber_frame_nonlinear_binding_node_id_duplicate",
            "/bindings/node_ids",
            "Node identities must be unique.",
        )
    count = _positive_index(binding.epoch_count, "/epoch_count")
    if count > STATEFUL_FIBER_FRAME2D_CHECKPOINT_CHAIN_MAX_CHECKPOINTS:
        _fail(
            "fiber_frame_nonlinear_binding_epoch_count_invalid",
            "/epoch_count",
            "Epoch count exceeds the bounded checkpoint profile.",
        )
    if (
        type(binding.epoch_bindings) is not tuple
        or len(binding.epoch_bindings) != count
        or not all(
            type(row) is FiberFrameNonlinearExecutionStateEpochBinding
            for row in binding.epoch_bindings
        )
    ):
        _fail(
            "fiber_frame_nonlinear_binding_epoch_set_invalid",
            "/epoch_bindings",
            "Epoch-binding tuple does not match epoch_count.",
        )
    for index, row in enumerate(binding.epoch_bindings):
        validate_fiber_frame_nonlinear_execution_state_epoch_binding(row)
        if row.epoch != index or row.step_index != index:
            _fail(
                "fiber_frame_nonlinear_binding_epoch_position_invalid",
                f"/epoch_bindings/{index}",
                "Epoch bindings must be contiguous from zero.",
            )
        for name, expected in (
            ("authority_profile", binding.authority_profile),
            ("state_ir_usage_profile", binding.state_ir_usage_profile),
            ("problem_contract_hash", binding.problem_contract_hash),
            ("model_ir_content_hash", binding.model_ir_content_hash),
            (
                "execution_topology_plan_hash",
                binding.execution_topology_plan_hash,
            ),
            (
                "physical_equation_scaling_binding_hash",
                binding.physical_equation_scaling_binding_hash,
            ),
            ("case_id", binding.case_id),
        ):
            if getattr(row, name) != expected:
                _fail(
                    "fiber_frame_nonlinear_binding_epoch_source_mismatch",
                    f"/epoch_bindings/{index}/{name}",
                    "Every epoch must share the outer source bindings.",
                )
        if index > 0:
            previous = binding.epoch_bindings[index - 1]
            if (
                row.parent_checkpoint_state_hash != previous.checkpoint_state_hash
                or row.accepted_kinematic_state_hash
                != previous.committed_kinematic_state_hash
                or row.accepted_material_state_bundle_hash
                != previous.committed_material_state_bundle_hash
            ):
                _fail(
                    "fiber_frame_nonlinear_binding_epoch_ancestry_mismatch",
                    f"/epoch_bindings/{index}/bindings",
                    "Epoch ancestry does not link the preceding committed states.",
                )
    first = binding.epoch_bindings[0]
    last = binding.epoch_bindings[-1]
    expected_terminals = {
        "root_checkpoint_state_hash": first.checkpoint_state_hash,
        "terminal_checkpoint_state_hash": last.checkpoint_state_hash,
        "root_kinematic_state_hash": first.committed_kinematic_state_hash,
        "terminal_kinematic_state_hash": last.committed_kinematic_state_hash,
        "root_material_state_bundle_hash": (first.committed_material_state_bundle_hash),
        "terminal_material_state_bundle_hash": (
            last.committed_material_state_bundle_hash
        ),
    }
    for name, expected in expected_terminals.items():
        if getattr(binding, name) != expected:
            _fail(
                "fiber_frame_nonlinear_binding_terminal_mismatch",
                f"/bindings/{name}",
                "Root or terminal binding does not match the epoch sequence.",
            )
    if not isinstance(binding.extensions, MappingProxyType) or binding.extensions:
        _fail(
            "fiber_frame_nonlinear_binding_extensions_invalid",
            "/extensions",
            "Nonlinear execution-state binding v1 requires empty extensions.",
        )
    expected_hash = canonical_hash(
        _binding_payload(binding, include_binding_hash=False)
    )
    if binding.binding_hash != expected_hash:
        _fail(
            "fiber_frame_nonlinear_binding_hash_mismatch",
            "/binding_hash",
            "Binding hash does not match canonical content.",
        )
    return binding


def validate_fiber_frame_nonlinear_execution_state_binding(
    problem: StatefulFiberFrame2DProblem,
    topology_plan: FiberFrameNonlinearExecutionTopologyPlan,
    physical_scaling: FiberFramePhysicalEquationScalingBinding,
    checkpoint_chain: StatefulFiberFrame2DCheckpointChain,
    kinematic_chain: FiberFrameNonlinearKinematicStateChain,
    material_chain: FiberFrameMaterialStateProjectionChain,
    binding: FiberFrameNonlinearExecutionStateBinding,
) -> FiberFrameNonlinearExecutionStateBinding:
    """Replay all source artifacts and the exact per-epoch composition."""

    _validate_source_artifacts(
        problem,
        topology_plan,
        physical_scaling,
        checkpoint_chain,
        kinematic_chain,
        material_chain,
    )
    validate_fiber_frame_nonlinear_execution_state_binding_shape(binding)
    expected = _build_binding(
        topology_plan,
        physical_scaling,
        checkpoint_chain,
        kinematic_chain,
        material_chain,
    )
    if binding.to_manifest() != expected.to_manifest():
        _fail(
            "fiber_frame_nonlinear_binding_source_replay_mismatch",
            "/",
            "Binding differs from replayed plan, scaling, and state chains.",
        )
    return binding


def validate_fiber_frame_nonlinear_execution_state_epoch_binding_manifest(
    payload: Any,
) -> Mapping[str, Any]:
    """Validate one descriptor-only epoch-binding manifest."""

    manifest = _manifest_object(payload, "/")
    row = _epoch_from_manifest(manifest)
    validate_fiber_frame_nonlinear_execution_state_epoch_binding(row)
    if row.to_manifest() != manifest:
        _fail(
            "fiber_frame_nonlinear_epoch_binding_manifest_invalid",
            "/",
            "Epoch-binding manifest is not canonical.",
        )
    return manifest


def validate_fiber_frame_nonlinear_execution_state_binding_manifest(
    payload: Any,
) -> Mapping[str, Any]:
    """Validate the descriptor-only outer binding manifest and canonical hash."""

    manifest = _manifest_object(payload, "/")
    binding = _binding_from_manifest(manifest)
    validate_fiber_frame_nonlinear_execution_state_binding_shape(binding)
    if binding.to_manifest() != manifest:
        _fail(
            "fiber_frame_nonlinear_binding_manifest_invalid",
            "/",
            "Nonlinear execution-state binding manifest is not canonical.",
        )
    return manifest


def _validate_source_artifacts(
    problem: StatefulFiberFrame2DProblem,
    topology_plan: FiberFrameNonlinearExecutionTopologyPlan,
    physical_scaling: FiberFramePhysicalEquationScalingBinding,
    checkpoint_chain: StatefulFiberFrame2DCheckpointChain,
    kinematic_chain: FiberFrameNonlinearKinematicStateChain,
    material_chain: FiberFrameMaterialStateProjectionChain,
) -> None:
    validate_fiber_frame_execution_topology_plan(topology_plan)
    validate_fiber_frame_execution_topology_against_problem(problem, topology_plan)
    validate_fiber_frame_physical_equation_scaling_against_problem(
        problem,
        topology_plan,
        physical_scaling,
    )
    validate_stateful_fiber_frame2d_checkpoint_chain(problem, checkpoint_chain)
    validate_fiber_frame_nonlinear_kinematic_state_chain(
        problem,
        topology_plan,
        checkpoint_chain,
        kinematic_chain,
    )
    validate_fiber_frame_material_state_projection_chain(
        problem,
        checkpoint_chain,
        material_chain,
    )
    expected_bindings = {
        "physical_scaling.topology_plan_hash": (
            physical_scaling.topology_plan_hash,
            topology_plan.plan_hash,
        ),
        "kinematic_chain.execution_topology_plan_hash": (
            kinematic_chain.execution_topology_plan_hash,
            topology_plan.plan_hash,
        ),
        "material_chain.execution_plan_hash": (
            material_chain.execution_plan_hash,
            topology_plan.plan_hash,
        ),
        "kinematic_chain.model_ir_content_hash": (
            kinematic_chain.model_ir_content_hash,
            topology_plan.model_ir_content_hash,
        ),
        "material_chain.model_ir_content_hash": (
            material_chain.model_ir_content_hash,
            topology_plan.model_ir_content_hash,
        ),
        "kinematic_chain.checkpoint_chain_hash": (
            kinematic_chain.checkpoint_chain_hash,
            checkpoint_chain.chain_hash,
        ),
        "material_chain.checkpoint_chain_hash": (
            material_chain.checkpoint_chain_hash,
            checkpoint_chain.chain_hash,
        ),
    }
    for name, (actual, expected) in expected_bindings.items():
        if actual != expected:
            _fail(
                "fiber_frame_nonlinear_binding_source_binding_mismatch",
                f"/sources/{name}",
                "Source artifacts do not share one plan and checkpoint ancestry.",
            )
    if (
        kinematic_chain.state_count != material_chain.projection_count
        or kinematic_chain.state_count != len(checkpoint_chain.checkpoints)
    ):
        _fail(
            "fiber_frame_nonlinear_binding_epoch_count_mismatch",
            "/sources",
            "Exactly one kinematic and material state is required per checkpoint.",
        )
    for index, (checkpoint, state, projection) in enumerate(
        zip(
            checkpoint_chain.checkpoints,
            kinematic_chain.committed_states,
            material_chain.projections,
            strict=True,
        )
    ):
        receipt = projection.receipt
        bundle = projection.bundle
        if (
            state.checkpoint_state_hash != checkpoint.state_hash
            or receipt.checkpoint_state_hash != checkpoint.state_hash
            or state.parent_checkpoint_state_hash != checkpoint.parent_state_hash
            or receipt.parent_checkpoint_state_hash != checkpoint.parent_state_hash
        ):
            _fail(
                "fiber_frame_nonlinear_binding_checkpoint_alignment_mismatch",
                f"/sources/epoch/{index}",
                "Kinematic and material states must identify the same checkpoint.",
            )
        if (
            state.state_hash != bundle.solver_state_hash
            or state.state_hash != receipt.solver_state_hash
        ):
            _fail(
                "fiber_frame_nonlinear_binding_solver_state_history_mismatch",
                f"/sources/epoch/{index}/solver_state_hash",
                "Material projection solver-state hash must equal the J3 state hash.",
            )
        if (
            state.epoch != index
            or bundle.epoch != index
            or receipt.checkpoint_epoch != index
            or state.step_index != index
            or receipt.checkpoint_step_index != index
            or state.load_factor != checkpoint.load_factor
            or receipt.checkpoint_load_factor != checkpoint.load_factor
        ):
            _fail(
                "fiber_frame_nonlinear_binding_epoch_alignment_mismatch",
                f"/sources/epoch/{index}",
                "Checkpoint, kinematic, and material coordinates must be identical.",
            )


def _build_binding(
    topology_plan: FiberFrameNonlinearExecutionTopologyPlan,
    physical_scaling: FiberFramePhysicalEquationScalingBinding,
    checkpoint_chain: StatefulFiberFrame2DCheckpointChain,
    kinematic_chain: FiberFrameNonlinearKinematicStateChain,
    material_chain: FiberFrameMaterialStateProjectionChain,
) -> FiberFrameNonlinearExecutionStateBinding:
    rows = tuple(
        _build_epoch_binding(
            physical_scaling,
            checkpoint_chain,
            kinematic_chain,
            material_chain,
            index,
        )
        for index in range(len(checkpoint_chain.checkpoints))
    )
    engine_scaling = physical_scaling.engine_scaling
    provisional = FiberFrameNonlinearExecutionStateBinding(
        schema_version=FIBER_FRAME_NONLINEAR_EXECUTION_STATE_BINDING_SCHEMA_VERSION,
        binding_hash=_HASH_ZERO,
        authority_profile=(
            FIBER_FRAME_NONLINEAR_EXECUTION_STATE_BINDING_AUTHORITY_PROFILE
        ),
        state_ir_usage_profile=FIBER_FRAME_STATE_IR_USAGE_PROFILE,
        checkpoint_chain_hash=checkpoint_chain.chain_hash,
        problem_contract_hash=topology_plan.problem_contract_hash,
        model_ir_content_hash=topology_plan.model_ir_content_hash,
        execution_topology_plan_id=topology_plan.plan_id,
        execution_topology_plan_hash=topology_plan.plan_hash,
        execution_topology_hash=topology_plan.topology_hash,
        execution_operator_hash=topology_plan.operator_hash,
        execution_numeric_buffer_hash=topology_plan.numeric_buffer_hash,
        solver_coordinate_scaling_hash=(topology_plan.solver_coordinate_scaling_hash),
        physical_equation_scaling_binding_hash=physical_scaling.binding_hash,
        engine_equation_scaling_hash=engine_scaling.scaling_hash,
        engine_equation_scaling_source_commitment_hash=(
            engine_scaling.source_commitment_hash
        ),
        physical_equation_order_hash=engine_scaling.equation_order_hash,
        physical_equation_free_dofs_content_hash=(
            engine_scaling.source_free_dofs_content_hash
        ),
        physical_equation_scale_vector_content_hash=(
            engine_scaling.scale_vector_content_hash
        ),
        kinematic_state_chain_hash=kinematic_chain.chain_hash,
        material_state_projection_chain_hash=material_chain.chain_hash,
        case_id=topology_plan.case_id,
        node_ids=topology_plan.node_ids,
        epoch_count=len(rows),
        root_checkpoint_state_hash=checkpoint_chain.root_checkpoint.state_hash,
        terminal_checkpoint_state_hash=(
            checkpoint_chain.terminal_checkpoint.state_hash
        ),
        root_kinematic_state_hash=kinematic_chain.root_kinematic_state_hash,
        terminal_kinematic_state_hash=(kinematic_chain.terminal_kinematic_state_hash),
        root_material_state_bundle_hash=(
            material_chain.projections[0].bundle.bundle_hash
        ),
        terminal_material_state_bundle_hash=(
            material_chain.terminal_material_state_bundle_hash
        ),
        epoch_bindings=rows,
        extensions=MappingProxyType({}),
    )
    result = replace(
        provisional,
        binding_hash=canonical_hash(
            _binding_payload(provisional, include_binding_hash=False)
        ),
    )
    return validate_fiber_frame_nonlinear_execution_state_binding_shape(result)


def _build_epoch_binding(
    physical_scaling: FiberFramePhysicalEquationScalingBinding,
    checkpoint_chain: StatefulFiberFrame2DCheckpointChain,
    kinematic_chain: FiberFrameNonlinearKinematicStateChain,
    material_chain: FiberFrameMaterialStateProjectionChain,
    index: int,
) -> FiberFrameNonlinearExecutionStateEpochBinding:
    checkpoint = checkpoint_chain.checkpoints[index]
    state = kinematic_chain.committed_states[index]
    projection = material_chain.projections[index]
    previous_state = None if index == 0 else kinematic_chain.committed_states[index - 1]
    previous_bundle = (
        None if index == 0 else material_chain.projections[index - 1].bundle
    )
    provisional = FiberFrameNonlinearExecutionStateEpochBinding(
        schema_version=(
            FIBER_FRAME_NONLINEAR_EXECUTION_STATE_EPOCH_BINDING_SCHEMA_VERSION
        ),
        epoch_binding_hash=_HASH_ZERO,
        authority_profile=(
            FIBER_FRAME_NONLINEAR_EXECUTION_STATE_BINDING_AUTHORITY_PROFILE
        ),
        state_ir_usage_profile=FIBER_FRAME_STATE_IR_USAGE_PROFILE,
        problem_contract_hash=kinematic_chain.problem_contract_hash,
        model_ir_content_hash=kinematic_chain.model_ir_content_hash,
        execution_topology_plan_hash=(kinematic_chain.execution_topology_plan_hash),
        physical_equation_scaling_binding_hash=physical_scaling.binding_hash,
        case_id=kinematic_chain.case_id,
        epoch=index,
        step_index=index,
        load_factor=checkpoint.load_factor,
        checkpoint_state_hash=checkpoint.state_hash,
        parent_checkpoint_state_hash=checkpoint.parent_state_hash,
        accepted_kinematic_state_hash=(
            None if previous_state is None else previous_state.state_hash
        ),
        trial_kinematic_state_hash=(None if index == 0 else state.parent_state_hash),
        committed_kinematic_state_hash=state.state_hash,
        material_projection_receipt_hash=projection.receipt.receipt_hash,
        material_solver_state_hash=projection.bundle.solver_state_hash,
        accepted_material_state_bundle_hash=(
            None if previous_bundle is None else previous_bundle.bundle_hash
        ),
        trial_material_state_bundle_hash=projection.receipt.trial_bundle_hash,
        committed_material_state_bundle_hash=projection.bundle.bundle_hash,
        extensions=MappingProxyType({}),
    )
    row = replace(
        provisional,
        epoch_binding_hash=canonical_hash(
            _epoch_payload(provisional, include_epoch_binding_hash=False)
        ),
    )
    return validate_fiber_frame_nonlinear_execution_state_epoch_binding(row)


def _epoch_payload(
    row: FiberFrameNonlinearExecutionStateEpochBinding,
    *,
    include_epoch_binding_hash: bool,
) -> dict[str, Any]:
    payload = {
        "schema_version": row.schema_version,
        "epoch_binding_hash": row.epoch_binding_hash,
        "authority_profile": row.authority_profile,
        "state_ir_usage_profile": row.state_ir_usage_profile,
        "bindings": {
            "problem_contract_hash": row.problem_contract_hash,
            "model_ir_content_hash": row.model_ir_content_hash,
            "execution_topology_plan_hash": row.execution_topology_plan_hash,
            "physical_equation_scaling_binding_hash": (
                row.physical_equation_scaling_binding_hash
            ),
            "case_id": row.case_id,
            "checkpoint_state_hash": row.checkpoint_state_hash,
            "parent_checkpoint_state_hash": row.parent_checkpoint_state_hash,
            "accepted_kinematic_state_hash": (row.accepted_kinematic_state_hash),
            "trial_kinematic_state_hash": row.trial_kinematic_state_hash,
            "committed_kinematic_state_hash": (row.committed_kinematic_state_hash),
            "material_projection_receipt_hash": (row.material_projection_receipt_hash),
            "material_solver_state_hash": row.material_solver_state_hash,
            "accepted_material_state_bundle_hash": (
                row.accepted_material_state_bundle_hash
            ),
            "trial_material_state_bundle_hash": (row.trial_material_state_bundle_hash),
            "committed_material_state_bundle_hash": (
                row.committed_material_state_bundle_hash
            ),
        },
        "coordinates": {
            "epoch": row.epoch,
            "step_index": row.step_index,
            "load_factor": row.load_factor,
        },
        "claim_boundary": dict(
            FIBER_FRAME_NONLINEAR_EXECUTION_STATE_EPOCH_CLAIM_BOUNDARY
        ),
        "extensions": dict(row.extensions),
    }
    if not include_epoch_binding_hash:
        payload.pop("epoch_binding_hash")
    return payload


def _binding_payload(
    binding: FiberFrameNonlinearExecutionStateBinding,
    *,
    include_binding_hash: bool,
) -> dict[str, Any]:
    payload = {
        "schema_version": binding.schema_version,
        "binding_hash": binding.binding_hash,
        "authority_profile": binding.authority_profile,
        "state_ir_usage_profile": binding.state_ir_usage_profile,
        "source_schema_versions": dict(_SOURCE_SCHEMA_VERSIONS),
        "bindings": {
            "checkpoint_chain_hash": binding.checkpoint_chain_hash,
            "problem_contract_hash": binding.problem_contract_hash,
            "model_ir_content_hash": binding.model_ir_content_hash,
            "execution_topology_plan_id": binding.execution_topology_plan_id,
            "execution_topology_plan_hash": (binding.execution_topology_plan_hash),
            "execution_topology_hash": binding.execution_topology_hash,
            "execution_operator_hash": binding.execution_operator_hash,
            "execution_numeric_buffer_hash": (binding.execution_numeric_buffer_hash),
            "solver_coordinate_scaling_hash": (binding.solver_coordinate_scaling_hash),
            "physical_equation_scaling_binding_hash": (
                binding.physical_equation_scaling_binding_hash
            ),
            "engine_equation_scaling_hash": (binding.engine_equation_scaling_hash),
            "engine_equation_scaling_source_commitment_hash": (
                binding.engine_equation_scaling_source_commitment_hash
            ),
            "physical_equation_order_hash": binding.physical_equation_order_hash,
            "physical_equation_free_dofs_content_hash": (
                binding.physical_equation_free_dofs_content_hash
            ),
            "physical_equation_scale_vector_content_hash": (
                binding.physical_equation_scale_vector_content_hash
            ),
            "kinematic_state_chain_hash": binding.kinematic_state_chain_hash,
            "material_state_projection_chain_hash": (
                binding.material_state_projection_chain_hash
            ),
            "case_id": binding.case_id,
            "node_ids": list(binding.node_ids),
            "root_checkpoint_state_hash": binding.root_checkpoint_state_hash,
            "terminal_checkpoint_state_hash": (binding.terminal_checkpoint_state_hash),
            "root_kinematic_state_hash": binding.root_kinematic_state_hash,
            "terminal_kinematic_state_hash": (binding.terminal_kinematic_state_hash),
            "root_material_state_bundle_hash": (
                binding.root_material_state_bundle_hash
            ),
            "terminal_material_state_bundle_hash": (
                binding.terminal_material_state_bundle_hash
            ),
        },
        "epoch_count": binding.epoch_count,
        "epoch_bindings": [row.to_manifest() for row in binding.epoch_bindings],
        "claim_boundary": dict(
            FIBER_FRAME_NONLINEAR_EXECUTION_STATE_BINDING_CLAIM_BOUNDARY
        ),
        "extensions": dict(binding.extensions),
    }
    if not include_binding_hash:
        payload.pop("binding_hash")
    return payload


def _epoch_from_manifest(
    manifest: Mapping[str, Any],
) -> FiberFrameNonlinearExecutionStateEpochBinding:
    _exact_keys(
        manifest,
        {
            "schema_version",
            "epoch_binding_hash",
            "authority_profile",
            "state_ir_usage_profile",
            "bindings",
            "coordinates",
            "claim_boundary",
            "extensions",
        },
        "/",
    )
    bindings = _manifest_object(manifest["bindings"], "/bindings")
    _exact_keys(
        bindings,
        {
            "problem_contract_hash",
            "model_ir_content_hash",
            "execution_topology_plan_hash",
            "physical_equation_scaling_binding_hash",
            "case_id",
            "checkpoint_state_hash",
            "parent_checkpoint_state_hash",
            "accepted_kinematic_state_hash",
            "trial_kinematic_state_hash",
            "committed_kinematic_state_hash",
            "material_projection_receipt_hash",
            "material_solver_state_hash",
            "accepted_material_state_bundle_hash",
            "trial_material_state_bundle_hash",
            "committed_material_state_bundle_hash",
        },
        "/bindings",
    )
    coordinates = _manifest_object(manifest["coordinates"], "/coordinates")
    _exact_keys(coordinates, {"epoch", "step_index", "load_factor"}, "/coordinates")
    _require_claim_boundary(
        manifest["claim_boundary"],
        FIBER_FRAME_NONLINEAR_EXECUTION_STATE_EPOCH_CLAIM_BOUNDARY,
        "/claim_boundary",
    )
    extensions = _empty_manifest_extensions(manifest["extensions"])
    return FiberFrameNonlinearExecutionStateEpochBinding(
        schema_version=manifest["schema_version"],
        epoch_binding_hash=manifest["epoch_binding_hash"],
        authority_profile=manifest["authority_profile"],
        state_ir_usage_profile=manifest["state_ir_usage_profile"],
        problem_contract_hash=bindings["problem_contract_hash"],
        model_ir_content_hash=bindings["model_ir_content_hash"],
        execution_topology_plan_hash=bindings["execution_topology_plan_hash"],
        physical_equation_scaling_binding_hash=(
            bindings["physical_equation_scaling_binding_hash"]
        ),
        case_id=bindings["case_id"],
        epoch=coordinates["epoch"],
        step_index=coordinates["step_index"],
        load_factor=coordinates["load_factor"],
        checkpoint_state_hash=bindings["checkpoint_state_hash"],
        parent_checkpoint_state_hash=bindings["parent_checkpoint_state_hash"],
        accepted_kinematic_state_hash=bindings["accepted_kinematic_state_hash"],
        trial_kinematic_state_hash=bindings["trial_kinematic_state_hash"],
        committed_kinematic_state_hash=(bindings["committed_kinematic_state_hash"]),
        material_projection_receipt_hash=(bindings["material_projection_receipt_hash"]),
        material_solver_state_hash=bindings["material_solver_state_hash"],
        accepted_material_state_bundle_hash=(
            bindings["accepted_material_state_bundle_hash"]
        ),
        trial_material_state_bundle_hash=(bindings["trial_material_state_bundle_hash"]),
        committed_material_state_bundle_hash=(
            bindings["committed_material_state_bundle_hash"]
        ),
        extensions=extensions,
    )


def _binding_from_manifest(
    manifest: Mapping[str, Any],
) -> FiberFrameNonlinearExecutionStateBinding:
    _exact_keys(
        manifest,
        {
            "schema_version",
            "binding_hash",
            "authority_profile",
            "state_ir_usage_profile",
            "source_schema_versions",
            "bindings",
            "epoch_count",
            "epoch_bindings",
            "claim_boundary",
            "extensions",
        },
        "/",
    )
    source_versions = _manifest_object(
        manifest["source_schema_versions"],
        "/source_schema_versions",
    )
    if source_versions != dict(_SOURCE_SCHEMA_VERSIONS) or any(
        type(value) is not str for value in source_versions.values()
    ):
        _fail(
            "fiber_frame_nonlinear_binding_source_schemas_invalid",
            "/source_schema_versions",
            "Source schema versions must match the J1-J4 contract set.",
        )
    bindings = _manifest_object(manifest["bindings"], "/bindings")
    expected_binding_keys = {
        "checkpoint_chain_hash",
        "problem_contract_hash",
        "model_ir_content_hash",
        "execution_topology_plan_id",
        "execution_topology_plan_hash",
        "execution_topology_hash",
        "execution_operator_hash",
        "execution_numeric_buffer_hash",
        "solver_coordinate_scaling_hash",
        "physical_equation_scaling_binding_hash",
        "engine_equation_scaling_hash",
        "engine_equation_scaling_source_commitment_hash",
        "physical_equation_order_hash",
        "physical_equation_free_dofs_content_hash",
        "physical_equation_scale_vector_content_hash",
        "kinematic_state_chain_hash",
        "material_state_projection_chain_hash",
        "case_id",
        "node_ids",
        "root_checkpoint_state_hash",
        "terminal_checkpoint_state_hash",
        "root_kinematic_state_hash",
        "terminal_kinematic_state_hash",
        "root_material_state_bundle_hash",
        "terminal_material_state_bundle_hash",
    }
    _exact_keys(bindings, expected_binding_keys, "/bindings")
    node_ids = bindings["node_ids"]
    if type(node_ids) is not list:
        _fail(
            "fiber_frame_nonlinear_binding_node_ids_invalid",
            "/bindings/node_ids",
            "Manifest node_ids must be a JSON array.",
        )
    epoch_payloads = manifest["epoch_bindings"]
    if type(epoch_payloads) is not list:
        _fail(
            "fiber_frame_nonlinear_binding_epoch_set_invalid",
            "/epoch_bindings",
            "Manifest epoch_bindings must be a JSON array.",
        )
    rows = tuple(
        _epoch_from_manifest(_manifest_object(value, f"/epoch_bindings/{index}"))
        for index, value in enumerate(epoch_payloads)
    )
    _require_claim_boundary(
        manifest["claim_boundary"],
        FIBER_FRAME_NONLINEAR_EXECUTION_STATE_BINDING_CLAIM_BOUNDARY,
        "/claim_boundary",
    )
    extensions = _empty_manifest_extensions(manifest["extensions"])
    return FiberFrameNonlinearExecutionStateBinding(
        schema_version=manifest["schema_version"],
        binding_hash=manifest["binding_hash"],
        authority_profile=manifest["authority_profile"],
        state_ir_usage_profile=manifest["state_ir_usage_profile"],
        checkpoint_chain_hash=bindings["checkpoint_chain_hash"],
        problem_contract_hash=bindings["problem_contract_hash"],
        model_ir_content_hash=bindings["model_ir_content_hash"],
        execution_topology_plan_id=bindings["execution_topology_plan_id"],
        execution_topology_plan_hash=bindings["execution_topology_plan_hash"],
        execution_topology_hash=bindings["execution_topology_hash"],
        execution_operator_hash=bindings["execution_operator_hash"],
        execution_numeric_buffer_hash=bindings["execution_numeric_buffer_hash"],
        solver_coordinate_scaling_hash=bindings["solver_coordinate_scaling_hash"],
        physical_equation_scaling_binding_hash=(
            bindings["physical_equation_scaling_binding_hash"]
        ),
        engine_equation_scaling_hash=bindings["engine_equation_scaling_hash"],
        engine_equation_scaling_source_commitment_hash=(
            bindings["engine_equation_scaling_source_commitment_hash"]
        ),
        physical_equation_order_hash=bindings["physical_equation_order_hash"],
        physical_equation_free_dofs_content_hash=(
            bindings["physical_equation_free_dofs_content_hash"]
        ),
        physical_equation_scale_vector_content_hash=(
            bindings["physical_equation_scale_vector_content_hash"]
        ),
        kinematic_state_chain_hash=bindings["kinematic_state_chain_hash"],
        material_state_projection_chain_hash=(
            bindings["material_state_projection_chain_hash"]
        ),
        case_id=bindings["case_id"],
        node_ids=tuple(node_ids),
        epoch_count=manifest["epoch_count"],
        root_checkpoint_state_hash=bindings["root_checkpoint_state_hash"],
        terminal_checkpoint_state_hash=bindings["terminal_checkpoint_state_hash"],
        root_kinematic_state_hash=bindings["root_kinematic_state_hash"],
        terminal_kinematic_state_hash=bindings["terminal_kinematic_state_hash"],
        root_material_state_bundle_hash=(bindings["root_material_state_bundle_hash"]),
        terminal_material_state_bundle_hash=(
            bindings["terminal_material_state_bundle_hash"]
        ),
        epoch_bindings=rows,
        extensions=extensions,
    )


def _validate_profiles(authority_profile: Any, state_ir_usage_profile: Any) -> None:
    if (
        type(authority_profile) is not str
        or authority_profile
        != FIBER_FRAME_NONLINEAR_EXECUTION_STATE_BINDING_AUTHORITY_PROFILE
    ):
        _fail(
            "fiber_frame_nonlinear_binding_authority_profile_invalid",
            "/authority_profile",
            "J4 binding cannot acquire numerical or engineering authority.",
        )
    if (
        type(state_ir_usage_profile) is not str
        or state_ir_usage_profile != FIBER_FRAME_STATE_IR_USAGE_PROFILE
    ):
        _fail(
            "fiber_frame_nonlinear_binding_state_ir_usage_invalid",
            "/state_ir_usage_profile",
            "StateIR v1 cannot represent the complete nonlinear state.",
        )


def _require_hash(value: Any, path: str) -> str:
    if type(value) is not str or not _HASH_PATTERN.fullmatch(value):
        _fail(
            "fiber_frame_nonlinear_binding_hash_invalid",
            path,
            "Expected a lowercase sha256:<hex> hash.",
        )
    return value


def _optional_hash(value: Any, path: str) -> str | None:
    if value is None:
        return None
    return _require_hash(value, path)


def _index(value: Any, path: str) -> int:
    if type(value) is not int or value < 0 or value > _MAX_INDEX:
        _fail(
            "fiber_frame_nonlinear_binding_index_invalid",
            path,
            "Expected a non-negative 32-bit integer.",
        )
    return value


def _positive_index(value: Any, path: str) -> int:
    normalized = _index(value, path)
    if normalized < 1:
        _fail(
            "fiber_frame_nonlinear_binding_index_invalid",
            path,
            "Expected a positive 32-bit integer.",
        )
    return normalized


def _finite_float(value: Any, path: str) -> float:
    if type(value) is not float or not math.isfinite(value):
        _fail(
            "fiber_frame_nonlinear_binding_float_invalid",
            path,
            "Expected a finite JSON float.",
        )
    return value


def _nonempty_string(value: Any, path: str) -> str:
    if type(value) is not str or not value or value.strip() != value:
        _fail(
            "fiber_frame_nonlinear_binding_string_invalid",
            path,
            "Expected a non-empty trimmed string.",
        )
    return value


def _stable_id(value: Any, path: str) -> str:
    normalized = _nonempty_string(value, path)
    if not _STABLE_ID_PATTERN.fullmatch(normalized):
        _fail(
            "fiber_frame_nonlinear_binding_stable_id_invalid",
            path,
            "Expected a stable identifier.",
        )
    return normalized


def _stable_id_tuple(value: Any, path: str) -> tuple[str, ...]:
    if type(value) is not tuple or not value:
        _fail(
            "fiber_frame_nonlinear_binding_stable_id_tuple_invalid",
            path,
            "Expected a non-empty tuple of stable identifiers.",
        )
    return tuple(
        _stable_id(item, f"{path}/{index}") for index, item in enumerate(value)
    )


def _manifest_object(value: Any, path: str) -> dict[str, Any]:
    if type(value) is not dict:
        _fail(
            "fiber_frame_nonlinear_binding_manifest_object_invalid",
            path,
            "Expected a JSON object.",
        )
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str], path: str) -> None:
    if set(value) != expected or any(type(key) is not str for key in value):
        _fail(
            "fiber_frame_nonlinear_binding_manifest_keys_invalid",
            path,
            "Manifest object keys do not match the schema exactly.",
        )


def _require_claim_boundary(
    value: Any,
    expected: Mapping[str, bool],
    path: str,
) -> None:
    payload = _manifest_object(value, path)
    _exact_keys(payload, set(expected), path)
    if any(
        type(payload[key]) is not bool or payload[key] is not expected[key]
        for key in expected
    ):
        _fail(
            "fiber_frame_nonlinear_binding_claim_boundary_invalid",
            path,
            "Claim-boundary booleans cannot be promoted or weakened.",
        )


def _empty_manifest_extensions(value: Any) -> Mapping[str, Any]:
    payload = _manifest_object(value, "/extensions")
    if payload:
        _fail(
            "fiber_frame_nonlinear_binding_extensions_invalid",
            "/extensions",
            "Nonlinear execution-state binding v1 requires empty extensions.",
        )
    return MappingProxyType({})


def _fail(code: str, path: str, message: str) -> None:
    raise FiberFrameNonlinearExecutionStateBindingError(code, path, message)


__all__ = [
    "FIBER_FRAME_NONLINEAR_EXECUTION_STATE_BINDING_AUTHORITY_PROFILE",
    "FIBER_FRAME_NONLINEAR_EXECUTION_STATE_BINDING_CLAIM_BOUNDARY",
    "FIBER_FRAME_NONLINEAR_EXECUTION_STATE_BINDING_SCHEMA_VERSION",
    "FIBER_FRAME_NONLINEAR_EXECUTION_STATE_EPOCH_BINDING_SCHEMA_VERSION",
    "FIBER_FRAME_NONLINEAR_EXECUTION_STATE_EPOCH_CLAIM_BOUNDARY",
    "FiberFrameNonlinearExecutionStateBinding",
    "FiberFrameNonlinearExecutionStateBindingError",
    "FiberFrameNonlinearExecutionStateEpochBinding",
    "create_fiber_frame_nonlinear_execution_state_binding",
    "validate_fiber_frame_nonlinear_execution_state_binding",
    "validate_fiber_frame_nonlinear_execution_state_binding_manifest",
    "validate_fiber_frame_nonlinear_execution_state_binding_shape",
    "validate_fiber_frame_nonlinear_execution_state_epoch_binding",
    "validate_fiber_frame_nonlinear_execution_state_epoch_binding_manifest",
]
