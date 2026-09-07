"""Actual solver labels, identical pools/budgets, and independent oracle audit."""

from copy import deepcopy
import json
from pathlib import Path

import pytest

from structural_analysis.ai.fiber_frame_candidate_learning import (
    train_fiber_frame_candidate_policy,
)
from structural_analysis.ai.fiber_frame_warm_start_data import (
    FiberFrameWarmStartDataCase,
)
from structural_analysis.api import nonlinear_fiber_frame as public_api
from structural_analysis.benchmark import fiber_frame_candidate_search as search
from structural_analysis.benchmark import fiber_frame_design as design
from structural_analysis.io.neutral.loader import load_neutral_json_bytes


def _model(width=0.4):
    path = (
        Path(__file__).resolve().parents[1]
        / "examples/public_rc_fiber_frame_cantilever.json"
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["sections"][0]["width_m"] = width
    payload["loads"][0]["components"]["FY"] = -1.0
    return load_neutral_json_bytes(json.dumps(payload).encode())


def _candidates():
    return tuple(
        design.FiberFrameDesignCandidate(
            key, (design.FiberFrameSectionChange("RC1", width_m=width),)
        )
        for key, width in (
            ("narrow", 0.36),
            ("near_limit", 0.395),
            ("wide", 0.42),
            ("wider", 0.44),
        )
    ) + (
        design.FiberFrameDesignCandidate(
            "invalid", (design.FiberFrameSectionChange("RC1", depth_m=0.05),)
        ),
    )


@pytest.fixture(scope="module")
def actual_study():
    cfg = public_api.PublicRCFiberFrameConfig(load_steps=2)
    cases = tuple(
        FiberFrameWarmStartDataCase(
            f"case-{index}",
            f"declared-project-{index}",
            f"declared-geometry-{index}",
            f"declared-history-{index}",
            split,
            _model(width),
            cfg,
        )
        for index, (width, split) in enumerate(
            ((0.34, "train"), (0.46, "train"), (0.37, "validation"), (0.43, "holdout"))
        )
    )
    training = train_fiber_frame_candidate_policy(cases, source_revision="a" * 40)
    assert training.status == "ready", training.to_dict()["failure"]
    labels = [
        row["targets"]
        for row in training.to_dict()["samples"]
        if row["split"] == "train"
    ]
    limits = design.FiberFrameTerminalLimits(
        maximum_translation_m=sum(row[0] for row in labels) / 2.0,
        maximum_absolute_fiber_strain=sum(row[1] for row in labels) / 2.0,
    )
    prices = design.FiberFrameMaterialPrices(
        100.0, 1.0, "KRW", "2026-09-08", "synthetic test table, not a quote"
    )
    captured = []
    fresh = design._evaluate_design

    def record_fresh(*args):
        row = fresh(*args)
        captured.append(deepcopy(row))
        return row

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(design, "_evaluate_design", record_fresh)
        result = search.compare_fiber_frame_candidate_search(
            _model(),
            _candidates(),
            training=training,
            prices=prices,
            terminal_limits=limits,
            source_revision="a" * 40,
            config=cfg,
            full_analysis_budget=2,
            exploration_slots=1,
            oracle_audit=True,
        )
    return training, cfg, limits, prices, result, captured


def test_actual_labels_and_online_final_candidates_are_full_solver_verified(
    actual_study,
) -> None:
    training, _, _, _, result, _ = actual_study
    data = training.to_dict()
    assert len(data["samples"]) == 4
    assert all(row["validation"]["contract_pass"] for row in data["cases"])
    assert data["cost_accounting"]["data_generation_wall_ns"] > 0
    assert data["cost_accounting"]["training_wall_ns"] > 0
    assert data["claims"]["independent_project_generalization_verified"] is False
    report = result.to_dict()
    assert report["status"] == "ready"
    assert report["declared_candidate_count"] == 5
    for arm in report["arms"]:
        assert len(arm["candidate_outcomes"]) == 5
        assert arm["cost_accounting"]["baseline_analysis_request_count"] == 1
        assert arm["cost_accounting"]["candidate_analysis_request_count"] == 1
        assert arm["cost_accounting"]["total_analysis_request_count"] == 2
        winner = arm["final_selection"]
        assert winner["full_reference_verification_pass"] is True
        assert winner["terminal_limit_status"] == "pass"
        assert winner["result"]["checkpoint"]["terminal_epoch"] == 2
        assert winner["quantities"]["detailed_takeoff"] is False
        assert winner["material_estimate"]["verified_quote"] is False
    assert report["cost_accounting"]["online_full_analysis_request_count"] == 4
    assert (
        report["cost_accounting"][
            "total_analysis_request_count_including_training_and_oracle"
        ]
        == 14
    )
    assert report["oracle"]["full_analysis_request_count"] == 6
    assert report["claims"]["screen_limits_cover_full_history_extrema"] is False
    assert report["claims"]["confirmed_construction_savings"] is False
    assert report["claims"]["generalized_speedup_claimed"] is False


def test_saved_comparison_accessor_preserves_producer_hashes_and_is_detached(
    actual_study,
) -> None:
    _, _, _, _, result, _ = actual_study
    report = result.to_dict()
    for arm in report["arms"]:
        comparison = result.design_comparison(arm["strategy"])
        assert type(comparison) is design.FiberFrameDesignComparison
        assert comparison.to_dict() == arm["design_comparison"]
        assert comparison.to_dict()["runtime"]["reference_analysis_request_count"] == 2
        comparison._payload["rows"][0]["candidate_id"] = "tampered-returned-copy"
        assert (
            result.design_comparison(arm["strategy"]).to_dict()
            == arm["design_comparison"]
        )
    with pytest.raises(ValueError, match="arm_name"):
        result.design_comparison("oracle")


def test_baseline_only_empty_shortlist_has_no_design_comparison(
    actual_study, monkeypatch
) -> None:
    training, cfg, limits, prices, _, captured = actual_study
    monkeypatch.setattr(design, "_evaluate_design", _cached_fresh(captured))
    result = search.compare_fiber_frame_candidate_search(
        _model(),
        [_candidates()[-1]],
        training=training,
        prices=prices,
        terminal_limits=limits,
        source_revision="a" * 40,
        config=cfg,
        full_analysis_budget=2,
    )
    for arm in result.to_dict()["arms"]:
        assert arm["shortlist"] == []
        assert arm["cost_accounting"]["total_analysis_request_count"] == 1
        assert arm["design_comparison"] is None
        assert result.design_comparison(arm["strategy"]) is None


def test_bare_sha256_revision_is_normalized_for_m2_producer(
    actual_study, monkeypatch
) -> None:
    training, cfg, limits, prices, _, captured = actual_study
    monkeypatch.setattr(design, "_evaluate_design", _cached_fresh(captured))
    result = search.compare_fiber_frame_candidate_search(
        _model(),
        _candidates(),
        training=training,
        prices=prices,
        terminal_limits=limits,
        source_revision="b" * 64,
        config=cfg,
        full_analysis_budget=2,
    )
    assert result.to_dict()["source_revision"] == "sha256:" + "b" * 64
    assert (
        result.design_comparison("learned").to_dict()["identity"]["source_revision"]
        == "sha256:" + "b" * 64
    )


def test_learned_uncertain_shortlist_and_cost_only_baseline_have_same_pool(
    actual_study,
) -> None:
    _, _, _, _, result, _ = actual_study
    report = result.to_dict()
    deterministic, learned = report["arms"]
    assert deterministic["shortlist"] == ["narrow"]
    assert learned["shortlist"] == ["near_limit"]
    assert deterministic["cost_accounting"]["inference_count"] == 0
    assert learned["cost_accounting"]["inference_count"] == 4
    assert learned["final_selection"]["candidate_id"] == "near_limit"
    assert deterministic["final_selection"]["candidate_id"] == "baseline"
    assert deterministic["oracle_audit"]["missed_feasible_count"] >= 1
    assert learned["oracle_audit"]["oracle_unverifiable_candidate_count"] == 1
    assert deterministic["oracle_audit"]["false_safe_count"] is None
    assert learned["oracle_audit"]["false_safe_count"] >= 0
    assert report["oracle"]["labels_available_to_online_selection"] is False
    invalid = next(
        row for row in report["oracle"]["rows"] if row["candidate_id"] == "invalid"
    )
    assert invalid["full_reference_verification_pass"] is False


def _cached_fresh(captured):
    by_id = {row["candidate_id"]: row for row in captured}

    def fresh(candidate_id, *_args):
        return deepcopy(by_id[candidate_id])

    return fresh


def test_no_oracle_means_missed_feasible_and_false_safe_are_unavailable(
    actual_study, monkeypatch
) -> None:
    training, cfg, limits, prices, original, captured = actual_study
    monkeypatch.setattr(design, "_evaluate_design", _cached_fresh(captured))
    result = search.compare_fiber_frame_candidate_search(
        _model(),
        _candidates(),
        training=training,
        prices=prices,
        terminal_limits=limits,
        source_revision="a" * 40,
        config=cfg,
        full_analysis_budget=2,
        exploration_slots=1,
    ).to_dict()
    assert (
        result["frozen_shortlist_hash"] == original.to_dict()["frozen_shortlist_hash"]
    )
    assert result["oracle"]["rows"] is None
    assert result["oracle"]["wall_ns"] is None
    for arm in result["arms"]:
        assert arm["oracle_audit"]["missed_feasible_count"] is None
        assert arm["oracle_audit"]["false_safe_count"] is None
        assert arm["oracle_audit"]["reason"] == "exhaustive_oracle_not_run"


def test_oracle_labels_cannot_change_already_frozen_online_selection(
    actual_study, monkeypatch
) -> None:
    training, cfg, limits, prices, original, captured = actual_study
    cached = _cached_fresh(captured)
    calls = []

    def alter_audit_only(candidate_id, *args):
        row = cached(candidate_id, *args)
        calls.append(candidate_id)
        if len(calls) > 4 and candidate_id != "baseline":
            row["full_reference_verification_pass"] = True
            row["terminal_limit_status"] = "fail"
        return row

    monkeypatch.setattr(design, "_evaluate_design", alter_audit_only)
    report = search.compare_fiber_frame_candidate_search(
        _model(),
        _candidates(),
        training=training,
        prices=prices,
        terminal_limits=limits,
        source_revision="a" * 40,
        config=cfg,
        full_analysis_budget=2,
        exploration_slots=1,
        oracle_audit=True,
    ).to_dict()
    original = original.to_dict()
    assert calls[:4] == ["baseline", "narrow", "baseline", "near_limit"]
    assert report["frozen_shortlist_hash"] == original["frozen_shortlist_hash"]
    assert [arm["final_selection"]["candidate_id"] for arm in report["arms"]] == [
        arm["final_selection"]["candidate_id"] for arm in original["arms"]
    ]
    assert (
        report["arms"][1]["oracle_audit"]["false_safe_count"]
        > original["arms"][1]["oracle_audit"]["false_safe_count"]
    )


def test_unknown_execution_counts_are_not_reported_as_known_zero(
    actual_study, monkeypatch
) -> None:
    training, cfg, limits, prices, _, captured = actual_study
    cached = _cached_fresh(captured)

    def unknown(candidate_id, *args):
        row = cached(candidate_id, *args)
        if candidate_id != "baseline":
            row.update(
                full_reference_verification_pass=False,
                solver_executed=None,
                terminal_limit_status="unavailable",
                result=None,
                validation=None,
                quantities=None,
                material_estimate=None,
                performance=None,
            )
        return row

    monkeypatch.setattr(design, "_evaluate_design", unknown)
    result = search.compare_fiber_frame_candidate_search(
        _model(),
        _candidates(),
        training=training,
        prices=prices,
        terminal_limits=limits,
        source_revision="a" * 40,
        config=cfg,
        full_analysis_budget=2,
        exploration_slots=1,
    ).to_dict()
    for arm in result["arms"]:
        assert arm["cost_accounting"]["unknown_solver_execution_count"] == 1
        assert arm["cost_accounting"]["known_solver_execution_count"] == 1


def test_pool_cannot_reuse_training_physics_even_with_new_candidate_id(
    actual_study,
) -> None:
    training, cfg, limits, prices, _, _ = actual_study
    seen = design.FiberFrameDesignCandidate(
        "seen", (design.FiberFrameSectionChange("RC1", width_m=0.34),)
    )
    with pytest.raises(ValueError, match="overlaps a training-label"):
        search.compare_fiber_frame_candidate_search(
            _model(),
            [seen],
            training=training,
            prices=prices,
            terminal_limits=limits,
            source_revision="a" * 40,
            config=cfg,
        )


def test_oracle_metrics_keep_unknown_physical_outcomes_separate() -> None:
    pool = [
        {"candidate_id": "safe", "predicted_terminal_safe": True},
        {"candidate_id": "failed", "predicted_terminal_safe": True},
        {"candidate_id": "missed", "predicted_terminal_safe": False},
    ]
    oracle = [
        {
            "candidate_id": "safe",
            "full_reference_verification_pass": True,
            "terminal_limit_status": "fail",
        },
        {
            "candidate_id": "failed",
            "full_reference_verification_pass": False,
            "terminal_limit_status": "unavailable",
        },
        {
            "candidate_id": "missed",
            "full_reference_verification_pass": True,
            "terminal_limit_status": "pass",
        },
    ]
    report = search._audit_outcomes(pool, ["safe"], oracle)
    assert report["false_safe_candidate_ids"] == ["safe"]
    assert report["predicted_safe_unverifiable_candidate_ids"] == ["failed"]
    assert report["missed_feasible_candidate_ids"] == ["missed"]
