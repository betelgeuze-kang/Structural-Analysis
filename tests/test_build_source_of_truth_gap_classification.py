from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_source_of_truth_gap_classification.py"
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

spec = importlib.util.spec_from_file_location(
    "build_source_of_truth_gap_classification",
    SCRIPT_PATH,
)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def test_source_of_truth_gap_classification_materializes_live_scan() -> None:
    payload = module.build_source_of_truth_gap_classification(repo_root=REPO_ROOT)
    rows = {row["candidate"]: row for row in payload["rows"]}

    assert payload["schema_version"] == "source-of-truth-gap-classification.v1"
    assert payload["status"] == "ready"
    assert payload["contract_pass"] is True
    assert payload["summary"] == {
        "accuracy_parity_scorecard_science_contract_pass": True,
        "aggregator_review_count": 3,
        "aggregator_reviewed_count": 3,
        "blocker_count": 0,
        "candidate_count": 5,
        "classification_bucket_count": 3,
        "completion_audit_pass": True,
        "completion_audit_requirement_count": 6,
        "completion_audit_requirement_pass_count": 6,
        "classification_evidence_matrix_count": 5,
        "classification_evidence_matrix_pass_count": 5,
        "classification_index_candidate_count": 5,
        "expected_candidate_count": 5,
        "fix_count": 2,
        "fixed_count": 2,
        "no_op_count": 0,
        "operator_action_count": 5,
    }
    assert payload["expected_candidates"] == list(module.EXPECTED_CANDIDATE_ORDER)
    assert set(rows) == module.EXPECTED_CANDIDATES
    assert payload["classification_rows"] == payload["rows"]
    assert set(payload["classification_by_candidate"]) == module.EXPECTED_CANDIDATES
    assert set(payload["classification_index"]) == module.EXPECTED_CANDIDATES
    evidence_matrix = {
        row["candidate"]: row for row in payload["classification_evidence_matrix"]
    }
    assert set(evidence_matrix) == module.EXPECTED_CANDIDATES
    assert len(payload["operator_actions"]) == 5
    assert payload["operator_action_index"] == {
        "accuracy_parity_scorecard": (
            "keep_accuracy_parity_scorecard_as_direct_freshness_leaf"
        ),
        "goal_operator_action_board": (
            "review_goal_operator_action_board_upstream_source_tracking"
        ),
        "goal_readiness_rollup": (
            "review_goal_readiness_rollup_upstream_source_tracking"
        ),
        "product_goal_completion_audit": (
            "review_product_goal_completion_audit_upstream_source_tracking"
        ),
        "product_production_ai_checkpoint_readiness": (
            "keep_product_production_ai_checkpoint_readiness_as_direct_freshness_leaf"
        ),
    }
    assert payload["completion_audit"]["status"] == "pass"
    assert payload["completion_audit"]["pass"] is True
    assert payload["completion_audit"]["blockers"] == []
    assert [
        row["requirement_id"] for row in payload["completion_audit"]["requirements"]
    ] == [
        "expected_candidate_set_complete",
        "direct_fix_candidates_verified",
        "aggregator_review_candidates_verified",
        "no_noop_candidates_required_or_found",
        "accuracy_parity_priority_review_verified",
        "operator_actions_complete",
    ]
    assert all(row["pass"] for row in payload["completion_audit"]["requirements"])
    assert payload["classification_by_bucket"] == {
        "aggregator-review": {
            "candidate_ids": [
                "goal_readiness_rollup",
                "product_goal_completion_audit",
                "goal_operator_action_board",
            ],
            "contract_pass_count": 3,
            "count": 3,
        },
        "fix": {
            "candidate_ids": [
                "accuracy_parity_scorecard",
                "product_production_ai_checkpoint_readiness",
            ],
            "contract_pass_count": 2,
            "count": 2,
        },
        "no-op": {
            "candidate_ids": [],
            "contract_pass_count": 0,
            "count": 0,
        },
    }

    accuracy = rows["accuracy_parity_scorecard"]
    assert accuracy["classification"] == "fix"
    assert accuracy["freshness_label"] == "accuracy_parity_scorecard"
    assert accuracy["live_checks"]["freshness_leaf_presence_matches"] is True
    assert accuracy["live_checks"]["accuracy_scorecard_science_contract_pass"] is True
    assert all(
        accuracy["live_checks"]["accuracy_scorecard_science_checks"].values()
    )
    assert payload["classification_index"]["accuracy_parity_scorecard"] == {
        "accuracy_scorecard_science_contract_pass": True,
        "candidate": "accuracy_parity_scorecard",
        "classification": "fix",
        "contract_pass": True,
        "current_repo_paths": [
            "implementation/phase1/real_accuracy_validation_report.json"
        ],
        "freshness_label": "accuracy_parity_scorecard",
        "freshness_policy": "direct_leaf_row",
        "operator_action": (
            "keep_accuracy_parity_scorecard_as_direct_freshness_leaf"
        ),
        "priority_rank": 1,
        "science_scorecard_priority_review": True,
        "status": "classified",
    }
    assert evidence_matrix["accuracy_parity_scorecard"] == {
        "candidate": "accuracy_parity_scorecard",
        "claim_boundary": (
            "This matrix row is classification evidence only. It does not "
            "replace the referenced leaf validation, aggregator receipt, "
            "or owner review."
        ),
        "classification": "fix",
        "contract_pass": True,
        "current_repo_path_presence": {
            "implementation/phase1/real_accuracy_validation_report.json": True
        },
        "current_repo_paths": [
            "implementation/phase1/real_accuracy_validation_report.json"
        ],
        "failed_live_checks": [],
        "freshness_label": "accuracy_parity_scorecard",
        "freshness_policy": "direct_leaf_row",
        "live_check_keys": [
            "accuracy_scorecard_science_checks",
            "accuracy_scorecard_science_contract_pass",
            "candidate_expected",
            "current_repo_match_present",
            "freshness_leaf_presence_matches",
            "metadata_present_on_current_matches",
        ],
        "operator_action": (
            "keep_accuracy_parity_scorecard_as_direct_freshness_leaf"
        ),
        "science_scorecard_priority_review": True,
        "source_tracking_mode": "direct_freshness_leaf",
        "source_tracking_requirement": (
            "candidate must be present in release freshness leaf rows and "
            "the matched artifact must expose source tracking metadata"
        ),
        "source_tracking_verified": True,
        "status": "classified",
        "validation_basis": [
            "leaf_artifact_in_default_freshness_rows",
            "science_scorecard_overall_pass_field",
            "benchmark_contract_and_kpi_fields",
            "public_hf_and_source_family_checks",
            "stability_suite_pass_field",
        ],
    }
    assert payload["accuracy_parity_scorecard_priority_review"] == {
        "candidate": "accuracy_parity_scorecard",
        "claim_boundary": (
            "Accuracy parity is treated as a direct science scorecard fix only "
            "because the live scorecard exposes and passes the required science "
            "checks. This review does not rerun the heavy validation."
        ),
        "classification": "fix",
        "contract_pass": True,
        "current_repo_paths": [
            "implementation/phase1/real_accuracy_validation_report.json"
        ],
        "decision": (
            "Direct science scorecard receipt with freshness source tracking; "
            "the artifact itself carries overall_pass, benchmark contract/KPI pass, "
            "direct-metric/source-family/public-HF checks, and stability-suite pass."
        ),
        "operator_action": (
            "keep_accuracy_parity_scorecard_as_direct_freshness_leaf"
        ),
        "science_checks": {
            "benchmark_contract_pass": True,
            "benchmark_kpi_pass": True,
            "direct_metric_source_pass": True,
            "overall_pass": True,
            "public_hf_case_count_pass": True,
            "source_family_pass": True,
            "stability_pass": True,
            "stability_suite_pass": True,
        },
        "science_contract_pass": True,
        "status": "classified",
        "validation_basis": [
            "leaf_artifact_in_default_freshness_rows",
            "science_scorecard_overall_pass_field",
            "benchmark_contract_and_kpi_fields",
            "public_hf_and_source_family_checks",
            "stability_suite_pass_field",
        ],
    }

    ai = rows["product_production_ai_checkpoint_readiness"]
    assert ai["classification"] == "fix"
    assert ai["live_checks"]["ai_contract_status_ready"] is True

    for candidate in (
        "goal_readiness_rollup",
        "product_goal_completion_audit",
        "goal_operator_action_board",
    ):
        row = rows[candidate]
        assert row["classification"] == "aggregator-review"
        assert row["freshness_label"] == ""
        assert row["live_checks"]["freshness_leaf_presence_matches"] is True
        assert row["live_checks"]["aggregator_source_tracking_present"] is True
        assert evidence_matrix[candidate]["source_tracking_mode"] == (
            "aggregator_upstream_source_tracking"
        )
        assert evidence_matrix[candidate]["source_tracking_verified"] is True
        assert evidence_matrix[candidate]["failed_live_checks"] == []
        assert payload["classification_index"][candidate]["operator_action"] == (
            f"review_{candidate}_upstream_source_tracking"
        )


def test_source_of_truth_gap_classification_cli_writes_artifact(tmp_path: Path) -> None:
    out = tmp_path / "source_of_truth_gap_classification.json"

    assert module.main(["--repo-root", str(REPO_ROOT), "--out", str(out)]) == 0

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["summary"]["candidate_count"] == 5
    assert payload["classification_by_bucket"]["fix"]["count"] == 2
    assert payload["classification_by_bucket"]["aggregator-review"]["count"] == 3
    assert payload["summary"]["classification_evidence_matrix_count"] == 5
    assert payload["summary"]["classification_evidence_matrix_pass_count"] == 5
    assert payload["summary"]["completion_audit_pass"] is True
    assert payload["completion_audit"]["requirement_pass_count"] == 6
    assert payload["classification_index"]["accuracy_parity_scorecard"][
        "science_scorecard_priority_review"
    ] is True
    assert payload["classification_evidence_matrix"][0]["candidate"] == (
        "accuracy_parity_scorecard"
    )
    assert payload["operator_actions"][0]["candidate"] == "accuracy_parity_scorecard"
    assert payload["input_checksums"][
        "scripts/build_source_of_truth_gap_classification.py"
    ].startswith("sha256:")
