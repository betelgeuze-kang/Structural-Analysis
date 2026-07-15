from __future__ import annotations

import base64
from dataclasses import replace
import io
import inspect
import json
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from jsonschema import Draft202012Validator
import pytest

from structural_analysis.engine_v2.assembly_backend import (
    fgmres_external_reviewer_root_bootstrap_v1 as bootstrap,
)
from structural_analysis.engine_v2.contracts._canonical import (
    canonical_hash,
    sha256_prefixed,
)


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = (
    ROOT
    / "src/structural_analysis/schemas"
    / "hip_fgmres_external_reviewer_root_bootstrap_v1.schema.json"
)
RESOURCE = (
    ROOT
    / "src/structural_analysis/engine_v2/assembly_backend/fixtures"
    / "fgmres_external_reviewer_root_bootstrap_v1/status.v1.json"
)
BOOTSTRAP_AT = "2026-07-15T12:00:00Z"


def _public_bytes(private_key: Ed25519PrivateKey) -> bytes:
    return private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )


def _review_material() -> tuple[
    tuple[bootstrap.HipFgmresExternalReviewerRootV1, ...],
    tuple[Ed25519PrivateKey, ...],
]:
    private_keys = tuple(
        Ed25519PrivateKey.from_private_bytes(bytes([index]) * 32)
        for index in range(1, 4)
    )
    roots = []
    for index, private_key in enumerate(private_keys, start=1):
        reviewer_id = f"reviewer.{index}"
        public_key = _public_bytes(private_key)
        roots.append(
            bootstrap.HipFgmresExternalReviewerRootV1(
                reviewer_id=reviewer_id,
                key_id=f"ed25519-review:{reviewer_id}:v1",
                key_epoch=1,
                public_key_base64=base64.b64encode(public_key).decode("ascii"),
                public_key_sha256=sha256_prefixed(public_key),
                valid_from_utc="2026-01-01T00:00:00Z",
                valid_until_utc="2027-01-01T00:00:00Z",
            )
        )
    return tuple(roots), private_keys


def _plan(
    *,
    roots: tuple[bootstrap.HipFgmresExternalReviewerRootV1, ...] | None = None,
) -> bootstrap.HipFgmresExternalReviewerRootBootstrapPlanV1:
    if roots is None:
        roots, _ = _review_material()
    return bootstrap.compile_hip_fgmres_external_reviewer_root_bootstrap_plan_v1(
        ceremony_id="reviewer-bootstrap.2026-07-15",
        nonce=b"ceremony-nonce" + b"\x00" * 18,
        bootstrap_at_utc=BOOTSTRAP_AT,
        target_lineage_nonce=b"lineage-nonce" + b"\x00" * 19,
        reviewer_roots=roots,
    )


def _endorsements(
    plan: bootstrap.HipFgmresExternalReviewerRootBootstrapPlanV1,
    private_keys: tuple[Ed25519PrivateKey, ...] | None = None,
) -> tuple[bootstrap.HipFgmresExternalReviewerRootEndorsementV1, ...]:
    if private_keys is None:
        _, private_keys = _review_material()
    message = bootstrap.compile_hip_fgmres_external_reviewer_root_bootstrap_endorsement_message_v1(
        plan
    )
    rows = []
    for root, private_key in zip(plan.reviewer_roots, private_keys, strict=True):
        signature = private_key.sign(message)
        rows.append(
            bootstrap.HipFgmresExternalReviewerRootEndorsementV1(
                reviewer_id=root.reviewer_id,
                reviewer_key_id=root.key_id,
                reviewer_key_epoch=root.key_epoch,
                plan_hash=plan.plan_hash,
                algorithm="Ed25519",
                signature_base64=base64.b64encode(signature).decode("ascii"),
                signature_sha256=sha256_prefixed(signature),
            )
        )
    return tuple(rows)


def _receipt() -> bootstrap.HipFgmresExternalReviewerRootBootstrapReceiptV1:
    roots, private_keys = _review_material()
    plan = _plan(roots=roots)
    return bootstrap.verify_hip_fgmres_external_reviewer_root_bootstrap_endorsements_v1(
        plan,
        endorsements=_endorsements(plan, private_keys),
    )


