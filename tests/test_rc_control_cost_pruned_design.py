"""Actual cost exclusions preserve the verified minimum and unknown feasibility."""

import json
from pathlib import Path

import pytest

from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    BoundedRCFiberDirectControlRequest,
)
from structural_analysis.benchmark import fiber_frame_design as design
from structural_analysis.benchmark import rc_control_design as study
from structural_analysis.io.neutral.loader import load_neutral_json


def inputs():
    return dict(
        baseline=load_neutral_json(
            Path("examples/public_rc_fiber_frame_cantilever.json")
        ),
        candidates=tuple(
            design.FiberFrameDesignCandidate(
                name, (design.FiberFrameSectionChange("RC1", width_m=width),)
            )
            for name, width in [("cheap", 0.3), ("costly", 0.5)]
        ),
        request=BoundedRCFiberDirectControlRequest(
            4, (-1e-5, -2e-5, 1e-5), allow_reversals=True, maximum_reversals=2
        ),
        history_limits=design.FiberFrameHistoryLimits(1, 1),
        material_limits=design.FiberFrameMaterialHistoryLimits(1, 1, 1),
        prices=design.FiberFrameMaterialPrices(
            100, 2, "USD", "2026-09-20", "synthetic test"
        ),
        source_revision="a" * 40,
    )


def test_real_cost_pruning_preserves_full_reference_minimum_without_solving_skipped(
    tmp_path,
):
    args = inputs()
    full = study.compare_rc_control_designs(**args, output_directory=tmp_path / "full")
    pruned = study.compare_rc_control_designs(
        **args, output_directory=tmp_path / "pruned", prune_cost_dominated=True
    )
    assert full["selected_candidate_id"] == pruned["selected_candidate_id"] == "cheap"
    assert (
        full["schema_version"] == study.SCHEMA
        and pruned["schema_version"] == study.PRUNED_SCHEMA
    )
    assert pruned["candidate_denominator"] == 3 and pruned["verified_count"] == 2
    assert pruned["cost_pruning"]["api_invocation_count"] == 4
    assert sum(len(r["invocations"]) for r in full["rows"]) == 6
    skipped = pruned["rows"][2]
    assert skipped["status"] == "skipped_cost_dominated"
    assert skipped["performance"] is None and skipped["screens"] is None
    assert (
        not skipped["full_reference_verification_pass"]
        and not skipped["selection_eligible"]
    )
    assert skipped["invocations"] == [] and set(skipped["artifacts"]) == {
        "model",
        "cost_skip",
    }
    assert not (tmp_path / "pruned/costly/result.json").exists()
    receipt = json.loads((tmp_path / "pruned/costly/cost-skip.json").read_bytes())
    assert receipt["incumbent"]["candidate_id"] == "cheap"
    assert (
        receipt["incumbent"]["result_sha256"]
        == pruned["rows"][1]["artifacts"]["result"]["sha256"]
    )
    assert pruned["cost_pruning"][
        "minimum_scoped_estimate_proved_within_declared_candidates"
    ]
    for a, b in zip(full["rows"][:2], pruned["rows"][:2]):
        assert a["artifacts"]["result"]["sha256"] == b["artifacts"]["result"]["sha256"]


def test_failed_screens_cannot_supply_pruning_incumbent(tmp_path):
    args = inputs()
    args["history_limits"] = design.FiberFrameHistoryLimits(1e-12, 1e-12)
    report = study.compare_rc_control_designs(
        **args, output_directory=tmp_path / "study", prune_cost_dominated=True
    )
    assert report["selected_candidate_id"] is None
    assert report["cost_pruning"]["skipped_count"] == 0
    assert report["cost_pruning"]["api_invocation_count"] == 6
    assert not report["cost_pruning"][
        "minimum_scoped_estimate_proved_within_declared_candidates"
    ]


def test_equal_costs_are_analyzed_and_ties_keep_existing_selection(tmp_path):
    args = inputs()
    args["prices"] = design.FiberFrameMaterialPrices(
        0, 0, "USD", "2026-09-20", "synthetic zero price"
    )
    report = study.compare_rc_control_designs(
        **args, output_directory=tmp_path / "study", prune_cost_dominated=True
    )
    assert report["cost_pruning"]["skipped_count"] == 0
    assert report["cost_pruning"]["api_invocation_count"] == 6
    assert report["selected_candidate_id"] == "baseline"


def test_invalid_expensive_candidate_is_retained_not_labeled_cost_skipped(tmp_path):
    args = inputs()
    args["candidates"] = (
        design.FiberFrameDesignCandidate(
            "invalid", (design.FiberFrameSectionChange("RC1", cover_m=2),)
        ),
    )
    report = study.compare_rc_control_designs(
        **args, output_directory=tmp_path / "study", prune_cost_dominated=True
    )
    assert report["rows"][1]["status"] == "invalid_candidate"
    assert (
        report["candidate_denominator"] == 2
        and report["cost_pruning"]["skipped_count"] == 0
    )
    assert not report["cost_pruning"][
        "minimum_scoped_estimate_proved_within_declared_candidates"
    ]


def test_unpriced_pruning_rejects_before_output(tmp_path):
    args = inputs()
    args["prices"] = None
    with pytest.raises(ValueError, match="price table"):
        study.compare_rc_control_designs(
            **args, output_directory=tmp_path / "study", prune_cost_dominated=True
        )
    assert not (tmp_path / "study").exists()


def test_unknown_execution_work_never_supplies_pruning_evidence(tmp_path, monkeypatch):
    original = study._reference_design_row

    def unknown(*args, **kwargs):
        row = original(*args, **kwargs)
        for invocation in row["invocations"]:
            invocation["unknown_execution_work"] = True
        return row

    monkeypatch.setattr(study, "_reference_design_row", unknown)
    report = study.compare_rc_control_designs(
        **inputs(), output_directory=tmp_path / "study", prune_cost_dominated=True
    )
    assert report["cost_pruning"]["skipped_count"] == 0
    assert report["cost_pruning"]["api_invocation_count"] == 6


def test_pruned_cli_exits_success_and_preserves_full_denominator(tmp_path, capsys):
    from dataclasses import asdict
    from structural_analysis.benchmark import rc_control_design_cli as cli

    args = inputs()
    payloads = {
        "model": args["baseline"].canonical_payload(),
        "request": args["request"].to_dict(),
        "experiment": {
            "schema_version": "rc-fiber-design-experiment.v3",
            "candidates": [c.to_dict() for c in args["candidates"]],
            "prices": asdict(args["prices"]),
            "terminal_limits": None,
            "history_limits": asdict(args["history_limits"]),
            "material_history_limits": asdict(args["material_limits"]),
        },
    }
    argv = [
        "--prune-cost-dominated",
        "--source-revision",
        "a" * 40,
        "--output",
        str(tmp_path / "out"),
    ]
    for key, value in payloads.items():
        path = tmp_path / (key + ".json")
        path.write_text(json.dumps(value))
        argv.extend(["--" + key, str(path)])
    assert cli.main(argv) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["status"] == "complete_with_cost_exclusions"
    assert summary["candidate_denominator"] == 3 and summary["verified_count"] == 2
