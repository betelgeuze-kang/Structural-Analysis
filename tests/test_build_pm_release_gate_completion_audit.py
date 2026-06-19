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
        "summary": {
            "evidence_source": f"{area_id}_report.json",
            "generated_at": "2026-06-16T00:00:00+00:00",
            "support_bundle_export_archive_sha256": "volatile-sha",
        },
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
        "summary": {
            "source": f"{milestone_id}.json",
            "generated_at": "2026-06-16T00:00:00+00:00",
            "support_bundle_export_archive_sha256": "volatile-sha",
        },
        "artifacts": {f"{milestone_id}_report": f"{milestone_id}.json"},
    }


def _passing_milestones() -> list[dict[str, object]]:
    required: dict[str, set[str]] = {}
    for milestone_id, _, _, check_key in build_audit_module.MILESTONE_REQUIREMENTS:
        required.setdefault(milestone_id, set()).add(check_key)
    return [_milestone(milestone_id, {key: True for key in keys}) for milestone_id, keys in required.items()]


def _passing_release_tiers() -> dict[str, object]:
    return {
        "technical_paid_pilot_candidate": True,
        "paid_pilot_scope_guard_pass": True,
        "paid_pilot_scope_guard_report": "paid_pilot_scope_guard_report.json",
        "limited_commercial_full_gate_ready": True,
        "ga_enterprise_evidence_gate_pass": True,
        "ga_enterprise_readiness_report": "ga_enterprise_readiness_report.json",
        "ga_enterprise_signoff_intake_packet": "ga_enterprise_signoff_intake_packet.json",
        "ga_enterprise_blockers": [],
    }


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
            "summary_line": "PM release gate: LIMITED_MILESTONE_READY | release_areas=BLOCKED",
            "full_release_gate_ready": False,
            "release_area_gate_ready": False,
            "limited_commercial_milestone_ready": True,
            "limited_commercial_release_ready": False,
            "limited_commercial_ready": False,
            "paid_pilot_candidate": True,
            "recommended_scope": "Paid Pilot / constrained customer PoC only",
            "release_tiers": _passing_release_tiers(),
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
                    "owner": "release_ci_owner",
                    "closure_state": "external_owner_input_ready",
                    "evidence_state": "external_evidence_missing",
                    "next_action": "Attach 30 consecutive PR CI PASS run records.",
                },
                {
                    "blocker_id": "basic_ci::nightly_ci_30_consecutive_pass_evidence_missing",
                    "owner": "release_ci_owner",
                    "closure_state": "external_owner_input_ready",
                    "evidence_state": "external_evidence_missing",
                    "next_action": "Attach 30 consecutive nightly CI PASS run records.",
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
    assert payload["summary"]["release_tier_requirement_count"] == len(
        build_audit_module.RELEASE_TIER_REQUIREMENTS
    )
    assert payload["summary"]["release_tier_blocked_count"] == 0
    assert payload["summary"]["blocked_external_owner_input_ready_count"] == 1
    assert payload["summary"]["blocked_release_area_claim_boundary_missing_count"] == 0
    assert payload["summary"]["blocked_release_area_next_action_missing_count"] == 0
    assert payload["summary"]["limited_commercial_milestone_ready"] is True
    assert payload["summary"]["limited_commercial_release_ready"] is False
    assert payload["summary"]["limited_commercial_ready"] is False
    assert rows["release_area.basic_ci"]["status"] == "blocked_external_owner_input_ready"
    assert rows["release_area.basic_ci"]["closure_states"] == {
        "basic_ci::nightly_ci_30_consecutive_pass_evidence_missing": "external_owner_input_ready",
        "basic_ci::pr_ci_30_consecutive_pass_evidence_missing": "external_owner_input_ready",
    }
    assert rows["release_area.basic_ci"]["next_actions"] == [
        {
            "blocker_id": "basic_ci::pr_ci_30_consecutive_pass_evidence_missing",
            "owner": "release_ci_owner",
            "closure_state": "external_owner_input_ready",
            "evidence_state": "external_evidence_missing",
            "next_action": "Attach 30 consecutive PR CI PASS run records.",
        },
        {
            "blocker_id": "basic_ci::nightly_ci_30_consecutive_pass_evidence_missing",
            "owner": "release_ci_owner",
            "closure_state": "external_owner_input_ready",
            "evidence_state": "external_evidence_missing",
            "next_action": "Attach 30 consecutive nightly CI PASS run records.",
        },
    ]
    assert "basic_ci::pr_ci_30_consecutive_pass_evidence_missing: Attach 30 consecutive PR CI PASS" in rows[
        "release_area.basic_ci"
    ]["next_action"]
    assert rows["m1_residual_report_fixed"]["status"] == "pass"
    assert rows["release_tier.paid_pilot_scope_guard_pass"]["status"] == "pass"
    assert "constrained customer PoC" in rows["release_tier.paid_pilot_scope_guard_pass"]["claim_boundary"]
    assert rows["release_tier.ga_enterprise_evidence_gate_pass"]["status"] == "pass"
    assert rows["release_area.support"]["summary_snapshot"]["evidence_source"] == "support_report.json"
    assert "generated_at" not in rows["release_area.support"]["summary_snapshot"]
    assert "support_bundle_export_archive_sha256" not in rows["release_area.support"]["summary_snapshot"]
    assert "generated_at" not in rows["m5_support_bundle_export"]["summary_snapshot"]
    assert "support_bundle_export_archive_sha256" not in rows["m5_support_bundle_export"]["summary_snapshot"]
    assert payload["snapshot_policy"]["stable_summary_snapshot"] is True


def test_build_audit_passes_only_when_full_gate_and_rows_pass(tmp_path: Path) -> None:
    pm_report = _write_json(
        tmp_path / "pm_release_gate_report.json",
        {
            "summary_line": "PM release gate: LIMITED_READY | release_areas=READY",
            "full_release_gate_ready": True,
            "release_area_gate_ready": True,
            "limited_commercial_ready": True,
            "paid_pilot_candidate": True,
            "release_tiers": _passing_release_tiers(),
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


def test_build_audit_prefixes_nested_release_area_blockers(tmp_path: Path) -> None:
    release_areas = [
        _area(area_id)
        for area_id, _, _ in build_audit_module.RELEASE_AREA_REQUIREMENTS
        if area_id != "evidence_freshness"
    ]
    release_areas.append(
        _area(
            "evidence_freshness",
            ok=False,
            blockers=["p0_closure_status::source_commit_missing"],
        )
    )
    pm_report = _write_json(
        tmp_path / "pm_release_gate_report.json",
        {
            "summary_line": "PM release gate: LIMITED_READY | release_areas=BLOCKED",
            "full_release_gate_ready": False,
            "release_area_matrix": release_areas,
            "milestones": _passing_milestones(),
            "release_tiers": _passing_release_tiers(),
        },
    )
    closure_board = _write_json(
        tmp_path / "pm_release_blocker_closure_board.json",
        {
            "rows": [
                {
                    "blocker_id": "evidence_freshness::p0_closure_status::source_commit_missing",
                    "owner": "release_owner",
                    "closure_state": "local_remediation_ready",
                    "evidence_state": "release_evidence_metadata_missing",
                    "next_action": "Regenerate the release evidence freshness report.",
                }
            ]
        },
    )

    payload = build_audit_module.build_audit(pm_report=pm_report, closure_board=closure_board)
    rows = {row["requirement_id"]: row for row in payload["rows"]}
    freshness = rows["release_area.evidence_freshness"]

    assert freshness["status"] == "blocked_local_remediation_ready"
    assert freshness["blockers"] == ["evidence_freshness::p0_closure_status::source_commit_missing"]
    assert freshness["closure_states"] == {
        "evidence_freshness::p0_closure_status::source_commit_missing": "local_remediation_ready"
    }
    assert "Regenerate the release evidence freshness report" in freshness["next_action"]


def test_build_audit_surfaces_release_tier_boundaries(tmp_path: Path) -> None:
    release_tiers = {
        "technical_paid_pilot_candidate": True,
        "paid_pilot_scope_guard_pass": True,
        "paid_pilot_scope_guard_report": "paid_pilot_scope_guard_report.json",
        "limited_commercial_full_gate_ready": False,
        "ga_enterprise_evidence_gate_pass": False,
        "ga_enterprise_readiness_report": "ga_enterprise_readiness_report.json",
        "ga_enterprise_signoff_intake_packet": "ga_enterprise_signoff_intake_packet.json",
        "ga_enterprise_blockers": ["independent_vv_missing", "customer_sla_missing"],
        "ga_enterprise_note": "GA still requires independent V&V and customer SLA evidence.",
    }
    pm_report = _write_json(
        tmp_path / "pm_release_gate_report.json",
        {
            "summary_line": "PM release gate: LIMITED_READY | release_areas=BLOCKED",
            "full_release_gate_ready": False,
            "release_area_gate_ready": False,
            "release_area_blockers": ["security::license_status_not_configured"],
            "recommended_scope": "Limited milestone evidence is green; keep use constrained to paid pilot.",
            "release_tiers": release_tiers,
            "release_area_matrix": [
                _area(area_id) for area_id, _, _ in build_audit_module.RELEASE_AREA_REQUIREMENTS
            ],
            "milestones": _passing_milestones(),
        },
    )
    closure_board = _write_json(tmp_path / "pm_release_blocker_closure_board.json", {"rows": []})

    payload = build_audit_module.build_audit(pm_report=pm_report, closure_board=closure_board)
    rows = {row["requirement_id"]: row for row in payload["rows"]}

    assert payload["summary"]["release_tier_requirement_count"] == 4
    assert payload["summary"]["release_tier_pass_count"] == 2
    assert payload["summary"]["release_tier_blocked_count"] == 2
    assert payload["summary"]["blocked_release_tier_claim_boundary_missing_count"] == 0
    assert payload["summary"]["blocked_release_tier_next_action_missing_count"] == 0
    assert rows["release_tier.technical_paid_pilot_candidate"]["status"] == "pass"
    assert rows["release_tier.paid_pilot_scope_guard_pass"]["status"] == "pass"
    assert rows["release_tier.limited_commercial_full_gate_ready"]["status"] == "blocked"
    assert rows["release_tier.limited_commercial_full_gate_ready"]["blockers"] == [
        "security::license_status_not_configured"
    ]
    assert "release-area blockers remain open" in rows[
        "release_tier.limited_commercial_full_gate_ready"
    ]["claim_boundary"]
    assert "Close all release-area blockers" in rows[
        "release_tier.limited_commercial_full_gate_ready"
    ]["next_action"]
    assert rows["release_tier.ga_enterprise_evidence_gate_pass"]["status"] == "blocked"
    assert rows["release_tier.ga_enterprise_evidence_gate_pass"]["blockers"] == [
        "independent_vv_missing",
        "customer_sla_missing",
    ]
    assert "independent V&V" in rows["release_tier.ga_enterprise_evidence_gate_pass"]["claim_boundary"]
    assert "independent V&V" in rows["release_tier.ga_enterprise_evidence_gate_pass"]["next_action"]


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
    out_markdown = out_md.read_text(encoding="utf-8")
    assert "release_area.basic_ci" in out_markdown
    assert "Next Action" in out_markdown
