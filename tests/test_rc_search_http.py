"""Real original search files through the read-only authenticated mount."""

import json
from pathlib import Path
import shutil

import pytest

from structural_analysis.execution.rc_search_http import (
    RcSearchArtifactBundle,
    RcSearchArtifactWSGIApplication,
)

ROOT = Path("tests/frontend/fixtures/rc-control-search")
HEADERS = {"X-Structural-Tenant": "alpha", "Authorization": "Bearer synthetic-alpha"}


def authorizer(tenant, token):
    return (tenant, token) in {("alpha", "synthetic-alpha"), ("beta", "synthetic-beta")}


@pytest.fixture(scope="module")
def bundle():
    expected = json.loads((ROOT / "result.json").read_bytes())["report_hash"]
    return RcSearchArtifactBundle.from_directory(ROOT, expected_report_hash=expected)


@pytest.fixture
def app(bundle):
    return RcSearchArtifactWSGIApplication(
        {("alpha", "experiment"): bundle}, authorize=authorizer
    )


def route(name="result.json"):
    return "/v1/rc-search/experiment/" + name


def test_original_artifact_graph_and_response_bytes(bundle, app):
    # Only actual graph references enter the mount. Producer logs, reservations,
    # duplicate request files and the fixture provenance file stay outside it.
    assert len(bundle.artifacts) == 75
    assert "provenance.json" not in bundle.artifacts
    assert "price_order-started.json" not in bundle.artifacts
    for name, raw in bundle.artifacts.items():
        result = app.handle("GET", route(name), headers=HEADERS)
        assert result.status == 200 and result.body == raw == (ROOT / name).read_bytes()
        assert result.headers["content-length"] == str(len(raw))
        assert result.headers["cache-control"] == "no-store"
        assert result.headers["x-content-type-options"] == "nosniff"


@pytest.mark.parametrize(
    "headers,status",
    [
        ({}, 401),
        ({"X-Structural-Tenant": "alpha", "Authorization": "Bearer wrong"}, 401),
        (
            {"X-Structural-Tenant": "beta", "Authorization": "Bearer synthetic-beta"},
            404,
        ),
        (
            {"X-Structural-Tenant": "beta", "Authorization": "Bearer synthetic-alpha"},
            401,
        ),
    ],
)
def test_credentials_bind_tenant_before_snapshot_lookup(app, headers, status):
    result = app.handle("GET", route(), headers=headers)
    assert result.status == status and b"synthetic-" not in result.body


@pytest.mark.parametrize(
    "name",
    [
        "../result.json",
        "pool/../result.json",
        "%2e%2e/result.json",
        "pool\\baseline.json",
        "result.json?x=1",
        "result.json#x",
        "provenance.json",
        "price_order-started.json",
        "unknown.json",
        "pool/hidden.env.json",
    ],
)
def test_only_exact_registered_paths_can_be_read(app, name):
    assert app.handle("GET", route(name), headers=HEADERS).status == 404


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE", "HEAD"])
def test_no_mutation_or_execution_routes(app, method):
    assert app.handle(method, route(), headers=HEADERS).status == 405


def test_callback_failure_and_truthy_non_boolean_do_not_authorize(bundle):
    def broken(*args):
        raise RuntimeError("private credential backend details")

    for callback in [broken, lambda *args: "yes"]:
        app = RcSearchArtifactWSGIApplication(
            {("alpha", "experiment"): bundle}, authorize=callback
        )
        response = app.handle("GET", route(), headers=HEADERS)
        assert response.status == 401 and b"private" not in response.body


def test_snapshots_are_immutable_and_no_disk_read_occurs_during_http(
    bundle, monkeypatch
):
    with pytest.raises(TypeError):
        bundle.artifacts["result.json"] = b"changed"
    mounts = {("alpha", "experiment"): bundle}
    app = RcSearchArtifactWSGIApplication(mounts, authorize=authorizer)
    mounts.clear()
    monkeypatch.setattr(
        Path,
        "open",
        lambda *a, **k: pytest.fail("HTTP must not read mutable filesystem paths"),
    )
    assert (
        app.handle("GET", route(), headers=HEADERS).body
        == bundle.artifacts["result.json"]
    )


def test_pin_mismatch_rejects_before_other_artifacts():
    calls = []

    def read(path, maximum):
        calls.append(path)
        return (ROOT / path).read_bytes()

    with pytest.raises(ValueError, match="pinned search result mismatch"):
        RcSearchArtifactBundle.from_reader(
            read, expected_report_hash="sha256:" + "0" * 64
        )
    assert calls == ["result.json"]


@pytest.mark.parametrize(
    "name", ["plan.json", "pool/middle.json", "learned_order/cheap/result.json"]
)
def test_changed_bytes_prevent_publication(name):
    expected = json.loads((ROOT / "result.json").read_bytes())["report_hash"]

    def read(path, maximum):
        raw = (ROOT / path).read_bytes()
        return (
            raw.replace(b'"schema_version":"', b'"schema_version":"changed-', 1)
            if path == name
            else raw
        )

    with pytest.raises(ValueError):
        RcSearchArtifactBundle.from_reader(read, expected_report_hash=expected)


