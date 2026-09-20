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
    from copy import deepcopy
    from scripts.run_rc_cost_pruning_campaign import pair_evidence

    assert pair_evidence(full, pruned)["comparable"] is True
    for mutation in (
        "unknown",
        "mismatch",
        "unselected",
        "input",
        "incomplete",
        "erased_work",
        "duplicate_row",
    ):
        changed = deepcopy(pruned)
        if mutation == "erased_work":
            changed["rows"][0]["invocations"] = []
        elif mutation == "duplicate_row":
            changed["rows"].append(deepcopy(changed["rows"][0]))
        elif mutation == "unknown":
            changed["rows"][0]["invocations"][0]["unknown_execution_work"] = True
        elif mutation == "mismatch":
            changed["rows"][0]["artifacts"]["result"]["sha256"] = "sha256:" + "0" * 64
        elif mutation == "unselected":
            changed["selected_candidate_id"] = None
        elif mutation == "input":
            changed["price_table_hash"] = "sha256:" + "0" * 64
        else:
            changed["status"] = "incomplete"
        assert pair_evidence(full, changed)["comparable"] is False
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


def test_campaign_retains_malformed_attempt_costs_and_missing_denominators():
    from scripts.run_rc_cost_pruning_campaign import summarize_pair, campaign_complete

    processes = {
        "full": {"return_code": 0, "wall_ns": 100},
        "pruned": {"return_code": 0, "wall_ns": 80},
    }
    malformed = summarize_pair({"full": {}, "pruned": {}}, processes)
    assert not malformed["comparable"] and "audit_error" in malformed
    assert malformed["pruned_over_full_process_ratio"] is None
    assert malformed["processes"] == processes
    missing = summarize_pair({"full": {}}, processes)
    assert missing["missing_report_modes"] == ["pruned"]
    assert missing["processes"]["pruned"]["wall_ns"] == 80
    assert not campaign_complete(
        {"planned_case_count": 1, "planned_pair_count": 2, "cases": []}
    )
    assert not campaign_complete(
        {
            "planned_case_count": 1,
            "planned_pair_count": 2,
            "cases": [{"pairs": [malformed]}],
        }
    )


def test_campaign_reader_rejects_ambiguous_json(tmp_path):
    from scripts.run_rc_cost_pruning_campaign import inspect_report

    (tmp_path / "comparison.json").write_text(
        '{"report_hash":"one","report_hash":"two"}'
    )
    with pytest.raises(ValueError):
        inspect_report(tmp_path)


@pytest.mark.parametrize('mutation', ['unbalanced', 'duplicate_mode', 'count', 'failed'])
def test_l_frame_audit_rejects_changed_protocol_before_reading_results(
    tmp_path, monkeypatch, mutation
):
    import importlib
    from pathlib import Path

    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'scripts'))
    campaign = importlib.import_module('audit_rc_l_frame_cost_campaign')
    plan = {'orders': [['full', 'pruned'], ['pruned', 'full']] * 2,
            'planned_process_count': 8}
    outcome = {'pairs': [{}, {}, {}, {}], 'all_pairs_comparable': True}
    if mutation == 'unbalanced':
        plan['orders'] = [['full', 'pruned']] * 4
    elif mutation == 'duplicate_mode':
        plan['orders'][0] = ['full', 'full']
    elif mutation == 'count':
        plan['planned_process_count'] = 6
    else:
        outcome['all_pairs_comparable'] = False
    (tmp_path / 'plan.json').write_text(json.dumps(plan))
    (tmp_path / 'outcome.json').write_text(json.dumps(outcome))
    with pytest.raises(ValueError, match='denominator|successful campaign'):
        campaign.audit(tmp_path)


def test_campaign_all_failed_processes_still_finalize_every_planned_pair(
    tmp_path, monkeypatch
):
    from types import SimpleNamespace
    from scripts import run_rc_cost_pruning_campaign as campaign

    root = tmp_path / "failed-campaign"
    monkeypatch.setattr(campaign.sys, "argv", ["campaign", "--output", str(root)])
    monkeypatch.setattr(campaign.subprocess, "check_output", lambda *a, **k: "a" * 40)
    monkeypatch.setattr(
        campaign.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=2)
    )
    assert campaign.main() == 1
    summary = json.loads((root / "summary.json").read_bytes())
    protocol = json.loads((root / "protocol.json").read_bytes())
    assert (
        len(summary["cases"]) == summary["planned_case_count"] == len(protocol["cases"])
    )
    pairs = [p for c in summary["cases"] for p in c["pairs"]]
    assert len(pairs) == summary["planned_pair_count"]
    for pair in pairs:
        assert pair["pruned_over_full_process_ratio"] is None
        assert pair["missing_report_modes"] == ["full", "pruned"]
        assert all(
            p["return_code"] == 2 and p["wall_ns"] > 0 and "audit_error" in p
            for p in pair["processes"].values()
        )
    assert (root / "inventory.json").is_file()
