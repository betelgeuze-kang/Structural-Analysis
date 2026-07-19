"""Deterministic CPU FGMRES recurrence for Engine v2 free equations.

The solver consumes an already scaled and replay-verified ExecutionPlan plus
the single reduced-CSR identity.  It emits compact checkpoint observations and
a descriptor-only solution artifact.  It does not construct ResultIR or claim
engineering-result authority.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from functools import lru_cache
from importlib import resources
import json
import math
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal

from jsonschema import Draft202012Validator, validators
import numpy as np

from .contracts._canonical import (
    CanonicalContractError,
    array_content_hash,
    array_data_hash,
    canonical_hash,
    has_immutable_bytes_backing,
    immutable_array,
)
from .contracts.equation_scaling import (
    EquationScaling,
    validate_equation_scaling_binding,
)
from .contracts.execution_plan import (
    EXECUTION_PLAN_DOF_COMPONENTS,
    ExecutionPlan,
    validate_execution_plan,
)
from .contracts.execution_plan_reduced_csr import (
    ExecutionPlanReducedCSR,
    validate_execution_plan_reduced_csr,
)

CPU_FGMRES_SCHEMA_VERSION = "structural-analysis-cpu-fgmres-run.v1"
CPU_FGMRES_RECURRENCE_PROFILE = (
    "left_equation_scaled_fgmres_two_pass_modified_gram_schmidt.v1"
)
CPU_FGMRES_ACCUMULATION_PROFILE = "ascending_index_python_fsum_fp64.v1"
CPU_FGMRES_IDENTITY_PRECONDITIONER = "identity_right_preconditioner.v1"
CPU_FGMRES_DIAGONAL_PRECONDITIONER = "fixed_positive_inverse_diagonal_right.v1"
CPU_FGMRES_SCALED_JACOBI_PRECONDITIONER = (
    "operator_derived_left_scaled_jacobi_right.v1"
)
CPU_FGMRES_SOLUTION_FILENAME = "solution_free.f64le"

_HASH_ZERO = "sha256:" + "0" * 64
_INPUT_NAMES = (
    "global_csr_values_si",
    "right_hand_side_si",
    "free_equation_scale_divisors_si",
    "initial_solution_free",
    "right_preconditioner_inverse_diagonal",
)
_TERMINAL_REASONS = (
    "initial_residual_satisfied",
    "converged_scaled_residual",
    "max_iterations",
    "arnoldi_breakdown",
)
_STRICT_JSON_TYPE_CHECKER = Draft202012Validator.TYPE_CHECKER.redefine(
    "integer", lambda _checker, value: type(value) is int
).redefine("number", lambda _checker, value: type(value) in (int, float))
_StrictDraft202012Validator = validators.extend(
    Draft202012Validator, type_checker=_STRICT_JSON_TYPE_CHECKER
)


class CPUFGMRESError(ValueError):
    """Fail-closed CPU FGMRES contract or recurrence error."""

    def __init__(self, code: str, path: str, message: str) -> None:
        self.code = code
        self.path = path
        self.message = message
        super().__init__(f"{code}@{path}: {message}")


@dataclass(frozen=True)
class CPUFGMRESVectorDescriptor:
    name: str
    dtype: Literal["<f8"]
    shape: tuple[int, ...]
    layout: Literal["C"]
    byte_order: Literal["little"]
    equation_scope: str
    byte_length: int
    data_hash: str
    content_hash: str
    artifact_uri: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["shape"] = list(self.shape)
        if self.artifact_uri is None:
            payload.pop("artifact_uri")
        return payload


@dataclass(frozen=True)
class CPUFGMRESObservation:
    observation_hash: str
    iteration: int
    restart_index: int
    inner_iteration: int
    raw_residual_data_hash: str
    scaled_residual_data_hash: str
    solution_free_data_hash: str
    raw_translation_l2_n: float
    raw_translation_linf_n: float
    raw_rotation_l2_nm: float
    raw_rotation_linf_nm: float
    scaled_l2: float
    scaled_linf: float
    governing_equation: int
    governing_node_id: str
    governing_dof: str

    def to_dict(self) -> dict[str, Any]:
        return _observation_payload(self, include_hash=True)


@dataclass(frozen=True)
class CPUFGMRESRestartRecord:
    restart_hash: str
    restart_index: int
    start_iteration: int
    end_iteration: int
    iteration_count: int
    start_observation_hash: str
    end_observation_hash: str
    disposition: str

    def to_dict(self) -> dict[str, Any]:
        return _restart_payload(self, include_hash=True)


@dataclass(frozen=True)
class _CPUFGMRESRestartSnapshot:
    restart_index: int
    iteration_count: int
    matvec_count: int
    solution_free: np.ndarray
    scaled_residual_free: np.ndarray


@dataclass(frozen=True)
class _CPUFGMRESResumeState:
    iteration_count: int
    matvec_count: int
    next_restart_index: int
    convergence_threshold_scaled_l2: float
    observations: tuple[CPUFGMRESObservation, ...]
    restart_history: tuple[CPUFGMRESRestartRecord, ...]
    solution_free: np.ndarray
    scaled_residual_free: np.ndarray


@dataclass(frozen=True)
class CPUFGMRESRun:
    schema_version: str
    run_hash: str
    execution_plan_hash: str
    scaling_hash: str
    reduced_csr_identity_hash: str
    operator_numeric_values_hash: str
    dof_count: int
    free_count: int
    global_csr_nnz: int
    preconditioner_profile: str
    max_iterations: int
    restart_length: int
    relative_tolerance_scaled_l2: float
    absolute_tolerance_scaled_l2: float
    arnoldi_breakdown_tolerance: float
    convergence_threshold_scaled_l2: float
    iteration_count: int
    matvec_count: int
    terminal_reason: str
    converged: bool
    input_descriptors: tuple[CPUFGMRESVectorDescriptor, ...]
    observations: tuple[CPUFGMRESObservation, ...]
    restart_history: tuple[CPUFGMRESRestartRecord, ...]
    solution_descriptor: CPUFGMRESVectorDescriptor
    _solution_free: np.ndarray
    _input_arrays: Mapping[str, np.ndarray]
    _execution_plan: ExecutionPlan
    _scaling: EquationScaling
    _reduced_csr: ExecutionPlanReducedCSR
    _restart_snapshots: tuple[_CPUFGMRESRestartSnapshot, ...]

    @property
    def solution_free(self) -> np.ndarray:
        return self._solution_free

    def to_manifest(self) -> dict[str, Any]:
        validate_cpu_fgmres_run(self)
        return _run_payload(self, include_run_hash=True)


def build_cpu_fgmres_left_scaled_jacobi_inverse_diagonal(
    *,
    execution_plan: ExecutionPlan,
    scaling: EquationScaling,
    reduced_csr: ExecutionPlanReducedCSR,
    global_csr_values_si: Any,
) -> np.ndarray:
    """Derive the exact right-Jacobi vector for ``D_free^-1 A_free``.

    The diagonal is selected from the authoritative reduced-CSR mapping. A
    missing, duplicate, non-finite, or non-positive diagonal fails closed; no
    regularization or fallback value is introduced.
    """

    plan = validate_execution_plan(execution_plan)
    validate_equation_scaling_binding(plan, scaling=scaling)
    reduced = validate_execution_plan_reduced_csr(
        reduced_csr,
        execution_plan=plan,
    )
    global_values = _float_vector(
        global_csr_values_si,
        shape=(int(plan.array("csr_column_indices").size),),
        path="/inputs/global_csr_values_si",
    )
    if array_data_hash(global_values) != reduced.operator_numeric_values_hash:
        _fail(
            "fgmres_operator_numeric_values_hash_mismatch",
            "/inputs/global_csr_values_si/data_hash",
            "Global CSR numeric bytes do not match the reduced-CSR identity.",
        )
    free_scale = _float_vector(
        scaling.scale_divisors_si[plan.array("free_dofs")],
        shape=(reduced.free_count,),
        path="/inputs/free_equation_scale_divisors_si",
    )
    return _derive_left_scaled_jacobi_inverse_diagonal(
        reduced=reduced,
        global_values=global_values,
        free_scale=free_scale,
    )


def run_cpu_fgmres(
    *,
    execution_plan: ExecutionPlan,
    scaling: EquationScaling,
    reduced_csr: ExecutionPlanReducedCSR,
    node_coordinates_m: Any,
    reference_equation_load_si: Any,
    global_csr_values_si: Any,
    right_hand_side_si: Any,
    solution_artifact_uri: str,
    max_iterations: int = 100,
    restart_length: int = 30,
    relative_tolerance_scaled_l2: float = 1.0e-8,
    absolute_tolerance_scaled_l2: float = 1.0e-12,
    arnoldi_breakdown_tolerance: float = 1.0e-14,
    initial_solution_free: Any | None = None,
    right_preconditioner_inverse_diagonal: Any | None = None,
    right_preconditioner_profile: str | None = None,
    _resume_state: _CPUFGMRESResumeState | None = None,
) -> CPUFGMRESRun:
    """Run the deterministic free-equation recurrence.

    ``right_hand_side_si`` defines ``A x = b`` in global equation order.  The
    reported raw residual uses the Engine v2 sign ``A x - b``.  Convergence is
    decided on the L2 norm of ``D_free^-1 (A x - b)``.
    """

    plan = validate_execution_plan(execution_plan)
    validate_equation_scaling_binding(
        plan,
        scaling=scaling,
        node_coordinates_m=node_coordinates_m,
        reference_equation_load_si=reference_equation_load_si,
    )
    reduced = validate_execution_plan_reduced_csr(reduced_csr, execution_plan=plan)
    free_count = reduced.free_count
    if free_count == 0:
        _fail(
            "fgmres_free_equation_space_empty",
            "/source/free_count",
            "Fully constrained plans must use no-solve/reaction-only routing.",
        )

    maximum = _exact_int(max_iterations, "/parameters/max_iterations", minimum=1)
    restart = _exact_int(restart_length, "/parameters/restart_length", minimum=1)
    if restart > free_count:
        _fail(
            "fgmres_restart_length_invalid",
            "/parameters/restart_length",
            "Restart length cannot exceed the free-equation count.",
        )
    relative_tolerance = _nonnegative_float(
        relative_tolerance_scaled_l2,
        "/parameters/relative_tolerance_scaled_l2",
    )
    absolute_tolerance = _nonnegative_float(
        absolute_tolerance_scaled_l2,
        "/parameters/absolute_tolerance_scaled_l2",
    )
    if relative_tolerance == 0.0 and absolute_tolerance == 0.0:
        _fail(
            "fgmres_tolerance_invalid",
            "/parameters",
            "At least one convergence tolerance must be positive.",
        )
    breakdown_tolerance = _positive_float(
        arnoldi_breakdown_tolerance,
        "/parameters/arnoldi_breakdown_tolerance",
    )

    global_nnz = int(plan.array("csr_column_indices").size)
    global_values = _float_vector(
        global_csr_values_si,
        shape=(global_nnz,),
        path="/inputs/global_csr_values_si",
    )
    if array_data_hash(global_values) != reduced.operator_numeric_values_hash:
        _fail(
            "fgmres_operator_numeric_values_hash_mismatch",
            "/inputs/global_csr_values_si/data_hash",
            "Global CSR numeric bytes do not match the reduced-CSR identity.",
        )
    right_hand_side = _float_vector(
        right_hand_side_si,
        shape=(plan.dof_count,),
        path="/inputs/right_hand_side_si",
    )
    free_dofs = plan.array("free_dofs")
    free_scale = _float_vector(
        scaling.scale_divisors_si[free_dofs],
        shape=(free_count,),
        path="/inputs/free_equation_scale_divisors_si",
    )
    if np.any(free_scale <= 0):  # pragma: no cover - scaling invariant
        _fail(
            "fgmres_scale_invalid",
            "/inputs/free_equation_scale_divisors_si",
            "Free-equation divisors must be positive.",
        )
    initial = _float_vector(
        np.zeros(free_count, dtype="<f8")
        if initial_solution_free is None
        else initial_solution_free,
        shape=(free_count,),
        path="/inputs/initial_solution_free",
    )
    requested_preconditioner = right_preconditioner_profile
    if requested_preconditioner is None:
        requested_preconditioner = (
            CPU_FGMRES_IDENTITY_PRECONDITIONER
            if right_preconditioner_inverse_diagonal is None
            else CPU_FGMRES_DIAGONAL_PRECONDITIONER
        )
    if requested_preconditioner == CPU_FGMRES_IDENTITY_PRECONDITIONER:
        if right_preconditioner_inverse_diagonal is not None:
            _fail(
                "fgmres_preconditioner_profile_mismatch",
                "/parameters/right_preconditioner_profile",
                "Identity profile does not accept an explicit diagonal.",
            )
        preconditioner_profile = CPU_FGMRES_IDENTITY_PRECONDITIONER
        preconditioner = _float_vector(
            np.ones(free_count, dtype="<f8"),
            shape=(free_count,),
            path="/inputs/right_preconditioner_inverse_diagonal",
        )
    elif requested_preconditioner == CPU_FGMRES_DIAGONAL_PRECONDITIONER:
        if right_preconditioner_inverse_diagonal is None:
            _fail(
                "fgmres_preconditioner_missing",
                "/inputs/right_preconditioner_inverse_diagonal",
                "Fixed diagonal profile requires explicit values.",
            )
        preconditioner_profile = CPU_FGMRES_DIAGONAL_PRECONDITIONER
        preconditioner = _float_vector(
            right_preconditioner_inverse_diagonal,
            shape=(free_count,),
            path="/inputs/right_preconditioner_inverse_diagonal",
        )
        if np.any(preconditioner <= 0):
            _fail(
                "fgmres_preconditioner_invalid",
                "/inputs/right_preconditioner_inverse_diagonal",
                "The fixed inverse diagonal must be strictly positive.",
            )
    elif requested_preconditioner == CPU_FGMRES_SCALED_JACOBI_PRECONDITIONER:
        preconditioner_profile = CPU_FGMRES_SCALED_JACOBI_PRECONDITIONER
        derived_preconditioner = _derive_left_scaled_jacobi_inverse_diagonal(
            reduced=reduced,
            global_values=global_values,
            free_scale=free_scale,
        )
        if right_preconditioner_inverse_diagonal is None:
            preconditioner = derived_preconditioner
        else:
            preconditioner = _float_vector(
                right_preconditioner_inverse_diagonal,
                shape=(free_count,),
                path="/inputs/right_preconditioner_inverse_diagonal",
            )
            if not np.array_equal(preconditioner, derived_preconditioner):
                _fail(
                    "fgmres_scaled_jacobi_binding_mismatch",
                    "/inputs/right_preconditioner_inverse_diagonal",
                    "Explicit Jacobi bytes do not match D_free^-1 A_free.",
                )
    else:
        _fail(
            "fgmres_preconditioner_profile_invalid",
            "/parameters/right_preconditioner_profile",
            "Unsupported right-preconditioner profile.",
        )
    solution_uri = _solution_artifact_uri(solution_artifact_uri)

    input_arrays = MappingProxyType(
        {
            "global_csr_values_si": global_values,
            "right_hand_side_si": right_hand_side,
            "free_equation_scale_divisors_si": free_scale,
            "initial_solution_free": initial,
            "right_preconditioner_inverse_diagonal": preconditioner,
        }
    )
    input_descriptors = tuple(
        _vector_descriptor(
            name,
            input_arrays[name],
            equation_scope=(
                "global_csr_pattern_order"
                if name == "global_csr_values_si"
                else "global_equations"
                if name == "right_hand_side_si"
                else "free_equations"
            ),
        )
        for name in _INPUT_NAMES
    )

    execution = _execute_fgmres(
        plan=plan,
        scaling=scaling,
        reduced=reduced,
        global_values=global_values,
        right_hand_side=right_hand_side,
        free_scale=free_scale,
        initial=initial,
        preconditioner=preconditioner,
        max_iterations=maximum,
        restart_length=restart,
        relative_tolerance=relative_tolerance,
        absolute_tolerance=absolute_tolerance,
        breakdown_tolerance=breakdown_tolerance,
        resume_state=_resume_state,
    )
    solution = _float_vector(
        execution["solution_free"],
        shape=(free_count,),
        path="/solution_artifact",
    )
    solution_descriptor = _vector_descriptor(
        "solution_free",
        solution,
        equation_scope="free_equations",
        artifact_uri=solution_uri,
    )
    provisional = CPUFGMRESRun(
        schema_version=CPU_FGMRES_SCHEMA_VERSION,
        run_hash=_HASH_ZERO,
        execution_plan_hash=plan.plan_hash,
        scaling_hash=scaling.scaling_hash,
        reduced_csr_identity_hash=reduced.identity_hash,
        operator_numeric_values_hash=reduced.operator_numeric_values_hash,
        dof_count=plan.dof_count,
        free_count=free_count,
        global_csr_nnz=global_nnz,
        preconditioner_profile=preconditioner_profile,
        max_iterations=maximum,
        restart_length=restart,
        relative_tolerance_scaled_l2=relative_tolerance,
        absolute_tolerance_scaled_l2=absolute_tolerance,
        arnoldi_breakdown_tolerance=breakdown_tolerance,
        convergence_threshold_scaled_l2=execution["convergence_threshold"],
        iteration_count=execution["iteration_count"],
        matvec_count=execution["matvec_count"],
        terminal_reason=execution["terminal_reason"],
        converged=execution["converged"],
        input_descriptors=input_descriptors,
        observations=execution["observations"],
        restart_history=execution["restart_history"],
        solution_descriptor=solution_descriptor,
        _solution_free=solution,
        _input_arrays=input_arrays,
        _execution_plan=plan,
        _scaling=scaling,
        _reduced_csr=reduced,
        _restart_snapshots=execution["restart_snapshots"],
    )
    run = replace(provisional, run_hash=_run_hash(provisional))
    return validate_cpu_fgmres_run(run)


def validate_cpu_fgmres_run(run: CPUFGMRESRun) -> CPUFGMRESRun:
    if type(run) is not CPUFGMRESRun:
        _fail("fgmres_run_type_invalid", "/", "Expected CPUFGMRESRun.")
    plan = validate_execution_plan(run._execution_plan)
    validate_equation_scaling_binding(plan, scaling=run._scaling)
    reduced = validate_execution_plan_reduced_csr(run._reduced_csr, execution_plan=plan)
    if not isinstance(run._input_arrays, MappingProxyType):
        _fail("fgmres_input_arrays_mutable", "/inputs", "Input map is mutable.")
    if tuple(run._input_arrays) != _INPUT_NAMES:
        _fail("fgmres_input_set_invalid", "/inputs", "Input vector set is invalid.")
    if (
        type(run.input_descriptors) is not tuple
        or tuple(row.name for row in run.input_descriptors) != _INPUT_NAMES
        or any(
            type(row) is not CPUFGMRESVectorDescriptor for row in run.input_descriptors
        )
    ):
        _fail(
            "fgmres_input_descriptor_set_invalid",
            "/inputs",
            "Input descriptors are invalid.",
        )
    scopes = {
        "global_csr_values_si": "global_csr_pattern_order",
        "right_hand_side_si": "global_equations",
        "free_equation_scale_divisors_si": "free_equations",
        "initial_solution_free": "free_equations",
        "right_preconditioner_inverse_diagonal": "free_equations",
    }
    for descriptor in run.input_descriptors:
        array = run._input_arrays[descriptor.name]
        _validate_float_array(array, path=f"/inputs/{descriptor.name}")
        expected = _vector_descriptor(
            descriptor.name,
            array,
            equation_scope=scopes[descriptor.name],
        )
        if descriptor != expected:
            _fail(
                "fgmres_input_descriptor_mismatch",
                f"/inputs/{descriptor.name}",
                "Input descriptor does not match immutable bytes.",
            )
    if (
        run.execution_plan_hash != plan.plan_hash
        or run.scaling_hash != run._scaling.scaling_hash
        or run.reduced_csr_identity_hash != reduced.identity_hash
        or run.operator_numeric_values_hash != reduced.operator_numeric_values_hash
        or run.dof_count != plan.dof_count
        or run.free_count != reduced.free_count
        or run.global_csr_nnz != plan.array("csr_column_indices").size
    ):
        _fail(
            "fgmres_source_binding_mismatch",
            "/source",
            "Run identifies different source contracts.",
        )
    if (
        array_data_hash(run._input_arrays["global_csr_values_si"])
        != reduced.operator_numeric_values_hash
    ):
        _fail(
            "fgmres_operator_numeric_values_hash_mismatch",
            "/inputs/global_csr_values_si/data_hash",
            "Operator numeric bytes are stale.",
        )
    expected_scale = run._scaling.scale_divisors_si[plan.array("free_dofs")]
    if not np.array_equal(
        run._input_arrays["free_equation_scale_divisors_si"], expected_scale
    ):
        _fail(
            "fgmres_free_scale_mismatch",
            "/inputs/free_equation_scale_divisors_si",
            "Free-equation scale vector is stale.",
        )
    if run.preconditioner_profile == CPU_FGMRES_IDENTITY_PRECONDITIONER:
        if not np.array_equal(
            run._input_arrays["right_preconditioner_inverse_diagonal"],
            np.ones(run.free_count, dtype="<f8"),
        ):
            _fail(
                "fgmres_preconditioner_profile_mismatch",
                "/solver/preconditioner_profile",
                "Identity profile has non-identity values.",
            )
    elif run.preconditioner_profile == CPU_FGMRES_DIAGONAL_PRECONDITIONER:
        if np.any(run._input_arrays["right_preconditioner_inverse_diagonal"] <= 0):
            _fail(
                "fgmres_preconditioner_invalid",
                "/inputs/right_preconditioner_inverse_diagonal",
                "The fixed inverse diagonal must be positive.",
            )
    elif run.preconditioner_profile == CPU_FGMRES_SCALED_JACOBI_PRECONDITIONER:
        expected_preconditioner = _derive_left_scaled_jacobi_inverse_diagonal(
            reduced=reduced,
            global_values=run._input_arrays["global_csr_values_si"],
            free_scale=run._input_arrays["free_equation_scale_divisors_si"],
        )
        if not np.array_equal(
            run._input_arrays["right_preconditioner_inverse_diagonal"],
            expected_preconditioner,
        ):
            _fail(
                "fgmres_scaled_jacobi_binding_mismatch",
                "/inputs/right_preconditioner_inverse_diagonal",
                "Stored Jacobi bytes do not match D_free^-1 A_free.",
            )
    else:
        _fail(
            "fgmres_preconditioner_profile_invalid",
            "/solver/preconditioner_profile",
            "Unsupported preconditioner profile.",
        )
    _validate_float_array(run._solution_free, path="/solution_artifact")
    if run._solution_free.shape != (run.free_count,):
        _fail(
            "fgmres_solution_shape_invalid",
            "/solution_artifact/shape",
            "Solution must match the free-equation count.",
        )
    expected_solution_descriptor = _vector_descriptor(
        "solution_free",
        run._solution_free,
        equation_scope="free_equations",
        artifact_uri=run.solution_descriptor.artifact_uri,
    )
    if run.solution_descriptor != expected_solution_descriptor:
        _fail(
            "fgmres_solution_descriptor_mismatch",
            "/solution_artifact",
            "Solution descriptor does not match immutable bytes.",
        )
    if type(run._restart_snapshots) is not tuple:
        _fail(
            "fgmres_restart_snapshot_set_invalid",
            "/restart_snapshots",
            "Restart snapshots must be immutable.",
        )
    restarted_records = {
        record.restart_index: record
        for record in run.restart_history
        if record.disposition == "restarted"
    }
    seen_snapshot_indices: set[int] = set()
    observation_by_hash = {
        observation.observation_hash: observation
        for observation in run.observations
    }
    free_dofs = [int(value) for value in plan.array("free_dofs")]
    row_ptr = [int(value) for value in reduced.array("free_csr_row_ptr")]
    columns = [
        int(value) for value in reduced.array("free_csr_column_indices")
    ]
    positions = [
        int(value)
        for value in reduced.array("free_csr_global_value_indices")
    ]
    reduced_values = [
        float(run._input_arrays["global_csr_values_si"][position])
        for position in positions
    ]
    rhs_free = [
        float(run._input_arrays["right_hand_side_si"][equation])
        for equation in free_dofs
    ]
    for snapshot in run._restart_snapshots:
        if type(snapshot) is not _CPUFGMRESRestartSnapshot:
            _fail(
                "fgmres_restart_snapshot_type_invalid",
                "/restart_snapshots",
                "Restart snapshot type is invalid.",
            )
        record = restarted_records.get(snapshot.restart_index)
        if record is None or snapshot.restart_index in seen_snapshot_indices:
            _fail(
                "fgmres_restart_snapshot_boundary_invalid",
                "/restart_snapshots",
                "Snapshot does not identify one completed restart boundary.",
            )
        seen_snapshot_indices.add(snapshot.restart_index)
        _validate_float_array(
            snapshot.solution_free,
            path=f"/restart_snapshots/{snapshot.restart_index}/solution_free",
        )
        _validate_float_array(
            snapshot.scaled_residual_free,
            path=(
                f"/restart_snapshots/{snapshot.restart_index}/"
                "scaled_residual_free"
            ),
        )
        end_observation = observation_by_hash.get(record.end_observation_hash)
        recomputed_observation, recomputed_scaled = _observe(
            plan=plan,
            scaling=run._scaling,
            free_dofs=free_dofs,
            row_ptr=row_ptr,
            columns=columns,
            reduced_values=reduced_values,
            rhs_free=rhs_free,
            solution=[float(value) for value in snapshot.solution_free],
            iteration=snapshot.iteration_count,
            restart_index=snapshot.restart_index,
            inner_iteration=record.iteration_count,
        )
        if (
            snapshot.solution_free.shape != (run.free_count,)
            or snapshot.scaled_residual_free.shape != (run.free_count,)
            or snapshot.iteration_count != record.end_iteration
            or snapshot.matvec_count != 1 + 2 * record.end_iteration
            or end_observation is None
            or array_data_hash(snapshot.solution_free)
            != end_observation.solution_free_data_hash
            or recomputed_observation != end_observation
            or not np.array_equal(
                immutable_array(recomputed_scaled, dtype="<f8"),
                snapshot.scaled_residual_free,
            )
        ):
            _fail(
                "fgmres_restart_snapshot_binding_invalid",
                f"/restart_snapshots/{snapshot.restart_index}",
                "Snapshot bytes or counters do not match the restart boundary.",
            )
    validate_cpu_fgmres_manifest(_run_payload(run, include_run_hash=True))
    if run.run_hash != _run_hash(run):
        _fail("fgmres_run_hash_mismatch", "/run_hash", "Run hash is stale.")
    return run


def replay_cpu_fgmres_run(
    run: CPUFGMRESRun,
    *,
    node_coordinates_m: Any,
    reference_equation_load_si: Any,
) -> CPUFGMRESRun:
    """Re-execute the exact recurrence and compare every compact checkpoint."""

    validated = validate_cpu_fgmres_run(run)
    replayed = run_cpu_fgmres(
        execution_plan=validated._execution_plan,
        scaling=validated._scaling,
        reduced_csr=validated._reduced_csr,
        node_coordinates_m=node_coordinates_m,
        reference_equation_load_si=reference_equation_load_si,
        global_csr_values_si=validated._input_arrays["global_csr_values_si"],
        right_hand_side_si=validated._input_arrays["right_hand_side_si"],
        solution_artifact_uri=str(validated.solution_descriptor.artifact_uri),
        max_iterations=validated.max_iterations,
        restart_length=validated.restart_length,
        relative_tolerance_scaled_l2=validated.relative_tolerance_scaled_l2,
        absolute_tolerance_scaled_l2=validated.absolute_tolerance_scaled_l2,
        arnoldi_breakdown_tolerance=validated.arnoldi_breakdown_tolerance,
        initial_solution_free=validated._input_arrays["initial_solution_free"],
        right_preconditioner_inverse_diagonal=(
            None
            if validated.preconditioner_profile == CPU_FGMRES_IDENTITY_PRECONDITIONER
            else validated._input_arrays["right_preconditioner_inverse_diagonal"]
        ),
        right_preconditioner_profile=validated.preconditioner_profile,
    )
    if replayed.to_manifest() != validated.to_manifest() or not np.array_equal(
        replayed.solution_free, validated.solution_free
    ):
        _fail(
            "fgmres_replay_mismatch",
            "/",
            "Replayed recurrence does not match the run receipt.",
        )
    return validated


def write_cpu_fgmres_solution_artifact(
    run: CPUFGMRESRun, output_file: str | Path
) -> Path:
    """Write the canonical solution bytes once and validate the stored bytes."""

    validated = validate_cpu_fgmres_run(run)
    target = Path(output_file)
    if target.name != CPU_FGMRES_SOLUTION_FILENAME:
        _fail(
            "fgmres_solution_filename_invalid",
            "/solution_artifact/artifact_uri",
            f"Output filename must be {CPU_FGMRES_SOLUTION_FILENAME}.",
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        _fail(
            "fgmres_solution_target_exists",
            "/solution_artifact",
            f"Refusing to overwrite existing artifact: {target}",
        )
    created = False
    try:
        with target.open("xb") as handle:
            created = True
            handle.write(memoryview(validated.solution_free).cast("B"))
        validate_cpu_fgmres_solution_bytes(validated, target.read_bytes())
    except Exception:
        if created:
            target.unlink(missing_ok=True)
        raise
    return target


def validate_cpu_fgmres_solution_bytes(
    run: CPUFGMRESRun, data: bytes | bytearray | memoryview
) -> None:
    validated = validate_cpu_fgmres_run(run)
    raw = bytes(data)
    descriptor = validated.solution_descriptor
    if len(raw) != descriptor.byte_length:
        _fail(
            "fgmres_solution_length_mismatch",
            "/solution_artifact/byte_length",
            "Solution byte length is stale.",
        )
    values = _float_vector(
        np.frombuffer(raw, dtype="<f8"),
        shape=descriptor.shape,
        path="/solution_artifact",
    )
    expected = _vector_descriptor(
        "solution_free",
        values,
        equation_scope="free_equations",
        artifact_uri=descriptor.artifact_uri,
    )
    if expected != descriptor:
        _fail(
            "fgmres_solution_hash_mismatch",
            "/solution_artifact",
            "Solution bytes do not match the descriptor.",
        )


def validate_cpu_fgmres_manifest(payload: Any) -> Mapping[str, Any]:
    errors = sorted(
        _schema_validator().iter_errors(payload),
        key=lambda error: tuple(str(value) for value in error.absolute_path),
    )
    if errors:
        error = errors[0]
        path = "/" + "/".join(str(value) for value in error.absolute_path)
        _fail("fgmres_schema_invalid", path or "/", error.message)
    if not isinstance(payload, Mapping):  # pragma: no cover - schema invariant
        _fail("fgmres_manifest_type_invalid", "/", "Expected an object.")

    source = payload["source"]
    descriptors = payload["inputs"]
    expected_shapes = {
        "global_csr_values_si": [source["global_csr_nnz"]],
        "right_hand_side_si": [source["dof_count"]],
        "free_equation_scale_divisors_si": [source["free_count"]],
        "initial_solution_free": [source["free_count"]],
        "right_preconditioner_inverse_diagonal": [source["free_count"]],
    }
    expected_scopes = {
        "global_csr_values_si": "global_csr_pattern_order",
        "right_hand_side_si": "global_equations",
        "free_equation_scale_divisors_si": "free_equations",
        "initial_solution_free": "free_equations",
        "right_preconditioner_inverse_diagonal": "free_equations",
    }
    for name in _INPUT_NAMES:
        descriptor = descriptors[name]
        if (
            descriptor["name"] != name
            or descriptor["shape"] != expected_shapes[name]
            or descriptor["byte_length"] != expected_shapes[name][0] * 8
            or descriptor["equation_scope"] != expected_scopes[name]
        ):
            _fail(
                "fgmres_input_descriptor_semantics_invalid",
                f"/inputs/{name}",
                "Input descriptor shape, scope, or byte length is stale.",
            )
    if (
        descriptors["global_csr_values_si"]["data_hash"]
        != source["operator_numeric_values_hash"]
    ):
        _fail(
            "fgmres_operator_numeric_values_hash_mismatch",
            "/inputs/global_csr_values_si/data_hash",
            "Operator numeric hash is stale.",
        )

    parameters = payload["parameters"]
    if parameters["restart_length"] > source["free_count"]:
        _fail(
            "fgmres_restart_length_invalid",
            "/parameters/restart_length",
            "Restart length exceeds the free-equation count.",
        )
    if (
        parameters["relative_tolerance_scaled_l2"] == 0.0
        and parameters["absolute_tolerance_scaled_l2"] == 0.0
    ):
        _fail(
            "fgmres_tolerance_invalid",
            "/parameters",
            "At least one convergence tolerance must be positive.",
        )
    observations = payload["observations"]
    terminal = payload["terminal"]
    if len(observations) != terminal["iteration_count"] + 1:
        _fail(
            "fgmres_observation_count_invalid",
            "/observations",
            "There must be one initial and one observation per iteration.",
        )
    for expected_iteration, observation in enumerate(observations):
        if observation["iteration"] != expected_iteration:
            _fail(
                "fgmres_observation_order_invalid",
                f"/observations/{expected_iteration}/iteration",
                "Observation iterations must be contiguous.",
            )
        without_hash = dict(observation)
        claimed_hash = without_hash.pop("observation_hash")
        if claimed_hash != canonical_hash(without_hash):
            _fail(
                "fgmres_observation_hash_mismatch",
                f"/observations/{expected_iteration}/observation_hash",
                "Observation hash is stale.",
            )
        norms = observation["norms"]
        if any(not math.isfinite(value) or value < 0.0 for value in norms.values()):
            _fail(
                "fgmres_observation_metric_invalid",
                f"/observations/{expected_iteration}/norms",
                "Residual norms must be finite and nonnegative.",
            )
        governing = observation["governing"]
        equation = governing["equation"]
        if (
            equation >= source["dof_count"]
            or governing["dof"] != EXECUTION_PLAN_DOF_COMPONENTS[equation % 6]
        ):
            _fail(
                "fgmres_governing_dof_invalid",
                f"/observations/{expected_iteration}/governing",
                "Governing equation and DOF are inconsistent.",
            )
    if observations[0]["restart_index"] != 0 or observations[0]["inner_iteration"] != 0:
        _fail(
            "fgmres_initial_observation_invalid",
            "/observations/0",
            "Initial observation must be restart 0, inner iteration 0.",
        )

    histories = payload["restart_history"]
    if not histories:
        _fail(
            "fgmres_restart_history_empty",
            "/restart_history",
            "At least one terminal restart record is required.",
        )
    observation_by_hash = {row["observation_hash"]: row for row in observations}
    previous_end = 0
    for index, record in enumerate(histories):
        if (
            record["restart_index"] != index
            or record["start_iteration"] != previous_end
        ):
            _fail(
                "fgmres_restart_history_order_invalid",
                f"/restart_history/{index}",
                "Restart records must be contiguous and ordered.",
            )
        if (
            record["iteration_count"]
            != record["end_iteration"] - record["start_iteration"]
            or record["start_observation_hash"] not in observation_by_hash
            or record["end_observation_hash"] not in observation_by_hash
            or observation_by_hash[record["start_observation_hash"]]["iteration"]
            != record["start_iteration"]
            or observation_by_hash[record["end_observation_hash"]]["iteration"]
            != record["end_iteration"]
        ):
            _fail(
                "fgmres_restart_history_semantics_invalid",
                f"/restart_history/{index}",
                "Restart boundaries or checkpoint hashes are stale.",
            )
        without_hash = dict(record)
        claimed_hash = without_hash.pop("restart_hash")
        if claimed_hash != canonical_hash(without_hash):
            _fail(
                "fgmres_restart_hash_mismatch",
                f"/restart_history/{index}/restart_hash",
                "Restart record hash is stale.",
            )
        if index < len(histories) - 1 and record["disposition"] != "restarted":
            _fail(
                "fgmres_restart_disposition_invalid",
                f"/restart_history/{index}/disposition",
                "Only nonterminal records may restart.",
            )
        if record["iteration_count"] > parameters["restart_length"] or (
            record["disposition"] == "restarted"
            and record["iteration_count"] != parameters["restart_length"]
        ):
            _fail(
                "fgmres_restart_length_semantics_invalid",
                f"/restart_history/{index}/iteration_count",
                "Restart record does not match the configured restart length.",
            )
        for iteration in range(
            record["start_iteration"] + 1, record["end_iteration"] + 1
        ):
            observation = observations[iteration]
            if (
                observation["restart_index"] != index
                or observation["inner_iteration"]
                != iteration - record["start_iteration"]
            ):
                _fail(
                    "fgmres_observation_restart_index_invalid",
                    f"/observations/{iteration}",
                    "Observation does not match its restart-cycle position.",
                )
        previous_end = record["end_iteration"]
    if previous_end != terminal["iteration_count"]:
        _fail(
            "fgmres_restart_history_terminal_mismatch",
            "/restart_history",
            "Restart history does not reach the terminal iteration.",
        )
    if histories[-1]["disposition"] != terminal["reason"]:
        _fail(
            "fgmres_restart_history_terminal_mismatch",
            "/restart_history/-1/disposition",
            "Final restart disposition does not match the terminal reason.",
        )

    converged_reasons = {
        "initial_residual_satisfied",
        "converged_scaled_residual",
    }
    if terminal["converged"] != (terminal["reason"] in converged_reasons):
        _fail(
            "fgmres_terminal_convergence_invalid",
            "/terminal",
            "Terminal reason and converged flag disagree.",
        )
    final_observation = observations[-1]
    if terminal["final_observation_hash"] != final_observation["observation_hash"]:
        _fail(
            "fgmres_terminal_observation_mismatch",
            "/terminal/final_observation_hash",
            "Terminal observation hash is stale.",
        )
    final_scaled_l2 = final_observation["norms"]["scaled_l2"]
    threshold = terminal["convergence_threshold_scaled_l2"]
    expected_threshold = max(
        parameters["absolute_tolerance_scaled_l2"],
        parameters["relative_tolerance_scaled_l2"]
        * observations[0]["norms"]["scaled_l2"],
    )
    if threshold != expected_threshold:
        _fail(
            "fgmres_terminal_threshold_invalid",
            "/terminal/convergence_threshold_scaled_l2",
            "Convergence threshold is stale.",
        )
    if terminal["converged"] != (final_scaled_l2 <= threshold):
        _fail(
            "fgmres_terminal_threshold_invalid",
            "/terminal",
            "Terminal convergence does not match the exact residual threshold.",
        )
    if (
        terminal["reason"] == "max_iterations"
        and terminal["iteration_count"] != parameters["max_iterations"]
    ):
        _fail(
            "fgmres_max_iterations_terminal_invalid",
            "/terminal/iteration_count",
            "Max-iterations terminal state stopped at another count.",
        )
    if terminal["matvec_count"] != 1 + 2 * terminal["iteration_count"]:
        _fail(
            "fgmres_matvec_count_invalid",
            "/terminal/matvec_count",
            "Matvec count does not match exact-observation recurrence accounting.",
        )
    if (
        terminal["reason"] == "initial_residual_satisfied"
        and terminal["iteration_count"] != 0
    ) or (
        terminal["reason"] == "converged_scaled_residual"
        and terminal["iteration_count"] == 0
    ):
        _fail(
            "fgmres_terminal_reason_invalid",
            "/terminal/reason",
            "Initial and iterative convergence reasons are inconsistent.",
        )

    solution = payload["solution_artifact"]
    if (
        solution["name"] != "solution_free"
        or solution["shape"] != [source["free_count"]]
        or solution["byte_length"] != source["free_count"] * 8
        or solution["equation_scope"] != "free_equations"
        or not solution["artifact_uri"].endswith(f"/{CPU_FGMRES_SOLUTION_FILENAME}")
        or solution["data_hash"] != final_observation["solution_free_data_hash"]
        or descriptors["initial_solution_free"]["data_hash"]
        != observations[0]["solution_free_data_hash"]
    ):
        _fail(
            "fgmres_solution_descriptor_semantics_invalid",
            "/solution_artifact",
            "Solution descriptor or checkpoint binding is stale.",
        )
    without_hash = dict(payload)
    claimed_run_hash = without_hash.pop("run_hash")
    if claimed_run_hash != canonical_hash(without_hash):
        _fail("fgmres_run_hash_mismatch", "/run_hash", "Run hash is stale.")
    return payload


def _derive_left_scaled_jacobi_inverse_diagonal(
    *,
    reduced: ExecutionPlanReducedCSR,
    global_values: np.ndarray,
    free_scale: np.ndarray,
) -> np.ndarray:
    row_ptr = reduced.array("free_csr_row_ptr")
    columns = reduced.array("free_csr_column_indices")
    positions = reduced.array("free_csr_global_value_indices")
    inverse: list[float] = []
    for row in range(reduced.free_count):
        diagonal_positions = [
            int(position)
            for position in range(int(row_ptr[row]), int(row_ptr[row + 1]))
            if int(columns[position]) == row
        ]
        if not diagonal_positions:
            _fail(
                "fgmres_scaled_jacobi_diagonal_missing",
                f"/reduced_csr/row/{row}",
                "Left-scaled Jacobi requires one structural diagonal entry.",
            )
        if len(diagonal_positions) != 1:
            _fail(
                "fgmres_scaled_jacobi_diagonal_duplicate",
                f"/reduced_csr/row/{row}",
                "Left-scaled Jacobi requires exactly one diagonal entry.",
            )
        diagonal = float(global_values[int(positions[diagonal_positions[0]])])
        scale = float(free_scale[row])
        scaled_diagonal = diagonal / scale
        if not math.isfinite(scaled_diagonal) or scaled_diagonal <= 0.0:
            _fail(
                "fgmres_scaled_jacobi_diagonal_invalid",
                f"/inputs/global_csr_values_si/diagonal/{row}",
                "Left-scaled Jacobi diagonal must be finite and positive.",
            )
        value = 1.0 / scaled_diagonal
        if not math.isfinite(value) or value <= 0.0:
            _fail(
                "fgmres_scaled_jacobi_inverse_invalid",
                f"/inputs/right_preconditioner_inverse_diagonal/{row}",
                "Derived Jacobi inverse must be finite and positive.",
            )
        inverse.append(value)
    return _float_vector(
        inverse,
        shape=(reduced.free_count,),
        path="/inputs/right_preconditioner_inverse_diagonal",
    )


def _execute_fgmres(
    *,
    plan: ExecutionPlan,
    scaling: EquationScaling,
    reduced: ExecutionPlanReducedCSR,
    global_values: np.ndarray,
    right_hand_side: np.ndarray,
    free_scale: np.ndarray,
    initial: np.ndarray,
    preconditioner: np.ndarray,
    max_iterations: int,
    restart_length: int,
    relative_tolerance: float,
    absolute_tolerance: float,
    breakdown_tolerance: float,
    resume_state: _CPUFGMRESResumeState | None,
) -> dict[str, Any]:
    free_dofs = [int(value) for value in plan.array("free_dofs")]
    row_ptr = [int(value) for value in reduced.array("free_csr_row_ptr")]
    columns = [int(value) for value in reduced.array("free_csr_column_indices")]
    positions = [int(value) for value in reduced.array("free_csr_global_value_indices")]
    reduced_values = [float(global_values[position]) for position in positions]
    rhs_free = [float(right_hand_side[index]) for index in free_dofs]
    scale_free = [float(value) for value in free_scale]
    preconditioner_values = [float(value) for value in preconditioner]
    restart_snapshots: list[_CPUFGMRESRestartSnapshot] = []
    if resume_state is None:
        current = [float(value) for value in initial]
        matvec_count = 0
        initial_observation, current_scaled_recurrence = _observe(
            plan=plan,
            scaling=scaling,
            free_dofs=free_dofs,
            row_ptr=row_ptr,
            columns=columns,
            reduced_values=reduced_values,
            rhs_free=rhs_free,
            solution=current,
            iteration=0,
            restart_index=0,
            inner_iteration=0,
        )
        matvec_count += 1
        observations = [initial_observation]
        initial_norm = initial_observation.scaled_l2
        convergence_threshold = max(
            absolute_tolerance,
            relative_tolerance * initial_norm,
        )
        if initial_norm <= convergence_threshold:
            terminal_reason = "initial_residual_satisfied"
            history = (
                _make_restart_record(
                    restart_index=0,
                    start=initial_observation,
                    end=initial_observation,
                    disposition=terminal_reason,
                ),
            )
            return {
                "solution_free": current,
                "convergence_threshold": convergence_threshold,
                "iteration_count": 0,
                "matvec_count": matvec_count,
                "terminal_reason": terminal_reason,
                "converged": True,
                "observations": tuple(observations),
                "restart_history": history,
                "restart_snapshots": tuple(restart_snapshots),
            }
        total_iterations = 0
        restart_index = 0
        histories: list[CPUFGMRESRestartRecord] = []
    else:
        validated_resume = _validate_resume_state(
            resume_state,
            plan=plan,
            scaling=scaling,
            free_dofs=free_dofs,
            row_ptr=row_ptr,
            columns=columns,
            reduced_values=reduced_values,
            rhs_free=rhs_free,
            initial=initial,
            max_iterations=max_iterations,
            restart_length=restart_length,
            relative_tolerance=relative_tolerance,
            absolute_tolerance=absolute_tolerance,
        )
        current = [float(value) for value in validated_resume.solution_free]
        current_scaled_recurrence = [
            float(value) for value in validated_resume.scaled_residual_free
        ]
        matvec_count = validated_resume.matvec_count
        observations = list(validated_resume.observations)
        convergence_threshold = (
            validated_resume.convergence_threshold_scaled_l2
        )
        total_iterations = validated_resume.iteration_count
        restart_index = validated_resume.next_restart_index
        histories = list(validated_resume.restart_history)
    terminal_reason: str | None = None
    while terminal_reason is None:
        cycle_start = observations[-1]
        cycle_solution = list(current)
        beta = _stable_l2(current_scaled_recurrence)
        if beta <= breakdown_tolerance:
            terminal_reason = "arnoldi_breakdown"
            histories.append(
                _make_restart_record(
                    restart_index=restart_index,
                    start=cycle_start,
                    end=cycle_start,
                    disposition=terminal_reason,
                )
            )
            break
        capacity = min(restart_length, max_iterations - total_iterations)
        basis_v: list[list[float]] = [
            [value / beta for value in current_scaled_recurrence]
        ]
        basis_z: list[list[float]] = []
        hessenberg = [[0.0] * capacity for _ in range(capacity + 1)]
        cosines = [0.0] * capacity
        sines = [0.0] * capacity
        projected_rhs = [0.0] * (capacity + 1)
        projected_rhs[0] = beta
        last_observation = cycle_start

        for inner_index in range(capacity):
            z = [
                preconditioner_values[index] * basis_v[inner_index][index]
                for index in range(reduced.free_count)
            ]
            _require_finite_vector(z, "/recurrence/preconditioned_basis")
            basis_z.append(z)
            w = _left_scaled_matvec(
                row_ptr,
                columns,
                reduced_values,
                z,
                scale_free,
            )
            matvec_count += 1
            for _pass in range(2):
                for basis_index in range(inner_index + 1):
                    coefficient = _stable_dot(basis_v[basis_index], w)
                    hessenberg[basis_index][inner_index] = math.fsum(
                        (
                            hessenberg[basis_index][inner_index],
                            coefficient,
                        )
                    )
                    w = [
                        w[index] - coefficient * basis_v[basis_index][index]
                        for index in range(reduced.free_count)
                    ]
                    _require_finite_vector(w, "/recurrence/orthogonalized_basis")
            next_norm = _stable_l2(w)
            hessenberg[inner_index + 1][inner_index] = next_norm
            if next_norm > breakdown_tolerance:
                basis_v.append([value / next_norm for value in w])

            for prior in range(inner_index):
                upper = hessenberg[prior][inner_index]
                lower = hessenberg[prior + 1][inner_index]
                hessenberg[prior][inner_index] = (
                    cosines[prior] * upper + sines[prior] * lower
                )
                hessenberg[prior + 1][inner_index] = (
                    -sines[prior] * upper + cosines[prior] * lower
                )
            diagonal = hessenberg[inner_index][inner_index]
            subdiagonal = hessenberg[inner_index + 1][inner_index]
            radius = math.hypot(diagonal, subdiagonal)
            if not math.isfinite(radius) or radius <= breakdown_tolerance:
                total_iterations += 1
                observation, current_scaled_recurrence = _observe(
                    plan=plan,
                    scaling=scaling,
                    free_dofs=free_dofs,
                    row_ptr=row_ptr,
                    columns=columns,
                    reduced_values=reduced_values,
                    rhs_free=rhs_free,
                    solution=current,
                    iteration=total_iterations,
                    restart_index=restart_index,
                    inner_iteration=inner_index + 1,
                )
                matvec_count += 1
                observations.append(observation)
                last_observation = observation
                terminal_reason = "arnoldi_breakdown"
                break
            cosine = diagonal / radius
            sine = subdiagonal / radius
            cosines[inner_index] = cosine
            sines[inner_index] = sine
            hessenberg[inner_index][inner_index] = radius
            hessenberg[inner_index + 1][inner_index] = 0.0
            projected_value = projected_rhs[inner_index]
            projected_rhs[inner_index] = cosine * projected_value
            projected_rhs[inner_index + 1] = -sine * projected_value
            coefficients = _back_substitute(
                hessenberg,
                projected_rhs,
                count=inner_index + 1,
                breakdown_tolerance=breakdown_tolerance,
            )
            if coefficients is None:
                candidate = list(current)
                terminal_reason = "arnoldi_breakdown"
            else:
                candidate = [
                    math.fsum(
                        [cycle_solution[row]]
                        + [
                            basis_z[column][row] * coefficients[column]
                            for column in range(inner_index + 1)
                        ]
                    )
                    for row in range(reduced.free_count)
                ]
                _require_finite_vector(candidate, "/recurrence/candidate_solution")
            total_iterations += 1
            observation, candidate_scaled_recurrence = _observe(
                plan=plan,
                scaling=scaling,
                free_dofs=free_dofs,
                row_ptr=row_ptr,
                columns=columns,
                reduced_values=reduced_values,
                rhs_free=rhs_free,
                solution=candidate,
                iteration=total_iterations,
                restart_index=restart_index,
                inner_iteration=inner_index + 1,
            )
            matvec_count += 1
            observations.append(observation)
            last_observation = observation
            current = candidate
            current_scaled_recurrence = candidate_scaled_recurrence
            if observation.scaled_l2 <= convergence_threshold:
                terminal_reason = "converged_scaled_residual"
            elif (
                terminal_reason == "arnoldi_breakdown"
                or next_norm <= breakdown_tolerance
            ):
                terminal_reason = "arnoldi_breakdown"
            elif total_iterations == max_iterations:
                terminal_reason = "max_iterations"
            if terminal_reason is not None:
                break

        disposition = terminal_reason or "restarted"
        record = _make_restart_record(
            restart_index=restart_index,
            start=cycle_start,
            end=last_observation,
            disposition=disposition,
        )
        histories.append(record)
        if terminal_reason is None:
            restart_snapshots.append(
                _CPUFGMRESRestartSnapshot(
                    restart_index=restart_index,
                    iteration_count=total_iterations,
                    matvec_count=matvec_count,
                    solution_free=immutable_array(current, dtype="<f8"),
                    scaled_residual_free=immutable_array(
                        current_scaled_recurrence,
                        dtype="<f8",
                    ),
                )
            )
            restart_index += 1

    return {
        "solution_free": current,
        "convergence_threshold": convergence_threshold,
        "iteration_count": total_iterations,
        "matvec_count": matvec_count,
        "terminal_reason": terminal_reason,
        "converged": terminal_reason == "converged_scaled_residual",
        "observations": tuple(observations),
        "restart_history": tuple(histories),
        "restart_snapshots": tuple(restart_snapshots),
    }


def _validate_resume_state(
    state: _CPUFGMRESResumeState,
    *,
    plan: ExecutionPlan,
    scaling: EquationScaling,
    free_dofs: list[int],
    row_ptr: list[int],
    columns: list[int],
    reduced_values: list[float],
    rhs_free: list[float],
    initial: np.ndarray,
    max_iterations: int,
    restart_length: int,
    relative_tolerance: float,
    absolute_tolerance: float,
) -> _CPUFGMRESResumeState:
    if type(state) is not _CPUFGMRESResumeState:
        _fail(
            "fgmres_resume_state_type_invalid",
            "/resume",
            "Expected an internal restart-boundary resume state.",
        )
    if (
        type(state.iteration_count) is not int
        or state.iteration_count <= 0
        or state.iteration_count >= max_iterations
        or type(state.matvec_count) is not int
        or state.matvec_count != 1 + 2 * state.iteration_count
        or type(state.next_restart_index) is not int
        or state.next_restart_index <= 0
    ):
        _fail(
            "fgmres_resume_counter_invalid",
            "/resume/boundary",
            "Resume counters must identify a nonterminal restart boundary.",
        )
    if (
        type(state.observations) is not tuple
        or len(state.observations) != state.iteration_count + 1
        or any(type(row) is not CPUFGMRESObservation for row in state.observations)
        or type(state.restart_history) is not tuple
        or len(state.restart_history) != state.next_restart_index
        or any(
            type(row) is not CPUFGMRESRestartRecord
            for row in state.restart_history
        )
    ):
        _fail(
            "fgmres_resume_prefix_invalid",
            "/resume",
            "Resume observations and restart history are incomplete.",
        )
    _validate_float_array(state.solution_free, path="/resume/solution_free")
    _validate_float_array(
        state.scaled_residual_free,
        path="/resume/scaled_residual_free",
    )
    free_count = len(free_dofs)
    if (
        state.solution_free.shape != (free_count,)
        or state.scaled_residual_free.shape != (free_count,)
    ):
        _fail(
            "fgmres_resume_vector_shape_invalid",
            "/resume",
            "Resume vectors must match the free-equation count.",
        )

    observation_by_hash: dict[str, CPUFGMRESObservation] = {}
    for expected_iteration, observation in enumerate(state.observations):
        if (
            observation.iteration != expected_iteration
            or observation.observation_hash
            != canonical_hash(_observation_payload(observation, include_hash=False))
        ):
            _fail(
                "fgmres_resume_observation_invalid",
                f"/resume/observations/{expected_iteration}",
                "Resume observation order or hash is stale.",
            )
        observation_by_hash[observation.observation_hash] = observation

    previous_end = 0
    for expected_index, record in enumerate(state.restart_history):
        start = observation_by_hash.get(record.start_observation_hash)
        end = observation_by_hash.get(record.end_observation_hash)
        if (
            record.restart_index != expected_index
            or record.start_iteration != previous_end
            or record.end_iteration
            != record.start_iteration + restart_length
            or record.iteration_count != restart_length
            or record.disposition != "restarted"
            or start is None
            or end is None
            or start.iteration != record.start_iteration
            or end.iteration != record.end_iteration
            or record.restart_hash
            != canonical_hash(_restart_payload(record, include_hash=False))
        ):
            _fail(
                "fgmres_resume_restart_history_invalid",
                f"/resume/restart_history/{expected_index}",
                "Resume history is not an exact completed restart prefix.",
            )
        for iteration in range(record.start_iteration + 1, record.end_iteration + 1):
            observation = state.observations[iteration]
            if (
                observation.restart_index != expected_index
                or observation.inner_iteration
                != iteration - record.start_iteration
            ):
                _fail(
                    "fgmres_resume_observation_boundary_invalid",
                    f"/resume/observations/{iteration}",
                    "Observation does not match its restart-cycle boundary.",
                )
        previous_end = record.end_iteration
    if previous_end != state.iteration_count:
        _fail(
            "fgmres_resume_restart_history_invalid",
            "/resume/restart_history",
            "Resume history does not reach the persisted iteration.",
        )

    initial_observation, _ = _observe(
        plan=plan,
        scaling=scaling,
        free_dofs=free_dofs,
        row_ptr=row_ptr,
        columns=columns,
        reduced_values=reduced_values,
        rhs_free=rhs_free,
        solution=[float(value) for value in initial],
        iteration=0,
        restart_index=0,
        inner_iteration=0,
    )
    expected_threshold = max(
        absolute_tolerance,
        relative_tolerance * initial_observation.scaled_l2,
    )
    last_observation = state.observations[-1]
    recomputed_observation, recomputed_scaled = _observe(
        plan=plan,
        scaling=scaling,
        free_dofs=free_dofs,
        row_ptr=row_ptr,
        columns=columns,
        reduced_values=reduced_values,
        rhs_free=rhs_free,
        solution=[float(value) for value in state.solution_free],
        iteration=state.iteration_count,
        restart_index=state.next_restart_index - 1,
        inner_iteration=restart_length,
    )
    recomputed_scaled_array = immutable_array(recomputed_scaled, dtype="<f8")
    if (
        initial_observation != state.observations[0]
        or state.convergence_threshold_scaled_l2 != expected_threshold
        or recomputed_observation != last_observation
        or not np.array_equal(
            recomputed_scaled_array,
            state.scaled_residual_free,
        )
        or array_data_hash(state.solution_free)
        != last_observation.solution_free_data_hash
        or last_observation.scaled_l2 <= expected_threshold
    ):
        _fail(
            "fgmres_resume_binding_invalid",
            "/resume",
            "Resume bytes do not reproduce the exact nonterminal boundary.",
        )
    return state


def _observe(
    *,
    plan: ExecutionPlan,
    scaling: EquationScaling,
    free_dofs: list[int],
    row_ptr: list[int],
    columns: list[int],
    reduced_values: list[float],
    rhs_free: list[float],
    solution: list[float],
    iteration: int,
    restart_index: int,
    inner_iteration: int,
) -> tuple[CPUFGMRESObservation, list[float]]:
    internal_free = _csr_matvec(row_ptr, columns, reduced_values, solution)
    raw_free = [
        internal_free[index] - rhs_free[index] for index in range(len(free_dofs))
    ]
    raw_full = [0.0] * plan.dof_count
    scaled_full = [0.0] * plan.dof_count
    for free_index, equation in enumerate(free_dofs):
        raw_full[equation] = raw_free[free_index]
        scaled_full[equation] = raw_free[free_index] / float(
            scaling.scale_divisors_si[equation]
        )
    raw_array = _float_vector(
        raw_full, shape=(plan.dof_count,), path="/recurrence/raw_residual_si"
    )
    scaled_array = _float_vector(
        scaled_full, shape=(plan.dof_count,), path="/recurrence/scaled_residual"
    )
    solution_array = _float_vector(
        solution, shape=(len(free_dofs),), path="/recurrence/solution_free"
    )
    translation = [raw_full[index] for index in free_dofs if index % 6 < 3]
    rotation = [raw_full[index] for index in free_dofs if index % 6 >= 3]
    active_scaled = [scaled_full[index] for index in free_dofs]
    governing_position = max(
        range(len(free_dofs)), key=lambda index: abs(active_scaled[index])
    )
    governing_equation = free_dofs[governing_position]
    node_id, dof = _equation_location(plan, governing_equation)
    provisional = CPUFGMRESObservation(
        observation_hash=_HASH_ZERO,
        iteration=iteration,
        restart_index=restart_index,
        inner_iteration=inner_iteration,
        raw_residual_data_hash=array_data_hash(raw_array),
        scaled_residual_data_hash=array_data_hash(scaled_array),
        solution_free_data_hash=array_data_hash(solution_array),
        raw_translation_l2_n=_stable_l2(translation),
        raw_translation_linf_n=_linf(translation),
        raw_rotation_l2_nm=_stable_l2(rotation),
        raw_rotation_linf_nm=_linf(rotation),
        scaled_l2=_stable_l2(active_scaled),
        scaled_linf=_linf(active_scaled),
        governing_equation=governing_equation,
        governing_node_id=node_id,
        governing_dof=dof,
    )
    observation = replace(
        provisional,
        observation_hash=canonical_hash(
            _observation_payload(provisional, include_hash=False)
        ),
    )
    recurrence_residual = [
        -raw_free[index] / float(scaling.scale_divisors_si[equation])
        for index, equation in enumerate(free_dofs)
    ]
    return observation, recurrence_residual


def _make_restart_record(
    *,
    restart_index: int,
    start: CPUFGMRESObservation,
    end: CPUFGMRESObservation,
    disposition: str,
) -> CPUFGMRESRestartRecord:
    provisional = CPUFGMRESRestartRecord(
        restart_hash=_HASH_ZERO,
        restart_index=restart_index,
        start_iteration=start.iteration,
        end_iteration=end.iteration,
        iteration_count=end.iteration - start.iteration,
        start_observation_hash=start.observation_hash,
        end_observation_hash=end.observation_hash,
        disposition=disposition,
    )
    return replace(
        provisional,
        restart_hash=canonical_hash(_restart_payload(provisional, include_hash=False)),
    )


def _csr_matvec(
    row_ptr: Sequence[int],
    columns: Sequence[int],
    values: Sequence[float],
    vector: Sequence[float],
) -> list[float]:
    result: list[float] = []
    for row in range(len(row_ptr) - 1):
        result.append(
            math.fsum(
                values[position] * vector[columns[position]]
                for position in range(row_ptr[row], row_ptr[row + 1])
            )
        )
    _require_finite_vector(result, "/recurrence/matvec")
    return result


def _left_scaled_matvec(
    row_ptr: Sequence[int],
    columns: Sequence[int],
    values: Sequence[float],
    vector: Sequence[float],
    scale: Sequence[float],
) -> list[float]:
    raw = _csr_matvec(row_ptr, columns, values, vector)
    result = [raw[index] / scale[index] for index in range(len(raw))]
    _require_finite_vector(result, "/recurrence/scaled_matvec")
    return result


def _stable_dot(left: Sequence[float], right: Sequence[float]) -> float:
    try:
        result = math.fsum(left[index] * right[index] for index in range(len(left)))
    except OverflowError as exc:
        _fail("fgmres_numeric_nonfinite", "/recurrence/dot", str(exc))
    if not math.isfinite(result):
        _fail("fgmres_numeric_nonfinite", "/recurrence/dot", "Dot product overflowed.")
    return result


def _stable_l2(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    try:
        squared = math.fsum(value * value for value in values)
        result = math.sqrt(squared)
    except (OverflowError, ValueError) as exc:
        _fail("fgmres_numeric_nonfinite", "/recurrence/norm", str(exc))
    if not math.isfinite(result):
        _fail("fgmres_numeric_nonfinite", "/recurrence/norm", "Norm overflowed.")
    return result


def _linf(values: Sequence[float]) -> float:
    return max((abs(value) for value in values), default=0.0)


def _back_substitute(
    hessenberg: list[list[float]],
    projected_rhs: list[float],
    *,
    count: int,
    breakdown_tolerance: float,
) -> list[float] | None:
    result = [0.0] * count
    for row in range(count - 1, -1, -1):
        diagonal = hessenberg[row][row]
        if abs(diagonal) <= breakdown_tolerance:
            return None
        tail = math.fsum(
            hessenberg[row][column] * result[column] for column in range(row + 1, count)
        )
        result[row] = (projected_rhs[row] - tail) / diagonal
    _require_finite_vector(result, "/recurrence/projected_solution")
    return result


def _equation_location(plan: ExecutionPlan, equation: int) -> tuple[str, str]:
    node_dofs = plan.array("node_dof_indices")
    matches = np.argwhere(node_dofs == equation)
    if matches.shape != (1, 2):  # pragma: no cover - ExecutionPlan invariant
        _fail(
            "fgmres_equation_location_invalid",
            "/observations/governing",
            "Equation does not map to one node/DOF.",
        )
    node_index, component_index = (int(value) for value in matches[0])
    return plan.node_ids[node_index], EXECUTION_PLAN_DOF_COMPONENTS[component_index]


def _vector_descriptor(
    name: str,
    array: np.ndarray,
    *,
    equation_scope: str,
    artifact_uri: str | None = None,
) -> CPUFGMRESVectorDescriptor:
    metadata = {
        "name": name,
        "dtype": "<f8",
        "shape": list(array.shape),
        "layout": "C",
        "byte_order": "little",
        "equation_scope": equation_scope,
        "byte_length": int(array.nbytes),
    }
    return CPUFGMRESVectorDescriptor(
        name=name,
        dtype="<f8",
        shape=tuple(int(value) for value in array.shape),
        layout="C",
        byte_order="little",
        equation_scope=equation_scope,
        byte_length=int(array.nbytes),
        data_hash=array_data_hash(array),
        content_hash=array_content_hash(metadata, array),
        artifact_uri=artifact_uri,
    )


def _run_payload(run: CPUFGMRESRun, *, include_run_hash: bool) -> dict[str, Any]:
    descriptors = {row.name: row.to_dict() for row in run.input_descriptors}
    payload: dict[str, Any] = {
        "schema_version": run.schema_version,
        "authority": "non_authoritative_solver_recurrence",
        "solver": {
            "recurrence_profile": CPU_FGMRES_RECURRENCE_PROFILE,
            "accumulation_profile": CPU_FGMRES_ACCUMULATION_PROFILE,
            "preconditioner_profile": run.preconditioner_profile,
        },
        "source": {
            "execution_plan_hash": run.execution_plan_hash,
            "scaling_hash": run.scaling_hash,
            "reduced_csr_identity_hash": run.reduced_csr_identity_hash,
            "operator_numeric_values_hash": run.operator_numeric_values_hash,
            "dof_count": run.dof_count,
            "free_count": run.free_count,
            "global_csr_nnz": run.global_csr_nnz,
            "equation_scaling_source_replay": "required_at_run_and_replay",
        },
        "inputs": descriptors,
        "parameters": {
            "max_iterations": run.max_iterations,
            "restart_length": run.restart_length,
            "relative_tolerance_scaled_l2": run.relative_tolerance_scaled_l2,
            "absolute_tolerance_scaled_l2": run.absolute_tolerance_scaled_l2,
            "arnoldi_breakdown_tolerance": run.arnoldi_breakdown_tolerance,
        },
        "observations": [row.to_dict() for row in run.observations],
        "restart_history": [row.to_dict() for row in run.restart_history],
        "terminal": {
            "reason": run.terminal_reason,
            "converged": run.converged,
            "iteration_count": run.iteration_count,
            "matvec_count": run.matvec_count,
            "convergence_threshold_scaled_l2": run.convergence_threshold_scaled_l2,
            "final_observation_hash": run.observations[-1].observation_hash,
        },
        "solution_artifact": run.solution_descriptor.to_dict(),
        "claim_boundary": {
            "result_ir_authority": False,
            "engineering_result_recovery": False,
            "reaction_authority": False,
            "hip_or_hardware_claim": False,
            "iteration_vectors_inline": False,
            "recurrence_replay_required": True,
        },
    }
    if include_run_hash:
        payload["run_hash"] = run.run_hash
    return payload


def _observation_payload(
    observation: CPUFGMRESObservation, *, include_hash: bool
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "iteration": observation.iteration,
        "restart_index": observation.restart_index,
        "inner_iteration": observation.inner_iteration,
        "vector_hashes": {
            "raw_residual": observation.raw_residual_data_hash,
            "scaled_residual": observation.scaled_residual_data_hash,
        },
        "solution_free_data_hash": observation.solution_free_data_hash,
        "norms": {
            "raw_translation_l2_n": observation.raw_translation_l2_n,
            "raw_translation_linf_n": observation.raw_translation_linf_n,
            "raw_rotation_l2_nm": observation.raw_rotation_l2_nm,
            "raw_rotation_linf_nm": observation.raw_rotation_linf_nm,
            "scaled_l2": observation.scaled_l2,
            "scaled_linf": observation.scaled_linf,
        },
        "governing": {
            "equation": observation.governing_equation,
            "node_id": observation.governing_node_id,
            "dof": observation.governing_dof,
        },
    }
    if include_hash:
        payload["observation_hash"] = observation.observation_hash
    return payload


def _restart_payload(
    record: CPUFGMRESRestartRecord, *, include_hash: bool
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "restart_index": record.restart_index,
        "start_iteration": record.start_iteration,
        "end_iteration": record.end_iteration,
        "iteration_count": record.iteration_count,
        "start_observation_hash": record.start_observation_hash,
        "end_observation_hash": record.end_observation_hash,
        "disposition": record.disposition,
    }
    if include_hash:
        payload["restart_hash"] = record.restart_hash
    return payload


def _run_hash(run: CPUFGMRESRun) -> str:
    return canonical_hash(_run_payload(run, include_run_hash=False))


def _float_vector(value: Any, *, shape: tuple[int, ...], path: str) -> np.ndarray:
    try:
        result = immutable_array(value, dtype="<f8")
    except CanonicalContractError as exc:
        _fail("fgmres_vector_invalid", path, str(exc))
    if result.shape != shape:
        _fail("fgmres_vector_shape_invalid", path, f"Expected shape {shape}.")
    return result


def _validate_float_array(value: Any, *, path: str) -> None:
    if (
        not isinstance(value, np.ndarray)
        or value.dtype.str != "<f8"
        or value.ndim != 1
        or not value.flags.c_contiguous
        or value.flags.writeable
        or not has_immutable_bytes_backing(value)
        or not np.all(np.isfinite(value))
    ):
        _fail(
            "fgmres_vector_contract_invalid",
            path,
            "Expected immutable, finite, rank-one canonical little-endian fp64.",
        )


def _require_finite_vector(values: Sequence[float], path: str) -> None:
    if any(not math.isfinite(value) for value in values):
        _fail("fgmres_numeric_nonfinite", path, "Recurrence produced non-finite data.")


def _exact_int(value: Any, path: str, *, minimum: int) -> int:
    if type(value) is not int or value < minimum:
        _fail("fgmres_integer_invalid", path, f"Expected integer >= {minimum}.")
    return value


def _nonnegative_float(value: Any, path: str) -> float:
    if type(value) not in (int, float) or isinstance(value, bool):
        _fail("fgmres_number_invalid", path, "Expected a real number.")
    result = float(value)
    if not math.isfinite(result) or result < 0.0:
        _fail("fgmres_number_invalid", path, "Expected finite value >= 0.")
    return 0.0 if result == 0.0 else result


def _positive_float(value: Any, path: str) -> float:
    result = _nonnegative_float(value, path)
    if result == 0.0:
        _fail("fgmres_number_invalid", path, "Expected a positive value.")
    return result


def _solution_artifact_uri(value: Any) -> str:
    if type(value) is not str or any(ord(character) < 32 for character in value):
        _fail(
            "fgmres_solution_artifact_uri_invalid",
            "/solution_artifact/artifact_uri",
            "Expected nonempty printable text.",
        )
    normalized = value.rstrip("/")
    if not normalized.endswith(f"/{CPU_FGMRES_SOLUTION_FILENAME}"):
        _fail(
            "fgmres_solution_artifact_uri_invalid",
            "/solution_artifact/artifact_uri",
            f"Artifact URI must end with /{CPU_FGMRES_SOLUTION_FILENAME}.",
        )
    return normalized


@lru_cache(maxsize=1)
def _schema_validator() -> Draft202012Validator:
    resource = resources.files("structural_analysis.schemas").joinpath(
        "cpu_fgmres_run_v1.schema.json"
    )
    with resource.open("r", encoding="utf-8") as handle:
        schema = json.load(handle)
    Draft202012Validator.check_schema(schema)
    return _StrictDraft202012Validator(schema)


def _fail(code: str, path: str, message: str) -> None:
    raise CPUFGMRESError(code, path, message)