def test_bounded_reader_and_symlinks_fail_before_snapshot(tmp_path):
    with pytest.raises(ValueError, match="budget"):
        RcSearchArtifactBundle.from_reader(
            lambda p, m: b"x" * (m + 1), expected_report_hash="sha256:" + "a" * 64
        )
    linked = tmp_path / "linked"
    try:
        linked.symlink_to(ROOT.resolve(), target_is_directory=True)
    except OSError:
        pytest.skip("host cannot create symlinks")
    expected = json.loads((ROOT / "result.json").read_bytes())["report_hash"]
    with pytest.raises(ValueError, match="real directory"):
        RcSearchArtifactBundle.from_directory(linked, expected_report_hash=expected)


def test_snapshot_retains_pinned_bytes_when_original_directory_later_changes(tmp_path):
    copy = tmp_path / "copy"
    shutil.copytree(ROOT, copy)
    expected = json.loads((copy / "result.json").read_bytes())["report_hash"]
    bundle = RcSearchArtifactBundle.from_directory(copy, expected_report_hash=expected)
    original = bundle.artifacts["pool/middle.json"]
    (copy / "pool/middle.json").write_bytes(b"changed")
    app = RcSearchArtifactWSGIApplication(
        {("alpha", "experiment"): bundle}, authorize=authorizer
    )
    assert (
        app.handle("GET", route("pool/middle.json"), headers=HEADERS).body == original
    )


def test_wsgi_read_only_framing_and_query_guard(app):
    class ForbiddenStream:
        def read(self, *args):
            pytest.fail("read-only mount must not consume request bodies")

    base = {
        "PATH_INFO": route(),
        "REQUEST_METHOD": "GET",
        "HTTP_X_STRUCTURAL_TENANT": "alpha",
        "HTTP_AUTHORIZATION": "Bearer synthetic-alpha",
        "wsgi.input": ForbiddenStream(),
    }
    for extra, status in [
        ({}, "200"),
        ({"CONTENT_LENGTH": "999999999"}, "400"),
        ({"CONTENT_LENGTH": "invalid"}, "400"),
        ({"HTTP_TRANSFER_ENCODING": "chunked"}, "400"),
        ({"QUERY_STRING": "ignored=no"}, "404"),
    ]:
        observed = []
        body = b"".join(app(base | extra, lambda s, h: observed.append((s, h))))
        assert observed[0][0].startswith(status)
        assert dict(observed[0][1])["Content-Length"] == str(len(body))


def test_search_without_oracle_mounts_only_its_actual_graph():
    root = Path("tests/frontend/fixtures/rc-control-search-no-oracle")
    expected = json.loads((root / "result.json").read_bytes())["report_hash"]
    bundle = RcSearchArtifactBundle.from_directory(root, expected_report_hash=expected)
    assert len(bundle.artifacts) == 42
    assert all(not path.startswith("exhaustive_oracle/") for path in bundle.artifacts)
    app = RcSearchArtifactWSGIApplication(
        {("alpha", "experiment"): bundle}, authorize=authorizer
    )
    assert (
        app.handle("GET", route(), headers=HEADERS).body
        == (root / "result.json").read_bytes()
    )
    assert (
        app.handle(
            "GET", route("exhaustive_oracle/comparison.json"), headers=HEADERS
        ).status
        == 404
    )


@pytest.mark.parametrize(
    "mutation", [None, "unknown_strategy", "old_version", "missing_ranking"]
)
def test_new_ranking_plan_snapshot_binds_version_and_named_strategy(mutation):
    from structural_analysis.benchmark.rc_control_candidate_ranking import (
        candidate_ranking,
        CHEAPER_BOUNDARY_RANKING,
    )
    from structural_analysis.execution.rc_search_http import _sha

    # Controlled metadata upgrade preserves the old fixture's same schedule.
    plan = json.loads((ROOT / "plan.json").read_bytes())
    plan["schema_version"] = "experimental-rc-control-candidate-search-plan.v3"
    plan["ranking"] = candidate_ranking(plan["predictions"], CHEAPER_BOUNDARY_RANKING)[
        1
    ]
    if mutation == "unknown_strategy":
        plan["ranking"]["strategy"] = "unknown"
    if mutation == "old_version":
        plan["schema_version"] = "experimental-rc-control-candidate-search-plan.v2"
    if mutation == "missing_ranking":
        plan.pop("ranking")

    def hashed(value, field):
        value.pop(field)

        def raw():
            return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()

        value[field] = _sha(raw())
        return raw()

    plan_bytes = hashed(plan, "plan_hash")
    result = json.loads((ROOT / "result.json").read_bytes())
    result["plan_hash"] = plan["plan_hash"]
    result_bytes = hashed(result, "report_hash")

    def read(name, maximum):
        return {"plan.json": plan_bytes, "result.json": result_bytes}.get(name) or (
            ROOT / name
        ).read_bytes()

    if mutation is not None:
        with pytest.raises(ValueError, match="metadata binding"):
            RcSearchArtifactBundle.from_reader(
                read, expected_report_hash=result["report_hash"]
            )
    else:
        b = RcSearchArtifactBundle.from_reader(
            read, expected_report_hash=result["report_hash"]
        )
        assert b.artifacts["plan.json"] == plan_bytes and len(b.artifacts) == 75


