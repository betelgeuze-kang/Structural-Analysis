from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from implementation.phase1.project_registry_service import build_project_registry
from implementation.phase1.release_registry_integrity import TECHNICAL_PRODUCER_KEY_ENV


SCRIPT = Path("implementation/phase1/generate_project_registry_index.py")


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _build_signed_registry(
    tmp_path: Path,
    *,
    registry: Path,
    project_id: str,
    project_name: str,
    generated_at: str,
) -> None:
    artifact = registry.parent / f"{project_id}.artifact.json"
    _write_json(artifact, {"project_id": project_id})
    private_key = tmp_path / "signing" / "private.pem"
    public_key = tmp_path / "signing" / "public.pem"
    package_root = tmp_path / "packages" / project_id
    build_project_registry(
        project_id=project_id,
        project_name=project_name,
        artifact_paths=[artifact],
        artifact_root=tmp_path,
        audit_payload=[{"artifact_label": artifact.name, "status": "completed"}],
        approval_payload=[{"status": "approved"}],
        private_key_out=private_key,
        public_key_out=public_key,
        signature_out=package_root / "signature.b64",
        package_out=package_root / "package.zip",
        out=registry,
        generated_at=generated_at,
    )
    os.environ[TECHNICAL_PRODUCER_KEY_ENV] = hashlib.sha256(public_key.read_bytes()).hexdigest()


def test_generate_project_registry_index_cli(tmp_path: Path) -> None:
    registry = tmp_path / "project_registry.json"
    _build_signed_registry(
        tmp_path,
        registry=registry,
        project_id="tower-a",
        project_name="Tower A",
        generated_at="2026-04-19T04:00:00+00:00",
    )
    out = tmp_path / "project_registry_index.json"
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--registry-paths", str(registry), "--out", str(out)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["summary"]["project_count"] == 1
    assert payload["rows"][0]["project_id"] == "tower-a"


def test_generate_project_registry_index_cli_scans_directories_and_writes_workspace(tmp_path: Path) -> None:
    release_root = tmp_path / "release"
    registry_a = release_root / "tower-a" / "project_registry.json"
    registry_b = release_root / "bridge-b" / "release_registry.json"
    _build_signed_registry(
        tmp_path,
        registry=registry_a,
        project_id="tower-a",
        project_name="Tower A",
        generated_at="2026-04-19T04:00:00+00:00",
    )
    _build_signed_registry(
        tmp_path,
        registry=registry_b,
        project_id="bridge-b",
        project_name="Bridge B",
        generated_at="2026-04-19T04:30:00+00:00",
    )

    out = release_root / "project_registry_index.json"
    workspace_out = release_root / "project_registry_portfolio_workspace.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--registry-dirs",
            str(release_root),
            "--registry-globs",
            str(release_root / "**" / "project_registry.json"),
            "--registry-paths",
            "",
            "--out",
            str(out),
            "--workspace-out",
            str(workspace_out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    workspace_payload = json.loads(workspace_out.read_text(encoding="utf-8"))
    assert payload["summary"]["project_count"] == 2
    assert payload["summary"]["unique_project_count"] == 2
    assert payload["scan"]["summary"]["directory_input_count"] == 1
    assert payload["scan"]["summary"]["duplicate_registry_count"] == 1
    assert workspace_payload["run_id"] == "phase1-project-registry-portfolio-workspace"
