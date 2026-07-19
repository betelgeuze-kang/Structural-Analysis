"""Canonical sparse-LU level schedule and HIP apply parity contract.

This module prepares backend-neutral little-endian fixture bytes for a HIP
triangular apply. It derives dependency levels from the canonical L/U arrays,
provides both the canonical Python-``fsum`` result and a sequential-FP64 device
order reference, and validates runtime output. It does not execute HIP or claim
that a production-size factor is performant.
"""

from __future__ import annotations

from dataclasses import dataclass
import struct
from typing import Any

import numpy as np

from structural_analysis.engine_v2.contracts._canonical import (
    array_data_hash,
    canonical_hash,
    has_immutable_bytes_backing,
    immutable_array,
    sha256_prefixed,
)
from structural_analysis.solvers.nonlinear.canonical_sparse_lu import (
    CanonicalSparseLUFactor,
    create_canonical_sparse_lu_factor,
    validate_canonical_sparse_lu_factor,
)


HIP_SPARSE_LU_APPLY_FIXTURE_VERSION = (
    "engine-v2-hip-sparse-lu-apply-fixture.v1"
)
HIP_SPARSE_LU_APPLY_OUTPUT_VERSION = (
    "engine-v2-hip-sparse-lu-apply-output.v1"
)
HIP_SPARSE_LU_FIXTURE_VALIDATION_OUTPUT_VERSION = (
    "engine-v2-hip-sparse-lu-fixture-validation-output.v1"
)
HIP_SPARSE_LU_FIXTURE_VALIDATION_PROFILE = (
    "engine-v2-hip-sparse-lu-host-fixture-parser.v1"
)
HIP_SPARSE_LU_APPLY_PARITY_PROFILE = (
    "engine-v2-cpu-hip-canonical-sparse-lu-apply-parity.v1"
)
HIP_SPARSE_LU_APPLY_SCHEDULE_PROFILE = (
    "csr_triangular_dependency_level_schedule.v1"
)
HIP_SPARSE_LU_APPLY_EXECUTION_PROFILE = (
    "same_stream_level_scheduled_csr_forward_backward.v1"
)
HIP_SPARSE_LU_APPLY_ACCUMULATION_PROFILE = (
    "ascending_column_sequential_fp64.v1"
)
HIP_SPARSE_LU_APPLY_BINARY_MAGIC = b"EV2SLU01"
HIP_SPARSE_LU_APPLY_ABSOLUTE_TOLERANCE_M = 1.0e-11
HIP_SPARSE_LU_APPLY_RELATIVE_TOLERANCE = 1.0e-11
HIP_SPARSE_LU_APPLY_HEADER = struct.Struct("<8sQQQQQ")


class HIPSparseLUApplyParityError(ValueError):
    """Fail-closed fixture or runtime-output validation error."""

    def __init__(self, code: str, path: str, message: str) -> None:
        self.code = code
        self.path = path
        self.message = message
        super().__init__(f"{code}@{path}: {message}")


def _fail(code: str, path: str, message: str) -> None:
    raise HIPSparseLUApplyParityError(code, path, message)


