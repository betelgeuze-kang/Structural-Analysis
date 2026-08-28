from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest

from implementation.phase1 import project_registry_service
from implementation.phase1.project_registry_service import build_project_registry, build_project_registry_index


NO_LEGAL_AUTHORITY = {
    "product_license_approval": False,
    "commercial_use_authority": False,
    "redistribution_authority": False,
    "third_party_redistribution_clearance": "not_established",
    "release_authority": False,
}


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_build_project_registry_generates_signed_reproducible_package(tmp_path: Path) -> None:
    artifact_a = tmp_path / "analysis_report.json"
    artifact_b = tmp_path / "model_export.mgt"
    artifact_a.write_text(json.dumps({"contract_pass": True, "reason_code": "PASS"}), encoding="utf-8")
    artifact_b.write_text("*MIDAS MODEL*\n", encoding="utf-8")
    audit_json = tmp_path / "audit_log.json"
    approval_json = tmp_path / "approval.json"
    _write_json(
        audit_json,
        {
            "audit_log": [
                {
                    "event_id": "audit-001",
                    "actor": "kim.structural",
                    "action": "registered_artifact",
                    "status": "completed",
                    "artifact_label": "analysis_report.json",
                    "timestamp": "2026-04-19T00:00:00+00:00",
                },
                {
                    "event_id": "audit-002",
                    "actor": "lee.engineer",
                    "action": "registered_artifact",
                    "status": "completed",
                    "artifact_label": "model_export.mgt",
                    "timestamp": "2026-04-19T00:05:00+00:00",
                },
            ]
        },
    )
    _write_json(
        approval_json,
        {
            "approvals": [
                {
                    "gate_id": "structural-review",
                    "approver": "kim.licensed",
                    "status": "approved",
                    "decided_at": "2026-04-19T01:00:00+00:00",
                    "product_license_approval": True,
                    "commercial_use_authority": True,
                    "redistribution_authority": True,
                    "release_authority": True,
                },
                {
                    "gate_id": "qa-signoff",
                    "approver": "lee.qa",
                    "status": "approved",
                    "decided_at": "2026-04-19T01:30:00+00:00",
                },
            ]
        },
    )

    out = tmp_path / "registry" / "project_registry.json"
    package_out = tmp_path / "registry" / "project_package.zip"
    private_key = tmp_path / "signing" / "project_registry_ed25519.pem"
    public_key = tmp_path / "signing" / "project_registry_ed25519.pub.pem"
    signature_out = tmp_path / "signing" / "project_registry.signature.b64"

    payload = build_project_registry(
        project_id="tower-a",
        project_name="Tower A",
        artifact_paths=[artifact_a, artifact_b],
        audit_payload=json.loads(audit_json.read_text(encoding="utf-8")),
        approval_payload=json.loads(approval_json.read_text(encoding="utf-8")),
        project_metadata={
            "family_id": "concrete_midrise_baseline",
            "portfolio_name": "phase1-native-authoring-ops-portfolio",
            "draft_label": "baseline",
        },
        private_key_out=private_key,
        public_key_out=public_key,
        signature_out=signature_out,
        package_out=package_out,
        out=out,
        generated_at="2026-04-19T02:00:00+00:00",
    )

    assert payload["contract_pass"] is True
    assert payload["checks"]["audit_trail_complete_pass"] is True
    assert payload["checks"]["approval_complete_pass"] is True
    assert payload["checks"]["signature_verified_pass"] is True
    assert payload["checks"]["package_reproducible_pass"] is True
    assert payload["checks"]["repository_license_packaged_pass"] is True
    assert payload["checks"]["rights_status_packaged_pass"] is True
    assert payload["checks"]["legal_authority_fail_closed_pass"] is True
    assert payload["technical_contract_pass"] is True
    assert payload["technical_contract_semantics"] == "technical_package_integrity_and_workflow_completion_only"
    assert payload["authority"] == NO_LEGAL_AUTHORITY
    assert payload["registry_body"]["authority"] == NO_LEGAL_AUTHORITY
    assert payload["registry_body"]["approval_semantics"] == "technical_project_workflow_only"
    assert payload["summary"]["key_generated_this_run"] is True
    assert package_out.exists()
    assert out.exists()
    assert signature_out.exists()
    assert payload["metadata"]["family_id"] == "concrete_midrise_baseline"
    assert payload["summary"]["portfolio_name"] == "phase1-native-authoring-ops-portfolio"
    package_sha256 = hashlib.sha256(package_out.read_bytes()).hexdigest()
    assert payload["summary"]["package_sha256"] == package_sha256
    with zipfile.ZipFile(package_out) as zf:
        assert zf.namelist() == [
            "LEGAL_AND_THIRD_PARTY_STATUS.json",
            "LICENSE",
            "artifacts/analysis_report.json",
            "artifacts/model_export.mgt",
            "package_manifest.json",
        ]
        bundled_license = zf.read("LICENSE")
        rights_status_bytes = zf.read("LEGAL_AND_THIRD_PARTY_STATUS.json")
        rights_status = json.loads(rights_status_bytes.decode("utf-8"))
        package_manifest = json.loads(zf.read("package_manifest.json").decode("utf-8"))
    repository_license = (Path(__file__).resolve().parents[1] / "LICENSE").read_bytes()
    assert bundled_license == repository_license
    assert rights_status["repository_license"]["sha256"] == hashlib.sha256(repository_license).hexdigest()
    assert rights_status["repository_license"]["bytes"] == len(repository_license)
    assert rights_status["rights_holder_decision"]["verified"] is False
    assert rights_status["rights_holder_decision"]["signature_verified"] is False
    assert rights_status["third_party_review"]["status"] == "not_established"
    assert rights_status["authority"] == NO_LEGAL_AUTHORITY
    assert package_manifest["project_id"] == "tower-a"
    assert package_manifest["schema_version"] == "project-package-manifest.v2"
    assert package_manifest["authority"] == NO_LEGAL_AUTHORITY
    legal_rows = {row["path"]: row for row in package_manifest["legal_and_third_party_artifacts"]}
    assert legal_rows["LICENSE"]["sha256"] == hashlib.sha256(repository_license).hexdigest()
    assert legal_rows["LICENSE"]["bytes"] == len(repository_license)
    assert legal_rows["LEGAL_AND_THIRD_PARTY_STATUS.json"]["sha256"] == hashlib.sha256(
        rights_status_bytes
    ).hexdigest()
    assert legal_rows["LEGAL_AND_THIRD_PARTY_STATUS.json"]["bytes"] == len(rights_status_bytes)
    assert len(package_manifest["artifact_rows"]) == 2


