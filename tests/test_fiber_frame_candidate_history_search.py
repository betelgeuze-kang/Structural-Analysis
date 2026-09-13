"""Ranking/audit contracts with algebraic fitting and explicit source stubs.

These tests make no numerical solver, worker, or physical provenance claim.
"""

from copy import deepcopy
from dataclasses import asdict
import json
import sys
from types import SimpleNamespace

import pytest

from structural_analysis.benchmark import fiber_frame_candidate_search as core
from structural_analysis.benchmark import fiber_frame_candidate_search_arm as arm
from structural_analysis.benchmark import fiber_frame_candidate_search_suite as suite
from structural_analysis.benchmark import fiber_frame_design as design
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from tests.test_fiber_frame_candidate_history_learning import (
    _model,
    history_training as _history_training,
    stub_sources as _stub_sources,
)


TERMINAL = design.FiberFrameTerminalLimits(1.0, 1.0)
HISTORY = design.FiberFrameHistoryLimits(2.0, 2.0)
MATERIAL = design.FiberFrameMaterialHistoryLimits(0.02, 0.2, 0.2)


@pytest.fixture
def stub_sources(monkeypatch):
    return _stub_sources.__wrapped__(monkeypatch)


@pytest.fixture
def history_training(stub_sources):
    return _history_training.__wrapped__(stub_sources)


def prediction(*, translation=1.5, strain=1.5, plastic=0.01, damage=0.1, ood=False):
    return {
        "maximum_translation_m": None if ood else 0.5,
        "maximum_absolute_fiber_strain": None if ood else 0.25,
        "ood": ood,
        "reason": "outside_range" if ood else "fixture_prediction",
        "uncertainty_kind": "uncalibrated_feature_range_indicator_not_probability",
        "physical_result_authority": False,
        "target_profile": core.HISTORY_TARGET_PROFILE,
        "history_prediction": None
        if ood
        else dict(
            zip(
                core._HISTORY_TARGETS,
                (translation, strain, plastic, damage, 0.0),
                strict=True,
            )
        ),
    }


def binding(history=HISTORY, material=MATERIAL):
    return {
        "candidate_target_profile": core.HISTORY_TARGET_PROFILE,
        "terminal_limits": asdict(TERMINAL),
        **({"history_limits": asdict(history)} if history is not None else {}),
        **(
            {"material_history_limits": asdict(material)}
            if material is not None
            else {}
        ),
    }


def pool_row(key, cost, payload, *, limits=None):
    limits = binding() if limits is None else limits
    return {
        "candidate_id": key,
        "screening_status": "ready",
        "preanalysis_material_estimate": cost,
        "prediction": deepcopy(payload),
        **core._requested_prediction_fields(
            payload,
            limits["terminal_limits"],
            limits.get("history_limits"),
            limits.get("material_history_limits"),
        ),
    }


class Policy:
    target_profile = core.HISTORY_TARGET_PROFILE

    def __init__(self, predictions):
        self.predictions = predictions
        self.calls = []
        self.artifact_hash = canonical_hash(self._payload())

    def _payload(self):
        return {"algebraic_fixture": True, "predictions": self.predictions}

    def predict(self, key, _config):
        self.calls.append(key)
        return SimpleNamespace(to_dict=lambda: deepcopy(self.predictions[key]))


def actual(key, *, terminal="pass", history="pass", material="pass", verified=True):
    return {
        "candidate_id": key,
        "full_reference_verification_pass": True,
        "full_history_verification_pass": True,
        "full_material_history_verification_pass": verified,
        "terminal_limit_status": terminal,
        "history_limit_status": history,
        "material_history_limit_status": material,
    }


@pytest.mark.parametrize("bad_scope", ["history", "material"])
def test_same_terminal_prediction_ranking_uses_requested_history_and_damage(bad_scope):
    bad = (
        prediction(translation=2.1)
        if bad_scope == "history"
        else prediction(damage=0.3)
    )
    rows = [
        pool_row("cheap-failing", 1.0, bad),
        pool_row("verified-prediction", 2.0, prediction()),
    ]
    assert all(row["predicted_terminal_safe"] is True for row in rows)
    assert core._learned_shortlist(rows, 1, 0) == (
        ["verified-prediction", "cheap-failing"],
        ["verified-prediction"],
    )
    assert core._deterministic_plan(rows, 2)[:2] == (
        ["cheap-failing", "verified-prediction"],
        ["cheap-failing"],
    )


