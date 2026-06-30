from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "materialize_gpcr_hard_decoy_suite_report.py"
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

spec = importlib.util.spec_from_file_location("materialize_gpcr_hard_decoy_suite_report", SCRIPT_PATH)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def _passing_target(target_id: str) -> dict[str, object]:
    return {
        "target_id": target_id,
        "ranking_pr_auc_ci_low": 0.46,
        "top20_hit_rate": 0.20,
        "decoys_above_positive_count": 0,
        "positive_out_anchored_by_top_decoys": False,
    }


def _positive_first_hard_decoy_rows() -> list[dict[str, object]]:
    return [
        {"molecule_id": "positive_1", "score": 0.95, "is_positive": True, "is_decoy": False},
        {"molecule_id": "positive_2", "score": 0.90, "is_positive": True, "is_decoy": False},
        {"molecule_id": "positive_3", "score": 0.85, "is_positive": True, "is_decoy": False},
        {"molecule_id": "decoy_1", "score": 0.40, "is_positive": False, "is_decoy": True},
        {"molecule_id": "decoy_2", "score": 0.10, "is_positive": False, "is_decoy": True},
    ]


def _decoy_first_hard_decoy_rows() -> list[dict[str, object]]:
    return [
        {"molecule_id": "decoy_1", "score": 0.99, "is_positive": False, "is_decoy": True},
        {"molecule_id": "positive_1", "score": 0.90, "is_positive": True, "is_decoy": False},
        {"molecule_id": "positive_2", "score": 0.85, "is_positive": True, "is_decoy": False},
        {"molecule_id": "decoy_2", "score": 0.20, "is_positive": False, "is_decoy": True},
        {"molecule_id": "decoy_3", "score": 0.10, "is_positive": False, "is_decoy": True},
    ]


def _passing_target_from_rows(target_id: str) -> dict[str, object]:
    return {
        "target_id": target_id,
        "ranking_pr_auc_ci_low": 0.80,
        "score_direction": "higher_is_better",
        "hard_decoy_rows": _positive_first_hard_decoy_rows(),
    }


def test_gpcr_hard_decoy_suite_passes_required_targets() -> None:
    report = module.materialize_gpcr_hard_decoy_suite_report(
        {"targets": [_passing_target("DRD2"), _passing_target("HTR2A"), _passing_target("OPRM1")]},
        repo_root=REPO_ROOT,
    )

    assert report["status"] == "ready"
    assert report["contract_pass"] is True
    assert report["broad_gpcr_family_claim_safe"] is True
    assert report["target_pass_count"] == 3
    assert report["first_blocked_target"] == ""
    assert report["first_blocker"] == ""
    assert report["blockers"] == []
    assert report["operator_evidence_gap_count"] == 0
    assert report["first_operator_evidence_gap"] == {}
    assert report["operator_handoff_summary"]["first_blocker"] == ""
    assert report["operator_handoff_summary"]["blocked_operator_slot_count"] == 0
    assert report["phase3_exit_gate"]["status"] == "ready"
    assert report["phase3_exit_gate"]["failed_criterion_count"] == 0
    assert report["phase3_exit_gate"]["failed_criteria"] == []
    assert {
        row["criterion_id"]: row["pass"]
        for row in report["phase3_exit_gate"]["criteria"]
    } == {
        "ranking_pr_auc_ci_low_min": True,
        "top20_hit_rate_min": True,
        "decoys_above_positive_count_max": True,
        "no_positive_out_anchored_by_top_decoys": True,
    }


def test_gpcr_hard_decoy_suite_derives_metrics_from_raw_hard_decoy_rows() -> None:
    report = module.materialize_gpcr_hard_decoy_suite_report(
        {
            "targets": [
                _passing_target_from_rows("DRD2"),
                _passing_target_from_rows("HTR2A"),
                _passing_target_from_rows("OPRM1"),
            ]
        },
        repo_root=REPO_ROOT,
    )

    assert report["status"] == "ready"
    assert report["broad_gpcr_family_claim_safe"] is True
    first_row = report["target_rows"][0]
    assert first_row["top20_hit_rate"] == 0.6
    assert first_row["decoys_above_positive_count"] == 0
    assert first_row["positive_out_anchored_by_top_decoys"] is False
    assert first_row["computed_hard_decoy_metrics"]["ranking_pr_auc"] == 1.0
    assert first_row["computed_hard_decoy_metrics"]["calculation_status"] == "computed"


def test_gpcr_hard_decoy_suite_blocks_metrics_that_conflict_with_raw_rows() -> None:
    conflicting_drd2 = {
        **_passing_target("DRD2"),
        "hard_decoy_rows": _decoy_first_hard_decoy_rows(),
    }
    report = module.materialize_gpcr_hard_decoy_suite_report(
        {
            "targets": [
                conflicting_drd2,
                _passing_target("HTR2A"),
                _passing_target("OPRM1"),
            ]
        },
        repo_root=REPO_ROOT,
    )

    assert report["status"] == "locked"
    assert report["first_blocked_target"] == "DRD2"
    assert (
        "DRD2:decoys_above_positive_count_inconsistent_with_hard_decoy_rows"
        in report["blockers"]
    )
    assert (
        "DRD2:positive_out_anchored_by_top_decoys_inconsistent_with_hard_decoy_rows"
        in report["blockers"]
    )
    assert "hard_decoy_metric_inconsistency" in report["root_cause_tags"]


