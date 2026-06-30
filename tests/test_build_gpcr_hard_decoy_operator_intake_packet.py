from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_gpcr_hard_decoy_operator_intake_packet.py"
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

spec = importlib.util.spec_from_file_location(
    "build_gpcr_hard_decoy_operator_intake_packet",
    SCRIPT_PATH,
)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def test_gpcr_hard_decoy_operator_intake_packet_exposes_required_targets() -> None:
    packet = module.build_gpcr_hard_decoy_operator_intake_packet(repo_root=REPO_ROOT)

    assert packet["schema_version"] == "gpcr-hard-decoy-operator-intake-packet.v1"
    assert packet["status"] == "ready_for_operator_input"
    assert packet["contract_pass"] is True
    assert packet["read_model_ready"] is True
    assert packet["route"] == "/product/gpcr-hard-decoy-suite-report/operator-intake"
    assert packet["read_model"] == {
        "route": "/product/gpcr-hard-decoy-suite-report/operator-intake",
        "alternate_routes": [
            "/product/gpcr-hard-decoy-suite-report",
            "/product/capabilities",
        ],
        "artifact": (
            "implementation/phase1/release_evidence/productization/"
            "gpcr_hard_decoy_operator_intake_packet.json"
        ),
        "mutation_allowed": False,
    }
    assert packet["broad_gpcr_family_claim_safe"] is False
    assert packet["owner_input_required"] is True
    assert packet["required_targets"] == ["DRD2", "HTR2A", "OPRM1"]
    assert packet["required_operator_fields"] == [
        "target_id",
        "ranking_pr_auc_ci_low",
        "top20_hit_rate",
        "decoys_above_positive_count",
        "positive_out_anchored_by_top_decoys",
        "score_direction",
        "hard_decoy_rows",
    ]
    assert packet["exit_criteria"] == {
        "decoys_above_positive_count_max": 0,
        "positive_out_anchored_by_top_decoys_allowed": False,
        "ranking_pr_auc_ci_low_min": 0.45,
        "top20_hit_rate_min": 0.2,
    }
    assert [slot["target_id"] for slot in packet["target_slots"]] == [
        "DRD2",
        "HTR2A",
        "OPRM1",
    ]
    assert packet["gate_unblock_plan_count"] == 3
    assert packet["target_execution_preflight_count"] == 3
    assert packet["first_target_execution_preflight_blocker"]["target_id"] == "DRD2"
    assert packet["first_target_execution_preflight_blocker"]["first_blocker"] == (
        "DRD2:hard_decoy_rows_required_for_actual_closure"
    )
    assert packet["minimum_target_count"] == 3
    assert packet["minimum_metric_field_count_per_target"] == 4
    preflight = {row["target_id"]: row for row in packet["target_execution_preflight"]}
    assert set(preflight) == {"DRD2", "HTR2A", "OPRM1"}
    assert preflight["DRD2"]["slot_id"] == "drd2_hard_decoy_metrics"
    assert preflight["DRD2"]["current_ready"] is False
    assert preflight["DRD2"]["phase3_blocked"] is True
    assert preflight["DRD2"]["missing_operator_fields"] == [
        "ranking_pr_auc_ci_low",
        "top20_hit_rate",
        "decoys_above_positive_count",
        "positive_out_anchored_by_top_decoys",
        "score_direction",
        "hard_decoy_rows",
    ]
    assert preflight["DRD2"]["current_values"] == {
        "decoys_above_positive_count": None,
        "hard_decoy_rows": None,
        "positive_out_anchored_by_top_decoys": None,
        "ranking_pr_auc_ci_low": None,
        "score_direction": None,
        "top20_hit_rate": None,
    }
    assert preflight["DRD2"]["blocked_phase3_criteria"] == [
        "ranking_pr_auc_ci_low_min",
        "top20_hit_rate_min",
        "decoys_above_positive_count_max",
        "no_positive_out_anchored_by_top_decoys",
        "raw_hard_decoy_rows_actual_closure",
    ]
    assert preflight["DRD2"]["root_cause_tags"] == [
        "hard_decoy_rows_required",
        "operator_values_required",
    ]
    assert (
        "materialize_gpcr_hard_decoy_suite_report.py"
        in preflight["DRD2"]["materialization_command"]
    )
    gate_plan = {row["target_id"]: row for row in packet["gate_unblock_plan"]}
    assert set(gate_plan) == {"DRD2", "HTR2A", "OPRM1"}
    assert gate_plan["DRD2"]["slot_id"] == "drd2_hard_decoy_metrics"
    assert gate_plan["DRD2"]["unblocks_phase3_criteria"] == [
        "ranking_pr_auc_ci_low_min",
        "top20_hit_rate_min",
        "decoys_above_positive_count_max",
        "no_positive_out_anchored_by_top_decoys",
        "raw_hard_decoy_rows_actual_closure",
    ]
    assert gate_plan["DRD2"]["minimum_evidence"]["required_hard_decoy_row_fields"] == [
        "molecule_id",
        "score",
        "is_positive",
        "is_decoy",
    ]
    assert gate_plan["DRD2"]["minimum_evidence"]["thresholds"] == {
        "decoys_above_positive_count": "<=0",
        "hard_decoy_rows": "computed_from_raw_hard_decoy_rows",
        "positive_out_anchored_by_top_decoys": False,
        "ranking_pr_auc_ci_low": ">=0.45",
        "top20_hit_rate": ">=0.2",
    }
    assert gate_plan["DRD2"]["minimum_evidence"]["criterion_by_field"] == {
        "decoys_above_positive_count": "decoys_above_positive_count_max",
        "hard_decoy_rows": "raw_hard_decoy_rows_actual_closure",
        "positive_out_anchored_by_top_decoys": "no_positive_out_anchored_by_top_decoys",
        "ranking_pr_auc_ci_low": "ranking_pr_auc_ci_low_min",
        "top20_hit_rate": "top20_hit_rate_min",
    }
    assert gate_plan["DRD2"]["materialization_steps"] == [
        "materialize_gpcr_hard_decoy_suite_report",
        "refresh_gpcr_hard_decoy_product_report",
        "refresh_product_capabilities_surface",
        "refresh_goal_bottleneck_roadmap_surface",
    ]
    assert (
        "materialize_gpcr_hard_decoy_suite_report.py"
        in gate_plan["DRD2"]["materialization_command"]
    )
    assert gate_plan["DRD2"]["validation_command"] == gate_plan["DRD2"][
        "materialization_command"
    ]
    assert packet["current_suite_status"]["first_blocked_target"] == "DRD2"
    assert packet["current_suite_status"]["blocker_count"] == 15
    assert packet["summary"]["target_execution_preflight_count"] == 3
    assert packet["summary"]["first_target_execution_preflight_target"] == "DRD2"
    assert packet["summary"]["first_target_execution_preflight_blocker"] == (
        "DRD2:hard_decoy_rows_required_for_actual_closure"
    )


