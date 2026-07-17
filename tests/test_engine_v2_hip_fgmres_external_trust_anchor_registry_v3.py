from __future__ import annotations

import base64
from dataclasses import replace
import inspect
import json
from pathlib import Path

from jsonschema import Draft202012Validator
import pytest

from structural_analysis.engine_v2.assembly_backend import (
    fgmres_external_reviewer_root_bootstrap_v1 as bootstrap,
)
from structural_analysis.engine_v2.assembly_backend import (
    fgmres_external_trust_anchor_registry_v3 as registry_v3,
)
from structural_analysis.engine_v2.contracts._canonical import (
    canonical_hash,
    sha256_prefixed,
)
from tests.test_engine_v2_hip_fgmres_external_reviewer_root_bootstrap_v1 import (
    _receipt as _bootstrap_receipt,
)
from tests.test_engine_v2_hip_fgmres_external_reviewer_root_bootstrap_v1 import (
    _review_material,
)


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = (
    ROOT
    / "src/structural_analysis/schemas"
    / "hip_fgmres_external_trust_anchor_registry_v3.schema.json"
)
ACTIVATED_AT = "2026-07-15T13:00:00Z"


def _genesis(
    source: bootstrap.HipFgmresExternalReviewerRootBootstrapReceiptV1 | None = None,
    *,
    activated_at_utc: str = ACTIVATED_AT,
) -> registry_v3.HipFgmresExternalTrustAnchorRegistryGenesisV3:
    return registry_v3.compile_hip_fgmres_external_trust_anchor_registry_genesis_v3(
        _bootstrap_receipt() if source is None else source,
        activated_at_utc=activated_at_utc,
    )


def _endorsements(
    genesis: registry_v3.HipFgmresExternalTrustAnchorRegistryGenesisV3,
    *,
    message: bytes | None = None,
) -> tuple[registry_v3.HipFgmresExternalReviewerRootActivationEndorsementV3, ...]:
    _, private_keys = _review_material()
    signed_message = (
        registry_v3.compile_hip_fgmres_external_trust_anchor_registry_activation_message_v3(
            genesis
        )
        if message is None
        else message
    )
    rows = []
    for root, private_key in zip(genesis.reviewer_roots, private_keys, strict=True):
        signature = private_key.sign(signed_message)
        rows.append(
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
    return tuple(rows)


def _result() -> registry_v3.HipFgmresExternalTrustAnchorRegistryResultV3:
    source = _bootstrap_receipt()
    genesis = _genesis(source)
    return registry_v3.verify_hip_fgmres_external_trust_anchor_registry_activation_v3(
        source,
        genesis=genesis,
        activation_endorsements=_endorsements(genesis),
    )


def _reseal_genesis(
    genesis: registry_v3.HipFgmresExternalTrustAnchorRegistryGenesisV3,
) -> registry_v3.HipFgmresExternalTrustAnchorRegistryGenesisV3:
    draft = replace(genesis, genesis_event_hash=registry_v3._ZERO_HASH)
    return replace(
        draft,
        genesis_event_hash=canonical_hash(
            registry_v3._genesis_payload(draft, include_hash=False)
        ),
    )


def _reseal_receipt(
    receipt: registry_v3.HipFgmresExternalTrustAnchorRegistryReceiptV3,
) -> registry_v3.HipFgmresExternalTrustAnchorRegistryReceiptV3:
    registry_hash = canonical_hash(
        {
            "genesis": receipt.genesis.to_dict(),
            "activation_endorsements": [
                row.to_dict() for row in receipt.activation_endorsements
            ],
        }
    )
    draft = replace(
        receipt,
        registry_hash=registry_hash,
        receipt_hash=registry_v3._ZERO_HASH,
    )
    return replace(
        draft,
        receipt_hash=canonical_hash(
            registry_v3._receipt_payload(draft, include_hash=False)
        ),
    )


def test_three_root_second_round_activates_only_detached_genesis() -> None:
    result = _result()
    receipt = result.receipt

    assert (
        registry_v3.validate_hip_fgmres_external_trust_anchor_registry_result_v3(result)
        is result
    )
    assert receipt.schema_version.endswith("trust-anchor-registry.v3")
    assert receipt.genesis.registry_epoch == 1
    assert receipt.genesis.event_count == 1
    assert receipt.genesis.reviewer_authority_count == 3
    assert receipt.genesis.activation_endorsement_count == 3
    assert receipt.genesis.enrolled_runner_key_count == 0
    assert receipt.genesis.active_runner_key_count == 0
    assert receipt.genesis.predecessor_registry_hash is None
    assert receipt.genesis.predecessor_authority_continuity_available is False
    assert receipt.claims.all_three_root_activation_signatures_verified is True
    assert receipt.claims.source_bootstrap_receipt_replayed_in_detached_receipt is False
    assert receipt.claims.package_registry_v3_inclusion_verified is False
    assert receipt.claims.operational_reviewer_authority_activated is False
    assert receipt.claims.runner_key_activation_verified is False
    assert receipt.claims.signed_trace_binding_verified is False
    assert receipt.claims.actual_external_gfx1100_verified is False
    assert receipt.claims.promotion_eligible is False


def test_registry_v3_manifest_is_strict_schema_valid_and_deterministic() -> None:
    first = _result()
    second = _result()
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))

    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(first.to_manifest())
    assert first.receipt == second.receipt
    assert first.receipt.registry_hash == second.receipt.registry_hash
    assert first.receipt.receipt_hash == second.receipt.receipt_hash


