"""Device-resident HIP FGMRES recurrence fixture and parity validator."""

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
from structural_analysis.engine_v2.cpu_fgmres import (
    CPU_FGMRES_SCALED_JACOBI_PRECONDITIONER,
    CPUFGMRESRun,
    run_cpu_fgmres,
)
from structural_analysis.engine_v2.cpu_fgmres_checkpoint import (
    CPUFGMRESCheckpoint,
    create_cpu_fgmres_checkpoint,
)
from structural_analysis.engine_v2_backends.hip_primitive_parity import (
    EngineV2CPUHIPParityReference,
    HIP_PRECONDITIONER_DERIVATION_PROFILE,
    _operator_derived_left_scaled_jacobi_exact,
    build_engine_v2_cpu_hip_parity_reference,
)


HIP_FGMRES_FIXTURE_VERSION = "engine-v2-hip-fgmres-recurrence-fixture.v1"
HIP_FGMRES_OUTPUT_VERSION = "engine-v2-hip-fgmres-recurrence-output.v1"
HIP_FGMRES_PARITY_PROFILE = "engine-v2-cpu-hip-fgmres-recurrence-parity.v1"
HIP_FGMRES_BINARY_MAGIC = b"EV2FGR01"
HIP_FGMRES_ABSOLUTE_TOLERANCE = 1.0e-11
HIP_FGMRES_RELATIVE_TOLERANCE = 1.0e-11
HIP_FGMRES_THREADS_PER_CASE = 64
HIP_FGMRES_REDUCTION_PROFILE = "fixed_block_binary_tree_fp64_probe.v1"
HIP_FGMRES_KRYLOV_WORKSPACE_PROFILE = "device_global_dynamic_dimension_fp64.v1"
HIP_FGMRES_REFERENCE_FREE_EQUATION_COUNT = 66
HIP_FGMRES_WORKSPACE_DOUBLES_PER_EQUATION = 71
HIP_FGMRES_MAXIMUM_FIXTURE_DIMENSION = 4092
HIP_FGMRES_MAXIMUM_RESTART_LENGTH = 32
HIP_FGMRES_OPERATOR_BLOCKS_PER_CASE = 4
HIP_FGMRES_EXECUTION_PROFILE = (
    "same_stream_fixed_kernel_sequence_device_guarded.v1"
)
HIP_FGMRES_CASE_IDS = (
    "converged_full_cycle",
    "restart_max_iterations",
)


class HIPFGMRESParityError(ValueError):
    """Fail-closed recurrence fixture or runtime-output error."""

    def __init__(self, code: str, path: str, message: str) -> None:
        self.code = code
        self.path = path
        self.message = message
        super().__init__(f"{code}@{path}: {message}")


def _fail(code: str, path: str, message: str) -> None:
    raise HIPFGMRESParityError(code, path, message)


@dataclass(frozen=True)
class HIPFGMRESCaseConfig:
    case_id: str
    max_iterations: int
    restart_length: int
    relative_tolerance_scaled_l2: float
    absolute_tolerance_scaled_l2: float
    arnoldi_breakdown_tolerance: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "max_iterations": self.max_iterations,
            "restart_length": self.restart_length,
            "relative_tolerance_scaled_l2": self.relative_tolerance_scaled_l2,
            "absolute_tolerance_scaled_l2": self.absolute_tolerance_scaled_l2,
            "arnoldi_breakdown_tolerance": self.arnoldi_breakdown_tolerance,
        }


