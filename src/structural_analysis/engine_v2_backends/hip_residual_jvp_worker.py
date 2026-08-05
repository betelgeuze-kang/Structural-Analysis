"""Hardware-evidence hardening for the HIP residual/JVP worker contract.

The contract state machine is retained in ``_hip_residual_jvp_worker_contract``.
This public module adds checks that cannot be satisfied by merely typing device
node names and arbitrary hashes into a Python object on a non-HIP host.
"""

from __future__ import annotations

from pathlib import Path
import re
from typing import Final

from . import _hip_residual_jvp_worker_contract as _contract


HIP_RESIDUAL_JVP_WORKER_PROFILE = _contract.HIP_RESIDUAL_JVP_WORKER_PROFILE
HIP_RESIDUAL_JVP_WORKER_SCHEMA_VERSION = (
    _contract.HIP_RESIDUAL_JVP_WORKER_SCHEMA_VERSION
)
HIP_REQUIRED_DEVICE_NODES = _contract.HIP_REQUIRED_DEVICE_NODES
HIPExecutionKind = _contract.HIPExecutionKind
ResidualFunction = _contract.ResidualFunction
JacobianVectorProduct = _contract.JacobianVectorProduct
HIPResidualJVPWorkerError = _contract.HIPResidualJVPWorkerError
HIPResidualJVPWorkerConfig = _contract.HIPResidualJVPWorkerConfig
HIPResidualJVPWorkerReceipt = _contract.HIPResidualJVPWorkerReceipt
execute_hip_residual_jvp_worker_probe = (
    _contract.execute_hip_residual_jvp_worker_probe
)
validate_hip_residual_jvp_worker_receipt = (
    _contract.validate_hip_residual_jvp_worker_receipt
)

_ZERO_HASH: Final = "sha256:" + "0" * 64
_GFX_ARCHITECTURE = re.compile(r"gfx[0-9a-f]{3,5}")
_FORBIDDEN_HARDWARE_BACKEND_MARKERS = ("contract_test", "synthetic", "mock")


def _local_hip_device_nodes_valid() -> bool:
    """Probe the current host rather than trusting declared path strings."""

    kfd = Path("/dev/kfd")
    dri = Path("/dev/dri")
    return bool(
        kfd.exists()
        and kfd.is_char_device()
        and dri.exists()
        and dri.is_dir()
    )


class HIPRuntimeEvidence(_contract.HIPRuntimeEvidence):
    """Runtime evidence that requires a real local HIP device for hardware mode."""

    def validate(self) -> None:
        super().validate()
        if self.execution_kind != "hardware":
            return
        if not _local_hip_device_nodes_valid():
            raise HIPResidualJVPWorkerError(
                "local_hip_device_probe_failed:/dev/kfd,/dev/dri"
            )
        architecture = self.device_architecture or ""
        if _GFX_ARCHITECTURE.fullmatch(architecture) is None:
            raise HIPResidualJVPWorkerError("device_architecture_invalid")
        if self.binary_sha256 == _ZERO_HASH:
            raise HIPResidualJVPWorkerError("hardware_binary_hash_placeholder_forbidden")
        if self.hardware_receipt_hash == _ZERO_HASH:
            raise HIPResidualJVPWorkerError(
                "hardware_receipt_hash_placeholder_forbidden"
            )
        backend = self.backend_id.lower()
        if any(marker in backend for marker in _FORBIDDEN_HARDWARE_BACKEND_MARKERS):
            raise HIPResidualJVPWorkerError("hardware_backend_id_not_production")
        if self.hip_kernel_invocation_count < (
            self.residual_kernel_invocation_count + self.jvp_kernel_invocation_count
        ):
            raise HIPResidualJVPWorkerError(
                "hip_kernel_invocation_count_inconsistent"
            )


__all__ = [
    "HIP_RESIDUAL_JVP_WORKER_PROFILE",
    "HIP_RESIDUAL_JVP_WORKER_SCHEMA_VERSION",
    "HIP_REQUIRED_DEVICE_NODES",
    "HIPExecutionKind",
    "ResidualFunction",
    "JacobianVectorProduct",
    "HIPResidualJVPWorkerError",
    "HIPRuntimeEvidence",
    "HIPResidualJVPWorkerConfig",
    "HIPResidualJVPWorkerReceipt",
    "execute_hip_residual_jvp_worker_probe",
    "validate_hip_residual_jvp_worker_receipt",
]
