"""Join exact fiber-frame kinematic and material-state histories.

PR-J3 retains one committed nonlinear kinematic state per checkpoint. PR-I/J4's
material projection chain retains one committed ``MaterialStateBundle`` per the
same checkpoint and binds each bundle to a caller-supplied solver-state hash.

This module proves that both histories describe the same checkpoint ancestry:
for every epoch, the material bundle's ``solver_state_hash`` must equal the
corresponding J3 committed-state hash. The outer envelope also binds J1 topology,
J2 physical equation scaling, ModelIR identity, checkpoint ancestry, and the
terminal kinematic/material states.

The join is non-authoritative. It does not decide convergence, replay a
constitutive transition, recover reactions/member forces, or grant numerical,
engineering, design, release, or commercial authority.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
import json
import math
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
from structural_analysis.assembly.stateful_fiber_frame2d_execution_topology import (
    FiberFrameNonlinearExecutionTopologyPlan,
    validate_fiber_frame_execution_topology_against_problem,
)
from structural_analysis.assembly.stateful_fiber_frame2d_kinematic_state_chain import (
    FiberFrameNonlinearKinematicState,
    FiberFrameNonlinearKinematicStateChain,
    validate_fiber_frame_nonlinear_kinematic_state_chain,
)
from structural_analysis.assembly.stateful_fiber_frame2d_material_state_projection_chain import (
    FiberFrameMaterialStateProjectionChain,
    create_fiber_frame_material_state_projection_chain,
    validate_fiber_frame_material_state_projection_chain,
)
from structural_analysis.assembly.stateful_fiber_frame2d_physical_equation_scaling import (
    FiberFramePhysicalEquationScalingBinding,
    validate_fiber_frame_physical_equation_scaling_against_problem,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash


FIBER_FRAME_NONLINEAR_STATE_BINDING_ROW_SCHEMA_VERSION = (
    "stateful-fiber-frame2d-nonlinear-state-binding-row.v1"
)
FIBER_FRAME_NONLINEAR_STATE_BINDING_SCHEMA_VERSION = (
    "stateful-fiber-frame2d-nonlinear-state-binding.v1"
)
FIBER_FRAME_NONLINEAR_STATE_BINDING_AUTHORITY_PROFILE = (
    "non_authoritative_kinematic_material_state_join.v1"
)
FIBER_FRAME_NONLINEAR_STATE_BINDING_PROFILE = (
    "checkpoint_epoch_kinematic_material_bundle_hash_join.v1"
)
FIBER_FRAME_NONLINEAR_STATE_BINDING_CLAIM_BOUNDARY = MappingProxyType(
    {
        "complete_checkpoint_chain_bound": True,
        "j1_execution_topology_bound": True,
        "j2_physical_equation_scaling_bound": True,
        "j3_kinematic_state_chain_bound": True,
        "material_state_projection_chain_bound": True,
        "one_material_bundle_per_committed_kinematic_state": True,
        "material_bundle_solver_state_hash_matches_kinematic_state": True,
        "terminal_kinematic_and_material_states_bound": True,
        "constitutive_transition_replayed": False,
        "residual_or_increment_convergence_bound": False,
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
_MAX_INDEX = 2**31 - 1


class FiberFrameNonlinearStateBindingError(ValueError):
    """Stable fail-closed error for J4 nonlinear state-history joins."""

    def __init__(self, code: str, path: str, message: str) -> None:
        self.code = code
        self.path = path
        self.message = message
        super().__init__(f"{code}@{path}: {message}")


@dataclass(frozen=True)
class FiberFrameNonlinearStateBindingRow:
    schema_version: str
    row_hash: str
    authority_profile: str
    binding_profile: str
    epoch: int
    step_index: int
    load_factor: float
    checkpoint_state_hash: str
    parent_checkpoint_state_hash: str | None
    kinematic_state_hash: str
    material_projection_receipt_hash: str
    material_state_bundle_hash: str
    material_bundle_solver_state_hash: str
    material_bundle_parent_hash: str | None
    material_bundle_epoch: int
    integration_point_order_hash: str
    source_identity_hash: str

    def to_manifest(self) -> dict[str, Any]:
        validate_fiber_frame_nonlinear_state_binding_row(self)
        return _row_payload(self, include_hash=True)


@dataclass(frozen=True)
class FiberFrameNonlinearStateBinding:
    schema_version: str
    binding_hash: str
    authority_profile: str
    binding_profile: str
    checkpoint_chain_hash: str
    kinematic_state_chain_hash: str
    material_projection_chain_hash: str
    physical_equation_scaling_binding_hash: str
    engine_equation_scaling_hash: str
    problem_contract_hash: str
    model_ir_content_hash: str
    execution_topology_plan_id: str
    execution_topology_plan_hash: str
    solver_coordinate_scaling_hash: str
    state_count: int
    root_checkpoint_state_hash: str
    terminal_checkpoint_state_hash: str
    root_kinematic_state_hash: str
    terminal_kinematic_state_hash: str
    root_material_state_bundle_hash: str
    terminal_material_state_bundle_hash: str
    rows: tuple[FiberFrameNonlinearStateBindingRow, ...]
    extensions: Mapping[str, Any]

    def to_manifest(self) -> dict[str, Any]:
        validate_fiber_frame_nonlinear_state_binding_shape(self)
        return _binding_payload(self, include_hash=True)


def create_material_projection_chain_for_kinematic_states(
    problem: StatefulFiberFrame2DProblem,
    plan: FiberFrameNonlinearExecutionTopologyPlan,
    checkpoint_chain: StatefulFiberFrame2DCheckpointChain,
    kinematic_chain: FiberFrameNonlinearKinematicStateChain,
) -> FiberFrameMaterialStateProjectionChain:
    """Create the exact material chain whose solver hashes are J3 state hashes."""

    validate_fiber_frame_execution_topology_against_problem(problem, plan)
    validate_stateful_fiber_frame2d_checkpoint_chain(problem, checkpoint_chain)
    validate_fiber_frame_nonlinear_kinematic_state_chain(
        problem,
        plan,
        checkpoint_chain,
        kinematic_chain,
    )
    return create_fiber_frame_material_state_projection_chain(
        problem,
        checkpoint_chain,
        model_ir_content_hash=kinematic_chain.model_ir_content_hash,
        execution_plan_hash=kinematic_chain.execution_topology_plan_hash,
        solver_state_hashes=kinematic_chain.solver_state_hashes,
    )


def create_fiber_frame_nonlinear_state_binding(
    problem: StatefulFiberFrame2DProblem,
    plan: FiberFrameNonlinearExecutionTopologyPlan,
    physical_scaling: FiberFramePhysicalEquationScalingBinding,
    checkpoint_chain: StatefulFiberFrame2DCheckpointChain,
    kinematic_chain: FiberFrameNonlinearKinematicStateChain,
    material_chain: FiberFrameMaterialStateProjectionChain,
) -> FiberFrameNonlinearStateBinding:
    """Create a complete non-authoritative J1/J2/J3/material history join."""

    _validate_sources(
        problem,
        plan,
        physical_scaling,
        checkpoint_chain,
        kinematic_chain,
        material_chain,
    )
    rows = tuple(
        _build_row(kinematic_state, projection)
        for kinematic_state, projection in zip(
            kinematic_chain.committed_states,
            material_chain.projections,
            strict=True,
        )
    )
    provisional = FiberFrameNonlinearStateBinding(
        schema_version=FIBER_FRAME_NONLINEAR_STATE_BINDING_SCHEMA_VERSION,
        binding_hash=_HASH_ZERO,
        authority_profile=FIBER_FRAME_NONLINEAR_STATE_BINDING_AUTHORITY_PROFILE,
        binding_profile=FIBER_FRAME_NONLINEAR_STATE_BINDING_PROFILE,
        checkpoint_chain_hash=checkpoint_chain.chain_hash,
        kinematic_state_chain_hash=kinematic_chain.chain_hash,
        material_projection_chain_hash=material_chain.chain_hash,
        physical_equation_scaling_binding_hash=physical_scaling.binding_hash,
        engine_equation_scaling_hash=physical_scaling.engine_equation_scaling_hash,
        problem_contract_hash=problem.contract_hash,
        model_ir_content_hash=kinematic_chain.model_ir_content_hash,
        execution_topology_plan_id=kinematic_chain.execution_topology_plan_id,
        execution_topology_plan_hash=kinematic_chain.execution_topology_plan_hash,
        solver_coordinate_scaling_hash=kinematic_chain.solver_coordinate_scaling_hash,
        state_count=len(rows),
        root_checkpoint_state_hash=kinematic_chain.root_checkpoint_state_hash,
        terminal_checkpoint_state_hash=(kinematic_chain.terminal_checkpoint_state_hash),
        root_kinematic_state_hash=kinematic_chain.root_kinematic_state_hash,
        terminal_kinematic_state_hash=kinematic_chain.terminal_kinematic_state_hash,
        root_material_state_bundle_hash=material_chain.projections[
            0
        ].bundle.bundle_hash,
        terminal_material_state_bundle_hash=(
            material_chain.terminal_material_state_bundle_hash
        ),
        rows=rows,
        extensions=MappingProxyType({}),
    )
    binding = replace(
        provisional,
        binding_hash=canonical_hash(_binding_payload(provisional, include_hash=False)),
    )
    return validate_fiber_frame_nonlinear_state_binding(
        problem,
        plan,
        physical_scaling,
        checkpoint_chain,
        kinematic_chain,
        material_chain,
        binding,
    )


def validate_fiber_frame_nonlinear_state_binding_row(
    row: FiberFrameNonlinearStateBindingRow,
) -> FiberFrameNonlinearStateBindingRow:
    """Validate one self-contained epoch-wise kinematic/material join."""

    if type(row) is not FiberFrameNonlinearStateBindingRow:
        _fail(
            "fiber_frame_nonlinear_state_binding_row_type_invalid",
            "/",
            "Expected FiberFrameNonlinearStateBindingRow.",
        )
    if row.schema_version != FIBER_FRAME_NONLINEAR_STATE_BINDING_ROW_SCHEMA_VERSION:
        _fail(
            "fiber_frame_nonlinear_state_binding_row_schema_invalid",
            "/schema_version",
            "Unsupported nonlinear state-binding row schema.",
        )
    _validate_profiles(row.authority_profile, row.binding_profile)
    _require_hash(row.row_hash, "/row_hash")
    epoch = _index(row.epoch, "/coordinates/epoch")
    step = _index(row.step_index, "/coordinates/step_index")
    bundle_epoch = _index(
        row.material_bundle_epoch,
        "/material/material_bundle_epoch",
    )
    if step != epoch or bundle_epoch != epoch:
        _fail(
            "fiber_frame_nonlinear_state_binding_row_epoch_mismatch",
            "/coordinates",
            "Checkpoint, kinematic, and material epochs must match.",
        )
    _finite(row.load_factor, "/coordinates/load_factor")
    for path, value in (
        ("/checkpoint/checkpoint_state_hash", row.checkpoint_state_hash),
        ("/kinematic/kinematic_state_hash", row.kinematic_state_hash),
        (
            "/material/material_projection_receipt_hash",
            row.material_projection_receipt_hash,
        ),
        ("/material/material_state_bundle_hash", row.material_state_bundle_hash),
        (
            "/material/material_bundle_solver_state_hash",
            row.material_bundle_solver_state_hash,
        ),
        (
            "/material/integration_point_order_hash",
            row.integration_point_order_hash,
        ),
        ("/material/source_identity_hash", row.source_identity_hash),
    ):
        _require_hash(value, path)
    if row.parent_checkpoint_state_hash is not None:
        _require_hash(
            row.parent_checkpoint_state_hash,
            "/checkpoint/parent_checkpoint_state_hash",
        )
    if row.material_bundle_parent_hash is not None:
        _require_hash(
            row.material_bundle_parent_hash,
            "/material/material_bundle_parent_hash",
        )
    if epoch == 0:
        if (
            row.parent_checkpoint_state_hash is not None
            or row.material_bundle_parent_hash is not None
            or row.load_factor != 0.0
        ):
            _fail(
                "fiber_frame_nonlinear_state_binding_initial_lineage_invalid",
                "/",
                "Epoch-zero join must be unparented at zero load.",
            )
    elif (
        row.parent_checkpoint_state_hash is None
        or row.material_bundle_parent_hash is None
    ):
        _fail(
            "fiber_frame_nonlinear_state_binding_parent_missing",
            "/",
            "Positive-epoch join requires checkpoint and bundle ancestry.",
        )
    if row.material_bundle_solver_state_hash != row.kinematic_state_hash:
        _fail(
            "fiber_frame_nonlinear_state_binding_solver_hash_mismatch",
            "/material/material_bundle_solver_state_hash",
            "Material bundle solver-state hash must equal the J3 committed-state hash.",
        )
    expected_hash = canonical_hash(_row_payload(row, include_hash=False))
    if row.row_hash != expected_hash:
        _fail(
            "fiber_frame_nonlinear_state_binding_row_hash_mismatch",
            "/row_hash",
            "State-binding row hash does not match canonical content.",
        )
    return row


def validate_fiber_frame_nonlinear_state_binding_shape(
    binding: FiberFrameNonlinearStateBinding,
) -> FiberFrameNonlinearStateBinding:
    """Validate self-contained envelope metadata, rows, and canonical hash."""

    if type(binding) is not FiberFrameNonlinearStateBinding:
        _fail(
            "fiber_frame_nonlinear_state_binding_type_invalid",
            "/",
            "Expected FiberFrameNonlinearStateBinding.",
        )
    if binding.schema_version != FIBER_FRAME_NONLINEAR_STATE_BINDING_SCHEMA_VERSION:
        _fail(
            "fiber_frame_nonlinear_state_binding_schema_invalid",
            "/schema_version",
            "Unsupported nonlinear state-binding schema.",
        )
    _validate_profiles(binding.authority_profile, binding.binding_profile)
    for path, value in (
        ("/binding_hash", binding.binding_hash),
        ("/bindings/checkpoint_chain_hash", binding.checkpoint_chain_hash),
        (
            "/bindings/kinematic_state_chain_hash",
            binding.kinematic_state_chain_hash,
        ),
        (
            "/bindings/material_projection_chain_hash",
            binding.material_projection_chain_hash,
        ),
        (
            "/bindings/physical_equation_scaling_binding_hash",
            binding.physical_equation_scaling_binding_hash,
        ),
        (
            "/bindings/engine_equation_scaling_hash",
            binding.engine_equation_scaling_hash,
        ),
        ("/bindings/problem_contract_hash", binding.problem_contract_hash),
        ("/bindings/model_ir_content_hash", binding.model_ir_content_hash),
        (
            "/bindings/execution_topology_plan_hash",
            binding.execution_topology_plan_hash,
        ),
        (
            "/bindings/solver_coordinate_scaling_hash",
            binding.solver_coordinate_scaling_hash,
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
    count = _positive_index(binding.state_count, "/state_count")
    if type(binding.rows) is not tuple or len(binding.rows) != count:
        _fail(
            "fiber_frame_nonlinear_state_binding_row_set_invalid",
            "/rows",
            "Row tuple does not match the declared positive state count.",
        )
    for index, row in enumerate(binding.rows):
        validate_fiber_frame_nonlinear_state_binding_row(row)
        if row.epoch != index or row.step_index != index:
            _fail(
                "fiber_frame_nonlinear_state_binding_row_order_invalid",
                f"/rows/{index}",
                "Rows must be contiguous and ordered from epoch zero.",
            )
        expected_parent = (
            None if index == 0 else binding.rows[index - 1].checkpoint_state_hash
        )
        if row.parent_checkpoint_state_hash != expected_parent:
            _fail(
                "fiber_frame_nonlinear_state_binding_checkpoint_parent_invalid",
                f"/rows/{index}/checkpoint/parent_checkpoint_state_hash",
                "Row checkpoint ancestry is not contiguous.",
            )
    first = binding.rows[0]
    last = binding.rows[-1]
    if (
        first.checkpoint_state_hash != binding.root_checkpoint_state_hash
        or last.checkpoint_state_hash != binding.terminal_checkpoint_state_hash
        or first.kinematic_state_hash != binding.root_kinematic_state_hash
        or last.kinematic_state_hash != binding.terminal_kinematic_state_hash
        or first.material_state_bundle_hash != binding.root_material_state_bundle_hash
        or last.material_state_bundle_hash
        != binding.terminal_material_state_bundle_hash
    ):
        _fail(
            "fiber_frame_nonlinear_state_binding_terminal_mismatch",
            "/rows",
            "Root or terminal row bindings do not match the envelope.",
        )
    if not isinstance(binding.extensions, MappingProxyType) or binding.extensions:
        _fail(
            "fiber_frame_nonlinear_state_binding_extensions_invalid",
            "/extensions",
            "J4 binding v1 requires immutable empty extensions.",
        )
    expected_hash = canonical_hash(_binding_payload(binding, include_hash=False))
    if binding.binding_hash != expected_hash:
        _fail(
            "fiber_frame_nonlinear_state_binding_hash_mismatch",
            "/binding_hash",
            "State-binding hash does not match canonical content.",
        )
    return binding


def validate_fiber_frame_nonlinear_state_binding(
    problem: StatefulFiberFrame2DProblem,
    plan: FiberFrameNonlinearExecutionTopologyPlan,
    physical_scaling: FiberFramePhysicalEquationScalingBinding,
    checkpoint_chain: StatefulFiberFrame2DCheckpointChain,
    kinematic_chain: FiberFrameNonlinearKinematicStateChain,
    material_chain: FiberFrameMaterialStateProjectionChain,
    binding: FiberFrameNonlinearStateBinding,
) -> FiberFrameNonlinearStateBinding:
    """Replay J1/J2/J3/material sources and every epoch-wise join."""

    _validate_sources(
        problem,
        plan,
        physical_scaling,
        checkpoint_chain,
        kinematic_chain,
        material_chain,
    )
    validate_fiber_frame_nonlinear_state_binding_shape(binding)
    expected_bindings = {
        "checkpoint_chain_hash": checkpoint_chain.chain_hash,
        "kinematic_state_chain_hash": kinematic_chain.chain_hash,
        "material_projection_chain_hash": material_chain.chain_hash,
        "physical_equation_scaling_binding_hash": physical_scaling.binding_hash,
        "engine_equation_scaling_hash": physical_scaling.engine_equation_scaling_hash,
        "problem_contract_hash": problem.contract_hash,
        "model_ir_content_hash": kinematic_chain.model_ir_content_hash,
        "execution_topology_plan_id": plan.plan_id,
        "execution_topology_plan_hash": plan.plan_hash,
        "solver_coordinate_scaling_hash": plan.solver_coordinate_scaling_hash,
        "state_count": len(checkpoint_chain.checkpoints),
        "root_checkpoint_state_hash": checkpoint_chain.root_checkpoint.state_hash,
        "terminal_checkpoint_state_hash": checkpoint_chain.terminal_checkpoint.state_hash,
        "root_kinematic_state_hash": kinematic_chain.root_kinematic_state_hash,
        "terminal_kinematic_state_hash": kinematic_chain.terminal_kinematic_state_hash,
        "root_material_state_bundle_hash": (
            material_chain.projections[0].bundle.bundle_hash
        ),
        "terminal_material_state_bundle_hash": (
            material_chain.terminal_material_state_bundle_hash
        ),
    }
    for name, expected in expected_bindings.items():
        if getattr(binding, name) != expected:
            _fail(
                "fiber_frame_nonlinear_state_binding_source_mismatch",
                f"/bindings/{name}",
                "J4 envelope does not bind the supplied source contracts.",
            )
    expected_rows = tuple(
        _build_row(state, projection)
        for state, projection in zip(
            kinematic_chain.committed_states,
            material_chain.projections,
            strict=True,
        )
    )
    for index, (actual, expected) in enumerate(
        zip(binding.rows, expected_rows, strict=True)
    ):
        if actual.to_manifest() != expected.to_manifest():
            _fail(
                "fiber_frame_nonlinear_state_binding_row_replay_mismatch",
                f"/rows/{index}",
                "Epoch-wise kinematic/material join does not replay exactly.",
            )
    return binding


def validate_fiber_frame_nonlinear_state_binding_manifest(
    payload: Any,
) -> Mapping[str, Any]:
    """Validate descriptor-free imported J4 metadata and canonical hashes."""

    manifest = _manifest_object(payload, "/")
    expected_keys = {
        "schema_version",
        "binding_hash",
        "authority_profile",
        "binding_profile",
        "bindings",
        "state_count",
        "rows",
        "claim_boundary",
        "extensions",
    }
    if set(manifest) != expected_keys:
        _fail(
            "fiber_frame_nonlinear_state_binding_manifest_fields_invalid",
            "/",
            "J4 manifest has missing or unknown fields.",
        )
    if manifest["schema_version"] != FIBER_FRAME_NONLINEAR_STATE_BINDING_SCHEMA_VERSION:
        _fail(
            "fiber_frame_nonlinear_state_binding_schema_invalid",
            "/schema_version",
            "Unsupported J4 manifest schema.",
        )
    _validate_profiles(
        manifest["authority_profile"],
        manifest["binding_profile"],
    )
    if manifest["claim_boundary"] != dict(
        FIBER_FRAME_NONLINEAR_STATE_BINDING_CLAIM_BOUNDARY
    ):
        _fail(
            "fiber_frame_nonlinear_state_binding_claim_boundary_invalid",
            "/claim_boundary",
            "J4 claim boundary changed.",
        )
    if manifest["extensions"] != {}:
        _fail(
            "fiber_frame_nonlinear_state_binding_extensions_invalid",
            "/extensions",
            "J4 manifest requires empty extensions.",
        )
    rows = manifest["rows"]
    if not isinstance(rows, list) or len(rows) != manifest["state_count"]:
        _fail(
            "fiber_frame_nonlinear_state_binding_manifest_rows_invalid",
            "/rows",
            "Manifest rows do not match state_count.",
        )
    for index, row in enumerate(rows):
        _validate_row_manifest(row, f"/rows/{index}")
    claimed = _require_hash(manifest["binding_hash"], "/binding_hash")
    unsigned = dict(manifest)
    unsigned.pop("binding_hash")
    if claimed != canonical_hash(unsigned):
        _fail(
            "fiber_frame_nonlinear_state_binding_hash_mismatch",
            "/binding_hash",
            "J4 manifest hash is stale.",
        )
    return manifest


def _validate_sources(
    problem: StatefulFiberFrame2DProblem,
    plan: FiberFrameNonlinearExecutionTopologyPlan,
    physical_scaling: FiberFramePhysicalEquationScalingBinding,
    checkpoint_chain: StatefulFiberFrame2DCheckpointChain,
    kinematic_chain: FiberFrameNonlinearKinematicStateChain,
    material_chain: FiberFrameMaterialStateProjectionChain,
) -> None:
    validate_fiber_frame_execution_topology_against_problem(problem, plan)
    validate_fiber_frame_physical_equation_scaling_against_problem(
        problem,
        plan,
        physical_scaling,
    )
    validate_stateful_fiber_frame2d_checkpoint_chain(problem, checkpoint_chain)
    validate_fiber_frame_nonlinear_kinematic_state_chain(
        problem,
        plan,
        checkpoint_chain,
        kinematic_chain,
    )
    validate_fiber_frame_material_state_projection_chain(
        problem,
        checkpoint_chain,
        material_chain,
    )
    if (
        physical_scaling.topology_plan_hash
        != kinematic_chain.execution_topology_plan_hash
    ):
        _fail(
            "fiber_frame_nonlinear_state_binding_physical_scaling_mismatch",
            "/bindings/physical_equation_scaling_binding_hash",
            "J2 scaling and J3 kinematics must bind the same J1 plan.",
        )
    if (
        material_chain.model_ir_content_hash != kinematic_chain.model_ir_content_hash
        or material_chain.execution_plan_hash
        != kinematic_chain.execution_topology_plan_hash
    ):
        _fail(
            "fiber_frame_nonlinear_state_binding_model_plan_mismatch",
            "/bindings",
            "Material and kinematic histories must share ModelIR and J1 plan identity.",
        )
    if (
        material_chain.checkpoint_chain_hash != kinematic_chain.checkpoint_chain_hash
        or material_chain.projection_count != kinematic_chain.state_count
    ):
        _fail(
            "fiber_frame_nonlinear_state_binding_chain_count_mismatch",
            "/bindings",
            "Material and kinematic histories must cover the same checkpoint chain.",
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
        ):
            _fail(
                "fiber_frame_nonlinear_state_binding_checkpoint_mismatch",
                f"/rows/{index}/checkpoint_state_hash",
                "Kinematic and material states must bind the same checkpoint.",
            )
        if (
            state.epoch != index
            or receipt.checkpoint_epoch != index
            or bundle.epoch != index
        ):
            _fail(
                "fiber_frame_nonlinear_state_binding_epoch_mismatch",
                f"/rows/{index}",
                "Checkpoint, kinematic state, receipt, and bundle epochs must match.",
            )
        if receipt.checkpoint_step_index != state.step_index:
            _fail(
                "fiber_frame_nonlinear_state_binding_step_mismatch",
                f"/rows/{index}",
                "Kinematic and material checkpoint step indices must match.",
            )
        if receipt.checkpoint_load_factor != state.load_factor:
            _fail(
                "fiber_frame_nonlinear_state_binding_load_factor_mismatch",
                f"/rows/{index}",
                "Kinematic and material checkpoint load factors must match.",
            )
        if (
            receipt.solver_state_hash != state.state_hash
            or bundle.solver_state_hash != state.state_hash
        ):
            _fail(
                "fiber_frame_nonlinear_state_binding_solver_hash_mismatch",
                f"/rows/{index}/material_bundle_solver_state_hash",
                "Material projection must use the exact J3 committed-state hash.",
            )
        if bundle.role != "committed":
            _fail(
                "fiber_frame_nonlinear_state_binding_material_role_invalid",
                f"/rows/{index}/material_state_bundle",
                "J4 binds committed material bundles only.",
            )


def _build_row(
    state: FiberFrameNonlinearKinematicState,
    projection: Any,
) -> FiberFrameNonlinearStateBindingRow:
    receipt = projection.receipt
    bundle = projection.bundle
    provisional = FiberFrameNonlinearStateBindingRow(
        schema_version=FIBER_FRAME_NONLINEAR_STATE_BINDING_ROW_SCHEMA_VERSION,
        row_hash=_HASH_ZERO,
        authority_profile=FIBER_FRAME_NONLINEAR_STATE_BINDING_AUTHORITY_PROFILE,
        binding_profile=FIBER_FRAME_NONLINEAR_STATE_BINDING_PROFILE,
        epoch=state.epoch,
        step_index=state.step_index,
        load_factor=state.load_factor,
        checkpoint_state_hash=state.checkpoint_state_hash,
        parent_checkpoint_state_hash=state.parent_checkpoint_state_hash,
        kinematic_state_hash=state.state_hash,
        material_projection_receipt_hash=receipt.receipt_hash,
        material_state_bundle_hash=bundle.bundle_hash,
        material_bundle_solver_state_hash=bundle.solver_state_hash,
        material_bundle_parent_hash=bundle.parent_bundle_hash,
        material_bundle_epoch=bundle.epoch,
        integration_point_order_hash=receipt.integration_point_order_hash,
        source_identity_hash=receipt.source_identity_hash,
    )
    row = replace(
        provisional,
        row_hash=canonical_hash(_row_payload(provisional, include_hash=False)),
    )
    return validate_fiber_frame_nonlinear_state_binding_row(row)


def _row_payload(
    row: FiberFrameNonlinearStateBindingRow,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload = {
        "schema_version": row.schema_version,
        "authority_profile": row.authority_profile,
        "binding_profile": row.binding_profile,
        "coordinates": {
            "epoch": row.epoch,
            "step_index": row.step_index,
            "load_factor": row.load_factor,
        },
        "checkpoint": {
            "checkpoint_state_hash": row.checkpoint_state_hash,
            "parent_checkpoint_state_hash": row.parent_checkpoint_state_hash,
        },
        "kinematic": {"kinematic_state_hash": row.kinematic_state_hash},
        "material": {
            "material_projection_receipt_hash": (row.material_projection_receipt_hash),
            "material_state_bundle_hash": row.material_state_bundle_hash,
            "material_bundle_solver_state_hash": (
                row.material_bundle_solver_state_hash
            ),
            "material_bundle_parent_hash": row.material_bundle_parent_hash,
            "material_bundle_epoch": row.material_bundle_epoch,
            "integration_point_order_hash": row.integration_point_order_hash,
            "source_identity_hash": row.source_identity_hash,
        },
    }
    if include_hash:
        payload["row_hash"] = row.row_hash
    return payload


def _binding_payload(
    binding: FiberFrameNonlinearStateBinding,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload = {
        "schema_version": binding.schema_version,
        "authority_profile": binding.authority_profile,
        "binding_profile": binding.binding_profile,
        "bindings": {
            "checkpoint_chain_hash": binding.checkpoint_chain_hash,
            "kinematic_state_chain_hash": binding.kinematic_state_chain_hash,
            "material_projection_chain_hash": (binding.material_projection_chain_hash),
            "physical_equation_scaling_binding_hash": (
                binding.physical_equation_scaling_binding_hash
            ),
            "engine_equation_scaling_hash": (binding.engine_equation_scaling_hash),
            "problem_contract_hash": binding.problem_contract_hash,
            "model_ir_content_hash": binding.model_ir_content_hash,
            "execution_topology_plan_id": binding.execution_topology_plan_id,
            "execution_topology_plan_hash": binding.execution_topology_plan_hash,
            "solver_coordinate_scaling_hash": (binding.solver_coordinate_scaling_hash),
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
        "state_count": binding.state_count,
        "rows": [row.to_manifest() for row in binding.rows],
        "claim_boundary": dict(FIBER_FRAME_NONLINEAR_STATE_BINDING_CLAIM_BOUNDARY),
        "extensions": dict(binding.extensions),
    }
    if include_hash:
        payload["binding_hash"] = binding.binding_hash
    return payload


def _validate_row_manifest(payload: Any, path: str) -> None:
    row = _manifest_object(payload, path)
    expected_keys = {
        "schema_version",
        "row_hash",
        "authority_profile",
        "binding_profile",
        "coordinates",
        "checkpoint",
        "kinematic",
        "material",
    }
    if set(row) != expected_keys:
        _fail(
            "fiber_frame_nonlinear_state_binding_row_manifest_fields_invalid",
            path,
            "Row manifest has missing or unknown fields.",
        )
    if row["schema_version"] != FIBER_FRAME_NONLINEAR_STATE_BINDING_ROW_SCHEMA_VERSION:
        _fail(
            "fiber_frame_nonlinear_state_binding_row_schema_invalid",
            f"{path}/schema_version",
            "Unsupported row manifest schema.",
        )
    _validate_profiles(row["authority_profile"], row["binding_profile"])
    if (
        row["material"]["material_bundle_solver_state_hash"]
        != row["kinematic"]["kinematic_state_hash"]
    ):
        _fail(
            "fiber_frame_nonlinear_state_binding_solver_hash_mismatch",
            f"{path}/material/material_bundle_solver_state_hash",
            "Material solver hash must equal kinematic state hash.",
        )
    claimed = _require_hash(row["row_hash"], f"{path}/row_hash")
    unsigned = dict(row)
    unsigned.pop("row_hash")
    if claimed != canonical_hash(unsigned):
        _fail(
            "fiber_frame_nonlinear_state_binding_row_hash_mismatch",
            f"{path}/row_hash",
            "Row manifest hash is stale.",
        )


def _manifest_object(payload: Any, path: str) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        _fail(
            "fiber_frame_nonlinear_state_binding_manifest_type_invalid",
            path,
            "Manifest must be an object.",
        )
    try:
        return json.loads(json.dumps(dict(payload), allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise FiberFrameNonlinearStateBindingError(
            "fiber_frame_nonlinear_state_binding_manifest_json_invalid",
            path,
            "Manifest must be finite strict JSON.",
        ) from exc


def _validate_profiles(authority_profile: Any, binding_profile: Any) -> None:
    if authority_profile != FIBER_FRAME_NONLINEAR_STATE_BINDING_AUTHORITY_PROFILE:
        _fail(
            "fiber_frame_nonlinear_state_binding_authority_invalid",
            "/authority_profile",
            "J4 state join cannot acquire solver or result authority.",
        )
    if binding_profile != FIBER_FRAME_NONLINEAR_STATE_BINDING_PROFILE:
        _fail(
            "fiber_frame_nonlinear_state_binding_profile_invalid",
            "/binding_profile",
            "Unsupported J4 state-binding profile.",
        )


def _stable_id(value: Any, path: str) -> str:
    normalized = str(value).strip()
    if not normalized or not re.fullmatch(
        r"[A-Za-z][A-Za-z0-9_.:-]{0,127}", normalized
    ):
        _fail(
            "fiber_frame_nonlinear_state_binding_id_invalid",
            path,
            "Expected a stable identifier.",
        )
    return normalized


def _require_hash(value: Any, path: str) -> str:
    normalized = str(value).strip()
    if not _HASH_PATTERN.fullmatch(normalized):
        _fail(
            "fiber_frame_nonlinear_state_binding_hash_invalid",
            path,
            "Expected a lowercase sha256:<hex> hash.",
        )
    return normalized


def _index(value: Any, path: str) -> int:
    if type(value) is not int or value < 0 or value > _MAX_INDEX:
        _fail(
            "fiber_frame_nonlinear_state_binding_index_invalid",
            path,
            "Expected a non-negative 32-bit integer.",
        )
    return value


def _positive_index(value: Any, path: str) -> int:
    normalized = _index(value, path)
    if normalized < 1:
        _fail(
            "fiber_frame_nonlinear_state_binding_count_invalid",
            path,
            "Expected a positive count.",
        )
    return normalized


def _finite(value: Any, path: str) -> float:
    if isinstance(value, bool) or type(value) not in (int, float):
        _fail(
            "fiber_frame_nonlinear_state_binding_number_invalid",
            path,
            "Expected a finite number.",
        )
    normalized = float(value)
    if not math.isfinite(normalized):
        _fail(
            "fiber_frame_nonlinear_state_binding_number_invalid",
            path,
            "Expected a finite number.",
        )
    return normalized


def _fail(code: str, path: str, message: str) -> None:
    raise FiberFrameNonlinearStateBindingError(code, path, message)


__all__ = [
    "FIBER_FRAME_NONLINEAR_STATE_BINDING_AUTHORITY_PROFILE",
    "FIBER_FRAME_NONLINEAR_STATE_BINDING_CLAIM_BOUNDARY",
    "FIBER_FRAME_NONLINEAR_STATE_BINDING_PROFILE",
    "FIBER_FRAME_NONLINEAR_STATE_BINDING_ROW_SCHEMA_VERSION",
    "FIBER_FRAME_NONLINEAR_STATE_BINDING_SCHEMA_VERSION",
    "FiberFrameNonlinearStateBinding",
    "FiberFrameNonlinearStateBindingError",
    "FiberFrameNonlinearStateBindingRow",
    "create_fiber_frame_nonlinear_state_binding",
    "create_material_projection_chain_for_kinematic_states",
    "validate_fiber_frame_nonlinear_state_binding",
    "validate_fiber_frame_nonlinear_state_binding_manifest",
    "validate_fiber_frame_nonlinear_state_binding_row",
    "validate_fiber_frame_nonlinear_state_binding_shape",
]
