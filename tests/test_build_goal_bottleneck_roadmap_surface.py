from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_goal_bottleneck_roadmap_surface.py"
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

spec = importlib.util.spec_from_file_location(
    "build_goal_bottleneck_roadmap_surface",
    SCRIPT_PATH,
)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def _row_by_phase(surface: dict[str, object]) -> dict[str, dict[str, object]]:
    rows = surface["roadmap_rows"]
    assert isinstance(rows, list)
    return {
        str(row["phase_id"]): row
        for row in rows
        if isinstance(row, dict) and "phase_id" in row
    }


def test_goal_bottleneck_roadmap_surface_exposes_goal_release_kpis() -> None:
    surface = module.build_goal_bottleneck_roadmap_surface(repo_root=REPO_ROOT)

    assert surface["schema_version"] == "goal-bottleneck-roadmap-surface.v1"
    assert surface["surface_id"] == "goal_bottleneck_roadmap_surface"
    assert surface["contract_pass"] is True
    assert surface["read_model_ready"] is True
    assert surface["route"] == "/goal/bottleneck"
    assert surface["read_model"] == {
        "route": "/goal/bottleneck",
        "alternate_routes": ["/goal/roadmap"],
        "artifact": (
            "implementation/phase1/release_evidence/productization/"
            "goal_bottleneck_roadmap_surface.json"
        ),
        "mutation_allowed": False,
    }
    assert surface["source_of_truth_gap_summary"] == {
        "candidate_count": 5,
        "fix_count": 2,
        "fixed_count": 2,
        "no_op_count": 0,
        "aggregator_review_count": 3,
    }
    classification = {
        row["candidate"]: row
        for row in surface["source_of_truth_gap_classification"]
    }
    assert set(classification) == {
        "accuracy_parity_scorecard",
        "product_production_ai_checkpoint_readiness",
        "goal_readiness_rollup",
        "product_goal_completion_audit",
        "goal_operator_action_board",
    }
    assert classification["accuracy_parity_scorecard"]["classification"] == "fix"
    assert classification["accuracy_parity_scorecard"]["freshness_label"] == (
        "accuracy_parity_scorecard"
    )
    assert "science_scorecard_overall_pass_field" in classification[
        "accuracy_parity_scorecard"
    ]["validation_basis"]
    assert classification["goal_operator_action_board"]["classification"] == (
        "aggregator-review"
    )
    assert classification["goal_operator_action_board"]["freshness_label"] == ""
    assert "not_closure_evidence_without_owner_receipts" in classification[
        "goal_operator_action_board"
    ]["validation_basis"]

    kpis = surface["release_decision_kpis"]
    pm_report = json.loads(
        (
            REPO_ROOT
            / "implementation/phase1/release_evidence/productization/"
            / "pm_release_gate_report.json"
        ).read_text(encoding="utf-8")
    )
    decision = pm_report["release_decision"]
    assert kpis == {
        key: decision[key]
        for key in (
            "release_allowed",
            "blocked_release_count",
            "first_blocker",
            "operator_action_count",
            "approval_token_count",
            "stale_artifact_count",
            "evidence_surface_count",
            "missing_evidence_surface_count",
            "locked_evidence_surface_count",
            "public_benchmark_ready",
        )
    }
    assert kpis["blocked_release_count"] == len(pm_report["full_release_blockers"])
    assert kpis["first_blocker"] == (
        "basic_ci::pr_ci_30_consecutive_pass_evidence_missing"
    )
    assert kpis["evidence_surface_count"] == 8
    assert kpis["locked_evidence_surface_count"] == 0
    assert kpis["missing_evidence_surface_count"] == 0
    assert surface["science_evidence_surface_bottlenecks"] == []
    assert surface["non_expert_release_briefing_ready"] is True

    briefing = surface["non_expert_release_briefing"]
    assert briefing["audience"] == "non_expert_pm_operator"
    assert briefing["release_allowed"] is False
    assert briefing["primary_release_blocker"] == (
        "basic_ci::pr_ci_30_consecutive_pass_evidence_missing"
    )
    assert briefing["refresh_required_operator_action_count"] == 0
    assert briefing["refresh_required_operator_actions"] == []

    release_area_handoffs = {
        row["blocker_id"]: row
        for row in briefing["release_area_owner_handoffs"]
    }
    assert set(release_area_handoffs) == set(pm_report["release_area_blockers"])
    required_release_area_handoffs = {
        "basic_ci::pr_ci_30_consecutive_pass_evidence_missing",
        "basic_ci::nightly_ci_30_consecutive_pass_evidence_missing",
        "ux::human_new_user_observation_missing_or_failed",
        "ux::human_new_user_30min_sample_evidence_missing",
        "security::license_status_not_configured",
    }
    assert required_release_area_handoffs.issubset(release_area_handoffs)
    assert kpis["blocked_release_count"] >= len(required_release_area_handoffs)
    assert briefing["release_area_blocker_count"] == len(release_area_handoffs)
    assert briefing["release_area_owner_handoff_count"] == len(release_area_handoffs)

    ci_handoff = release_area_handoffs[
        "basic_ci::pr_ci_30_consecutive_pass_evidence_missing"
    ]
    assert ci_handoff["owner"] == "release_ci_owner"
    assert ci_handoff["handoff_state"] == "external_owner_input_ready"
    assert ci_handoff["external_input_required"] is True
    assert ci_handoff["evidence_state"] == "self_hosted_runner_offline"
    assert "Bring at least one GitHub Actions self-hosted runner online" in ci_handoff[
        "owner_action"
    ]
    assert "rerun the workflow" in ci_handoff["owner_action"]
    assert "collect 30 additional consecutive successful CI run" in ci_handoff[
        "owner_action"
    ]
    assert ci_handoff["acceptance_criteria_count"] == 4
    assert "ci_streak_intake_packet" in ci_handoff["evidence_artifact_keys"]

    ux_handoff = release_area_handoffs[
        "ux::human_new_user_observation_missing_or_failed"
    ]
    assert ux_handoff["owner"] == "ux_research_owner"
    assert ux_handoff["evidence_state"] == "missing_human_new_user_observation"
    assert "ux_new_user_observation_intake_packet" in ux_handoff[
        "evidence_artifact_keys"
    ]
    security_handoff = release_area_handoffs[
        "security::license_status_not_configured"
    ]
    assert security_handoff["owner"] == "product_legal_owner"
    assert security_handoff["evidence_state"] == "not_configured"

    assert briefing["human_ux_blockers"] == [
        "ux::human_new_user_observation_missing_or_failed",
        "ux::human_new_user_30min_sample_evidence_missing",
    ]
    assert briefing["human_ux_owner_action"] == (
        "attach a passing human new-user observation record before claiming "
        "the UX release-area gate"
    )
    human_ux = briefing["human_ux_release_gate"]
    assert human_ux["status"] == "blocked"
    assert human_ux["release_area_blockers"] == briefing["human_ux_blockers"]
    assert human_ux["human_observation_contract_pass"] is False
    assert human_ux["human_observation_reason_code"] == (
        "ERR_UX_NEW_USER_OBSERVATION_REQUIRED"
    )
    assert human_ux["human_observation_blocker_count"] == 12
    assert human_ux["owner_intake_contract_pass"] is False
    assert human_ux["owner_intake_reason_code"] == (
        "ERR_UX_NEW_USER_OBSERVATION_OWNER_INPUT_REQUIRED"
    )
    assert human_ux["owner_intake_current_blocker_count"] == 12
    assert human_ux["missing_field_count"] == 14
    assert human_ux["workflow_step_pass_count"] == 0
    assert human_ux["required_workflow_step_count"] == 5
    assert human_ux["missing_workflow_steps"] == [
        "import",
        "model_health",
        "analysis_setup",
        "run_monitor",
        "compare_report",
    ]
    assert human_ux["max_completion_minutes"] == 30
    assert "Automated rehearsal or templates do not close it" in human_ux[
        "plain_status"
    ]
    assert human_ux["evidence_artifacts"] == {
        "observation_report": (
            "implementation/phase1/release_evidence/productization/"
            "ux_new_user_observation_report.json"
        ),
        "owner_intake_packet": (
            "implementation/phase1/release_evidence/productization/"
            "ux_new_user_observation_intake_packet.json"
        ),
        "observation_source": (
            "implementation/phase1/release_evidence/productization/"
            "ux_new_user_observation.json"
        ),
        "template": "docs/templates/ux_new_user_observation.template.json",
    }
    assert any(
        "build_ux_new_user_observation_report.py" in command
        for command in human_ux["validation_commands"]
    )
    assert human_ux["claim_boundary"] == (
        "This report validates a human new-user observation record. Automated "
        "browser rehearsal evidence does not satisfy the PM UX release-area "
        "gate by itself."
    )

    assert briefing["primary_roadmap_bottleneck"] == (
        "basic_ci::pr_ci_30_consecutive_pass_evidence_missing"
    )
    assert briefing["primary_roadmap_phase_id"] == "phase_1_goal_release_cockpit"
    assert briefing["blocked_science_or_beta_phase_count"] == 0
    assert briefing["blocked_science_or_beta_phases"] == []
    assert briefing["next_owner_handoff_count"] == 0
    assert briefing["first_operator_handoff"] == {}
    assert briefing["next_owner_handoff_slot_count"] == 0
    assert briefing["first_operator_handoff_slot"] == {}
    assert briefing["claim_boundaries"] == [
        "do_not_claim_limited_commercial_release_until_release_allowed_true",
        "do_not_replace_human_ux_observation_with_templates_or_automation",
    ]
    assert surface["operator_evidence_handoff_count"] == 0
    assert surface["operator_evidence_handoff_queue"] == []
    assert surface["operator_evidence_handoff_slot_count"] == 0
    assert surface["operator_evidence_handoff_slot_queue"] == []


