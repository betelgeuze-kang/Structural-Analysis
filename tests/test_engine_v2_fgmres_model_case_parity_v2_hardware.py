"""Actual-gfx1030 high-load model-case parity v2 and ResultIR gate."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from structural_analysis.engine_v2.assembly_backend.fgmres_model_case_parity_v2 import (
    attest_hip_fgmres_model_case_parity_v2,
    validate_hip_fgmres_model_case_parity_result_v2,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_result_ir_v3 import (
    build_hip_fgmres_result_ir_v3,
    validate_hip_fgmres_result_ir_v3,
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
_REQUIRED_ENV = "ENGINE_V2_REQUIRE_FGMRES_MODEL_CASE_PARITY_V2_HARDWARE"
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
    / "src/structural_analysis/engine_v2/assembly_backend"
    / "fgmres_model_case_parity_v2.py",
    ROOT
    / "src/structural_analysis/engine_v2/assembly_backend"
    / "fgmres_result_ir_v2.py",
    ROOT
    / "src/structural_analysis/engine_v2/assembly_backend"
    / "fgmres_result_ir_v3.py",
    ROOT
    / "src/structural_analysis/schemas"
    / "fp64_csr_residual_normwise_v1.schema.json",
    ROOT
    / "src/structural_analysis/schemas"
    / "hip_fgmres_terminal_metric_parity_v2.schema.json",
    ROOT
    / "src/structural_analysis/schemas"
    / "hip_fgmres_model_case_parity_v2.schema.json",
    ROOT / "src/structural_analysis/schemas" / "hip_fgmres_result_ir_v3.schema.json",
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


def _attest_live_model_case_v2(
    cpu_result: Any,
    observation_result: Any,
    device_identity_result: Any,
) -> Any:
    case = attest_hip_fgmres_model_case_parity_v2(
        cpu_result,
        observation_result,
        device_identity_result,
    )
    assert validate_hip_fgmres_model_case_parity_result_v2(case) is case
    assert case.receipt.claims.actual_hip_backend_verified
    assert case.receipt.claims.terminal_normwise_metric_v2_verified
    assert case.receipt.claims.single_terminal_restart_true_residual_metric_v2_verified
    assert not case.receipt.claims.general_restart_history_metric_v2_verified
    assert not case.receipt.history.checkpoint_vector_roles_exported
    bridge = build_hip_fgmres_result_ir_v3(case)
    assert validate_hip_fgmres_result_ir_v3(bridge) is bridge
    assert bridge.receipt.claims.result_ir_v3_ready
    assert not bridge.base_result_ir_v2.claims.result_ir_ready
    assert bridge.base_result_ir_v2.source_provenance.case_id == case.receipt.case_id
    assert bridge.base_result_ir_v2.source_provenance.case_parity_receipt_hash == (
        case.receipt.receipt_hash
    )
    return SimpleNamespace(
        cpu_result=cpu_result,
        observation_result=observation_result,
        device_identity_result=device_identity_result,
        case=case,
        bridge=bridge,
    )


def test_native_gfx1030_high_load_model_case_parity_v2_and_result_ir() -> None:
    required = _hardware_required()
    architecture = _native_gfx1030(required)
    source_before = _source_aggregate()
    resources: list[Any] = []
    results: list[tuple[str, Any]] = []
    try:
        for specification in _HIGH_LOAD_CASES:
            slot = _high_load_slot(*specification)
            print(f"actual-gfx1030 model-case-v2 cell: {slot.slot_id}", flush=True)
            opened, result, audit_context, _ordinal_context = _execute_live_case(
                slot,
                architecture,
                required,
                parity_attestor=_attest_live_model_case_v2,
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
        assert validate_hip_fgmres_result_ir_v3(result.bridge) is result.bridge
        records = result.case.terminal_metric_parity.receipt.records
        history = result.case.receipt.history
        print(
            "actual-gfx1030 model-case-v2 result: "
            f"slot={slot_id} "
            f"case_id={result.case.receipt.case_id} "
            f"result_ir_v3_hash={result.bridge.receipt.receipt_hash} "
            f"base_result_ir_v2_hash={result.bridge.base_result_ir_v2.result_ir_hash} "
            f"estimated_ratio={history.estimated_residual.maximum_tolerance_ratio!r} "
            f"update_ratio={history.solution_update.maximum_tolerance_ratio!r} "
            + " ".join(
                f"{row.name}_ratio={row.maximum_bound_ratio!r}" for row in records
            ),
            flush=True,
        )
        assert all(row.record_difference_bound_passed for row in records)
        assert history.general_history_status == (
            "not_verified_missing_checkpoint_vectors_and_scalar_error_models"
        )
