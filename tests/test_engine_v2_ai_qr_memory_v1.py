from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, dataclass, replace
import json
from pathlib import Path
import sys

from jsonschema import Draft202012Validator
import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from structural_analysis.engine_v2.ai.projection import (  # noqa: E402
    _projection_hash,
    validate_fixed_rank_projection,
)
from structural_analysis.engine_v2.ai.qr_memory import (  # noqa: E402
    QRMemoryError,
    _memory_hash,
    _teacher_chain_root_from_memory,
    create_fixed_rank_qr_memory,
    update_fixed_rank_qr_memory_from_run,
    validate_fixed_rank_qr_memory,
)
from structural_analysis.engine_v2.buffers import (  # noqa: E402
    pack_solver_model_buffers,
)
from structural_analysis.engine_v2.contracts._canonical import (  # noqa: E402
    immutable_array,
)
from structural_analysis.engine_v2.contracts.execution_plan import (  # noqa: E402
    compile_execution_plan,
)
from structural_analysis.engine_v2.runner import (  # noqa: E402
    execute_linear_static_plan_v1,
)
from structural_analysis.model_ir import load_model_ir_v2  # noqa: E402

FIXTURE = REPO_ROOT / "tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json"
SCHEMA = (
    SRC_ROOT
    / "structural_analysis/schemas/fixed_rank_qr_memory_v1.schema.json"
)
SOURCE = SRC_ROOT / "structural_analysis/engine_v2/ai/qr_memory.py"


def _plan_and_run(
    load_pattern_id: str = "LC_WEAK",
    *,
    matrix_backend: str = "dense",
):
    buffers = pack_solver_model_buffers(
        load_model_ir_v2(FIXTURE), load_pattern_id=load_pattern_id
    )
    plan = compile_execution_plan(buffers, matrix_backend=matrix_backend)
    run = execute_linear_static_plan_v1(buffers, plan)
    return plan, run


def _rehash(memory):
    provisional = replace(memory, memory_hash="sha256:" + ("0" * 64))
    return replace(provisional, memory_hash=_memory_hash(provisional))


def test_empty_memory_is_valid_schema_bound_deterministic_and_immutable() -> None:
    plan, _run = _plan_and_run()
    first = create_fixed_rank_qr_memory(plan, rank_cap=4)
    second = create_fixed_rank_qr_memory(plan, rank_cap=4)
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))

    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(first.to_manifest())
    assert first.memory_hash == second.memory_hash
    assert first.to_manifest() == second.to_manifest()
    assert first.plan_hash == plan.plan_hash
    assert first.operator_hash == plan.operator_hash
    assert first.pattern_hash == plan.pattern_hash
    assert first.partition_hash == plan.partition_hash
    assert first.active_teacher_count == 0
    assert first.accepted_teacher_count_total == 0
    assert first.evicted_teacher_count_total == 0
    assert first.chain_anchor_hash == first.rolling_teacher_chain_hash
    assert first.provenance == ()
    assert first.projection is None
    assert first.raw_modes.shape == (len(plan.free_dofs), 0)
    assert first.basis_q.shape == (len(plan.free_dofs), 0)
    assert first.update_receipt.operation == "initialize"
    assert first.update_receipt.projection_rebuild_count == 0
    assert first.update_receipt.reverse_mode_autograd_call_count == 0
    assert first.update_receipt.gradient_update_count == 0
    validate_fixed_rank_qr_memory(first, expected_plan=plan)

    for array in (first.raw_modes, first.basis_q):
        assert array.dtype.str == "<f8"
        assert array.flags.c_contiguous
        assert not array.flags.writeable
        with pytest.raises(ValueError):
            array.setflags(write=True)


