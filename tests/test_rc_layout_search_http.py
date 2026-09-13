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
        "row_estimate",
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
        elif change == "row_estimate":
            comparison["rows"][0]["material_estimate"]["total"] += 1
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


@pytest.fixture(
    scope="module",
    params=[("price_order", 3), ("learned_order", 3), ("price_order", 2)],
)
def pruned_graph(inputs, tmp_path_factory, request):  # noqa: F811
    from structural_analysis.benchmark.rc_control_layout_search import (
        run_control_layout_cost_pruned_strategy,
    )

    strategy, budget = request.param
    args = dict(inputs) | {"full_analysis_budget": budget}
    if strategy == "price_order":
        args.pop("policy")
        args.pop("training_report")
    root = tmp_path_factory.mktemp("layout-pruned-http") / strategy
    report = run_control_layout_cost_pruned_strategy(
        **args, strategy=strategy, output_directory=root
    )
    return root, report, strategy


def test_actual_pruned_http_retains_decisions_and_unevaluated_models(
    pruned_graph, monkeypatch
):
    root, report, strategy = pruned_graph

    def forbidden(*args, **kwargs):
        pytest.fail("graph admission or delivery executed a solver or training")

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
    pruning = report["arms"][strategy]["cost_pruning"]
    assert report["candidate_coverage_audit"] is None
    assert report["candidate_cost_optimality_audit"] is None
    for key in pruning["unevaluated_candidate_ids"]:
        assert f"pool/{key}.json" in bundle.artifacts
        assert not any(p.startswith(f"{strategy}/{key}/") for p in bundle.artifacts)
    for ref in pruning["decisions"]:
        assert f"{strategy}/{ref['artifact']['path']}" in bundle.artifacts
    assert ("policy.json" in bundle.artifacts) == (strategy == "learned_order")
    originals = {p: (root / p).read_bytes() for p in bundle.artifacts}
    app = RcSearchArtifactWSGIApplication(
        {("tenant", "pruned"): bundle},
        authorize=lambda t, k: (t, k) == ("tenant", "synthetic"),
    )
    monkeypatch.setattr(Path, "open", forbidden)
    for path, raw in originals.items():
        response = app.handle(
            "GET",
            "/v1/rc-search/pruned/" + path,
            headers={
                "X-Structural-Tenant": "tenant",
                "Authorization": "Bearer synthetic",
            },
        )
        assert response.status == 200 and response.body == raw
    assert (
        app.handle("GET", "/v1/rc-search/pruned/result.json", headers={}).status == 401
    )


@pytest.mark.parametrize(
    "change",
    [
        "decision_missing",
        "decision_action",
        "decision_future_rows",
        "decision_path",
        "decision_cost",
        "skipped_list",
        "feasibility",
        "global_optimality",
        "horizon",
        "coverage",
        "policy",
        "extra_row",
        "missing_row",
        "estimate",
        "performance",
        "original_request",
        "original_verification",
        "original_work",
        "comparison_price",
    ],
)
def test_pruned_rejects_self_consistently_rehashed_records(pruned_graph, change):
    root, report, strategy = pruned_graph
    bundle = RcSearchArtifactBundle.from_directory(
        root, expected_report_hash=report["report_hash"]
    )
    files = dict(bundle.artifacts)
    result = json.loads(files["result.json"])
    plan = json.loads(files["plan.json"])
    path = f"{strategy}/comparison.json"
    comparison = json.loads(files[path])
    pruning = comparison["cost_pruning"]
    if change == "decision_missing":
        pruning["decisions"].pop()
    elif change in ("decision_action", "decision_future_rows", "decision_path"):
        record = pruning["decisions"][0]
        dpath = f"{strategy}/{record['artifact']['path']}"
        decision = json.loads(files[dpath])
        if change == "decision_action":
            record["action"] = decision["action"] = "skip_cost_dominated"
        elif change == "decision_future_rows":
            decision["evaluated_candidate_ids_before"] = ["baseline"]
        else:
            record["artifact"]["path"] = "decisions/../00.json"
        raw = rehash(decision, "decision_hash")
        files[dpath] = raw
        record["artifact"].update(byte_length=len(raw), sha256=study._sha(raw))
    elif change == "decision_cost":
        pruning["decision_wall_ns"] = True
    elif change == "skipped_list":
        pruning["skipped_cost_dominated_candidate_ids"] = ["baseline"]
    elif change == "feasibility":
        pruning["unevaluated_physical_feasibility"] = "infeasible"
    elif change == "global_optimality":
        pruning["global_cost_optimality_proved"] = True
    elif change == "horizon":
        pruning["outside_consideration_horizon_candidate_ids"] = ["baseline"]
    elif change == "coverage":
        result["candidate_cost_optimality_audit"] = {"regret": 0}
    elif change == "policy":
        plan["execution_policy"]["unused_analysis_budget_reallocated"] = True
        result["execution_policy"] = plan["execution_policy"]
    elif change == "extra_row":
        comparison["rows"].append(comparison["rows"][0])
    elif change == "missing_row":
        from structural_analysis.benchmark.rc_control_candidate_search import _work

        comparison["rows"].pop(0)
        result["arms"][strategy]["execution_work"] = _work(comparison)
        result["arms"][strategy]["request_count"] = len(comparison["rows"])
    elif change == "estimate":
        comparison["rows"][0]["material_estimate"]["total"] += 1
    elif change == "comparison_price":
        comparison["price_table_hash"] = "sha256:" + "0" * 64
    elif change == "performance":
        row = comparison["rows"][0]
        row["performance"]["maximum_translation_m"] = 0
        row["screens"]["maximum_translation_m"]["value"] = 0
    else:
        row = comparison["rows"][0]
        role = {
            "original_request": "result",
            "original_verification": "verification",
            "original_work": "analysis_outcome",
        }[change]
        ref = row["artifacts"][role]
        original_path = f"{strategy}/{ref['path']}"
        original = json.loads(files[original_path])
        if change == "original_request":
            original["request"]["control_global_dof"] += 1
            raw = rehash(original, "result_hash")
        else:
            if change == "original_verification":
                original["fresh_source_execution_invoked"] = False
            else:
                original["work"]["known_newton_iteration_count"] += 1
            raw = study._bytes(original)
        files[original_path] = raw
        ref.update(byte_length=len(raw), sha256=study._sha(raw))
    files["plan.json"] = rehash(plan, "plan_hash")
    result["plan_hash"] = plan["plan_hash"]
    files[path] = rehash(comparison, "report_hash")
    result["arms"][strategy]["comparison_hash"] = comparison["report_hash"]
    result["arms"][strategy]["cost_pruning"] = pruning
    files["result.json"] = rehash(result, "report_hash")
    with pytest.raises(ValueError):
        RcSearchArtifactBundle.from_reader(
            lambda name, maximum: files[name],
            expected_report_hash=result["report_hash"],
        )