@dataclass(frozen=True)
class HIPFGMRESRecurrenceFixture:
    schema_version: str
    execution_plan_hash: str
    scaling_hash: str
    reduced_csr_identity_hash: str
    operator_numeric_values_hash: str
    row_ptr: np.ndarray
    column_indices: np.ndarray
    values: np.ndarray
    right_hand_side: np.ndarray
    scale_divisors: np.ndarray
    initial_solution: np.ndarray
    inverse_diagonal: np.ndarray
    cases: tuple[HIPFGMRESCaseConfig, ...]

    @property
    def dimension(self) -> int:
        return int(self.right_hand_side.size)

    @property
    def nnz(self) -> int:
        return int(self.values.size)

    def to_bytes(self) -> bytes:
        chunks = [
            struct.pack(
                "<8sQQQ",
                HIP_FGMRES_BINARY_MAGIC,
                self.dimension,
                self.nnz,
                len(self.cases),
            ),
            self.row_ptr.tobytes(order="C"),
            self.column_indices.tobytes(order="C"),
            self.values.tobytes(order="C"),
            self.right_hand_side.tobytes(order="C"),
            self.scale_divisors.tobytes(order="C"),
            self.initial_solution.tobytes(order="C"),
            self.inverse_diagonal.tobytes(order="C"),
        ]
        chunks.extend(
            struct.pack(
                "<QQddd",
                case.max_iterations,
                case.restart_length,
                case.relative_tolerance_scaled_l2,
                case.absolute_tolerance_scaled_l2,
                case.arnoldi_breakdown_tolerance,
            )
            for case in self.cases
        )
        return b"".join(chunks)

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
            "right_hand_side": self.right_hand_side,
            "scale_divisors": self.scale_divisors,
            "initial_solution": self.initial_solution,
            "inverse_diagonal": self.inverse_diagonal,
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
            "cases": [case.to_dict() for case in self.cases],
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
class CPUHIPFGMRESRecurrenceReference:
    primitive_reference: EngineV2CPUHIPParityReference
    fixture: HIPFGMRESRecurrenceFixture
    cpu_runs: tuple[CPUFGMRESRun, ...]
    checkpoint: CPUFGMRESCheckpoint


def _run_variant(
    reference: EngineV2CPUHIPParityReference,
    config: HIPFGMRESCaseConfig,
) -> CPUFGMRESRun:
    source = reference.cpu_run
    return run_cpu_fgmres(
        execution_plan=source._execution_plan,
        scaling=source._scaling,
        reduced_csr=source._reduced_csr,
        node_coordinates_m=reference.node_coordinates_m,
        reference_equation_load_si=reference.reference_equation_load_si,
        global_csr_values_si=source._input_arrays["global_csr_values_si"],
        right_hand_side_si=source._input_arrays["right_hand_side_si"],
        solution_artifact_uri=(
            f"artifact://engine-v2-cpu-hip-recurrence/{config.case_id}/"
            "solution_free.f64le"
        ),
        max_iterations=config.max_iterations,
        restart_length=config.restart_length,
        relative_tolerance_scaled_l2=config.relative_tolerance_scaled_l2,
        absolute_tolerance_scaled_l2=config.absolute_tolerance_scaled_l2,
        arnoldi_breakdown_tolerance=config.arnoldi_breakdown_tolerance,
        initial_solution_free=source._input_arrays["initial_solution_free"],
        right_preconditioner_inverse_diagonal=source._input_arrays[
            "right_preconditioner_inverse_diagonal"
        ],
        right_preconditioner_profile=source.preconditioner_profile,
    )


