from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parent.parent / "scripts" / "build_pm_release_reproduction_command_audit.py"
)
SPEC = importlib.util.spec_from_file_location("build_pm_release_reproduction_command_audit", SCRIPT_PATH)
assert SPEC is not None
build_pm_release_reproduction_command_audit = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(build_pm_release_reproduction_command_audit)


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _write_text(path: Path, payload: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")
    return path


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    _write_text(repo / "scripts" / "ok.py", "#!/usr/bin/env python3\n")
    _write_text(repo / "scripts" / "external.py", "#!/usr/bin/env python3\n")
    _write_json(repo / "package.json", {"scripts": {"ai:preflight": "./scripts/ai-preflight.sh"}})
    (repo / "implementation" / "phase1" / "release_evidence" / "productization").mkdir(
        parents=True,
        exist_ok=True,
    )
    return repo


def _report_for_commands(tmp_path: Path, commands: list[object]) -> dict[str, object]:
    repo = _repo(tmp_path)
    artifact = _write_json(repo / "artifact.json", {"rows": [{"reproduction_commands": commands}]})
    return build_pm_release_reproduction_command_audit.build_report(
        input_paths=[artifact],
        package_json=repo / "package.json",
        repo_root=repo,
    )


def test_accepts_valid_python_npm_run_and_npm_audit_commands(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    artifact = _write_json(
        repo / "artifact.json",
        {
            "rows": [
                {
                    "reproduction_commands": [
                        "python3 scripts/ok.py --out implementation/phase1/release_evidence/productization/out.json",
                        "npm run ai:preflight",
                        "npm audit --audit-level high",
                    ]
                }
            ]
        },
    )

    payload = build_pm_release_reproduction_command_audit.build_report(
        input_paths=[artifact],
        package_json=repo / "package.json",
        repo_root=repo,
    )

    assert payload["contract_pass"] is True
    assert payload["summary"]["command_count"] == 3
    assert payload["summary"]["violation_count"] == 0
    assert payload["blockers"] == []


def test_rejects_shell_composition(tmp_path: Path) -> None:
    payload = _report_for_commands(tmp_path, ["python3 scripts/ok.py && python3 scripts/ok.py"])

    assert payload["contract_pass"] is False
    assert "command_shell_composition" in payload["blockers"]


def test_rejects_missing_script(tmp_path: Path) -> None:
    payload = _report_for_commands(tmp_path, ["python3 scripts/missing.py"])

    assert payload["contract_pass"] is False
    assert "command_script_missing" in payload["blockers"]


def test_rejects_missing_npm_target(tmp_path: Path) -> None:
    payload = _report_for_commands(tmp_path, ["npm run missing"])

    assert payload["contract_pass"] is False
    assert "command_npm_script_missing" in payload["blockers"]


def test_rejects_escaping_output_path(tmp_path: Path) -> None:
    payload = _report_for_commands(tmp_path, ["python3 scripts/ok.py --out ../outside.json"])

    assert payload["contract_pass"] is False
    assert "command_output_path_escapes_repo" in payload["blockers"]


def test_rejects_non_string_command(tmp_path: Path) -> None:
    payload = _report_for_commands(tmp_path, ["python3 scripts/ok.py", 17])

    assert payload["contract_pass"] is False
    assert "command_non_string" in payload["blockers"]
    assert payload["summary"]["command_count"] == 2


def test_accepts_current_pm_release_command_artifacts() -> None:
    payload = build_pm_release_reproduction_command_audit.build_report()

    assert payload["contract_pass"] is True
    assert payload["reason_code"] == "PASS"
    assert payload["summary"]["artifact_count"] == 7
    assert payload["summary"]["artifact_pass_count"] == 7
    assert payload["summary"]["command_count"] > 0
    assert payload["summary"]["external_owner_command_count"] >= 1
    assert payload["blockers"] == []


def test_cli_writes_json_and_markdown_and_fail_blocked(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    artifact = _write_json(repo / "artifact.json", {"validation_commands": ["python3 scripts/ok.py"]})
    out = tmp_path / "audit.json"
    out_md = tmp_path / "audit.md"

    assert build_pm_release_reproduction_command_audit.main(
        [
            "--repo-root",
            str(repo),
            "--package-json",
            str(repo / "package.json"),
            "--input",
            str(artifact),
            "--out",
            str(out),
            "--out-md",
            str(out_md),
        ]
    ) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["contract_pass"] is True
    assert "# PM Release Reproduction Command Audit" in out_md.read_text(encoding="utf-8")

    blocked = _write_json(repo / "blocked.json", {"validation_commands": ["python3 scripts/missing.py"]})
    assert build_pm_release_reproduction_command_audit.main(
        [
            "--repo-root",
            str(repo),
            "--package-json",
            str(repo / "package.json"),
            "--input",
            str(blocked),
            "--out",
            str(tmp_path / "blocked.json"),
            "--out-md",
            str(tmp_path / "blocked.md"),
            "--fail-blocked",
        ]
    ) == 1