@dataclass(frozen=True)
class HIPSparseLUApplyFixture:
    """Canonical factor, dependency schedules, and one RHS fixture."""

    schema_version: str
    factor: CanonicalSparseLUFactor
    right_hand_side_kn: np.ndarray
    lower_level_pointer: np.ndarray
    lower_level_rows: np.ndarray
    upper_level_pointer: np.ndarray
    upper_level_rows: np.ndarray
    schedule_contract_hash: str

    @property
    def dimension(self) -> int:
        return self.factor.dimension

    @property
    def lower_level_count(self) -> int:
        return int(self.lower_level_pointer.size - 1)

    @property
    def upper_level_count(self) -> int:
        return int(self.upper_level_pointer.size - 1)

    @property
    def expected_kernel_invocation_count(self) -> int:
        return self.lower_level_count + self.upper_level_count + 2

    def to_bytes(self) -> bytes:
        validate_hip_sparse_lu_apply_fixture(self)
        factor = self.factor
        chunks = [
            HIP_SPARSE_LU_APPLY_HEADER.pack(
                HIP_SPARSE_LU_APPLY_BINARY_MAGIC,
                self.dimension,
                int(factor.lower_numeric_values.size),
                int(factor.upper_numeric_values.size),
                self.lower_level_count,
                self.upper_level_count,
            )
        ]
        chunks.extend(
            memoryview(array).cast("B")
            for array in _fixture_arrays(self).values()
        )
        return b"".join(chunks)

    @property
    def fixture_hash(self) -> str:
        return sha256_prefixed(self.to_bytes())

    @property
    def preconditioner_contract_hash(self) -> str:
        return canonical_hash(
            {
                "parity_profile": HIP_SPARSE_LU_APPLY_PARITY_PROFILE,
                "factor_contract_hash": self.factor.contract_hash,
                "schedule_contract_hash": self.schedule_contract_hash,
                "fixture_hash": self.fixture_hash,
                "input_force_unit": "kN",
                "output_displacement_unit": "m",
            }
        )

    def to_manifest(self) -> dict[str, Any]:
        validate_hip_sparse_lu_apply_fixture(self)
        arrays = _fixture_arrays(self)
        return {
            "schema_version": self.schema_version,
            "fixture_hash": self.fixture_hash,
            "parity_profile": HIP_SPARSE_LU_APPLY_PARITY_PROFILE,
            "schedule_profile": HIP_SPARSE_LU_APPLY_SCHEDULE_PROFILE,
            "execution_profile": HIP_SPARSE_LU_APPLY_EXECUTION_PROFILE,
            "accumulation_profile": HIP_SPARSE_LU_APPLY_ACCUMULATION_PROFILE,
            "factor_contract_hash": self.factor.contract_hash,
            "schedule_contract_hash": self.schedule_contract_hash,
            "preconditioner_contract_hash": (
                self.preconditioner_contract_hash
            ),
            "dimension": self.dimension,
            "lower_nnz": int(self.factor.lower_numeric_values.size),
            "upper_nnz": int(self.factor.upper_numeric_values.size),
            "lower_level_count": self.lower_level_count,
            "upper_level_count": self.upper_level_count,
            "expected_kernel_invocation_count": (
                self.expected_kernel_invocation_count
            ),
            "binary_profile": "canonical_little_endian_mixed_numeric.v1",
            "arrays": {
                name: {
                    "dtype": array.dtype.str,
                    "shape": [int(value) for value in array.shape],
                    "byte_length": int(array.nbytes),
                    "data_hash": array_data_hash(array),
                }
                for name, array in arrays.items()
            },
            "claim_boundary": (
                "This fixture fixes sparse-LU factor bytes, row/column "
                "permutations, triangular dependency levels, and one RHS. "
                "Actual HIP execution, production-size scalability, "
                "performance, and CPU/HIP parity require a device receipt."
            ),
        }


@dataclass(frozen=True)
class HIPSparseLUApplyReference:
    fixture: HIPSparseLUApplyFixture
    canonical_solution_m: np.ndarray
    device_order_solution_m: np.ndarray


def create_hip_sparse_lu_apply_fixture(
    factor: CanonicalSparseLUFactor,
    *,
    right_hand_side_kn: Any,
) -> HIPSparseLUApplyFixture:
    """Derive immutable triangular level schedules for one canonical factor."""

    validated = validate_canonical_sparse_lu_factor(factor)
    rhs = _finite_vector(
        right_hand_side_kn,
        dimension=validated.dimension,
        path="/right_hand_side_kn",
    )
    lower_pointer, lower_rows = _derive_level_schedule(
        row_pointer=validated.lower_row_pointer,
        column_indices=validated.lower_column_indices,
        dimension=validated.dimension,
        lower=True,
    )
    upper_pointer, upper_rows = _derive_level_schedule(
        row_pointer=validated.upper_row_pointer,
        column_indices=validated.upper_column_indices,
        dimension=validated.dimension,
        lower=False,
    )
    schedule_hash = _schedule_contract_hash(
        factor=validated,
        lower_level_pointer=lower_pointer,
        lower_level_rows=lower_rows,
        upper_level_pointer=upper_pointer,
        upper_level_rows=upper_rows,
    )
    fixture = HIPSparseLUApplyFixture(
        schema_version=HIP_SPARSE_LU_APPLY_FIXTURE_VERSION,
        factor=validated,
        right_hand_side_kn=rhs,
        lower_level_pointer=lower_pointer,
        lower_level_rows=lower_rows,
        upper_level_pointer=upper_pointer,
        upper_level_rows=upper_rows,
        schedule_contract_hash=schedule_hash,
    )
    return validate_hip_sparse_lu_apply_fixture(fixture)


