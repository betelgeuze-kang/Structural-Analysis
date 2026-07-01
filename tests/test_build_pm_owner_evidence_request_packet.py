from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "build_pm_owner_evidence_request_packet.py"
SPEC = importlib.util.spec_from_file_location("build_pm_owner_evidence_request_packet", SCRIPT_PATH)
assert SPEC is not None
build_packet_module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(build_packet_module)


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _row(
    blocker_id: str,
    *,
    owner: str = "release_ci_owner",
    owner_action: str = "Collect evidence.",
    intake_path: str = "implementation/phase1/release_evidence/productization/ci_streak_intake_packet.json",
) -> dict:
    return {
        "blocker_id": blocker_id,
        "owner": owner,
        "scope": "release_area",
        "title": "Basic CI",
        "owner_action": owner_action,
        "next_action": owner_action,
        "acceptance_criteria": ["`ci_streak_intake_packet.json.contract_pass == true`"],
        "reproduction_commands": ["python3 scripts/build_ci_streak_intake_packet.py"],
        "verification_commands": ["python3 scripts/build_ci_streak_intake_packet.py --fail-blocked"],
        "handoff_ready": bool(owner_action),
        "handoff_state": "external_owner_input_ready",
        "handoff": {"expected_intake_artifact": "ci_streak_intake_packet"},
        "evidence_status": {"state": "missing_tracked_ci_streak_evidence"},
        "evidence_artifacts": {
            "ci_streak_intake_packet": intake_path
        },
        "external_input_required": True,
        "owner_input_required": True,
        "claim_boundary": "Tracked CI evidence is required.",
    }


def test_build_packet_groups_ci_blockers_by_owner_and_dedupes_commands(tmp_path: Path) -> None:
    intake = _write_json(
        tmp_path / "ci_streak_intake_packet.json",
        {
            "schema_version": "ci-streak-intake-packet.v1",
            "contract_pass": False,
            "reason_code": "ERR_CI_STREAK_SOURCE_EVIDENCE_INCOMPLETE",
            "current_blockers": ["pr:pr_ci_30_consecutive_pass_evidence_missing"],
            "summary": {"lane_count": 1, "lane_pass_count": 0, "threshold": 30},
            "lane_rows": [
                {
                    "lane": "pr",
                    "threshold": 30,
                    "threshold_pass": False,
                    "consecutive_pass_count": 0,
                    "missing_consecutive_pass_count": 30,
                    "github_actions_workflow_registered": True,
                    "github_actions_workflow_state": "active",
                    "local_required_trigger_present": True,
                    "local_workflow_trigger_events": ["pull_request", "push"],
                    "streak_source": "no_pull_request_run_source",
                    "blockers": ["pr_ci_30_consecutive_pass_evidence_missing"],
                }
            ],
            "claim_boundary": "tracked CI only",
        },
    )
    action_register = _write_json(
        tmp_path / "pm_release_blocker_action_register.json",
        {
            "pm_summary_line": "PM release gate: LIMITED_READY | release_areas=BLOCKED",
            "summary": {
                "open_blocker_count": 2,
                "release_area_gate_ready": False,
                "full_release_gate_ready": False,
                "limited_commercial_milestone_ready": True,
                "limited_commercial_release_ready": False,
                "limited_commercial_ready": False,
                "paid_pilot_candidate": True,
            },
            "rows": [
                _row("basic_ci::pr_ci_30_consecutive_pass_evidence_missing", intake_path=str(intake)),
                _row("basic_ci::nightly_ci_30_consecutive_pass_evidence_missing", intake_path=str(intake)),
            ],
        },
    )

    payload = build_packet_module.build_packet(action_register=action_register)
    packet = payload["owner_packets"][0]

    assert payload["contract_pass"] is True
    assert payload["reason_code"] == "PASS"
    assert payload["summary"]["owner_packet_count"] == 1
    assert payload["summary"]["open_blocker_count"] == 2
    assert payload["summary"]["handoff_contract_pass"] is True
    assert payload["summary"]["evidence_closure_pass"] is False
    assert payload["summary"]["expected_intake_count"] == 1
    assert payload["summary"]["expected_intake_contract_pass_count"] == 0
    assert payload["summary"]["expected_intake_open_blocker_count"] == 1
    assert payload["summary"]["expected_intake_lane_request_count"] == 1
    assert payload["summary"]["limited_commercial_milestone_ready"] is True
    assert payload["summary"]["limited_commercial_release_ready"] is False
    assert payload["summary"]["limited_commercial_ready"] is False
    assert packet["owner"] == "release_ci_owner"
    assert packet["blocker_count"] == 2
    assert packet["blocker_ids"] == [
        "basic_ci::pr_ci_30_consecutive_pass_evidence_missing",
        "basic_ci::nightly_ci_30_consecutive_pass_evidence_missing",
    ]
    assert packet["reproduction_commands"] == ["python3 scripts/build_ci_streak_intake_packet.py"]
    assert packet["expected_intake_paths"] == [str(intake)]
    assert packet["expected_intake_details"][0]["schema_version"] == "ci-streak-intake-packet.v1"
    assert packet["intake_current_blockers"] == ["pr:pr_ci_30_consecutive_pass_evidence_missing"]
    assert packet["intake_lane_request_rows"][0]["lane"] == "pr"
    assert packet["intake_lane_request_rows"][0]["local_workflow_trigger_events"] == ["pull_request", "push"]
    markdown = build_packet_module._markdown(payload)
    assert "## Intake Details" in markdown
    assert "| `pr` | 0/30 | 30 | `no_pull_request_run_source` |" in markdown
    assert "## Owner Commands" in markdown
    assert "`python3 scripts/build_ci_streak_intake_packet.py --fail-blocked`" in markdown
    assert "does not create or replace tracked CI streaks" in payload["claim_boundary"]


