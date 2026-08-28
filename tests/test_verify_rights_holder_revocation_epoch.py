from __future__ import annotations

import base64
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess

from jsonschema import Draft202012Validator

from tests.license_decision_test_support import sha256_bytes
from verify_rights_holder_revocation_epoch import (
    _license_closure_pass,
    canonical_revocation_epoch_bytes,
    inspect_rights_holder_revocation_epoch,
)


DECISION_ID = "RH-LICENSE-DECISION-001"
DECISION_SIGNER_ID = "rights-holder-primary"
DECISION_SHA256 = "sha256:" + "d" * 64


def test_revocation_aggregate_requires_final_closure_release_authority() -> None:
    closure = {
        "contract_pass": True,
        "rights_holder_decision": {
            "contract_pass": True,
            "signature_verified": True,
            "decision_id_binding_pass": True,
            "subject_binding_pass": True,
            "source_worktree_binding_pass": True,
            "signer_policy_authorized_pass": True,
        },
        "authority": {
            "first_party_commercial_use_approved": True,
            "first_party_redistribution_approved": True,
            "third_party_material_redistribution_approved": True,
            "overall_release_authority": False,
        },
    }

    assert _license_closure_pass(closure, require_release_authority=False) is True
    assert _license_closure_pass(closure, require_release_authority=True) is False


