from __future__ import annotations

import base64
from dataclasses import replace
import inspect
import json
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from jsonschema import Draft202012Validator
import pytest

from structural_analysis.engine_v2.assembly_backend import (
    fgmres_external_key_enrollment_v1 as enrollment_v1,
)
from structural_analysis.engine_v2.assembly_backend import (
    fgmres_external_runner_key_lifecycle_v3 as lifecycle_v3,
)
from structural_analysis.engine_v2.assembly_backend import (
    fgmres_external_trust_anchor_registry_v3 as registry_v3,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_fixture_registry_v1 import (
    HIP_FGMRES_FIXTURE_REGISTRY_SUITE_ID_V1,
)
from structural_analysis.engine_v2.contracts._canonical import (
    canonical_hash,
    sha256_prefixed,
)
from tests.test_engine_v2_hip_fgmres_external_reviewer_root_bootstrap_v1 import (
    _endorsements as _bootstrap_endorsements,
)
from tests.test_engine_v2_hip_fgmres_external_reviewer_root_bootstrap_v1 import (
    _plan as _bootstrap_plan,
)
from tests.test_engine_v2_hip_fgmres_external_reviewer_root_bootstrap_v1 import (
    _review_material,
)
from tests.test_engine_v2_hip_fgmres_external_trust_anchor_registry_v3 import (
    _result as _source_registry_result,
)


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = (
    ROOT
    / "src/structural_analysis/schemas"
    / "hip_fgmres_external_runner_key_lifecycle_v3.schema.json"
)
FIXTURE_BYTES_HASH = (
    "sha256:bc12d11a15d23f2768e4c27e5f8449f88d26453f9579ebb741861a3176eae2fa"
)
FIXTURE_HASH = "sha256:0f9fb841c2ed6bfe2aef43024d5a496485f06d3d00b95892c7304b7e0dab7eb6"
ENROLLED_AT = "2026-07-15T13:15:00Z"
ACTIVATED_AT = "2026-07-15T14:00:00Z"


def _public_key(private_key: Ed25519PrivateKey) -> bytes:
    return private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )


def _runner_material(
    source: registry_v3.HipFgmresExternalTrustAnchorRegistryResultV3,
    *,
    valid_from_utc: str = "2026-07-15T13:30:00Z",
    valid_until_utc: str = "2026-08-15T00:00:00Z",
) -> tuple[
    Ed25519PrivateKey,
    enrollment_v1.HipFgmresExternalKeyEnrollmentReceiptV1,
]:
    private_key = Ed25519PrivateKey.from_private_bytes(b"R" * 32)
    public_key = _public_key(private_key)
    challenge = enrollment_v1.compile_hip_fgmres_external_key_enrollment_challenge_v1(
        nonce=b"runner-enrollment-nonce-v3" + b"\x00" * 6,
        request_id="request:runner-v3-enrollment-001",
        runner_id="external-runner",
        key_id="ed25519:external-runner:v1",
        key_epoch=1,
        predecessor_registry_epoch=1,
        predecessor_registry_hash=source.receipt.registry_hash,
        target_registry_epoch=2,
        predecessor_key=None,
        public_key=public_key,
        public_key_sha256=sha256_prefixed(public_key),
        allowed_architecture_base="gfx1100",
        allowed_suite_id=HIP_FGMRES_FIXTURE_REGISTRY_SUITE_ID_V1,
        allowed_fixture_registry_bytes_sha256=FIXTURE_BYTES_HASH,
        allowed_fixture_registry_hash=FIXTURE_HASH,
        minimum_run_sequence=1,
        maximum_run_sequence=100,
        valid_from_utc=valid_from_utc,
        valid_until_utc=valid_until_utc,
        runner_declared_key_origin="runner_declared_isolated_hsm",
        attestation_digest_sha256=sha256_prefixed(b"unverified-runner-attestation"),
    )
    proof = private_key.sign(
        enrollment_v1.compile_hip_fgmres_external_key_enrollment_proof_message_v1(
            challenge
        )
    )
    receipt = enrollment_v1.verify_hip_fgmres_external_key_enrollment_proof_v1(
        challenge,
        proof_signature_base64=base64.b64encode(proof).decode("ascii"),
    )
    return private_key, receipt