def test_build_packet_surfaces_intake_field_requests_without_current_values(tmp_path: Path) -> None:
    intake = _write_json(
        tmp_path / "license_status_intake_packet.json",
        {
            "schema_version": "license-status-intake-packet.v1",
            "contract_pass": False,
            "reason_code": "ERR_LICENSE_STATUS_NOT_CLOSED",
            "current_blockers": ["license_id_missing"],
            "summary": {"field_count": 1, "field_pass_count": 0, "closure_contract_pass": False},
            "field_rows": [
                {
                    "field": "license_id",
                    "required_value": "non-placeholder license or approval identifier",
                    "template_value": "LICENSE-ID",
                    "current_value": "SENSITIVE-LICENSE-ID",
                    "owner_note": "Template values such as LICENSE-ID are rejected.",
                    "closure_check": "license_id_present_pass",
                    "closure_check_pass": False,
                }
            ],
        },
    )
    row = _row(
        "security::license_status_not_configured",
        owner="product_legal_owner",
        intake_path=str(intake),
    )
    row["handoff"] = {"expected_intake_artifact": "license_status_intake_packet"}
    row["evidence_artifacts"] = {"license_status_intake_packet": str(intake)}
    action_register = _write_json(
        tmp_path / "pm_release_blocker_action_register.json",
        {
            "pm_summary_line": "PM release gate: LIMITED_READY | release_areas=BLOCKED",
            "summary": {"open_blocker_count": 1},
            "rows": [row],
        },
    )

    payload = build_packet_module.build_packet(action_register=action_register)
    packet = payload["owner_packets"][0]
    field_row = packet["intake_field_request_rows"][0]

    assert packet["owner"] == "product_legal_owner"
    assert payload["summary"]["expected_intake_field_request_count"] == 1
    assert packet["intake_current_blockers"] == ["license_id_missing"]
    assert field_row["field"] == "license_id"
    assert field_row["check"] == "license_id_present_pass"
    assert "current_value" not in field_row
    assert "SENSITIVE-LICENSE-ID" not in json.dumps(packet)
    markdown = build_packet_module._markdown(payload)
    assert "| `license_id` | non-placeholder license or approval identifier | `license_id_present_pass` |" in markdown
    assert "SENSITIVE-LICENSE-ID" not in markdown


