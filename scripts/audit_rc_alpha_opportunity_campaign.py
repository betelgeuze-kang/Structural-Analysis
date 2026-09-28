"""Read-only exact-packet audit of the prospective RC alpha opportunity run."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from run_rc_alpha_opportunity_campaign import prepare_cases, summarize_completed_secant
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
        trials.append(
            {
                "case_id": case.case_id,
                "line_searches": counted["line_searches"],
                "trials": counted["trials"],
                "failed_trials": counted["failed_trials"],
                "failed_trial_dispatch_wall_ns": counted[
                    "failed_trial_dispatch_wall_ns"
                ],
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
        "schema_version": "rc-alpha-training-opportunity-readonly-audit.v1",
        "producer_revision": PRODUCER_REVISION,
        "plan_sha256": PLAN_SHA256,
        "outcome_sha256": OUTCOME_SHA256,
        "inventory_sha256": INVENTORY_SHA256,
        "file_count": len(files),
        "total_bytes": sum(row["bytes"] for row in files),
        "all_cases_complete_and_original_histories_pass": True,
        "trial_rows": trials,
        "line_searches": sum(row["line_searches"] for row in trials),
        "failed_trials": sum(row["failed_trials"] for row in trials),
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