def validate_hip_sparse_lu_apply_fixture(
    fixture: HIPSparseLUApplyFixture,
) -> HIPSparseLUApplyFixture:
    if type(fixture) is not HIPSparseLUApplyFixture:
        _fail("hip_sparse_lu_fixture_type_invalid", "/", "Expected fixture.")
    if fixture.schema_version != HIP_SPARSE_LU_APPLY_FIXTURE_VERSION:
        _fail(
            "hip_sparse_lu_fixture_schema_invalid",
            "/schema_version",
            "Unsupported fixture schema.",
        )
    factor = validate_canonical_sparse_lu_factor(fixture.factor)
    _validate_float_array(
        fixture.right_hand_side_kn,
        shape=(factor.dimension,),
        path="/right_hand_side_kn",
    )
    _validate_level_schedule(
        row_pointer=factor.lower_row_pointer,
        column_indices=factor.lower_column_indices,
        level_pointer=fixture.lower_level_pointer,
        level_rows=fixture.lower_level_rows,
        dimension=factor.dimension,
        lower=True,
        path="/lower_schedule",
    )
    _validate_level_schedule(
        row_pointer=factor.upper_row_pointer,
        column_indices=factor.upper_column_indices,
        level_pointer=fixture.upper_level_pointer,
        level_rows=fixture.upper_level_rows,
        dimension=factor.dimension,
        lower=False,
        path="/upper_schedule",
    )
    expected_hash = _schedule_contract_hash(
        factor=factor,
        lower_level_pointer=fixture.lower_level_pointer,
        lower_level_rows=fixture.lower_level_rows,
        upper_level_pointer=fixture.upper_level_pointer,
        upper_level_rows=fixture.upper_level_rows,
    )
    if fixture.schedule_contract_hash != expected_hash:
        _fail(
            "hip_sparse_lu_schedule_hash_mismatch",
            "/schedule_contract_hash",
            "Schedule contract hash is stale.",
        )
    return fixture


def build_hip_sparse_lu_apply_reference() -> HIPSparseLUApplyReference:
    """Build a nontrivial deterministic factor fixture and two CPU results."""

    factor = _synthetic_factor()
    fixture = create_hip_sparse_lu_apply_fixture(
        factor,
        right_hand_side_kn=np.asarray(
            [0.125, -0.4, 0.75, -0.2, 0.9, -0.33, 0.48, -0.61],
            dtype="<f8",
        ),
    )
    canonical = immutable_array(
        factor.solve_kn_to_m(fixture.right_hand_side_kn),
        dtype="<f8",
    )
    device_order = immutable_array(
        _device_order_apply(fixture),
        dtype="<f8",
    )
    return HIPSparseLUApplyReference(
        fixture=fixture,
        canonical_solution_m=canonical,
        device_order_solution_m=device_order,
    )


