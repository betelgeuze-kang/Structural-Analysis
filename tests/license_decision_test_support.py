from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Callable


SCRIPT_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from verify_rights_holder_license_decision import (  # noqa: E402
    REPLAY_POLICY,
    REQUIRED_FIRST_PARTY_COVERAGE,
    REPOSITORY_ID,
    canonical_decision_bytes,
    sha256_bytes,
)


PRODUCT_SCOPE = [
    "review-assist",
    "specified-structure-families",
    "specified-workflows",
    "engine-and-reviewer-evidence-package",
]
DECISION_ID = "RH-LICENSE-DECISION-001"
RIGHTS_HOLDER_ID = "product-owner"
SIGNER_ID = "rights-holder-primary"
_TEST_NOW = datetime.now(timezone.utc)
ISSUED_AT_UTC = (_TEST_NOW - timedelta(days=1)).isoformat()
EXPIRES_AT_UTC = (_TEST_NOW + timedelta(days=30)).isoformat()
LICENSE_POLICY_VERSION = "test-policy-v1"
COVERED_FIRST_PARTY_PATHS = list(REQUIRED_FIRST_PARTY_COVERAGE)


def _run(
    *args: str, cwd: Path | None = None, input_bytes: bytes | None = None
) -> bytes:
    completed = subprocess.run(
        list(args),
        cwd=cwd,
        input=input_bytes,
        capture_output=True,
        check=True,
    )
    return completed.stdout


def write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def sign_decision(
    decision: dict[str, Any],
    *,
    private_key: Path,
) -> dict[str, Any]:
    decision.pop("signature", None)
    signed_bytes = canonical_decision_bytes(decision)
    signature = _run(
        "openssl",
        "dgst",
        "-sha256",
        "-sign",
        str(private_key),
        input_bytes=signed_bytes,
    )
    decision["signature"] = {
        "algorithm": "rsa-sha256",
        "signed_payload_sha256": sha256_bytes(signed_bytes),
        "value_base64": base64.b64encode(signature).decode("ascii"),
    }
    return decision