def test_near_limit_exploration_uses_combined_ratio_not_terminal_ratio():
    rows = [
        pool_row("cheap-safe", 1.0, prediction()),
        pool_row("near", 3.0, prediction(damage=0.202)),
        pool_row("far-cheaper", 2.0, prediction(damage=0.8)),
    ]
    assert len({row["predicted_limit_ratio"] for row in rows}) == 1
    assert core._learned_shortlist(rows, 2, 1)[1] == ["cheap-safe", "near"]


def test_unrequested_scopes_do_not_change_ranking_and_remain_unavailable():
    row = pool_row(
        "a", 1.0, prediction(translation=3.0, damage=0.9), limits=binding(None, None)
    )
    assert (
        row["predicted_history_safe"] is row["predicted_material_history_safe"] is None
    )
    assert row["predicted_requested_limits_safe"] is True
    assert row["predicted_requested_limit_ratio"] == row["predicted_limit_ratio"] == 0.5


@pytest.mark.parametrize(
    "value,expected,ratio", [(0.0, True, 0.75), (0.001, False, sys.float_info.max)]
)
def test_zero_material_limit_uses_exact_gate_with_finite_ranking(
    value, expected, ratio
):
    limits = binding(material=design.FiberFrameMaterialHistoryLimits(0.0, 0.2, 0.2))
    row = pool_row("a", 1.0, prediction(plastic=value), limits=limits)
    assert row["predicted_material_history_safe"] is expected
    assert row["predicted_requested_limits_safe"] is expected
    assert row["predicted_requested_limit_ratio"] == ratio
    json.dumps(row, allow_nan=False)
    assert core._finite_limit_ratio(1.0, 5e-324) == sys.float_info.max


def test_ood_preserves_unknown_and_gets_exploration_without_false_safety():
    rows = [
        pool_row("safe", 1.0, prediction()),
        pool_row("ood", 4.0, prediction(ood=True)),
        pool_row("near", 2.0, prediction(damage=0.201)),
    ]
    assert all(rows[1][key] is None for key in core._COMBINED_FIELDS)
    assert core._learned_shortlist(rows, 2, 1)[1] == ["safe", "ood"]
    audit = core._audit_outcomes(
        rows, [], [actual(row["candidate_id"]) for row in rows], True, True
    )
    assert audit["predicted_requested_limits_safety_candidate_count"] == 2
    assert audit["predicted_history_safety_candidate_count"] == 2
    assert audit["predicted_material_history_safety_available"] is True


def test_combined_false_safe_and_unverifiable_do_not_replace_terminal_audit():
    rows = [
        pool_row(key, 1.0, prediction())
        for key in ("damage-fail", "unverified", "terminal-fail", "feasible")
    ]
    oracle = [
        actual("damage-fail", material="fail"),
        actual("unverified", verified=False),
        actual("terminal-fail", terminal="fail"),
        actual("feasible"),
    ]
    audit = core._audit_outcomes(rows, [], oracle, True, True)
    assert audit["false_safe_candidate_ids"] == ["terminal-fail"]
    assert audit["combined_false_safe_candidate_ids"] == [
        "damage-fail",
        "terminal-fail",
    ]
    assert audit["combined_predicted_safe_unverifiable_candidate_ids"] == ["unverified"]
    assert audit["missed_feasible_candidate_ids"] == ["feasible"]
    assert (
        audit["combined_false_safe_definition"]
        == "predicted_requested_limits_safe_but_verified_requested_limit_failure"
    )
    assert (
        audit["combined_predicted_safe_unverifiable_definition"]
        == "predicted_requested_limits_safe_without_all_requested_verification"
    )
    original = deepcopy(audit)
    deterministic = core._without_prediction_claims(audit)
    assert audit == original
    assert (
        deterministic["false_safe_count"]
        is deterministic["combined_false_safe_count"]
        is None
    )
    assert deterministic["combined_predicted_safe_unverifiable_candidate_ids"] is None
    assert deterministic["predicted_history_safety_available"] is False
    assert deterministic["predicted_material_history_safety_candidate_count"] == 0


