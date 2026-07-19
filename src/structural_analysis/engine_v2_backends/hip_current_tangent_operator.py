"""HIP fixture and parity contract for the current-tangent operator.

The fixture serializes the backend-neutral current-tangent parent arrays, one
state/direction pair, and deterministic free-row incidence schedules.  The
device-order CPU evaluator mirrors the one-thread-per-free-row HIP algorithm.
Actual HIP execution and numerical parity remain separate receipt gates.
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
    has_immutable_bytes_backing,
    immutable_array,
    sha256_prefixed,
)
from structural_analysis.engine_v2.contracts.current_tangent_operator import (
    CurrentTangentOperatorContract,
    create_current_tangent_operator,
    validate_current_tangent_operator,
)


HIP_CURRENT_TANGENT_FIXTURE_VERSION = (
    "engine-v2-hip-current-tangent-operator-fixture.v1"
)
HIP_CURRENT_TANGENT_OUTPUT_VERSION = (
    "engine-v2-hip-current-tangent-operator-output.v1"
)
HIP_CURRENT_TANGENT_FIXTURE_VALIDATION_OUTPUT_VERSION = (
    "engine-v2-hip-current-tangent-fixture-validation-output.v1"
)
HIP_CURRENT_TANGENT_FIXTURE_VALIDATION_PROFILE = (
    "engine-v2-hip-current-tangent-host-fixture-parser.v1"
)
HIP_CURRENT_TANGENT_PARITY_PROFILE = (
    "engine-v2-cpu-hip-current-tangent-operator-parity.v1"
)
HIP_CURRENT_TANGENT_SCHEDULE_PROFILE = (
    "free_row_sorted_element_local_incidence.v1"
)
HIP_CURRENT_TANGENT_EXECUTION_PROFILE = (
    "one_thread_per_free_row_reference_frame_geometry.v1"
)
HIP_CURRENT_TANGENT_ACCUMULATION_PROFILE = (
    "reference_then_sorted_frame_then_sorted_geometry_sequential_fp64.v1"
)
HIP_CURRENT_TANGENT_BINARY_MAGIC = b"EV2CTO01"
HIP_CURRENT_TANGENT_ABSOLUTE_TOLERANCE_N_PER_M = 1.0e-6
HIP_CURRENT_TANGENT_RELATIVE_TOLERANCE = 1.0e-11
HIP_CURRENT_TANGENT_HEADER = struct.Struct("<8sQQQQQQQd")

_PARENT_ARRAY_NAMES = (
    "reference_row_pointer",
    "reference_column_indices",
    "reference_values_n_per_m",
    "free_global_dofs",
    "background_global_displacements_m",
    "frame_dofs",
    "frame_stiffness_delta_n_per_m",
    "geometry_dofs",
    "geometry_relative_translation_operators",
    "geometry_reference_chords_m",
    "geometry_reference_lengths_m",
    "geometry_axial_stiffness_n_per_m",
)


class HIPCurrentTangentOperatorError(ValueError):
    """Fail-closed fixture or runtime-output validation error."""

    def __init__(self, code: str, path: str, message: str) -> None:
        self.code = code
        self.path = path
        self.message = message
        super().__init__(f"{code}@{path}: {message}")


def _fail(code: str, path: str, message: str) -> None:
    raise HIPCurrentTangentOperatorError(code, path, message)


@dataclass(frozen=True)
class HIPCurrentTangentOperatorFixture:
    """Canonical operator parents, input vectors, and HIP row schedules."""

    schema_version: str
    operator: CurrentTangentOperatorContract
    free_displacements_m: np.ndarray
    free_direction_m: np.ndarray
    load_factor: float
    global_to_free: np.ndarray
    frame_incidence_pointer: np.ndarray
    frame_incidence_element: np.ndarray
    frame_incidence_local_dof: np.ndarray
    geometry_incidence_pointer: np.ndarray
    geometry_incidence_element: np.ndarray
    geometry_incidence_local_dof: np.ndarray
    schedule_contract_hash: str

    @property
    def equation_count(self) -> int:
        return self.operator.equation_count

    @property
    def global_dof_count(self) -> int:
        return self.operator.global_dof_count

    @property
    def frame_incidence_count(self) -> int:
        return int(self.frame_incidence_element.size)

    @property
    def geometry_incidence_count(self) -> int:
        return int(self.geometry_incidence_element.size)

    @property
    def expected_kernel_invocation_count(self) -> int:
        return 1

    def to_bytes(self) -> bytes:
        validate_hip_current_tangent_operator_fixture(self)
        header = HIP_CURRENT_TANGENT_HEADER.pack(
            HIP_CURRENT_TANGENT_BINARY_MAGIC,
            self.equation_count,
            self.global_dof_count,
            self.operator.reference_nnz,
            self.operator.frame_element_count,
            self.operator.geometry_element_count,
            self.frame_incidence_count,
            self.geometry_incidence_count,
            self.load_factor,
        )
        return b"".join(
            [header]
            + [
                array.tobytes(order="C")
                for array in _fixture_arrays(self).values()
            ]
        )

    @property
    def fixture_hash(self) -> str:
        return sha256_prefixed(self.to_bytes())

    @property
    def execution_contract_hash(self) -> str:
        return canonical_hash(
            {
                "parity_profile": HIP_CURRENT_TANGENT_PARITY_PROFILE,
                "operator_contract_hash": self.operator.contract_hash,
                "schedule_contract_hash": self.schedule_contract_hash,
                "fixture_hash": self.fixture_hash,
                "execution_profile": HIP_CURRENT_TANGENT_EXECUTION_PROFILE,
                "accumulation_profile": (
                    HIP_CURRENT_TANGENT_ACCUMULATION_PROFILE
                ),
            }
        )

    def to_manifest(self) -> dict[str, Any]:
        validate_hip_current_tangent_operator_fixture(self)
        arrays = _fixture_arrays(self)
        return {
            "schema_version": self.schema_version,
            "fixture_hash": self.fixture_hash,
            "parity_profile": HIP_CURRENT_TANGENT_PARITY_PROFILE,
            "schedule_profile": HIP_CURRENT_TANGENT_SCHEDULE_PROFILE,
            "execution_profile": HIP_CURRENT_TANGENT_EXECUTION_PROFILE,
            "accumulation_profile": (
                HIP_CURRENT_TANGENT_ACCUMULATION_PROFILE
            ),
            "operator_contract_hash": self.operator.contract_hash,
            "schedule_contract_hash": self.schedule_contract_hash,
            "execution_contract_hash": self.execution_contract_hash,
            "load_factor": self.load_factor,
            "dimensions": {
                "equation_count": self.equation_count,
                "global_dof_count": self.global_dof_count,
                "reference_nnz": self.operator.reference_nnz,
                "frame_element_count": self.operator.frame_element_count,
                "geometry_element_count": self.operator.geometry_element_count,
                "frame_incidence_count": self.frame_incidence_count,
                "geometry_incidence_count": self.geometry_incidence_count,
            },
            "expected_kernel_invocation_count": (
                self.expected_kernel_invocation_count
            ),
            "binary_profile": "canonical_little_endian_mixed_numeric.v1",
            "fixture_byte_length": len(self.to_bytes()),
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
                "This fixture binds one backend-neutral current-tangent "
                "operator, deterministic derived row-incidence schedules, "
                "and one state/direction pair. Actual HIP execution, CPU/HIP "
                "numerical parity, actual-MGT scale, performance, and G1 "
                "closure require separate device evidence."
            ),
        }


@dataclass(frozen=True)
class HIPCurrentTangentOperatorReference:
    """Canonical NumPy and device-order CPU actions for one fixture."""

    fixture: HIPCurrentTangentOperatorFixture
    canonical_action_n_per_m: np.ndarray
    device_order_action_n_per_m: np.ndarray


def create_hip_current_tangent_operator_fixture(
    operator: CurrentTangentOperatorContract,
    *,
    free_displacements_m: Any,
    load_factor: float,
    free_direction_m: Any,
) -> HIPCurrentTangentOperatorFixture:
    """Create deterministic row schedules for one current-tangent action."""

    validated = validate_current_tangent_operator(operator)
    state = _finite_vector(
        free_displacements_m,
        dimension=validated.equation_count,
        path="/free_displacements_m",
    )
    direction = _finite_vector(
        free_direction_m,
        dimension=validated.equation_count,
        path="/free_direction_m",
    )
    try:
        factor = float(load_factor)
    except (TypeError, ValueError):
        _fail(
            "hip_current_tangent_load_factor_invalid",
            "/load_factor",
            "Load factor must be finite.",
        )
    if not math.isfinite(factor):
        _fail(
            "hip_current_tangent_load_factor_invalid",
            "/load_factor",
            "Load factor must be finite.",
        )

    global_to_free = np.full(
        validated.global_dof_count,
        -1,
        dtype=np.int64,
    )
    free = validated.array("free_global_dofs")
    global_to_free[free] = np.arange(validated.equation_count, dtype=np.int64)
    global_to_free = immutable_array(global_to_free, dtype="<i8")
    frame_pointer, frame_element, frame_local = _derive_incidence_schedule(
        validated.array("frame_dofs"),
        global_to_free=global_to_free,
        equation_count=validated.equation_count,
    )
    geometry_pointer, geometry_element, geometry_local = (
        _derive_incidence_schedule(
            validated.array("geometry_dofs"),
            global_to_free=global_to_free,
            equation_count=validated.equation_count,
        )
    )
    schedule_hash = _schedule_contract_hash(
        operator=validated,
        global_to_free=global_to_free,
        frame_incidence_pointer=frame_pointer,
        frame_incidence_element=frame_element,
        frame_incidence_local_dof=frame_local,
        geometry_incidence_pointer=geometry_pointer,
        geometry_incidence_element=geometry_element,
        geometry_incidence_local_dof=geometry_local,
    )
    fixture = HIPCurrentTangentOperatorFixture(
        schema_version=HIP_CURRENT_TANGENT_FIXTURE_VERSION,
        operator=validated,
        free_displacements_m=state,
        free_direction_m=direction,
        load_factor=factor,
        global_to_free=global_to_free,
        frame_incidence_pointer=frame_pointer,
        frame_incidence_element=frame_element,
        frame_incidence_local_dof=frame_local,
        geometry_incidence_pointer=geometry_pointer,
        geometry_incidence_element=geometry_element,
        geometry_incidence_local_dof=geometry_local,
        schedule_contract_hash=schedule_hash,
    )
    return validate_hip_current_tangent_operator_fixture(fixture)


def validate_hip_current_tangent_operator_fixture(
    fixture: HIPCurrentTangentOperatorFixture,
) -> HIPCurrentTangentOperatorFixture:
    """Fail closed on stale schedules, mutable arrays, or invalid inputs."""

    if type(fixture) is not HIPCurrentTangentOperatorFixture:
        _fail(
            "hip_current_tangent_fixture_type_invalid",
            "/",
            "Expected HIPCurrentTangentOperatorFixture.",
        )
    if fixture.schema_version != HIP_CURRENT_TANGENT_FIXTURE_VERSION:
        _fail(
            "hip_current_tangent_fixture_version_invalid",
            "/schema_version",
            "Fixture schema version is invalid.",
        )
    operator = validate_current_tangent_operator(fixture.operator)
    if not math.isfinite(fixture.load_factor):
        _fail(
            "hip_current_tangent_load_factor_invalid",
            "/load_factor",
            "Load factor must be finite.",
        )
    _validate_fixture_array(
        fixture.free_displacements_m,
        dtype="<f8",
        shape=(operator.equation_count,),
        path="/free_displacements_m",
    )
    _validate_fixture_array(
        fixture.free_direction_m,
        dtype="<f8",
        shape=(operator.equation_count,),
        path="/free_direction_m",
    )
    expected_global_to_free = np.full(
        operator.global_dof_count,
        -1,
        dtype=np.int64,
    )
    expected_global_to_free[operator.array("free_global_dofs")] = np.arange(
        operator.equation_count,
        dtype=np.int64,
    )
    _validate_fixture_array(
        fixture.global_to_free,
        dtype="<i8",
        shape=(operator.global_dof_count,),
        path="/global_to_free",
    )
    if not np.array_equal(fixture.global_to_free, expected_global_to_free):
        _fail(
            "hip_current_tangent_global_to_free_invalid",
            "/global_to_free",
            "Global-to-free map does not match the operator equation order.",
        )

    expected_frame = _derive_incidence_schedule(
        operator.array("frame_dofs"),
        global_to_free=fixture.global_to_free,
        equation_count=operator.equation_count,
    )
    expected_geometry = _derive_incidence_schedule(
        operator.array("geometry_dofs"),
        global_to_free=fixture.global_to_free,
        equation_count=operator.equation_count,
    )
    actual_schedules = (
        fixture.frame_incidence_pointer,
        fixture.frame_incidence_element,
        fixture.frame_incidence_local_dof,
        fixture.geometry_incidence_pointer,
        fixture.geometry_incidence_element,
        fixture.geometry_incidence_local_dof,
    )
    expected_schedules = (*expected_frame, *expected_geometry)
    schedule_paths = (
        "/frame_incidence_pointer",
        "/frame_incidence_element",
        "/frame_incidence_local_dof",
        "/geometry_incidence_pointer",
        "/geometry_incidence_element",
        "/geometry_incidence_local_dof",
    )
    for array, expected, path in zip(
        actual_schedules,
        expected_schedules,
        schedule_paths,
        strict=True,
    ):
        _validate_fixture_array(
            array,
            dtype="<i8",
            shape=expected.shape,
            path=path,
        )
        if not np.array_equal(array, expected):
            _fail(
                "hip_current_tangent_schedule_invalid",
                path,
                "Incidence schedule does not match the operator DOFs.",
            )
    expected_hash = _schedule_contract_hash(
        operator=operator,
        global_to_free=fixture.global_to_free,
        frame_incidence_pointer=fixture.frame_incidence_pointer,
        frame_incidence_element=fixture.frame_incidence_element,
        frame_incidence_local_dof=fixture.frame_incidence_local_dof,
        geometry_incidence_pointer=fixture.geometry_incidence_pointer,
        geometry_incidence_element=fixture.geometry_incidence_element,
        geometry_incidence_local_dof=fixture.geometry_incidence_local_dof,
    )
    if fixture.schedule_contract_hash != expected_hash:
        _fail(
            "hip_current_tangent_schedule_hash_mismatch",
            "/schedule_contract_hash",
            "Schedule contract hash is stale.",
        )
    operator.apply_n_per_m(
        fixture.free_displacements_m,
        fixture.load_factor,
        fixture.free_direction_m,
    )
    return fixture


def build_hip_current_tangent_operator_reference(
) -> HIPCurrentTangentOperatorReference:
    """Build the nontrivial deterministic fixture and both CPU references."""

    operator = _synthetic_operator()
    fixture = create_hip_current_tangent_operator_fixture(
        operator,
        free_displacements_m=np.array(
            [0.0012, -0.0007, 0.0004, 0.0021, -0.0013],
            dtype=np.float64,
        ),
        load_factor=0.73,
        free_direction_m=np.array(
            [0.75, -0.5, 0.375, -0.625, 0.25],
            dtype=np.float64,
        ),
    )
    return create_hip_current_tangent_operator_reference(fixture)


def create_hip_current_tangent_operator_reference(
    fixture: HIPCurrentTangentOperatorFixture,
) -> HIPCurrentTangentOperatorReference:
    """Build canonical and device-order CPU actions for any valid fixture."""

    validated = validate_hip_current_tangent_operator_fixture(fixture)
    canonical = immutable_array(
        validated.operator.apply_n_per_m(
            validated.free_displacements_m,
            validated.load_factor,
            validated.free_direction_m,
        ),
        dtype="<f8",
    )
    device_order = immutable_array(
        _device_order_action(validated),
        dtype="<f8",
    )
    return HIPCurrentTangentOperatorReference(
        fixture=validated,
        canonical_action_n_per_m=canonical,
        device_order_action_n_per_m=device_order,
    )


def compare_hip_current_tangent_operator_output(
    reference: HIPCurrentTangentOperatorReference,
    runtime_output: Any,
) -> dict[str, Any]:
    """Validate one actual HIP action against canonical and device-order CPU."""

    if type(reference) is not HIPCurrentTangentOperatorReference:
        _fail(
            "hip_current_tangent_reference_invalid",
            "/",
            "Expected HIPCurrentTangentOperatorReference.",
        )
    fixture = validate_hip_current_tangent_operator_fixture(reference.fixture)
    if not isinstance(runtime_output, dict):
        _fail(
            "hip_current_tangent_output_type_invalid",
            "/",
            "Expected object.",
        )
    required = {
        "schema_version",
        "status",
        "cpu_backend",
        "device_name",
        "gcn_arch_name",
        "execution_profile",
        "accumulation_profile",
        "equation_count",
        "kernel_invocation_count",
        "mid_action_d2h_transfer_count",
        "blocking_d2h_synchronization_count",
        "action_n_per_m",
    }
    if set(runtime_output) != required:
        _fail(
            "hip_current_tangent_output_fields_invalid",
            "/",
            "Runtime output fields are not exact.",
        )
    expected = {
        "schema_version": HIP_CURRENT_TANGENT_OUTPUT_VERSION,
        "status": "ok",
        "cpu_backend": False,
        "execution_profile": HIP_CURRENT_TANGENT_EXECUTION_PROFILE,
        "accumulation_profile": HIP_CURRENT_TANGENT_ACCUMULATION_PROFILE,
        "equation_count": fixture.equation_count,
        "kernel_invocation_count": fixture.expected_kernel_invocation_count,
        "mid_action_d2h_transfer_count": 0,
        "blocking_d2h_synchronization_count": 1,
    }
    for name, value in expected.items():
        if runtime_output[name] != value:
            _fail(
                "hip_current_tangent_output_semantics_invalid",
                f"/{name}",
                "Runtime metadata does not match the fixture contract.",
            )
    for name in ("device_name", "gcn_arch_name"):
        if not isinstance(runtime_output[name], str) or not runtime_output[
            name
        ].strip():
            _fail(
                "hip_current_tangent_device_identity_invalid",
                f"/{name}",
                "Device identity is required.",
            )
    action = _finite_vector(
        runtime_output["action_n_per_m"],
        dimension=fixture.equation_count,
        path="/action_n_per_m",
    )
    canonical_error = np.abs(action - reference.canonical_action_n_per_m)
    device_error = np.abs(action - reference.device_order_action_n_per_m)
    canonical_max_abs = float(np.max(canonical_error, initial=0.0))
    device_max_abs = float(np.max(device_error, initial=0.0))
    scale = max(
        float(
            np.max(
                np.abs(reference.canonical_action_n_per_m),
                initial=0.0,
            )
        ),
        1.0,
    )
    tolerance = max(
        HIP_CURRENT_TANGENT_ABSOLUTE_TOLERANCE_N_PER_M,
        HIP_CURRENT_TANGENT_RELATIVE_TOLERANCE * scale,
    )
    return {
        "profile": HIP_CURRENT_TANGENT_PARITY_PROFILE,
        "contract_pass": bool(
            canonical_max_abs <= tolerance and device_max_abs <= tolerance
        ),
        "canonical_cpu_max_abs_error_n_per_m": canonical_max_abs,
        "device_order_cpu_max_abs_error_n_per_m": device_max_abs,
        "comparison_tolerance_n_per_m": tolerance,
        "action_data_hash": array_data_hash(action),
        "canonical_action_data_hash": array_data_hash(
            reference.canonical_action_n_per_m
        ),
        "device_order_action_data_hash": array_data_hash(
            reference.device_order_action_n_per_m
        ),
        "actual_hardware_execution_required_for_claim": True,
        "actual_mgt_scale_claim": False,
        "production_performance_claim": False,
    }


def validate_hip_current_tangent_fixture_parser_output(
    fixture: HIPCurrentTangentOperatorFixture,
    runtime_output: Any,
) -> dict[str, Any]:
    """Validate the same HIP binary's host-only fixture-parser output."""

    validated = validate_hip_current_tangent_operator_fixture(fixture)
    if not isinstance(runtime_output, dict):
        _fail(
            "hip_current_tangent_parser_output_type_invalid",
            "/",
            "Expected object.",
        )
    required = {
        "schema_version",
        "status",
        "mode",
        "actual_hardware",
        "hip_runtime_api_call_count",
        "equation_count",
        "global_dof_count",
        "reference_nnz",
        "frame_element_count",
        "geometry_element_count",
        "frame_incidence_count",
        "geometry_incidence_count",
        "expected_kernel_invocation_count",
        "fixture_byte_length",
    }
    if set(runtime_output) != required:
        _fail(
            "hip_current_tangent_parser_output_fields_invalid",
            "/",
            "Fixture-parser output fields are not exact.",
        )
    expected = {
        "schema_version": (
            HIP_CURRENT_TANGENT_FIXTURE_VALIDATION_OUTPUT_VERSION
        ),
        "status": "ok",
        "mode": "host_fixture_validation_only",
        "actual_hardware": False,
        "hip_runtime_api_call_count": 0,
        "equation_count": validated.equation_count,
        "global_dof_count": validated.global_dof_count,
        "reference_nnz": validated.operator.reference_nnz,
        "frame_element_count": validated.operator.frame_element_count,
        "geometry_element_count": validated.operator.geometry_element_count,
        "frame_incidence_count": validated.frame_incidence_count,
        "geometry_incidence_count": validated.geometry_incidence_count,
        "expected_kernel_invocation_count": (
            validated.expected_kernel_invocation_count
        ),
        "fixture_byte_length": len(validated.to_bytes()),
    }
    if runtime_output != expected:
        _fail(
            "hip_current_tangent_parser_output_semantics_invalid",
            "/",
            "Fixture-parser metadata does not match the canonical fixture.",
        )
    return {
        "profile": HIP_CURRENT_TANGENT_FIXTURE_VALIDATION_PROFILE,
        "contract_pass": True,
        "fixture_hash": validated.fixture_hash,
        "runtime_output_hash": canonical_hash(runtime_output),
        "equation_count": validated.equation_count,
        "fixture_byte_length": expected["fixture_byte_length"],
        "actual_hardware_execution": False,
        "hip_runtime_api_call_count": 0,
    }


