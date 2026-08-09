from __future__ import annotations

import inspect

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


def _technically_passing_linear_receipt() -> F3StageGateReceipt:
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


def test_complete_first_stage_passes_technical_gate_but_not_public_promotion() -> None:
    receipt = _technically_passing_linear_receipt()

    assert receipt.public_product_promotion_passed is False
    assert receipt.vertical_stage_contract_passed is True
    assert receipt.technical_blockers == ()
    assert receipt.promotion_blockers == (
        "planar_product_replay_prerequisite_not_bound",
        "planar_external_vv_prerequisite_not_bound",
    )
    assert receipt.blockers == receipt.promotion_blockers
    assert receipt.verified_surfaces == F3_REQUIRED_SURFACES


def test_public_gate_has_no_caller_asserted_planar_prerequisite_input() -> None:
    parameters = inspect.signature(evaluate_f3_stage_gate).parameters

    assert "promotion_prerequisites" not in parameters


def test_external_vv_artifact_without_signature_verification_fails_closed() -> None:
    receipt = evaluate_f3_stage_gate(
        stage="frame3d_linear",
        source_commit_sha=SOURCE_SHA,
        evidence=_complete_evidence(),
    )

    assert receipt.vertical_stage_contract_passed is True
    assert receipt.public_product_promotion_passed is False
    assert receipt.promotion_blockers == (
        "external_vv_signature_verification_missing",
        "planar_product_replay_prerequisite_not_bound",
        "planar_external_vv_prerequisite_not_bound",
    )


def test_user_authorized_signature_verifier_waiver_is_technical_only() -> None:
    receipt = evaluate_f3_stage_gate(
        stage="frame3d_linear",
        source_commit_sha=SOURCE_SHA,
        evidence=_complete_evidence(),
        external_vv_signature=ExternalVVSignatureVerification(
            status="waived",
            authority="user_authorized_signature_verifier_waiver",
            waiver_reason="User explicitly authorized self-verification without a signer.",
        ),
    )

    assert receipt.vertical_stage_contract_passed is True
    assert receipt.public_product_promotion_passed is False
    assert receipt.external_vv_signature_status == "waived"
    assert receipt.technical_blockers == ()
    assert receipt.promotion_blockers == (
        "external_vv_signature_verification_waived",
        "planar_product_replay_prerequisite_not_bound",
        "planar_external_vv_prerequisite_not_bound",
    )
    assert receipt.blockers == receipt.promotion_blockers


def test_verified_signature_without_planar_prerequisites_never_promotes() -> None:
    receipt = evaluate_f3_stage_gate(
        stage="frame3d_linear",
        source_commit_sha=SOURCE_SHA,
        evidence=_complete_evidence(),
        external_vv_signature=_verified_signature(),
    )

    assert receipt.vertical_stage_contract_passed is True
    assert receipt.public_product_promotion_passed is False
    assert receipt.promotion_blockers == (
        "planar_product_replay_prerequisite_not_bound",
        "planar_external_vv_prerequisite_not_bound",
    )


def test_v2_gate_round_trip_replays_all_serialized_invariants() -> None:
    receipt = _technically_passing_linear_receipt()

    assert F3StageGateReceipt.from_dict(receipt.to_dict()) == receipt


@pytest.mark.parametrize(
    ("field", "value", "expected_error"),
    [
        ("vertical_stage_contract_passed", "false", "pass_type_invalid"),
        ("public_product_promotion_passed", 0, "pass_type_invalid"),
        ("stage_index", True, "stage_index_invalid"),
    ],
)
def test_v2_gate_rejects_non_exact_bool_and_integer_types(
    field: str, value: object, expected_error: str
) -> None:
    payload = _technically_passing_linear_receipt().to_dict()
    payload[field] = value

    with pytest.raises(ValueError, match=expected_error):
        F3StageGateReceipt.from_dict(payload)


def test_v2_gate_rejects_tampered_blocker_union_and_promotion_bit() -> None:
    payload = _technically_passing_linear_receipt().to_dict()
    payload["blockers"] = []
    with pytest.raises(ValueError, match="blockers_inconsistent"):
        F3StageGateReceipt.from_dict(payload)

    payload = _technically_passing_linear_receipt().to_dict()
    payload["public_product_promotion_passed"] = True
    with pytest.raises(ValueError, match="public_pass_inconsistent"):
        F3StageGateReceipt.from_dict(payload)


def test_v2_gate_rejects_surface_binding_and_source_hash_tampering() -> None:
    payload = _technically_passing_linear_receipt().to_dict()
    payload["evidence_artifact_sha256"].pop("solver")
    with pytest.raises(ValueError, match="evidence_bindings_invalid"):
        F3StageGateReceipt.from_dict(payload)

    payload = _technically_passing_linear_receipt().to_dict()
    payload["source_commit_sha"] = "not-a-commit"
    with pytest.raises(ValueError, match="source_commit_sha_invalid"):
        F3StageGateReceipt.from_dict(payload)


def test_signature_verifier_waiver_requires_authority_reason_and_vv_artifact() -> None:
    receipt = evaluate_f3_stage_gate(
        stage="frame3d_linear",
        source_commit_sha=SOURCE_SHA,
        evidence=[
            item for item in _complete_evidence() if item.surface != "external_vv"
        ],
        external_vv_signature=ExternalVVSignatureVerification(status="waived"),
    )

    assert "external_vv_signature_waiver_authority_invalid" in receipt.blockers
    assert "external_vv_signature_waiver_reason_missing" in receipt.blockers
    assert "external_vv_signature_waiver_artifact_missing" in receipt.blockers


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
        predecessor_receipt=_technically_passing_linear_receipt(),
        predecessor_receipt_sha256=RECEIPT_SHA,
    )

    assert missing.public_product_promotion_passed is False
    assert "predecessor_stage_receipt_missing" in missing.blockers
    assert passed.vertical_stage_contract_passed is True
    assert passed.public_product_promotion_passed is False
    assert "predecessor_stage_not_promoted" in passed.promotion_blockers


def test_waived_predecessor_keeps_vertical_chain_open_but_not_promotion() -> None:
    waiver = ExternalVVSignatureVerification(
        status="waived",
        authority="user_authorized_signature_verifier_waiver",
        waiver_reason="Internal technical replay only.",
    )
    linear = evaluate_f3_stage_gate(
        stage="frame3d_linear",
        source_commit_sha=SOURCE_SHA,
        evidence=_complete_evidence(),
        external_vv_signature=waiver,
    )
    load = evaluate_f3_stage_gate(
        stage="frame3d_load_control",
        source_commit_sha=SOURCE_SHA,
        evidence=_complete_evidence(),
        external_vv_signature=waiver,
        predecessor_receipt=linear,
        predecessor_receipt_sha256=RECEIPT_SHA,
    )

    assert linear.vertical_stage_contract_passed is True
    assert load.vertical_stage_contract_passed is True
    assert load.public_product_promotion_passed is False
    assert "predecessor_stage_not_closed" not in load.blockers
    assert "predecessor_stage_not_promoted" in load.promotion_blockers


def test_predecessor_source_drift_and_nonclosure_are_rejected() -> None:
    predecessor = _technically_passing_linear_receipt()
    drifted = F3StageGateReceipt(
        **{
            **predecessor.__dict__,
            "source_commit_sha": "d" * 40,
            "technical_blockers": ("synthetic_nonclosure",),
            "blockers": ("synthetic_nonclosure",),
            "vertical_stage_contract_passed": False,
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
