from __future__ import annotations

import base64
import hashlib
import io
import json
from pathlib import Path
import stat
import zipfile

import pytest

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from implementation.phase1 import release_registry_integrity
from implementation.phase1.release_registry_integrity import (
    NO_LEGAL_AUTHORITY,
    TECHNICAL_PRODUCER_KEY_ENV,
    _safe_artifact_label,
    _normalized_artifact_rows,
    load_and_verify_release_registry_file,
    verify_release_registry_integrity,
)
from tests.release_registry_integrity_test_support import write_valid_release_registry


def _resign_project(payload: dict, tmp_path) -> None:
    project = payload["project_registry_report"]
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


def _replace_package_entries(payload: dict, replacements: dict[str, bytes | None]) -> None:
    project = payload["project_registry_report"]
    package_path = project["registry_body"]["package_artifact"]["path"]
    with zipfile.ZipFile(package_path) as source:
        entries = {
            info.filename: source.read(info.filename)
            for info in source.infolist()
            if info.filename not in replacements or replacements[info.filename] is not None
        }
    for name, replacement in replacements.items():
        if replacement is not None:
            entries[name] = replacement
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as target:
        for name, package_payload in sorted(entries.items()):
            target.writestr(name, package_payload)
    package_bytes = output.getvalue()
    with open(package_path, "wb") as stream:
        stream.write(package_bytes)
    project["registry_body"]["package_artifact"].update(
        sha256=hashlib.sha256(package_bytes).hexdigest(),
        bytes=len(package_bytes),
    )


def _recompress_package(payload: dict) -> None:
    project = payload["project_registry_report"]
    package_path = project["registry_body"]["package_artifact"]["path"]
    with zipfile.ZipFile(package_path) as source:
        entries = [(info.filename, source.read(info.filename)) for info in source.infolist()]
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as target:
        for name, package_payload in entries:
            target.writestr(name, package_payload)
    package_bytes = output.getvalue()
    with open(package_path, "wb") as stream:
        stream.write(package_bytes)
    project["registry_body"]["package_artifact"].update(
        sha256=hashlib.sha256(package_bytes).hexdigest(),
        bytes=len(package_bytes),
    )


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


def test_release_registry_integrity_rejects_noncanonical_audit_row_schema(tmp_path) -> None:
    registry_path, payload = write_valid_release_registry(tmp_path)
    project = payload["project_registry_report"]
    project["registry_body"]["audit_log"][0]["unsigned_extension"] = "accepted"
    _resign_project(payload, tmp_path)

    result = verify_release_registry_integrity(payload, registry_path=registry_path)

    assert result["checks"]["project_registry_signature_pass"] is True
    assert result["checks"]["project_registry_workflow_recomputed_pass"] is False
    assert result["technical_release_registry_integrity_pass"] is False


def test_release_registry_integrity_malformed_paths_and_labels_fail_closed(tmp_path) -> None:
    registry_path, payload = write_valid_release_registry(tmp_path)
    payload["registry_body"]["artifacts"][0]["label"] = "\ud800"
    payload["registry_body"]["artifacts"][0]["path"] = "invalid\0path"

    result = verify_release_registry_integrity(payload, registry_path=registry_path)

    assert result["technical_release_registry_integrity_pass"] is False
    assert result["checks"]["registry_artifact_hashes_and_sizes_pass"] is False
    assert result["legal_authority_established"] is False


def test_release_registry_unsigned_summary_cannot_change_verified_projection(tmp_path) -> None:
    registry_path, payload = write_valid_release_registry(
        tmp_path,
        summary_extra={"mgt_export_direct_patch_change_count": 0},
    )
    payload["summary"]["mgt_export_direct_patch_change_count"] = 3
    payload["summary"]["release_authority"] = True

    result = verify_release_registry_integrity(payload, registry_path=registry_path)

    assert result["technical_release_registry_integrity_pass"] is True
    assert result["verified_release_projection"]["mgt_export_direct_patch_change_count"] == 0
    assert "release_authority" not in result["verified_release_projection"]
    assert result["authority"] == NO_LEGAL_AUTHORITY


