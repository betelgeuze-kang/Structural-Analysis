from __future__ import annotations

import pytest

from structural_analysis.validation.f3_vertical_evidence import (
    F3_REQUIRED_SURFACES,
    F3_STAGE_ORDER,
    ExternalVVSignatureVerification,
    F3Evidence,
    F3StageGateReceipt,
    evaluate_f3_stage_gate,
)


SOURCE_SHA = "a" * 40
ARTIFACT_SHA = "sha256:" + "b" * 64
RECEIPT_SHA = "sha256:" + "c" * 64


def _complete_evidence() -> list[F3Evidence]:
    return [
        F3Evidence(surface=surface, status="verified", artifact_sha256=ARTIFACT_SHA)
        for surface in F3_REQUIRED_SURFACES
    ]


def _verified_signature() -> ExternalVVSignatureVerification:
    return ExternalVVSignatureVerification(
        status="verified",
        authority="independent_external_vv_signature_verifier",
        signer_id="vv-lab-key-1",
        signed_artifact_sha256=ARTIFACT_SHA,
        verification_receipt_sha256=RECEIPT_SHA,
    )


def _passing_linear_receipt() -> F3StageGateReceipt:
    return evaluate_f3_stage_gate(
        stage="frame3d_linear",
        source_commit_sha=SOURCE_SHA,
        evidence=_complete_evidence(),
        external_vv_signature=_verified_signature(),
    )


def test_stage_and_surface_contract_is_complete_and_ordered() -> None:
    assert F3_STAGE_ORDER == (
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
    assert F3_REQUIRED_SURFACES == (
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


def test_complete_first_stage_with_independent_signature_can_pass() -> None:
    receipt = _passing_linear_receipt()

    assert receipt.public_product_promotion_passed is True
    assert receipt.blockers == ()
    assert receipt.verified_surfaces == F3_REQUIRED_SURFACES


def test_external_vv_artifact_without_signature_verification_fails_closed() -> None:
    receipt = evaluate_f3_stage_gate(
        stage="frame3d_linear",
        source_commit_sha=SOURCE_SHA,
        evidence=_complete_evidence(),
    )

    assert receipt.public_product_promotion_passed is False
    assert receipt.blockers == ("external_vv_signature_verification_missing",)


@pytest.mark.parametrize(
    ("signature", "expected_blocker"),
    [
        (
            ExternalVVSignatureVerification(status="unverified"),
            "external_vv_signature_verification_unverified",
        ),
        (
            ExternalVVSignatureVerification(
                status="verified",
                authority="self_asserted",
                signer_id="local",
                signed_artifact_sha256=ARTIFACT_SHA,
                verification_receipt_sha256=RECEIPT_SHA,
            ),
            "external_vv_signature_verifier_authority_invalid",
        ),
        (
            ExternalVVSignatureVerification(
                status="verified",
                authority="independent_external_vv_signature_verifier",
                signer_id="vv-lab-key-1",
                signed_artifact_sha256="sha256:" + "d" * 64,
                verification_receipt_sha256=RECEIPT_SHA,
            ),
            "external_vv_signature_artifact_binding_mismatch",
        ),
    ],
)
def test_unverified_self_asserted_or_unbound_signature_is_rejected(
    signature: ExternalVVSignatureVerification,
    expected_blocker: str,
) -> None:
    receipt = evaluate_f3_stage_gate(
        stage="frame3d_linear",
        source_commit_sha=SOURCE_SHA,
        evidence=_complete_evidence(),
        external_vv_signature=signature,
    )

    assert receipt.public_product_promotion_passed is False
    assert expected_blocker in receipt.blockers


def test_missing_duplicate_unknown_and_blocked_surfaces_fail_closed() -> None:
    evidence = _complete_evidence()
    evidence = [item for item in evidence if item.surface != "checkpoint"]
    evidence.append(F3Evidence("solver", "verified", ARTIFACT_SHA))
    evidence.append(F3Evidence("not_a_surface", "verified", ARTIFACT_SHA))
    evidence = [
        F3Evidence(item.surface, "blocked", item.artifact_sha256)
        if item.surface == "workbench"
        else item
        for item in evidence
    ]

    receipt = evaluate_f3_stage_gate(
        stage="frame3d_linear",
        source_commit_sha=SOURCE_SHA,
        evidence=evidence,
        external_vv_signature=_verified_signature(),
    )

    assert receipt.public_product_promotion_passed is False
    assert "missing_evidence_surface:checkpoint" in receipt.blockers
    assert "duplicate_evidence_surface:solver" in receipt.blockers
    assert "unknown_evidence_surface:not_a_surface" in receipt.blockers
    assert "evidence_not_verified:workbench" in receipt.blockers


def test_second_stage_requires_closed_bound_immediate_predecessor() -> None:
    missing = evaluate_f3_stage_gate(
        stage="frame3d_load_control",
        source_commit_sha=SOURCE_SHA,
        evidence=_complete_evidence(),
        external_vv_signature=_verified_signature(),
    )
    passed = evaluate_f3_stage_gate(
        stage="frame3d_load_control",
        source_commit_sha=SOURCE_SHA,
        evidence=_complete_evidence(),
        external_vv_signature=_verified_signature(),
        predecessor_receipt=_passing_linear_receipt(),
        predecessor_receipt_sha256=RECEIPT_SHA,
    )

    assert missing.public_product_promotion_passed is False
    assert "predecessor_stage_receipt_missing" in missing.blockers
    assert passed.public_product_promotion_passed is True


def test_predecessor_source_drift_and_nonclosure_are_rejected() -> None:
    predecessor = _passing_linear_receipt()
    drifted = F3StageGateReceipt(
        **{
            **predecessor.__dict__,
            "source_commit_sha": "d" * 40,
            "public_product_promotion_passed": False,
        }
    )

    receipt = evaluate_f3_stage_gate(
        stage="frame3d_load_control",
        source_commit_sha=SOURCE_SHA,
        evidence=_complete_evidence(),
        external_vv_signature=_verified_signature(),
        predecessor_receipt=drifted,
        predecessor_receipt_sha256=RECEIPT_SHA,
    )

    assert "predecessor_stage_not_closed" in receipt.blockers
    assert "predecessor_source_commit_mismatch" in receipt.blockers


def test_invalid_hashes_and_unknown_stage_never_promote() -> None:
    evidence = _complete_evidence()
    evidence[0] = F3Evidence("model_ir", "verified", "not-a-sha")
    receipt = evaluate_f3_stage_gate(
        stage="frame3d_linear",
        source_commit_sha="short",
        evidence=evidence,
        external_vv_signature=_verified_signature(),
    )

    assert "source_commit_sha_invalid" in receipt.blockers
    assert "evidence_artifact_sha256_invalid:model_ir" in receipt.blockers
    with pytest.raises(ValueError, match="unknown F3 stage"):
        evaluate_f3_stage_gate(
            stage="frame3d_magic",
            source_commit_sha=SOURCE_SHA,
            evidence=_complete_evidence(),
        )