def _derive_incidence_schedule(
    dofs: np.ndarray,
    *,
    global_to_free: np.ndarray,
    equation_count: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    rows: list[list[tuple[int, int]]] = [
        [] for _index in range(equation_count)
    ]
    for element in range(int(dofs.shape[0])):
        for local_dof in range(int(dofs.shape[1])):
            free_row = int(global_to_free[int(dofs[element, local_dof])])
            if free_row >= 0:
                rows[free_row].append((element, local_dof))
    pointer = [0]
    elements: list[int] = []
    locals_: list[int] = []
    for entries in rows:
        entries.sort()
        elements.extend(element for element, _local in entries)
        locals_.extend(local for _element, local in entries)
        pointer.append(len(elements))
    return (
        immutable_array(pointer, dtype="<i8"),
        immutable_array(elements, dtype="<i8"),
        immutable_array(locals_, dtype="<i8"),
    )


def _schedule_contract_hash(
    *,
    operator: CurrentTangentOperatorContract,
    global_to_free: np.ndarray,
    frame_incidence_pointer: np.ndarray,
    frame_incidence_element: np.ndarray,
    frame_incidence_local_dof: np.ndarray,
    geometry_incidence_pointer: np.ndarray,
    geometry_incidence_element: np.ndarray,
    geometry_incidence_local_dof: np.ndarray,
) -> str:
    arrays = {
        "global_to_free": global_to_free,
        "frame_incidence_pointer": frame_incidence_pointer,
        "frame_incidence_element": frame_incidence_element,
        "frame_incidence_local_dof": frame_incidence_local_dof,
        "geometry_incidence_pointer": geometry_incidence_pointer,
        "geometry_incidence_element": geometry_incidence_element,
        "geometry_incidence_local_dof": geometry_incidence_local_dof,
    }
    return canonical_hash(
        {
            "profile": HIP_CURRENT_TANGENT_SCHEDULE_PROFILE,
            "operator_contract_hash": operator.contract_hash,
            "arrays": {
                name: {
                    "dtype": array.dtype.str,
                    "shape": [int(value) for value in array.shape],
                    "data_hash": array_data_hash(array),
                }
                for name, array in arrays.items()
            },
        }
    )


def _device_order_action(
    fixture: HIPCurrentTangentOperatorFixture,
) -> np.ndarray:
    operator = fixture.operator
    state_global = np.array(
        operator.array("background_global_displacements_m"),
        dtype=np.float64,
        copy=True,
    )
    direction_global = np.zeros(operator.global_dof_count, dtype=np.float64)
    free = operator.array("free_global_dofs")
    state_global[free] = fixture.free_displacements_m
    direction_global[free] = fixture.free_direction_m
    row_pointer = operator.array("reference_row_pointer")
    columns = operator.array("reference_column_indices")
    values = operator.array("reference_values_n_per_m")
    frame_dofs = operator.array("frame_dofs")
    frame_delta = operator.array("frame_stiffness_delta_n_per_m")
    result = np.empty(operator.equation_count, dtype=np.float64)
    for row in range(operator.equation_count):
        total = 0.0
        for position in range(
            int(row_pointer[row]),
            int(row_pointer[row + 1]),
        ):
            total = total + float(values[position]) * float(
                fixture.free_direction_m[int(columns[position])]
            )
        for position in range(
            int(fixture.frame_incidence_pointer[row]),
            int(fixture.frame_incidence_pointer[row + 1]),
        ):
            element = int(fixture.frame_incidence_element[position])
            local_dof = int(fixture.frame_incidence_local_dof[position])
            element_action = 0.0
            for column in range(12):
                element_action = element_action + float(
                    frame_delta[element, local_dof, column]
                ) * float(
                    direction_global[int(frame_dofs[element, column])]
                )
            total = total + fixture.load_factor * element_action
        for position in range(
            int(fixture.geometry_incidence_pointer[row]),
            int(fixture.geometry_incidence_pointer[row + 1]),
        ):
            total = total + _geometry_local_action(
                operator=operator,
                state_global=state_global,
                direction_global=direction_global,
                element=int(fixture.geometry_incidence_element[position]),
                local_dof=int(
                    fixture.geometry_incidence_local_dof[position]
                ),
            )
        result[row] = total
    return result


def _geometry_local_action(
    *,
    operator: CurrentTangentOperatorContract,
    state_global: np.ndarray,
    direction_global: np.ndarray,
    element: int,
    local_dof: int,
) -> float:
    dofs = operator.array("geometry_dofs")
    relative = operator.array("geometry_relative_translation_operators")
    reference_chords = operator.array("geometry_reference_chords_m")
    reference_length = float(
        operator.array("geometry_reference_lengths_m")[element]
    )
    axial = float(operator.array("geometry_axial_stiffness_n_per_m")[element])
    relative_translation = [0.0, 0.0, 0.0]
    relative_direction = [0.0, 0.0, 0.0]
    for axis in range(3):
        state_sum = 0.0
        direction_sum = 0.0
        for local in range(12):
            coefficient = float(relative[element, axis, local])
            global_dof = int(dofs[element, local])
            state_sum = state_sum + coefficient * float(
                state_global[global_dof]
            )
            direction_sum = direction_sum + coefficient * float(
                direction_global[global_dof]
            )
        relative_translation[axis] = state_sum
        relative_direction[axis] = direction_sum
    current_chord = [
        float(reference_chords[element, axis])
        + relative_translation[axis]
        for axis in range(3)
    ]
    length_squared = 0.0
    for axis in range(3):
        length_squared = (
            length_squared + current_chord[axis] * current_chord[axis]
        )
    current_length = math.sqrt(length_squared)
    if current_length <= 1.0e-12:
        _fail(
            "hip_current_tangent_geometry_chord_collapsed",
            f"/apply/geometry/{element}",
            "Finite-chord axial element collapsed.",
        )
    current_direction = [
        current_chord[axis] / current_length for axis in range(3)
    ]
    reference_direction = [
        float(reference_chords[element, axis]) / reference_length
        for axis in range(3)
    ]
    linear_extension = 0.0
    relative_squared = 0.0
    current_projection = 0.0
    projection_delta = 0.0
    direction_delta = [
        current_direction[axis] - reference_direction[axis]
        for axis in range(3)
    ]
    for axis in range(3):
        linear_extension = (
            linear_extension
            + reference_direction[axis] * relative_translation[axis]
        )
        relative_squared = (
            relative_squared
            + relative_translation[axis] * relative_translation[axis]
        )
        current_projection = (
            current_projection
            + current_direction[axis] * relative_direction[axis]
        )
        projection_delta = (
            projection_delta
            + direction_delta[axis] * relative_direction[axis]
        )
    extension = (
        2.0 * reference_length * linear_extension + relative_squared
    ) / (current_length + reference_length)
    end_action = [0.0, 0.0, 0.0]
    geometric_scale = axial * extension / current_length
    for axis in range(3):
        material = axial * (
            projection_delta * reference_direction[axis]
            + current_projection * direction_delta[axis]
        )
        geometric = geometric_scale * (
            relative_direction[axis]
            - current_projection * current_direction[axis]
        )
        end_action[axis] = material + geometric
    nodal_action = 0.0
    for axis in range(3):
        nodal_action = nodal_action + float(
            relative[element, axis, local_dof]
        ) * end_action[axis]
    return nodal_action


def _fixture_arrays(
    fixture: HIPCurrentTangentOperatorFixture,
) -> dict[str, np.ndarray]:
    arrays = {
        name: fixture.operator.array(name) for name in _PARENT_ARRAY_NAMES
    }
    arrays.update(
        {
            "global_to_free": fixture.global_to_free,
            "frame_incidence_pointer": fixture.frame_incidence_pointer,
            "frame_incidence_element": fixture.frame_incidence_element,
            "frame_incidence_local_dof": fixture.frame_incidence_local_dof,
            "geometry_incidence_pointer": fixture.geometry_incidence_pointer,
            "geometry_incidence_element": fixture.geometry_incidence_element,
            "geometry_incidence_local_dof": (
                fixture.geometry_incidence_local_dof
            ),
            "free_displacements_m": fixture.free_displacements_m,
            "free_direction_m": fixture.free_direction_m,
        }
    )
    return arrays


def _finite_vector(values: Any, *, dimension: int, path: str) -> np.ndarray:
    try:
        array = np.asarray(values, dtype=np.float64)
    except (TypeError, ValueError):
        _fail(
            "hip_current_tangent_vector_invalid",
            path,
            f"Expected a finite FP64 vector of length {dimension}.",
        )
    if array.shape != (dimension,) or not np.all(np.isfinite(array)):
        _fail(
            "hip_current_tangent_vector_invalid",
            path,
            f"Expected a finite FP64 vector of length {dimension}.",
        )
    return immutable_array(array, dtype="<f8")


def _validate_fixture_array(
    array: Any,
    *,
    dtype: str,
    shape: tuple[int, ...],
    path: str,
) -> None:
    if (
        type(array) is not np.ndarray
        or array.dtype.str != dtype
        or array.shape != shape
        or not array.flags.c_contiguous
        or array.flags.writeable
        or not has_immutable_bytes_backing(array)
    ):
        _fail(
            "hip_current_tangent_array_invalid",
            path,
            "Array must have canonical immutable little-endian bytes.",
        )
    if array.dtype.kind == "f" and not np.all(np.isfinite(array)):
        _fail(
            "hip_current_tangent_array_nonfinite",
            path,
            "Array contains a non-finite value.",
        )


def _synthetic_operator() -> CurrentTangentOperatorContract:
    row_pointer = np.array([0, 3, 6, 9, 12, 15], dtype=np.int64)
    columns = np.array(
        [0, 1, 3, 0, 1, 2, 1, 2, 4, 0, 3, 4, 2, 3, 4],
        dtype=np.int64,
    )
    values = np.array(
        [
            8.0e6,
            -1.2e6,
            0.7e6,
            -1.2e6,
            7.5e6,
            -0.9e6,
            -0.9e6,
            6.8e6,
            0.6e6,
            0.7e6,
            5.9e6,
            -0.8e6,
            0.6e6,
            -0.8e6,
            6.4e6,
        ],
        dtype=np.float64,
    )
    free_global_dofs = np.array([0, 1, 2, 6, 7], dtype=np.int64)
    background = np.zeros(12, dtype=np.float64)
    background[8] = 0.0015
    frame_dofs = np.arange(12, dtype=np.int64).reshape(1, 12)
    raw = np.arange(1, 145, dtype=np.float64).reshape(12, 12)
    frame_delta = 125.0 * (raw + raw.T)
    frame_delta += np.diag(np.linspace(2.0e5, 4.2e5, 12))
    relative = np.zeros((1, 3, 12), dtype=np.float64)
    relative[0, :, :3] = -np.eye(3)
    relative[0, :, 6:9] = np.eye(3)
    reference_chord = np.array([[2.0, 0.3, -0.1]], dtype=np.float64)
    reference_length = np.linalg.norm(reference_chord, axis=1)
    axial_stiffness = np.array([3.15e7], dtype=np.float64)
    return create_current_tangent_operator(
        case_id="engine_v2_hip_current_tangent_synthetic",
        residual_formula_hash=canonical_hash(
            {"formula": "synthetic_current_tangent_fixture.v1"}
        ),
        source_action_contract="synthetic_reference_frame_geometry_action.v1",
        reference_row_pointer=row_pointer,
        reference_column_indices=columns,
        reference_values_n_per_m=values,
        free_global_dofs=free_global_dofs,
        background_global_displacements_m=background,
        frame_dofs=frame_dofs,
        frame_stiffness_delta_n_per_m=frame_delta.reshape(1, 12, 12),
        geometry_dofs=frame_dofs,
        geometry_relative_translation_operators=relative,
        geometry_reference_chords_m=reference_chord,
        geometry_reference_lengths_m=reference_length,
        geometry_axial_stiffness_n_per_m=axial_stiffness,
    )