def compare_hip_sparse_lu_apply_output(
    reference: HIPSparseLUApplyReference,
    runtime_output: Any,
) -> dict[str, Any]:
    """Validate one actual HIP runtime payload against both CPU references."""

    if type(reference) is not HIPSparseLUApplyReference:
        _fail("hip_sparse_lu_reference_invalid", "/", "Expected reference.")
    fixture = validate_hip_sparse_lu_apply_fixture(reference.fixture)
    if not isinstance(runtime_output, dict):
        _fail("hip_sparse_lu_output_type_invalid", "/", "Expected object.")
    required = {
        "schema_version",
        "status",
        "cpu_backend",
        "device_name",
        "gcn_arch_name",
        "execution_profile",
        "accumulation_profile",
        "dimension",
        "lower_level_count",
        "upper_level_count",
        "kernel_invocation_count",
        "mid_apply_d2h_transfer_count",
        "blocking_d2h_synchronization_count",
        "solution_m",
    }
    if set(runtime_output) != required:
        _fail(
            "hip_sparse_lu_output_fields_invalid",
            "/",
            "Runtime output fields are not exact.",
        )
    expected_scalars = {
        "schema_version": HIP_SPARSE_LU_APPLY_OUTPUT_VERSION,
        "status": "ok",
        "cpu_backend": False,
        "execution_profile": HIP_SPARSE_LU_APPLY_EXECUTION_PROFILE,
        "accumulation_profile": HIP_SPARSE_LU_APPLY_ACCUMULATION_PROFILE,
        "dimension": fixture.dimension,
        "lower_level_count": fixture.lower_level_count,
        "upper_level_count": fixture.upper_level_count,
        "kernel_invocation_count": fixture.expected_kernel_invocation_count,
        "mid_apply_d2h_transfer_count": 0,
        "blocking_d2h_synchronization_count": 1,
    }
    for name, expected in expected_scalars.items():
        if runtime_output[name] != expected:
            _fail(
                "hip_sparse_lu_output_semantics_invalid",
                f"/{name}",
                "Runtime metadata does not match the fixture contract.",
            )
    for name in ("device_name", "gcn_arch_name"):
        if not isinstance(runtime_output[name], str) or not runtime_output[
            name
        ].strip():
            _fail(
                "hip_sparse_lu_device_identity_invalid",
                f"/{name}",
                "Device identity is required.",
            )
    solution = _finite_vector(
        runtime_output["solution_m"],
        dimension=fixture.dimension,
        path="/solution_m",
    )
    canonical_error = np.abs(solution - reference.canonical_solution_m)
    device_order_error = np.abs(solution - reference.device_order_solution_m)
    canonical_max_abs = float(np.max(canonical_error))
    device_order_max_abs = float(np.max(device_order_error))
    canonical_scale = max(
        float(np.max(np.abs(reference.canonical_solution_m))),
        1.0,
    )
    tolerance = max(
        HIP_SPARSE_LU_APPLY_ABSOLUTE_TOLERANCE_M,
        HIP_SPARSE_LU_APPLY_RELATIVE_TOLERANCE * canonical_scale,
    )
    contract_pass = bool(
        canonical_max_abs <= tolerance and device_order_max_abs <= tolerance
    )
    return {
        "profile": HIP_SPARSE_LU_APPLY_PARITY_PROFILE,
        "contract_pass": contract_pass,
        "canonical_cpu_max_abs_error_m": canonical_max_abs,
        "device_order_cpu_max_abs_error_m": device_order_max_abs,
        "comparison_tolerance_m": tolerance,
        "solution_data_hash": array_data_hash(solution),
        "canonical_solution_data_hash": array_data_hash(
            reference.canonical_solution_m
        ),
        "device_order_solution_data_hash": array_data_hash(
            reference.device_order_solution_m
        ),
        "actual_hardware_execution_required_for_claim": True,
        "production_performance_claim": False,
    }


def validate_hip_sparse_lu_fixture_parser_output(
    fixture: HIPSparseLUApplyFixture,
    runtime_output: Any,
) -> dict[str, Any]:
    """Validate the same HIP binary's host-only fixture-parser output."""

    validated = validate_hip_sparse_lu_apply_fixture(fixture)
    if not isinstance(runtime_output, dict):
        _fail("hip_sparse_lu_parser_output_type_invalid", "/", "Expected object.")
    required = {
        "schema_version",
        "status",
        "mode",
        "actual_hardware",
        "hip_runtime_api_call_count",
        "dimension",
        "lower_nnz",
        "upper_nnz",
        "lower_level_count",
        "upper_level_count",
        "expected_kernel_invocation_count",
        "fixture_byte_length",
    }
    if set(runtime_output) != required:
        _fail(
            "hip_sparse_lu_parser_output_fields_invalid",
            "/",
            "Fixture-parser output fields are not exact.",
        )
    expected = {
        "schema_version": HIP_SPARSE_LU_FIXTURE_VALIDATION_OUTPUT_VERSION,
        "status": "ok",
        "mode": "host_fixture_validation_only",
        "actual_hardware": False,
        "hip_runtime_api_call_count": 0,
        "dimension": validated.dimension,
        "lower_nnz": int(validated.factor.lower_numeric_values.size),
        "upper_nnz": int(validated.factor.upper_numeric_values.size),
        "lower_level_count": validated.lower_level_count,
        "upper_level_count": validated.upper_level_count,
        "expected_kernel_invocation_count": (
            validated.expected_kernel_invocation_count
        ),
        "fixture_byte_length": len(validated.to_bytes()),
    }
    if runtime_output != expected:
        _fail(
            "hip_sparse_lu_parser_output_semantics_invalid",
            "/",
            "Fixture-parser metadata does not match the canonical fixture.",
        )
    return {
        "profile": HIP_SPARSE_LU_FIXTURE_VALIDATION_PROFILE,
        "contract_pass": True,
        "fixture_hash": validated.fixture_hash,
        "runtime_output_hash": canonical_hash(runtime_output),
        "dimension": validated.dimension,
        "fixture_byte_length": expected["fixture_byte_length"],
        "actual_hardware_execution": False,
        "hip_runtime_api_call_count": 0,
    }