def build_cpu_hip_fgmres_recurrence_reference() -> CPUHIPFGMRESRecurrenceReference:
    """Build converged and forced-restart CPU runs plus one shared HIP fixture."""

    primitive = build_engine_v2_cpu_hip_parity_reference(
        free_equation_count=HIP_FGMRES_REFERENCE_FREE_EQUATION_COUNT
    )
    source = primitive.cpu_run
    cases = (
        HIPFGMRESCaseConfig(
            case_id=HIP_FGMRES_CASE_IDS[0],
            max_iterations=source.max_iterations,
            restart_length=source.restart_length,
            relative_tolerance_scaled_l2=source.relative_tolerance_scaled_l2,
            absolute_tolerance_scaled_l2=source.absolute_tolerance_scaled_l2,
            arnoldi_breakdown_tolerance=source.arnoldi_breakdown_tolerance,
        ),
        HIPFGMRESCaseConfig(
            case_id=HIP_FGMRES_CASE_IDS[1],
            max_iterations=2,
            restart_length=1,
            relative_tolerance_scaled_l2=1.0e-30,
            absolute_tolerance_scaled_l2=1.0e-30,
            arnoldi_breakdown_tolerance=1.0e-14,
        ),
    )
    cpu_runs = (source, _run_variant(primitive, cases[1]))
    if any(
        run.preconditioner_profile
        != CPU_FGMRES_SCALED_JACOBI_PRECONDITIONER
        for run in cpu_runs
    ):
        raise AssertionError("FGMRES recurrence preconditioner profile drifted")
    free_dofs = source._execution_plan.array("free_dofs")
    fixture = HIPFGMRESRecurrenceFixture(
        schema_version=HIP_FGMRES_FIXTURE_VERSION,
        execution_plan_hash=source.execution_plan_hash,
        scaling_hash=source.scaling_hash,
        reduced_csr_identity_hash=source.reduced_csr_identity_hash,
        operator_numeric_values_hash=source.operator_numeric_values_hash,
        row_ptr=immutable_array(
            source._reduced_csr.array("free_csr_row_ptr"),
            dtype="<i8",
        ),
        column_indices=immutable_array(
            source._reduced_csr.array("free_csr_column_indices"),
            dtype="<i4",
        ),
        values=immutable_array(
            source._input_arrays["global_csr_values_si"][
                source._reduced_csr.array("free_csr_global_value_indices")
            ],
            dtype="<f8",
        ),
        right_hand_side=immutable_array(
            source._input_arrays["right_hand_side_si"][free_dofs],
            dtype="<f8",
        ),
        scale_divisors=immutable_array(
            source._input_arrays["free_equation_scale_divisors_si"],
            dtype="<f8",
        ),
        initial_solution=immutable_array(
            source._input_arrays["initial_solution_free"],
            dtype="<f8",
        ),
        inverse_diagonal=immutable_array(
            source._input_arrays["right_preconditioner_inverse_diagonal"],
            dtype="<f8",
        ),
        cases=cases,
    )
    validate_hip_fgmres_fixture(fixture)
    checkpoint = create_cpu_fgmres_checkpoint(
        cpu_runs[1],
        restart_index=0,
        checkpoint_artifact_uri=(
            "artifact://engine-v2/cpu-hip-fgmres/"
            "fgmres_restart_checkpoint.bin"
        ),
    )
    return CPUHIPFGMRESRecurrenceReference(
        primitive_reference=primitive,
        fixture=fixture,
        cpu_runs=cpu_runs,
        checkpoint=checkpoint,
    )