def _approvals(
    statement: lifecycle_v3.RunnerKeyStatementV3,
    *,
    count: int = 2,
    message: bytes | None = None,
) -> tuple[lifecycle_v3.HipFgmresExternalRunnerKeyReviewerApprovalV3, ...]:
    _, private_keys = _review_material()
    signed_message = (
        lifecycle_v3.compile_hip_fgmres_external_runner_key_review_message_v3(statement)
        if message is None
        else message
    )
    rows = []
    for root, private_key in zip(
        statement.reviewer_roots[:count],
        private_keys[:count],
        strict=True,
    ):
        signature = private_key.sign(signed_message)
        rows.append(
            lifecycle_v3.HipFgmresExternalRunnerKeyReviewerApprovalV3(
                reviewer_id=root.reviewer_id,
                reviewer_key_id=root.key_id,
                reviewer_key_epoch=root.key_epoch,
                statement_hash=statement.statement_hash,
                algorithm="Ed25519",
                signature_base64=base64.b64encode(signature).decode("ascii"),
                signature_sha256=sha256_prefixed(signature),
            )
        )
    return tuple(rows)


def _events(
    source: registry_v3.HipFgmresExternalTrustAnchorRegistryResultV3,
    enrollment_receipt: enrollment_v1.HipFgmresExternalKeyEnrollmentReceiptV1,
    *,
    enrollment_approval_count: int = 2,
    activation_approval_count: int = 2,
    enrolled_at_utc: str = ENROLLED_AT,
    activated_at_utc: str = ACTIVATED_AT,
) -> tuple[
    lifecycle_v3.HipFgmresExternalRunnerKeyEnrollmentEventV3,
    lifecycle_v3.HipFgmresExternalRunnerKeyActivationEventV3,
]:
    enrollment_statement = (
        lifecycle_v3.compile_hip_fgmres_external_runner_key_enrollment_statement_v3(
            source.receipt,
            enrollment_receipt,
            enrolled_at_utc=enrolled_at_utc,
        )
    )
    enrollment_event = (
        lifecycle_v3.finalize_hip_fgmres_external_runner_key_enrollment_event_v3(
            enrollment_statement,
            approvals=_approvals(
                enrollment_statement,
                count=enrollment_approval_count,
            ),
        )
    )
    activation_statement = (
        lifecycle_v3.compile_hip_fgmres_external_runner_key_activation_statement_v3(
            source.receipt,
            enrollment_receipt,
            enrollment_event,
            activated_at_utc=activated_at_utc,
        )
    )
    activation_event = (
        lifecycle_v3.finalize_hip_fgmres_external_runner_key_activation_event_v3(
            activation_statement,
            approvals=_approvals(
                activation_statement,
                count=activation_approval_count,
            ),
        )
    )
    return enrollment_event, activation_event


def _result(
    *,
    enrollment_approval_count: int = 2,
    activation_approval_count: int = 2,
) -> lifecycle_v3.HipFgmresExternalRunnerKeyLifecycleResultV3:
    source = _source_registry_result()
    _, enrollment_receipt = _runner_material(source)
    enrollment_event, activation_event = _events(
        source,
        enrollment_receipt,
        enrollment_approval_count=enrollment_approval_count,
        activation_approval_count=activation_approval_count,
    )
    return lifecycle_v3.verify_hip_fgmres_external_runner_key_lifecycle_v3(
        source,
        enrollment_receipt,
        enrollment_event=enrollment_event,
        activation_event=activation_event,
    )


def _reseal_receipt(
    receipt: lifecycle_v3.HipFgmresExternalRunnerKeyLifecycleReceiptV3,
) -> lifecycle_v3.HipFgmresExternalRunnerKeyLifecycleReceiptV3:
    draft = replace(receipt, receipt_hash=lifecycle_v3._ZERO_HASH)
    return replace(
        draft,
        receipt_hash=canonical_hash(
            lifecycle_v3._receipt_payload(draft, include_hash=False)
        ),
    )


