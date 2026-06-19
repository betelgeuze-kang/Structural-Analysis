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
    for script_name in [
        "build_pm_release_blocker_action_register.py",
        "build_pm_release_blocker_closure_board.py",
        "build_pm_release_gate_completion_audit.py",
        "build_pm_release_gate_reviewer_handoff.py",
        "build_pm_owner_evidence_request_packet.py",
        "build_mgt_g1_direct_residual_terminal_gate_report.py",
        "build_mgt_g1_shell_material_budgeted_continuation_status.py",
        "report_commercial_gap_ledger_status.py",
        "report_gap_closure_status.py",
        "build_support_bundle.py",
        "build_paid_pilot_scope_guard_report.py",
        "report_pm_release_gate.py",
        "build_pm_release_reproduction_command_audit.py",
    ]:
        _write_text(repo / "scripts" / script_name, "#!/usr/bin/env python3\n")
    _write_json(repo / "package.json", {"scripts": {"ai:preflight": "./scripts/ai-preflight.sh"}})
    (repo / "implementation" / "phase1" / "release_evidence" / "productization").mkdir(
        parents=True,
        exist_ok=True,
    )
    return repo


def _seed_package_outputs(repo: Path, *, skip_labels: set[str] | None = None) -> None:
    skip = skip_labels or set()
    for label, path, _producer in build_pm_release_reproduction_command_audit._package_regeneration_output_specs():
        if label in skip:
            continue
        target = repo / path
        if target.suffix == ".zip":
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"zip placeholder")
        else:
            _write_text(target, "{}\n")


def _report_for_commands(tmp_path: Path, commands: list[object]) -> dict[str, object]:
    repo = _repo(tmp_path)
    artifact = _write_json(repo / "artifact.json", {"rows": [{"reproduction_commands": commands}]})
    return build_pm_release_reproduction_command_audit.build_report(
        input_paths=[artifact],
        package_json=repo / "package.json",
        repo_root=repo,
        include_package_recipe=False,
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
        include_package_recipe=False,
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
    assert payload["summary"]["package_regeneration_command_count"] == 13
    assert payload["summary"]["package_regeneration_violation_count"] == 0
    assert payload["summary"]["external_owner_command_count"] >= 1
    assert any(
        "build_pm_release_blocker_closure_board.py" in command
        for command in payload["package_regeneration_commands"]
    )
    assert any(
        "build_pm_release_gate_completion_audit.py" in command
        for command in payload["package_regeneration_commands"]
    )
    assert any(
        "build_pm_release_gate_reviewer_handoff.py" in command
        for command in payload["package_regeneration_commands"]
    )
    assert any(
        "build_pm_owner_evidence_request_packet.py" in command
        for command in payload["package_regeneration_commands"]
    )
    assert any(
        "build_paid_pilot_scope_guard_report.py" in command
        for command in payload["package_regeneration_commands"]
    )
    assert any(
        "build_mgt_g1_direct_residual_terminal_gate_report.py" in command
        for command in payload["package_regeneration_commands"]
    )
    assert any(
        "build_mgt_g1_shell_material_budgeted_continuation_status.py" in command
        for command in payload["package_regeneration_commands"]
    )
    assert any(
        "report_commercial_gap_ledger_status.py" in command
        for command in payload["package_regeneration_commands"]
    )
    assert any(
        "report_gap_closure_status.py" in command
        for command in payload["package_regeneration_commands"]
    )
    assert payload["summary"]["package_regeneration_expected_output_count"] == 23
    assert payload["summary"]["package_regeneration_expected_output_pass_count"] == 23
    assert payload["summary"]["package_regeneration_output_violation_count"] == 0
    assert any(
        row["label"] == "pm_failure_bundle_coverage" and row["contract_pass"] is True
        for row in payload["package_regeneration_output_rows"]
    )
    assert any(
        row["label"] == "commercial_gap_ledger_status" and row["contract_pass"] is True
        for row in payload["package_regeneration_output_rows"]
    )
    assert any(
        row["label"] == "g1_direct_residual_terminal_gate_report"
        and row["contract_pass"] is True
        for row in payload["package_regeneration_output_rows"]
    )
    assert any(
        row["label"] == "g1_shell_material_budgeted_continuation_status"
        and row["contract_pass"] is True
        for row in payload["package_regeneration_output_rows"]
    )
    assert any(
        row["label"] == "gap_closure_status" and row["contract_pass"] is True
        for row in payload["package_regeneration_output_rows"]
    )
    assert payload["blockers"] == []


def test_package_recipe_tracks_support_failure_bundle_coverage_output(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _seed_package_outputs(repo)

    payload = build_pm_release_reproduction_command_audit.build_report(
        input_paths=[],
        package_json=repo / "package.json",
        repo_root=repo,
        include_package_recipe=True,
    )

    assert payload["contract_pass"] is True
    coverage_rows = [
        row
        for row in payload["package_regeneration_output_rows"]
        if row["label"] == "pm_failure_bundle_coverage"
    ]
    assert len(coverage_rows) == 1
    assert coverage_rows[0]["path"].endswith("pm_failure_bundle_coverage.json")
    assert coverage_rows[0]["producer"] == "build_support_bundle.py"
    assert coverage_rows[0]["exists"] is True
    assert coverage_rows[0]["is_file"] is True


def test_package_recipe_blocks_missing_support_failure_bundle_coverage_output(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _seed_package_outputs(repo, skip_labels={"pm_failure_bundle_coverage"})

    payload = build_pm_release_reproduction_command_audit.build_report(
        input_paths=[],
        package_json=repo / "package.json",
        repo_root=repo,
        include_package_recipe=True,
    )

    assert payload["contract_pass"] is False
    assert "pm_failure_bundle_coverage:package_output_missing" in payload["blockers"]
    coverage_rows = [
        row
        for row in payload["package_regeneration_output_rows"]
        if row["label"] == "pm_failure_bundle_coverage"
    ]
    assert coverage_rows == [
        {
            "label": "pm_failure_bundle_coverage",
            "path": "implementation/phase1/release/support_bundle/pm_failure_bundle_coverage.json",
            "producer": "build_support_bundle.py",
            "exists": False,
            "is_file": False,
            "contract_pass": False,
            "blockers": ["package_output_missing"],
        }
    ]


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
            "--no-package-recipe",
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