def _derive_level_schedule(
    *,
    row_pointer: np.ndarray,
    column_indices: np.ndarray,
    dimension: int,
    lower: bool,
) -> tuple[np.ndarray, np.ndarray]:
    levels = [-1] * dimension
    rows = range(dimension) if lower else range(dimension - 1, -1, -1)
    for row in rows:
        start = int(row_pointer[row])
        stop = int(row_pointer[row + 1])
        dependencies = (
            column_indices[start : stop - 1]
            if lower
            else column_indices[start + 1 : stop]
        )
        level = 0
        for raw_column in dependencies:
            column = int(raw_column)
            if levels[column] < 0:
                _fail(
                    "hip_sparse_lu_dependency_order_invalid",
                    f"/{'lower' if lower else 'upper'}/{row}",
                    "A triangular dependency has no prior level.",
                )
            level = max(level, levels[column] + 1)
        levels[row] = level
    level_rows: list[int] = []
    level_pointer = [0]
    for level in range(max(levels) + 1):
        level_rows.extend(row for row, value in enumerate(levels) if value == level)
        level_pointer.append(len(level_rows))
    return (
        immutable_array(level_pointer, dtype="<i8"),
        immutable_array(level_rows, dtype="<i8"),
    )


def _validate_level_schedule(
    *,
    row_pointer: np.ndarray,
    column_indices: np.ndarray,
    level_pointer: np.ndarray,
    level_rows: np.ndarray,
    dimension: int,
    lower: bool,
    path: str,
) -> None:
    _validate_int_array(level_pointer, path=f"{path}/level_pointer")
    _validate_int_array(level_rows, path=f"{path}/level_rows")
    if (
        level_pointer.size < 2
        or level_pointer[0] != 0
        or level_pointer[-1] != dimension
        or np.any(level_pointer[1:] <= level_pointer[:-1])
        or level_rows.size != dimension
        or not np.array_equal(np.sort(level_rows), np.arange(dimension))
    ):
        _fail(
            "hip_sparse_lu_level_schedule_invalid",
            path,
            "Level schedule is not a complete ordered partition.",
        )
    row_level = np.empty(dimension, dtype=np.int64)
    for level in range(level_pointer.size - 1):
        start = int(level_pointer[level])
        stop = int(level_pointer[level + 1])
        rows = level_rows[start:stop]
        if np.any(rows[1:] <= rows[:-1]):
            _fail(
                "hip_sparse_lu_level_row_order_invalid",
                f"{path}/{level}",
                "Rows within a level must be ascending.",
            )
        row_level[rows] = level
    for row in range(dimension):
        start = int(row_pointer[row])
        stop = int(row_pointer[row + 1])
        dependencies = (
            column_indices[start : stop - 1]
            if lower
            else column_indices[start + 1 : stop]
        )
        if any(row_level[int(column)] >= row_level[row] for column in dependencies):
            _fail(
                "hip_sparse_lu_level_dependency_invalid",
                f"{path}/{row}",
                "Dependency is not in an earlier level.",
            )


def _device_order_apply(fixture: HIPSparseLUApplyFixture) -> np.ndarray:
    factor = fixture.factor
    permuted = np.empty(fixture.dimension, dtype=np.float64)
    for index in range(fixture.dimension):
        permuted[int(factor.row_permutation[index])] = (
            float(fixture.right_hand_side_kn[index]) * 1000.0
        )
    lower_solution = np.zeros(fixture.dimension, dtype=np.float64)
    _sequential_level_solve(
        row_pointer=factor.lower_row_pointer,
        column_indices=factor.lower_column_indices,
        numeric_values=factor.lower_numeric_values,
        level_pointer=fixture.lower_level_pointer,
        level_rows=fixture.lower_level_rows,
        right_hand_side=permuted,
        solution=lower_solution,
        lower=True,
    )
    upper_solution = np.zeros(fixture.dimension, dtype=np.float64)
    _sequential_level_solve(
        row_pointer=factor.upper_row_pointer,
        column_indices=factor.upper_column_indices,
        numeric_values=factor.upper_numeric_values,
        level_pointer=fixture.upper_level_pointer,
        level_rows=fixture.upper_level_rows,
        right_hand_side=lower_solution,
        solution=upper_solution,
        lower=False,
    )
    return np.ascontiguousarray(
        upper_solution[factor.column_permutation],
        dtype="<f8",
    )


