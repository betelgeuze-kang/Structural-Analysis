"""Real full-layout search plus failure and accounting boundary checks."""

from copy import deepcopy
from dataclasses import replace
import json

import pytest

from tests.test_rc_control_layout_dataset import roster
from tests.test_rc_control_layout_learning import train
from tests.test_rc_control_learning import case
from structural_analysis.benchmark import rc_control_layout_search as search
from structural_analysis.benchmark import rc_control_design as study
from structural_analysis.benchmark import fiber_frame_design as design


@pytest.fixture(scope="module")
def inputs(tmp_path_factory):
    root = tmp_path_factory.mktemp("layout-search-training")
    cases = roster(root)
    policy, training = train(cases, root / "training")
    return dict(
        baseline=cases[2].model,
        candidates=tuple(
            search.RCControlLayoutCandidate(
                name,
                case(
                    root, name, "validation", lengths=lengths, load="fixed-history"
                ).model,
            )
            for name, lengths in (("small", (2.2, 1.7)), ("large", (2.9, 2.2)))
        ),
        request=cases[2].request,
        policy=policy,
        training_report=training,
        prices=design.FiberFrameMaterialPrices(
            100, 1, "KRW", "2026-09-13", "synthetic only"
        ),
        history_limits=design.FiberFrameHistoryLimits(1, 1),
        material_limits=design.FiberFrameMaterialHistoryLimits(1, 1, 1),
        terminal_limits=design.FiberFrameTerminalLimits(1, 1),
        source_revision="a" * 40,
        full_analysis_budget=2,
    )


@pytest.fixture(scope="module")
def actual(inputs, tmp_path_factory):
    root = tmp_path_factory.mktemp("layout-search") / "search"
    calls = []
    original = study._reference_design_row

    def observed(*args, **kwargs):
        assert (root / "plan.json").is_file()
        # Both online shortlists have been published before the first reference call.
        plan = json.loads((root / "plan.json").read_bytes())
        assert set(plan["plans"]) == {"price_order", "learned_order"}
        calls.append(args[0].canonical_model_checksum)
        return original(*args, **kwargs)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(study, "_reference_design_row", observed)
        report = search.compare_control_layout_search(
            **inputs, output_directory=root, evaluate_exhaustive_oracle=True
        )
    return root, report, calls


def test_real_frozen_layout_search_full_references_and_original_artifacts(
    actual, inputs
):
    root, report, calls = actual
    assert len(calls) == 7  # two baseline+small arms, then all three oracle models
    assert calls[-1] == inputs["candidates"][1].model.canonical_model_checksum
    plan = json.loads((root / "plan.json").read_bytes())
    assert report["candidate_cost_optimality_audit"]["status"] == "complete"
    assert report["historical_training_cost_counted_once_outside_online_arms"] is True
    assert report["claims"]["net_savings_proved"] is False
    assert report["claims"]["functional_equivalence_verified"] is False
    assert report["claims"]["workbench_search_review_integrated"] is False
    for name in ("price_order", "learned_order", "exhaustive_oracle"):
        comparison = json.loads((root / name / "comparison.json").read_bytes())
        assert comparison["selected_candidate_id"] == "small"
        for row in comparison["rows"]:
            assert row["full_reference_verification_pass"] is True
            assert row["screens"]["terminal_maximum_translation_m"]["status"] == "pass"
            pool = next(
                p for p in plan["pool"] if p["candidate_id"] == row["candidate_id"]
            )
            assert row["material_estimate"] == pool["material_estimate"]
            assert row["quantities"] == pool["quantities"]
            for ref in row["artifacts"].values():
                raw = (root / name / ref["path"]).read_bytes()
                assert study._sha(raw) == ref["sha256"]
                assert len(raw) == ref["byte_length"]
            assert (
                row["artifacts"]["model"]["sha256"] == pool["model_artifact"]["sha256"]
            )
    for arm in ("price_order", "learned_order"):
        assert (
            report["candidate_cost_optimality_audit"]["arms"][arm][
                "selected_minus_pool_minimum_estimate"
            ]
            == 0
        )
        assert (
            report["candidate_coverage_audit"]["arms"][arm]["missed_feasible_count"]
            == 1
        )


def retained_rows(actual, monkeypatch):
    """Control-flow doubles only; no new numerical or artifact-verification claim."""
    root, _, _ = actual
    rows = json.loads((root / "exhaustive_oracle/comparison.json").read_bytes())["rows"]
    by_model = {r["quantities"]["model_checksum"]: r for r in rows}

    def retained(model, *args, **kwargs):
        row = deepcopy(by_model[model.canonical_model_checksum])
        return row

    monkeypatch.setattr(study, "_reference_design_row", retained)


def test_no_oracle_keeps_optimality_unknown(actual, inputs, tmp_path, monkeypatch):
    retained_rows(actual, monkeypatch)
    report = search.compare_control_layout_search(
        **inputs, output_directory=tmp_path / "search"
    )
    assert report["oracle"] is None
    assert report["candidate_cost_optimality_audit"]["status"] == "oracle_not_run"
    assert (
        report["candidate_coverage_audit"]["arms"]["learned_order"][
            "missed_feasible_count"
        ]
        is None
    )


