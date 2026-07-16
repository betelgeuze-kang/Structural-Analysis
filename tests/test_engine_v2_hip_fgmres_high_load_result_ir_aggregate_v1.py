from __future__ import annotations

import ast
import copy
from dataclasses import replace
import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator
import numpy as np
import pytest

from structural_analysis.engine_v2.assembly_backend import (
    fgmres_high_load_result_ir_aggregate_v1 as aggregate_module,
)
from structural_analysis.engine_v2.assembly_backend import (
    fgmres_result_ir_v3 as result_ir_v3,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_high_load_compatibility_registry_v1 import (
    HIP_FGMRES_HIGH_LOAD_COMPATIBILITY_REGISTRY_REQUIRED_SLOT_IDS_V1,
    load_hip_fgmres_high_load_compatibility_registry_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_model_case_terminal_metric_parity_v2 import (
    replay_hip_fgmres_detached_terminal_metric_parity_v2,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_terminal_outcome_observation_v1 import (
    HipFgmresTerminalOutcomeCountersV1,
    HipFgmresTerminalOutcomeMetricsV1,
    HipFgmresTerminalOutcomeV1,
)
from structural_analysis.engine_v2.contracts._canonical import sha256_prefixed
from structural_analysis.engine_v2.contracts.result_ir_v2 import (
    SourceProvenance,
    _build_result_ir_v2_unvalidated_physics,
)
from structural_analysis.engine_v2.contracts.state_ir import (
    commit_trial_state,
    create_initial_state,
    open_trial_state,
)
from structural_analysis.engine_v2.solvers.gpu_tree_reference_v2 import (
    fgmres_gpu_tree_l2_v2,
    fgmres_gpu_tree_linf_v2,
)


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = (
    ROOT
    / "src/structural_analysis/schemas"
    / "hip_fgmres_high_load_result_ir_aggregate_v1.schema.json"
)
MODULE = (
    ROOT
    / "src/structural_analysis/engine_v2/assembly_backend"
    / "fgmres_high_load_result_ir_aggregate_v1.py"
)


def _hash(label: str) -> str:
    return "sha256:" + hashlib.sha256(label.encode("utf-8")).hexdigest()


def _terminal_outcome(slot) -> tuple[bytes, bytes, HipFgmresTerminalOutcomeV1]:
    plan = slot.execution_plan
    cpu = slot.cpu_result
    solution = np.array(cpu.reduced_solution, dtype="<f8", order="C", copy=True)
    residual = np.array(cpu.true_residual, dtype="<f8", order="C", copy=True)
    solution[solution == 0.0] = 0.0
    residual[residual == 0.0] = 0.0
    free = plan.array("free_dofs").astype(np.int64, copy=False)
    rhs = plan.array("global_load")[free]
    residual_l2 = fgmres_gpu_tree_l2_v2(residual).value
    residual_linf = fgmres_gpu_tree_linf_v2(residual).value
    rhs_l2 = fgmres_gpu_tree_l2_v2(rhs).value
    rhs_linf = fgmres_gpu_tree_linf_v2(rhs).value
    solution_l2 = fgmres_gpu_tree_l2_v2(solution).value
    row = cpu.history[-1]
    metrics = HipFgmresTerminalOutcomeMetricsV1(
        rhs_l2=rhs_l2,
        rhs_linf=rhs_linf,
        solver_tolerance_l2=cpu.solver_tolerance_l2,
        authoritative_tolerance_scaled_linf=plan.residual_tolerance,
        initial_residual_l2=cpu.initial_residual_l2,
        final_residual_l2=residual_l2,
        final_residual_linf=residual_linf,
        final_scaled_residual=residual_linf / max(1.0, rhs_linf),
        previous_checkpoint_residual_l2=residual_l2,
        solution_update_l2=row.solution_update_l2,
        solution_scale_l2=solution_l2,
        estimated_residual_l2=row.estimated_residual_l2,
        arnoldi_work_l2=0.0,
        arnoldi_breakdown_threshold=0.0,
        triangular_scale=0.0,
    )
    counters = HipFgmresTerminalOutcomeCountersV1(
        scheduled_iterations=cpu.iteration_count,
        effective_iterations=cpu.iteration_count,
        scheduled_restarts=cpu.restart_count,
        effective_restarts=cpu.restart_count,
        effective_arnoldi_dimension=slot.policy.restart_dimension,
        happy_breakdown_count=0,
        stagnation_checkpoint_count=0,
        false_convergence_count=0,
        operator_apply_count=cpu.operator_apply_count,
        preconditioner_apply_count=cpu.preconditioner_apply_count,
        restart_dimension=slot.policy.restart_dimension,
    )
    outcome = HipFgmresTerminalOutcomeV1(
        outcome_class="converged",
        active=0,
        terminal_status=cpu.status,
        terminal_status_code=1,
        termination_code=cpu.termination_code,
        termination_code_value=2,
        device_error_bits=0,
        device_error_names=(),
        counters=counters,
        record_metrics_authoritative=True,
        metrics=metrics,
        restart_rows=(),
        solution_x_all_finite=True,
        true_residual_all_finite=True,
        observed_solution_x_l2=solution_l2,
        observed_true_residual_l2=residual_l2,
        observed_true_residual_linf=residual_linf,
        observed_true_residual_scaled_linf=(residual_linf / max(1.0, rhs_linf)),
        true_residual_record_metrics_match=True,
    )
    return solution.tobytes(order="C"), residual.tobytes(order="C"), outcome


def _mint_unit_test_result_v3(slot, index: int):
    """Mint only the private issuance boundary used by this unit test."""

    plan = slot.execution_plan
    cpu = slot.cpu_result
    solution_x, true_residual, outcome = _terminal_outcome(slot)
    terminal = replay_hip_fgmres_detached_terminal_metric_parity_v2(
        execution_plan=plan,
        cpu_result=cpu,
        solution_x=solution_x,
        true_residual=true_residual,
        outcome=outcome,
    )
    free = plan.array("free_dofs")
    constrained = plan.array("constrained_dofs")
    displacement = np.zeros(plan.dof_count, dtype="<f8")
    displacement[free] = np.frombuffer(solution_x, dtype="<f8")
    displacement[constrained] = 0.0
    initial = create_initial_state(plan)
    trial = open_trial_state(
        initial,
        displacement,
        load_step=1,
        iteration=cpu.iteration_count,
        load_factor=1.0,
        expected_plan=plan,
    )
    committed = commit_trial_state(initial, trial, expected_plan=plan)
    provenance = SourceProvenance(
        case_id=_hash(f"high-load-case-{index}"),
        case_parity_receipt_hash=_hash(f"high-load-case-receipt-{index}"),
        terminal_observation_receipt_hash=_hash(f"high-load-observation-{index}"),
        completion_export_receipt_hash=_hash(f"high-load-export-receipt-{index}"),
        completion_export_payload_hash=_hash(f"high-load-export-payload-{index}"),
        device_identity_receipt_hash=_hash(f"high-load-device-{index}"),
        solution_payload_sha256=sha256_prefixed(solution_x),
        exported_free_residual_payload_sha256=sha256_prefixed(true_residual),
        compiled_architecture="gfx1030",
        runtime_architecture_base="gfx1030",
        device_ordinal=0,
        device_uuid_bytes_hex=f"{index + 1:032x}",
        device_pci_bdf="0000:03:00.0",
    )
    base = _build_result_ir_v2_unvalidated_physics(
        plan,
        trial,
        committed,
        displacement,
        np.frombuffer(true_residual, dtype="<f8"),
        provenance,
        result_id=f"Result.synthetic-high-load-{index}.v2",
    )
    roundoff, witness = result_ir_v3._residual_chain_and_physics_witness(
        plan=plan,
        base=base,
        terminal=terminal,
        solution_x=solution_x,
        true_residual=true_residual,
        evaluated_trial_state=trial,
        committed_state=committed,
    )
    receipt = result_ir_v3._build_receipt(
        plan=plan,
        base=base,
        witness=witness,
        terminal=terminal,
        fsum_to_plan=roundoff,
        solution_x=solution_x,
        true_residual=true_residual,
    )
    token = object()
    result = result_ir_v3.HipFgmresResultIRResultV3(
        receipt=receipt,
        base_result_ir_v2=base,
        accepted_state=initial,
        evaluated_trial_state=trial,
        committed_state=committed,
        terminal_metric_parity=terminal,
        fsum_to_result_ir_plan_roundoff=roundoff,
        _source_execution_plan=plan,
        _source_solution_x=solution_x,
        _source_true_residual=true_residual,
        _source_case_identity_token=token,
    )
    issuance = result_ir_v3._HipFgmresResultIRIssuanceV3(
        receipt=receipt,
        result_ir_v2=base,
        accepted_state=initial,
        evaluated_trial_state=trial,
        committed_state=committed,
        terminal_metric_parity=terminal,
        fsum_to_plan_roundoff=roundoff,
        source_execution_plan=plan,
        source_solution_x=solution_x,
        source_true_residual=true_residual,
        source_case_identity_token=token,
    )
    with result_ir_v3._ISSUANCE_LOCK:
        result_ir_v3._ISSUANCES[result] = issuance
    return result_ir_v3.validate_hip_fgmres_result_ir_v3(result)


@pytest.fixture(scope="module")
def registry():
    return load_hip_fgmres_high_load_compatibility_registry_v1()


@pytest.fixture(scope="module")
def children(registry):
    return tuple(
        _mint_unit_test_result_v3(slot, index)
        for index, slot in enumerate(registry.slots)
    )


@pytest.fixture(scope="module")
def aggregate(children):
    return aggregate_module.attest_hip_fgmres_high_load_result_ir_aggregate_v1(
        tuple(reversed(children))
    )


def test_aggregate_canonicalizes_three_result_ir_v3_and_pins_exact_totals(
    aggregate,
) -> None:
    receipt = aggregate.receipt
    assert tuple(row.slot_id for row in receipt.observations) == (
        HIP_FGMRES_HIGH_LOAD_COMPATIBILITY_REGISTRY_REQUIRED_SLOT_IDS_V1
    )
    assert tuple(
        row.source_execution_plan.plan_hash for row in aggregate.result_ir_v3_children
    ) == tuple(row.execution_plan_hash for row in receipt.observations)
    assert (
        receipt.totals
        == aggregate_module.HipFgmresHighLoadResultIRAggregateTotalsV1(
            required_slot_count=3,
            result_ir_v3_ready_count=3,
            retained_base_result_ir_v2_ready_count=0,
            unique_result_ir_v3_count=3,
            committed_state_count=3,
            package_global_dof_count=78,
            package_element_count=10,
            package_free_dof_count=60,
            package_csr_nnz=1188,
            result_array_count=18,
            result_array_byte_count=3392,
            detached_completion_payload_count=6,
            detached_completion_payload_byte_count=960,
            aggregate_additional_device_operation_count=0,
            aggregate_additional_d2h_operation_count=0,
            aggregate_additional_solve_count=0,
            aggregate_additional_export_count=0,
            aggregate_fallback_count=0,
        )
    )
    assert receipt.claims.exact_three_original_scale_result_ir_v3_verified
    assert receipt.claims.retained_base_result_ir_v2_ready_count_zero
    assert not receipt.claims.general_restart_history_v2_verified
    assert not receipt.claims.commercial_ready


def test_aggregate_receipt_schema_and_public_result_replay(aggregate) -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    payload = aggregate.to_manifest()
    Draft202012Validator(schema).validate(payload)
    assert (
        aggregate_module.validate_hip_fgmres_high_load_result_ir_aggregate_result_v1(
            aggregate
        )
        is aggregate
    )
    assert (
        aggregate_module.validate_hip_fgmres_high_load_result_ir_aggregate_receipt_v1(
            aggregate.receipt
        )
        is aggregate.receipt
    )


def test_aggregate_rejects_duplicate_plan_and_unissued_clone(
    registry,
    children,
) -> None:
    with pytest.raises(
        aggregate_module.HipFgmresHighLoadResultIRAggregateV1Error
    ) as duplicate:
        aggregate_module._evaluate(
            registry,
            (children[0], children[0], children[2]),
        )
    assert duplicate.value.code == (
        "hip_fgmres_high_load_result_ir_aggregate_children_invalid"
    )

    clone = copy.copy(children[0])
    with pytest.raises(result_ir_v3.HipFgmresResultIRV3Error) as unissued:
        aggregate_module._evaluate(registry, (clone, children[1], children[2]))
    assert unissued.value.code == "hip_fgmres_result_ir_v3_issuance_unavailable"

    with pytest.raises(
        aggregate_module.HipFgmresHighLoadResultIRAggregateV1Error
    ) as distinct_duplicate:
        aggregate_module._evaluate(
            registry,
            (children[0], children[1], _mint_unit_test_result_v3(registry.slots[1], 9)),
        )
    assert distinct_duplicate.value.code == (
        "hip_fgmres_high_load_result_ir_aggregate_duplicate_child"
    )


def test_aggregate_direct_construction_and_issuance_transplant_fail_closed(
    aggregate,
    children,
) -> None:
    direct = aggregate_module.HipFgmresHighLoadResultIRAggregateResultV1(
        receipt=aggregate.receipt,
        _result_ir_v3_children=aggregate.result_ir_v3_children,
    )
    with pytest.raises(
        aggregate_module.HipFgmresHighLoadResultIRAggregateV1Error
    ) as unavailable:
        aggregate_module.validate_hip_fgmres_high_load_result_ir_aggregate_result_v1(
            direct
        )
    assert unavailable.value.code == (
        "hip_fgmres_high_load_result_ir_aggregate_issuance_unavailable"
    )

    second = aggregate_module.attest_hip_fgmres_high_load_result_ir_aggregate_v1(
        children
    )
    with aggregate_module._ISSUANCE_LOCK:
        first_issuance = aggregate_module._ISSUANCES[aggregate]
        aggregate_module._ISSUANCES[aggregate] = aggregate_module._ISSUANCES[second]
    try:
        with pytest.raises(
            aggregate_module.HipFgmresHighLoadResultIRAggregateV1Error
        ) as transplanted:
            aggregate_module.validate_hip_fgmres_high_load_result_ir_aggregate_result_v1(
                aggregate
            )
        assert transplanted.value.code == (
            "hip_fgmres_high_load_result_ir_aggregate_issuance_binding_mismatch"
        )
    finally:
        with aggregate_module._ISSUANCE_LOCK:
            aggregate_module._ISSUANCES[aggregate] = first_issuance


def test_aggregate_schema_rejects_reorder_unknown_and_claim_promotion(
    aggregate,
) -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    payload = aggregate_module._receipt_payload(aggregate.receipt, include_hash=True)
    unknown = copy.deepcopy(payload)
    unknown["serialized_provenance_authority"] = True
    promoted = copy.deepcopy(payload)
    promoted["claims"]["commercial_ready"] = True
    reordered = copy.deepcopy(payload)
    reordered["observations"] = list(reversed(reordered["observations"]))
    assert list(validator.iter_errors(unknown))
    assert list(validator.iter_errors(promoted))
    # The generic schema permits three structurally valid rows; semantic
    # validation owns canonical package order.
    assert not list(validator.iter_errors(reordered))
    forged = replace(
        aggregate.receipt,
        observations=tuple(reversed(aggregate.receipt.observations)),
    )
    with pytest.raises(
        aggregate_module.HipFgmresHighLoadResultIRAggregateV1Error
    ) as order:
        aggregate_module._validate_receipt_semantics(
            forged,
            load_hip_fgmres_high_load_compatibility_registry_v1(),
        )
    assert order.value.code == (
        "hip_fgmres_high_load_result_ir_aggregate_semantics_invalid"
    )


def test_aggregate_module_has_no_native_runtime_or_result_builder_calls() -> None:
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    calls = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert not any("runtime" in name or "hiprtc" in name for name in imports)
    assert {
        "build_hip_fgmres_result_ir_v3",
        "solve_cpu_fgmres_reference_v1",
        "open_hip_fgmres_global_recurrence_context_v1",
        "attest_hip_device_identity_v1",
    }.isdisjoint(calls)
    assert "_ISSUANCES" not in aggregate_module.__all__
    assert "_AggregateIssuanceV1" not in aggregate_module.__all__
