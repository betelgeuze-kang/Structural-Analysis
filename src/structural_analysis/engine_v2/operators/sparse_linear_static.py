"""Deterministic CPU direct-CSR execution for ``ExecutionPlanV2``.

Assembly, residual/JVP, reaction, and recovery remain sparse or element-local.
The SciPy sparse direct solve is intentionally not claimed to be O(N).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from functools import lru_cache
import json
import math
from pathlib import Path
import warnings
from typing import Any

from jsonschema import Draft202012Validator
import numpy as np

from structural_analysis.engine_v2.buffers import DOF_ORDER
from structural_analysis.engine_v2.contracts._canonical import (
    array_content_hash,
    array_data_hash,
    canonical_hash,
    has_immutable_bytes_backing,
    immutable_array,
)
from structural_analysis.engine_v2.contracts.execution_plan_v2 import (
    ExecutionPlanV2,
    PlanArrayDescriptorV2,
    _csr_matvec,
    validate_execution_plan_v2,
)
from structural_analysis.solvers.equation_scaling import (
    EquationScaling6DOF,
    build_equation_scaling_6dof,
    characteristic_length_from_coordinates,
)

SPARSE_LINEAR_STATIC_RESULT_V2_SCHEMA_VERSION = (
    "structural-analysis-sparse-linear-static-result.v2"
)
_DOFS_PER_NODE = 6
_RESULT_ARRAY_NAMES = (
    "displacements_si",
    "reactions_si",
    "residual_si",
    "element_end_forces_local_si",
    "element_strain_energy_j",
)


class SparseLinearStaticErrorV2(RuntimeError):
    """Fail-closed sparse execution/result error."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True)
class SparseLinearStaticResultV2:
    schema_version: str
    status: str
    backend: str
    execution_plan_hash: str
    operator_version: str
    operator_hash: str
    numeric_snapshot_hash: str
    result_hash: str
    total_strain_energy_j: float
    free_residual_linf: float
    scaled_free_residual: float
    equation_scaling_6dof: EquationScaling6DOF
    constrained_dofs: tuple[int, ...]
    free_dofs: tuple[int, ...]
    descriptors: tuple[PlanArrayDescriptorV2, ...]
    displacements_si: np.ndarray
    reactions_si: np.ndarray
    residual_si: np.ndarray
    element_end_forces_local_si: np.ndarray
    element_strain_energy_j: np.ndarray

    def array(self, name: str) -> np.ndarray:
        if name not in _RESULT_ARRAY_NAMES:
            raise KeyError(f"Unknown sparse result array: {name}")
        return getattr(self, name)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "backend": self.backend,
            "execution_plan_hash": self.execution_plan_hash,
            "operator_version": self.operator_version,
            "operator_hash": self.operator_hash,
            "numeric_snapshot_hash": self.numeric_snapshot_hash,
            "result_hash": self.result_hash,
            "metrics": {
                "total_strain_energy_j": self.total_strain_energy_j,
                "free_residual_linf": self.free_residual_linf,
                "scaled_free_residual": self.scaled_free_residual,
                "equation_scaling_6dof": self.equation_scaling_6dof.to_dict(),
            },
            "constraint_partition": {
                "constrained_dofs": list(self.constrained_dofs),
                "free_dofs": list(self.free_dofs),
            },
            "arrays": [row.to_dict() for row in self.descriptors],
            "claim_boundary": {
                "global_dense_matrix_materialized": False,
                "residual_jvp_complexity": "O(nnz)",
                "linear_solver": "scipy_sparse_direct",
                "direct_solve_complexity_claim": "not_O_N",
                "end_to_end_O_N_claim": False,
                "fallback_used": False,
                "validation_mode": "exact_same_runtime_direct_solve_replay",
                "cross_platform_serialized_replay": "not_implemented",
            },
            "extensions": {},
        }

    def to_manifest(self) -> dict[str, Any]:
        return self.to_dict()


