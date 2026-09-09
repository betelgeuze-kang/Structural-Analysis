"""Verify three recorded constant-load repetitions against original pilot bytes.

This performs no solver execution or fitting. Recorded process/audit receipts do
not authenticate their producer or establish independent physical accuracy.
"""

from pathlib import Path
from collections import Counter
import argparse
import hashlib
import json
import statistics
import time
from typing import Any


def read(p):
    return json.loads(p.read_bytes())


def require(v, label):
    if not v:
        raise ValueError(label)


def encoded(v):
    return json.dumps(
        v, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode()


def checked(p, key):
    v = read(p)
    require(
        v[key]
        == "sha256:"
        + hashlib.sha256(encoded({k: x for k, x in v.items() if k != key})).hexdigest(),
        "hash " + str(p),
    )
    return v


def dist(values):
    require(len(values) == 3, "three paired samples required")
    return {
        "samples": values,
        "median": statistics.median(values),
        "minimum": min(values),
        "maximum": max(values),
        "sample_stdev": statistics.stdev(values),
    }


def complete_schedule(plan, outcome):
    require(
        type(plan["repeat_count_after_admission"]) is int
        and plan["repeat_count_after_admission"] == 3,
        "three declared repetitions required",
    )
    require(
        2 <= len(plan["cases"]) <= 32 and len(set(plan["cases"])) == len(plan["cases"]),
        "distinct declared case coverage required",
    )
    require(
        outcome["failure"] is None and len(outcome["rows"]) == 3,
        "three completed repetitions required",
    )
    require(
        [r["stage"] for r in outcome["rows"]] == ["repeat-1", "repeat-2", "repeat-3"],
        "exact repeat schedule required",
    )
    for row in outcome["rows"]:
        require(
            type(row["exit_code"]) is int and row["exit_code"] == 0, "driver failure"
        )
        require([a["case"] for a in row["audits"]] == plan["cases"], "audit coverage")
        require(
            all(
                type(a["exit_code"]) is int and a["exit_code"] == 0
                for a in row["audits"]
            ),
            "original audit failure",
        )


def original_path_costs(root, path, work):
    recovery = read(root / "preload-recovery-outcome.json")
    require(recovery["status"] == "returned", "preload recovery incomplete")
    invocations = [
        *path["preload_invocations"],
        *(i for e in path["entries"] for i in e["invocations"]),
    ]
    costs = dict(work=dict(work), accepted_targets=path["accepted_target_count"])
    for clock in ("wall", "cpu"):
        core = [i[clock + "_ns"] for i in invocations]
        proposals = [e["proposal_" + clock + "_ns"] for e in path["entries"]]
        recoveries = [
            recovery[clock + "_ns"],
            *(e["recovery_" + clock + "_ns"] for e in path["entries"]),
        ]
        total = path[clock + "_ns"]
        require(
            all(
                type(v) is int and v >= 0
                for v in [*core, *proposals, *recoveries, total]
            ),
            "original timing unavailable",
        )
        require(
            sum(core) + sum(proposals) + sum(recoveries) <= total,
            "nested time exceeds path",
        )
        costs.update(
            {
                "core_" + clock + "_ns": sum(core),
                "proposal_" + clock + "_ns": sum(proposals),
                "recovery_" + clock + "_ns": sum(recoveries),
                "path_" + clock + "_ns": total,
            }
        )
    return costs


def summarize(root):
    root = Path(root)
    start = time.perf_counter_ns()
    plan = read(root / "plan.json")
    outcome = read(root / "repeat-outcome.json")
    complete_schedule(plan, outcome)
    bindings = read(root / "execution-bindings.json")
    manifest = read(root / "source-manifest.json")
    require(
        plan["source_revision"]
        == bindings["numerical_source_revision"]
        == manifest["source_revision"],
        "frozen source revision differs",
    )
    for path, digest in read(root / "execution-bindings.json")["files"].items():
        require(
            hashlib.sha256((root / path).read_bytes()).hexdigest() == digest,
            "execution source/input binding",
        )
    for item in read(root / "source-manifest.json")["files"]:
        require(
            hashlib.sha256((root / "source" / item["path"]).read_bytes()).hexdigest()
            == item["sha256"],
            "frozen numerical source",
        )
    for name, digest in plan["inputs"].items():
        require(
            hashlib.sha256((root / "inputs" / name).read_bytes()).hexdigest() == digest,
            "original input bytes",
        )
    work: Counter[str] = Counter()
    polishing: Counter[str] = Counter()
    audit_work: Counter[str] = Counter()
    rows = []
    step_pairs = 0
    history_pairs = 0
    times: dict[str, dict[str, list[float]]] = {
        c: {a: [] for a in ["reference", "secant", "fresh-reference"]}
        for c in plan["cases"]
    }
    for outer in outcome["rows"]:
        require(outer["exit_code"] == 0, "driver failure")
        stage = outer["stage"]
        suite = read(root / stage / "suite-outcome.json")
        require(
            suite["source_inputs_unchanged"]
            and [r["case"] for r in suite["rows"]] == plan["cases"],
            "case coverage",
        )
        require([r["case"] for r in outer["audits"]] == plan["cases"], "audit coverage")
        for case, process, audit_process in zip(
            plan["cases"], suite["rows"], outer["audits"], strict=True
        ):
            require(
                process["exit_code"] == audit_process["exit_code"] == 0,
                "worker or original audit failure",
            )
            base = root / stage / case
            study = base / "study"
            pilot = root / "pilot" / case / "study"
            report = checked(study / "comparison.json", "report_hash")
            audited = read(base / "original-audit.json")
            require(
                audited["original_records_reproduced"] is True
                and audited["repeat_admissible"] is True,
                "original audit not admitted",
            )
            expected_order = plan["pilot_orders"][case]
            if stage in ("repeat-1", "repeat-3"):
                expected_order = expected_order[::-1]
            require(
                process["arm_order"] == expected_order, "predeclared arm order differs"
            )
            require(
                report["source_revision"] == plan["source_revision"]
                and report["request"]
                == read(root / "inputs" / (case + "-request.json")),
                "source/request identity",
            )
            require(
                report["arm_order"] == process["arm_order"]
                and report["reference_repeat_exact"] is True
                and report["all_execution_work_reported"] is True,
                "original comparison flags",
            )
            require(
                report["absolute_tolerance"] == plan["absolute_tolerance"] == 1e-10
                and report["relative_tolerance"] == plan["relative_tolerance"] == 1e-8,
                "unchanged comparisons",
            )
            require(
                all(
                    report["comparisons"][a]["full_history_pass"]
                    for a in ["reference", "secant"]
                ),
                "fixed physical comparison",
            )
            case_work: Counter[str] = Counter()
            expected_audit: Counter[str] = Counter()
            for arm in ["reference", "secant", "fresh-reference"]:
                path = checked(study / arm / "path.json", "path_hash")
                old = checked(pilot / arm / "path.json", "path_hash")
                require(
                    path["status"] == "complete"
                    and path["accepted_target_count"]
                    == len(path["entries"])
                    == plan["target_count"],
                    "complete path required",
                )
                for k in [
                    "preload_response",
                    "response_history",
                    "terminal_checkpoint",
                ]:
                    require(
                        encoded(path[k]) == encoded(old[k]),
                        "full original repeat mismatch",
                    )
                history_pairs += 1
                files = ["preload-step.json"] + [
                    f"{e['target_index']:03d}-{i['ordinal']}-step.json"
                    for e in path["entries"]
                    for i in e["invocations"]
                ]
                recorded_invocations = [
                    *path["preload_invocations"],
                    *(i for e in path["entries"] for i in e["invocations"]),
                ]
                require(
                    len(files) == len(recorded_invocations),
                    "original invocation coverage differs",
                )
                for filename, invocation in zip(
                    files, recorded_invocations, strict=True
                ):
                    raw = (study / arm / filename).read_bytes()
                    require(
                        raw == (pilot / arm / filename).read_bytes(),
                        "original step bytes differ",
                    )
                    step_pairs += 1
                    step = json.loads(raw)
                    metrics = step["trial_solution"]["metrics"]
                    expected_work = {
                        "core_calls": 1,
                        "newton_iterations": metrics["iteration_count"],
                        "linear_solves": metrics["linear_solve_count"],
                    }
                    require(
                        invocation["work"] == expected_work,
                        "original step work differs",
                    )
                    expected_audit["assembly_replays"] += 1
                    expected_audit["rational_record_rebuilds"] += 1
                    expected_audit["material_integrations"] += sum(
                        len(s["fiber_responses"])
                        for m in step["trial_assembly"]["member_assemblies"]
                        for s in m["element_response"]["section_responses"]
                    )
                    p = metrics.get("terminal_polishing")
                    require(p is not None, "declared polishing work unavailable")
                    for key in [
                        "attempt_count",
                        "accepted_correction_count",
                        "assembly_call_count",
                        "assembly_exception_count",
                        "linear_solve_count",
                        "linear_solve_exception_count",
                    ]:
                        require(
                            type(p[key]) is int and p[key] >= 0,
                            "original polishing counter",
                        )
                        polishing[key] += p[key]
                arm_work: Counter[str] = Counter()
                for inv in [
                    *path["preload_invocations"],
                    *[i for e in path["entries"] for i in e["invocations"]],
                ]:
                    require(
                        not inv["unknown_work"] and inv["status"] == "returned",
                        "unknown original work",
                    )
                    for key in ["core_calls", "newton_iterations", "linear_solves"]:
                        require(
                            type(inv["work"][key]) is int and inv["work"][key] >= 0,
                            "original work counter",
                        )
                    arm_work.update(inv["work"])
                costs = original_path_costs(study / arm, path, arm_work)
                require(costs == audited["paths"][arm], "audited original costs differ")
                case_work.update(arm_work)
                times[case][arm].append(path["wall_ns"] / 1e9)
                rows.append(
                    {
                        "stage": stage,
                        "case": case,
                        "arm": arm,
                        "costs": costs,
                    }
                )
            require(
                dict(case_work) == audited["original_work"],
                "audited total work differs",
            )
            require(
                audited["audit_work"]
                == {**expected_audit, "newton_solves": 0, "state_commits": 0},
                "separate audit work differs from original material point coverage",
            )
            work.update(case_work)
            audit_work.update(audited["audit_work"])
    summary: dict[str, Any] = {
        "schema_version": "rc-constant-seed-repetitions.v1",
        "numerical_source_revision": plan["source_revision"],
        "audit_source_revision": read(root / "execution-bindings.json")[
            "audit_source_revision"
        ],
        "repeats_per_case": 3,
        "cases": plan["cases"],
        "full_fixed_secant_comparisons_passed": 3 * len(plan["cases"]),
        "exact_original_step_pairs": step_pairs,
        "exact_original_history_checkpoint_pairs": history_pairs,
        "original_work": dict(work),
        "included_polishing_work": dict(polishing),
        "separate_audit_work": dict(audit_work),
        "rows": rows,
        "timing": {
            c: {
                **{a: dist(v) for a, v in arms.items()},
                "paired_reference_over_secant_ratio": dist(
                    [
                        r / s
                        for r, s in zip(arms["reference"], arms["secant"], strict=True)
                    ]
                ),
                "paired_saved_seconds": dist(
                    [
                        r - s
                        for r, s in zip(arms["reference"], arms["secant"], strict=True)
                    ]
                ),
            }
            for c, arms in times.items()
        },
        "whole_repeat_driver_seconds": outcome["whole_driver_wall_ns"] / 1e9,
        "summary_wall_ns": time.perf_counter_ns() - start,
        "independent_physical_validation": False,
        "external_training_admission": False,
        "learned_acceleration": False,
        "exclusive_hardware": False,
    }
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = summarize(args.root)
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2)
    print(json.dumps(result, indent=2))
