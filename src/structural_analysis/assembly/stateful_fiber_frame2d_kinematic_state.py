"""Typed nonlinear kinematic-state transport for the bounded fiber frame.

This additive contract keeps Engine v2 StateIR v1 unchanged.  Each committed
fiber-frame checkpoint is projected into three equivalent displacement views:

- physical solver order ``[UX, UY, RZ]``;
- generalized solver coordinates used by the current Newton implementation;
- canonical node-major six-DOF order ``[UX, UY, UZ, RX, RY, RZ]``.

The state and chain bind J1 topology, J2 physical scaling, exact checkpoint
ancestry, and immutable displacement bytes.  They do not bind constitutive
history and grant no convergence, numerical-result, engineering, design,
release, or commercial authority.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
import json
import math
import re
from types import MappingProxyType
from typing import Any, Literal

import numpy as np

from structural_analysis.assembly.stateful_fiber_frame2d import (
    StatefulFiberFrame2DProblem,
    validate_stateful_fiber_frame2d_checkpoint,
)
from structural_analysis.assembly.stateful_fiber_frame2d_checkpoint_chain_io import (
    StatefulFiberFrame2DCheckpointChain,
    validate_stateful_fiber_frame2d_checkpoint_chain,
)
from structural_analysis.assembly.stateful_fiber_frame2d_execution_topology import (
    FiberFrameNonlinearExecutionTopologyPlan,
    physical_3dof_to_canonical_6dof,
    physical_3dof_to_solver_generalized,
    validate_fiber_frame_execution_topology_against_problem,
)
from structural_analysis.assembly.stateful_fiber_frame2d_physical_scaling import (
    FiberFramePhysicalEquationScalingReceipt,
    validate_fiber_frame_physical_equation_scaling_against_problem,
)
from structural_analysis.assembly.stateful_fiber_frame2d_state import (
    StatefulFiberFrame2DCheckpoint,
)
from structural_analysis.engine_v2.contracts._canonical import (
    array_content_hash,
    array_data_hash,
    canonical_hash,
    has_immutable_bytes_backing,
    immutable_array,
)


FIBER_FRAME_NONLINEAR_KINEMATIC_STATE_SCHEMA_VERSION = (
    "stateful-fiber-frame2d-nonlinear-kinematic-state.v1"
)
FIBER_FRAME_NONLINEAR_KINEMATIC_STATE_CHAIN_SCHEMA_VERSION = (
    "stateful-fiber-frame2d-nonlinear-kinematic-state-chain.v1"
)
FIBER_FRAME_NONLINEAR_KINEMATIC_AUTHORITY_PROFILE = (
    "non_authoritative_nonlinear_kinematic_state_transport.v1"
)
FIBER_FRAME_NONLINEAR_KINEMATIC_BINDING_PROFILE = (
    "checkpoint_physical_generalized_canonical6dof.v1"
)
FIBER_FRAME_NONLINEAR_KINEMATIC_CLAIM_BOUNDARY = MappingProxyType(
    {
        "checkpoint_ancestry_bound": True,
        "j1_topology_bound": True,
        "j2_physical_scaling_bound": True,
        "physical_solver_displacement_bound": True,
        "generalized_solver_coordinates_bound": True,
        "canonical_six_dof_displacement_bound": True,
        "inactive_dofs_exact_zero": True,
        "material_state_history_bound": False,
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
_STATE_ARRAY_SPECS = (
    ("physical_displacement_solver_order", "<f8"),
    ("generalized_coordinates_solver_order", "<f8"),
    ("canonical_displacement_6dof", "<f8"),
)
_STATE_ARRAY_NAMES = tuple(name for name, _dtype in _STATE_ARRAY_SPECS)


class FiberFrameNonlinearKinematicStateError(ValueError):
    """Stable fail-closed kinematic-state transport error."""

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
    data_hash: str
    content_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "dtype": self.dtype,
            "shape": list(self.shape),
            "layout": self.layout,
            "byte_length": self.byte_length,
            "data_hash": self.data_hash,
            "content_hash": self.content_hash,
        }


@dataclass(frozen=True)
class FiberFrameNonlinearKinematicState:
    schema_version: str
    state_hash: str
    authority_profile: str
    binding_profile: str
    topology_plan_hash: str
    physical_scaling_hash: str
    problem_contract_hash: str
    checkpoint_state_hash: str
    parent_checkpoint_state_hash: str | None
    epoch: int
    step_index: int
    load_factor: float
    source_commitment_hash: str
    solver_dof_count: int
    physical_dof_count: int
    descriptors: tuple[FiberFrameKinematicArrayDescriptor, ...]
    _arrays: Mapping[str, np.ndarray] = field(repr=False, compare=False)
    extensions: Mapping[str, Any] = field(repr=False, compare=False)

    def array(self, name: str) -> np.ndarray:
        try:
            return self._arrays[name]
        except KeyError as exc:
            raise KeyError(f"Unknown nonlinear kinematic-state array: {name}") from exc

    def to_manifest(self) -> dict[str, Any]:
        validate_fiber_frame_nonlinear_kinematic_state(self)
        return _state_payload(self, include_hash=True)


@dataclass(frozen=True)
class FiberFrameNonlinearKinematicStateChain:
    schema_version: str
    chain_hash: str
    authority_profile: str
    binding_profile: str
    checkpoint_chain_hash: str
    topology_plan_hash: str
    physical_scaling_hash: str
    problem_contract_hash: str
    state_count: int
    root_checkpoint_state_hash: str
    terminal_checkpoint_state_hash: str
    root_kinematic_state_hash: str
    terminal_kinematic_state_hash: str
    states: tuple[FiberFrameNonlinearKinematicState, ...]
    extensions: Mapping[str, Any] = field(repr=False, compare=False)

    def to_manifest(self) -> dict[str, Any]:
        validate_fiber_frame_nonlinear_kinematic_state_chain_shape(self)
        return _chain_payload(self, include_hash=True)


def create_fiber_frame_nonlinear_kinematic_state(
    problem: StatefulFiberFrame2DProblem,
    topology_plan: FiberFrameNonlinearExecutionTopologyPlan,
    physical_scaling: FiberFramePhysicalEquationScalingReceipt,
    checkpoint: StatefulFiberFrame2DCheckpoint,
) -> FiberFrameNonlinearKinematicState:
    """Project one committed checkpoint into typed nonlinear kinematics."""

    validate_fiber_frame_execution_topology_against_problem(problem, topology_plan)
    validate_fiber_frame_physical_equation_scaling_against_problem(
        problem,
        topology_plan,
        physical_scaling,
    )
    validate_stateful_fiber_frame2d_checkpoint(problem, checkpoint)
    physical = immutable_array(checkpoint.global_displacements, dtype="<f8")
    if physical.shape != (topology_plan.solver_dof_count,):
        _fail(
            "fiber_frame_kinematic_checkpoint_displacement_shape_invalid",
            "/checkpoint/global_displacements",
            "Checkpoint displacement count does not match the J1 solver space.",
        )
    generalized = physical_3dof_to_solver_generalized(topology_plan, physical)
    canonical = physical_3dof_to_canonical_6dof(topology_plan, physical)
    arrays = MappingProxyType(
        {
            "physical_displacement_solver_order": physical,
            "generalized_coordinates_solver_order": generalized,
            "canonical_displacement_6dof": canonical,
        }
    )
    descriptors = tuple(_descriptor(name, arrays[name]) for name in _STATE_ARRAY_NAMES)
    source_commitment_hash = canonical_hash(
        {
            "checkpoint_state_hash": checkpoint.state_hash,
            "checkpoint_parent_state_hash": checkpoint.parent_state_hash,
            "checkpoint_epoch": checkpoint.epoch,
            "checkpoint_step_index": checkpoint.step_index,
            "checkpoint_load_factor": checkpoint.load_factor,
            "topology_plan_hash": topology_plan.plan_hash,
            "physical_scaling_hash": physical_scaling.scaling_hash,
            "array_content_hashes": {row.name: row.content_hash for row in descriptors},
        }
    )
    provisional = FiberFrameNonlinearKinematicState(
        schema_version=FIBER_FRAME_NONLINEAR_KINEMATIC_STATE_SCHEMA_VERSION,
        state_hash=_HASH_ZERO,
        authority_profile=FIBER_FRAME_NONLINEAR_KINEMATIC_AUTHORITY_PROFILE,
        binding_profile=FIBER_FRAME_NONLINEAR_KINEMATIC_BINDING_PROFILE,
        topology_plan_hash=topology_plan.plan_hash,
        physical_scaling_hash=physical_scaling.scaling_hash,
        problem_contract_hash=problem.contract_hash,
        checkpoint_state_hash=checkpoint.state_hash,
        parent_checkpoint_state_hash=checkpoint.parent_state_hash,
        epoch=checkpoint.epoch,
        step_index=checkpoint.step_index,
        load_factor=checkpoint.load_factor,
        source_commitment_hash=source_commitment_hash,
        solver_dof_count=topology_plan.solver_dof_count,
        physical_dof_count=topology_plan.physical_dof_count,
        descriptors=descriptors,
        _arrays=arrays,
        extensions=MappingProxyType({}),
    )
    state = replace(
        provisional,
        state_hash=canonical_hash(_state_payload(provisional, include_hash=False)),
    )
    validate_fiber_frame_nonlinear_kinematic_state(state)
    validate_fiber_frame_nonlinear_kinematic_state_against_checkpoint(
        problem,
        topology_plan,
        physical_scaling,
        checkpoint,
        state,
    )
    return state


def create_fiber_frame_nonlinear_kinematic_state_chain(
    problem: StatefulFiberFrame2DProblem,
    topology_plan: FiberFrameNonlinearExecutionTopologyPlan,
    physical_scaling: FiberFramePhysicalEquationScalingReceipt,
    checkpoint_chain: StatefulFiberFrame2DCheckpointChain,
) -> FiberFrameNonlinearKinematicStateChain:
    """Project one complete checkpoint ancestry into a kinematic-state chain."""

    validate_stateful_fiber_frame2d_checkpoint_chain(problem, checkpoint_chain)
    validate_fiber_frame_execution_topology_against_problem(problem, topology_plan)
    validate_fiber_frame_physical_equation_scaling_against_problem(
        problem,
        topology_plan,
        physical_scaling,
    )
    states = tuple(
        create_fiber_frame_nonlinear_kinematic_state(
            problem,
            topology_plan,
            physical_scaling,
            checkpoint,
        )
        for checkpoint in checkpoint_chain.checkpoints
    )
    provisional = FiberFrameNonlinearKinematicStateChain(
        schema_version=FIBER_FRAME_NONLINEAR_KINEMATIC_STATE_CHAIN_SCHEMA_VERSION,
        chain_hash=_HASH_ZERO,
        authority_profile=FIBER_FRAME_NONLINEAR_KINEMATIC_AUTHORITY_PROFILE,
        binding_profile=FIBER_FRAME_NONLINEAR_KINEMATIC_BINDING_PROFILE,
        checkpoint_chain_hash=checkpoint_chain.chain_hash,
        topology_plan_hash=topology_plan.plan_hash,
        physical_scaling_hash=physical_scaling.scaling_hash,
        problem_contract_hash=problem.contract_hash,
        state_count=len(states),
        root_checkpoint_state_hash=checkpoint_chain.root_checkpoint.state_hash,
        terminal_checkpoint_state_hash=(
            checkpoint_chain.terminal_checkpoint.state_hash
        ),
        root_kinematic_state_hash=states[0].state_hash,
        terminal_kinematic_state_hash=states[-1].state_hash,
        states=states,
        extensions=MappingProxyType({}),
    )
    chain = replace(
        provisional,
        chain_hash=canonical_hash(_chain_payload(provisional, include_hash=False)),
    )
    return validate_fiber_frame_nonlinear_kinematic_state_chain(
        problem,
        topology_plan,
        physical_scaling,
        checkpoint_chain,
        chain,
    )


def validate_fiber_frame_nonlinear_kinematic_state(
    state: FiberFrameNonlinearKinematicState,
) -> FiberFrameNonlinearKinematicState:
    """Validate self-contained state metadata, arrays, and canonical hash."""

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
    if state.authority_profile != FIBER_FRAME_NONLINEAR_KINEMATIC_AUTHORITY_PROFILE:
        _fail(
            "fiber_frame_kinematic_state_authority_invalid",
            "/authority_profile",
            "Kinematic-state transport cannot acquire result authority.",
        )
    if state.binding_profile != FIBER_FRAME_NONLINEAR_KINEMATIC_BINDING_PROFILE:
        _fail(
            "fiber_frame_kinematic_state_binding_profile_invalid",
            "/binding_profile",
            "Unsupported nonlinear kinematic binding profile.",
        )
    for path, value in (
        ("/state_hash", state.state_hash),
        ("/topology_plan_hash", state.topology_plan_hash),
        ("/physical_scaling_hash", state.physical_scaling_hash),
        ("/problem_contract_hash", state.problem_contract_hash),
        ("/checkpoint_state_hash", state.checkpoint_state_hash),
        ("/source_commitment_hash", state.source_commitment_hash),
    ):
        _require_hash(value, path)
    epoch = _index(state.epoch, "/epoch")
    step = _index(state.step_index, "/step_index")
    if epoch != step:
        _fail(
            "fiber_frame_kinematic_state_step_epoch_mismatch",
            "/step_index",
            "Step index must equal epoch for this bounded checkpoint path.",
        )
    if epoch == 0:
        if state.parent_checkpoint_state_hash is not None:
            _fail(
                "fiber_frame_kinematic_state_initial_parent_invalid",
                "/parent_checkpoint_state_hash",
                "Epoch-zero kinematic state must be unparented.",
            )
    else:
        _require_hash(
            state.parent_checkpoint_state_hash,
            "/parent_checkpoint_state_hash",
        )
    _finite(state.load_factor, "/load_factor")
    solver_count = _index(state.solver_dof_count, "/solver_dof_count")
    physical_count = _index(state.physical_dof_count, "/physical_dof_count")
    if solver_count < 3 or solver_count % 3:
        _fail(
            "fiber_frame_kinematic_state_solver_dof_count_invalid",
            "/solver_dof_count",
            "Solver DOF count must be a positive multiple of three.",
        )
    if physical_count != 2 * solver_count or physical_count % 6:
        _fail(
            "fiber_frame_kinematic_state_physical_dof_count_invalid",
            "/physical_dof_count",
            "Physical DOF count must be the six-DOF expansion of solver space.",
        )
    _validate_array_map(state)
    canonical = state.array("canonical_displacement_6dof")
    inactive = np.asarray(
        [
            6 * node + component
            for node in range(physical_count // 6)
            for component in (2, 3, 4)
        ],
        dtype=np.int64,
    )
    if not np.array_equal(canonical[inactive], np.zeros(inactive.size)):
        _fail(
            "fiber_frame_kinematic_state_inactive_displacement_nonzero",
            "/arrays/canonical_displacement_6dof",
            "Inactive UZ/RX/RY displacements must remain exact zero.",
        )
    if not isinstance(state.extensions, MappingProxyType) or state.extensions:
        _fail(
            "fiber_frame_kinematic_state_extensions_invalid",
            "/extensions",
            "Kinematic-state v1 requires immutable empty extensions.",
        )
    expected_hash = canonical_hash(_state_payload(state, include_hash=False))
    if state.state_hash != expected_hash:
        _fail(
            "fiber_frame_kinematic_state_hash_mismatch",
            "/state_hash",
            "Kinematic-state hash does not match canonical content.",
        )
    return state


def validate_fiber_frame_nonlinear_kinematic_state_against_checkpoint(
    problem: StatefulFiberFrame2DProblem,
    topology_plan: FiberFrameNonlinearExecutionTopologyPlan,
    physical_scaling: FiberFramePhysicalEquationScalingReceipt,
    checkpoint: StatefulFiberFrame2DCheckpoint,
    state: FiberFrameNonlinearKinematicState,
) -> FiberFrameNonlinearKinematicState:
    """Replay one state from its exact source checkpoint and contracts."""

    validate_fiber_frame_execution_topology_against_problem(problem, topology_plan)
    validate_fiber_frame_physical_equation_scaling_against_problem(
        problem,
        topology_plan,
        physical_scaling,
    )
    validate_stateful_fiber_frame2d_checkpoint(problem, checkpoint)
    validate_fiber_frame_nonlinear_kinematic_state(state)
    expected = _build_state_without_source_revalidation(
        problem,
        topology_plan,
        physical_scaling,
        checkpoint,
    )
    if state.to_manifest() != expected.to_manifest():
        _fail(
            "fiber_frame_kinematic_state_source_replay_mismatch",
            "/",
            "Kinematic state does not replay from the supplied checkpoint.",
        )
    for name in _STATE_ARRAY_NAMES:
        if not np.array_equal(state.array(name), expected.array(name)):
            _fail(
                "fiber_frame_kinematic_state_source_array_mismatch",
                f"/arrays/{name}",
                "Kinematic-state bytes do not replay from the checkpoint.",
            )
    return state


def validate_fiber_frame_nonlinear_kinematic_state_chain_shape(
    chain: FiberFrameNonlinearKinematicStateChain,
) -> FiberFrameNonlinearKinematicStateChain:
    """Validate self-contained chain metadata and canonical hash."""

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
    if chain.authority_profile != FIBER_FRAME_NONLINEAR_KINEMATIC_AUTHORITY_PROFILE:
        _fail(
            "fiber_frame_kinematic_chain_authority_invalid",
            "/authority_profile",
            "Kinematic-state chain cannot acquire result authority.",
        )
    if chain.binding_profile != FIBER_FRAME_NONLINEAR_KINEMATIC_BINDING_PROFILE:
        _fail(
            "fiber_frame_kinematic_chain_binding_profile_invalid",
            "/binding_profile",
            "Unsupported nonlinear kinematic binding profile.",
        )
    for path, value in (
        ("/chain_hash", chain.chain_hash),
        ("/checkpoint_chain_hash", chain.checkpoint_chain_hash),
        ("/topology_plan_hash", chain.topology_plan_hash),
        ("/physical_scaling_hash", chain.physical_scaling_hash),
        ("/problem_contract_hash", chain.problem_contract_hash),
        ("/root_checkpoint_state_hash", chain.root_checkpoint_state_hash),
        (
            "/terminal_checkpoint_state_hash",
            chain.terminal_checkpoint_state_hash,
        ),
        ("/root_kinematic_state_hash", chain.root_kinematic_state_hash),
        (
            "/terminal_kinematic_state_hash",
            chain.terminal_kinematic_state_hash,
        ),
    ):
        _require_hash(value, path)
    count = _index(chain.state_count, "/state_count")
    if count < 1 or type(chain.states) is not tuple or len(chain.states) != count:
        _fail(
            "fiber_frame_kinematic_chain_state_set_invalid",
            "/states",
            "State tuple does not match the declared positive count.",
        )
    for index, state in enumerate(chain.states):
        validate_fiber_frame_nonlinear_kinematic_state(state)
        if state.epoch != index or state.step_index != index:
            _fail(
                "fiber_frame_kinematic_chain_epoch_invalid",
                f"/states/{index}",
                "Kinematic-state epochs must be contiguous from zero.",
            )
        expected_parent = (
            None if index == 0 else chain.states[index - 1].checkpoint_state_hash
        )
        if state.parent_checkpoint_state_hash != expected_parent:
            _fail(
                "fiber_frame_kinematic_chain_parent_invalid",
                f"/states/{index}/parent_checkpoint_state_hash",
                "Kinematic-state checkpoint ancestry is not contiguous.",
            )
        if (
            state.topology_plan_hash != chain.topology_plan_hash
            or state.physical_scaling_hash != chain.physical_scaling_hash
            or state.problem_contract_hash != chain.problem_contract_hash
        ):
            _fail(
                "fiber_frame_kinematic_chain_binding_mismatch",
                f"/states/{index}",
                "Every state must share one problem, topology, and scaling.",
            )
    if (
        chain.states[0].checkpoint_state_hash != chain.root_checkpoint_state_hash
        or chain.states[-1].checkpoint_state_hash
        != chain.terminal_checkpoint_state_hash
        or chain.states[0].state_hash != chain.root_kinematic_state_hash
        or chain.states[-1].state_hash != chain.terminal_kinematic_state_hash
    ):
        _fail(
            "fiber_frame_kinematic_chain_terminal_binding_mismatch",
            "/states",
            "Root or terminal state bindings do not match the chain envelope.",
        )
    if not isinstance(chain.extensions, MappingProxyType) or chain.extensions:
        _fail(
            "fiber_frame_kinematic_chain_extensions_invalid",
            "/extensions",
            "Kinematic-state chain v1 requires immutable empty extensions.",
        )
    expected_hash = canonical_hash(_chain_payload(chain, include_hash=False))
    if chain.chain_hash != expected_hash:
        _fail(
            "fiber_frame_kinematic_chain_hash_mismatch",
            "/chain_hash",
            "Kinematic-state-chain hash does not match canonical content.",
        )
    return chain


def validate_fiber_frame_nonlinear_kinematic_state_chain(
    problem: StatefulFiberFrame2DProblem,
    topology_plan: FiberFrameNonlinearExecutionTopologyPlan,
    physical_scaling: FiberFramePhysicalEquationScalingReceipt,
    checkpoint_chain: StatefulFiberFrame2DCheckpointChain,
    chain: FiberFrameNonlinearKinematicStateChain,
) -> FiberFrameNonlinearKinematicStateChain:
    """Replay every state against the supplied checkpoint ancestry."""

    validate_stateful_fiber_frame2d_checkpoint_chain(problem, checkpoint_chain)
    validate_fiber_frame_execution_topology_against_problem(problem, topology_plan)
    validate_fiber_frame_physical_equation_scaling_against_problem(
        problem,
        topology_plan,
        physical_scaling,
    )
    validate_fiber_frame_nonlinear_kinematic_state_chain_shape(chain)
    if chain.checkpoint_chain_hash != checkpoint_chain.chain_hash:
        _fail(
            "fiber_frame_kinematic_chain_checkpoint_hash_mismatch",
            "/checkpoint_chain_hash",
            "Kinematic chain does not bind the supplied checkpoint chain.",
        )
    if len(chain.states) != len(checkpoint_chain.checkpoints):
        _fail(
            "fiber_frame_kinematic_chain_count_mismatch",
            "/state_count",
            "Kinematic-state count does not match checkpoint ancestry.",
        )
    for index, (checkpoint, state) in enumerate(
        zip(checkpoint_chain.checkpoints, chain.states, strict=True)
    ):
        try:
            validate_fiber_frame_nonlinear_kinematic_state_against_checkpoint(
                problem,
                topology_plan,
                physical_scaling,
                checkpoint,
                state,
            )
        except FiberFrameNonlinearKinematicStateError as exc:
            _fail(
                "fiber_frame_kinematic_chain_state_replay_failed",
                f"/states/{index}",
                str(exc),
            )
    return chain


def validate_fiber_frame_nonlinear_kinematic_array_bytes(
    state: FiberFrameNonlinearKinematicState,
    *,
    name: str,
    payload: bytes,
) -> np.ndarray:
    """Validate one external displacement array against its descriptor."""

    validate_fiber_frame_nonlinear_kinematic_state(state)
    if type(payload) is not bytes:
        _fail(
            "fiber_frame_kinematic_array_bytes_invalid",
            f"/arrays/{name}",
            "External displacement artifact must be immutable bytes.",
        )
    descriptor = _descriptor_by_name(state.descriptors, name)
    if len(payload) != descriptor.byte_length:
        _fail(
            "fiber_frame_kinematic_array_length_mismatch",
            f"/arrays/{name}",
            "External displacement artifact length does not match descriptor.",
        )
    array = np.frombuffer(payload, dtype=descriptor.dtype).reshape(descriptor.shape)
    immutable = immutable_array(array, dtype=descriptor.dtype)
    if array_data_hash(immutable) != descriptor.data_hash:
        _fail(
            "fiber_frame_kinematic_array_hash_mismatch",
            f"/arrays/{name}",
            "External displacement artifact hash does not match descriptor.",
        )
    return immutable


def validate_fiber_frame_nonlinear_kinematic_manifest(
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate strict descriptor-only state metadata and canonical hash."""

    normalized = _strict_json_object(payload, "/")
    expected_keys = {
        "schema_version",
        "state_hash",
        "authority_profile",
        "binding_profile",
        "bindings",
        "checkpoint",
        "dof_counts",
        "array_descriptors",
        "claim_boundary",
        "extensions",
    }
    if set(normalized) != expected_keys:
        _fail(
            "fiber_frame_kinematic_manifest_fields_invalid",
            "/",
            "Kinematic-state manifest has missing or unknown fields.",
        )
    if (
        normalized["schema_version"]
        != FIBER_FRAME_NONLINEAR_KINEMATIC_STATE_SCHEMA_VERSION
    ):
        _fail(
            "fiber_frame_kinematic_state_schema_invalid",
            "/schema_version",
            "Unsupported nonlinear kinematic-state schema.",
        )
    if (
        normalized["authority_profile"]
        != FIBER_FRAME_NONLINEAR_KINEMATIC_AUTHORITY_PROFILE
    ):
        _fail(
            "fiber_frame_kinematic_state_authority_invalid",
            "/authority_profile",
            "Kinematic-state manifest cannot acquire result authority.",
        )
    if normalized["claim_boundary"] != dict(
        FIBER_FRAME_NONLINEAR_KINEMATIC_CLAIM_BOUNDARY
    ):
        _fail(
            "fiber_frame_kinematic_manifest_claim_boundary_invalid",
            "/claim_boundary",
            "Kinematic-state claim boundary changed.",
        )
    if normalized["extensions"] != {}:
        _fail(
            "fiber_frame_kinematic_state_extensions_invalid",
            "/extensions",
            "Kinematic-state manifest requires empty extensions.",
        )
    descriptors = normalized["array_descriptors"]
    if not isinstance(descriptors, list) or [
        row.get("name") for row in descriptors if isinstance(row, Mapping)
    ] != list(_STATE_ARRAY_NAMES):
        _fail(
            "fiber_frame_kinematic_manifest_descriptor_set_invalid",
            "/array_descriptors",
            "Kinematic-state descriptor set or order is invalid.",
        )
    claimed_hash = _require_hash(normalized["state_hash"], "/state_hash")
    unsigned = dict(normalized)
    unsigned.pop("state_hash")
    if claimed_hash != canonical_hash(unsigned):
        _fail(
            "fiber_frame_kinematic_state_hash_mismatch",
            "/state_hash",
            "Kinematic-state manifest hash is stale.",
        )
    return normalized