def test_activation_requires_a_distinct_domain_from_bootstrap_possession() -> None:
    source = _bootstrap_receipt()
    genesis = _genesis(source)
    bootstrap_message = bootstrap.compile_hip_fgmres_external_reviewer_root_bootstrap_endorsement_message_v1(
        source.plan
    )

    with pytest.raises(
        registry_v3.HipFgmresExternalTrustAnchorRegistryV3Error
    ) as error:
        registry_v3.verify_hip_fgmres_external_trust_anchor_registry_activation_v3(
            source,
            genesis=genesis,
            activation_endorsements=_endorsements(
                genesis,
                message=bootstrap_message,
            ),
        )

    assert error.value.code == "hip_fgmres_external_registry_v3_endorsement_invalid"


@pytest.mark.parametrize("mode", ["missing", "duplicate", "reordered", "list"])
def test_activation_endorsement_set_is_exact_ordered_three_of_three(mode: str) -> None:
    source = _bootstrap_receipt()
    genesis = _genesis(source)
    rows = _endorsements(genesis)
    changed: object
    if mode == "missing":
        changed = rows[:-1]
    elif mode == "duplicate":
        changed = (rows[0], rows[0], rows[2])
    elif mode == "reordered":
        changed = (rows[1], rows[0], rows[2])
    else:
        changed = list(rows)

    with pytest.raises(
        registry_v3.HipFgmresExternalTrustAnchorRegistryV3Error
    ) as error:
        registry_v3.verify_hip_fgmres_external_trust_anchor_registry_activation_v3(
            source,
            genesis=genesis,
            activation_endorsements=changed,  # type: ignore[arg-type]
        )

    assert error.value.code in {
        "hip_fgmres_external_registry_v3_endorsements_invalid",
        "hip_fgmres_external_registry_v3_endorsement_invalid",
    }


def test_wrong_reviewer_key_signature_is_rejected() -> None:
    source = _bootstrap_receipt()
    genesis = _genesis(source)
    rows = _endorsements(genesis)
    changed = (replace(rows[0], signature_base64=rows[1].signature_base64), *rows[1:])
    changed = (
        replace(
            changed[0],
            signature_sha256=sha256_prefixed(
                base64.b64decode(changed[0].signature_base64)
            ),
        ),
        *changed[1:],
    )

    with pytest.raises(
        registry_v3.HipFgmresExternalTrustAnchorRegistryV3Error
    ) as error:
        registry_v3.verify_hip_fgmres_external_trust_anchor_registry_activation_v3(
            source,
            genesis=genesis,
            activation_endorsements=changed,
        )

    assert error.value.code == "hip_fgmres_external_registry_v3_endorsement_invalid"


def test_detached_receipt_commits_but_does_not_replay_bootstrap_source() -> None:
    attached = _result()
    foreign_genesis = _reseal_genesis(
        replace(
            attached.receipt.genesis,
            bootstrap_receipt_hash=canonical_hash({"foreign": "bootstrap"}),
        )
    )
    foreign_receipt = _reseal_receipt(
        replace(
            attached.receipt,
            genesis=foreign_genesis,
            activation_endorsements=_endorsements(foreign_genesis),
        )
    )

    assert (
        registry_v3.validate_hip_fgmres_external_trust_anchor_registry_receipt_v3(
            foreign_receipt
        )
        is foreign_receipt
    )
    forged_result = replace(attached, receipt=foreign_receipt)
    with pytest.raises(
        registry_v3.HipFgmresExternalTrustAnchorRegistryV3Error
    ) as error:
        registry_v3.validate_hip_fgmres_external_trust_anchor_registry_result_v3(
            forged_result
        )

    assert (
        error.value.code == "hip_fgmres_external_registry_v3_bootstrap_binding_invalid"
    )