def test_project_registry_fails_closed_when_repository_license_is_missing(tmp_path: Path, monkeypatch) -> None:
    artifact = tmp_path / "artifact.json"
    artifact.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(project_registry_service, "REPOSITORY_LICENSE", tmp_path / "missing-LICENSE")

    with pytest.raises(FileNotFoundError, match="repository LICENSE missing or unsafe"):
        build_project_registry(
            project_id="blocked",
            project_name="Blocked",
            artifact_paths=[artifact],
            audit_payload=[{"artifact_label": "artifact.json", "status": "completed"}],
            approval_payload=[{"status": "approved"}],
            private_key_out=tmp_path / "private.pem",
            public_key_out=tmp_path / "public.pem",
            signature_out=tmp_path / "signature.b64",
            package_out=tmp_path / "project_package.zip",
            out=tmp_path / "project_registry.json",
            generated_at="2026-04-19T02:00:00+00:00",
        )


def test_project_registry_rejects_package_without_exact_license_bytes(tmp_path: Path, monkeypatch) -> None:
    artifact = tmp_path / "artifact.json"
    artifact.write_text("{}\n", encoding="utf-8")
    original_build = project_registry_service._build_package_bytes

    def _tampered_build(*args, **kwargs):
        package_bytes = original_build(*args, **kwargs)
        source = zipfile.ZipFile(io.BytesIO(package_bytes))
        output = io.BytesIO()
        with source, zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as target:
            for info in source.infolist():
                payload = b"tampered\n" if info.filename == "LICENSE" else source.read(info.filename)
                target.writestr(info, payload)
        return output.getvalue()

    monkeypatch.setattr(project_registry_service, "_build_package_bytes", _tampered_build)
    payload = build_project_registry(
        project_id="blocked",
        project_name="Blocked",
        artifact_paths=[artifact],
        audit_payload=[{"artifact_label": "artifact.json", "status": "completed"}],
        approval_payload=[{"status": "approved"}],
        private_key_out=tmp_path / "private.pem",
        public_key_out=tmp_path / "public.pem",
        signature_out=tmp_path / "signature.b64",
        package_out=tmp_path / "project_package.zip",
        out=tmp_path / "project_registry.json",
        generated_at="2026-04-19T02:00:00+00:00",
    )

    assert payload["contract_pass"] is False
    assert payload["technical_contract_pass"] is False
    assert payload["reason_code"] == "ERR_PACKAGE"
    assert payload["checks"]["repository_license_packaged_pass"] is False
    assert payload["authority"] == NO_LEGAL_AUTHORITY