def _build_state_without_source_revalidation(
    problem: StatefulFiberFrame2DProblem,
    topology_plan: FiberFrameNonlinearExecutionTopologyPlan,
    physical_scaling: FiberFramePhysicalEquationScalingReceipt,
    checkpoint: StatefulFiberFrame2DCheckpoint,
) -> FiberFrameNonlinearKinematicState:
    physical = immutable_array(checkpoint.global_displacements, dtype="<f8")
    generalized = physical_3dof_to_solver_generalized(topology_plan, physical)
    canonical = physical_3dof_to_canonical_6dof(topology_plan, physical)
    arrays = MappingProxyType(
        {
            "physical_displacement_solver_order": physical,
            "generalized_coordinates_solver_order": generalized,
            "canonical_displacement_6dof": canonical,
        }
    )
    descriptors = tuple(_descriptor(name, arrays[name]) for name in _STATE_ARRAY_NAMES)
    source_commitment_hash = canonical_hash(
        {
            "checkpoint_state_hash": checkpoint.state_hash,
            "checkpoint_parent_state_hash": checkpoint.parent_state_hash,
            "checkpoint_epoch": checkpoint.epoch,
            "checkpoint_step_index": checkpoint.step_index,
            "checkpoint_load_factor": checkpoint.load_factor,
            "topology_plan_hash": topology_plan.plan_hash,
            "physical_scaling_hash": physical_scaling.scaling_hash,
            "array_content_hashes": {row.name: row.content_hash for row in descriptors},
        }
    )
    provisional = FiberFrameNonlinearKinematicState(
        schema_version=FIBER_FRAME_NONLINEAR_KINEMATIC_STATE_SCHEMA_VERSION,
        state_hash=_HASH_ZERO,
        authority_profile=FIBER_FRAME_NONLINEAR_KINEMATIC_AUTHORITY_PROFILE,
        binding_profile=FIBER_FRAME_NONLINEAR_KINEMATIC_BINDING_PROFILE,
        topology_plan_hash=topology_plan.plan_hash,
        physical_scaling_hash=physical_scaling.scaling_hash,
        problem_contract_hash=problem.contract_hash,
        checkpoint_state_hash=checkpoint.state_hash,
        parent_checkpoint_state_hash=checkpoint.parent_state_hash,
        epoch=checkpoint.epoch,
        step_index=checkpoint.step_index,
        load_factor=checkpoint.load_factor,
        source_commitment_hash=source_commitment_hash,
        solver_dof_count=topology_plan.solver_dof_count,
        physical_dof_count=topology_plan.physical_dof_count,
        descriptors=descriptors,
        _arrays=arrays,
        extensions=MappingProxyType({}),
    )
    return replace(
        provisional,
        state_hash=canonical_hash(_state_payload(provisional, include_hash=False)),
    )


