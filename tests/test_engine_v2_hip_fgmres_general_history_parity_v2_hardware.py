"""Actual-gfx1030 multi-restart checkpoint history and parity gate."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

from structural_analysis.engine_v2.assembly_backend.fgmres_checkpoint_history_context_v1 import (
    open_hip_fgmres_checkpoint_history_context_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_completion_export_v2 import (
    open_hip_fgmres_completion_export_context_v2,
    validate_hip_fgmres_completion_export_result_v2,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_fixture_registry_v1 import (
    load_hip_fgmres_fixture_registry_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_general_history_parity_v2 import (
    attest_hip_fgmres_general_history_parity_v2,
    validate_hip_fgmres_general_history_parity_result_v2,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_global_recurrence_context_v1 import (
    open_hip_fgmres_global_recurrence_context_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_sealed_checkpoint_transaction_v1 import (
    open_hip_fgmres_sealed_checkpoint_transaction_context_v1,
)
from structural_analysis.engine_v2.solvers.cpu_fgmres import (
    solve_cpu_fgmres_checkpoint_history_v2,
)

from tests.test_engine_v2_hip_fgmres_sealed_checkpoint_transaction_hardware_v1 import (
    _native_gfx1030,
    _open_canonical_chain,
)


ROOT = Path(__file__).resolve().parents[1]
_REQUIRED_ENV = "ENGINE_V2_REQUIRE_FGMRES_GENERAL_HISTORY_PARITY_V2_HARDWARE"
_SOURCE_PATHS = (
    ROOT
    / "src/structural_analysis/engine_v2/assembly_backend"
    / "fgmres_checkpoint_history_plan_v1.py",
    ROOT
    / "src/structural_analysis/engine_v2/assembly_backend"
    / "fgmres_checkpoint_history_rtc_v1.py",
    ROOT
    / "src/structural_analysis/engine_v2/assembly_backend"
    / "fgmres_checkpoint_history_context_v1.py",
    ROOT
    / "src/structural_analysis/engine_v2/assembly_backend"
    / "fgmres_completion_export_v2.py",
    ROOT
    / "src/structural_analysis/engine_v2/assembly_backend"
    / "fgmres_general_history_parity_v2.py",
    ROOT
    / "src/structural_analysis/engine_v2/assembly_backend/kernels"
    / "engine_v2_fgmres_checkpoint_history_v1.hip.cpp",
    ROOT / "src/structural_analysis/engine_v2/solvers/cpu_fgmres.py",
    ROOT
    / "src/structural_analysis/schemas"
    / "hip_fgmres_checkpoint_history_plan_v1.schema.json",
    ROOT
    / "src/structural_analysis/schemas"
    / "cpu_fgmres_checkpoint_history_v2.schema.json",
    ROOT
    / "src/structural_analysis/schemas"
    / "hip_fgmres_checkpoint_history_context_v1.schema.json",
    ROOT
    / "src/structural_analysis/schemas"
    / "hip_fgmres_completion_export_v2.schema.json",
    ROOT
    / "src/structural_analysis/schemas"
    / "hip_fgmres_general_history_parity_v2.schema.json",
    Path(__file__).resolve(),
)


def _source_aggregate() -> str:
    digest = hashlib.sha256()
    for path in _SOURCE_PATHS:
        relative = path.relative_to(ROOT).as_posix().encode()
        payload = path.read_bytes()
        digest.update(len(relative).to_bytes(8, "little"))
        digest.update(relative)
        digest.update(len(payload).to_bytes(8, "little"))
        digest.update(payload)
    return "sha256:" + digest.hexdigest()


def _cleanup(resources: tuple[Any, ...]) -> None:
    errors: list[BaseException] = []
    for resource in resources:
        if resource is None:
            continue
        try:
            resource.close()
        except BaseException as exc:
            errors.append(exc)
    if errors:
        raise errors[0]


def test_native_gfx1030_general_multi_restart_history_v2() -> None:
    required = (
        os.environ.get("ENGINE_V2_REQUIRE_HIP_HARDWARE") == "1"
        or os.environ.get(_REQUIRED_ENV) == "1"
    )
    architecture = _native_gfx1030(required)
    slot = next(
        row
        for row in load_hip_fgmres_fixture_registry_v1().slots
        if row.slot_id == "recurrence_later_restart_partial_final_cycle"
    )
    source_before = _source_aggregate()
    chain = sealed = global_open = history_open = export_open = None
    try:
        chain, predecessor = _open_canonical_chain(
            model=slot.model,
            architecture=architecture,
            required=required,
            policy=slot.policy,
            load_pattern_id=slot.execution_plan.load_pattern_id,
        )
        sealed = open_hip_fgmres_sealed_checkpoint_transaction_context_v1(
            chain.canonical,
            predecessor,
        )
        sealed_pending = sealed.context.enqueue_sealed_checkpoint_transaction()
        continuation = sealed.context.synchronize_sealed_checkpoint_transaction(
            sealed_pending
        )
        global_open = open_hip_fgmres_global_recurrence_context_v1(
            sealed.context,
            continuation,
        )
        history_open = open_hip_fgmres_checkpoint_history_context_v1(
            global_open.context
        )
        global_pending = global_open.context.enqueue_remaining_global_recurrence()
        completion = global_open.context.synchronize(global_pending)
        export_open = open_hip_fgmres_completion_export_context_v2(
            global_open.context,
            completion,
            history_open.context,
        )
        exported = export_open.context.export()
        assert validate_hip_fgmres_completion_export_result_v2(exported) is exported
        cpu = solve_cpu_fgmres_checkpoint_history_v2(
            slot.execution_plan,
            slot.policy,
        )
        parity = attest_hip_fgmres_general_history_parity_v2(
            cpu,
            exported,
            expected_export_context=export_open.context,
        )
        assert validate_hip_fgmres_general_history_parity_result_v2(parity) is parity
        assert parity.receipt.dimensions.populated_restart_count == 3
        assert tuple(row.end_iteration for row in parity.receipt.rows) == (2, 4, 5)
        assert exported.receipt.telemetry.total_blocking_d2h_attempt_count == 5
        assert exported.receipt.telemetry.total_blocking_d2h_success_count == 5
        assert exported.receipt.telemetry.composite_fallback_count == 0
        history = exported.history_export.receipt.telemetry
        assert history.capture_launch_attempt_count == 6
        assert history.capture_launch_success_count == 6
        assert history.acknowledged_module_launch_count == 7
        assert history.recurrence_d2h_operation_count == 0
        assert all(
            row.solution.fixed_componentwise_gate_passed
            and row.true_residual_l2.bound_passed
            and row.estimated_residual_l2.bound_passed
            and row.solution_update_l2.bound_passed
            for row in parity.receipt.rows
        )
        print(
            "actual-gfx1030 general-history-v2: "
            f"parity_id={parity.receipt.parity_id} "
            f"receipt_hash={parity.receipt.receipt_hash} "
            f"completion_hash={exported.receipt.receipt_hash} "
            f"rows={parity.receipt.dimensions.populated_restart_count} "
            f"d2h={exported.receipt.telemetry.total_blocking_d2h_attempt_count}",
            flush=True,
        )
    finally:
        _cleanup(
            (
                export_open.context
                if export_open is not None
                else (history_open.context if history_open is not None else None),
                global_open.context if global_open is not None else None,
                sealed.context if sealed is not None else None,
                chain,
            )
        )
    assert export_open is not None
    assert export_open.context.receipt().status == "context_closed"
    assert export_open.context.receipt().to_dict()["reason"] is None
    assert export_open.context.receipt().telemetry.total_blocking_d2h_success_count == 5
    assert history_open is not None
    assert history_open.context.receipt().status == "context_closed"
    assert history_open.context.receipt().to_dict()["reason"] is None
    assert _source_aggregate() == source_before
