"""Actual solver labels, identical pools/budgets, and independent oracle audit."""

from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from structural_analysis.ai import fiber_frame_candidate_learning as learning
from structural_analysis.ai.fiber_frame_candidate_learning import (
    train_fiber_frame_candidate_policy,
)
from structural_analysis.ai.fiber_frame_warm_start_data import (
    FiberFrameWarmStartDataCase,
)
from structural_analysis.api import nonlinear_fiber_frame as public_api
from structural_analysis.benchmark import fiber_frame_candidate_search as search
from structural_analysis.benchmark import fiber_frame_design as design
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
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
def math_training_artifact():
    """Hash-binding fixture only: no labels or physical result authority claimed."""
    config = public_api.PublicRCFiberFrameConfig(load_steps=2)
    samples = []
    for index, (width, split) in enumerate(
        ((0.34, "train"), (0.46, "train"), (0.37, "validation"), (0.43, "holdout"))
    ):
        model = _model(width)
        features, context = learning.candidate_preanalysis_features(model, config)
        body = {
            "identity_profile": learning.PHYSICAL_MODEL_IDENTITY_PROFILE,
            "feature_profile": learning.CANDIDATE_FEATURE_PROFILE,
            "case_id": f"math-only-{index}",
            "split": split,
            "model_identity_hash": learning.candidate_model_identity(model),
            "context_hash": context,
            "features": features,
            "targets": [0.001 / width, 0.0001 / width],
        }
        samples.append({**body, "sample_hash": canonical_hash(body)})
    policy = learning._fit(samples, 1e-6, 0.1)
    report = {
        "schema_version": learning.CANDIDATE_LEARNING_SCHEMA,
        "identity_profile": learning.PHYSICAL_MODEL_IDENTITY_PROFILE,
        "feature_profile": learning.CANDIDATE_FEATURE_PROFILE,
        "status": "ready",
        "samples": samples,
        "cases": [
            {
                "case_id": row["case_id"],
                "split": row["split"],
                "status": "ready",
                "analysis_requested": True,
            }
            for row in samples
        ],
        "policy": policy.to_dict(),
        "cost_accounting": {
            "data_generation_wall_ns": 0,
            "training_wall_ns": 0,
            "full_analysis_request_count": len(samples),
        },
    }
    report["report_hash"] = canonical_hash(report)
    return learning.FiberFrameCandidateTrainingResult(
        "ready", policy, json.dumps(report)
    )


def _rehash(payload, field):
    payload[field] = canonical_hash(
        {key: value for key, value in payload.items() if key != field}
    )


def _search_binding_probe(training, *, baseline=None, candidates=None, **options):
    return search.compare_fiber_frame_candidate_search(
        _model() if baseline is None else baseline,
        _candidates()[:1] if candidates is None else candidates,
        training=training,
        prices=design.FiberFrameMaterialPrices(
            100.0, 1.0, "KRW", "2026-09-08", "test only"
        ),
        terminal_limits=design.FiberFrameTerminalLimits(0.01, 0.01),
        source_revision="a" * 40,
        config=public_api.PublicRCFiberFrameConfig(load_steps=2),
        full_analysis_budget=2,
        **options,
    )


@pytest.mark.parametrize(
    "arm_order",
    [
        None,
        (),
        ("deterministic",),
        ("deterministic", "deterministic"),
        ("learned", "oracle"),
        ("learned", "deterministic", "learned"),
        (True, "learned"),
        "deterministic,learned",
        {"deterministic", "learned"},
    ],
)
def test_invalid_arm_order_is_rejected_before_prediction_or_analysis(
    math_training_artifact, monkeypatch, arm_order
):
    def forbidden(*args, **kwargs):
        pytest.fail("invalid arm order must fail before prediction or analysis")

    monkeypatch.setattr(learning.FiberFrameCandidatePolicy, "predict", forbidden)
    monkeypatch.setattr(design, "compare_public_rc_fiber_frame_designs", forbidden)
    monkeypatch.setattr(public_api, "analyze_public_rc_fiber_frame", forbidden)
    with pytest.raises(ValueError, match="arm_order"):
        _search_binding_probe(math_training_artifact, arm_order=arm_order)