def solve_sparse_execution_plan_v2(plan: ExecutionPlanV2) -> SparseLinearStaticResultV2:
    """Execute one validated plan without rebuilding or densifying its CSR."""

    validate_execution_plan_v2(plan)
    free = np.asarray(plan.array("free_dofs"), dtype=np.int64)
    constrained = np.asarray(plan.array("constrained_dofs"), dtype=np.int64)
    displacement = np.zeros(plan.dof_count, dtype="<f8")
    displacement[free] = _solve_reduced_system(plan)
    displacement[displacement == 0.0] = 0.0

    residual = plan.residual(displacement)
    free_residual_linf = float(np.max(np.abs(residual[free]))) if free.size else 0.0
    reference_force = max(
        1.0,
        float(np.max(np.abs(plan.array("global_load")))),
    )
    equation_scaling = build_equation_scaling_6dof(
        reference_force=reference_force,
        characteristic_length=characteristic_length_from_coordinates(
            plan._source_buffers.array("node_coordinates_m")
        ),
        residual=residual[free],
        increment=displacement[free],
        tangent=_reduced_matrix(plan),
        dof_labels=tuple(DOF_ORDER[index % _DOFS_PER_NODE] for index in free),
    )
    scaled_residual = equation_scaling.scaled_residual_norm
    status = "ready" if scaled_residual <= plan.residual_tolerance else "failed"

    reactions = np.zeros(plan.dof_count, dtype="<f8")
    reactions[constrained] = residual[constrained]
    element_forces = np.zeros((plan.element_count, 2, _DOFS_PER_NODE), dtype="<f8")
    element_energy = np.zeros(plan.element_count, dtype="<f8")
    element_dofs = plan.array("element_global_dofs")
    transforms = plan.array("recovery_transform_global_to_local")
    local_stiffness = plan.array("recovery_stiffness_local")
    for element_index in range(plan.element_count):
        global_displacement = displacement[element_dofs[element_index]]
        local_displacement = transforms[element_index] @ global_displacement
        local_force = local_stiffness[element_index] @ local_displacement
        element_forces[element_index] = local_force.reshape(2, _DOFS_PER_NODE)
        element_energy[element_index] = 0.5 * float(local_displacement @ local_force)
    if np.any(element_energy < 0.0):
        raise SparseLinearStaticErrorV2(
            "sparse_linear_static_negative_energy",
            "Element strain energy must not be negative.",
        )
    total_energy = float(np.sum(element_energy))
    if total_energy < 0.0 or not math.isfinite(total_energy):
        raise SparseLinearStaticErrorV2(
            "sparse_linear_static_negative_energy",
            "Total strain energy must be finite and nonnegative.",
        )
    if total_energy == 0.0:
        total_energy = 0.0

    arrays = {
        "displacements_si": _normalized_immutable(
            displacement.reshape(plan.node_count, _DOFS_PER_NODE)
        ),
        "reactions_si": _normalized_immutable(
            reactions.reshape(plan.node_count, _DOFS_PER_NODE)
        ),
        "residual_si": _normalized_immutable(
            residual.reshape(plan.node_count, _DOFS_PER_NODE)
        ),
        "element_end_forces_local_si": _normalized_immutable(element_forces),
        "element_strain_energy_j": _normalized_immutable(element_energy),
    }
    descriptors = tuple(
        _result_array_descriptor(name, arrays[name]) for name in _RESULT_ARRAY_NAMES
    )
    result_hash = _result_hash(
        plan=plan,
        status=status,
        descriptors=descriptors,
        total_energy=total_energy,
        free_residual_linf=free_residual_linf,
        scaled_free_residual=scaled_residual,
        equation_scaling_6dof=equation_scaling,
    )
    result = SparseLinearStaticResultV2(
        schema_version=SPARSE_LINEAR_STATIC_RESULT_V2_SCHEMA_VERSION,
        status=status,
        backend="cpu_scipy_sparse_direct_csr_fp64",
        execution_plan_hash=plan.plan_hash,
        operator_version=plan.operator_version,
        operator_hash=plan.operator_hash,
        numeric_snapshot_hash=plan.numeric_snapshot_hash,
        result_hash=result_hash,
        total_strain_energy_j=total_energy,
        free_residual_linf=free_residual_linf,
        scaled_free_residual=scaled_residual,
        equation_scaling_6dof=equation_scaling,
        constrained_dofs=plan.constrained_dofs,
        free_dofs=plan.free_dofs,
        descriptors=descriptors,
        **arrays,
    )
    validate_sparse_linear_static_result_v2(result, expected_plan=plan)
    return result