def test_build_packet_emits_closed_release_owner_packet_when_no_blockers(tmp_path: Path) -> None:
    action_register = _write_json(
        tmp_path / "pm_release_blocker_action_register.json",
        {
            "pm_summary_line": "PM release gate: READY",
            "summary": {"open_blocker_count": 0},
            "rows": [],
        },
    )

    payload = build_packet_module.build_packet(action_register=action_register)

    assert payload["contract_pass"] is True
    assert payload["summary"]["open_blocker_count"] == 0
    assert payload["summary"]["handoff_contract_pass"] is True
    assert payload["summary"]["evidence_closure_pass"] is True
    assert payload["summary"]["expected_intake_count"] == 0
    assert payload["summary"]["release_tier_request_count"] == 0
    assert payload["owner_packets"][0]["owner"] == "release_owner"
    assert payload["owner_packets"][0]["blocker_ids"] == []


def test_build_packet_maps_open_blockers_to_blocked_release_tiers(tmp_path: Path) -> None:
    action_register = _write_json(
        tmp_path / "pm_release_blocker_action_register.json",
        {
            "pm_summary_line": "PM release gate: LIMITED_MILESTONE_READY",
            "summary": {"open_blocker_count": 1},
            "rows": [_row("basic_ci::pr_ci_30_consecutive_pass_evidence_missing")],
        },
    )
    reviewer_handoff = _write_json(
        tmp_path / "pm_release_gate_reviewer_handoff.json",
        {
            "release_tier_rows": [
                {
                    "requirement_id": "release_tier.technical_paid_pilot_candidate",
                    "status": "pass",
                    "blockers": [],
                },
                {
                    "requirement_id": "release_tier.limited_commercial_full_gate_ready",
                    "status": "blocked",
                    "blockers": ["basic_ci::pr_ci_30_consecutive_pass_evidence_missing"],
                    "next_action": "Close release-area blockers.",
                    "claim_boundary": "Limited Commercial cannot be promoted while blockers remain.",
                },
                {
                    "requirement_id": "release_tier.ga_enterprise_evidence_gate_pass",
                    "status": "blocked",
                    "blockers": [
                        "independent_vv_missing",
                        "basic_ci::pr_ci_30_consecutive_pass_evidence_missing",
                    ],
                    "next_action": "Attach GA signoffs and close release-area blockers.",
                    "claim_boundary": "GA still requires independent V&V and release-area closure.",
                },
            ]
        },
    )

    payload = build_packet_module.build_packet(
        action_register=action_register,
        reviewer_handoff=reviewer_handoff,
    )
    packet = payload["owner_packets"][0]
    request_row = packet["request_rows"][0]

    assert payload["summary"]["open_blocker_with_release_tier_impact_count"] == 1
    assert payload["summary"]["blocked_release_tier_impact_count"] == 2
    assert request_row["blocked_release_tiers"] == [
        "release_tier.limited_commercial_full_gate_ready",
        "release_tier.ga_enterprise_evidence_gate_pass",
    ]
    assert packet["blocked_release_tiers"] == request_row["blocked_release_tiers"]
    markdown = build_packet_module._markdown(payload)
    assert "Release Tiers" in markdown
    assert "`release_tier.limited_commercial_full_gate_ready`" in markdown


def test_build_packet_maps_milestone_blockers_to_technical_paid_pilot_tier(tmp_path: Path) -> None:
    row = _row(
        "M5::pm_blocker_closure_board_count_mismatch",
        owner="release_owner",
        owner_action="Regenerate PM release evidence.",
        intake_path="",
    )
    row["scope"] = "milestone"
    row["title"] = "Commercial Packaging"
    row["handoff"] = {}
    row["evidence_artifacts"] = {}
    row["external_input_required"] = False
    row["owner_input_required"] = False
    action_register = _write_json(
        tmp_path / "pm_release_blocker_action_register.json",
        {
            "pm_summary_line": "PM release gate: BLOCKED",
            "summary": {"open_blocker_count": 1},
            "rows": [row],
        },
    )
    reviewer_handoff = _write_json(
        tmp_path / "pm_release_gate_reviewer_handoff.json",
        {
            "release_tier_rows": [
                {
                    "requirement_id": "release_tier.technical_paid_pilot_candidate",
                    "status": "blocked",
                    "blockers": ["technical_paid_pilot_candidate_false"],
                    "next_action": "Regenerate the PM release gate after milestone evidence changes.",
                    "claim_boundary": "Technical paid pilot candidate depends on milestone evidence.",
                }
            ]
        },
    )

    payload = build_packet_module.build_packet(
        action_register=action_register,
        reviewer_handoff=reviewer_handoff,
    )
    request_row = payload["owner_packets"][0]["request_rows"][0]

    assert payload["summary"]["release_tier_impact_contract_pass"] is True
    assert payload["summary"]["missing_release_tier_impact_count"] == 0
    assert request_row["blocked_release_tiers"] == [
        "release_tier.technical_paid_pilot_candidate"
    ]