def test_requested_arm_order_preserves_frozen_shortlists_budgets_and_oracle_boundary(
    math_training_artifact, monkeypatch
):
    """Exercise orchestration with unverified boundary stubs, without new solves."""
    config = public_api.PublicRCFiberFrameConfig(load_steps=2)
    policy = math_training_artifact.policy
    narrow = policy.predict(_model(0.36), config)
    near_limit = policy.predict(_model(0.395), config)
    assert not narrow.ood and not near_limit.ood
    limits = design.FiberFrameTerminalLimits(
        (narrow.maximum_translation_m + near_limit.maximum_translation_m) / 2,
        (
            narrow.maximum_absolute_fiber_strain
            + near_limit.maximum_absolute_fiber_strain
        )
        / 2,
    )
    prices = design.FiberFrameMaterialPrices(
        100.0, 1.0, "KRW", "2026-09-08", "test only"
    )
    events = []
    original_predict = learning.FiberFrameCandidatePolicy.predict
    original_shortlist = search._learned_shortlist

    def predict(self, *args):
        events.append(("prediction",))
        return original_predict(self, *args)

    def freeze(*args):
        result = original_shortlist(*args)
        events.append(("freeze", tuple(result[1])))
        return result

    requested = None

    def compare(_baseline, candidates, *args, **kwargs):
        selected = tuple(candidate.candidate_id for candidate in candidates)
        events.append(("online", selected))
        if requested is not None:
            requested.clear()  # The caller's mutable list must already be detached.
        rows = [
            search._unavailable(key, "unverified test boundary")
            for key in ("baseline", *selected)
        ]
        return SimpleNamespace(to_dict=lambda: deepcopy({"rows": rows}))

    def oracle(candidate_id, *args):
        events.append(("oracle", candidate_id))
        return search._unavailable(candidate_id, "unverified test boundary")

    def forbidden(*args, **kwargs):
        pytest.fail("this orchestration test must not generate physical labels")

    monkeypatch.setattr(learning.FiberFrameCandidatePolicy, "predict", predict)
    monkeypatch.setattr(search, "_learned_shortlist", freeze)
    monkeypatch.setattr(design, "compare_public_rc_fiber_frame_designs", compare)
    monkeypatch.setattr(design, "_evaluate_design", oracle)
    monkeypatch.setattr(public_api, "analyze_public_rc_fiber_frame", forbidden)
    reports = []
    for requested in (None, ["learned", "deterministic"]):
        expected_order = (
            ["deterministic", "learned"] if requested is None else list(requested)
        )
        events.clear()
        result = search.compare_fiber_frame_candidate_search(
            _model(),
            _candidates()[:2],
            training=math_training_artifact,
            prices=prices,
            terminal_limits=limits,
            source_revision="a" * 40,
            config=config,
            full_analysis_budget=2,
            exploration_slots=0,
            oracle_audit=True,
            **({} if requested is None else {"arm_order": requested}),
        )
        report = result.to_dict()
        reports.append(report)
        assert report["execution_order"] == expected_order
        assert [arm["strategy"] for arm in report["arms"]] == [
            "deterministic",
            "learned",
        ]
        assert [name for name, _ in result._comparison_snapshots] == [
            "deterministic",
            "learned",
        ]
        shortlists = {
            arm["strategy"]: tuple(arm["shortlist"]) for arm in report["arms"]
        }
        assert shortlists == {"deterministic": ("narrow",), "learned": ("near_limit",)}
        assert events[:3] == [
            ("prediction",),
            ("prediction",),
            ("freeze", ("near_limit",)),
        ]
        assert events[3:5] == [("online", shortlists[name]) for name in expected_order]
        assert events[5:] == [
            ("oracle", name) for name in ("baseline", "narrow", "near_limit")
        ]
        assert report["fixed_full_analysis_budget_per_arm"] == 2
        assert report["cost_accounting"]["online_full_analysis_request_count"] == 4
        for arm in report["arms"]:
            assert arm["cost_accounting"]["baseline_analysis_request_count"] == 1
            assert arm["cost_accounting"]["candidate_analysis_request_count"] == 1
            assert arm["cost_accounting"]["total_analysis_request_count"] == 2
            assert arm["frozen_shortlist_hash"] == report["frozen_shortlist_hash"]
            assert arm["final_selection"] is None
        assert report["status"] == "blocked"
        assert report["oracle"]["labels_available_to_online_selection"] is False
    assert reports[0]["frozen_shortlist_hash"] == reports[1]["frozen_shortlist_hash"]
    assert reports[0]["candidate_pool"] == reports[1]["candidate_pool"]


def test_hash_bound_training_artifact_reaches_fresh_analysis_boundary(
    math_training_artifact, monkeypatch
) -> None:
    class ReachedFreshAnalysis(RuntimeError):
        pass

    def stop(*_args, **_kwargs):
        raise ReachedFreshAnalysis

    monkeypatch.setattr(design, "compare_public_rc_fiber_frame_designs", stop)
    with pytest.raises(ReachedFreshAnalysis):
        _search_binding_probe(math_training_artifact)


