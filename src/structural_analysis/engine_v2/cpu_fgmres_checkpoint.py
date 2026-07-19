"""Persisted restart-boundary checkpoint contract for deterministic CPU FGMRES."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from functools import lru_cache
import hashlib
from importlib import resources
import json
from pathlib import Path
import struct
from types import MappingProxyType
from typing import Any, Literal

from jsonschema import Draft202012Validator, validators
import numpy as np

from .contracts._canonical import (
    array_data_hash,
    canonical_hash,
    canonical_json_bytes,
    immutable_array,
    sha256_prefixed,
)
from .contracts.equation_scaling import (
    EquationScaling,
    validate_equation_scaling_binding,
)
from .contracts.execution_plan import ExecutionPlan, validate_execution_plan
from .contracts.execution_plan_reduced_csr import (
    ExecutionPlanReducedCSR,
    validate_execution_plan_reduced_csr,
)
from .cpu_fgmres import (
    CPU_FGMRES_DIAGONAL_PRECONDITIONER,
    CPU_FGMRES_IDENTITY_PRECONDITIONER,
    CPU_FGMRES_SCALED_JACOBI_PRECONDITIONER,
    CPUFGMRESError,
    CPUFGMRESObservation,
    CPUFGMRESRestartRecord,
    CPUFGMRESRun,
    CPUFGMRESVectorDescriptor,
    _CPUFGMRESResumeState,
    _float_vector,
    _validate_resume_state,
    _vector_descriptor,
    build_cpu_fgmres_left_scaled_jacobi_inverse_diagonal,
    run_cpu_fgmres,
    validate_cpu_fgmres_run,
)


CPU_FGMRES_CHECKPOINT_SCHEMA_VERSION = (
    "structural-analysis-cpu-fgmres-checkpoint.v1"
)
CPU_FGMRES_CHECKPOINT_STORAGE_PROFILE = (
    "canonical_little_endian_fgmres_restart_checkpoint.v1"
)
CPU_FGMRES_CHECKPOINT_FILENAME = "fgmres_restart_checkpoint.bin"
CPU_FGMRES_CHECKPOINT_MAGIC = b"EV2FGCP1"
CPU_FGMRES_CHECKPOINT_HEADER = struct.Struct("<8sQQQQd")
_HASH_ZERO = "sha256:" + "0" * 64
_INPUT_NAMES = (
    "global_csr_values_si",
    "right_hand_side_si",
    "free_equation_scale_divisors_si",
    "initial_solution_free",
    "right_preconditioner_inverse_diagonal",
)
_VECTOR_NAMES = ("solution_free", "scaled_recurrence_residual_free")
_STRICT_JSON_TYPE_CHECKER = Draft202012Validator.TYPE_CHECKER.redefine(
    "integer", lambda _checker, value: type(value) is int
).redefine("number", lambda _checker, value: type(value) in (int, float))
_StrictDraft202012Validator = validators.extend(
    Draft202012Validator,
    type_checker=_STRICT_JSON_TYPE_CHECKER,
)


@dataclass(frozen=True)
class CPUFGMRESCheckpointVectorDescriptor:
    name: str
    dtype: Literal["<f8"]
    shape: tuple[int, ...]
    byte_order: Literal["little"]
    offset: int
    byte_length: int
    data_hash: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["shape"] = list(self.shape)
        return payload


@dataclass(frozen=True)
class CPUFGMRESCheckpointArtifactDescriptor:
    storage_profile: str
    artifact_uri: str
    byte_length: int
    data_hash: str
    content_hash: str
    header_byte_length: int
    vectors: tuple[CPUFGMRESCheckpointVectorDescriptor, ...]

    def to_dict(self, *, checkpoint: CPUFGMRESCheckpoint) -> dict[str, Any]:
        return {
            "storage_profile": self.storage_profile,
            "artifact_uri": self.artifact_uri,
            "byte_length": self.byte_length,
            "data_hash": self.data_hash,
            "content_hash": self.content_hash,
            "header": {
                "magic": CPU_FGMRES_CHECKPOINT_MAGIC.decode("ascii"),
                "byte_length": self.header_byte_length,
                "free_count": checkpoint.free_count,
                "iteration_count": checkpoint.iteration_count,
                "matvec_count": checkpoint.matvec_count,
                "next_restart_index": checkpoint.next_restart_index,
                "convergence_threshold_scaled_l2": (
                    checkpoint.convergence_threshold_scaled_l2
                ),
            },
            "vectors": [row.to_dict() for row in self.vectors],
        }


@dataclass(frozen=True)
class CPUFGMRESCheckpoint:
    schema_version: str
    checkpoint_hash: str
    recurrence_contract_hash: str
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
    next_restart_index: int
    observations: tuple[CPUFGMRESObservation, ...]
    restart_history: tuple[CPUFGMRESRestartRecord, ...]
    input_descriptors: tuple[CPUFGMRESVectorDescriptor, ...]
    artifact_descriptor: CPUFGMRESCheckpointArtifactDescriptor
    _solution_free: np.ndarray
    _scaled_residual_free: np.ndarray
    _input_arrays: Mapping[str, np.ndarray]
    _execution_plan: ExecutionPlan
    _scaling: EquationScaling
    _reduced_csr: ExecutionPlanReducedCSR

    @property
    def solution_free(self) -> np.ndarray:
        return self._solution_free

    @property
    def scaled_residual_free(self) -> np.ndarray:
        return self._scaled_residual_free

    def to_manifest(self) -> dict[str, Any]:
        validate_cpu_fgmres_checkpoint(self)
        return _checkpoint_payload(self, include_checkpoint_hash=True)

    def to_bytes(self) -> bytes:
        validate_cpu_fgmres_checkpoint(self)
        return _checkpoint_bytes(self)


def create_cpu_fgmres_checkpoint(
    run: CPUFGMRESRun,
    *,
    restart_index: int,
    checkpoint_artifact_uri: str,
) -> CPUFGMRESCheckpoint:
    """Capture one completed, nonterminal restart boundary from a CPU run."""

    validated = validate_cpu_fgmres_run(run)
    if type(restart_index) is not int or restart_index < 0:
        _fail(
            "fgmres_checkpoint_restart_index_invalid",
            "/boundary/restart_index",
            "Restart index must be a nonnegative integer.",
        )
    snapshot = next(
        (
            row
            for row in validated._restart_snapshots
            if row.restart_index == restart_index
        ),
        None,
    )
    if snapshot is None:
        _fail(
            "fgmres_checkpoint_restart_boundary_unavailable",
            "/boundary/restart_index",
            "The run did not retain that completed nonterminal restart boundary.",
        )
    observations = validated.observations[: snapshot.iteration_count + 1]
    restart_history = validated.restart_history[: restart_index + 1]
    uri = _checkpoint_artifact_uri(checkpoint_artifact_uri)
    input_arrays = MappingProxyType(dict(validated._input_arrays))
    provisional = CPUFGMRESCheckpoint(
        schema_version=CPU_FGMRES_CHECKPOINT_SCHEMA_VERSION,
        checkpoint_hash=_HASH_ZERO,
        recurrence_contract_hash=_HASH_ZERO,
        execution_plan_hash=validated.execution_plan_hash,
        scaling_hash=validated.scaling_hash,
        reduced_csr_identity_hash=validated.reduced_csr_identity_hash,
        operator_numeric_values_hash=validated.operator_numeric_values_hash,
        dof_count=validated.dof_count,
        free_count=validated.free_count,
        global_csr_nnz=validated.global_csr_nnz,
        preconditioner_profile=validated.preconditioner_profile,
        max_iterations=validated.max_iterations,
        restart_length=validated.restart_length,
        relative_tolerance_scaled_l2=validated.relative_tolerance_scaled_l2,
        absolute_tolerance_scaled_l2=validated.absolute_tolerance_scaled_l2,
        arnoldi_breakdown_tolerance=validated.arnoldi_breakdown_tolerance,
        convergence_threshold_scaled_l2=(
            validated.convergence_threshold_scaled_l2
        ),
        iteration_count=snapshot.iteration_count,
        matvec_count=snapshot.matvec_count,
        next_restart_index=restart_index + 1,
        observations=observations,
        restart_history=restart_history,
        input_descriptors=validated.input_descriptors,
        artifact_descriptor=_empty_artifact_descriptor(uri),
        _solution_free=snapshot.solution_free,
        _scaled_residual_free=snapshot.scaled_residual_free,
        _input_arrays=input_arrays,
        _execution_plan=validated._execution_plan,
        _scaling=validated._scaling,
        _reduced_csr=validated._reduced_csr,
    )
    with_contract = replace(
        provisional,
        recurrence_contract_hash=_recurrence_contract_hash(provisional),
    )
    with_artifact = replace(
        with_contract,
        artifact_descriptor=_artifact_descriptor(with_contract, uri),
    )
    checkpoint = replace(
        with_artifact,
        checkpoint_hash=_checkpoint_hash(with_artifact),
    )
    return validate_cpu_fgmres_checkpoint(checkpoint)


def load_cpu_fgmres_checkpoint(
    payload: Any,
    data: bytes | bytearray | memoryview,
    *,
    execution_plan: ExecutionPlan,
    scaling: EquationScaling,
    reduced_csr: ExecutionPlanReducedCSR,
    node_coordinates_m: Any,
    reference_equation_load_si: Any,
    global_csr_values_si: Any,
    right_hand_side_si: Any,
    initial_solution_free: Any | None = None,
    right_preconditioner_inverse_diagonal: Any | None = None,
) -> CPUFGMRESCheckpoint:
    """Load a persisted checkpoint against explicit source contracts and bytes."""

    manifest = validate_cpu_fgmres_checkpoint_manifest(payload)
    plan = validate_execution_plan(execution_plan)
    validate_equation_scaling_binding(
        plan,
        scaling=scaling,
        node_coordinates_m=node_coordinates_m,
        reference_equation_load_si=reference_equation_load_si,
    )
    reduced = validate_execution_plan_reduced_csr(
        reduced_csr,
        execution_plan=plan,
    )
    source = manifest["source"]
    if (
        source["execution_plan_hash"] != plan.plan_hash
        or source["scaling_hash"] != scaling.scaling_hash
        or source["reduced_csr_identity_hash"] != reduced.identity_hash
        or source["operator_numeric_values_hash"]
        != reduced.operator_numeric_values_hash
        or source["dof_count"] != plan.dof_count
        or source["free_count"] != reduced.free_count
        or source["global_csr_nnz"]
        != int(plan.array("csr_column_indices").size)
    ):
        _fail(
            "fgmres_checkpoint_source_binding_mismatch",
            "/source",
            "Checkpoint identifies different Engine v2 source contracts.",
        )
    global_values = _float_vector(
        global_csr_values_si,
        shape=(source["global_csr_nnz"],),
        path="/inputs/global_csr_values_si",
    )
    if array_data_hash(global_values) != reduced.operator_numeric_values_hash:
        _fail(
            "fgmres_checkpoint_operator_values_mismatch",
            "/inputs/global_csr_values_si",
            "Operator bytes do not match the reduced-CSR identity.",
        )
    right_hand_side = _float_vector(
        right_hand_side_si,
        shape=(plan.dof_count,),
        path="/inputs/right_hand_side_si",
    )
    free_scale = _float_vector(
        scaling.scale_divisors_si[plan.array("free_dofs")],
        shape=(reduced.free_count,),
        path="/inputs/free_equation_scale_divisors_si",
    )
    initial = _float_vector(
        np.zeros(reduced.free_count, dtype="<f8")
        if initial_solution_free is None
        else initial_solution_free,
        shape=(reduced.free_count,),
        path="/inputs/initial_solution_free",
    )
    profile = manifest["solver"]["preconditioner_profile"]
    if profile == CPU_FGMRES_IDENTITY_PRECONDITIONER:
        if right_preconditioner_inverse_diagonal is not None:
            _fail(
                "fgmres_checkpoint_preconditioner_profile_mismatch",
                "/solver/preconditioner_profile",
                "Identity checkpoint must be loaded without an explicit diagonal.",
            )
        preconditioner = _float_vector(
            np.ones(reduced.free_count, dtype="<f8"),
            shape=(reduced.free_count,),
            path="/inputs/right_preconditioner_inverse_diagonal",
        )
    elif profile == CPU_FGMRES_DIAGONAL_PRECONDITIONER:
        if right_preconditioner_inverse_diagonal is None:
            _fail(
                "fgmres_checkpoint_preconditioner_missing",
                "/inputs/right_preconditioner_inverse_diagonal",
                "Diagonal checkpoint requires its exact preconditioner bytes.",
            )
        preconditioner = _float_vector(
            right_preconditioner_inverse_diagonal,
            shape=(reduced.free_count,),
            path="/inputs/right_preconditioner_inverse_diagonal",
        )
        if np.any(preconditioner <= 0.0):
            _fail(
                "fgmres_checkpoint_preconditioner_invalid",
                "/inputs/right_preconditioner_inverse_diagonal",
                "Checkpoint preconditioner entries must be positive.",
            )
    elif profile == CPU_FGMRES_SCALED_JACOBI_PRECONDITIONER:
        derived_preconditioner = (
            build_cpu_fgmres_left_scaled_jacobi_inverse_diagonal(
                execution_plan=plan,
                scaling=scaling,
                reduced_csr=reduced,
                global_csr_values_si=global_values,
            )
        )
        if right_preconditioner_inverse_diagonal is None:
            preconditioner = derived_preconditioner
        else:
            preconditioner = _float_vector(
                right_preconditioner_inverse_diagonal,
                shape=(reduced.free_count,),
                path="/inputs/right_preconditioner_inverse_diagonal",
            )
            if not np.array_equal(preconditioner, derived_preconditioner):
                _fail(
                    "fgmres_checkpoint_scaled_jacobi_binding_mismatch",
                    "/inputs/right_preconditioner_inverse_diagonal",
                    "Checkpoint Jacobi bytes do not match D_free^-1 A_free.",
                )
    else:  # pragma: no cover - schema invariant
        _fail(
            "fgmres_checkpoint_preconditioner_profile_invalid",
            "/solver/preconditioner_profile",
            "Unsupported preconditioner profile.",
        )
    input_arrays = MappingProxyType(
        {
            "global_csr_values_si": global_values,
            "right_hand_side_si": right_hand_side,
            "free_equation_scale_divisors_si": free_scale,
            "initial_solution_free": initial,
            "right_preconditioner_inverse_diagonal": preconditioner,
        }
    )
    input_descriptors = _input_descriptors(input_arrays)
    if {row.name: row.to_dict() for row in input_descriptors} != manifest["inputs"]:
        _fail(
            "fgmres_checkpoint_input_binding_mismatch",
            "/inputs",
            "Explicit input bytes do not match the checkpoint descriptors.",
        )
    solution, scaled_residual = _decode_checkpoint_bytes(manifest, bytes(data))
    parameters = manifest["parameters"]
    boundary = manifest["boundary"]
    checkpoint = CPUFGMRESCheckpoint(
        schema_version=manifest["schema_version"],
        checkpoint_hash=manifest["checkpoint_hash"],
        recurrence_contract_hash=manifest["recurrence_contract_hash"],
        execution_plan_hash=source["execution_plan_hash"],
        scaling_hash=source["scaling_hash"],
        reduced_csr_identity_hash=source["reduced_csr_identity_hash"],
        operator_numeric_values_hash=source["operator_numeric_values_hash"],
        dof_count=source["dof_count"],
        free_count=source["free_count"],
        global_csr_nnz=source["global_csr_nnz"],
        preconditioner_profile=profile,
        max_iterations=parameters["max_iterations"],
        restart_length=parameters["restart_length"],
        relative_tolerance_scaled_l2=parameters[
            "relative_tolerance_scaled_l2"
        ],
        absolute_tolerance_scaled_l2=parameters[
            "absolute_tolerance_scaled_l2"
        ],
        arnoldi_breakdown_tolerance=parameters[
            "arnoldi_breakdown_tolerance"
        ],
        convergence_threshold_scaled_l2=boundary[
            "convergence_threshold_scaled_l2"
        ],
        iteration_count=boundary["iteration_count"],
        matvec_count=boundary["matvec_count"],
        next_restart_index=boundary["next_restart_index"],
        observations=tuple(
            _observation_from_payload(row) for row in manifest["observations"]
        ),
        restart_history=tuple(
            _restart_from_payload(row) for row in manifest["restart_history"]
        ),
        input_descriptors=input_descriptors,
        artifact_descriptor=_artifact_descriptor_from_payload(
            manifest["artifact"]
        ),
        _solution_free=solution,
        _scaled_residual_free=scaled_residual,
        _input_arrays=input_arrays,
        _execution_plan=plan,
        _scaling=scaling,
        _reduced_csr=reduced,
    )
    return validate_cpu_fgmres_checkpoint(checkpoint)


def resume_cpu_fgmres_from_checkpoint(
    checkpoint: CPUFGMRESCheckpoint,
    *,
    solution_artifact_uri: str,
) -> CPUFGMRESRun:
    """Continue the exact recurrence without replaying completed iterations."""

    validated = validate_cpu_fgmres_checkpoint(checkpoint)
    return run_cpu_fgmres(
        execution_plan=validated._execution_plan,
        scaling=validated._scaling,
        reduced_csr=validated._reduced_csr,
        node_coordinates_m=None,
        reference_equation_load_si=None,
        global_csr_values_si=validated._input_arrays["global_csr_values_si"],
        right_hand_side_si=validated._input_arrays["right_hand_side_si"],
        solution_artifact_uri=solution_artifact_uri,
        max_iterations=validated.max_iterations,
        restart_length=validated.restart_length,
        relative_tolerance_scaled_l2=validated.relative_tolerance_scaled_l2,
        absolute_tolerance_scaled_l2=validated.absolute_tolerance_scaled_l2,
        arnoldi_breakdown_tolerance=validated.arnoldi_breakdown_tolerance,
        initial_solution_free=validated._input_arrays["initial_solution_free"],
        right_preconditioner_inverse_diagonal=(
            None
            if validated.preconditioner_profile
            == CPU_FGMRES_IDENTITY_PRECONDITIONER
            else validated._input_arrays[
                "right_preconditioner_inverse_diagonal"
            ]
        ),
        right_preconditioner_profile=validated.preconditioner_profile,
        _resume_state=_resume_state(validated),
    )


def write_cpu_fgmres_checkpoint_artifact(
    checkpoint: CPUFGMRESCheckpoint,
    output_file: str | Path,
) -> Path:
    validated = validate_cpu_fgmres_checkpoint(checkpoint)
    target = Path(output_file)
    if target.name != CPU_FGMRES_CHECKPOINT_FILENAME:
        _fail(
            "fgmres_checkpoint_filename_invalid",
            "/artifact/artifact_uri",
            f"Output filename must be {CPU_FGMRES_CHECKPOINT_FILENAME}.",
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        _fail(
            "fgmres_checkpoint_target_exists",
            "/artifact",
            f"Refusing to overwrite existing artifact: {target}",
        )
    created = False
    try:
        with target.open("xb") as handle:
            created = True
            handle.write(_checkpoint_bytes(validated))
        validate_cpu_fgmres_checkpoint_bytes(validated, target.read_bytes())
    except Exception:
        if created:
            target.unlink(missing_ok=True)
        raise
    return target


def validate_cpu_fgmres_checkpoint(
    checkpoint: CPUFGMRESCheckpoint,
) -> CPUFGMRESCheckpoint:
    if type(checkpoint) is not CPUFGMRESCheckpoint:
        _fail(
            "fgmres_checkpoint_type_invalid",
            "/",
            "Expected CPUFGMRESCheckpoint.",
        )
    if not isinstance(checkpoint._input_arrays, MappingProxyType):
        _fail(
            "fgmres_checkpoint_inputs_mutable",
            "/inputs",
            "Checkpoint input map must be immutable.",
        )
    plan = validate_execution_plan(checkpoint._execution_plan)
    validate_equation_scaling_binding(plan, scaling=checkpoint._scaling)
    reduced = validate_execution_plan_reduced_csr(
        checkpoint._reduced_csr,
        execution_plan=plan,
    )
    if (
        checkpoint.execution_plan_hash != plan.plan_hash
        or checkpoint.scaling_hash != checkpoint._scaling.scaling_hash
        or checkpoint.reduced_csr_identity_hash != reduced.identity_hash
        or checkpoint.operator_numeric_values_hash
        != reduced.operator_numeric_values_hash
        or checkpoint.dof_count != plan.dof_count
        or checkpoint.free_count != reduced.free_count
        or checkpoint.global_csr_nnz
        != int(plan.array("csr_column_indices").size)
    ):
        _fail(
            "fgmres_checkpoint_source_binding_mismatch",
            "/source",
            "Checkpoint source binding is stale.",
        )
    if tuple(checkpoint._input_arrays) != _INPUT_NAMES:
        _fail(
            "fgmres_checkpoint_input_set_invalid",
            "/inputs",
            "Checkpoint input set is invalid.",
        )
    expected_descriptors = _input_descriptors(checkpoint._input_arrays)
    if checkpoint.input_descriptors != expected_descriptors:
        _fail(
            "fgmres_checkpoint_input_binding_mismatch",
            "/inputs",
            "Input descriptors do not match immutable bytes.",
        )
    expected_artifact = _artifact_descriptor(
        checkpoint,
        checkpoint.artifact_descriptor.artifact_uri,
    )
    if checkpoint.artifact_descriptor != expected_artifact:
        _fail(
            "fgmres_checkpoint_artifact_descriptor_mismatch",
            "/artifact",
            "Checkpoint artifact descriptor does not match exact bytes.",
        )
    payload = _checkpoint_payload(checkpoint, include_checkpoint_hash=True)
    validate_cpu_fgmres_checkpoint_manifest(payload)
    if checkpoint.recurrence_contract_hash != _recurrence_contract_hash(checkpoint):
        _fail(
            "fgmres_checkpoint_recurrence_contract_hash_mismatch",
            "/recurrence_contract_hash",
            "Checkpoint recurrence contract hash is stale.",
        )
    if checkpoint.checkpoint_hash != _checkpoint_hash(checkpoint):
        _fail(
            "fgmres_checkpoint_hash_mismatch",
            "/checkpoint_hash",
            "Checkpoint hash is stale.",
        )
    _validate_resume_state_for_checkpoint(checkpoint)
    return checkpoint


def validate_cpu_fgmres_checkpoint_manifest(payload: Any) -> Mapping[str, Any]:
    errors = sorted(
        _schema_validator().iter_errors(payload),
        key=lambda error: tuple(str(value) for value in error.absolute_path),
    )
    if errors:
        error = errors[0]
        path = "/" + "/".join(str(value) for value in error.absolute_path)
        _fail("fgmres_checkpoint_schema_invalid", path or "/", error.message)
    if not isinstance(payload, Mapping):  # pragma: no cover - schema invariant
        _fail("fgmres_checkpoint_manifest_type_invalid", "/", "Expected object.")
    without_hash = dict(payload)
    claimed_hash = without_hash.pop("checkpoint_hash")
    if claimed_hash != canonical_hash(without_hash):
        _fail(
            "fgmres_checkpoint_hash_mismatch",
            "/checkpoint_hash",
            "Checkpoint manifest hash is stale.",
        )
    recurrence_payload = {
        "source": payload["source"],
        "solver": payload["solver"],
        "inputs": payload["inputs"],
        "parameters": payload["parameters"],
        "initial_observation": payload["observations"][0],
    }
    if payload["recurrence_contract_hash"] != canonical_hash(recurrence_payload):
        _fail(
            "fgmres_checkpoint_recurrence_contract_hash_mismatch",
            "/recurrence_contract_hash",
            "Recurrence contract hash is stale.",
        )
    source = payload["source"]
    descriptors = payload["inputs"]
    expected_input_semantics = {
        "global_csr_values_si": (
            source["global_csr_nnz"],
            "global_csr_pattern_order",
        ),
        "right_hand_side_si": (source["dof_count"], "global_equations"),
        "free_equation_scale_divisors_si": (
            source["free_count"],
            "free_equations",
        ),
        "initial_solution_free": (source["free_count"], "free_equations"),
        "right_preconditioner_inverse_diagonal": (
            source["free_count"],
            "free_equations",
        ),
    }
    for name, (length, scope) in expected_input_semantics.items():
        descriptor = descriptors[name]
        if (
            descriptor["name"] != name
            or descriptor["shape"] != [length]
            or descriptor["byte_length"] != length * 8
            or descriptor["equation_scope"] != scope
        ):
            _fail(
                "fgmres_checkpoint_input_descriptor_semantics_invalid",
                f"/inputs/{name}",
                "Checkpoint input descriptor shape or scope is stale.",
            )
    if (
        descriptors["global_csr_values_si"]["data_hash"]
        != source["operator_numeric_values_hash"]
    ):
        _fail(
            "fgmres_checkpoint_operator_values_mismatch",
            "/inputs/global_csr_values_si/data_hash",
            "Operator numeric hash is stale.",
        )
    parameters = payload["parameters"]
    if (
        parameters["restart_length"] > source["free_count"]
        or parameters["restart_length"] >= parameters["max_iterations"]
        or (
            parameters["relative_tolerance_scaled_l2"] == 0.0
            and parameters["absolute_tolerance_scaled_l2"] == 0.0
        )
    ):
        _fail(
            "fgmres_checkpoint_parameter_semantics_invalid",
            "/parameters",
            "Checkpoint parameters cannot produce a nonterminal restart boundary.",
        )
    observations = payload["observations"]
    history = payload["restart_history"]
    boundary = payload["boundary"]
    if len(observations) != boundary["iteration_count"] + 1:
        _fail(
            "fgmres_checkpoint_observation_count_invalid",
            "/observations",
            "Checkpoint observations must be a contiguous recurrence prefix.",
        )
    observation_by_hash: dict[str, Mapping[str, Any]] = {}
    for index, observation in enumerate(observations):
        without_observation_hash = dict(observation)
        observation_hash = without_observation_hash.pop("observation_hash")
        if (
            observation["iteration"] != index
            or observation_hash != canonical_hash(without_observation_hash)
        ):
            _fail(
                "fgmres_checkpoint_observation_invalid",
                f"/observations/{index}",
                "Checkpoint observation order or hash is stale.",
            )
        observation_by_hash[observation_hash] = observation
    previous_end = 0
    for index, record in enumerate(history):
        without_restart_hash = dict(record)
        restart_hash = without_restart_hash.pop("restart_hash")
        start = observation_by_hash.get(record["start_observation_hash"])
        end = observation_by_hash.get(record["end_observation_hash"])
        if (
            record["restart_index"] != index
            or record["start_iteration"] != previous_end
            or record["iteration_count"] != payload["parameters"]["restart_length"]
            or record["end_iteration"]
            != record["start_iteration"] + record["iteration_count"]
            or record["disposition"] != "restarted"
            or restart_hash != canonical_hash(without_restart_hash)
            or start is None
            or end is None
            or start["iteration"] != record["start_iteration"]
            or end["iteration"] != record["end_iteration"]
        ):
            _fail(
                "fgmres_checkpoint_restart_history_invalid",
                f"/restart_history/{index}",
                "Checkpoint history is not an exact restarted prefix.",
            )
        for iteration in range(
            record["start_iteration"] + 1,
            record["end_iteration"] + 1,
        ):
            observation = observations[iteration]
            if (
                observation["restart_index"] != index
                or observation["inner_iteration"]
                != iteration - record["start_iteration"]
            ):
                _fail(
                    "fgmres_checkpoint_observation_boundary_invalid",
                    f"/observations/{iteration}",
                    "Observation is assigned to a different restart cycle.",
                )
        previous_end = record["end_iteration"]
    expected_threshold = max(
        parameters["absolute_tolerance_scaled_l2"],
        parameters["relative_tolerance_scaled_l2"]
        * observations[0]["norms"]["scaled_l2"],
    )
    if (
        len(history) != boundary["next_restart_index"]
        or previous_end != boundary["iteration_count"]
        or boundary["last_observation_hash"]
        != observations[-1]["observation_hash"]
        or boundary["matvec_count"] != 1 + 2 * boundary["iteration_count"]
        or boundary["iteration_count"] >= payload["parameters"]["max_iterations"]
        or boundary["convergence_threshold_scaled_l2"] != expected_threshold
        or observations[0]["restart_index"] != 0
        or observations[0]["inner_iteration"] != 0
        or observations[-1]["norms"]["scaled_l2"] <= expected_threshold
    ):
        _fail(
            "fgmres_checkpoint_boundary_invalid",
            "/boundary",
            "Checkpoint boundary counters or terminal binding are stale.",
        )
    artifact = payload["artifact"]
    vectors = artifact["vectors"]
    vector_byte_length = source["free_count"] * 8
    if (
        artifact["artifact_uri"].strip() != artifact["artifact_uri"]
        or "\\" in artifact["artifact_uri"]
        or artifact["header"]["free_count"] != source["free_count"]
        or artifact["header"]["iteration_count"]
        != boundary["iteration_count"]
        or artifact["header"]["matvec_count"] != boundary["matvec_count"]
        or artifact["header"]["next_restart_index"]
        != boundary["next_restart_index"]
        or artifact["header"]["convergence_threshold_scaled_l2"]
        != boundary["convergence_threshold_scaled_l2"]
        or artifact["byte_length"]
        != CPU_FGMRES_CHECKPOINT_HEADER.size + 2 * vector_byte_length
        or [row["name"] for row in vectors] != list(_VECTOR_NAMES)
        or vectors[0]["shape"] != [source["free_count"]]
        or vectors[1]["shape"] != [source["free_count"]]
        or vectors[0]["offset"] != CPU_FGMRES_CHECKPOINT_HEADER.size
        or vectors[1]["offset"]
        != CPU_FGMRES_CHECKPOINT_HEADER.size + vector_byte_length
        or any(row["byte_length"] != vector_byte_length for row in vectors)
        or vectors[0]["data_hash"]
        != observations[-1]["solution_free_data_hash"]
    ):
        _fail(
            "fgmres_checkpoint_artifact_semantics_invalid",
            "/artifact",
            "Checkpoint header, vector offsets, or boundary binding is stale.",
        )
    return payload


def validate_cpu_fgmres_checkpoint_bytes(
    checkpoint: CPUFGMRESCheckpoint,
    data: bytes | bytearray | memoryview,
) -> None:
    validated = validate_cpu_fgmres_checkpoint(checkpoint)
    _decode_checkpoint_bytes(validated.to_manifest(), bytes(data))


def _resume_state(checkpoint: CPUFGMRESCheckpoint) -> _CPUFGMRESResumeState:
    return _CPUFGMRESResumeState(
        iteration_count=checkpoint.iteration_count,
        matvec_count=checkpoint.matvec_count,
        next_restart_index=checkpoint.next_restart_index,
        convergence_threshold_scaled_l2=(
            checkpoint.convergence_threshold_scaled_l2
        ),
        observations=checkpoint.observations,
        restart_history=checkpoint.restart_history,
        solution_free=checkpoint.solution_free,
        scaled_residual_free=checkpoint.scaled_residual_free,
    )


def _validate_resume_state_for_checkpoint(
    checkpoint: CPUFGMRESCheckpoint,
) -> None:
    plan = checkpoint._execution_plan
    reduced = checkpoint._reduced_csr
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
        float(checkpoint._input_arrays["global_csr_values_si"][position])
        for position in positions
    ]
    rhs_free = [
        float(checkpoint._input_arrays["right_hand_side_si"][equation])
        for equation in free_dofs
    ]
    _validate_resume_state(
        _resume_state(checkpoint),
        plan=plan,
        scaling=checkpoint._scaling,
        free_dofs=free_dofs,
        row_ptr=row_ptr,
        columns=columns,
        reduced_values=reduced_values,
        rhs_free=rhs_free,
        initial=checkpoint._input_arrays["initial_solution_free"],
        max_iterations=checkpoint.max_iterations,
        restart_length=checkpoint.restart_length,
        relative_tolerance=checkpoint.relative_tolerance_scaled_l2,
        absolute_tolerance=checkpoint.absolute_tolerance_scaled_l2,
    )


def _checkpoint_bytes(checkpoint: CPUFGMRESCheckpoint) -> bytes:
    return b"".join(
        (
            CPU_FGMRES_CHECKPOINT_HEADER.pack(
                CPU_FGMRES_CHECKPOINT_MAGIC,
                checkpoint.free_count,
                checkpoint.iteration_count,
                checkpoint.matvec_count,
                checkpoint.next_restart_index,
                checkpoint.convergence_threshold_scaled_l2,
            ),
            memoryview(checkpoint.solution_free).cast("B"),
            memoryview(checkpoint.scaled_residual_free).cast("B"),
        )
    )


def _decode_checkpoint_bytes(
    payload: Mapping[str, Any],
    data: bytes,
) -> tuple[np.ndarray, np.ndarray]:
    artifact = payload["artifact"]
    if len(data) != artifact["byte_length"]:
        _fail(
            "fgmres_checkpoint_artifact_length_mismatch",
            "/artifact/byte_length",
            "Checkpoint artifact byte length is stale.",
        )
    if sha256_prefixed(data) != artifact["data_hash"]:
        _fail(
            "fgmres_checkpoint_artifact_hash_mismatch",
            "/artifact/data_hash",
            "Checkpoint artifact bytes do not match the data hash.",
        )
    try:
        (
            magic,
            free_count,
            iteration_count,
            matvec_count,
            next_restart_index,
            convergence_threshold,
        ) = CPU_FGMRES_CHECKPOINT_HEADER.unpack_from(data)
    except struct.error as exc:
        raise CPUFGMRESError(
            "fgmres_checkpoint_header_invalid",
            "/artifact/header",
            "Checkpoint header cannot be decoded.",
        ) from exc
    header = artifact["header"]
    if (
        magic != CPU_FGMRES_CHECKPOINT_MAGIC
        or free_count != header["free_count"]
        or iteration_count != header["iteration_count"]
        or matvec_count != header["matvec_count"]
        or next_restart_index != header["next_restart_index"]
        or convergence_threshold != header["convergence_threshold_scaled_l2"]
    ):
        _fail(
            "fgmres_checkpoint_header_mismatch",
            "/artifact/header",
            "Checkpoint header does not match the manifest boundary.",
        )
    metadata = _artifact_metadata_from_payload(artifact)
    if _artifact_content_hash(metadata, data) != artifact["content_hash"]:
        _fail(
            "fgmres_checkpoint_artifact_content_hash_mismatch",
            "/artifact/content_hash",
            "Checkpoint metadata and bytes do not match the content hash.",
        )
    arrays: dict[str, np.ndarray] = {}
    for descriptor in artifact["vectors"]:
        start = descriptor["offset"]
        end = start + descriptor["byte_length"]
        array = immutable_array(
            np.frombuffer(data[start:end], dtype="<f8"),
            dtype="<f8",
        )
        if (
            array.shape != tuple(descriptor["shape"])
            or array_data_hash(array) != descriptor["data_hash"]
        ):
            _fail(
                "fgmres_checkpoint_vector_hash_mismatch",
                f"/artifact/vectors/{descriptor['name']}",
                "Checkpoint vector bytes do not match their descriptor.",
            )
        arrays[descriptor["name"]] = array
    return arrays[_VECTOR_NAMES[0]], arrays[_VECTOR_NAMES[1]]


def _artifact_descriptor(
    checkpoint: CPUFGMRESCheckpoint,
    artifact_uri: str,
) -> CPUFGMRESCheckpointArtifactDescriptor:
    header_length = CPU_FGMRES_CHECKPOINT_HEADER.size
    vector_length = checkpoint.free_count * 8
    vectors = (
        CPUFGMRESCheckpointVectorDescriptor(
            name=_VECTOR_NAMES[0],
            dtype="<f8",
            shape=(checkpoint.free_count,),
            byte_order="little",
            offset=header_length,
            byte_length=vector_length,
            data_hash=array_data_hash(checkpoint.solution_free),
        ),
        CPUFGMRESCheckpointVectorDescriptor(
            name=_VECTOR_NAMES[1],
            dtype="<f8",
            shape=(checkpoint.free_count,),
            byte_order="little",
            offset=header_length + vector_length,
            byte_length=vector_length,
            data_hash=array_data_hash(checkpoint.scaled_residual_free),
        ),
    )
    raw = _checkpoint_bytes(checkpoint)
    provisional = CPUFGMRESCheckpointArtifactDescriptor(
        storage_profile=CPU_FGMRES_CHECKPOINT_STORAGE_PROFILE,
        artifact_uri=artifact_uri,
        byte_length=len(raw),
        data_hash=sha256_prefixed(raw),
        content_hash=_HASH_ZERO,
        header_byte_length=header_length,
        vectors=vectors,
    )
    metadata = _artifact_metadata(checkpoint, provisional)
    return replace(
        provisional,
        content_hash=_artifact_content_hash(metadata, raw),
    )


def _empty_artifact_descriptor(
    artifact_uri: str,
) -> CPUFGMRESCheckpointArtifactDescriptor:
    return CPUFGMRESCheckpointArtifactDescriptor(
        storage_profile=CPU_FGMRES_CHECKPOINT_STORAGE_PROFILE,
        artifact_uri=artifact_uri,
        byte_length=0,
        data_hash=_HASH_ZERO,
        content_hash=_HASH_ZERO,
        header_byte_length=CPU_FGMRES_CHECKPOINT_HEADER.size,
        vectors=(),
    )


def _artifact_descriptor_from_payload(
    payload: Mapping[str, Any],
) -> CPUFGMRESCheckpointArtifactDescriptor:
    return CPUFGMRESCheckpointArtifactDescriptor(
        storage_profile=payload["storage_profile"],
        artifact_uri=payload["artifact_uri"],
        byte_length=payload["byte_length"],
        data_hash=payload["data_hash"],
        content_hash=payload["content_hash"],
        header_byte_length=payload["header"]["byte_length"],
        vectors=tuple(
            CPUFGMRESCheckpointVectorDescriptor(
                name=row["name"],
                dtype=row["dtype"],
                shape=tuple(row["shape"]),
                byte_order=row["byte_order"],
                offset=row["offset"],
                byte_length=row["byte_length"],
                data_hash=row["data_hash"],
            )
            for row in payload["vectors"]
        ),
    )


def _artifact_metadata(
    checkpoint: CPUFGMRESCheckpoint,
    descriptor: CPUFGMRESCheckpointArtifactDescriptor,
) -> dict[str, Any]:
    payload = descriptor.to_dict(checkpoint=checkpoint)
    payload.pop("data_hash")
    payload.pop("content_hash")
    return payload


def _artifact_metadata_from_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(payload)
    result.pop("data_hash")
    result.pop("content_hash")
    return result


def _artifact_content_hash(metadata: Mapping[str, Any], raw: bytes) -> str:
    digest = hashlib.sha256()
    digest.update(canonical_json_bytes(metadata))
    digest.update(b"\0")
    digest.update(raw)
    return f"sha256:{digest.hexdigest()}"


def _checkpoint_payload(
    checkpoint: CPUFGMRESCheckpoint,
    *,
    include_checkpoint_hash: bool,
) -> dict[str, Any]:
    descriptors = {row.name: row.to_dict() for row in checkpoint.input_descriptors}
    payload: dict[str, Any] = {
        "schema_version": checkpoint.schema_version,
        "recurrence_contract_hash": checkpoint.recurrence_contract_hash,
        "authority": "non_authoritative_solver_restart_checkpoint",
        "source": {
            "execution_plan_hash": checkpoint.execution_plan_hash,
            "scaling_hash": checkpoint.scaling_hash,
            "reduced_csr_identity_hash": checkpoint.reduced_csr_identity_hash,
            "operator_numeric_values_hash": checkpoint.operator_numeric_values_hash,
            "dof_count": checkpoint.dof_count,
            "free_count": checkpoint.free_count,
            "global_csr_nnz": checkpoint.global_csr_nnz,
        },
        "solver": {"preconditioner_profile": checkpoint.preconditioner_profile},
        "inputs": descriptors,
        "parameters": {
            "max_iterations": checkpoint.max_iterations,
            "restart_length": checkpoint.restart_length,
            "relative_tolerance_scaled_l2": (
                checkpoint.relative_tolerance_scaled_l2
            ),
            "absolute_tolerance_scaled_l2": (
                checkpoint.absolute_tolerance_scaled_l2
            ),
            "arnoldi_breakdown_tolerance": (
                checkpoint.arnoldi_breakdown_tolerance
            ),
        },
        "boundary": {
            "iteration_count": checkpoint.iteration_count,
            "matvec_count": checkpoint.matvec_count,
            "next_restart_index": checkpoint.next_restart_index,
            "convergence_threshold_scaled_l2": (
                checkpoint.convergence_threshold_scaled_l2
            ),
            "last_observation_hash": checkpoint.observations[-1].observation_hash,
        },
        "observations": [row.to_dict() for row in checkpoint.observations],
        "restart_history": [row.to_dict() for row in checkpoint.restart_history],
        "artifact": checkpoint.artifact_descriptor.to_dict(checkpoint=checkpoint),
        "claim_boundary": {
            "restart_boundary_only": True,
            "resumable_without_completed_iteration_replay": True,
            "result_ir_authority": False,
            "engineering_result_recovery": False,
            "hip_or_hardware_claim": False,
            "inline_vector_values": False,
        },
    }
    if include_checkpoint_hash:
        payload["checkpoint_hash"] = checkpoint.checkpoint_hash
    return payload


def _recurrence_contract_hash(checkpoint: CPUFGMRESCheckpoint) -> str:
    payload = _checkpoint_payload(checkpoint, include_checkpoint_hash=False)
    return canonical_hash(
        {
            "source": payload["source"],
            "solver": payload["solver"],
            "inputs": payload["inputs"],
            "parameters": payload["parameters"],
            "initial_observation": payload["observations"][0],
        }
    )


def _checkpoint_hash(checkpoint: CPUFGMRESCheckpoint) -> str:
    return canonical_hash(_checkpoint_payload(checkpoint, include_checkpoint_hash=False))


def _input_descriptors(
    input_arrays: Mapping[str, np.ndarray],
) -> tuple[CPUFGMRESVectorDescriptor, ...]:
    return tuple(
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


def _observation_from_payload(payload: Mapping[str, Any]) -> CPUFGMRESObservation:
    norms = payload["norms"]
    governing = payload["governing"]
    vectors = payload["vector_hashes"]
    return CPUFGMRESObservation(
        observation_hash=payload["observation_hash"],
        iteration=payload["iteration"],
        restart_index=payload["restart_index"],
        inner_iteration=payload["inner_iteration"],
        raw_residual_data_hash=vectors["raw_residual"],
        scaled_residual_data_hash=vectors["scaled_residual"],
        solution_free_data_hash=payload["solution_free_data_hash"],
        raw_translation_l2_n=norms["raw_translation_l2_n"],
        raw_translation_linf_n=norms["raw_translation_linf_n"],
        raw_rotation_l2_nm=norms["raw_rotation_l2_nm"],
        raw_rotation_linf_nm=norms["raw_rotation_linf_nm"],
        scaled_l2=norms["scaled_l2"],
        scaled_linf=norms["scaled_linf"],
        governing_equation=governing["equation"],
        governing_node_id=governing["node_id"],
        governing_dof=governing["dof"],
    )


def _restart_from_payload(payload: Mapping[str, Any]) -> CPUFGMRESRestartRecord:
    return CPUFGMRESRestartRecord(
        restart_hash=payload["restart_hash"],
        restart_index=payload["restart_index"],
        start_iteration=payload["start_iteration"],
        end_iteration=payload["end_iteration"],
        iteration_count=payload["iteration_count"],
        start_observation_hash=payload["start_observation_hash"],
        end_observation_hash=payload["end_observation_hash"],
        disposition=payload["disposition"],
    )


def _checkpoint_artifact_uri(value: Any) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or "\\" in value
        or not value.strip().endswith(f"/{CPU_FGMRES_CHECKPOINT_FILENAME}")
    ):
        _fail(
            "fgmres_checkpoint_artifact_uri_invalid",
            "/artifact/artifact_uri",
            f"Artifact URI must end with /{CPU_FGMRES_CHECKPOINT_FILENAME}.",
        )
    return value.strip()


@lru_cache(maxsize=1)
def _schema_validator() -> _StrictDraft202012Validator:
    schema = json.loads(
        resources.files("structural_analysis.schemas")
        .joinpath("cpu_fgmres_checkpoint_v1.schema.json")
        .read_text(encoding="utf-8")
    )
    _StrictDraft202012Validator.check_schema(schema)
    return _StrictDraft202012Validator(schema)


def _fail(code: str, path: str, message: str) -> None:
    raise CPUFGMRESError(code, path, message)
