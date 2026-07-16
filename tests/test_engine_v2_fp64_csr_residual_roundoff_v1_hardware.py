"""Actual-gfx1030 high-load residual roundoff gate for Engine v2."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from structural_analysis.engine_v2.assembly_backend.fgmres_all_converged_fixture_registry_v1 import (
    _policy_parameters,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_model_case_parity_v1 import (
    HIP_FGMRES_MODEL_CASE_PARITY_ABSOLUTE_TOLERANCE_V1,
    replay_hip_fgmres_detached_residual_roundoff_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_plan import (
    compile_hip_fgmres_plan_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_recurrence_plan_v2 import (
    compile_hip_fgmres_recurrence_plan_v2,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_terminal_outcome_observation_v1 import (
    validate_hip_fgmres_terminal_outcome_observation_result_v1,
)
from structural_analysis.engine_v2.assembly_backend.free_space_plan import (
    compile_hip_free_space_operator_plan_v1,
)
from structural_analysis.engine_v2.backends.hip.device_identity_v1 import (
    validate_hip_device_identity_result_v1,
)
from structural_analysis.engine_v2.buffers import pack_solver_model_buffers
from structural_analysis.engine_v2.contracts.execution_plan_v2 import (
    compile_execution_plan_v2,
)
from structural_analysis.engine_v2.solvers.cpu_fgmres import (
    compile_fgmres_policy_v1,
    solve_cpu_fgmres_reference_v1,
)
from structural_analysis.model_ir import parse_model_ir_v2

from tests.test_engine_v2_hip_fgmres_model_family_parity_v2_hardware import (
    _attach_cleanup_failures,
    _execute_live_case,
)
from tests.test_engine_v2_hip_fgmres_sealed_checkpoint_transaction_hardware_v1 import (
    _native_gfx1030,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = (
    ROOT
    / "src/structural_analysis/engine_v2/assembly_backend/fixtures"
    / "fgmres_all_converged_v1"
)
_REQUIRED_ENV = "ENGINE_V2_REQUIRE_FP64_CSR_RESIDUAL_ROUNDOFF_V1_HARDWARE"
_HIGH_LOAD_CASES = (
    (
        "solution_frame_single_rotated_axis_bending",
        "solution_frame_single_rotated_axis_bending.model.json",
        "FY",
        -10000.0,
    ),
    (
        "solution_frame_serial_four_span_axial",
        "solution_frame_serial_four_span_axial.model.json",
        "FX",
        100000.0,
    ),
    (
        "solution_frame_serial_five_span_axial",
        "solution_frame_serial_five_span_axial.model.json",
        "FX",
        100000.0,
    ),
)


def _hardware_required() -> bool:
    return (
        os.environ.get("ENGINE_V2_REQUIRE_HIP_HARDWARE") == "1"
        or os.environ.get(_REQUIRED_ENV) == "1"
    )


def _high_load_slot(
    slot_id: str,
    resource_name: str,
    component: str,
    load: float,
) -> Any:
    payload = json.loads((FIXTURE_DIR / resource_name).read_text(encoding="utf-8"))
    payload["load_patterns"][0]["nodal_loads"][0]["components_si"][component] = load
    source_ref = f"actual-gfx1030:fp64-csr-roundoff:{slot_id}:{float.hex(load)}"
    payload["provenance"]["source_ref"] = source_ref
    payload["provenance"]["source_sha256"] = (
        "sha256:" + hashlib.sha256(source_ref.encode("utf-8")).hexdigest()
    )
    model = parse_model_ir_v2(payload, require_analysis_ready=True)
    load_pattern_id = payload["load_patterns"][0]["id"]
    execution = compile_execution_plan_v2(
        pack_solver_model_buffers(model, load_pattern_id=load_pattern_id),
        residual_tolerance=1.0e-10,
    )
    parameters = _policy_parameters(slot_id)
    policy = compile_fgmres_policy_v1(**parameters)
    free_space = compile_hip_free_space_operator_plan_v1(execution)
    fgmres = compile_hip_fgmres_plan_v1(execution, free_space, policy)
    recurrence = compile_hip_fgmres_recurrence_plan_v2(fgmres)
    cpu = solve_cpu_fgmres_reference_v1(execution, policy)
    assert cpu.status == "converged"
    assert cpu.solver_tolerance_passed
    assert cpu.authoritative_plan_tolerance_passed
    return SimpleNamespace(
        slot_id=slot_id,
        model=model,
        execution_plan=execution,
        policy=policy,
        fgmres_plan=fgmres,
        recurrence_plan=recurrence,
        cpu_result=cpu,
    )


def _attest_live_roundoff_only(
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
    replay = replay_hip_fgmres_detached_residual_roundoff_v1(
        execution_plan=plan,
        cpu_result=cpu_result,
        solution_x=bytes(export_result.solution_x),
        true_residual=bytes(export_result.true_residual),
    )
    assert replay.solution_comparison.componentwise_tolerance_passed
    assert replay.cpu_reference_vs_candidate.receipt.summary.componentwise_bound_passed
    assert replay.candidate_vs_independent_replay.receipt.summary.componentwise_bound_passed
    assert not replay.cpu_reference_vs_candidate.receipt.claims.actual_backend_verified
    return SimpleNamespace(
        cpu_result=cpu_result,
        observation_result=observation_result,
        device_identity_result=device_identity_result,
        replay=replay,
    )


def test_native_gfx1030_high_load_residual_roundoff_contract() -> None:
    required = _hardware_required()
    architecture = _native_gfx1030(required)
    resources: list[Any] = []
    results: list[tuple[str, Any]] = []
    try:
        for specification in _HIGH_LOAD_CASES:
            slot = _high_load_slot(*specification)
            print(f"actual-gfx1030 roundoff cell: {slot.slot_id}", flush=True)
            opened, result, audit_context, _ordinal_context = _execute_live_case(
                slot,
                architecture,
                required,
                parity_attestor=_attest_live_roundoff_only,
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
    assert any(
        result.replay.cpu_reference_vs_candidate.receipt.summary.maximum_absolute_difference_upper_bound
        > HIP_FGMRES_MODEL_CASE_PARITY_ABSOLUTE_TOLERANCE_V1
        for _slot_id, result in results
    )
    for slot_id, result in results:
        cpu_vs_hip = result.replay.cpu_reference_vs_candidate.receipt.summary
        hip_vs_replay = result.replay.candidate_vs_independent_replay.receipt.summary
        print(
            "actual-gfx1030 roundoff result: "
            f"slot={slot_id} "
            f"cpu_hip_difference={cpu_vs_hip.maximum_absolute_difference_upper_bound!r} "
            f"cpu_hip_bound={cpu_vs_hip.componentwise_bound_linf!r} "
            f"cpu_hip_ratio={cpu_vs_hip.maximum_componentwise_bound_ratio!r} "
            f"cpu_backward_error={cpu_vs_hip.reference_componentwise_backward_error!r} "
            f"hip_backward_error={cpu_vs_hip.candidate_componentwise_backward_error!r} "
            f"hip_replay_difference={hip_vs_replay.maximum_absolute_difference_upper_bound!r} "
            f"hip_replay_bound={hip_vs_replay.componentwise_bound_linf!r} "
            f"hip_replay_ratio={hip_vs_replay.maximum_componentwise_bound_ratio!r}",
            flush=True,
        )
        assert cpu_vs_hip.maximum_componentwise_bound_ratio <= 1.0
        assert hip_vs_replay.maximum_componentwise_bound_ratio <= 1.0
        assert cpu_vs_hip.candidate_componentwise_backward_error < 1.0e-8
        assert hip_vs_replay.reference_componentwise_backward_error < 1.0e-8