def _reseal_activation_statement(
    statement: lifecycle_v3.HipFgmresExternalRunnerKeyActivationStatementV3,
) -> lifecycle_v3.HipFgmresExternalRunnerKeyActivationStatementV3:
    draft = replace(statement, statement_hash=lifecycle_v3._ZERO_HASH)
    return replace(
        draft,
        statement_hash=canonical_hash(
            lifecycle_v3._activation_statement_payload(draft, include_hash=False)
        ),
    )


def test_reviewed_v3_lineage_enrolls_then_activates_one_detached_runner_key() -> None:
    result = _result()
    receipt = result.receipt

    assert (
        lifecycle_v3.validate_hip_fgmres_external_runner_key_lifecycle_result_v3(result)
        is result
    )
    assert receipt.registry_epoch == 3
    assert receipt.predecessor_registry_epoch == 2
    assert receipt.event_count == 3
    assert receipt.reviewer_authority_count == 3
    assert receipt.enrolled_runner_key_count == 1
    assert receipt.active_runner_key_count == 1
    assert receipt.enrollment_event.statement.sequence == 2
    assert receipt.activation_event.statement.sequence == 3
    assert receipt.activation_event.statement.previous_event_hash == (
        receipt.enrollment_event.event_hash
    )
    assert receipt.active_key.status == "active"
    assert receipt.active_key.runner_id == "external-runner"
    assert receipt.active_key.allowed_architecture_base == "gfx1100"
    assert receipt.claims.detached_runner_key_possession_verified is True
    assert receipt.claims.enrollment_reviewer_quorum_verified is True
    assert receipt.claims.activation_reviewer_quorum_verified is True
    assert receipt.claims.package_registry_v3_inclusion_verified is False
    assert receipt.claims.package_runner_key_activation_verified is False
    assert receipt.claims.actual_isolated_runner_verified is False
    assert receipt.claims.runner_hsm_origin_verified is False
    assert receipt.claims.actual_external_gfx1100_verified is False
    assert receipt.claims.promotion_eligible is False


def test_outer_schema_is_strict_valid_and_result_is_deterministic() -> None:
    first = _result()
    second = _result()
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))

    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(first.to_manifest())
    assert first.receipt == second.receipt
    assert first.receipt.registry_hash == second.receipt.registry_hash
    assert first.receipt.receipt_hash == second.receipt.receipt_hash


@pytest.mark.parametrize("approval_count", [2, 3])
def test_policy_accepts_ordered_two_or_three_of_three_quorum(
    approval_count: int,
) -> None:
    result = _result(
        enrollment_approval_count=approval_count,
        activation_approval_count=approval_count,
    )
    assert len(result.receipt.enrollment_event.approvals) == approval_count
    assert len(result.receipt.activation_event.approvals) == approval_count


@pytest.mark.parametrize("mode", ["missing", "duplicate", "reordered", "list"])
def test_reviewer_quorum_is_unique_canonical_and_at_least_two(mode: str) -> None:
    source = _source_registry_result()
    _, enrollment_receipt = _runner_material(source)
    statement = (
        lifecycle_v3.compile_hip_fgmres_external_runner_key_enrollment_statement_v3(
            source.receipt,
            enrollment_receipt,
            enrolled_at_utc=ENROLLED_AT,
        )
    )
    rows = _approvals(statement, count=3)
    changed: object
    if mode == "missing":
        changed = rows[:1]
    elif mode == "duplicate":
        changed = (rows[0], rows[0])
    elif mode == "reordered":
        changed = (rows[1], rows[0])
    else:
        changed = list(rows[:2])

    with pytest.raises(lifecycle_v3.HipFgmresExternalRunnerKeyLifecycleV3Error):
        lifecycle_v3.finalize_hip_fgmres_external_runner_key_enrollment_event_v3(
            statement,
            approvals=changed,  # type: ignore[arg-type]
        )


