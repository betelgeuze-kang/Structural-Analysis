"""Real M2/search serialization with retained rows and synthetic material data.

The imported fixture forbids analysis, fitting and subprocess execution. This
checks the producer/consumer row-order contract, not new physical evidence.
"""

from copy import deepcopy
import json

import pytest

from structural_analysis.benchmark import fiber_frame_candidate_search as search
from structural_analysis.benchmark import fiber_frame_candidate_search_arm as arm
from structural_analysis.benchmark import fiber_frame_candidate_search_suite as suite
from tests.test_fiber_frame_candidate_material_contract import (
    arguments as _arguments,
    material_request as _material_request,
    no_execution as _no_execution,
    retained as _retained,
    stub_rows as _stub_rows,
)


@pytest.fixture(autouse=True)
def no_execution(monkeypatch):
    return _no_execution.__wrapped__(monkeypatch)


@pytest.fixture(scope="module")
def retained():
    return _retained.__wrapped__()


@pytest.fixture
def material_request(tmp_path, retained):
    return _material_request.__wrapped__(tmp_path, retained)


@pytest.fixture
def arguments(material_request):
    return _arguments.__wrapped__(material_request)


@pytest.fixture
def stub_rows(retained, monkeypatch):
    return _stub_rows.__wrapped__(retained, monkeypatch)


def test_material_multi_candidate_bundle_preserves_execution_order(
    arguments, stub_rows, tmp_path
):
    options = {
        **arguments,
        "candidates": tuple(reversed(arguments["candidates"])),
        "full_analysis_budget": 3,
        "exploration_slots": 0,
    }
    expectations = arm.prepare_fiber_frame_candidate_search_expectations(**options)
    binding = expectations["input_binding"]
    result = search.compare_fiber_frame_candidate_search(**options, oracle_audit=False)
    report = result.to_dict()
    (tmp_path / "producer-report.json").write_text(json.dumps(report, sort_keys=True))

    declared = [row["candidate_id"] for row in report["candidate_pool"]]
    assert declared == ["near-limit", "narrow"]
    assert report["arms"][0]["shortlist"] == ["narrow", "near-limit"]
    assert report["status"] == "ready"
    assert len(stub_rows) == 6  # Two arms; each has one baseline and two candidates.

    for produced in report["arms"]:
        assert [
            row["candidate_id"] for row in produced["candidate_outcomes"]
        ] == declared
        by_id = {row["candidate_id"]: row for row in produced["candidate_outcomes"]}
        requested = [
            produced["baseline"],
            *(by_id[key] for key in produced["shortlist"]),
        ]
        assert [
            row["candidate_id"] for row in produced["design_comparison"]["rows"]
        ] == ["baseline", *produced["shortlist"]]
        # The unchanged producer bundle is valid when checked in execution order.
        arm._validate_bundle(produced, requested, binding)

    before = deepcopy(report)
    suite._validate_report(report, binding, suite.STRATEGIES, False)
    assert report == before