def validate_sparse_linear_static_result_v2(
    result: SparseLinearStaticResultV2,
    *,
    expected_plan: ExecutionPlanV2,
) -> None:
    """Validate result receipt hashes and recompute sparse physics invariants."""

    if type(result) is not SparseLinearStaticResultV2:
        raise SparseLinearStaticErrorV2(
            "sparse_linear_static_result_type_invalid",
            "Expected a SparseLinearStaticResultV2 instance.",
        )
    if type(result.descriptors) is not tuple or any(
        type(row) is not PlanArrayDescriptorV2 for row in result.descriptors
    ):
        _result_fail("sparse_linear_static_result_container_invalid")
    validate_execution_plan_v2(expected_plan)
    errors = sorted(
        _result_validator().iter_errors(result.to_dict()),
        key=lambda error: list(error.absolute_path),
    )
    if errors:
        error = errors[0]
        path = "/" + "/".join(str(part) for part in error.absolute_path)
        raise SparseLinearStaticErrorV2(
            "sparse_linear_static_result_schema_invalid",
            f"{path}: {error.message}",
        )
    if result.schema_version != SPARSE_LINEAR_STATIC_RESULT_V2_SCHEMA_VERSION:
        _result_fail("sparse_linear_static_result_schema_mismatch")
    bindings = (
        (result.execution_plan_hash, expected_plan.plan_hash),
        (result.operator_version, expected_plan.operator_version),
        (result.operator_hash, expected_plan.operator_hash),
        (result.numeric_snapshot_hash, expected_plan.numeric_snapshot_hash),
        (result.constrained_dofs, expected_plan.constrained_dofs),
        (result.free_dofs, expected_plan.free_dofs),
    )
    if any(actual != expected for actual, expected in bindings):
        _result_fail("sparse_linear_static_result_plan_binding_mismatch")
    if tuple(row.name for row in result.descriptors) != _RESULT_ARRAY_NAMES:
        _result_fail("sparse_linear_static_result_descriptor_set_invalid")
    expected_shapes = {
        "displacements_si": (expected_plan.node_count, _DOFS_PER_NODE),
        "reactions_si": (expected_plan.node_count, _DOFS_PER_NODE),
        "residual_si": (expected_plan.node_count, _DOFS_PER_NODE),
        "element_end_forces_local_si": (
            expected_plan.element_count,
            2,
            _DOFS_PER_NODE,
        ),
        "element_strain_energy_j": (expected_plan.element_count,),
    }
    for descriptor in result.descriptors:
        array = result.array(descriptor.name)
        if (
            type(array) is not np.ndarray
            or array.dtype.str != "<f8"
            or array.shape != expected_shapes[descriptor.name]
            or not array.flags.c_contiguous
            or not has_immutable_bytes_backing(array)
            or not np.all(np.isfinite(array))
            or np.any(np.signbit(array[array == 0.0]))
        ):
            _result_fail("sparse_linear_static_result_array_invalid")
        if _result_array_descriptor(descriptor.name, array) != descriptor:
            _result_fail("sparse_linear_static_result_descriptor_mismatch")
    if (
        np.any(result.element_strain_energy_j < 0.0)
        or not math.isfinite(result.total_strain_energy_j)
        or result.total_strain_energy_j < 0.0
    ):
        _result_fail("sparse_linear_static_result_negative_energy")

    displacement = result.displacements_si.reshape(-1)
    replayed_displacement = np.zeros(expected_plan.dof_count, dtype="<f8")
    free = np.asarray(expected_plan.free_dofs, dtype=np.int64)
    replayed_displacement[free] = _solve_reduced_system(expected_plan)
    replayed_displacement = _normalized_copy(replayed_displacement)
    if not np.array_equal(displacement, replayed_displacement):
        _result_fail("sparse_linear_static_result_direct_solve_replay_mismatch")
    expected_residual = _normalized_copy(expected_plan.residual(displacement))
    if not np.array_equal(result.residual_si.reshape(-1), expected_residual):
        _result_fail("sparse_linear_static_result_residual_mismatch")
    expected_reactions = np.zeros(expected_plan.dof_count, dtype="<f8")
    constrained = np.asarray(expected_plan.constrained_dofs, dtype=np.int64)
    expected_reactions[constrained] = expected_residual[constrained]
    expected_reactions = _normalized_copy(expected_reactions)
    actual_reactions = result.reactions_si.reshape(-1)
    if np.any(actual_reactions[free] != 0.0):
        _result_fail("sparse_linear_static_result_free_reaction_nonzero")
    if not np.array_equal(actual_reactions, expected_reactions):
        _result_fail("sparse_linear_static_result_reaction_mismatch")
    if np.any(displacement[constrained] != 0.0):
        _result_fail("sparse_linear_static_result_constraint_mismatch")

    expected_forces = np.zeros_like(result.element_end_forces_local_si)
    expected_energy = np.zeros_like(result.element_strain_energy_j)
    element_dofs = expected_plan.array("element_global_dofs")
    transforms = expected_plan.array("recovery_transform_global_to_local")
    local_stiffness = expected_plan.array("recovery_stiffness_local")
    for element_index in range(expected_plan.element_count):
        local_displacement = (
            transforms[element_index] @ displacement[element_dofs[element_index]]
        )
        local_force = local_stiffness[element_index] @ local_displacement
        expected_forces[element_index] = local_force.reshape(2, _DOFS_PER_NODE)
        expected_energy[element_index] = 0.5 * float(local_displacement @ local_force)
    expected_forces = _normalized_copy(expected_forces)
    expected_energy = _normalized_copy(expected_energy)
    if np.any(expected_energy < 0.0):
        _result_fail("sparse_linear_static_result_negative_energy")
    if not np.array_equal(result.element_end_forces_local_si, expected_forces):
        _result_fail("sparse_linear_static_result_recovery_mismatch")
    if not np.array_equal(result.element_strain_energy_j, expected_energy):
        _result_fail("sparse_linear_static_result_energy_mismatch")
    expected_total = float(np.sum(expected_energy))
    if expected_total == 0.0:
        expected_total = 0.0
    if result.total_strain_energy_j != expected_total:
        _result_fail("sparse_linear_static_result_energy_mismatch")

    expected_linf = float(np.max(np.abs(expected_residual[free]))) if free.size else 0.0
    reference_force = max(
        1.0,
        float(np.max(np.abs(expected_plan.array("global_load")))),
    )
    expected_scaling = build_equation_scaling_6dof(
        reference_force=reference_force,
        characteristic_length=characteristic_length_from_coordinates(
            expected_plan._source_buffers.array("node_coordinates_m")
        ),
        residual=expected_residual[free],
        increment=displacement[free],
        tangent=_reduced_matrix(expected_plan),
        dof_labels=tuple(DOF_ORDER[index % _DOFS_PER_NODE] for index in free),
    )
    expected_scaled = expected_scaling.scaled_residual_norm
    if not math.isclose(
        result.free_residual_linf, expected_linf, rel_tol=0.0, abs_tol=0.0
    ):
        _result_fail("sparse_linear_static_result_residual_metric_mismatch")
    if not math.isclose(
        result.scaled_free_residual, expected_scaled, rel_tol=0.0, abs_tol=0.0
    ):
        _result_fail("sparse_linear_static_result_residual_metric_mismatch")
    if result.equation_scaling_6dof != expected_scaling:
        _result_fail("sparse_linear_static_result_equation_scaling_mismatch")
    expected_status = (
        "ready" if expected_scaled <= expected_plan.residual_tolerance else "failed"
    )
    if result.status != expected_status:
        _result_fail("sparse_linear_static_result_status_mismatch")
    expected_hash = _result_hash(
        plan=expected_plan,
        status=result.status,
        descriptors=result.descriptors,
        total_energy=result.total_strain_energy_j,
        free_residual_linf=result.free_residual_linf,
        scaled_free_residual=result.scaled_free_residual,
        equation_scaling_6dof=result.equation_scaling_6dof,
    )
    if result.result_hash != expected_hash:
        _result_fail("sparse_linear_static_result_hash_mismatch")