def _reseal_plan(
    plan: bootstrap.HipFgmresExternalReviewerRootBootstrapPlanV1,
) -> bootstrap.HipFgmresExternalReviewerRootBootstrapPlanV1:
    source_commitment = canonical_hash(plan.source_registry.to_dict())
    policy_hash = canonical_hash(plan.reviewer_policy.to_dict())
    roots_commitment = canonical_hash([root.to_dict() for root in plan.reviewer_roots])
    lineage_id = bootstrap._target_lineage_id_v1(
        ceremony_id=plan.ceremony_id,
        nonce_base64=plan.nonce_base64,
        bootstrap_at_utc=plan.bootstrap_at_utc,
        source_lineage_commitment_hash=source_commitment,
        target_lineage_nonce_base64=plan.target_lineage_nonce_base64,
        reviewer_policy_hash=policy_hash,
        reviewer_root_commitment_hash=roots_commitment,
    )
    draft = replace(
        plan,
        source_lineage_commitment_hash=source_commitment,
        reviewer_policy_hash=policy_hash,
        reviewer_root_commitment_hash=roots_commitment,
        target_lineage_id=lineage_id,
        plan_hash=bootstrap._ZERO_HASH,
    )
    return replace(
        draft,
        plan_hash=canonical_hash(bootstrap._plan_payload_v1(draft, include_hash=False)),
    )


def _reseal_receipt(
    receipt: bootstrap.HipFgmresExternalReviewerRootBootstrapReceiptV1,
) -> bootstrap.HipFgmresExternalReviewerRootBootstrapReceiptV1:
    draft = replace(receipt, receipt_hash=bootstrap._ZERO_HASH)
    return replace(
        draft,
        receipt_hash=canonical_hash(
            bootstrap._receipt_payload_v1(draft, include_hash=False)
        ),
    )


def test_package_status_is_exact_pending_fresh_genesis_contract() -> None:
    status = bootstrap.load_hip_fgmres_external_reviewer_root_bootstrap_status_v1()

    assert status.status == "pending_independent_reviewer_root_material"
    assert status.contract_bytes_sha256 == sha256_prefixed(RESOURCE.read_bytes())
    assert status.source_registry.registry_bytes_sha256.startswith("sha256:dfa6172c")
    assert status.source_registry.registry_hash.startswith("sha256:5dc12aa7")
    assert status.source_registry.reviewer_authority_count == 0
    assert status.source_registry.enrolled_key_count == 0
    assert status.source_registry.active_key_count == 0
    assert status.source_registry.source_authority_mode == (
        "empty_genesis_no_signing_authority"
    )
    assert status.source_registry.authority_continuity_available is False
    assert status.reviewer_policy.reviewer_count == 3
    assert status.reviewer_policy.minimum_event_approvals == 2
    assert status.reviewer_policy.bootstrap_endorsement_count == 3
    assert status.reviewer_policy.target_genesis_activation_endorsement_count == 3
    assert (
        status.reviewer_policy.target_genesis_binds_bootstrap_plan_and_receipt_hashes
        is True
    )
    assert status.reviewer_policy.lineage_bound_runner_enrollment_required is True
    assert status.bootstrap_plan is None
    assert status.bootstrap_receipt is None
    assert status.claims.fresh_genesis_required is True
    assert status.claims.reviewer_root_material_present is False
    assert status.claims.target_registry_genesis_activated is False
    assert status.claims.promotion_eligible is False
    assert status.claims.commercial_ready is False
    assert (
        bootstrap.validate_hip_fgmres_external_reviewer_root_bootstrap_status_v1(status)
        is status
    )


def test_schema_and_status_resource_are_strict_and_code_pinned() -> None:
    schema_raw = SCHEMA.read_bytes()
    status_raw = RESOURCE.read_bytes()
    schema = json.loads(schema_raw)
    manifest = json.loads(status_raw)

    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(manifest)
    assert sha256_prefixed(schema_raw) == bootstrap._SCHEMA_RESOURCE_BYTES_SHA256_V1
    assert sha256_prefixed(status_raw) == bootstrap._STATUS_RESOURCE_BYTES_SHA256_V1
    assert manifest["source_lineage_commitment_hash"] == canonical_hash(
        manifest["source_registry"]
    )
    assert manifest["reviewer_policy_hash"] == canonical_hash(
        manifest["reviewer_policy"]
    )
    without_hash = dict(manifest)
    without_hash.pop("status_hash")
    assert manifest["status_hash"] == canonical_hash(without_hash)


def test_source_schema_and_head_time_are_replayed_from_exact_v2_resources(
    monkeypatch: Any,
) -> None:
    schema_hash, head_time = bootstrap._read_exact_source_material_v1()
    source_schema = (
        ROOT
        / "src/structural_analysis/schemas"
        / "hip_fgmres_external_trust_anchor_registry_v2.schema.json"
    )
    source_registry = (
        ROOT
        / "src/structural_analysis/engine_v2/assembly_backend/fixtures"
        / "fgmres_external_trust_anchors_v2/registry.v2.json"
    )
    source_manifest = json.loads(source_registry.read_text(encoding="utf-8"))

    assert schema_hash == sha256_prefixed(source_schema.read_bytes())
    assert head_time == source_manifest["events"][-1]["occurred_at_utc"]
    assert head_time == "2026-07-15T00:00:00Z"

    monkeypatch.setattr(
        bootstrap,
        "_read_exact_source_material_v1",
        lambda: ("sha256:" + "1" * 64, head_time),
    )
    with pytest.raises(
        bootstrap.HipFgmresExternalReviewerRootBootstrapV1Error
    ) as caught:
        bootstrap._load_exact_source_identity_v1()
    assert caught.value.code == (
        "hip_fgmres_external_reviewer_bootstrap_source_identity_mismatch"
    )