def test_goal_bottleneck_surface_does_not_read_molecular_release_artifacts(
    monkeypatch,
) -> None:
    original_load_json = module._load_json
    loaded_paths: list[str] = []

    def tracking_load_json(repo_root: Path, path: Path) -> dict[str, object]:
        loaded_paths.append(path.as_posix())
        return original_load_json(repo_root, path)

    monkeypatch.setattr(module, "_load_json", tracking_load_json)

    surface = module.build_goal_bottleneck_roadmap_surface(repo_root=REPO_ROOT)
    forbidden_tokens = ("gpcr", "pocketmd", "md3bead")

    assert not hasattr(module, "_gpcr_row")
    assert not hasattr(module, "_pocketmd_row")
    assert not hasattr(module, "_science_evidence_surface_rows")
    assert not any(
        token in name.lower()
        for name in dir(module)
        if name.startswith("DEFAULT_")
        for token in forbidden_tokens
    )
    assert not any(
        token in path.lower()
        for path in loaded_paths
        for token in forbidden_tokens
    )
    surface_text = json.dumps(
        {
            "roadmap_rows": surface["roadmap_rows"],
            "science_evidence_surface_status": surface[
                "science_evidence_surface_status"
            ],
            "science_evidence_surface_bottlenecks": surface[
                "science_evidence_surface_bottlenecks"
            ],
            "capability_summary_rows": surface["capability_summary_rows"],
            "non_expert_release_briefing": surface["non_expert_release_briefing"],
        },
        ensure_ascii=False,
    ).lower()
    assert not any(token in surface_text for token in forbidden_tokens)