def _reduced_matrix(plan: ExecutionPlanV2) -> Any:
    try:
        from scipy.sparse import csr_matrix
    except ImportError as exc:  # pragma: no cover - environment-dependent
        raise SparseLinearStaticErrorV2(
            "sparse_linear_static_scipy_unavailable",
            "SciPy is required for the explicit sparse-direct execution path.",
        ) from exc

    free_count = len(plan.free_dofs)
    reduced_matrix = csr_matrix(
        (
            plan.array("reduced_stiffness_csr_values"),
            plan.array("reduced_csr_column_indices"),
            plan.array("reduced_csr_row_ptr"),
        ),
        shape=(free_count, free_count),
        copy=False,
    )
    if reduced_matrix.nnz != plan.reduced_nnz or not reduced_matrix.has_sorted_indices:
        raise SparseLinearStaticErrorV2(
            "sparse_linear_static_csr_construction_mismatch",
            "SciPy did not preserve the retained sorted reduced CSR slots.",
        )
    return reduced_matrix


def _solve_reduced_system(plan: ExecutionPlanV2) -> np.ndarray:
    try:
        from scipy.sparse.linalg import MatrixRankWarning, spsolve
    except ImportError as exc:  # pragma: no cover - environment-dependent
        raise SparseLinearStaticErrorV2(
            "sparse_linear_static_scipy_unavailable",
            "SciPy is required for the explicit sparse-direct execution path.",
        ) from exc

    free_count = len(plan.free_dofs)
    reduced_matrix = _reduced_matrix(plan)
    free = np.asarray(plan.free_dofs, dtype=np.int64)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", MatrixRankWarning)
            solution = spsolve(
                reduced_matrix,
                plan.array("global_load")[free],
                permc_spec="NATURAL",
                use_umfpack=False,
            )
    except (RuntimeError, ValueError, Warning) as exc:
        raise SparseLinearStaticErrorV2(
            "sparse_linear_static_singular_or_failed_solve",
            f"Reduced sparse-direct solve failed: {exc}",
        ) from exc
    normalized = _normalized_copy(np.asarray(solution, dtype="<f8").reshape(-1))
    if normalized.shape != (free_count,):
        raise SparseLinearStaticErrorV2(
            "sparse_linear_static_solution_shape_invalid",
            "Sparse-direct solve returned an invalid vector shape.",
        )
    return normalized


