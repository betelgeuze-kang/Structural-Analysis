from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "build_pm_release_gate_completion_audit.py"
SPEC = importlib.util.spec_from_file_location("build_pm_release_gate_completion_audit", SCRIPT_PATH)
assert SPEC is not None
build_audit_module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(build_audit_module)


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _area(area_id: str, *, ok: bool = True, blockers: list[str] | None = None) -> dict[str, object]:
    return {
        "area": area_id,
        "title": area_id.replace("_", " ").title(),
        "ok": ok,
        "blockers": blockers or [],
        "checks": {"explicit_check": ok},
        "summary": {"evidence_source": f"{area_id}_report.json"},
        "artifacts": {f"{area_id}_report": f"{area_id}_report.json"},
        "claim_boundary": f"{area_id} claim boundary",
    }


def _milestone(milestone_id: str, checks: dict[str, bool]) -> dict[str, object]:
    return {
        "milestone": milestone_id,
        "title": milestone_id,
        "ok": all(checks.values()),
        "blockers": [],
        "checks": checks,
        "summary": {"source": f"{milestone_id}.json"},
        "artifacts": {f"{milestone_id}_report": f"{milestone_id}.json"},
    }


def _passing_milestones() -> list[dict[str, object]]:
    required: dict[str, set[str]] = {}
    for milestone_id, _, _, check_key in build_audit_module.MILESTONE_REQUIREMENTS:
        required.setdefault(milestone_id, set()).add(check_key)
    return [_milestone(milestone_id, {key: True for key in keys}) for milestone_id, keys in required.items()]


def test_build_audit_expands_release_areas_and_milestone_requirements(tmp_path: Path) -> None:
    release_areas = [
        _area(area_id)
        for area_id, _, _ in build_audit_module.RELEASE_AREA_REQUIREMENTS
        if area_id != "basic_ci"
    ]
    release_areas.append(
        _area(
            "basic_ci",
            ok=False,
            blockers=[
                "pr_ci_30_consecutive_pass_evidence_missing",
                "nightly_ci_30_consecutive_pass_evidence_missing",
            ],
        )
    )
    pm_report = _write_json(
        tmp_path / "pm_release_gate_report.json",
        {
            "summary_line": "PM release gate: LIMITED_READY | release_areas=BLOCKED",
            "full_release_gate_ready": False,
            "release_area_gate_ready": False,
            "limited_commercial_ready": True,
            "paid_pilot_candidate": True,
            "release_area_matrix": release_areas,
            "milestones": _passing_milestones(),
        },
    )
    closure_board = _write_json(
        tmp_path / "pm_release_blocker_closure_board.json",
        {
            "contract_pass": False,
            "rows": [
                {
                    "blocker_id": "basic_ci::pr_ci_30_consecutive_pass_evidence_missing",
                    "closure_state": "external_owner_input_ready",
                },
                {
                    "blocker_id": "basic_ci::nightly_ci_30_consecutive_pass_evidence_missing",
                    "closure_state": "external_owner_input_ready",
                },
            ],
        },
    )

    payload = build_audit_module.build_audit(pm_report=pm_report, closure_board=closure_board)
    rows = {row["requirement_id"]: row for row in payload["rows"]}

    assert payload["contract_pass"] is False
    assert payload["reason_code"] == "ERR_PM_REQUIREMENTS_BLOCKED"
    assert payload["summary"]["release_area_requirement_count"] == len(
        build_audit_module.RELEASE_AREA_REQUIREMENTS
    )
    assert payload["summary"]["release_area_blocked_count"] == 1
    assert payload["summary"]["milestone_subrequirement_blocked_count"] == 0
    assert payload["summary"]["blocked_external_owner_input_ready_count"] == 1
    assert rows["release_area.basic_ci"]["status"] == "blocked_external_owner_input_ready"
    assert rows["release_area.basic_ci"]["closure_states"] == {
        "basic_ci::nightly_ci_30_consecutive_pass_evidence_missing": "external_owner_input_ready",
        "basic_ci::pr_ci_30_consecutive_pass_evidence_missing": "external_owner_input_ready",
    }
    assert rows["m1_residual_report_fixed"]["status"] == "pass"


def test_build_audit_passes_only_when_full_gate_and_rows_pass(tmp_path: Path) -> None:
    pm_report = _write_json(
        tmp_path / "pm_release_gate_report.json",
        {
            "summary_line": "PM release gate: LIMITED_READY | release_areas=READY",
            "full_release_gate_ready": True,
            "release_area_gate_ready": True,
            "limited_commercial_ready": True,
            "paid_pilot_candidate": True,
            "release_area_matrix": [
                _area(area_id) for area_id, _, _ in build_audit_module.RELEASE_AREA_REQUIREMENTS
            ],
            "milestones": _passing_milestones(),
        },
    )
    closure_board = _write_json(tmp_path / "pm_release_blocker_closure_board.json", {"rows": []})

    payload = build_audit_module.build_audit(pm_report=pm_report, closure_board=closure_board)

    assert payload["contract_pass"] is True
    assert payload["reason_code"] == "PASS"
    assert payload["summary"]["blocked_requirement_count"] == 0


def test_cli_writes_json_and_markdown(tmp_path: Path, capsys) -> None:
    pm_report = _write_json(
        tmp_path / "pm_release_gate_report.json",
        {
            "summary_line": "PM release gate: BLOCKED",
            "full_release_gate_ready": False,
            "release_area_matrix": [_area(area_id) for area_id, _, _ in build_audit_module.RELEASE_AREA_REQUIREMENTS],
            "milestones": _passing_milestones(),
        },
    )
    closure_board = _write_json(tmp_path / "pm_release_blocker_closure_board.json", {"rows": []})
    out = tmp_path / "audit.json"
    out_md = tmp_path / "audit.md"

    exit_code = build_audit_module.main(
        [
            "--pm-report",
            str(pm_report),
            "--closure-board",
            str(closure_board),
            "--out",
            str(out),
            "--out-md",
            str(out_md),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "PM Release Gate Completion Audit" in captured.out
    assert json.loads(out.read_text(encoding="utf-8"))["summary"]["explicit_requirement_count"] > 0
    assert "release_area.basic_ci" in out_md.read_text(encoding="utf-8")