def test_update_uses_exact_committed_minus_initial_free_dof_teacher() -> None:
    plan, run = _plan_and_run()
    empty = create_fixed_rank_qr_memory(plan, rank_cap=4)

    memory = update_fixed_rank_qr_memory_from_run(empty, run)
    free = plan.array("free_dofs")
    expected_mode = (
        run.committed_state.displacement_si[free]
        - run.initial_state.displacement_si[free]
    )

    assert memory.active_teacher_count == 1
    assert memory.accepted_teacher_count_total == 1
    assert memory.evicted_teacher_count_total == 0
    np.testing.assert_array_equal(memory.raw_modes[:, 0], expected_mode)
    assert memory.projection is not None
    np.testing.assert_array_equal(
        memory.projection.candidate_vectors, memory.raw_modes
    )
    np.testing.assert_array_equal(memory.projection.basis_q, memory.basis_q)
    validate_fixed_rank_projection(memory.projection, expected_plan=plan)
    validate_fixed_rank_qr_memory(memory, expected_plan=plan)

    provenance = memory.provenance[0]
    assert provenance.sequence == 1
    assert provenance.receipt_chain_hash == run.receipt_chain_hash
    assert provenance.result_ir_hash == run.result_ir.result_ir_hash
    assert provenance.backend_native_result_hash == run.backend_result.result_hash
    assert provenance.initial_state_hash == run.initial_state.state_hash
    assert provenance.committed_state_hash == run.committed_state.state_hash
    assert provenance.solver_artifact_hash == run.buffers.artifact_hash
    assert provenance.previous_teacher_chain_hash == empty.rolling_teacher_chain_hash
    assert provenance.teacher_chain_hash == memory.rolling_teacher_chain_hash

    with pytest.raises(FrozenInstanceError):
        provenance.sequence = 2  # type: ignore[misc]
    for array in (memory.raw_modes, memory.basis_q):
        assert not array.flags.writeable
        with pytest.raises(ValueError):
            array.setflags(write=True)


def test_update_receipt_replays_exact_projection_and_no_backprop_counts() -> None:
    plan, run = _plan_and_run()
    memory = update_fixed_rank_qr_memory_from_run(
        create_fixed_rank_qr_memory(plan, rank_cap=3), run
    )
    assert memory.projection is not None
    receipt = memory.update_receipt
    complexity = memory.projection.complexity_receipt
    n = len(plan.free_dofs)

    assert receipt.operation == "append"
    assert receipt.previous_active_teacher_count == 0
    assert receipt.current_active_teacher_count == 1
    assert receipt.appended_teacher_count == 1
    assert receipt.evicted_teacher_count_this_update == 0
    assert receipt.fifo_retained_teacher_count == 0
    assert receipt.accepted_teacher_count_total == 1
    assert receipt.evicted_teacher_count_total == 0
    assert receipt.teacher_free_dof_subtraction_count == n
    assert receipt.projection_rebuild_count == 1
    assert receipt.projection_candidate_count == 1
    assert receipt.projection_retained_rank == memory.retained_rank
    assert (
        receipt.projection_basis_scaling_multiply_count
        == complexity.basis_scaling_multiply_count
    )
    assert (
        receipt.projection_orthogonalization_dot_count
        == complexity.orthogonalization_dot_count
    )
    assert (
        receipt.projection_orthogonalization_axpy_count
        == complexity.orthogonalization_axpy_count
    )
    assert (
        receipt.projection_normalization_divide_count
        == complexity.normalization_divide_count
    )
    assert receipt.raw_mode_elements == n
    assert receipt.basis_elements == n * memory.retained_rank
    assert receipt.max_dense_square_dimension <= memory.rank_cap
    assert receipt.reverse_mode_autograd_call_count == 0
    assert receipt.gradient_update_count == 0
    assert receipt.storage_complexity == "O(Nk)"
    assert receipt.rebuild_complexity == "O(Nk^2)"

    constraints = memory.to_manifest()["implementation_constraints"]
    assert constraints["teacher_source"] == "validated_ready_linear_static_run_only"
    assert constraints["eviction_policy"] == "deterministic_fifo"
    assert constraints["reverse_mode_autograd"] is False
    assert constraints["gradient_updates"] is False
    assert constraints["legacy_training_imports"] is False


