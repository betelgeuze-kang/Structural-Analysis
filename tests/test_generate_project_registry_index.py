from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


SCRIPT = Path("implementation/phase1/generate_project_registry_index.py")


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_generate_project_registry_index_cli(tmp_path: Path) -> None:
    registry = tmp_path / "project_registry.json"
    _write_json(
        registry,
        {
            "generated_at": "2026-04-19T04:00:00+00:00",
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
    _write_json(
        registry_a,
        {
            "generated_at": "2026-04-19T04:00:00+00:00",
            "contract_pass": True,
            "reason_code": "PASS",
            "summary": {
                "project_id": "tower-a",
                "project_name": "Tower A",
                "artifact_count": 2,
                "approval_count": 2,
                "approved_count": 2,
                "audit_event_count": 3,
                "package_sha256": "sha-a",
                "registry_body_sha256": "body-a",
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
            "generated_at": "2026-04-19T04:30:00+00:00",
            "contract_pass": True,
            "reason_code": "PASS",
            "summary": {
                "project_id": "bridge-b",
                "project_name": "Bridge B",
                "artifact_count": 1,
                "approval_count": 1,
                "approved_count": 1,
                "audit_event_count": 1,
                "package_sha256": "sha-b",
                "registry_body_sha256": "body-b",
            },
            "checks": {
                "signature_verified_pass": True,
                "package_reproducible_pass": True,
            },
        },
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