def test_gpcr_hard_decoy_suite_blocks_missing_operator_values() -> None:
    report = module.materialize_gpcr_hard_decoy_suite_report({"targets": []}, repo_root=REPO_ROOT)

    assert report["status"] == "locked"
    assert report["broad_gpcr_family_claim_safe"] is False
    assert report["first_blocked_target"] == "DRD2"
    assert report["first_blocker"] == "DRD2:operator_metrics_required"
    assert report["root_cause_tags"] == ["operator_values_required"]
    assert "DRD2:ranking_pr_auc_ci_low_required" in report["blockers"]
    assert "OPRM1:positive_out_anchored_by_top_decoys_required" in report["blockers"]
    assert report["operator_intake_route"] == (
        "/product/gpcr-hard-decoy-suite-report/operator-intake"
    )
    assert report["operator_intake_required_slot_count"] == 3
    assert report["operator_evidence_gap_count"] == 3
    assert report["first_operator_evidence_gap"]["slot_id"] == (
        "drd2_hard_decoy_metrics"
    )
    assert report["first_operator_evidence_gap"]["target_id"] == "DRD2"
    assert report["first_operator_evidence_gap"]["blocked_phase3_criteria"] == [
        "ranking_pr_auc_ci_low_min",
        "top20_hit_rate_min",
        "decoys_above_positive_count_max",
        "no_positive_out_anchored_by_top_decoys",
    ]
    assert report["operator_handoff_summary"]["first_blocker"] == (
        "DRD2:operator_metrics_required"
    )
    assert report["operator_handoff_summary"]["first_blocked_target"] == "DRD2"
    assert report["operator_handoff_summary"]["first_next_action"] == (
        "fill DRD2 hard-decoy metrics in the GPCR operator intake packet"
    )
    assert report["operator_handoff_summary"]["blocked_operator_slot_count"] == 3
    assert report["operator_handoff_summary"]["minimum_evidence"]["target_id"] == "DRD2"
    assert report["phase3_exit_gate"]["status"] == "blocked"
    assert report["phase3_exit_gate"]["failed_criterion_count"] == 4
    assert report["phase3_exit_gate"]["failed_criteria"] == [
        "ranking_pr_auc_ci_low_min",
        "top20_hit_rate_min",
        "decoys_above_positive_count_max",
        "no_positive_out_anchored_by_top_decoys",
    ]
    ranking_gate = report["phase3_exit_gate"]["criteria"][0]
    assert ranking_gate["failed_targets"] == ["DRD2", "HTR2A", "OPRM1"]
    assert ranking_gate["required"] == ">=0.45"


def test_gpcr_hard_decoy_suite_reports_threshold_root_causes() -> None:
    report = module.materialize_gpcr_hard_decoy_suite_report(
        {
            "targets": [
                {
                    "target_id": "DRD2",
                    "ranking_pr_auc_ci_low": 0.44,
                    "top20_hit_rate": 0.19,
                    "decoys_above_positive_count": 1,
                    "positive_out_anchored_by_top_decoys": True,
                },
                _passing_target("HTR2A"),
                _passing_target("OPRM1"),
            ]
        },
        repo_root=REPO_ROOT,
    )

    assert report["first_blocked_target"] == "DRD2"
    assert report["root_cause_tags"] == [
        "ranking_pr_auc_ci_low_below_threshold",
        "top20_hit_rate_below_threshold",
        "decoy_rank_leakage",
        "positive_out_anchored_by_top_decoys",
    ]
    drd2 = report["target_rows"][0]
    assert drd2["status"] == "blocked"
    assert drd2["blockers"] == [
        "DRD2:ranking_pr_auc_ci_low_below_threshold",
        "DRD2:top20_hit_rate_below_threshold",
        "DRD2:decoys_above_positive_count_above_limit",
        "DRD2:positive_out_anchored_by_top_decoys",
    ]
    assert report["phase3_exit_gate"]["failed_criteria"] == [
        "ranking_pr_auc_ci_low_min",
        "top20_hit_rate_min",
        "decoys_above_positive_count_max",
        "no_positive_out_anchored_by_top_decoys",
    ]
    assert report["phase3_exit_gate"]["criteria"][0]["failed_targets"] == ["DRD2"]


