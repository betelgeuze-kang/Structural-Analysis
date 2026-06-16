from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "build_frontend_dependency_audit_report.py"
SPEC = importlib.util.spec_from_file_location("build_frontend_dependency_audit_report", SCRIPT_PATH)
assert SPEC is not None
build_frontend_dependency_audit_report = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(build_frontend_dependency_audit_report)


def _write(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_frontend_dependency_audit_blocks_high_vulnerability(tmp_path: Path) -> None:
    package_json = _write(tmp_path / "package.json", {"devDependencies": {"vite": "8.0.8"}})
    package_lock = _write(tmp_path / "package-lock.json", {"packages": {}})
    audit_payload = {
        "vulnerabilities": {
            "vite": {
                "name": "vite",
                "severity": "high",
                "isDirect": True,
                "range": "8.0.0 - 8.0.15",
                "fixAvailable": {"name": "vite", "version": "8.0.16", "isSemVerMajor": False},
                "via": [
                    {
                        "title": "vite: server.fs.deny bypass",
                        "severity": "high",
                        "url": "https://github.com/advisories/GHSA-fx2h-pf6j-xcff",
                        "range": ">=8.0.0 <=8.0.15",
                    }
                ],
            }
        },
        "metadata": {"vulnerabilities": {"info": 0, "low": 0, "moderate": 0, "high": 1, "critical": 0}},
    }

    payload = build_frontend_dependency_audit_report.build_report(
        audit_payload=audit_payload,
        audit_exit_code=1,
        audit_stdout=json.dumps(audit_payload),
        audit_stderr="",
        package_json=package_json,
        package_lock=package_lock,
    )

    assert payload["contract_pass"] is False
    assert "frontend_dependency_high_or_critical_vulnerabilities_present" in payload["blockers"]
    assert payload["summary"]["high_vulnerability_count"] == 1
    assert payload["vulnerabilities"][0]["fix_available"]["version"] == "8.0.16"


def test_frontend_dependency_audit_passes_zero_vulnerabilities(tmp_path: Path) -> None:
    package_json = _write(tmp_path / "package.json", {"devDependencies": {"vite": "8.0.16"}})
    package_lock = _write(tmp_path / "package-lock.json", {"packages": {}})
    audit_payload = {
        "metadata": {
            "vulnerabilities": {
                "info": 0,
                "low": 0,
                "moderate": 0,
                "high": 0,
                "critical": 0,
                "total": 0,
            }
        }
    }

    payload = build_frontend_dependency_audit_report.build_report(
        audit_payload=audit_payload,
        audit_exit_code=0,
        audit_stdout=json.dumps(audit_payload),
        audit_stderr="",
        package_json=package_json,
        package_lock=package_lock,
    )

    assert payload["contract_pass"] is True
    assert payload["blockers"] == []
    assert payload["checks"]["dependency_vulnerability_total_zero_pass"] is True
