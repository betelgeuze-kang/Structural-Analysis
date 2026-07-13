from __future__ import annotations

import copy
import ctypes
from dataclasses import dataclass
import json
import os
from pathlib import Path
import sys
from typing import Any, NoReturn

import numpy as np
import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from structural_analysis.engine_v2.assembly_backend.context import (  # noqa: E402
    open_hip_assembly_execution_context,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_canonical_predecessor_v1 import (  # noqa: E402
    open_hip_fgmres_canonical_predecessor_context_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_live_checkpoint_context_v1 import (  # noqa: E402
    open_hip_fgmres_live_checkpoint_context_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_plan import (  # noqa: E402
    compile_hip_fgmres_plan_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_recurrence_plan_v2 import (  # noqa: E402
    HIP_FGMRES_CONTROL_STATE_BYTES_V2,
    compile_hip_fgmres_recurrence_plan_v2,
    hip_fgmres_control_state_abi_payload_v2,
    hip_fgmres_solve_record_abi_payload_v2,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_rtc_v2 import (  # noqa: E402
    reduction_stage_output_counts_v2,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_sealed_checkpoint_transaction_v1 import (  # noqa: E402
    open_hip_fgmres_sealed_checkpoint_transaction_context_v1,
    validate_hip_fgmres_sealed_checkpoint_continuation_capability_v1,
    validate_hip_fgmres_sealed_checkpoint_transaction_receipt_v1,
)
from structural_analysis.engine_v2.assembly_backend.free_space import (  # noqa: E402
    open_hip_free_space_execution_context,
)
from structural_analysis.engine_v2.assembly_backend.free_space_plan import (  # noqa: E402
    compile_hip_free_space_operator_plan_v1,
)
from structural_analysis.engine_v2.assembly_backend.krylov_primitives import (  # noqa: E402
    open_hip_krylov_primitives_execution_context,
)
from structural_analysis.engine_v2.assembly_backend.plan import (  # noqa: E402
    compile_hip_assembly_plan_v1,
)
from structural_analysis.engine_v2.assembly_backend.resident import (  # noqa: E402
    open_hip_resident_csr_execution_context,
)
from structural_analysis.engine_v2.backends.hip.native import (  # noqa: E402
    probe_hip_capability,
)
from structural_analysis.engine_v2.buffers import pack_solver_model_buffers  # noqa: E402
from structural_analysis.engine_v2.contracts.execution_plan_v2 import (  # noqa: E402
    compile_execution_plan_v2,
)
from structural_analysis.engine_v2.contracts.state_ir import (  # noqa: E402
    create_initial_state,
)
from structural_analysis.engine_v2.solvers.cpu_fgmres import (  # noqa: E402
    FgmresPolicyV1,
    compile_fgmres_policy_v1,
)
from structural_analysis.model_ir import (  # noqa: E402
    load_model_ir_v2,
    parse_model_ir_v2,
)

from tests.test_engine_v2_hip_fgmres_canonical_predecessor_hardware_v1 import (  # noqa: E402
    FIXTURE,
    _close_chain,
)
from tests.test_engine_v2_hip_fgmres_initial_hardware_v2 import (  # noqa: E402
    _field_offsets,
    _i32,
)
from tests.test_engine_v2_hip_resident_csr_hardware_v1 import (  # noqa: E402
    _local_architectures,
)


_TERMINAL_FAILURE_CLEARING_SOURCE_SHA256 = (
    "sha256:a5b39fb976aa330eaffae74feb8561f241df662a21dc32354b8010af2bb1c93d"
)


def _hardware_required() -> bool:
    return any(
        os.environ.get(name) == "1"
        for name in (
            "ENGINE_V2_REQUIRE_HIP_HARDWARE",
            ("ENGINE_V2_REQUIRE_HIP_FGMRES_SEALED_CHECKPOINT_TRANSACTION_HARDWARE"),
        )
    )


def _hardware_gate(required: bool, message: str) -> NoReturn:
    if required:
        pytest.fail(message, pytrace=False)
    pytest.skip(f"{message} No CPU fallback was used.")


def _native_gfx1030(required: bool) -> str:
    architectures = _local_architectures()
    if not architectures:
        _hardware_gate(required, "No real gfx agent was detected.")
    if architectures[0] != "gfx1030":
        _hardware_gate(
            required,
            f"Primary real HIP agent is {architectures[0]}, not gfx1030.",
        )
    capability = probe_hip_capability(device_ordinal=0)
    if capability.status != "ready":
        assert not capability.fallback_used
        _hardware_gate(
            required,
            f"Native HIP unavailable: {capability.status_code}.",
        )
    return architectures[0]


@dataclass(slots=True)
class _NativeCanonicalChain:
    assembly: Any
    resident: Any
    free_space: Any
    primitives: Any
    live: Any
    canonical: Any
    recurrence: Any

    def close(self) -> None:
        _close_chain(
            ("canonical-predecessor", self.canonical),
            ("fgmres-live", self.live),
            ("krylov", self.primitives),
            ("free-space", self.free_space),
            ("resident", self.resident),
            ("assembly", self.assembly),
        )


def _open_canonical_chain(
    *,
    model: Any,
    architecture: str,
    required: bool,
    policy: FgmresPolicyV1,
    verify_cpu_parity: bool = True,
) -> tuple[_NativeCanonicalChain, Any]:
    buffers = pack_solver_model_buffers(model, load_pattern_id="LC_AXIAL")
    execution_plan = compile_execution_plan_v2(buffers)
    assembly_plan = compile_hip_assembly_plan_v1(buffers, execution_plan)
    assembly = resident = free_space = primitives = live = canonical = None
    try:
        assembly_open = open_hip_assembly_execution_context(
            buffers,
            execution_plan,
            assembly_plan,
            verify_cpu_parity=verify_cpu_parity,
            device_ordinal=0,
            architecture=architecture,
        )
        assembly = assembly_open.context
        if not assembly_open.ready or assembly is None:
            _hardware_gate(
                required,
                f"Assembly unavailable: {assembly_open.receipt.status}.",
            )
        assert assembly_open.receipt.actual_backend == "hip"
        assert assembly_open.receipt.telemetry.fallback_count == 0

        resident_open = open_hip_resident_csr_execution_context(
            assembly,
            create_initial_state(execution_plan),
            architecture=architecture,
        )
        resident = resident_open.context
        if not resident_open.ready or resident is None:
            _hardware_gate(
                required,
                f"Resident unavailable: {resident_open.receipt.status}.",
            )

        free_space_plan = compile_hip_free_space_operator_plan_v1(execution_plan)
        free_open = open_hip_free_space_execution_context(
            resident,
            free_space_plan,
            architecture=architecture,
        )
        free_space = free_open.context
        if not free_open.ready or free_space is None:
            _hardware_gate(
                required,
                f"FreeSpace unavailable: {free_open.receipt.status}.",
            )
        source_apply = free_space.enqueue_operator_apply()
        if source_apply.status != "enqueued":
            _hardware_gate(required, "Native source apply was not enqueued.")

        primitives_open = open_hip_krylov_primitives_execution_context(
            free_space,
            source_apply,
            architecture=architecture,
        )
        primitives = primitives_open.context
        if not primitives_open.ready or primitives is None:
            _hardware_gate(
                required,
                f"Krylov unavailable: {primitives_open.receipt.status}.",
            )
        assert primitives_open.receipt.actual_backend == "hip"

        fgmres_plan = compile_hip_fgmres_plan_v1(
            execution_plan,
            free_space_plan,
            policy,
        )
        recurrence = compile_hip_fgmres_recurrence_plan_v2(fgmres_plan)
        live_open = open_hip_fgmres_live_checkpoint_context_v1(
            primitives,
            source_apply,
            recurrence,
            architecture=architecture,
        )
        live = live_open.context
        if not live_open.ready or live is None:
            _hardware_gate(
                required,
                f"Live FGMRES unavailable: {live_open.receipt.status}.",
            )
        assert live_open.receipt.actual_backend == "hip"
        assert live_open.receipt.kernel is not None
        assert live_open.receipt.kernel.kernel_origin == "internally_compiled"

        canonical_open = open_hip_fgmres_canonical_predecessor_context_v1(live)
        canonical = canonical_open.context
        predecessor_pending = canonical.enqueue_canonical_predecessor()
        capability = canonical.synchronize_canonical_predecessor(predecessor_pending)
        chain = _NativeCanonicalChain(
            assembly,
            resident,
            free_space,
            primitives,
            live,
            canonical,
            recurrence,
        )
        return chain, capability
    except BaseException:
        _close_chain(
            ("canonical-predecessor", canonical),
            ("fgmres-live", live),
            ("krylov", primitives),
            ("free-space", free_space),
            ("resident", resident),
            ("assembly", assembly),
        )
        raise


def _planned_first_column_policy() -> FgmresPolicyV1:
    return compile_fgmres_policy_v1(
        restart_dimension=1,
        max_iterations=2,
        relative_tolerance=1.0e-15,
    )


def _f513_paired_frame_model() -> Any:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    node_count = 86
    payload["model_id"] = "sealed-checkpoint-late-invalid-f513"
    payload["provenance"]["source_ref"] = (
        "generated:sealed-checkpoint-late-invalid-f513"
    )
    payload["nodes"] = [
        {
            "id": f"N{index + 1}",
            "index": index,
            "coordinates_m": [float(index), 0.0, 0.0],
            "source_id": f"generated:N{index + 1}",
            "extensions": {},
        }
        for index in range(node_count)
    ]
    element_template = payload["elements"][0]
    payload["elements"] = []
    for index, first_node in enumerate(range(0, node_count, 2)):
        element = copy.deepcopy(element_template)
        element.update(
            id=f"E{index + 1}",
            index=index,
            node_ids=[f"N{first_node + 1}", f"N{first_node + 2}"],
            source_id=f"generated:E{index + 1}",
        )
        payload["elements"].append(element)
    payload["constraints"][0]["dofs"] = ["UX", "UY", "UZ"]
    payload["constraints"][0]["prescribed_values_si"] = {
        "UX": 0.0,
        "UY": 0.0,
        "UZ": 0.0,
    }
    axial_pattern = copy.deepcopy(payload["load_patterns"][0])
    axial_pattern["nodal_loads"][0].update(
        id="L_AXIAL_TIP",
        node_id=f"N{node_count}",
        source_id="generated:L_AXIAL_TIP",
    )
    payload["load_patterns"] = [axial_pattern]
    return parse_model_ir_v2(payload)


def _download_bytes(
    runtime: Any,
    stream: Any,
    pointers: dict[str, int],
    byte_lengths: dict[str, int],
    roles: tuple[str, ...],
) -> dict[str, np.ndarray]:
    outputs = {role: np.empty(byte_lengths[role], dtype="u1") for role in roles}
    for role, output in outputs.items():
        runtime.copy_d2h_async(
            output,
            ctypes.c_void_p(pointers[role]),
            stream,
        )
    runtime.synchronize(stream)
    return outputs


def test_native_gfx1030_canonical_to_sealed_transaction_is_exact_nonowning_chain() -> (
    None
):
    required = _hardware_required()
    architecture = _native_gfx1030(required)
    chain, predecessor_capability = _open_canonical_chain(
        model=load_model_ir_v2(FIXTURE),
        architecture=architecture,
        required=required,
        policy=_planned_first_column_policy(),
    )
    sealed = None
    try:
        canonical_receipt = chain.canonical.receipt()
        live_telemetry_before = chain.live.receipt().telemetry
        assembly_telemetry_before = chain.assembly.receipt().telemetry

        sealed = open_hip_fgmres_sealed_checkpoint_transaction_context_v1(
            chain.canonical,
            predecessor_capability,
        )
        assert sealed.ready
        assert sealed.receipt.actual_backend == "hip"
        pending = sealed.context.enqueue_sealed_checkpoint_transaction()
        assert pending.attempted_launch_count == 4
        assert pending.accepted_launch_count_lower_bound == 4
        assert pending.accepted_launch_count_upper_bound == 4
        kernel = chain.live._kernel
        assert kernel is not None
        assert kernel._checkpoint_pending_snapshot(chain.live._checkpoint_token) == (
            (chain.live._stream_pointer_snapshot, 4),
        )

        continuation = sealed.context.synchronize_sealed_checkpoint_transaction(pending)
        assert (
            validate_hip_fgmres_sealed_checkpoint_continuation_capability_v1(
                continuation,
                expected_context=sealed.context,
            )
            is continuation
        )
        assert kernel._checkpoint_pending_snapshot(chain.live._checkpoint_token) == ()

        receipt = sealed.context.receipt()
        validate_hip_fgmres_sealed_checkpoint_transaction_receipt_v1(
            receipt,
            expected_context=sealed.context,
        )
        assert receipt.status == "transaction_fenced"
        assert (
            receipt.bindings.kernel_source_sha256
            == _TERMINAL_FAILURE_CLEARING_SOURCE_SHA256
        )
        assert receipt.telemetry.predecessor_capability_consume_count == 1
        assert receipt.telemetry.kernel_launch_attempt_count == 4
        assert receipt.telemetry.kernel_launch_accept_lower_bound == 4
        assert receipt.telemetry.kernel_launch_accept_upper_bound == 4
        assert receipt.telemetry.fence_attempt_count == 1
        assert receipt.telemetry.fence_success_count == 1
        assert receipt.telemetry.pending_consume_attempt_count == 1
        assert receipt.telemetry.consumed_launch_count == 4
        assert canonical_receipt.telemetry.fence_success_count == 1
        assert (
            canonical_receipt.telemetry.fence_success_count
            + receipt.telemetry.fence_success_count
            == 2
        )

        assert receipt.projection.additional_allocation_count == 0
        assert receipt.projection.additional_device_bytes == 0
        assert receipt.projection.additional_borrow_count == 0
        assert receipt.projection.additional_checkpoint_owner_count == 0
        assert receipt.projection.additional_module_load_count == 0
        assert receipt.telemetry.allocation_count == 0
        assert receipt.telemetry.allocation_borrow_count == 0
        assert receipt.telemetry.checkpoint_owner_acquire_count == 0
        assert receipt.telemetry.module_load_count == 0
        assert receipt.telemetry.module_unload_count == 0
        assert receipt.telemetry.h2d_operation_count == 0
        assert receipt.telemetry.d2h_operation_count == 0
        assert receipt.telemetry.intermediate_sync_count == 0
        assert receipt.telemetry.fallback_count == 0
        assert chain.live.receipt().telemetry == live_telemetry_before
        assert chain.assembly.receipt().telemetry == assembly_telemetry_before

        assert receipt.claims.canonical_predecessor_capability_consumed
        assert receipt.claims.direct11_physical16_continuity_bound
        assert receipt.claims.same_runtime_device_stream_bound
        assert receipt.claims.fixed_four_row_program_bound
        assert receipt.claims.fixed_four_row_transaction_fenced
        assert receipt.claims.conditional_post_checkpoint_capability_issued
        assert not receipt.claims.device_validation_outcome_host_observed
        assert not receipt.claims.actual_mask_host_observed
        assert not receipt.claims.commit_gate_host_observed
        assert not receipt.claims.checkpoint_commit_host_observed
        assert not receipt.claims.authoritative_predecessor_proven
        assert not receipt.claims.authoritative_numerical_transaction_proven
        assert not receipt.claims.solution_ready
        assert not receipt.claims.later_recurrence_ready
        assert not receipt.claims.iteration_host_copy_zero_proven
        assert not receipt.claims.asymptotic_o_n_proven
        assert not receipt.claims.speedup_proven
        assert not receipt.claims.commercial_ready
        assert not receipt.claims.promotion_eligible
    finally:
        if sealed is not None and not sealed.context.closed:
            sealed.context.close()
        chain.close()


def test_native_gfx1030_sealed_late_nonfinite_source_preserves_full_destinations() -> (
    None
):
    required = _hardware_required()
    architecture = _native_gfx1030(required)
    chain, predecessor_capability = _open_canonical_chain(
        model=_f513_paired_frame_model(),
        architecture=architecture,
        required=required,
        policy=_planned_first_column_policy(),
        verify_cpu_parity=False,
    )
    sealed = None
    try:
        free_dof_count = chain.recurrence.free_dof_count
        restart_dimension = chain.recurrence.restart_dimension
        assert free_dof_count == 513
        assert free_dof_count >= 513
        assert restart_dimension == 1
        assert len(reduction_stage_output_counts_v2(free_dof_count)) == 2

        runtime = chain.live._runtime
        stream = chain.live._stream
        assert runtime is not None and stream is not None
        pointers = chain.canonical._pointers
        byte_lengths = chain.canonical._owned_byte_lengths
        destination_roles = ("solution_x", "true_residual")

        # Verification-only download before the late adversarial mutation.
        destination_before = _download_bytes(
            runtime,
            stream,
            pointers,
            byte_lengths,
            destination_roles,
        )

        trial_solution = np.full(free_dof_count, 2.0, dtype="<f8")
        trial_solution[-1] = np.nan
        basis_v = np.zeros(
            (restart_dimension + 1) * free_dof_count,
            dtype="<f8",
        )
        basis_v[restart_dimension * free_dof_count :] = 3.0
        basis_v[-1] = -np.inf
        assert free_dof_count - 1 >= 512

        # Verification-only fault injection after the canonical predecessor
        # fence. It is outside all product receipt telemetry and claims.
        runtime.copy_h2d_async(
            ctypes.c_void_p(pointers["work_w"]),
            trial_solution,
            stream,
        )
        runtime.copy_h2d_async(
            ctypes.c_void_p(pointers["basis_v"]),
            basis_v,
            stream,
        )
        runtime.synchronize(stream)

        sealed = open_hip_fgmres_sealed_checkpoint_transaction_context_v1(
            chain.canonical,
            predecessor_capability,
        )
        pending = sealed.context.enqueue_sealed_checkpoint_transaction()
        kernel = chain.live._kernel
        assert kernel is not None
        assert kernel._checkpoint_pending_snapshot(chain.live._checkpoint_token) == (
            (chain.live._stream_pointer_snapshot, 4),
        )
        conditional_continuation = (
            sealed.context.synchronize_sealed_checkpoint_transaction(pending)
        )
        assert kernel._checkpoint_pending_snapshot(chain.live._checkpoint_token) == ()

        receipt = sealed.context.receipt()
        validate_hip_fgmres_sealed_checkpoint_transaction_receipt_v1(
            receipt,
            expected_context=sealed.context,
        )
        assert (
            validate_hip_fgmres_sealed_checkpoint_continuation_capability_v1(
                conditional_continuation,
                expected_context=sealed.context,
            )
            is conditional_continuation
        )
        assert receipt.status == "transaction_fenced"
        assert (
            receipt.bindings.kernel_source_sha256
            == _TERMINAL_FAILURE_CLEARING_SOURCE_SHA256
        )
        assert receipt.telemetry.kernel_launch_attempt_count == 4
        assert receipt.telemetry.consumed_launch_count == 4
        assert receipt.telemetry.fence_success_count == 1
        assert receipt.telemetry.h2d_operation_count == 0
        assert receipt.telemetry.d2h_operation_count == 0
        assert receipt.telemetry.intermediate_sync_count == 0
        assert receipt.telemetry.fallback_count == 0
        assert receipt.claims.conditional_post_checkpoint_capability_issued
        assert not receipt.claims.device_validation_outcome_host_observed
        assert not receipt.claims.actual_mask_host_observed
        assert not receipt.claims.commit_gate_host_observed
        assert not receipt.claims.checkpoint_commit_host_observed
        assert not receipt.claims.authoritative_numerical_transaction_proven
        assert not receipt.claims.solution_ready

        # Verification-only observations after the product receipt was built.
        observed = _download_bytes(
            runtime,
            stream,
            pointers,
            byte_lengths,
            (
                "solution_x",
                "true_residual",
                "work_w",
                "basis_v",
                "fgmres_control_state_v2",
                "solve_record",
            ),
        )
        for role in destination_roles:
            assert observed[role].tobytes() == destination_before[role].tobytes()
        assert observed["work_w"].tobytes() == trial_solution.tobytes()
        assert observed["basis_v"].tobytes() == basis_v.tobytes()

        control_abi = hip_fgmres_control_state_abi_payload_v2()
        record_abi = hip_fgmres_solve_record_abi_payload_v2()
        control_offsets = _field_offsets(control_abi["fields"])
        record_offsets = _field_offsets(record_abi["header_fields"])
        control_payload = observed["fgmres_control_state_v2"].tobytes()
        record_payload = observed["solve_record"].tobytes()
        assert len(control_payload) == HIP_FGMRES_CONTROL_STATE_BYTES_V2
        stage_count = len(reduction_stage_output_counts_v2(free_dof_count))
        assert (
            _i32(control_payload, control_offsets, "phase")
            == control_abi["phase_codes"]["failed"]
        )
        assert _i32(control_payload, control_offsets, "schedule_epoch") == (
            27 + 14 * stage_count
        )
        assert _i32(control_payload, control_offsets, "reduction_epoch") == (
            14 * stage_count
        )
        assert _i32(control_payload, control_offsets, "failure_origin") == 2
        assert (
            _i32(
                control_payload,
                control_offsets,
                "pending_terminal_status",
            )
            == 6
        )
        assert (
            _i32(
                control_payload,
                control_offsets,
                "pending_termination_code",
            )
            == 47
        )
        actual_mask = _i32(
            control_payload,
            control_offsets,
            "reduction_valid_mask",
        )
        assert actual_mask in (1792, 7936)
        predecessor_state = _i32(
            control_payload,
            control_offsets,
            "predecessor_validation_state",
        )
        assert predecessor_state in {
            control_abi["predecessor_validation_state_codes"]["consumed"],
            control_abi["predecessor_validation_state_codes"]["commit_preflighted"],
        }
        assert (
            _i32(
                control_payload,
                control_offsets,
                "predecessor_mask_snapshot",
            )
            == actual_mask
        )
        assert (
            _i32(
                control_payload,
                control_offsets,
                "predecessor_reduction_epoch_snapshot",
            )
            == 14 * stage_count
        )

        assert _i32(record_payload, record_offsets, "active") == 0
        assert _i32(record_payload, record_offsets, "terminal_status") == 6
        assert _i32(record_payload, record_offsets, "termination_code") == 47
        assert _i32(record_payload, record_offsets, "device_error_bits") == 4
        restart_begin = int(record_abi["header_bytes"])
        restart_end = restart_begin + int(record_abi["restart_bytes"])
        assert record_payload[restart_begin:restart_end] == bytes(
            record_abi["restart_bytes"]
        )

        # The host capability remains explicitly conditional. The actual
        # device continuation flag above is zero and is not promoted into the
        # product receipt.
        final_receipt = sealed.context.receipt()
        assert final_receipt.receipt_hash == receipt.receipt_hash
        assert not final_receipt.claims.device_validation_outcome_host_observed
        assert not final_receipt.claims.authoritative_numerical_transaction_proven
        assert _i32(control_payload, control_offsets, "commit_required") == 0
        assert (
            _i32(
                control_payload,
                control_offsets,
                "continuation_required",
            )
            == 0
        )
    finally:
        if sealed is not None and not sealed.context.closed:
            sealed.context.close()
        chain.close()