def test_package_resource_read_is_bounded_before_full_materialization() -> None:
    class OversizedResource:
        @staticmethod
        def is_file() -> bool:
            return True

        @staticmethod
        def open(mode: str) -> io.BytesIO:
            assert mode == "rb"
            return io.BytesIO(b"x" * (bootstrap._MAX_RESOURCE_BYTES_V1 + 2))

    with pytest.raises(
        bootstrap.HipFgmresExternalReviewerRootBootstrapV1Error
    ) as caught:
        bootstrap._read_bounded_resource_v1(
            OversizedResource(),
            path="/oversized",
            missing_code="missing",
            read_code="read",
        )
    assert caught.value.code == (
        "hip_fgmres_external_reviewer_bootstrap_extent_invalid"
    )


def test_detached_all_root_success_is_deterministic_and_non_authoritative() -> None:
    receipt = _receipt()
    repeated = _receipt()

    assert receipt == repeated
    assert (
        bootstrap.validate_hip_fgmres_external_reviewer_root_bootstrap_plan_v1(
            receipt.plan
        )
        is receipt.plan
    )
    assert (
        bootstrap.validate_hip_fgmres_external_reviewer_root_bootstrap_receipt_v1(
            receipt
        )
        is receipt
    )
    assert len(receipt.endorsements) == 3
    assert (
        receipt.claims.all_target_reviewer_private_key_possession_signatures_verified
        is True
    )
    assert receipt.claims.all_target_reviewer_exact_plan_signatures_verified is True
    assert receipt.claims.package_bootstrap_inclusion_verified is False
    assert receipt.claims.target_registry_genesis_activated is False
    assert receipt.claims.predecessor_reviewer_authority_continuity_verified is False
    assert receipt.claims.reviewer_human_identity_verified is False
    assert receipt.claims.reviewer_hsm_origin_verified is False
    assert receipt.claims.external_monotonic_anchor_verified is False
    assert receipt.claims.hardware_execution_verified is False


def test_endorsement_message_binds_domain_plan_and_fresh_lineage() -> None:
    plan = _plan()
    message = bootstrap.compile_hip_fgmres_external_reviewer_root_bootstrap_endorsement_message_v1(
        plan
    )
    changed = bootstrap.compile_hip_fgmres_external_reviewer_root_bootstrap_plan_v1(
        ceremony_id="reviewer-bootstrap.2026-07-15",
        nonce=b"different-nonce" + b"\x00" * 17,
        bootstrap_at_utc=BOOTSTRAP_AT,
        target_lineage_nonce=b"another-lineage" + b"\x00" * 17,
        reviewer_roots=plan.reviewer_roots,
    )
    changed_message = bootstrap.compile_hip_fgmres_external_reviewer_root_bootstrap_endorsement_message_v1(
        changed
    )

    assert message.startswith(
        bootstrap.HIP_FGMRES_EXTERNAL_REVIEWER_ROOT_BOOTSTRAP_ENDORSEMENT_DOMAIN_V1
    )
    assert message != changed_message
    assert plan.target_registry_id != plan.source_registry.registry_id
    assert plan.target_lineage_id != changed.target_lineage_id


def test_target_lineage_id_binds_the_complete_ceremony_statement() -> None:
    roots, _ = _review_material()
    common = {
        "target_lineage_nonce": b"fixed-lineage-nonce" + b"\x00" * 13,
        "reviewer_roots": roots,
    }
    base = bootstrap.compile_hip_fgmres_external_reviewer_root_bootstrap_plan_v1(
        ceremony_id="reviewer-bootstrap.base",
        nonce=b"base-ceremony-nonce" + b"\x00" * 13,
        bootstrap_at_utc="2026-07-15T12:00:00Z",
        **common,
    )
    variants = (
        bootstrap.compile_hip_fgmres_external_reviewer_root_bootstrap_plan_v1(
            ceremony_id="reviewer-bootstrap.changed-id",
            nonce=b"base-ceremony-nonce" + b"\x00" * 13,
            bootstrap_at_utc="2026-07-15T12:00:00Z",
            **common,
        ),
        bootstrap.compile_hip_fgmres_external_reviewer_root_bootstrap_plan_v1(
            ceremony_id="reviewer-bootstrap.base",
            nonce=b"changed-ceremony" + b"\x00" * 16,
            bootstrap_at_utc="2026-07-15T12:00:00Z",
            **common,
        ),
        bootstrap.compile_hip_fgmres_external_reviewer_root_bootstrap_plan_v1(
            ceremony_id="reviewer-bootstrap.base",
            nonce=b"base-ceremony-nonce" + b"\x00" * 13,
            bootstrap_at_utc="2026-07-15T12:00:01Z",
            **common,
        ),
    )

    assert (
        len({base.target_lineage_id, *(item.target_lineage_id for item in variants)})
        == 4
    )


