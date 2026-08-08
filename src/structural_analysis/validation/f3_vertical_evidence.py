"""Fail-closed evidence gate for staged Frame3D and dynamics promotion.

The gate deliberately validates evidence identity and ordering only.  It does not
run, sign, or independently verify a solver result.  In particular, an external
V&V artifact is insufficient until an independent signature-verifier receipt is
bound to it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal, Sequence


F3_STAGE_ORDER: Final[tuple[str, ...]] = (
    "frame3d_linear",
    "frame3d_load_control",
    "frame3d_direct_control",
    "frame3d_stateful_material",
    "modal_buckling",
    "sdof_authenticated_transient",
    "mdof_linear_transient",
    "nonlinear_mdof",
    "shell",
    "contact",
)

F3_REQUIRED_SURFACES: Final[tuple[str, ...]] = (
    "model_ir",
    "solver",
    "result_ir",
    "recovery",
    "checkpoint",
    "workbench",
    "benchmark",
    "platform",
    "external_vv",
)

_SHA256_PREFIX = "sha256:"
_EXTERNAL_VERIFIER_AUTHORITY = "independent_external_vv_signature_verifier"


def _is_hex(value: str, length: int) -> bool:
    return len(value) == length and all(character in "0123456789abcdef" for character in value)


def _is_source_commit_sha(value: str) -> bool:
    return _is_hex(value, 40)


def _is_sha256(value: str | None) -> bool:
    return bool(
        value
        and value.startswith(_SHA256_PREFIX)
        and _is_hex(value.removeprefix(_SHA256_PREFIX), 64)
    )


@dataclass(frozen=True)
class F3Evidence:
    """One content-addressed evidence item for a required product surface."""

    surface: str
    status: Literal["verified", "blocked"]
    artifact_sha256: str | None


@dataclass(frozen=True)
class ExternalVVSignatureVerification:
    """Adapter output expected from an independent signature verifier."""

    status: Literal["verified", "unverified", "absent"]
    authority: str | None = None
    signer_id: str | None = None
    signed_artifact_sha256: str | None = None
    verification_receipt_sha256: str | None = None


@dataclass(frozen=True)
class F3StageGateReceipt:
    """Deterministic promotion result for one stage in the F3 sequence."""

    schema: Literal["f3-vertical-evidence-gate.v1"]
    stage: str
    stage_index: int
    source_commit_sha: str
    required_surfaces: tuple[str, ...]
    verified_surfaces: tuple[str, ...]
    evidence_artifact_sha256: tuple[tuple[str, str], ...]
    predecessor_stage: str | None
    predecessor_receipt_sha256: str | None
    external_vv_signature_status: Literal["verified", "unverified", "absent"]
    blockers: tuple[str, ...]
    public_product_promotion_passed: bool


def evaluate_f3_stage_gate(
    *,
    stage: str,
    source_commit_sha: str,
    evidence: Sequence[F3Evidence],
    external_vv_signature: ExternalVVSignatureVerification | None = None,
    predecessor_receipt: F3StageGateReceipt | None = None,
    predecessor_receipt_sha256: str | None = None,
) -> F3StageGateReceipt:
    """Evaluate the complete vertical evidence set for ``stage``.

    Later stages require a passing receipt from the immediately preceding stage,
    bound to the same source commit.  All failures become stable blocker codes;
    no missing or partial evidence is treated as promotion-ready.
    """

    if stage not in F3_STAGE_ORDER:
        raise ValueError(f"unknown F3 stage: {stage}")

    blockers: list[str] = []
    if not _is_source_commit_sha(source_commit_sha):
        blockers.append("source_commit_sha_invalid")

    evidence_by_surface: dict[str, F3Evidence] = {}
    duplicate_surfaces: set[str] = set()
    for item in evidence:
        if item.surface not in F3_REQUIRED_SURFACES:
            blockers.append(f"unknown_evidence_surface:{item.surface}")
            continue
        if item.surface in evidence_by_surface:
            duplicate_surfaces.add(item.surface)
            continue
        evidence_by_surface[item.surface] = item

    blockers.extend(
        f"duplicate_evidence_surface:{surface}" for surface in sorted(duplicate_surfaces)
    )

    verified_surfaces: list[str] = []
    artifact_bindings: list[tuple[str, str]] = []
    for surface in F3_REQUIRED_SURFACES:
        item = evidence_by_surface.get(surface)
        if item is None:
            blockers.append(f"missing_evidence_surface:{surface}")
            continue
        if item.status != "verified":
            blockers.append(f"evidence_not_verified:{surface}")
        if not _is_sha256(item.artifact_sha256):
            blockers.append(f"evidence_artifact_sha256_invalid:{surface}")
        if item.status == "verified" and _is_sha256(item.artifact_sha256):
            verified_surfaces.append(surface)
            artifact_bindings.append((surface, item.artifact_sha256 or ""))

    signature = external_vv_signature or ExternalVVSignatureVerification(status="absent")
    external_vv_artifact = evidence_by_surface.get("external_vv")
    if signature.status == "absent":
        blockers.append("external_vv_signature_verification_missing")
    elif signature.status != "verified":
        blockers.append("external_vv_signature_verification_unverified")
    else:
        if signature.authority != _EXTERNAL_VERIFIER_AUTHORITY:
            blockers.append("external_vv_signature_verifier_authority_invalid")
        if not signature.signer_id:
            blockers.append("external_vv_signature_signer_id_missing")
        if not _is_sha256(signature.verification_receipt_sha256):
            blockers.append("external_vv_signature_receipt_sha256_invalid")
        if not _is_sha256(signature.signed_artifact_sha256):
            blockers.append("external_vv_signed_artifact_sha256_invalid")
        elif (
            external_vv_artifact is None
            or signature.signed_artifact_sha256 != external_vv_artifact.artifact_sha256
        ):
            blockers.append("external_vv_signature_artifact_binding_mismatch")

    stage_index = F3_STAGE_ORDER.index(stage)
    expected_predecessor = F3_STAGE_ORDER[stage_index - 1] if stage_index else None
    if expected_predecessor is None:
        if predecessor_receipt is not None or predecessor_receipt_sha256 is not None:
            blockers.append("unexpected_predecessor_receipt")
    elif predecessor_receipt is None:
        blockers.append("predecessor_stage_receipt_missing")
    else:
        if predecessor_receipt.stage != expected_predecessor:
            blockers.append("predecessor_stage_order_mismatch")
        if not predecessor_receipt.public_product_promotion_passed:
            blockers.append("predecessor_stage_not_closed")
        if predecessor_receipt.source_commit_sha != source_commit_sha:
            blockers.append("predecessor_source_commit_mismatch")
        if not _is_sha256(predecessor_receipt_sha256):
            blockers.append("predecessor_receipt_sha256_invalid")

    unique_blockers = tuple(dict.fromkeys(blockers))
    return F3StageGateReceipt(
        schema="f3-vertical-evidence-gate.v1",
        stage=stage,
        stage_index=stage_index,
        source_commit_sha=source_commit_sha,
        required_surfaces=F3_REQUIRED_SURFACES,
        verified_surfaces=tuple(verified_surfaces),
        evidence_artifact_sha256=tuple(artifact_bindings),
        predecessor_stage=expected_predecessor,
        predecessor_receipt_sha256=predecessor_receipt_sha256,
        external_vv_signature_status=signature.status,
        blockers=unique_blockers,
        public_product_promotion_passed=not unique_blockers,
    )


__all__ = [
    "F3_STAGE_ORDER",
    "F3_REQUIRED_SURFACES",
    "F3Evidence",
    "ExternalVVSignatureVerification",
    "F3StageGateReceipt",
    "evaluate_f3_stage_gate",
]