def test_coherently_rehashed_promotion_claim_is_rejected() -> None:
    receipt = _result().receipt
    claims = replace(receipt.claims, promotion_eligible=True)
    changed = _reseal_receipt(replace(receipt, claims=claims))

    with pytest.raises(
        registry_v3.HipFgmresExternalTrustAnchorRegistryV3Error
    ) as error:
        registry_v3.validate_hip_fgmres_external_trust_anchor_registry_receipt_v3(
            changed
        )

    assert error.value.code in {
        "hip_fgmres_external_registry_v3_schema_invalid",
        "hip_fgmres_external_registry_v3_receipt_semantics_invalid",
    }


def test_boolean_integer_aliases_in_claims_and_policy_are_rejected() -> None:
    receipt = _result().receipt
    claims = replace(receipt.claims, detached_registry_genesis_self_consistent=1)
    changed_receipt = _reseal_receipt(replace(receipt, claims=claims))
    with pytest.raises(
        registry_v3.HipFgmresExternalTrustAnchorRegistryV3Error
    ) as error:
        registry_v3.validate_hip_fgmres_external_trust_anchor_registry_receipt_v3(
            changed_receipt
        )
    assert error.value.code == "hip_fgmres_external_registry_v3_schema_invalid"

    policy = replace(
        receipt.genesis.reviewer_policy,
        reviewer_root_set_immutable=1,
    )
    changed_genesis = _reseal_genesis(
        replace(
            receipt.genesis,
            reviewer_policy=policy,
            reviewer_policy_hash=canonical_hash(policy.to_dict()),
        )
    )
    with pytest.raises(
        registry_v3.HipFgmresExternalTrustAnchorRegistryV3Error
    ) as error:
        registry_v3.validate_hip_fgmres_external_trust_anchor_registry_genesis_v3(
            changed_genesis
        )
    assert (
        error.value.code == "hip_fgmres_external_registry_v3_genesis_semantics_invalid"
    )


def test_integer_boolean_alias_in_genesis_is_rejected_before_schema() -> None:
    genesis = _reseal_genesis(replace(_genesis(), registry_epoch=True))

    with pytest.raises(
        registry_v3.HipFgmresExternalTrustAnchorRegistryV3Error
    ) as error:
        registry_v3.validate_hip_fgmres_external_trust_anchor_registry_genesis_v3(
            genesis
        )

    assert (
        error.value.code == "hip_fgmres_external_registry_v3_genesis_semantics_invalid"
    )


@pytest.mark.parametrize(
    ("activated_at", "accepted"),
    [
        ("2026-07-15T12:00:00Z", False),
        ("2026-07-15T12:00:00.000001Z", True),
        ("2026-12-31T23:59:59.999999Z", True),
        ("2027-01-01T00:00:00Z", False),
    ],
)
def test_activation_time_is_strictly_after_bootstrap_and_inside_root_validity(
    activated_at: str,
    accepted: bool,
) -> None:
    if accepted:
        assert _genesis(activated_at_utc=activated_at).activated_at_utc == activated_at
        return
    with pytest.raises(registry_v3.HipFgmresExternalTrustAnchorRegistryV3Error):
        _genesis(activated_at_utc=activated_at)


def test_package_status_remains_pending_without_reviewer_or_runner_material() -> None:
    status = bootstrap.load_hip_fgmres_external_reviewer_root_bootstrap_status_v1()

    assert status.status == "pending_independent_reviewer_root_material"
    assert status.source_registry.reviewer_authority_count == 0
    assert status.source_registry.enrolled_key_count == 0
    assert status.source_registry.active_key_count == 0
    assert status.bootstrap_plan is None
    assert status.bootstrap_receipt is None
    assert status.claims.target_registry_genesis_activated is False
    assert status.claims.runner_key_activation_verified is False


def test_registry_v3_module_has_no_private_key_or_signing_api() -> None:
    source = inspect.getsource(registry_v3)

    assert "Ed25519PrivateKey" not in source
    assert ".sign(" not in source
    assert "from_private_bytes" not in source