def test_gpcr_hard_decoy_suite_cli_writes_report_and_surface(tmp_path: Path) -> None:
    intake = tmp_path / "gpcr_intake.json"
    intake.write_text(json.dumps({"targets": []}), encoding="utf-8")
    out_report = tmp_path / "gpcr_report.json"
    out_surface = tmp_path / "gpcr_surface.json"

    assert (
        module.main(
            [
                "--intake",
                str(intake),
                "--out-report",
                str(out_report),
                "--out-surface",
                str(out_surface),
                "--repo-root",
                str(REPO_ROOT),
            ]
        )
        == 0
    )

    report = json.loads(out_report.read_text(encoding="utf-8"))
    surface = json.loads(out_surface.read_text(encoding="utf-8"))
    assert report["status"] == "locked"
    assert surface["surface_id"] == "gpcr_hard_decoy_evidence_surface"
    assert surface["locked"] is True
    assert surface["first_blocked_target"] == "DRD2"
    assert surface["first_blocker"] == "DRD2:operator_metrics_required"
    assert surface["root_cause_tags"] == ["operator_values_required"]
    assert surface["phase3_exit_gate"]["status"] == "blocked"
    assert surface["phase3_exit_gate"]["failed_criterion_count"] == 4
    assert surface["operator_intake_route"] == (
        "/product/gpcr-hard-decoy-suite-report/operator-intake"
    )
    assert surface["operator_intake_required_slot_count"] == 3
    assert surface["operator_evidence_gap_count"] == 3
    assert surface["first_operator_evidence_gap"]["slot_id"] == (
        "drd2_hard_decoy_metrics"
    )
    assert surface["first_operator_evidence_gap"]["target_id"] == "DRD2"
    assert surface["first_operator_evidence_gap"]["blocked_phase3_criteria"] == [
        "ranking_pr_auc_ci_low_min",
        "top20_hit_rate_min",
        "decoys_above_positive_count_max",
        "no_positive_out_anchored_by_top_decoys",
    ]
    assert surface["operator_handoff_summary"] == {
        "route": "/product/gpcr-hard-decoy-suite-report/operator-intake",
        "artifact": (
            "implementation/phase1/release_evidence/productization/"
            "gpcr_hard_decoy_operator_intake_packet.json"
        ),
        "first_blocker": "DRD2:operator_metrics_required",
        "first_blocked_target": "DRD2",
        "first_next_action": (
            "fill DRD2 hard-decoy metrics in the GPCR operator intake packet"
        ),
        "required_slot_count": 3,
        "blocked_operator_slot_count": 3,
        "minimum_evidence": {
            "target_id": "DRD2",
            "required_operator_fields": [
                "target_id",
                "ranking_pr_auc_ci_low",
                "top20_hit_rate",
                "decoys_above_positive_count",
                "positive_out_anchored_by_top_decoys",
            ],
            "thresholds": {
                "ranking_pr_auc_ci_low": ">=0.45",
                "top20_hit_rate": ">=0.2",
                "decoys_above_positive_count": "<=0",
                "positive_out_anchored_by_top_decoys": False,
            },
            "criterion_by_field": {
                "ranking_pr_auc_ci_low": "ranking_pr_auc_ci_low_min",
                "top20_hit_rate": "top20_hit_rate_min",
                "decoys_above_positive_count": "decoys_above_positive_count_max",
                "positive_out_anchored_by_top_decoys": (
                    "no_positive_out_anchored_by_top_decoys"
                ),
            },
        },
        "materialization_steps": [
            "materialize_gpcr_hard_decoy_suite_report",
            "refresh_gpcr_hard_decoy_product_report",
            "refresh_product_capabilities_surface",
            "refresh_goal_bottleneck_roadmap_surface",
        ],
        "materialization_command": (
            "python3 scripts/materialize_gpcr_hard_decoy_suite_report.py "
            "--intake implementation/phase1/release_evidence/productization/"
            "gpcr_hard_decoy_operator_template.json "
            "--out-report implementation/phase1/release_evidence/productization/"
            "gpcr_hard_decoy_suite_report.json "
            "--out-surface implementation/phase1/release_evidence/surface/"
            "gpcr_hard_decoy_evidence_surface.json --fail-blocked"
        ),
        "validation_command": (
            "python3 scripts/materialize_gpcr_hard_decoy_suite_report.py "
            "--intake implementation/phase1/release_evidence/productization/"
            "gpcr_hard_decoy_operator_template.json "
            "--out-report implementation/phase1/release_evidence/productization/"
            "gpcr_hard_decoy_suite_report.json "
            "--out-surface implementation/phase1/release_evidence/surface/"
            "gpcr_hard_decoy_evidence_surface.json --fail-blocked"
        ),
    }
    assert surface["next_actions"] == [
        "fill_gpcr_hard_decoy_operator_intake_packet",
        "fill_drd2_htr2a_oprm1_operator_template_values",
        "run_gpcr_hard_decoy_suite_materializer",
        "refresh_gpcr_hard_decoy_product_report",
        "regenerate_product_capabilities_surface",
        "regenerate_goal_bottleneck_roadmap_surface",
    ]