def test_gpcr_hard_decoy_operator_intake_packet_materialization_sequence() -> None:
    packet = module.build_gpcr_hard_decoy_operator_intake_packet(repo_root=REPO_ROOT)

    assert [step["step_id"] for step in packet["materialization_sequence"]] == [
        "fill_gpcr_hard_decoy_operator_template",
        "materialize_gpcr_hard_decoy_suite_report",
        "refresh_gpcr_hard_decoy_product_report",
        "refresh_product_capabilities_surface",
        "refresh_goal_bottleneck_roadmap_surface",
    ]
    assert packet["acceptance_criteria"] == [
        "gpcr_hard_decoy_suite_report.target_pass_count == 3",
        "gpcr_hard_decoy_suite_report.broad_gpcr_family_claim_safe == true",
        "gpcr_hard_decoy_suite_report.blockers == []",
        (
            "gpcr_hard_decoy_suite_report.phase3_exit_gate."
            "raw_hard_decoy_rows_actual_closure == pass"
        ),
        "gpcr_hard_decoy_product_report.science_claim_status == ready",
        "gpcr_hard_decoy_evidence_surface.locked == false",
    ]
    assert packet["next_actions"][0] == "fill_gpcr_hard_decoy_operator_intake_packet"
    assert packet["linked_artifacts"]["operator_template"] == (
        "implementation/phase1/release_evidence/productization/"
        "gpcr_hard_decoy_operator_template.json"
    )
    assert packet["target_slots"][0]["template_artifact"] == (
        "implementation/phase1/release_evidence/productization/"
        "gpcr_hard_decoy_operator_template.json"
    )
    assert packet["gate_unblock_plan"][0]["template_artifact"] == (
        "implementation/phase1/release_evidence/productization/"
        "gpcr_hard_decoy_operator_template.json"
    )


def test_gpcr_hard_decoy_operator_intake_packet_cli_writes_json_and_markdown(
    tmp_path: Path,
) -> None:
    out = tmp_path / "gpcr_hard_decoy_operator_intake_packet.json"
    out_md = tmp_path / "gpcr_hard_decoy_operator_intake_packet.md"

    assert module.main(["--repo-root", str(REPO_ROOT), "--out", str(out), "--out-md", str(out_md)]) == 0

    payload = json.loads(out.read_text(encoding="utf-8"))
    markdown = out_md.read_text(encoding="utf-8")
    assert payload["input_checksums"][
        "scripts/build_gpcr_hard_decoy_operator_intake_packet.py"
    ].startswith("sha256:")
    assert payload["packet_id"] == "gpcr_hard_decoy_operator_intake_packet"
    assert "# GPCR Hard-Decoy Operator Intake Packet" in markdown
    assert "## Gate Unblock Plan" in markdown
    assert "## Target Execution Preflight" in markdown
    assert "materialize_gpcr_hard_decoy_suite_report" in markdown