def test_release_registry_rejects_coordinated_project_artifact_omission(tmp_path) -> None:
    registry_path, payload = write_valid_release_registry(tmp_path)
    project_body = payload["project_registry_report"]["registry_body"]
    removed = project_body["artifact_rows"].pop(0)
    project_body["audit_log"] = [
        row
        for row in project_body["audit_log"]
        if row.get("artifact_label") != removed["label"]
    ]
    manifest = project_body["package_manifest"]
    manifest["artifact_rows"] = [
        row for row in manifest["artifact_rows"] if row.get("label") != removed["label"]
    ]
    manifest_bytes = json.dumps(
        manifest,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    _replace_package_entries(
        payload,
        {
            f"artifacts/{removed['label']}": None,
            "package_manifest.json": manifest_bytes,
        },
    )
    _resign_project(payload, tmp_path)

    result = verify_release_registry_integrity(payload, registry_path=registry_path)

    assert result["checks"]["project_registry_signature_pass"] is True
    assert result["checks"]["project_package_exact_entries_pass"] is True
    assert result["checks"]["release_project_artifact_bijection_pass"] is False
    assert result["technical_release_registry_integrity_pass"] is False


def test_release_registry_malformed_packaged_rights_status_fails_closed(tmp_path) -> None:
    registry_path, payload = write_valid_release_registry(tmp_path)
    project_body = payload["project_registry_report"]["registry_body"]
    malformed = b"[]"
    legal_rows = project_body["package_manifest"]["legal_and_third_party_artifacts"]
    rights_row = next(
        row for row in legal_rows if row["path"] == "LEGAL_AND_THIRD_PARTY_STATUS.json"
    )
    rights_row.update(sha256=hashlib.sha256(malformed).hexdigest(), bytes=len(malformed))
    manifest_bytes = json.dumps(
        project_body["package_manifest"],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    _replace_package_entries(
        payload,
        {
            "LEGAL_AND_THIRD_PARTY_STATUS.json": malformed,
            "package_manifest.json": manifest_bytes,
        },
    )
    _resign_project(payload, tmp_path)

    result = verify_release_registry_integrity(payload, registry_path=registry_path)

    assert result["technical_release_registry_integrity_pass"] is False
    assert result["checks"]["project_package_authority_fail_closed_pass"] is False
    assert result["authority"] == NO_LEGAL_AUTHORITY


def test_release_registry_rejects_duplicate_key_packaged_rights_status(tmp_path) -> None:
    registry_path, payload = write_valid_release_registry(tmp_path)
    project_body = payload["project_registry_report"]["registry_body"]
    rights_status = project_body["rights_status"]
    canonical = json.dumps(
        rights_status,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    ambiguous = (
        b'{"authority":{"commercial_use_authority":true,'
        b'"redistribution_authority":true,"release_authority":true},'
        + canonical[1:]
    )
    assert json.loads(ambiguous.decode("utf-8")) == rights_status

    legal_rows = project_body["package_manifest"]["legal_and_third_party_artifacts"]
    rights_row = next(
        row for row in legal_rows if row["path"] == "LEGAL_AND_THIRD_PARTY_STATUS.json"
    )
    rights_row.update(
        sha256=hashlib.sha256(ambiguous).hexdigest(),
        bytes=len(ambiguous),
    )
    manifest_bytes = json.dumps(
        project_body["package_manifest"],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    _replace_package_entries(
        payload,
        {
            "LEGAL_AND_THIRD_PARTY_STATUS.json": ambiguous,
            "package_manifest.json": manifest_bytes,
        },
    )
    _resign_project(payload, tmp_path)

    result = verify_release_registry_integrity(payload, registry_path=registry_path)

    assert result["technical_release_registry_integrity_pass"] is False
    assert result["checks"]["project_registry_signature_pass"] is True
    assert result["checks"]["project_package_artifact_hashes_pass"] is True
    assert result["checks"]["project_package_rights_status_canonical_pass"] is False
    assert result["checks"]["project_package_authority_fail_closed_pass"] is False
    assert result["authority"] == NO_LEGAL_AUTHORITY


def test_release_registry_file_rejects_duplicate_or_noncanonical_raw_json(
    tmp_path: Path,
) -> None:
    registry_path, payload = write_valid_release_registry(tmp_path / "fixture")
    canonical = json.dumps(payload, indent=2).encode("utf-8")
    registry_path.write_bytes(canonical)
    loaded, valid = load_and_verify_release_registry_file(registry_path)
    assert loaded == payload
    assert valid["technical_release_registry_integrity_pass"] is True

    registry_path.write_text(json.dumps(payload), encoding="utf-8")
    loaded, noncanonical = load_and_verify_release_registry_file(registry_path)
    assert loaded is None
    assert noncanonical["checks"]["release_registry_raw_canonical_pass"] is False

    duplicate = b'{"reason_code":"ATTACK",' + canonical[1:]
    registry_path.write_bytes(duplicate)
    loaded, ambiguous = load_and_verify_release_registry_file(registry_path)
    assert loaded is None
    assert ambiguous["technical_release_registry_integrity_pass"] is False


def test_release_registry_rejects_zip_symlink_entry(tmp_path: Path) -> None:
    registry_path, payload = write_valid_release_registry(tmp_path)
    project = payload["project_registry_report"]
    package_path = Path(project["registry_body"]["package_artifact"]["path"])
    with zipfile.ZipFile(package_path) as source:
        entries = [(info, source.read(info.filename)) for info in source.infolist()]
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as target:
        for info, entry_payload in entries:
            if info.filename == "LICENSE":
                link = zipfile.ZipInfo("LICENSE")
                link.create_system = 3
                link.external_attr = (stat.S_IFLNK | 0o777) << 16
                target.writestr(link, entry_payload)
            else:
                target.writestr(info, entry_payload)
    package_bytes = output.getvalue()
    package_path.write_bytes(package_bytes)
    project["registry_body"]["package_artifact"].update(
        sha256=hashlib.sha256(package_bytes).hexdigest(),
        bytes=len(package_bytes),
    )
    _resign_project(payload, tmp_path)

    result = verify_release_registry_integrity(payload, registry_path=registry_path)

    assert result["technical_release_registry_integrity_pass"] is False
    assert result["checks"]["project_package_exact_entries_pass"] is False


def test_packaged_rights_license_metadata_binds_exact_license_bytes(tmp_path: Path) -> None:
    registry_path, payload = write_valid_release_registry(tmp_path)
    project_body = payload["project_registry_report"]["registry_body"]
    rights_status = project_body["rights_status"]
    rights_status["repository_license"]["sha256"] = "0" * 64
    rights_bytes = json.dumps(
        rights_status, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    legal_rows = project_body["package_manifest"]["legal_and_third_party_artifacts"]
    rights_row = next(
        row for row in legal_rows if row["path"] == "LEGAL_AND_THIRD_PARTY_STATUS.json"
    )
    rights_row.update(
        sha256=hashlib.sha256(rights_bytes).hexdigest(), bytes=len(rights_bytes)
    )
    manifest_bytes = json.dumps(
        project_body["package_manifest"],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    _replace_package_entries(
        payload,
        {
            "LEGAL_AND_THIRD_PARTY_STATUS.json": rights_bytes,
            "package_manifest.json": manifest_bytes,
        },
    )
    _resign_project(payload, tmp_path)

    result = verify_release_registry_integrity(payload, registry_path=registry_path)

    assert result["technical_release_registry_integrity_pass"] is False
    assert result["checks"]["repository_license_packaged_pass"] is False


def test_package_manifest_project_id_must_match_signed_project_body(tmp_path: Path) -> None:
    registry_path, payload = write_valid_release_registry(tmp_path)
    project_body = payload["project_registry_report"]["registry_body"]
    project_body["package_manifest"]["project_id"] = "attacker-project"
    manifest_bytes = json.dumps(
        project_body["package_manifest"],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    _replace_package_entries(payload, {"package_manifest.json": manifest_bytes})
    _resign_project(payload, tmp_path)

    result = verify_release_registry_integrity(payload, registry_path=registry_path)

    assert result["technical_release_registry_integrity_pass"] is False
    assert result["checks"]["project_package_exact_entries_pass"] is False


@pytest.mark.parametrize(
    "label",
    ["CON", "con.txt", "LPT1.json", "aux.", "trail ", "name:stream"],
)
def test_windows_unsafe_artifact_labels_are_rejected(label: str) -> None:
    assert _safe_artifact_label(label) == ""


def test_artifact_labels_reject_casefold_collisions() -> None:
    rows = [
        {"label": "Report", "path": "a", "sha256": "a" * 64, "bytes": 1},
        {"label": "report", "path": "b", "sha256": "b" * 64, "bytes": 1},
    ]
    assert _normalized_artifact_rows(rows, include_path=True) is None


def test_release_registry_rejects_self_consistent_arbitrary_packaged_license(tmp_path) -> None:
    registry_path, payload = write_valid_release_registry(tmp_path)
    project_body = payload["project_registry_report"]["registry_body"]
    arbitrary_license = b"attacker supplied license text\n"
    legal_rows = project_body["package_manifest"]["legal_and_third_party_artifacts"]
    license_row = next(row for row in legal_rows if row["path"] == "LICENSE")
    license_row.update(
        sha256=hashlib.sha256(arbitrary_license).hexdigest(),
        bytes=len(arbitrary_license),
    )
    manifest_bytes = json.dumps(
        project_body["package_manifest"],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    _replace_package_entries(
        payload,
        {
            "LICENSE": arbitrary_license,
            "package_manifest.json": manifest_bytes,
        },
    )
    _resign_project(payload, tmp_path)

    result = verify_release_registry_integrity(payload, registry_path=registry_path)

    assert result["checks"]["project_registry_signature_pass"] is True
    assert result["checks"]["project_package_artifact_hashes_pass"] is True
    assert result["checks"]["repository_license_packaged_pass"] is False
    assert result["technical_release_registry_integrity_pass"] is False


def test_release_registry_rejects_zip_resource_limit_excess(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry_path, payload = write_valid_release_registry(tmp_path)
    monkeypatch.setattr(release_registry_integrity, "MAX_PROJECT_PACKAGE_ENTRIES", 2)

    result = verify_release_registry_integrity(payload, registry_path=registry_path)

    assert result["technical_release_registry_integrity_pass"] is False
    assert result["checks"]["project_package_exact_entries_pass"] is False


def test_release_registry_rejects_zip_total_uncompressed_limit_excess(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry_path, payload = write_valid_release_registry(tmp_path)
    monkeypatch.setattr(release_registry_integrity, "MAX_PROJECT_PACKAGE_UNCOMPRESSED_BYTES", 1)

    result = verify_release_registry_integrity(payload, registry_path=registry_path)

    assert result["technical_release_registry_integrity_pass"] is False
    assert result["checks"]["project_package_exact_entries_pass"] is False


def test_release_registry_rejects_zip_compression_ratio_limit_excess(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry_path, payload = write_valid_release_registry(tmp_path)
    _recompress_package(payload)
    _resign_project(payload, tmp_path)
    monkeypatch.setattr(release_registry_integrity, "MAX_PROJECT_PACKAGE_COMPRESSION_RATIO", 1)

    result = verify_release_registry_integrity(payload, registry_path=registry_path)

    assert result["checks"]["project_registry_signature_pass"] is True
    assert result["technical_release_registry_integrity_pass"] is False
    assert result["checks"]["project_package_exact_entries_pass"] is False


def test_release_registry_requires_environment_pinned_technical_key(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry_path, payload = write_valid_release_registry(tmp_path)
    monkeypatch.setenv(TECHNICAL_PRODUCER_KEY_ENV, "0" * 64)

    result = verify_release_registry_integrity(payload, registry_path=registry_path)

    assert result["technical_release_registry_integrity_pass"] is False
    assert result["checks"]["technical_producer_key_policy_pass"] is False
    assert result["authority"] == NO_LEGAL_AUTHORITY


@pytest.mark.parametrize("label", ["visible\u200bcontrol", "delete\x7fcontrol", "fullwidthＡ"])
def test_release_registry_rejects_unicode_control_or_noncanonical_labels(label: str) -> None:
    assert _safe_artifact_label(label) == ""


def test_release_registry_file_identity_comparison_uses_fd_snapshots(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact = tmp_path / "artifact.bin"
    artifact.write_bytes(b"stable")
    monkeypatch.setattr(
        release_registry_integrity.os.path,
        "samefile",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("path re-resolution")),
    )

    assert release_registry_integrity._same_file_reference(
        artifact,
        artifact,
        registry_path=None,
    ) is True