@pytest.mark.parametrize(
    "bootstrap_at_utc",
    ["2026-07-14T23:59:59Z", "2026-07-15T00:00:00Z"],
)
def test_bootstrap_must_be_strictly_after_source_registry_head(
    bootstrap_at_utc: str,
) -> None:
    roots, _ = _review_material()
    with pytest.raises(
        bootstrap.HipFgmresExternalReviewerRootBootstrapV1Error
    ) as caught:
        bootstrap.compile_hip_fgmres_external_reviewer_root_bootstrap_plan_v1(
            ceremony_id="reviewer-bootstrap.time-order",
            nonce=b"time-order-nonce" + b"\x00" * 16,
            bootstrap_at_utc=bootstrap_at_utc,
            target_lineage_nonce=b"time-lineage-nonce" + b"\x00" * 14,
            reviewer_roots=roots,
        )
    assert caught.value.code == (
        "hip_fgmres_external_reviewer_bootstrap_time_order_invalid"
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("registry_bytes_sha256", "sha256:" + "1" * 64),
        ("registry_schema_bytes_sha256", "sha256:" + "0" * 64),
        ("registry_hash", "sha256:" + "2" * 64),
        ("registry_epoch", 2),
        ("head_event_hash", "sha256:" + "3" * 64),
        ("head_event_occurred_at_utc", "2026-07-15T00:00:01Z"),
        ("reviewer_authority_count", 1),
        ("reviewer_authority_commitment_hash", "sha256:" + "4" * 64),
        ("enrolled_key_count", 1),
        ("active_key_count", 1),
        ("replay_receipt_hash", "sha256:" + "5" * 64),
        ("source_authority_mode", "reviewer_quorum"),
        ("authority_continuity_available", True),
    ],
)
def test_exact_source_identity_mutation_is_rejected(field: str, value: Any) -> None:
    plan = _plan()
    forged_source = replace(plan.source_registry, **{field: value})
    forged = _reseal_plan(replace(plan, source_registry=forged_source))

    with pytest.raises(bootstrap.HipFgmresExternalReviewerRootBootstrapV1Error):
        bootstrap.validate_hip_fgmres_external_reviewer_root_bootstrap_plan_v1(forged)


def test_source_loader_drift_is_rejected_before_plan_mint(monkeypatch: Any) -> None:
    current = bootstrap._SOURCE_REGISTRY_LOADER_V1()
    monkeypatch.setattr(
        bootstrap,
        "_SOURCE_REGISTRY_LOADER_V1",
        lambda: replace(current, registry_hash="sha256:" + "7" * 64),
    )

    with pytest.raises(
        bootstrap.HipFgmresExternalReviewerRootBootstrapV1Error
    ) as caught:
        _plan()
    assert caught.value.code == (
        "hip_fgmres_external_reviewer_bootstrap_source_identity_mismatch"
    )


def test_integer_float_and_boolean_aliases_cannot_cross_exact_type_boundaries() -> None:
    plan = _plan()
    forged_source = replace(plan.source_registry, registry_epoch=1.0)
    forged_plan = _reseal_plan(replace(plan, source_registry=forged_source))
    with pytest.raises(bootstrap.HipFgmresExternalReviewerRootBootstrapV1Error):
        bootstrap.validate_hip_fgmres_external_reviewer_root_bootstrap_plan_v1(
            forged_plan
        )

    forged_policy = replace(plan.reviewer_policy, reviewer_count=3.0)
    forged_plan = _reseal_plan(replace(plan, reviewer_policy=forged_policy))
    with pytest.raises(bootstrap.HipFgmresExternalReviewerRootBootstrapV1Error):
        bootstrap.validate_hip_fgmres_external_reviewer_root_bootstrap_plan_v1(
            forged_plan
        )

    forged_plan = _reseal_plan(replace(plan, target_lineage_generation=1.0))
    with pytest.raises(bootstrap.HipFgmresExternalReviewerRootBootstrapV1Error):
        bootstrap.validate_hip_fgmres_external_reviewer_root_bootstrap_plan_v1(
            forged_plan
        )

    receipt = _receipt()
    forged_endorsements = list(receipt.endorsements)
    forged_endorsements[0] = replace(forged_endorsements[0], reviewer_key_epoch=1.0)
    with pytest.raises(bootstrap.HipFgmresExternalReviewerRootBootstrapV1Error):
        bootstrap.verify_hip_fgmres_external_reviewer_root_bootstrap_endorsements_v1(
            receipt.plan,
            endorsements=tuple(forged_endorsements),
        )

    forged_claims = replace(
        receipt.claims,
        package_bootstrap_inclusion_verified=0,
    )
    forged_receipt = _reseal_receipt(replace(receipt, claims=forged_claims))
    with pytest.raises(bootstrap.HipFgmresExternalReviewerRootBootstrapV1Error):
        bootstrap.validate_hip_fgmres_external_reviewer_root_bootstrap_receipt_v1(
            forged_receipt
        )

    status = bootstrap.load_hip_fgmres_external_reviewer_root_bootstrap_status_v1()
    forged_status_source = replace(status.source_registry, registry_epoch=1.0)
    draft_status = replace(
        status,
        source_registry=forged_status_source,
        source_lineage_commitment_hash=canonical_hash(forged_status_source.to_dict()),
        status_hash=bootstrap._ZERO_HASH,
    )
    forged_status = replace(
        draft_status,
        status_hash=canonical_hash(
            bootstrap._package_status_payload_v1(
                draft_status,
                include_hash=False,
            )
        ),
    )
    with pytest.raises(bootstrap.HipFgmresExternalReviewerRootBootstrapV1Error):
        bootstrap._validate_package_status_result_v1(forged_status)


