from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/build_g1_mgt_production_promotion_gate_v2.py"
SPEC = importlib.util.spec_from_file_location("g1_promotion_gate_v2", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def _identity(architecture: str, suffix: str, **overrides):
    value = {
        "architecture": architecture,
        "signer_id": f"signer-{suffix}",
        "public_key_sha256": "sha256:" + suffix * 64,
        "organization_id": f"org-{suffix}",
        "runner_id": f"runner-{suffix}",
        "execution_location": f"site-{suffix}",
        "source_commit_sha": "a" * 40,
        "wheel_sha256": "sha256:" + "b" * 64,
        "revoked": False,
    }
    value.update(overrides)
    return value


def _policy(*identities, expires_at="2027-01-01T00:00:00Z"):
    return module.create_hashed_receipt(
        schema_version=module.TRUST_POLICY_VERSION,
        issued_at="2026-01-01T00:00:00Z",
        expires_at=expires_at,
        identities=list(identities),
    )


def _envelope(identity: dict):
    return {
        "signature": {
            "state": "verified",
            "signer_id": identity["signer_id"],
            "public_key_sha256": identity["public_key_sha256"],
        },
        "claims": {"signed_receipt": True},
        "evidence_payload": {
            "runner_attestation": {
                key: identity[key]
                for key in ("organization_id", "runner_id", "execution_location")
            },
            "hardware": {
                "gcn_arch_name": identity["architecture"],
                "wheel_sha256": identity["wheel_sha256"],
            },
            "source": {"repository_commit_sha": identity["source_commit_sha"]},
        },
    }


def test_missing_optional_inputs_remain_partial() -> None:
    payload = module.build(root=ROOT, generated_at="2026-08-09T00:00:00Z")
    module.validate(payload, root=ROOT)
    assert payload["status"] == "partial"
    assert payload["claims"]["production_worker_ready"] is False
    assert payload["claims"]["self_declared_identity_promoted"] is False
    assert payload["claims"]["gfx1100_workflow_executed_by_this_builder"] is False
    assert all(value is False for value in payload["promotion_requirements"].values())
    assert "nonlinear_material_family_breadth" in payload["blockers_remaining"]


def test_detached_self_signature_sidecars_are_not_discovered() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "detached_self_signature" not in source
    assert ".glob(" not in source
    assert ".rglob(" not in source


def test_current_validation_replays_default_upstream_chain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = module.build(root=ROOT, generated_at="2026-08-09T00:00:00Z")
    original = module.build

    def drifted_build(**kwargs):
        candidate = original(**kwargs)
        candidate["sources"]["performance_receipt_hash"] = "sha256:" + "f" * 64
        candidate["receipt_hash"] = module._hash(candidate)
        return candidate

    monkeypatch.setattr(module, "build", drifted_build)
    with pytest.raises(ValueError, match="current_replay_mismatch"):
        module.validate(payload, root=ROOT, current=True)


def test_secure_json_rejects_symlink_duplicate_keys_and_nonfinite(
    tmp_path: Path,
) -> None:
    target = tmp_path / "input.json"
    target.write_text('{"a":1,"a":2}', encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate_json_key"):
        module.secure_read_json(target, allowed_root=tmp_path)
    target.write_text('{"a":NaN}', encoding="utf-8")
    with pytest.raises(ValueError, match="nonfinite_json_constant"):
        module.secure_read_json(target, allowed_root=tmp_path)
    target.write_text('{"a":1}', encoding="utf-8")
    link = tmp_path / "link.json"
    link.symlink_to(target)
    with pytest.raises(ValueError, match="symlink_input_forbidden"):
        module.secure_read_json(link, allowed_root=tmp_path)


def test_trust_policy_requires_external_pin_and_valid_epoch() -> None:
    policy = _policy(_identity("gfx1030", "1"), _identity("gfx1100", "2"))
    now = datetime(2026, 8, 9, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="not_externally_pinned"):
        module.validate_trust_policy(policy, expected_hash=None, now=now)
    expired = _policy(
        _identity("gfx1030", "1"),
        _identity("gfx1100", "2"),
        expires_at="2026-02-01T00:00:00Z",
    )
    with pytest.raises(ValueError, match="expired_or_not_yet_valid"):
        module.validate_trust_policy(
            expired, expected_hash=expired["receipt_hash"], now=now
        )


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ("unknown", "unknown_signer_key"),
        ("revoked", "revoked_signer_key"),
        ("self_declared", "self_declared_identity_mismatch"),
        ("collision", "identity_collision"),
        ("source", "source_epoch_drift"),
        ("wheel", "wheel_drift"),
    ],
)
def test_identity_pair_rejects_untrusted_or_drifted_metadata(
    mutation: str, reason: str
) -> None:
    left = _identity("gfx1030", "1")
    right = _identity("gfx1100", "2")
    policy = _policy(left, right)
    envelopes = [_envelope(left), _envelope(right)]
    if mutation == "unknown":
        envelopes[1]["signature"]["public_key_sha256"] = "sha256:" + "3" * 64
    elif mutation == "revoked":
        policy = _policy(left, {**right, "revoked": True})
    elif mutation == "self_declared":
        envelopes[1]["evidence_payload"]["runner_attestation"]["runner_id"] = (
            "untrusted-self-declared-runner"
        )
    elif mutation == "collision":
        policy = _policy(left, {**right, "organization_id": left["organization_id"]})
        envelopes[1] = _envelope(policy["identities"][1])
    elif mutation == "source":
        changed = {**right, "source_commit_sha": "c" * 40}
        policy = _policy(left, changed)
        envelopes[1] = _envelope(changed)
    elif mutation == "wheel":
        changed = {**right, "wheel_sha256": "sha256:" + "d" * 64}
        policy = _policy(left, changed)
        envelopes[1] = _envelope(changed)
    with pytest.raises(ValueError, match=reason):
        module.validate_trusted_identity_pair(envelopes, policy)