def test_build_packet_blocks_when_reviewer_handoff_omits_release_tier_impact(tmp_path: Path) -> None:
    action_register = _write_json(
        tmp_path / "pm_release_blocker_action_register.json",
        {
            "pm_summary_line": "PM release gate: LIMITED_MILESTONE_READY",
            "summary": {"open_blocker_count": 1},
            "rows": [_row("basic_ci::pr_ci_30_consecutive_pass_evidence_missing")],
        },
    )
    reviewer_handoff = _write_json(
        tmp_path / "pm_release_gate_reviewer_handoff.json",
        {
            "release_tier_rows": [
                {
                    "requirement_id": "release_tier.limited_commercial_full_gate_ready",
                    "status": "blocked",
                    "blockers": ["security::license_status_not_configured"],
                    "next_action": "Close release-area blockers.",
                    "claim_boundary": "Limited Commercial cannot be promoted while blockers remain.",
                }
            ]
        },
    )

    payload = build_packet_module.build_packet(
        action_register=action_register,
        reviewer_handoff=reviewer_handoff,
    )

    assert payload["contract_pass"] is False
    assert payload["reason_code"] == "ERR_PM_OWNER_EVIDENCE_REQUEST_INCOMPLETE"
    assert payload["summary"]["release_tier_impact_contract_pass"] is False
    assert payload["summary"]["missing_release_tier_impact_count"] == 1
    assert payload["missing_release_tier_impacts"] == [
        "basic_ci::pr_ci_30_consecutive_pass_evidence_missing"
    ]
    assert payload["owner_packets"][0]["request_rows"][0]["blocked_release_tiers"] == []


