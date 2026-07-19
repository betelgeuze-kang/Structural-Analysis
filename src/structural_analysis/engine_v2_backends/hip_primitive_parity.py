"""Backend adapter fixture and validator for Engine v2 HIP primitives.

This module binds a small HIP operation probe to the same reduced-CSR identity
used by the deterministic CPU FGMRES reference.  Passing it establishes only
primitive numerical semantics.  It does not establish a device-resident full
FGMRES recurrence, a production preconditioner, or a performance claim.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import struct
from typing import Any

import numpy as np

from structural_analysis.engine_v2.contracts._canonical import (
    array_data_hash,
    canonical_hash,
    immutable_array,
    sha256_prefixed,
)
from structural_analysis.engine_v2.contracts.equation_scaling import (
    bind_equation_scaling_to_execution_plan,
    create_equation_scaling,
)
from structural_analysis.engine_v2.contracts.execution_plan import (
    create_execution_plan,
)
from structural_analysis.engine_v2.contracts.execution_plan_reduced_csr import (
    create_execution_plan_reduced_csr,
)
from structural_analysis.engine_v2.cpu_fgmres import (
    CPU_FGMRES_SCALED_JACOBI_PRECONDITIONER,
    CPUFGMRESRun,
    run_cpu_fgmres,
)


HIP_PRIMITIVE_FIXTURE_VERSION = "engine-v2-hip-primitive-fixture.v1"
HIP_PRIMITIVE_OUTPUT_VERSION = "engine-v2-hip-primitive-output.v1"
HIP_PRIMITIVE_PARITY_PROFILE = "engine-v2-cpu-hip-primitive-parity.v1"
HIP_PRIMITIVE_BINARY_MAGIC = b"EV2HIP01"
HIP_PRIMITIVE_OPERATION_ORDER = (
    "spmv",
    "dot",
    "l2_norm",
    "linf_norm",
    "preconditioner_apply",
    "axpy",
    "solution_update",
)
HIP_PRIMITIVE_REQUIRED_KERNEL_INVOCATIONS = 6
HIP_PRIMITIVE_ABSOLUTE_TOLERANCE = 1.0e-12
HIP_PRIMITIVE_RELATIVE_TOLERANCE = 1.0e-12
HIP_PRECONDITIONER_DERIVATION_PROFILE = (
    "exact_positive_diagonal_inverse_of_left_scaled_reduced_operator.v1"
)


class HIPPrimitiveParityError(ValueError):
    """Fail-closed HIP primitive output or fixture validation error."""

    def __init__(self, code: str, path: str, message: str) -> None:
        self.code = code
        self.path = path
        self.message = message
        super().__init__(f"{code}@{path}: {message}")


def _fail(code: str, path: str, message: str) -> None:
    raise HIPPrimitiveParityError(code, path, message)


@dataclass(frozen=True)
class HIPPrimitiveFixture:
    """Canonical little-endian input bytes for the HIP operation probe."""

    schema_version: str
    execution_plan_hash: str
    scaling_hash: str
    reduced_csr_identity_hash: str
    operator_numeric_values_hash: str
    row_ptr: np.ndarray
    column_indices: np.ndarray
    values: np.ndarray
    x: np.ndarray
    y: np.ndarray
    scale_divisors: np.ndarray
    inverse_diagonal: np.ndarray
    solution: np.ndarray
    direction: np.ndarray
    axpy_alpha: float
    update_alpha: float

    @property
    def dimension(self) -> int:
        return int(self.x.size)

    @property
    def nnz(self) -> int:
        return int(self.values.size)

    def to_bytes(self) -> bytes:
        header = struct.pack(
            "<8sQQdd",
            HIP_PRIMITIVE_BINARY_MAGIC,
            self.dimension,
            self.nnz,
            self.axpy_alpha,
            self.update_alpha,
        )
        return b"".join(
            (
                header,
                self.row_ptr.tobytes(order="C"),
                self.column_indices.tobytes(order="C"),
                self.values.tobytes(order="C"),
                self.x.tobytes(order="C"),
                self.y.tobytes(order="C"),
                self.scale_divisors.tobytes(order="C"),
                self.inverse_diagonal.tobytes(order="C"),
                self.solution.tobytes(order="C"),
                self.direction.tobytes(order="C"),
            )
        )

    @property
    def fixture_hash(self) -> str:
        return sha256_prefixed(self.to_bytes())

    @property
    def preconditioner_contract_hash(self) -> str:
        return canonical_hash(
            {
                "preconditioner_profile": (
                    CPU_FGMRES_SCALED_JACOBI_PRECONDITIONER
                ),
                "derivation_profile": HIP_PRECONDITIONER_DERIVATION_PROFILE,
                "scaling_hash": self.scaling_hash,
                "reduced_csr_identity_hash": self.reduced_csr_identity_hash,
                "operator_numeric_values_hash": (
                    self.operator_numeric_values_hash
                ),
                "inverse_diagonal_data_hash": array_data_hash(
                    self.inverse_diagonal
                ),
            }
        )

    def to_manifest(self) -> dict[str, Any]:
        arrays = {
            "row_ptr": self.row_ptr,
            "column_indices": self.column_indices,
            "values": self.values,
            "x": self.x,
            "y": self.y,
            "scale_divisors": self.scale_divisors,
            "inverse_diagonal": self.inverse_diagonal,
            "solution": self.solution,
            "direction": self.direction,
        }
        return {
            "schema_version": self.schema_version,
            "fixture_hash": self.fixture_hash,
            "execution_plan_hash": self.execution_plan_hash,
            "scaling_hash": self.scaling_hash,
            "reduced_csr_identity_hash": self.reduced_csr_identity_hash,
            "operator_numeric_values_hash": self.operator_numeric_values_hash,
            "preconditioner_profile": (
                CPU_FGMRES_SCALED_JACOBI_PRECONDITIONER
            ),
            "preconditioner_derivation_profile": (
                HIP_PRECONDITIONER_DERIVATION_PROFILE
            ),
            "preconditioner_contract_hash": self.preconditioner_contract_hash,
            "binary_profile": "canonical_little_endian_mixed_numeric.v1",
            "dimension": self.dimension,
            "nnz": self.nnz,
            "axpy_alpha": self.axpy_alpha,
            "update_alpha": self.update_alpha,
            "arrays": {
                name: {
                    "dtype": array.dtype.str,
                    "shape": list(array.shape),
                    "byte_length": int(array.nbytes),
                    "data_hash": array_data_hash(array),
                }
                for name, array in arrays.items()
            },
        }


@dataclass(frozen=True)
class EngineV2CPUHIPParityReference:
    """CPU FGMRES run and its exact reduced-CSR primitive fixture."""

    cpu_run: CPUFGMRESRun
    fixture: HIPPrimitiveFixture
    node_coordinates_m: np.ndarray
    reference_equation_load_si: np.ndarray


def _hash(character: str) -> str:
    return "sha256:" + character * 64


def build_engine_v2_cpu_hip_parity_reference(
    *,
    free_equation_count: int = 6,
) -> EngineV2CPUHIPParityReference:
    """Build a deterministic CPU reference and matching HIP primitive fixture."""

    if (
        type(free_equation_count) is not int
        or free_equation_count < 6
        or free_equation_count > 4092
        or free_equation_count % 6 != 0
    ):
        raise ValueError(
            "free_equation_count must be a multiple of six in [6, 4092]"
        )
    dof_count = free_equation_count + 6
    node_count = dof_count // 6
    free = np.arange(6, dof_count, dtype="<i4")
    constrained = np.arange(6, dtype="<i4")
    global_to_free = np.full(dof_count, -1, dtype="<i4")
    global_to_free[free] = np.arange(free.size, dtype="<i4")
    base = create_execution_plan(
        model_ir_content_hash=_hash("a"),
        solver_buffer_schema_version="solver-model-buffers.v1",
        solver_numeric_buffer_hash=_hash("b"),
        solver_entity_mapping_hash=_hash("c"),
        solver_artifact_hash=_hash("d"),
        load_pattern_id="HIP_PARITY_LC1",
        operator_id="linear-static-operator",
        operator_version="linear-static-operator.v1",
        operator_hash=_hash("e"),
        node_ids=tuple(f"N{index + 1}" for index in range(node_count)),
        element_ids=tuple(f"E{index + 1}" for index in range(node_count - 1)),
        node_dof_indices=np.arange(dof_count, dtype="<i4").reshape(
            node_count, 6
        ),
        global_to_free=global_to_free,
        element_global_dofs=np.asarray(
            [
                np.arange(6 * index, 6 * (index + 2), dtype="<i4")
                for index in range(node_count - 1)
            ],
            dtype="<i4",
        ),
        constrained_dofs=constrained,
        free_dofs=free,
        csr_row_ptr=np.arange(
            0,
            dof_count * dof_count + 1,
            dof_count,
            dtype="<i8",
        ),
        csr_column_indices=np.tile(
            np.arange(dof_count, dtype="<i4"),
            dof_count,
        ),
    )
    coordinates = immutable_array(
        [[2.0 * index, 0.0, 0.0] for index in range(node_count)],
        dtype="<f8",
    )
    right_hand_side = np.zeros(dof_count, dtype="<f8")
    if free_equation_count == 6:
        right_hand_side[free] = np.asarray(
            [2.0, 3.0, 4.0, 5.0, 6.0, 7.0],
            dtype="<f8",
        )
    else:
        right_hand_side[free] = 2.0 + (
            np.arange(free_equation_count, dtype="<f8") % 11.0
        )
    right_hand_side = immutable_array(right_hand_side, dtype="<f8")
    scaling = create_equation_scaling(
        execution_plan=base,
        node_coordinates_m=coordinates,
        reference_equation_load_si=right_hand_side,
    )
    plan = bind_equation_scaling_to_execution_plan(
        base,
        scaling,
        node_coordinates_m=coordinates,
        reference_equation_load_si=right_hand_side,
    )
    free_matrix = np.diag(np.full(free.size, 4.0, dtype="<f8"))
    free_matrix += np.diag(np.full(free.size - 1, -1.0, dtype="<f8"), 1)
    free_matrix += np.diag(np.full(free.size - 1, -1.0, dtype="<f8"), -1)
    global_values = np.zeros(dof_count * dof_count, dtype="<f8")
    for free_row, global_row in enumerate(free):
        for free_column, global_column in enumerate(free):
            global_values[global_row * dof_count + global_column] = free_matrix[
                free_row,
                free_column,
            ]
    global_values = immutable_array(global_values, dtype="<f8")
    reduced = create_execution_plan_reduced_csr(
        plan,
        operator_numeric_values_hash=array_data_hash(global_values),
    )
    cpu_run = run_cpu_fgmres(
        execution_plan=plan,
        scaling=scaling,
        reduced_csr=reduced,
        node_coordinates_m=coordinates,
        reference_equation_load_si=right_hand_side,
        global_csr_values_si=global_values,
        right_hand_side_si=right_hand_side,
        solution_artifact_uri=(
            "artifact://engine-v2-cpu-hip-parity/"
            f"free-{free_equation_count}/solution_free.f64le"
        ),
        max_iterations=12 if free_equation_count == 6 else 32,
        restart_length=min(free_equation_count, 32),
        relative_tolerance_scaled_l2=1.0e-12,
        absolute_tolerance_scaled_l2=1.0e-14,
        right_preconditioner_profile=CPU_FGMRES_SCALED_JACOBI_PRECONDITIONER,
    )
    inverse_diagonal = cpu_run._input_arrays[
        "right_preconditioner_inverse_diagonal"
    ]
    if cpu_run.preconditioner_profile != CPU_FGMRES_SCALED_JACOBI_PRECONDITIONER:
        raise AssertionError("HIP parity fixture preconditioner profile drifted")
    positions = reduced.array("free_csr_global_value_indices")
    reduced_values = immutable_array(global_values[positions], dtype="<f8")
    if free_equation_count == 6:
        x = [0.5, -1.0, 2.0, 0.25, -0.75, 1.5]
        y = [-2.0, 0.5, 1.25, -0.5, 2.0, -1.0]
        solution = [0.1, 0.2, -0.1, 0.4, -0.3, 0.25]
        direction = [1.0, -0.5, 0.25, 2.0, -1.0, 0.75]
    else:
        indices = np.arange(free_equation_count, dtype="<f8")
        x = ((indices % 9.0) - 4.0) / 4.0
        y = ((indices % 7.0) - 3.0) / 3.0
        solution = ((indices % 5.0) - 2.0) / 20.0
        direction = ((indices % 11.0) - 5.0) / 5.0
    fixture = HIPPrimitiveFixture(
        schema_version=HIP_PRIMITIVE_FIXTURE_VERSION,
        execution_plan_hash=plan.plan_hash,
        scaling_hash=scaling.scaling_hash,
        reduced_csr_identity_hash=reduced.identity_hash,
        operator_numeric_values_hash=reduced.operator_numeric_values_hash,
        row_ptr=immutable_array(reduced.array("free_csr_row_ptr"), dtype="<i8"),
        column_indices=immutable_array(
            reduced.array("free_csr_column_indices"),
            dtype="<i4",
        ),
        values=reduced_values,
        x=immutable_array(x, dtype="<f8"),
        y=immutable_array(y, dtype="<f8"),
        scale_divisors=immutable_array(
            cpu_run._input_arrays["free_equation_scale_divisors_si"],
            dtype="<f8",
        ),
        inverse_diagonal=inverse_diagonal,
        solution=immutable_array(solution, dtype="<f8"),
        direction=immutable_array(direction, dtype="<f8"),
        axpy_alpha=1.25,
        update_alpha=-0.4,
    )
    validate_hip_primitive_fixture(fixture)
    return EngineV2CPUHIPParityReference(
        cpu_run=cpu_run,
        fixture=fixture,
        node_coordinates_m=coordinates,
        reference_equation_load_si=right_hand_side,
    )


def validate_hip_primitive_fixture(
    fixture: HIPPrimitiveFixture,
) -> HIPPrimitiveFixture:
    if type(fixture) is not HIPPrimitiveFixture:
        _fail("hip_fixture_type_invalid", "/", "Expected HIPPrimitiveFixture.")
    if fixture.schema_version != HIP_PRIMITIVE_FIXTURE_VERSION:
        _fail("hip_fixture_schema_invalid", "/schema_version", "Unsupported fixture.")
    dimension = fixture.dimension
    if dimension <= 0 or fixture.row_ptr.shape != (dimension + 1,):
        _fail("hip_fixture_dimension_invalid", "/arrays/row_ptr", "Invalid CSR rows.")
    specs = (
        (fixture.row_ptr, "<i8", (dimension + 1,), "/arrays/row_ptr"),
        (fixture.column_indices, "<i4", (fixture.nnz,), "/arrays/column_indices"),
        (fixture.values, "<f8", (fixture.nnz,), "/arrays/values"),
        (fixture.x, "<f8", (dimension,), "/arrays/x"),
        (fixture.y, "<f8", (dimension,), "/arrays/y"),
        (
            fixture.scale_divisors,
            "<f8",
            (dimension,),
            "/arrays/scale_divisors",
        ),
        (fixture.inverse_diagonal, "<f8", (dimension,), "/arrays/inverse_diagonal"),
        (fixture.solution, "<f8", (dimension,), "/arrays/solution"),
        (fixture.direction, "<f8", (dimension,), "/arrays/direction"),
    )
    for array, dtype, shape, path in specs:
        if (
            not isinstance(array, np.ndarray)
            or array.dtype != np.dtype(dtype)
            or array.shape != shape
            or array.flags.writeable
            or not array.flags.c_contiguous
            or not np.all(np.isfinite(array))
        ):
            _fail("hip_fixture_array_invalid", path, "Array contract is invalid.")
    if (
        int(fixture.row_ptr[0]) != 0
        or int(fixture.row_ptr[-1]) != fixture.nnz
        or np.any(np.diff(fixture.row_ptr) < 0)
        or np.any(fixture.column_indices < 0)
        or np.any(fixture.column_indices >= dimension)
    ):
        _fail("hip_fixture_csr_invalid", "/arrays", "CSR structure is invalid.")
    if np.any(fixture.scale_divisors <= 0.0) or np.any(
        fixture.inverse_diagonal <= 0.0
    ):
        _fail(
            "hip_fixture_preconditioner_invalid",
            "/arrays/inverse_diagonal",
            "Scale and inverse diagonal must be positive.",
        )
    if not _operator_derived_left_scaled_jacobi_exact(
        row_ptr=fixture.row_ptr,
        columns=fixture.column_indices,
        values=fixture.values,
        scale_divisors=fixture.scale_divisors,
        inverse_diagonal=fixture.inverse_diagonal,
    ):
        _fail(
            "hip_fixture_preconditioner_binding_invalid",
            "/arrays/inverse_diagonal",
            "Jacobi bytes must equal the exact D_free^-1 A_free diagonal inverse.",
        )
    if not all(math.isfinite(value) for value in (fixture.axpy_alpha, fixture.update_alpha)):
        _fail("hip_fixture_scalar_invalid", "/", "Scalars must be finite.")
    return fixture


def _operator_derived_left_scaled_jacobi_exact(
    *,
    row_ptr: np.ndarray,
    columns: np.ndarray,
    values: np.ndarray,
    scale_divisors: np.ndarray,
    inverse_diagonal: np.ndarray,
) -> bool:
    for row in range(int(inverse_diagonal.size)):
        diagonal_positions = [
            position
            for position in range(int(row_ptr[row]), int(row_ptr[row + 1]))
            if int(columns[position]) == row
        ]
        if len(diagonal_positions) != 1:
            return False
        scaled_diagonal = (
            float(values[diagonal_positions[0]]) / float(scale_divisors[row])
        )
        if not math.isfinite(scaled_diagonal) or scaled_diagonal <= 0.0:
            return False
        if float(inverse_diagonal[row]) != 1.0 / scaled_diagonal:
            return False
    return True


def cpu_hip_primitive_reference(fixture: HIPPrimitiveFixture) -> dict[str, Any]:
    """Evaluate the primitive fixture with the CPU accumulation contract."""

    checked = validate_hip_primitive_fixture(fixture)
    row_ptr = [int(value) for value in checked.row_ptr]
    columns = [int(value) for value in checked.column_indices]
    values = [float(value) for value in checked.values]
    x = [float(value) for value in checked.x]
    y = [float(value) for value in checked.y]
    spmv = [
        math.fsum(
            values[position] * x[columns[position]]
            for position in range(row_ptr[row], row_ptr[row + 1])
        )
        for row in range(checked.dimension)
    ]
    dot = math.fsum(left * right for left, right in zip(x, y, strict=True))
    l2_norm = math.sqrt(math.fsum(value * value for value in x))
    linf_norm = max(abs(value) for value in x)
    return {
        "spmv": spmv,
        "dot": dot,
        "l2_norm": l2_norm,
        "linf_norm": linf_norm,
        "preconditioner_apply": [
            float(scale) * value
            for scale, value in zip(checked.inverse_diagonal, x, strict=True)
        ],
        "axpy": [
            checked.axpy_alpha * left + right
            for left, right in zip(x, y, strict=True)
        ],
        "solution_update": [
            float(solution) + checked.update_alpha * float(direction)
            for solution, direction in zip(
                checked.solution,
                checked.direction,
                strict=True,
            )
        ],
    }


def compare_hip_primitive_output(
    fixture: HIPPrimitiveFixture,
    payload: Any,
    *,
    absolute_tolerance: float = HIP_PRIMITIVE_ABSOLUTE_TOLERANCE,
    relative_tolerance: float = HIP_PRIMITIVE_RELATIVE_TOLERANCE,
) -> dict[str, Any]:
    """Validate actual HIP telemetry and compare every operation to CPU truth."""

    checked = validate_hip_primitive_fixture(fixture)
    if not isinstance(payload, dict):
        _fail("hip_output_type_invalid", "/", "Expected a JSON object.")
    required_metadata = {
        "schema_version": HIP_PRIMITIVE_OUTPUT_VERSION,
        "runtime_status": "success",
        "backend": "amd_rocm_hip",
        "cpu_backend": False,
        "same_stream_ordering": True,
        "production_full_recurrence_claim": False,
        "preconditioner_profile": (
            CPU_FGMRES_SCALED_JACOBI_PRECONDITIONER
        ),
    }
    for key, expected in required_metadata.items():
        if payload.get(key) != expected:
            _fail(
                "hip_output_runtime_contract_invalid",
                f"/{key}",
                f"Expected {expected!r}.",
            )
    if payload.get("runtime_status_code") != 0:
        _fail("hip_output_status_invalid", "/runtime_status_code", "HIP status failed.")
    if payload.get("fixture_dimension") != checked.dimension or payload.get(
        "fixture_nnz"
    ) != checked.nnz:
        _fail("hip_output_fixture_mismatch", "/", "Fixture dimensions are stale.")
    if not isinstance(payload.get("device_name"), str) or not payload["device_name"]:
        _fail("hip_output_device_missing", "/device_name", "Device name is required.")
    architecture = payload.get("gcn_arch_name")
    if not isinstance(architecture, str) or not architecture.startswith("gfx"):
        _fail("hip_output_arch_invalid", "/gcn_arch_name", "AMD gfx target required.")
    invocation_count = payload.get("kernel_invocation_count")
    if type(invocation_count) is not int or invocation_count < (
        HIP_PRIMITIVE_REQUIRED_KERNEL_INVOCATIONS
    ):
        _fail(
            "hip_output_kernel_count_invalid",
            "/kernel_invocation_count",
            "All primitive kernels must execute.",
        )
    if payload.get("blocking_d2h_synchronization_count") != 1:
        _fail(
            "hip_output_sync_contract_invalid",
            "/blocking_d2h_synchronization_count",
            "The primitive probe must synchronize D2H once.",
        )
    operations = payload.get("operations")
    if not isinstance(operations, dict) or set(operations) != set(
        HIP_PRIMITIVE_OPERATION_ORDER
    ):
        _fail(
            "hip_output_operation_set_invalid",
            "/operations",
            "Primitive operation set is invalid.",
        )
    absolute = _nonnegative_finite(absolute_tolerance, "/absolute_tolerance")
    relative = _nonnegative_finite(relative_tolerance, "/relative_tolerance")
    if absolute == 0.0 and relative == 0.0:
        _fail("hip_output_tolerance_invalid", "/", "A tolerance must be positive.")
    reference = cpu_hip_primitive_reference(checked)
    rows = []
    for operation in HIP_PRIMITIVE_OPERATION_ORDER:
        reference_value = reference[operation]
        actual_value = operations[operation]
        row = _comparison_row(
            operation,
            reference_value,
            actual_value,
            dimension=checked.dimension,
            absolute_tolerance=absolute,
            relative_tolerance=relative,
        )
        rows.append(row)
    contract_pass = all(row["contract_pass"] for row in rows)
    return {
        "schema_version": HIP_PRIMITIVE_PARITY_PROFILE,
        "fixture_hash": checked.fixture_hash,
        "device_name": payload["device_name"],
        "gcn_arch_name": architecture,
        "runtime_status_propagation_pass": True,
        "same_stream_ordering_pass": True,
        "cpu_fallback_absent": True,
        "absolute_tolerance": absolute,
        "relative_tolerance": relative,
        "operation_rows": rows,
        "maximum_absolute_error": max(row["maximum_absolute_error"] for row in rows),
        "maximum_relative_error": max(row["maximum_relative_error"] for row in rows),
        "contract_pass": contract_pass,
        "operator_derived_scaled_jacobi_apply_probe_claim": contract_pass,
        "full_recurrence_parity_claim": False,
        "performance_claim": False,
    }


def _comparison_row(
    operation: str,
    reference: Any,
    actual: Any,
    *,
    dimension: int,
    absolute_tolerance: float,
    relative_tolerance: float,
) -> dict[str, Any]:
    vector_operations = {
        "spmv",
        "preconditioner_apply",
        "axpy",
        "solution_update",
    }
    if operation in vector_operations:
        reference_values = _finite_vector(reference, dimension, f"/{operation}/reference")
        actual_values = _finite_vector(actual, dimension, f"/{operation}/actual")
    else:
        reference_values = [_finite_number(reference, f"/{operation}/reference")]
        actual_values = [_finite_number(actual, f"/{operation}/actual")]
    absolute_errors = [
        abs(actual_value - reference_value)
        for reference_value, actual_value in zip(
            reference_values,
            actual_values,
            strict=True,
        )
    ]
    allowed = [
        max(absolute_tolerance, relative_tolerance * abs(reference_value))
        for reference_value in reference_values
    ]
    relative_errors = [
        error / max(abs(reference_value), absolute_tolerance)
        for error, reference_value in zip(
            absolute_errors,
            reference_values,
            strict=True,
        )
    ]
    return {
        "operation": operation,
        "component_count": len(reference_values),
        "maximum_absolute_error": max(absolute_errors, default=0.0),
        "maximum_relative_error": max(relative_errors, default=0.0),
        "maximum_allowed_error": max(allowed, default=absolute_tolerance),
        "contract_pass": all(
            error <= limit
            for error, limit in zip(absolute_errors, allowed, strict=True)
        ),
    }


def _finite_vector(value: Any, length: int, path: str) -> list[float]:
    if not isinstance(value, list) or len(value) != length:
        _fail("hip_output_vector_invalid", path, "Vector length is invalid.")
    return [_finite_number(item, f"{path}/{index}") for index, item in enumerate(value)]


def _finite_number(value: Any, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail("hip_output_number_invalid", path, "Finite number required.")
    result = float(value)
    if not math.isfinite(result):
        _fail("hip_output_number_invalid", path, "Finite number required.")
    return result


def _nonnegative_finite(value: Any, path: str) -> float:
    result = _finite_number(value, path)
    if result < 0.0:
        _fail("hip_output_tolerance_invalid", path, "Tolerance must be nonnegative.")
    return result


def parity_receipt_hash(payload: dict[str, Any]) -> str:
    """Hash a receipt payload after excluding its claimed receipt hash."""

    return canonical_hash(
        {key: value for key, value in payload.items() if key != "receipt_hash"}
    )
