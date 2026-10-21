"""Direct free-CSR Newton trials for the existing fixed-chord fiber frame.

This execution-only consumer preserves member integration and accumulation order.
Terminal engineering receipts continue to use the existing dense assembler.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any, NamedTuple

import numpy as np
from scipy.sparse import csr_matrix

from .stateful_fiber_frame2d import (
    StatefulFiberFrame2DProblem,
    _finite,
    validate_stateful_fiber_frame2d_checkpoint,
)
from .stateful_fiber_frame2d_state import StatefulFiberFrame2DCheckpoint


class _TopologyPlan(NamedTuple):
    indptr: tuple[int, ...]
    indices: tuple[int, ...]
    data_rows: tuple[int, ...]
    # Per member: unique CSR positions and their corresponding 6x6 local slots.
    members: tuple[tuple[tuple[int, ...], tuple[int, ...], tuple[int, ...]], ...]


@lru_cache(maxsize=64)
def _topology_plan(
    global_count: int,
    free_dofs: tuple[int, ...],
    member_dofs: tuple[tuple[int, ...], ...],
) -> _TopologyPlan:
    """Cache only immutable integer topology, never a problem or physical value."""
    if len(set(free_dofs)) != len(free_dofs) or any(
        type(dof) is not int or not 0 <= dof < global_count for dof in free_dofs
    ):
        raise ValueError("direct sparse free DOF topology is invalid")
    free_index = {dof: index for index, dof in enumerate(free_dofs)}
    columns = [set() for _ in free_dofs]
    local_pairs = []
    for dofs in member_dofs:
        if (
            len(dofs) != 6
            or len(set(dofs)) != 6
            or any(type(dof) is not int or not 0 <= dof < global_count for dof in dofs)
        ):
            raise ValueError("direct sparse member DOF topology is invalid")
        active = [
            (local, free_index[dof])
            for local, dof in enumerate(dofs)
            if dof in free_index
        ]
        pairs = []
        for local_row, row in active:
            for local_column, column in active:
                columns[row].add(column)
                pairs.append((row, column, local_row, local_column))
        local_pairs.append(pairs)
    indptr, indices, data_rows = [0], [], []
    positions = {}
    for row, row_columns in enumerate(columns):
        for column in sorted(row_columns):
            positions[row, column] = len(indices)
            indices.append(column)
            data_rows.append(row)
        indptr.append(len(indices))
    groups = []
    for pairs in local_pairs:
        groups.append(
            (
                tuple(positions[row, column] for row, column, _, _ in pairs),
                tuple(local_row for _, _, local_row, _ in pairs),
                tuple(local_column for _, _, _, local_column in pairs),
            )
        )
    return _TopologyPlan(tuple(indptr), tuple(indices), tuple(data_rows), tuple(groups))


def _immutable_array(value: np.ndarray) -> np.ndarray:
    array = np.ascontiguousarray(value)
    return np.frombuffer(array.tobytes(), dtype=array.dtype).reshape(array.shape)


@dataclass(frozen=True)
class DirectSparseFiberFrameTrial:
    parent_checkpoint_hash: str
    target_load_factor: float
    free_global_dofs: tuple[int, ...]
    generalized_coordinates_m: np.ndarray
    global_displacements: np.ndarray
    residual_kn: np.ndarray
    jacobian_kn_per_m: csr_matrix
    internal_loads_global: np.ndarray
    external_loads_global: np.ndarray
    reactions_global: np.ndarray
    pattern_nnz: int
    # Bytes in the returned numeric buffers only, not peak RSS, temporaries,
    # Python objects/cache entries or cumulative allocation traffic.
    allocated_bytes: int


def assemble_stateful_fiber_frame2d_direct_sparse(
    problem: StatefulFiberFrame2DProblem,
    accepted_checkpoint: StatefulFiberFrame2DCheckpoint,
    *,
    target_load_factor: float,
    trial_free_coordinates_m: Any,
) -> DirectSparseFiberFrameTrial:
    """Assemble one unchanged material trial without a global dense tangent."""
    validate_stateful_fiber_frame2d_checkpoint(problem, accepted_checkpoint)
    load_factor = _finite(target_load_factor, name="target_load_factor")
    free_dofs = problem.free_global_dofs
    try:
        free = np.asarray(trial_free_coordinates_m, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError("trial_free_coordinates_m has invalid values") from exc
    if free.shape != (len(free_dofs),) or not np.all(np.isfinite(free)):
        raise ValueError("trial_free_coordinates_m has invalid shape or values")
    scale = problem.physical_coordinate_scale
    generalized = np.zeros(problem.global_dof_count, dtype=np.float64)
    generalized[list(free_dofs)] = free
    global_displacements = scale * generalized
    internal = np.zeros(problem.global_dof_count, dtype=np.float64)
    member_dofs = tuple(
        problem.member_global_dofs(member) for member in problem.members
    )
    plan = _topology_plan(problem.global_dof_count, free_dofs, member_dofs)
    data = np.zeros(len(plan.indices), dtype=np.float64)
    for member, parent, dofs, group in zip(
        problem.members,
        accepted_checkpoint.element_states,
        member_dofs,
        plan.members,
        strict=True,
    ):
        transformation = problem.member_transformation(member)
        local_displacements = transformation @ global_displacements[list(dofs)]
        response = member.element.integrate(local_displacements, parent)
        if response.parent_state_hash != parent.state_hash:
            raise ValueError(
                "element response parent_state_hash does not match checkpoint parent"
            )
        internal_global = transformation.T @ response.internal_force_local
        tangent_global = (
            transformation.T @ response.consistent_tangent_local @ transformation
        )
        internal[list(dofs)] += internal_global
        positions, local_rows, local_columns = group
        if positions:
            # Positions are unique within this member; member order matches dense +=.
            data[list(positions)] += tangent_global[
                list(local_rows), list(local_columns)
            ]
    external = load_factor * problem.reference_external_load_vector()
    physical_residual = internal - external
    free_scale = scale[list(free_dofs)]
    residual = free_scale * physical_residual[list(free_dofs)]
    # Preserve dense's (row_scale * accumulated_tangent) * column_scale order.
    data = (free_scale[list(plan.data_rows)] * data) * free_scale[list(plan.indices)]
    jacobian = csr_matrix(
        (
            data,
            np.asarray(plan.indices, dtype=np.int64),
            np.asarray(plan.indptr, dtype=np.int64),
        ),
        shape=(len(free_dofs), len(free_dofs)),
        copy=False,
    )
    # Structural zeros and every tiny nonzero are retained; no dropping/elimination.
    jacobian.data = _immutable_array(jacobian.data)
    jacobian.indices = _immutable_array(jacobian.indices)
    jacobian.indptr = _immutable_array(jacobian.indptr)
    reactions = np.zeros(problem.global_dof_count, dtype=np.float64)
    reactions[list(problem.fixed_global_dofs)] = physical_residual[
        list(problem.fixed_global_dofs)
    ]
    vectors = tuple(
        _immutable_array(array)
        for array in (
            generalized,
            global_displacements,
            residual,
            internal,
            external,
            reactions,
        )
    )
    allocated_bytes = sum(array.nbytes for array in vectors) + sum(
        array.nbytes for array in (jacobian.data, jacobian.indices, jacobian.indptr)
    )
    return DirectSparseFiberFrameTrial(
        accepted_checkpoint.state_hash,
        load_factor,
        free_dofs,
        *vectors[:3],
        jacobian,
        *vectors[3:],
        len(plan.indices),
        allocated_bytes,
    )


__all__ = [
    "DirectSparseFiberFrameTrial",
    "assemble_stateful_fiber_frame2d_direct_sparse",
]
