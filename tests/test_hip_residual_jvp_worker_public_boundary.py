from __future__ import annotations

from types import MappingProxyType

import numpy as np
import pytest

from structural_analysis.engine_v2_backends import (
    _hip_residual_jvp_worker_contract as private_contract,
)
from structural_analysis.engine_v2_backends.hip_residual_jvp_worker import (
    HIPResidualJVPWorkerError,
    validate_hip_residual_jvp_worker_receipt,
)


def _residual(state: np.ndarray) -> np.ndarray:
    x, y = state
    return np.asarray([x * x + 2.0 * y, np.sin(x) - y * y], dtype=np.float64)


def _jvp(state: np.ndarray, direction: np.ndarray) -> np.ndarray:
    x, y = state
    return np.asarray(
        [
            2.0 * x * direction[0] + 2.0 * direction[1],
            np.cos(x) * direction[0] - 2.0 * y * direction[1],
        ],
        dtype=np.float64,
    )


def test_public_validator_rejects_private_state_machine_promotion_receipt() -> None:
    runtime = private_contract.HIPRuntimeEvidence(
        execution_kind="hardware",
        source_commit_sha="a" * 40,
        binary_sha256="sha256:" + "b" * 64,
        backend_id="hip_residual_jvp_worker_gfx1030",
        device_architecture="gfx1030",
        available_device_nodes=("/dev/kfd", "/dev/dri"),
        hardware_receipt_hash="sha256:" + "c" * 64,
        hip_kernel_invocation_count=12,
        residual_kernel_invocation_count=4,
        jvp_kernel_invocation_count=8,
        hip_krylov_solver_used=True,
        accepted_state_tangent_refresh_hip_used=True,
        accepted_state_tangent_refresh_cpu_used=False,
        jvp_rows_retained=True,
        cpu_fallback_used=False,
        regularization_used=False,
        mid_step_d2h_count=0,
        production_lifecycle=private_contract.HIPProductionLifecycleEvidence(
            wheel_sha256="sha256:" + "d" * 64,
            dedicated_amd_runner=True,
            runner_id="amd-gfx-runner-01",
            runner_labels=("self-hosted", "linux", "amd-gpu", "rocm"),
            state_rhs_csr_uploaded=True,
            persistent_device_buffers_used=True,
            residual_jvp_on_device=True,
            accepted_state_tangent_refresh_on_device=True,
            equation_scaling_on_device=True,
            production_preconditioner_used=True,
            production_fgmres_used=True,
            newton_update_on_device=True,
            line_search_on_device=True,
            material_commit_rollback_on_device=True,
            convergence_gate_on_device=True,
            checkpoint_emitted=True,
            result_ir_emitted=True,
            diagnostic_ir_emitted=True,
            krylov_iteration_count=8,
            matvec_count=10,
            preconditioner_apply_count=8,
            h2d_bytes=4096,
            d2h_bytes=1024,
            mid_step_d2h_bytes=0,
            peak_vram_bytes=64 * 1024 * 1024,
            checkpoint_overhead_seconds=0.02,
            end_to_end_wall_seconds=1.0,
            cpu_baseline_wall_seconds=2.0,
            speedup_vs_cpu=2.0,
            terminal_result_ir_hash="sha256:" + "e" * 64,
            cpu_terminal_result_ir_hash="sha256:" + "e" * 64,
            terminal_result_ir_parity=True,
        ),
        runtime_metadata=MappingProxyType({"private_contract_probe": True}),
    )
    private_receipt = private_contract.execute_hip_residual_jvp_worker_probe(
        runtime=runtime,
        accepted_state=[0.4, -0.2],
        direction=[1.0, 0.5],
        residual=_residual,
        jacobian_vector_product=_jvp,
    )

    assert private_receipt.hardware_execution_proven is True
    assert private_receipt.production_path_ready is True
    assert private_receipt.blockers == ()
    with pytest.raises(
        HIPResidualJVPWorkerError,
        match="public_hardware_receipt_external_attestation_boundary_missing",
    ):
        validate_hip_residual_jvp_worker_receipt(private_receipt)