def _sequential_level_solve(
    *,
    row_pointer: np.ndarray,
    column_indices: np.ndarray,
    numeric_values: np.ndarray,
    level_pointer: np.ndarray,
    level_rows: np.ndarray,
    right_hand_side: np.ndarray,
    solution: np.ndarray,
    lower: bool,
) -> None:
    for level in range(level_pointer.size - 1):
        for offset in range(
            int(level_pointer[level]),
            int(level_pointer[level + 1]),
        ):
            row = int(level_rows[offset])
            start = int(row_pointer[row])
            stop = int(row_pointer[row + 1])
            tail = 0.0
            positions = range(start, stop - 1) if lower else range(start + 1, stop)
            for position in positions:
                product = float(numeric_values[position]) * float(
                    solution[int(column_indices[position])]
                )
                tail += product
            diagonal = 1.0 if lower else float(numeric_values[start])
            solution[row] = (float(right_hand_side[row]) - tail) / diagonal


def _schedule_contract_hash(
    *,
    factor: CanonicalSparseLUFactor,
    lower_level_pointer: np.ndarray,
    lower_level_rows: np.ndarray,
    upper_level_pointer: np.ndarray,
    upper_level_rows: np.ndarray,
) -> str:
    return canonical_hash(
        {
            "profile": HIP_SPARSE_LU_APPLY_SCHEDULE_PROFILE,
            "factor_contract_hash": factor.contract_hash,
            "lower_level_pointer_data_hash": array_data_hash(
                lower_level_pointer
            ),
            "lower_level_rows_data_hash": array_data_hash(lower_level_rows),
            "upper_level_pointer_data_hash": array_data_hash(
                upper_level_pointer
            ),
            "upper_level_rows_data_hash": array_data_hash(upper_level_rows),
            "within_level_row_order": "ascending",
            "dependency_rule": "strictly_earlier_level",
        }
    )


def _fixture_arrays(fixture: HIPSparseLUApplyFixture) -> dict[str, np.ndarray]:
    factor = fixture.factor
    return {
        "lower_row_pointer": factor.lower_row_pointer,
        "lower_column_indices": factor.lower_column_indices,
        "lower_numeric_values": factor.lower_numeric_values,
        "upper_row_pointer": factor.upper_row_pointer,
        "upper_column_indices": factor.upper_column_indices,
        "upper_numeric_values": factor.upper_numeric_values,
        "row_permutation": factor.row_permutation,
        "column_permutation": factor.column_permutation,
        "lower_level_pointer": fixture.lower_level_pointer,
        "lower_level_rows": fixture.lower_level_rows,
        "upper_level_pointer": fixture.upper_level_pointer,
        "upper_level_rows": fixture.upper_level_rows,
        "right_hand_side_kn": fixture.right_hand_side_kn,
    }


def _finite_vector(values: Any, *, dimension: int, path: str) -> np.ndarray:
    try:
        array = immutable_array(values, dtype="<f8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise HIPSparseLUApplyParityError(
            "hip_sparse_lu_vector_invalid",
            path,
            "Expected finite FP64 vector.",
        ) from exc
    if array.shape != (dimension,) or not np.all(np.isfinite(array)):
        _fail(
            "hip_sparse_lu_vector_invalid",
            path,
            f"Expected finite FP64 vector with shape ({dimension},).",
        )
    return array


def _validate_float_array(
    array: Any,
    *,
    shape: tuple[int, ...],
    path: str,
) -> None:
    if (
        not isinstance(array, np.ndarray)
        or array.dtype.str != "<f8"
        or array.shape != shape
        or not np.all(np.isfinite(array))
        or not has_immutable_bytes_backing(array)
    ):
        _fail(
            "hip_sparse_lu_float_array_invalid",
            path,
            "Array is not immutable canonical FP64.",
        )


def _validate_int_array(array: Any, *, path: str) -> None:
    if (
        not isinstance(array, np.ndarray)
        or array.dtype.str != "<i8"
        or array.ndim != 1
        or not has_immutable_bytes_backing(array)
    ):
        _fail(
            "hip_sparse_lu_integer_array_invalid",
            path,
            "Array is not immutable canonical int64.",
        )


