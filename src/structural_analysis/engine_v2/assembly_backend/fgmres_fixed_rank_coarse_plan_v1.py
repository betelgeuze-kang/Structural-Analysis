"""Plan-only HIP ABI for the fixed-rank FGMRES coarse preconditioner.

This additive contract binds the CPU reference coarse-space artifact to the
exact buffers of one :class:`HipFgmresPlanV1`.  It describes a four-launch,
same-stream replacement for the recurrence's Jacobi-only
``basis_v -> preconditioned_basis_z`` step:

``prepare -> Z.T r -> (L L.T) solve -> coarse correction + Jacobi smoothing``.

The physical basis ``Z``, retained ``A Z`` columns, and the small Cholesky
factor are uploaded once before recurrence.  Every application then performs
no host transfer, CSR application, allocation, or synchronization.  This file
does not allocate, compile, launch, or claim HIP numerical parity; it is the
strict plan/source ABI for that later runtime slice.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field as dataclass_field, replace
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Literal

from jsonschema import Draft202012Validator

from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.engine_v2.solvers.cpu_fgmres_fixed_rank_coarse_v1 import (
    CPU_FGMRES_FIXED_RANK_COARSE_ALGORITHM_VERSION_V1,
    CPU_FGMRES_FIXED_RANK_COARSE_SPACE_V1_SCHEMA_VERSION,
    MAX_CPU_FGMRES_COARSE_RANK_V1,
    CpuFgmresFixedRankCoarseError,
    CpuFgmresFixedRankCoarseSpaceV1,
    validate_cpu_fgmres_fixed_rank_coarse_space_v1,
)

from .fgmres_plan import (
    HipFgmresBufferPlanV1,
    HipFgmresPlanV1,
    HipFgmresPlanV1Error,
    validate_hip_fgmres_plan_v1,
)


HIP_FGMRES_FIXED_RANK_COARSE_PLAN_V1_SCHEMA_VERSION = (
    "structural-analysis-hip-fgmres-fixed-rank-coarse-plan.v1"
)
HIP_FGMRES_FIXED_RANK_COARSE_PLAN_V1_CAPABILITY_PROFILE = (
    "phase0_hip_fgmres_fixed_rank_coarse_application_plan"
)
HIP_FGMRES_FIXED_RANK_COARSE_APPLICATION_ABI_VERSION_V1 = 1
HIP_FGMRES_FIXED_RANK_COARSE_BLOCK_SIZE_V1 = 256

HIP_FGMRES_FIXED_RANK_COARSE_PREPARE_SYMBOL_V1 = (
    "engine_v2_fgmres_fixed_rank_coarse_prepare_v1"
)
HIP_FGMRES_FIXED_RANK_COARSE_DOT_SYMBOL_V1 = "engine_v2_fgmres_fixed_rank_coarse_dot_v1"
HIP_FGMRES_FIXED_RANK_COARSE_SOLVE_SYMBOL_V1 = (
    "engine_v2_fgmres_fixed_rank_coarse_solve_v1"
)
HIP_FGMRES_FIXED_RANK_COARSE_APPLY_SYMBOL_V1 = (
    "engine_v2_fgmres_fixed_rank_coarse_apply_v1"
)
HIP_FGMRES_FIXED_RANK_COARSE_KERNEL_SYMBOLS_V1 = (
    HIP_FGMRES_FIXED_RANK_COARSE_PREPARE_SYMBOL_V1,
    HIP_FGMRES_FIXED_RANK_COARSE_DOT_SYMBOL_V1,
    HIP_FGMRES_FIXED_RANK_COARSE_SOLVE_SYMBOL_V1,
    HIP_FGMRES_FIXED_RANK_COARSE_APPLY_SYMBOL_V1,
)

_SOURCE_RESOURCE = "kernels/engine_v2_fgmres_fixed_rank_coarse_v1.hip.cpp"
_SOURCE_PATH = Path(__file__).with_name("kernels") / Path(_SOURCE_RESOURCE).name
_SCHEMA_RESOURCE = "hip_fgmres_fixed_rank_coarse_plan_v1.schema.json"
_SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schemas" / _SCHEMA_RESOURCE
_COMPILE_OPTIONS = ("-O3", "-std=c++17", "-ffp-contract=off")
_ZERO_HASH = "sha256:" + "0" * 64
_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_INT32_MAX = (1 << 31) - 1
_UINT64_MAX = (1 << 64) - 1
_BORROWED_NAMES = (
    "jacobi_inverse",
    "basis_v",
    "preconditioned_basis_z",
)
_OWNED_NAMES = (
    "coarse_physical_basis_z",
    "coarse_operator_basis_az",
    "coarse_cholesky_l",
    "coarse_rhs",
    "coarse_coefficients",
    "coarse_status",
)
_BUFFER_NAMES = _BORROWED_NAMES + _OWNED_NAMES
_STATUS_BITS = {
    "invalid_geometry": 0,
    "nonfinite_input": 1,
    "nonpositive_factor": 2,
    "nonfinite_arithmetic": 3,
}


class HipFgmresFixedRankCoarsePlanV1Error(ValueError):
    """Stable fail-closed error with a JSON-pointer path."""

    def __init__(self, code: str, path: str, message: str = "") -> None:
        self.code = code
        self.path = path
        self.message = message or code
        super().__init__(f"{code}@{path}: {self.message}")


@dataclass(frozen=True, slots=True)
class HipFgmresFixedRankCoarseBufferPlanV1:
    """One exact parent borrow or coarse-context allocation extent."""

    name: str
    ownership: Literal["borrowed", "owned"]
    dtype: Literal["<f8", "<u4"]
    shape: tuple[int, ...]
    element_count: int
    byte_length: int
    access: str
    source: str
    initialization: str
    layout: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["shape"] = list(self.shape)
        payload["memory_space"] = "hip_device"
        return payload


@dataclass(frozen=True, slots=True)
class HipFgmresFixedRankCoarseLaunchPlanV1:
    """One ordered launch in an application of the coarse preconditioner."""

    ordinal: int
    symbol: str
    grid_x: int
    block_x: int
    grid_formula: str
    reads: tuple[str, ...]
    writes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ordinal": self.ordinal,
            "symbol": self.symbol,
            "grid": [self.grid_x, 1, 1],
            "block": [self.block_x, 1, 1],
            "grid_formula": self.grid_formula,
            "reads": list(self.reads),
            "writes": list(self.writes),
        }


@dataclass(frozen=True, slots=True)
class HipFgmresFixedRankCoarsePlanV1:
    """Immutable source-bound plan for a future live HIP coarse context."""

    schema_version: str
    capability_profile: str
    application_abi_version: int
    source_fgmres_plan_id: str
    source_fgmres_plan_hash: str
    source_fgmres_memory_layout_hash: str
    source_execution_plan_hash: str
    source_operator_hash: str
    source_numeric_snapshot_hash: str
    source_partition_hash: str
    source_coarse_space_schema_version: str
    source_coarse_algorithm_version: str
    source_coarse_space_hash: str
    physical_basis_data_hash: str
    operator_basis_data_hash: str
    cholesky_data_hash: str
    free_dof_count: int
    reduced_nnz: int
    restart_dimension: int
    max_iterations: int
    retained_rank: int
    rank_cap: int
    buffers: tuple[HipFgmresFixedRankCoarseBufferPlanV1, ...]
    launches: tuple[HipFgmresFixedRankCoarseLaunchPlanV1, ...]
    borrowed_device_byte_span: int
    owned_device_byte_length: int
    static_upload_copy_count: int
    static_upload_byte_count: int
    application_kernel_launch_count: int
    application_h2d_copy_count: int
    application_d2h_copy_count: int
    application_csr_apply_count: int
    application_allocation_count: int
    application_synchronization_count: int
    dense_projector_element_count: int
    kernel_source_resource: str
    kernel_source_hash: str
    compile_options: tuple[str, ...]
    kernel_symbols: tuple[str, ...]
    kernel_abi_hash: str
    memory_layout_hash: str
    plan_hash: str
    _source_fgmres_plan: HipFgmresPlanV1 = dataclass_field(
        repr=False,
        compare=False,
    )
    _source_coarse_space: CpuFgmresFixedRankCoarseSpaceV1 = dataclass_field(
        repr=False,
        compare=False,
    )

    def buffer(self, name: str) -> HipFgmresFixedRankCoarseBufferPlanV1:
        for row in self.buffers:
            if row.name == name:
                return row
        raise KeyError(name)

    def to_dict(self) -> dict[str, Any]:
        validate_hip_fgmres_fixed_rank_coarse_plan_v1(self)
        return _plan_payload(self, include_hash=True)

    def to_manifest(self) -> dict[str, Any]:
        return self.to_dict()


def hip_fgmres_fixed_rank_coarse_kernel_abi_payload_v1() -> dict[str, Any]:
    """Return the dimension-independent four-kernel application ABI."""

    return {
        "application_abi_version": (
            HIP_FGMRES_FIXED_RANK_COARSE_APPLICATION_ABI_VERSION_V1
        ),
        "scalar_type": "fp64",
        "index_type": "i32",
        "status_type": "u32",
        "rank_cap": MAX_CPU_FGMRES_COARSE_RANK_V1,
        "block_size": HIP_FGMRES_FIXED_RANK_COARSE_BLOCK_SIZE_V1,
        "source_resource": _SOURCE_RESOURCE,
        "compile_options": list(_COMPILE_OPTIONS),
        "kernel_symbols": list(HIP_FGMRES_FIXED_RANK_COARSE_KERNEL_SYMBOLS_V1),
        "matrix_layouts": {
            "physical_basis_z": "row_major_free_dof_by_rank",
            "operator_basis_az": "row_major_free_dof_by_rank",
            "coarse_cholesky_l": "row_major_rank_by_rank_lower_triangle",
            "basis_v": "row_major_column_by_free_dof",
            "preconditioned_basis_z": "row_major_column_by_free_dof",
        },
        "application_equations": {
            "coarse_rhs": "g=Z^T*r",
            "small_solve": "L*L^T*c=g",
            "coarse_correction": "z_c=Z*c",
            "smoothing": "z=z_c+diag(A)^-1*(r-AZ*c)",
        },
        "launch_order": [
            "prepare_workspace_and_status",
            "deterministic_block_tree_coarse_dot",
            "single_thread_bounded_cholesky_solve",
            "row_parallel_coarse_plus_jacobi_apply",
        ],
        "status_bits": dict(_STATUS_BITS),
        "failure_propagation": (
            "upstream_status_forces_nan_rows_and_numeric_apply_failures_publish_"
            "status_plus_at_least_one_nan_sentinel_without_host_read"
        ),
        "pointer_contract": {
            "fp64_alignment_bytes": 8,
            "status_alignment_bytes": 4,
            "all_buffer_ranges_disjoint": True,
            "uintptr_range_checked": True,
        },
        "integration_seam": {
            "replaces": "recurrence_v2_vector_mode_APPLY_JACOBI_INDEXED",
            "input": "basis_v[logical_index,:]",
            "output": "preconditioned_basis_z[logical_index,:]",
            "same_stream_required": True,
        },
    }


def compile_hip_fgmres_fixed_rank_coarse_plan_v1(
    fgmres_plan: HipFgmresPlanV1,
    coarse_space: CpuFgmresFixedRankCoarseSpaceV1,
) -> HipFgmresFixedRankCoarsePlanV1:
    """Compile an additive plan without allocating, copying, or launching."""

    _validate_sources(fgmres_plan, coarse_space)
    f = int(fgmres_plan.free_dof_count)
    k = int(coarse_space.retained_rank)
    m = int(fgmres_plan.restart_dimension)
    buffers = _compile_buffers(fgmres_plan, f=f, k=k, m=m)
    launches = _compile_launches(f=f, k=k)
    borrowed_bytes = sum(
        row.byte_length for row in buffers if row.ownership == "borrowed"
    )
    owned_bytes = sum(row.byte_length for row in buffers if row.ownership == "owned")
    static_upload_bytes = 8 * (2 * f * k + k * k)
    source_hash = _kernel_source_hash()
    abi_hash = canonical_hash(hip_fgmres_fixed_rank_coarse_kernel_abi_payload_v1())
    physical_hash = _descriptor_hash(coarse_space, "physical_basis_z")
    operator_hash = _descriptor_hash(coarse_space, "operator_basis_az")
    cholesky_hash = _descriptor_hash(coarse_space, "coarse_cholesky_l")
    draft = HipFgmresFixedRankCoarsePlanV1(
        schema_version=HIP_FGMRES_FIXED_RANK_COARSE_PLAN_V1_SCHEMA_VERSION,
        capability_profile=(HIP_FGMRES_FIXED_RANK_COARSE_PLAN_V1_CAPABILITY_PROFILE),
        application_abi_version=(
            HIP_FGMRES_FIXED_RANK_COARSE_APPLICATION_ABI_VERSION_V1
        ),
        source_fgmres_plan_id=fgmres_plan.plan_id,
        source_fgmres_plan_hash=fgmres_plan.plan_hash,
        source_fgmres_memory_layout_hash=fgmres_plan.memory_layout_hash,
        source_execution_plan_hash=fgmres_plan.source_execution_plan_hash,
        source_operator_hash=fgmres_plan.source_operator_hash,
        source_numeric_snapshot_hash=fgmres_plan.source_numeric_snapshot_hash,
        source_partition_hash=fgmres_plan.source_partition_hash,
        source_coarse_space_schema_version=coarse_space.schema_version,
        source_coarse_algorithm_version=coarse_space.algorithm_version,
        source_coarse_space_hash=coarse_space.coarse_space_hash,
        physical_basis_data_hash=physical_hash,
        operator_basis_data_hash=operator_hash,
        cholesky_data_hash=cholesky_hash,
        free_dof_count=f,
        reduced_nnz=int(fgmres_plan.reduced_csr_nnz),
        restart_dimension=m,
        max_iterations=int(fgmres_plan.max_iterations),
        retained_rank=k,
        rank_cap=int(coarse_space.rank_cap),
        buffers=buffers,
        launches=launches,
        borrowed_device_byte_span=borrowed_bytes,
        owned_device_byte_length=owned_bytes,
        static_upload_copy_count=3,
        static_upload_byte_count=static_upload_bytes,
        application_kernel_launch_count=4,
        application_h2d_copy_count=0,
        application_d2h_copy_count=0,
        application_csr_apply_count=0,
        application_allocation_count=0,
        application_synchronization_count=0,
        dense_projector_element_count=0,
        kernel_source_resource=_SOURCE_RESOURCE,
        kernel_source_hash=source_hash,
        compile_options=_COMPILE_OPTIONS,
        kernel_symbols=HIP_FGMRES_FIXED_RANK_COARSE_KERNEL_SYMBOLS_V1,
        kernel_abi_hash=abi_hash,
        memory_layout_hash=_ZERO_HASH,
        plan_hash=_ZERO_HASH,
        _source_fgmres_plan=fgmres_plan,
        _source_coarse_space=coarse_space,
    )
    with_layout = replace(draft, memory_layout_hash=_memory_layout_hash(draft))
    result = replace(
        with_layout,
        plan_hash=canonical_hash(_plan_payload(with_layout, include_hash=False)),
    )
    return validate_hip_fgmres_fixed_rank_coarse_plan_v1(
        result,
        expected_fgmres_plan=fgmres_plan,
        expected_coarse_space=coarse_space,
    )


def validate_hip_fgmres_fixed_rank_coarse_plan_v1(
    plan: HipFgmresFixedRankCoarsePlanV1,
    *,
    expected_fgmres_plan: HipFgmresPlanV1 | None = None,
    expected_coarse_space: CpuFgmresFixedRankCoarseSpaceV1 | None = None,
) -> HipFgmresFixedRankCoarsePlanV1:
    """Replay sources, extents, source bytes, ABI, and canonical hashes."""

    if type(plan) is not HipFgmresFixedRankCoarsePlanV1:
        _fail("hip_fgmres_coarse_plan_type_invalid", "/")
    if (
        type(plan._source_fgmres_plan) is not HipFgmresPlanV1
        or type(plan._source_coarse_space) is not CpuFgmresFixedRankCoarseSpaceV1
    ):
        _fail("hip_fgmres_coarse_plan_source_missing", "/source_contract")
    if (
        expected_fgmres_plan is not None
        and plan._source_fgmres_plan is not expected_fgmres_plan
    ):
        _fail("hip_fgmres_coarse_expected_fgmres_plan_mismatch", "/source_contract")
    if (
        expected_coarse_space is not None
        and plan._source_coarse_space is not expected_coarse_space
    ):
        _fail("hip_fgmres_coarse_expected_space_mismatch", "/source_contract")
    fgmres = plan._source_fgmres_plan
    coarse = plan._source_coarse_space
    _validate_sources(fgmres, coarse)
    f = int(fgmres.free_dof_count)
    k = int(coarse.retained_rank)
    m = int(fgmres.restart_dimension)
    expected_buffers = _compile_buffers(fgmres, f=f, k=k, m=m)
    expected_launches = _compile_launches(f=f, k=k)
    expected_bindings = (
        (plan.schema_version, HIP_FGMRES_FIXED_RANK_COARSE_PLAN_V1_SCHEMA_VERSION),
        (
            plan.capability_profile,
            HIP_FGMRES_FIXED_RANK_COARSE_PLAN_V1_CAPABILITY_PROFILE,
        ),
        (
            plan.application_abi_version,
            HIP_FGMRES_FIXED_RANK_COARSE_APPLICATION_ABI_VERSION_V1,
        ),
        (plan.source_fgmres_plan_id, fgmres.plan_id),
        (plan.source_fgmres_plan_hash, fgmres.plan_hash),
        (plan.source_fgmres_memory_layout_hash, fgmres.memory_layout_hash),
        (plan.source_execution_plan_hash, fgmres.source_execution_plan_hash),
        (plan.source_operator_hash, fgmres.source_operator_hash),
        (plan.source_numeric_snapshot_hash, fgmres.source_numeric_snapshot_hash),
        (plan.source_partition_hash, fgmres.source_partition_hash),
        (plan.source_coarse_space_schema_version, coarse.schema_version),
        (plan.source_coarse_algorithm_version, coarse.algorithm_version),
        (plan.source_coarse_space_hash, coarse.coarse_space_hash),
        (plan.physical_basis_data_hash, _descriptor_hash(coarse, "physical_basis_z")),
        (plan.operator_basis_data_hash, _descriptor_hash(coarse, "operator_basis_az")),
        (plan.cholesky_data_hash, _descriptor_hash(coarse, "coarse_cholesky_l")),
        (plan.free_dof_count, f),
        (plan.reduced_nnz, int(fgmres.reduced_csr_nnz)),
        (plan.restart_dimension, m),
        (plan.max_iterations, int(fgmres.max_iterations)),
        (plan.retained_rank, k),
        (plan.rank_cap, int(coarse.rank_cap)),
        (plan.buffers, expected_buffers),
        (plan.launches, expected_launches),
        (
            plan.borrowed_device_byte_span,
            sum(
                row.byte_length
                for row in expected_buffers
                if row.ownership == "borrowed"
            ),
        ),
        (
            plan.owned_device_byte_length,
            sum(
                row.byte_length for row in expected_buffers if row.ownership == "owned"
            ),
        ),
        (plan.static_upload_copy_count, 3),
        (plan.static_upload_byte_count, 8 * (2 * f * k + k * k)),
        (plan.application_kernel_launch_count, 4),
        (plan.application_h2d_copy_count, 0),
        (plan.application_d2h_copy_count, 0),
        (plan.application_csr_apply_count, 0),
        (plan.application_allocation_count, 0),
        (plan.application_synchronization_count, 0),
        (plan.dense_projector_element_count, 0),
        (plan.kernel_source_resource, _SOURCE_RESOURCE),
        (plan.kernel_source_hash, _kernel_source_hash()),
        (plan.compile_options, _COMPILE_OPTIONS),
        (plan.kernel_symbols, HIP_FGMRES_FIXED_RANK_COARSE_KERNEL_SYMBOLS_V1),
        (
            plan.kernel_abi_hash,
            canonical_hash(hip_fgmres_fixed_rank_coarse_kernel_abi_payload_v1()),
        ),
    )
    if any(actual != expected for actual, expected in expected_bindings):
        _fail("hip_fgmres_coarse_plan_replay_mismatch", "/")
    _validate_exact_scalar_types(plan)
    if plan.memory_layout_hash != _memory_layout_hash(plan):
        _fail("hip_fgmres_coarse_memory_layout_hash_mismatch", "/memory_layout_hash")
    _validate_schema(_plan_payload(plan, include_hash=True))
    if plan.plan_hash != canonical_hash(_plan_payload(plan, include_hash=False)):
        _fail("hip_fgmres_coarse_plan_hash_mismatch", "/plan_hash")
    return plan


def _validate_sources(
    fgmres_plan: HipFgmresPlanV1,
    coarse_space: CpuFgmresFixedRankCoarseSpaceV1,
) -> None:
    if type(fgmres_plan) is not HipFgmresPlanV1:
        _fail("hip_fgmres_coarse_source_plan_type_invalid", "/source_contract/fgmres")
    if type(coarse_space) is not CpuFgmresFixedRankCoarseSpaceV1:
        _fail(
            "hip_fgmres_coarse_source_space_type_invalid",
            "/source_contract/coarse_space",
        )
    try:
        validate_hip_fgmres_plan_v1(fgmres_plan)
    except HipFgmresPlanV1Error as exc:
        raise HipFgmresFixedRankCoarsePlanV1Error(
            "hip_fgmres_coarse_source_plan_invalid",
            "/source_contract/fgmres",
            exc.code,
        ) from exc
    try:
        validate_cpu_fgmres_fixed_rank_coarse_space_v1(coarse_space)
    except CpuFgmresFixedRankCoarseError as exc:
        raise HipFgmresFixedRankCoarsePlanV1Error(
            "hip_fgmres_coarse_source_space_invalid",
            "/source_contract/coarse_space",
            exc.code,
        ) from exc
    if (
        coarse_space.schema_version
        != CPU_FGMRES_FIXED_RANK_COARSE_SPACE_V1_SCHEMA_VERSION
        or coarse_space.algorithm_version
        != CPU_FGMRES_FIXED_RANK_COARSE_ALGORITHM_VERSION_V1
        or coarse_space.retained_rank > MAX_CPU_FGMRES_COARSE_RANK_V1
    ):
        _fail(
            "hip_fgmres_coarse_source_space_version_invalid",
            "/source_contract/coarse_space",
        )
    bindings = (
        (fgmres_plan.source_execution_plan_hash, coarse_space.execution_plan_hash),
        (fgmres_plan.source_operator_hash, coarse_space.operator_hash),
        (fgmres_plan.source_numeric_snapshot_hash, coarse_space.numeric_snapshot_hash),
        (fgmres_plan.source_partition_hash, coarse_space.partition_hash),
        (fgmres_plan.free_dof_count, coarse_space.free_dof_count),
        (fgmres_plan.reduced_csr_nnz, coarse_space.reduced_nnz),
    )
    if any(actual != expected for actual, expected in bindings):
        _fail("hip_fgmres_coarse_source_binding_mismatch", "/source_contract")


def _compile_buffers(
    fgmres_plan: HipFgmresPlanV1,
    *,
    f: int,
    k: int,
    m: int,
) -> tuple[HipFgmresFixedRankCoarseBufferPlanV1, ...]:
    source_rows = {name: fgmres_plan.buffer(name) for name in _BORROWED_NAMES}
    expected_parent_shapes = {
        "jacobi_inverse": (f,),
        "basis_v": (m + 1, f),
        "preconditioned_basis_z": (m, f),
    }
    rows: list[HipFgmresFixedRankCoarseBufferPlanV1] = []
    for name in _BORROWED_NAMES:
        source = source_rows[name]
        if (
            type(source) is not HipFgmresBufferPlanV1
            or source.dtype != "<f8"
            or source.shape != expected_parent_shapes[name]
        ):
            _fail("hip_fgmres_coarse_parent_buffer_invalid", f"/buffers/{name}")
        rows.append(
            HipFgmresFixedRankCoarseBufferPlanV1(
                name=name,
                ownership="borrowed",
                dtype="<f8",
                shape=source.shape,
                element_count=source.element_count,
                byte_length=source.byte_length,
                access=(
                    "read_only"
                    if name != "preconditioned_basis_z"
                    else "write_logical_column"
                ),
                source=f"fgmres_plan:{name}",
                initialization="parent_owned_no_transfer",
                layout=(
                    "vector"
                    if name == "jacobi_inverse"
                    else "row_major_column_by_free_dof"
                ),
            )
        )
    specifications = (
        (
            "coarse_physical_basis_z",
            "<f8",
            (f, k),
            "read_only",
            "cpu_coarse_space:physical_basis_z",
            "one_time_async_h2d_before_recurrence",
            "row_major_free_dof_by_rank",
        ),
        (
            "coarse_operator_basis_az",
            "<f8",
            (f, k),
            "read_only",
            "cpu_coarse_space:operator_basis_az",
            "one_time_async_h2d_before_recurrence",
            "row_major_free_dof_by_rank",
        ),
        (
            "coarse_cholesky_l",
            "<f8",
            (k, k),
            "read_only",
            "cpu_coarse_space:coarse_cholesky_l",
            "one_time_async_h2d_before_recurrence",
            "row_major_rank_by_rank_lower_triangle",
        ),
        (
            "coarse_rhs",
            "<f8",
            (k,),
            "read_write",
            "coarse_context",
            "prepare_kernel_each_application",
            "vector_rank",
        ),
        (
            "coarse_coefficients",
            "<f8",
            (k,),
            "read_write",
            "coarse_context",
            "prepare_kernel_each_application",
            "vector_rank",
        ),
        (
            "coarse_status",
            "<u4",
            (1,),
            "read_write",
            "coarse_context",
            "prepare_kernel_each_application",
            "scalar_status_bits",
        ),
    )
    for name, dtype, shape, access, source, initialization, layout in specifications:
        count = 1
        for extent in shape:
            count = _checked_product(
                count, extent, path=f"/buffers/{name}/element_count"
            )
        item_size = 8 if dtype == "<f8" else 4
        rows.append(
            HipFgmresFixedRankCoarseBufferPlanV1(
                name=name,
                ownership="owned",
                dtype=dtype,  # type: ignore[arg-type]
                shape=shape,
                element_count=count,
                byte_length=_checked_product(
                    count,
                    item_size,
                    path=f"/buffers/{name}/byte_length",
                ),
                access=access,
                source=source,
                initialization=initialization,
                layout=layout,
            )
        )
    return tuple(rows)


def _compile_launches(
    *,
    f: int,
    k: int,
) -> tuple[HipFgmresFixedRankCoarseLaunchPlanV1, ...]:
    return (
        HipFgmresFixedRankCoarseLaunchPlanV1(
            ordinal=0,
            symbol=HIP_FGMRES_FIXED_RANK_COARSE_PREPARE_SYMBOL_V1,
            grid_x=1,
            block_x=1,
            grid_formula="1",
            reads=(),
            writes=("coarse_rhs", "coarse_coefficients", "coarse_status"),
        ),
        HipFgmresFixedRankCoarseLaunchPlanV1(
            ordinal=1,
            symbol=HIP_FGMRES_FIXED_RANK_COARSE_DOT_SYMBOL_V1,
            grid_x=k,
            block_x=HIP_FGMRES_FIXED_RANK_COARSE_BLOCK_SIZE_V1,
            grid_formula="retained_rank",
            reads=("basis_v", "coarse_physical_basis_z", "coarse_status"),
            writes=("coarse_rhs", "coarse_status"),
        ),
        HipFgmresFixedRankCoarseLaunchPlanV1(
            ordinal=2,
            symbol=HIP_FGMRES_FIXED_RANK_COARSE_SOLVE_SYMBOL_V1,
            grid_x=1,
            block_x=1,
            grid_formula="1",
            reads=("coarse_cholesky_l", "coarse_rhs", "coarse_status"),
            writes=("coarse_coefficients", "coarse_status"),
        ),
        HipFgmresFixedRankCoarseLaunchPlanV1(
            ordinal=3,
            symbol=HIP_FGMRES_FIXED_RANK_COARSE_APPLY_SYMBOL_V1,
            grid_x=(f + HIP_FGMRES_FIXED_RANK_COARSE_BLOCK_SIZE_V1 - 1)
            // HIP_FGMRES_FIXED_RANK_COARSE_BLOCK_SIZE_V1,
            block_x=HIP_FGMRES_FIXED_RANK_COARSE_BLOCK_SIZE_V1,
            grid_formula="ceil(free_dof_count/256)",
            reads=(
                "jacobi_inverse",
                "basis_v",
                "coarse_physical_basis_z",
                "coarse_operator_basis_az",
                "coarse_coefficients",
                "coarse_status",
            ),
            writes=("preconditioned_basis_z", "coarse_status"),
        ),
    )


def _descriptor_hash(
    coarse_space: CpuFgmresFixedRankCoarseSpaceV1,
    name: str,
) -> str:
    for row in coarse_space.descriptors:
        if row.name == name:
            return row.data_hash
    _fail("hip_fgmres_coarse_source_descriptor_missing", f"/source_contract/{name}")


def _kernel_source_hash() -> str:
    try:
        source = _SOURCE_PATH.read_bytes()
    except OSError as exc:
        raise HipFgmresFixedRankCoarsePlanV1Error(
            "hip_fgmres_coarse_kernel_source_missing",
            "/kernel/source_resource",
            type(exc).__name__,
        ) from exc
    if not source or b"\x00" in source:
        _fail("hip_fgmres_coarse_kernel_source_invalid", "/kernel/source_resource")
    return "sha256:" + hashlib.sha256(source).hexdigest()


def _memory_layout_hash(plan: HipFgmresFixedRankCoarsePlanV1) -> str:
    return canonical_hash(
        {
            "buffers": [row.to_dict() for row in plan.buffers],
            "launches": [row.to_dict() for row in plan.launches],
            "borrowed_device_byte_span": plan.borrowed_device_byte_span,
            "owned_device_byte_length": plan.owned_device_byte_length,
            "static_upload_copy_count": plan.static_upload_copy_count,
            "static_upload_byte_count": plan.static_upload_byte_count,
        }
    )


def _plan_payload(
    plan: HipFgmresFixedRankCoarsePlanV1,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload = {
        "schema_version": plan.schema_version,
        "capability_profile": plan.capability_profile,
        "application_abi_version": plan.application_abi_version,
        "source_contract": {
            "fgmres_plan_id": plan.source_fgmres_plan_id,
            "fgmres_plan_hash": plan.source_fgmres_plan_hash,
            "fgmres_memory_layout_hash": plan.source_fgmres_memory_layout_hash,
            "execution_plan_hash": plan.source_execution_plan_hash,
            "operator_hash": plan.source_operator_hash,
            "numeric_snapshot_hash": plan.source_numeric_snapshot_hash,
            "partition_hash": plan.source_partition_hash,
            "coarse_space_schema_version": (plan.source_coarse_space_schema_version),
            "coarse_algorithm_version": plan.source_coarse_algorithm_version,
            "coarse_space_hash": plan.source_coarse_space_hash,
            "physical_basis_data_hash": plan.physical_basis_data_hash,
            "operator_basis_data_hash": plan.operator_basis_data_hash,
            "cholesky_data_hash": plan.cholesky_data_hash,
        },
        "dimensions": {
            "free_dof_count": plan.free_dof_count,
            "reduced_nnz": plan.reduced_nnz,
            "restart_dimension": plan.restart_dimension,
            "max_iterations": plan.max_iterations,
            "retained_rank": plan.retained_rank,
            "rank_cap": plan.rank_cap,
        },
        "memory_plan": {
            "buffers": [row.to_dict() for row in plan.buffers],
            "borrowed_device_byte_span": plan.borrowed_device_byte_span,
            "owned_device_byte_length": plan.owned_device_byte_length,
            "static_upload_copy_count": plan.static_upload_copy_count,
            "static_upload_byte_count": plan.static_upload_byte_count,
            "memory_layout_hash": plan.memory_layout_hash,
        },
        "application_schedule": {
            "launches": [row.to_dict() for row in plan.launches],
            "kernel_launch_count": plan.application_kernel_launch_count,
            "h2d_copy_count": plan.application_h2d_copy_count,
            "d2h_copy_count": plan.application_d2h_copy_count,
            "csr_apply_count": plan.application_csr_apply_count,
            "allocation_count": plan.application_allocation_count,
            "synchronization_count": plan.application_synchronization_count,
            "dense_projector_element_count": plan.dense_projector_element_count,
            "work_complexity": "O(N*k+k^2) with fixed k<=16",
        },
        "kernel": {
            "source_resource": plan.kernel_source_resource,
            "source_hash": plan.kernel_source_hash,
            "compile_options": list(plan.compile_options),
            "symbols": list(plan.kernel_symbols),
            "abi_hash": plan.kernel_abi_hash,
        },
        "claim_boundary": {
            "compile_time_plan_only": True,
            "fixed_source_present": True,
            "static_upload_planned": True,
            "application_iteration_h2d_zero_planned": True,
            "application_iteration_d2h_zero_planned": True,
            "application_additional_csr_zero_planned": True,
            "kernel_compiled": False,
            "device_allocation_performed": False,
            "device_upload_performed": False,
            "execution_performed": False,
            "numerical_parity_proven": False,
            "iteration_host_copy_zero_proven": False,
            "amg_or_dd_proven": False,
            "mesh_independent_iterations_proven": False,
            "end_to_end_O_N_proven": False,
            "speedup_proven": False,
            "promotion_eligible": False,
            "commercial_ready": False,
            "python_semantic_replay_required": True,
        },
    }
    if include_hash:
        payload["plan_hash"] = plan.plan_hash
    return payload


def _validate_exact_scalar_types(plan: HipFgmresFixedRankCoarsePlanV1) -> None:
    integer_values = (
        plan.application_abi_version,
        plan.free_dof_count,
        plan.reduced_nnz,
        plan.restart_dimension,
        plan.max_iterations,
        plan.retained_rank,
        plan.rank_cap,
        plan.borrowed_device_byte_span,
        plan.owned_device_byte_length,
        plan.static_upload_copy_count,
        plan.static_upload_byte_count,
        plan.application_kernel_launch_count,
        plan.application_h2d_copy_count,
        plan.application_d2h_copy_count,
        plan.application_csr_apply_count,
        plan.application_allocation_count,
        plan.application_synchronization_count,
        plan.dense_projector_element_count,
    )
    if any(type(value) is not int or value < 0 for value in integer_values):
        _fail("hip_fgmres_coarse_plan_scalar_type_invalid", "/")
    if (
        type(plan.buffers) is not tuple
        or any(
            type(row) is not HipFgmresFixedRankCoarseBufferPlanV1
            for row in plan.buffers
        )
        or tuple(row.name for row in plan.buffers) != _BUFFER_NAMES
        or type(plan.launches) is not tuple
        or any(
            type(row) is not HipFgmresFixedRankCoarseLaunchPlanV1
            for row in plan.launches
        )
        or type(plan.compile_options) is not tuple
        or type(plan.kernel_symbols) is not tuple
    ):
        _fail("hip_fgmres_coarse_plan_container_invalid", "/")
    hashes = (
        plan.source_fgmres_plan_hash,
        plan.source_fgmres_memory_layout_hash,
        plan.source_execution_plan_hash,
        plan.source_operator_hash,
        plan.source_numeric_snapshot_hash,
        plan.source_partition_hash,
        plan.source_coarse_space_hash,
        plan.physical_basis_data_hash,
        plan.operator_basis_data_hash,
        plan.cholesky_data_hash,
        plan.kernel_source_hash,
        plan.kernel_abi_hash,
        plan.memory_layout_hash,
        plan.plan_hash,
    )
    if any(type(value) is not str or not _HASH_RE.fullmatch(value) for value in hashes):
        _fail("hip_fgmres_coarse_plan_hash_invalid", "/")


def _checked_product(left: int, right: int, *, path: str) -> int:
    if (
        type(left) is not int
        or type(right) is not int
        or left < 0
        or right < 0
        or (left != 0 and right > _UINT64_MAX // left)
    ):
        _fail("hip_fgmres_coarse_extent_overflow", path)
    return left * right


@lru_cache(maxsize=1)
def _schema() -> dict[str, Any]:
    try:
        payload = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise HipFgmresFixedRankCoarsePlanV1Error(
            "hip_fgmres_coarse_schema_unavailable",
            "/",
            type(exc).__name__,
        ) from exc
    Draft202012Validator.check_schema(payload)
    return payload


def _validate_schema(payload: dict[str, Any]) -> None:
    errors = sorted(
        Draft202012Validator(_schema()).iter_errors(payload),
        key=lambda error: list(error.absolute_path),
    )
    if errors:
        error = errors[0]
        path = "/" + "/".join(str(part) for part in error.absolute_path)
        _fail("hip_fgmres_coarse_plan_schema_invalid", path, error.message)


def _fail(code: str, path: str, message: str = "") -> None:
    raise HipFgmresFixedRankCoarsePlanV1Error(code, path, message)


__all__ = [
    "HIP_FGMRES_FIXED_RANK_COARSE_APPLICATION_ABI_VERSION_V1",
    "HIP_FGMRES_FIXED_RANK_COARSE_APPLY_SYMBOL_V1",
    "HIP_FGMRES_FIXED_RANK_COARSE_BLOCK_SIZE_V1",
    "HIP_FGMRES_FIXED_RANK_COARSE_DOT_SYMBOL_V1",
    "HIP_FGMRES_FIXED_RANK_COARSE_KERNEL_SYMBOLS_V1",
    "HIP_FGMRES_FIXED_RANK_COARSE_PLAN_V1_CAPABILITY_PROFILE",
    "HIP_FGMRES_FIXED_RANK_COARSE_PLAN_V1_SCHEMA_VERSION",
    "HIP_FGMRES_FIXED_RANK_COARSE_PREPARE_SYMBOL_V1",
    "HIP_FGMRES_FIXED_RANK_COARSE_SOLVE_SYMBOL_V1",
    "HipFgmresFixedRankCoarseBufferPlanV1",
    "HipFgmresFixedRankCoarseLaunchPlanV1",
    "HipFgmresFixedRankCoarsePlanV1",
    "HipFgmresFixedRankCoarsePlanV1Error",
    "compile_hip_fgmres_fixed_rank_coarse_plan_v1",
    "hip_fgmres_fixed_rank_coarse_kernel_abi_payload_v1",
    "validate_hip_fgmres_fixed_rank_coarse_plan_v1",
]
