from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/build_g1_mgt_hardware_envelope.py"
SPEC = importlib.util.spec_from_file_location(
    "build_g1_mgt_hardware_envelope", SCRIPT
)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def test_committed_local_hardware_envelope_is_current() -> None:
    payload = module.validate(
        json.loads((ROOT / module.DEFAULT_OUT).read_text(encoding="utf-8")),
        root=ROOT,
        require_current_sources=True,
    )
    assert payload["claims"]["actual_production_mgt_hardware"] is True
    assert payload["claims"]["actual_gfx1030_hardware"] is True
    assert payload["claims"]["actual_gfx1100_hardware"] is False
    assert payload["claims"]["signed_receipt"] is False
    assert payload["claims"]["cross_device_pair"] is False
    assert payload["claims"]["g1_closure"] is False
    assert payload["evidence_payload"]["terminal"]["equation_count"] == 70_560
    assert payload["evidence_payload"]["material"][
        "integration_point_count"
    ] == 5_572


def test_envelope_hash_and_evidence_replay_fail_closed() -> None:
    payload = json.loads((ROOT / module.DEFAULT_OUT).read_text(encoding="utf-8"))
    tampered = deepcopy(payload)
    tampered["evidence_payload"]["performance"]["h2d_bytes"] += 1
    with pytest.raises(ValueError, match="receipt_hash_mismatch"):
        module.validate(tampered, root=ROOT, require_current_sources=True)


def test_ephemeral_ed25519_signature_round_trip() -> None:
    cryptography = pytest.importorskip("cryptography")
    del cryptography
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey,
    )

    unsigned = module.build(
        root=ROOT,
        organization_id="self-test-org",
        runner_id="self-test-runner",
        execution_location="ephemeral-test",
        independent_from_local_gfx1030=False,
    )
    private_key = Ed25519PrivateKey.generate()
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    signature = private_key.sign(module.evidence_bytes(unsigned))
    signed = module.attach_signature(
        unsigned,
        signature_bytes=signature,
        public_key_pem=public_pem,
        signer_id="ephemeral-self-test",
        root=ROOT,
    )
    assert signed["signature"]["state"] == "verified"
    assert signed["claims"]["signed_receipt"] is True
    assert signed["claims"]["independent_gfx1100_hardware"] is False