def test_pruned_constant_preload_without_incumbent_keeps_all_original_rows(
    inputs,  # noqa: F811
    tmp_path,
):
    from dataclasses import replace
    from structural_analysis.benchmark import fiber_frame_design as design
    from structural_analysis.benchmark.rc_control_layout_search import (
        run_control_layout_cost_pruned_strategy,
    )

    args = {k: v for k, v in inputs.items() if k not in ("policy", "training_report")}
    args.update(
        request=replace(
            args["request"], constant_nodal_loads=(("N3", 0.0, -0.1, 0.0),)
        ),
        full_analysis_budget=3,
        history_limits=design.FiberFrameHistoryLimits(1e-30, 1e-30),
    )
    root = tmp_path / "constant-no-incumbent"
    report = run_control_layout_cost_pruned_strategy(
        **args, strategy="price_order", output_directory=root
    )
    arm = report["arms"]["price_order"]
    assert arm["selected_candidate_id"] is None
    assert arm["request_count"] == 3
    assert arm["cost_pruning"]["skipped_cost_dominated_candidate_ids"] == []
    comparison = json.loads((root / arm["comparison_path"]).read_bytes())
    assert all(
        row["full_reference_verification_pass"] is True for row in comparison["rows"]
    )
    bundle = RcSearchArtifactBundle.from_directory(
        root, expected_report_hash=report["report_hash"]
    )
    assert sum(path.endswith("/result.json") for path in bundle.artifacts) == 3


def test_pruned_rejects_zero_work_even_with_original_records_rebound(pruned_graph):
    root, report, strategy = pruned_graph
    bundle = RcSearchArtifactBundle.from_directory(
        root, expected_report_hash=report["report_hash"]
    )
    files = dict(bundle.artifacts)
    result = json.loads(files["result.json"])
    path = f"{strategy}/comparison.json"
    comparison = json.loads(files[path])
    row = comparison["rows"][0]

    def replace_original(role, value, hash_key=None):
        ref = row["artifacts"][role]
        raw = rehash(value, hash_key) if hash_key else study._bytes(value)
        files[f"{strategy}/{ref['path']}"] = raw
        ref.update(byte_length=len(raw), sha256=study._sha(raw))

    raw_result = json.loads(files[f"{strategy}/{row['artifacts']['result']['path']}"])
    raw_result["metrics"]["control_work"]["attempted_step_count"] = 0
    replace_original("result", raw_result, "result_hash")
    row["invocations"][0]["work"] = raw_result["metrics"]["control_work"]
    replace_original("analysis_outcome", row["invocations"][0])
    verification = json.loads(
        files[f"{strategy}/{row['artifacts']['verification']['path']}"]
    )
    verification["verified_result_hash"] = raw_result["result_hash"]
    replace_original("verification", verification)
    from structural_analysis.benchmark.rc_control_candidate_search import _work

    result["arms"][strategy]["execution_work"] = _work(comparison)
    files[path] = rehash(comparison, "report_hash")
    result["arms"][strategy]["comparison_hash"] = comparison["report_hash"]
    files["result.json"] = rehash(result, "report_hash")
    with pytest.raises(ValueError, match="original work excludes complete path"):
        RcSearchArtifactBundle.from_reader(
            lambda name, maximum: files[name],
            expected_report_hash=result["report_hash"],
        )