def standalone_documents(strategy):
    """Controlled metadata conversion; it is not a new physical execution."""
    plan = json.loads((ROOT / "plan.json").read_bytes())
    report = json.loads((ROOT / "result.json").read_bytes())
    plan.update(
        schema_version="experimental-rc-control-candidate-strategy-plan.v1",
        strategy=strategy,
        oracle_after_online_arms=False,
        plans={strategy: plan["plans"][strategy]},
    )
    report.update(
        schema_version="experimental-rc-control-candidate-strategy.v1",
        strategy=strategy,
        oracle=None,
        arms={strategy: report["arms"][strategy]},
    )
    if strategy == "price_order":
        plan.update(
            predictions=[],
            policy_hash=None,
            training_report_hash=None,
            original_training_and_pool_models_disjoint=None,
        )
        report.update(
            historical_training_cost=None,
            candidate_coverage_audit=None,
            ranking_wall_ns=0,
        )
    return plan, report


def standalone_reader(plan, report):
    from structural_analysis.benchmark.rc_control_design import _bytes, _sha

    def bind(doc, key):
        doc.pop(key, None)
        doc[key] = _sha(_bytes(doc))
        return _bytes(doc)

    plan_raw = bind(plan, "plan_hash")
    report["plan_hash"] = plan["plan_hash"]
    result_raw = bind(report, "report_hash")
    calls = []

    def read(name, maximum):
        calls.append(name)
        if name == "plan.json":
            return plan_raw
        if name == "result.json":
            return result_raw
        return (ROOT / name).read_bytes()

    return read, calls


@pytest.mark.parametrize("strategy", ["price_order", "learned_order"])
def test_standalone_graph_only_reads_declared_strategy(strategy):
    plan, report = standalone_documents(strategy)
    read, calls = standalone_reader(plan, report)
    bundle = RcSearchArtifactBundle.from_reader(
        read, expected_report_hash=report["report_hash"]
    )
    other = "learned_order" if strategy == "price_order" else "price_order"
    assert not any(p.startswith((other + "/", "exhaustive_oracle/")) for p in calls)
    assert ("policy.json" in calls) is (strategy == "learned_order")
    assert ("historical-training.json" in calls) is (strategy == "learned_order")
    assert "strategy-runtime.json" not in calls
    app = RcSearchArtifactWSGIApplication(
        {("alpha", "experiment"): bundle}, authorize=authorizer
    )
    for name, raw in bundle.artifacts.items():
        response = app.handle("GET", route(name), headers=HEADERS)
        assert response.status == 200 and response.body == raw
    for path in [
        other + "/comparison.json",
        "exhaustive_oracle/comparison.json",
        "strategy-runtime.json",
    ]:
        assert app.handle("GET", route(path), headers=HEADERS).status == 404
    assert app.handle("GET", route(), headers={}).status == 401


@pytest.mark.parametrize(
    "mutation",
    [
        "other_plan_strategy",
        "oracle",
        "other_arm",
        "legacy_schema",
        "policy_hash",
        "predictions",
        "training",
        "missing_null",
        "ranking_time_bool",
        "shortlist",
    ],
)
def test_rehashed_standalone_cross_bindings_reject(mutation):
    plan, report = standalone_documents("price_order")
    if mutation == "other_plan_strategy":
        plan["strategy"] = "learned_order"
    elif mutation == "oracle":
        report["oracle"] = {"status": "completed"}
    elif mutation == "other_arm":
        report["arms"]["learned_order"] = report["arms"]["price_order"]
    elif mutation == "legacy_schema":
        report["schema_version"] = "experimental-rc-control-candidate-search.v3"
    elif mutation == "policy_hash":
        plan["policy_hash"] = "sha256:" + "a" * 64
    elif mutation == "predictions":
        plan["predictions"] = [{}]
    elif mutation == "training":
        report["historical_training_cost"] = {}
    elif mutation == "missing_null":
        plan.pop("policy_hash")
    elif mutation == "ranking_time_bool":
        report["ranking_wall_ns"] = False
    elif mutation == "shortlist":
        plan["plans"]["price_order"]["shortlist"] = ["middle"]
    read, _ = standalone_reader(plan, report)
    with pytest.raises(ValueError):
        RcSearchArtifactBundle.from_reader(
            read, expected_report_hash=report["report_hash"]
        )
