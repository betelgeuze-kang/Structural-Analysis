"""CPU compiler for the Engine v2 HIP element-assembly symbolic plan.

The artifact produced here is deliberately a *symbolic* device-input plan.  It
contains the local-frame reference-axis decision and the inverse mapping from
each retained CSR slot to the element/local matrix contributions that target
that slot.  It neither copies CSR numerical values nor performs HIP work.

The three described arrays are detached, immutable byte-backed snapshots.  A
validated source ``ExecutionPlanV2`` and ``SolverModelBuffers`` are retained
only as validation witnesses; they are not part of the described/uploadable
assembly payload.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field as dataclass_field, replace
from functools import lru_cache
import json
import math
from pathlib import Path
from typing import Any, Mapping

from jsonschema import Draft202012Validator
import numpy as np

from structural_analysis.engine_v2.backends.cpu_reference.linear_static import (
    CPUReferenceError,
    _frame_transform,
)
from structural_analysis.engine_v2.buffers import (
    SOLVER_MODEL_BUFFERS_SCHEMA_VERSION,
    SolverModelBuffers,
)
from structural_analysis.engine_v2.contracts._canonical import (
    array_content_hash,
    array_data_hash,
    canonical_hash,
    has_immutable_bytes_backing,
    immutable_array,
)
from structural_analysis.engine_v2.contracts.execution_plan_v2 import (
    EXECUTION_PLAN_V2_CAPABILITY_PROFILE,
    EXECUTION_PLAN_V2_SCHEMA_VERSION,
    ExecutionPlanV2,
    ExecutionPlanV2Error,
    _detached_source_snapshot,
    validate_execution_plan_v2,
)


HIP_ASSEMBLY_PLAN_V1_SCHEMA_VERSION = "structural-analysis-hip-assembly-plan.v1"
HIP_ASSEMBLY_PLAN_V1_CAPABILITY_PROFILE = "phase0_hip_element_assembly_symbolic_plan"
HIP_ASSEMBLY_PLAN_V1_AXIS_POLICY = (
    "cpu_reference_global_z_unless_abs_local_x_z_gt_0_9_v1"
)
HIP_ASSEMBLY_PLAN_V1_ASSEMBLY_ORDER = (
    "element_index_then_local_row_then_local_column_v1"
)
HIP_ASSEMBLY_PLAN_V1_REVERSE_ORDER = "csr_slot_then_stable_source_contribution_index_v1"

# Kernel ABI values.  Zero and all values other than these two are invalid.
REFERENCE_AXIS_GLOBAL_Y = 1
REFERENCE_AXIS_GLOBAL_Z = 2
REFERENCE_AXIS_SWITCH_THRESHOLD = 0.9

_DOFS_PER_ELEMENT = 12
_CONTRIBUTIONS_PER_ELEMENT = _DOFS_PER_ELEMENT * _DOFS_PER_ELEMENT
_INT32_MAX = int(np.iinfo(np.int32).max)
_ZERO_HASH = "sha256:" + "0" * 64
_ARRAY_NAMES = (
    "reference_axis_code",
    "reverse_segment_offsets",
    "reverse_contribution_indices",
)
_ARRAY_DTYPES = {
    "reference_axis_code": "|u1",
    "reverse_segment_offsets": "<i4",
    "reverse_contribution_indices": "<i4",
}


class HipAssemblyPlanV1Error(ValueError):
    """Fail-closed assembly-plan error with a stable code and JSON pointer."""

    def __init__(self, code: str, path: str, message: str) -> None:
        self.code = code
        self.path = path
        self.message = message
        super().__init__(f"{code}@{path}: {message}")


@dataclass(frozen=True)
class AssemblyArrayDescriptorV1:
    """Canonical metadata and exact-byte hashes for one symbolic array."""

    name: str
    dtype: str
    shape: tuple[int, ...]
    layout: str
    byte_length: int
    data_hash: str
    content_hash: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["shape"] = list(self.shape)
        return payload


@dataclass(frozen=True)
class HipAssemblyPlanV1:
    """Immutable CPU-compiled symbolic input for future HIP assembly kernels."""

    schema_version: str
    capability_profile: str
    assembly_plan_id: str
    assembly_plan_hash: str

    model_ir_content_hash: str
    solver_buffer_schema_version: str
    solver_numeric_buffer_hash: str
    solver_entity_mapping_hash: str
    solver_artifact_hash: str
    load_pattern_id: str

    source_execution_plan_schema_version: str
    source_execution_plan_capability_profile: str
    source_execution_plan_id: str
    source_execution_plan_hash: str
    source_operator_version: str
    source_element_operator_version: str
    source_symbolic_reuse_hash: str
    source_partition_hash: str
    source_ordering_hash: str
    source_scatter_content_hash: str
    source_geometry_hash: str
    source_support_partition_hash: str

    node_count: int
    element_count: int
    dof_count: int
    csr_nnz: int
    contributions_per_element: int
    contribution_count: int

    axis_policy_hash: str
    reverse_map_hash: str
    symbolic_payload_hash: str
    descriptors: tuple[AssemblyArrayDescriptorV1, ...]
    _arrays: tuple[np.ndarray, ...] = dataclass_field(repr=False, compare=False)
    _source_buffers: SolverModelBuffers = dataclass_field(
        repr=False,
        compare=False,
    )
    _source_execution_plan: ExecutionPlanV2 = dataclass_field(
        repr=False,
        compare=False,
    )

    def array(self, name: str) -> np.ndarray:
        try:
            index = _ARRAY_NAMES.index(name)
        except ValueError as exc:
            raise KeyError(f"Unknown HIP assembly-plan array: {name}") from exc
        return self._arrays[index]

    @property
    def described_array_byte_length(self) -> int:
        """Bytes in the three uploadable symbolic arrays only."""

        return sum(row.byte_length for row in self.descriptors)

    def to_dict(self) -> dict[str, Any]:
        descriptors = {row.name: row.to_dict() for row in self.descriptors}
        return {
            "schema_version": self.schema_version,
            "capability_profile": self.capability_profile,
            "assembly_plan_id": self.assembly_plan_id,
            "input_binding": {
                "model_ir_content_hash": self.model_ir_content_hash,
                "solver_buffer_schema_version": self.solver_buffer_schema_version,
                "solver_numeric_buffer_hash": self.solver_numeric_buffer_hash,
                "solver_entity_mapping_hash": self.solver_entity_mapping_hash,
                "solver_artifact_hash": self.solver_artifact_hash,
                "load_pattern_id": self.load_pattern_id,
            },
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
                "element_operator_version": self.source_element_operator_version,
                "symbolic_reuse_hash": self.source_symbolic_reuse_hash,
                "partition_hash": self.source_partition_hash,
                "ordering_hash": self.source_ordering_hash,
                "scatter_content_hash": self.source_scatter_content_hash,
                "geometry_hash": self.source_geometry_hash,
                "support_partition_hash": self.source_support_partition_hash,
            },
            "dimensions": {
                "node_count": self.node_count,
                "element_count": self.element_count,
                "dof_count": self.dof_count,
                "csr_nnz": self.csr_nnz,
                "dofs_per_element": _DOFS_PER_ELEMENT,
                "contributions_per_element": self.contributions_per_element,
                "contribution_count": self.contribution_count,
                "reverse_segment_count": self.csr_nnz,
            },
            "axis_policy": {
                "policy": HIP_ASSEMBLY_PLAN_V1_AXIS_POLICY,
                "default_reference_axis": "global_z",
                "switch_reference_axis": "global_y",
                "switch_comparison": "abs_local_x_z_strictly_greater_than",
                "switch_threshold": REFERENCE_AXIS_SWITCH_THRESHOLD,
                "codes": {
                    "global_y": REFERENCE_AXIS_GLOBAL_Y,
                    "global_z": REFERENCE_AXIS_GLOBAL_Z,
                },
                "reference_axis_code": self.array("reference_axis_code").tolist(),
                "axis_policy_hash": self.axis_policy_hash,
            },
            "reverse_assembly_plan": {
                "source_format": "csr",
                "source_assembly_order": HIP_ASSEMBLY_PLAN_V1_ASSEMBLY_ORDER,
                "contribution_index_order": HIP_ASSEMBLY_PLAN_V1_ASSEMBLY_ORDER,
                "reverse_segment_order": HIP_ASSEMBLY_PLAN_V1_REVERSE_ORDER,
                "structural_zero_segments_retained": True,
                "reverse_segment_offsets": self.array(
                    "reverse_segment_offsets"
                ).tolist(),
                "reverse_contribution_indices": self.array(
                    "reverse_contribution_indices"
                ).tolist(),
                "reverse_map_hash": self.reverse_map_hash,
            },
            "symbolic_payload": {
                "index_base": 0,
                "index_dtype": "<i4",
                "axis_code_dtype": "|u1",
                "csr_numeric_values_present": False,
                "described_array_byte_length": self.described_array_byte_length,
                "arrays": [descriptors[name] for name in _ARRAY_NAMES],
                "symbolic_payload_hash": self.symbolic_payload_hash,
            },
            "claim_boundary": {
                "compiler_location": "cpu",
                "reverse_compile_complexity": "O(C+Z)_fixed_12x12_scatter",
                "manifest_serialization_complexity": (
                    "O(C+Z)_with_high_transient_python_object_memory"
                ),
                "contribution_formula": "C=144E",
                "global_dense_matrix_materialized": False,
                "csr_numeric_values_copied_or_described": False,
                "hip_execution_performed": False,
                "device_allocation_performed": False,
                "numerical_assembly_performed": False,
                "solver_ready": False,
                "end_to_end_O_N_claim": False,
                "commercial_solver_parity_claim": False,
            },
            "assembly_plan_hash": self.assembly_plan_hash,
            "extensions": {},
        }

    def to_manifest(self) -> dict[str, Any]:
        return self.to_dict()


def compile_hip_assembly_plan_v1(
    buffers: SolverModelBuffers,
    execution_plan: ExecutionPlanV2,
) -> HipAssemblyPlanV1:
    """Compile and fully validate the CPU-side HIP assembly symbolic plan."""

    _validate_sources(buffers, execution_plan)
    # Never retain caller-owned mapping containers as validation witnesses.
    # ExecutionPlanV2 already binds an independently validated source-buffer
    # snapshot; detach that snapshot once more and retain a separate plan
    # object so a caller cannot invalidate this artifact after compilation by
    # replacing a MappingProxyType backing entry or a plan field.
    source_buffers = _detached_source_snapshot(execution_plan._source_buffers)
    source_execution_plan = replace(
        execution_plan,
        _source_buffers=source_buffers,
    )
    _validate_sources(buffers, source_execution_plan)
    contribution_count = _guard_dimensions(
        node_count=source_execution_plan.node_count,
        element_count=source_execution_plan.element_count,
        dof_count=source_execution_plan.dof_count,
        csr_nnz=source_execution_plan.nnz,
    )

    reference_axis_code = _compile_reference_axis_codes(source_buffers)
    reverse_offsets, reverse_indices = _compile_reverse_map(
        source_execution_plan.array("csr_element_scatter_indices"),
        csr_nnz=source_execution_plan.nnz,
    )
    if reverse_indices.size != contribution_count:  # pragma: no cover - guard invariant
        _raise(
            "hip_assembly_plan_contribution_count_mismatch",
            "/dimensions/contribution_count",
            "Compiled reverse map does not contain exactly 144E contributions.",
        )

    arrays = {
        "reference_axis_code": _detached_immutable_array(
            reference_axis_code, dtype="u1"
        ),
        "reverse_segment_offsets": _detached_immutable_array(
            reverse_offsets, dtype="<i4"
        ),
        "reverse_contribution_indices": _detached_immutable_array(
            reverse_indices, dtype="<i4"
        ),
    }
    descriptors = tuple(_array_descriptor(name, arrays[name]) for name in _ARRAY_NAMES)
    scatter_descriptor = _source_plan_descriptor(
        source_execution_plan, "csr_element_scatter_indices"
    )

    artifact = HipAssemblyPlanV1(
        schema_version=HIP_ASSEMBLY_PLAN_V1_SCHEMA_VERSION,
        capability_profile=HIP_ASSEMBLY_PLAN_V1_CAPABILITY_PROFILE,
        assembly_plan_id="HipAssemblyPlan:" + "0" * 24,
        assembly_plan_hash=_ZERO_HASH,
        model_ir_content_hash=source_buffers.model_ir_content_hash,
        solver_buffer_schema_version=source_buffers.schema_version,
        solver_numeric_buffer_hash=source_buffers.numeric_buffer_hash,
        solver_entity_mapping_hash=source_buffers.entity_mapping_hash,
        solver_artifact_hash=source_buffers.artifact_hash,
        load_pattern_id=source_buffers.load_pattern_id,
        source_execution_plan_schema_version=source_execution_plan.schema_version,
        source_execution_plan_capability_profile=(
            source_execution_plan.capability_profile
        ),
        source_execution_plan_id=source_execution_plan.plan_id,
        source_execution_plan_hash=source_execution_plan.plan_hash,
        source_operator_version=source_execution_plan.operator_version,
        source_element_operator_version=(
            source_execution_plan.source_element_operator_version
        ),
        source_symbolic_reuse_hash=source_execution_plan.symbolic_reuse_hash,
        source_partition_hash=source_execution_plan.partition_hash,
        source_ordering_hash=source_execution_plan.ordering_hash,
        source_scatter_content_hash=scatter_descriptor.content_hash,
        source_geometry_hash=_source_geometry_hash(source_buffers),
        source_support_partition_hash=_source_support_partition_hash(
            source_buffers, source_execution_plan
        ),
        node_count=source_execution_plan.node_count,
        element_count=source_execution_plan.element_count,
        dof_count=source_execution_plan.dof_count,
        csr_nnz=source_execution_plan.nnz,
        contributions_per_element=_CONTRIBUTIONS_PER_ELEMENT,
        contribution_count=contribution_count,
        axis_policy_hash=_ZERO_HASH,
        reverse_map_hash=_ZERO_HASH,
        symbolic_payload_hash=_ZERO_HASH,
        descriptors=descriptors,
        _arrays=tuple(arrays[name] for name in _ARRAY_NAMES),
        _source_buffers=source_buffers,
        _source_execution_plan=source_execution_plan,
    )
    descriptor_map = {row.name: row for row in descriptors}
    artifact = replace(
        artifact,
        axis_policy_hash=_axis_policy_hash(artifact, descriptor_map),
        reverse_map_hash=_reverse_map_hash(artifact, descriptor_map),
    )
    artifact = replace(
        artifact,
        symbolic_payload_hash=_symbolic_payload_hash(artifact, descriptor_map),
    )
    artifact = replace(
        artifact,
        assembly_plan_id=_assembly_plan_id(artifact),
    )
    artifact = replace(
        artifact,
        assembly_plan_hash=_assembly_plan_hash(artifact),
    )
    validate_hip_assembly_plan_v1(
        artifact,
        expected_buffers=buffers,
        expected_execution_plan=execution_plan,
    )
    return artifact


def validate_hip_assembly_plan_v1(
    artifact: HipAssemblyPlanV1,
    *,
    expected_buffers: SolverModelBuffers | None = None,
    expected_execution_plan: ExecutionPlanV2 | None = None,
) -> None:
    """Validate sources, exact storage, semantics, and every derived hash."""

    if type(artifact) is not HipAssemblyPlanV1:
        _raise(
            "hip_assembly_plan_type_invalid",
            "/",
            "Expected an exact HipAssemblyPlanV1 instance.",
        )
    if (
        type(artifact.descriptors) is not tuple
        or any(
            type(row) is not AssemblyArrayDescriptorV1 for row in artifact.descriptors
        )
        or type(artifact._arrays) is not tuple
        or len(artifact._arrays) != len(_ARRAY_NAMES)
        or any(type(array) is not np.ndarray for array in artifact._arrays)
        or type(artifact._source_buffers) is not SolverModelBuffers
        or type(artifact._source_execution_plan) is not ExecutionPlanV2
    ):
        _fail("hip_assembly_plan_container_invalid", "/symbolic_payload")

    try:
        manifest = artifact.to_dict()
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise HipAssemblyPlanV1Error(
            "hip_assembly_plan_manifest_invalid",
            "/",
            f"Cannot build assembly-plan manifest: {exc}",
        ) from exc
    errors = sorted(
        _schema_validator().iter_errors(manifest),
        key=lambda error: list(error.absolute_path),
    )
    if errors:
        error = errors[0]
        path = "/" + "/".join(str(part) for part in error.absolute_path)
        raise HipAssemblyPlanV1Error(
            "hip_assembly_plan_schema_invalid", path, error.message
        )

    if artifact.schema_version != HIP_ASSEMBLY_PLAN_V1_SCHEMA_VERSION:
        _fail("hip_assembly_plan_schema_mismatch", "/schema_version")
    if artifact.capability_profile != HIP_ASSEMBLY_PLAN_V1_CAPABILITY_PROFILE:
        _fail("hip_assembly_plan_profile_mismatch", "/capability_profile")
    if artifact.solver_buffer_schema_version != SOLVER_MODEL_BUFFERS_SCHEMA_VERSION:
        _fail(
            "hip_assembly_plan_buffer_schema_mismatch",
            "/input_binding/solver_buffer_schema_version",
        )
    if (
        artifact.source_execution_plan_schema_version
        != EXECUTION_PLAN_V2_SCHEMA_VERSION
    ):
        _fail(
            "hip_assembly_plan_source_schema_mismatch",
            "/source_contract/execution_plan_schema_version",
        )
    if (
        artifact.source_execution_plan_capability_profile
        != EXECUTION_PLAN_V2_CAPABILITY_PROFILE
    ):
        _fail(
            "hip_assembly_plan_source_profile_mismatch",
            "/source_contract/execution_plan_capability_profile",
        )

    source_buffers = artifact._source_buffers
    source_plan = artifact._source_execution_plan
    _validate_sources(source_buffers, source_plan)
    _validate_source_bindings(artifact, source_buffers, source_plan)

    if expected_buffers is not None:
        if type(expected_buffers) is not SolverModelBuffers:
            _fail("hip_assembly_plan_expected_buffer_invalid", "/input_binding")
        _validate_sources(expected_buffers, source_plan)
        _validate_source_bindings(artifact, expected_buffers, source_plan)
        if expected_buffers.artifact_hash != source_buffers.artifact_hash:
            _fail(
                "hip_assembly_plan_source_buffer_mismatch",
                "/input_binding/solver_artifact_hash",
            )
    if expected_execution_plan is not None:
        if type(expected_execution_plan) is not ExecutionPlanV2:
            _fail(
                "hip_assembly_plan_expected_execution_plan_invalid",
                "/source_contract",
            )
        validation_buffers = expected_buffers or source_buffers
        _validate_sources(validation_buffers, expected_execution_plan)
        _validate_source_bindings(artifact, validation_buffers, expected_execution_plan)
        if expected_execution_plan.plan_hash != source_plan.plan_hash:
            _fail(
                "hip_assembly_plan_source_execution_plan_mismatch",
                "/source_contract/execution_plan_hash",
            )

    expected_contribution_count = _guard_dimensions(
        node_count=artifact.node_count,
        element_count=artifact.element_count,
        dof_count=artifact.dof_count,
        csr_nnz=artifact.csr_nnz,
    )
    if (
        artifact.contributions_per_element != _CONTRIBUTIONS_PER_ELEMENT
        or artifact.contribution_count != expected_contribution_count
    ):
        _fail(
            "hip_assembly_plan_contribution_count_mismatch",
            "/dimensions/contribution_count",
        )
    if (
        artifact.node_count != source_plan.node_count
        or artifact.element_count != source_plan.element_count
        or artifact.dof_count != source_plan.dof_count
        or artifact.csr_nnz != source_plan.nnz
    ):
        _fail("hip_assembly_plan_dimension_mismatch", "/dimensions")

    descriptor_names = tuple(row.name for row in artifact.descriptors)
    if descriptor_names != _ARRAY_NAMES or len(set(descriptor_names)) != len(
        _ARRAY_NAMES
    ):
        _fail(
            "hip_assembly_plan_descriptor_set_invalid",
            "/symbolic_payload/arrays",
        )
    expected_shapes = {
        "reference_axis_code": (artifact.element_count,),
        "reverse_segment_offsets": (artifact.csr_nnz + 1,),
        "reverse_contribution_indices": (artifact.contribution_count,),
    }
    for descriptor in artifact.descriptors:
        array = artifact.array(descriptor.name)
        if type(array) is not np.ndarray:
            _fail(
                "hip_assembly_plan_array_type_invalid",
                f"/symbolic_payload/arrays/{descriptor.name}",
            )
        if (
            array.dtype.str != _ARRAY_DTYPES[descriptor.name]
            or array.shape != expected_shapes[descriptor.name]
        ):
            _fail(
                "hip_assembly_plan_array_layout_invalid",
                f"/symbolic_payload/arrays/{descriptor.name}",
            )
        if not array.flags.c_contiguous or not has_immutable_bytes_backing(array):
            _fail(
                "hip_assembly_plan_array_storage_invalid",
                f"/symbolic_payload/arrays/{descriptor.name}",
            )
        if _array_descriptor(descriptor.name, array) != descriptor:
            _fail(
                "hip_assembly_plan_array_descriptor_mismatch",
                f"/symbolic_payload/arrays/{descriptor.name}",
            )

    _validate_array_aliasing(artifact)
    _validate_reference_axis_codes_independent(artifact, source_buffers)
    _validate_reverse_map_independent(artifact, source_plan)

    descriptor_map = {row.name: row for row in artifact.descriptors}
    if artifact.axis_policy_hash != _axis_policy_hash(artifact, descriptor_map):
        _fail(
            "hip_assembly_plan_axis_policy_hash_mismatch",
            "/axis_policy/axis_policy_hash",
        )
    if artifact.reverse_map_hash != _reverse_map_hash(artifact, descriptor_map):
        _fail(
            "hip_assembly_plan_reverse_map_hash_mismatch",
            "/reverse_assembly_plan/reverse_map_hash",
        )
    if artifact.symbolic_payload_hash != _symbolic_payload_hash(
        artifact, descriptor_map
    ):
        _fail(
            "hip_assembly_plan_symbolic_payload_hash_mismatch",
            "/symbolic_payload/symbolic_payload_hash",
        )
    if artifact.assembly_plan_id != _assembly_plan_id(artifact):
        _fail("hip_assembly_plan_id_mismatch", "/assembly_plan_id")
    if artifact.assembly_plan_hash != _assembly_plan_hash(artifact):
        _fail("hip_assembly_plan_hash_mismatch", "/assembly_plan_hash")


def _validate_sources(
    buffers: SolverModelBuffers, execution_plan: ExecutionPlanV2
) -> None:
    if type(buffers) is not SolverModelBuffers:
        _raise(
            "hip_assembly_plan_source_buffer_invalid",
            "/input_binding",
            "Source must be an exact SolverModelBuffers instance.",
        )
    if type(execution_plan) is not ExecutionPlanV2:
        _raise(
            "hip_assembly_plan_source_execution_plan_invalid",
            "/source_contract",
            "Source must be an exact ExecutionPlanV2 instance.",
        )
    try:
        validate_execution_plan_v2(execution_plan, expected_buffers=buffers)
    except ExecutionPlanV2Error as exc:
        raise HipAssemblyPlanV1Error(
            "hip_assembly_plan_source_execution_plan_invalid",
            exc.path,
            f"{exc.code}: {exc.message}",
        ) from exc


def _validate_source_bindings(
    artifact: HipAssemblyPlanV1,
    buffers: SolverModelBuffers,
    execution_plan: ExecutionPlanV2,
) -> None:
    scatter_descriptor = _source_plan_descriptor(
        execution_plan, "csr_element_scatter_indices"
    )
    bindings = (
        (
            artifact.model_ir_content_hash,
            buffers.model_ir_content_hash,
            "model_ir_content_hash",
        ),
        (
            artifact.solver_buffer_schema_version,
            buffers.schema_version,
            "solver_buffer_schema_version",
        ),
        (
            artifact.solver_numeric_buffer_hash,
            buffers.numeric_buffer_hash,
            "solver_numeric_buffer_hash",
        ),
        (
            artifact.solver_entity_mapping_hash,
            buffers.entity_mapping_hash,
            "solver_entity_mapping_hash",
        ),
        (artifact.solver_artifact_hash, buffers.artifact_hash, "solver_artifact_hash"),
        (artifact.load_pattern_id, buffers.load_pattern_id, "load_pattern_id"),
    )
    for actual, expected, field in bindings:
        if actual != expected:
            _fail(
                "hip_assembly_plan_source_buffer_mismatch",
                f"/input_binding/{field}",
            )
    plan_bindings = (
        (
            artifact.source_execution_plan_schema_version,
            execution_plan.schema_version,
            "execution_plan_schema_version",
        ),
        (
            artifact.source_execution_plan_capability_profile,
            execution_plan.capability_profile,
            "execution_plan_capability_profile",
        ),
        (
            artifact.source_execution_plan_id,
            execution_plan.plan_id,
            "execution_plan_id",
        ),
        (
            artifact.source_execution_plan_hash,
            execution_plan.plan_hash,
            "execution_plan_hash",
        ),
        (
            artifact.source_operator_version,
            execution_plan.operator_version,
            "operator_version",
        ),
        (
            artifact.source_element_operator_version,
            execution_plan.source_element_operator_version,
            "element_operator_version",
        ),
        (
            artifact.source_symbolic_reuse_hash,
            execution_plan.symbolic_reuse_hash,
            "symbolic_reuse_hash",
        ),
        (
            artifact.source_partition_hash,
            execution_plan.partition_hash,
            "partition_hash",
        ),
        (artifact.source_ordering_hash, execution_plan.ordering_hash, "ordering_hash"),
        (
            artifact.source_scatter_content_hash,
            scatter_descriptor.content_hash,
            "scatter_content_hash",
        ),
        (
            artifact.source_geometry_hash,
            _source_geometry_hash(buffers),
            "geometry_hash",
        ),
        (
            artifact.source_support_partition_hash,
            _source_support_partition_hash(buffers, execution_plan),
            "support_partition_hash",
        ),
    )
    for actual, expected, field in plan_bindings:
        if actual != expected:
            _fail(
                "hip_assembly_plan_source_execution_plan_mismatch",
                f"/source_contract/{field}",
            )


def _guard_dimensions(
    *, node_count: int, element_count: int, dof_count: int, csr_nnz: int
) -> int:
    values = {
        "node_count": node_count,
        "element_count": element_count,
        "dof_count": dof_count,
        "csr_nnz": csr_nnz,
    }
    for name, value in values.items():
        if type(value) is not int or value <= 0:
            _raise(
                "hip_assembly_plan_dimension_invalid",
                f"/dimensions/{name}",
                f"{name} must be an exact positive integer.",
            )
        if value > _INT32_MAX:
            _raise(
                "hip_assembly_plan_int32_capacity_exceeded",
                f"/dimensions/{name}",
                f"{name} exceeds the signed-int32 ABI capacity.",
            )
    if csr_nnz + 1 > _INT32_MAX:
        _raise(
            "hip_assembly_plan_int32_capacity_exceeded",
            "/dimensions/reverse_segment_offsets",
            "Z+1 exceeds the signed-int32 addressable segment count.",
        )
    contribution_count = element_count * _CONTRIBUTIONS_PER_ELEMENT
    if contribution_count > _INT32_MAX:
        _raise(
            "hip_assembly_plan_int32_capacity_exceeded",
            "/dimensions/contribution_count",
            "C=144E exceeds the signed-int32 ABI capacity.",
        )
    symbolic_payload_byte_length = (
        element_count
        + (csr_nnz + 1) * np.dtype("<i4").itemsize
        + contribution_count * np.dtype("<i4").itemsize
    )
    if symbolic_payload_byte_length > _INT32_MAX:
        _raise(
            "hip_assembly_plan_int32_capacity_exceeded",
            "/dimensions/symbolic_payload_byte_length",
            "The three described symbolic arrays exceed the schema's signed-int32 byte-length capacity.",
        )
    return contribution_count


def _compile_reference_axis_codes(buffers: SolverModelBuffers) -> np.ndarray:
    coordinates = buffers.array("node_coordinates_m")
    connectivity = buffers.array("element_connectivity")
    result = np.empty(connectivity.shape[0], dtype="u1")
    for element_index in range(connectivity.shape[0]):
        node_i = int(connectivity[element_index, 0])
        node_j = int(connectivity[element_index, 1])
        delta = coordinates[node_j] - coordinates[node_i]
        length = float(np.linalg.norm(delta))
        # ExecutionPlanV2 validation already proves the CPU length invariant.
        if not math.isfinite(length) or length <= 1.0e-12:  # pragma: no cover
            _raise(
                "hip_assembly_plan_axis_source_invalid",
                f"/elements/{element_index}",
                "Cannot derive a reference axis from a zero-length element.",
            )
        local_x_z = float(delta[2]) / length
        result[element_index] = (
            REFERENCE_AXIS_GLOBAL_Y
            if abs(local_x_z) > REFERENCE_AXIS_SWITCH_THRESHOLD
            else REFERENCE_AXIS_GLOBAL_Z
        )
    return result


def _compile_reverse_map(
    element_scatter_indices: np.ndarray, *, csr_nnz: int
) -> tuple[np.ndarray, np.ndarray]:
    """Invert fixed 12x12 scatter in O(C+Z), preserving source order."""

    if type(element_scatter_indices) is not np.ndarray:
        _raise(
            "hip_assembly_plan_scatter_invalid",
            "/source_contract/scatter_content_hash",
            "Element scatter must be an exact NumPy array.",
        )
    if (
        element_scatter_indices.dtype.str != "<i4"
        or element_scatter_indices.ndim != 3
        or element_scatter_indices.shape[1:]
        != (
            _DOFS_PER_ELEMENT,
            _DOFS_PER_ELEMENT,
        )
    ):
        _raise(
            "hip_assembly_plan_scatter_invalid",
            "/source_contract/scatter_content_hash",
            "Element scatter must have dtype <i4 and shape (E,12,12).",
        )
    if type(csr_nnz) is not int or csr_nnz <= 0 or csr_nnz >= _INT32_MAX:
        _raise(
            "hip_assembly_plan_int32_capacity_exceeded",
            "/dimensions/csr_nnz",
            "Z must be positive and Z+1 must fit the signed-int32 ABI.",
        )
    contribution_count = int(element_scatter_indices.size)
    if contribution_count > _INT32_MAX:
        _raise(
            "hip_assembly_plan_int32_capacity_exceeded",
            "/dimensions/contribution_count",
            "Scatter contribution count exceeds signed-int32 capacity.",
        )

    flat = element_scatter_indices.reshape(-1)
    counts = np.zeros(csr_nnz, dtype=np.int64)
    for source_index in range(contribution_count):
        target = int(flat[source_index])
        if target < 0 or target >= csr_nnz:
            _raise(
                "hip_assembly_plan_scatter_range_invalid",
                "/source_contract/scatter_content_hash",
                f"Scatter target {target} is outside [0, Z).",
            )
        counts[target] += 1

    offsets64 = np.empty(csr_nnz + 1, dtype=np.int64)
    offsets64[0] = 0
    np.cumsum(counts, out=offsets64[1:])
    if int(offsets64[-1]) != contribution_count:  # pragma: no cover
        _raise(
            "hip_assembly_plan_reverse_map_invalid",
            "/reverse_assembly_plan",
            "Reverse-map prefix sum lost contributions.",
        )
    cursor = offsets64[:-1].copy()
    reverse = np.empty(contribution_count, dtype="<i4")
    for source_index in range(contribution_count):
        target = int(flat[source_index])
        destination = int(cursor[target])
        reverse[destination] = source_index
        cursor[target] += 1
    return (
        immutable_array(offsets64, dtype="<i4"),
        immutable_array(reverse, dtype="<i4"),
    )


def _validate_reference_axis_codes_independent(
    artifact: HipAssemblyPlanV1, buffers: SolverModelBuffers
) -> None:
    actual = artifact.array("reference_axis_code")
    if np.any(
        (actual != REFERENCE_AXIS_GLOBAL_Y) & (actual != REFERENCE_AXIS_GLOBAL_Z)
    ):
        _fail(
            "hip_assembly_plan_axis_code_invalid",
            "/axis_policy/reference_axis_code",
        )

    coordinates = buffers.array("node_coordinates_m")
    connectivity = buffers.array("element_connectivity")
    rolls = buffers.array("element_local_axis_rotation_rad")
    independently_derived = np.empty(artifact.element_count, dtype="u1")
    try:
        for element_index in range(artifact.element_count):
            node_i = int(connectivity[element_index, 0])
            node_j = int(connectivity[element_index, 1])
            transform, _ = _frame_transform(
                coordinates[node_i],
                coordinates[node_j],
                float(rolls[element_index]),
            )
            independently_derived[element_index] = (
                REFERENCE_AXIS_GLOBAL_Y
                if abs(float(transform[0, 2])) > REFERENCE_AXIS_SWITCH_THRESHOLD
                else REFERENCE_AXIS_GLOBAL_Z
            )
    except CPUReferenceError as exc:  # pragma: no cover - source preflight invariant
        raise HipAssemblyPlanV1Error(
            "hip_assembly_plan_axis_source_invalid",
            "/source_contract/geometry_hash",
            str(exc),
        ) from exc
    if not np.array_equal(actual, independently_derived):
        _fail(
            "hip_assembly_plan_axis_rederivation_mismatch",
            "/axis_policy/reference_axis_code",
        )


def _validate_reverse_map_independent(
    artifact: HipAssemblyPlanV1, execution_plan: ExecutionPlanV2
) -> None:
    scatter = execution_plan.array("csr_element_scatter_indices").reshape(-1)
    offsets = artifact.array("reverse_segment_offsets")
    reverse = artifact.array("reverse_contribution_indices")
    contribution_count = artifact.contribution_count

    if np.any(scatter < 0) or np.any(scatter >= artifact.csr_nnz):
        _fail(
            "hip_assembly_plan_scatter_range_invalid",
            "/source_contract/scatter_content_hash",
        )
    if (
        int(offsets[0]) != 0
        or int(offsets[-1]) != contribution_count
        or np.any(offsets < 0)
        or np.any(np.diff(offsets.astype(np.int64, copy=False)) < 0)
    ):
        _fail(
            "hip_assembly_plan_reverse_offsets_invalid",
            "/reverse_assembly_plan/reverse_segment_offsets",
        )

    expected_counts = np.zeros(artifact.csr_nnz, dtype=np.int64)
    for source_index in range(contribution_count):
        expected_counts[int(scatter[source_index])] += 1
    if not np.array_equal(
        np.diff(offsets.astype(np.int64, copy=False)), expected_counts
    ):
        _fail(
            "hip_assembly_plan_reverse_segment_count_mismatch",
            "/reverse_assembly_plan/reverse_segment_offsets",
        )

    seen = np.zeros(contribution_count, dtype=np.bool_)
    for target in range(artifact.csr_nnz):
        start = int(offsets[target])
        stop = int(offsets[target + 1])
        previous = -1
        for position in range(start, stop):
            source_index = int(reverse[position])
            if source_index < 0 or source_index >= contribution_count:
                _fail(
                    "hip_assembly_plan_reverse_index_range_invalid",
                    "/reverse_assembly_plan/reverse_contribution_indices",
                )
            if seen[source_index]:
                _fail(
                    "hip_assembly_plan_reverse_index_duplicate",
                    "/reverse_assembly_plan/reverse_contribution_indices",
                )
            if source_index <= previous:
                _fail(
                    "hip_assembly_plan_reverse_order_invalid",
                    "/reverse_assembly_plan/reverse_contribution_indices",
                )
            if int(scatter[source_index]) != target:
                _fail(
                    "hip_assembly_plan_reverse_membership_invalid",
                    "/reverse_assembly_plan/reverse_contribution_indices",
                )
            seen[source_index] = True
            previous = source_index
    if not bool(np.all(seen)):
        _fail(
            "hip_assembly_plan_reverse_index_missing",
            "/reverse_assembly_plan/reverse_contribution_indices",
        )


def _validate_array_aliasing(artifact: HipAssemblyPlanV1) -> None:
    arrays = list(artifact._arrays)
    for left in range(len(arrays)):
        for right in range(left + 1, len(arrays)):
            if np.shares_memory(arrays[left], arrays[right]):
                _fail(
                    "hip_assembly_plan_array_alias_invalid",
                    "/symbolic_payload/arrays",
                )
    source_arrays = list(artifact._source_execution_plan._arrays) + [
        artifact._source_buffers.array(row.name)
        for row in artifact._source_buffers.descriptors
    ]
    for array in arrays:
        if any(np.shares_memory(array, source) for source in source_arrays):
            _fail(
                "hip_assembly_plan_array_alias_invalid",
                "/symbolic_payload/arrays",
            )


def _array_descriptor(name: str, array: np.ndarray) -> AssemblyArrayDescriptorV1:
    metadata = {
        "name": name,
        "dtype": array.dtype.str,
        "shape": [int(value) for value in array.shape],
        "layout": "C",
        "byte_length": int(array.nbytes),
    }
    return AssemblyArrayDescriptorV1(
        name=name,
        dtype=array.dtype.str,
        shape=tuple(int(value) for value in array.shape),
        layout="C",
        byte_length=int(array.nbytes),
        data_hash=array_data_hash(array),
        content_hash=array_content_hash(metadata, array),
    )


def _detached_immutable_array(value: Any, *, dtype: Any) -> np.ndarray:
    """Return bytes-backed storage that cannot alias equal one-byte sources.

    CPython interns every one-byte ``bytes`` value.  A one-element uint8 axis
    vector could therefore accidentally share storage with an equal one-byte
    source code array even after an ordinary byte copy.  One private padding
    byte keeps the backing allocation distinct while the exposed array view,
    descriptor byte length, and hashed data remain exact.
    """

    target_dtype = np.dtype(dtype)
    if target_dtype.itemsize > 1:
        target_dtype = target_dtype.newbyteorder("<")
    contiguous = np.ascontiguousarray(value, dtype=target_dtype)
    payload = contiguous.tobytes(order="C")
    backing = bytes(bytearray(payload + b"\xa5"))
    return np.frombuffer(backing, dtype=target_dtype, count=contiguous.size).reshape(
        contiguous.shape
    )


def _source_buffer_descriptor(buffers: SolverModelBuffers, name: str) -> Any:
    for descriptor in buffers.descriptors:
        if descriptor.name == name:
            return descriptor
    _raise(
        "hip_assembly_plan_source_buffer_invalid",
        f"/input_binding/{name}",
        f"Source SolverModelBuffers lacks descriptor {name}.",
    )


def _source_plan_descriptor(execution_plan: ExecutionPlanV2, name: str) -> Any:
    for descriptor in execution_plan.descriptors:
        if descriptor.name == name:
            return descriptor
    _raise(
        "hip_assembly_plan_source_execution_plan_invalid",
        f"/source_contract/{name}",
        f"Source ExecutionPlanV2 lacks descriptor {name}.",
    )


def _source_geometry_hash(buffers: SolverModelBuffers) -> str:
    return canonical_hash(
        {
            "axis_policy": HIP_ASSEMBLY_PLAN_V1_AXIS_POLICY,
            "element_ids": list(buffers.entity_ids["elements"]),
            "arrays": [
                _source_buffer_descriptor(buffers, name).to_dict()
                for name in (
                    "node_coordinates_m",
                    "element_connectivity",
                    "element_local_axis_rotation_rad",
                )
            ],
        }
    )


def _source_support_partition_hash(
    buffers: SolverModelBuffers, execution_plan: ExecutionPlanV2
) -> str:
    return canonical_hash(
        {
            "support_mask": _source_buffer_descriptor(
                buffers, "support_mask"
            ).to_dict(),
            "partition_hash": execution_plan.partition_hash,
            "partition_arrays": [
                _source_plan_descriptor(execution_plan, name).to_dict()
                for name in ("constrained_dofs", "free_dofs", "global_to_free")
            ],
        }
    )


def _axis_policy_hash(
    artifact: HipAssemblyPlanV1,
    descriptors: Mapping[str, AssemblyArrayDescriptorV1],
) -> str:
    return canonical_hash(
        {
            "policy": HIP_ASSEMBLY_PLAN_V1_AXIS_POLICY,
            "default_reference_axis": "global_z",
            "switch_reference_axis": "global_y",
            "switch_comparison": "abs_local_x_z_strictly_greater_than",
            "switch_threshold": REFERENCE_AXIS_SWITCH_THRESHOLD,
            "codes": {
                "global_y": REFERENCE_AXIS_GLOBAL_Y,
                "global_z": REFERENCE_AXIS_GLOBAL_Z,
            },
            "source_geometry_hash": artifact.source_geometry_hash,
            "element_count": artifact.element_count,
            "array": descriptors["reference_axis_code"].to_dict(),
        }
    )


def _reverse_map_hash(
    artifact: HipAssemblyPlanV1,
    descriptors: Mapping[str, AssemblyArrayDescriptorV1],
) -> str:
    return canonical_hash(
        {
            "source_format": "csr",
            "source_assembly_order": HIP_ASSEMBLY_PLAN_V1_ASSEMBLY_ORDER,
            "reverse_segment_order": HIP_ASSEMBLY_PLAN_V1_REVERSE_ORDER,
            "source_scatter_content_hash": artifact.source_scatter_content_hash,
            "csr_nnz": artifact.csr_nnz,
            "contribution_count": artifact.contribution_count,
            "structural_zero_segments_retained": True,
            "arrays": [
                descriptors[name].to_dict()
                for name in (
                    "reverse_segment_offsets",
                    "reverse_contribution_indices",
                )
            ],
        }
    )


def _symbolic_payload_hash(
    artifact: HipAssemblyPlanV1,
    descriptors: Mapping[str, AssemblyArrayDescriptorV1],
) -> str:
    return canonical_hash(
        {
            "schema_version": HIP_ASSEMBLY_PLAN_V1_SCHEMA_VERSION,
            "capability_profile": HIP_ASSEMBLY_PLAN_V1_CAPABILITY_PROFILE,
            "solver_artifact_hash": artifact.solver_artifact_hash,
            "execution_plan_hash": artifact.source_execution_plan_hash,
            "support_partition_hash": artifact.source_support_partition_hash,
            "axis_policy_hash": artifact.axis_policy_hash,
            "reverse_map_hash": artifact.reverse_map_hash,
            "dimensions": {
                "node_count": artifact.node_count,
                "element_count": artifact.element_count,
                "dof_count": artifact.dof_count,
                "csr_nnz": artifact.csr_nnz,
                "contribution_count": artifact.contribution_count,
            },
            "csr_numeric_values_present": False,
            "arrays": [descriptors[name].to_dict() for name in _ARRAY_NAMES],
        }
    )


def _assembly_plan_id(artifact: HipAssemblyPlanV1) -> str:
    seed = canonical_hash(
        {
            "solver_artifact_hash": artifact.solver_artifact_hash,
            "execution_plan_hash": artifact.source_execution_plan_hash,
            "symbolic_payload_hash": artifact.symbolic_payload_hash,
        }
    )
    return f"HipAssemblyPlan:{seed.removeprefix('sha256:')[:24]}"


def _assembly_plan_hash(artifact: HipAssemblyPlanV1) -> str:
    payload = artifact.to_dict()
    payload.pop("assembly_plan_hash")
    return canonical_hash(payload)


@lru_cache(maxsize=1)
def _schema_validator() -> Draft202012Validator:
    schema_path = (
        Path(__file__).resolve().parents[2]
        / "schemas"
        / "hip_assembly_plan_v1.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _fail(code: str, path: str) -> None:
    messages = {
        "hip_assembly_plan_container_invalid": "Assembly-plan containers and sources must use exact contract types.",
        "hip_assembly_plan_schema_mismatch": "Assembly-plan schema version is invalid.",
        "hip_assembly_plan_profile_mismatch": "Assembly-plan capability profile is invalid.",
        "hip_assembly_plan_buffer_schema_mismatch": "Solver-buffer schema binding is invalid.",
        "hip_assembly_plan_source_schema_mismatch": "Source ExecutionPlan schema binding is invalid.",
        "hip_assembly_plan_source_profile_mismatch": "Source ExecutionPlan capability binding is invalid.",
        "hip_assembly_plan_expected_buffer_invalid": "Expected buffers use an invalid type.",
        "hip_assembly_plan_expected_execution_plan_invalid": "Expected execution plan uses an invalid type.",
        "hip_assembly_plan_source_buffer_mismatch": "Assembly plan is bound to different SolverModelBuffers.",
        "hip_assembly_plan_source_execution_plan_mismatch": "Assembly plan is bound to a different ExecutionPlanV2.",
        "hip_assembly_plan_contribution_count_mismatch": "Contribution dimensions do not satisfy C=144E.",
        "hip_assembly_plan_dimension_mismatch": "Assembly dimensions differ from the bound ExecutionPlanV2.",
        "hip_assembly_plan_descriptor_set_invalid": "Symbolic descriptor names/order are invalid.",
        "hip_assembly_plan_array_type_invalid": "Symbolic arrays must be exact NumPy ndarrays.",
        "hip_assembly_plan_array_layout_invalid": "Symbolic array dtype or shape is invalid.",
        "hip_assembly_plan_array_storage_invalid": "Symbolic array is not immutable C-order bytes-backed storage.",
        "hip_assembly_plan_array_descriptor_mismatch": "Symbolic descriptor/hash is stale.",
        "hip_assembly_plan_array_alias_invalid": "Symbolic arrays must not alias one another or source arrays.",
        "hip_assembly_plan_axis_code_invalid": "Reference-axis code must be 1=global_Y or 2=global_Z.",
        "hip_assembly_plan_axis_rederivation_mismatch": "Reference-axis codes differ from independent CPU convention rederivation.",
        "hip_assembly_plan_scatter_range_invalid": "Source scatter contains a signed or out-of-range CSR index.",
        "hip_assembly_plan_reverse_offsets_invalid": "Reverse offsets must be nonnegative, monotonic, and span exactly C.",
        "hip_assembly_plan_reverse_segment_count_mismatch": "Reverse segment sizes differ from source scatter counts.",
        "hip_assembly_plan_reverse_index_range_invalid": "Reverse contribution index is signed or outside [0,C).",
        "hip_assembly_plan_reverse_index_duplicate": "Reverse contribution indices contain a duplicate.",
        "hip_assembly_plan_reverse_order_invalid": "Reverse segment does not preserve stable source contribution order.",
        "hip_assembly_plan_reverse_membership_invalid": "Reverse contribution targets the wrong CSR segment.",
        "hip_assembly_plan_reverse_index_missing": "Reverse contribution permutation is incomplete.",
        "hip_assembly_plan_axis_policy_hash_mismatch": "Axis-policy hash is stale.",
        "hip_assembly_plan_reverse_map_hash_mismatch": "Reverse-map hash is stale.",
        "hip_assembly_plan_symbolic_payload_hash_mismatch": "Symbolic-payload hash is stale.",
        "hip_assembly_plan_id_mismatch": "Assembly-plan ID is stale.",
        "hip_assembly_plan_hash_mismatch": "Assembly-plan aggregate hash is stale.",
    }
    _raise(code, path, messages.get(code, code))


def _raise(code: str, path: str, message: str) -> None:
    raise HipAssemblyPlanV1Error(code, path, message)


__all__ = [
    "HIP_ASSEMBLY_PLAN_V1_ASSEMBLY_ORDER",
    "HIP_ASSEMBLY_PLAN_V1_AXIS_POLICY",
    "HIP_ASSEMBLY_PLAN_V1_CAPABILITY_PROFILE",
    "HIP_ASSEMBLY_PLAN_V1_REVERSE_ORDER",
    "HIP_ASSEMBLY_PLAN_V1_SCHEMA_VERSION",
    "REFERENCE_AXIS_GLOBAL_Y",
    "REFERENCE_AXIS_GLOBAL_Z",
    "REFERENCE_AXIS_SWITCH_THRESHOLD",
    "AssemblyArrayDescriptorV1",
    "HipAssemblyPlanV1",
    "HipAssemblyPlanV1Error",
    "compile_hip_assembly_plan_v1",
    "validate_hip_assembly_plan_v1",
]