@pytest.mark.parametrize(
    "change",
    [
        "budget",
        "context",
        "duplicate",
        "training_overlap",
        "policy_binding",
        "training_cost",
        "unknown_training_work",
        "training_phase",
    ],
)
def test_preflight_rejects_before_outputs(inputs, tmp_path, change):
    args = dict(inputs)
    if change == "budget":
        args["full_analysis_budget"] = True
    elif change == "context":
        args["request"] = replace(
            args["request"], targets_m=tuple(v * 1.1 for v in args["request"].targets_m)
        )
    elif change == "duplicate":
        args["candidates"] = (
            args["candidates"][0],
            search.RCControlLayoutCandidate("alias", args["candidates"][0].model),
        )
    elif change == "training_overlap":
        args["baseline"] = roster(tmp_path)[0].model
    else:
        training = deepcopy(args["training_report"])
        if change == "policy_binding":
            training["policy"]["sha256"] = "sha256:" + "0" * 64
        elif change == "training_cost":
            training["wall_ns"] = True
        elif change == "training_phase":
            training["label_invocations"][1]["phase"] = "analysis"
        else:
            training["label_invocations"][0]["unknown_execution_work"] = True
        training["report_hash"] = study._sha(
            study._bytes({k: v for k, v in training.items() if k != "report_hash"})
        )
        args["training_report"] = training
    root = tmp_path / "search"
    with pytest.raises(ValueError):
        search.compare_control_layout_search(**args, output_directory=root)
    assert not root.exists()


@pytest.mark.parametrize("interrupt", [False, True])
def test_unknown_or_interrupted_work_stops_before_second_arm(
    inputs, tmp_path, monkeypatch, interrupt
):
    calls = []

    def fail(*args, **kwargs):
        calls.append(1)
        if interrupt:
            raise KeyboardInterrupt()
        return {
            "candidate_id": "baseline",
            "artifacts": {},
            "invocations": [{"unknown_execution_work": True, "work": None}],
        }

    monkeypatch.setattr(study, "_reference_design_row", fail)
    root = tmp_path / "search"
    with pytest.raises(KeyboardInterrupt if interrupt else ValueError):
        search.compare_control_layout_search(
            **inputs, output_directory=root, evaluate_exhaustive_oracle=True
        )
    assert len(calls) == 1
    assert not (root / "learned_order").exists()
    assert not (root / "exhaustive_oracle").exists()
    assert not (root / "result.json").exists()
    assert (
        json.loads((root / "price_order/outcome.json").read_bytes())[
            "unknown_work_until_outcome"
        ]
        is True
    )


@pytest.mark.parametrize("name", ["baseline", "../escape", "a/b", "a\\b", ""])
def test_candidate_ids_cannot_be_paths(inputs, name):
    with pytest.raises(ValueError):
        search.RCControlLayoutCandidate(name, inputs["baseline"])


@pytest.mark.parametrize("strategy", ["price_order", "learned_order"])
def test_standalone_actual_references_and_frozen_single_plan(
    inputs, tmp_path, monkeypatch, strategy
):
    args = dict(inputs)
    root = tmp_path / strategy
    calls = []
    original = study._reference_design_row

    def observed(*a, **kw):
        plan = json.loads((root / "plan.json").read_bytes())
        assert set(plan["plans"]) == {strategy}
        calls.append(a[0].canonical_model_checksum)
        return original(*a, **kw)

    def forbidden(*a, **kw):
        pytest.fail("price execution accessed learned computation")

    monkeypatch.setattr(study, "_reference_design_row", observed)
    if strategy == "price_order":
        args.pop("policy")
        args.pop("training_report")
        monkeypatch.setattr(search, "_training_cost", forbidden)
        monkeypatch.setattr(search.RCControlLayoutPolicy, "predict", forbidden)
    report = search.run_control_layout_strategy(
        **args, strategy=strategy, output_directory=root
    )
    assert len(calls) == 2
    assert set(report["arms"]) == {strategy}
    assert report["strategy"] == strategy
    assert report["historical_training_cost_counted_once_outside_online_arms"] is (
        strategy == "learned_order"
    )
    assert report["schema_version"] == "experimental-rc-control-layout-strategy.v1"
    assert report["oracle"] is None
    assert not (root / "exhaustive_oracle").exists()
    assert report["candidate_cost_optimality_audit"]["status"] == "oracle_not_run"
    comparison = json.loads((root / strategy / "comparison.json").read_bytes())
    assert comparison["selected_candidate_id"] == "small"
    for row in comparison["rows"]:
        assert row["full_reference_verification_pass"] is True
        for ref in row["artifacts"].values():
            raw = (root / strategy / ref["path"]).read_bytes()
            assert study._sha(raw) == ref["sha256"]
            assert len(raw) == ref["byte_length"]
    plan = json.loads((root / "plan.json").read_bytes())
    if strategy == "price_order":
        assert plan["policy_hash"] is None
        assert plan["training_report_hash"] is None
        assert plan["predictions"] == []
        assert report["ranking_wall_ns"] == 0
        assert report["historical_training_cost"] is None
        assert report["candidate_coverage_audit"] is None
        assert not (root / "policy.json").exists()
        assert not (root / "historical-training.json").exists()
    else:
        assert report["historical_training_cost"] == inputs["training_report"]
        assert (root / "policy.json").is_file()
        assert (root / "historical-training.json").is_file()


@pytest.mark.parametrize(
    "change", ["price_policy", "price_training", "oracle", "selector", "missing_policy"]
)
def test_standalone_rejects_invalid_strategy_inputs_before_output(
    inputs, tmp_path, change
):
    args = dict(inputs)
    strategy = "learned_order"
    if change.startswith("price_"):
        strategy = "price_order"
        args.pop("training_report" if change == "price_policy" else "policy")
    elif change == "oracle":
        args["evaluate_exhaustive_oracle"] = True
    elif change == "selector":
        strategy = "exhaustive_oracle"
    else:
        args.pop("policy")
    root = tmp_path / "search"
    with pytest.raises(ValueError):
        search.run_control_layout_strategy(
            **args, strategy=strategy, output_directory=root
        )
    assert not root.exists()
