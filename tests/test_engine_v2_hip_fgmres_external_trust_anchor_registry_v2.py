from __future__ import annotations

import base64
from copy import deepcopy
from dataclasses import replace
from functools import lru_cache
import json
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from jsonschema import Draft202012Validator
import pytest

from structural_analysis.engine_v2.assembly_backend import (
    fgmres_external_trust_anchor_registry_v2 as registry,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_external_key_enrollment_v1 import (
    HipFgmresExternalKeyEnrollmentPredecessorKeyV1,
    compile_hip_fgmres_external_key_enrollment_challenge_v1,
    compile_hip_fgmres_external_key_enrollment_proof_message_v1,
    verify_hip_fgmres_external_key_enrollment_proof_v1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_fixture_registry_v1 import (
    HIP_FGMRES_FIXTURE_REGISTRY_SUITE_ID_V1,
    load_hip_fgmres_fixture_registry_v1,
)
from structural_analysis.engine_v2.contracts._canonical import (
    canonical_hash,
    canonical_json_bytes,
    sha256_prefixed,
)


ROOT = Path(__file__).resolve().parents[1]
RESOURCE = (
    ROOT
    / "src/structural_analysis/engine_v2/assembly_backend/fixtures"
    / "fgmres_external_trust_anchors_v2/registry.v2.json"
)
SCHEMA = (
    ROOT
    / "src/structural_analysis/schemas"
    / "hip_fgmres_external_trust_anchor_registry_v2.schema.json"
)
INIT_AT = "2026-07-15T00:00:00Z"
ENROLL_1_AT = "2026-07-15T00:00:01Z"
ACTIVATE_1_AT = "2026-07-15T00:01:00Z"
ENROLL_2_AT = "2026-07-15T00:02:00Z"
ROTATE_AT = "2026-07-15T00:10:00Z"
KEY_2_END = "2026-07-15T00:20:00Z"
REVOKE_AT = "2026-07-15T00:11:00Z"


@lru_cache(maxsize=1)
def _fixture_registry() -> Any:
    """Avoid replaying the immutable package fixture registry per test builder."""

    return load_hip_fgmres_fixture_registry_v1()


def _public_bytes(private_key: Ed25519PrivateKey) -> bytes:
    return private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )


def _review_material() -> tuple[list[dict[str, Any]], list[Ed25519PrivateKey]]:
    private_keys = [Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()]
    rows = []
    for index, private_key in enumerate(private_keys, start=1):
        reviewer_id = f"reviewer.{index}"
        public_key = _public_bytes(private_key)
        rows.append(
            {
                "reviewer_id": reviewer_id,
                "key_id": f"ed25519-review:{reviewer_id}:v1",
                "key_epoch": 1,
                "public_key_base64": base64.b64encode(public_key).decode("ascii"),
                "public_key_sha256": sha256_prefixed(public_key),
                "valid_from_utc": "2026-01-01T00:00:00Z",
                "valid_until_utc": "2027-01-01T00:00:00Z",
            }
        )
    return rows, private_keys


def _init_event() -> dict[str, Any]:
    event = {
        "sequence": 1,
        "event_type": "registry_initialized",
        "occurred_at_utc": INIT_AT,
        "previous_event_hash": None,
        "action": {
            "registry_id": registry.HIP_FGMRES_EXTERNAL_TRUST_ANCHOR_REGISTRY_ID_V2,
            "minimum_reviewer_approvals": 2,
            "reviewer_authority_count": 0,
            "reviewer_authority_commitment_hash": canonical_hash([]),
        },
        "approvals": [],
    }
    event["event_hash"] = canonical_hash(event)
    return event


def _reviewer_objects(
    reviewer_rows: list[dict[str, Any]],
) -> tuple[registry.HipFgmresExternalTrustReviewerAuthorityV2, ...]:
    return tuple(
        registry.HipFgmresExternalTrustReviewerAuthorityV2(**row)
        for row in reviewer_rows
    )


def _seal_manifest(
    events: list[dict[str, Any]],
    reviewer_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    events[0]["action"]["reviewer_authority_count"] = len(reviewer_rows)
    events[0]["action"]["reviewer_authority_commitment_hash"] = canonical_hash(
        reviewer_rows
    )
    events[0]["event_hash"] = canonical_hash(
        {key: value for key, value in events[0].items() if key != "event_hash"}
    )
    if len(events) > 1:
        # The initial authority commitment is immutable.  Synthetic builders set
        # it before approving later events; callers may not mutate it afterwards.
        for index in range(1, len(events)):
            if index == 1:
                events[index]["previous_event_hash"] = events[0]["event_hash"]
    prefix_hashes = registry._registry_prefix_hashes_v2(
        events=events,
        reviewers=_reviewer_objects(reviewer_rows),
    )
    payload = {
        "schema_version": (
            registry.HIP_FGMRES_EXTERNAL_TRUST_ANCHOR_REGISTRY_SCHEMA_VERSION_V2
        ),
        "capability_profile": (
            registry.HIP_FGMRES_EXTERNAL_TRUST_ANCHOR_REGISTRY_CAPABILITY_PROFILE_V2
        ),
        "evidence_scope": (
            registry.HIP_FGMRES_EXTERNAL_TRUST_ANCHOR_REGISTRY_EVIDENCE_SCOPE_V2
        ),
        "registry_epoch": len(events),
        "predecessor_registry_epoch": len(events) - 1,
        "predecessor_registry_hash": (None if len(events) == 1 else prefix_hashes[-2]),
        "reviewer_authorities": reviewer_rows,
        "events": events,
    }
    payload["registry_hash"] = prefix_hashes[-1]
    return payload


def _approved_event(
    *,
    events: list[dict[str, Any]],
    event_type: str,
    occurred_at_utc: str,
    action: dict[str, Any],
    reviewer_rows: list[dict[str, Any]],
    reviewer_private_keys: list[Ed25519PrivateKey],
) -> dict[str, Any]:
    event = {
        "sequence": len(events) + 1,
        "event_type": event_type,
        "occurred_at_utc": occurred_at_utc,
        "previous_event_hash": events[-1]["event_hash"],
        "action": action,
        "approvals": [],
    }
    message = registry._review_approval_message_v2(event)
    event["approvals"] = [
        {
            "reviewer_id": row["reviewer_id"],
            "reviewer_key_id": row["key_id"],
            "signature_base64": base64.b64encode(private_key.sign(message)).decode(
                "ascii"
            ),
        }
        for row, private_key in zip(reviewer_rows, reviewer_private_keys, strict=True)
    ]
    event["event_hash"] = canonical_hash(event)
    return event


def _enrollment_receipt(
    *,
    events: list[dict[str, Any]],
    reviewer_rows: list[dict[str, Any]],
    runner_private_key: Ed25519PrivateKey,
    runner_id: str,
    key_epoch: int,
    minimum_run_sequence: int,
    maximum_run_sequence: int,
    valid_from_utc: str,
    valid_until_utc: str,
    predecessor_key: HipFgmresExternalKeyEnrollmentPredecessorKeyV1 | None,
    predecessor_epoch_override: int | None = None,
) -> Any:
    fixture_registry = _fixture_registry()
    public_key = _public_bytes(runner_private_key)
    predecessor_epoch = (
        len(events)
        if predecessor_epoch_override is None
        else predecessor_epoch_override
    )
    predecessor_hash = _seal_manifest(events, reviewer_rows)["registry_hash"]
    challenge = compile_hip_fgmres_external_key_enrollment_challenge_v1(
        nonce=bytes([key_epoch]) * 32,
        request_id=f"request:enroll:{runner_id}:v{key_epoch}",
        runner_id=runner_id,
        key_id=f"ed25519:{runner_id}:v{key_epoch}",
        key_epoch=key_epoch,
        predecessor_registry_epoch=predecessor_epoch,
        predecessor_registry_hash=predecessor_hash,
        target_registry_epoch=predecessor_epoch + 1,
        predecessor_key=predecessor_key,
        public_key=public_key,
        public_key_sha256=sha256_prefixed(public_key),
        allowed_architecture_base="gfx1100",
        allowed_suite_id=HIP_FGMRES_FIXTURE_REGISTRY_SUITE_ID_V1,
        allowed_fixture_registry_bytes_sha256=(fixture_registry.registry_bytes_sha256),
        allowed_fixture_registry_hash=fixture_registry.registry_hash,
        minimum_run_sequence=minimum_run_sequence,
        maximum_run_sequence=maximum_run_sequence,
        valid_from_utc=valid_from_utc,
        valid_until_utc=valid_until_utc,
        runner_declared_key_origin="runner_declared_isolated_hsm",
        attestation_digest_sha256=None,
    )
    proof = runner_private_key.sign(
        compile_hip_fgmres_external_key_enrollment_proof_message_v1(challenge)
    )
    return verify_hip_fgmres_external_key_enrollment_proof_v1(
        challenge,
        proof_signature_base64=base64.b64encode(proof).decode("ascii"),
    )


def _active_manifest() -> tuple[dict[str, Any], dict[str, Any]]:
    reviewer_rows, reviewer_private_keys = _review_material()
    runner_private_key = Ed25519PrivateKey.generate()
    events = [_init_event()]
    receipt = _enrollment_receipt(
        events=events,
        reviewer_rows=reviewer_rows,
        runner_private_key=runner_private_key,
        runner_id="external-runner",
        key_epoch=1,
        minimum_run_sequence=1,
        maximum_run_sequence=10,
        valid_from_utc=ACTIVATE_1_AT,
        valid_until_utc=ROTATE_AT,
        predecessor_key=None,
    )
    events.append(
        _approved_event(
            events=events,
            event_type="key_enrolled",
            occurred_at_utc=ENROLL_1_AT,
            action={"enrollment_receipt": receipt.to_dict()},
            reviewer_rows=reviewer_rows,
            reviewer_private_keys=reviewer_private_keys,
        )
    )
    events.append(
        _approved_event(
            events=events,
            event_type="key_activated",
            occurred_at_utc=ACTIVATE_1_AT,
            action={
                "key_id": "ed25519:external-runner:v1",
                "activated_at_utc": ACTIVATE_1_AT,
            },
            reviewer_rows=reviewer_rows,
            reviewer_private_keys=reviewer_private_keys,
        )
    )
    return _seal_manifest(events, reviewer_rows), {
        "events": events,
        "reviewer_rows": reviewer_rows,
        "reviewer_private_keys": reviewer_private_keys,
        "runner_private_key": runner_private_key,
        "receipt": receipt,
    }


def _rotated_manifest() -> tuple[dict[str, Any], dict[str, Any]]:
    _, context = _active_manifest()
    events = context["events"]
    reviewer_rows = context["reviewer_rows"]
    reviewer_private_keys = context["reviewer_private_keys"]
    successor_private_key = Ed25519PrivateKey.generate()
    predecessor = HipFgmresExternalKeyEnrollmentPredecessorKeyV1(
        key_id="ed25519:external-runner:v1",
        key_epoch=1,
        public_key_sha256=sha256_prefixed(_public_bytes(context["runner_private_key"])),
        maximum_run_sequence=10,
    )
    receipt = _enrollment_receipt(
        events=events,
        reviewer_rows=reviewer_rows,
        runner_private_key=successor_private_key,
        runner_id="external-runner",
        key_epoch=2,
        minimum_run_sequence=11,
        maximum_run_sequence=20,
        valid_from_utc=ROTATE_AT,
        valid_until_utc=KEY_2_END,
        predecessor_key=predecessor,
    )
    events.append(
        _approved_event(
            events=events,
            event_type="key_enrolled",
            occurred_at_utc=ENROLL_2_AT,
            action={"enrollment_receipt": receipt.to_dict()},
            reviewer_rows=reviewer_rows,
            reviewer_private_keys=reviewer_private_keys,
        )
    )
    events.append(
        _approved_event(
            events=events,
            event_type="key_rotated",
            occurred_at_utc=ROTATE_AT,
            action={
                "retired_key_id": "ed25519:external-runner:v1",
                "successor_key_id": "ed25519:external-runner:v2",
                "rotated_at_utc": ROTATE_AT,
            },
            reviewer_rows=reviewer_rows,
            reviewer_private_keys=reviewer_private_keys,
        )
    )
    context["successor_private_key"] = successor_private_key
    context["successor_receipt"] = receipt
    return _seal_manifest(events, reviewer_rows), context


def _compile(manifest: dict[str, Any]) -> Any:
    return registry._compile_hip_fgmres_external_trust_anchor_registry_snapshot_v2(
        manifest,
        registry_bytes_sha256=canonical_hash({"synthetic-registry": manifest}),
    )


def _reseal_after_event_mutation(manifest: dict[str, Any]) -> None:
    reviewers = _reviewer_objects(manifest["reviewer_authorities"])
    prefixes = registry._registry_prefix_hashes_v2(
        events=manifest["events"], reviewers=reviewers
    )
    manifest["predecessor_registry_epoch"] = manifest["registry_epoch"] - 1
    manifest["predecessor_registry_hash"] = (
        None if manifest["registry_epoch"] == 1 else prefixes[-2]
    )
    manifest["registry_hash"] = prefixes[-1]


def test_package_registry_v2_is_exact_empty_initial_nonpromoting() -> None:
    result = registry.load_hip_fgmres_external_trust_anchor_registry_v2()
    payload = result.to_dict()
    assert result.registry_bytes_sha256 == (
        "sha256:dfa6172c8819f812d9992f64e6e3d5fa0f97e7c2651b49ca7ee47ccc557a2fbc"
    )
    assert result.registry_hash == (
        "sha256:5dc12aa7bb553f1852eb702f1d0ad6f3b927f193dcd7ce28f85a5c9658d6b1e4"
    )
    assert (result.registry_epoch, result.event_count) == (1, 1)
    assert result.predecessor_registry_epoch == 0
    assert result.predecessor_registry_hash is None
    assert result.reviewer_authorities == ()
    assert result.keys == ()
    assert result.active_key_count == 0
    assert payload["enrolled_key_count"] == 0
    assert payload["claims"]["private_keys_packaged"] is False
    assert payload["claims"]["historical_recovery_verified"] is False
    assert payload["claims"]["operational_reviewer_bootstrap_verified"] is False
    assert payload["claims"]["promotion_eligible"] is False
    assert payload["claims"]["commercial_ready"] is False
    assert (
        registry.validate_hip_fgmres_external_trust_anchor_registry_result_v2(result)
        is result
    )


def test_package_registry_v2_resource_matches_schema_and_hashes() -> None:
    payload = json.loads(RESOURCE.read_text(encoding="utf-8"))
    schema = registry._parse_strict_object_v2(SCHEMA.read_bytes(), path="/schema-test")
    Draft202012Validator.check_schema(schema)
    assert not list(Draft202012Validator(schema).iter_errors(payload))
    prefixes = registry._registry_prefix_hashes_v2(
        events=payload["events"],
        reviewers=_reviewer_objects(payload["reviewer_authorities"]),
    )
    assert payload["registry_hash"] == prefixes[-1]
    assert payload["events"][0]["event_hash"] == canonical_hash(
        {
            key: value
            for key, value in payload["events"][0].items()
            if key != "event_hash"
        }
    )


def test_low_order_reviewer_public_key_is_rejected_at_registry_compile() -> None:
    reviewer_rows, _ = _review_material()
    low_order = b"\x00" * 32
    reviewer_rows[0]["public_key_base64"] = base64.b64encode(low_order).decode("ascii")
    reviewer_rows[0]["public_key_sha256"] = sha256_prefixed(low_order)
    with pytest.raises(registry.HipFgmresExternalTrustAnchorRegistryV2Error) as caught:
        _compile(_seal_manifest([_init_event()], reviewer_rows))
    assert caught.value.code == (
        "hip_fgmres_external_trust_registry_v2_reviewer_key_invalid"
    )


def test_declared_registry_hash_must_equal_final_rolling_hash() -> None:
    manifest = registry._parse_strict_object_v2(
        RESOURCE.read_bytes(), path="/registry-test"
    )
    manifest["registry_hash"] = canonical_hash(
        {key: value for key, value in manifest.items() if key != "registry_hash"}
    )
    with pytest.raises(registry.HipFgmresExternalTrustAnchorRegistryV2Error) as caught:
        _compile(manifest)
    assert caught.value.code == (
        "hip_fgmres_external_trust_registry_v2_content_hash_mismatch"
    )


def test_registry_prefix_hash_is_fixed_shape_linear_rolling_chain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event_count = 800
    events = [
        {"event_hash": canonical_hash({"synthetic-event": index})}
        for index in range(1, event_count + 1)
    ]
    actual_canonical_hash = registry.canonical_hash
    rolling_payloads: list[dict[str, Any]] = []

    def observed_canonical_hash(value: Any) -> str:
        if type(value) is dict and "head_event_hash" in value:
            rolling_payloads.append(value)
        return actual_canonical_hash(value)

    monkeypatch.setattr(registry, "canonical_hash", observed_canonical_hash)
    prefixes = registry._registry_prefix_hashes_v2(events=events, reviewers=())

    expected_fields = {
        "schema_version",
        "capability_profile",
        "evidence_scope",
        "registry_epoch",
        "predecessor_registry_hash",
        "reviewer_authority_commitment_hash",
        "head_event_hash",
    }
    assert len(prefixes) == len(rolling_payloads) == event_count
    assert all(set(payload) == expected_fields for payload in rolling_payloads)
    assert rolling_payloads[0]["predecessor_registry_hash"] is None
    assert all(
        rolling_payloads[index]["predecessor_registry_hash"] == prefixes[index - 1]
        for index in range(1, event_count)
    )
    assert all(
        payload["head_event_hash"] == event["event_hash"]
        for payload, event in zip(rolling_payloads, events, strict=True)
    )
    assert max(map(len, map(canonical_json_bytes, rolling_payloads))) < 600


def test_runner_indexes_avoid_full_key_scans_and_enforce_exact_successor() -> None:
    class NoFullScanKeyMap(dict[str, Any]):
        def values(self) -> Any:
            raise AssertionError("full-key scan is forbidden during event replay")

    predecessor_registry_hash = canonical_hash({"registry-epoch": 1})
    first_public_key = _public_bytes(Ed25519PrivateKey.generate())
    first_public_hash = sha256_prefixed(first_public_key)
    first = registry._EnrollmentViewV2(
        key_id="ed25519:linear-runner:v1",
        key_epoch=1,
        runner_id="linear-runner",
        public_key_base64=base64.b64encode(first_public_key).decode("ascii"),
        public_key_sha256=first_public_hash,
        allowed_architecture_base="gfx1100",
        allowed_suite_id="linear-suite",
        allowed_fixture_registry_bytes_sha256=canonical_hash({"fixture-raw": 1}),
        allowed_fixture_registry_hash=canonical_hash({"fixture": 1}),
        minimum_run_sequence=1,
        maximum_run_sequence=10,
        valid_from_utc="2026-07-15T00:01:00Z",
        valid_until_utc="2026-07-15T00:10:00Z",
        predecessor_registry_epoch=1,
        predecessor_registry_hash=predecessor_registry_hash,
        target_registry_epoch=2,
        predecessor_key_id=None,
        predecessor_key_epoch=None,
        predecessor_public_key_sha256=None,
        predecessor_maximum_run_sequence=None,
        receipt_hash=canonical_hash({"receipt": 1}),
    )
    assert registry._validate_enrollment_view_v2(first, path="/linear/first") is None
    hostile_views = (
        replace(first, maximum_run_sequence=None),
        replace(first, valid_until_utc=None),
        replace(first, key_epoch=100_001),
        replace(first, maximum_run_sequence=9_223_372_036_854_775_808),
    )
    for hostile_view in hostile_views:
        with pytest.raises(
            registry.HipFgmresExternalTrustAnchorRegistryV2Error
        ) as hostile:
            registry._validate_enrollment_view_v2(hostile_view, path="/linear/hostile")
        assert hostile.value.code == (
            "hip_fgmres_external_trust_registry_v2_enrollment_invalid"
        )
    keys: NoFullScanKeyMap = NoFullScanKeyMap()
    runner_predecessors: dict[str, registry._EnrollmentViewV2] = {}
    public_hashes: set[str] = set()
    registry._apply_enrollment_v2(
        first,
        event={"sequence": 2, "event_hash": canonical_hash({"event": 2})},
        expected_predecessor_registry_hash=predecessor_registry_hash,
        keys=keys,
        runner_predecessors=runner_predecessors,
        public_hashes=public_hashes,
        path="/linear/first",
    )

    active_key_by_runner: dict[str, str] = {}
    registry._apply_activation_v2(
        {
            "action": {
                "key_id": first.key_id,
                "activated_at_utc": first.valid_from_utc,
            },
            "occurred_at_utc": first.valid_from_utc,
            "event_hash": canonical_hash({"event": "activate"}),
        },
        keys=keys,
        active_key_by_runner=active_key_by_runner,
        path="/linear/activate",
    )
    assert active_key_by_runner == {first.runner_id: first.key_id}

    successor_registry_hash = canonical_hash({"registry-epoch": 2})
    successor = replace(
        first,
        key_id="ed25519:linear-runner:v2",
        key_epoch=2,
        public_key_sha256=canonical_hash({"public-key": 2}),
        minimum_run_sequence=11,
        maximum_run_sequence=20,
        valid_from_utc=first.valid_until_utc,
        valid_until_utc="2026-07-15T00:20:00Z",
        predecessor_registry_epoch=2,
        predecessor_registry_hash=successor_registry_hash,
        target_registry_epoch=3,
        predecessor_key_id=first.key_id,
        predecessor_key_epoch=first.key_epoch,
        predecessor_public_key_sha256=first.public_key_sha256,
        predecessor_maximum_run_sequence=first.maximum_run_sequence,
        receipt_hash=canonical_hash({"receipt": 2}),
    )
    with pytest.raises(
        registry.HipFgmresExternalTrustAnchorRegistryV2Error
    ) as noncontiguous:
        registry._apply_enrollment_v2(
            replace(successor, minimum_run_sequence=12),
            event={"sequence": 3, "event_hash": canonical_hash({"event": 3})},
            expected_predecessor_registry_hash=successor_registry_hash,
            keys=keys,
            runner_predecessors=runner_predecessors,
            public_hashes=public_hashes,
            path="/linear/successor",
        )
    assert noncontiguous.value.code == (
        "hip_fgmres_external_trust_registry_v2_key_sequence_not_contiguous"
    )

    registry._apply_enrollment_v2(
        successor,
        event={"sequence": 3, "event_hash": canonical_hash({"event": 3})},
        expected_predecessor_registry_hash=successor_registry_hash,
        keys=keys,
        runner_predecessors=runner_predecessors,
        public_hashes=public_hashes,
        path="/linear/successor",
    )
    assert runner_predecessors[first.runner_id] is successor


def test_derived_keys_accept_interleaved_runner_event_order_in_linear_pass() -> None:
    def anchor(
        runner_id: str,
        key_epoch: int,
        minimum_run_sequence: int,
        maximum_run_sequence: int,
        valid_from_utc: str,
        valid_until_utc: str,
    ) -> registry.HipFgmresExternalTrustAnchorV2:
        private_key = Ed25519PrivateKey.generate()
        public_key = _public_bytes(private_key)
        return registry.HipFgmresExternalTrustAnchorV2(
            key_id=f"ed25519:{runner_id}:v{key_epoch}",
            key_epoch=key_epoch,
            status="enrolled",
            runner_id=runner_id,
            public_key_base64=base64.b64encode(public_key).decode("ascii"),
            public_key_sha256=sha256_prefixed(public_key),
            allowed_architecture_base="gfx1100",
            allowed_suite_id="linear-interleaved-suite",
            allowed_fixture_registry_bytes_sha256=canonical_hash(
                {"fixture-raw": runner_id}
            ),
            allowed_fixture_registry_hash=canonical_hash({"fixture": runner_id}),
            minimum_run_sequence=minimum_run_sequence,
            maximum_run_sequence=maximum_run_sequence,
            valid_from_utc=valid_from_utc,
            valid_until_utc=valid_until_utc,
            enrollment_receipt_hash=canonical_hash({"receipt": [runner_id, key_epoch]}),
            enrollment_event_hash=canonical_hash({"event": [runner_id, key_epoch]}),
            activation_event_hash=None,
            activated_at_utc=None,
            terminal_event_hash=None,
            terminal_at_utc=None,
            revocation_effect=None,
            terminal_reason=None,
        )

    runner_b_v1 = anchor(
        "runner-b",
        1,
        1,
        10,
        "2026-07-15T00:00:00Z",
        "2026-07-15T00:10:00Z",
    )
    runner_a_v1 = anchor(
        "runner-a",
        1,
        1,
        10,
        "2026-07-15T00:00:00Z",
        "2026-07-15T00:10:00Z",
    )
    runner_b_v2 = anchor(
        "runner-b",
        2,
        11,
        20,
        "2026-07-15T00:10:00Z",
        "2026-07-15T00:20:00Z",
    )

    assert (
        registry._validate_derived_keys_v2((runner_b_v1, runner_a_v1, runner_b_v2))
        is None
    )
    hostile_anchors = (
        replace(runner_b_v1, maximum_run_sequence=None),
        replace(runner_b_v1, valid_until_utc=None),
        replace(runner_b_v1, key_epoch=100_001),
        replace(
            runner_b_v1,
            maximum_run_sequence=9_223_372_036_854_775_808,
        ),
    )
    for hostile_anchor in hostile_anchors:
        with pytest.raises(
            registry.HipFgmresExternalTrustAnchorRegistryV2Error
        ) as hostile:
            registry._validate_derived_keys_v2((hostile_anchor,))
        assert hostile.value.code == (
            "hip_fgmres_external_trust_registry_v2_derived_key_invalid"
        )


@pytest.mark.parametrize(
    ("raw", "code"),
    [
        (
            b"\xef\xbb\xbf{}",
            "hip_fgmres_external_trust_registry_v2_json_bom_forbidden",
        ),
        (
            b'{"a":1,"a":2}',
            "hip_fgmres_external_trust_registry_v2_json_duplicate_key",
        ),
        (
            b'{"a":NaN}',
            "hip_fgmres_external_trust_registry_v2_json_invalid",
        ),
    ],
)
def test_registry_v2_strict_parser_rejects_alternate_json(
    raw: bytes, code: str
) -> None:
    with pytest.raises(registry.HipFgmresExternalTrustAnchorRegistryV2Error) as caught:
        registry._parse_strict_object_v2(raw, path="/test")
    assert caught.value.code == code


def test_registry_v2_strict_parser_bounds_depth_and_error_path() -> None:
    for depth in (65, 2_000):
        raw = b'{"a":' * depth + b"0" + b"}" * depth
        with pytest.raises(
            registry.HipFgmresExternalTrustAnchorRegistryV2Error
        ) as caught:
            registry._parse_strict_object_v2(raw, path="/test")
        assert caught.value.code == (
            "hip_fgmres_external_trust_registry_v2_extent_invalid"
        )
        assert len(caught.value.path) <= registry._MAX_ERROR_PATH_CHARS


def test_registry_v2_hostile_values_cannot_amplify_error_output() -> None:
    hostile = "x" * 100_001

    def assert_bounded(
        error: registry.HipFgmresExternalTrustAnchorRegistryV2Error,
    ) -> None:
        assert hostile not in str(error)
        assert len(error.message) <= registry._MAX_ERROR_MESSAGE_CHARS
        assert len(error.path) <= registry._MAX_ERROR_PATH_CHARS
        assert len(str(error)) <= 1_024

    hostile_key = hostile.encode("ascii")
    duplicate_raw = b'{"' + hostile_key + b'":1,"' + hostile_key + b'":2}'
    with pytest.raises(
        registry.HipFgmresExternalTrustAnchorRegistryV2Error
    ) as duplicate:
        registry._parse_strict_object_v2(duplicate_raw, path="/duplicate")
    assert duplicate.value.code == (
        "hip_fgmres_external_trust_registry_v2_json_duplicate_key"
    )
    assert duplicate.value.message == "duplicate object member"
    assert_bounded(duplicate.value)

    manifest = registry._parse_strict_object_v2(
        RESOURCE.read_bytes(), path="/registry-hostile"
    )
    manifest[hostile] = hostile
    with pytest.raises(registry.HipFgmresExternalTrustAnchorRegistryV2Error) as schema:
        _compile(manifest)
    assert schema.value.code == (
        "hip_fgmres_external_trust_registry_v2_schema_validation_failed"
    )
    assert schema.value.message == (
        "schema keyword additionalProperties rejected value"
    )
    assert_bounded(schema.value)

    def hostile_validator(_: dict[str, Any]) -> Any:
        raise RuntimeError(hostile)

    with pytest.raises(
        registry.HipFgmresExternalTrustAnchorRegistryV2Error
    ) as injected:
        registry._validated_enrollment_view_v2(
            {},
            validator=hostile_validator,
            path="/" + hostile,
        )
    assert injected.value.code == (
        "hip_fgmres_external_trust_registry_v2_enrollment_invalid"
    )
    assert injected.value.message == "RuntimeError"
    assert_bounded(injected.value)


def test_direct_public_key_and_string_extents_fail_before_decode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest, context = _active_manifest()
    result = _compile(manifest)
    reviewer = _reviewer_objects(context["reviewer_rows"])[0]
    view = registry._validated_enrollment_view_v2(
        context["receipt"].to_dict(),
        validator=None,
        path="/direct/view",
    )
    anchor = result.keys[0]
    hostile = "A" * 1_000_000
    hostile_reviewer = replace(reviewer, public_key_base64=hostile)
    hostile_view = replace(view, public_key_base64=hostile)
    hostile_anchor = replace(anchor, public_key_base64=hostile)

    def decoder_must_not_run(*_: Any, **__: Any) -> Any:
        raise AssertionError("oversized public key reached Base64 decoder")

    monkeypatch.setattr(
        registry,
        "decode_canonical_base64_v1",
        decoder_must_not_run,
    )

    with pytest.raises(
        registry.HipFgmresExternalTrustAnchorRegistryV2Error
    ) as reviewer_property:
        hostile_reviewer.public_key_bytes
    assert reviewer_property.value.code == (
        "hip_fgmres_external_trust_registry_v2_reviewer_key_invalid"
    )
    with pytest.raises(
        registry.HipFgmresExternalTrustAnchorRegistryV2Error
    ) as anchor_property:
        hostile_anchor.public_key_bytes
    assert anchor_property.value.code == (
        "hip_fgmres_external_trust_registry_v2_runner_key_invalid"
    )
    with pytest.raises(
        registry.HipFgmresExternalTrustAnchorRegistryV2Error
    ) as reviewer_validator:
        registry._validate_reviewer_authorities_v2((hostile_reviewer,))
    assert reviewer_validator.value.code == (
        "hip_fgmres_external_trust_registry_v2_reviewer_invalid"
    )
    with pytest.raises(
        registry.HipFgmresExternalTrustAnchorRegistryV2Error
    ) as view_validator:
        registry._validate_enrollment_view_v2(hostile_view, path="/direct/view")
    assert view_validator.value.code == (
        "hip_fgmres_external_trust_registry_v2_enrollment_invalid"
    )
    with pytest.raises(
        registry.HipFgmresExternalTrustAnchorRegistryV2Error
    ) as result_validator:
        registry._validate_hip_fgmres_external_trust_anchor_registry_snapshot_result_v2(
            replace(result, keys=(hostile_anchor,))
        )
    assert result_validator.value.code == (
        "hip_fgmres_external_trust_registry_v2_derived_key_invalid"
    )

    for hostile_key in (
        replace(anchor, key_id="ed25519:runner:v" + "9" * 1_000_000),
        replace(anchor, allowed_suite_id=hostile),
    ):
        with pytest.raises(
            registry.HipFgmresExternalTrustAnchorRegistryV2Error
        ) as extent:
            registry._validate_derived_keys_v2((hostile_key,))
        assert extent.value.code == (
            "hip_fgmres_external_trust_registry_v2_derived_key_invalid"
        )
        assert len(str(extent.value)) <= 1_024

    with pytest.raises(
        registry.HipFgmresExternalTrustAnchorRegistryV2Error
    ) as timestamp:
        registry._parse_utc_v2(hostile + "Z", "/direct/timestamp")
    assert timestamp.value.code == (
        "hip_fgmres_external_trust_registry_v2_timestamp_invalid"
    )
    assert len(str(timestamp.value)) <= 1_024


def test_structural_registry_v2_enrolls_and_activates_real_pop_receipt() -> None:
    manifest, context = _active_manifest()
    result = _compile(manifest)
    assert (result.registry_epoch, result.event_count) == (3, 3)
    assert result.enrolled_key_count == 1
    assert result.active_key_count == 1
    key = result.keys[0]
    assert key.status == "active"
    assert key.activated_at_utc == ACTIVATE_1_AT
    assert key.enrollment_receipt_hash == context["receipt"].receipt_hash
    assert key.activation_event_hash == manifest["events"][2]["event_hash"]
    assert key.terminal_event_hash is None


def test_detached_active_key_requires_exact_reviewer_activation_time() -> None:
    result = _compile(_active_manifest()[0])
    active = result.keys[0]
    for invalid in (
        replace(active, activated_at_utc=None),
        replace(active, activation_event_hash=None),
        replace(active, activated_at_utc="2026-07-15T00:00:00Z"),
    ):
        draft = replace(
            result,
            keys=(invalid,),
            receipt_hash="sha256:" + "0" * 64,
        )
        forged = replace(
            draft,
            receipt_hash=canonical_hash(
                registry._result_payload_v2(draft, include_hash=False)
            ),
        )
        with pytest.raises(
            registry.HipFgmresExternalTrustAnchorRegistryV2Error
        ) as caught:
            registry._validate_hip_fgmres_external_trust_anchor_registry_snapshot_result_v2(
                forged
            )
        assert caught.value.code == (
            "hip_fgmres_external_trust_registry_v2_derived_key_invalid"
        )


def test_detached_terminal_time_must_strictly_follow_activation_time() -> None:
    result = _compile(_rotated_manifest()[0])
    retired, active = result.keys
    invalid = replace(retired, terminal_at_utc=retired.activated_at_utc)
    draft = replace(
        result,
        keys=(invalid, active),
        receipt_hash="sha256:" + "0" * 64,
    )
    forged = replace(
        draft,
        receipt_hash=canonical_hash(
            registry._result_payload_v2(draft, include_hash=False)
        ),
    )
    with pytest.raises(registry.HipFgmresExternalTrustAnchorRegistryV2Error) as caught:
        registry._validate_hip_fgmres_external_trust_anchor_registry_snapshot_result_v2(
            forged
        )
    assert caught.value.code == (
        "hip_fgmres_external_trust_registry_v2_derived_key_invalid"
    )


def test_event_chain_predecessor_and_epoch_mutation_fail_closed() -> None:
    manifest, _ = _active_manifest()
    broken = deepcopy(manifest)
    broken["events"][2]["previous_event_hash"] = canonical_hash(
        {"wrong": "predecessor"}
    )
    _reseal_after_event_mutation(broken)
    with pytest.raises(
        registry.HipFgmresExternalTrustAnchorRegistryV2Error
    ) as predecessor:
        _compile(broken)
    assert predecessor.value.code in {
        "hip_fgmres_external_trust_registry_v2_event_predecessor_invalid",
        "hip_fgmres_external_trust_registry_v2_event_hash_invalid",
    }

    _, context = _active_manifest()
    events = [_init_event()]
    receipt = _enrollment_receipt(
        events=events,
        reviewer_rows=context["reviewer_rows"],
        runner_private_key=Ed25519PrivateKey.generate(),
        runner_id="epoch-skip-runner",
        key_epoch=1,
        minimum_run_sequence=1,
        maximum_run_sequence=5,
        valid_from_utc=ACTIVATE_1_AT,
        valid_until_utc=ROTATE_AT,
        predecessor_key=None,
        predecessor_epoch_override=2,
    )
    events.append(
        _approved_event(
            events=events,
            event_type="key_enrolled",
            occurred_at_utc=ENROLL_1_AT,
            action={"enrollment_receipt": receipt.to_dict()},
            reviewer_rows=context["reviewer_rows"],
            reviewer_private_keys=context["reviewer_private_keys"],
        )
    )
    with pytest.raises(registry.HipFgmresExternalTrustAnchorRegistryV2Error) as epoch:
        _compile(_seal_manifest(events, context["reviewer_rows"]))
    assert epoch.value.code == (
        "hip_fgmres_external_trust_registry_v2_enrollment_binding_invalid"
    )


def test_reviewer_approval_insufficient_duplicate_wrong_key_and_domain_rejected() -> (
    None
):
    manifest, context = _active_manifest()

    insufficient = deepcopy(manifest)
    insufficient["events"][1]["approvals"] = insufficient["events"][1]["approvals"][:1]
    insufficient["events"][1]["event_hash"] = canonical_hash(
        {
            key: value
            for key, value in insufficient["events"][1].items()
            if key != "event_hash"
        }
    )
    _reseal_after_event_mutation(insufficient)
    with pytest.raises(registry.HipFgmresExternalTrustAnchorRegistryV2Error) as short:
        _compile(insufficient)
    assert short.value.code == (
        "hip_fgmres_external_trust_registry_v2_schema_validation_failed"
    )

    duplicate = deepcopy(manifest)
    duplicate["events"][1]["approvals"][1] = deepcopy(
        duplicate["events"][1]["approvals"][0]
    )
    duplicate["events"][1]["event_hash"] = canonical_hash(
        {
            key: value
            for key, value in duplicate["events"][1].items()
            if key != "event_hash"
        }
    )
    _reseal_after_event_mutation(duplicate)
    with pytest.raises(
        registry.HipFgmresExternalTrustAnchorRegistryV2Error
    ) as repeated:
        _compile(duplicate)
    assert repeated.value.code == (
        "hip_fgmres_external_trust_registry_v2_approval_authority_invalid"
    )

    wrong_key = deepcopy(manifest)
    wrong_key["events"][1]["approvals"][0]["reviewer_key_id"] = wrong_key[
        "reviewer_authorities"
    ][1]["key_id"]
    wrong_key["events"][1]["event_hash"] = canonical_hash(
        {
            key: value
            for key, value in wrong_key["events"][1].items()
            if key != "event_hash"
        }
    )
    _reseal_after_event_mutation(wrong_key)
    with pytest.raises(
        registry.HipFgmresExternalTrustAnchorRegistryV2Error
    ) as mismatched:
        _compile(wrong_key)
    assert mismatched.value.code == (
        "hip_fgmres_external_trust_registry_v2_approval_authority_invalid"
    )

    wrong_domain = deepcopy(manifest)
    event = wrong_domain["events"][1]
    message = b"wrong-domain\x00" + registry._review_approval_message_v2(event)
    event["approvals"][0]["signature_base64"] = base64.b64encode(
        context["reviewer_private_keys"][0].sign(message)
    ).decode("ascii")
    event["event_hash"] = canonical_hash(
        {key: value for key, value in event.items() if key != "event_hash"}
    )
    _reseal_after_event_mutation(wrong_domain)
    with pytest.raises(registry.HipFgmresExternalTrustAnchorRegistryV2Error) as domain:
        _compile(wrong_domain)
    assert domain.value.code == (
        "hip_fgmres_external_trust_registry_v2_approval_signature_invalid"
    )


def test_reviewer_approval_order_and_valid_until_boundary_are_rejected() -> None:
    manifest, context = _active_manifest()

    reordered = deepcopy(manifest)
    event = reordered["events"][-1]
    event["approvals"].reverse()
    event["event_hash"] = canonical_hash(
        {key: value for key, value in event.items() if key != "event_hash"}
    )
    _reseal_after_event_mutation(reordered)
    with pytest.raises(registry.HipFgmresExternalTrustAnchorRegistryV2Error) as order:
        _compile(reordered)
    assert order.value.code == (
        "hip_fgmres_external_trust_registry_v2_approval_authority_invalid"
    )

    events = context["events"]
    authority_end = context["reviewer_rows"][0]["valid_until_utc"]
    events.append(
        _approved_event(
            events=events,
            event_type="key_retired",
            occurred_at_utc=authority_end,
            action={
                "key_id": "ed25519:external-runner:v1",
                "retired_at_utc": authority_end,
                "reason": "review authority half-open boundary",
            },
            reviewer_rows=context["reviewer_rows"],
            reviewer_private_keys=context["reviewer_private_keys"],
        )
    )
    with pytest.raises(
        registry.HipFgmresExternalTrustAnchorRegistryV2Error
    ) as inactive:
        _compile(_seal_manifest(events, context["reviewer_rows"]))
    assert inactive.value.code == (
        "hip_fgmres_external_trust_registry_v2_approval_authority_inactive"
    )


def test_atomic_rotation_derives_retired_and_active_keys() -> None:
    manifest, context = _rotated_manifest()
    result = _compile(manifest)
    assert result.registry_epoch == 5
    assert result.active_key_count == 1
    old, new = result.keys
    assert (old.status, new.status) == ("retired", "active")
    assert old.maximum_run_sequence + 1 == new.minimum_run_sequence
    assert old.valid_until_utc == new.valid_from_utc == ROTATE_AT
    assert old.terminal_event_hash == manifest["events"][4]["event_hash"]
    assert new.activation_event_hash == manifest["events"][4]["event_hash"]
    assert new.activated_at_utc == ROTATE_AT
    assert new.enrollment_receipt_hash == context["successor_receipt"].receipt_hash


def test_rotation_time_overlap_and_reactivation_fail_closed() -> None:
    active, context = _active_manifest()
    events = context["events"]
    predecessor = HipFgmresExternalKeyEnrollmentPredecessorKeyV1(
        key_id="ed25519:external-runner:v1",
        key_epoch=1,
        public_key_sha256=sha256_prefixed(_public_bytes(context["runner_private_key"])),
        maximum_run_sequence=10,
    )
    overlapping = _enrollment_receipt(
        events=events,
        reviewer_rows=context["reviewer_rows"],
        runner_private_key=Ed25519PrivateKey.generate(),
        runner_id="external-runner",
        key_epoch=2,
        minimum_run_sequence=11,
        maximum_run_sequence=20,
        valid_from_utc="2026-07-15T00:09:00Z",
        valid_until_utc=KEY_2_END,
        predecessor_key=predecessor,
    )
    events.append(
        _approved_event(
            events=events,
            event_type="key_enrolled",
            occurred_at_utc=ENROLL_2_AT,
            action={"enrollment_receipt": overlapping.to_dict()},
            reviewer_rows=context["reviewer_rows"],
            reviewer_private_keys=context["reviewer_private_keys"],
        )
    )
    with pytest.raises(registry.HipFgmresExternalTrustAnchorRegistryV2Error) as overlap:
        _compile(_seal_manifest(events, context["reviewer_rows"]))
    assert overlap.value.code == (
        "hip_fgmres_external_trust_registry_v2_key_range_overlap"
    )

    rotated, rotated_context = _rotated_manifest()
    events = rotated_context["events"]
    events.append(
        _approved_event(
            events=events,
            event_type="key_activated",
            occurred_at_utc="2026-07-15T00:12:00Z",
            action={
                "key_id": "ed25519:external-runner:v1",
                "activated_at_utc": "2026-07-15T00:12:00Z",
            },
            reviewer_rows=rotated_context["reviewer_rows"],
            reviewer_private_keys=rotated_context["reviewer_private_keys"],
        )
    )
    with pytest.raises(
        registry.HipFgmresExternalTrustAnchorRegistryV2Error
    ) as reactivated:
        _compile(_seal_manifest(events, rotated_context["reviewer_rows"]))
    assert reactivated.value.code == (
        "hip_fgmres_external_trust_registry_v2_activation_invalid"
    )


@pytest.mark.parametrize("effect", ["prospective", "retroactive"])
def test_revocation_effect_is_derived_and_second_revocation_rejected(
    effect: str,
) -> None:
    manifest, context = _active_manifest()
    events = context["events"]
    events.append(
        _approved_event(
            events=events,
            event_type="key_revoked",
            occurred_at_utc=REVOKE_AT,
            action={
                "key_id": "ed25519:external-runner:v1",
                "revoked_at_utc": REVOKE_AT,
                "revocation_effect": effect,
                "reason": "reviewed lifecycle revocation",
            },
            reviewer_rows=context["reviewer_rows"],
            reviewer_private_keys=context["reviewer_private_keys"],
        )
    )
    result = _compile(_seal_manifest(events, context["reviewer_rows"]))
    assert result.active_key_count == 0
    assert result.keys[0].status == "revoked"
    assert result.keys[0].revocation_effect == effect

    events.append(
        _approved_event(
            events=events,
            event_type="key_revoked",
            occurred_at_utc="2026-07-15T00:12:00Z",
            action={
                "key_id": "ed25519:external-runner:v1",
                "revoked_at_utc": "2026-07-15T00:12:00Z",
                "revocation_effect": "retroactive",
                "reason": "duplicate revocation must fail",
            },
            reviewer_rows=context["reviewer_rows"],
            reviewer_private_keys=context["reviewer_private_keys"],
        )
    )
    with pytest.raises(
        registry.HipFgmresExternalTrustAnchorRegistryV2Error
    ) as duplicate:
        _compile(_seal_manifest(events, context["reviewer_rows"]))
    assert duplicate.value.code == (
        "hip_fgmres_external_trust_registry_v2_revocation_invalid"
    )


def test_global_public_key_reuse_across_runners_is_rejected() -> None:
    manifest, context = _active_manifest()
    events = context["events"]
    reused = _enrollment_receipt(
        events=events,
        reviewer_rows=context["reviewer_rows"],
        runner_private_key=context["runner_private_key"],
        runner_id="other-runner",
        key_epoch=1,
        minimum_run_sequence=1,
        maximum_run_sequence=10,
        valid_from_utc=ACTIVATE_1_AT,
        valid_until_utc=ROTATE_AT,
        predecessor_key=None,
    )
    events.append(
        _approved_event(
            events=events,
            event_type="key_enrolled",
            occurred_at_utc=ENROLL_2_AT,
            action={"enrollment_receipt": reused.to_dict()},
            reviewer_rows=context["reviewer_rows"],
            reviewer_private_keys=context["reviewer_private_keys"],
        )
    )
    with pytest.raises(registry.HipFgmresExternalTrustAnchorRegistryV2Error) as caught:
        _compile(_seal_manifest(events, context["reviewer_rows"]))
    assert caught.value.code == (
        "hip_fgmres_external_trust_registry_v2_enrollment_binding_invalid"
    )


def test_reviewer_public_key_cannot_be_reused_as_runner_key() -> None:
    reviewer_rows, reviewer_private_keys = _review_material()
    events = [_init_event()]
    receipt = _enrollment_receipt(
        events=events,
        reviewer_rows=reviewer_rows,
        runner_private_key=reviewer_private_keys[0],
        runner_id="cross-role-runner",
        key_epoch=1,
        minimum_run_sequence=1,
        maximum_run_sequence=10,
        valid_from_utc=ACTIVATE_1_AT,
        valid_until_utc=ROTATE_AT,
        predecessor_key=None,
    )
    events.append(
        _approved_event(
            events=events,
            event_type="key_enrolled",
            occurred_at_utc=ENROLL_1_AT,
            action={"enrollment_receipt": receipt.to_dict()},
            reviewer_rows=reviewer_rows,
            reviewer_private_keys=reviewer_private_keys,
        )
    )
    with pytest.raises(registry.HipFgmresExternalTrustAnchorRegistryV2Error) as caught:
        _compile(_seal_manifest(events, reviewer_rows))
    assert caught.value.code == (
        "hip_fgmres_external_trust_registry_v2_enrollment_binding_invalid"
    )


def test_code_anchored_package_resource_tamper_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = RESOURCE.read_bytes()
    monkeypatch.setattr(registry, "_read_fixed_resource_v2", lambda: original + b" ")
    with pytest.raises(registry.HipFgmresExternalTrustAnchorRegistryV2Error) as caught:
        registry.load_hip_fgmres_external_trust_anchor_registry_v2()
    assert caught.value.code == (
        "hip_fgmres_external_trust_registry_v2_resource_hash_mismatch"
    )


def test_private_result_validator_rejects_hostile_container_types() -> None:
    result = registry.load_hip_fgmres_external_trust_anchor_registry_v2()
    hostile_results = (
        replace(result, keys=[]),
        replace(result, registry_hash=None),
    )
    for hostile in hostile_results:
        with pytest.raises(
            registry.HipFgmresExternalTrustAnchorRegistryV2Error
        ) as caught:
            registry._validate_hip_fgmres_external_trust_anchor_registry_snapshot_result_v2(
                hostile
            )
        assert caught.value.code == (
            "hip_fgmres_external_trust_registry_v2_result_invalid"
        )

    alias_claims = replace(
        result.claims,
        package_owned_registry_loaded=1,
        commercial_ready=0,
    )
    alias_draft = replace(
        result,
        claims=alias_claims,
        receipt_hash=registry._ZERO_HASH,
    )
    alias_result = replace(
        alias_draft,
        receipt_hash=canonical_hash(
            registry._result_payload_v2(alias_draft, include_hash=False)
        ),
    )
    with pytest.raises(registry.HipFgmresExternalTrustAnchorRegistryV2Error) as alias:
        registry._validate_hip_fgmres_external_trust_anchor_registry_snapshot_result_v2(
            alias_result
        )
    assert alias.value.code == ("hip_fgmres_external_trust_registry_v2_result_invalid")
    assert list(result.claims.to_dict()).count("reviewer_human_identity_verified") == 1
