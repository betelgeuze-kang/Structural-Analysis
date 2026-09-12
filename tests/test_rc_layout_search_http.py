"""Actual layout graph admission and immutable authenticated HTTP bytes."""

import json
from pathlib import Path

import pytest

from tests.test_rc_control_layout_search import actual as search_study, inputs  # noqa: F401
from structural_analysis.benchmark import rc_control_design as study
from structural_analysis.benchmark import rc_control_layout_learning as learning
from structural_analysis.execution.rc_search_http import (
    RcSearchArtifactBundle,
    RcSearchArtifactWSGIApplication,
)


@pytest.fixture(scope="module")
def graph(search_study):  # noqa: F811
    root, report, _ = search_study
    bundle = RcSearchArtifactBundle.from_directory(
        root, expected_report_hash=report["report_hash"]
    )
    return root, report, bundle


def test_actual_layout_graph_has_exact_http_bytes_without_any_new_solve(
    graph, monkeypatch
):
    root, report, original = graph

    def forbidden(*args, **kwargs):
        raise AssertionError("graph admission must not solve or fit")

    monkeypatch.setattr(study.api, "analyze_bounded_rc_fiber_direct_control", forbidden)
    monkeypatch.setattr(
        study.api, "validate_bounded_rc_fiber_direct_control_artifacts", forbidden
    )
    monkeypatch.setattr(learning, "_candidate_fit_parameters", forbidden)
    bundle = RcSearchArtifactBundle.from_directory(
        root, expected_report_hash=report["report_hash"]
    )
    assert bundle.artifacts == original.artifacts
    assert len(bundle.artifacts) == 67
    assert "price_order/outcome.json" not in bundle.artifacts
    assert "price_order/baseline/row.json" not in bundle.artifacts
    app = RcSearchArtifactWSGIApplication(
        {("tenant", "layout"): bundle},
        authorize=lambda t, k: (t, k) == ("tenant", "synthetic"),
    )
    expected = {name: (root / name).read_bytes() for name in bundle.artifacts}
    monkeypatch.setattr(Path, "open", forbidden)
    for name, raw in expected.items():
        response = app.handle(
            "GET",
            "/v1/rc-search/layout/" + name,
            headers={
                "X-Structural-Tenant": "tenant",
                "Authorization": "Bearer synthetic",
            },
        )
        assert response.status == 200 and response.body == raw
    assert (
        app.handle("GET", "/v1/rc-search/layout/result.json", headers={}).status == 401
    )
    assert (
        app.handle(
            "POST",
            "/v1/rc-search/layout/result.json",
            headers={
                "X-Structural-Tenant": "tenant",
                "Authorization": "Bearer synthetic",
            },
        ).status
        == 405
    )
    with pytest.raises(TypeError):
        bundle.artifacts["result.json"] = b"changed"


def rehash(document, key):
    document[key] = study._sha(
        study._bytes({k: v for k, v in document.items() if k != key})
    )
    return study._bytes(document)


@pytest.mark.parametrize(
    "change",
    [
        "raw_result",
        "pin",
        "shortlist",
        "coverage",
        "request_count",
        "path",
        "missing_checkpoint",
        "old_schema",
        "claims",
        "estimate",
        "price_table",
        "prediction",
        "model_identity",
        "quantity",
        "screen",
        "cost",
    ],
)
def test_rejects_tampered_or_self_consistently_rehashed_graphs(graph, change):
    _, report, bundle = graph
    files = dict(bundle.artifacts)
    result = json.loads(files["result.json"])
    plan = json.loads(files["plan.json"])
    expected = report["report_hash"]
    if change == "raw_result":
        files["price_order/baseline/baseline/result.json"] += b" "
    elif change == "pin":
        expected = "sha256:" + "0" * 64
    elif change == "shortlist":
        plan["plans"]["price_order"]["shortlist"] = ["large"]
        files["plan.json"] = rehash(plan, "plan_hash")
        result["plan_hash"] = plan["plan_hash"]
    elif change == "coverage":
        result["candidate_coverage_audit"]["arms"]["learned_order"][
            "missed_feasible_count"
        ] = 999
    elif change == "request_count":
        result["arms"]["price_order"]["request_count"] = True
    elif change == "old_schema":
        result["schema_version"] = "experimental-rc-control-candidate-search.v3"
    elif change == "claims":
        result["claims"]["net_savings_proved"] = True
    elif change == "cost":
        result["online_and_optional_oracle_wall_ns"] = 0
    elif change == "estimate":
        plan["predictions"][0]["estimate"] += 1
        files["plan.json"] = rehash(plan, "plan_hash")
        result["plan_hash"] = plan["plan_hash"]
    elif change == "price_table":
        table = json.loads(files["price-table.json"])
        table["concrete_per_m3"] += 1
        files["price-table.json"] = study._bytes(table)
    elif change in ("prediction", "model_identity"):
        if change == "prediction":
            plan["predictions"][0]["prediction"]["performance"][
                "maximum_translation_m"
            ] *= 2
        else:
            plan["pool"][0]["model_identity"] = "sha256:" + "0" * 64
        files["plan.json"] = rehash(plan, "plan_hash")
        result["plan_hash"] = plan["plan_hash"]
    else:
        key = "price_order/comparison.json"
        comparison = json.loads(files[key])
        if change == "path":
            comparison["rows"][0]["artifacts"]["result"]["path"] = "../result.json"
        elif change == "quantity":
            comparison["rows"][0]["quantities"] = {}
        elif change == "screen":
            comparison["rows"][0]["screens"]["maximum_translation_m"]["status"] = "fail"
        else:
            comparison["rows"][0]["artifacts"].pop("checkpoint")
        files[key] = rehash(comparison, "report_hash")
        result["arms"]["price_order"]["comparison_hash"] = comparison["report_hash"]
    if change not in ("raw_result", "pin"):
        files["result.json"] = rehash(result, "report_hash")
        expected = result["report_hash"]
    with pytest.raises(ValueError):
        RcSearchArtifactBundle.from_reader(
            lambda name, maximum: files[name], expected_report_hash=expected
        )


