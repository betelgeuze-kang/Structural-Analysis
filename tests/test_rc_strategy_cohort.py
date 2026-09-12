"""Portable snapshots of original fixture graphs with controlled runtime metadata."""

import json
from pathlib import Path

import pytest

from structural_analysis.benchmark.rc_control_design import _bytes, _sha
from structural_analysis.execution.rc_search_http import RcSearchArtifactBundle
from structural_analysis.execution.rc_strategy_cohort import (
    RcStrategyCohortBundle,
    create_rc_strategy_cohort,
)
from tests.test_rc_control_strategy_costs import ROOT, paired, rebind


@pytest.fixture(scope="module")
def inputs():
    pair = paired()
    result = {}
    for strategy, data in pair.items():
        report, plan = data["report"], data["plan"]
        cost = report["candidate_cost_optimality_audit"]
        cost["arms"] = {strategy: cost["arms"][strategy]}
        if strategy == "price_order":
            plan["original_training_and_pool_models_disjoint"] = None
            report["candidate_coverage_audit"] = None
        else:
            audit = report["candidate_coverage_audit"]
            audit["arms"] = {strategy: audit["arms"][strategy]}
            for row in audit["candidates"]:
                row["shortlisted_by"] = [
                    s for s in row["shortlisted_by"] if s == strategy
                ]
        rebind(data)
        originals = {
            "result.json": _bytes(data["report"]),
            "plan.json": _bytes(data["plan"]),
        }
        bundle = RcSearchArtifactBundle.from_reader(
            lambda path, maximum: originals[path]
            if path in originals
            else (ROOT / path).read_bytes(),
            expected_report_hash=data["report"]["report_hash"],
        )
        result[strategy] = (bundle, _bytes(data["runtime"]))
    return (result,)


@pytest.fixture(scope="module")
def bundle(inputs):
    return create_rc_strategy_cohort(inputs, source_revision="a" * 40)


def test_roundtrip_binds_runtime_preserves_original_graph_and_uses_relative_paths(
    bundle, inputs, tmp_path
):
    manifest = json.loads(bundle.artifacts["cohort.json"])
    assert manifest["cost_accounting"]["pair_count"] == 1
    for strategy, (study, runtime) in inputs[0].items():
        prefix = f"pairs/0/{strategy}/"
        for name, raw in study.artifacts.items():
            assert bundle.artifacts[prefix + name] == raw
        assert bundle.artifacts[prefix + "strategy-runtime.json"] == runtime
        assert manifest["pairs"][0][strategy]["runtime"]["sha256"] == _sha(runtime)
    destination = tmp_path / "export"
    bundle.write_directory(destination)
    restored = RcStrategyCohortBundle.from_reader(
        lambda path, maximum: (destination / path).read_bytes(),
        expected_report_hash=bundle.report_hash,
    )
    assert restored.artifacts == bundle.artifacts
    assert all(
        not Path(p).is_absolute() and ".." not in Path(p).parts
        for p in bundle.artifacts
    )
    with pytest.raises(TypeError):
        bundle.artifacts["extra"] = b"changed"
    with pytest.raises(FileExistsError):
        bundle.write_directory(destination)


@pytest.mark.parametrize(
    "mutation",
    [
        "ratio",
        "boolean_count",
        "runtime_hash",
        "path_escape",
        "other_strategy",
        "attestation",
        "extra_claim",
    ],
)
def test_rehashed_manifest_cannot_change_cost_scope_or_original_bindings(
    bundle, mutation
):
    manifest = json.loads(bundle.artifacts["cohort.json"])
    if mutation == "ratio":
        manifest["cost_accounting"]["learned_plus_historical_over_price_ratio"] = 0
    elif mutation == "boolean_count":
        manifest["cost_accounting"]["pair_count"] = True
    elif mutation == "runtime_hash":
        manifest["pairs"][0]["price_order"]["runtime"]["sha256"] = "sha256:" + "0" * 64
    elif mutation == "path_escape":
        manifest["pairs"][0]["price_order"]["runtime"]["path"] = "../runtime.json"
    elif mutation == "other_strategy":
        manifest["pairs"][0]["price_order"]["report_hash"] = manifest["pairs"][0][
            "learned_order"
        ]["report_hash"]
    elif mutation == "attestation":
        manifest["source_revision_is_attestation"] = True
    elif mutation == "extra_claim":
        manifest["net_savings_proved"] = True
    manifest.pop("report_hash")
    manifest["report_hash"] = _sha(_bytes(manifest))
    calls = []

    def read(path, maximum):
        calls.append(path)
        return _bytes(manifest) if path == "cohort.json" else bundle.artifacts[path]

    with pytest.raises(ValueError):
        RcStrategyCohortBundle.from_reader(
            read, expected_report_hash=manifest["report_hash"]
        )
    assert all(".." not in p for p in calls)


@pytest.mark.parametrize(
    "path",
    [
        "pairs/0/price_order/strategy-runtime.json",
        "pairs/0/learned_order/learned_order/cheap/checkpoint.json",
    ],
)
def test_changed_original_bytes_reject_before_publication(bundle, path):
    def read(name, maximum):
        return bundle.artifacts[name] + (b" " if name == path else b"")

    with pytest.raises(ValueError):
        RcStrategyCohortBundle.from_reader(
            read, expected_report_hash=bundle.report_hash
        )


def test_duplicate_execution_and_wrong_runtime_are_not_new_pairs(inputs):
    with pytest.raises(ValueError, match="duplicate"):
        create_rc_strategy_cohort(inputs + inputs, source_revision="a" * 40)
    pair = dict(inputs[0])
    pair["price_order"] = (pair["price_order"][0], pair["learned_order"][1])
    with pytest.raises(ValueError):
        create_rc_strategy_cohort((pair,), source_revision="a" * 40)


def test_failed_export_leaves_no_root_manifest(bundle, tmp_path, monkeypatch):
    original = Path.open

    def failing(self, *args, **kwargs):
        if self.name == "strategy-runtime.json":
            raise OSError("controlled write failure")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", failing)
    root = tmp_path / "partial"
    with pytest.raises(OSError):
        bundle.write_directory(root)
    assert not (root / "cohort.json").exists()


def test_reader_byte_budget_is_enforced(bundle):
    with pytest.raises(ValueError, match="budget"):
        RcStrategyCohortBundle.from_reader(
            lambda path, maximum: b"x" * (maximum + 1),
            expected_report_hash=bundle.report_hash,
        )


def test_cohort_uses_existing_authenticated_read_only_snapshot_mount(bundle):
    from structural_analysis.execution.rc_search_http import (
        RcSearchArtifactWSGIApplication,
    )

    app = RcSearchArtifactWSGIApplication(
        {("alpha", "cohort"): bundle},
        authorize=lambda tenant, token: (tenant, token) == ("alpha", "synthetic"),
    )
    headers = {"X-Structural-Tenant": "alpha", "Authorization": "Bearer synthetic"}
    for path, raw in bundle.artifacts.items():
        response = app.handle("GET", "/v1/rc-search/cohort/" + path, headers=headers)
        assert response.status == 200 and response.body == raw
    assert (
        app.handle("GET", "/v1/rc-search/cohort/cohort.json", headers={}).status == 401
    )
    assert (
        app.handle("POST", "/v1/rc-search/cohort/cohort.json", headers=headers).status
        == 405
    )
    assert (
        app.handle("GET", "/v1/rc-search/cohort/unknown.json", headers=headers).status
        == 404
    )
