from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "build_pm_release_blocker_closure_board.py"
SPEC = importlib.util.spec_from_file_location("build_pm_release_blocker_closure_board", SCRIPT_PATH)
assert SPEC is not None
build_board_module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(build_board_module)


@pytest.fixture(autouse=True)
def _clean_source_provenance_for_computation_tests(monkeypatch: pytest.MonkeyPatch):
    original = build_board_module.commit_bound_input_metadata

    def _passing_metadata(*args: Any, **kwargs: Any) -> dict[str, Any]:
        metadata = original(*args, **kwargs)
        provenance = dict(metadata["source_input_provenance"])
        provenance.update(
            {
                "contract_pass": True,
                "reason_code": "PASS",
                "blocker_count": 0,
                "blockers": [],
            }
        )
        metadata["source_input_provenance"] = provenance
        return metadata

    monkeypatch.setattr(
        build_board_module, "commit_bound_input_metadata", _passing_metadata
    )


def _write_json(path: Path, payload: object) -> Path:
    if isinstance(payload, dict) and (
        "pm_release_gate" in path.name
        or path.name == "pm-release-gate.json"
        or ("action" in path.name and "register" in path.name)
    ):
        payload = dict(payload)
        payload.setdefault("contract_pass", True)
        payload.setdefault("source_input_provenance", {"contract_pass": True})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _blocked_source_metadata(*args: Any, **kwargs: Any) -> dict[str, Any]:
    paths = list(args[0] if args else kwargs.get("paths", []))
    return {
        "source_commit_sha": "a" * 40,
        "input_checksums": {str(path): "missing" for path in paths},
        "source_input_provenance": {
            "contract_pass": False,
            "reason_code": "ERR_SOURCE_INPUT_NOT_REPRODUCIBLE",
            "blocker_count": 1,
            "blockers": ["source_commit_unresolved"],
        },
    }


