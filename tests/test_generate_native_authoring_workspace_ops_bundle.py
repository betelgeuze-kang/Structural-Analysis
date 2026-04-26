from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import zipfile

from implementation.phase1.generate_native_authoring_workspace_ops_bundle import (
    build_native_authoring_workspace_ops_bundle,
)
from implementation.phase1.generate_native_authoring_workspace_summary import (
    build_native_authoring_workspace_payload,
)


SCRIPT = Path("implementation/phase1/generate_native_authoring_workspace_ops_bundle.py")


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_build_native_authoring_workspace_ops_bundle_generates_solver_batch_and_registry_artifacts(
    tmp_path: Path,
) -> None:
    release_authoring = tmp_path / "release" / "authoring"
    release_signing = tmp_path / "release" / "signing"
    workspace_summary = release_authoring / "native_authoring_workspace_summary.json"
    workspace_draft = release_authoring / "native_authoring_workspace_draft.json"
    solver_session = release_authoring / "native_authoring_solver_session.json"
    solver_loadcomb = release_authoring / "native_authoring_solver_session.loadcomb_preview.mgt"
    job_manifest = release_authoring / "native_authoring_job_manifest.json"
    batch_report = release_authoring / "native_authoring_batch_job_report.json"
    project_registry = release_authoring / "native_authoring_project_registry.json"
    project_package = release_authoring / "native_authoring_project_package.zip"
    private_key = release_signing / "native_authoring_project_registry_ed25519.pem"
    public_key = release_signing / "native_authoring_project_registry_ed25519.pub.pem"
    signature = release_signing / "native_authoring_project_registry.signature.b64"
    out = release_authoring / "native_authoring_ops_bundle.json"

    payload = build_native_authoring_workspace_ops_bundle(
        workspace_summary_path=workspace_summary,
        solver_session_out=solver_session,
        solver_loadcomb_out=solver_loadcomb,
        job_manifest_out=job_manifest,
        batch_report_out=batch_report,
        snapshot_root=release_authoring / "snapshots",
        project_registry_out=project_registry,
        project_package_out=project_package,
        private_key_out=private_key,
        public_key_out=public_key,
        signature_out=signature,
        out=out,
        generated_at="2026-04-19T08:00:00+00:00",
        family_id="concrete_midrise_baseline",
        portfolio_name="phase1-native-authoring-ops-portfolio",
        draft_label="baseline",
    )

    assert payload["contract_pass"] is True
    assert payload["generated_at"] == "2026-04-19T08:00:00+00:00"
    assert payload["inputs"]["workspace_summary_source_mode"] == "generated"
    assert payload["inputs"]["family_id"] == "concrete_midrise_baseline"
    assert payload["summary"]["portfolio_name"] == "phase1-native-authoring-ops-portfolio"
    assert payload["artifacts"]["solver_session_json"] == str(solver_session)
    assert payload["artifacts"]["workspace_draft_json"] == str(workspace_draft)
    assert payload["artifacts"]["solver_loadcomb_preview_mgt"] == str(solver_loadcomb)
    assert payload["artifacts"]["batch_job_report_json"] == str(batch_report)
    assert payload["artifacts"]["project_registry_json"] == str(project_registry)
    assert payload["artifacts"]["project_package_zip"] == str(project_package)
    assert payload["artifacts"]["project_registry_signature"] == str(signature)
    assert payload["summary"]["workspace_artifact_count"] == 3
    assert payload["summary"]["solver_combo_count"] == 13
    assert payload["summary"]["solver_mesh_request_count"] == 2
    assert workspace_summary.exists()
    assert workspace_draft.exists()
    assert solver_session.exists()
    assert solver_loadcomb.exists()
    assert job_manifest.exists()
    assert batch_report.exists()
    assert project_registry.exists()
    assert project_package.exists()
    assert public_key.exists()
    assert signature.exists()

    batch_payload = json.loads(batch_report.read_text(encoding="utf-8"))
    assert batch_payload["contract_pass"] is True
    assert batch_payload["summary"]["job_count"] == 3
    assert batch_payload["summary"]["snapshot_count"] == 3
    solver_job = next(row for row in batch_payload["queue_rows"] if row["job_id"].endswith("solver-session"))
    assert solver_job["lifecycle_status"] == "completed"
    assert solver_job["artifact_paths"] == [
        str(solver_session),
        str(solver_loadcomb),
    ]
    registry_job = next(row for row in batch_payload["queue_rows"] if row["job_id"].endswith("project-registry"))
    assert registry_job["lifecycle_status"] == "completed"
    assert registry_job["artifact_paths"] == [
        str(project_registry),
        str(project_package),
        str(public_key),
        str(signature),
    ]
    assert Path(solver_job["latest_snapshot"]).exists()
    assert Path(registry_job["latest_snapshot"]).exists()

    registry_payload = json.loads(project_registry.read_text(encoding="utf-8"))
    assert registry_payload["contract_pass"] is True
    assert registry_payload["metadata"]["draft_label"] == "baseline"
    assert registry_payload["summary"]["artifact_count"] == 4
    assert registry_payload["checks"]["signature_verified_pass"] is True
    assert registry_payload["artifacts"]["project_package_zip"] == str(project_package)
    assert registry_payload["artifacts"]["project_registry_json"] == str(project_registry)
    assert registry_payload["artifacts"]["project_signature_b64"] == str(signature)
    assert payload["summary"]["registry_package_sha256"] == registry_payload["summary"]["package_sha256"]

    with zipfile.ZipFile(project_package) as zf:
        assert zf.namelist() == [
            "artifacts/native_authoring_job_manifest.json",
            "artifacts/native_authoring_solver_session.json",
            "artifacts/native_authoring_solver_session.loadcomb_preview.mgt",
            "artifacts/native_authoring_workspace_summary.json",
            "package_manifest.json",
        ]
        package_manifest = json.loads(zf.read("package_manifest.json").decode("utf-8"))

    assert package_manifest["generated_at"] == "2026-04-19T08:00:00+00:00"
    assert len(package_manifest["artifact_rows"]) == 4


