from __future__ import annotations

import base64
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess

from jsonschema import Draft202012Validator

from tests.license_decision_test_support import sha256_bytes
from verify_rights_holder_revocation_epoch import (
    canonical_revocation_epoch_bytes,
    inspect_rights_holder_revocation_epoch,
)


HEAD = "a" * 40
DECISION_ID = "RH-LICENSE-DECISION-001"
DECISION_SIGNER_ID = "rights-holder-primary"


def _signed_epoch(
    tmp_path: Path,
    *,
    revoked_decisions: list[str] | None = None,
    revoked_signers: list[str] | None = None,
    epoch_number: int = 7,
) -> tuple[Path, Path, dict]:
    private_key = tmp_path / "revocation-private.pem"
    public_key = tmp_path / "revocation-public.pem"
    subprocess.run(
        [
            "openssl",
            "genpkey",
            "-algorithm",
            "RSA",
            "-pkeyopt",
            "rsa_keygen_bits:2048",
            "-out",
            str(private_key),
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "openssl",
            "pkey",
            "-in",
            str(private_key),
            "-pubout",
            "-out",
            str(public_key),
        ],
        check=True,
        capture_output=True,
    )
    payload = {
        "schema_version": "rights-holder-revocation-epoch.v1",
        "repository_id": "betelgeuze-kang/structural-analysis",
        "epoch": epoch_number,
        "issued_at_utc": datetime.now(timezone.utc).isoformat(),
        "default_branch": "main",
        "default_branch_commit_sha": HEAD,
        "signer_id": "rights-holder-revocation-root",
        "previous_epoch_sha256": "",
        "revoked_signer_ids": revoked_signers or [],
        "revoked_decision_ids": revoked_decisions or [],
        "claim_boundary": (
            "This signed test epoch carries revocations only and grants no software-use, "
            "commercial, redistribution, third-party, or release authority whatsoever."
        ),
    }
    signed_bytes = canonical_revocation_epoch_bytes(payload)
    completed = subprocess.run(
        ["openssl", "dgst", "-sha256", "-sign", str(private_key)],
        input=signed_bytes,
        check=True,
        capture_output=True,
    )
    payload["signature"] = {
        "algorithm": "rsa-sha256",
        "signed_payload_sha256": sha256_bytes(signed_bytes),
        "value_base64": base64.b64encode(completed.stdout).decode("ascii"),
    }
    epoch = tmp_path / "revocation-epoch.json"
    epoch.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    epoch.chmod(0o600)
    public_key.chmod(0o600)
    return epoch, public_key, payload


def _inspect(epoch: Path, public_key: Path, **overrides: object) -> dict:
    arguments = {
        "epoch_path": epoch.resolve(),
        "public_key_path": public_key.resolve(),
        "expected_epoch_sha256": sha256_bytes(epoch.read_bytes()),
        "expected_public_key_sha256": sha256_bytes(public_key.read_bytes()),
        "expected_minimum_epoch": 7,
        "expected_default_branch": "main",
        "expected_default_branch_head": HEAD,
        "decision_id": DECISION_ID,
        "decision_signer_id": DECISION_SIGNER_ID,
    }
    arguments.update(overrides)
    return inspect_rights_holder_revocation_epoch(**arguments)


def test_signed_latest_revocation_epoch_passes_without_a_revocation(
    tmp_path: Path,
) -> None:
    epoch, public_key, epoch_payload = _signed_epoch(tmp_path)
    schema = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "canonical"
            / "rights-holder-revocation-epoch.v1.schema.json"
        ).read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(epoch_payload)

    result = _inspect(epoch, public_key)

    assert result["contract_pass"] is True
    assert result["signature_verified"] is True
    assert result["branch_binding_pass"] is True
    assert result["epoch_number_pass"] is True
    assert result["decision_revoked"] is False
    assert result["signer_revoked"] is False
    assert result["release_authority"] is False


def test_latest_epoch_revocation_blocks_an_old_source_decision(tmp_path: Path) -> None:
    epoch, public_key, _payload = _signed_epoch(
        tmp_path,
        revoked_decisions=[DECISION_ID],
    )

    result = _inspect(epoch, public_key)

    assert result["contract_pass"] is False
    assert result["signature_verified"] is True
    assert result["decision_revoked"] is True
    assert "rights_holder_decision_revoked_by_latest_epoch" in result["blockers"]
    assert result["release_authority"] is False


def test_revocation_epoch_rejects_hash_branch_and_epoch_rollback(
    tmp_path: Path,
) -> None:
    epoch, public_key, _payload = _signed_epoch(tmp_path, epoch_number=6)

    result = _inspect(
        epoch,
        public_key,
        expected_epoch_sha256="sha256:" + "0" * 64,
        expected_default_branch_head="b" * 40,
    )

    assert result["contract_pass"] is False
    assert "revocation_epoch_hash_mismatch" in result["blockers"]
    assert "revocation_epoch_default_branch_binding_mismatch" in result["blockers"]
    assert "revocation_epoch_rollback_detected" in result["blockers"]
    assert result["release_authority"] is False


def test_revocation_epoch_malformed_revocation_rows_fail_closed(
    tmp_path: Path,
) -> None:
    epoch, public_key, _payload = _signed_epoch(
        tmp_path,
        revoked_signers=[["not-a-string"]],  # type: ignore[list-item]
        revoked_decisions=[{"not": "an-id"}],  # type: ignore[list-item]
    )

    result = _inspect(epoch, public_key)

    assert result["contract_pass"] is False
    assert "revocation_epoch_schema_invalid" in result["blockers"]
    assert result["decision_revoked"] is False
    assert result["signer_revoked"] is False
    assert result["release_authority"] is False