@pytest.mark.parametrize(
    "mutation",
    [
        "reverse",
        "duplicate_reviewer",
        "duplicate_key",
        "duplicate_public_key",
        "expired",
        "not_yet_valid",
        "valid_until_boundary",
        "wrong_key_epoch",
    ],
)
def test_reviewer_root_policy_attacks_are_rejected(mutation: str) -> None:
    roots, _ = _review_material()
    rows = list(roots)
    if mutation == "reverse":
        rows.reverse()
    elif mutation == "duplicate_reviewer":
        rows[1] = replace(
            rows[1],
            reviewer_id=rows[0].reviewer_id,
            key_id=rows[0].key_id,
        )
    elif mutation == "duplicate_key":
        rows[1] = replace(rows[1], key_id=rows[0].key_id)
    elif mutation == "duplicate_public_key":
        rows[1] = replace(
            rows[1],
            public_key_base64=rows[0].public_key_base64,
            public_key_sha256=rows[0].public_key_sha256,
        )
    elif mutation == "expired":
        rows[0] = replace(rows[0], valid_until_utc="2026-07-15T11:59:59Z")
    elif mutation == "not_yet_valid":
        rows[0] = replace(rows[0], valid_from_utc="2026-07-15T12:00:01Z")
    elif mutation == "valid_until_boundary":
        rows[0] = replace(rows[0], valid_until_utc=BOOTSTRAP_AT)
    elif mutation == "wrong_key_epoch":
        rows[0] = replace(rows[0], key_epoch=2)

    with pytest.raises(bootstrap.HipFgmresExternalReviewerRootBootstrapV1Error):
        _plan(roots=tuple(rows))


@pytest.mark.parametrize("count", [0, 2, 4])
def test_exactly_three_reviewer_roots_are_required(count: int) -> None:
    roots, _ = _review_material()
    supplied = roots[:count] if count <= 3 else roots + (roots[0],)

    with pytest.raises(bootstrap.HipFgmresExternalReviewerRootBootstrapV1Error):
        _plan(roots=supplied)


def test_wrong_nested_input_types_fail_on_stable_contract_paths() -> None:
    roots, private_keys = _review_material()
    with pytest.raises(
        bootstrap.HipFgmresExternalReviewerRootBootstrapV1Error
    ) as caught:
        _plan(roots=(object(), *roots[1:]))  # type: ignore[arg-type]
    assert caught.value.code == (
        "hip_fgmres_external_reviewer_bootstrap_reviewer_roots_invalid"
    )

    plan = _plan(roots=roots)
    endorsements = _endorsements(plan, private_keys)
    with pytest.raises(
        bootstrap.HipFgmresExternalReviewerRootBootstrapV1Error
    ) as caught:
        bootstrap.verify_hip_fgmres_external_reviewer_root_bootstrap_endorsements_v1(
            plan,
            endorsements=(object(), *endorsements[1:]),  # type: ignore[arg-type]
        )
    assert caught.value.code == (
        "hip_fgmres_external_reviewer_bootstrap_endorsements_invalid"
    )


def test_oversized_collections_fail_before_payload_materialization() -> None:
    roots, private_keys = _review_material()
    plan = _plan(roots=roots)
    with pytest.raises(
        bootstrap.HipFgmresExternalReviewerRootBootstrapV1Error
    ) as caught:
        bootstrap.validate_hip_fgmres_external_reviewer_root_bootstrap_plan_v1(
            replace(plan, reviewer_roots=roots * 10_000)
        )
    assert caught.value.code == (
        "hip_fgmres_external_reviewer_bootstrap_plan_type_invalid"
    )

    receipt = (
        bootstrap.verify_hip_fgmres_external_reviewer_root_bootstrap_endorsements_v1(
            plan,
            endorsements=_endorsements(plan, private_keys),
        )
    )
    with pytest.raises(
        bootstrap.HipFgmresExternalReviewerRootBootstrapV1Error
    ) as caught:
        bootstrap.validate_hip_fgmres_external_reviewer_root_bootstrap_receipt_v1(
            replace(receipt, endorsements=receipt.endorsements * 10_000)
        )
    assert caught.value.code == (
        "hip_fgmres_external_reviewer_bootstrap_receipt_type_invalid"
    )