def test_build_packet_surfaces_blocked_release_tier_owner_requests(tmp_path: Path) -> None:
    ga_intake = _write_json(
        tmp_path / "ga_enterprise_signoff_intake_packet.json",
        {
            "schema_version": "ga-enterprise-signoff-intake-packet.v1",
            "contract_pass": False,
            "reason_code": "ERR_GA_ENTERPRISE_SIGNOFF_OWNER_INPUT_REQUIRED",
            "current_blockers": ["independent_vv_missing"],
            "signoff_rows": [
                {
                    "blocker": "independent_vv_missing",
                    "signoff": "independent_vv_attestation",
                    "owner": "independent_vv_owner",
                    "evidence_status": {"state": "missing_external_signoff_evidence"},
                    "evidence_path": "implementation/phase1/release_evidence/productization/independent_vv_attestation.json",
                    "template_path": "docs/templates/independent_vv_attestation.template.json",
                    "evidence_contract_pass": False,
                    "next_action": "Attach independent V&V attestation.",
                    "acceptance": "`independent_vv_attestation.contract_pass == true`",
                    "required_fields": ["contract_pass", "approval_decision"],
                    "missing_fields": ["contract_pass", "approval_decision"],
                }
            ],
        },
    )
    reviewer_handoff = _write_json(
        tmp_path / "pm_release_gate_reviewer_handoff.json",
        {
            "release_tier_rows": [
                {
                    "requirement_id": "release_tier.limited_commercial_full_gate_ready",
                    "status": "blocked",
                    "blockers": ["basic_ci::pr_ci_30_consecutive_pass_evidence_missing"],
                    "next_action": "Close all release-area blockers before Limited Commercial promotion.",
                    "claim_boundary": "Limited Commercial cannot be promoted while release-area blockers remain open.",
                },
                {
                    "requirement_id": "release_tier.ga_enterprise_evidence_gate_pass",
                    "status": "blocked",
                    "blockers": ["independent_vv_missing"],
                    "next_action": "Attach independent V&V before GA/Enterprise release.",
                    "claim_boundary": "GA still requires independent V&V and support evidence.",
                },
            ]
        },
    )
    action_register = _write_json(
        tmp_path / "pm_release_blocker_action_register.json",
        {
            "pm_summary_line": "PM release gate: LIMITED_MILESTONE_READY",
            "summary": {
                "open_blocker_count": 0,
                "limited_commercial_milestone_ready": True,
                "limited_commercial_release_ready": False,
                "limited_commercial_ready": False,
                "paid_pilot_candidate": True,
            },
            "rows": [],
        },
    )

    payload = build_packet_module.build_packet(
        action_register=action_register,
        reviewer_handoff=reviewer_handoff,
        ga_signoff_intake_packet=ga_intake,
    )

    assert payload["contract_pass"] is True
    assert payload["summary"]["evidence_closure_pass"] is False
    assert payload["summary"]["release_tier_owner_packet_count"] == 2
    assert payload["summary"]["release_tier_request_count"] == 2
    assert payload["summary"]["release_tier_incomplete_request_count"] == 0
    assert payload["summary"]["expected_intake_count"] == 1
    assert payload["summary"]["expected_intake_open_blocker_count"] == 1
    assert payload["summary"]["expected_intake_signoff_request_count"] == 1
    assert [packet["owner"] for packet in payload["release_tier_owner_packets"]] == [
        "release_owner",
        "ga_release_owner",
    ]
    ga_packet = payload["release_tier_owner_packets"][1]
    assert ga_packet["expected_intake_paths"] == [str(ga_intake)]
    assert ga_packet["intake_current_blockers"] == ["independent_vv_missing"]
    assert ga_packet["intake_signoff_request_rows"][0]["signoff"] == "independent_vv_attestation"
    assert ga_packet["intake_signoff_request_rows"][0]["missing_fields"] == [
        "contract_pass",
        "approval_decision",
    ]
    markdown = build_packet_module._markdown(payload)
    assert "## Release Tier Owner Requests" in markdown
    assert "`release_tier.ga_enterprise_evidence_gate_pass`" in markdown
    assert "| `independent_vv_attestation` | `independent_vv_owner` |" in markdown
    assert "independent V&V" in payload["claim_boundary"]


def test_build_packet_blocks_when_owner_request_is_incomplete(tmp_path: Path) -> None:
    action_register = _write_json(
        tmp_path / "pm_release_blocker_action_register.json",
        {
            "pm_summary_line": "PM release gate: LIMITED_READY | release_areas=BLOCKED",
            "summary": {"open_blocker_count": 1},
            "rows": [_row("security::license_status_not_configured", owner="product_legal_owner", owner_action="")],
        },
    )

    payload = build_packet_module.build_packet(action_register=action_register)

    assert payload["contract_pass"] is False
    assert payload["reason_code"] == "ERR_PM_OWNER_EVIDENCE_REQUEST_INCOMPLETE"
    assert payload["incomplete_blockers"] == ["security::license_status_not_configured"]
    assert payload["summary"]["handoff_contract_pass"] is False
    assert payload["summary"]["evidence_closure_pass"] is False


def test_cli_writes_json_and_markdown(tmp_path: Path, capsys) -> None:
    action_register = _write_json(
        tmp_path / "pm_release_blocker_action_register.json",
        {
            "pm_summary_line": "PM release gate",
            "summary": {"open_blocker_count": 0},
            "rows": [],
        },
    )
    out = tmp_path / "owner-packet.json"
    out_md = tmp_path / "owner-packet.md"
    reviewer_handoff = _write_json(tmp_path / "empty_handoff.json", {"release_tier_rows": []})

    exit_code = build_packet_module.main(
        [
            "--action-register",
            str(action_register),
            "--reviewer-handoff",
            str(reviewer_handoff),
            "--out",
            str(out),
            "--out-md",
            str(out_md),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "PM Owner Evidence Request Packet" in captured.out
    assert json.loads(out.read_text(encoding="utf-8"))["summary"]["owner_packet_count"] == 1
    markdown = out_md.read_text(encoding="utf-8")
    assert "No open owner evidence requests" in markdown
    assert "No open intake details." in markdown
    assert "## Owner Commands" in markdown
