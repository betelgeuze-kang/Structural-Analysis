from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import struct
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import numpy as np
import pytest

from structural_analysis.engine_v2.assembly_backend import (
    fgmres_external_release_identity_v1 as release_identity_module,
    fgmres_external_signed_evidence_v1 as evidence_module,
    fgmres_external_signed_evidence_v2 as evidence_v2_module,
    fgmres_model_case_parity_v1 as case_module,
    fgmres_model_family_parity_v2 as family_module,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_completion_export_v1 import (
    _bundle_hash,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_external_signed_evidence_v1 import (
    HIP_FGMRES_EXTERNAL_SIGNED_EVIDENCE_CAPABILITY_PROFILE_V1,
    HIP_FGMRES_EXTERNAL_SIGNED_EVIDENCE_SCHEMA_VERSION_V1,
    HIP_FGMRES_EXTERNAL_SIGNED_PAYLOAD_SCHEMA_VERSION_V1,
    HipFgmresExternalSignedEvidenceV1Error,
    compile_hip_fgmres_external_release_binding_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_external_trust_anchor_registry_v1 import (
    HipFgmresExternalTrustAnchorRegistryResultV1,
    HipFgmresExternalTrustAnchorV1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_fixture_registry_v1 import (
    HIP_FGMRES_FIXTURE_REGISTRY_REQUIRED_SLOT_IDS_V1,
    HIP_FGMRES_FIXTURE_REGISTRY_SUITE_ID_V1,
    load_hip_fgmres_fixture_registry_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_model_case_parity_v1 import (
    HIP_FGMRES_MODEL_CASE_PARITY_CAPABILITY_PROFILE_V1,
    HIP_FGMRES_MODEL_CASE_PARITY_EVIDENCE_SCOPE_V1,
    HIP_FGMRES_MODEL_CASE_PARITY_SCHEMA_VERSION_V1,
    HipFgmresModelCaseParityBindingsV1,
    HipFgmresModelCaseParityClaimsV1,
    HipFgmresModelCaseParityDimensionsV1,
    HipFgmresModelCaseParityDiscreteComparisonV1,
    HipFgmresModelCaseParityReceiptV1,
    HipFgmresModelCaseParityTelemetryV1,
    HipFgmresModelCaseParityToleranceV1,
    replay_hip_fgmres_detached_model_case_numerics_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_model_family_parity_v2 import (
    HIP_FGMRES_MODEL_FAMILY_PARITY_CAPABILITY_PROFILE_V2,
    HIP_FGMRES_MODEL_FAMILY_PARITY_EVIDENCE_SCOPE_V2,
    HIP_FGMRES_MODEL_FAMILY_PARITY_SCHEMA_VERSION_V2,
    HIP_FGMRES_MODEL_FAMILY_REQUIRED_ARCHITECTURE_BASES_V2,
    HipFgmresModelFamilyClaimsV2,
    HipFgmresModelFamilyCoverageV2,
    HipFgmresModelFamilyObservedCellV2,
    HipFgmresModelFamilyParityReceiptV2,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_recurrence_plan_v2 import (
    HIP_FGMRES_RECURRENCE_ABI_VERSION_V2,
    hip_fgmres_recurrence_kernel_abi_payload_v2,
    hip_fgmres_solve_record_abi_payload_v2,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_terminal_outcome_observation_v1 import (
    HipFgmresTerminalOutcomePolicySnapshotV1,
    decode_hip_fgmres_detached_completion_payload_v1,
)
from structural_analysis.engine_v2.contracts._canonical import (
    canonical_hash,
    canonical_json_bytes,
    sha256_prefixed,
)
from structural_analysis.engine_v2.solvers.gpu_tree_reference_v2 import (
    fgmres_gpu_tree_l2_v2,
    fgmres_gpu_tree_linf_v2,
)


_HASH = "sha256:" + "1" * 64
_ABI = hip_fgmres_solve_record_abi_payload_v2()
_KERNEL_ABI = hip_fgmres_recurrence_kernel_abi_payload_v2()
_HEADER_BYTES = 192
_RESTART_BYTES = 72
_SQRT_EPSILON = float.fromhex("0x1p-26")
_BREAKDOWN_TAU = float.fromhex("0x1p-46")


def _hash(label: str) -> str:
    return canonical_hash({"test_label": label})


def _descriptor(name: str, *, restart: bool) -> dict[str, Any]:
    key = "restart_fields" if restart else "header_fields"
    return next(row for row in _ABI[key] if row["name"] == name)


def _write_field(
    payload: bytearray,
    name: str,
    value: int | float,
    *,
    restart_index: int | None = None,
) -> None:
    descriptor = _descriptor(name, restart=restart_index is not None)
    base = (
        0 if restart_index is None else _HEADER_BYTES + restart_index * _RESTART_BYTES
    )
    format_code = "<i" if descriptor["dtype"] == "i32" else "<d"
    struct.pack_into(format_code, payload, base + descriptor["offset_bytes"], value)


def _flag(*names: str) -> int:
    bits = _ABI["restart_flag_bits"]
    return sum(1 << int(bits[name]) for name in names)


def _policy_snapshot(slot: Any) -> HipFgmresTerminalOutcomePolicySnapshotV1:
    policy = slot.policy
    return HipFgmresTerminalOutcomePolicySnapshotV1(
        restart_dimension=policy.restart_dimension,
        max_iterations=policy.max_iterations,
        maximum_restart_count=slot.recurrence_plan.maximum_restart_count,
        stagnation_checkpoint_limit=policy.stagnation_checkpoint_limit,
        absolute_tolerance=policy.absolute_tolerance,
        relative_tolerance=policy.relative_tolerance,
        authoritative_tolerance=slot.execution_plan.residual_tolerance,
        stagnation_relative_tolerance=policy.stagnation_relative_tolerance,
        divergence_factor=policy.divergence_factor,
    )


def _terminal_payloads(slot: Any) -> tuple[bytes, bytes, bytes]:
    cpu = slot.cpu_result
    plan = slot.execution_plan
    policy = _policy_snapshot(slot)
    solution = bytes(cpu.reduced_solution.tobytes(order="C"))
    residual = bytes(cpu.true_residual.tobytes(order="C"))
    rhs = plan.array("global_load")[plan.array("free_dofs").astype(np.int64)]
    rhs_l2 = fgmres_gpu_tree_l2_v2(rhs).value
    rhs_linf = fgmres_gpu_tree_linf_v2(rhs).value
    residual_array = np.frombuffer(residual, dtype="<f8")
    final_l2 = fgmres_gpu_tree_l2_v2(residual_array).value
    final_linf = fgmres_gpu_tree_linf_v2(residual_array).value
    final_scaled = final_linf / max(1.0, rhs_linf)
    solver_tolerance = max(
        policy.absolute_tolerance,
        policy.relative_tolerance * rhs_l2,
    )
    initial_terminal = cpu.termination_code == "converged_initial_true_residual"
    max_iterations = cpu.termination_code == "max_iterations_exhausted"
    positive_updates = [
        row.solution_update_l2 for row in cpu.history if row.solution_update_l2 > 0.0
    ]
    solution_scale = (
        min(positive_updates) / (2.0 * _SQRT_EPSILON)
        if max_iterations and positive_updates
        else 0.0
    )
    rows: list[dict[str, int | float]] = []
    previous_checkpoint = cpu.initial_residual_l2
    stagnation_count = 0
    for index, cpu_row in enumerate(cpu.history):
        final = index == len(cpu.history) - 1
        row_l2 = final_l2 if final else cpu_row.true_residual_l2
        row_linf = final_linf if final else cpu_row.true_residual_linf
        row_scaled = row_linf / max(1.0, rhs_linf)
        flags = _flag("true_residual_replayed")
        if row_l2 <= solver_tolerance:
            flags |= _flag("solver_l2_passed")
        if row_scaled <= policy.authoritative_tolerance:
            flags |= _flag("authoritative_linf_passed")
        if final and cpu.termination_code == "converged_happy_breakdown":
            flags |= _flag("happy_breakdown")
        if max_iterations:
            plateau = row_l2 >= (
                (1.0 - policy.stagnation_relative_tolerance) * previous_checkpoint
            )
            tiny = cpu_row.solution_update_l2 <= _SQRT_EPSILON * solution_scale
            if plateau:
                flags |= _flag("stagnation_plateau")
            if tiny:
                flags |= _flag("tiny_update")
            stagnation_count = stagnation_count + 1 if plateau and tiny else 0
            previous_checkpoint = row_l2
        rows.append(
            {
                "restart_index": cpu_row.restart_index,
                "start_iteration": cpu_row.start_iteration,
                "end_iteration": cpu_row.end_iteration,
                "arnoldi_step_count": cpu_row.arnoldi_step_count,
                "reorthogonalization_count": cpu_row.reorthogonalization_count,
                "termination_hint": _ABI["restart_hint_codes"][
                    cpu_row.termination_hint
                ],
                "flags": flags,
                "reserved_i32_0": 0,
                "estimated_residual_l2": cpu_row.estimated_residual_l2,
                "true_residual_l2": row_l2,
                "true_residual_linf": row_linf,
                "scaled_true_residual": row_scaled,
                "solution_update_l2": cpu_row.solution_update_l2,
            }
        )
    last = rows[-1] if rows else None
    effective_dimension = 0 if last is None else int(last["arnoldi_step_count"])
    previous_metric = (
        final_l2
        if max_iterations
        else (final_l2 if initial_terminal else cpu.initial_residual_l2)
    )
    estimated_metric = (
        final_l2 if initial_terminal else float(last["estimated_residual_l2"])
    )
    update_metric = 0.0 if last is None else float(last["solution_update_l2"])
    work_l2 = 0.0 if initial_terminal else 1.0
    header: dict[str, int | float] = {
        "recurrence_abi_version": HIP_FGMRES_RECURRENCE_ABI_VERSION_V2,
        "active": 0,
        "terminal_status": _ABI["terminal_status_codes"][cpu.status],
        "termination_code": _ABI["termination_codes"][cpu.termination_code],
        "device_error_bits": 0,
        "scheduled_iterations": policy.max_iterations,
        "effective_iterations": cpu.iteration_count,
        "scheduled_restarts": policy.maximum_restart_count,
        "effective_restarts": cpu.restart_count,
        "effective_arnoldi_dimension": effective_dimension,
        "happy_breakdown_count": int(
            cpu.termination_code == "converged_happy_breakdown"
        ),
        "stagnation_checkpoint_count": stagnation_count,
        "false_convergence_count": 0,
        "operator_apply_count": cpu.operator_apply_count,
        "preconditioner_apply_count": cpu.preconditioner_apply_count,
        "restart_dimension": policy.restart_dimension,
        "rhs_l2": rhs_l2,
        "rhs_linf": rhs_linf,
        "solver_tolerance_l2": solver_tolerance,
        "authoritative_tolerance_scaled_linf": policy.authoritative_tolerance,
        "initial_residual_l2": cpu.initial_residual_l2,
        "final_residual_l2": final_l2,
        "final_residual_linf": final_linf,
        "final_scaled_residual": final_scaled,
        "previous_checkpoint_residual_l2": previous_metric,
        "solution_update_l2": update_metric,
        "solution_scale_l2": solution_scale,
        "estimated_residual_l2": estimated_metric,
        "arnoldi_work_l2": work_l2,
        "arnoldi_breakdown_threshold": _BREAKDOWN_TAU * work_l2,
        "triangular_scale": 0.0 if initial_terminal else 1.0,
        "reserved_f64_0": 0.0,
    }
    record = bytearray(_HEADER_BYTES + _RESTART_BYTES * policy.maximum_restart_count)
    for name, value in header.items():
        _write_field(record, name, value)
    for index, row in enumerate(rows):
        for name, value in row.items():
            _write_field(record, name, value, restart_index=index)
    decoded = decode_hip_fgmres_detached_completion_payload_v1(
        solution_x=solution,
        true_residual=residual,
        solve_record=bytes(record),
        free_dof_count=int(plan.array("free_dofs").size),
        maximum_restart_count=policy.maximum_restart_count,
        policy=policy,
    )
    assert decoded.terminal_status == cpu.status
    return solution, residual, bytes(record)


def _discrete() -> HipFgmresModelCaseParityDiscreteComparisonV1:
    return HipFgmresModelCaseParityDiscreteComparisonV1(
        terminal_status_match=True,
        termination_code_match=True,
        iteration_count_match=True,
        restart_count_match=True,
        operator_apply_count_match=True,
        preconditioner_apply_count_match=True,
        restart_history_shape_match=True,
        restart_history_discrete_fields_match=True,
        restart_history_metrics_within_tolerance=True,
        terminal_metrics_within_tolerance=True,
        numerical_failure_absent=True,
    )


def _case_receipt(
    slot: Any,
    runner: dict[str, Any],
    payloads: tuple[bytes, bytes, bytes],
) -> HipFgmresModelCaseParityReceiptV1:
    solution, residual, record = payloads
    completion_hash = _bundle_hash(payloads)
    policy_snapshot = _policy_snapshot(slot)
    outcome = decode_hip_fgmres_detached_completion_payload_v1(
        solution_x=solution,
        true_residual=residual,
        solve_record=record,
        free_dof_count=int(slot.execution_plan.array("free_dofs").size),
        maximum_restart_count=policy_snapshot.maximum_restart_count,
        policy=policy_snapshot,
    )
    vectors = replay_hip_fgmres_detached_model_case_numerics_v1(
        execution_plan=slot.execution_plan,
        cpu_result=slot.cpu_result,
        solution_x=solution,
        true_residual=residual,
        outcome=outcome,
    )
    plan = slot.execution_plan
    bindings = HipFgmresModelCaseParityBindingsV1(
        model_ir_content_hash=slot.model.content_hash,
        execution_plan_id=plan.plan_id,
        execution_plan_hash=plan.plan_hash,
        operator_hash=plan.operator_hash,
        numeric_snapshot_hash=plan.numeric_snapshot_hash,
        symbolic_reuse_hash=plan.symbolic_reuse_hash,
        partition_hash=plan.partition_hash,
        load_pattern_id=plan.load_pattern_id,
        fgmres_plan_id=slot.fgmres_plan.plan_id,
        fgmres_plan_hash=slot.fgmres_plan.plan_hash,
        recurrence_plan_id=slot.recurrence_plan.plan_id,
        recurrence_plan_hash=slot.recurrence_plan.plan_hash,
        policy_hash=slot.policy.policy_hash,
        terminal_observation_id=_hash(f"terminal-id:{slot.slot_id}"),
        terminal_observation_receipt_hash=_hash(f"terminal-receipt:{slot.slot_id}"),
        terminal_outcome_hash=_hash(f"outcome:{slot.slot_id}"),
        completion_export_context_id=_hash(f"completion-id:{slot.slot_id}"),
        completion_export_receipt_hash=_hash(f"completion-receipt:{slot.slot_id}"),
        completion_export_payload_hash=completion_hash,
        global_context_id=_hash(f"global-id:{slot.slot_id}"),
        global_receipt_hash=_hash(f"global-receipt:{slot.slot_id}"),
        kernel_identity_hash=runner["kernel_identity_hash"],
        kernel_source_sha256=runner["kernel_source_sha256"],
        compiled_architecture=runner["compiled_architecture"],
        runtime_architecture_base="gfx1100",
        device_ordinal=runner["device_ordinal"],
        device_identity_receipt_hash=_hash("device-identity-receipt"),
        runtime_library_sha256=runner["runtime_library_sha256"],
        device_uuid_bytes_hex=runner["device_uuid_bytes_hex"],
        device_pci_bdf=runner["device_pci_bdf"],
        cpu_result_hash=slot.cpu_result.result_hash,
    )
    case_id = canonical_hash(
        {
            "profile": HIP_FGMRES_MODEL_CASE_PARITY_CAPABILITY_PROFILE_V1,
            "execution_plan_hash": bindings.execution_plan_hash,
            "policy_hash": bindings.policy_hash,
            "terminal_observation_receipt_hash": (
                bindings.terminal_observation_receipt_hash
            ),
            "device_identity_receipt_hash": bindings.device_identity_receipt_hash,
        }
    )
    draft = HipFgmresModelCaseParityReceiptV1(
        schema_version=HIP_FGMRES_MODEL_CASE_PARITY_SCHEMA_VERSION_V1,
        capability_profile=HIP_FGMRES_MODEL_CASE_PARITY_CAPABILITY_PROFILE_V1,
        status="case_parity_verified",
        evidence_scope=HIP_FGMRES_MODEL_CASE_PARITY_EVIDENCE_SCOPE_V1,
        actual_backend="hip",
        promotion_eligible=False,
        case_id=case_id,
        bindings=bindings,
        dimensions=HipFgmresModelCaseParityDimensionsV1(
            global_dof_count=plan.dof_count,
            free_dof_count=int(plan.array("free_dofs").size),
            reduced_csr_nnz=plan.reduced_nnz,
            restart_dimension=slot.policy.restart_dimension,
            max_iterations=slot.policy.max_iterations,
            maximum_restart_count=slot.recurrence_plan.maximum_restart_count,
            populated_restart_row_count=len(slot.cpu_result.history),
        ),
        tolerance=HipFgmresModelCaseParityToleranceV1(),
        discrete=_discrete(),
        vectors=vectors,
        telemetry=HipFgmresModelCaseParityTelemetryV1(),
        claims=HipFgmresModelCaseParityClaimsV1(),
        receipt_hash="sha256:" + "0" * 64,
    )
    return replace(
        draft,
        receipt_hash=canonical_hash(
            case_module._receipt_payload(draft, include_hash=False)
        ),
    )


def _family_receipt(
    registry: Any,
    runner: dict[str, Any],
    receipts: tuple[HipFgmresModelCaseParityReceiptV1, ...],
) -> HipFgmresModelFamilyParityReceiptV2:
    observations = []
    for slot, receipt in zip(registry.slots, receipts, strict=True):
        logical_case_key = canonical_hash(
            {
                "registry_hash": registry.registry_hash,
                "slot_registration_hash": slot.slot_registration_hash,
                "slot_id": slot.slot_id,
                "descriptor_hash": slot.descriptor.descriptor_hash,
                "execution_plan_hash": slot.execution_plan.plan_hash,
                "fgmres_plan_hash": slot.fgmres_plan.plan_hash,
                "recurrence_plan_hash": slot.recurrence_plan.plan_hash,
                "policy_hash": slot.policy.policy_hash,
                "cpu_result_hash": slot.cpu_result.result_hash,
            }
        )
        matrix_cell_id = canonical_hash(
            {
                "logical_case_key": logical_case_key,
                "runtime_architecture_base": "gfx1100",
                "device_identity_receipt_hash": (
                    receipt.bindings.device_identity_receipt_hash
                ),
                "case_receipt_hash": receipt.receipt_hash,
            }
        )
        observations.append(
            HipFgmresModelFamilyObservedCellV2(
                slot_id=slot.slot_id,
                runtime_architecture_base="gfx1100",
                compiled_architecture=runner["compiled_architecture"],
                device_ordinal=runner["device_ordinal"],
                device_uuid_bytes_hex=runner["device_uuid_bytes_hex"],
                device_pci_bdf=runner["device_pci_bdf"],
                runtime_library_sha256=runner["runtime_library_sha256"],
                kernel_identity_hash=runner["kernel_identity_hash"],
                kernel_source_sha256=runner["kernel_source_sha256"],
                case_id=receipt.case_id,
                case_receipt_hash=receipt.receipt_hash,
                device_identity_receipt_hash=(
                    receipt.bindings.device_identity_receipt_hash
                ),
                model_ir_content_hash=slot.model.content_hash,
                execution_plan_hash=slot.execution_plan.plan_hash,
                fgmres_plan_hash=slot.fgmres_plan.plan_hash,
                recurrence_plan_hash=slot.recurrence_plan.plan_hash,
                policy_hash=slot.policy.policy_hash,
                cpu_result_hash=slot.cpu_result.result_hash,
                descriptor_hash=slot.descriptor.descriptor_hash,
                slot_registration_hash=slot.slot_registration_hash,
                case_fingerprint=slot.case_fingerprint,
                logical_case_key=logical_case_key,
                matrix_cell_id=matrix_cell_id,
            )
        )
    covered = tuple(
        f"gfx1100:{slot_id}"
        for slot_id in HIP_FGMRES_FIXTURE_REGISTRY_REQUIRED_SLOT_IDS_V1
    )
    missing = tuple(
        f"gfx1030:{slot_id}"
        for slot_id in HIP_FGMRES_FIXTURE_REGISTRY_REQUIRED_SLOT_IDS_V1
    )
    draft = HipFgmresModelFamilyParityReceiptV2(
        schema_version=HIP_FGMRES_MODEL_FAMILY_PARITY_SCHEMA_VERSION_V2,
        capability_profile=HIP_FGMRES_MODEL_FAMILY_PARITY_CAPABILITY_PROFILE_V2,
        status="partial_fixed_suite_hardware_observation",
        evidence_scope=HIP_FGMRES_MODEL_FAMILY_PARITY_EVIDENCE_SCOPE_V2,
        registry_bytes_sha256=registry.registry_bytes_sha256,
        registry_hash=registry.registry_hash,
        required_architecture_bases=(
            HIP_FGMRES_MODEL_FAMILY_REQUIRED_ARCHITECTURE_BASES_V2
        ),
        required_slot_ids=HIP_FGMRES_FIXTURE_REGISTRY_REQUIRED_SLOT_IDS_V1,
        observations=tuple(observations),
        coverage=HipFgmresModelFamilyCoverageV2(
            required_slot_count=10,
            required_architecture_count=2,
            expected_matrix_cell_count=20,
            validated_input_case_count=10,
            covered_matrix_cell_count=10,
            missing_matrix_cell_count=10,
            covered_cells=covered,
            missing_cells=missing,
            observed_architecture_bases=("gfx1100",),
            completed_architecture_bases=("gfx1100",),
            incomplete_architecture_bases=("gfx1030",),
        ),
        claims=HipFgmresModelFamilyClaimsV2(),
        promotion_eligible=False,
        receipt_hash="sha256:" + "0" * 64,
    )
    return replace(
        draft,
        receipt_hash=canonical_hash(
            family_module._receipt_payload(draft, include_hash=False)
        ),
    )


@pytest.fixture(scope="module")
def evidence_material() -> dict[str, Any]:
    registry = load_hip_fgmres_fixture_registry_v1()
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    key_id = "ed25519:external-runner:v1"
    trust_key = HipFgmresExternalTrustAnchorV1(
        key_id=key_id,
        key_epoch=1,
        status="active",
        runner_id="external-runner",
        public_key_base64=base64.b64encode(public_key).decode("ascii"),
        public_key_sha256=sha256_prefixed(public_key),
        allowed_architecture_base="gfx1100",
        allowed_suite_id=HIP_FGMRES_FIXTURE_REGISTRY_SUITE_ID_V1,
        allowed_fixture_registry_bytes_sha256=registry.registry_bytes_sha256,
        allowed_fixture_registry_hash=registry.registry_hash,
        minimum_run_sequence=1,
        maximum_run_sequence=10,
        valid_from_utc="2026-01-01T00:00:00Z",
        valid_until_utc="2027-01-01T00:00:00Z",
        revoked_at_utc=None,
        revocation_reason=None,
    )
    trust_registry = HipFgmresExternalTrustAnchorRegistryResultV1(
        registry_bytes_sha256=_hash("synthetic-trust-registry-bytes"),
        registry_hash=_hash("synthetic-trust-registry"),
        registry_epoch=1,
        keys=(trust_key,),
        receipt_hash=_hash("synthetic-trust-registry-receipt"),
    )
    release = compile_hip_fgmres_external_release_binding_v1(
        wheel_filename="structural_optimization_workbench-1.0.0-py3-none-any.whl",
        wheel_byte_count=123456,
        wheel_sha256=_hash("candidate-wheel"),
        wheel_record_sha256=_hash("candidate-wheel-record"),
        source_commit="a" * 40,
        source_tree_sha256=_hash("source-tree"),
        source_bundle_sha256=_hash("source-bundle"),
        runner_source_sha256=_hash("runner-source"),
        build_recipe_sha256=_hash("build-recipe"),
        dependency_lock_sha256=_hash("dependency-lock"),
    )
    runner = {
        "runner_id": "external-runner",
        "run_sequence": 1,
        "runner_nonce_base64": base64.b64encode(b"R" * 32).decode("ascii"),
        "started_at_utc": "2026-07-14T00:00:01.000000Z",
        "completed_at_utc": "2026-07-14T00:00:02.000000Z",
        "architecture_base": "gfx1100",
        "compiled_architecture": "gfx1100",
        "device_ordinal": 0,
        "device_uuid_bytes_hex": "02" * 16,
        "device_pci_bdf": "0000:0c:00.0",
        "device_name": "synthetic-test-gfx1100",
        "rocm_version": "test-rocm",
        "driver_version": "test-driver",
        "hiprtc_version": "test-hiprtc",
        "runtime_library_sha256": _hash("runtime-library"),
        "runtime_dependency_manifest_hash": _hash("runtime-dependencies"),
        "kernel_identity_hash": _hash("kernel-identity"),
        "kernel_source_sha256": _hash("kernel-source"),
        "kernel_code_object_sha256": _hash("kernel-code-object"),
    }
    payloads = tuple(_terminal_payloads(slot) for slot in registry.slots)
    receipts = tuple(
        _case_receipt(slot, runner, raw)
        for slot, raw in zip(registry.slots, payloads, strict=True)
    )
    family = _family_receipt(registry, runner, receipts)
    cases = []
    for slot, raw, receipt in zip(registry.slots, payloads, receipts, strict=True):
        row = {
            "slot_id": slot.slot_id,
            "slot_registration_hash": slot.slot_registration_hash,
            "model_case_receipt_v1": receipt.to_dict(),
            "solution_x_base64": base64.b64encode(raw[0]).decode("ascii"),
            "true_residual_base64": base64.b64encode(raw[1]).decode("ascii"),
            "solve_record_base64": base64.b64encode(raw[2]).decode("ascii"),
            "completion_payload_hash": _bundle_hash(raw),
        }
        row["case_evidence_hash"] = canonical_hash(row)
        cases.append(row)
    return {
        "registry": registry,
        "private_key": private_key,
        "trust_registry": trust_registry,
        "release": release,
        "runner": runner,
        "family": family,
        "cases": cases,
        "now": datetime(2026, 7, 14, 0, 0, 0, tzinfo=timezone.utc),
    }


def _refresh_case_hashes_and_aggregate(payload: dict[str, Any]) -> None:
    aggregate = []
    for row in payload["cases"]:
        row["case_evidence_hash"] = canonical_hash(
            {key: value for key, value in row.items() if key != "case_evidence_hash"}
        )
        aggregate.append(
            {
                "slot_id": row["slot_id"],
                "slot_registration_hash": row["slot_registration_hash"],
                "case_receipt_hash": row["model_case_receipt_v1"]["receipt_hash"],
                "completion_payload_hash": row["completion_payload_hash"],
                "case_evidence_hash": row["case_evidence_hash"],
            }
        )
    payload["ordered_case_aggregate_hash"] = canonical_hash(aggregate)


def _build_envelope(
    material: dict[str, Any],
    *,
    mutate: Any = None,
    challenge_override: Any | None = None,
) -> tuple[bytes, Any]:
    challenge = challenge_override
    if challenge is None:
        challenge = evidence_module._issue_challenge_with_registry(
            release_binding=material["release"],
            key_id="ed25519:external-runner:v1",
            runner_id="external-runner",
            run_sequence=1,
            request_id="request:test-001",
            campaign_id="campaign:test-001",
            ttl_seconds=900,
            registry=material["trust_registry"],
            now=material["now"],
        )
    registry = material["registry"]
    payload = {
        "payload_schema_version": (
            HIP_FGMRES_EXTERNAL_SIGNED_PAYLOAD_SCHEMA_VERSION_V1
        ),
        "purpose": "hip_fgmres_external_gfx1100_fixed_suite_attestation",
        "evidence_scope": "trusted_runner_signed_serialized_lane_non_promoting",
        "challenge": challenge.to_dict(),
        "release_binding": material["release"].to_dict(),
        "runner": dict(material["runner"]),
        "fixture_registry": {
            "suite_id": HIP_FGMRES_FIXTURE_REGISTRY_SUITE_ID_V1,
            "registry_bytes_sha256": registry.registry_bytes_sha256,
            "registry_hash": registry.registry_hash,
            "registry_receipt_hash": registry.receipt_hash,
            "ordered_slot_ids": list(HIP_FGMRES_FIXTURE_REGISTRY_REQUIRED_SLOT_IDS_V1),
        },
        "family_receipt_v2": material["family"].to_dict(),
        "cases": [dict(row) for row in material["cases"]],
        "common_runtime_binding_hash": canonical_hash(
            evidence_module._runtime_binding_payload(material["runner"])
        ),
        "ordered_case_aggregate_hash": _HASH,
        "claims": {
            "runner_attests_actual_native_hip_execution": True,
            "runner_attests_external_gfx1100_fixed_suite": True,
            "raw_completion_payloads_included": True,
            "full_model_family_parity_verified": False,
            "multiarchitecture_promotion_verified": False,
            "result_ir_verified": False,
            "iteration_host_copy_zero_verified": False,
            "speedup_verified": False,
            "end_to_end_o_n_verified": False,
            "commercial_ready": False,
            "promotion_eligible": False,
        },
    }
    _refresh_case_hashes_and_aggregate(payload)
    if mutate is not None:
        mutate(payload)
    signed_payload_hash = sha256_prefixed(canonical_json_bytes(payload))
    root = {
        "schema_version": HIP_FGMRES_EXTERNAL_SIGNED_EVIDENCE_SCHEMA_VERSION_V1,
        "capability_profile": (
            HIP_FGMRES_EXTERNAL_SIGNED_EVIDENCE_CAPABILITY_PROFILE_V1
        ),
        "algorithm": "Ed25519",
        "key_id": "ed25519:external-runner:v1",
        "signed_payload_sha256": signed_payload_hash,
        "signed_payload": payload,
    }
    message = evidence_module._SIGNATURE_DOMAIN + canonical_json_bytes(root)
    root["signature_base64"] = base64.b64encode(
        material["private_key"].sign(message)
    ).decode("ascii")
    root["envelope_hash"] = canonical_hash(root)
    return canonical_json_bytes(root), challenge


def _verify(
    raw: bytes,
    challenge: Any,
    material: dict[str, Any],
    *,
    success_commit_hook: Any = None,
) -> Any:
    return evidence_module._verify_with_authorities(
        raw,
        challenge=challenge,
        release_binding=material["release"],
        trust_registry=material["trust_registry"],
        fixture_registry=material["registry"],
        now=material["now"] + timedelta(seconds=3),
        success_commit_hook=success_commit_hook,
    )


def test_exact_signed_gfx1100_ten_slot_envelope_replays_and_consumes_challenge(
    evidence_material: dict[str, Any],
) -> None:
    raw, challenge = _build_envelope(evidence_material)
    receipt = _verify(raw, challenge, evidence_material)

    assert challenge.consumed
    assert receipt.verified_slot_count == 10
    assert receipt.verified_slot_ids == (
        HIP_FGMRES_FIXTURE_REGISTRY_REQUIRED_SLOT_IDS_V1
    )
    assert receipt.claims.ed25519_signature_verified
    assert receipt.claims.raw_numerical_parity_replayed
    assert receipt.claims.solve_record_semantics_replayed
    assert not receipt.claims.durable_replay_ledger_verified
    assert not receipt.claims.same_artifact_two_architecture_verified
    assert not receipt.claims.multiarchitecture_promotion_verified
    assert not receipt.claims.commercial_ready
    assert not receipt.promotion_eligible

    with pytest.raises(HipFgmresExternalSignedEvidenceV1Error) as replayed:
        _verify(raw, challenge, evidence_material)
    assert replayed.value.code == "hip_fgmres_external_challenge_replayed"


def test_success_commit_hook_receives_final_receipt_before_challenge_consumption(
    evidence_material: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw, challenge = _build_envelope(evidence_material)
    committed: list[Any] = []
    order: list[str] = []

    def validate_numerics(*_args: Any, **_kwargs: Any) -> None:
        order.append("numeric_validation")

    monkeypatch.setattr(evidence_module, "_validate_cases", validate_numerics)

    def commit(receipt: Any) -> None:
        assert order == ["numeric_validation"]
        assert not challenge.consumed
        assert (
            evidence_module.validate_hip_fgmres_external_signed_evidence_receipt_v1(
                receipt
            )
            is receipt
        )
        assert receipt.challenge_id == challenge.challenge_id
        assert not receipt.claims.durable_replay_ledger_verified
        order.append("success_commit")
        committed.append(receipt)

    returned = _verify(
        raw,
        challenge,
        evidence_material,
        success_commit_hook=commit,
    )

    assert committed == [returned]
    assert committed[0] is returned
    assert order == ["numeric_validation", "success_commit"]
    assert challenge.consumed


def test_success_commit_hook_failure_releases_reservation_without_consuming(
    evidence_material: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw, challenge = _build_envelope(evidence_material)
    finalized: list[Any] = []
    order: list[str] = []

    def validate_numerics(*_args: Any, **_kwargs: Any) -> None:
        order.append("numeric_validation")

    monkeypatch.setattr(evidence_module, "_validate_cases", validate_numerics)

    class CommitFailure(RuntimeError):
        pass

    def reject_commit(receipt: Any) -> None:
        assert order == ["numeric_validation"]
        assert not challenge.consumed
        order.append("success_commit")
        finalized.append(receipt)
        raise CommitFailure("durable commit failed")

    with pytest.raises(CommitFailure, match="durable commit failed"):
        _verify(
            raw,
            challenge,
            evidence_material,
            success_commit_hook=reject_commit,
        )

    assert len(finalized) == 1
    assert order == ["numeric_validation", "success_commit"]
    assert not challenge.consumed
    reservation = challenge._reserve()
    challenge._release(reservation)
    assert not challenge.consumed


def test_rehydrated_stored_challenge_completes_actual_signed_verification(
    evidence_material: dict[str, Any],
) -> None:
    raw, original = _build_envelope(evidence_material)
    restored = evidence_module._rehydrate_hip_fgmres_external_challenge_v1(
        original.to_dict()
    )

    assert restored is not original
    assert restored.to_dict() == original.to_dict()
    receipt = _verify(raw, restored, evidence_material)

    assert restored.consumed
    assert not original.consumed
    assert receipt.challenge_id == restored.challenge_id
    assert not receipt.claims.durable_replay_ledger_verified


def test_stored_challenge_rehydration_rejects_malformed_and_forged_payloads(
    evidence_material: dict[str, Any],
) -> None:
    _, challenge = _build_envelope(evidence_material)
    valid = challenge.to_dict()

    cases: tuple[tuple[Any, str], ...] = (
        ([], "hip_fgmres_external_stored_challenge_type_invalid"),
        (
            {key: value for key, value in valid.items() if key != "campaign_id"},
            "hip_fgmres_external_stored_challenge_fields_invalid",
        ),
        (
            {**valid, "unknown": "field"},
            "hip_fgmres_external_stored_challenge_fields_invalid",
        ),
        (
            {**valid, "expected_run_sequence": True},
            "hip_fgmres_external_stored_challenge_field_invalid",
        ),
        (
            {**valid, "request_id": "INVALID"},
            "hip_fgmres_external_stored_challenge_semantics_invalid",
        ),
        (
            {**valid, "nonce_base64": "A" * 44},
            "hip_fgmres_external_stored_challenge_nonce_invalid",
        ),
        (
            {**valid, "expires_at_utc": valid["issued_at_utc"]},
            "hip_fgmres_external_stored_challenge_timestamp_invalid",
        ),
        (
            {**valid, "audience": "untrusted-verifier"},
            "hip_fgmres_external_stored_challenge_semantics_invalid",
        ),
        (
            {**valid, "expected_architecture_base": "gfx1030"},
            "hip_fgmres_external_stored_challenge_semantics_invalid",
        ),
        (
            {**valid, "expected_suite_id": "wrong-suite"},
            "hip_fgmres_external_stored_challenge_semantics_invalid",
        ),
        (
            {**valid, "campaign_id": "campaign:forged"},
            "hip_fgmres_external_stored_challenge_hash_invalid",
        ),
    )
    for payload, expected_code in cases:
        with pytest.raises(HipFgmresExternalSignedEvidenceV1Error) as caught:
            evidence_module._rehydrate_hip_fgmres_external_challenge_v1(payload)
        assert caught.value.code == expected_code

    private_payload = evidence_module._ChallengePayloadV1(**valid)
    with pytest.raises(HipFgmresExternalSignedEvidenceV1Error) as private_mint:
        evidence_module.HipFgmresExternalChallengeV1(
            private_payload,
            mint=object(),
        )
    assert private_mint.value.code == (
        "hip_fgmres_external_challenge_construction_forbidden"
    )


def test_routing_extractor_is_strict_but_does_not_claim_signature_authority(
    evidence_material: dict[str, Any],
) -> None:
    raw, challenge = _build_envelope(evidence_material)

    payload = evidence_module._extract_hip_fgmres_external_envelope_routing_v1(raw)
    assert payload["challenge_id"] == challenge.challenge_id
    assert payload == challenge.to_dict()

    with pytest.raises(HipFgmresExternalSignedEvidenceV1Error) as noncanonical:
        evidence_module._extract_hip_fgmres_external_envelope_routing_v1(raw + b"\n")
    assert noncanonical.value.code == "hip_fgmres_external_envelope_not_canonical"

    with pytest.raises(HipFgmresExternalSignedEvidenceV1Error) as duplicate:
        evidence_module._extract_hip_fgmres_external_envelope_routing_v1(
            b'{"a":1,"a":2}'
        )
    assert duplicate.value.code == "hip_fgmres_external_envelope_duplicate_key"

    parsed = evidence_module._parse_canonical_envelope(raw)
    parsed["signed_payload"]["challenge"]["campaign_id"] = "campaign:forged"
    with pytest.raises(HipFgmresExternalSignedEvidenceV1Error) as hash_tamper:
        evidence_module._extract_hip_fgmres_external_envelope_routing_v1(
            canonical_json_bytes(parsed)
        )
    assert hash_tamper.value.code == "hip_fgmres_external_envelope_semantics_invalid"

    parsed["signed_payload_sha256"] = sha256_prefixed(
        canonical_json_bytes(parsed["signed_payload"])
    )
    parsed["envelope_hash"] = canonical_hash(
        {key: value for key, value in parsed.items() if key != "envelope_hash"}
    )
    with pytest.raises(HipFgmresExternalSignedEvidenceV1Error) as forged:
        evidence_module._extract_hip_fgmres_external_envelope_routing_v1(
            canonical_json_bytes(parsed)
        )
    assert forged.value.code == "hip_fgmres_external_stored_challenge_hash_invalid"

    parsed = evidence_module._parse_canonical_envelope(raw)
    parsed["signature_base64"] = base64.b64encode(b"\x00" * 64).decode("ascii")
    parsed["envelope_hash"] = canonical_hash(
        {key: value for key, value in parsed.items() if key != "envelope_hash"}
    )
    routed_payload = evidence_module._extract_hip_fgmres_external_envelope_routing_v1(
        canonical_json_bytes(parsed)
    )
    assert routed_payload["challenge_id"] == challenge.challenge_id
    assert routed_payload == challenge.to_dict()

    with pytest.raises(HipFgmresExternalSignedEvidenceV1Error) as oversized:
        evidence_module._extract_hip_fgmres_external_envelope_routing_v1(
            b"x" * (evidence_module._ENVELOPE_MAX_BYTES + 1)
        )
    assert oversized.value.code == "hip_fgmres_external_envelope_extent_invalid"


def test_public_package_registry_with_zero_keys_rejects_synthetic_envelope(
    evidence_material: dict[str, Any],
) -> None:
    raw, challenge = _build_envelope(evidence_material)
    with pytest.raises(HipFgmresExternalSignedEvidenceV1Error) as caught:
        evidence_module.verify_hip_fgmres_external_signed_evidence_v1(
            raw,
            challenge=challenge,
            release_binding=evidence_material["release"],
        )
    assert caught.value.code == "hip_fgmres_external_trust_anchor_not_found"
    assert not challenge.consumed


def test_canonical_json_and_signature_tamper_fail_closed_without_consuming(
    evidence_material: dict[str, Any],
) -> None:
    raw, challenge = _build_envelope(evidence_material)
    with pytest.raises(HipFgmresExternalSignedEvidenceV1Error) as whitespace:
        _verify(raw + b"\n", challenge, evidence_material)
    assert whitespace.value.code == "hip_fgmres_external_envelope_not_canonical"
    assert not challenge.consumed

    parsed = evidence_module._parse_canonical_envelope(raw)
    parsed["signature_base64"] = base64.b64encode(b"\x00" * 64).decode("ascii")
    parsed["envelope_hash"] = canonical_hash(
        {key: value for key, value in parsed.items() if key != "envelope_hash"}
    )
    with pytest.raises(HipFgmresExternalSignedEvidenceV1Error) as signature:
        _verify(canonical_json_bytes(parsed), challenge, evidence_material)
    assert signature.value.code == "hip_fgmres_external_signature_invalid"
    assert not challenge.consumed


def test_trusted_signer_cannot_reorder_slots_or_mix_raw_numerics(
    evidence_material: dict[str, Any],
) -> None:
    def reorder(payload: dict[str, Any]) -> None:
        payload["cases"][0], payload["cases"][1] = (
            payload["cases"][1],
            payload["cases"][0],
        )
        _refresh_case_hashes_and_aggregate(payload)

    raw, challenge = _build_envelope(evidence_material, mutate=reorder)
    with pytest.raises(HipFgmresExternalSignedEvidenceV1Error) as reordered:
        _verify(raw, challenge, evidence_material)
    assert reordered.value.code == "hip_fgmres_external_case_order_invalid"
    assert not challenge.consumed

    def mix(payload: dict[str, Any]) -> None:
        payload["cases"][0]["solution_x_base64"] = payload["cases"][1][
            "solution_x_base64"
        ]
        _refresh_case_hashes_and_aggregate(payload)

    mixed_raw, mixed_challenge = _build_envelope(evidence_material, mutate=mix)
    with pytest.raises(HipFgmresExternalSignedEvidenceV1Error) as mixed:
        _verify(mixed_raw, mixed_challenge, evidence_material)
    assert mixed.value.code in {
        "hip_fgmres_external_case_base64_invalid",
        "hip_fgmres_external_completion_payload_hash_invalid",
    }
    assert not mixed_challenge.consumed


def test_challenge_is_bound_to_exact_envelope_and_release(
    evidence_material: dict[str, Any],
) -> None:
    raw, _ = _build_envelope(evidence_material)
    _, other_challenge = _build_envelope(evidence_material)
    with pytest.raises(HipFgmresExternalSignedEvidenceV1Error) as caught:
        _verify(raw, other_challenge, evidence_material)
    assert caught.value.code == "hip_fgmres_external_challenge_mismatch"
    assert not other_challenge.consumed


def test_challenge_reservation_is_atomic_across_threads(
    evidence_material: dict[str, Any],
) -> None:
    _, challenge = _build_envelope(evidence_material)

    def reserve() -> tuple[str, Any]:
        try:
            return "reserved", challenge._reserve()
        except HipFgmresExternalSignedEvidenceV1Error as exc:
            return exc.code, None

    with ThreadPoolExecutor(max_workers=8) as executor:
        outcomes = tuple(executor.map(lambda _: reserve(), range(8)))
    reserved = tuple(row for row in outcomes if row[0] == "reserved")
    assert len(reserved) == 1
    assert all(
        row[0] in {"reserved", "hip_fgmres_external_challenge_replayed"}
        for row in outcomes
    )
    challenge._release(reserved[0][1])
    assert not challenge.consumed


def test_challenge_lifetime_cannot_outlive_trust_anchor(
    evidence_material: dict[str, Any],
) -> None:
    near_key_expiry = datetime(
        2026,
        12,
        31,
        23,
        59,
        30,
        tzinfo=timezone.utc,
    )
    with pytest.raises(HipFgmresExternalSignedEvidenceV1Error) as caught:
        evidence_module._issue_challenge_with_registry(
            release_binding=evidence_material["release"],
            key_id="ed25519:external-runner:v1",
            runner_id="external-runner",
            run_sequence=1,
            request_id="request:key-expiry",
            campaign_id="campaign:key-expiry",
            ttl_seconds=60,
            registry=evidence_material["trust_registry"],
            now=near_key_expiry,
        )
    assert caught.value.code == "hip_fgmres_external_trust_anchor_not_active"


def test_expired_challenge_and_mixed_device_fail_before_consumption(
    evidence_material: dict[str, Any],
) -> None:
    raw, challenge = _build_envelope(evidence_material)
    with pytest.raises(HipFgmresExternalSignedEvidenceV1Error) as expired:
        evidence_module._verify_with_authorities(
            raw,
            challenge=challenge,
            release_binding=evidence_material["release"],
            trust_registry=evidence_material["trust_registry"],
            fixture_registry=evidence_material["registry"],
            now=evidence_material["now"] + timedelta(seconds=901),
        )
    assert expired.value.code == (
        "hip_fgmres_external_challenge_expired_or_time_invalid"
    )
    assert not challenge.consumed

    def mix_device(payload: dict[str, Any]) -> None:
        payload["runner"]["device_uuid_bytes_hex"] = "03" * 16
        payload["common_runtime_binding_hash"] = canonical_hash(
            evidence_module._runtime_binding_payload(payload["runner"])
        )

    mixed_raw, mixed_challenge = _build_envelope(
        evidence_material,
        mutate=mix_device,
    )
    with pytest.raises(HipFgmresExternalSignedEvidenceV1Error) as mixed:
        _verify(mixed_raw, mixed_challenge, evidence_material)
    assert mixed.value.code == ("hip_fgmres_external_runner_family_binding_mismatch")
    assert not mixed_challenge.consumed


@pytest.mark.parametrize(
    ("raw", "code"),
    [
        (b"\xef\xbb\xbf{}", "hip_fgmres_external_envelope_bom_forbidden"),
        (b'{"a":1,"a":2}', "hip_fgmres_external_envelope_duplicate_key"),
        (b'{"a":Infinity}', "hip_fgmres_external_envelope_json_invalid"),
    ],
)
def test_envelope_parser_rejects_bom_duplicate_and_nonfinite(
    raw: bytes,
    code: str,
) -> None:
    with pytest.raises(HipFgmresExternalSignedEvidenceV1Error) as caught:
        evidence_module._parse_canonical_envelope(raw)
    assert caught.value.code == code


@pytest.mark.parametrize(
    "depth",
    [
        evidence_module._ENVELOPE_MAX_JSON_DEPTH + 1,
        1_100,
    ],
)
def test_envelope_parser_maps_excessive_json_nesting_to_stable_extent_error(
    depth: int,
) -> None:
    raw = b"[" * depth + b"0" + b"]" * depth
    with pytest.raises(HipFgmresExternalSignedEvidenceV1Error) as caught:
        evidence_module._parse_canonical_envelope(raw)
    assert caught.value.code == "hip_fgmres_external_envelope_extent_invalid"


def test_envelope_parser_applies_depth_limit_to_empty_containers() -> None:
    accepted_depth = evidence_module._ENVELOPE_MAX_JSON_DEPTH
    accepted_raw = b"[" * accepted_depth + b"]" * accepted_depth
    with pytest.raises(HipFgmresExternalSignedEvidenceV1Error) as accepted:
        evidence_module._parse_canonical_envelope(accepted_raw)
    assert accepted.value.code == "hip_fgmres_external_envelope_root_invalid"

    rejected_depth = accepted_depth + 1
    rejected_raw = b"[" * rejected_depth + b"]" * rejected_depth
    with pytest.raises(HipFgmresExternalSignedEvidenceV1Error) as rejected:
        evidence_module._parse_canonical_envelope(rejected_raw)
    assert rejected.value.code == "hip_fgmres_external_envelope_extent_invalid"


def test_envelope_parser_bounds_total_json_nodes() -> None:
    raw = (
        b"["
        + b",".join(b"0" for _ in range(evidence_module._ENVELOPE_MAX_JSON_NODES))
        + b"]"
    )
    assert len(raw) < evidence_module._ENVELOPE_MAX_BYTES
    with pytest.raises(HipFgmresExternalSignedEvidenceV1Error) as caught:
        evidence_module._parse_canonical_envelope(raw)
    assert caught.value.code == "hip_fgmres_external_envelope_extent_invalid"


def test_envelope_parser_shares_wide_paths_and_bounds_error_text() -> None:
    long_key = b"k" * 100_000
    deep_leaf = b"[" * 65 + b"0" + b"]" * 65
    raw = b'{"' + long_key + b'":[' + b",".join([deep_leaf] * 256) + b"]}"
    assert len(raw) < evidence_module._ENVELOPE_MAX_BYTES
    with pytest.raises(HipFgmresExternalSignedEvidenceV1Error) as caught:
        evidence_module._parse_canonical_envelope(raw)
    assert caught.value.code == "hip_fgmres_external_envelope_extent_invalid"
    assert len(caught.value.path) <= evidence_module._ENVELOPE_MAX_ERROR_PATH_CHARS
    assert len(str(caught.value)) < 768


def test_schema_validation_stops_after_first_error_and_bounds_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FirstError:
        absolute_path = ("signed_payload", "cases")
        validator = "maxItems"
        message = "attacker-controlled-instance" * 100_000

    class FailFastProbeValidator:
        @staticmethod
        def check_schema(schema: dict[str, Any]) -> None:
            assert schema["$schema"].endswith("2020-12/schema")

        def __init__(self, schema: dict[str, Any]) -> None:
            assert schema["type"] == "object"

        def iter_errors(self, payload: dict[str, Any]) -> Any:
            assert payload == {}
            yield FirstError()
            raise AssertionError("schema errors must not be materialized")

    monkeypatch.setattr(
        evidence_module,
        "Draft202012Validator",
        FailFastProbeValidator,
    )
    with pytest.raises(HipFgmresExternalSignedEvidenceV1Error) as caught:
        evidence_module._validate_json_schema(
            {},
            evidence_module._ENVELOPE_SCHEMA_RESOURCE,
            path="/envelope",
        )
    assert caught.value.code == "hip_fgmres_external_schema_validation_failed"
    assert caught.value.path == "/envelope/signed_payload/cases"
    assert caught.value.message == "schema keyword maxItems rejected value"


def test_schema_validator_internal_failure_maps_to_stable_domain_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class BrokenValidator:
        @staticmethod
        def check_schema(schema: dict[str, Any]) -> None:
            assert schema["type"] == "object"

        def __init__(self, schema: dict[str, Any]) -> None:
            assert schema["$schema"].endswith("2020-12/schema")

        def iter_errors(self, payload: dict[str, Any]) -> Any:
            del payload
            raise RuntimeError("library detail must not escape")
            yield

    monkeypatch.setattr(evidence_module, "Draft202012Validator", BrokenValidator)
    with pytest.raises(HipFgmresExternalSignedEvidenceV1Error) as caught:
        evidence_module._validate_json_schema(
            {},
            evidence_module._ENVELOPE_SCHEMA_RESOURCE,
            path="/envelope",
        )
    assert caught.value.code == "hip_fgmres_external_schema_invalid"
    assert caught.value.path == "/envelope"
    assert caught.value.message == "RuntimeError"


def _make_verified_release_v2(
    material: dict[str, Any],
    *,
    identity_label: str = "primary",
) -> Any:
    binding = material["release"]
    draft = release_identity_module.HipFgmresExternalReleaseIdentityReceiptV1(
        schema_version=(
            release_identity_module.HIP_FGMRES_EXTERNAL_RELEASE_IDENTITY_SCHEMA_VERSION_V1
        ),
        capability_profile=(
            release_identity_module.HIP_FGMRES_EXTERNAL_RELEASE_IDENTITY_CAPABILITY_PROFILE_V1
        ),
        status="external_release_artifacts_independently_verified",
        evidence_scope=(
            release_identity_module.HIP_FGMRES_EXTERNAL_RELEASE_IDENTITY_EVIDENCE_SCOPE_V1
        ),
        release_binding_hash=binding.binding_hash,
        wheel_identity_hash=_hash(f"v2-wheel-identity-{identity_label}"),
        installed_replay_hash=_hash(f"v2-installed-{identity_label}"),
        source_identity_hash=_hash(f"v2-source-{identity_label}"),
        dependency_lock_receipt_hash=_hash(f"v2-dependency-{identity_label}"),
        build_recipe_semantic_hash=_hash(f"v2-recipe-{identity_label}"),
        wheel_filename=binding.wheel_filename,
        wheel_byte_count=binding.wheel_byte_count,
        wheel_sha256=binding.wheel_sha256,
        wheel_record_sha256=binding.wheel_record_sha256,
        wheel_member_count=2,
        installed_verified_member_count=1,
        installed_extra_file_count=0,
        installed_script_file_count=0,
        installed_script_manifest_sha256=_hash(f"v2-scripts-{identity_label}"),
        source_commit=binding.source_commit,
        source_tree_sha256=binding.source_tree_sha256,
        source_tracked_file_count=1,
        source_bundle_byte_count=1,
        source_bundle_sha256=binding.source_bundle_sha256,
        runner_source_file_count=1,
        runner_source_sha256=binding.runner_source_sha256,
        build_recipe_sha256=binding.build_recipe_sha256,
        dependency_lock_sha256=binding.dependency_lock_sha256,
        dependency_artifact_count=0,
        dependency_artifact_aggregate_hash=_hash(
            f"v2-dependency-aggregate-{identity_label}"
        ),
        claims=release_identity_module.HipFgmresExternalReleaseIdentityClaimsV1(),
        promotion_eligible=False,
        receipt_hash="sha256:" + "0" * 64,
    )
    receipt = replace(
        draft,
        receipt_hash=canonical_hash(
            release_identity_module._receipt_payload(draft, include_hash=False)
        ),
    )
    release_identity_module.validate_hip_fgmres_external_release_identity_receipt_v1(
        receipt
    )
    paths = release_identity_module.HipFgmresExternalReleaseArtifactPathsV1(
        repository_root=f"/synthetic/{identity_label}/repository",
        artifact_root=f"/synthetic/{identity_label}/artifacts",
        wheel_filename=binding.wheel_filename,
        source_bundle_filename="source.tar",
        runner_source_paths=("runner.py",),
        build_recipe_path="build-recipe.json",
        dependency_lock_path="dependency-lock.json",
        dependency_artifact_root=f"/synthetic/{identity_label}/wheelhouse",
    )
    return release_identity_module.HipFgmresExternalVerifiedReleaseV1(
        paths=paths,
        release_binding=binding,
        identity_receipt=receipt,
        mint=release_identity_module._VERIFIED_RELEASE_MINT,
    )


def _build_envelope_v2(
    material: dict[str, Any],
    verified_release: Any,
    *,
    mutate: Any = None,
    challenge_override: Any | None = None,
) -> tuple[bytes, Any]:
    challenge = challenge_override
    if challenge is None:
        challenge = evidence_v2_module._issue_challenge_with_registry_v2(
            verified_release=verified_release,
            key_id="ed25519:external-runner:v1",
            runner_id="external-runner",
            run_sequence=1,
            request_id="request:v2-test-001",
            campaign_id="campaign:v2-test-001",
            ttl_seconds=900,
            registry=material["trust_registry"],
            now=material["now"],
        )
    registry = material["registry"]
    identity = verified_release.identity_receipt
    payload = {
        "payload_schema_version": (
            evidence_v2_module.HIP_FGMRES_EXTERNAL_SIGNED_PAYLOAD_SCHEMA_VERSION_V2
        ),
        "purpose": "hip_fgmres_external_gfx1100_release_identity_attestation",
        "evidence_scope": (
            "trusted_runner_signed_release_identity_serialized_lane_non_promoting"
        ),
        "challenge": challenge.to_dict(),
        "release_binding": verified_release.release_binding.to_dict(),
        "release_identity_receipt_schema_version": identity.schema_version,
        "release_identity_receipt_hash": identity.receipt_hash,
        "runner": dict(material["runner"]),
        "fixture_registry": {
            "suite_id": HIP_FGMRES_FIXTURE_REGISTRY_SUITE_ID_V1,
            "registry_bytes_sha256": registry.registry_bytes_sha256,
            "registry_hash": registry.registry_hash,
            "registry_receipt_hash": registry.receipt_hash,
            "ordered_slot_ids": list(HIP_FGMRES_FIXTURE_REGISTRY_REQUIRED_SLOT_IDS_V1),
        },
        "family_receipt_v2": material["family"].to_dict(),
        "cases": [dict(row) for row in material["cases"]],
        "common_runtime_binding_hash": canonical_hash(
            evidence_module._runtime_binding_payload(material["runner"])
        ),
        "ordered_case_aggregate_hash": _HASH,
        "claims": {
            "runner_attests_actual_native_hip_execution": True,
            "runner_attests_external_gfx1100_fixed_suite": True,
            "runner_attests_release_identity_receipt_hash": True,
            "raw_completion_payloads_included": True,
            "full_model_family_parity_verified": False,
            "multiarchitecture_promotion_verified": False,
            "result_ir_verified": False,
            "iteration_host_copy_zero_verified": False,
            "speedup_verified": False,
            "end_to_end_o_n_verified": False,
            "commercial_ready": False,
            "promotion_eligible": False,
        },
    }
    _refresh_case_hashes_and_aggregate(payload)
    if mutate is not None:
        mutate(payload)
    root = {
        "schema_version": (
            evidence_v2_module.HIP_FGMRES_EXTERNAL_SIGNED_EVIDENCE_SCHEMA_VERSION_V2
        ),
        "capability_profile": (
            evidence_v2_module.HIP_FGMRES_EXTERNAL_SIGNED_EVIDENCE_CAPABILITY_PROFILE_V2
        ),
        "algorithm": "Ed25519",
        "key_id": "ed25519:external-runner:v1",
        "signed_payload_sha256": sha256_prefixed(canonical_json_bytes(payload)),
        "signed_payload": payload,
    }
    message = evidence_v2_module._SIGNATURE_DOMAIN_V2 + canonical_json_bytes(root)
    root["signature_base64"] = base64.b64encode(
        material["private_key"].sign(message)
    ).decode("ascii")
    root["envelope_hash"] = canonical_hash(root)
    return canonical_json_bytes(root), challenge


def _verify_v2(
    raw: bytes,
    challenge: Any,
    verified_release: Any,
    material: dict[str, Any],
) -> Any:
    return evidence_v2_module._verify_with_authorities_v2(
        raw,
        challenge=challenge,
        verified_release=verified_release,
        trust_registry=material["trust_registry"],
        fixture_registry=material["registry"],
        now=material["now"] + timedelta(seconds=3),
    )


def test_v2_signed_release_identity_hash_happy_path_is_direct_and_non_promoting(
    evidence_material: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    verified_release = _make_verified_release_v2(evidence_material)
    monkeypatch.setattr(
        release_identity_module,
        "verify_hip_fgmres_external_release_artifacts_v1",
        lambda value: value,
    )
    monkeypatch.setattr(
        evidence_module,
        "_TRUST_REGISTRY_LOADER_AUTHORITY",
        lambda: evidence_material["trust_registry"],
    )
    monkeypatch.setattr(
        evidence_module,
        "_FIXTURE_REGISTRY_LOADER_AUTHORITY",
        lambda: evidence_material["registry"],
    )
    monkeypatch.setattr(
        evidence_v2_module,
        "_utc_now_v2",
        lambda: evidence_material["now"] + timedelta(seconds=3),
    )
    raw, challenge = _build_envelope_v2(evidence_material, verified_release)

    verified = evidence_v2_module.verify_hip_fgmres_external_signed_evidence_for_verified_release_v2(
        raw,
        challenge=challenge,
        verified_release=verified_release,
    )
    receipt = verified.signed_receipt

    assert challenge.consumed
    assert (
        type(verified) is evidence_v2_module.HipFgmresExternalVerifiedSignedEvidenceV2
    )
    assert verified.identity_receipt is verified_release.identity_receipt
    assert receipt.release_identity_receipt_hash == (
        verified_release.identity_receipt.receipt_hash
    )
    assert receipt.claims.signed_envelope_binds_release_identity_receipt
    assert receipt.claims.release_artifacts_freshly_replayed
    assert not receipt.claims.durable_replay_ledger_verified
    assert not receipt.claims.hardware_root_attested
    assert not receipt.claims.promotion_eligible
    assert not receipt.claims.commercial_ready

    with pytest.raises(
        evidence_v2_module.HipFgmresExternalSignedEvidenceV2Error
    ) as forged_authority:
        evidence_v2_module.HipFgmresExternalVerifiedSignedEvidenceV2(
            identity_receipt=verified_release.identity_receipt,
            signed_receipt=receipt,
            mint=object(),
        )
    assert forged_authority.value.code == (
        "hip_fgmres_external_v2_verified_signed_evidence_construction_forbidden"
    )


def test_v2_resigned_identity_hash_mutation_is_rejected_before_consumption(
    evidence_material: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    verified_release = _make_verified_release_v2(evidence_material)
    monkeypatch.setattr(
        release_identity_module,
        "verify_hip_fgmres_external_release_artifacts_v1",
        lambda value: value,
    )
    raw, challenge = _build_envelope_v2(
        evidence_material,
        verified_release,
        mutate=lambda payload: payload.__setitem__(
            "release_identity_receipt_hash", _hash("attacker-selected-identity")
        ),
    )

    with pytest.raises(
        evidence_v2_module.HipFgmresExternalSignedEvidenceV2Error
    ) as caught:
        _verify_v2(raw, challenge, verified_release, evidence_material)

    assert caught.value.code == "hip_fgmres_external_v2_release_identity_mismatch"
    assert not challenge.consumed


def test_v2_same_binding_different_identity_receipt_substitution_is_rejected(
    evidence_material: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = _make_verified_release_v2(evidence_material, identity_label="original")
    substituted = _make_verified_release_v2(
        evidence_material,
        identity_label="substituted",
    )
    monkeypatch.setattr(
        release_identity_module,
        "verify_hip_fgmres_external_release_artifacts_v1",
        lambda value: value,
    )
    raw, challenge = _build_envelope_v2(evidence_material, original)

    with pytest.raises(
        evidence_v2_module.HipFgmresExternalSignedEvidenceV2Error
    ) as caught:
        _verify_v2(raw, challenge, substituted, evidence_material)

    assert caught.value.code == "hip_fgmres_external_v2_release_identity_mismatch"
    assert original.release_binding == substituted.release_binding
    assert original.identity_receipt.receipt_hash != (
        substituted.identity_receipt.receipt_hash
    )
    assert not challenge.consumed


def test_v1_and_v2_envelopes_cannot_downgrade_across_verifiers(
    evidence_material: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    verified_release = _make_verified_release_v2(evidence_material)
    monkeypatch.setattr(
        release_identity_module,
        "verify_hip_fgmres_external_release_artifacts_v1",
        lambda value: value,
    )
    v1_raw, v1_challenge = _build_envelope(evidence_material)
    v2_raw, v2_challenge = _build_envelope_v2(evidence_material, verified_release)

    with pytest.raises(
        evidence_v2_module.HipFgmresExternalSignedEvidenceV2Error
    ) as v1_into_v2:
        _verify_v2(v1_raw, v2_challenge, verified_release, evidence_material)
    assert v1_into_v2.value.code == ("hip_fgmres_external_v2_schema_validation_failed")

    with pytest.raises(HipFgmresExternalSignedEvidenceV1Error) as v2_into_v1:
        _verify(v2_raw, v1_challenge, evidence_material)
    assert v2_into_v1.value.code == "hip_fgmres_external_schema_validation_failed"
    assert not v1_challenge.consumed
    assert not v2_challenge.consumed


def test_v2_artifact_drift_during_verify_fails_before_challenge_consumption(
    evidence_material: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    verified_release = _make_verified_release_v2(evidence_material)
    calls = 0

    def replay(value: Any) -> Any:
        nonlocal calls
        calls += 1
        if calls > 2:
            raise release_identity_module.HipFgmresExternalReleaseIdentityV1Error(
                "synthetic_artifact_drift",
                "/artifact",
            )
        return value

    monkeypatch.setattr(
        release_identity_module,
        "verify_hip_fgmres_external_release_artifacts_v1",
        replay,
    )
    raw, challenge = _build_envelope_v2(evidence_material, verified_release)

    with pytest.raises(
        evidence_v2_module.HipFgmresExternalSignedEvidenceV2Error
    ) as caught:
        _verify_v2(raw, challenge, verified_release, evidence_material)

    assert caught.value.code == (
        "hip_fgmres_external_v2_release_artifact_replay_failed"
    )
    assert calls == 3
    assert not challenge.consumed


def test_v2_public_empty_registry_path_fails_closed(
    evidence_material: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    verified_release = _make_verified_release_v2(evidence_material)
    monkeypatch.setattr(
        release_identity_module,
        "verify_hip_fgmres_external_release_artifacts_v1",
        lambda value: value,
    )

    with pytest.raises(
        evidence_v2_module.HipFgmresExternalSignedEvidenceV2Error
    ) as caught:
        evidence_v2_module.issue_hip_fgmres_external_evidence_challenge_for_verified_release_v2(
            verified_release=verified_release,
            key_id="ed25519:external-runner:v1",
            runner_id="external-runner",
            run_sequence=1,
            request_id="request:v2-public-empty",
            campaign_id="campaign:v2-public-empty",
        )

    assert caught.value.code == "hip_fgmres_external_v2_trust_anchor_not_found"


def test_v2_parser_rejects_excessive_depth_with_bounded_error() -> None:
    raw = b"[" * 65 + b"]" * 65

    with pytest.raises(
        evidence_v2_module.HipFgmresExternalSignedEvidenceV2Error
    ) as caught:
        evidence_v2_module._parse_canonical_envelope_v2(raw)

    assert caught.value.code == "hip_fgmres_external_v2_envelope_extent_invalid"
    assert (
        len(caught.value.path) <= evidence_v2_module._ENVELOPE_MAX_ERROR_PATH_CHARS_V2
    )


def test_v2_rejects_signature_created_with_v1_domain_before_consumption(
    evidence_material: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    verified_release = _make_verified_release_v2(evidence_material)
    monkeypatch.setattr(
        release_identity_module,
        "verify_hip_fgmres_external_release_artifacts_v1",
        lambda value: value,
    )
    raw, challenge = _build_envelope_v2(evidence_material, verified_release)
    root = evidence_v2_module._parse_canonical_envelope_v2(raw)
    root.pop("envelope_hash")
    message = evidence_module._SIGNATURE_DOMAIN + canonical_json_bytes(
        evidence_v2_module._signed_content_v2(root)
    )
    root["signature_base64"] = base64.b64encode(
        evidence_material["private_key"].sign(message)
    ).decode("ascii")
    root["envelope_hash"] = canonical_hash(root)

    with pytest.raises(
        evidence_v2_module.HipFgmresExternalSignedEvidenceV2Error
    ) as caught:
        _verify_v2(
            canonical_json_bytes(root),
            challenge,
            verified_release,
            evidence_material,
        )

    assert caught.value.code == "hip_fgmres_external_v2_signature_invalid"
    assert not challenge.consumed


def test_v2_rejects_resigned_false_to_true_claim_before_consumption(
    evidence_material: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    verified_release = _make_verified_release_v2(evidence_material)
    monkeypatch.setattr(
        release_identity_module,
        "verify_hip_fgmres_external_release_artifacts_v1",
        lambda value: value,
    )
    raw, challenge = _build_envelope_v2(
        evidence_material,
        verified_release,
        mutate=lambda payload: payload["claims"].__setitem__(
            "full_model_family_parity_verified",
            True,
        ),
    )

    with pytest.raises(
        evidence_v2_module.HipFgmresExternalSignedEvidenceV2Error
    ) as caught:
        _verify_v2(raw, challenge, verified_release, evidence_material)

    assert caught.value.code in {
        "hip_fgmres_external_v2_schema_validation_failed",
        "hip_fgmres_external_v2_payload_claims_invalid",
    }
    assert not challenge.consumed


def test_signed_nested_receipt_parsers_reject_unverified_extra_fields(
    evidence_material: dict[str, Any],
) -> None:
    family_payload = evidence_material["family"].to_dict()
    family_payload["unverified_assertion"] = True
    with pytest.raises(HipFgmresExternalSignedEvidenceV1Error) as family_error:
        evidence_module._parse_family_receipt(family_payload)
    assert family_error.value.code == "hip_fgmres_external_family_receipt_invalid"

    case_payload = dict(evidence_material["cases"][0]["model_case_receipt_v1"])
    case_payload["unverified_assertion"] = True
    with pytest.raises(HipFgmresExternalSignedEvidenceV1Error) as case_error:
        evidence_module._parse_model_case_receipt(case_payload)
    assert case_error.value.code == ("hip_fgmres_external_model_case_receipt_invalid")


def test_v2_addition_does_not_promote_v1_receipt_claims() -> None:
    assert not evidence_module.HipFgmresExternalSignedEvidenceClaimsV1().durable_replay_ledger_verified
    identity_claims = release_identity_module.HipFgmresExternalReleaseIdentityClaimsV1()
    assert not identity_claims.signed_envelope_binds_release_identity_receipt
    assert not identity_claims.durable_replay_ledger_verified


def _detached_signed_receipt_v1() -> Any:
    draft = evidence_module.HipFgmresExternalSignedEvidenceReceiptV1(
        schema_version=(
            evidence_module.HIP_FGMRES_EXTERNAL_SIGNED_EVIDENCE_RECEIPT_SCHEMA_VERSION_V1
        ),
        capability_profile=(
            evidence_module.HIP_FGMRES_EXTERNAL_SIGNED_EVIDENCE_CAPABILITY_PROFILE_V1
        ),
        status="external_gfx1100_fixed_suite_signed_evidence_verified",
        evidence_scope=(
            evidence_module.HIP_FGMRES_EXTERNAL_SIGNED_EVIDENCE_RECEIPT_SCOPE_V1
        ),
        envelope_hash=_hash("v1-detached-envelope"),
        signed_payload_sha256=_hash("v1-detached-payload"),
        key_id="ed25519:external-runner:v1",
        key_epoch=1,
        runner_id="external-runner",
        run_sequence=1,
        challenge_id=_hash("v1-detached-challenge"),
        release_binding_hash=_hash("v1-detached-release"),
        trust_registry_hash=_hash("v1-detached-trust"),
        fixture_registry_hash=_hash("v1-detached-fixture"),
        family_receipt_hash=_hash("v1-detached-family"),
        common_runtime_binding_hash=_hash("v1-detached-runtime"),
        ordered_case_aggregate_hash=_hash("v1-detached-cases"),
        verified_slot_count=len(HIP_FGMRES_FIXTURE_REGISTRY_REQUIRED_SLOT_IDS_V1),
        verified_slot_ids=HIP_FGMRES_FIXTURE_REGISTRY_REQUIRED_SLOT_IDS_V1,
        claims=evidence_module.HipFgmresExternalSignedEvidenceClaimsV1(),
        promotion_eligible=False,
        receipt_hash="sha256:" + "0" * 64,
    )
    return replace(
        draft,
        receipt_hash=canonical_hash(
            evidence_module._verification_receipt_payload(
                draft,
                include_hash=False,
            )
        ),
    )


@pytest.mark.parametrize(
    ("runner_id", "key_id"),
    [
        ("external:runner", "ed25519:external-runner:v1"),
        ("alternate-runner", "ed25519:external-runner:v1"),
    ],
)
def test_v1_detached_signed_receipt_rejects_runner_or_key_relation_forgery(
    runner_id: str,
    key_id: str,
) -> None:
    valid = _detached_signed_receipt_v1()
    assert (
        evidence_module.validate_hip_fgmres_external_signed_evidence_receipt_v1(valid)
        is valid
    )
    receipt = replace(valid, runner_id=runner_id, key_id=key_id)
    forged = replace(
        receipt,
        receipt_hash=canonical_hash(
            evidence_module._verification_receipt_payload(
                receipt,
                include_hash=False,
            )
        ),
    )

    with pytest.raises(HipFgmresExternalSignedEvidenceV1Error):
        evidence_module.validate_hip_fgmres_external_signed_evidence_receipt_v1(forged)


def _detached_signed_receipt_v2() -> Any:
    draft = evidence_v2_module.HipFgmresExternalSignedEvidenceReceiptV2(
        schema_version=(
            evidence_v2_module.HIP_FGMRES_EXTERNAL_SIGNED_EVIDENCE_RECEIPT_SCHEMA_VERSION_V2
        ),
        capability_profile=(
            evidence_v2_module.HIP_FGMRES_EXTERNAL_SIGNED_EVIDENCE_CAPABILITY_PROFILE_V2
        ),
        status="external_gfx1100_release_identity_signed_evidence_verified",
        evidence_scope=(
            evidence_v2_module.HIP_FGMRES_EXTERNAL_SIGNED_EVIDENCE_RECEIPT_SCOPE_V2
        ),
        envelope_hash=_hash("v2-detached-envelope"),
        signed_payload_sha256=_hash("v2-detached-payload"),
        key_id="ed25519:external-runner:v1",
        key_epoch=1,
        runner_id="external-runner",
        run_sequence=1,
        challenge_id=_hash("v2-detached-challenge"),
        release_binding_hash=_hash("v2-detached-release"),
        release_identity_receipt_schema_version=(
            release_identity_module.HIP_FGMRES_EXTERNAL_RELEASE_IDENTITY_SCHEMA_VERSION_V1
        ),
        release_identity_receipt_hash=_hash("v2-detached-identity"),
        trust_registry_hash=_hash("v2-detached-trust"),
        fixture_registry_hash=_hash("v2-detached-fixture"),
        family_receipt_hash=_hash("v2-detached-family"),
        common_runtime_binding_hash=_hash("v2-detached-runtime"),
        ordered_case_aggregate_hash=_hash("v2-detached-cases"),
        verified_slot_count=len(HIP_FGMRES_FIXTURE_REGISTRY_REQUIRED_SLOT_IDS_V1),
        verified_slot_ids=HIP_FGMRES_FIXTURE_REGISTRY_REQUIRED_SLOT_IDS_V1,
        claims=evidence_v2_module.HipFgmresExternalSignedEvidenceClaimsV2(),
        promotion_eligible=False,
        receipt_hash="sha256:" + "0" * 64,
    )
    return replace(
        draft,
        receipt_hash=canonical_hash(
            evidence_v2_module._verification_receipt_payload_v2(
                draft,
                include_hash=False,
            )
        ),
    )


@pytest.mark.parametrize(
    ("runner_id", "key_id"),
    [
        ("external:runner", "ed25519:external-runner:v1"),
        ("alternate-runner", "ed25519:external-runner:v1"),
    ],
)
def test_v2_detached_signed_receipt_rejects_runner_or_key_relation_forgery(
    runner_id: str,
    key_id: str,
) -> None:
    valid = _detached_signed_receipt_v2()
    assert (
        evidence_v2_module.validate_hip_fgmres_external_signed_evidence_receipt_v2(
            valid
        )
        is valid
    )
    receipt = replace(
        valid,
        runner_id=runner_id,
        key_id=key_id,
    )
    forged = replace(
        receipt,
        receipt_hash=canonical_hash(
            evidence_v2_module._verification_receipt_payload_v2(
                receipt,
                include_hash=False,
            )
        ),
    )

    with pytest.raises(evidence_v2_module.HipFgmresExternalSignedEvidenceV2Error):
        evidence_v2_module.validate_hip_fgmres_external_signed_evidence_receipt_v2(
            forged
        )
