"""Native COO/CSR tangent assembly for the corotational fiber-frame path."""

from __future__ import annotations

from dataclasses import dataclass, replace
import math
from types import MappingProxyType
from typing import Any, Mapping

import numpy as np
from scipy.sparse import coo_matrix, csr_matrix

from structural_analysis.assembly.stateful_corotational_fiber_frame2d import (
    StatefulCorotationalFiberFrame2DProblem,
    assemble_stateful_corotational_fiber_frame2d,
    validate_stateful_corotational_fiber_frame2d_checkpoint,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_state import (
    StatefulCorotationalFiberFrame2DCheckpoint,
)
from structural_analysis.engine_v2.contracts._canonical import (
    array_data_hash,
    canonical_hash,
    immutable_array,
)


COROTATIONAL_FIBER_FRAME_SPARSE_ASSEMBLY_SCHEMA_VERSION = (
    "stateful-corotational-fiber-frame2d-native-coo-csr.v1"
)
COROTATIONAL_FIBER_FRAME_SPARSE_STORAGE_PROFILE = (
    "element_triplet_coalesce_sorted_csr_fp64.v1"
)
COROTATIONAL_FIBER_FRAME_DENSE_SPARSE_PARITY_SCHEMA_VERSION = (
    "stateful-corotational-fiber-frame2d-dense-sparse-parity.v1"
)
COROTATIONAL_FIBER_FRAME_DENSE_SPARSE_PARITY_TOLERANCE = 1.0e-13


@dataclass(frozen=True)
class CorotationalFiberFrameSparseAssembly:
    """Immutable receipt and arrays for one native sparse trial assembly."""

    schema_version: str
    assembly_hash: str
    storage_profile: str
    problem_contract_hash: str
    parent_checkpoint_hash: str
    target_load_factor: float
    free_equation_count: int
    raw_coo_entry_count: int
    csr_nnz: int
    csr_pattern_hash: str
    csr_numeric_hash: str
    generalized_coordinates_m: np.ndarray
    global_displacements: np.ndarray
    residual_kn: np.ndarray
    internal_loads_global: np.ndarray
    external_loads_global: np.ndarray
    reactions_global: np.ndarray
    coo_row_indices: np.ndarray
    coo_column_indices: np.ndarray
    coo_values_kn_per_m: np.ndarray
    csr_row_ptr: np.ndarray
    csr_column_indices: np.ndarray
    csr_values_kn_per_m: np.ndarray
    trial_element_state_hashes: tuple[str, ...]

    @property
    def jacobian_csr(self) -> csr_matrix:
        """Return an independently owned CSR matrix reconstructed from frozen arrays."""

        return csr_matrix(
            (
                np.array(self.csr_values_kn_per_m, copy=True),
                np.array(self.csr_column_indices, copy=True),
                np.array(self.csr_row_ptr, copy=True),
            ),
            shape=(self.free_equation_count, self.free_equation_count),
            dtype=np.float64,
        )

    def to_manifest(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "assembly_hash": self.assembly_hash,
            "storage_profile": self.storage_profile,
            "problem_contract_hash": self.problem_contract_hash,
            "parent_checkpoint_hash": self.parent_checkpoint_hash,
            "target_load_factor": self.target_load_factor,
            "free_equation_count": self.free_equation_count,
            "raw_coo_entry_count": self.raw_coo_entry_count,
            "csr_nnz": self.csr_nnz,
            "csr_pattern_hash": self.csr_pattern_hash,
            "csr_numeric_hash": self.csr_numeric_hash,
            "array_hashes": {
                "generalized_coordinates_m": array_data_hash(
                    self.generalized_coordinates_m
                ),
                "global_displacements": array_data_hash(self.global_displacements),
                "residual_kn": array_data_hash(self.residual_kn),
                "internal_loads_global": array_data_hash(self.internal_loads_global),
                "external_loads_global": array_data_hash(self.external_loads_global),
                "reactions_global": array_data_hash(self.reactions_global),
                "coo_row_indices": array_data_hash(self.coo_row_indices),
                "coo_column_indices": array_data_hash(self.coo_column_indices),
                "coo_values_kn_per_m": array_data_hash(self.coo_values_kn_per_m),
                "csr_row_ptr": array_data_hash(self.csr_row_ptr),
                "csr_column_indices": array_data_hash(self.csr_column_indices),
                "csr_values_kn_per_m": array_data_hash(self.csr_values_kn_per_m),
            },
            "trial_element_state_hashes": list(self.trial_element_state_hashes),
        }


@dataclass(frozen=True)
class CorotationalFiberFrameDenseSparseParityReceipt:
    """Fail-closed dense/native-sparse comparison for one identical trial."""

    schema_version: str
    receipt_hash: str
    problem_contract_hash: str
    parent_checkpoint_hash: str
    target_load_factor: float
    dense_assembly_hash: str
    sparse_assembly_hash: str
    csr_pattern_hash: str
    csr_numeric_hash: str
    csr_nnz: int
    metrics: Mapping[str, float]
    checks: Mapping[str, bool]
    authority: Mapping[str, str]

    def to_manifest(self) -> dict[str, Any]:
        payload = _parity_payload(self, include_hash=True)
        expected = canonical_hash(_parity_payload(self, include_hash=False))
        if self.receipt_hash != expected or not all(self.checks.values()):
            raise ValueError("dense/sparse parity receipt is stale or failed")
        return payload


def assemble_stateful_corotational_fiber_frame2d_sparse(
    problem: StatefulCorotationalFiberFrame2DProblem,
    accepted_checkpoint: StatefulCorotationalFiberFrame2DCheckpoint,
    *,
    target_load_factor: float,
    trial_free_coordinates_m: Any,
) -> CorotationalFiberFrameSparseAssembly:
    """Scatter member tangents directly to COO and canonical sorted CSR."""

    validate_stateful_corotational_fiber_frame2d_checkpoint(
        problem, accepted_checkpoint
    )
    load_factor = _finite(target_load_factor, "target_load_factor")
    free_dofs = problem.free_global_dofs
    try:
        free = np.asarray(trial_free_coordinates_m, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError("trial_free_coordinates_m has invalid values") from exc
    if free.shape != (len(free_dofs),) or not np.all(np.isfinite(free)):
        raise ValueError("trial_free_coordinates_m has invalid shape or values")

    scale = np.asarray(problem.physical_coordinate_scale, dtype=np.float64)
    generalized = np.zeros(problem.global_dof_count, dtype=np.float64)
    prescribed = problem.prescribed_displacement_vector(load_factor)
    generalized[list(problem.fixed_global_dofs)] = (
        prescribed[list(problem.fixed_global_dofs)]
        / scale[list(problem.fixed_global_dofs)]
    )
    generalized[list(free_dofs)] = free
    global_displacements = scale * generalized
    global_displacements[list(problem.fixed_global_dofs)] = prescribed[
        list(problem.fixed_global_dofs)
    ]
    internal = np.zeros(problem.global_dof_count, dtype=np.float64)
    external = load_factor * problem.reference_external_load_vector()
    free_position = {global_dof: index for index, global_dof in enumerate(free_dofs)}
    coo_rows: list[int] = []
    coo_columns: list[int] = []
    coo_values: list[float] = []
    trial_hashes: list[str] = []

    for member, parent in zip(
        problem.members, accepted_checkpoint.element_states, strict=True
    ):
        global_dofs = problem.member_global_dofs(member)
        response = member.element.integrate(
            global_displacements[list(global_dofs)], parent
        )
        if response.parent_state_hash != parent.state_hash:
            raise ValueError("sparse assembly element parent binding failed")
        internal[list(global_dofs)] += response.internal_force_global
        tangent = np.asarray(response.consistent_tangent_global, dtype=np.float64)
        for local_row, global_row in enumerate(global_dofs):
            row = free_position.get(global_row)
            if row is None:
                continue
            for local_column, global_column in enumerate(global_dofs):
                column = free_position.get(global_column)
                if column is None:
                    continue
                coo_rows.append(row)
                coo_columns.append(column)
                coo_values.append(
                    float(
                        scale[global_row]
                        * tangent[local_row, local_column]
                        * scale[global_column]
                    )
                )
        trial_hashes.append(response.state.state_hash)

    physical_residual = internal - external
    residual = scale[list(free_dofs)] * physical_residual[list(free_dofs)]
    reactions = np.zeros(problem.global_dof_count, dtype=np.float64)
    reactions[list(problem.fixed_global_dofs)] = physical_residual[
        list(problem.fixed_global_dofs)
    ]
    size = len(free_dofs)
    coo = coo_matrix(
        (
            np.asarray(coo_values, dtype=np.float64),
            (
                np.asarray(coo_rows, dtype=np.int64),
                np.asarray(coo_columns, dtype=np.int64),
            ),
        ),
        shape=(size, size),
        dtype=np.float64,
    )
    csr = coo.tocsr(copy=True)
    csr.sum_duplicates()
    csr.eliminate_zeros()
    csr.sort_indices()
    if csr.shape != (size, size) or not np.all(np.isfinite(csr.data)):
        raise ValueError("native CSR tangent is invalid")

    frozen = {
        "generalized": immutable_array(generalized, dtype="<f8"),
        "global_displacements": immutable_array(global_displacements, dtype="<f8"),
        "residual": immutable_array(residual, dtype="<f8"),
        "internal": immutable_array(internal, dtype="<f8"),
        "external": immutable_array(external, dtype="<f8"),
        "reactions": immutable_array(reactions, dtype="<f8"),
        "coo_rows": immutable_array(coo_rows, dtype="<i8"),
        "coo_columns": immutable_array(coo_columns, dtype="<i8"),
        "coo_values": immutable_array(coo_values, dtype="<f8"),
        "csr_row_ptr": immutable_array(csr.indptr, dtype="<i8"),
        "csr_columns": immutable_array(csr.indices, dtype="<i8"),
        "csr_values": immutable_array(csr.data, dtype="<f8"),
    }
    pattern_hash = canonical_hash(
        {
            "shape": [size, size],
            "row_ptr": frozen["csr_row_ptr"].tolist(),
            "column_indices": frozen["csr_columns"].tolist(),
        }
    )
    numeric_hash = array_data_hash(frozen["csr_values"])
    provisional = CorotationalFiberFrameSparseAssembly(
        schema_version=COROTATIONAL_FIBER_FRAME_SPARSE_ASSEMBLY_SCHEMA_VERSION,
        assembly_hash=_HASH_ZERO,
        storage_profile=COROTATIONAL_FIBER_FRAME_SPARSE_STORAGE_PROFILE,
        problem_contract_hash=problem.contract_hash,
        parent_checkpoint_hash=accepted_checkpoint.state_hash,
        target_load_factor=load_factor,
        free_equation_count=size,
        raw_coo_entry_count=len(coo_values),
        csr_nnz=int(csr.nnz),
        csr_pattern_hash=pattern_hash,
        csr_numeric_hash=numeric_hash,
        generalized_coordinates_m=frozen["generalized"],
        global_displacements=frozen["global_displacements"],
        residual_kn=frozen["residual"],
        internal_loads_global=frozen["internal"],
        external_loads_global=frozen["external"],
        reactions_global=frozen["reactions"],
        coo_row_indices=frozen["coo_rows"],
        coo_column_indices=frozen["coo_columns"],
        coo_values_kn_per_m=frozen["coo_values"],
        csr_row_ptr=frozen["csr_row_ptr"],
        csr_column_indices=frozen["csr_columns"],
        csr_values_kn_per_m=frozen["csr_values"],
        trial_element_state_hashes=tuple(trial_hashes),
    )
    return replace(
        provisional,
        assembly_hash=canonical_hash(
            {
                key: value
                for key, value in provisional.to_manifest().items()
                if key != "assembly_hash"
            }
        ),
    )


def compare_corotational_fiber_frame_dense_sparse_assembly(
    problem: StatefulCorotationalFiberFrame2DProblem,
    accepted_checkpoint: StatefulCorotationalFiberFrame2DCheckpoint,
    *,
    target_load_factor: float,
    trial_free_coordinates_m: Any,
) -> CorotationalFiberFrameDenseSparseParityReceipt:
    """Build independent dense and native sparse paths for one trial coordinate."""

    dense = assemble_stateful_corotational_fiber_frame2d(
        problem,
        accepted_checkpoint,
        target_load_factor=target_load_factor,
        trial_free_coordinates_m=trial_free_coordinates_m,
    )
    sparse = assemble_stateful_corotational_fiber_frame2d_sparse(
        problem,
        accepted_checkpoint,
        target_load_factor=target_load_factor,
        trial_free_coordinates_m=trial_free_coordinates_m,
    )
    metrics = MappingProxyType(
        {
            "generalized_coordinate_scaled_linf": _scaled_linf(
                dense.generalized_coordinates_m, sparse.generalized_coordinates_m
            ),
            "global_displacement_scaled_linf": _scaled_linf(
                dense.global_displacements, sparse.global_displacements
            ),
            "residual_scaled_linf": _scaled_linf(dense.residual_kn, sparse.residual_kn),
            "tangent_scaled_linf": _scaled_linf(
                dense.jacobian_kn_per_m, sparse.jacobian_csr.toarray()
            ),
            "internal_load_scaled_linf": _scaled_linf(
                dense.internal_loads_global, sparse.internal_loads_global
            ),
            "external_load_scaled_linf": _scaled_linf(
                dense.external_loads_global, sparse.external_loads_global
            ),
            "reaction_scaled_linf": _scaled_linf(
                dense.reactions_global, sparse.reactions_global
            ),
        }
    )
    tolerance = COROTATIONAL_FIBER_FRAME_DENSE_SPARSE_PARITY_TOLERANCE
    checks = MappingProxyType(
        {
            "native_coo_created": sparse.raw_coo_entry_count > 0,
            "canonical_csr_created": sparse.csr_nnz > 0,
            "canonical_csr_sorted": sparse.jacobian_csr.has_sorted_indices,
            "generalized_coordinate_parity": metrics[
                "generalized_coordinate_scaled_linf"
            ]
            <= tolerance,
            "global_displacement_parity": metrics["global_displacement_scaled_linf"]
            <= tolerance,
            "residual_parity": metrics["residual_scaled_linf"] <= tolerance,
            "tangent_parity": metrics["tangent_scaled_linf"] <= tolerance,
            "internal_load_parity": metrics["internal_load_scaled_linf"] <= tolerance,
            "external_load_parity": metrics["external_load_scaled_linf"] <= tolerance,
            "reaction_parity": metrics["reaction_scaled_linf"] <= tolerance,
            "trial_state_hash_parity": sparse.trial_element_state_hashes
            == tuple(state.state_hash for state in dense.trial_element_states),
        }
    )
    if not all(checks.values()):
        raise ValueError("corotational dense/sparse assembly parity failed")
    provisional = CorotationalFiberFrameDenseSparseParityReceipt(
        schema_version=COROTATIONAL_FIBER_FRAME_DENSE_SPARSE_PARITY_SCHEMA_VERSION,
        receipt_hash=_HASH_ZERO,
        problem_contract_hash=problem.contract_hash,
        parent_checkpoint_hash=accepted_checkpoint.state_hash,
        target_load_factor=float(target_load_factor),
        dense_assembly_hash=canonical_hash(dense.to_dict()),
        sparse_assembly_hash=sparse.assembly_hash,
        csr_pattern_hash=sparse.csr_pattern_hash,
        csr_numeric_hash=sparse.csr_numeric_hash,
        csr_nnz=sparse.csr_nnz,
        metrics=metrics,
        checks=checks,
        authority=MappingProxyType(
            {
                "numerical_parity": "bounded_candidate",
                "engineering_result": "not_created",
                "external_vv": "not_attached",
                "release_readiness": "not_authoritative",
            }
        ),
    )
    return replace(
        provisional,
        receipt_hash=canonical_hash(_parity_payload(provisional, include_hash=False)),
    )


def _parity_payload(
    receipt: CorotationalFiberFrameDenseSparseParityReceipt,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": receipt.schema_version,
        "problem_contract_hash": receipt.problem_contract_hash,
        "parent_checkpoint_hash": receipt.parent_checkpoint_hash,
        "target_load_factor": receipt.target_load_factor,
        "dense_assembly_hash": receipt.dense_assembly_hash,
        "sparse_assembly_hash": receipt.sparse_assembly_hash,
        "csr_pattern_hash": receipt.csr_pattern_hash,
        "csr_numeric_hash": receipt.csr_numeric_hash,
        "csr_nnz": receipt.csr_nnz,
        "metrics": dict(receipt.metrics),
        "checks": dict(receipt.checks),
        "authority": dict(receipt.authority),
    }
    if include_hash:
        payload["receipt_hash"] = receipt.receipt_hash
    return payload


def _finite(value: Any, name: str) -> float:
    if isinstance(value, (bool, np.bool_)):
        raise ValueError(f"{name} must be finite")
    try:
        normalized = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be finite") from exc
    if not math.isfinite(normalized):
        raise ValueError(f"{name} must be finite")
    return normalized


def _linf(values: Any) -> float:
    array = np.asarray(values, dtype=np.float64)
    return float(np.max(np.abs(array))) if array.size else 0.0


def _scaled_linf(left: Any, right: Any) -> float:
    left_array = np.asarray(left, dtype=np.float64)
    right_array = np.asarray(right, dtype=np.float64)
    return _linf(left_array - right_array) / max(
        1.0, _linf(left_array), _linf(right_array)
    )


_HASH_ZERO = "sha256:" + "0" * 64


__all__ = [
    "COROTATIONAL_FIBER_FRAME_DENSE_SPARSE_PARITY_SCHEMA_VERSION",
    "COROTATIONAL_FIBER_FRAME_DENSE_SPARSE_PARITY_TOLERANCE",
    "COROTATIONAL_FIBER_FRAME_SPARSE_ASSEMBLY_SCHEMA_VERSION",
    "COROTATIONAL_FIBER_FRAME_SPARSE_STORAGE_PROFILE",
    "CorotationalFiberFrameDenseSparseParityReceipt",
    "CorotationalFiberFrameSparseAssembly",
    "assemble_stateful_corotational_fiber_frame2d_sparse",
    "compare_corotational_fiber_frame_dense_sparse_assembly",
]