@pytest.mark.parametrize(
    "mutation, message",
    [
        ("stale_report", "report hash"),
        ("stale_sample", "sample hash"),
        ("rehashed_split", "sample membership"),
        ("rehashed_identity", "sample membership"),
        ("detached_policy", "policy identity"),
        ("old_schema", "schema or profile"),
        ("old_identity_profile", "schema or profile"),
        ("missing_identity_profile", "schema or profile"),
        ("old_feature_profile", "schema or profile"),
        ("sample_identity_profile", "sample profile"),
        ("sample_feature_profile", "sample profile"),
        ("duplicate_sample", "duplicate training sample"),
        ("detached_case", "case and sample membership"),
        ("blocked_case", "case and sample membership"),
        ("negative_cost", "cost accounting"),
        ("boolean_cost", "cost accounting"),
        ("missing_cost", "cost accounting"),
        ("null_training_cost", "cost accounting"),
        ("detached_request_count", "request count"),
    ],
)
def test_search_rejects_detached_training_bindings_before_ranking_or_solving(
    math_training_artifact, monkeypatch, mutation, message
) -> None:
    report = math_training_artifact.to_dict()
    if mutation == "stale_report":
        report["cost_accounting"]["data_generation_wall_ns"] = 1
    elif mutation == "stale_sample":
        report["samples"][0]["split"] = "holdout"
    elif mutation == "rehashed_split":
        report["samples"][0]["split"] = "holdout"
        _rehash(report["samples"][0], "sample_hash")
    elif mutation == "rehashed_identity":
        report["samples"][0]["model_identity_hash"] = "sha256:" + "f" * 64
        _rehash(report["samples"][0], "sample_hash")
    elif mutation == "detached_policy":
        report["policy"]["weights"][0][0] += 1
    elif mutation == "old_schema":
        report["schema_version"] = "fiber-frame-candidate-learning.v1"
    elif mutation == "old_identity_profile":
        report["identity_profile"] = "normalized-authored-model.v1"
    elif mutation == "missing_identity_profile":
        report.pop("identity_profile")
    elif mutation == "old_feature_profile":
        report["feature_profile"] = "aggregate-features.v1"
    elif mutation in ("sample_identity_profile", "sample_feature_profile"):
        field = mutation.removeprefix("sample_")
        report["samples"][0][field] = "unknown.v1"
        _rehash(report["samples"][0], "sample_hash")
    elif mutation == "duplicate_sample":
        report["samples"].append(deepcopy(report["samples"][0]))
    elif mutation == "detached_case":
        report["cases"][0]["case_id"] = "detached"
    elif mutation == "blocked_case":
        report["cases"][0]["status"] = "blocked"
    elif mutation == "negative_cost":
        report["cost_accounting"]["data_generation_wall_ns"] = -1
    elif mutation == "boolean_cost":
        report["cost_accounting"]["training_wall_ns"] = True
    elif mutation == "missing_cost":
        report["cost_accounting"].pop("full_analysis_request_count")
    elif mutation == "null_training_cost":
        report["cost_accounting"]["training_wall_ns"] = None
    elif mutation == "detached_request_count":
        report["cost_accounting"]["full_analysis_request_count"] = 0
    if mutation != "stale_report":
        _rehash(report, "report_hash")
    detached = learning.FiberFrameCandidateTrainingResult(
        "ready", math_training_artifact.policy, json.dumps(report)
    )

    def forbidden(*_args, **_kwargs):
        pytest.fail("detached training artifacts must be rejected before online work")

    monkeypatch.setattr(design, "apply_fiber_frame_section_changes", forbidden)
    monkeypatch.setattr(design, "compare_public_rc_fiber_frame_designs", forbidden)
    with pytest.raises(ValueError, match=message):
        _search_binding_probe(detached)
    # Validation neither repairs nor promotes the supplied raw artifact.
    assert detached.to_dict() == report


def _relabel_single_member(model):
    payload = model.canonical_payload()
    node_map = {
        row["id"]: f"renamed-node-{i}" for i, row in enumerate(payload["nodes"])
    }
    for node in payload["nodes"]:
        node["id"] = node_map[node["id"]]
    for member in payload["elements"]:
        member.update(
            id="renamed-member",
            section="renamed-section",
            nodes=[node_map[key] for key in member["nodes"]],
        )
    for row in (*payload["loads"], *payload["supports"]):
        row["node"] = node_map[row["node"]]
    payload["sections"][0].update(
        id="renamed-section",
        steel_material="renamed-steel",
        concrete_material="renamed-concrete",
    )
    for material in payload["materials"]:
        material["id"] = "renamed-" + material["id"]
    for key in ("nodes", "materials", "sections", "elements"):
        payload[key].reverse()
    payload["metadata"] = {"case_id": "renamed"}
    return load_neutral_json_bytes(json.dumps(payload).encode())


@pytest.mark.parametrize("overlap", ["baseline", "candidate"])
def test_entity_relabel_cannot_bypass_online_training_overlap(
    math_training_artifact, monkeypatch, overlap
) -> None:
    baseline = _relabel_single_member(_model(0.34 if overlap == "baseline" else 0.4))
    candidates = [
        design.FiberFrameDesignCandidate(
            "renamed-training",
            (design.FiberFrameSectionChange("renamed-section", width_m=0.34),),
        )
    ]

    def forbidden(*_args, **_kwargs):
        pytest.fail("training overlap must not request a solve")

    monkeypatch.setattr(design, "compare_public_rc_fiber_frame_designs", forbidden)
    with pytest.raises(ValueError, match=f"online {overlap} overlaps a training-label"):
        _search_binding_probe(
            math_training_artifact, baseline=baseline, candidates=candidates
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
