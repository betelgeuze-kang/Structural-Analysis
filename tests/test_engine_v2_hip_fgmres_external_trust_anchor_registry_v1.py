from __future__ import annotations

import base64
import inspect
import json
from pathlib import Path

from jsonschema import Draft202012Validator
import pytest

from structural_analysis.engine_v2.assembly_backend import (
    fgmres_external_trust_anchor_registry_v1 as registry_module,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_external_trust_anchor_registry_v1 import (
    HipFgmresExternalTrustAnchorRegistryV1Error,
    load_hip_fgmres_external_trust_anchor_registry_v1,
    validate_hip_fgmres_external_trust_anchor_registry_result_v1,
)


ROOT = Path(__file__).resolve().parents[1]
RESOURCE = (
    ROOT
    / "src/structural_analysis/engine_v2/assembly_backend/fixtures"
    / "fgmres_external_trust_anchors_v1/registry.v1.json"
)
SCHEMA = (
    ROOT
    / "src/structural_analysis/schemas"
    / "hip_fgmres_external_trust_anchor_registry_v1.schema.json"
)


def test_package_registry_is_intentionally_empty_and_nonpromoting() -> None:
    result = load_hip_fgmres_external_trust_anchor_registry_v1()
    manifest = result.to_dict()

    assert result.registry_bytes_sha256 == (
        "sha256:f39fc9a2a932b8e92be028ee87d036445cdcb33f244f10af85ee9127290e61c6"
    )
    assert result.registry_hash == (
        "sha256:4154e2e679ce17b986eac4e90735e518ceddda62751625aa6e254742924b1704"
    )
    assert result.keys == ()
    assert result.active_key_count == 0
    assert manifest["claims"]["external_gfx1100_signed_cells"] == 0
    assert not manifest["claims"]["durable_replay_protection"]
    assert not manifest["claims"]["promotion_eligible"]
    assert (
        validate_hip_fgmres_external_trust_anchor_registry_result_v1(result) is result
    )
    assert (
        tuple(
            inspect.signature(
                load_hip_fgmres_external_trust_anchor_registry_v1
            ).parameters
        )
        == ()
    )


def test_registry_resource_matches_strict_schema_and_declared_hash() -> None:
    payload = json.loads(RESOURCE.read_text(encoding="utf-8"))
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    assert not list(Draft202012Validator(schema).iter_errors(payload))


@pytest.mark.parametrize(
    ("raw", "code"),
    [
        (b"\xef\xbb\xbf{}", "hip_fgmres_external_trust_registry_json_bom_forbidden"),
        (b'{"a":1,"a":2}', "hip_fgmres_external_trust_registry_json_duplicate_key"),
        (b'{"a":NaN}', "hip_fgmres_external_trust_registry_json_invalid"),
    ],
)
def test_strict_registry_json_rejects_alternate_inputs(raw: bytes, code: str) -> None:
    with pytest.raises(HipFgmresExternalTrustAnchorRegistryV1Error) as caught:
        registry_module._parse_strict_object(raw, path="/test")
    assert caught.value.code == code


def test_code_anchored_raw_resource_tamper_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = RESOURCE.read_bytes()
    monkeypatch.setattr(
        registry_module, "_read_fixed_resource", lambda: original + b" "
    )
    with pytest.raises(HipFgmresExternalTrustAnchorRegistryV1Error) as caught:
        load_hip_fgmres_external_trust_anchor_registry_v1()
    assert caught.value.code == (
        "hip_fgmres_external_trust_registry_resource_hash_mismatch"
    )


def test_v1_registry_wraps_low_order_key_as_stable_registry_error() -> None:
    low_order = b"\x00" * 32
    anchor = registry_module.HipFgmresExternalTrustAnchorV1(
        key_id="ed25519:external-runner:v1",
        key_epoch=1,
        status="active",
        runner_id="external-runner",
        public_key_base64=base64.b64encode(low_order).decode("ascii"),
        public_key_sha256="sha256:" + "0" * 64,
        allowed_architecture_base="gfx1100",
        allowed_suite_id="synthetic",
        allowed_fixture_registry_bytes_sha256="sha256:" + "0" * 64,
        allowed_fixture_registry_hash="sha256:" + "0" * 64,
        minimum_run_sequence=1,
        maximum_run_sequence=None,
        valid_from_utc="2026-01-01T00:00:00Z",
        valid_until_utc=None,
        revoked_at_utc=None,
        revocation_reason=None,
    )
    with pytest.raises(HipFgmresExternalTrustAnchorRegistryV1Error) as caught:
        _ = anchor.public_key_bytes
    assert caught.value.code == "hip_fgmres_external_trust_registry_key_invalid"
