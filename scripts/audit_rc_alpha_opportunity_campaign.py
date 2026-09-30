"""Read-only exact-packet audit of the prospective RC alpha opportunity run."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

if __package__:
    from .run_rc_alpha_opportunity_campaign import (
        ALPHAS,
        _account_trial_dispatches,
        prepare_cases,
        summarize_completed_secant,
    )
else:
    from run_rc_alpha_opportunity_campaign import (
        ALPHAS,
        _account_trial_dispatches,
        prepare_cases,
        summarize_completed_secant,
    )
from structural_analysis.benchmark.rc_control_design import _bytes, _sha
from structural_analysis.benchmark.rc_control_seed_runtime import (
    _numeric_payload_difference,
)


PRODUCER_REVISION = "e5011c08f1088acf351133936dcbd1220f9f5761"
PLAN_SHA256 = "a3a0fbf6b92b8add583eeebdf8d108b8f6b81eb8081f2e98ad889fb4e76233da"
OUTCOME_SHA256 = "11a2cf1f18b34a877d675bc42ae1fc986c4daa20acecb202bc1531b2f1611202"
INVENTORY_SHA256 = "5d6bdbec7776370a07bd88b850a012ba6356feccbd8df0124aa489b1bfd72bad"


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _read_json(path):
    _require(
        path.is_file() and not path.is_symlink(), f"regular original required: {path}"
    )
    return json.loads(path.read_bytes())


def _history(path):
    return (
        [path["preload_response"]] if path["preload_response"] is not None else []
    ) + path["response_history"]


def _finite_norm(values):
    _require(type(values) is list and values, "nonempty residual vector required")
    _require(
        all(type(value) in (int, float) and math.isfinite(value) for value in values),
        "finite residual vector required",
    )
    return max(abs(value) for value in values)


def _preload_trial_scope(step, outcome):
    """Count the constant-preload search and its timed assembly separately."""
    _require(
        step.get("status") == "ready" and step.get("committed") is True,
        "committed preload step required",
    )
    _require(
        outcome.get("status") == "returned"
        and outcome.get("unknown_work") is False
        and outcome.get("committed") is True,
        "known committed preload outcome required",
    )
    solution = step["trial_solution"]
    history, convergence = (
        solution["line_search_history"],
        solution["convergence_history"],
    )
    _require(
        type(history) is list and type(convergence) is list,
        "preload trial history required",
    )
    by_iteration = {
        row["iteration"]: row
        for row in convergence
        if type(row) is dict and type(row.get("iteration")) is int
    }
    _require(
        len(by_iteration) == len(convergence),
        "unique preload convergence rows required",
    )
    rows = []
    previous = -1
    for line in history:
        _require(
            type(line) is dict
            and type(line.get("iteration")) is int
            and line["iteration"] > previous
            and line["iteration"] in by_iteration,
            "ordered preload line search required",
        )
        previous = line["iteration"]
        before = by_iteration[previous]
        attempts = line.get("attempts")
        _require(
            type(attempts) is list
            and 1 <= len(attempts) <= len(ALPHAS)
            and line.get("attempt_count") == len(attempts),
            "complete preload attempts required",
        )
        _require(
            line.get("starting_free_displacements_m")
            == before.get("free_displacements_m")
            and line.get("newton_increment_m") == before.get("newton_increment_m")
            and line.get("attempt_count") == before.get("line_search_attempt_count")
            and line.get("selected_alpha") == before.get("line_search_alpha"),
            "preload convergence and search state differ",
        )
        before_norm = _finite_norm(before.get("residual_kn"))
        _require(before_norm > 0, "positive pretrial preload residual required")
        accepted_index = None
        for index, attempt in enumerate(attempts):
            _require(
                type(attempt) is dict
                and attempt.get("alpha") == ALPHAS[index]
                and type(attempt.get("accepted")) is bool,
                "original preload alpha grid required",
            )
            accepted = _finite_norm(attempt.get("trial_residual_kn")) < before_norm
            _require(
                accepted == attempt["accepted"],
                "preload alpha acceptance differs from raw residual",
            )
            if accepted:
                _require(
                    accepted_index is None and index == len(attempts) - 1,
                    "accepted preload trial must terminate search",
                )
                accepted_index = index
        _require(
            line["selected_alpha"]
            == (0.0 if accepted_index is None else ALPHAS[accepted_index]),
            "selected preload alpha differs",
        )
        rows.append(
            {
                "trial_count": len(attempts),
                "observed_failed_trial_count": len(attempts)
                if accepted_index is None
                else accepted_index,
            }
        )
    calls = outcome["newton_assembly_work"]["calls"]
    joined = _account_trial_dispatches(rows, calls)
    trial_calls = [call for call in calls if call.get("phase") == "line_search"]
    return {
        "line_searches": len(rows),
        "trials": joined["trial_dispatches"],
        "failed_trials": sum(row["observed_failed_trial_count"] for row in rows),
        "line_search_assembly_wall_ns": sum(call["wall_ns"] for call in trial_calls),
        "failed_trial_dispatch_wall_ns": joined["failed_trial_dispatch_wall_ns"],
    }


def _target_trial_scope(folder, counted, target_count):
    """Use only target outcomes; the path phase total also includes preload."""
    wall_ns = 0
    trial_count = 0
    for index in range(target_count):
        outcome = _read_json(folder / "secant" / f"{index:03d}-1-outcome.json")
        calls = outcome["newton_assembly_work"]["calls"]
        trials = [call for call in calls if call.get("phase") == "line_search"]
        _require(
            all(
                call.get("status") == "returned"
                and type(call.get("wall_ns")) is int
                and call["wall_ns"] >= 0
                for call in trials
            ),
            "complete timed target trial dispatches required",
        )
        trial_count += len(trials)
        wall_ns += sum(call["wall_ns"] for call in trials)
    _require(trial_count == counted["trials"], "target trace and dispatch count differ")
    return {
        "line_searches": counted["line_searches"],
        "trials": trial_count,
        "failed_trials": counted["failed_trials"],
        "line_search_assembly_wall_ns": wall_ns,
        "failed_trial_dispatch_wall_ns": counted["failed_trial_dispatch_wall_ns"],
    }


def audit(packet: Path):
    root = packet.resolve(strict=True)
    plan_bytes, outcome_bytes = (
        (root / "plan.json").read_bytes(),
        (root / "outcome.json").read_bytes(),
    )
    _require(
        hashlib.sha256(plan_bytes).hexdigest() == PLAN_SHA256,
        "original plan bytes differ",
    )
    _require(
        hashlib.sha256(outcome_bytes).hexdigest() == OUTCOME_SHA256,
        "original outcome bytes differ",
    )
    plan, outcome = json.loads(plan_bytes), json.loads(outcome_bytes)
    _require(plan["source_revision"] == PRODUCER_REVISION, "producer source differs")
    _require(
        plan["plan_hash"]
        == _sha(_bytes({k: v for k, v in plan.items() if k != "plan_hash"})),
        "plan hash differs",
    )
    _require(
        outcome["outcome_hash"]
        == _sha(_bytes({k: v for k, v in outcome.items() if k != "outcome_hash"})),
        "outcome hash differs",
    )
    _require(outcome["plan_hash"] == plan["plan_hash"], "outcome plan differs")
    cases = prepare_cases()
    _require(
        len(plan["cases"]) == len(outcome["cases"]) == len(cases) == 3,
        "complete declared roster required",
    )
    trials = []
    for case, declared, result in zip(
        cases, plan["cases"], outcome["cases"], strict=True
    ):
        _require(
            declared["case_id"] == result["case_id"] == case.case_id
            and declared["split"] == "train"
            and declared["model"] == case.model.canonical_payload()
            and declared["request"] == case.request.to_dict(),
            "case model/request or train-only declaration differs",
        )
        _require(
            result["status"] == "complete_eligible",
            "failed case remains in denominator",
        )
        folder = root / case.case_id
        report = _read_json(folder / "comparison.json")
        _require(
            report["report_hash"]
            == _sha(_bytes({k: v for k, v in report.items() if k != "report_hash"})),
            "comparison hash differs",
        )
        _require(
            report["source_revision"] == PRODUCER_REVISION, "comparison source differs"
        )
        paths = {
            name: _read_json(folder / name / "path.json")
            for name in ("reference", "secant", "fresh-reference")
        }
        for name, path in paths.items():
            _require(
                path["path_hash"]
                == _sha(_bytes({k: v for k, v in path.items() if k != "path_hash"})),
                "path hash differs",
            )
            reported = (
                report["fresh_reference"]
                if name == "fresh-reference"
                else report["arms"][name]
            )
            _require(
                reported == {k: path[k] for k in reported},
                "comparison and original path differ",
            )
            _require(path["status"] == "complete", "incomplete original path")
        fresh = paths["fresh-reference"]
        for name in ("reference", "secant"):
            structure, _, _, within = _numeric_payload_difference(
                _history(fresh),
                _history(paths[name]),
                absolute_tolerance=report["absolute_tolerance"],
                relative_tolerance=report["relative_tolerance"],
            )
            _require(
                structure
                and within
                and report["comparisons"][name]["full_history_pass"],
                "fresh full-history comparison differs",
            )
        _require(
            _bytes(_history(paths["reference"])) == _bytes(_history(fresh))
            and _bytes(paths["reference"]["terminal_checkpoint"])
            == _bytes(fresh["terminal_checkpoint"]),
            "fresh reference repeat differs",
        )
        counted = summarize_completed_secant(folder, report, case)
        _require(
            counted == result["opportunity"], "source trace and outcome counts differ"
        )
        preload_invocations = paths["secant"].get("preload_invocations")
        _require(
            type(preload_invocations) is list
            and len(preload_invocations) == 1
            and preload_invocations[0].get("status") == "returned"
            and preload_invocations[0].get("unknown_work") is False,
            "one known constant preload required",
        )
        preload = _preload_trial_scope(
            _read_json(folder / "secant" / "preload-step.json"),
            _read_json(folder / "secant" / "preload-outcome.json"),
        )
        target = _target_trial_scope(folder, counted, len(case.request.targets_m))
        whole = {
            key: preload[key] + target[key]
            for key in (
                "line_searches",
                "trials",
                "failed_trials",
                "line_search_assembly_wall_ns",
                "failed_trial_dispatch_wall_ns",
            )
        }
        _require(
            whole["line_search_assembly_wall_ns"]
            == counted["secant_line_search_assembly_wall_ns"]
            == report["assembly_phase_work"]["secant"]["phase_wall_ns"]["line_search"],
            "preload plus target timing must equal whole-path assembly timing",
        )
        trials.append(
            {
                "case_id": case.case_id,
                "target_control": target,
                "constant_preload": preload,
                "whole_secant_path": whole,
                "secant_path_wall_ns": counted["secant_path_wall_ns"],
                "report_hash": counted["report_hash"],
            }
        )
    files = []
    for path in sorted(root.rglob("*")):
        _require(
            not path.is_symlink() and not path.name.startswith(".env"),
            "unsupported packet entry",
        )
        if path.is_dir():
            continue
        _require(path.is_file(), "regular packet file required")
        data = path.read_bytes()
        files.append(
            {
                "path": path.relative_to(root).as_posix(),
                "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        )
    _require(
        hashlib.sha256(_bytes(files)).hexdigest() == INVENTORY_SHA256,
        "original packet inventory differs",
    )
    return {
        "schema_version": "rc-alpha-training-opportunity-readonly-audit.v2",
        "producer_revision": PRODUCER_REVISION,
        "plan_sha256": PLAN_SHA256,
        "outcome_sha256": OUTCOME_SHA256,
        "inventory_sha256": INVENTORY_SHA256,
        "file_count": len(files),
        "total_bytes": sum(row["bytes"] for row in files),
        "all_cases_complete_and_original_histories_pass": True,
        "trial_rows": trials,
        "target_control": {
            key: sum(row["target_control"][key] for row in trials)
            for key in trials[0]["target_control"]
        },
        "constant_preload": {
            key: sum(row["constant_preload"][key] for row in trials)
            for key in trials[0]["constant_preload"]
        },
        "whole_secant_path": {
            key: sum(row["whole_secant_path"][key] for row in trials)
            for key in trials[0]["whole_secant_path"]
        },
        "solver_calls_in_readonly_audit": 0,
        "policy_fits_in_readonly_audit": 0,
        "independent_physical_validation": False,
        "learned_net_savings_proved": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.packet), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
