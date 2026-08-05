from __future__ import annotations

from types import MappingProxyType

import numpy as np
import pytest

import structural_analysis.engine_v2_backends.hip_residual_jvp_worker as worker
from structural_analysis.engine_v2_backends.hip_residual_jvp_worker import (
    HIPResidualJVPWorkerConfig,
    HIPResidualJVPWorkerError,
    HIPRuntimeEvidence,
    execute_hip_residual_jvp_worker_probe,
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


def _runtime(**overrides):
    values = {
        "execution_kind": "contract_test",
        "source_commit_sha": "a" * 40,
        "binary_sha256": "sha256:" + "b" * 64,
        "backend_id": "hip_residual_jvp_worker_contract_test",
        "device_architecture": None,
        "available_device_nodes": (),
        "hardware_receipt_hash": None,
        "hip_kernel_invocation_count": 0,
        "residual_kernel_invocation_count": 0,
        "jvp_kernel_invocation_count": 0,
        "hip_krylov_solver_used": False,
        "accepted_state_tangent_refresh_hip_used": False,
        "accepted_state_tangent_refresh_cpu_used": False,
        "jvp_rows_retained": False,
        "cpu_fallback_used": False,
        "regularization_used": False,
        "mid_step_d2h_count": 0,
        "runtime_metadata": MappingProxyType({"test_contract": True}),
    }
    values.update(overrides)
    return HIPRuntimeEvidence(**values)


def _execute(runtime: HIPRuntimeEvidence, *, jvp=_jvp):
    return execute_hip_residual_jvp_worker_probe(
        runtime=runtime,
        accepted_state=[0.4, -0.2],
        direction=[1.0, 0.5],
        residual=_residual,
        jacobian_vector_product=jvp,
    )


def _allow_local_hip_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(worker, "_local_hip_device_nodes_valid", lambda: True)


def test_contract_test_can_verify_math_but_cannot_promote_hardware() -> None:
    receipt = _execute(_runtime())

    validate_hip_residual_jvp_worker_receipt(receipt)
    assert receipt.directional_gate_passed is True
    assert receipt.hardware_execution_proven is False
    assert receipt.production_path_ready is False
    assert "actual_hip_hardware_execution_missing" in receipt.blockers
    assert "hip_kernel_invocation_missing" in receipt.blockers
    assert "hip_krylov_solver_not_used" in receipt.blockers
    assert receipt.numerical_authority == "diagnostic_only"
    assert receipt.engineering_authority == "none"
    assert receipt.release_authority == "none"


def test_synthetic_hardware_metadata_cannot_replace_local_device_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(worker, "_local_hip_device_nodes_valid", lambda: False)
    runtime = _runtime(
        execution_kind="hardware",
        backend_id="hip_residual_jvp_worker_gfx1030",
        device_architecture="gfx1030",
        available_device_nodes=("/dev/kfd", "/dev/dri"),
        hardware_receipt_hash="sha256:" + "c" * 64,
        hip_kernel_invocation_count=12,
        residual_kernel_invocation_count=4,
        jvp_kernel_invocation_count=8,
        hip_krylov_solver_used=True,
        accepted_state_tangent_refresh_hip_used=True,
        jvp_rows_retained=True,
    )

    with pytest.raises(HIPResidualJVPWorkerError, match="local_hip_device_probe_failed"):
        _execute(runtime)


def test_complete_local_hardware_claim_remains_blocked_until_external_attestation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _allow_local_hip_probe(monkeypatch)
    receipt = _execute(
        _runtime(
            execution_kind="hardware",
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
        )
    )

    validate_hip_residual_jvp_worker_receipt(receipt)
    assert receipt.directional_gate_passed is True
    assert receipt.runtime["execution_kind"] == "hardware"
    assert receipt.hardware_execution_proven is False
    assert receipt.production_path_ready is False
    assert receipt.blockers == (
        "hardware_execution_attestation_unverified",
        "independent_hardware_operator_attestation_missing",
    )
    assert receipt.numerical_authority == "diagnostic_only"
    assert receipt.engineering_authority == "none"
    assert receipt.release_authority == "none"


def test_cpu_fallback_and_cpu_tangent_refresh_block_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _allow_local_hip_probe(monkeypatch)
    receipt = _execute(
        _runtime(
            execution_kind="hardware",
            backend_id="hip_residual_jvp_worker_gfx1030",
            device_architecture="gfx1030",
            available_device_nodes=("/dev/kfd", "/dev/dri"),
            hardware_receipt_hash="sha256:" + "d" * 64,
            hip_kernel_invocation_count=3,
            residual_kernel_invocation_count=1,
            jvp_kernel_invocation_count=2,
            hip_krylov_solver_used=True,
            accepted_state_tangent_refresh_hip_used=True,
            accepted_state_tangent_refresh_cpu_used=True,
            jvp_rows_retained=True,
            cpu_fallback_used=True,
        )
    )

    assert receipt.hardware_execution_proven is False
    assert receipt.production_path_ready is False
    assert "accepted_state_tangent_refresh_used_cpu" in receipt.blockers
    assert "cpu_fallback_used" in receipt.blockers
    assert "hardware_execution_attestation_unverified" in receipt.blockers


def test_wrong_jvp_blocks_production_even_with_complete_runtime_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _allow_local_hip_probe(monkeypatch)

    def wrong_jvp(state: np.ndarray, direction: np.ndarray) -> np.ndarray:
        return _jvp(state, direction) + np.asarray([0.1, 0.1])

    receipt = _execute(
        _runtime(
            execution_kind="hardware",
            backend_id="hip_residual_jvp_worker_gfx1100",
            device_architecture="gfx1100",
            available_device_nodes=("/dev/kfd", "/dev/dri"),
            hardware_receipt_hash="sha256:" + "e" * 64,
            hip_kernel_invocation_count=3,
            residual_kernel_invocation_count=1,
            jvp_kernel_invocation_count=2,
            hip_krylov_solver_used=True,
            accepted_state_tangent_refresh_hip_used=True,
            jvp_rows_retained=True,
        ),
        jvp=wrong_jvp,
    )

    assert receipt.directional_gate_passed is False
    assert receipt.hardware_execution_proven is False
    assert receipt.production_path_ready is False
    assert "physical_residual_jacobian_directional_gate_failed" in receipt.blockers
    assert "independent_hardware_operator_attestation_missing" in receipt.blockers


def test_hardware_runtime_requires_device_nodes_and_receipt_hash() -> None:
    with pytest.raises(HIPResidualJVPWorkerError, match="hardware_receipt_hash"):
        _runtime(
            execution_kind="hardware",
            device_architecture="gfx1030",
            available_device_nodes=("/dev/kfd", "/dev/dri"),
        ).validate()
    with pytest.raises(HIPResidualJVPWorkerError, match="required_device_nodes"):
        _runtime(
            execution_kind="hardware",
            device_architecture="gfx1030",
            available_device_nodes=("/dev/kfd",),
            hardware_receipt_hash="sha256:" + "f" * 64,
        ).validate()


def test_hardware_runtime_rejects_placeholder_hashes_and_test_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _allow_local_hip_probe(monkeypatch)
    with pytest.raises(HIPResidualJVPWorkerError, match="binary_hash_placeholder"):
        _runtime(
            execution_kind="hardware",
            backend_id="hip_residual_jvp_worker_gfx1030",
            binary_sha256="sha256:" + "0" * 64,
            device_architecture="gfx1030",
            available_device_nodes=("/dev/kfd", "/dev/dri"),
            hardware_receipt_hash="sha256:" + "f" * 64,
        ).validate()
    with pytest.raises(HIPResidualJVPWorkerError, match="backend_id_not_production"):
        _runtime(
            execution_kind="hardware",
            backend_id="hip_residual_jvp_worker_contract_test",
            device_architecture="gfx1030",
            available_device_nodes=("/dev/kfd", "/dev/dri"),
            hardware_receipt_hash="sha256:" + "f" * 64,
        ).validate()


def test_hardware_runtime_rejects_invalid_architecture_and_inconsistent_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _allow_local_hip_probe(monkeypatch)
    with pytest.raises(HIPResidualJVPWorkerError, match="device_architecture_invalid"):
        _runtime(
            execution_kind="hardware",
            backend_id="hip_residual_jvp_worker_device",
            device_architecture="amd-radeon",
            available_device_nodes=("/dev/kfd", "/dev/dri"),
            hardware_receipt_hash="sha256:" + "f" * 64,
        ).validate()
    with pytest.raises(HIPResidualJVPWorkerError, match="invocation_count_inconsistent"):
        _runtime(
            execution_kind="hardware",
            backend_id="hip_residual_jvp_worker_gfx1030",
            device_architecture="gfx1030",
            available_device_nodes=("/dev/kfd", "/dev/dri"),
            hardware_receipt_hash="sha256:" + "f" * 64,
            hip_kernel_invocation_count=2,
            residual_kernel_invocation_count=2,
            jvp_kernel_invocation_count=2,
        ).validate()


def test_worker_config_forbids_fallback_and_regularization() -> None:
    with pytest.raises(HIPResidualJVPWorkerError, match="fallback_or_regularization"):
        HIPResidualJVPWorkerConfig(fallback_allowed=True).validate()
    with pytest.raises(HIPResidualJVPWorkerError, match="fallback_or_regularization"):
        HIPResidualJVPWorkerConfig(regularization_allowed=True).validate()