def test_missing_oracle_does_not_turn_unknown_counts_into_zero():
    audit = core._audit_outcomes(
        [pool_row("a", 1.0, prediction())], [], None, True, True
    )
    assert audit["combined_false_safe_count"] is None
    assert audit["combined_predicted_safe_unverifiable_candidate_ids"] is None
    assert audit["predicted_history_safety_available"] is True


@pytest.mark.parametrize(
    "mutation",
    [
        "binding-omission",
        "binding-mismatch",
        "prediction-profile",
        "prediction-key",
        "row-key",
        "wrong-safe",
        "wrong-ratio",
        "boolean-safe",
        "history-range",
        "damage-range",
    ],
)
def test_rehashed_prediction_scope_tampering_cannot_pass(mutation):
    limits = binding()
    rows = [pool_row("a", 1.0, prediction())]
    core._validate_prediction_pool(rows, limits, predictions_required=True)
    row = rows[0]
    if mutation == "binding-omission":
        limits.pop("candidate_target_profile")
    elif mutation == "binding-mismatch":
        limits["candidate_target_profile"] = core.TERMINAL_TARGET_PROFILE
    elif mutation == "prediction-profile":
        row["prediction"].pop("target_profile")
    elif mutation == "prediction-key":
        row["prediction"].pop("history_prediction")
    elif mutation == "row-key":
        row.pop("predicted_history_safe")
    elif mutation == "wrong-safe":
        row["predicted_requested_limits_safe"] = False
    elif mutation == "wrong-ratio":
        row["predicted_requested_limit_ratio"] = 0.0
    elif mutation == "boolean-safe":
        row["predicted_requested_limits_safe"] = 1
    elif mutation == "history-range":
        row["prediction"]["history_prediction"][core._HISTORY_TARGETS[0]] = 0.1
    elif mutation == "damage-range":
        row["prediction"]["history_prediction"][core._HISTORY_TARGETS[3]] = 1.1
    envelope = {"input_binding": limits, "candidate_pool": rows}
    envelope["report_hash"] = canonical_hash(envelope)
    with pytest.raises(ValueError):
        core._validate_prediction_pool(
            envelope["candidate_pool"],
            envelope["input_binding"],
            predictions_required=True,
        )


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -0.1, True])
def test_malformed_new_prediction_values_reject_before_ranking(bad):
    value = prediction()
    value["history_prediction"][core._HISTORY_TARGETS[2]] = bad
    with pytest.raises(ValueError):
        pool_row("a", 1.0, value)


def test_arm_plans_bind_profile_limits_budget_and_do_not_predict_oracle():
    policy = Policy({"cheap": prediction(damage=0.4), "safe": prediction()})
    pool = [pool_row(key, cost, None) for key, cost in (("cheap", 1.0), ("safe", 2.0))]
    prepared = {
        "pool": pool,
        "models": {key: key for key in policy.predictions},
        "policy": policy,
        "policy_hash": policy.artifact_hash,
        "cfg": object(),
        "terminal_limits": TERMINAL,
        "history_limits": HISTORY,
        "material_history_limits": MATERIAL,
        "full_analysis_budget": 2,
        "exploration_slots": 0,
        "input_binding": binding(),
    }
    deterministic = arm._plan(prepared, "deterministic")[0]
    learned = arm._plan(prepared, "learned")[0]
    oracle = arm._plan(prepared, "oracle")[0]
    assert policy.calls == ["cheap", "safe"]
    assert deterministic["frozen_plan"]["shortlist"] == ["cheap"]
    assert learned["frozen_plan"]["shortlist"] == ["safe"]
    assert (
        len(learned["frozen_plan"]["shortlist"]) + 1 == prepared["full_analysis_budget"]
    )
    assert oracle["frozen_plan"]["shortlist"] == ["cheap", "safe"]
    assert all(row["prediction"] is None for row in oracle["candidate_pool"])
    assert all(row["prediction"] is None for row in pool)
    core._validate_prediction_pool(
        learned["candidate_pool"], binding(), predictions_required=True
    )
    before = deepcopy(learned)
    core._audit_outcomes(
        learned["candidate_pool"],
        ["safe"],
        [actual("cheap"), actual("safe", material="fail")],
        True,
        True,
    )
    assert learned == before
    prepared["input_binding"] = dict(binding(), candidate_target_profile="changed")
    changed = arm._plan(prepared, "oracle")[0]
    assert changed["frozen_plan_hash"] != oracle["frozen_plan_hash"]


