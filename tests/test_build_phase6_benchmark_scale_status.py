from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts/build_phase6_benchmark_scale_status.py"
for candidate in (REPO_ROOT / "scripts", REPO_ROOT / "src"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

spec = importlib.util.spec_from_file_location("build_phase6_benchmark_scale_status", SCRIPT_PATH)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def test_phase6_benchmark_scale_status_blocks_without_medium_large_evidence() -> None:
    payload = module.build_phase6_benchmark_scale_status(repo_root=REPO_ROOT)

    assert payload["schema_version"] == "phase6-benchmark-scale-status.v1"
    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is False
    assert payload["developer_preview_release_candidate_claim"] is False
    assert payload["seed_benchmark_status"] == "ready"
    medium = payload["medium_gate"]
    assert medium["status"] == "blocked"
    assert medium["contract_pass"] is False
    assert medium["required_medium_model_count"] == 5
    assert medium["current_medium_model_scorecard_count"] == 0
    assert medium["pass_or_approved_review_count"] == 0
    assert medium["local_candidate_artifact_count"] == 2
    assert medium["local_topology_contract_pass"] is True
    assert medium["required_evidence_count"] == 9
    assert medium["required_evidence_pass_count"] == 4
    assert medium["case_ready_count"] == 0
    medium_progress = medium["progress_partition"]
    assert medium_progress["schema_version"] == (
        "phase6-medium-benchmark-progress-partition.v1"
    )
    assert medium_progress["local_candidate_selection"] == {
        "contract_pass": False,
        "current": 2,
        "label": "parser/topology candidate cases selected",
        "remaining": 3,
        "required": 5,
    }
    assert medium_progress["scorecard_execution"]["current"] == 0
    assert medium_progress["scorecard_execution"]["remaining"] == 5
    assert medium_progress["pass_or_approved_review"]["current"] == 0
    assert medium_progress["case_ready_for_credit"]["current"] == 0
    assert medium_progress["evidence_contract"]["current"] == 4
    assert "Only the scorecard and review counts" in medium_progress["claim_boundary"]
    medium_actions = {row["id"]: row for row in medium["operator_next_actions"]}
    assert set(medium_actions) == {
        "select_additional_medium_model_cases",
        "complete_product_legal_license_review",
        "attach_medium_reference_outputs",
        "record_medium_canonical_normalization",
        "run_medium_scorecard_receipts",
        "attach_medium_pass_or_approved_review_decisions",
    }
    assert medium_actions["run_medium_scorecard_receipts"]["lane"] == "opensees-medium"
    assert (
        medium_actions["run_medium_scorecard_receipts"]["remaining_case_count"] == 5
    )
    assert "medium_structural_models_current_below_required:0/5" in medium["blockers"]
    assert "medium_model_pass_or_review_below_required:0/5" in medium["blockers"]
    assert "opensees_medium_scorecard_execution_missing" in medium["blockers"]
    medium_grouping = medium["blocker_grouping_metadata"]
    assert medium_grouping["schema_version"] == "phase6-benchmark-scale-blocker-groups.v1"
    assert medium_grouping["blocker_count"] == len(medium["blockers"])
    assert medium_grouping["unassigned_blockers"] == []
    assert "opensees_medium_scorecard_execution_missing" in medium_grouping[
        "groups"
    ]["medium_scorecard_execution"]["blockers"]
    assert "medium_structural_models_current_below_required:0/5" in medium_grouping[
        "groups"
    ]["medium_quantity_shortfall"]["blockers"]
    large = payload["large_gate"]
    assert large["status"] == "blocked"
    assert large["contract_pass"] is False
    assert large["required_large_model_count"] == 2
    assert large["current_large_source_model_count"] == 2
    assert large["current_large_model_execution_receipt_count"] == 2
    assert large["crash_oom_free_execution_count"] == 2
    assert large["scorecard_or_review_count"] == 0
    assert large["source_url_verified_count"] == 2
    assert large["source_checksum_count"] == 2
    large_progress = large["progress_partition"]
    assert large_progress["schema_version"] == (
        "phase6-large-benchmark-progress-partition.v1"
    )
    assert large_progress["execution_receipts"]["contract_pass"] is True
    assert large_progress["crash_oom_free"]["contract_pass"] is True
    assert large_progress["scorecard_or_review"] == {
        "contract_pass": False,
        "current": 0,
        "label": "large scorecard or approved review decisions",
        "remaining": 2,
        "required": 2,
    }
    large_actions = {row["id"]: row for row in large["operator_next_actions"]}
    assert large_actions["attach_large_scorecard_or_approved_review"]["lane"] == (
        "opensees-large"
    )
    assert (
        large_actions["attach_large_scorecard_or_approved_review"][
            "remaining_case_count"
        ]
        == 2
    )
    assert "large_structural_models_current_below_required:0/2" not in large["blockers"]
    assert "large_model_execution_count_below_required:0/2" not in large["blockers"]
    assert "large_model_crash_oom_free_count_below_required:0/2" not in large["blockers"]
    assert "large_model_runner_not_implemented" not in large["blockers"]
    assert "large_model_execution_receipt_missing" not in large["blockers"]
    assert "large_model_scorecard_or_review_missing" in large["blockers"]
    assert "large_model_scorecard_or_review_count_below_required:0/2" in large["blockers"]
    large_grouping = large["blocker_grouping_metadata"]
    assert large_grouping["schema_version"] == "phase6-benchmark-scale-blocker-groups.v1"
    assert large_grouping["blocker_count"] == len(large["blockers"])
    assert large_grouping["unassigned_blockers"] == []
    assert "large_model_scorecard_or_review_missing" in large_grouping["groups"][
        "large_runner_execution"
    ]["blockers"]
    assert "large_model_scorecard_or_review_count_below_required:0/2" in large_grouping[
        "groups"
    ]["large_quantity_shortfall"]["blockers"]
    assert "large_structural_models_current_below_required:0/2" not in large_grouping[
        "groups"
    ]["large_quantity_shortfall"]["blockers"]
    grouping = payload["blocker_grouping_metadata"]
    assert grouping["blocker_count"] == len(payload["blockers"])
    assert grouping["unassigned_blockers"] == []
    assert grouping["groups"]["source_license_identity"]["blocker_count"] == 1
    assert payload["summary"] == {
        "large_crash_oom_free": "2/2",
        "large_execution_receipts": "2/2",
        "large_scorecard_or_review": "0/2",
        "medium_local_candidates": "2/5",
        "medium_pass_or_review": "0/5",
        "medium_scorecard_receipts": "0/5",
        "operator_next_action_count": 10,
    }
    assert "run_medium_scorecard_receipts" in payload["next_actions"]
    assert "attach_large_scorecard_or_approved_review" in payload["next_actions"]
    assert len(payload["operator_next_actions"]) == 10
    assert "parser-only topology evidence" in payload["claim_boundary"]
    assert "policy-only acquisition rows" in payload["claim_boundary"]


def test_phase6_benchmark_scale_status_check_detects_missing_output(tmp_path: Path) -> None:
    ok, message = module.check_phase6_benchmark_scale_status(
        repo_root=REPO_ROOT,
        out_path=tmp_path / "missing.json",
    )

    assert ok is False
    assert message.startswith("phase6_benchmark_scale_status_missing:")


def test_phase6_benchmark_scale_status_check_detects_drift(tmp_path: Path) -> None:
    out = tmp_path / "scale.json"
    module.write_phase6_benchmark_scale_status(repo_root=REPO_ROOT, out_path=out)
    payload = json.loads(out.read_text(encoding="utf-8"))
    payload["contract_pass"] = True
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    ok, message = module.check_phase6_benchmark_scale_status(repo_root=REPO_ROOT, out_path=out)

    assert ok is False
    assert message == "phase6_benchmark_scale_status_mismatch"