def test_nested_string_extents_fail_before_hash_payload_materialization(
    monkeypatch: Any,
) -> None:
    roots, private_keys = _review_material()
    plan = _plan(roots=roots)
    endorsements = _endorsements(plan, private_keys)
    oversized = "A" * 10_000

    def unexpected_materialization(*args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        raise AssertionError("invalid nested extent reached payload materialization")

    with monkeypatch.context() as guarded:
        guarded.setattr(
            bootstrap,
            "_load_exact_source_identity_v1",
            unexpected_materialization,
        )
        for forged_root in (
            replace(roots[0], reviewer_id=oversized),
            replace(roots[0], public_key_base64=oversized),
        ):
            with pytest.raises(
                bootstrap.HipFgmresExternalReviewerRootBootstrapV1Error
            ) as caught:
                _plan(roots=(forged_root, *roots[1:]))
            assert caught.value.code == (
                "hip_fgmres_external_reviewer_bootstrap_reviewer_root_invalid"
            )

    with monkeypatch.context() as guarded:
        guarded.setattr(
            bootstrap,
            "_receipt_payload_v1",
            unexpected_materialization,
        )
        with pytest.raises(
            bootstrap.HipFgmresExternalReviewerRootBootstrapV1Error
        ) as caught:
            bootstrap.verify_hip_fgmres_external_reviewer_root_bootstrap_endorsements_v1(
                plan,
                endorsements=(
                    replace(endorsements[0], signature_base64=oversized),
                    *endorsements[1:],
                ),
            )
        assert caught.value.code == (
            "hip_fgmres_external_reviewer_bootstrap_endorsement_invalid"
        )


def test_low_order_reviewer_public_key_is_rejected() -> None:
    roots, _ = _review_material()
    low_order = b"\x00" * 32
    forged = replace(
        roots[0],
        public_key_base64=base64.b64encode(low_order).decode("ascii"),
        public_key_sha256=sha256_prefixed(low_order),
    )

    with pytest.raises(
        bootstrap.HipFgmresExternalReviewerRootBootstrapV1Error
    ) as caught:
        _plan(roots=(forged, *roots[1:]))
    assert caught.value.code == (
        "hip_fgmres_external_reviewer_bootstrap_public_key_invalid"
    )


def test_nonce_reuse_and_invalid_extents_are_rejected() -> None:
    roots, _ = _review_material()
    common = b"same-nonce" + b"\x00" * 22

    with pytest.raises(
        bootstrap.HipFgmresExternalReviewerRootBootstrapV1Error
    ) as caught:
        bootstrap.compile_hip_fgmres_external_reviewer_root_bootstrap_plan_v1(
            ceremony_id="reviewer-bootstrap.2026-07-15",
            nonce=common,
            bootstrap_at_utc=BOOTSTRAP_AT,
            target_lineage_nonce=common,
            reviewer_roots=roots,
        )
    assert caught.value.code == "hip_fgmres_external_reviewer_bootstrap_nonce_reuse"

    for invalid in (b"", b"x" * 31, b"x" * 33):
        with pytest.raises(bootstrap.HipFgmresExternalReviewerRootBootstrapV1Error):
            bootstrap.compile_hip_fgmres_external_reviewer_root_bootstrap_plan_v1(
                ceremony_id="reviewer-bootstrap.2026-07-15",
                nonce=invalid,
                bootstrap_at_utc=BOOTSTRAP_AT,
                target_lineage_nonce=b"y" * 32,
                reviewer_roots=roots,
            )


def test_plan_hash_lineage_and_target_identity_tampering_is_rejected() -> None:
    plan = _plan()
    attacks = (
        replace(plan, plan_hash="sha256:" + "1" * 64),
        replace(plan, target_lineage_id="sha256:" + "2" * 64),
        replace(plan, target_registry_id=plan.source_registry.registry_id),
        replace(plan, target_lineage_generation=2),
        replace(plan, reviewer_policy_hash="sha256:" + "3" * 64),
    )
    for forged in attacks:
        with pytest.raises(bootstrap.HipFgmresExternalReviewerRootBootstrapV1Error):
            bootstrap.validate_hip_fgmres_external_reviewer_root_bootstrap_plan_v1(
                forged
            )


def test_missing_extra_duplicate_and_reordered_endorsements_are_rejected() -> None:
    roots, private_keys = _review_material()
    plan = _plan(roots=roots)
    valid = _endorsements(plan, private_keys)
    attacks = (
        valid[:2],
        valid + (valid[0],),
        (valid[1], valid[0], valid[2]),
        (valid[0], valid[0], valid[2]),
    )
    for endorsements in attacks:
        with pytest.raises(bootstrap.HipFgmresExternalReviewerRootBootstrapV1Error):
            bootstrap.verify_hip_fgmres_external_reviewer_root_bootstrap_endorsements_v1(
                plan,
                endorsements=endorsements,
            )


def test_wrong_key_wrong_domain_and_plan_transplant_are_rejected() -> None:
    roots, private_keys = _review_material()
    plan = _plan(roots=roots)
    valid = list(_endorsements(plan, private_keys))
    wrong_key_signature = private_keys[1].sign(
        bootstrap.compile_hip_fgmres_external_reviewer_root_bootstrap_endorsement_message_v1(
            plan
        )
    )
    valid[0] = replace(
        valid[0],
        signature_base64=base64.b64encode(wrong_key_signature).decode("ascii"),
        signature_sha256=sha256_prefixed(wrong_key_signature),
    )
    with pytest.raises(
        bootstrap.HipFgmresExternalReviewerRootBootstrapV1Error
    ) as caught:
        bootstrap.verify_hip_fgmres_external_reviewer_root_bootstrap_endorsements_v1(
            plan,
            endorsements=tuple(valid),
        )
    assert caught.value.code == (
        "hip_fgmres_external_reviewer_bootstrap_signature_invalid"
    )

    valid = list(_endorsements(plan, private_keys))
    wrong_domain_signature = private_keys[0].sign(
        b"wrong-domain" + plan.plan_hash.encode()
    )
    valid[0] = replace(
        valid[0],
        signature_base64=base64.b64encode(wrong_domain_signature).decode("ascii"),
        signature_sha256=sha256_prefixed(wrong_domain_signature),
    )
    with pytest.raises(bootstrap.HipFgmresExternalReviewerRootBootstrapV1Error):
        bootstrap.verify_hip_fgmres_external_reviewer_root_bootstrap_endorsements_v1(
            plan,
            endorsements=tuple(valid),
        )

    changed_plan = replace(plan, ceremony_id="reviewer-bootstrap.transplant")
    changed_plan = _reseal_plan(changed_plan)
    with pytest.raises(bootstrap.HipFgmresExternalReviewerRootBootstrapV1Error):
        bootstrap.verify_hip_fgmres_external_reviewer_root_bootstrap_endorsements_v1(
            changed_plan,
            endorsements=_endorsements(plan, private_keys),
        )


def test_noncanonical_or_malformed_signature_is_rejected() -> None:
    roots, private_keys = _review_material()
    plan = _plan(roots=roots)
    valid = list(_endorsements(plan, private_keys))
    malformed = b"\xff" * 64
    valid[0] = replace(
        valid[0],
        signature_base64=base64.b64encode(malformed).decode("ascii"),
        signature_sha256=sha256_prefixed(malformed),
    )

    with pytest.raises(
        bootstrap.HipFgmresExternalReviewerRootBootstrapV1Error
    ) as caught:
        bootstrap.verify_hip_fgmres_external_reviewer_root_bootstrap_endorsements_v1(
            plan,
            endorsements=tuple(valid),
        )
    assert caught.value.code == (
        "hip_fgmres_external_reviewer_bootstrap_signature_invalid"
    )


def test_forged_detached_claims_and_receipt_hash_are_rejected() -> None:
    receipt = _receipt()
    forged_claims = replace(receipt.claims, package_bootstrap_inclusion_verified=True)
    forged = _reseal_receipt(replace(receipt, claims=forged_claims))
    with pytest.raises(bootstrap.HipFgmresExternalReviewerRootBootstrapV1Error):
        bootstrap.validate_hip_fgmres_external_reviewer_root_bootstrap_receipt_v1(
            forged
        )

    with pytest.raises(
        bootstrap.HipFgmresExternalReviewerRootBootstrapV1Error
    ) as caught:
        bootstrap.validate_hip_fgmres_external_reviewer_root_bootstrap_receipt_v1(
            replace(receipt, receipt_hash="sha256:" + "9" * 64)
        )
    assert caught.value.code == (
        "hip_fgmres_external_reviewer_bootstrap_receipt_hash_invalid"
    )


def test_package_status_result_cannot_be_forged_or_caller_selected() -> None:
    status = bootstrap.load_hip_fgmres_external_reviewer_root_bootstrap_status_v1()
    signature = inspect.signature(
        bootstrap.load_hip_fgmres_external_reviewer_root_bootstrap_status_v1
    )
    assert not signature.parameters

    forged = replace(status, contract_bytes_sha256="sha256:" + "8" * 64)
    with pytest.raises(bootstrap.HipFgmresExternalReviewerRootBootstrapV1Error):
        forged.to_dict()
    with pytest.raises(bootstrap.HipFgmresExternalReviewerRootBootstrapV1Error):
        bootstrap.validate_hip_fgmres_external_reviewer_root_bootstrap_status_v1(forged)


def test_package_status_to_dict_replays_the_exact_package_resource(
    monkeypatch: Any,
) -> None:
    status = bootstrap.load_hip_fgmres_external_reviewer_root_bootstrap_status_v1()
    raw = RESOURCE.read_bytes()
    monkeypatch.setattr(bootstrap, "_read_fixed_resource_v1", lambda: raw + b" ")

    with pytest.raises(
        bootstrap.HipFgmresExternalReviewerRootBootstrapV1Error
    ) as caught:
        status.to_dict()
    assert caught.value.code == (
        "hip_fgmres_external_reviewer_bootstrap_resource_hash_mismatch"
    )


def test_resource_and_schema_tampering_fail_closed(monkeypatch: Any) -> None:
    raw = RESOURCE.read_bytes()
    monkeypatch.setattr(bootstrap, "_read_fixed_resource_v1", lambda: raw + b" ")
    with pytest.raises(
        bootstrap.HipFgmresExternalReviewerRootBootstrapV1Error
    ) as caught:
        bootstrap._load_package_status_v1()
    assert caught.value.code == (
        "hip_fgmres_external_reviewer_bootstrap_resource_hash_mismatch"
    )

    monkeypatch.setattr(bootstrap, "_read_fixed_resource_v1", lambda: raw)
    monkeypatch.setattr(
        bootstrap,
        "_SCHEMA_RESOURCE_BYTES_SHA256_V1",
        "sha256:" + "0" * 64,
    )
    with pytest.raises(
        bootstrap.HipFgmresExternalReviewerRootBootstrapV1Error
    ) as caught:
        bootstrap._load_package_status_v1()
    assert caught.value.code == (
        "hip_fgmres_external_reviewer_bootstrap_schema_hash_mismatch"
    )


@pytest.mark.parametrize(
    ("raw", "code"),
    [
        (
            b'{"a":1,"a":2}',
            "hip_fgmres_external_reviewer_bootstrap_json_duplicate_key",
        ),
        (
            b"\xef\xbb\xbf{}",
            "hip_fgmres_external_reviewer_bootstrap_json_bom_forbidden",
        ),
        (b'{"a":NaN}', "hip_fgmres_external_reviewer_bootstrap_json_invalid"),
        (b"[]", "hip_fgmres_external_reviewer_bootstrap_json_root_invalid"),
    ],
)
def test_strict_json_parser_rejects_ambiguous_inputs(raw: bytes, code: str) -> None:
    with pytest.raises(
        bootstrap.HipFgmresExternalReviewerRootBootstrapV1Error
    ) as caught:
        bootstrap._parse_strict_object_v1(raw, path="/hostile")
    assert caught.value.code == code


def test_json_depth_nodes_and_error_text_are_bounded() -> None:
    deep: Any = None
    for _ in range(bootstrap._MAX_JSON_DEPTH_V1 + 1):
        deep = [deep]
    with pytest.raises(
        bootstrap.HipFgmresExternalReviewerRootBootstrapV1Error
    ) as caught:
        bootstrap._enforce_json_bounds_v1(deep, path="/deep")
    assert caught.value.code == "hip_fgmres_external_reviewer_bootstrap_extent_invalid"

    many = list(range(bootstrap._MAX_JSON_NODES_V1 + 1))
    with pytest.raises(bootstrap.HipFgmresExternalReviewerRootBootstrapV1Error):
        bootstrap._enforce_json_bounds_v1(many, path="/many")

    with pytest.raises(
        bootstrap.HipFgmresExternalReviewerRootBootstrapV1Error
    ) as caught:
        bootstrap._fail("bounded", "/" + "p" * 2000, "m" * 2000)
    assert len(caught.value.path) <= bootstrap._MAX_ERROR_PATH_CHARS_V1
    assert len(caught.value.message) <= bootstrap._MAX_ERROR_MESSAGE_CHARS_V1


def test_package_fixture_contains_no_reviewer_or_private_material() -> None:
    raw = RESOURCE.read_text(encoding="utf-8")
    manifest = json.loads(raw)

    assert manifest["bootstrap_plan"] is None
    assert manifest["bootstrap_receipt"] is None
    assert "public_key_base64" not in raw
    assert "signature_base64" not in raw
    assert "private_key" not in raw.lower()
    assert "seed" not in raw.lower()
    assert manifest["claims"]["reviewer_root_material_present"] is False
    assert manifest["claims"]["target_registry_genesis_activated"] is False
