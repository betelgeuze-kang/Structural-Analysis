"""Actual-gfx1030 high-load terminal metric parity v2 gate."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from structural_analysis.engine_v2.assembly_backend.fgmres_model_case_terminal_metric_parity_v2 import (
    replay_hip_fgmres_detached_terminal_metric_parity_v2,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_terminal_outcome_observation_v1 import (
    validate_hip_fgmres_terminal_outcome_observation_result_v1,
)
from structural_analysis.engine_v2.backends.hip.device_identity_v1 import (
    validate_hip_device_identity_result_v1,
)

from tests.test_engine_v2_fp64_csr_residual_roundoff_v1_hardware import (
    _HIGH_LOAD_CASES,
    _high_load_slot,
)
from tests.test_engine_v2_hip_fgmres_model_family_parity_v2_hardware import (
    _attach_cleanup_failures,
    _execute_live_case,
)
from tests.test_engine_v2_hip_fgmres_sealed_checkpoint_transaction_hardware_v1 import (
    _native_gfx1030,
)


ROOT = Path(__file__).resolve().parents[1]
_REQUIRED_ENV = "ENGINE_V2_REQUIRE_FGMRES_TERMINAL_METRIC_PARITY_V2_HARDWARE"
_SOURCE_PATHS = (
    ROOT
    / "src/structural_analysis/engine_v2/contracts"
    / "fp64_csr_residual_roundoff_v1.py",
    ROOT
    / "src/structural_analysis/engine_v2/contracts"
    / "fp64_csr_residual_normwise_v1.py",
    ROOT
    / "src/structural_analysis/engine_v2/assembly_backend"
    / "fgmres_model_case_terminal_metric_parity_v2.py",
    ROOT
    / "src/structural_analysis/schemas"
    / "fp64_csr_residual_normwise_v1.schema.json",
    ROOT
    / "src/structural_analysis/schemas"
    / "hip_fgmres_terminal_metric_parity_v2.schema.json",
    Path(__file__).resolve(),
)


def _hardware_required() -> bool:
    return (
        os.environ.get("ENGINE_V2_REQUIRE_HIP_HARDWARE") == "1"
        or os.environ.get(_REQUIRED_ENV) == "1"
    )


def _source_aggregate() -> str:
    digest = hashlib.sha256()
    for path in _SOURCE_PATHS:
        relative = path.relative_to(ROOT).as_posix().encode("utf-8")
        payload = path.read_bytes()
        digest.update(len(relative).to_bytes(8, "little"))
        digest.update(relative)
        digest.update(len(payload).to_bytes(8, "little"))
        digest.update(payload)
    return "sha256:" + digest.hexdigest()


def _attest_live_terminal_metric_v2(
    cpu_result: Any,
    observation_result: Any,
    device_identity_result: Any,
) -> Any:
    export_result = observation_result._source_export_result
    export_context = observation_result._source_export_context
    validate_hip_fgmres_terminal_outcome_observation_result_v1(
        observation_result,
        expected_export_result=export_result,
        expected_export_context=export_context,
    )
    authority = export_context._model_case_parity_authority(export_result)
    plan = authority.source.source_execution_plan
    validate_hip_device_identity_result_v1(
        device_identity_result,
        expected_loaded_runtime=authority.source.loaded_runtime,
    )
    assert observation_result.receipt.actual_backend == "hip"
    assert export_result.receipt.actual_backend == "hip"
    assert device_identity_result.receipt.actual_backend == "hip"
    assert device_identity_result.receipt.architecture.runtime.base == "gfx1030"
    terminal = replay_hip_fgmres_detached_terminal_metric_parity_v2(
        execution_plan=plan,
        cpu_result=cpu_result,
        solution_x=bytes(export_result.solution_x),
        true_residual=bytes(export_result.true_residual),
        outcome=observation_result.outcome,
    )
    assert terminal.roundoff_replay.solution_comparison.componentwise_tolerance_passed
    assert terminal.receipt.summary.all_terminal_record_bounds_passed
    assert not terminal.receipt.claims.actual_backend_verified
    assert not terminal.receipt.claims.hardware_provenance_verified
    return SimpleNamespace(
        cpu_result=cpu_result,
        observation_result=observation_result,
        device_identity_result=device_identity_result,
        terminal=terminal,
    )


def test_native_gfx1030_high_load_terminal_metric_parity_v2() -> None:
    required = _hardware_required()
    architecture = _native_gfx1030(required)
    source_before = _source_aggregate()
    resources: list[Any] = []
    results: list[tuple[str, Any]] = []
    try:
        for specification in _HIGH_LOAD_CASES:
            slot = _high_load_slot(*specification)
            print(f"actual-gfx1030 terminal-metric-v2 cell: {slot.slot_id}", flush=True)
            opened, result, audit_context, _ordinal_context = _execute_live_case(
                slot,
                architecture,
                required,
                parity_attestor=_attest_live_terminal_metric_v2,
            )
            resources.append(opened)
            results.append((slot.slot_id, result))
            audit = audit_context.result
            assert audit is not None
            assert (
                audit.receipt.window.recurrence_program.d2h_blocking.attempt_count == 0
            )
            assert (
                audit.receipt.window.completion_export.d2h_blocking.attempt_count == 3
            )
            assert (
                audit.receipt.window.completion_export.d2h_blocking.failure_count == 0
            )
            assert audit.completion_export_result.receipt.telemetry.fallback_count == 0
    finally:
        cleanup_errors: list[BaseException] = []
        for opened in reversed(resources):
            try:
                opened.close()
            except BaseException as exc:
                cleanup_errors.append(exc)
        if cleanup_errors:
            first = cleanup_errors[0]
            _attach_cleanup_failures(first, cleanup_errors[1:])
            raise first

    assert len(results) == len(_HIGH_LOAD_CASES)
    assert _source_aggregate() == source_before
    for slot_id, result in results:
        records = result.terminal.receipt.records
        print(
            "actual-gfx1030 terminal-metric-v2 result: "
            f"slot={slot_id} "
            + " ".join(
                f"{row.name}_difference={row.absolute_record_difference_upper_bound!r} "
                f"{row.name}_bound={row.total_record_difference_upper_bound!r} "
                f"{row.name}_ratio={row.maximum_bound_ratio!r}"
                for row in records
            ),
            flush=True,
        )
        assert all(row.record_difference_bound_passed for row in records)
        assert all(row.maximum_bound_ratio <= 1.0 for row in records)