def test_build_board_groups_open_blockers_by_closure_state(tmp_path: Path) -> None:
    pm_report = _write_json(
        tmp_path / "pm_release_gate_report.json",
        {
            "summary_line": "PM release gate: LIMITED_MILESTONE_READY | release_areas=BLOCKED",
            "paid_pilot_candidate": True,
            "limited_commercial_milestone_ready": True,
            "limited_commercial_release_ready": False,
            "limited_commercial_ready": False,
            "release_area_gate_ready": False,
            "full_release_gate_ready": False,
            "full_release_blockers": [
                "basic_ci::pr_ci_30_consecutive_pass_evidence_missing",
                "security::frontend_dependency_audit_missing_or_failed",
            ],
        },
    )
    action_register = _write_json(
        tmp_path / "pm_release_blocker_action_register.json",
        {
            "contract_pass": False,
            "pm_summary_line": "PM release gate: LIMITED_MILESTONE_READY | release_areas=BLOCKED",
            "summary": {
                "open_blocker_count": 2,
                "handoff_ready_count": 2,
                "handoff_not_ready_count": 0,
                "all_open_blockers_have_handoff": True,
                "full_release_gate_ready": False,
                "limited_commercial_milestone_ready": True,
                "limited_commercial_release_ready": False,
                "limited_commercial_ready": False,
            },
            "rows": [
                {
                    "blocker_id": "basic_ci::pr_ci_30_consecutive_pass_evidence_missing",
                    "scope": "release_area",
                    "owner": "release_ci_owner",
                    "owner_input_required": True,
                    "external_input_required": True,
                    "resolution_type": "external_tracked_ci_evidence_required",
                    "next_action": "Collect additional PR CI streak evidence.",
                    "handoff_ready": True,
                    "handoff_state": "external_owner_input_ready",
                    "evidence_status": {"state": "missing_tracked_ci_streak_evidence"},
                    "evidence_artifacts": {"ci_streak_intake_packet": "ci_streak_intake_packet.json"},
                    "acceptance_criteria": ["`pr_pass_streak_count >= 30`"],
                    "reproduction_commands": ["python3 scripts/build_ci_streak_intake_packet.py"],
                    "verification_commands": ["python3 scripts/build_ci_streak_intake_packet.py --fail-blocked"],
                    "claim_boundary": "Tracked PR CI evidence is required.",
                },
                {
                    "blocker_id": "security::frontend_dependency_audit_missing_or_failed",
                    "scope": "release_area",
                    "owner": "frontend_security_owner",
                    "owner_input_required": False,
                    "external_input_required": False,
                    "resolution_type": "local_dependency_remediation_required",
                    "next_action": "Patch vulnerable frontend dependencies.",
                    "handoff_ready": True,
                    "handoff_state": "local_remediation_ready",
                    "evidence_status": {"state": "dependency_vulnerabilities_present"},
                    "evidence_artifacts": {"frontend_dependency_audit_report": "frontend_dependency_audit.json"},
                    "acceptance_criteria": ["`high_or_critical_vulnerability_count == 0`"],
                    "reproduction_commands": ["npm audit --audit-level high"],
                    "verification_commands": ["npm audit --audit-level high"],
                },
            ],
        },
    )

    payload = build_board_module.build_board(action_register=action_register, pm_report=pm_report)
    rows = {row["blocker_id"]: row for row in payload["rows"]}

    assert payload["contract_pass"] is False
    assert payload["source_commit_sha"]
    assert payload["engine_version"] == "structural-analysis@0.3.0"
    assert payload["reused_evidence"] is True
    assert (
        payload["reuse_policy"]
        == "pm_release_blocker_closure_board_aggregates_action_register_and_pm_report"
    )
    assert action_register.as_posix() in payload["input_checksums"]
    assert pm_report.as_posix() in payload["input_checksums"]
    assert "scripts/build_pm_release_blocker_closure_board.py" in payload["input_checksums"]
    assert "scripts/release_evidence_metadata.py" in payload["input_checksums"]
    assert payload["aggregator_freshness_policy"]["mode"] == "direct_aggregator_source_tracking"
    assert payload["reason_code"] == "ERR_UPSTREAM_ACTION_REGISTER_BLOCKED"
    assert payload["summary"]["open_blocker_count"] == 2
    assert payload["summary"]["register_open_blocker_count"] == 2
    assert payload["summary"]["external_owner_input_ready_count"] == 1
    assert payload["summary"]["local_remediation_ready_count"] == 1
    assert payload["summary"]["handoff_not_ready_count"] == 0
    assert payload["summary"]["all_open_blockers_have_handoff"] is True
    assert payload["summary"]["paid_pilot_candidate"] is True
    assert payload["summary"]["limited_commercial_milestone_ready"] is True
    assert payload["summary"]["limited_commercial_release_ready"] is False
    assert payload["summary"]["limited_commercial_ready"] is False
    assert payload["summary"]["action_register_matches_pm_report"] is True
    assert payload["summary"]["missing_from_action_register_count"] == 0
    assert payload["summary"]["stale_action_register_blocker_count"] == 0

    ci_row = rows["basic_ci::pr_ci_30_consecutive_pass_evidence_missing"]
    assert ci_row["closure_state"] == "external_owner_input_ready"
    assert ci_row["evidence_state"] == "missing_tracked_ci_streak_evidence"
    assert ci_row["primary_evidence_artifacts"]["ci_streak_intake_packet"] == "ci_streak_intake_packet.json"
    assert ci_row["claim_boundary"] == "Tracked PR CI evidence is required."

    dependency_row = rows["security::frontend_dependency_audit_missing_or_failed"]
    assert dependency_row["closure_state"] == "local_remediation_ready"
    assert dependency_row["external_input_required"] is False


def test_build_board_passes_when_gate_and_register_are_closed(tmp_path: Path) -> None:
    pm_report = _write_json(
        tmp_path / "pm_release_gate_report.json",
        {"summary_line": "PM release gate: LIMITED_READY", "full_release_gate_ready": True},
    )
    action_register = _write_json(
        tmp_path / "pm_release_blocker_action_register.json",
        {
            "contract_pass": True,
            "summary": {"open_blocker_count": 0, "all_open_blockers_have_handoff": True},
            "rows": [],
        },
    )

    payload = build_board_module.build_board(action_register=action_register, pm_report=pm_report)

    assert payload["contract_pass"] is True
    assert payload["reason_code"] == "PASS"
    assert payload["summary"]["open_blocker_count"] == 0
    assert payload["summary"]["action_register_matches_pm_report"] is True
    assert payload["rows"] == []