def sparse_reduced_jvp(plan: ExecutionPlanV2, direction: np.ndarray) -> np.ndarray:
    """Apply the retained reduced CSR directly; useful to iterative clients."""

    validate_execution_plan_v2(plan)
    vector = np.asarray(direction, dtype="<f8").reshape(-1)
    if vector.shape != (len(plan.free_dofs),) or not np.all(np.isfinite(vector)):
        raise ValueError(
            f"direction must be a finite vector with {len(plan.free_dofs)} values."
        )
    return _csr_matvec(
        plan.array("reduced_csr_row_ptr"),
        plan.array("reduced_csr_column_indices"),
        plan.array("reduced_stiffness_csr_values"),
        vector,
    )


def _normalized_immutable(value: np.ndarray) -> np.ndarray:
    return immutable_array(_normalized_copy(value), dtype="<f8")


def _normalized_copy(value: np.ndarray) -> np.ndarray:
    array = np.ascontiguousarray(value, dtype="<f8").copy()
    if not np.all(np.isfinite(array)):
        raise SparseLinearStaticErrorV2(
            "sparse_linear_static_non_finite_result",
            "Result payload contains NaN or Infinity.",
        )
    array[array == 0.0] = 0.0
    return array


def _result_array_descriptor(name: str, array: np.ndarray) -> PlanArrayDescriptorV2:
    metadata = {
        "name": name,
        "dtype": array.dtype.str,
        "shape": [int(value) for value in array.shape],
        "layout": "C",
        "byte_length": int(array.nbytes),
    }
    return PlanArrayDescriptorV2(
        name=name,
        dtype=array.dtype.str,
        shape=tuple(int(value) for value in array.shape),
        layout="C",
        byte_length=int(array.nbytes),
        data_hash=array_data_hash(array),
        content_hash=array_content_hash(metadata, array),
    )


def _result_hash(
    *,
    plan: ExecutionPlanV2,
    status: str,
    descriptors: tuple[PlanArrayDescriptorV2, ...],
    total_energy: float,
    free_residual_linf: float,
    scaled_free_residual: float,
    equation_scaling_6dof: EquationScaling6DOF,
) -> str:
    return canonical_hash(
        {
            "schema_version": SPARSE_LINEAR_STATIC_RESULT_V2_SCHEMA_VERSION,
            "execution_plan_hash": plan.plan_hash,
            "operator_hash": plan.operator_hash,
            "numeric_snapshot_hash": plan.numeric_snapshot_hash,
            "status": status,
            "backend": "cpu_scipy_sparse_direct_csr_fp64",
            "arrays": [asdict(row) for row in descriptors],
            "total_strain_energy_j": total_energy,
            "free_residual_linf": free_residual_linf,
            "scaled_free_residual": scaled_free_residual,
            "equation_scaling_6dof": equation_scaling_6dof.to_dict(),
        }
    )


@lru_cache(maxsize=1)
def _result_validator() -> Draft202012Validator:
    path = (
        Path(__file__).resolve().parents[2]
        / "schemas"
        / "sparse_linear_static_result_v2.schema.json"
    )
    schema = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _result_fail(code: str) -> None:
    raise SparseLinearStaticErrorV2(code, code)


__all__ = [
    "SPARSE_LINEAR_STATIC_RESULT_V2_SCHEMA_VERSION",
    "SparseLinearStaticErrorV2",
    "SparseLinearStaticResultV2",
    "solve_sparse_execution_plan_v2",
    "sparse_reduced_jvp",
    "validate_sparse_linear_static_result_v2",
]