@pytest.fixture(scope="module", params=["price_order", "learned_order"])
def standalone_graph(inputs, tmp_path_factory, request):  # noqa: F811
    from structural_analysis.benchmark.rc_control_layout_search import (
        run_control_layout_strategy,
    )

    strategy = request.param
    args = dict(inputs)
    if strategy == "price_order":
        args.pop("policy")
        args.pop("training_report")
    root = tmp_path_factory.mktemp("layout-single-http") / strategy
    report = run_control_layout_strategy(
        **args, strategy=strategy, output_directory=root
    )
    return root, report, strategy


def test_standalone_original_graph_http_without_solver_or_training(
    standalone_graph, monkeypatch
):
    root, report, strategy = standalone_graph

    def forbidden(*args, **kwargs):
        pytest.fail("admission executed solver or training")

    monkeypatch.setattr(study.api, "analyze_bounded_rc_fiber_direct_control", forbidden)
    monkeypatch.setattr(
        study.api, "validate_bounded_rc_fiber_direct_control_artifacts", forbidden
    )
    monkeypatch.setattr(learning, "_candidate_fit_parameters", forbidden)
    if strategy == "price_order":
        monkeypatch.setattr(learning.RCControlLayoutPolicy, "predict", forbidden)
    bundle = RcSearchArtifactBundle.from_directory(
        root, expected_report_hash=report["report_hash"]
    )
    assert ("policy.json" in bundle.artifacts) == (strategy == "learned_order")
    assert ("historical-training.json" in bundle.artifacts) == (
        strategy == "learned_order"
    )
    assert not any("exhaustive_oracle" in name for name in bundle.artifacts)
    app = RcSearchArtifactWSGIApplication(
        {("tenant", "single"): bundle},
        authorize=lambda t, k: (t, k) == ("tenant", "synthetic"),
    )
    for name, raw in bundle.artifacts.items():
        assert raw == (root / name).read_bytes()
        response = app.handle(
            "GET",
            "/v1/rc-search/single/" + name,
            headers={
                "X-Structural-Tenant": "tenant",
                "Authorization": "Bearer synthetic",
            },
        )
        assert response.status == 200 and response.body == raw


@pytest.mark.parametrize(
    "change",
    [
        "strategy",
        "oracle",
        "timing",
        "coverage",
        "training",
        "extra_arm",
        "raw_checkpoint",
    ],
)
def test_standalone_rejects_rehashed_contract_tampering(standalone_graph, change):
    root, report, strategy = standalone_graph
    bundle = RcSearchArtifactBundle.from_directory(
        root, expected_report_hash=report["report_hash"]
    )
    files = dict(bundle.artifacts)
    result = json.loads(files["result.json"])
    plan = json.loads(files["plan.json"])
    if change == "strategy":
        plan["strategy"] = (
            "learned_order" if strategy == "price_order" else "price_order"
        )
    elif change == "oracle":
        plan["oracle_after_online_arms"] = True
    elif change == "timing":
        result["timing_scope"] = "both_arms"
    elif change == "coverage":
        result["candidate_coverage_audit"] = {"missed_feasible_count": 0}
    elif change == "training":
        result["historical_training_cost_counted_once_outside_online_arms"] = (
            strategy == "price_order"
        )
    elif change == "extra_arm":
        result["arms"]["extra"] = result["arms"][strategy]
    else:
        files[f"{strategy}/baseline/baseline/checkpoint.json"] += b" "
    files["plan.json"] = rehash(plan, "plan_hash")
    result["plan_hash"] = plan["plan_hash"]
    files["result.json"] = rehash(result, "report_hash")
    with pytest.raises(ValueError):
        RcSearchArtifactBundle.from_reader(
            lambda name, maximum: files[name],
            expected_report_hash=result["report_hash"],
        )
