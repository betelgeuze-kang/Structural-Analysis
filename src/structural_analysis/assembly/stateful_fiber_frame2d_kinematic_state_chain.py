"""Typed nonlinear kinematic-state transport for fiber-frame checkpoints.

The bounded fiber-frame checkpoint is a three-DOF-per-node physical state.  This
module projects a complete checkpoint ancestry into canonical six-DOF
displacement states bound to the separate nonlinear execution-topology plan.

Exactly one committed kinematic state is retained per checkpoint.  Positive
epochs also carry a receipt for a deterministically replayed
accepted -> trial -> committed lifecycle.  The trial state is not retained as a
second checkpoint state; its hash is reproduced during validation.

No Engine v2 ``StateIR v1`` object is created here.  Its
``stateless_linear_elastic`` constitutive profile cannot describe this nonlinear
checkpoint history.  The canonical displacement vector may only be used later
as an explicitly optional StateIR displacement carrier.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
import math
import re
from types import MappingProxyType
from typing import Any, Literal

import numpy as np

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
    canonical_6dof_to_physical_3dof,
    physical_3dof_to_canonical_6dof,
    physical_3dof_to_solver_generalized,
    solver_generalized_to_physical_3dof,
    validate_fiber_frame_execution_topology_against_problem,
    validate_fiber_frame_execution_topology_plan,
)
from structural_analysis.assembly.stateful_fiber_frame2d_state import (
    STATEFUL_FIBER_FRAME2D_CHECKPOINT_SCHEMA_VERSION,
    StatefulFiberFrame2DCheckpoint,
)
from structural_analysis.engine_v2.contracts._canonical import (
    CanonicalContractError,
    array_content_hash,
    array_data_hash,
    canonical_hash,
    has_immutable_bytes_backing,
    immutable_array,
)


FIBER_FRAME_NONLINEAR_KINEMATIC_STATE_SCHEMA_VERSION = (
    "stateful-fiber-frame2d-nonlinear-kinematic-state.v1"
)
FIBER_FRAME_NONLINEAR_KINEMATIC_TRANSITION_SCHEMA_VERSION = (
    "stateful-fiber-frame2d-nonlinear-kinematic-transition.v1"
)
FIBER_FRAME_NONLINEAR_KINEMATIC_STATE_CHAIN_SCHEMA_VERSION = (
    "stateful-fiber-frame2d-nonlinear-kinematic-state-chain.v1"
)
FIBER_FRAME_NONLINEAR_KINEMATIC_AUTHORITY_PROFILE = (
    "non_authoritative_checkpoint_kinematic_state_transport.v1"
)
FIBER_FRAME_NONLINEAR_KINEMATIC_CARRIER_PROFILE = (
    "canonical_six_dof_displacement_only.v1"
)
FIBER_FRAME_NONLINEAR_KINEMATIC_LIFECYCLE_PROFILE = (
    "accepted_trial_committed_checkpoint_projection.v1"
)
FIBER_FRAME_STATE_IR_USAGE_PROFILE = (
    "state_ir_v1_not_emitted_optional_displacement_carrier_only.v1"
)

FIBER_FRAME_NONLINEAR_KINEMATIC_STATE_CLAIM_BOUNDARY = MappingProxyType(
    {
        "checkpoint_state_bound": True,
        "parent_checkpoint_state_hash_bound": True,
        "execution_topology_plan_bound": True,
        "solver_coordinate_scaling_bound": True,
        "canonical_six_dof_displacement_mapping_bound": True,
        "inactive_uz_rx_ry_exact_zero": True,
        "complete_checkpoint_chain_bound": False,
        "trial_commit_lifecycle_replayed": False,
        "velocity_or_acceleration_history_bound": False,
        "constitutive_state_history_bound": False,
        "state_ir_v1_object_emitted": False,
        "state_ir_v1_complete_state_claim": False,
        "solver_convergence_authority": False,
        "nonlinear_numerical_result_authority": False,
        "reaction_or_member_force_authority": False,
        "design_or_code_authority": False,
        "release_readiness": False,
        "commercial_use": False,
    }
)
FIBER_FRAME_NONLINEAR_KINEMATIC_TRANSITION_CLAIM_BOUNDARY = MappingProxyType(
    {
        "parent_and_child_checkpoint_hashes_bound": True,
        "accepted_trial_committed_state_hashes_bound": True,
        "execution_topology_plan_bound": True,
        "complete_checkpoint_chain_bound": False,
        "trial_state_payload_replayed_by_receipt_alone": False,
        "velocity_or_acceleration_history_bound": False,
        "constitutive_state_history_bound": False,
        "state_ir_v1_object_emitted": False,
        "state_ir_v1_complete_state_claim": False,
        "solver_convergence_authority": False,
        "nonlinear_numerical_result_authority": False,
        "reaction_or_member_force_authority": False,
        "design_or_code_authority": False,
        "release_readiness": False,
        "commercial_use": False,
    }
)
FIBER_FRAME_NONLINEAR_KINEMATIC_CLAIM_BOUNDARY = MappingProxyType(
    {
        "complete_checkpoint_chain_bound": True,
        "execution_topology_plan_bound": True,
        "solver_coordinate_scaling_bound": True,
        "one_committed_kinematic_state_per_checkpoint": True,
        "trial_commit_lifecycle_replayed": True,
        "canonical_six_dof_displacement_mapping_bound": True,
        "inactive_uz_rx_ry_exact_zero": True,
        "velocity_or_acceleration_history_bound": False,
        "constitutive_state_history_bound": False,
        "state_ir_v1_object_emitted": False,
        "state_ir_v1_complete_state_claim": False,
        "solver_convergence_authority": False,
        "nonlinear_numerical_result_authority": False,
        "reaction_or_member_force_authority": False,
        "design_or_code_authority": False,
        "release_readiness": False,
        "commercial_use": False,
    }
)

_HASH_ZERO = "sha256:" + "0" * 64
_HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_STABLE_ID_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,127}$")
_MAX_INDEX = 2**31 - 1
_SOLVER_COMPONENTS = ("UX", "UY", "RZ")
_CANONICAL_COMPONENTS = ("UX", "UY", "UZ", "RX", "RY", "RZ")
_CHECKPOINT_DISPLACEMENT_UNITS = ("m", "m", "rad")
_GENERALIZED_COORDINATE_UNITS = ("m", "m", "m")
_CANONICAL_DISPLACEMENT_UNITS = ("m", "m", "m", "rad", "rad", "rad")
_STATE_ARRAY_NAMES = (
    "checkpoint_displacement_physical_3dof",
    "solver_generalized_coordinates_m",
    "canonical_displacement_si",
)


class FiberFrameNonlinearKinematicStateError(ValueError):
    """Stable fail-closed error for nonlinear kinematic-state transport."""

    def __init__(self, code: str, path: str, message: str) -> None:
        self.code = code
        self.path = path
        self.message = message
        super().__init__(f"{code}@{path}: {message}")


@dataclass(frozen=True)
class FiberFrameKinematicArrayDescriptor:
    name: str
    dtype: str
    shape: tuple[int, ...]
    layout: Literal["C"]
    byte_length: int
    coordinate_order_hash: str
    data_hash: str
    content_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "dtype": self.dtype,
            "shape": list(self.shape),
            "layout": self.layout,
            "byte_length": self.byte_length,
            "coordinate_order_hash": self.coordinate_order_hash,
            "data_hash": self.data_hash,
            "content_hash": self.content_hash,
        }


@dataclass(frozen=True)
class FiberFrameNonlinearKinematicState:
    schema_version: str
    state_id: str
    state_hash: str
    authority_profile: str
    carrier_profile: str
    state_ir_usage_profile: str
    role: Literal["trial", "committed"]
    problem_contract_hash: str
    model_ir_content_hash: str
    execution_topology_plan_id: str
    execution_topology_plan_hash: str
    solver_coordinate_scaling_hash: str
    checkpoint_state_hash: str
    parent_checkpoint_state_hash: str | None
    case_id: str
    node_ids: tuple[str, ...]
    epoch: int
    step_index: int
    load_factor: float
    parent_state_hash: str | None
    node_count: int
    solver_dof_count: int
    physical_dof_count: int
    rotation_coordinate_scale_m: float
    descriptors: tuple[FiberFrameKinematicArrayDescriptor, ...]
    _arrays: Mapping[str, np.ndarray] = field(repr=False, compare=False)
    extensions: Mapping[str, Any]

    def array(self, name: str) -> np.ndarray:
        try:
            return self._arrays[name]
        except KeyError as exc:
            raise KeyError(f"Unknown nonlinear kinematic-state array: {name}") from exc

    def to_manifest(self) -> dict[str, Any]:
        validate_fiber_frame_nonlinear_kinematic_state_shape(self)
        return _state_payload(self, include_state_hash=True)


@dataclass(frozen=True)
class FiberFrameNonlinearKinematicTransitionReceipt:
    schema_version: str
    transition_hash: str
    authority_profile: str
    lifecycle_profile: str
    problem_contract_hash: str
    model_ir_content_hash: str
    execution_topology_plan_hash: str
    case_id: str
    epoch: int
    step_index: int
    load_factor: float
    parent_checkpoint_state_hash: str
    checkpoint_state_hash: str
    accepted_state_hash: str
    trial_state_hash: str
    committed_state_hash: str
    extensions: Mapping[str, Any]

    def to_manifest(self) -> dict[str, Any]:
        validate_fiber_frame_nonlinear_kinematic_transition_receipt(self)
        return _transition_payload(self, include_transition_hash=True)


@dataclass(frozen=True)
class FiberFrameNonlinearKinematicStateChain:
    schema_version: str
    chain_hash: str
    authority_profile: str
    carrier_profile: str
    lifecycle_profile: str
    state_ir_usage_profile: str
    checkpoint_chain_hash: str
    problem_contract_hash: str
    model_ir_content_hash: str
    execution_topology_plan_id: str
    execution_topology_plan_hash: str
    solver_coordinate_scaling_hash: str
    case_id: str
    node_ids: tuple[str, ...]
    state_count: int
    transition_count: int
    root_checkpoint_state_hash: str
    terminal_checkpoint_state_hash: str
    root_kinematic_state_hash: str
    terminal_kinematic_state_hash: str
    committed_states: tuple[FiberFrameNonlinearKinematicState, ...]
    transitions: tuple[FiberFrameNonlinearKinematicTransitionReceipt, ...]
    extensions: Mapping[str, Any]

    @property
    def solver_state_hashes(self) -> tuple[str, ...]:
        """Return the exact hashes consumed by the later material binding."""

        return tuple(state.state_hash for state in self.committed_states)

    def to_manifest(self) -> dict[str, Any]:
        validate_fiber_frame_nonlinear_kinematic_state_chain_shape(self)
        return _chain_payload(self, include_chain_hash=True)


def create_fiber_frame_nonlinear_kinematic_state_chain(
    problem: StatefulFiberFrame2DProblem,
    plan: FiberFrameNonlinearExecutionTopologyPlan,
    checkpoint_chain: StatefulFiberFrame2DCheckpointChain,
) -> FiberFrameNonlinearKinematicStateChain:
    """Project a complete checkpoint ancestry into canonical displacement states."""

    validate_fiber_frame_execution_topology_plan(plan)
    validate_fiber_frame_execution_topology_against_problem(problem, plan)
    validate_stateful_fiber_frame2d_checkpoint_chain(problem, checkpoint_chain)
    states, transitions = _project_checkpoint_chain(plan, checkpoint_chain)
    provisional = FiberFrameNonlinearKinematicStateChain(
        schema_version=FIBER_FRAME_NONLINEAR_KINEMATIC_STATE_CHAIN_SCHEMA_VERSION,
        chain_hash=_HASH_ZERO,
        authority_profile=FIBER_FRAME_NONLINEAR_KINEMATIC_AUTHORITY_PROFILE,
        carrier_profile=FIBER_FRAME_NONLINEAR_KINEMATIC_CARRIER_PROFILE,
        lifecycle_profile=FIBER_FRAME_NONLINEAR_KINEMATIC_LIFECYCLE_PROFILE,
        state_ir_usage_profile=FIBER_FRAME_STATE_IR_USAGE_PROFILE,
        checkpoint_chain_hash=checkpoint_chain.chain_hash,
        problem_contract_hash=problem.contract_hash,
        model_ir_content_hash=plan.model_ir_content_hash,
        execution_topology_plan_id=plan.plan_id,
        execution_topology_plan_hash=plan.plan_hash,
        solver_coordinate_scaling_hash=plan.solver_coordinate_scaling_hash,
        case_id=problem.case_id,
        node_ids=plan.node_ids,
        state_count=len(states),
        transition_count=len(transitions),
        root_checkpoint_state_hash=checkpoint_chain.root_checkpoint.state_hash,
        terminal_checkpoint_state_hash=checkpoint_chain.terminal_checkpoint.state_hash,
        root_kinematic_state_hash=states[0].state_hash,
        terminal_kinematic_state_hash=states[-1].state_hash,
        committed_states=states,
        transitions=transitions,
        extensions=MappingProxyType({}),
    )
    result = replace(
        provisional,
        chain_hash=canonical_hash(
            _chain_payload(provisional, include_chain_hash=False)
        ),
    )
    return validate_fiber_frame_nonlinear_kinematic_state_chain(
        problem,
        plan,
        checkpoint_chain,
        result,
    )


def validate_fiber_frame_nonlinear_kinematic_state_shape(
    state: FiberFrameNonlinearKinematicState,
) -> FiberFrameNonlinearKinematicState:
    """Validate a retained or transient state without external source objects."""

    if type(state) is not FiberFrameNonlinearKinematicState:
        _fail(
            "fiber_frame_kinematic_state_type_invalid",
            "/",
            "Expected FiberFrameNonlinearKinematicState.",
        )
    if state.schema_version != FIBER_FRAME_NONLINEAR_KINEMATIC_STATE_SCHEMA_VERSION:
        _fail(
            "fiber_frame_kinematic_state_schema_invalid",
            "/schema_version",
            "Unsupported nonlinear kinematic-state schema.",
        )
    _validate_profiles(
        authority_profile=state.authority_profile,
        carrier_profile=state.carrier_profile,
        state_ir_usage_profile=state.state_ir_usage_profile,
    )
    _stable_id(state.state_id, "/state_id")
    for path, value in (
        ("/state_hash", state.state_hash),
        ("/bindings/problem_contract_hash", state.problem_contract_hash),
        ("/bindings/model_ir_content_hash", state.model_ir_content_hash),
        (
            "/bindings/execution_topology_plan_hash",
            state.execution_topology_plan_hash,
        ),
        (
            "/bindings/solver_coordinate_scaling_hash",
            state.solver_coordinate_scaling_hash,
        ),
        ("/bindings/checkpoint_state_hash", state.checkpoint_state_hash),
    ):
        _require_hash(value, path)
    _stable_id(state.execution_topology_plan_id, "/bindings/execution_topology_plan_id")
    _nonempty_string(state.case_id, "/bindings/case_id")
    if state.parent_checkpoint_state_hash is not None:
        _require_hash(
            state.parent_checkpoint_state_hash,
            "/bindings/parent_checkpoint_state_hash",
        )
    if state.parent_state_hash is not None:
        _require_hash(state.parent_state_hash, "/coordinates/parent_state_hash")
    if state.role not in ("trial", "committed"):
        _fail(
            "fiber_frame_kinematic_state_role_invalid",
            "/role",
            "Kinematic state role must be trial or committed.",
        )
    epoch = _index(state.epoch, "/coordinates/epoch")
    step = _index(state.step_index, "/coordinates/step_index")
    if step != epoch:
        _fail(
            "fiber_frame_kinematic_state_step_epoch_mismatch",
            "/coordinates/step_index",
            "Checkpoint step index must equal epoch.",
        )
    load_factor = _finite_float(state.load_factor, "/coordinates/load_factor")
    node_count = _positive_index(state.node_count, "/layout/node_count")
    solver_count = _positive_index(
        state.solver_dof_count,
        "/layout/solver_dof_count",
    )
    physical_count = _positive_index(
        state.physical_dof_count,
        "/layout/physical_dof_count",
    )
    if solver_count != 3 * node_count or physical_count != 6 * node_count:
        _fail(
            "fiber_frame_kinematic_state_dof_count_invalid",
            "/layout",
            "DOF counts must equal node_count*3 and node_count*6.",
        )
    node_ids = _stable_id_tuple(state.node_ids, "/layout/node_ids")
    if len(node_ids) != node_count:
        _fail(
            "fiber_frame_kinematic_state_node_count_mismatch",
            "/layout/node_ids",
            "Node identity count does not match node_count.",
        )
    if len(set(node_ids)) != len(node_ids):
        _fail(
            "fiber_frame_kinematic_state_node_id_duplicate",
            "/layout/node_ids",
            "Node identities must be unique.",
        )
    rotation_scale = _positive_float(
        state.rotation_coordinate_scale_m,
        "/layout/rotation_coordinate_scale_m",
    )
    if epoch == 0:
        if (
            state.role != "committed"
            or state.parent_state_hash is not None
            or state.parent_checkpoint_state_hash is not None
            or load_factor != 0.0
        ):
            _fail(
                "fiber_frame_kinematic_state_initial_lineage_invalid",
                "/coordinates",
                "Epoch zero must be an unparented committed zero-load state.",
            )
    elif state.parent_state_hash is None or state.parent_checkpoint_state_hash is None:
        _fail(
            "fiber_frame_kinematic_state_parent_missing",
            "/coordinates/parent_state_hash",
            "Positive-epoch state requires state and checkpoint ancestry.",
        )
    if state.role == "trial" and epoch == 0:
        _fail(
            "fiber_frame_kinematic_state_trial_epoch_invalid",
            "/coordinates/epoch",
            "Trial state epoch must be positive.",
        )
    _validate_state_array_map(state)
    physical = state.array("checkpoint_displacement_physical_3dof")
    generalized = state.array("solver_generalized_coordinates_m")
    canonical = state.array("canonical_displacement_si")
    expected_generalized = physical.copy()
    expected_generalized[2::3] *= rotation_scale
    expected_canonical = np.zeros(physical_count, dtype=np.float64)
    expected_canonical[np.asarray(_active_physical_dofs(node_count))] = physical
    if not np.array_equal(generalized, expected_generalized):
        _fail(
            "fiber_frame_kinematic_state_generalized_mapping_mismatch",
            "/arrays/solver_generalized_coordinates_m",
            "Generalized coordinates do not match physical UX/UY/RZ values.",
        )
    if not np.array_equal(canonical, expected_canonical):
        _fail(
            "fiber_frame_kinematic_state_canonical_mapping_mismatch",
            "/arrays/canonical_displacement_si",
            "Canonical displacement does not map exact UX/UY/RZ values and zeros.",
        )
    if epoch == 0 and (
        np.any(physical != 0.0)
        or np.any(generalized != 0.0)
        or np.any(canonical != 0.0)
    ):
        _fail(
            "fiber_frame_kinematic_state_initial_nonzero",
            "/arrays",
            "Epoch-zero kinematic arrays must be exact zero.",
        )
    if not isinstance(state.extensions, MappingProxyType) or state.extensions:
        _fail(
            "fiber_frame_kinematic_state_extensions_invalid",
            "/extensions",
            "Kinematic-state v1 requires immutable empty extensions.",
        )
    expected_hash = canonical_hash(_state_payload(state, include_state_hash=False))
    if state.state_hash != expected_hash:
        _fail(
            "fiber_frame_kinematic_state_hash_mismatch",
            "/state_hash",
            "State hash does not match canonical content.",
        )
    return state


def validate_fiber_frame_nonlinear_kinematic_transition_receipt(
    receipt: FiberFrameNonlinearKinematicTransitionReceipt,
) -> FiberFrameNonlinearKinematicTransitionReceipt:
    """Validate one self-contained accepted -> trial -> committed receipt."""

    if type(receipt) is not FiberFrameNonlinearKinematicTransitionReceipt:
        _fail(
            "fiber_frame_kinematic_transition_type_invalid",
            "/",
            "Expected FiberFrameNonlinearKinematicTransitionReceipt.",
        )
    if (
        receipt.schema_version
        != FIBER_FRAME_NONLINEAR_KINEMATIC_TRANSITION_SCHEMA_VERSION
    ):
        _fail(
            "fiber_frame_kinematic_transition_schema_invalid",
            "/schema_version",
            "Unsupported nonlinear kinematic-transition schema.",
        )
    if receipt.authority_profile != FIBER_FRAME_NONLINEAR_KINEMATIC_AUTHORITY_PROFILE:
        _fail(
            "fiber_frame_kinematic_authority_profile_invalid",
            "/authority_profile",
            "Kinematic transport cannot acquire result authority.",
        )
    if receipt.lifecycle_profile != FIBER_FRAME_NONLINEAR_KINEMATIC_LIFECYCLE_PROFILE:
        _fail(
            "fiber_frame_kinematic_lifecycle_profile_invalid",
            "/lifecycle_profile",
            "Unsupported kinematic lifecycle profile.",
        )
    for path, value in (
        ("/transition_hash", receipt.transition_hash),
        ("/bindings/problem_contract_hash", receipt.problem_contract_hash),
        ("/bindings/model_ir_content_hash", receipt.model_ir_content_hash),
        (
            "/bindings/execution_topology_plan_hash",
            receipt.execution_topology_plan_hash,
        ),
        (
            "/bindings/parent_checkpoint_state_hash",
            receipt.parent_checkpoint_state_hash,
        ),
        ("/bindings/checkpoint_state_hash", receipt.checkpoint_state_hash),
        ("/lifecycle/accepted_state_hash", receipt.accepted_state_hash),
        ("/lifecycle/trial_state_hash", receipt.trial_state_hash),
        ("/lifecycle/committed_state_hash", receipt.committed_state_hash),
    ):
        _require_hash(value, path)
    _nonempty_string(receipt.case_id, "/bindings/case_id")
    epoch = _positive_index(receipt.epoch, "/coordinates/epoch")
    step = _positive_index(receipt.step_index, "/coordinates/step_index")
    if step != epoch:
        _fail(
            "fiber_frame_kinematic_transition_step_epoch_mismatch",
            "/coordinates/step_index",
            "Transition step index must equal epoch.",
        )
    _finite_float(receipt.load_factor, "/coordinates/load_factor")
    if (
        len(
            {
                receipt.accepted_state_hash,
                receipt.trial_state_hash,
                receipt.committed_state_hash,
            }
        )
        != 3
    ):
        _fail(
            "fiber_frame_kinematic_transition_state_cycle",
            "/lifecycle",
            "Accepted, trial, and committed hashes must be distinct.",
        )
    if not isinstance(receipt.extensions, MappingProxyType) or receipt.extensions:
        _fail(
            "fiber_frame_kinematic_transition_extensions_invalid",
            "/extensions",
            "Transition v1 requires immutable empty extensions.",
        )
    expected_hash = canonical_hash(
        _transition_payload(receipt, include_transition_hash=False)
    )
    if receipt.transition_hash != expected_hash:
        _fail(
            "fiber_frame_kinematic_transition_hash_mismatch",
            "/transition_hash",
            "Transition hash does not match canonical content.",
        )
    return receipt


def validate_fiber_frame_nonlinear_kinematic_state_chain_shape(
    chain: FiberFrameNonlinearKinematicStateChain,
) -> FiberFrameNonlinearKinematicStateChain:
    """Validate self-contained chain metadata, lifecycle links, and hashes."""

    if type(chain) is not FiberFrameNonlinearKinematicStateChain:
        _fail(
            "fiber_frame_kinematic_chain_type_invalid",
            "/",
            "Expected FiberFrameNonlinearKinematicStateChain.",
        )
    if (
        chain.schema_version
        != FIBER_FRAME_NONLINEAR_KINEMATIC_STATE_CHAIN_SCHEMA_VERSION
    ):
        _fail(
            "fiber_frame_kinematic_chain_schema_invalid",
            "/schema_version",
            "Unsupported nonlinear kinematic-state-chain schema.",
        )
    _validate_profiles(
        authority_profile=chain.authority_profile,
        carrier_profile=chain.carrier_profile,
        lifecycle_profile=chain.lifecycle_profile,
        state_ir_usage_profile=chain.state_ir_usage_profile,
    )
    for path, value in (
        ("/chain_hash", chain.chain_hash),
        ("/bindings/checkpoint_chain_hash", chain.checkpoint_chain_hash),
        ("/bindings/problem_contract_hash", chain.problem_contract_hash),
        ("/bindings/model_ir_content_hash", chain.model_ir_content_hash),
        (
            "/bindings/execution_topology_plan_hash",
            chain.execution_topology_plan_hash,
        ),
        (
            "/bindings/solver_coordinate_scaling_hash",
            chain.solver_coordinate_scaling_hash,
        ),
        (
            "/bindings/root_checkpoint_state_hash",
            chain.root_checkpoint_state_hash,
        ),
        (
            "/bindings/terminal_checkpoint_state_hash",
            chain.terminal_checkpoint_state_hash,
        ),
        (
            "/bindings/root_kinematic_state_hash",
            chain.root_kinematic_state_hash,
        ),
        (
            "/bindings/terminal_kinematic_state_hash",
            chain.terminal_kinematic_state_hash,
        ),
    ):
        _require_hash(value, path)
    _stable_id(
        chain.execution_topology_plan_id,
        "/bindings/execution_topology_plan_id",
    )
    _nonempty_string(chain.case_id, "/bindings/case_id")
    node_ids = _stable_id_tuple(chain.node_ids, "/bindings/node_ids")
    if len(set(node_ids)) != len(node_ids):
        _fail(
            "fiber_frame_kinematic_chain_node_id_duplicate",
            "/bindings/node_ids",
            "Node identities must be unique.",
        )
    state_count = _positive_index(chain.state_count, "/state_count")
    if state_count > STATEFUL_FIBER_FRAME2D_CHECKPOINT_CHAIN_MAX_CHECKPOINTS:
        _fail(
            "fiber_frame_kinematic_chain_state_count_invalid",
            "/state_count",
            "Kinematic-state count exceeds the bounded checkpoint profile.",
        )
    transition_count = _index(chain.transition_count, "/transition_count")
    if transition_count != state_count - 1:
        _fail(
            "fiber_frame_kinematic_chain_transition_count_mismatch",
            "/transition_count",
            "Exactly one transition is required per positive-epoch state.",
        )
    if (
        type(chain.committed_states) is not tuple
        or len(chain.committed_states) != state_count
        or not all(
            type(state) is FiberFrameNonlinearKinematicState
            for state in chain.committed_states
        )
    ):
        _fail(
            "fiber_frame_kinematic_chain_state_set_invalid",
            "/committed_states",
            "Committed-state tuple does not match state_count.",
        )
    if (
        type(chain.transitions) is not tuple
        or len(chain.transitions) != transition_count
        or not all(
            type(receipt) is FiberFrameNonlinearKinematicTransitionReceipt
            for receipt in chain.transitions
        )
    ):
        _fail(
            "fiber_frame_kinematic_chain_transition_set_invalid",
            "/transitions",
            "Transition tuple does not match transition_count.",
        )
    for index, state in enumerate(chain.committed_states):
        validate_fiber_frame_nonlinear_kinematic_state_shape(state)
        if (
            state.role != "committed"
            or state.epoch != index
            or state.step_index != index
        ):
            _fail(
                "fiber_frame_kinematic_chain_state_position_invalid",
                f"/committed_states/{index}",
                "Retained states must be committed and contiguous from epoch zero.",
            )
        for name, expected in (
            ("problem_contract_hash", chain.problem_contract_hash),
            ("model_ir_content_hash", chain.model_ir_content_hash),
            ("execution_topology_plan_id", chain.execution_topology_plan_id),
            ("execution_topology_plan_hash", chain.execution_topology_plan_hash),
            (
                "solver_coordinate_scaling_hash",
                chain.solver_coordinate_scaling_hash,
            ),
            ("case_id", chain.case_id),
            ("node_ids", chain.node_ids),
        ):
            if getattr(state, name) != expected:
                _fail(
                    "fiber_frame_kinematic_chain_state_binding_mismatch",
                    f"/committed_states/{index}/{name}",
                    "Every retained state must share the chain bindings.",
                )
    first = chain.committed_states[0]
    last = chain.committed_states[-1]
    if (
        first.checkpoint_state_hash != chain.root_checkpoint_state_hash
        or last.checkpoint_state_hash != chain.terminal_checkpoint_state_hash
        or first.state_hash != chain.root_kinematic_state_hash
        or last.state_hash != chain.terminal_kinematic_state_hash
    ):
        _fail(
            "fiber_frame_kinematic_chain_terminal_binding_mismatch",
            "/bindings",
            "Root or terminal checkpoint/kinematic bindings are inconsistent.",
        )
    for index, receipt in enumerate(chain.transitions, start=1):
        validate_fiber_frame_nonlinear_kinematic_transition_receipt(receipt)
        accepted = chain.committed_states[index - 1]
        committed = chain.committed_states[index]
        expected = {
            "problem_contract_hash": chain.problem_contract_hash,
            "model_ir_content_hash": chain.model_ir_content_hash,
            "execution_topology_plan_hash": chain.execution_topology_plan_hash,
            "case_id": chain.case_id,
            "epoch": index,
            "step_index": index,
            "parent_checkpoint_state_hash": accepted.checkpoint_state_hash,
            "checkpoint_state_hash": committed.checkpoint_state_hash,
            "accepted_state_hash": accepted.state_hash,
            "trial_state_hash": committed.parent_state_hash,
            "committed_state_hash": committed.state_hash,
        }
        for name, value in expected.items():
            if getattr(receipt, name) != value:
                _fail(
                    "fiber_frame_kinematic_chain_lifecycle_link_mismatch",
                    f"/transitions/{index - 1}/{name}",
                    "Transition does not connect adjacent checkpoint states.",
                )
        if receipt.load_factor != committed.load_factor:
            _fail(
                "fiber_frame_kinematic_chain_load_factor_mismatch",
                f"/transitions/{index - 1}/coordinates/load_factor",
                "Transition and committed state load factors differ.",
            )
    if not isinstance(chain.extensions, MappingProxyType) or chain.extensions:
        _fail(
            "fiber_frame_kinematic_chain_extensions_invalid",
            "/extensions",
            "Kinematic-state-chain v1 requires immutable empty extensions.",
        )
    expected_hash = canonical_hash(_chain_payload(chain, include_chain_hash=False))
    if chain.chain_hash != expected_hash:
        _fail(
            "fiber_frame_kinematic_chain_hash_mismatch",
            "/chain_hash",
            "Chain hash does not match canonical content.",
        )
    return chain


def validate_fiber_frame_nonlinear_kinematic_state_chain(
    problem: StatefulFiberFrame2DProblem,
    plan: FiberFrameNonlinearExecutionTopologyPlan,
    checkpoint_chain: StatefulFiberFrame2DCheckpointChain,
    chain: FiberFrameNonlinearKinematicStateChain,
) -> FiberFrameNonlinearKinematicStateChain:
    """Replay the complete checkpoint-to-kinematic-state lifecycle."""

    validate_fiber_frame_execution_topology_plan(plan)
    validate_fiber_frame_execution_topology_against_problem(problem, plan)
    validate_stateful_fiber_frame2d_checkpoint_chain(problem, checkpoint_chain)
    validate_fiber_frame_nonlinear_kinematic_state_chain_shape(chain)
    expected_bindings = {
        "checkpoint_chain_hash": checkpoint_chain.chain_hash,
        "problem_contract_hash": problem.contract_hash,
        "model_ir_content_hash": plan.model_ir_content_hash,
        "execution_topology_plan_id": plan.plan_id,
        "execution_topology_plan_hash": plan.plan_hash,
        "solver_coordinate_scaling_hash": plan.solver_coordinate_scaling_hash,
        "case_id": problem.case_id,
        "node_ids": plan.node_ids,
        "state_count": len(checkpoint_chain.checkpoints),
        "transition_count": len(checkpoint_chain.checkpoints) - 1,
        "root_checkpoint_state_hash": checkpoint_chain.root_checkpoint.state_hash,
        "terminal_checkpoint_state_hash": (
            checkpoint_chain.terminal_checkpoint.state_hash
        ),
    }
    for name, expected in expected_bindings.items():
        if getattr(chain, name) != expected:
            _fail(
                "fiber_frame_kinematic_chain_source_binding_mismatch",
                f"/bindings/{name}",
                "Kinematic chain does not bind the supplied problem, plan, or checkpoints.",
            )
    expected_states, expected_transitions = _project_checkpoint_chain(
        plan,
        checkpoint_chain,
    )
    for index, (actual, expected, checkpoint) in enumerate(
        zip(
            chain.committed_states,
            expected_states,
            checkpoint_chain.checkpoints,
            strict=True,
        )
    ):
        _validate_state_against_sources(plan, checkpoint, actual)
        _require_exact_state(actual, expected, path=f"/committed_states/{index}")
    for index, (actual, expected) in enumerate(
        zip(chain.transitions, expected_transitions, strict=True)
    ):
        if actual.to_manifest() != expected.to_manifest():
            _fail(
                "fiber_frame_kinematic_chain_transition_replay_mismatch",
                f"/transitions/{index}",
                "Transition differs from checkpoint/plan lifecycle replay.",
            )
    return chain


def validate_fiber_frame_nonlinear_kinematic_state_array_bytes(
    state: FiberFrameNonlinearKinematicState,
    *,
    name: str,
    payload: bytes | bytearray | memoryview,
) -> np.ndarray:
    """Validate one external state array against its exact byte descriptor."""

    validate_fiber_frame_nonlinear_kinematic_state_shape(state)
    if type(name) is not str or name not in _STATE_ARRAY_NAMES:
        _fail(
            "fiber_frame_kinematic_state_array_name_invalid",
            "/name",
            "Unknown nonlinear kinematic-state array name.",
        )
    if not isinstance(payload, bytes):
        _fail(
            "fiber_frame_kinematic_state_array_bytes_invalid",
            f"/arrays/{name}",
            "External state-array payload must be immutable bytes.",
        )
    descriptor = _descriptor_by_name(state.descriptors, name)
    if len(payload) != descriptor.byte_length:
        _fail(
            "fiber_frame_kinematic_state_array_bytes_invalid",
            f"/arrays/{name}",
            "External state-array byte length differs from its descriptor.",
        )
    try:
        array = np.frombuffer(payload, dtype=descriptor.dtype).reshape(descriptor.shape)
    except (TypeError, ValueError) as exc:
        raise FiberFrameNonlinearKinematicStateError(
            "fiber_frame_kinematic_state_array_bytes_invalid",
            f"/arrays/{name}",
            "External state-array bytes cannot be reshaped.",
        ) from exc
    if not np.all(np.isfinite(array)):
        _fail(
            "fiber_frame_kinematic_state_array_nonfinite",
            f"/arrays/{name}",
            "External state-array bytes contain non-finite values.",
        )
    if (
        array_data_hash(array) != descriptor.data_hash
        or _array_descriptor(name, array, state.node_ids) != descriptor
    ):
        _fail(
            "fiber_frame_kinematic_state_array_hash_mismatch",
            f"/arrays/{name}",
            "External state-array bytes do not match the descriptor.",
        )
    return immutable_array(array, dtype="<f8")


def validate_fiber_frame_nonlinear_kinematic_state_manifest(
    payload: Any,
) -> Mapping[str, Any]:
    """Validate a descriptor-only state manifest and its canonical hash."""

    manifest = _manifest_object(payload, "/")
    _validate_state_manifest_semantics(manifest)
    unsigned = dict(manifest)
    claimed = unsigned.pop("state_hash")
    if claimed != canonical_hash(unsigned):
        _fail(
            "fiber_frame_kinematic_state_hash_mismatch",
            "/state_hash",
            "Manifest state hash does not match canonical content.",
        )
    return manifest


def validate_fiber_frame_nonlinear_kinematic_state_chain_manifest(
    payload: Any,
) -> Mapping[str, Any]:
    """Validate descriptor-only chain semantics and all nested lifecycle links."""

    manifest = _manifest_object(payload, "/")
    _validate_chain_manifest_semantics(manifest)
    unsigned = dict(manifest)
    claimed = unsigned.pop("chain_hash")
    if claimed != canonical_hash(unsigned):
        _fail(
            "fiber_frame_kinematic_chain_hash_mismatch",
            "/chain_hash",
            "Manifest chain hash does not match canonical content.",
        )
    return manifest


def _project_checkpoint_chain(
    plan: FiberFrameNonlinearExecutionTopologyPlan,
    checkpoint_chain: StatefulFiberFrame2DCheckpointChain,
) -> tuple[
    tuple[FiberFrameNonlinearKinematicState, ...],
    tuple[FiberFrameNonlinearKinematicTransitionReceipt, ...],
]:
    checkpoints = checkpoint_chain.checkpoints
    root = _build_state(
        plan,
        checkpoints[0],
        role="committed",
        parent_state_hash=None,
    )
    states: list[FiberFrameNonlinearKinematicState] = [root]
    transitions: list[FiberFrameNonlinearKinematicTransitionReceipt] = []
    for checkpoint in checkpoints[1:]:
        accepted = states[-1]
        trial = _build_state(
            plan,
            checkpoint,
            role="trial",
            parent_state_hash=accepted.state_hash,
        )
        committed = _build_state(
            plan,
            checkpoint,
            role="committed",
            parent_state_hash=trial.state_hash,
        )
        transitions.append(
            _build_transition(
                plan,
                checkpoint,
                accepted=accepted,
                trial=trial,
                committed=committed,
            )
        )
        states.append(committed)
    return tuple(states), tuple(transitions)


def _build_state(
    plan: FiberFrameNonlinearExecutionTopologyPlan,
    checkpoint: StatefulFiberFrame2DCheckpoint,
    *,
    role: Literal["trial", "committed"],
    parent_state_hash: str | None,
) -> FiberFrameNonlinearKinematicState:
    physical = _float_vector(
        checkpoint.global_displacements,
        plan.solver_dof_count,
        "/checkpoint/global_displacements",
    )
    generalized = physical_3dof_to_solver_generalized(plan, physical)
    canonical = physical_3dof_to_canonical_6dof(plan, physical)
    arrays = MappingProxyType(
        {
            "checkpoint_displacement_physical_3dof": physical,
            "solver_generalized_coordinates_m": generalized,
            "canonical_displacement_si": canonical,
        }
    )
    descriptors = tuple(
        _array_descriptor(name, arrays[name], plan.node_ids)
        for name in _STATE_ARRAY_NAMES
    )
    provisional = FiberFrameNonlinearKinematicState(
        schema_version=FIBER_FRAME_NONLINEAR_KINEMATIC_STATE_SCHEMA_VERSION,
        state_id=_state_id(plan, checkpoint, role),
        state_hash=_HASH_ZERO,
        authority_profile=FIBER_FRAME_NONLINEAR_KINEMATIC_AUTHORITY_PROFILE,
        carrier_profile=FIBER_FRAME_NONLINEAR_KINEMATIC_CARRIER_PROFILE,
        state_ir_usage_profile=FIBER_FRAME_STATE_IR_USAGE_PROFILE,
        role=role,
        problem_contract_hash=plan.problem_contract_hash,
        model_ir_content_hash=plan.model_ir_content_hash,
        execution_topology_plan_id=plan.plan_id,
        execution_topology_plan_hash=plan.plan_hash,
        solver_coordinate_scaling_hash=plan.solver_coordinate_scaling_hash,
        checkpoint_state_hash=checkpoint.state_hash,
        parent_checkpoint_state_hash=checkpoint.parent_state_hash,
        case_id=checkpoint.case_id,
        node_ids=plan.node_ids,
        epoch=checkpoint.epoch,
        step_index=checkpoint.step_index,
        load_factor=checkpoint.load_factor,
        parent_state_hash=parent_state_hash,
        node_count=plan.node_count,
        solver_dof_count=plan.solver_dof_count,
        physical_dof_count=plan.physical_dof_count,
        rotation_coordinate_scale_m=(
            plan.solver_coordinate_scaling.rotation_coordinate_scale_m
        ),
        descriptors=descriptors,
        _arrays=arrays,
        extensions=MappingProxyType({}),
    )
    state = replace(
        provisional,
        state_hash=canonical_hash(
            _state_payload(provisional, include_state_hash=False)
        ),
    )
    validate_fiber_frame_nonlinear_kinematic_state_shape(state)
    _validate_state_against_sources(plan, checkpoint, state)
    return state


def _build_transition(
    plan: FiberFrameNonlinearExecutionTopologyPlan,
    checkpoint: StatefulFiberFrame2DCheckpoint,
    *,
    accepted: FiberFrameNonlinearKinematicState,
    trial: FiberFrameNonlinearKinematicState,
    committed: FiberFrameNonlinearKinematicState,
) -> FiberFrameNonlinearKinematicTransitionReceipt:
    if checkpoint.parent_state_hash is None:
        _fail(
            "fiber_frame_kinematic_transition_checkpoint_parent_missing",
            "/checkpoint/parent_state_hash",
            "Positive-epoch checkpoint requires a parent hash.",
        )
    provisional = FiberFrameNonlinearKinematicTransitionReceipt(
        schema_version=FIBER_FRAME_NONLINEAR_KINEMATIC_TRANSITION_SCHEMA_VERSION,
        transition_hash=_HASH_ZERO,
        authority_profile=FIBER_FRAME_NONLINEAR_KINEMATIC_AUTHORITY_PROFILE,
        lifecycle_profile=FIBER_FRAME_NONLINEAR_KINEMATIC_LIFECYCLE_PROFILE,
        problem_contract_hash=plan.problem_contract_hash,
        model_ir_content_hash=plan.model_ir_content_hash,
        execution_topology_plan_hash=plan.plan_hash,
        case_id=checkpoint.case_id,
        epoch=checkpoint.epoch,
        step_index=checkpoint.step_index,
        load_factor=checkpoint.load_factor,
        parent_checkpoint_state_hash=checkpoint.parent_state_hash,
        checkpoint_state_hash=checkpoint.state_hash,
        accepted_state_hash=accepted.state_hash,
        trial_state_hash=trial.state_hash,
        committed_state_hash=committed.state_hash,
        extensions=MappingProxyType({}),
    )
    receipt = replace(
        provisional,
        transition_hash=canonical_hash(
            _transition_payload(provisional, include_transition_hash=False)
        ),
    )
    return validate_fiber_frame_nonlinear_kinematic_transition_receipt(receipt)


def _validate_state_against_sources(
    plan: FiberFrameNonlinearExecutionTopologyPlan,
    checkpoint: StatefulFiberFrame2DCheckpoint,
    state: FiberFrameNonlinearKinematicState,
) -> None:
    validate_fiber_frame_nonlinear_kinematic_state_shape(state)
    expected = {
        "problem_contract_hash": plan.problem_contract_hash,
        "model_ir_content_hash": plan.model_ir_content_hash,
        "execution_topology_plan_id": plan.plan_id,
        "execution_topology_plan_hash": plan.plan_hash,
        "solver_coordinate_scaling_hash": plan.solver_coordinate_scaling_hash,
        "checkpoint_state_hash": checkpoint.state_hash,
        "parent_checkpoint_state_hash": checkpoint.parent_state_hash,
        "case_id": checkpoint.case_id,
        "node_ids": plan.node_ids,
        "epoch": checkpoint.epoch,
        "step_index": checkpoint.step_index,
        "load_factor": checkpoint.load_factor,
        "node_count": plan.node_count,
        "solver_dof_count": plan.solver_dof_count,
        "physical_dof_count": plan.physical_dof_count,
        "rotation_coordinate_scale_m": (
            plan.solver_coordinate_scaling.rotation_coordinate_scale_m
        ),
    }
    for name, value in expected.items():
        if getattr(state, name) != value:
            _fail(
                "fiber_frame_kinematic_state_source_binding_mismatch",
                f"/{name}",
                "State does not bind the exact plan and checkpoint source.",
            )
    physical = state.array("checkpoint_displacement_physical_3dof")
    expected_physical = np.asarray(checkpoint.global_displacements, dtype="<f8")
    if not np.array_equal(physical, expected_physical):
        _fail(
            "fiber_frame_kinematic_state_checkpoint_displacement_mismatch",
            "/arrays/checkpoint_displacement_physical_3dof",
            "Retained physical displacement differs from checkpoint bytes.",
        )
    expected_generalized = physical_3dof_to_solver_generalized(plan, physical)
    expected_canonical = physical_3dof_to_canonical_6dof(plan, physical)
    if not np.array_equal(
        state.array("solver_generalized_coordinates_m"),
        expected_generalized,
    ):
        _fail(
            "fiber_frame_kinematic_state_solver_mapping_mismatch",
            "/arrays/solver_generalized_coordinates_m",
            "State does not use the exact solver-coordinate scaling receipt.",
        )
    if not np.array_equal(state.array("canonical_displacement_si"), expected_canonical):
        _fail(
            "fiber_frame_kinematic_state_canonical_mapping_mismatch",
            "/arrays/canonical_displacement_si",
            "State does not use the exact topology scatter mapping.",
        )
    gathered = canonical_6dof_to_physical_3dof(plan, expected_canonical)
    if not np.array_equal(gathered, physical):
        _fail(
            "fiber_frame_kinematic_state_canonical_roundtrip_mismatch",
            "/arrays/canonical_displacement_si",
            "Canonical displacement does not round-trip to checkpoint coordinates.",
        )
    physical_roundtrip = solver_generalized_to_physical_3dof(
        plan,
        expected_generalized,
    )
    tolerance = 2.0 * np.finfo(np.float64).eps * np.maximum(1.0, np.abs(physical))
    if not np.all(np.abs(physical_roundtrip - physical) <= tolerance):
        _fail(
            "fiber_frame_kinematic_state_solver_roundtrip_mismatch",
            "/arrays/solver_generalized_coordinates_m",
            "Solver generalized coordinates do not round-trip within FP64 bounds.",
        )


def _require_exact_state(
    actual: FiberFrameNonlinearKinematicState,
    expected: FiberFrameNonlinearKinematicState,
    *,
    path: str,
) -> None:
    if actual.to_manifest() != expected.to_manifest():
        _fail(
            "fiber_frame_kinematic_chain_state_replay_mismatch",
            path,
            "Retained state manifest differs from checkpoint/plan replay.",
        )
    for name in _STATE_ARRAY_NAMES:
        if not np.array_equal(actual.array(name), expected.array(name)):
            _fail(
                "fiber_frame_kinematic_chain_state_replay_mismatch",
                f"{path}/arrays/{name}",
                "Retained state bytes differ from checkpoint/plan replay.",
            )


def _state_payload(
    state: FiberFrameNonlinearKinematicState,
    *,
    include_state_hash: bool,
) -> dict[str, Any]:
    payload = {
        "schema_version": state.schema_version,
        "state_id": state.state_id,
        "state_hash": state.state_hash,
        "role": state.role,
        "authority_profile": state.authority_profile,
        "carrier_profile": state.carrier_profile,
        "state_ir_usage_profile": state.state_ir_usage_profile,
        "bindings": {
            "problem_contract_hash": state.problem_contract_hash,
            "model_ir_content_hash": state.model_ir_content_hash,
            "execution_topology_plan_id": state.execution_topology_plan_id,
            "execution_topology_plan_hash": state.execution_topology_plan_hash,
            "execution_topology_schema_version": (
                FIBER_FRAME_EXECUTION_TOPOLOGY_SCHEMA_VERSION
            ),
            "solver_coordinate_scaling_hash": state.solver_coordinate_scaling_hash,
            "checkpoint_state_hash": state.checkpoint_state_hash,
            "parent_checkpoint_state_hash": state.parent_checkpoint_state_hash,
            "checkpoint_schema_version": (
                STATEFUL_FIBER_FRAME2D_CHECKPOINT_SCHEMA_VERSION
            ),
            "case_id": state.case_id,
        },
        "coordinates": {
            "epoch": state.epoch,
            "step_index": state.step_index,
            "load_factor": state.load_factor,
            "parent_state_hash": state.parent_state_hash,
        },
        "layout": {
            "node_ids": list(state.node_ids),
            "node_count": state.node_count,
            "solver_dof_count": state.solver_dof_count,
            "physical_dof_count": state.physical_dof_count,
            "solver_components": list(_SOLVER_COMPONENTS),
            "canonical_components": list(_CANONICAL_COMPONENTS),
            "checkpoint_displacement_units": list(_CHECKPOINT_DISPLACEMENT_UNITS),
            "generalized_coordinate_units": list(_GENERALIZED_COORDINATE_UNITS),
            "canonical_displacement_units": list(_CANONICAL_DISPLACEMENT_UNITS),
            "rotation_coordinate_scale_m": state.rotation_coordinate_scale_m,
        },
        "array_descriptors": [row.to_dict() for row in state.descriptors],
        "claim_boundary": dict(FIBER_FRAME_NONLINEAR_KINEMATIC_STATE_CLAIM_BOUNDARY),
        "extensions": dict(state.extensions),
    }
    if not include_state_hash:
        payload.pop("state_hash")
    return payload


def _transition_payload(
    receipt: FiberFrameNonlinearKinematicTransitionReceipt,
    *,
    include_transition_hash: bool,
) -> dict[str, Any]:
    payload = {
        "schema_version": receipt.schema_version,
        "transition_hash": receipt.transition_hash,
        "authority_profile": receipt.authority_profile,
        "lifecycle_profile": receipt.lifecycle_profile,
        "bindings": {
            "problem_contract_hash": receipt.problem_contract_hash,
            "model_ir_content_hash": receipt.model_ir_content_hash,
            "execution_topology_plan_hash": receipt.execution_topology_plan_hash,
            "parent_checkpoint_state_hash": receipt.parent_checkpoint_state_hash,
            "checkpoint_state_hash": receipt.checkpoint_state_hash,
            "case_id": receipt.case_id,
        },
        "coordinates": {
            "epoch": receipt.epoch,
            "step_index": receipt.step_index,
            "load_factor": receipt.load_factor,
        },
        "lifecycle": {
            "accepted_role": "committed",
            "accepted_state_hash": receipt.accepted_state_hash,
            "trial_role": "trial",
            "trial_state_hash": receipt.trial_state_hash,
            "committed_role": "committed",
            "committed_state_hash": receipt.committed_state_hash,
        },
        "claim_boundary": dict(
            FIBER_FRAME_NONLINEAR_KINEMATIC_TRANSITION_CLAIM_BOUNDARY
        ),
        "extensions": dict(receipt.extensions),
    }
    if not include_transition_hash:
        payload.pop("transition_hash")
    return payload


def _chain_payload(
    chain: FiberFrameNonlinearKinematicStateChain,
    *,
    include_chain_hash: bool,
) -> dict[str, Any]:
    payload = {
        "schema_version": chain.schema_version,
        "chain_hash": chain.chain_hash,
        "authority_profile": chain.authority_profile,
        "carrier_profile": chain.carrier_profile,
        "lifecycle_profile": chain.lifecycle_profile,
        "state_ir_usage_profile": chain.state_ir_usage_profile,
        "bindings": {
            "checkpoint_chain_hash": chain.checkpoint_chain_hash,
            "checkpoint_chain_schema_version": (
                STATEFUL_FIBER_FRAME2D_CHECKPOINT_CHAIN_SCHEMA_VERSION
            ),
            "problem_contract_hash": chain.problem_contract_hash,
            "model_ir_content_hash": chain.model_ir_content_hash,
            "execution_topology_plan_id": chain.execution_topology_plan_id,
            "execution_topology_plan_hash": chain.execution_topology_plan_hash,
            "execution_topology_schema_version": (
                FIBER_FRAME_EXECUTION_TOPOLOGY_SCHEMA_VERSION
            ),
            "solver_coordinate_scaling_hash": chain.solver_coordinate_scaling_hash,
            "case_id": chain.case_id,
            "node_ids": list(chain.node_ids),
            "root_checkpoint_state_hash": chain.root_checkpoint_state_hash,
            "terminal_checkpoint_state_hash": chain.terminal_checkpoint_state_hash,
            "root_kinematic_state_hash": chain.root_kinematic_state_hash,
            "terminal_kinematic_state_hash": chain.terminal_kinematic_state_hash,
        },
        "state_count": chain.state_count,
        "transition_count": chain.transition_count,
        "committed_states": [state.to_manifest() for state in chain.committed_states],
        "transitions": [receipt.to_manifest() for receipt in chain.transitions],
        "claim_boundary": dict(FIBER_FRAME_NONLINEAR_KINEMATIC_CLAIM_BOUNDARY),
        "extensions": dict(chain.extensions),
    }
    if not include_chain_hash:
        payload.pop("chain_hash")
    return payload


def _validate_state_manifest_semantics(manifest: Mapping[str, Any]) -> None:
    _exact_keys(
        manifest,
        {
            "schema_version",
            "state_id",
            "state_hash",
            "role",
            "authority_profile",
            "carrier_profile",
            "state_ir_usage_profile",
            "bindings",
            "coordinates",
            "layout",
            "array_descriptors",
            "claim_boundary",
            "extensions",
        },
        "/",
    )
    if (
        manifest["schema_version"]
        != FIBER_FRAME_NONLINEAR_KINEMATIC_STATE_SCHEMA_VERSION
    ):
        _fail(
            "fiber_frame_kinematic_state_schema_invalid",
            "/schema_version",
            "Unsupported nonlinear kinematic-state schema.",
        )
    _validate_profiles(
        authority_profile=manifest["authority_profile"],
        carrier_profile=manifest["carrier_profile"],
        state_ir_usage_profile=manifest["state_ir_usage_profile"],
    )
    _stable_id(manifest["state_id"], "/state_id")
    _require_hash(manifest["state_hash"], "/state_hash")
    role = manifest["role"]
    if type(role) is not str or role not in ("trial", "committed"):
        _fail(
            "fiber_frame_kinematic_state_role_invalid",
            "/role",
            "Kinematic state role must be trial or committed.",
        )
    bindings = _manifest_object(manifest["bindings"], "/bindings")
    _exact_keys(
        bindings,
        {
            "problem_contract_hash",
            "model_ir_content_hash",
            "execution_topology_plan_id",
            "execution_topology_plan_hash",
            "execution_topology_schema_version",
            "solver_coordinate_scaling_hash",
            "checkpoint_state_hash",
            "parent_checkpoint_state_hash",
            "checkpoint_schema_version",
            "case_id",
        },
        "/bindings",
    )
    for name in (
        "problem_contract_hash",
        "model_ir_content_hash",
        "execution_topology_plan_hash",
        "solver_coordinate_scaling_hash",
        "checkpoint_state_hash",
    ):
        _require_hash(bindings[name], f"/bindings/{name}")
    if bindings["parent_checkpoint_state_hash"] is not None:
        _require_hash(
            bindings["parent_checkpoint_state_hash"],
            "/bindings/parent_checkpoint_state_hash",
        )
    _stable_id(
        bindings["execution_topology_plan_id"],
        "/bindings/execution_topology_plan_id",
    )
    _nonempty_string(bindings["case_id"], "/bindings/case_id")
    if (
        bindings["execution_topology_schema_version"]
        != FIBER_FRAME_EXECUTION_TOPOLOGY_SCHEMA_VERSION
        or bindings["checkpoint_schema_version"]
        != STATEFUL_FIBER_FRAME2D_CHECKPOINT_SCHEMA_VERSION
    ):
        _fail(
            "fiber_frame_kinematic_state_source_schema_invalid",
            "/bindings",
            "State source schema binding is unsupported.",
        )
    coordinates = _manifest_object(manifest["coordinates"], "/coordinates")
    _exact_keys(
        coordinates,
        {"epoch", "step_index", "load_factor", "parent_state_hash"},
        "/coordinates",
    )
    epoch = _index(coordinates["epoch"], "/coordinates/epoch")
    step = _index(coordinates["step_index"], "/coordinates/step_index")
    if step != epoch:
        _fail(
            "fiber_frame_kinematic_state_step_epoch_mismatch",
            "/coordinates/step_index",
            "Checkpoint step index must equal epoch.",
        )
    load_factor = _finite_float(
        coordinates["load_factor"],
        "/coordinates/load_factor",
    )
    parent_state_hash = coordinates["parent_state_hash"]
    if parent_state_hash is not None:
        _require_hash(parent_state_hash, "/coordinates/parent_state_hash")
    if epoch == 0:
        if (
            role != "committed"
            or parent_state_hash is not None
            or bindings["parent_checkpoint_state_hash"] is not None
            or load_factor != 0.0
        ):
            _fail(
                "fiber_frame_kinematic_state_initial_lineage_invalid",
                "/coordinates",
                "Epoch zero must be an unparented committed zero-load state.",
            )
    elif parent_state_hash is None or bindings["parent_checkpoint_state_hash"] is None:
        _fail(
            "fiber_frame_kinematic_state_parent_missing",
            "/coordinates/parent_state_hash",
            "Positive-epoch state requires state and checkpoint ancestry.",
        )
    layout = _manifest_object(manifest["layout"], "/layout")
    _exact_keys(
        layout,
        {
            "node_ids",
            "node_count",
            "solver_dof_count",
            "physical_dof_count",
            "solver_components",
            "canonical_components",
            "checkpoint_displacement_units",
            "generalized_coordinate_units",
            "canonical_displacement_units",
            "rotation_coordinate_scale_m",
        },
        "/layout",
    )
    node_ids = _manifest_stable_id_list(layout["node_ids"], "/layout/node_ids")
    node_count = _positive_index(layout["node_count"], "/layout/node_count")
    solver_count = _positive_index(
        layout["solver_dof_count"],
        "/layout/solver_dof_count",
    )
    physical_count = _positive_index(
        layout["physical_dof_count"],
        "/layout/physical_dof_count",
    )
    if (
        len(node_ids) != node_count
        or len(set(node_ids)) != len(node_ids)
        or solver_count != 3 * node_count
        or physical_count != 6 * node_count
    ):
        _fail(
            "fiber_frame_kinematic_state_layout_invalid",
            "/layout",
            "Node and DOF counts are inconsistent.",
        )
    if (
        layout["solver_components"] != list(_SOLVER_COMPONENTS)
        or layout["canonical_components"] != list(_CANONICAL_COMPONENTS)
        or layout["checkpoint_displacement_units"]
        != list(_CHECKPOINT_DISPLACEMENT_UNITS)
        or layout["generalized_coordinate_units"] != list(_GENERALIZED_COORDINATE_UNITS)
        or layout["canonical_displacement_units"] != list(_CANONICAL_DISPLACEMENT_UNITS)
    ):
        _fail(
            "fiber_frame_kinematic_state_layout_invalid",
            "/layout",
            "DOF component or unit layout is invalid.",
        )
    _positive_float(
        layout["rotation_coordinate_scale_m"],
        "/layout/rotation_coordinate_scale_m",
    )
    descriptors = manifest["array_descriptors"]
    if not isinstance(descriptors, list) or len(descriptors) != len(_STATE_ARRAY_NAMES):
        _fail(
            "fiber_frame_kinematic_state_descriptor_set_invalid",
            "/array_descriptors",
            "State manifest requires all array descriptors.",
        )
    expected_shapes = {
        "checkpoint_displacement_physical_3dof": [solver_count],
        "solver_generalized_coordinates_m": [solver_count],
        "canonical_displacement_si": [physical_count],
    }
    for index, (name, descriptor) in enumerate(
        zip(_STATE_ARRAY_NAMES, descriptors, strict=True)
    ):
        _validate_descriptor_manifest(
            descriptor,
            name=name,
            shape=expected_shapes[name],
            node_ids=tuple(node_ids),
            path=f"/array_descriptors/{index}",
        )
    _validate_claim_boundary(
        manifest["claim_boundary"],
        FIBER_FRAME_NONLINEAR_KINEMATIC_STATE_CLAIM_BOUNDARY,
        "/claim_boundary",
    )
    if manifest["extensions"] != {}:
        _fail(
            "fiber_frame_kinematic_state_extensions_invalid",
            "/extensions",
            "Kinematic-state v1 requires empty extensions.",
        )


def _validate_transition_manifest_semantics(
    manifest: Mapping[str, Any],
    path: str,
) -> None:
    _exact_keys(
        manifest,
        {
            "schema_version",
            "transition_hash",
            "authority_profile",
            "lifecycle_profile",
            "bindings",
            "coordinates",
            "lifecycle",
            "claim_boundary",
            "extensions",
        },
        path,
    )
    if (
        manifest["schema_version"]
        != FIBER_FRAME_NONLINEAR_KINEMATIC_TRANSITION_SCHEMA_VERSION
    ):
        _fail(
            "fiber_frame_kinematic_transition_schema_invalid",
            f"{path}/schema_version",
            "Unsupported nonlinear kinematic-transition schema.",
        )
    if (
        manifest["authority_profile"]
        != FIBER_FRAME_NONLINEAR_KINEMATIC_AUTHORITY_PROFILE
    ):
        _fail(
            "fiber_frame_kinematic_authority_profile_invalid",
            f"{path}/authority_profile",
            "Kinematic transport cannot acquire result authority.",
        )
    if (
        manifest["lifecycle_profile"]
        != FIBER_FRAME_NONLINEAR_KINEMATIC_LIFECYCLE_PROFILE
    ):
        _fail(
            "fiber_frame_kinematic_lifecycle_profile_invalid",
            f"{path}/lifecycle_profile",
            "Unsupported kinematic lifecycle profile.",
        )
    _require_hash(manifest["transition_hash"], f"{path}/transition_hash")
    bindings = _manifest_object(manifest["bindings"], f"{path}/bindings")
    _exact_keys(
        bindings,
        {
            "problem_contract_hash",
            "model_ir_content_hash",
            "execution_topology_plan_hash",
            "parent_checkpoint_state_hash",
            "checkpoint_state_hash",
            "case_id",
        },
        f"{path}/bindings",
    )
    for name in (
        "problem_contract_hash",
        "model_ir_content_hash",
        "execution_topology_plan_hash",
        "parent_checkpoint_state_hash",
        "checkpoint_state_hash",
    ):
        _require_hash(bindings[name], f"{path}/bindings/{name}")
    _nonempty_string(bindings["case_id"], f"{path}/bindings/case_id")
    coordinates = _manifest_object(manifest["coordinates"], f"{path}/coordinates")
    _exact_keys(
        coordinates,
        {"epoch", "step_index", "load_factor"},
        f"{path}/coordinates",
    )
    epoch = _positive_index(coordinates["epoch"], f"{path}/coordinates/epoch")
    if (
        _positive_index(
            coordinates["step_index"],
            f"{path}/coordinates/step_index",
        )
        != epoch
    ):
        _fail(
            "fiber_frame_kinematic_transition_step_epoch_mismatch",
            f"{path}/coordinates/step_index",
            "Transition step index must equal epoch.",
        )
    _finite_float(coordinates["load_factor"], f"{path}/coordinates/load_factor")
    lifecycle = _manifest_object(manifest["lifecycle"], f"{path}/lifecycle")
    _exact_keys(
        lifecycle,
        {
            "accepted_role",
            "accepted_state_hash",
            "trial_role",
            "trial_state_hash",
            "committed_role",
            "committed_state_hash",
        },
        f"{path}/lifecycle",
    )
    if (
        lifecycle["accepted_role"] != "committed"
        or lifecycle["trial_role"] != "trial"
        or lifecycle["committed_role"] != "committed"
    ):
        _fail(
            "fiber_frame_kinematic_transition_role_invalid",
            f"{path}/lifecycle",
            "Transition lifecycle roles are invalid.",
        )
    state_hashes = tuple(
        lifecycle[name]
        for name in (
            "accepted_state_hash",
            "trial_state_hash",
            "committed_state_hash",
        )
    )
    for name, value in zip(
        ("accepted_state_hash", "trial_state_hash", "committed_state_hash"),
        state_hashes,
        strict=True,
    ):
        _require_hash(value, f"{path}/lifecycle/{name}")
    if len(set(state_hashes)) != 3:
        _fail(
            "fiber_frame_kinematic_transition_state_cycle",
            f"{path}/lifecycle",
            "Accepted, trial, and committed hashes must be distinct.",
        )
    _validate_claim_boundary(
        manifest["claim_boundary"],
        FIBER_FRAME_NONLINEAR_KINEMATIC_TRANSITION_CLAIM_BOUNDARY,
        f"{path}/claim_boundary",
    )
    if manifest["extensions"] != {}:
        _fail(
            "fiber_frame_kinematic_transition_extensions_invalid",
            f"{path}/extensions",
            "Transition v1 requires empty extensions.",
        )
    unsigned = dict(manifest)
    claimed = unsigned.pop("transition_hash")
    if claimed != canonical_hash(unsigned):
        _fail(
            "fiber_frame_kinematic_transition_hash_mismatch",
            f"{path}/transition_hash",
            "Transition manifest hash does not match canonical content.",
        )


def _validate_chain_manifest_semantics(manifest: Mapping[str, Any]) -> None:
    _exact_keys(
        manifest,
        {
            "schema_version",
            "chain_hash",
            "authority_profile",
            "carrier_profile",
            "lifecycle_profile",
            "state_ir_usage_profile",
            "bindings",
            "state_count",
            "transition_count",
            "committed_states",
            "transitions",
            "claim_boundary",
            "extensions",
        },
        "/",
    )
    if (
        manifest["schema_version"]
        != FIBER_FRAME_NONLINEAR_KINEMATIC_STATE_CHAIN_SCHEMA_VERSION
    ):
        _fail(
            "fiber_frame_kinematic_chain_schema_invalid",
            "/schema_version",
            "Unsupported nonlinear kinematic-state-chain schema.",
        )
    _validate_profiles(
        authority_profile=manifest["authority_profile"],
        carrier_profile=manifest["carrier_profile"],
        lifecycle_profile=manifest["lifecycle_profile"],
        state_ir_usage_profile=manifest["state_ir_usage_profile"],
    )
    _require_hash(manifest["chain_hash"], "/chain_hash")
    bindings = _manifest_object(manifest["bindings"], "/bindings")
    _exact_keys(
        bindings,
        {
            "checkpoint_chain_hash",
            "checkpoint_chain_schema_version",
            "problem_contract_hash",
            "model_ir_content_hash",
            "execution_topology_plan_id",
            "execution_topology_plan_hash",
            "execution_topology_schema_version",
            "solver_coordinate_scaling_hash",
            "case_id",
            "node_ids",
            "root_checkpoint_state_hash",
            "terminal_checkpoint_state_hash",
            "root_kinematic_state_hash",
            "terminal_kinematic_state_hash",
        },
        "/bindings",
    )
    for name in (
        "checkpoint_chain_hash",
        "problem_contract_hash",
        "model_ir_content_hash",
        "execution_topology_plan_hash",
        "solver_coordinate_scaling_hash",
        "root_checkpoint_state_hash",
        "terminal_checkpoint_state_hash",
        "root_kinematic_state_hash",
        "terminal_kinematic_state_hash",
    ):
        _require_hash(bindings[name], f"/bindings/{name}")
    if (
        bindings["checkpoint_chain_schema_version"]
        != STATEFUL_FIBER_FRAME2D_CHECKPOINT_CHAIN_SCHEMA_VERSION
        or bindings["execution_topology_schema_version"]
        != FIBER_FRAME_EXECUTION_TOPOLOGY_SCHEMA_VERSION
    ):
        _fail(
            "fiber_frame_kinematic_chain_source_schema_invalid",
            "/bindings",
            "Chain source schema binding is unsupported.",
        )
    _stable_id(
        bindings["execution_topology_plan_id"],
        "/bindings/execution_topology_plan_id",
    )
    _nonempty_string(bindings["case_id"], "/bindings/case_id")
    node_ids = _manifest_stable_id_list(bindings["node_ids"], "/bindings/node_ids")
    if len(set(node_ids)) != len(node_ids):
        _fail(
            "fiber_frame_kinematic_chain_node_id_duplicate",
            "/bindings/node_ids",
            "Node identities must be unique.",
        )
    state_count = _positive_index(manifest["state_count"], "/state_count")
    if state_count > STATEFUL_FIBER_FRAME2D_CHECKPOINT_CHAIN_MAX_CHECKPOINTS:
        _fail(
            "fiber_frame_kinematic_chain_state_count_invalid",
            "/state_count",
            "Kinematic-state count exceeds the bounded checkpoint profile.",
        )
    transition_count = _index(manifest["transition_count"], "/transition_count")
    if transition_count != state_count - 1:
        _fail(
            "fiber_frame_kinematic_chain_transition_count_mismatch",
            "/transition_count",
            "Exactly one transition is required per positive-epoch state.",
        )
    states = manifest["committed_states"]
    transitions = manifest["transitions"]
    if not isinstance(states, list) or len(states) != state_count:
        _fail(
            "fiber_frame_kinematic_chain_state_set_invalid",
            "/committed_states",
            "Committed-state list does not match state_count.",
        )
    if not isinstance(transitions, list) or len(transitions) != transition_count:
        _fail(
            "fiber_frame_kinematic_chain_transition_set_invalid",
            "/transitions",
            "Transition list does not match transition_count.",
        )
    state_rows: list[Mapping[str, Any]] = []
    for index, value in enumerate(states):
        state = _manifest_object(value, f"/committed_states/{index}")
        validate_fiber_frame_nonlinear_kinematic_state_manifest(state)
        if state["role"] != "committed" or state["coordinates"]["epoch"] != index:
            _fail(
                "fiber_frame_kinematic_chain_state_position_invalid",
                f"/committed_states/{index}",
                "Retained state must be committed at its contiguous epoch.",
            )
        state_bindings = state["bindings"]
        for name, expected in (
            ("problem_contract_hash", bindings["problem_contract_hash"]),
            ("model_ir_content_hash", bindings["model_ir_content_hash"]),
            (
                "execution_topology_plan_id",
                bindings["execution_topology_plan_id"],
            ),
            (
                "execution_topology_plan_hash",
                bindings["execution_topology_plan_hash"],
            ),
            (
                "solver_coordinate_scaling_hash",
                bindings["solver_coordinate_scaling_hash"],
            ),
            ("case_id", bindings["case_id"]),
        ):
            if state_bindings[name] != expected:
                _fail(
                    "fiber_frame_kinematic_chain_state_binding_mismatch",
                    f"/committed_states/{index}/bindings/{name}",
                    "State does not share the chain binding.",
                )
        if state["layout"]["node_ids"] != bindings["node_ids"]:
            _fail(
                "fiber_frame_kinematic_chain_state_binding_mismatch",
                f"/committed_states/{index}/layout/node_ids",
                "State node order does not share the chain binding.",
            )
        state_rows.append(state)
    if (
        state_rows[0]["bindings"]["checkpoint_state_hash"]
        != bindings["root_checkpoint_state_hash"]
        or state_rows[-1]["bindings"]["checkpoint_state_hash"]
        != bindings["terminal_checkpoint_state_hash"]
        or state_rows[0]["state_hash"] != bindings["root_kinematic_state_hash"]
        or state_rows[-1]["state_hash"] != bindings["terminal_kinematic_state_hash"]
    ):
        _fail(
            "fiber_frame_kinematic_chain_terminal_binding_mismatch",
            "/bindings",
            "Root or terminal manifest bindings are inconsistent.",
        )
    for index, value in enumerate(transitions, start=1):
        transition = _manifest_object(value, f"/transitions/{index - 1}")
        _validate_transition_manifest_semantics(
            transition,
            f"/transitions/{index - 1}",
        )
        accepted = state_rows[index - 1]
        committed = state_rows[index]
        transition_bindings = transition["bindings"]
        lifecycle = transition["lifecycle"]
        expected = {
            "problem_contract_hash": bindings["problem_contract_hash"],
            "model_ir_content_hash": bindings["model_ir_content_hash"],
            "execution_topology_plan_hash": bindings["execution_topology_plan_hash"],
            "case_id": bindings["case_id"],
            "parent_checkpoint_state_hash": accepted["bindings"][
                "checkpoint_state_hash"
            ],
            "checkpoint_state_hash": committed["bindings"]["checkpoint_state_hash"],
        }
        if any(transition_bindings[name] != expected[name] for name in expected):
            _fail(
                "fiber_frame_kinematic_chain_lifecycle_link_mismatch",
                f"/transitions/{index - 1}/bindings",
                "Transition bindings do not connect adjacent states.",
            )
        if (
            transition["coordinates"]["epoch"] != index
            or transition["coordinates"]["step_index"] != index
            or transition["coordinates"]["load_factor"]
            != committed["coordinates"]["load_factor"]
            or lifecycle["accepted_state_hash"] != accepted["state_hash"]
            or lifecycle["trial_state_hash"]
            != committed["coordinates"]["parent_state_hash"]
            or lifecycle["committed_state_hash"] != committed["state_hash"]
        ):
            _fail(
                "fiber_frame_kinematic_chain_lifecycle_link_mismatch",
                f"/transitions/{index - 1}",
                "Transition lifecycle does not connect adjacent states.",
            )
    _validate_claim_boundary(
        manifest["claim_boundary"],
        FIBER_FRAME_NONLINEAR_KINEMATIC_CLAIM_BOUNDARY,
        "/claim_boundary",
    )
    if manifest["extensions"] != {}:
        _fail(
            "fiber_frame_kinematic_chain_extensions_invalid",
            "/extensions",
            "Kinematic-state-chain v1 requires empty extensions.",
        )


def _validate_state_array_map(state: FiberFrameNonlinearKinematicState) -> None:
    arrays = state._arrays
    if not isinstance(arrays, MappingProxyType):
        _fail(
            "fiber_frame_kinematic_state_array_map_invalid",
            "/arrays",
            "State array map must be immutable.",
        )
    if type(state.descriptors) is not tuple or any(
        type(row) is not FiberFrameKinematicArrayDescriptor for row in state.descriptors
    ):
        _fail(
            "fiber_frame_kinematic_state_descriptor_type_invalid",
            "/array_descriptors",
            "Unexpected state descriptor type.",
        )
    names = tuple(row.name for row in state.descriptors)
    if names != _STATE_ARRAY_NAMES or tuple(arrays) != _STATE_ARRAY_NAMES:
        _fail(
            "fiber_frame_kinematic_state_array_order_invalid",
            "/arrays",
            "State arrays and descriptors must use the fixed order.",
        )
    expected_shapes = {
        "checkpoint_displacement_physical_3dof": (state.solver_dof_count,),
        "solver_generalized_coordinates_m": (state.solver_dof_count,),
        "canonical_displacement_si": (state.physical_dof_count,),
    }
    for descriptor in state.descriptors:
        array = arrays[descriptor.name]
        _validate_contract_array(
            array,
            expected_shapes[descriptor.name],
            f"/arrays/{descriptor.name}",
        )
        if descriptor != _array_descriptor(descriptor.name, array, state.node_ids):
            _fail(
                "fiber_frame_kinematic_state_descriptor_mismatch",
                f"/array_descriptors/{descriptor.name}",
                "Descriptor does not match retained array bytes.",
            )


def _array_descriptor(
    name: str,
    array: np.ndarray,
    node_ids: tuple[str, ...],
) -> FiberFrameKinematicArrayDescriptor:
    order_hash = _coordinate_order_hash(name, node_ids)
    metadata = {
        "name": name,
        "dtype": array.dtype.str,
        "shape": list(array.shape),
        "layout": "C",
        "byte_length": int(array.nbytes),
        "coordinate_order_hash": order_hash,
    }
    return FiberFrameKinematicArrayDescriptor(
        name=name,
        dtype=array.dtype.str,
        shape=tuple(int(value) for value in array.shape),
        layout="C",
        byte_length=int(array.nbytes),
        coordinate_order_hash=order_hash,
        data_hash=array_data_hash(array),
        content_hash=array_content_hash(metadata, array),
    )


def _coordinate_order_hash(name: str, node_ids: tuple[str, ...]) -> str:
    components = (
        _CANONICAL_COMPONENTS
        if name == "canonical_displacement_si"
        else _SOLVER_COMPONENTS
    )
    return canonical_hash(
        {
            "array_name": name,
            "node_ids": list(node_ids),
            "node_major_components": list(components),
        }
    )


def _validate_descriptor_manifest(
    payload: Any,
    *,
    name: str,
    shape: list[int],
    node_ids: tuple[str, ...],
    path: str,
) -> None:
    descriptor = _manifest_object(payload, path)
    _exact_keys(
        descriptor,
        {
            "name",
            "dtype",
            "shape",
            "layout",
            "byte_length",
            "coordinate_order_hash",
            "data_hash",
            "content_hash",
        },
        path,
    )
    if (
        descriptor["name"] != name
        or descriptor["dtype"] != "<f8"
        or descriptor["shape"] != shape
        or descriptor["layout"] != "C"
        or type(descriptor["byte_length"]) is not int
        or descriptor["byte_length"] != math.prod(shape) * 8
        or descriptor["coordinate_order_hash"] != _coordinate_order_hash(name, node_ids)
    ):
        _fail(
            "fiber_frame_kinematic_state_descriptor_invalid",
            path,
            "State descriptor layout, shape, or coordinate order is invalid.",
        )
    for key in ("coordinate_order_hash", "data_hash", "content_hash"):
        _require_hash(descriptor[key], f"{path}/{key}")


def _descriptor_by_name(
    descriptors: tuple[FiberFrameKinematicArrayDescriptor, ...],
    name: str,
) -> FiberFrameKinematicArrayDescriptor:
    for descriptor in descriptors:
        if descriptor.name == name:
            return descriptor
    _fail(
        "fiber_frame_kinematic_state_descriptor_missing",
        f"/array_descriptors/{name}",
        "Required state descriptor is missing.",
    )


def _validate_contract_array(value: Any, shape: tuple[int, ...], path: str) -> None:
    if (
        not isinstance(value, np.ndarray)
        or value.dtype.str != "<f8"
        or value.shape != shape
        or not value.flags.c_contiguous
        or not has_immutable_bytes_backing(value)
    ):
        _fail(
            "fiber_frame_kinematic_state_array_contract_invalid",
            path,
            "Expected immutable C-order canonical <f8 array and exact shape.",
        )
    if not np.all(np.isfinite(value)):
        _fail(
            "fiber_frame_kinematic_state_array_nonfinite",
            path,
            "State array values must be finite.",
        )


def _float_vector(value: Any, count: int, path: str) -> np.ndarray:
    try:
        inspected = np.asarray(value, dtype=object)
    except (TypeError, ValueError, OverflowError) as exc:
        raise FiberFrameNonlinearKinematicStateError(
            "fiber_frame_kinematic_state_array_invalid",
            path,
            "State array input cannot be inspected.",
        ) from exc
    if any(isinstance(item, (bool, np.bool_)) for item in inspected.reshape(-1)):
        _fail(
            "fiber_frame_kinematic_state_array_invalid",
            path,
            "Boolean values are not kinematic coordinates.",
        )
    try:
        result = immutable_array(value, dtype="<f8")
    except CanonicalContractError as exc:
        raise FiberFrameNonlinearKinematicStateError(
            "fiber_frame_kinematic_state_array_invalid",
            path,
            str(exc),
        ) from exc
    if result.shape != (count,):
        _fail(
            "fiber_frame_kinematic_state_array_shape_invalid",
            path,
            f"Expected shape {(count,)}.",
        )
    return result


def _state_id(
    plan: FiberFrameNonlinearExecutionTopologyPlan,
    checkpoint: StatefulFiberFrame2DCheckpoint,
    role: str,
) -> str:
    return (
        "ffkin."
        f"{plan.plan_hash.removeprefix('sha256:')[:16]}."
        f"{role}.e{checkpoint.epoch}"
    )


def _active_physical_dofs(node_count: int) -> tuple[int, ...]:
    return tuple(
        6 * node + component for node in range(node_count) for component in (0, 1, 5)
    )


def _validate_profiles(
    *,
    authority_profile: Any,
    carrier_profile: Any,
    state_ir_usage_profile: Any,
    lifecycle_profile: Any | None = None,
) -> None:
    if authority_profile != FIBER_FRAME_NONLINEAR_KINEMATIC_AUTHORITY_PROFILE:
        _fail(
            "fiber_frame_kinematic_authority_profile_invalid",
            "/authority_profile",
            "Kinematic transport cannot acquire result authority.",
        )
    if carrier_profile != FIBER_FRAME_NONLINEAR_KINEMATIC_CARRIER_PROFILE:
        _fail(
            "fiber_frame_kinematic_carrier_profile_invalid",
            "/carrier_profile",
            "Unsupported nonlinear kinematic carrier profile.",
        )
    if state_ir_usage_profile != FIBER_FRAME_STATE_IR_USAGE_PROFILE:
        _fail(
            "fiber_frame_kinematic_state_ir_usage_invalid",
            "/state_ir_usage_profile",
            "StateIR v1 cannot be promoted to the complete nonlinear state.",
        )
    if (
        lifecycle_profile is not None
        and lifecycle_profile != FIBER_FRAME_NONLINEAR_KINEMATIC_LIFECYCLE_PROFILE
    ):
        _fail(
            "fiber_frame_kinematic_lifecycle_profile_invalid",
            "/lifecycle_profile",
            "Unsupported nonlinear kinematic lifecycle profile.",
        )


def _validate_claim_boundary(
    value: Any,
    expected_claims: Mapping[str, bool],
    path: str,
) -> None:
    payload = _manifest_object(value, path)
    expected = dict(expected_claims)
    _exact_keys(payload, set(expected), path)
    if (
        any(type(payload[name]) is not bool for name in expected)
        or dict(payload) != expected
    ):
        _fail(
            "fiber_frame_kinematic_claim_boundary_invalid",
            path,
            "Kinematic claim boundary cannot be widened or changed.",
        )


def _manifest_object(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail(
            "fiber_frame_kinematic_manifest_object_invalid",
            path,
            "Expected a manifest object.",
        )
    if any(type(key) is not str for key in value):
        _fail(
            "fiber_frame_kinematic_manifest_object_invalid",
            path,
            "Manifest object keys must be strings.",
        )
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str], path: str) -> None:
    if set(value) != expected:
        _fail(
            "fiber_frame_kinematic_manifest_keys_invalid",
            path,
            "Manifest object keys differ from the v1 contract.",
        )


def _manifest_stable_id_list(value: Any, path: str) -> list[str]:
    if not isinstance(value, list) or not value:
        _fail(
            "fiber_frame_kinematic_stable_id_list_invalid",
            path,
            "Expected a non-empty stable-ID list.",
        )
    for index, item in enumerate(value):
        _stable_id(item, f"{path}/{index}")
    return value


def _stable_id_tuple(value: Any, path: str) -> tuple[str, ...]:
    if type(value) is not tuple or not value:
        _fail(
            "fiber_frame_kinematic_stable_id_tuple_invalid",
            path,
            "Expected a non-empty stable-ID tuple.",
        )
    for index, item in enumerate(value):
        _stable_id(item, f"{path}/{index}")
    return value


def _stable_id(value: Any, path: str) -> str:
    if type(value) is not str or _STABLE_ID_PATTERN.fullmatch(value) is None:
        _fail(
            "fiber_frame_kinematic_stable_id_invalid",
            path,
            "Expected a stable identifier.",
        )
    return value


def _nonempty_string(value: Any, path: str) -> str:
    if type(value) is not str or not value.strip() or value != value.strip():
        _fail(
            "fiber_frame_kinematic_string_invalid",
            path,
            "Expected a normalized non-empty string.",
        )
    return value


def _require_hash(value: Any, path: str) -> str:
    if type(value) is not str or _HASH_PATTERN.fullmatch(value) is None:
        _fail(
            "fiber_frame_kinematic_hash_invalid",
            path,
            "Expected a lowercase sha256:<hex> hash.",
        )
    return value


def _index(value: Any, path: str) -> int:
    if type(value) is not int or value < 0 or value > _MAX_INDEX:
        _fail(
            "fiber_frame_kinematic_index_invalid",
            path,
            "Expected a non-negative 32-bit integer.",
        )
    return value


def _positive_index(value: Any, path: str) -> int:
    result = _index(value, path)
    if result < 1:
        _fail(
            "fiber_frame_kinematic_index_invalid",
            path,
            "Expected a positive 32-bit integer.",
        )
    return result


def _finite_float(value: Any, path: str) -> float:
    if isinstance(value, (bool, np.bool_)) or type(value) not in (int, float):
        _fail(
            "fiber_frame_kinematic_number_invalid",
            path,
            "Expected a finite real number.",
        )
    result = float(value)
    if not math.isfinite(result):
        _fail(
            "fiber_frame_kinematic_number_invalid",
            path,
            "Expected a finite real number.",
        )
    return 0.0 if result == 0.0 else result


def _positive_float(value: Any, path: str) -> float:
    result = _finite_float(value, path)
    if result <= 0.0:
        _fail(
            "fiber_frame_kinematic_number_invalid",
            path,
            "Expected a positive finite real number.",
        )
    return result


def _fail(code: str, path: str, message: str) -> None:
    raise FiberFrameNonlinearKinematicStateError(code, path, message)


__all__ = [
    "FIBER_FRAME_NONLINEAR_KINEMATIC_AUTHORITY_PROFILE",
    "FIBER_FRAME_NONLINEAR_KINEMATIC_CARRIER_PROFILE",
    "FIBER_FRAME_NONLINEAR_KINEMATIC_CLAIM_BOUNDARY",
    "FIBER_FRAME_NONLINEAR_KINEMATIC_LIFECYCLE_PROFILE",
    "FIBER_FRAME_NONLINEAR_KINEMATIC_STATE_CLAIM_BOUNDARY",
    "FIBER_FRAME_NONLINEAR_KINEMATIC_STATE_CHAIN_SCHEMA_VERSION",
    "FIBER_FRAME_NONLINEAR_KINEMATIC_STATE_SCHEMA_VERSION",
    "FIBER_FRAME_NONLINEAR_KINEMATIC_TRANSITION_CLAIM_BOUNDARY",
    "FIBER_FRAME_NONLINEAR_KINEMATIC_TRANSITION_SCHEMA_VERSION",
    "FIBER_FRAME_STATE_IR_USAGE_PROFILE",
    "FiberFrameKinematicArrayDescriptor",
    "FiberFrameNonlinearKinematicState",
    "FiberFrameNonlinearKinematicStateChain",
    "FiberFrameNonlinearKinematicStateError",
    "FiberFrameNonlinearKinematicTransitionReceipt",
    "create_fiber_frame_nonlinear_kinematic_state_chain",
    "validate_fiber_frame_nonlinear_kinematic_state_array_bytes",
    "validate_fiber_frame_nonlinear_kinematic_state_chain",
    "validate_fiber_frame_nonlinear_kinematic_state_chain_manifest",
    "validate_fiber_frame_nonlinear_kinematic_state_chain_shape",
    "validate_fiber_frame_nonlinear_kinematic_state_manifest",
    "validate_fiber_frame_nonlinear_kinematic_state_shape",
    "validate_fiber_frame_nonlinear_kinematic_transition_receipt",
]