def test_enrollment_and_activation_review_domains_cannot_be_replayed() -> None:
    source = _source_registry_result()
    _, enrollment_receipt = _runner_material(source)
    enrollment_statement = (
        lifecycle_v3.compile_hip_fgmres_external_runner_key_enrollment_statement_v3(
            source.receipt,
            enrollment_receipt,
            enrolled_at_utc=ENROLLED_AT,
        )
    )
    enrollment_event = (
        lifecycle_v3.finalize_hip_fgmres_external_runner_key_enrollment_event_v3(
            enrollment_statement,
            approvals=_approvals(enrollment_statement),
        )
    )
    activation_statement = (
        lifecycle_v3.compile_hip_fgmres_external_runner_key_activation_statement_v3(
            source.receipt,
            enrollment_receipt,
            enrollment_event,
            activated_at_utc=ACTIVATED_AT,
        )
    )
    enrollment_message = (
        lifecycle_v3.compile_hip_fgmres_external_runner_key_review_message_v3(
            enrollment_statement
        )
    )

    with pytest.raises(
        lifecycle_v3.HipFgmresExternalRunnerKeyLifecycleV3Error
    ) as error:
        lifecycle_v3.finalize_hip_fgmres_external_runner_key_activation_event_v3(
            activation_statement,
            approvals=_approvals(
                activation_statement,
                message=enrollment_message,
            ),
        )

    assert error.value.code == (
        "hip_fgmres_external_runner_key_lifecycle_v3_approval_invalid"
    )


def test_wrong_reviewer_key_signature_is_rejected() -> None:
    source = _source_registry_result()
    _, enrollment_receipt = _runner_material(source)
    statement = (
        lifecycle_v3.compile_hip_fgmres_external_runner_key_enrollment_statement_v3(
            source.receipt,
            enrollment_receipt,
            enrolled_at_utc=ENROLLED_AT,
        )
    )
    rows = _approvals(statement)
    changed_signature = rows[1].signature_base64
    changed = (
        replace(
            rows[0],
            signature_base64=changed_signature,
            signature_sha256=sha256_prefixed(base64.b64decode(changed_signature)),
        ),
        rows[1],
    )

    with pytest.raises(
        lifecycle_v3.HipFgmresExternalRunnerKeyLifecycleV3Error
    ) as error:
        lifecycle_v3.finalize_hip_fgmres_external_runner_key_enrollment_event_v3(
            statement,
            approvals=changed,
        )

    assert error.value.code == (
        "hip_fgmres_external_runner_key_lifecycle_v3_approval_invalid"
    )


def test_enrollment_challenge_must_name_exact_v3_genesis_predecessor() -> None:
    source = _source_registry_result()
    runner_key = Ed25519PrivateKey.from_private_bytes(b"S" * 32)
    public_key = _public_key(runner_key)
    challenge = enrollment_v1.compile_hip_fgmres_external_key_enrollment_challenge_v1(
        nonce=b"foreign-predecessor" + b"\x00" * 13,
        request_id="request:foreign-predecessor",
        runner_id="external-runner",
        key_id="ed25519:external-runner:v1",
        key_epoch=1,
        predecessor_registry_epoch=1,
        predecessor_registry_hash=canonical_hash({"foreign": "registry"}),
        target_registry_epoch=2,
        predecessor_key=None,
        public_key=public_key,
        public_key_sha256=sha256_prefixed(public_key),
        allowed_architecture_base="gfx1100",
        allowed_suite_id=HIP_FGMRES_FIXTURE_REGISTRY_SUITE_ID_V1,
        allowed_fixture_registry_bytes_sha256=FIXTURE_BYTES_HASH,
        allowed_fixture_registry_hash=FIXTURE_HASH,
        minimum_run_sequence=1,
        maximum_run_sequence=100,
        valid_from_utc="2026-07-15T13:30:00Z",
        valid_until_utc="2026-08-15T00:00:00Z",
        runner_declared_key_origin="runner_declared_unknown",
        attestation_digest_sha256=None,
    )
    signature = runner_key.sign(
        enrollment_v1.compile_hip_fgmres_external_key_enrollment_proof_message_v1(
            challenge
        )
    )
    receipt = enrollment_v1.verify_hip_fgmres_external_key_enrollment_proof_v1(
        challenge,
        proof_signature_base64=base64.b64encode(signature).decode("ascii"),
    )

    with pytest.raises(
        lifecycle_v3.HipFgmresExternalRunnerKeyLifecycleV3Error
    ) as error:
        lifecycle_v3.compile_hip_fgmres_external_runner_key_enrollment_statement_v3(
            source.receipt,
            receipt,
            enrolled_at_utc=ENROLLED_AT,
        )

    assert error.value.code == (
        "hip_fgmres_external_runner_key_lifecycle_v3_enrollment_lineage_invalid"
    )