def test_goal_bottleneck_roadmap_surface_promotes_stale_refresh_operator_action(
    monkeypatch,
) -> None:
    original_load_json = module._load_json
    pm_report = original_load_json(REPO_ROOT, module.DEFAULT_PM_REPORT)
    action_register = original_load_json(REPO_ROOT, module.DEFAULT_ACTION_REGISTER)

    stale_pm_report = copy.deepcopy(pm_report)
    decision = stale_pm_report["release_decision"]
    decision["stale_artifact_count"] = 2
    decision["operator_action_count"] = int(decision["operator_action_count"]) + 1
    decision["operator_actions"] = [
        {
            "action_id": "refresh_release_evidence_freshness",
            "status": "refresh_required",
            "reason": (
                "release_evidence_freshness_report has stale or incomplete "
                "source-of-truth blockers"
            ),
            "artifact": "release_evidence_freshness_report",
        },
        *decision["operator_actions"],
    ]

    stale_action_register = copy.deepcopy(action_register)
    stale_action_register["release_decision_operator_actions"] = [
        row
        for row in stale_action_register["release_decision_operator_actions"]
        if row["action_id"] != "refresh_release_evidence_freshness"
    ]

    def fake_load_json(repo_root: Path, path: Path) -> dict[str, object]:
        if path == module.DEFAULT_PM_REPORT:
            return copy.deepcopy(stale_pm_report)
        if path == module.DEFAULT_ACTION_REGISTER:
            return copy.deepcopy(stale_action_register)
        return original_load_json(repo_root, path)

    monkeypatch.setattr(module, "_load_json", fake_load_json)

    surface = module.build_goal_bottleneck_roadmap_surface(repo_root=REPO_ROOT)

    assert surface["release_decision_kpis"]["stale_artifact_count"] == 2
    assert "refresh_stale_goal_artifacts" in surface["next_actions"]
    actions = {
        row["action_id"]: row
        for row in surface["release_decision_operator_actions"]
    }
    refresh_action = actions["refresh_release_evidence_freshness"]
    assert refresh_action["status"] == "refresh_required"
    assert refresh_action["artifact"] == "release_evidence_freshness_report"
    briefing = surface["non_expert_release_briefing"]
    assert briefing["refresh_required_operator_action_count"] == 1
    assert briefing["refresh_required_operator_actions"] == [refresh_action]


