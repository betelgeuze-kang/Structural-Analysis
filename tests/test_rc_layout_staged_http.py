"""Original staged graphs, rehashed tampering, and exact authenticated delivery."""

import json

import pytest

from tests.test_rc_control_layout_search import inputs  # noqa: F401
from structural_analysis.benchmark import rc_control_layout_search as search
from structural_analysis.benchmark import rc_control_design as study
from structural_analysis.benchmark import fiber_frame_design as design
from structural_analysis.benchmark.rc_control_candidate_search import _work
from structural_analysis.execution.rc_search_http import (
    RcSearchArtifactBundle,
    RcSearchArtifactWSGIApplication,
)


@pytest.fixture(
    scope="module",
    params=[("price_order", 2), ("learned_order", 2), ("price_order", 1)],
)
def staged(inputs, tmp_path_factory, request):  # noqa: F811
    strategy, count = request.param
    options = dict(inputs)
    if strategy == "price_order":
        options.pop("policy")
        options.pop("training_report")
    options.update(
        full_analysis_budget=3, history_limits=design.FiberFrameHistoryLimits(1, 2e-6)
    )
    root = tmp_path_factory.mktemp("staged-http") / "result"
    result = search.run_control_layout_staged_strategy(
        **options, strategy=strategy, prefix_target_count=count, output_directory=root
    )
    bundle = RcSearchArtifactBundle.from_directory(
        root, expected_report_hash=result["report_hash"]
    )
    return root, result, bundle, strategy


def test_actual_staged_originals_are_delivered_without_solving(staged, monkeypatch):
    root, result, original, strategy = staged

    def forbidden(*args, **kwargs):
        raise AssertionError("admission must not execute numerical paths")

    monkeypatch.setattr(study.api, "analyze_bounded_rc_fiber_direct_control", forbidden)
    monkeypatch.setattr(
        study.api, "validate_bounded_rc_fiber_direct_control_artifacts", forbidden
    )
    bundle = RcSearchArtifactBundle.from_directory(
        root, expected_report_hash=result["report_hash"]
    )
    assert bundle.artifacts == original.artifacts
    app = RcSearchArtifactWSGIApplication(
        {("tenant", "staged"): bundle},
        authorize=lambda t, k: (t, k) == ("tenant", "token"),
    )
    for path, raw in bundle.artifacts.items():
        response = app.handle(
            "GET",
            "/v1/rc-search/staged/" + path,
            headers={"X-Structural-Tenant": "tenant", "Authorization": "Bearer token"},
        )
        assert (
            response.status == 200
            and response.body == (root / path).read_bytes() == raw
        )
    assert (
        app.handle("GET", "/v1/rc-search/staged/result.json", headers={}).status == 401
    )
    assert f"{strategy}/prefix/small/decision.json" in bundle.artifacts
    assert f"{strategy}/prefix/small/request.json" in bundle.artifacts
    assert f"{strategy}/prefix/small/row.json" in bundle.artifacts


def rehash(d, key):
    d[key] = study._sha(study._bytes({k: v for k, v in d.items() if k != key}))
    return study._bytes(d)


@pytest.mark.parametrize(
    "change",
    [
        "count_bool",
        "count_full",
        "terminal_policy",
        "request_context",
        "decision_action",
        "decision_model",
        "full_acceptance",
        "violations",
        "missing_decision",
        "extra_decision",
        "rejected_ids",
        "exclude_prefix_work",
        "prefix_work",
        "row_performance",
        "row_model",
        "result_request",
        "verification_flag",
        "missing_checkpoint",
        "path",
        "row_work",
    ],
)
def test_staged_rejects_rehashed_tampering(staged, change):
    _, _, bundle, strategy = staged
    files = dict(bundle.artifacts)
    result = json.loads(files["result.json"])
    plan = json.loads(files["plan.json"])
    cpath = f"{strategy}/comparison.json"
    comparison = json.loads(files[cpath])
    info = comparison["prefix_screening"]
    record = info["decisions"][0]
    dpath = f"{strategy}/{record['artifact']['path']}"
    decision = json.loads(files[dpath])
    folder = dpath.rsplit("/", 1)[0]
    row = json.loads(files[f"{folder}/row.json"])
    if change == "count_bool":
        plan["prefix_screening"]["target_count"] = True
    elif change == "count_full":
        plan["prefix_screening"]["target_count"] = len(
            plan["control_request"]["targets_m"]
        )
    elif change == "terminal_policy":
        plan["prefix_screening"]["terminal_limits_used"] = True
    elif change == "request_context":
        request = json.loads(files[f"{folder}/request.json"])
        request["targets_m"][0] *= 1.1
        raw = study._bytes(request)
        files[f"{folder}/request.json"] = raw
        decision["prefix_request"].update(sha256=study._sha(raw), byte_length=len(raw))
    elif change == "decision_action":
        decision["action"] = record["action"] = (
            "reject_history_maximum"
            if decision["action"] != "reject_history_maximum"
            else "execute_full_reference"
        )
    elif change == "decision_model":
        decision["model_checksum"] = "sha256:" + "0" * 64
    elif change == "full_acceptance":
        decision["full_history_acceptance"] = True
    elif change == "violations":
        decision["history_maximum_violations"] = [
            {"metric": "terminal_maximum_translation_m", "value": 3, "limit": 1}
        ]
    elif change == "missing_decision":
        info["decisions"].pop()
    elif change == "extra_decision":
        info["decisions"].append(record)
    elif change == "rejected_ids":
        info["rejected_history_maximum_candidate_ids"] = ["baseline"]
    elif change == "prefix_work":
        info["prefix_execution_work"] = _work({"rows": []})
    elif change == "exclude_prefix_work":
        result["arms"][strategy]["execution_work"] = _work(comparison)
    elif change == "row_performance":
        row["performance"]["maximum_absolute_fiber_strain"] = 0
        row["screens"]["maximum_absolute_fiber_strain"].update(value=0, status="pass")
        row["selection_eligible"] = all(
            s["status"] == "pass" for s in row["screens"].values()
        )
    elif change == "row_model":
        row["artifacts"]["model"]["sha256"] = plan["pool"][0]["model_artifact"][
            "sha256"
        ]
    elif change in ("result_request", "verification_flag"):
        role = "result" if change == "result_request" else "verification"
        ref = row["artifacts"][role]
        path = f"{folder}/{ref['path']}"
        doc = json.loads(files[path])
        if role == "result":
            doc["request"]["maximum_targets"] -= 1
            raw = rehash(doc, "result_hash")
        else:
            doc["solver_replay_performed"] = False
            raw = study._bytes(doc)
        files[path] = raw
        ref.update(sha256=study._sha(raw), byte_length=len(raw))
    elif change == "missing_checkpoint":
        files.pop(f"{folder}/{row['artifacts']['checkpoint']['path']}")
    elif change == "path":
        decision["prefix_row"]["path"] = "../row.json"
    elif change == "row_work":
        row["invocations"][0]["work"]["attempted_step_count"] = 0
    if change in (
        "row_performance",
        "row_model",
        "result_request",
        "verification_flag",
        "row_work",
    ):
        raw = study._bytes(row)
        files[f"{folder}/row.json"] = raw
        decision["prefix_row"].update(sha256=study._sha(raw), byte_length=len(raw))
    raw = rehash(decision, "decision_hash")
    files[dpath] = raw
    record["artifact"].update(sha256=study._sha(raw), byte_length=len(raw))
    files["plan.json"] = rehash(plan, "plan_hash")
    result["plan_hash"] = plan["plan_hash"]
    result["prefix_screening"] = plan["prefix_screening"]
    files[cpath] = rehash(comparison, "report_hash")
    result["arms"][strategy]["comparison_hash"] = comparison["report_hash"]
    result["arms"][strategy]["prefix_screening"] = info
    files["result.json"] = rehash(result, "report_hash")
    with pytest.raises(ValueError):
        RcSearchArtifactBundle.from_reader(
            lambda name, maximum: files[name],
            expected_report_hash=result["report_hash"],
        )