def test_generate_native_authoring_workspace_ops_bundle_cli_reuses_existing_summary_deterministically(
    tmp_path: Path,
) -> None:
    release_authoring = tmp_path / "release" / "authoring"
    release_signing = tmp_path / "release" / "signing"
    workspace_summary = release_authoring / "native_authoring_workspace_summary.json"
    solver_session = release_authoring / "native_authoring_solver_session.json"
    solver_loadcomb = release_authoring / "native_authoring_solver_session.loadcomb_preview.mgt"
    job_manifest = release_authoring / "native_authoring_job_manifest.json"
    batch_report = release_authoring / "native_authoring_batch_job_report.json"
    project_registry = release_authoring / "native_authoring_project_registry.json"
    project_package = release_authoring / "native_authoring_project_package.zip"
    private_key = release_signing / "native_authoring_project_registry_ed25519.pem"
    public_key = release_signing / "native_authoring_project_registry_ed25519.pub.pem"
    signature = release_signing / "native_authoring_project_registry.signature.b64"
    out = release_authoring / "native_authoring_ops_bundle.json"

    _write_json(
        workspace_summary,
        build_native_authoring_workspace_payload(generated_at="2026-04-19T09:00:00+00:00"),
    )

    command = [
        sys.executable,
        str(SCRIPT),
        "--workspace-summary",
        str(workspace_summary),
        "--solver-session-out",
        str(solver_session),
        "--solver-loadcomb-out",
        str(solver_loadcomb),
        "--job-manifest-out",
        str(job_manifest),
        "--batch-report-out",
        str(batch_report),
        "--snapshot-root",
        str(release_authoring / "snapshots"),
        "--project-registry-out",
        str(project_registry),
        "--project-package-out",
        str(project_package),
        "--private-key-out",
        str(private_key),
        "--public-key-out",
        str(public_key),
        "--signature-out",
        str(signature),
        "--out",
        str(out),
    ]

    proc_1 = subprocess.run(command, check=False, capture_output=True, text=True)
    assert proc_1.returncode == 0, proc_1.stderr
    bundle_payload_1 = json.loads(out.read_text(encoding="utf-8"))
    registry_payload_1 = json.loads(project_registry.read_text(encoding="utf-8"))

    proc_2 = subprocess.run(command, check=False, capture_output=True, text=True)
    assert proc_2.returncode == 0, proc_2.stderr
    bundle_payload_2 = json.loads(out.read_text(encoding="utf-8"))
    registry_payload_2 = json.loads(project_registry.read_text(encoding="utf-8"))

    assert bundle_payload_1["inputs"]["workspace_summary_source_mode"] == "loaded"
    assert bundle_payload_2["inputs"]["workspace_summary_source_mode"] == "loaded"
    assert bundle_payload_1["generated_at"] == "2026-04-19T09:00:00+00:00"
    assert bundle_payload_2["generated_at"] == "2026-04-19T09:00:00+00:00"
    assert bundle_payload_2["artifacts"]["solver_session_json"] == str(solver_session)
    assert bundle_payload_2["artifacts"]["solver_loadcomb_preview_mgt"] == str(solver_loadcomb)
    assert registry_payload_1["summary"]["package_sha256"] == registry_payload_2["summary"]["package_sha256"]
