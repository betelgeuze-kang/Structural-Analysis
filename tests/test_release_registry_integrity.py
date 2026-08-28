from __future__ import annotations

import base64
import hashlib
import io
import json
import zipfile

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from implementation.phase1.release_registry_integrity import (
    NO_LEGAL_AUTHORITY,
    verify_release_registry_integrity,
)
from tests.release_registry_integrity_test_support import write_valid_release_registry


def test_release_registry_integrity_verifies_signed_body_artifacts_and_package(tmp_path) -> None:
    registry_path, payload = write_valid_release_registry(tmp_path)

    result = verify_release_registry_integrity(payload, registry_path=registry_path)

    assert result["technical_release_registry_integrity_pass"] is True
    assert all(result["checks"].values())
    assert result["legal_authority_established"] is False
    assert result["authority"] == NO_LEGAL_AUTHORITY


def test_release_registry_integrity_rejects_unsigned_body_mutation(tmp_path) -> None:
    registry_path, payload = write_valid_release_registry(tmp_path)
    payload["registry_body"]["generated_at"] = "2099-01-01T00:00:00+00:00"

    result = verify_release_registry_integrity(payload, registry_path=registry_path)

    assert result["technical_release_registry_integrity_pass"] is False
    assert result["checks"]["registry_body_hash_pass"] is False
    assert result["checks"]["registry_ed25519_signature_pass"] is False


def test_release_registry_integrity_rejects_artifact_mutation(tmp_path) -> None:
    registry_path, payload = write_valid_release_registry(tmp_path)
    artifact_path = payload["registry_body"]["artifacts"][0]["path"]
    with open(artifact_path, "ab") as stream:
        stream.write(b"tampered\n")

    result = verify_release_registry_integrity(payload, registry_path=registry_path)

    assert result["technical_release_registry_integrity_pass"] is False
    assert result["checks"]["registry_artifact_hashes_and_sizes_pass"] is False
    assert result["checks"]["project_registry_artifact_files_pass"] is False


def test_release_registry_integrity_rejects_project_package_extra_entry(tmp_path) -> None:
    registry_path, payload = write_valid_release_registry(tmp_path)
    package_path = payload["artifacts"]["project_package_zip"]
    with zipfile.ZipFile(package_path) as source:
        rows = [(info, source.read(info.filename)) for info in source.infolist()]
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as target:
        for info, package_payload in rows:
            target.writestr(info, package_payload)
        target.writestr("unlisted.txt", b"tampered\n")
    with open(package_path, "wb") as stream:
        stream.write(output.getvalue())

    result = verify_release_registry_integrity(payload, registry_path=registry_path)

    assert result["technical_release_registry_integrity_pass"] is False
    assert result["checks"]["project_package_exact_entries_pass"] is False
    assert result["checks"]["project_package_binding_pass"] is False


def test_release_registry_integrity_rejects_legal_authority_claim(tmp_path) -> None:
    registry_path, payload = write_valid_release_registry(tmp_path)
    payload["authority"]["release_authority"] = True

    result = verify_release_registry_integrity(payload, registry_path=registry_path)

    assert result["technical_release_registry_integrity_pass"] is False
    assert result["checks"]["registry_authority_fail_closed_pass"] is False
    assert result["authority"] == NO_LEGAL_AUTHORITY


def test_release_registry_integrity_rejects_self_reported_pass_without_signature(tmp_path) -> None:
    registry_path = tmp_path / "release-registry.json"
    payload = {"contract_pass": True, "reason_code": "PASS", "summary": {"signing_algorithm": "ed25519"}}
    registry_path.write_text(json.dumps(payload), encoding="utf-8")

    result = verify_release_registry_integrity(payload, registry_path=registry_path)

    assert result["technical_release_registry_integrity_pass"] is False
    assert result["checks"]["registry_body_present_pass"] is False


def test_release_registry_integrity_binds_project_signature_to_release_key(tmp_path) -> None:
    registry_path, payload = write_valid_release_registry(tmp_path)
    project = payload["project_registry_report"]
    attacker_key = Ed25519PrivateKey.generate()
    attacker_public = tmp_path / "attacker-project-public.pem"
    attacker_signature = tmp_path / "attacker-project.signature.b64"
    attacker_public.write_bytes(
        attacker_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    project_body = json.dumps(
        project["registry_body"],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    signature_b64 = base64.b64encode(attacker_key.sign(project_body)).decode("ascii")
    attacker_signature.write_text(signature_b64 + "\n", encoding="ascii")
    project["signature"].update(
        public_key_path=str(attacker_public),
        signature_out=str(attacker_signature),
        signature_b64=signature_b64,
    )
    payload["artifacts"]["project_registry_signature"] = str(attacker_signature)
    with open(payload["artifacts"]["project_registry_report"], "w", encoding="utf-8") as stream:
        json.dump(project, stream, ensure_ascii=False, indent=2)

    result = verify_release_registry_integrity(payload, registry_path=registry_path)

    assert result["technical_release_registry_integrity_pass"] is False
    assert result["checks"]["project_registry_signature_pass"] is True
    assert result["checks"]["project_registry_signing_key_binding_pass"] is False
    assert result["legal_authority_established"] is False


def test_release_registry_integrity_recomputes_project_workflow_completion(tmp_path) -> None:
    registry_path, payload = write_valid_release_registry(tmp_path)
    project = payload["project_registry_report"]
    project["registry_body"]["approvals"][0]["status"] = "pending"
    project_body = json.dumps(
        project["registry_body"],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    body_sha256 = hashlib.sha256(project_body).hexdigest()
    private_key = serialization.load_pem_private_key(
        (tmp_path / "signing" / "release-registry-private.pem").read_bytes(),
        password=None,
    )
    assert isinstance(private_key, Ed25519PrivateKey)
    signature_b64 = base64.b64encode(private_key.sign(project_body)).decode("ascii")
    project["signature"]["signature_b64"] = signature_b64
    project["signature"]["canonical_body_sha256"] = body_sha256
    project["summary"]["registry_body_sha256"] = body_sha256
    with open(project["signature"]["signature_out"], "w", encoding="ascii") as stream:
        stream.write(signature_b64 + "\n")
    with open(payload["artifacts"]["project_registry_report"], "w", encoding="utf-8") as stream:
        json.dump(project, stream, ensure_ascii=False, indent=2)

    result = verify_release_registry_integrity(payload, registry_path=registry_path)

    assert result["technical_release_registry_integrity_pass"] is False
    assert result["checks"]["project_registry_signature_pass"] is True
    assert result["checks"]["project_registry_workflow_recomputed_pass"] is False
    assert result["legal_authority_established"] is False


def test_release_registry_integrity_malformed_paths_and_labels_fail_closed(tmp_path) -> None:
    registry_path, payload = write_valid_release_registry(tmp_path)
    payload["registry_body"]["artifacts"][0]["label"] = "\ud800"
    payload["registry_body"]["artifacts"][0]["path"] = "invalid\0path"

    result = verify_release_registry_integrity(payload, registry_path=registry_path)

    assert result["technical_release_registry_integrity_pass"] is False
    assert result["checks"]["registry_artifact_hashes_and_sizes_pass"] is False
    assert result["legal_authority_established"] is False