def test_legacy_pool_audit_and_prediction_claims_have_no_new_fields():
    rows = [
        {
            "candidate_id": "legacy",
            "screening_status": "ready",
            "preanalysis_material_estimate": 1.0,
            "prediction": None,
            "predicted_terminal_safe": True,
            "predicted_limit_ratio": 0.5,
        }
    ]
    core._validate_prediction_pool(rows, {"terminal_limits": asdict(TERMINAL)})
    assert core._target_profile_binding(SimpleNamespace()) == {}
    assert core._learned_shortlist(rows, 1, 0) == (["legacy"], ["legacy"])
    audit = core._without_prediction_claims(core._audit_outcomes(rows, [], None))
    assert not any(key.startswith("combined_") for key in audit)


def test_suite_rejects_rehashed_omitted_profile_before_any_result_validation():
    limits = binding()
    limits.update(
        source_revision="a" * 40,
        configuration={},
        price_basis={},
        policy_artifact_hash="sha256:" + "1" * 64,
        training_report_hash="sha256:" + "2" * 64,
        full_analysis_budget=2,
        exploration_slots=0,
        candidates=[],
    )
    report = {"report_hash": ""}
    report["report_hash"] = canonical_hash({})
    with pytest.raises(ValueError, match="profile presence"):
        suite._validate_report(report, limits, ("deterministic", "learned"), False)


def test_typed_seven_target_artifact_freezes_all_arm_plans_without_new_analysis(
    history_training, stub_sources, monkeypatch
):
    def forbidden(*args, **kwargs):
        pytest.fail("plan preparation must not execute a public analysis or refit")

    monkeypatch.setattr(core.public_api, "analyze_public_rc_fiber_frame", forbidden)
    baseline = _model()
    candidates = tuple(
        design.FiberFrameDesignCandidate(
            f"width-{width}",
            (
                design.FiberFrameSectionChange(
                    baseline.sections[0]["id"], width_m=width
                ),
            ),
        )
        for width in (0.38, 0.42)
    )
    before = history_training.to_dict()
    expected = arm.prepare_fiber_frame_candidate_search_expectations(
        baseline,
        candidates,
        training=history_training,
        prices=design.FiberFrameMaterialPrices(
            100.0, 1.0, "KRW", "2026-09-09", "synthetic contract fixture"
        ),
        terminal_limits=TERMINAL,
        history_limits=HISTORY,
        material_history_limits=MATERIAL,
        source_revision="a" * 40,
        config=stub_sources[0][0].config,
        full_analysis_budget=2,
        exploration_slots=0,
    )
    assert (
        expected["input_binding"]["candidate_target_profile"]
        == core.HISTORY_TARGET_PROFILE
    )
    for strategy in arm.STRATEGIES:
        plan = expected[strategy]
        core._validate_prediction_pool(
            plan["candidate_pool"],
            expected["input_binding"],
            predictions_required=strategy == "learned",
        )
        assert plan["frozen_plan"]["input_binding_hash"] == canonical_hash(
            expected["input_binding"]
        )
        assert all(
            (row["prediction"] is not None) == (strategy == "learned")
            for row in plan["candidate_pool"]
        )
    assert history_training.to_dict() == before
    assert stub_sources[2]["analysis_stub"] == 4


@pytest.mark.parametrize("profile", [None, False, core.TERMINAL_TARGET_PROFILE])
def test_explicit_invalid_profile_binding_is_not_a_legacy_downgrade(profile):
    with pytest.raises(ValueError, match="profile binding"):
        core._validate_prediction_pool([], {"candidate_target_profile": profile})


