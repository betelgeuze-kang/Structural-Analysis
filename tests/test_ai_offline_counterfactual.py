from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from scripts.build_ai_shadow_counterfactual_artifacts import (
    DATASET_PATH,
    SCORECARD_PATH,
    build_sources,
)
from structural_analysis.ai.offline_counterfactual import (
    OfflineCounterfactualError,
    build_offline_counterfactual_dataset,
    build_shadow_policy_scorecard,
    validate_offline_counterfactual_dataset,
    validate_shadow_policy_scorecard,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def built_artifacts():
    sources = build_sources()
    dataset = build_offline_counterfactual_dataset(sources)
    scorecard = build_shadow_policy_scorecard(dataset)
    return sources, dataset.to_dict(), scorecard.to_dict()


def _rehash_row(row: dict) -> None:
    row["row_hash"] = canonical_hash(
        {key: value for key, value in row.items() if key != "row_hash"}
    )


def _rehash_dataset(dataset: dict, *, lineage_changed: bool = False) -> None:
    if lineage_changed:
        dataset["lineage_root_hash"] = canonical_hash(
            {
                "sources": dataset["sources"],
                "outcome_hashes": sorted(
                    row["lineage"]["counterfactual_outcome_hash"]
                    for row in dataset["rows"]
                    if row["lineage"]["counterfactual_outcome_hash"] is not None
                ),
            }
        )
    dataset["dataset_hash"] = canonical_hash(
        {key: value for key, value in dataset.items() if key != "dataset_hash"}
    )


def _rehash_scorecard(scorecard: dict) -> None:
    scorecard["scorecard_hash"] = canonical_hash(
        {key: value for key, value in scorecard.items() if key != "scorecard_hash"}
    )


def test_rebuild_matches_committed_artifacts_and_validates(built_artifacts) -> None:
    _, dataset, scorecard = built_artifacts

    assert dataset == json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    assert scorecard == json.loads(SCORECARD_PATH.read_text(encoding="utf-8"))
    assert validate_offline_counterfactual_dataset(dataset) == dataset
    assert validate_shadow_policy_scorecard(scorecard) == scorecard
    assert DATASET_PATH.is_relative_to(ROOT)
    assert SCORECARD_PATH.is_relative_to(ROOT)


def test_dataset_is_split_safe_evaluation_only_and_fully_lineaged(
    built_artifacts,
) -> None:
    sources, dataset, _ = built_artifacts

    assert dataset["source_kind"] == "repository_generated_contract_fixture"
    assert dataset["split_counts"] == {
        "calibration": 4,
        "validation": 4,
        "holdout": 4,
    }
    assert dataset["source_count"] == len(sources) == 3
    assert dataset["eligible_proposal_count"] == 12
    assert dataset["evaluated_counterfactual_count"] == 12
    assert dataset["missing_counterfactual_count"] == 0
    assert dataset["identical_action_proposal_count"] == 3
    assert all(dataset["leakage_checks"].values())
    assert dataset["data_use"] == {
        "training_eligible": False,
        "evaluation_only": True,
        "raw_customer_payload_included": False,
    }
    assert dataset["executed_ai_action_count"] == 0
    assert dataset["ai_action_executed"] is False
    assert dataset["result_authority"] is False
    assert dataset["guarded_execution_eligible"] is False
    assert dataset["empirical_performance_claim"] is False

    groups: dict[str, str] = {}
    models: dict[str, str] = {}
    problems: dict[str, str] = {}
    states: dict[str, str] = {}
    feature_columns = set(dataset["feature_columns"])
    for row in dataset["rows"]:
        split = row["split"]
        group = row["model_group_id"]
        model = row["lineage"]["model_ir_content_hash"]
        problem = row["lineage"]["problem_contract_hash"]
        state = row["lineage"]["observation_state_hash"]
        assert groups.setdefault(group, split) == split
        assert models.setdefault(model, split) == split
        assert problems.setdefault(problem, split) == split
        assert states.setdefault(state, split) == split
        assert set(row["features"]) == feature_columns
        assert not ({"baseline", "counterfactual", "comparison"} & feature_columns)
        assert (
            row["lineage"]["counterfactual_outcome_hash"]
            == (row["labels"]["counterfactual"]["outcome_hash"])
        )
        assert (
            row["lineage"]["evaluator_receipt_hash"]
            == (row["labels"]["counterfactual"]["evaluator_receipt_hash"])
        )


def test_identical_baseline_actions_are_not_mislabeled_counterfactuals(
    built_artifacts,
) -> None:
    sources, dataset, _ = built_artifacts

    assert all(len(source.outcomes) == 4 for source in sources)
    for source in sources:
        first = source.adapter.transition_bindings[0]
        assert first.shadow_proposed_step_size == pytest.approx(
            first.baseline_step_size
        )
        assert all(outcome.transition_index != 0 for outcome in source.outcomes)
    assert all(
        row["features"]["proposed_step_size"]
        != pytest.approx(row["labels"]["baseline"]["step_size"], abs=1.0e-15)
        for row in dataset["rows"]
    )


def test_scorecard_passes_only_the_repository_contract_fixture(
    built_artifacts,
) -> None:
    _, dataset, scorecard = built_artifacts

    assert scorecard["dataset_hash"] == dataset["dataset_hash"]
    assert scorecard["status"] == "contract_fixture_pass"
    assert scorecard["contract_pass"] is True
    assert scorecard["policy_gate_pass"] is False
    assert all(scorecard["gates"].values())
    assert scorecard["metrics"]["counterfactual_coverage"] == 1.0
    assert scorecard["metrics"]["counterfactual_safety_rate"] == 1.0
    assert scorecard["metrics"]["local_non_regression_rate"] == 1.0
    assert scorecard["metrics"]["holdout_non_regression_rate"] == 1.0
    assert scorecard["recommendation"] == "retain_shadow_only"
    assert scorecard["ai_action_executed"] is False
    assert scorecard["result_authority"] is False
    assert scorecard["guarded_execution_eligible"] is False
    assert scorecard["empirical_performance_claim"] is False


def test_missing_replay_receipt_blocks_coverage_without_invalidating_dataset(
    built_artifacts,
) -> None:
    _, original, _ = built_artifacts
    dataset = deepcopy(original)
    row = dataset["rows"][0]
    group = row["model_group_id"]
    row["labels"]["counterfactual"] = None
    row["labels"]["comparison"] = None
    row["lineage"]["counterfactual_outcome_hash"] = None
    row["lineage"]["evaluator_receipt_hash"] = None
    _rehash_row(row)
    dataset["evaluated_counterfactual_count"] -= 1
    dataset["missing_counterfactual_count"] += 1
    source = next(
        source for source in dataset["sources"] if source["model_group_id"] == group
    )
    source["evaluated_row_count"] -= 1
    _rehash_dataset(dataset, lineage_changed=True)

    assert validate_offline_counterfactual_dataset(dataset) == dataset
    scorecard = build_shadow_policy_scorecard(dataset).to_dict()
    assert scorecard["status"] == "blocked"
    assert scorecard["contract_pass"] is True
    assert scorecard["policy_gate_pass"] is False
    assert scorecard["gates"]["counterfactual_coverage_pass"] is False


def test_source_kind_relabel_cannot_self_authorize_policy_gate(
    built_artifacts,
) -> None:
    _, original, _ = built_artifacts
    dataset = deepcopy(original)
    dataset["source_kind"] = "independent_replay_receipts"
    _rehash_dataset(dataset)

    scorecard = build_shadow_policy_scorecard(dataset).to_dict()
    assert scorecard["source_kind"] == "independent_replay_receipts"
    assert all(scorecard["gates"].values())
    assert scorecard["status"] == "blocked"
    assert scorecard["policy_gate_pass"] is False
    assert scorecard["guarded_execution_eligible"] is False


def test_future_label_feature_and_split_leakage_fail_closed(
    built_artifacts,
) -> None:
    _, original, _ = built_artifacts
    leaked_feature = deepcopy(original)
    leaked_feature["rows"][0]["features"]["future_committed"] = True
    _rehash_row(leaked_feature["rows"][0])
    _rehash_dataset(leaked_feature)
    with pytest.raises(OfflineCounterfactualError, match="offline_schema_invalid"):
        validate_offline_counterfactual_dataset(leaked_feature)

    split_leak = deepcopy(original)
    split_leak["sources"][1]["model_ir_content_hash"] = split_leak["sources"][0][
        "model_ir_content_hash"
    ]
    _rehash_dataset(split_leak, lineage_changed=True)
    with pytest.raises(
        OfflineCounterfactualError,
        match="counterfactual_model_split_leakage",
    ):
        validate_offline_counterfactual_dataset(split_leak)

    problem_leak = deepcopy(original)
    problem_leak["sources"][1]["problem_contract_hash"] = problem_leak["sources"][0][
        "problem_contract_hash"
    ]
    _rehash_dataset(problem_leak, lineage_changed=True)
    with pytest.raises(
        OfflineCounterfactualError,
        match="counterfactual_problem_split_leakage",
    ):
        validate_offline_counterfactual_dataset(problem_leak)


def test_rehashed_comparison_tamper_and_authority_promotion_fail_closed(
    built_artifacts,
) -> None:
    _, original, _ = built_artifacts
    comparison_tamper = deepcopy(original)
    comparison = comparison_tamper["rows"][0]["labels"]["comparison"]
    comparison["iteration_density_advantage"] += 1.0
    _rehash_row(comparison_tamper["rows"][0])
    _rehash_dataset(comparison_tamper)
    with pytest.raises(
        OfflineCounterfactualError,
        match="counterfactual_comparison_mismatch",
    ):
        validate_offline_counterfactual_dataset(comparison_tamper)

    promoted = deepcopy(original)
    promoted["guarded_execution_eligible"] = True
    _rehash_dataset(promoted)
    with pytest.raises(OfflineCounterfactualError, match="offline_schema_invalid"):
        validate_offline_counterfactual_dataset(promoted)


def test_rehashed_scorecard_metric_tamper_fails_closed(built_artifacts) -> None:
    _, _, original = built_artifacts
    scorecard = deepcopy(original)
    scorecard["metrics"]["counterfactual_coverage"] = 0.5
    _rehash_scorecard(scorecard)

    with pytest.raises(
        OfflineCounterfactualError,
        match="shadow_scorecard_metric_mismatch",
    ):
        validate_shadow_policy_scorecard(scorecard)
