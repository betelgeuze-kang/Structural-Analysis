from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_non_expert_release_briefing_report.py"
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

spec = importlib.util.spec_from_file_location(
    "build_non_expert_release_briefing_report", SCRIPT_PATH
)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def test_non_expert_release_briefing_report_wraps_goal_briefing() -> None:
    payload = module.build_report(repo_root=REPO_ROOT)
    goal_surface = json.loads(
        (
            REPO_ROOT
            / "implementation/phase1/release_evidence/productization/"
            "goal_bottleneck_roadmap_surface.json"
        ).read_text(encoding="utf-8")
    )
    goal_briefing = goal_surface["non_expert_release_briefing"]

    assert payload["schema_version"] == "non-expert-release-briefing-report.v1"
    assert payload["contract_pass"] is True
    assert payload["read_model_ready"] is True
    assert payload["status"] == "ready_release_blocked"
    assert payload["route"] == "/goal/non-expert-release-briefing"
    assert payload["read_model"] == {
        "route": "/goal/non-expert-release-briefing",
        "alternate_routes": ["/goal/bottleneck", "/goal/roadmap", "/product/capabilities"],
        "artifact": (
            "implementation/phase1/release_evidence/productization/"
            "non_expert_release_briefing_report.json"
        ),
        "mutation_allowed": False,
    }
    assert payload["release_allowed"] is False
    assert payload["primary_release_blocker"] == goal_briefing[
        "primary_release_blocker"
    ]
    assert payload["release_area_blocker_count"] == goal_briefing[
        "release_area_blocker_count"
    ]
    assert payload["blocked_science_or_beta_phase_count"] == 0
    assert payload["blocked_science_or_beta_phases"] == []
    assert payload["human_ux_summary"]["status"] == "blocked"
    assert payload["human_ux_summary"]["human_observation_contract_pass"] is False
    assert payload["human_ux_summary"]["owner_intake_contract_pass"] is False
    assert payload["human_ux_summary"]["workflow_step_pass_count"] == 0
    assert payload["human_ux_summary"]["required_workflow_step_count"] == 5
    assert payload["first_operator_handoff"] == {}
    assert payload["next_owner_action_count"] == len(
        goal_briefing["release_area_owner_handoffs"]
    )
    assert payload["next_owner_actions"][0]["source"] == "release_area"
    assert payload["next_owner_actions"][0]["blocker_id"] == (
        "basic_ci::pr_ci_30_consecutive_pass_evidence_missing"
    )
    assert payload["next_owner_actions"][0]["owner"] == "release_ci_owner"
    assert payload["next_owner_actions"][0]["external_input_required"] is True
    assert "self-hosted runner" in payload["next_owner_actions"][0]["owner_action"]
    assert "do_not_replace_human_ux_observation_with_templates_or_automation" in payload[
        "claim_boundaries"
    ]
    assert "does not create new release evidence" in payload["claim_boundary"]
    assert "quarantined non-structural artifacts" in payload["claim_boundary"]
    assert payload["reused_evidence"] is True
    assert payload["reuse_policy"] == (
        "non_expert_release_briefing_report_from_goal_bottleneck_surface"
    )


def test_non_expert_release_briefing_report_has_no_molecular_claim_surface() -> None:
    payload = module.build_report(repo_root=REPO_ROOT)
    forbidden_tokens = ("gpcr", "pocketmd", "md3bead", "casf", "pdbbind")
    payload_text = json.dumps(payload, ensure_ascii=False).lower()

    assert not any(token in payload_text for token in forbidden_tokens)
    assert payload["blocked_science_or_beta_phase_count"] == 0
    assert payload["first_operator_handoff"] == {}


def test_non_expert_release_briefing_report_blocks_when_goal_briefing_missing(
    tmp_path: Path,
) -> None:
    goal_surface = tmp_path / "goal_bottleneck_roadmap_surface.json"
    goal_surface.write_text(json.dumps({}), encoding="utf-8")

    payload = module.build_report(repo_root=REPO_ROOT, goal_surface=goal_surface)

    assert payload["contract_pass"] is False
    assert payload["status"] == "blocked_report_incomplete"
    assert payload["reason_code"] == "ERR_NON_EXPERT_BRIEFING_INCOMPLETE"
    assert "non_expert_release_briefing_missing_or_not_ready" in payload["blockers"]
    assert "briefing_required_key_missing:plain_status" in payload["blockers"]


def test_non_expert_release_briefing_report_cli_writes_json_and_markdown(
    tmp_path: Path,
) -> None:
    out = tmp_path / "briefing.json"
    out_md = tmp_path / "briefing.md"

    assert (
        module.main(
            [
                "--repo-root",
                str(REPO_ROOT),
                "--out",
                str(out),
                "--out-md",
                str(out_md),
                "--fail-blocked",
            ]
        )
        == 0
    )

    payload = json.loads(out.read_text(encoding="utf-8"))
    markdown = out_md.read_text(encoding="utf-8")
    assert payload["contract_pass"] is True
    assert "# Non-Expert Release Briefing" in markdown
    assert "Human UX Gate" in markdown
    assert "Scoped Release Blockers" in markdown
    assert "do_not_claim_tier_beta_until_public_benchmark_ready_true" not in markdown
    assert "GPCR" not in markdown
    assert "PocketMD" not in markdown