@pytest.mark.parametrize(
    ("activated_at", "accepted"),
    [
        ("2026-07-15T13:15:00Z", False),
        ("2026-07-15T13:29:59.999999Z", False),
        ("2026-07-15T13:30:00Z", True),
        ("2026-08-14T23:59:59.999999Z", True),
        ("2026-08-15T00:00:00Z", False),
    ],
)
def test_activation_is_strictly_after_enrollment_and_inside_key_half_open_window(
    activated_at: str,
    accepted: bool,
) -> None:
    source = _source_registry_result()
    _, enrollment_receipt = _runner_material(source)
    if accepted:
        _, activation = _events(
            source,
            enrollment_receipt,
            activated_at_utc=activated_at,
        )
        assert activation.statement.activated_at_utc == activated_at
        return
    with pytest.raises(lifecycle_v3.HipFgmresExternalRunnerKeyLifecycleV3Error):
        _events(
            source,
            enrollment_receipt,
            activated_at_utc=activated_at,
        )


def test_attached_result_replays_bootstrap_source_not_only_detached_roots() -> None:
    result = _result()
    foreign_private_keys = tuple(
        Ed25519PrivateKey.from_private_bytes(bytes([index]) * 32)
        for index in range(4, 7)
    )
    foreign_roots = []
    for index, private_key in enumerate(foreign_private_keys, start=1):
        reviewer_id = f"foreign.{index}"
        public_key = _public_key(private_key)
        foreign_roots.append(
            replace(
                result.receipt.source_registry_receipt.genesis.reviewer_roots[
                    index - 1
                ],
                reviewer_id=reviewer_id,
                key_id=f"ed25519-review:{reviewer_id}:v1",
                public_key_base64=base64.b64encode(public_key).decode("ascii"),
                public_key_sha256=sha256_prefixed(public_key),
            )
        )
    plan = _bootstrap_plan(roots=tuple(foreign_roots))
    bootstrap_receipt = registry_v3.bootstrap_v1.verify_hip_fgmres_external_reviewer_root_bootstrap_endorsements_v1(
        plan,
        endorsements=_bootstrap_endorsements(plan, foreign_private_keys),
    )
    genesis = registry_v3.compile_hip_fgmres_external_trust_anchor_registry_genesis_v3(
        bootstrap_receipt,
        activated_at_utc="2026-07-15T13:00:00Z",
    )
    genesis_message = registry_v3.compile_hip_fgmres_external_trust_anchor_registry_activation_message_v3(
        genesis
    )
    genesis_approvals = []
    for root, private_key in zip(
        genesis.reviewer_roots,
        foreign_private_keys,
        strict=True,
    ):
        signature = private_key.sign(genesis_message)
        genesis_approvals.append(
            registry_v3.HipFgmresExternalReviewerRootActivationEndorsementV3(
                reviewer_id=root.reviewer_id,
                reviewer_key_id=root.key_id,
                reviewer_key_epoch=root.key_epoch,
                genesis_event_hash=genesis.genesis_event_hash,
                bootstrap_receipt_hash=genesis.bootstrap_receipt_hash,
                algorithm="Ed25519",
                signature_base64=base64.b64encode(signature).decode("ascii"),
                signature_sha256=sha256_prefixed(signature),
            )
        )
    foreign_source = (
        registry_v3.verify_hip_fgmres_external_trust_anchor_registry_activation_v3(
            bootstrap_receipt,
            genesis=genesis,
            activation_endorsements=tuple(genesis_approvals),
        )
    )

    with pytest.raises(
        lifecycle_v3.HipFgmresExternalRunnerKeyLifecycleV3Error
    ) as error:
        lifecycle_v3.validate_hip_fgmres_external_runner_key_lifecycle_result_v3(
            replace(result, source_registry_result=foreign_source)
        )

    assert error.value.code == (
        "hip_fgmres_external_runner_key_lifecycle_v3_source_binding_invalid"
    )


