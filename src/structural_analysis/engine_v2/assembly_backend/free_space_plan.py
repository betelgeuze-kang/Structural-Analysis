"""Non-solver free-space symbolic overlay for an ``ExecutionPlanV2``.

The sparse v2 execution plan already contains the canonical constrained/free
partition and the exact map from its full CSR values into ``K_ff``.  This
module packages only those immutable integer arrays for a future same-stream
HIP consumer.  It deliberately does not copy, describe as uploadable, or own
the reduced numeric values, and it does not replace the source plan's
``scipy_sparse_direct`` solver policy.

The retained CPU reduced-value descriptor is a verification-oracle binding
only.  A device context must materialize its numeric ``K_ff`` by gathering
from the assembly-owned full CSR with ``reduced_csr_global_value_indices``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field as dataclass_field, replace
from functools import lru_cache
import json
from pathlib import Path
from typing import Any, Literal

from jsonschema import Draft202012Validator
import numpy as np

from structural_analysis.engine_v2.contracts._canonical import (
    array_content_hash,
    array_data_hash,
    canonical_hash,
    has_immutable_bytes_backing,
)
from structural_analysis.engine_v2.contracts.execution_plan_v2 import (
    EXECUTION_PLAN_V2_CAPABILITY_PROFILE,
    EXECUTION_PLAN_V2_SCHEMA_VERSION,
    ExecutionPlanV2,
    ExecutionPlanV2Error,
    _detached_source_snapshot,
    validate_execution_plan_v2,
)

HIP_FREE_SPACE_OPERATOR_PLAN_V1_SCHEMA_VERSION = (
    "structural-analysis-hip-free-space-operator-plan.v1"
)
HIP_FREE_SPACE_OPERATOR_PLAN_V1_CAPABILITY_PROFILE = (
    "phase0_hip_free_space_symbolic_non_solver_overlay"
)
HIP_FREE_SPACE_OPERATOR_PLAN_V1_SOURCE_ROLE = (
    "operator_partition_verification_witness_not_solver_execution"
)
HIP_FREE_SPACE_OPERATOR_PLAN_V1_MATERIALIZATION = (
    "same_stream_device_gather_from_assembly_owned_full_csr"
)

_ZERO_HASH = "sha256:" + "0" * 64
_INT32_MAX = int(np.iinfo(np.int32).max)
_SOURCE_SOLVER_POLICY = "scipy_sparse_direct"
_ARRAY_NAMES = (
    "free_dofs",
    "global_to_free",
    "reduced_csr_row_ptr",
    "reduced_csr_column_indices",
    "reduced_csr_global_value_indices",
)
_REDUCED_ORACLE_ARRAY_NAME = "reduced_stiffness_csr_values"


class HipFreeSpaceOperatorPlanV1Error(ValueError):
    """Fail-closed free-space overlay error with stable code and path."""

    def __init__(self, code: str, path: str, message: str) -> None:
        self.code = code
        self.path = path
        self.message = message
        super().__init__(f"{code}@{path}: {message}")


@dataclass(frozen=True, slots=True)
class FreeSpaceArrayDescriptorV1:
    """Exact metadata and hashes for one uploadable symbolic array."""

    name: str
    dtype: Literal["<i4"]
    shape: tuple[int, ...]
    layout: Literal["C"]
    byte_length: int
    data_hash: str
    content_hash: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["shape"] = list(self.shape)
        return payload


@dataclass(frozen=True, slots=True)
class FreeSpaceVerificationOracleBindingV1:
    """Descriptor-only binding to CPU ``K_ff`` values; never an upload."""

    source_array_name: Literal["reduced_stiffness_csr_values"]
    dtype: Literal["<f8"]
    shape: tuple[int, ...]
    layout: Literal["C"]
    byte_length: int
    data_hash: str
    content_hash: str
    role: Literal["verification_oracle_only_never_device_input"] = (
        "verification_oracle_only_never_device_input"
    )
    device_upload_forbidden: Literal[True] = True

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["shape"] = list(self.shape)
        return payload


@dataclass(frozen=True, slots=True)
class HipFreeSpaceOperatorPlanV1:
    """Immutable symbolic-only overlay derived from one exact sparse plan."""

    schema_version: str
    capability_profile: str
    plan_id: str
    plan_hash: str
    free_space_view_hash: str

    source_execution_plan_schema_version: str
    source_execution_plan_capability_profile: str
    source_execution_plan_id: str
    source_execution_plan_hash: str
    source_operator_version: str
    source_operator_hash: str
    source_numeric_snapshot_hash: str
    source_symbolic_reuse_hash: str
    source_partition_hash: str
    source_model_ir_content_hash: str
    source_solver_artifact_hash: str
    source_load_pattern_id: str
    source_solver_policy: str

    global_dof_count: int
    constrained_dof_count: int
    free_dof_count: int
    full_csr_nnz: int
    reduced_csr_nnz: int

    descriptors: tuple[FreeSpaceArrayDescriptorV1, ...]
    verification_oracle: FreeSpaceVerificationOracleBindingV1
    _arrays: tuple[np.ndarray, ...] = dataclass_field(repr=False, compare=False)
    _source_execution_plan: ExecutionPlanV2 = dataclass_field(
        repr=False,
        compare=False,
    )

    def array(self, name: str) -> np.ndarray:
        try:
            index = _ARRAY_NAMES.index(name)
        except ValueError as exc:
            raise KeyError(f"Unknown HIP free-space overlay array: {name}") from exc
        return self._arrays[index]

    @property
    def described_array_byte_length(self) -> int:
        """Bytes in the five symbolic arrays; numeric ``K_ff`` is excluded."""

        return sum(row.byte_length for row in self.descriptors)

    def to_dict(self) -> dict[str, Any]:
        descriptors = {row.name: row.to_dict() for row in self.descriptors}
        return {
            "schema_version": self.schema_version,
            "capability_profile": self.capability_profile,
            "plan_id": self.plan_id,
            "source_contract": {
                "execution_plan_schema_version": (
                    self.source_execution_plan_schema_version
                ),
                "execution_plan_capability_profile": (
                    self.source_execution_plan_capability_profile
                ),
                "execution_plan_id": self.source_execution_plan_id,
                "execution_plan_hash": self.source_execution_plan_hash,
                "operator_version": self.source_operator_version,
                "operator_hash": self.source_operator_hash,
                "numeric_snapshot_hash": self.source_numeric_snapshot_hash,
                "symbolic_reuse_hash": self.source_symbolic_reuse_hash,
                "partition_hash": self.source_partition_hash,
                "model_ir_content_hash": self.source_model_ir_content_hash,
                "solver_artifact_hash": self.source_solver_artifact_hash,
                "load_pattern_id": self.source_load_pattern_id,
                "solver_policy": self.source_solver_policy,
                "source_plan_role": HIP_FREE_SPACE_OPERATOR_PLAN_V1_SOURCE_ROLE,
            },
            "dimensions": {
                "global_dof_count": self.global_dof_count,
                "constrained_dof_count": self.constrained_dof_count,
                "free_dof_count": self.free_dof_count,
                "full_csr_nnz": self.full_csr_nnz,
                "reduced_csr_nnz": self.reduced_csr_nnz,
            },
            "overlay_policy": {
                "kind": "device_free_space_symbolic_view",
                "solver_role": "none",
                "source_solver_policy_overridden": False,
                "numeric_materialization": (
                    HIP_FREE_SPACE_OPERATOR_PLAN_V1_MATERIALIZATION
                ),
                "prescribed_displacement_mode": "zero_only",
                "index_base": 0,
                "index_dtype": "<i4",
            },
            "symbolic_payload": {
                "format": "csr",
                "array_order": list(_ARRAY_NAMES),
                "described_array_byte_length": self.described_array_byte_length,
                "arrays": [descriptors[name] for name in _ARRAY_NAMES],
                "device_h2d_role": "symbolic_only",
                "reduced_numeric_values_present": False,
                "reduced_numeric_values_h2d_forbidden": True,
                "free_space_view_hash": self.free_space_view_hash,
            },
            "verification_oracle": self.verification_oracle.to_dict(),
            "claim_boundary": {
                "execution_performed": False,
                "device_allocation_performed": False,
                "device_numeric_materialization_performed": False,
                "solver_policy_overridden": False,
                "solver_ready": False,
                "device_resident_krylov_ready": False,
                "host_reduced_numeric_h2d_allowed": False,
                "end_to_end_O_N_claim": False,
                "performance_or_speedup_claim": False,
                "commercial_readiness": False,
            },
            "plan_hash": self.plan_hash,
            "extensions": {},
        }

    def to_manifest(self) -> dict[str, Any]:
        return self.to_dict()


def compile_hip_free_space_operator_plan_v1(
    source_plan: ExecutionPlanV2,
) -> HipFreeSpaceOperatorPlanV1:
    """Derive a detached symbolic overlay without changing source policy."""

    _validate_source_plan(source_plan)
    # Retain an independent source-buffer owner and a distinct plan object.
    # The plan arrays are immutable bytes-backed, while replacing a caller's
    # tuple or dataclass fields after this point cannot alter this witness.
    source_buffers = _detached_source_snapshot(source_plan._source_buffers)
    source_buffers = replace(
        source_buffers,
        descriptors=tuple(replace(row) for row in source_buffers.descriptors),
    )
    source_witness = replace(
        source_plan,
        descriptors=tuple(replace(row) for row in source_plan.descriptors),
        _arrays=tuple(list(source_plan._arrays)),
        _source_buffers=source_buffers,
    )
    _validate_source_plan(source_witness)

    derived = _derive_symbolic_arrays(source_witness)
    arrays = {
        name: _detached_immutable_array(derived[name], dtype="<i4")
        for name in _ARRAY_NAMES
    }
    for name in _ARRAY_NAMES:
        if not np.array_equal(arrays[name], source_witness.array(name)):
            _fail(
                "hip_free_space_source_rederivation_mismatch",
                f"/symbolic_payload/arrays/{name}",
                "Source plan symbolic array differs from independent rederivation.",
            )

    descriptors = tuple(_array_descriptor(name, arrays[name]) for name in _ARRAY_NAMES)
    oracle = _oracle_binding(source_witness)
    source_policy = _source_solver_policy(source_witness)
    artifact = HipFreeSpaceOperatorPlanV1(
        schema_version=HIP_FREE_SPACE_OPERATOR_PLAN_V1_SCHEMA_VERSION,
        capability_profile=HIP_FREE_SPACE_OPERATOR_PLAN_V1_CAPABILITY_PROFILE,
        plan_id="HipFreeSpacePlan:" + "0" * 24,
        plan_hash=_ZERO_HASH,
        free_space_view_hash=_ZERO_HASH,
        source_execution_plan_schema_version=source_witness.schema_version,
        source_execution_plan_capability_profile=source_witness.capability_profile,
        source_execution_plan_id=source_witness.plan_id,
        source_execution_plan_hash=source_witness.plan_hash,
        source_operator_version=source_witness.operator_version,
        source_operator_hash=source_witness.operator_hash,
        source_numeric_snapshot_hash=source_witness.numeric_snapshot_hash,
        source_symbolic_reuse_hash=source_witness.symbolic_reuse_hash,
        source_partition_hash=source_witness.partition_hash,
        source_model_ir_content_hash=source_witness.model_ir_content_hash,
        source_solver_artifact_hash=source_witness.solver_artifact_hash,
        source_load_pattern_id=source_witness.load_pattern_id,
        source_solver_policy=source_policy,
        global_dof_count=source_witness.dof_count,
        constrained_dof_count=int(source_witness.array("constrained_dofs").size),
        free_dof_count=int(source_witness.array("free_dofs").size),
        full_csr_nnz=source_witness.nnz,
        reduced_csr_nnz=source_witness.reduced_nnz,
        descriptors=descriptors,
        verification_oracle=oracle,
        _arrays=tuple(arrays[name] for name in _ARRAY_NAMES),
        _source_execution_plan=source_witness,
    )
    artifact = replace(
        artifact,
        free_space_view_hash=_free_space_view_hash(artifact),
    )
    artifact = replace(artifact, plan_id=_plan_id(artifact))
    artifact = replace(artifact, plan_hash=_plan_hash(artifact))
    validate_hip_free_space_operator_plan_v1(
        artifact,
        expected_execution_plan=source_plan,
    )
    return artifact


def validate_hip_free_space_operator_plan_v1(
    artifact: HipFreeSpaceOperatorPlanV1,
    *,
    expected_execution_plan: ExecutionPlanV2 | None = None,
) -> None:
    """Validate exact storage, source rederivation, policy, and all hashes."""

    if type(artifact) is not HipFreeSpaceOperatorPlanV1:
        _raise(
            "hip_free_space_plan_type_invalid",
            "/",
            "Expected an exact HipFreeSpaceOperatorPlanV1 instance.",
        )
    if (
        type(artifact.descriptors) is not tuple
        or any(
            type(row) is not FreeSpaceArrayDescriptorV1 for row in artifact.descriptors
        )
        or type(artifact.verification_oracle)
        is not FreeSpaceVerificationOracleBindingV1
        or type(artifact._arrays) is not tuple
        or len(artifact._arrays) != len(_ARRAY_NAMES)
        or any(type(array) is not np.ndarray for array in artifact._arrays)
        or type(artifact._source_execution_plan) is not ExecutionPlanV2
    ):
        _fail("hip_free_space_plan_container_invalid", "/symbolic_payload")

    try:
        manifest = artifact.to_dict()
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise HipFreeSpaceOperatorPlanV1Error(
            "hip_free_space_plan_manifest_invalid",
            "/",
            f"Cannot build free-space plan manifest: {exc}",
        ) from exc
    errors = sorted(
        _schema_validator().iter_errors(manifest),
        key=lambda error: list(error.absolute_path),
    )
    if errors:
        error = errors[0]
        path = "/" + "/".join(str(part) for part in error.absolute_path)
        raise HipFreeSpaceOperatorPlanV1Error(
            "hip_free_space_plan_schema_invalid", path, error.message
        )

    if artifact.schema_version != HIP_FREE_SPACE_OPERATOR_PLAN_V1_SCHEMA_VERSION:
        _fail("hip_free_space_plan_schema_mismatch", "/schema_version")
    if (
        artifact.capability_profile
        != HIP_FREE_SPACE_OPERATOR_PLAN_V1_CAPABILITY_PROFILE
    ):
        _fail("hip_free_space_plan_profile_mismatch", "/capability_profile")

    source = artifact._source_execution_plan
    _validate_source_plan(source)
    _validate_exact_scalar_types(artifact)
    _validate_source_bindings(artifact, source)
    if expected_execution_plan is not None:
        if type(expected_execution_plan) is not ExecutionPlanV2:
            _fail(
                "hip_free_space_expected_plan_invalid",
                "/source_contract",
                "Expected source must be an exact ExecutionPlanV2.",
            )
        _validate_source_plan(expected_execution_plan)
        _validate_source_bindings(artifact, expected_execution_plan)
        if expected_execution_plan.plan_hash != source.plan_hash:
            _fail(
                "hip_free_space_source_plan_mismatch",
                "/source_contract/execution_plan_hash",
            )

    expected_dimensions = {
        "global_dof_count": source.dof_count,
        "constrained_dof_count": int(source.array("constrained_dofs").size),
        "free_dof_count": int(source.array("free_dofs").size),
        "full_csr_nnz": source.nnz,
        "reduced_csr_nnz": source.reduced_nnz,
    }
    for name, expected in expected_dimensions.items():
        actual = getattr(artifact, name)
        _require_positive_int(actual, f"/dimensions/{name}")
        if actual != expected:
            _fail("hip_free_space_dimension_mismatch", f"/dimensions/{name}")
    if (
        artifact.constrained_dof_count + artifact.free_dof_count
        != artifact.global_dof_count
    ):
        _fail("hip_free_space_partition_count_mismatch", "/dimensions")

    descriptor_names = tuple(row.name for row in artifact.descriptors)
    if descriptor_names != _ARRAY_NAMES or len(set(descriptor_names)) != len(
        _ARRAY_NAMES
    ):
        _fail(
            "hip_free_space_descriptor_set_invalid",
            "/symbolic_payload/arrays",
        )
    expected_shapes = {
        "free_dofs": (artifact.free_dof_count,),
        "global_to_free": (artifact.global_dof_count,),
        "reduced_csr_row_ptr": (artifact.free_dof_count + 1,),
        "reduced_csr_column_indices": (artifact.reduced_csr_nnz,),
        "reduced_csr_global_value_indices": (artifact.reduced_csr_nnz,),
    }
    for descriptor in artifact.descriptors:
        array = artifact.array(descriptor.name)
        if (
            type(array) is not np.ndarray
            or array.dtype.str != "<i4"
            or array.shape != expected_shapes[descriptor.name]
            or not array.flags.c_contiguous
            or not has_immutable_bytes_backing(array)
        ):
            _fail(
                "hip_free_space_array_storage_invalid",
                f"/symbolic_payload/arrays/{descriptor.name}",
            )
        if _array_descriptor(descriptor.name, array) != descriptor:
            _fail(
                "hip_free_space_array_descriptor_mismatch",
                f"/symbolic_payload/arrays/{descriptor.name}",
            )
        source_descriptor = _source_descriptor(source, descriptor.name)
        if descriptor.to_dict() != source_descriptor.to_dict():
            _fail(
                "hip_free_space_source_descriptor_mismatch",
                f"/symbolic_payload/arrays/{descriptor.name}",
            )

    _validate_array_aliasing(artifact)
    independently_derived = _derive_symbolic_arrays(source)
    for name in _ARRAY_NAMES:
        actual = artifact.array(name)
        if not np.array_equal(actual, independently_derived[name]):
            _fail(
                "hip_free_space_source_rederivation_mismatch",
                f"/symbolic_payload/arrays/{name}",
            )
        if not np.array_equal(actual, source.array(name)):
            _fail(
                "hip_free_space_source_array_mismatch",
                f"/symbolic_payload/arrays/{name}",
            )
    _validate_symbolic_semantics(artifact)

    expected_oracle = _oracle_binding(source)
    if artifact.verification_oracle != expected_oracle:
        _fail(
            "hip_free_space_oracle_binding_mismatch",
            "/verification_oracle",
        )
    if artifact.free_space_view_hash != _free_space_view_hash(artifact):
        _fail(
            "hip_free_space_view_hash_mismatch",
            "/symbolic_payload/free_space_view_hash",
        )
    if artifact.plan_id != _plan_id(artifact):
        _fail("hip_free_space_plan_id_mismatch", "/plan_id")
    if artifact.plan_hash != _plan_hash(artifact):
        _fail("hip_free_space_plan_hash_mismatch", "/plan_hash")


def _validate_source_plan(source_plan: ExecutionPlanV2) -> None:
    if type(source_plan) is not ExecutionPlanV2:
        _raise(
            "hip_free_space_source_plan_invalid",
            "/source_contract",
            "Source must be an exact ExecutionPlanV2.",
        )
    try:
        validate_execution_plan_v2(
            source_plan,
            expected_buffers=source_plan._source_buffers,
        )
    except (AttributeError, ExecutionPlanV2Error) as exc:
        path = getattr(exc, "path", "/source_contract")
        code = getattr(exc, "code", type(exc).__name__)
        message = getattr(exc, "message", str(exc))
        raise HipFreeSpaceOperatorPlanV1Error(
            "hip_free_space_source_plan_invalid",
            path,
            f"{code}: {message}",
        ) from exc
    if source_plan.schema_version != EXECUTION_PLAN_V2_SCHEMA_VERSION:
        _fail(
            "hip_free_space_source_schema_mismatch",
            "/source_contract/execution_plan_schema_version",
        )
    if source_plan.capability_profile != EXECUTION_PLAN_V2_CAPABILITY_PROFILE:
        _fail(
            "hip_free_space_source_profile_mismatch",
            "/source_contract/execution_plan_capability_profile",
        )
    if _source_solver_policy(source_plan) != _SOURCE_SOLVER_POLICY:
        _fail(
            "hip_free_space_source_solver_policy_mismatch",
            "/source_contract/solver_policy",
        )


def _validate_source_bindings(
    artifact: HipFreeSpaceOperatorPlanV1,
    source: ExecutionPlanV2,
) -> None:
    bindings = (
        (
            artifact.source_execution_plan_schema_version,
            source.schema_version,
            "execution_plan_schema_version",
        ),
        (
            artifact.source_execution_plan_capability_profile,
            source.capability_profile,
            "execution_plan_capability_profile",
        ),
        (artifact.source_execution_plan_id, source.plan_id, "execution_plan_id"),
        (artifact.source_execution_plan_hash, source.plan_hash, "execution_plan_hash"),
        (artifact.source_operator_version, source.operator_version, "operator_version"),
        (artifact.source_operator_hash, source.operator_hash, "operator_hash"),
        (
            artifact.source_numeric_snapshot_hash,
            source.numeric_snapshot_hash,
            "numeric_snapshot_hash",
        ),
        (
            artifact.source_symbolic_reuse_hash,
            source.symbolic_reuse_hash,
            "symbolic_reuse_hash",
        ),
        (artifact.source_partition_hash, source.partition_hash, "partition_hash"),
        (
            artifact.source_model_ir_content_hash,
            source.model_ir_content_hash,
            "model_ir_content_hash",
        ),
        (
            artifact.source_solver_artifact_hash,
            source.solver_artifact_hash,
            "solver_artifact_hash",
        ),
        (artifact.source_load_pattern_id, source.load_pattern_id, "load_pattern_id"),
        (
            artifact.source_solver_policy,
            _source_solver_policy(source),
            "solver_policy",
        ),
    )
    for actual, expected, name in bindings:
        if actual != expected:
            _fail(
                "hip_free_space_source_binding_mismatch",
                f"/source_contract/{name}",
            )


def _derive_symbolic_arrays(source: ExecutionPlanV2) -> dict[str, np.ndarray]:
    """Independently reconstruct free partition and reduced CSR in O(G+Z)."""

    global_dof_count = source.dof_count
    support_mask = source._source_buffers.array("support_mask").reshape(-1)
    if support_mask.size != global_dof_count:
        _fail(
            "hip_free_space_support_shape_invalid",
            "/source_contract/partition_hash",
        )
    constrained = np.asarray(np.flatnonzero(support_mask), dtype="<i4")
    free_mask = np.ones(global_dof_count, dtype=np.bool_)
    free_mask[constrained] = False
    free = np.asarray(np.flatnonzero(free_mask), dtype="<i4")
    if not free.size or not constrained.size:
        _fail(
            "hip_free_space_partition_empty",
            "/source_contract/partition_hash",
        )
    global_to_free = np.full(global_dof_count, -1, dtype="<i4")
    global_to_free[free] = np.arange(free.size, dtype="<i4")

    full_row_ptr = source.array("csr_row_ptr")
    full_columns = source.array("csr_column_indices")
    reduced_row_ptr = [0]
    reduced_columns: list[int] = []
    reduced_global_positions: list[int] = []
    for global_row_value in free:
        global_row = int(global_row_value)
        start = int(full_row_ptr[global_row])
        stop = int(full_row_ptr[global_row + 1])
        for full_position in range(start, stop):
            global_column = int(full_columns[full_position])
            reduced_column = int(global_to_free[global_column])
            if reduced_column >= 0:
                reduced_columns.append(reduced_column)
                reduced_global_positions.append(full_position)
        reduced_row_ptr.append(len(reduced_columns))
    if len(reduced_columns) > _INT32_MAX:
        _fail(
            "hip_free_space_int32_capacity_exceeded",
            "/dimensions/reduced_csr_nnz",
        )
    return {
        "free_dofs": np.asarray(free, dtype="<i4"),
        "global_to_free": np.asarray(global_to_free, dtype="<i4"),
        "reduced_csr_row_ptr": np.asarray(reduced_row_ptr, dtype="<i4"),
        "reduced_csr_column_indices": np.asarray(reduced_columns, dtype="<i4"),
        "reduced_csr_global_value_indices": np.asarray(
            reduced_global_positions, dtype="<i4"
        ),
    }


def _validate_symbolic_semantics(artifact: HipFreeSpaceOperatorPlanV1) -> None:
    free = artifact.array("free_dofs")
    global_to_free = artifact.array("global_to_free")
    row_ptr = artifact.array("reduced_csr_row_ptr")
    columns = artifact.array("reduced_csr_column_indices")
    mapping = artifact.array("reduced_csr_global_value_indices")
    if np.any(np.diff(free.astype(np.int64, copy=False)) <= 0):
        _fail("hip_free_space_free_dofs_invalid", "/symbolic_payload/arrays/free_dofs")
    expected_map = np.full(artifact.global_dof_count, -1, dtype="<i4")
    expected_map[free] = np.arange(artifact.free_dof_count, dtype="<i4")
    if not np.array_equal(global_to_free, expected_map):
        _fail(
            "hip_free_space_global_to_free_invalid",
            "/symbolic_payload/arrays/global_to_free",
        )
    if (
        int(row_ptr[0]) != 0
        or int(row_ptr[-1]) != artifact.reduced_csr_nnz
        or np.any(np.diff(row_ptr.astype(np.int64, copy=False)) <= 0)
    ):
        _fail(
            "hip_free_space_row_ptr_invalid",
            "/symbolic_payload/arrays/reduced_csr_row_ptr",
        )
    if (
        np.any(columns < 0)
        or np.any(columns >= artifact.free_dof_count)
        or np.any(mapping < 0)
        or np.any(mapping >= artifact.full_csr_nnz)
    ):
        _fail("hip_free_space_index_range_invalid", "/symbolic_payload/arrays")
    if mapping.size > 1 and np.any(np.diff(mapping.astype(np.int64, copy=False)) <= 0):
        _fail(
            "hip_free_space_global_value_mapping_invalid",
            "/symbolic_payload/arrays/reduced_csr_global_value_indices",
        )
    for row in range(artifact.free_dof_count):
        begin = int(row_ptr[row])
        end = int(row_ptr[row + 1])
        row_columns = columns[begin:end]
        if (
            not row_columns.size
            or np.any(np.diff(row_columns.astype(np.int64, copy=False)) <= 0)
            or np.count_nonzero(row_columns == row) != 1
        ):
            _fail(
                "hip_free_space_reduced_row_invalid",
                "/symbolic_payload/arrays/reduced_csr_column_indices",
            )


def _validate_exact_scalar_types(artifact: HipFreeSpaceOperatorPlanV1) -> None:
    for name in (
        "global_dof_count",
        "constrained_dof_count",
        "free_dof_count",
        "full_csr_nnz",
        "reduced_csr_nnz",
    ):
        _require_positive_int(getattr(artifact, name), f"/dimensions/{name}")
    for name in (
        "schema_version",
        "capability_profile",
        "plan_id",
        "plan_hash",
        "free_space_view_hash",
        "source_execution_plan_schema_version",
        "source_execution_plan_capability_profile",
        "source_execution_plan_id",
        "source_execution_plan_hash",
        "source_operator_version",
        "source_operator_hash",
        "source_numeric_snapshot_hash",
        "source_symbolic_reuse_hash",
        "source_partition_hash",
        "source_model_ir_content_hash",
        "source_solver_artifact_hash",
        "source_load_pattern_id",
        "source_solver_policy",
    ):
        if type(getattr(artifact, name)) is not str:
            _fail("hip_free_space_scalar_type_invalid", f"/{name}")


def _validate_array_aliasing(artifact: HipFreeSpaceOperatorPlanV1) -> None:
    arrays = list(artifact._arrays)
    for left in range(len(arrays)):
        for right in range(left + 1, len(arrays)):
            if np.shares_memory(arrays[left], arrays[right]):
                _fail(
                    "hip_free_space_array_alias_invalid",
                    "/symbolic_payload/arrays",
                )
    source = artifact._source_execution_plan
    source_arrays = list(source._arrays) + [
        source._source_buffers.array(row.name)
        for row in source._source_buffers.descriptors
    ]
    for array in arrays:
        if any(np.shares_memory(array, source_array) for source_array in source_arrays):
            _fail(
                "hip_free_space_array_alias_invalid",
                "/symbolic_payload/arrays",
            )


def _array_descriptor(name: str, array: np.ndarray) -> FreeSpaceArrayDescriptorV1:
    metadata = {
        "name": name,
        "dtype": array.dtype.str,
        "shape": [int(value) for value in array.shape],
        "layout": "C",
        "byte_length": int(array.nbytes),
    }
    return FreeSpaceArrayDescriptorV1(
        name=name,
        dtype="<i4",
        shape=tuple(int(value) for value in array.shape),
        layout="C",
        byte_length=int(array.nbytes),
        data_hash=array_data_hash(array),
        content_hash=array_content_hash(metadata, array),
    )


def _oracle_binding(source: ExecutionPlanV2) -> FreeSpaceVerificationOracleBindingV1:
    descriptor = _source_descriptor(source, _REDUCED_ORACLE_ARRAY_NAME)
    return FreeSpaceVerificationOracleBindingV1(
        source_array_name=_REDUCED_ORACLE_ARRAY_NAME,
        dtype="<f8",
        shape=tuple(descriptor.shape),
        layout="C",
        byte_length=descriptor.byte_length,
        data_hash=descriptor.data_hash,
        content_hash=descriptor.content_hash,
    )


def _source_descriptor(source: ExecutionPlanV2, name: str) -> Any:
    for descriptor in source.descriptors:
        if descriptor.name == name:
            return descriptor
    _fail(
        "hip_free_space_source_descriptor_missing",
        f"/source_contract/{name}",
    )


def _source_solver_policy(source: ExecutionPlanV2) -> str:
    try:
        value = source.to_dict()["solver_policy"]["linear_solver"]
    except (KeyError, TypeError) as exc:
        raise HipFreeSpaceOperatorPlanV1Error(
            "hip_free_space_source_solver_policy_missing",
            "/source_contract/solver_policy",
            "Source plan has no canonical linear solver policy.",
        ) from exc
    if type(value) is not str:
        _fail(
            "hip_free_space_source_solver_policy_invalid",
            "/source_contract/solver_policy",
        )
    return value


def _free_space_view_hash(artifact: HipFreeSpaceOperatorPlanV1) -> str:
    return canonical_hash(
        {
            "schema_version": HIP_FREE_SPACE_OPERATOR_PLAN_V1_SCHEMA_VERSION,
            "capability_profile": HIP_FREE_SPACE_OPERATOR_PLAN_V1_CAPABILITY_PROFILE,
            "source_execution_plan_hash": artifact.source_execution_plan_hash,
            "source_operator_hash": artifact.source_operator_hash,
            "source_numeric_snapshot_hash": artifact.source_numeric_snapshot_hash,
            "source_symbolic_reuse_hash": artifact.source_symbolic_reuse_hash,
            "source_partition_hash": artifact.source_partition_hash,
            "source_solver_policy": artifact.source_solver_policy,
            "source_solver_policy_overridden": False,
            "source_plan_role": HIP_FREE_SPACE_OPERATOR_PLAN_V1_SOURCE_ROLE,
            "numeric_materialization": (
                HIP_FREE_SPACE_OPERATOR_PLAN_V1_MATERIALIZATION
            ),
            "prescribed_displacement_mode": "zero_only",
            "dimensions": {
                "global_dof_count": artifact.global_dof_count,
                "constrained_dof_count": artifact.constrained_dof_count,
                "free_dof_count": artifact.free_dof_count,
                "full_csr_nnz": artifact.full_csr_nnz,
                "reduced_csr_nnz": artifact.reduced_csr_nnz,
            },
            "symbolic_arrays": [row.to_dict() for row in artifact.descriptors],
            "verification_oracle": artifact.verification_oracle.to_dict(),
            "reduced_numeric_values_present": False,
            "reduced_numeric_values_h2d_forbidden": True,
        }
    )


def _plan_id(artifact: HipFreeSpaceOperatorPlanV1) -> str:
    digest = canonical_hash(
        {
            "source_execution_plan_hash": artifact.source_execution_plan_hash,
            "free_space_view_hash": artifact.free_space_view_hash,
        }
    )
    return "HipFreeSpacePlan:" + digest.removeprefix("sha256:")[:24]


def _plan_hash(artifact: HipFreeSpaceOperatorPlanV1) -> str:
    payload = artifact.to_dict()
    payload.pop("plan_hash")
    return canonical_hash(payload)


def _detached_immutable_array(value: Any, *, dtype: Any) -> np.ndarray:
    target_dtype = np.dtype(dtype).newbyteorder("<")
    contiguous = np.ascontiguousarray(value, dtype=target_dtype)
    payload = contiguous.tobytes(order="C")
    # A private padding byte prevents tiny equal bytes objects from being
    # interned into an accidental alias while leaving the view/hash exact.
    backing = bytes(bytearray(payload + b"\xa5"))
    return np.frombuffer(
        backing,
        dtype=target_dtype,
        count=contiguous.size,
    ).reshape(contiguous.shape)


def _require_positive_int(value: Any, path: str) -> None:
    if type(value) is not int or value <= 0 or value > _INT32_MAX:
        _fail(
            "hip_free_space_dimension_invalid",
            path,
            "Dimension must be an exact positive signed-int32 integer.",
        )


@lru_cache(maxsize=1)
def _schema_validator() -> Draft202012Validator:
    schema_path = (
        Path(__file__).resolve().parents[2]
        / "schemas"
        / "hip_free_space_operator_plan_v1.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _fail(code: str, path: str, message: str | None = None) -> None:
    raise HipFreeSpaceOperatorPlanV1Error(code, path, message or code)


def _raise(code: str, path: str, message: str) -> None:
    raise HipFreeSpaceOperatorPlanV1Error(code, path, message)


__all__ = [
    "HIP_FREE_SPACE_OPERATOR_PLAN_V1_CAPABILITY_PROFILE",
    "HIP_FREE_SPACE_OPERATOR_PLAN_V1_MATERIALIZATION",
    "HIP_FREE_SPACE_OPERATOR_PLAN_V1_SCHEMA_VERSION",
    "HIP_FREE_SPACE_OPERATOR_PLAN_V1_SOURCE_ROLE",
    "FreeSpaceArrayDescriptorV1",
    "FreeSpaceVerificationOracleBindingV1",
    "HipFreeSpaceOperatorPlanV1",
    "HipFreeSpaceOperatorPlanV1Error",
    "compile_hip_free_space_operator_plan_v1",
    "validate_hip_free_space_operator_plan_v1",
]