@pytest.mark.parametrize("staged", [("price_order", 1)], indirect=True)
def test_known_prefix_verification_failure_cannot_replace_full_acceptance(staged):
    _, _, bundle, strategy = staged
    files = dict(bundle.artifacts)
    result = json.loads(files["result.json"])
    path = f"{strategy}/comparison.json"
    comparison = json.loads(files[path])
    record = comparison["prefix_screening"]["decisions"][0]
    dpath = f"{strategy}/{record['artifact']['path']}"
    folder = dpath.rsplit("/", 1)[0]
    decision = json.loads(files[dpath])
    row = json.loads(files[f"{folder}/row.json"])
    ref = row["artifacts"]["verification"]
    vpath = f"{folder}/{ref['path']}"
    verification = json.loads(files[vpath])
    verification.update(
        solver_replay_performed=False, errors=["simulated verification failure"]
    )
    raw = study._bytes(verification)
    files[vpath] = raw
    ref.update(sha256=study._sha(raw), byte_length=len(raw))
    row.update(
        full_reference_verification_pass=False,
        selection_eligible=False,
        status="verification_blocked",
        performance=None,
        screens=None,
        failure={"phase": "verification", "kind": "simulated"},
    )
    raw = study._bytes(row)
    files[f"{folder}/row.json"] = raw
    decision["prefix_row"].update(sha256=study._sha(raw), byte_length=len(raw))
    decision.update(
        prefix_verified=False,
        history_maximum_violations=[],
        action="execute_full_reference",
    )
    files[dpath] = rehash(decision, "decision_hash")
    record["artifact"].update(
        sha256=study._sha(files[dpath]), byte_length=len(files[dpath])
    )
    files[path] = rehash(comparison, "report_hash")
    result["arms"][strategy].update(
        comparison_hash=comparison["report_hash"],
        prefix_screening=comparison["prefix_screening"],
    )
    files["result.json"] = rehash(result, "report_hash")
    admitted = RcSearchArtifactBundle.from_reader(
        lambda name, maximum: files[name], expected_report_hash=result["report_hash"]
    )
    assert (
        admitted.artifacts[f"{strategy}/small/baseline/result.json"]
        == bundle.artifacts[f"{strategy}/small/baseline/result.json"]
    )
    assert result["arms"][strategy]["selected_candidate_id"] == "large"


def test_actual_staged_preload_graph_admits_original_preload_work(inputs, tmp_path):  # noqa: F811
    from dataclasses import replace

    options = {
        k: v for k, v in inputs.items() if k not in ("policy", "training_report")
    }
    options.update(
        request=replace(
            options["request"], constant_nodal_loads=(("N3", 0.0, -0.1, 0.0),)
        ),
        full_analysis_budget=3,
        history_limits=design.FiberFrameHistoryLimits(1, 2e-6),
    )
    root = tmp_path / "staged-preload"
    result = search.run_control_layout_staged_strategy(
        **options, strategy="price_order", prefix_target_count=2, output_directory=root
    )
    bundle = RcSearchArtifactBundle.from_directory(
        root, expected_report_hash=result["report_hash"]
    )
    assert "price_order/prefix/small/baseline/result.json" in bundle.artifacts
    prefix = json.loads(bundle.artifacts["price_order/prefix/small/decision.json"])
    assert prefix["execution_work"]["known_counters"]["attempted_step_count"] == 6
