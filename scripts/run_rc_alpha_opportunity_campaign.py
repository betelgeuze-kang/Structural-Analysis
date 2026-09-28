"""Prospective training-only screen for RC line-search work on harder histories.

This measures the optimized secant baseline; it does not fit or deploy an alpha
policy. The three synthetic cases share one authored template and are not
independent-project evidence. Failed paths remain in the declared denominator.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import re
import subprocess
from time import perf_counter_ns

if __package__:
    from .screen_rc_line_search_alpha import _line_rows
else:
    from screen_rc_line_search_alpha import _line_rows
from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    BoundedRCFiberDirectControlRequest,
)
from structural_analysis.benchmark import rc_control_learning as learning
from structural_analysis.benchmark.rc_control_design import _bytes, _save, _sha
from structural_analysis.benchmark.rc_control_learning_split import (
    control_training_exclusion_groups,
    validate_control_learning_split_shapes,
)
from structural_analysis.benchmark.rc_control_seed_runtime import (
    benchmark_rc_control_seed_paths,
)
from structural_analysis.io.neutral.loader import load_neutral_json_bytes


ARITHMETIC = "retained-twofold-refinement.v1"
ALPHAS = tuple(2.0**-index for index in range(13))
CASES = (
    (
        "train-alpha-h",
        2.45,
        2.05,
        (-0.75, -2.25, -4.5, -12.0, -4.8, 2.4, 7.2, 10.2, 3.6, -3.6, -8.4, 0.0),
    ),
    (
        "train-alpha-i",
        3.15,
        2.55,
        (-0.75, -2.25, -4.5, -14.4, -5.4, 2.7, 8.1, 11.7, 4.2, -4.2, -9.6, 0.0),
    ),
    (
        "train-alpha-j",
        3.65,
        2.95,
        (-0.75, -2.25, -4.5, -16.8, -6.0, 3.0, 9.0, 13.2, 4.8, -4.8, -10.8, 0.0),
    ),
)


def prepare_cases():
    template_path = (
        Path(__file__).resolve().parents[1]
        / "examples/public_rc_fiber_frame_l_frame_material_history.json"
    )
    template = json.loads(template_path.read_bytes())
    cases = []
    for case_id, width, height, targets_mm in CASES:
        model_json = json.loads(json.dumps(template))
        for node in model_json["nodes"]:
            if node["id"] == "N2":
                node["coordinates"] = [width, 0.0, 0.0]
            elif node["id"] == "N3":
                node["coordinates"] = [width, height, 0.0]
        model = load_neutral_json_bytes(
            _bytes(model_json), source_path=f"memory://{case_id}.json"
        )
        request = BoundedRCFiberDirectControlRequest(
            7,
            tuple(value / 1000 for value in targets_mm),
            allow_reversals=True,
            maximum_reversals=5,
            constant_nodal_loads=(("N3", 0.0, -20.0, 0.0),),
        )
        request = replace(
            request,
            solver_config=replace(
                request.solver_config,
                newton=replace(
                    request.solver_config.newton,
                    terminal_polishing=True,
                    line_search_alphas=ALPHAS,
                ),
            ),
        )
        cases.append(
            learning.RCControlLearningCase(
                case_id,
                f"synthetic-{case_id}",
                f"synthetic-{case_id}",
                f"synthetic-{case_id}",
                "train",
                model,
                request,
            )
        )
    validate_control_learning_split_shapes(cases)
    groups = control_training_exclusion_groups(cases)["groups"]
    if groups != [[case.case_id] for case in cases]:
        raise ValueError("three distinct training shape/history groups required")
    return cases


def _account_trial_dispatches(rows, calls):
    """Join each recorded trial to one timed assembly in solver order."""
    if type(rows) is not list or type(calls) is not list:
        raise ValueError("original trial rows and assembly calls required")
    trials = [call for call in calls if call.get("phase") == "line_search"]
    if len(trials) != sum(row["trial_count"] for row in rows):
        raise ValueError("trial trace and line-search assembly count differ")
    if any(
        call.get("status") != "returned"
        or type(call.get("wall_ns")) is not int
        or call["wall_ns"] < 0
        for call in trials
    ):
        raise ValueError("complete measured line-search dispatches required")
    offset = 0
    failed_wall = 0
    for row in rows:
        count = row["trial_count"]
        failed_count = row["observed_failed_trial_count"]
        if (
            type(count) is not int
            or type(failed_count) is not int
            or not 0 <= failed_count <= count
        ):
            raise ValueError("bounded original failed-trial count required")
        failed_wall += sum(
            call["wall_ns"] for call in trials[offset : offset + failed_count]
        )
        offset += count
    return {
        "trial_dispatches": len(trials),
        "failed_trial_dispatch_wall_ns": failed_wall,
    }


def summarize_completed_secant(root, report, case):
    if (
        report.get("model_checksum") != case.model.canonical_model_checksum
        or report.get("request") != case.request.to_dict()
        or report.get("reference_repeat_exact") is not True
        or report.get("all_execution_work_reported") is not True
        or report["arms"]["reference"]["status"] != "complete"
        or report["arms"]["secant"]["status"] != "complete"
        or report["fresh_reference"]["status"] != "complete"
        or not all(row["full_history_pass"] for row in report["comparisons"].values())
    ):
        raise ValueError("complete original reference/secant paths required")
    arm = report["arms"]["secant"]
    if len(arm["entries"]) != len(case.request.targets_m):
        raise ValueError("complete target roster required")
    totals = {
        "line_searches": 0,
        "trials": 0,
        "failed_trials": 0,
        "nonunit_first_accepts": 0,
        "null_accepts": 0,
        "failed_trial_dispatch_wall_ns": 0,
    }
    for target_index, entry in enumerate(arm["entries"]):
        invocations = entry["invocations"]
        if (
            entry["target_index"] != target_index
            or len(invocations) != 1
            or invocations[0]["status"] != "returned"
            or invocations[0]["unknown_work"] is not False
        ):
            raise ValueError("retries or unknown work cannot provide a complete label")
        step_path = root / "secant" / f"{target_index:03d}-1-step.json"
        context_path = root / "secant" / f"{target_index:03d}-context.json"
        outcome_path = root / "secant" / f"{target_index:03d}-1-outcome.json"
        step_bytes, context_bytes = step_path.read_bytes(), context_path.read_bytes()
        step, context = json.loads(step_bytes), json.loads(context_bytes)
        outcome = json.loads(outcome_path.read_bytes())
        if step.get("status") != "ready" or step.get("committed") is not True:
            raise ValueError("selected secant step must be committed")
        rows = _line_rows(
            step,
            context,
            case_id=case.case_id,
            target_index=target_index,
            step_path=str(step_path.relative_to(root)),
            step_sha256=hashlib.sha256(step_bytes).hexdigest(),
            context_path=str(context_path.relative_to(root)),
            context_sha256=hashlib.sha256(context_bytes).hexdigest(),
        )
        work = outcome["newton_assembly_work"]
        joined = _account_trial_dispatches(rows, work["calls"])
        totals["line_searches"] += len(rows)
        totals["trials"] += joined["trial_dispatches"]
        totals["failed_trials"] += sum(
            row["observed_failed_trial_count"] for row in rows
        )
        totals["nonunit_first_accepts"] += sum(
            row["first_accepted_index"] not in (None, 0) for row in rows
        )
        totals["null_accepts"] += sum(
            row["first_accepted_index"] is None for row in rows
        )
        totals["failed_trial_dispatch_wall_ns"] += joined[
            "failed_trial_dispatch_wall_ns"
        ]
    if totals["trials"] != totals["line_searches"] + totals["failed_trials"]:
        raise ValueError("trial and first-accept accounting differs")
    totals.update(
        secant_path_wall_ns=arm["wall_ns"],
        secant_line_search_assembly_wall_ns=report["assembly_phase_work"]["secant"][
            "phase_wall_ns"
        ].get("line_search"),
        reference_path_wall_ns=report["arms"]["reference"]["wall_ns"],
        whole_benchmark_wall_ns=report["whole_study_wall_ns"],
        report_hash=report["report_hash"],
    )
    return totals


def _clean_head():
    repo = Path(__file__).resolve().parents[1]
    head = subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
    ).strip()
    status = subprocess.check_output(
        ["git", "-C", str(repo), "status", "--porcelain"], text=True
    )
    if not re.fullmatch(r"[0-9a-f]{40}", head) or status:
        raise ValueError("exact clean committed source required")
    return head


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    cases = prepare_cases()
    if args.preflight_only:
        print(
            json.dumps({"cases": [case.case_id for case in cases], "solver_calls": 0})
        )
        return
    head = _clean_head()
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    plan = {
        "schema_version": "rc-alpha-training-opportunity-plan.v1",
        "source_revision": head,
        "source_template": "examples/public_rc_fiber_frame_l_frame_material_history.json",
        "arithmetic_profile": ARITHMETIC,
        "cases": [
            {
                "case_id": case.case_id,
                "split": case.split,
                "project_id": case.project_id,
                "geometry_family_id": case.geometry_family_id,
                "load_history_id": case.load_history_id,
                "model": case.model.canonical_payload(),
                "request": case.request.to_dict(),
            }
            for case in cases
        ],
        "full_paths_per_case": ["reference", "secant", "fresh-reference"],
        "record_assembly_work": True,
        "record_assembly_timing": True,
        "reuse_line_search_assembly": True,
        "failed_paths_in_denominator": True,
        "train_only": True,
        "independent_project_provenance": False,
        "learned_policy_fits": 0,
        "counterfactual_alpha_path_executed": False,
        "net_savings_proved": False,
    }
    plan["plan_hash"] = _sha(_bytes(plan))
    _save(root, "plan.json", _bytes(plan))
    results = []
    for case in cases:
        case_root = root / case.case_id
        _save(
            root,
            f"{case.case_id}-started.json",
            _bytes(
                {
                    "case_id": case.case_id,
                    "plan_hash": plan["plan_hash"],
                    "status": "started",
                    "unknown_work_until_outcome": True,
                }
            ),
        )
        start = perf_counter_ns()
        try:
            report = benchmark_rc_control_seed_paths(
                case.model,
                case.request,
                source_revision=head,
                output_directory=case_root,
                record_assembly_work=True,
                record_assembly_timing=True,
                reuse_line_search_assembly=True,
                **learning._arithmetic_kwargs(ARITHMETIC),
            )
            try:
                opportunity = summarize_completed_secant(case_root, report, case)
                status = "complete_eligible"
            except (KeyError, ValueError, TypeError, OSError) as exc:
                opportunity = None
                status = "ineligible_path_or_trace"
                reason = type(exc).__name__ + ": " + str(exc)
            result = {
                "case_id": case.case_id,
                "status": status,
                "report_hash": report["report_hash"],
                "opportunity": opportunity,
                **({"reason": reason} if opportunity is None else {}),
            }
        except Exception as exc:
            result = {
                "case_id": case.case_id,
                "status": "raised",
                "reason": type(exc).__name__ + ": " + str(exc),
                "unknown_work": True,
            }
        result["enclosing_case_wall_ns"] = perf_counter_ns() - start
        _save(root, f"{case.case_id}-outcome.json", _bytes(result))
        results.append(result)
    outcome = {
        "schema_version": "rc-alpha-training-opportunity-outcome.v1",
        "plan_hash": plan["plan_hash"],
        "cases": results,
        "eligible_count": sum(r["status"] == "complete_eligible" for r in results),
        "declared_case_count": len(cases),
        "reserved_cases_executed": False,
        "learned_policy_fits": 0,
        "counterfactual_alpha_path_executed": False,
        "net_savings_proved": False,
    }
    outcome["outcome_hash"] = _sha(_bytes(outcome))
    _save(root, "outcome.json", _bytes(outcome))
    print(json.dumps({"output": str(root), "statuses": [r["status"] for r in results]}))


if __name__ == "__main__":
    main()