def test_project_registry_service_cli_smoke_and_reproducible_hash(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact.json"
    artifact.write_text(json.dumps({"value": 1}), encoding="utf-8")
    audit_json = tmp_path / "audit.json"
    approval_json = tmp_path / "approval.json"
    _write_json(
        audit_json,
        {
            "events": [
                {
                    "event_id": "evt-1",
                    "actor": "park.pm",
                    "action": "registered_artifact",
                    "status": "completed",
                    "artifact_label": "artifact.json",
                    "timestamp": "2026-04-19T00:00:00+00:00",
                }
            ]
        },
    )
    _write_json(
        approval_json,
        {
            "approval_rows": [
                {
                    "gate_id": "approval-main",
                    "approver": "park.pm",
                    "status": "approved",
                    "decided_at": "2026-04-19T00:10:00+00:00",
                }
            ]
        },
    )

    package_out_1 = tmp_path / "run1" / "package.zip"
    out_1 = tmp_path / "run1" / "project_registry.json"
    package_out_2 = tmp_path / "run2" / "package.zip"
    out_2 = tmp_path / "run2" / "project_registry.json"
    private_key = tmp_path / "signing" / "project_registry_ed25519.pem"
    public_key = tmp_path / "signing" / "project_registry_ed25519.pub.pem"
    signature_out = tmp_path / "signing" / "project_registry.signature.b64"

    common_args = [
        sys.executable,
        "implementation/phase1/project_registry_service.py",
        "--project-id",
        "bridge-b",
        "--project-name",
        "Bridge B",
        "--artifact-paths",
        str(artifact),
        "--audit-log-json",
        str(audit_json),
        "--approval-json",
        str(approval_json),
        "--private-key-out",
        str(private_key),
        "--public-key-out",
        str(public_key),
        "--signature-out",
        str(signature_out),
        "--generated-at",
        "2026-04-19T03:00:00+00:00",
    ]

    proc_1 = subprocess.run(
        common_args + ["--package-out", str(package_out_1), "--out", str(out_1)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc_1.returncode == 0, proc_1.stderr
    proc_2 = subprocess.run(
        common_args + ["--package-out", str(package_out_2), "--out", str(out_2)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc_2.returncode == 0, proc_2.stderr

    payload_1 = json.loads(out_1.read_text(encoding="utf-8"))
    payload_2 = json.loads(out_2.read_text(encoding="utf-8"))
    assert payload_1["contract_pass"] is True
    assert payload_2["contract_pass"] is True
    assert payload_1["summary"]["package_sha256"] == payload_2["summary"]["package_sha256"]
    assert payload_1["summary_line"].startswith("Project registry service: PASS")
    assert payload_2["checks"]["signature_verified_pass"] is True


def test_project_registry_index_aggregates_multiple_signed_projects(tmp_path: Path) -> None:
    registry_a = tmp_path / "a.json"
    registry_b = tmp_path / "b.json"
    _write_json(
        registry_a,
        {
            "generated_at": "2026-04-19T03:00:00+00:00",
            "contract_pass": True,
            "summary": {
                "project_id": "tower-a",
                "project_name": "Tower A",
                "approval_count": 2,
                "approved_count": 2,
                "audit_event_count": 3,
                "package_sha256": "sha-a",
            },
            "checks": {
                "signature_verified_pass": True,
                "package_reproducible_pass": True,
            },
        },
    )
    _write_json(
        registry_b,
        {
            "generated_at": "2026-04-19T04:00:00+00:00",
            "contract_pass": True,
            "summary": {
                "project_id": "bridge-b",
                "project_name": "Bridge B",
                "approval_count": 1,
                "approved_count": 1,
                "audit_event_count": 2,
                "package_sha256": "sha-b",
            },
            "checks": {
                "signature_verified_pass": True,
                "package_reproducible_pass": True,
            },
        },
    )

    out = tmp_path / "portfolio" / "project_registry_index.json"
    payload = build_project_registry_index(registry_paths=[registry_a, registry_b], out=out)

    assert payload["contract_pass"] is True
    assert payload["technical_contract_pass"] is True
    assert payload["authority"] == NO_LEGAL_AUTHORITY
    assert payload["summary"]["project_count"] == 2
    assert payload["summary"]["complete_project_count"] == 2
    assert payload["summary"]["signature_verified_count"] == 2
    assert payload["summary"]["package_reproducible_count"] == 2
    assert payload["summary"]["unique_project_count"] == 2
    assert payload["summary"]["family_count"] == 0
    assert payload["summary"]["approval_complete_count"] == 2
    assert payload["summary"]["latest_registry_generated_at"] == "2026-04-19T04:00:00+00:00"
    assert payload["scan"]["summary"]["discovered_registry_count"] == 2
    assert payload["project_rows"][0]["project_id"] == "bridge-b"
    assert payload["rows"][0]["project_id"] == "bridge-b"
    assert out.exists()


def test_project_registry_index_discovers_directory_and_glob_inputs_with_workspace(tmp_path: Path) -> None:
    release_root = tmp_path / "release"
    registry_a = release_root / "tower-a" / "project_registry.json"
    registry_b = release_root / "bridge-b" / "release_registry.json"
    _write_json(
        registry_a,
        {
            "generated_at": "2026-04-19T05:00:00+00:00",
            "contract_pass": True,
            "reason_code": "PASS",
            "summary": {
                "project_id": "tower-a",
                "project_name": "Tower A",
                "project_family_id": "concrete_midrise_baseline",
                "portfolio_name": "phase1-native-authoring-ops-portfolio",
                "draft_label": "baseline",
                "artifact_count": 2,
                "approval_count": 2,
                "approved_count": 2,
                "pending_count": 0,
                "audit_event_count": 3,
                "package_sha256": "sha-a",
                "registry_body_sha256": "body-a",
            },
            "checks": {
                "signature_verified_pass": True,
                "package_reproducible_pass": True,
            },
            "metadata": {
                "family_id": "concrete_midrise_baseline",
                "portfolio_name": "phase1-native-authoring-ops-portfolio",
                "draft_label": "baseline",
            },
        },
    )
    _write_json(
        registry_b,
        {
            "generated_at": "2026-04-19T06:00:00+00:00",
            "contract_pass": True,
            "reason_code": "PASS",
            "summary": {
                "project_id": "bridge-b",
                "project_name": "Bridge B",
                "project_family_id": "steel_braced_alt",
                "portfolio_name": "phase1-native-authoring-ops-portfolio",
                "draft_label": "steel-alt",
                "artifact_count": 1,
                "approval_count": 1,
                "approved_count": 1,
                "pending_count": 0,
                "audit_event_count": 2,
                "package_sha256": "sha-b",
                "registry_body_sha256": "body-b",
            },
            "checks": {
                "signature_verified_pass": True,
                "package_reproducible_pass": True,
            },
            "metadata": {
                "family_id": "steel_braced_alt",
                "portfolio_name": "phase1-native-authoring-ops-portfolio",
                "draft_label": "steel-alt",
            },
        },
    )

    out = release_root / "project_registry_index.json"
    workspace_out = release_root / "project_registry_portfolio_workspace.json"
    payload = build_project_registry_index(
        registry_dirs=[release_root],
        registry_globs=[str(release_root / "**" / "project_registry.json")],
        out=out,
        workspace_out=workspace_out,
    )

    assert payload["contract_pass"] is True
    assert payload["summary"]["project_count"] == 2
    assert payload["summary"]["unique_project_count"] == 2
    assert payload["summary"]["family_count"] == 2
    assert payload["summary"]["portfolio_count"] == 1
    assert payload["summary"]["total_approval_count"] == 3
    assert payload["scan"]["summary"]["directory_input_count"] == 1
    assert payload["scan"]["summary"]["glob_input_count"] == 1
    assert payload["scan"]["summary"]["discovered_registry_count"] == 2
    assert payload["scan"]["summary"]["duplicate_registry_count"] == 1
    tower_row = next(row for row in payload["rows"] if row["project_id"] == "tower-a")
    assert tower_row["source_kinds"] == ["directory", "glob"]
    assert tower_row["artifact_count"] == 2
    assert tower_row["approval_complete"] is True
    assert payload["project_rows"][0]["project_id"] == "bridge-b"
    assert payload["family_rows"][0]["portfolio_name"] == "phase1-native-authoring-ops-portfolio"
    assert workspace_out.exists()
    workspace_payload = json.loads(workspace_out.read_text(encoding="utf-8"))
    assert workspace_payload["run_id"] == "phase1-project-registry-portfolio-workspace"
    assert workspace_payload["technical_contract_pass"] is True
    assert workspace_payload["authority"] == NO_LEGAL_AUTHORITY
    assert len(workspace_payload["family_rows"]) == 2
    assert workspace_payload["artifacts"]["project_registry_index_json"] == str(out)