def _ranking_declaration():
    """Only the pre-physical report prefix; no invented result authority."""
    limits = binding(material=None)
    pool = [
        pool_row(
            "cheap-history-failure", 1.0, prediction(translation=3.0), limits=limits
        ),
        pool_row("safe", 2.0, prediction(), limits=limits),
        pool_row(
            "near-history-limit", 3.0, prediction(translation=1.99), limits=limits
        ),
    ]
    for row in pool:
        row.update(changes=[], model_checksum=canonical_hash(row["candidate_id"]))
    limits.update(
        source_revision="a" * 40,
        configuration={},
        price_basis={},
        policy_artifact_hash=canonical_hash("synthetic-policy"),
        training_report_hash=canonical_hash("synthetic-training"),
        full_analysis_budget=3,
        exploration_slots=1,
        candidates=[
            {key: row[key] for key in ("candidate_id", "changes", "model_checksum")}
            for row in pool
        ],
    )
    plans = {
        "deterministic": (
            [row["candidate_id"] for row in pool],
            [pool[0]["candidate_id"], "safe"],
        ),
        "learned": (
            ["safe", "near-history-limit", pool[0]["candidate_id"]],
            ["safe", "near-history-limit"],
        ),
    }
    report = {
        **{
            key: limits[key]
            for key in (
                "source_revision",
                "configuration",
                "price_basis",
                "terminal_limits",
                "history_limits",
                "policy_artifact_hash",
                "training_report_hash",
                "candidate_target_profile",
                "exploration_slots",
            )
        },
        "schema_version": "fiber-frame-candidate-search-comparison.v3",
        "identity_profile": suite.PHYSICAL_MODEL_IDENTITY_PROFILE,
        "feature_profile": suite.CANDIDATE_FEATURE_PROFILE,
        "fixed_full_analysis_budget_per_arm": 3,
        "execution_order": list(suite.STRATEGIES),
        "baseline_included_in_budget": True,
        "declared_candidate_count": len(pool),
        "candidate_pool": pool,
        "arms": [
            {"strategy": strategy, "ranking": ranking, "shortlist": shortlist}
            for strategy, (ranking, shortlist) in plans.items()
        ],
    }
    return report, limits


def _seal_ranking_report(report, limits):
    frozen = canonical_hash(
        {
            "pool": report["candidate_pool"],
            "shortlists": {arm["strategy"]: arm["shortlist"] for arm in report["arms"]},
            "policy_hash": limits["policy_artifact_hash"],
        }
    )
    report["frozen_shortlist_hash"] = frozen
    for row in report["arms"]:
        row["frozen_shortlist_hash"] = frozen
    report["report_hash"] = canonical_hash(
        {key: value for key, value in report.items() if key != "report_hash"}
    )


@pytest.mark.parametrize("strategy", suite.STRATEGIES)
@pytest.mark.parametrize("field", ["ranking", "shortlist"])
def test_suite_rejects_coherently_rehashed_ranking_order_before_physical_rows(
    strategy, field
):
    report, limits = _ranking_declaration()
    selected = next(row for row in report["arms"] if row["strategy"] == strategy)
    selected[field].reverse()
    _seal_ranking_report(report, limits)
    with pytest.raises(
        ValueError, match=f"{strategy} requested-scope ranking or shortlist"
    ):
        suite._validate_report(report, limits, suite.STRATEGIES, False)


def test_suite_rejects_coherently_rehashed_terminal_only_learned_plan():
    report, limits = _ranking_declaration()
    terminal_only = [
        {key: value for key, value in row.items() if key not in core._COMBINED_FIELDS}
        for row in report["candidate_pool"]
    ]
    ranking, shortlist = core._learned_shortlist(terminal_only, 2, 1)
    assert shortlist != report["arms"][1]["shortlist"]
    report["arms"][1].update(ranking=ranking, shortlist=shortlist)
    _seal_ranking_report(report, limits)
    with pytest.raises(
        ValueError, match="learned requested-scope ranking or shortlist"
    ):
        suite._validate_report(report, limits, suite.STRATEGIES, False)