def _state_payload(
    state: FiberFrameNonlinearKinematicState,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload = {
        "schema_version": state.schema_version,
        "authority_profile": state.authority_profile,
        "binding_profile": state.binding_profile,
        "bindings": {
            "topology_plan_hash": state.topology_plan_hash,
            "physical_scaling_hash": state.physical_scaling_hash,
            "problem_contract_hash": state.problem_contract_hash,
            "checkpoint_state_hash": state.checkpoint_state_hash,
            "parent_checkpoint_state_hash": state.parent_checkpoint_state_hash,
            "source_commitment_hash": state.source_commitment_hash,
        },
        "checkpoint": {
            "epoch": state.epoch,
            "step_index": state.step_index,
            "load_factor": state.load_factor,
        },
        "dof_counts": {
            "solver": state.solver_dof_count,
            "physical": state.physical_dof_count,
        },
        "array_descriptors": [row.to_dict() for row in state.descriptors],
        "claim_boundary": dict(FIBER_FRAME_NONLINEAR_KINEMATIC_CLAIM_BOUNDARY),
        "extensions": dict(state.extensions),
    }
    if include_hash:
        payload["state_hash"] = state.state_hash
    return payload


def _chain_payload(
    chain: FiberFrameNonlinearKinematicStateChain,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload = {
        "schema_version": chain.schema_version,
        "authority_profile": chain.authority_profile,
        "binding_profile": chain.binding_profile,
        "bindings": {
            "checkpoint_chain_hash": chain.checkpoint_chain_hash,
            "topology_plan_hash": chain.topology_plan_hash,
            "physical_scaling_hash": chain.physical_scaling_hash,
            "problem_contract_hash": chain.problem_contract_hash,
            "root_checkpoint_state_hash": chain.root_checkpoint_state_hash,
            "terminal_checkpoint_state_hash": (chain.terminal_checkpoint_state_hash),
            "root_kinematic_state_hash": chain.root_kinematic_state_hash,
            "terminal_kinematic_state_hash": (chain.terminal_kinematic_state_hash),
        },
        "state_count": chain.state_count,
        "states": [state.to_manifest() for state in chain.states],
        "claim_boundary": dict(FIBER_FRAME_NONLINEAR_KINEMATIC_CLAIM_BOUNDARY),
        "extensions": dict(chain.extensions),
    }
    if include_hash:
        payload["chain_hash"] = chain.chain_hash
    return payload


def _validate_array_map(state: FiberFrameNonlinearKinematicState) -> None:
    if not isinstance(state._arrays, MappingProxyType) or tuple(state._arrays) != (
        _STATE_ARRAY_NAMES
    ):
        _fail(
            "fiber_frame_kinematic_state_array_set_invalid",
            "/arrays",
            "Array map must be immutable and use the exact ordered set.",
        )
    if (
        type(state.descriptors) is not tuple
        or tuple(row.name for row in state.descriptors) != _STATE_ARRAY_NAMES
    ):
        _fail(
            "fiber_frame_kinematic_state_descriptor_set_invalid",
            "/array_descriptors",
            "Descriptor tuple does not match the exact ordered array set.",
        )
    by_name = {row.name: row for row in state.descriptors}
    expected_shapes = {
        "physical_displacement_solver_order": (state.solver_dof_count,),
        "generalized_coordinates_solver_order": (state.solver_dof_count,),
        "canonical_displacement_6dof": (state.physical_dof_count,),
    }
    for name, dtype in _STATE_ARRAY_SPECS:
        array = state._arrays[name]
        if (
            not isinstance(array, np.ndarray)
            or array.dtype.str != dtype
            or array.shape != expected_shapes[name]
            or not array.flags.c_contiguous
            or not has_immutable_bytes_backing(array)
        ):
            _fail(
                "fiber_frame_kinematic_state_array_contract_invalid",
                f"/arrays/{name}",
                "Kinematic-state array contract is invalid.",
            )
        if by_name[name] != _descriptor(name, array):
            _fail(
                "fiber_frame_kinematic_state_descriptor_mismatch",
                f"/arrays/{name}",
                "Descriptor does not match retained displacement bytes.",
            )


def _descriptor(
    name: str,
    array: np.ndarray,
) -> FiberFrameKinematicArrayDescriptor:
    metadata = {
        "name": name,
        "dtype": array.dtype.str,
        "shape": list(array.shape),
        "layout": "C",
        "byte_length": int(array.nbytes),
    }
    return FiberFrameKinematicArrayDescriptor(
        name=name,
        dtype=array.dtype.str,
        shape=tuple(int(value) for value in array.shape),
        layout="C",
        byte_length=int(array.nbytes),
        data_hash=array_data_hash(array),
        content_hash=array_content_hash(metadata, array),
    )


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
        "Required displacement descriptor is missing.",
    )


def _strict_json_object(payload: Mapping[str, Any], path: str) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        _fail(
            "fiber_frame_kinematic_manifest_type_invalid",
            path,
            "Manifest must be an object.",
        )
    try:
        return json.loads(json.dumps(dict(payload), allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise FiberFrameNonlinearKinematicStateError(
            "fiber_frame_kinematic_manifest_json_invalid",
            path,
            "Manifest must be finite strict JSON.",
        ) from exc


def _require_hash(value: Any, path: str) -> str:
    normalized = str(value).strip()
    if not _HASH_PATTERN.fullmatch(normalized):
        _fail(
            "fiber_frame_kinematic_hash_invalid",
            path,
            "Expected a lowercase sha256:<hex> hash.",
        )
    return normalized


def _index(value: Any, path: str) -> int:
    if type(value) is not int or value < 0 or value > _MAX_INDEX:
        _fail(
            "fiber_frame_kinematic_index_invalid",
            path,
            "Expected a non-negative 32-bit integer.",
        )
    return value


def _finite(value: Any, path: str) -> float:
    if isinstance(value, bool) or type(value) not in (int, float):
        _fail(
            "fiber_frame_kinematic_number_invalid",
            path,
            "Expected a finite number.",
        )
    normalized = float(value)
    if not math.isfinite(normalized):
        _fail(
            "fiber_frame_kinematic_number_invalid",
            path,
            "Expected a finite number.",
        )
    return normalized


def _fail(code: str, path: str, message: str) -> None:
    raise FiberFrameNonlinearKinematicStateError(code, path, message)


__all__ = [
    "FIBER_FRAME_NONLINEAR_KINEMATIC_AUTHORITY_PROFILE",
    "FIBER_FRAME_NONLINEAR_KINEMATIC_BINDING_PROFILE",
    "FIBER_FRAME_NONLINEAR_KINEMATIC_CLAIM_BOUNDARY",
    "FIBER_FRAME_NONLINEAR_KINEMATIC_STATE_CHAIN_SCHEMA_VERSION",
    "FIBER_FRAME_NONLINEAR_KINEMATIC_STATE_SCHEMA_VERSION",
    "FiberFrameKinematicArrayDescriptor",
    "FiberFrameNonlinearKinematicState",
    "FiberFrameNonlinearKinematicStateChain",
    "FiberFrameNonlinearKinematicStateError",
    "create_fiber_frame_nonlinear_kinematic_state",
    "create_fiber_frame_nonlinear_kinematic_state_chain",
    "validate_fiber_frame_nonlinear_kinematic_array_bytes",
    "validate_fiber_frame_nonlinear_kinematic_manifest",
    "validate_fiber_frame_nonlinear_kinematic_state",
    "validate_fiber_frame_nonlinear_kinematic_state_against_checkpoint",
    "validate_fiber_frame_nonlinear_kinematic_state_chain",
    "validate_fiber_frame_nonlinear_kinematic_state_chain_shape",
]