def test_build_board_and_cli_fail_closed_on_source_provenance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    monkeypatch.setattr(
        build_board_module,
        "commit_bound_input_metadata",
        _blocked_source_metadata,
    )
    pm_report = _write_json(
        tmp_path / "pm_release_gate_report.json",
        {"summary_line": "PM release gate: READY", "full_release_gate_ready": True},
    )
    action_register = _write_json(
        tmp_path / "pm_release_blocker_action_register.json",
        {"contract_pass": True, "summary": {"open_blocker_count": 0}, "rows": []},
    )
    payload = build_board_module.build_board(
        action_register=action_register,
        pm_report=pm_report,
    )

    assert payload["computed_without_provenance"]["contract_pass"] is True
    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is False
    assert payload["reason_code"] == "ERR_SOURCE_INPUT_NOT_REPRODUCIBLE"

    exit_code = build_board_module.main(
        [
            "--action-register",
            str(action_register),
            "--pm-report",
            str(pm_report),
            "--out",
            str(tmp_path / "board.json"),
            "--out-md",
            str(tmp_path / "board.md"),
            "--fail-blocked",
        ]
    )
    capsys.readouterr()
    assert exit_code == 1


def test_build_board_compares_ga_enterprise_blockers_with_action_register(tmp_path: Path) -> None:
    pm_report = _write_json(
        tmp_path / "pm_release_gate_report.json",
        {
            "summary_line": "PM release gate: BLOCKED | release_areas=BLOCKED",
            "full_release_gate_ready": False,
            "full_release_blockers": ["security::license_status_not_configured"],
            "release_tiers": {
                "ga_enterprise_blockers": [
                    "independent_vv_missing",
                    "fresh_full_validation::gpu_hip_solver::fresh_validation_receipt_missing",
                ]
            },
        },
    )
    action_register = _write_json(
        tmp_path / "pm_release_blocker_action_register.json",
        {
            "contract_pass": False,
            "summary": {"open_blocker_count": 3, "all_open_blockers_have_handoff": True},
            "rows": [
                {
                    "blocker_id": "security::license_status_not_configured",
                    "owner": "product_legal_owner",
                    "external_input_required": True,
                    "owner_input_required": True,
                    "next_action": "Attach license approval evidence.",
                    "handoff_ready": True,
                    "handoff_state": "external_owner_input_ready",
                },
                {
                    "blocker_id": "independent_vv_missing",
                    "owner": "independent_vv_owner",
                    "external_input_required": True,
                    "owner_input_required": True,
                    "next_action": "Attach independent V&V evidence.",
                    "handoff_ready": True,
                    "handoff_state": "external_owner_input_ready",
                },
                {
                    "blocker_id": "fresh_full_validation::gpu_hip_solver::fresh_validation_receipt_missing",
                    "owner": "validation_lane_owner",
                    "external_input_required": False,
                    "owner_input_required": False,
                    "next_action": "Run the GPU HIP fresh validation lane.",
                    "handoff_ready": True,
                    "handoff_state": "local_remediation_ready",
                },
            ],
        },
    )

    payload = build_board_module.build_board(action_register=action_register, pm_report=pm_report)

    assert payload["contract_pass"] is False
    assert payload["reason_code"] == "ERR_UPSTREAM_ACTION_REGISTER_BLOCKED"
    assert payload["summary"]["action_register_matches_pm_report"] is True
    assert payload["summary"]["pm_report_blocker_count"] == 3
    assert payload["summary"]["register_blocker_count"] == 3
    assert payload["summary"]["missing_from_action_register"] == []
    assert payload["summary"]["stale_action_register_blockers"] == []


