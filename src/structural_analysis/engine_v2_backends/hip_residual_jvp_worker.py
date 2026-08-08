"""Hardware-evidence hardening for the HIP residual/JVP worker contract.

The contract state machine is retained in ``_hip_residual_jvp_worker_contract``.
This public module adds checks that cannot be satisfied by merely typing device
node names and arbitrary hashes into a Python object on a non-HIP host.

A Python callback probe cannot independently prove that the residual/JVP values
were produced by the declared HIP binary. Consequently, even a complete local
hardware claim remains a diagnostic candidate here. A separate signed external
attestation/promotion boundary is required before hardware execution or a
production path can be marked proven.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
import re
from typing import Final

import numpy as np

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
HIPProductionLifecycleEvidence = _contract.HIPProductionLifecycleEvidence
HIPResidualJVPWorkerConfig = _contract.HIPResidualJVPWorkerConfig
HIPResidualJVPWorkerReceipt = _contract.HIPResidualJVPWorkerReceipt

_ZERO_HASH: Final = "sha256:" + "0" * 64
_GFX_ARCHITECTURE = re.compile(r"gfx[0-9a-f]{3,5}")
_FORBIDDEN_HARDWARE_BACKEND_MARKERS = ("contract_test", "synthetic", "mock")
_EXTERNAL_ATTESTATION_BLOCKERS: Final = (
    "hardware_execution_attestation_unverified",
    "independent_hardware_operator_attestation_missing",
)


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


def _retain_external_attestation_boundary(
    receipt: HIPResidualJVPWorkerReceipt,
) -> HIPResidualJVPWorkerReceipt:
    runtime = receipt.runtime
    if runtime.get("execution_kind") != "hardware":
        return receipt
    blockers = list(receipt.blockers)
    for blocker in _EXTERNAL_ATTESTATION_BLOCKERS:
        if blocker not in blockers:
            blockers.append(blocker)
    provisional = receipt.to_dict()
    provisional.pop("claim_boundary", None)
    provisional.pop("receipt_hash", None)
    provisional["blockers"] = blockers
    provisional["hardware_execution_proven"] = False
    provisional["production_path_ready"] = False
    return replace(
        receipt,
        blockers=tuple(blockers),
        hardware_execution_proven=False,
        production_path_ready=False,
        receipt_hash=_contract._json_hash(provisional),
    )


def validate_hip_residual_jvp_worker_receipt(
    receipt: HIPResidualJVPWorkerReceipt,
) -> None:
    """Validate the supported public receipt without accepting private promotion."""

    _contract.validate_hip_residual_jvp_worker_receipt(receipt)
    if receipt.runtime.get("execution_kind") != "hardware":
        return
    if any(blocker not in receipt.blockers for blocker in _EXTERNAL_ATTESTATION_BLOCKERS):
        raise HIPResidualJVPWorkerError(
            "public_hardware_receipt_external_attestation_boundary_missing"
        )
    if receipt.hardware_execution_proven or receipt.production_path_ready:
        raise HIPResidualJVPWorkerError(
            "public_hardware_promotion_forbidden_without_external_attestation"
        )


def execute_hip_residual_jvp_worker_probe(
    *,
    runtime: HIPRuntimeEvidence,
    accepted_state: Sequence[float] | np.ndarray,
    direction: Sequence[float] | np.ndarray,
    residual: ResidualFunction,
    jacobian_vector_product: JacobianVectorProduct,
    config: HIPResidualJVPWorkerConfig | None = None,
) -> HIPResidualJVPWorkerReceipt:
    """Assess the local HIP contract without granting external proof authority."""

    receipt = _contract.execute_hip_residual_jvp_worker_probe(
        runtime=runtime,
        accepted_state=accepted_state,
        direction=direction,
        residual=residual,
        jacobian_vector_product=jacobian_vector_product,
        config=config,
    )
    hardened = _retain_external_attestation_boundary(receipt)
    validate_hip_residual_jvp_worker_receipt(hardened)
    return hardened


__all__ = [
    "HIP_RESIDUAL_JVP_WORKER_PROFILE",
    "HIP_RESIDUAL_JVP_WORKER_SCHEMA_VERSION",
    "HIP_REQUIRED_DEVICE_NODES",
    "HIPExecutionKind",
    "ResidualFunction",
    "JacobianVectorProduct",
    "HIPResidualJVPWorkerError",
    "HIPProductionLifecycleEvidence",
    "HIPRuntimeEvidence",
    "HIPResidualJVPWorkerConfig",
    "HIPResidualJVPWorkerReceipt",
    "execute_hip_residual_jvp_worker_probe",
    "validate_hip_residual_jvp_worker_receipt",
]