def validate_hip_fgmres_fixture(
    fixture: HIPFGMRESRecurrenceFixture,
) -> HIPFGMRESRecurrenceFixture:
    if type(fixture) is not HIPFGMRESRecurrenceFixture:
        _fail("hip_fgmres_fixture_type_invalid", "/", "Expected fixture.")
    if fixture.schema_version != HIP_FGMRES_FIXTURE_VERSION:
        _fail("hip_fgmres_fixture_schema_invalid", "/schema_version", "Unsupported.")
    dimension = fixture.dimension
    if (
        dimension <= 0
        or dimension > HIP_FGMRES_MAXIMUM_FIXTURE_DIMENSION
        or fixture.nnz <= 0
    ):
        _fail("hip_fgmres_fixture_dimension_invalid", "/", "Dimension is invalid.")
    specs = (
        (fixture.row_ptr, "<i8", (dimension + 1,), "/arrays/row_ptr"),
        (fixture.column_indices, "<i4", (fixture.nnz,), "/arrays/column_indices"),
        (fixture.values, "<f8", (fixture.nnz,), "/arrays/values"),
        (fixture.right_hand_side, "<f8", (dimension,), "/arrays/right_hand_side"),
        (fixture.scale_divisors, "<f8", (dimension,), "/arrays/scale_divisors"),
        (fixture.initial_solution, "<f8", (dimension,), "/arrays/initial_solution"),
        (fixture.inverse_diagonal, "<f8", (dimension,), "/arrays/inverse_diagonal"),
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
            _fail("hip_fgmres_fixture_array_invalid", path, "Array is invalid.")
    if (
        int(fixture.row_ptr[0]) != 0
        or int(fixture.row_ptr[-1]) != fixture.nnz
        or np.any(np.diff(fixture.row_ptr) < 0)
        or np.any(fixture.column_indices < 0)
        or np.any(fixture.column_indices >= dimension)
    ):
        _fail("hip_fgmres_fixture_csr_invalid", "/arrays", "CSR is invalid.")
    if np.any(fixture.scale_divisors <= 0.0) or np.any(
        fixture.inverse_diagonal <= 0.0
    ):
        _fail("hip_fgmres_fixture_scaling_invalid", "/arrays", "Scale is invalid.")
    if not _operator_derived_left_scaled_jacobi_exact(
        row_ptr=fixture.row_ptr,
        columns=fixture.column_indices,
        values=fixture.values,
        scale_divisors=fixture.scale_divisors,
        inverse_diagonal=fixture.inverse_diagonal,
    ):
        _fail(
            "hip_fgmres_fixture_preconditioner_binding_invalid",
            "/arrays/inverse_diagonal",
            "Jacobi bytes must equal the exact D_free^-1 A_free diagonal inverse.",
        )
    if tuple(case.case_id for case in fixture.cases) != HIP_FGMRES_CASE_IDS:
        _fail("hip_fgmres_fixture_cases_invalid", "/cases", "Case set is invalid.")
    for index, case in enumerate(fixture.cases):
        if (
            case.max_iterations <= 0
            or case.max_iterations > 128
            or case.restart_length <= 0
            or case.restart_length > dimension
            or case.restart_length > HIP_FGMRES_MAXIMUM_RESTART_LENGTH
            or case.relative_tolerance_scaled_l2 < 0.0
            or case.absolute_tolerance_scaled_l2 < 0.0
            or case.arnoldi_breakdown_tolerance <= 0.0
        ):
            _fail(
                "hip_fgmres_fixture_case_invalid",
                f"/cases/{index}",
                "Case configuration is invalid.",
            )
    return fixture


def compare_hip_fgmres_recurrence_output(
    reference: CPUHIPFGMRESRecurrenceReference,
    payload: Any,
    *,
    absolute_tolerance: float = HIP_FGMRES_ABSOLUTE_TOLERANCE,
    relative_tolerance: float = HIP_FGMRES_RELATIVE_TOLERANCE,
) -> dict[str, Any]:
    """Compare actual device-resident recurrence output with both CPU runs."""

    fixture = validate_hip_fgmres_fixture(reference.fixture)
    if not isinstance(payload, dict):
        _fail("hip_fgmres_output_type_invalid", "/", "Expected object.")
    metadata = {
        "schema_version": HIP_FGMRES_OUTPUT_VERSION,
        "runtime_status": "success",
        "runtime_status_code": 0,
        "backend": "amd_rocm_hip",
        "cpu_backend": False,
        "same_stream_ordering": True,
        "mid_recurrence_host_transfer_count": 0,
        "blocking_d2h_synchronization_count": 1,
        "checkpoint_h2d_transfer_count": 1,
        "checkpoint_completed_iteration_replay_count": 0,
        "threads_per_case": HIP_FGMRES_THREADS_PER_CASE,
        "reduction_profile": HIP_FGMRES_REDUCTION_PROFILE,
        "krylov_workspace_profile": HIP_FGMRES_KRYLOV_WORKSPACE_PROFILE,
        "workspace_dimension": fixture.dimension,
        "workspace_doubles_per_case": (
            HIP_FGMRES_WORKSPACE_DOUBLES_PER_EQUATION * fixture.dimension
        ),
        "operator_blocks_per_case": HIP_FGMRES_OPERATOR_BLOCKS_PER_CASE,
        "recurrence_execution_profile": HIP_FGMRES_EXECUTION_PROFILE,
        "device_resident_full_recurrence_probe": True,
        "production_recurrence_claim": False,
        "preconditioner_profile": (
            CPU_FGMRES_SCALED_JACOBI_PRECONDITIONER
        ),
    }
    for key, expected in metadata.items():
        if payload.get(key) != expected:
            _fail(
                "hip_fgmres_output_runtime_contract_invalid",
                f"/{key}",
                f"Expected {expected!r}.",
            )
    cooperative_launch_supported = payload.get("cooperative_launch_supported")
    if type(cooperative_launch_supported) is not bool:
        _fail(
            "hip_fgmres_output_runtime_contract_invalid",
            "/cooperative_launch_supported",
            "A boolean cooperative-launch capability is required.",
        )
    architecture = payload.get("gcn_arch_name")
    if not isinstance(architecture, str) or not architecture.startswith("gfx"):
        _fail("hip_fgmres_output_arch_invalid", "/gcn_arch_name", "gfx required.")
    expected_multi_block_kernel_count = _expected_multi_block_kernel_count(
        reference
    )
    total_kernel_count = payload.get("kernel_invocation_count")
    multi_block_kernel_count = payload.get("multi_block_kernel_invocation_count")
    if (
        type(total_kernel_count) is not int
        or type(multi_block_kernel_count) is not int
        or multi_block_kernel_count != expected_multi_block_kernel_count
        or total_kernel_count != multi_block_kernel_count
    ):
        _fail(
            "hip_fgmres_output_kernel_count_invalid",
            "/kernel_invocation_count",
            "Kernel counts must bind the exact device-guarded multi-block "
            "sequence.",
        )
    rows = payload.get("cases")
    if not isinstance(rows, list) or len(rows) != len(fixture.cases):
        _fail("hip_fgmres_output_cases_invalid", "/cases", "Case count is invalid.")
    absolute = _nonnegative_finite(absolute_tolerance, "/absolute_tolerance")
    relative = _nonnegative_finite(relative_tolerance, "/relative_tolerance")
    if absolute == 0.0 and relative == 0.0:
        _fail("hip_fgmres_tolerance_invalid", "/", "A tolerance is required.")
    comparisons = [
        _compare_case(
            config,
            cpu_run,
            actual,
            absolute_tolerance=absolute,
            relative_tolerance=relative,
        )
        for config, cpu_run, actual in zip(
            fixture.cases,
            reference.cpu_runs,
            rows,
            strict=True,
        )
    ]
    checkpoint_comparison = _compare_checkpoint_resume(
        reference,
        payload.get("checkpoint_resume"),
        checkpoint_hash=payload.get("checkpoint_hash"),
        checkpoint_artifact_data_hash=payload.get(
            "checkpoint_artifact_data_hash"
        ),
        checkpoint_recurrence_contract_hash=payload.get(
            "checkpoint_recurrence_contract_hash"
        ),
        absolute_tolerance=absolute,
        relative_tolerance=relative,
    )
    contract_pass = all(row["contract_pass"] for row in comparisons) and bool(
        checkpoint_comparison["contract_pass"]
    )
    return {
        "schema_version": HIP_FGMRES_PARITY_PROFILE,
        "fixture_hash": fixture.fixture_hash,
        "device_name": payload.get("device_name"),
        "gcn_arch_name": architecture,
        "absolute_tolerance": absolute,
        "relative_tolerance": relative,
        "case_rows": comparisons,
        "checkpoint_resume": checkpoint_comparison,
        "maximum_solution_absolute_error": max(
            row["solution_maximum_absolute_error"] for row in comparisons
        ),
        "maximum_observation_absolute_error": max(
            row["observation_maximum_absolute_error"] for row in comparisons
        ),
        "terminal_semantics_exact": all(
            row["terminal_semantics_exact"] for row in comparisons
        ),
        "restart_checkpoint_semantics_exact": all(
            row["restart_checkpoint_semantics_exact"] for row in comparisons
        ),
        "persisted_checkpoint_resume_semantics_exact": checkpoint_comparison[
            "contract_pass"
        ],
        "contract_pass": contract_pass,
        "device_resident_full_recurrence_probe_claim": contract_pass,
        "parallel_reduction_recurrence_probe_claim": contract_pass,
        "device_global_krylov_workspace_probe_claim": contract_pass,
        "cooperative_launch_supported": cooperative_launch_supported,
        "multi_block_recurrence_probe_claim": contract_pass,
        "operator_derived_scaled_jacobi_recurrence_probe_claim": (
            contract_pass
        ),
        "multi_block_kernel_invocation_count": multi_block_kernel_count,
        "production_recurrence_claim": False,
        "performance_claim": False,
    }


def _expected_multi_block_kernel_count(
    reference: CPUHIPFGMRESRecurrenceReference,
) -> int:
    cases = (
        reference.fixture.cases[0],
        reference.fixture.cases[1],
        reference.fixture.cases[1],
    )
    starts = (0, 0, reference.checkpoint.iteration_count)
    total = 0
    for index, (case, first_iteration) in enumerate(
        zip(cases, starts, strict=True)
    ):
        total += 5 if index == 2 else 7
        total += 1  # final device solution copy
        for cycle_start in range(
            first_iteration,
            case.max_iterations,
            case.restart_length,
        ):
            capacity = min(
                case.restart_length,
                case.max_iterations - cycle_start,
            )
            total += 3  # cycle begin, vector begin, cycle disposition
            total += sum(
                14 + 6 * (inner + 1) for inner in range(capacity)
            )
    return total


def _compare_checkpoint_resume(
    reference: CPUHIPFGMRESRecurrenceReference,
    actual: Any,
    *,
    checkpoint_hash: Any,
    checkpoint_artifact_data_hash: Any,
    checkpoint_recurrence_contract_hash: Any,
    absolute_tolerance: float,
    relative_tolerance: float,
) -> dict[str, Any]:
    checkpoint = reference.checkpoint
    cpu_run = reference.cpu_runs[1]
    if not isinstance(actual, dict):
        _fail(
            "hip_fgmres_checkpoint_resume_missing",
            "/checkpoint_resume",
            "Persisted checkpoint resume output is required.",
        )
    expected_metadata = {
        "case_id": "restart_max_iterations",
        "runtime_status_code": 0,
        "artifact_loaded": True,
        "device_resident_suffix_recurrence": True,
        "completed_iteration_replay_count": 0,
        "resumed_from_iteration": checkpoint.iteration_count,
        "restart_index_base": checkpoint.next_restart_index,
        "terminal_reason": cpu_run.terminal_reason,
        "converged": cpu_run.converged,
        "iteration_count": cpu_run.iteration_count,
        "matvec_count": cpu_run.matvec_count,
        "suffix_restart_count": (
            len(cpu_run.restart_history) - checkpoint.next_restart_index
        ),
    }
    metadata_exact = all(
        actual.get(key) == expected for key, expected in expected_metadata.items()
    )
    hash_binding_exact = bool(
        checkpoint_hash == checkpoint.checkpoint_hash
        and checkpoint_artifact_data_hash
        == checkpoint.artifact_descriptor.data_hash
        and checkpoint_recurrence_contract_hash
        == checkpoint.recurrence_contract_hash
    )
    solution_actual = _finite_vector(
        actual.get("solution"),
        cpu_run.free_count,
        "/checkpoint_resume/solution",
    )
    solution_errors, solution_pass = _errors(
        [float(value) for value in cpu_run.solution_free],
        solution_actual,
        absolute_tolerance=absolute_tolerance,
        relative_tolerance=relative_tolerance,
    )
    suffix_observations = cpu_run.observations[checkpoint.iteration_count :]
    l2_actual = _finite_vector(
        actual.get("scaled_l2_suffix_history"),
        len(suffix_observations),
        "/checkpoint_resume/scaled_l2_suffix_history",
    )
    linf_actual = _finite_vector(
        actual.get("scaled_linf_suffix_history"),
        len(suffix_observations),
        "/checkpoint_resume/scaled_linf_suffix_history",
    )
    l2_errors, l2_pass = _errors(
        [row.scaled_l2 for row in suffix_observations],
        l2_actual,
        absolute_tolerance=absolute_tolerance,
        relative_tolerance=relative_tolerance,
    )
    linf_errors, linf_pass = _errors(
        [row.scaled_linf for row in suffix_observations],
        linf_actual,
        absolute_tolerance=absolute_tolerance,
        relative_tolerance=relative_tolerance,
    )
    restart_expected = [
        {
            "start_iteration": row.start_iteration,
            "end_iteration": row.end_iteration,
            "iteration_count": row.iteration_count,
            "disposition": row.disposition,
        }
        for row in cpu_run.restart_history[checkpoint.next_restart_index :]
    ]
    restart_exact = actual.get("restart_suffix_history") == restart_expected
    threshold = _finite_number(
        actual.get("convergence_threshold_scaled_l2"),
        "/checkpoint_resume/convergence_threshold_scaled_l2",
    )
    threshold_exact = threshold == checkpoint.convergence_threshold_scaled_l2
    contract_pass = bool(
        metadata_exact
        and hash_binding_exact
        and solution_pass
        and l2_pass
        and linf_pass
        and restart_exact
        and threshold_exact
    )
    return {
        "checkpoint_hash": checkpoint.checkpoint_hash,
        "checkpoint_artifact_data_hash": (
            checkpoint.artifact_descriptor.data_hash
        ),
        "checkpoint_recurrence_contract_hash": (
            checkpoint.recurrence_contract_hash
        ),
        "resumed_from_iteration": checkpoint.iteration_count,
        "completed_iteration_replay_count": 0,
        "metadata_exact": metadata_exact,
        "hash_binding_exact": hash_binding_exact,
        "terminal_semantics_exact": metadata_exact,
        "restart_suffix_semantics_exact": restart_exact,
        "threshold_exact": threshold_exact,
        "solution_maximum_absolute_error": max(solution_errors, default=0.0),
        "observation_maximum_absolute_error": max(
            [*l2_errors, *linf_errors],
            default=0.0,
        ),
        "contract_pass": contract_pass,
        "production_checkpoint_claim": False,
    }


def _compare_case(
    config: HIPFGMRESCaseConfig,
    cpu_run: CPUFGMRESRun,
    actual: Any,
    *,
    absolute_tolerance: float,
    relative_tolerance: float,
) -> dict[str, Any]:
    if not isinstance(actual, dict) or actual.get("case_id") != config.case_id:
        _fail("hip_fgmres_case_identity_invalid", "/cases", "Case ID is stale.")
    if actual.get("runtime_status_code") != 0:
        _fail("hip_fgmres_case_status_invalid", "/cases", "Device status failed.")
    terminal_expected = {
        "terminal_reason": cpu_run.terminal_reason,
        "converged": cpu_run.converged,
        "iteration_count": cpu_run.iteration_count,
        "matvec_count": cpu_run.matvec_count,
        "restart_count": len(cpu_run.restart_history),
    }
    terminal_exact = all(actual.get(key) == value for key, value in terminal_expected.items())
    solution_actual = _finite_vector(
        actual.get("solution"),
        cpu_run.free_count,
        f"/cases/{config.case_id}/solution",
    )
    solution_reference = [float(value) for value in cpu_run.solution_free]
    solution_errors, solution_pass = _errors(
        solution_reference,
        solution_actual,
        absolute_tolerance=absolute_tolerance,
        relative_tolerance=relative_tolerance,
    )
    l2_actual = _finite_vector(
        actual.get("scaled_l2_history"),
        len(cpu_run.observations),
        f"/cases/{config.case_id}/scaled_l2_history",
    )
    linf_actual = _finite_vector(
        actual.get("scaled_linf_history"),
        len(cpu_run.observations),
        f"/cases/{config.case_id}/scaled_linf_history",
    )
    l2_errors, l2_pass = _errors(
        [row.scaled_l2 for row in cpu_run.observations],
        l2_actual,
        absolute_tolerance=absolute_tolerance,
        relative_tolerance=relative_tolerance,
    )
    linf_errors, linf_pass = _errors(
        [row.scaled_linf for row in cpu_run.observations],
        linf_actual,
        absolute_tolerance=absolute_tolerance,
        relative_tolerance=relative_tolerance,
    )
    threshold = _finite_number(
        actual.get("convergence_threshold_scaled_l2"),
        f"/cases/{config.case_id}/convergence_threshold_scaled_l2",
    )
    threshold_error = abs(threshold - cpu_run.convergence_threshold_scaled_l2)
    threshold_pass = threshold_error <= max(
        absolute_tolerance,
        relative_tolerance * abs(cpu_run.convergence_threshold_scaled_l2),
    )
    restart_actual = actual.get("restart_history")
    restart_reference = [
        {
            "start_iteration": row.start_iteration,
            "end_iteration": row.end_iteration,
            "iteration_count": row.iteration_count,
            "disposition": row.disposition,
        }
        for row in cpu_run.restart_history
    ]
    restart_exact = restart_actual == restart_reference
    contract_pass = bool(
        terminal_exact
        and solution_pass
        and l2_pass
        and linf_pass
        and threshold_pass
        and restart_exact
    )
    return {
        "case_id": config.case_id,
        "cpu_run_hash": cpu_run.run_hash,
        "terminal_semantics_exact": terminal_exact,
        "restart_checkpoint_semantics_exact": restart_exact,
        "solution_maximum_absolute_error": max(solution_errors, default=0.0),
        "observation_maximum_absolute_error": max(
            [*l2_errors, *linf_errors],
            default=0.0,
        ),
        "threshold_absolute_error": threshold_error,
        "contract_pass": contract_pass,
    }


def _errors(
    reference: list[float],
    actual: list[float],
    *,
    absolute_tolerance: float,
    relative_tolerance: float,
) -> tuple[list[float], bool]:
    errors = [
        abs(actual_value - reference_value)
        for reference_value, actual_value in zip(reference, actual, strict=True)
    ]
    passed = all(
        error
        <= max(absolute_tolerance, relative_tolerance * abs(reference_value))
        for error, reference_value in zip(errors, reference, strict=True)
    )
    return errors, passed


def _finite_vector(value: Any, length: int, path: str) -> list[float]:
    if not isinstance(value, list) or len(value) != length:
        _fail("hip_fgmres_output_vector_invalid", path, "Vector length is invalid.")
    return [_finite_number(item, f"{path}/{index}") for index, item in enumerate(value)]


def _finite_number(value: Any, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail("hip_fgmres_output_number_invalid", path, "Finite number required.")
    result = float(value)
    if not math.isfinite(result):
        _fail("hip_fgmres_output_number_invalid", path, "Finite number required.")
    return result


def _nonnegative_finite(value: Any, path: str) -> float:
    result = _finite_number(value, path)
    if result < 0.0:
        _fail("hip_fgmres_tolerance_invalid", path, "Tolerance must be nonnegative.")
    return result


def fgmres_recurrence_receipt_hash(payload: dict[str, Any]) -> str:
    return canonical_hash(
        {key: value for key, value in payload.items() if key != "receipt_hash"}
    )