def test_goal_bottleneck_roadmap_surface_links_structural_release_bottleneck() -> None:
    surface = module.build_goal_bottleneck_roadmap_surface(repo_root=REPO_ROOT)
    rows = _row_by_phase(surface)

    assert set(rows) == {
        "phase_0_source_of_truth_hardening",
        "phase_1_goal_release_cockpit",
    }
    assert rows["phase_0_source_of_truth_hardening"]["state"] == "ready"
    phase_1 = rows["phase_1_goal_release_cockpit"]
    assert phase_1["state"] == "blocked"
    assert phase_1["bottleneck"] == (
        "basic_ci::pr_ci_30_consecutive_pass_evidence_missing"
    )
    assert phase_1["first_blocker"] == (
        "basic_ci::pr_ci_30_consecutive_pass_evidence_missing"
    )
    kpis = surface["release_decision_kpis"]
    assert phase_1["summary"] == {
        "release_allowed": kpis["release_allowed"],
        "blocked_release_count": kpis["blocked_release_count"],
        "operator_action_count": kpis["operator_action_count"],
        "approval_token_count": kpis["approval_token_count"],
        "action_register_contract_pass": False,
        "product_capability_count": 1,
        "blocked_capability_count": 0,
    }
    assert phase_1["next_actions"] == ["work_release_decision_operator_actions"]
    assert surface["primary_roadmap_bottleneck"] == (
        "basic_ci::pr_ci_30_consecutive_pass_evidence_missing"
    )
    assert surface["primary_roadmap_phase_id"] == "phase_1_goal_release_cockpit"


def test_goal_bottleneck_roadmap_surface_cli_writes_payload(tmp_path: Path) -> None:
    out = tmp_path / "productization" / "goal_bottleneck_roadmap_surface.json"

    assert module.main(["--repo-root", str(REPO_ROOT), "--out", str(out)]) == 0

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "goal-bottleneck-roadmap-surface.v1"
    assert payload["surface_id"] == "goal_bottleneck_roadmap_surface"
    assert payload["summary_line"].startswith("Goal bottleneck roadmap surface: READY")