def test_build_board_blocks_stale_action_register(tmp_path: Path) -> None:
    pm_report = _write_json(
        tmp_path / "pm_release_gate_report.json",
        {
            "summary_line": "PM release gate: LIMITED_READY | release_areas=BLOCKED",
            "full_release_gate_ready": False,
            "full_release_blockers": ["security::license_status_not_configured"],
        },
    )
    action_register = _write_json(
        tmp_path / "pm_release_blocker_action_register.json",
        {
            "contract_pass": False,
            "summary": {"open_blocker_count": 1, "all_open_blockers_have_handoff": True},
            "rows": [
                {
                    "blocker_id": "ux::human_new_user_observation_missing_or_failed",
                    "owner": "ux_research_owner",
                    "external_input_required": True,
                    "owner_input_required": True,
                    "next_action": "Attach observed UX sample workflow evidence.",
                    "handoff_ready": True,
                    "handoff_state": "external_owner_input_ready",
                }
            ],
        },
    )

    payload = build_board_module.build_board(action_register=action_register, pm_report=pm_report)

    assert payload["contract_pass"] is False
    assert payload["reason_code"] == "ERR_UPSTREAM_ACTION_REGISTER_BLOCKED"
    assert payload["summary"]["action_register_matches_pm_report"] is False
    assert payload["summary"]["missing_from_action_register"] == ["security::license_status_not_configured"]
    assert payload["summary"]["stale_action_register_blockers"] == [
        "ux::human_new_user_observation_missing_or_failed"
    ]


def test_build_board_allows_structural_scope_cleanup_adjunct_handoff(
    tmp_path: Path,
) -> None:
    pm_report = _write_json(
        tmp_path / "pm_release_gate_report.json",
        {
            "summary_line": "PM release gate: BLOCKED | release_areas=BLOCKED",
            "full_release_gate_ready": False,
            "full_release_blockers": ["security::license_status_not_configured"],
        },
    )
    action_register = _write_json(
        tmp_path / "pm_release_blocker_action_register.json",
        {
            "contract_pass": False,
            "summary": {"open_blocker_count": 2, "all_open_blockers_have_handoff": True},
            "rows": [
                {
                    "blocker_id": "structural_scope_cleanup::owner_review_decisions_pending",
                    "owner": "release_scope_owner",
                    "external_input_required": True,
                    "owner_input_required": True,
                    "next_action": "Record owner decisions for quarantined non-structural paths.",
                    "handoff_ready": True,
                    "handoff_state": "external_owner_input_ready",
                },
                {
                    "blocker_id": "security::license_status_not_configured",
                    "owner": "product_legal_owner",
                    "external_input_required": True,
                    "owner_input_required": True,
                    "next_action": "Attach license approval evidence.",
                    "handoff_ready": True,
                    "handoff_state": "external_owner_input_ready",
                },
            ],
        },
    )

    payload = build_board_module.build_board(
        action_register=action_register,
        pm_report=pm_report,
    )

    assert payload["contract_pass"] is False
    assert payload["reason_code"] == "ERR_UPSTREAM_ACTION_REGISTER_BLOCKED"
    assert payload["summary"]["action_register_matches_pm_report"] is True
    assert payload["summary"]["missing_from_action_register"] == []
    assert payload["summary"]["stale_action_register_blockers"] == []
    assert payload["summary"]["allowed_adjunct_action_register_blockers"] == [
        "structural_scope_cleanup::owner_review_decisions_pending"
    ]