def test_fifo_is_deterministic_and_chain_preserves_evicted_history_anchor() -> None:
    plan, run = _plan_and_run()

    def build_three():
        memory = create_fixed_rank_qr_memory(plan, rank_cap=2)
        first = update_fixed_rank_qr_memory_from_run(memory, run)
        second = update_fixed_rank_qr_memory_from_run(first, run)
        third = update_fixed_rank_qr_memory_from_run(second, run)
        return first, second, third

    first, _second, third = build_three()
    _repeat_first, _repeat_second, repeated = build_three()

    assert third.memory_hash == repeated.memory_hash
    np.testing.assert_array_equal(third.raw_modes, repeated.raw_modes)
    assert third.accepted_teacher_count_total == 3
    assert third.evicted_teacher_count_total == 1
    assert third.active_teacher_count == 2
    assert [row.sequence for row in third.provenance] == [2, 3]
    assert third.chain_anchor_hash == first.provenance[0].teacher_chain_hash
    assert (
        third.provenance[0].previous_teacher_chain_hash
        == third.chain_anchor_hash
    )
    assert (
        third.rolling_teacher_chain_hash
        == third.provenance[-1].teacher_chain_hash
    )
    receipt = third.update_receipt
    assert receipt.operation == "append_fifo_evict"
    assert receipt.previous_active_teacher_count == 2
    assert receipt.current_active_teacher_count == 2
    assert receipt.evicted_teacher_count_this_update == 1
    assert receipt.fifo_retained_teacher_count == 1
    assert receipt.evicted_teacher_count_total == 1
    # Repeated authoritative solves are dependent, but raw FIFO history remains 2.
    assert third.projection is not None
    assert third.projection.candidate_count == 2
    assert third.retained_rank == 1
    validate_fixed_rank_qr_memory(third, expected_plan=plan)


def test_different_plan_and_rehashed_binding_changes_are_rejected() -> None:
    plan, _run = _plan_and_run("LC_WEAK")
    _other_plan, other_run = _plan_and_run("LC_STRONG")
    memory = create_fixed_rank_qr_memory(plan, rank_cap=2)

    with pytest.raises(QRMemoryError) as mismatch:
        update_fixed_rank_qr_memory_from_run(memory, other_run)
    assert mismatch.value.code == "qr_memory_plan_binding_mismatch"

    for field in ("plan_hash", "operator_hash", "pattern_hash", "partition_hash"):
        forged = replace(memory, **{field: "sha256:" + ("1" * 64)})
        root = _teacher_chain_root_from_memory(forged)
        forged = replace(
            forged,
            chain_anchor_hash=root,
            rolling_teacher_chain_hash=root,
        )
        forged = _rehash(forged)
        with pytest.raises(QRMemoryError) as error:
            validate_fixed_rank_qr_memory(forged, expected_plan=plan)
        assert error.value.code == "qr_memory_plan_binding_mismatch"


def test_embedded_projection_binding_is_checked_without_external_plan() -> None:
    plan, run = _plan_and_run()
    memory = update_fixed_rank_qr_memory_from_run(
        create_fixed_rank_qr_memory(plan, rank_cap=2), run
    )
    assert memory.projection is not None
    provisional_projection = replace(
        memory.projection,
        plan_hash="sha256:" + ("2" * 64),
        projection_hash="sha256:" + ("0" * 64),
    )
    forged_projection = replace(
        provisional_projection,
        projection_hash=_projection_hash(provisional_projection),
    )
    forged = _rehash(replace(memory, projection=forged_projection))

    with pytest.raises(QRMemoryError) as error:
        validate_fixed_rank_qr_memory(forged)
    assert error.value.code == "qr_memory_projection_replay_mismatch"