def test_fallback_zero_receipt_rejects_nonzero_and_source_drift() -> None:
    workers = [
        {
            "source": {
                "repository_commit_sha": "a" * 40,
                "wheel_sha256": "sha256:" + "b" * 64,
            }
        },
        {
            "source": {
                "repository_commit_sha": "a" * 40,
                "wheel_sha256": "sha256:" + "b" * 64,
            }
        },
    ]
    receipt = module.create_hashed_receipt(
        schema_version=module.FALLBACK_VERSION,
        source_commit_sha="a" * 40,
        wheel_sha256="sha256:" + "b" * 64,
        workload_hash="sha256:" + "c" * 64,
        checkpoint_sha256="sha256:" + "d" * 64,
        architectures={"gfx1030": 0, "gfx1100": 0},
    )
    module.validate_fallback_zero_receipt(receipt, workers)
    nonzero = deepcopy(receipt)
    nonzero["architectures"]["gfx1100"] = 1
    nonzero["receipt_hash"] = module._hash(nonzero)
    with pytest.raises(ValueError, match="fallback_nonzero"):
        module.validate_fallback_zero_receipt(nonzero, workers)


@pytest.mark.parametrize(
    ("field", "reason"),
    [
        ("source_commit_sha", "performance_source_epoch_drift"),
        ("wheel_sha256", "performance_wheel_drift"),
        ("workload_hash", "performance_workload_drift"),
        ("checkpoint_sha256", "performance_checkpoint_drift"),
        ("terminal_parity_digest", "performance_terminal_parity_drift"),
    ],
)
def test_performance_receipt_must_bind_worker_fallback_checkpoint_chain(
    field: str, reason: str
) -> None:
    workers = [
        {
            "source": {
                "repository_commit_sha": "a" * 40,
                "wheel_sha256": "sha256:" + "b" * 64,
            },
            "terminal_parity": {"parity_digest": "sha256:" + "e" * 64},
        }
        for _ in range(2)
    ]
    fallback = {
        "workload_hash": "sha256:" + "c" * 64,
        "checkpoint_sha256": "sha256:" + "d" * 64,
    }
    checkpoint = {"checkpoint": {"file_sha256": "sha256:" + "d" * 64}}
    performance = {
        "claims": {"cross_device_production_performance_sweep": True},
        "identity": {
            "source_commit_sha": "a" * 40,
            "wheel_sha256": "sha256:" + "b" * 64,
            "workload_hash": "sha256:" + "c" * 64,
            "checkpoint_sha256": "sha256:" + "d" * 64,
            "terminal_parity_digest": "sha256:" + "e" * 64,
        },
    }
    drifted = deepcopy(performance)
    drifted["identity"][field] = (
        "f" * 40 if field == "source_commit_sha" else "sha256:" + "f" * 64
    )
    with pytest.raises(ValueError, match=reason):
        module.validate_cross_receipt_bindings(
            performance=drifted,
            fallback=fallback,
            checkpoint=checkpoint,
            workers=workers,
        )
