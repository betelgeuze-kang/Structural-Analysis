from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from structural_analysis.engine_v2.assembly_backend.fgmres_fixture_registry_v1 import (
    load_hip_fgmres_fixture_registry_v1,
)
from structural_analysis.engine_v2.solvers.cpu_fgmres import (
    CpuFgmresReferenceError,
    solve_cpu_fgmres_checkpoint_history_v2,
    validate_cpu_fgmres_checkpoint_history_result_v2,
)


@pytest.mark.parametrize(
    "slot_id",
    (
        "recurrence_initial_or_early_terminal",
        "recurrence_later_restart_partial_final_cycle",
        "recurrence_exact_full_final_cycle_guard",
    ),
)
def test_cpu_checkpoint_history_replays_fixture_restart_vectors(slot_id: str) -> None:
    registry = load_hip_fgmres_fixture_registry_v1()
    slot = next(row for row in registry.slots if row.slot_id == slot_id)
    result = solve_cpu_fgmres_checkpoint_history_v2(
        slot.execution_plan,
        slot.policy,
    )
    assert (
        validate_cpu_fgmres_checkpoint_history_result_v2(
            result,
            expected_plan=slot.execution_plan,
            expected_policy=slot.policy,
        )
        is result
    )
    assert result.base_result.result_hash == slot.cpu_result.result_hash
    assert len(result.checkpoints) == len(result.base_result.history)
    assert tuple(row.restart_index for row in result.checkpoints) == tuple(
        range(1, len(result.checkpoints) + 1)
    )
    assert all(
        row.solution.shape
        == row.true_residual.shape
        == (len(slot.execution_plan.free_dofs),)
        and not row.solution.flags.writeable
        and not row.true_residual.flags.writeable
        for row in result.checkpoints
    )


def test_cpu_checkpoint_history_multi_restart_update_matches_record() -> None:
    slot = next(
        row
        for row in load_hip_fgmres_fixture_registry_v1().slots
        if row.slot_id == "recurrence_later_restart_partial_final_cycle"
    )
    result = solve_cpu_fgmres_checkpoint_history_v2(
        slot.execution_plan,
        slot.policy,
    )
    assert len(result.checkpoints) == 3
    assert tuple(row.end_iteration for row in result.base_result.history) == (2, 4, 5)
    assert result.checkpoint_bundle_hash.startswith("sha256:")
    assert result.result_hash.startswith("sha256:")


def test_cpu_checkpoint_history_rejects_vector_and_hash_mutation() -> None:
    slot = next(
        row
        for row in load_hip_fgmres_fixture_registry_v1().slots
        if row.slot_id == "recurrence_later_restart_partial_final_cycle"
    )
    result = solve_cpu_fgmres_checkpoint_history_v2(
        slot.execution_plan,
        slot.policy,
    )
    first = result.checkpoints[0]
    changed = np.array(first.solution, copy=True)
    changed[0] = np.nextafter(changed[0], np.inf)
    changed.setflags(write=False)
    tampered_checkpoint = replace(first, solution=changed)
    with pytest.raises(CpuFgmresReferenceError):
        validate_cpu_fgmres_checkpoint_history_result_v2(
            replace(
                result,
                checkpoints=(tampered_checkpoint, *result.checkpoints[1:]),
            ),
            expected_plan=slot.execution_plan,
            expected_policy=slot.policy,
        )
    with pytest.raises(CpuFgmresReferenceError, match="hash_invalid"):
        validate_cpu_fgmres_checkpoint_history_result_v2(
            replace(result, result_hash="sha256:" + "0" * 64),
            expected_plan=slot.execution_plan,
            expected_policy=slot.policy,
        )