def test_coherently_rehashed_promotion_and_package_claims_are_rejected() -> None:
    receipt = _result().receipt
    changed_claims = replace(
        receipt.claims,
        package_runner_key_activation_verified=True,
        promotion_eligible=True,
    )
    changed = _reseal_receipt(replace(receipt, claims=changed_claims))

    with pytest.raises(
        lifecycle_v3.HipFgmresExternalRunnerKeyLifecycleV3Error
    ) as error:
        lifecycle_v3.validate_hip_fgmres_external_runner_key_lifecycle_receipt_v3(
            changed
        )

    assert error.value.code == (
        "hip_fgmres_external_runner_key_lifecycle_v3_receipt_semantics_invalid"
    )


def test_boolean_integer_aliases_are_rejected() -> None:
    receipt = _result().receipt
    changed_claims = replace(
        receipt.claims,
        detached_runner_key_possession_verified=1,
    )
    changed = _reseal_receipt(replace(receipt, claims=changed_claims))
    with pytest.raises(lifecycle_v3.HipFgmresExternalRunnerKeyLifecycleV3Error):
        lifecycle_v3.validate_hip_fgmres_external_runner_key_lifecycle_receipt_v3(
            changed
        )

    changed_count = _reseal_receipt(replace(receipt, registry_epoch=True))
    with pytest.raises(lifecycle_v3.HipFgmresExternalRunnerKeyLifecycleV3Error):
        lifecycle_v3.validate_hip_fgmres_external_runner_key_lifecycle_receipt_v3(
            changed_count
        )


def test_activation_event_standalone_validation_binds_runner_key_window() -> None:
    result = _result()
    statement = result.receipt.activation_event.statement
    changed = _reseal_activation_statement(
        replace(statement, valid_from_utc="2026-07-15T14:00:00.000001Z")
    )

    with pytest.raises(
        lifecycle_v3.HipFgmresExternalRunnerKeyLifecycleV3Error
    ) as error:
        lifecycle_v3.validate_hip_fgmres_external_runner_key_activation_statement_v3(
            changed
        )

    assert error.value.code == (
        "hip_fgmres_external_runner_key_lifecycle_v3_activation_statement_invalid"
    )


def test_malformed_reviewer_root_collection_fails_on_stable_contract_path() -> None:
    result = _result()
    statement = result.receipt.enrollment_event.statement
    changed = replace(
        statement,
        reviewer_roots=(object(), *statement.reviewer_roots[1:]),  # type: ignore[arg-type]
    )

    with pytest.raises(
        lifecycle_v3.HipFgmresExternalRunnerKeyLifecycleV3Error
    ) as error:
        lifecycle_v3.validate_hip_fgmres_external_runner_key_enrollment_statement_v3(
            changed
        )

    assert error.value.code == (
        "hip_fgmres_external_runner_key_lifecycle_v3_reviewer_roots_invalid"
    )


def test_product_module_has_no_private_key_or_signing_api() -> None:
    source = inspect.getsource(lifecycle_v3)

    assert "Ed25519PrivateKey" not in source
    assert ".sign(" not in source
    assert "from_private_bytes" not in source
    assert not any(name.startswith("sign_") for name in lifecycle_v3.__all__)
