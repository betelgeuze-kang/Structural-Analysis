from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from implementation.phase1.project_registry_service import (
    LEGAL_CLAIM_BOUNDARY,
    TECHNICAL_CONTRACT_SEMANTICS,
    _no_legal_authority,
    build_project_registry,
)
from implementation.phase1.release_registry_integrity import (
    REQUIRED_RELEASE_ARTIFACT_LABELS,
    TECHNICAL_PRODUCER_KEY_ENV,
)


def _canonical_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def write_valid_release_registry(
    root: Path,
    *,
    body_artifact_paths: list[Path] | None = None,
    summary_extra: dict[str, Any] | None = None,
    checks_extra: dict[str, Any] | None = None,
) -> tuple[Path, dict[str, Any]]:
    generated_at = "2026-06-16T00:00:00+00:00"
    artifact_paths = list(body_artifact_paths or [])
    if len(artifact_paths) < len(REQUIRED_RELEASE_ARTIFACT_LABELS):
        for index in range(len(artifact_paths), len(REQUIRED_RELEASE_ARTIFACT_LABELS)):
            label = sorted(REQUIRED_RELEASE_ARTIFACT_LABELS)[index]
            artifact = root / f"required-{label}.json"
            _write(artifact, b'{"contract_pass":true}\n')
            artifact_paths.append(artifact)

    signing_dir = root / "signing"
    private_key_path = signing_dir / "release-registry-private.pem"
    public_key_path = signing_dir / "release-registry-public.pem"
    release_signature_path = signing_dir / "release-registry.signature.b64"
    private_key = Ed25519PrivateKey.generate()
    _write(
        private_key_path,
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ),
    )
    _write(
        public_key_path,
        private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ),
    )
    os.environ[TECHNICAL_PRODUCER_KEY_ENV] = hashlib.sha256(public_key_path.read_bytes()).hexdigest()

    artifact_rows = []
    required_labels = sorted(REQUIRED_RELEASE_ARTIFACT_LABELS)
    for index, path in enumerate(artifact_paths, start=1):
        payload = path.read_bytes()
        artifact_rows.append(
            {
                "label": required_labels[index - 1]
                if index <= len(required_labels)
                else f"release_artifact_{index}",
                "path": str(path),
                "sha256": hashlib.sha256(payload).hexdigest(),
                "bytes": len(payload),
            }
        )
    release_claim_boundary = (
        "The release-registry Ed25519 signature verifies registry bytes only and grants no legal authority."
    )
    body = {
        "schema_version": "1.0",
        "registry_id": "phase1-signed-release-registry",
        "generated_at": generated_at,
        "artifacts": artifact_rows,
        "accelerated_coverage_provenance": dict(summary_extra or {}),
        "technical_contract_semantics": TECHNICAL_CONTRACT_SEMANTICS,
        "signature_claim_boundary": release_claim_boundary,
        "legal_claim_boundary": LEGAL_CLAIM_BOUNDARY,
        "authority": _no_legal_authority(),
    }
    canonical_body = _canonical_bytes(body)
    body_sha256 = hashlib.sha256(canonical_body).hexdigest()
    release_signature_b64 = base64.b64encode(private_key.sign(canonical_body)).decode("ascii")
    _write(release_signature_path, (release_signature_b64 + "\n").encode("ascii"))

    project_registry_path = root / "project-registry.json"
    project_package_path = root / "project-package.zip"
    project_signature_path = signing_dir / "project-registry.signature.b64"
    project_artifact_paths = [*artifact_paths, public_key_path, release_signature_path]
    project_artifact_labels = [
        *[str(row["label"]) for row in artifact_rows],
        "release_registry_public_key",
        "release_registry_signature",
    ]
    project_registry = build_project_registry(
        project_id="phase1-release",
        project_name="Phase1 Test Release",
        artifact_paths=project_artifact_paths,
        artifact_labels=project_artifact_labels,
        artifact_root=root,
        audit_payload=[
            {"event_id": f"audit-{index}", "artifact_label": label, "status": "completed"}
            for index, label in enumerate(project_artifact_labels, start=1)
        ],
        approval_payload=[{"gate_id": "technical-review", "status": "approved"}],
        private_key_out=private_key_path,
        public_key_out=public_key_path,
        signature_out=project_signature_path,
        package_out=project_package_path,
        out=project_registry_path,
        generated_at=generated_at,
    )

    summary: dict[str, Any] = {
        "artifact_count": len(artifact_rows) + 3,
        "signing_algorithm": "ed25519",
        "registry_body_sha256": body_sha256,
        "project_registry_package_sha256": project_registry["summary"]["package_sha256"],
        "project_registry_package_bytes": project_registry["summary"]["package_bytes"],
    }
    summary.update(summary_extra or {})
    checks: dict[str, Any] = {
        "green_reports_pass": True,
        "lock_manifest_hash_match": True,
        "artifact_hashes_present_pass": True,
        "public_key_written_pass": True,
        "signature_generated_pass": True,
        "signature_verified_pass": True,
        "legal_authority_fail_closed_pass": True,
        "project_registry_package_pass": True,
        "project_registry_signature_verified_pass": True,
        "project_registry_legal_authority_fail_closed_pass": True,
    }
    checks.update(checks_extra or {})
    report: dict[str, Any] = {
        "schema_version": "1.0",
        "run_id": "phase1-generate-signed-release-registry",
        "generated_at": generated_at,
        "checks": checks,
        "summary": summary,
        "registry_body": body,
        "signature": {
            "algorithm": "ed25519",
            "public_key_path": str(public_key_path),
            "signature_b64": release_signature_b64,
            "signature_out": str(release_signature_path),
            "canonical_body_sha256": body_sha256,
        },
        "artifacts": {
            "project_registry_report": str(project_registry_path),
            "project_package_zip": str(project_package_path),
            "project_registry_signature": str(project_signature_path),
        },
        "project_registry_report": project_registry,
        "technical_contract_semantics": TECHNICAL_CONTRACT_SEMANTICS,
        "signature_claim_boundary": release_claim_boundary,
        "legal_claim_boundary": LEGAL_CLAIM_BOUNDARY,
        "authority": _no_legal_authority(),
        "technical_contract_pass": True,
        "contract_pass": True,
        "reason_code": "PASS",
        "reason": "technically signed release registry generated",
    }
    registry_path = root / "release-registry.json"
    registry_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return registry_path, report
