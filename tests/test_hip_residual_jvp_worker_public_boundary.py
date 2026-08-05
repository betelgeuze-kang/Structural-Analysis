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