def _synthetic_factor() -> CanonicalSparseLUFactor:
    lower_columns = (
        (0,),
        (0, 1),
        (0, 2),
        (1, 2, 3),
        (1, 4),
        (3, 4, 5),
        (2, 5, 6),
        (4, 6, 7),
    )
    lower_values = (
        (1.0,),
        (0.2, 1.0),
        (-0.1, 1.0),
        (0.3, -0.2, 1.0),
        (0.15, 1.0),
        (-0.25, 0.1, 1.0),
        (0.12, -0.08, 1.0),
        (0.05, 0.09, 1.0),
    )
    upper_columns = (
        (0, 1, 2),
        (1, 3, 4),
        (2, 3, 6),
        (3, 5),
        (4, 5, 7),
        (5, 6),
        (6, 7),
        (7,),
    )
    upper_values = (
        (4.0, -0.4, 0.2),
        (3.5, -0.3, 0.1),
        (3.8, 0.25, -0.15),
        (3.2, -0.2),
        (2.9, 0.18, -0.12),
        (3.1, 0.14),
        (2.7, -0.1),
        (2.5,),
    )
    lower_pointer, lower_indices, lower_numeric = _csr_arrays(
        lower_columns,
        lower_values,
    )
    upper_pointer, upper_indices, upper_numeric = _csr_arrays(
        upper_columns,
        upper_values,
    )
    return create_canonical_sparse_lu_factor(
        lower_row_pointer=lower_pointer,
        lower_column_indices=lower_indices,
        lower_numeric_values=lower_numeric,
        upper_row_pointer=upper_pointer,
        upper_column_indices=upper_indices,
        upper_numeric_values=upper_numeric,
        row_permutation=np.asarray([2, 0, 1, 4, 3, 6, 7, 5], dtype="<i8"),
        column_permutation=np.asarray(
            [1, 0, 3, 2, 5, 4, 7, 6],
            dtype="<i8",
        ),
        source_operator_pattern_hash=canonical_hash(
            {"fixture": "hip_sparse_lu_pattern"}
        ),
        source_operator_numeric_values_hash=canonical_hash(
            {"fixture": "hip_sparse_lu_values"}
        ),
    )


def _csr_arrays(
    columns: tuple[tuple[int, ...], ...],
    values: tuple[tuple[float, ...], ...],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    pointer = [0]
    flat_columns: list[int] = []
    flat_values: list[float] = []
    for row_columns, row_values in zip(columns, values, strict=True):
        flat_columns.extend(row_columns)
        flat_values.extend(row_values)
        pointer.append(len(flat_columns))
    return (
        np.asarray(pointer, dtype="<i8"),
        np.asarray(flat_columns, dtype="<i8"),
        np.asarray(flat_values, dtype="<f8"),
    )


__all__ = [
    "HIP_SPARSE_LU_APPLY_ABSOLUTE_TOLERANCE_M",
    "HIP_SPARSE_LU_APPLY_ACCUMULATION_PROFILE",
    "HIP_SPARSE_LU_APPLY_BINARY_MAGIC",
    "HIP_SPARSE_LU_APPLY_EXECUTION_PROFILE",
    "HIP_SPARSE_LU_APPLY_FIXTURE_VERSION",
    "HIP_SPARSE_LU_APPLY_OUTPUT_VERSION",
    "HIP_SPARSE_LU_APPLY_PARITY_PROFILE",
    "HIP_SPARSE_LU_APPLY_RELATIVE_TOLERANCE",
    "HIP_SPARSE_LU_APPLY_SCHEDULE_PROFILE",
    "HIP_SPARSE_LU_FIXTURE_VALIDATION_OUTPUT_VERSION",
    "HIP_SPARSE_LU_FIXTURE_VALIDATION_PROFILE",
    "HIPSparseLUApplyFixture",
    "HIPSparseLUApplyParityError",
    "HIPSparseLUApplyReference",
    "build_hip_sparse_lu_apply_reference",
    "compare_hip_sparse_lu_apply_output",
    "create_hip_sparse_lu_apply_fixture",
    "validate_hip_sparse_lu_apply_fixture",
    "validate_hip_sparse_lu_fixture_parser_output",
]