def _signed_epoch(
    tmp_path: Path,
    *,
    revoked_decisions: list[str] | None = None,
    revoked_signers: list[str] | None = None,
    epoch_number: int = 7,
) -> tuple[Path, Path, dict, Path]:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "tests@example.invalid"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Tests"], cwd=repo, check=True)
    (repo / "source.txt").write_text("source\n", encoding="utf-8")
    subprocess.run(["git", "add", "source.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "source"], cwd=repo, check=True)
    source_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()
    source_tree = subprocess.run(
        ["git", "rev-parse", "HEAD^{tree}"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()
    (repo / "current.txt").write_text("current\n", encoding="utf-8")
    subprocess.run(["git", "add", "current.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "current"], cwd=repo, check=True)
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
        "source_commit_sha": source_commit,
        "source_tree_sha": source_tree,
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
    return epoch, public_key, payload, repo


def _inspect(epoch: Path, public_key: Path, repo: Path, **overrides: object) -> dict:
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()
    arguments = {
        "epoch_path": epoch.resolve(),
        "public_key_path": public_key.resolve(),
        "expected_epoch_sha256": sha256_bytes(epoch.read_bytes()),
        "expected_public_key_sha256": sha256_bytes(public_key.read_bytes()),
        "expected_minimum_epoch": 7,
        "expected_default_branch": "main",
        "expected_default_branch_head": head,
        "repo_root": repo.resolve(),
        "decision_id": DECISION_ID,
        "decision_signer_id": DECISION_SIGNER_ID,
        "decision_sha256": DECISION_SHA256,
        "license_closure_sha256": "sha256:" + "c" * 64,
        "license_closure_contract_pass": True,
    }
    arguments.update(overrides)
    return inspect_rights_holder_revocation_epoch(**arguments)


def _rewrite_signed_epoch(epoch: Path, payload: dict, private_key: Path) -> None:
    payload.pop("signature", None)
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
    epoch.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def test_signed_latest_revocation_epoch_passes_without_a_revocation(
    tmp_path: Path,
) -> None:
    epoch, public_key, epoch_payload, repo = _signed_epoch(tmp_path)
    schema = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "canonical"
            / "rights-holder-revocation-epoch.v1.schema.json"
        ).read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(epoch_payload)

    result = _inspect(epoch, public_key, repo)

    assert result["contract_pass"] is True
    assert result["signature_verified"] is True
    assert result["branch_binding_pass"] is True
    assert result["epoch_number_pass"] is True
    assert result["decision_revoked"] is False
    assert result["signer_revoked"] is False
    assert result["release_authority"] is False


def test_latest_epoch_revocation_blocks_an_old_source_decision(tmp_path: Path) -> None:
    epoch, public_key, _payload, repo = _signed_epoch(
        tmp_path,
        revoked_decisions=[DECISION_ID],
    )

    result = _inspect(epoch, public_key, repo)

    assert result["contract_pass"] is False
    assert result["signature_verified"] is True
    assert result["decision_revoked"] is True
    assert "rights_holder_decision_revoked_by_latest_epoch" in result["blockers"]
    assert result["release_authority"] is False


def test_revocation_epoch_rejects_hash_branch_and_epoch_rollback(
    tmp_path: Path,
) -> None:
    epoch, public_key, _payload, repo = _signed_epoch(tmp_path, epoch_number=6)

    result = _inspect(
        epoch,
        public_key,
        repo,
        expected_epoch_sha256="sha256:" + "0" * 64,
        expected_default_branch_head="b" * 40,
    )

    assert result["contract_pass"] is False
    assert "revocation_epoch_hash_mismatch" in result["blockers"]
    assert "revocation_epoch_default_branch_binding_mismatch" in result["blockers"]
    assert "revocation_epoch_rollback_detected" in result["blockers"]
    assert result["release_authority"] is False


def test_revocation_epoch_rejects_impossible_current_head_self_reference(
    tmp_path: Path,
) -> None:
    epoch, public_key, payload, repo = _signed_epoch(tmp_path)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()
    head_tree = subprocess.run(
        ["git", "rev-parse", "HEAD^{tree}"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    payload["source_commit_sha"] = head
    payload["source_tree_sha"] = head_tree
    _rewrite_signed_epoch(epoch, payload, tmp_path / "revocation-private.pem")

    result = _inspect(
        epoch,
        public_key,
        repo,
        expected_epoch_sha256=sha256_bytes(epoch.read_bytes()),
    )

    assert result["signature_verified"] is True
    assert result["branch_binding_pass"] is False
    assert result["contract_pass"] is False


def test_revocation_epoch_malformed_revocation_rows_fail_closed(
    tmp_path: Path,
) -> None:
    epoch, public_key, _payload, repo = _signed_epoch(
        tmp_path,
        revoked_signers=[["not-a-string"]],  # type: ignore[list-item]
        revoked_decisions=[{"not": "an-id"}],  # type: ignore[list-item]
    )

    result = _inspect(epoch, public_key, repo)

    assert result["contract_pass"] is False
    assert "revocation_epoch_schema_invalid" in result["blockers"]
    assert result["decision_revoked"] is False
    assert result["signer_revoked"] is False
    assert result["release_authority"] is False


def test_revocation_cli_binds_one_immutable_license_closure_snapshot(tmp_path: Path) -> None:
    epoch, public_key, _payload, repo = _signed_epoch(tmp_path)
    closure = tmp_path / "license-closure.json"
    closure.write_text(
        json.dumps(
            {
                "contract_pass": True,
                "rights_holder_decision": {
                    "contract_pass": True,
                    "signature_verified": True,
                    "decision_id_binding_pass": True,
                    "subject_binding_pass": True,
                    "source_worktree_binding_pass": True,
                    "signer_policy_authorized_pass": True,
                    "decision_id": DECISION_ID,
                    "signer_id": DECISION_SIGNER_ID,
                    "decision_sha256": DECISION_SHA256,
                },
            }
        ),
        encoding="utf-8",
    )
    closure.chmod(0o600)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()
    out = tmp_path / "inspection.json"
    script = Path(__file__).resolve().parents[1] / "scripts" / "verify_rights_holder_revocation_epoch.py"

    completed = subprocess.run(
        [
            "/usr/bin/python3",
            "-I",
            "-B",
            str(script),
            "--epoch",
            str(epoch.resolve()),
            "--public-key",
            str(public_key.resolve()),
            "--expected-epoch-sha256",
            sha256_bytes(epoch.read_bytes()),
            "--expected-public-key-sha256",
            sha256_bytes(public_key.read_bytes()),
            "--expected-minimum-epoch",
            "7",
            "--expected-default-branch",
            "main",
            "--expected-default-branch-head",
            head,
            "--repo-root",
            str(repo.resolve()),
            "--license-closure",
            str(closure.resolve()),
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(out.read_text(encoding="utf-8"))
    assert result["contract_pass"] is True
    assert result["decision_sha256"] == DECISION_SHA256
    assert result["license_closure_sha256"] == sha256_bytes(closure.read_bytes())
    assert result["release_authority"] is False