def test_forged_run_and_trial_or_proposal_objects_cannot_be_teachers() -> None:
    plan, run = _plan_and_run()
    memory = create_fixed_rank_qr_memory(plan, rank_cap=2)
    forged_run = replace(run, receipt_chain_hash="sha256:" + ("0" * 64))

    with pytest.raises(QRMemoryError) as forged_error:
        update_fixed_rank_qr_memory_from_run(memory, forged_run)
    assert forged_error.value.code == "qr_memory_authoritative_run_invalid"

    with pytest.raises(QRMemoryError) as trial_error:
        update_fixed_rank_qr_memory_from_run(
            memory,
            run.evaluated_trial_state,  # type: ignore[arg-type]
        )
    assert trial_error.value.code == "qr_memory_authoritative_run_type_invalid"

    @dataclass(frozen=True)
    class RejectedProposal:
        status: str = "rejected"

    with pytest.raises(QRMemoryError) as proposal_error:
        update_fixed_rank_qr_memory_from_run(
            memory,
            RejectedProposal(),  # type: ignore[arg-type]
        )
    assert proposal_error.value.code == "qr_memory_authoritative_run_type_invalid"


def test_raw_basis_provenance_receipt_and_aggregate_tampering_fail_closed() -> None:
    plan, run = _plan_and_run()
    memory = update_fixed_rank_qr_memory_from_run(
        create_fixed_rank_qr_memory(plan, rank_cap=2), run
    )

    raw = memory.raw_modes.copy()
    raw[0, 0] += 1.0e-9
    with pytest.raises(QRMemoryError) as raw_error:
        validate_fixed_rank_qr_memory(
            replace(memory, raw_modes=immutable_array(raw, dtype="<f8"))
        )
    assert raw_error.value.code == "qr_memory_projection_replay_mismatch"

    basis = memory.basis_q.copy()
    basis[0, 0] += 1.0e-9
    with pytest.raises(QRMemoryError) as basis_error:
        validate_fixed_rank_qr_memory(
            replace(memory, basis_q=immutable_array(basis, dtype="<f8"))
        )
    assert basis_error.value.code == "qr_memory_projection_replay_mismatch"

    forged_row = replace(
        memory.provenance[0], result_ir_hash="sha256:" + ("3" * 64)
    )
    with pytest.raises(QRMemoryError) as provenance_error:
        validate_fixed_rank_qr_memory(replace(memory, provenance=(forged_row,)))
    assert provenance_error.value.code == "qr_memory_teacher_chain_invalid"

    forged_receipt = replace(
        memory.update_receipt,
        raw_mode_elements=memory.update_receipt.raw_mode_elements + 1,
    )
    with pytest.raises(QRMemoryError) as receipt_error:
        validate_fixed_rank_qr_memory(
            replace(memory, update_receipt=forged_receipt)
        )
    assert receipt_error.value.code == "qr_memory_update_receipt_mismatch"

    with pytest.raises(QRMemoryError) as hash_error:
        validate_fixed_rank_qr_memory(
            replace(memory, memory_hash="sha256:" + ("0" * 64))
        )
    assert hash_error.value.code == "qr_memory_hash_mismatch"


@pytest.mark.parametrize("rank_cap", [0, 17, True, 1.5])
def test_rank_cap_is_strictly_bounded(rank_cap: object) -> None:
    plan, _run = _plan_and_run()
    with pytest.raises(QRMemoryError) as error:
        create_fixed_rank_qr_memory(plan, rank_cap=rank_cap)  # type: ignore[arg-type]
    assert error.value.code == "qr_memory_rank_cap_invalid"


def test_qr_memory_module_has_no_ml_framework_or_legacy_imports() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".", 1)[0])

    assert not imported_roots.intersection(
        {"torch", "jax", "tensorflow", "autograd"}
    )
    assert "implementation.phase1" not in source
    assert "structural_analysis.ai" not in source
    assert "backward(" not in source
    assert "requires_grad" not in source
