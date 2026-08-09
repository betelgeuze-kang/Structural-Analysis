"""Fail-closed evidence gate for staged Frame3D and dynamics promotion.

The gate deliberately validates evidence identity and ordering only.  It does not
run, sign, or independently verify a solver result.  An external V&V artifact is
normally insufficient until an independent signature-verifier receipt is bound
to it.  A user-authorized verifier waiver is represented explicitly; it never
masquerades as a verified signature.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final, Literal, Mapping, Sequence


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
_SIGNATURE_STATUSES: Final[tuple[str, ...]] = (
    "verified",
    "unverified",
    "absent",
    "waived",
)
_GATE_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "schema",
        "stage",
        "stage_index",
        "source_commit_sha",
        "required_surfaces",
        "verified_surfaces",
        "evidence_artifact_sha256",
        "predecessor_stage",
        "predecessor_receipt_sha256",
        "external_vv_signature_status",
        "technical_blockers",
        "promotion_blockers",
        "blockers",
        "vertical_stage_contract_passed",
        "public_product_promotion_passed",
    }
)


def _is_hex(value: str, length: int) -> bool:
    return len(value) == length and all(
        character in "0123456789abcdef" for character in value
    )


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

    status: Literal["verified", "unverified", "absent", "waived"]
    authority: str | None = None
    signer_id: str | None = None
    signed_artifact_sha256: str | None = None
    verification_receipt_sha256: str | None = None
    waiver_reason: str | None = None


@dataclass(frozen=True)
class F3StageGateReceipt:
    """Deterministic promotion result for one stage in the F3 sequence."""

    schema: Literal["f3-vertical-evidence-gate.v2"]
    stage: str
    stage_index: int
    source_commit_sha: str
    required_surfaces: tuple[str, ...]
    verified_surfaces: tuple[str, ...]
    evidence_artifact_sha256: tuple[tuple[str, str], ...]
    predecessor_stage: str | None
    predecessor_receipt_sha256: str | None
    external_vv_signature_status: Literal["verified", "unverified", "absent", "waived"]
    technical_blockers: tuple[str, ...]
    promotion_blockers: tuple[str, ...]
    blockers: tuple[str, ...]
    vertical_stage_contract_passed: bool
    public_product_promotion_passed: bool

    @property
    def status(self) -> Literal["ready", "partial", "blocked"]:
        if self.public_product_promotion_passed:
            return "ready"
        if self.vertical_stage_contract_passed:
            return "partial"
        return "blocked"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "stage": self.stage,
            "stage_index": self.stage_index,
            "source_commit_sha": self.source_commit_sha,
            "required_surfaces": list(self.required_surfaces),
            "verified_surfaces": list(self.verified_surfaces),
            "evidence_artifact_sha256": dict(self.evidence_artifact_sha256),
            "predecessor_stage": self.predecessor_stage,
            "predecessor_receipt_sha256": self.predecessor_receipt_sha256,
            "external_vv_signature_status": self.external_vv_signature_status,
            "technical_blockers": list(self.technical_blockers),
            "promotion_blockers": list(self.promotion_blockers),
            "blockers": list(self.blockers),
            "vertical_stage_contract_passed": self.vertical_stage_contract_passed,
            "public_product_promotion_passed": self.public_product_promotion_passed,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> F3StageGateReceipt:
        """Deserialize a v2 gate only after replaying its structural invariants."""

        if set(payload) != _GATE_FIELDS:
            raise ValueError("f3_stage_gate_fields_invalid")
        if payload.get("schema") != "f3-vertical-evidence-gate.v2":
            raise ValueError("f3_stage_gate_schema_invalid")

        stage = payload.get("stage")
        stage_index = payload.get("stage_index")
        if not isinstance(stage, str) or stage not in F3_STAGE_ORDER:
            raise ValueError("f3_stage_gate_stage_invalid")
        if type(stage_index) is not int or stage_index != F3_STAGE_ORDER.index(stage):
            raise ValueError("f3_stage_gate_stage_index_invalid")

        source_commit_sha = payload.get("source_commit_sha")
        if not isinstance(source_commit_sha, str) or not _is_source_commit_sha(
            source_commit_sha
        ):
            raise ValueError("f3_stage_gate_source_commit_sha_invalid")

        def _string_tuple(name: str) -> tuple[str, ...]:
            value = payload.get(name)
            if not isinstance(value, (list, tuple)) or any(
                not isinstance(item, str) or not item for item in value
            ):
                raise ValueError(f"f3_stage_gate_{name}_invalid")
            return tuple(value)

        required_surfaces = _string_tuple("required_surfaces")
        if required_surfaces != F3_REQUIRED_SURFACES:
            raise ValueError("f3_stage_gate_required_surfaces_invalid")
        verified_surfaces = _string_tuple("verified_surfaces")
        if len(set(verified_surfaces)) != len(
            verified_surfaces
        ) or verified_surfaces != tuple(
            surface for surface in F3_REQUIRED_SURFACES if surface in verified_surfaces
        ):
            raise ValueError("f3_stage_gate_verified_surfaces_invalid")

        bindings = payload.get("evidence_artifact_sha256")
        if not isinstance(bindings, Mapping):
            raise ValueError("f3_stage_gate_evidence_bindings_invalid")
        if set(bindings) != set(verified_surfaces) or any(
            not isinstance(surface, str)
            or not isinstance(artifact_sha256, str)
            or not _is_sha256(artifact_sha256)
            for surface, artifact_sha256 in bindings.items()
        ):
            raise ValueError("f3_stage_gate_evidence_bindings_invalid")

        expected_predecessor = F3_STAGE_ORDER[stage_index - 1] if stage_index else None
        predecessor_stage = payload.get("predecessor_stage")
        predecessor_receipt_sha256 = payload.get("predecessor_receipt_sha256")
        if predecessor_stage != expected_predecessor:
            raise ValueError("f3_stage_gate_predecessor_stage_invalid")
        if predecessor_receipt_sha256 is not None and (
            not isinstance(predecessor_receipt_sha256, str)
            or not _is_sha256(predecessor_receipt_sha256)
        ):
            raise ValueError("f3_stage_gate_predecessor_receipt_sha256_invalid")
        if expected_predecessor is None and predecessor_receipt_sha256 is not None:
            raise ValueError("f3_stage_gate_predecessor_receipt_unexpected")

        signature_status = payload.get("external_vv_signature_status")
        if signature_status not in _SIGNATURE_STATUSES:
            raise ValueError("f3_stage_gate_signature_status_invalid")

        technical_blockers = _string_tuple("technical_blockers")
        promotion_blockers = _string_tuple("promotion_blockers")
        blockers = _string_tuple("blockers")
        if len(set(technical_blockers)) != len(technical_blockers) or len(
            set(promotion_blockers)
        ) != len(promotion_blockers):
            raise ValueError("f3_stage_gate_blocker_duplicates")
        expected_blockers = tuple(
            dict.fromkeys((*technical_blockers, *promotion_blockers))
        )
        if blockers != expected_blockers:
            raise ValueError("f3_stage_gate_blockers_inconsistent")

        vertical_stage_contract_passed = payload.get("vertical_stage_contract_passed")
        public_product_promotion_passed = payload.get("public_product_promotion_passed")
        if (
            type(vertical_stage_contract_passed) is not bool
            or type(public_product_promotion_passed) is not bool
        ):
            raise ValueError("f3_stage_gate_pass_type_invalid")
        if vertical_stage_contract_passed is not (not technical_blockers):
            raise ValueError("f3_stage_gate_vertical_pass_inconsistent")
        if public_product_promotion_passed is not (
            vertical_stage_contract_passed and not promotion_blockers
        ):
            raise ValueError("f3_stage_gate_public_pass_inconsistent")
        if (
            expected_predecessor is not None
            and vertical_stage_contract_passed
            and predecessor_receipt_sha256 is None
        ):
            raise ValueError("f3_stage_gate_predecessor_receipt_sha256_missing")

        return cls(
            schema="f3-vertical-evidence-gate.v2",
            stage=stage,
            stage_index=stage_index,
            source_commit_sha=source_commit_sha,
            required_surfaces=required_surfaces,
            verified_surfaces=verified_surfaces,
            evidence_artifact_sha256=tuple(
                (surface, bindings[surface]) for surface in verified_surfaces
            ),
            predecessor_stage=predecessor_stage,
            predecessor_receipt_sha256=predecessor_receipt_sha256,
            external_vv_signature_status=signature_status,
            technical_blockers=technical_blockers,
            promotion_blockers=promotion_blockers,
            blockers=blockers,
            vertical_stage_contract_passed=vertical_stage_contract_passed,
            public_product_promotion_passed=public_product_promotion_passed,
        )


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

    Later stages require a technically passing receipt from the immediately
    preceding stage, bound to the same source commit. Technical closure and
    public-product promotion are independent axes: valid waivers can close the
    former but never the latter. All failures become stable blocker codes.
    """

    if stage not in F3_STAGE_ORDER:
        raise ValueError(f"unknown F3 stage: {stage}")

    technical_blockers: list[str] = []
    promotion_blockers: list[str] = []
    if not _is_source_commit_sha(source_commit_sha):
        technical_blockers.append("source_commit_sha_invalid")

    evidence_by_surface: dict[str, F3Evidence] = {}
    duplicate_surfaces: set[str] = set()
    for item in evidence:
        if item.surface not in F3_REQUIRED_SURFACES:
            technical_blockers.append(f"unknown_evidence_surface:{item.surface}")
            continue
        if item.surface in evidence_by_surface:
            duplicate_surfaces.add(item.surface)
            continue
        evidence_by_surface[item.surface] = item

    technical_blockers.extend(
        f"duplicate_evidence_surface:{surface}"
        for surface in sorted(duplicate_surfaces)
    )

    verified_surfaces: list[str] = []
    artifact_bindings: list[tuple[str, str]] = []
    for surface in F3_REQUIRED_SURFACES:
        item = evidence_by_surface.get(surface)
        if item is None:
            technical_blockers.append(f"missing_evidence_surface:{surface}")
            continue
        if item.status != "verified":
            technical_blockers.append(f"evidence_not_verified:{surface}")
        if not _is_sha256(item.artifact_sha256):
            technical_blockers.append(f"evidence_artifact_sha256_invalid:{surface}")
        if item.status == "verified" and _is_sha256(item.artifact_sha256):
            verified_surfaces.append(surface)
            artifact_bindings.append((surface, item.artifact_sha256 or ""))

    signature = external_vv_signature or ExternalVVSignatureVerification(
        status="absent"
    )
    external_vv_artifact = evidence_by_surface.get("external_vv")
    if signature.status == "waived":
        if signature.authority != "user_authorized_signature_verifier_waiver":
            technical_blockers.append("external_vv_signature_waiver_authority_invalid")
        if not signature.waiver_reason:
            technical_blockers.append("external_vv_signature_waiver_reason_missing")
        if external_vv_artifact is None or not _is_sha256(
            external_vv_artifact.artifact_sha256
        ):
            technical_blockers.append("external_vv_signature_waiver_artifact_missing")
        if not any(
            blocker.startswith("external_vv_signature_waiver_")
            for blocker in technical_blockers
        ):
            promotion_blockers.append("external_vv_signature_verification_waived")
    elif signature.status == "absent":
        promotion_blockers.append("external_vv_signature_verification_missing")
    elif signature.status != "verified":
        promotion_blockers.append("external_vv_signature_verification_unverified")
    else:
        if signature.authority != _EXTERNAL_VERIFIER_AUTHORITY:
            promotion_blockers.append(
                "external_vv_signature_verifier_authority_invalid"
            )
        if not signature.signer_id:
            promotion_blockers.append("external_vv_signature_signer_id_missing")
        if not _is_sha256(signature.verification_receipt_sha256):
            promotion_blockers.append("external_vv_signature_receipt_sha256_invalid")
        if not _is_sha256(signature.signed_artifact_sha256):
            promotion_blockers.append("external_vv_signed_artifact_sha256_invalid")
        elif (
            external_vv_artifact is None
            or signature.signed_artifact_sha256 != external_vv_artifact.artifact_sha256
        ):
            promotion_blockers.append("external_vv_signature_artifact_binding_mismatch")

    # No production adapter currently binds the exact Planar product-replay and
    # independent V&V receipts required for F3 promotion.  Deliberately do not
    # accept caller-supplied booleans or hashes here: a future adapter must verify
    # canonical paths, schemas, source epochs, and claims in a separate authority
    # review before these blockers can be removed.
    promotion_blockers.extend(
        (
            "planar_product_replay_prerequisite_not_bound",
            "planar_external_vv_prerequisite_not_bound",
        )
    )

    stage_index = F3_STAGE_ORDER.index(stage)
    expected_predecessor = F3_STAGE_ORDER[stage_index - 1] if stage_index else None
    if expected_predecessor is None:
        if predecessor_receipt is not None or predecessor_receipt_sha256 is not None:
            technical_blockers.append("unexpected_predecessor_receipt")
    elif predecessor_receipt is None:
        technical_blockers.append("predecessor_stage_receipt_missing")
    else:
        if predecessor_receipt.stage != expected_predecessor:
            technical_blockers.append("predecessor_stage_order_mismatch")
        if not predecessor_receipt.vertical_stage_contract_passed:
            technical_blockers.append("predecessor_stage_not_closed")
        if not predecessor_receipt.public_product_promotion_passed:
            promotion_blockers.append("predecessor_stage_not_promoted")
        if predecessor_receipt.source_commit_sha != source_commit_sha:
            technical_blockers.append("predecessor_source_commit_mismatch")
        if not _is_sha256(predecessor_receipt_sha256):
            technical_blockers.append("predecessor_receipt_sha256_invalid")

    unique_technical_blockers = tuple(dict.fromkeys(technical_blockers))
    unique_promotion_blockers = tuple(dict.fromkeys(promotion_blockers))
    unique_blockers = tuple(
        dict.fromkeys((*unique_technical_blockers, *unique_promotion_blockers))
    )
    vertical_stage_contract_passed = not unique_technical_blockers
    return F3StageGateReceipt(
        schema="f3-vertical-evidence-gate.v2",
        stage=stage,
        stage_index=stage_index,
        source_commit_sha=source_commit_sha,
        required_surfaces=F3_REQUIRED_SURFACES,
        verified_surfaces=tuple(verified_surfaces),
        evidence_artifact_sha256=tuple(artifact_bindings),
        predecessor_stage=expected_predecessor,
        predecessor_receipt_sha256=predecessor_receipt_sha256,
        external_vv_signature_status=signature.status,
        technical_blockers=unique_technical_blockers,
        promotion_blockers=unique_promotion_blockers,
        blockers=unique_blockers,
        vertical_stage_contract_passed=vertical_stage_contract_passed,
        public_product_promotion_passed=(
            vertical_stage_contract_passed and not unique_promotion_blockers
        ),
    )


__all__ = [
    "F3_STAGE_ORDER",
    "F3_REQUIRED_SURFACES",
    "F3Evidence",
    "ExternalVVSignatureVerification",
    "F3StageGateReceipt",
    "evaluate_f3_stage_gate",
]
