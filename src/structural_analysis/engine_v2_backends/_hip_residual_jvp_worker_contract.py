"""Fail-closed production HIP residual/JVP worker contract.

This module binds actual runtime evidence to the physical-residual and accepted-
state Jacobian/JVP directional gate. GitHub-hosted contract tests may exercise the
state machine, but only an actual hardware execution can satisfy the production
path. No CPU diagnostic path, fallback, or regularization can be promoted.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
import hashlib
import json
from types import MappingProxyType
from typing import Any, Final, Literal

import numpy as np

from structural_analysis.solvers.nonlinear.residual_jacobian_consistency import (
    DirectionalConsistencyConfig,
    probe_residual_jacobian_directional_consistency,
    validate_directional_receipt,
)


HIP_RESIDUAL_JVP_WORKER_PROFILE: Final = "g1_production_hip_residual_jvp_worker.v1"
HIP_RESIDUAL_JVP_WORKER_SCHEMA_VERSION: Final = (
    "g1-production-hip-residual-jvp-worker-receipt.v1"
)
HIP_REQUIRED_DEVICE_NODES: Final = ("/dev/kfd", "/dev/dri")

HIPExecutionKind = Literal["hardware", "contract_test"]
ResidualFunction = Callable[[np.ndarray], np.ndarray]
JacobianVectorProduct = Callable[[np.ndarray, np.ndarray], np.ndarray]


class HIPResidualJVPWorkerError(ValueError):
    """Raised when the worker contract is malformed or unsafe."""


@dataclass(frozen=True)
class HIPRuntimeEvidence:
    execution_kind: HIPExecutionKind
    source_commit_sha: str
    binary_sha256: str
    backend_id: str
    device_architecture: str | None
    available_device_nodes: tuple[str, ...]
    hardware_receipt_hash: str | None
    hip_kernel_invocation_count: int
    residual_kernel_invocation_count: int
    jvp_kernel_invocation_count: int
    hip_krylov_solver_used: bool
    accepted_state_tangent_refresh_hip_used: bool
    accepted_state_tangent_refresh_cpu_used: bool
    jvp_rows_retained: bool
    cpu_fallback_used: bool
    regularization_used: bool
    mid_step_d2h_count: int
    runtime_metadata: Mapping[str, Any] = field(
        default_factory=lambda: MappingProxyType({})
    )

    def validate(self) -> None:
        if self.execution_kind not in ("hardware", "contract_test"):
            raise HIPResidualJVPWorkerError("execution_kind_invalid")
        if not _is_commit_sha(self.source_commit_sha):
            raise HIPResidualJVPWorkerError("source_commit_sha_invalid")
        if not _is_hash(self.binary_sha256):
            raise HIPResidualJVPWorkerError("binary_sha256_invalid")
        if not self.backend_id:
            raise HIPResidualJVPWorkerError("backend_id_missing")
        for label, value in (
            ("hip_kernel_invocation_count", self.hip_kernel_invocation_count),
            ("residual_kernel_invocation_count", self.residual_kernel_invocation_count),
            ("jvp_kernel_invocation_count", self.jvp_kernel_invocation_count),
            ("mid_step_d2h_count", self.mid_step_d2h_count),
        ):
            if type(value) is bool or not isinstance(value, int) or value < 0:
                raise HIPResidualJVPWorkerError(f"{label}_invalid")
        if self.execution_kind == "hardware":
            if not self.device_architecture:
                raise HIPResidualJVPWorkerError("device_architecture_missing")
            if not _is_hash(self.hardware_receipt_hash):
                raise HIPResidualJVPWorkerError("hardware_receipt_hash_invalid")
            missing = set(HIP_REQUIRED_DEVICE_NODES) - set(self.available_device_nodes)
            if missing:
                raise HIPResidualJVPWorkerError(
                    "required_device_nodes_missing:" + ",".join(sorted(missing))
                )
        elif self.hardware_receipt_hash is not None:
            raise HIPResidualJVPWorkerError(
                "contract_test_must_not_attach_hardware_receipt"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "execution_kind": self.execution_kind,
            "source_commit_sha": self.source_commit_sha,
            "binary_sha256": self.binary_sha256,
            "backend_id": self.backend_id,
            "device_architecture": self.device_architecture,
            "available_device_nodes": list(self.available_device_nodes),
            "hardware_receipt_hash": self.hardware_receipt_hash,
            "hip_kernel_invocation_count": self.hip_kernel_invocation_count,
            "residual_kernel_invocation_count": self.residual_kernel_invocation_count,
            "jvp_kernel_invocation_count": self.jvp_kernel_invocation_count,
            "hip_krylov_solver_used": self.hip_krylov_solver_used,
            "accepted_state_tangent_refresh_hip_used": (
                self.accepted_state_tangent_refresh_hip_used
            ),
            "accepted_state_tangent_refresh_cpu_used": (
                self.accepted_state_tangent_refresh_cpu_used
            ),
            "jvp_rows_retained": self.jvp_rows_retained,
            "cpu_fallback_used": self.cpu_fallback_used,
            "regularization_used": self.regularization_used,
            "mid_step_d2h_count": self.mid_step_d2h_count,
            "runtime_metadata": _deep_thaw(self.runtime_metadata),
        }


@dataclass(frozen=True)
class HIPResidualJVPWorkerConfig:
    require_hip_krylov_solver: bool = True
    require_retained_jvp_rows: bool = True
    require_accepted_state_hip_refresh: bool = True
    maximum_mid_step_d2h_count: int = 0
    fallback_allowed: bool = False
    regularization_allowed: bool = False
    directional_config: DirectionalConsistencyConfig = field(
        default_factory=DirectionalConsistencyConfig
    )

    def validate(self) -> None:
        if self.fallback_allowed or self.regularization_allowed:
            raise HIPResidualJVPWorkerError(
                "fallback_or_regularization_forbidden"
            )
        if (
            type(self.maximum_mid_step_d2h_count) is bool
            or not isinstance(self.maximum_mid_step_d2h_count, int)
            or self.maximum_mid_step_d2h_count < 0
        ):
            raise HIPResidualJVPWorkerError(
                "maximum_mid_step_d2h_count_invalid"
            )
        self.directional_config.validate()


@dataclass(frozen=True)
class HIPResidualJVPWorkerReceipt:
    source_commit_sha: str
    backend_id: str
    binary_sha256: str
    runtime: Mapping[str, Any]
    directional_receipt: Mapping[str, Any]
    blockers: tuple[str, ...]
    contract_pass: bool
    directional_gate_passed: bool
    hardware_execution_proven: bool
    production_path_ready: bool
    cpu_fallback_used: bool
    regularization_used: bool
    receipt_hash: str
    schema_version: str = HIP_RESIDUAL_JVP_WORKER_SCHEMA_VERSION
    profile: str = HIP_RESIDUAL_JVP_WORKER_PROFILE
    numerical_authority: str = "diagnostic_only"
    engineering_authority: str = "none"
    release_authority: str = "none"
    claim_boundary: str = (
        "This receipt can prove a bounded production HIP residual/JVP worker path only "
        "when backed by actual hardware evidence, physical residual/JVP directional "
        "consistency, retained JVP rows, accepted-state HIP tangent refresh, HIP Krylov, "
        "and fallback-zero execution. It does not prove G1 full-load/full-mesh closure, "
        "material breadth, engineering recovery, design authority, commercial readiness, "
        "or performance advantage."
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "profile": self.profile,
            "source_commit_sha": self.source_commit_sha,
            "backend_id": self.backend_id,
            "binary_sha256": self.binary_sha256,
            "runtime": _deep_thaw(self.runtime),
            "directional_receipt": _deep_thaw(self.directional_receipt),
            "blockers": list(self.blockers),
            "contract_pass": self.contract_pass,
            "directional_gate_passed": self.directional_gate_passed,
            "hardware_execution_proven": self.hardware_execution_proven,
            "production_path_ready": self.production_path_ready,
            "cpu_fallback_used": self.cpu_fallback_used,
            "regularization_used": self.regularization_used,
            "numerical_authority": self.numerical_authority,
            "engineering_authority": self.engineering_authority,
            "release_authority": self.release_authority,
            "claim_boundary": self.claim_boundary,
            "receipt_hash": self.receipt_hash,
        }


def execute_hip_residual_jvp_worker_probe(
    *,
    runtime: HIPRuntimeEvidence,
    accepted_state: Sequence[float] | np.ndarray,
    direction: Sequence[float] | np.ndarray,
    residual: ResidualFunction,
    jacobian_vector_product: JacobianVectorProduct,
    config: HIPResidualJVPWorkerConfig | None = None,
) -> HIPResidualJVPWorkerReceipt:
    """Run the physical directional gate and assess production HIP eligibility."""

    cfg = config or HIPResidualJVPWorkerConfig()
    cfg.validate()
    runtime.validate()
    directional = probe_residual_jacobian_directional_consistency(
        source_commit_sha=runtime.source_commit_sha,
        operator_id=HIP_RESIDUAL_JVP_WORKER_PROFILE,
        backend_id=runtime.backend_id,
        accepted_state=accepted_state,
        direction=direction,
        residual=residual,
        jacobian_vector_product=jacobian_vector_product,
        config=cfg.directional_config,
    )
    validate_directional_receipt(directional)

    blockers: list[str] = []
    if runtime.execution_kind != "hardware":
        blockers.append("actual_hip_hardware_execution_missing")
    if runtime.hip_kernel_invocation_count <= 0:
        blockers.append("hip_kernel_invocation_missing")
    if runtime.residual_kernel_invocation_count <= 0:
        blockers.append("hip_residual_kernel_invocation_missing")
    if runtime.jvp_kernel_invocation_count <= 0:
        blockers.append("hip_jvp_kernel_invocation_missing")
    if cfg.require_hip_krylov_solver and not runtime.hip_krylov_solver_used:
        blockers.append("hip_krylov_solver_not_used")
    if cfg.require_retained_jvp_rows and not runtime.jvp_rows_retained:
        blockers.append("jvp_rows_not_retained")
    if cfg.require_accepted_state_hip_refresh:
        if not runtime.accepted_state_tangent_refresh_hip_used:
            blockers.append("accepted_state_tangent_refresh_not_on_hip")
        if runtime.accepted_state_tangent_refresh_cpu_used:
            blockers.append("accepted_state_tangent_refresh_used_cpu")
    if runtime.cpu_fallback_used:
        blockers.append("cpu_fallback_used")
    if runtime.regularization_used:
        blockers.append("regularization_used")
    if runtime.mid_step_d2h_count > cfg.maximum_mid_step_d2h_count:
        blockers.append("mid_step_d2h_limit_exceeded")
    if not directional.consistent_residual_jacobian_newton_gate_passed:
        blockers.append("physical_residual_jacobian_directional_gate_failed")
    blockers = list(dict.fromkeys(blockers))
    production_ready = not blockers
    runtime_payload = MappingProxyType(runtime.to_dict())
    directional_payload = MappingProxyType(directional.to_dict())
    provisional = {
        "schema_version": HIP_RESIDUAL_JVP_WORKER_SCHEMA_VERSION,
        "profile": HIP_RESIDUAL_JVP_WORKER_PROFILE,
        "source_commit_sha": runtime.source_commit_sha,
        "backend_id": runtime.backend_id,
        "binary_sha256": runtime.binary_sha256,
        "runtime": _deep_thaw(runtime_payload),
        "directional_receipt": _deep_thaw(directional_payload),
        "blockers": blockers,
        "contract_pass": True,
        "directional_gate_passed": (
            directional.consistent_residual_jacobian_newton_gate_passed
        ),
        "hardware_execution_proven": runtime.execution_kind == "hardware",
        "production_path_ready": production_ready,
        "cpu_fallback_used": runtime.cpu_fallback_used,
        "regularization_used": runtime.regularization_used,
        "numerical_authority": "diagnostic_only",
        "engineering_authority": "none",
        "release_authority": "none",
    }
    return HIPResidualJVPWorkerReceipt(
        source_commit_sha=runtime.source_commit_sha,
        backend_id=runtime.backend_id,
        binary_sha256=runtime.binary_sha256,
        runtime=runtime_payload,
        directional_receipt=directional_payload,
        blockers=tuple(blockers),
        contract_pass=True,
        directional_gate_passed=(
            directional.consistent_residual_jacobian_newton_gate_passed
        ),
        hardware_execution_proven=runtime.execution_kind == "hardware",
        production_path_ready=production_ready,
        cpu_fallback_used=runtime.cpu_fallback_used,
        regularization_used=runtime.regularization_used,
        receipt_hash=_json_hash(provisional),
    )


def validate_hip_residual_jvp_worker_receipt(
    receipt: HIPResidualJVPWorkerReceipt,
) -> None:
    if type(receipt) is not HIPResidualJVPWorkerReceipt:
        raise HIPResidualJVPWorkerError("receipt_type_invalid")
    if receipt.schema_version != HIP_RESIDUAL_JVP_WORKER_SCHEMA_VERSION:
        raise HIPResidualJVPWorkerError("receipt_schema_invalid")
    if receipt.profile != HIP_RESIDUAL_JVP_WORKER_PROFILE:
        raise HIPResidualJVPWorkerError("receipt_profile_invalid")
    if receipt.contract_pass is not True:
        raise HIPResidualJVPWorkerError("receipt_contract_not_passed")
    if receipt.numerical_authority != "diagnostic_only":
        raise HIPResidualJVPWorkerError("numerical_authority_invalid")
    if receipt.engineering_authority != "none" or receipt.release_authority != "none":
        raise HIPResidualJVPWorkerError("product_authority_invalid")
    if receipt.production_path_ready != (len(receipt.blockers) == 0):
        raise HIPResidualJVPWorkerError("production_path_truth_mismatch")
    if receipt.production_path_ready and not receipt.hardware_execution_proven:
        raise HIPResidualJVPWorkerError("production_ready_without_hardware")
    payload = receipt.to_dict()
    observed_hash = payload.pop("receipt_hash")
    payload.pop("claim_boundary", None)
    if observed_hash != _json_hash(payload):
        raise HIPResidualJVPWorkerError("receipt_hash_mismatch")


def _deep_thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _deep_thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_deep_thaw(item) for item in value]
    return value


def _json_hash(payload: Mapping[str, Any]) -> str:
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(serialized).hexdigest()


def _is_commit_sha(value: str) -> bool:
    return len(value) == 40 and all(
        character in "0123456789abcdef" for character in value
    )


def _is_hash(value: object) -> bool:
    return (
        isinstance(value, str)
        and value.startswith("sha256:")
        and len(value) == 71
        and all(character in "0123456789abcdef" for character in value[7:])
    )