def build_signed_decision_repository(
    repo_root: Path,
    *,
    approve_signer: bool = True,
    revoke_signer: bool = False,
    revoke_decision: bool = False,
    rsa_bits: int = 2048,
    mutate_signer: Callable[[dict[str, Any]], None] | None = None,
    mutate_decision: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    repo_root.mkdir(parents=True, exist_ok=True)
    license_path = repo_root / "LICENSE"
    license_path.write_text(
        "Copyright (c) repository rights holder. All rights reserved. No license granted.\n",
        encoding="utf-8",
    )

    private_key = repo_root.parent / f"{repo_root.name}-test-private-key.pem"
    public_key = repo_root / "canonical" / "rights-holder-public.pem"
    public_key.parent.mkdir(parents=True, exist_ok=True)
    license_policy = repo_root / "canonical" / "license-policies" / "test-policy.txt"
    license_policy.parent.mkdir(parents=True, exist_ok=True)
    license_policy.write_text(
        "Test-only rights-holder policy artifact. It identifies bounded first-party "
        "commercial-use and redistribution terms solely for cryptographic verifier tests.\n",
        encoding="utf-8",
    )
    _run(
        "openssl",
        "genpkey",
        "-algorithm",
        "RSA",
        "-pkeyopt",
        f"rsa_keygen_bits:{rsa_bits}",
        "-out",
        str(private_key),
    )
    _run(
        "openssl",
        "pkey",
        "-in",
        str(private_key),
        "-pubout",
        "-out",
        str(public_key),
    )

    signer = {
        "signer_id": SIGNER_ID,
        "rights_holder_id": RIGHTS_HOLDER_ID,
        "algorithm": "rsa-sha256",
        "public_key_path": "canonical/rights-holder-public.pem",
        "public_key_sha256": sha256_bytes(public_key.read_bytes()),
        "allowed_repository_license_sha256": sha256_bytes(license_path.read_bytes()),
        "allowed_license_ids": ["LIC-001"],
        "allowed_license_policy": {
            "document_path": "canonical/license-policies/test-policy.txt",
            "document_sha256": sha256_bytes(license_policy.read_bytes()),
            "version": LICENSE_POLICY_VERSION,
            "covered_first_party_paths": list(COVERED_FIRST_PARTY_PATHS),
        },
        "allowed_tiers": ["limited-commercial"],
        "allowed_approver_roles": ["product_owner"],
        "allowed_product_scope": list(PRODUCT_SCOPE),
    }
    if mutate_signer is not None:
        mutate_signer(signer)
    trust_root = {
        "schema_version": "rights-holder-license-trust-root.v1",
        "repository_id": REPOSITORY_ID,
        "approved_signers": [signer] if approve_signer else [],
        "revoked_signer_ids": [SIGNER_ID] if revoke_signer else [],
        "revoked_decision_ids": [DECISION_ID] if revoke_decision else [],
        "claim_boundary": (
            "This test trust root identifies one repository-approved signing key only; "
            "it does not itself grant commercial, redistribution, or release authority."
        ),
    }
    trust_root_path = write_json(
        repo_root / "canonical" / "rights-holder-license-trust-root.v1.json",
        trust_root,
    )

    (repo_root / ".gitignore").write_text(
        "license_status.json\n",
        encoding="utf-8",
    )

    _run("git", "init", "-q", cwd=repo_root)
    _run("git", "config", "user.name", "License Test", cwd=repo_root)
    _run("git", "config", "user.email", "license-test@example.invalid", cwd=repo_root)
    _run(
        "git",
        "add",
        "LICENSE",
        ".gitignore",
        "canonical/rights-holder-public.pem",
        "canonical/rights-holder-license-trust-root.v1.json",
        "canonical/license-policies/test-policy.txt",
        cwd=repo_root,
    )
    _run("git", "commit", "-q", "-m", "test trust root", cwd=repo_root)
    source_commit_sha = _run("git", "rev-parse", "HEAD", cwd=repo_root).decode().strip()

    decision: dict[str, Any] = {
        "schema_version": "rights-holder-license-decision.v1",
        "decision_id": DECISION_ID,
        "rights_holder_id": RIGHTS_HOLDER_ID,
        "signer_id": SIGNER_ID,
        "issued_at_utc": ISSUED_AT_UTC,
        "expires_at_utc": EXPIRES_AT_UTC,
        "replay_policy": REPLAY_POLICY,
        "nonce": "fixture_nonce_0123456789abcdef0123456789abcdef",
        "subject": {
            "repository_id": REPOSITORY_ID,
            "source_commit_sha": source_commit_sha,
            "repository_license_sha256": sha256_bytes(license_path.read_bytes()),
            "license_id": "LIC-001",
            "license_policy": {
                "document_path": "canonical/license-policies/test-policy.txt",
                "document_sha256": sha256_bytes(license_policy.read_bytes()),
                "version": LICENSE_POLICY_VERSION,
                "covered_first_party_paths": list(COVERED_FIRST_PARTY_PATHS),
            },
            "tier": "limited-commercial",
            "approver_role": "product_owner",
            "product_scope": list(PRODUCT_SCOPE),
        },
        "grants": {
            "repository_use_approved": True,
            "commercial_use_approved": True,
            "redistribution_approved": True,
            "third_party_material_redistribution_approved": False,
            "release_authority_granted": False,
        },
        "claim_boundary": (
            "This signed test decision applies only to the exact repository, source, "
            "root license, tier, and scope; it grants no third-party rights or release authority."
        ),
    }
    if mutate_decision is not None:
        mutate_decision(decision)
    sign_decision(decision, private_key=private_key)
    decision_path = write_json(
        repo_root
        / "implementation"
        / "phase1"
        / "release"
        / "license_decisions"
        / "rights-holder-decision.json",
        decision,
    )
    return {
        "repo_root": repo_root,
        "license_path": license_path,
        "private_key": private_key,
        "public_key": public_key,
        "license_policy": license_policy,
        "trust_root": trust_root,
        "trust_root_path": trust_root_path,
        "decision": decision,
        "decision_path": decision_path,
        "source_commit_sha": source_commit_sha,
    }


def license_status_payload(
    decision_path: Path | str,
    *,
    approval_ref: str = DECISION_ID,
    issuer: str = RIGHTS_HOLDER_ID,
    approved_at_utc: str = ISSUED_AT_UTC,
    expires_at_utc: str = EXPIRES_AT_UTC,
) -> dict[str, Any]:
    return {
        "status": "active",
        "tier": "limited-commercial",
        "license_id": "LIC-001",
        "issuer": issuer,
        "approver_role": "product_owner",
        "approval_ref": approval_ref,
        "approved_at_utc": approved_at_utc,
        "evidence_ref": str(decision_path),
        "product_scope": list(PRODUCT_SCOPE),
        "expires_at_utc": expires_at_utc,
    }
