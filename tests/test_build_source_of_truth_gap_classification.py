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
        "aggregator_review_count": 3,
        "aggregator_reviewed_count": 3,
        "blocker_count": 0,
        "candidate_count": 5,
        "expected_candidate_count": 5,
        "fix_count": 2,
        "fixed_count": 2,
        "no_op_count": 0,
    }
    assert set(rows) == module.EXPECTED_CANDIDATES

    accuracy = rows["accuracy_parity_scorecard"]
    assert accuracy["classification"] == "fix"
    assert accuracy["freshness_label"] == "accuracy_parity_scorecard"
    assert accuracy["live_checks"]["freshness_leaf_presence_matches"] is True
    assert accuracy["live_checks"]["accuracy_scorecard_science_contract_pass"] is True
    assert all(
        accuracy["live_checks"]["accuracy_scorecard_science_checks"].values()
    )

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


def test_source_of_truth_gap_classification_cli_writes_artifact(tmp_path: Path) -> None:
    out = tmp_path / "source_of_truth_gap_classification.json"

    assert module.main(["--repo-root", str(REPO_ROOT), "--out", str(out)]) == 0

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["summary"]["candidate_count"] == 5
    assert payload["input_checksums"][
        "scripts/build_source_of_truth_gap_classification.py"
    ].startswith("sha256:")