def test_cli_writes_json_and_markdown(tmp_path: Path, capsys) -> None:
    pm_report = _write_json(
        tmp_path / "pm_release_gate_report.json",
        {
            "summary_line": "PM release gate: LIMITED_READY",
            "full_release_gate_ready": False,
            "full_release_blockers": ["ux::human_new_user_observation_missing_or_failed"],
        },
    )
    action_register = _write_json(
        tmp_path / "pm_release_blocker_action_register.json",
        {
            "contract_pass": False,
            "summary": {"open_blocker_count": 1, "all_open_blockers_have_handoff": True},
            "rows": [
                {
                    "blocker_id": "ux::human_new_user_observation_missing_or_failed",
                    "owner": "ux_research_owner",
                    "external_input_required": True,
                    "owner_input_required": True,
                    "next_action": "Attach observed UX sample workflow evidence.",
                    "handoff_ready": True,
                    "handoff_state": "external_owner_input_ready",
                }
            ],
        },
    )
    out = tmp_path / "board.json"
    out_md = tmp_path / "board.md"

    exit_code = build_board_module.main(
        [
            "--action-register",
            str(action_register),
            "--pm-report",
            str(pm_report),
            "--out",
            str(out),
            "--out-md",
            str(out_md),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "PM Release Blocker Closure Board" in captured.out
    assert json.loads(out.read_text(encoding="utf-8"))["summary"]["open_blocker_count"] == 1
    assert "ux::human_new_user_observation_missing_or_failed" in out_md.read_text(encoding="utf-8")
    assert "action_register_matches_pm_report" in out_md.read_text(encoding="utf-8")


def test_build_board_relative_reads_are_independent_of_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(build_board_module.ROOT)
    expected = build_board_module.build_board()
    alternate_cwd = tmp_path / "alternate-cwd"
    alternate_cwd.mkdir()
    monkeypatch.chdir(alternate_cwd)

    actual = build_board_module.build_board()

    assert actual["pm_summary_line"] == expected["pm_summary_line"]
    assert actual["summary"] == expected["summary"]
    assert actual["rows"] == expected["rows"]
    assert actual["input_checksums"] == expected["input_checksums"]


def test_build_board_propagates_each_blocked_upstream_contract_and_cli(
    tmp_path: Path, capsys
) -> None:
    pm_report = _write_json(
        tmp_path / "pm-release-gate.json",
        {
            "summary_line": "PM release gate: READY",
            "contract_pass": True,
            "source_input_provenance": {"contract_pass": False},
            "full_release_gate_ready": True,
            "full_release_blockers": [],
        },
    )
    action_register = _write_json(
        tmp_path / "action-register.json",
        {
            "contract_pass": True,
            "source_input_provenance": {"contract_pass": True},
            "summary": {"open_blocker_count": 0},
            "rows": [],
        },
    )

    pm_blocked = build_board_module.build_board(
        action_register=action_register,
        pm_report=pm_report,
    )

    assert pm_blocked["rows"] == []
    assert pm_blocked["computed_without_provenance"]["contract_pass"] is True
    assert pm_blocked["reason_code"] == "ERR_UPSTREAM_PM_RELEASE_GATE_BLOCKED"
    assert pm_blocked["blockers"] == ["ERR_UPSTREAM_PM_RELEASE_GATE_BLOCKED"]

    _write_json(
        pm_report,
        {
            "summary_line": "PM release gate: READY",
            "contract_pass": True,
            "source_input_provenance": {"contract_pass": True},
            "full_release_gate_ready": True,
            "full_release_blockers": [],
        },
    )
    action_payload = json.loads(action_register.read_text(encoding="utf-8"))
    action_payload["contract_pass"] = False
    _write_json(action_register, action_payload)
    action_blocked = build_board_module.build_board(
        action_register=action_register,
        pm_report=pm_report,
    )

    assert action_blocked["rows"] == []
    assert action_blocked["computed_without_provenance"]["contract_pass"] is True
    assert action_blocked["reason_code"] == "ERR_UPSTREAM_ACTION_REGISTER_BLOCKED"
    assert action_blocked["blockers"] == ["ERR_UPSTREAM_ACTION_REGISTER_BLOCKED"]
    upstream = action_blocked["computed_without_provenance"]["upstream_contracts"]
    assert upstream["pm_release_gate_report"]["required_pass"] is True
    assert upstream["pm_release_blocker_action_register"]["required_pass"] is False

    exit_code = build_board_module.main(
        [
            "--action-register",
            str(action_register),
            "--pm-report",
            str(pm_report),
            "--out",
            str(tmp_path / "closure-board.json"),
            "--out-md",
            str(tmp_path / "closure-board.md"),
            "--fail-blocked",
        ]
    )
    capsys.readouterr()
    assert exit_code == 1


def test_build_board_requires_explicit_action_register_provenance_contract(
    tmp_path: Path,
) -> None:
    pm_report = _write_json(
        tmp_path / "pm-release-gate.json",
        {
            "summary_line": "PM release gate: READY",
            "full_release_gate_ready": True,
            "full_release_blockers": [],
        },
    )
    action_register = tmp_path / "legacy-action-register.json"
    action_register.write_text(
        json.dumps(
            {
                "contract_pass": True,
                "summary": {"open_blocker_count": 0},
                "rows": [],
            }
        ),
        encoding="utf-8",
    )

    payload = build_board_module.build_board(
        action_register=action_register,
        pm_report=pm_report,
    )

    assert payload["reason_code"] == "ERR_UPSTREAM_ACTION_REGISTER_BLOCKED"
    upstream = payload["computed_without_provenance"]["upstream_contracts"][
        "pm_release_blocker_action_register"
    ]
    assert upstream["source_input_provenance_present"] is False
    assert upstream["required_pass"] is False
