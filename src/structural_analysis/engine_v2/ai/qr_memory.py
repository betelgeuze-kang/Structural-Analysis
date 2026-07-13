"""Bounded solver-approved QR correction memory for Engine v2 Phase 0.

Only a fully validated, ready :class:`LinearStaticRun` can add one teacher.
The physical teacher mode is exactly ``(u_committed - u_initial)[free_dofs]``.
At most sixteen modes are retained with deterministic FIFO eviction, and the
projection basis is rebuilt by :func:`build_fixed_rank_projection` after every
accepted update.  This module has no training, gradient, or legacy-AI path.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from functools import lru_cache
import hashlib
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
import numpy as np

from structural_analysis.engine_v2.ai.projection import (
    DEFAULT_DROP_TOLERANCE,
    MAX_PROJECTION_RANK,
    FixedRankProjection,
    ProjectionError,
    build_fixed_rank_projection,
    validate_fixed_rank_projection,
)
from structural_analysis.engine_v2.contracts._canonical import (
    array_content_hash,
    array_data_hash,
    canonical_hash,
    canonical_json_bytes,
    has_immutable_bytes_backing,
    immutable_array,
    sha256_prefixed,
)
from structural_analysis.engine_v2.contracts.execution_plan import (
    ExecutionPlan,
    validate_execution_plan,
)
from structural_analysis.engine_v2.runner import (
    LinearStaticRun,
    validate_linear_static_run,
)

FIXED_RANK_QR_MEMORY_SCHEMA_VERSION = (
    "structural-analysis-fixed-rank-qr-memory.v1"
)
FIXED_RANK_QR_MEMORY_ALGORITHM_VERSION = "solver_approved_fifo_qr_memory.v1"


class QRMemoryError(ValueError):
    """Fail-closed QR-memory error with a stable code and JSON path."""

    def __init__(self, code: str, path: str, message: str) -> None:
        self.code = code
        self.path = path
        self.message = message
        super().__init__(f"{code}@{path}: {message}")


@dataclass(frozen=True, slots=True)
class QRTeacherProvenance:
    """Hash-only provenance for one active solver-approved teacher mode."""

    sequence: int
    teacher_id: str
    receipt_chain_hash: str
    result_ir_hash: str
    backend_native_result_hash: str
    initial_state_hash: str
    committed_state_hash: str
    solver_artifact_hash: str
    matrix_backend: str
    teacher_mode_data_hash: str
    teacher_mode_content_hash: str
    previous_teacher_chain_hash: str
    teacher_chain_hash: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class QRMemoryUpdateReceipt:
    """Exact bounded counts for initialization or the most recent update."""

    operation: str
    previous_active_teacher_count: int
    current_active_teacher_count: int
    appended_teacher_count: int
    evicted_teacher_count_this_update: int
    fifo_retained_teacher_count: int
    accepted_teacher_count_total: int
    evicted_teacher_count_total: int
    teacher_free_dof_subtraction_count: int
    projection_rebuild_count: int
    projection_candidate_count: int
    projection_retained_rank: int
    projection_basis_scaling_multiply_count: int
    projection_orthogonalization_dot_count: int
    projection_orthogonalization_axpy_count: int
    projection_normalization_divide_count: int
    raw_mode_elements: int
    basis_elements: int
    max_dense_square_dimension: int
    reverse_mode_autograd_call_count: int
    gradient_update_count: int
    storage_complexity: str
    rebuild_complexity: str

    def to_dict(self) -> dict[str, int | str]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class FixedRankQRMemory:
    """Immutable plan-bound active FIFO window and its QR projection."""

    schema_version: str
    algorithm_version: str
    plan_hash: str
    operator_hash: str
    pattern_hash: str
    partition_hash: str
    free_dof_count: int
    rank_cap: int
    accepted_teacher_count_total: int
    evicted_teacher_count_total: int
    chain_anchor_hash: str
    rolling_teacher_chain_hash: str
    provenance: tuple[QRTeacherProvenance, ...]
    raw_modes: np.ndarray
    basis_q: np.ndarray
    projection: FixedRankProjection | None
    update_receipt: QRMemoryUpdateReceipt
    memory_hash: str

    @property
    def active_teacher_count(self) -> int:
        return len(self.provenance)

    @property
    def retained_rank(self) -> int:
        return int(self.basis_q.shape[1])

    def to_manifest(self) -> dict[str, Any]:
        validate_fixed_rank_qr_memory(self)
        return _memory_manifest(self, include_memory_hash=True)


def create_fixed_rank_qr_memory(
    plan: ExecutionPlan,
    rank_cap: int = MAX_PROJECTION_RANK,
) -> FixedRankQRMemory:
    """Create a valid empty memory bound to one exact ExecutionPlan."""

    _validate_rank_cap(rank_cap)
    _validate_plan(plan)
    free_dof_count = int(plan.array("free_dofs").size)
    raw_modes = immutable_array(
        np.empty((free_dof_count, 0), dtype="<f8"), dtype="<f8"
    )
    basis_q = immutable_array(
        np.empty((free_dof_count, 0), dtype="<f8"), dtype="<f8"
    )
    root = _teacher_chain_root(plan, int(rank_cap))
    provisional = FixedRankQRMemory(
        schema_version=FIXED_RANK_QR_MEMORY_SCHEMA_VERSION,
        algorithm_version=FIXED_RANK_QR_MEMORY_ALGORITHM_VERSION,
        plan_hash=plan.plan_hash,
        operator_hash=plan.operator_hash,
        pattern_hash=plan.pattern_hash,
        partition_hash=plan.partition_hash,
        free_dof_count=free_dof_count,
        rank_cap=int(rank_cap),
        accepted_teacher_count_total=0,
        evicted_teacher_count_total=0,
        chain_anchor_hash=root,
        rolling_teacher_chain_hash=root,
        provenance=(),
        raw_modes=raw_modes,
        basis_q=basis_q,
        projection=None,
        update_receipt=_expected_update_receipt(
            free_dof_count=free_dof_count,
            rank_cap=int(rank_cap),
            accepted_total=0,
            projection=None,
        ),
        memory_hash="sha256:" + ("0" * 64),
    )
    memory = replace(provisional, memory_hash=_memory_hash(provisional))
    validate_fixed_rank_qr_memory(memory, expected_plan=plan)
    return memory


def update_fixed_rank_qr_memory_from_run(
    memory: FixedRankQRMemory,
    authoritative_run: LinearStaticRun,
) -> FixedRankQRMemory:
    """Append one validated solver teacher and rebuild the bounded basis."""

    if not isinstance(authoritative_run, LinearStaticRun):
        _fail(
            "qr_memory_authoritative_run_type_invalid",
            "/authoritative_run",
            "Only a LinearStaticRun can provide a teacher mode.",
        )
    try:
        validate_linear_static_run(
            authoritative_run,
            expected_buffers=authoritative_run.buffers,
        )
    except Exception as exc:
        raise QRMemoryError(
            "qr_memory_authoritative_run_invalid",
            "/authoritative_run",
            f"LinearStaticRun validation failed: {exc}",
        ) from exc
    if authoritative_run.status != "ready":
        _fail(
            "qr_memory_authoritative_run_not_ready",
            "/authoritative_run/status",
            "Teacher runs must have ready status.",
        )

    run_plan = authoritative_run.execution_plan
    validate_fixed_rank_qr_memory(memory, expected_plan=run_plan)
    free = run_plan.array("free_dofs")
    teacher_mode = immutable_array(
        authoritative_run.committed_state.displacement_si[free]
        - authoritative_run.initial_state.displacement_si[free],
        dtype="<f8",
    )
    if teacher_mode.shape != (memory.free_dof_count,) or not np.all(
        np.isfinite(teacher_mode)
    ):
        _fail(
            "qr_memory_teacher_mode_invalid",
            "/teacher_mode",
            "Committed-minus-initial free-DOF mode is invalid.",
        )
    if not np.any(teacher_mode != 0.0):
        _fail(
            "qr_memory_teacher_mode_zero",
            "/teacher_mode",
            "A zero physical mode cannot form a correction basis.",
        )

    next_sequence = memory.accepted_teacher_count_total + 1
    provenance = _teacher_provenance(
        authoritative_run,
        teacher_mode,
        sequence=next_sequence,
        previous_chain_hash=memory.rolling_teacher_chain_hash,
    )
    old_active = memory.active_teacher_count
    if old_active < memory.rank_cap:
        active_provenance = memory.provenance + (provenance,)
        columns = [memory.raw_modes, teacher_mode.reshape(-1, 1)]
        chain_anchor = memory.chain_anchor_hash
    else:
        active_provenance = memory.provenance[1:] + (provenance,)
        columns = [memory.raw_modes[:, 1:], teacher_mode.reshape(-1, 1)]
        chain_anchor = memory.provenance[0].teacher_chain_hash
    raw_modes = immutable_array(np.column_stack(columns), dtype="<f8")

    try:
        projection = build_fixed_rank_projection(
            run_plan,
            raw_modes,
            rank_cap=memory.rank_cap,
            drop_tolerance=DEFAULT_DROP_TOLERANCE,
        )
    except ProjectionError as exc:
        raise QRMemoryError(
            "qr_memory_projection_rebuild_failed",
            "/projection",
            f"Fixed-rank projection rebuild failed: {exc}",
        ) from exc

    accepted_total = next_sequence
    evicted_total = max(0, accepted_total - memory.rank_cap)
    provisional = replace(
        memory,
        accepted_teacher_count_total=accepted_total,
        evicted_teacher_count_total=evicted_total,
        chain_anchor_hash=chain_anchor,
        rolling_teacher_chain_hash=provenance.teacher_chain_hash,
        provenance=active_provenance,
        raw_modes=raw_modes,
        basis_q=projection.basis_q,
        projection=projection,
        update_receipt=_expected_update_receipt(
            free_dof_count=memory.free_dof_count,
            rank_cap=memory.rank_cap,
            accepted_total=accepted_total,
            projection=projection,
        ),
        memory_hash="sha256:" + ("0" * 64),
    )
    updated = replace(provisional, memory_hash=_memory_hash(provisional))
    validate_fixed_rank_qr_memory(updated, expected_plan=run_plan)
    return updated


def validate_fixed_rank_qr_memory(
    memory: FixedRankQRMemory,
    *,
    expected_plan: ExecutionPlan | None = None,
) -> None:
    """Replay storage, projection, FIFO, provenance, counts, and hashes."""

    if not isinstance(memory, FixedRankQRMemory):
        _fail(
            "qr_memory_type_invalid", "/", "Expected a FixedRankQRMemory instance."
        )
    if memory.schema_version != FIXED_RANK_QR_MEMORY_SCHEMA_VERSION:
        _fail(
            "qr_memory_schema_version_mismatch",
            "/schema_version",
            "Unsupported QR-memory schema version.",
        )
    if memory.algorithm_version != FIXED_RANK_QR_MEMORY_ALGORITHM_VERSION:
        _fail(
            "qr_memory_algorithm_version_mismatch",
            "/algorithm_version",
            "Unsupported QR-memory algorithm version.",
        )
    _validate_rank_cap(memory.rank_cap)
    if (
        isinstance(memory.free_dof_count, (bool, np.bool_))
        or not isinstance(memory.free_dof_count, (int, np.integer))
        or memory.free_dof_count <= 0
    ):
        _fail(
            "qr_memory_free_dof_count_invalid",
            "/free_dof_count",
            "Free DOF count must be positive.",
        )
    for field in (
        "accepted_teacher_count_total",
        "evicted_teacher_count_total",
    ):
        value = getattr(memory, field)
        if (
            isinstance(value, (bool, np.bool_))
            or not isinstance(value, (int, np.integer))
            or value < 0
        ):
            _fail(
                "qr_memory_count_invalid",
                f"/{field}",
                f"{field} must be a non-negative integer.",
            )
    if not isinstance(memory.provenance, tuple) or any(
        not isinstance(row, QRTeacherProvenance) for row in memory.provenance
    ):
        _fail(
            "qr_memory_provenance_type_invalid",
            "/provenance",
            "Provenance must be a tuple of QRTeacherProvenance values.",
        )
    if not isinstance(memory.update_receipt, QRMemoryUpdateReceipt):
        _fail(
            "qr_memory_update_receipt_type_invalid",
            "/update_receipt",
            "Expected QRMemoryUpdateReceipt.",
        )

    active_count = memory.active_teacher_count
    expected_active = min(memory.accepted_teacher_count_total, memory.rank_cap)
    expected_evicted = max(
        0, memory.accepted_teacher_count_total - memory.rank_cap
    )
    if active_count != expected_active or memory.evicted_teacher_count_total != expected_evicted:
        _fail(
            "qr_memory_fifo_count_mismatch",
            "/provenance",
            "Active/evicted counts do not match deterministic FIFO policy.",
        )

    _validate_array(
        memory.raw_modes,
        name="raw_modes",
        expected_shape=(memory.free_dof_count, active_count),
    )
    retained_rank = (
        int(memory.basis_q.shape[1])
        if isinstance(memory.basis_q, np.ndarray) and memory.basis_q.ndim == 2
        else -1
    )
    _validate_array(
        memory.basis_q,
        name="basis_q",
        expected_shape=(memory.free_dof_count, retained_rank),
    )

    if active_count == 0:
        if memory.projection is not None or retained_rank != 0:
            _fail(
                "qr_memory_empty_projection_invalid",
                "/projection",
                "Empty memory requires no projection and an empty basis.",
            )
    else:
        if not isinstance(memory.projection, FixedRankProjection):
            _fail(
                "qr_memory_projection_missing",
                "/projection",
                "Non-empty memory requires a FixedRankProjection.",
            )
        try:
            validate_fixed_rank_projection(
                memory.projection,
                expected_plan=expected_plan,
            )
        except ProjectionError as exc:
            raise QRMemoryError(
                "qr_memory_projection_invalid",
                "/projection",
                f"Projection validation failed: {exc}",
            ) from exc
        if (
            memory.projection.plan_hash != memory.plan_hash
            or memory.projection.operator_hash != memory.operator_hash
            or memory.projection.pattern_hash != memory.pattern_hash
            or memory.projection.rank_cap != memory.rank_cap
            or memory.projection.candidate_count != active_count
            or memory.projection.free_dof_count != memory.free_dof_count
            or not np.array_equal(
                memory.projection.candidate_vectors, memory.raw_modes
            )
            or not np.array_equal(memory.projection.basis_q, memory.basis_q)
        ):
            _fail(
                "qr_memory_projection_replay_mismatch",
                "/projection",
                "Projection candidates or basis differ from active raw modes.",
            )
        if memory.projection.drop_tolerance != DEFAULT_DROP_TOLERANCE:
            _fail(
                "qr_memory_projection_policy_mismatch",
                "/projection/drop_tolerance",
                "QR memory requires the fixed Phase 0 drop tolerance.",
            )

    if expected_plan is not None:
        _validate_plan(expected_plan)
        bindings = (
            (memory.plan_hash, expected_plan.plan_hash, "plan_hash"),
            (memory.operator_hash, expected_plan.operator_hash, "operator_hash"),
            (memory.pattern_hash, expected_plan.pattern_hash, "pattern_hash"),
            (
                memory.partition_hash,
                expected_plan.partition_hash,
                "partition_hash",
            ),
            (
                memory.free_dof_count,
                int(expected_plan.array("free_dofs").size),
                "free_dof_count",
            ),
        )
        for actual, expected, field in bindings:
            if actual != expected:
                _fail(
                    "qr_memory_plan_binding_mismatch",
                    f"/plan_binding/{field}",
                    f"QR memory {field} differs from the ExecutionPlan.",
                )

    root = _teacher_chain_root_from_memory(memory)
    if active_count == 0:
        if (
            memory.chain_anchor_hash != root
            or memory.rolling_teacher_chain_hash != root
        ):
            _fail(
                "qr_memory_teacher_chain_invalid",
                "/rolling_teacher_chain_hash",
                "Empty memory must use the deterministic root chain hash.",
            )
    else:
        previous = memory.chain_anchor_hash
        first_sequence = memory.evicted_teacher_count_total + 1
        for index, row in enumerate(memory.provenance):
            expected_sequence = first_sequence + index
            if row.sequence != expected_sequence:
                _fail(
                    "qr_memory_provenance_sequence_invalid",
                    f"/provenance/{index}/sequence",
                    "Active provenance sequence is not FIFO-contiguous.",
                )
            mode = immutable_array(memory.raw_modes[:, index], dtype="<f8")
            data_hash, content_hash = _teacher_mode_hashes(
                mode, sequence=row.sequence
            )
            if (
                row.teacher_mode_data_hash != data_hash
                or row.teacher_mode_content_hash != content_hash
            ):
                _fail(
                    "qr_memory_teacher_mode_hash_mismatch",
                    f"/provenance/{index}/teacher_mode_data_hash",
                    "Teacher-mode provenance differs from raw mode bytes.",
                )
            if row.previous_teacher_chain_hash != previous:
                _fail(
                    "qr_memory_teacher_chain_invalid",
                    f"/provenance/{index}/previous_teacher_chain_hash",
                    "Teacher provenance chain link is stale.",
                )
            expected_chain = _teacher_chain_hash(row)
            if row.teacher_chain_hash != expected_chain:
                _fail(
                    "qr_memory_teacher_chain_invalid",
                    f"/provenance/{index}/teacher_chain_hash",
                    "Teacher provenance chain hash is stale.",
                )
            expected_teacher_id = _teacher_id(expected_chain)
            if row.teacher_id != expected_teacher_id:
                _fail(
                    "qr_memory_teacher_id_invalid",
                    f"/provenance/{index}/teacher_id",
                    "Teacher ID does not derive from its chain hash.",
                )
            previous = expected_chain
        if memory.rolling_teacher_chain_hash != previous:
            _fail(
                "qr_memory_teacher_chain_invalid",
                "/rolling_teacher_chain_hash",
                "Rolling teacher chain does not end at the newest teacher.",
            )

    expected_receipt = _expected_update_receipt(
        free_dof_count=memory.free_dof_count,
        rank_cap=memory.rank_cap,
        accepted_total=memory.accepted_teacher_count_total,
        projection=memory.projection,
    )
    if memory.update_receipt != expected_receipt:
        _fail(
            "qr_memory_update_receipt_mismatch",
            "/update_receipt",
            "Update receipt differs from exact bounded replay counts.",
        )

    payload = _memory_manifest(memory, include_memory_hash=True)
    errors = sorted(
        _schema_validator().iter_errors(payload),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    if errors:
        error = errors[0]
        path = "/" + "/".join(str(part) for part in error.absolute_path)
        _fail("qr_memory_schema_invalid", path, error.message)
    if memory.memory_hash != _memory_hash(memory):
        _fail(
            "qr_memory_hash_mismatch",
            "/memory_hash",
            "QR-memory aggregate hash is stale.",
        )


def _validate_rank_cap(rank_cap: Any) -> None:
    if (
        isinstance(rank_cap, (bool, np.bool_))
        or not isinstance(rank_cap, (int, np.integer))
        or not 1 <= int(rank_cap) <= MAX_PROJECTION_RANK
    ):
        _fail(
            "qr_memory_rank_cap_invalid",
            "/rank_cap",
            f"Rank cap must be an integer in [1, {MAX_PROJECTION_RANK}].",
        )


def _validate_plan(plan: Any) -> None:
    if not isinstance(plan, ExecutionPlan):
        _fail(
            "qr_memory_execution_plan_type_invalid",
            "/plan",
            "Expected an ExecutionPlan.",
        )
    try:
        validate_execution_plan(plan)
    except Exception as exc:
        raise QRMemoryError(
            "qr_memory_execution_plan_invalid",
            "/plan",
            f"ExecutionPlan validation failed: {exc}",
        ) from exc


def _validate_array(
    array: Any,
    *,
    name: str,
    expected_shape: tuple[int, int],
) -> None:
    if not isinstance(array, np.ndarray) or array.dtype.str != "<f8":
        _fail(
            "qr_memory_array_dtype_invalid",
            f"/arrays/{name}/dtype",
            f"{name} must use little-endian float64.",
        )
    if array.ndim != 2 or array.shape != expected_shape:
        _fail(
            "qr_memory_array_shape_invalid",
            f"/arrays/{name}/shape",
            f"Expected {expected_shape}, received {getattr(array, 'shape', None)}.",
        )
    if not array.flags.c_contiguous or not has_immutable_bytes_backing(array):
        _fail(
            "qr_memory_array_storage_invalid",
            f"/arrays/{name}",
            f"{name} must be C-contiguous and immutable-bytes-backed.",
        )
    if not np.all(np.isfinite(array)):
        _fail(
            "qr_memory_array_non_finite",
            f"/arrays/{name}",
            f"{name} contains a non-finite value.",
        )


def _teacher_provenance(
    run: LinearStaticRun,
    mode: np.ndarray,
    *,
    sequence: int,
    previous_chain_hash: str,
) -> QRTeacherProvenance:
    data_hash, content_hash = _teacher_mode_hashes(mode, sequence=sequence)
    provisional = QRTeacherProvenance(
        sequence=sequence,
        teacher_id="Teacher:pending",
        receipt_chain_hash=run.receipt_chain_hash,
        result_ir_hash=run.result_ir.result_ir_hash,
        backend_native_result_hash=run.backend_result.result_hash,
        initial_state_hash=run.initial_state.state_hash,
        committed_state_hash=run.committed_state.state_hash,
        solver_artifact_hash=run.buffers.artifact_hash,
        matrix_backend=run.execution_plan.matrix_backend,
        teacher_mode_data_hash=data_hash,
        teacher_mode_content_hash=content_hash,
        previous_teacher_chain_hash=previous_chain_hash,
        teacher_chain_hash="sha256:" + ("0" * 64),
    )
    chain_hash = _teacher_chain_hash(provisional)
    return replace(
        provisional,
        teacher_id=_teacher_id(chain_hash),
        teacher_chain_hash=chain_hash,
    )


def _teacher_mode_hashes(
    mode: np.ndarray,
    *,
    sequence: int,
) -> tuple[str, str]:
    metadata = {
        "name": "teacher_physical_free_dof_mode",
        "definition": "(committed_displacement-initial_displacement)[free_dofs]",
        "sequence": sequence,
        "dtype": mode.dtype.str,
        "shape": [int(value) for value in mode.shape],
        "layout": "C",
        "byte_length": int(mode.nbytes),
    }
    return array_data_hash(mode), array_content_hash(metadata, mode)


def _teacher_chain_hash(row: QRTeacherProvenance) -> str:
    payload = row.to_dict()
    payload.pop("teacher_id")
    payload.pop("teacher_chain_hash")
    return canonical_hash(
        {
            "schema_version": FIXED_RANK_QR_MEMORY_SCHEMA_VERSION,
            "algorithm_version": FIXED_RANK_QR_MEMORY_ALGORITHM_VERSION,
            "teacher": payload,
        }
    )


def _teacher_id(chain_hash: str) -> str:
    return f"Teacher:{chain_hash.removeprefix('sha256:')[:24]}"


def _teacher_chain_root(plan: ExecutionPlan, rank_cap: int) -> str:
    return canonical_hash(
        {
            "schema_version": FIXED_RANK_QR_MEMORY_SCHEMA_VERSION,
            "algorithm_version": FIXED_RANK_QR_MEMORY_ALGORITHM_VERSION,
            "chain": "empty_teacher_root",
            "plan_hash": plan.plan_hash,
            "operator_hash": plan.operator_hash,
            "pattern_hash": plan.pattern_hash,
            "partition_hash": plan.partition_hash,
            "rank_cap": rank_cap,
        }
    )


def _teacher_chain_root_from_memory(memory: FixedRankQRMemory) -> str:
    return canonical_hash(
        {
            "schema_version": memory.schema_version,
            "algorithm_version": memory.algorithm_version,
            "chain": "empty_teacher_root",
            "plan_hash": memory.plan_hash,
            "operator_hash": memory.operator_hash,
            "pattern_hash": memory.pattern_hash,
            "partition_hash": memory.partition_hash,
            "rank_cap": memory.rank_cap,
        }
    )


def _expected_update_receipt(
    *,
    free_dof_count: int,
    rank_cap: int,
    accepted_total: int,
    projection: FixedRankProjection | None,
) -> QRMemoryUpdateReceipt:
    if accepted_total == 0:
        return QRMemoryUpdateReceipt(
            operation="initialize",
            previous_active_teacher_count=0,
            current_active_teacher_count=0,
            appended_teacher_count=0,
            evicted_teacher_count_this_update=0,
            fifo_retained_teacher_count=0,
            accepted_teacher_count_total=0,
            evicted_teacher_count_total=0,
            teacher_free_dof_subtraction_count=0,
            projection_rebuild_count=0,
            projection_candidate_count=0,
            projection_retained_rank=0,
            projection_basis_scaling_multiply_count=0,
            projection_orthogonalization_dot_count=0,
            projection_orthogonalization_axpy_count=0,
            projection_normalization_divide_count=0,
            raw_mode_elements=0,
            basis_elements=0,
            max_dense_square_dimension=0,
            reverse_mode_autograd_call_count=0,
            gradient_update_count=0,
            storage_complexity="O(Nk)",
            rebuild_complexity="O(Nk^2)",
        )
    if projection is None:
        _fail(
            "qr_memory_projection_missing",
            "/projection",
            "Updated memory requires a projection.",
        )
    active = min(accepted_total, rank_cap)
    previous_active = min(accepted_total - 1, rank_cap)
    evicted_this = int(accepted_total > rank_cap)
    complexity = projection.complexity_receipt
    return QRMemoryUpdateReceipt(
        operation=("append_fifo_evict" if evicted_this else "append"),
        previous_active_teacher_count=previous_active,
        current_active_teacher_count=active,
        appended_teacher_count=1,
        evicted_teacher_count_this_update=evicted_this,
        fifo_retained_teacher_count=previous_active - evicted_this,
        accepted_teacher_count_total=accepted_total,
        evicted_teacher_count_total=max(0, accepted_total - rank_cap),
        teacher_free_dof_subtraction_count=free_dof_count,
        projection_rebuild_count=1,
        projection_candidate_count=projection.candidate_count,
        projection_retained_rank=projection.retained_rank,
        projection_basis_scaling_multiply_count=(
            complexity.basis_scaling_multiply_count
        ),
        projection_orthogonalization_dot_count=(
            complexity.orthogonalization_dot_count
        ),
        projection_orthogonalization_axpy_count=(
            complexity.orthogonalization_axpy_count
        ),
        projection_normalization_divide_count=(
            complexity.normalization_divide_count
        ),
        raw_mode_elements=free_dof_count * active,
        basis_elements=free_dof_count * projection.retained_rank,
        max_dense_square_dimension=complexity.max_dense_square_dimension,
        reverse_mode_autograd_call_count=0,
        gradient_update_count=0,
        storage_complexity="O(Nk)",
        rebuild_complexity="O(Nk^2)",
    )


def _memory_manifest(
    memory: FixedRankQRMemory,
    *,
    include_memory_hash: bool,
) -> dict[str, Any]:
    projection_summary: dict[str, Any] | None
    if memory.projection is None:
        projection_summary = None
    else:
        projection_summary = {
            "schema_version": memory.projection.schema_version,
            "algorithm_version": memory.projection.algorithm_version,
            "projection_hash": memory.projection.projection_hash,
            "candidate_count": memory.projection.candidate_count,
            "retained_rank": memory.projection.retained_rank,
            "drop_tolerance": memory.projection.drop_tolerance,
        }
    payload: dict[str, Any] = {
        "schema_version": memory.schema_version,
        "algorithm_version": memory.algorithm_version,
        "plan_binding": {
            "plan_hash": memory.plan_hash,
            "operator_hash": memory.operator_hash,
            "pattern_hash": memory.pattern_hash,
            "partition_hash": memory.partition_hash,
        },
        "free_dof_count": memory.free_dof_count,
        "rank_cap": memory.rank_cap,
        "active_teacher_count": memory.active_teacher_count,
        "accepted_teacher_count_total": memory.accepted_teacher_count_total,
        "evicted_teacher_count_total": memory.evicted_teacher_count_total,
        "chain_anchor_hash": memory.chain_anchor_hash,
        "rolling_teacher_chain_hash": memory.rolling_teacher_chain_hash,
        "provenance": [row.to_dict() for row in memory.provenance],
        "arrays": {
            "raw_modes": _array_descriptor("raw_modes", memory.raw_modes),
            "basis_q": _array_descriptor("basis_q", memory.basis_q),
        },
        "projection": projection_summary,
        "update_receipt": memory.update_receipt.to_dict(),
        "implementation_constraints": {
            "teacher_source": "validated_ready_linear_static_run_only",
            "physical_mode": (
                "(committed_displacement-initial_displacement)[free_dofs]"
            ),
            "eviction_policy": "deterministic_fifo",
            "basis_rebuild": "build_fixed_rank_projection",
            "reverse_mode_autograd": False,
            "gradient_updates": False,
            "legacy_training_imports": False,
        },
        "claim_boundary": "solver_approved_qr_correction_memory_not_training",
    }
    if include_memory_hash:
        payload["memory_hash"] = memory.memory_hash
    return payload


def _array_descriptor(name: str, array: np.ndarray) -> dict[str, Any]:
    metadata = {
        "name": name,
        "dtype": array.dtype.str,
        "shape": [int(value) for value in array.shape],
        "layout": "C",
        "byte_length": int(array.nbytes),
    }
    if array.size:
        data_hash = array_data_hash(array)
        content_hash = array_content_hash(metadata, array)
    else:
        raw = array.tobytes(order="C")
        data_hash = sha256_prefixed(raw)
        digest = hashlib.sha256()
        digest.update(canonical_json_bytes(metadata))
        digest.update(b"\0")
        digest.update(raw)
        content_hash = f"sha256:{digest.hexdigest()}"
    return {**metadata, "data_hash": data_hash, "content_hash": content_hash}


def _memory_hash(memory: FixedRankQRMemory) -> str:
    return canonical_hash(_memory_manifest(memory, include_memory_hash=False))


@lru_cache(maxsize=1)
def _schema_validator() -> Draft202012Validator:
    path = (
        Path(__file__).resolve().parents[2]
        / "schemas"
        / "fixed_rank_qr_memory_v1.schema.json"
    )
    schema = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _fail(code: str, path: str, message: str) -> None:
    raise QRMemoryError(code, path, message)


__all__ = [
    "FIXED_RANK_QR_MEMORY_ALGORITHM_VERSION",
    "FIXED_RANK_QR_MEMORY_SCHEMA_VERSION",
    "FixedRankQRMemory",
    "QRMemoryError",
    "QRMemoryUpdateReceipt",
    "QRTeacherProvenance",
    "create_fixed_rank_qr_memory",
    "update_fixed_rank_qr_memory_from_run",
    "validate_fixed_rank_qr_memory",
]
