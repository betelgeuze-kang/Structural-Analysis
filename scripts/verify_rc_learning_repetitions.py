"""Compare terminal retained-learning repetitions with their sealed pilot.

This consumes the explicit pilot/repetition driver layout. It never launches a
solver, executes a saved script, refits a policy, or establishes physical truth.
Per-run original arithmetic/material audits remain separate required receipts.
"""

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import statistics
from time import perf_counter_ns


def read(path):
    return json.loads(path.read_bytes())


def encoded(value):
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def terminal(receipt):
    require(
        type(receipt["exit_code"]) is int and receipt["exit_code"] == 0,
        "recorded process did not exit zero",
    )
    pid = receipt["pid"]
    require(type(pid) is int and pid > 0, "positive recorded PID required")
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return
    raise ValueError("recorded PID is still present; terminal evidence required")


def checked(path, key):
    value = read(path)
    payload = dict(value)
    identity = payload.pop(key)
    require(identity == "sha256:" + digest(encoded(payload)), f"hash differs: {path}")
    return value


def distribution(values):
    return dict(
        samples=values,
        median=statistics.median(values),
        sample_stdev=statistics.stdev(values),
        minimum=min(values),
        maximum=max(values),
    )


def verify(root):
    """Refuse incomplete runs before reading the large original inventory."""
    started = perf_counter_ns()
    require((root / "suite-outcome.json").is_file(), "repetition driver is incomplete")
    suite = read(root / "suite-outcome.json")
    plan = read(root / "plan.json")
    slots = plan["slots"]
    require(suite["all_processes_exited"] is True, "driver is not terminal")
    require(
        len(slots) == len(suite["outcomes"]) == 3, "three declared repeats required"
    )
    require(len({s["id"] for s in slots}) == 3, "distinct repeat IDs required")
    require(
        len({r["pid"] for r in suite["outcomes"]}) == 3, "distinct worker PIDs required"
    )
    for outcome, slot in zip(suite["outcomes"], slots, strict=True):
        require(outcome["slot_id"] == slot["id"], "repeat order differs")
        terminal(outcome)
        terminal(outcome["audit"])
    driver_pid = read(root / "driver-started.json")["pid"]
    terminal(dict(pid=driver_pid, exit_code=0))
    pilot = Path(plan["pilot_root"])
    seal = read(Path(str(pilot) + "-sealed.json"))
    require(seal == plan["pilot_seal"], "pilot seal differs from declared admission")
    inventory_raw = Path(str(pilot) + "-inventory.json").read_bytes()
    require(
        digest(inventory_raw) == seal["inventory_sha256"], "pilot inventory differs"
    )
    inventory = json.loads(inventory_raw)
    require(len(inventory["files"]) == seal["file_count"], "pilot file count differs")
    for record in inventory["files"]:
        path = pilot / record["path"]
        require(
            path.resolve().is_relative_to(pilot.resolve()),
            "inventory path escapes root",
        )
        raw = path.read_bytes()
        require(
            len(raw) == record["size_bytes"] and digest(raw) == record["sha256"],
            f"sealed pilot file differs: {path}",
        )
    pilot_plan = read(pilot / "plan.json")
    pilot_audit = read(pilot / "learning-observation-audit.json")
    require(pilot_audit["repeat_admission"] is True, "pilot did not admit repeats")
    require(slots == pilot_plan["admitted_repeats"], "predeclared schedules differ")
    require(plan["source_revision"] == pilot_plan["source_revision"], "source differs")
    pilot_study = pilot / "slots/pilot/study"
    sources = read(pilot / "source-files.json")
    rows = []
    total = Counter()
    steps = histories = 0
    for slot, outcome in zip(slots, suite["outcomes"], strict=True):
        child = root / slot["id"]
        declaration = read(child / "plan.json")
        for key in [
            "source_revision",
            "inputs",
            "cases",
            "ridge",
            "ood_margin",
            "arithmetic_profile",
        ]:
            require(
                declaration[key] == pilot_plan[key],
                f"repeat declaration differs: {key}",
            )
        require(declaration["slots"] == [slot], "child schedule differs")
        require(
            read(child / "suite-outcome.json")["outcomes"]
            == [{k: v for k, v in outcome.items() if k != "audit"}],
            "child process receipt differs",
        )
        require(
            read(child / "audit-process.json") == outcome["audit"],
            "audit receipt differs",
        )
        for prefix, record in [
            *[("source", row) for row in sources["files"]],
            *[("", row) for row in pilot_plan["inputs"]],
        ]:
            raw = (child / prefix / record["path"]).read_bytes()
            require(
                len(raw) == record["byte_length"] and digest(raw) == record["sha256"],
                "frozen source or input differs",
            )
        audit = read(child / "learning-observation-audit.json")
        for key in [
            "source_revision",
            "original_core_records_checked",
            "original_training_pairs_checked",
            "frozen_policy_predictions_checked",
            "native_reopens_exact",
            "total_work",
            "repeat_admission",
        ]:
            require(audit[key] == pilot_audit[key], f"audited repeat differs: {key}")
        study = child / "slots" / slot["id"] / "study"
        worker = read(study.parent / "study-worker-source.json")
        require(worker["pid"] == outcome["pid"], "worker identity differs")
        require(
            Path(worker["module"]).resolve()
            == (
                child
                / "source/src/structural_analysis/benchmark/rc_control_learning.py"
            ).resolve(),
            "worker source path differs",
        )
        report = checked(study / "learning-study.json", "report_hash")
        require(
            report["report_hash"] == audit["slots"][0]["report_hash"],
            "audited report differs",
        )
        for name in ["policy.json", "training-samples.json"]:
            require(
                (study / name).read_bytes() == (pilot_study / name).read_bytes(),
                f"fresh train-only artifact differs: {name}",
            )
        for phase in ["generation", "evaluation"]:
            require(not report[phase + "_work"]["unknown_work"], "unknown work remains")
            phase_work = Counter()
            for case in report[phase]:
                base = study / case["case_id"] / phase
                original = pilot_study / case["case_id"] / phase
                comparison = checked(base / "comparison.json", "report_hash")
                require(
                    comparison == case["report"], "comparison/report binding differs"
                )
                prior = read(original / "comparison.json")
                require(
                    comparison["comparisons"] == prior["comparisons"],
                    "physical comparison outcomes differ from pilot",
                )
                require(comparison["reference_repeat_exact"], "fresh reference differs")
                for arm in [*comparison["arm_order"], "fresh-reference"]:
                    path = checked(base / arm / "path.json", "path_hash")
                    old = checked(original / arm / "path.json", "path_hash")
                    arm_report = (
                        comparison["fresh_reference"]
                        if arm == "fresh-reference"
                        else comparison["arms"][arm]
                    )
                    require(
                        all(
                            encoded(value) == encoded(path[key])
                            for key, value in arm_report.items()
                        ),
                        "path is not bound to the comparison report",
                    )
                    audited_path = audit["slots"][0]["cases"][case["case_id"]]["paths"][
                        arm
                    ]
                    require(
                        path["wall_ns"] / 1e9 == audited_path["wall_seconds"]
                        and path["cpu_ns"] / 1e9 == audited_path["cpu_seconds"],
                        "path timing differs from audited timing",
                    )
                    require(path["status"] == "complete", "incomplete path")
                    for key in [
                        "response_history",
                        "terminal_checkpoint",
                        "accepted_target_count",
                    ]:
                        require(
                            encoded(path[key]) == encoded(old[key]),
                            f"original {key} differs",
                        )
                    histories += 1
                    path_work = Counter()
                    for entry, old_entry in zip(
                        path["entries"], old["entries"], strict=True
                    ):
                        for key in [
                            "target_index",
                            "target_m",
                            "parent_hash",
                            "proposal",
                        ]:
                            require(
                                encoded(entry[key]) == encoded(old_entry[key]),
                                "accepted-prefix or proposal record differs",
                            )
                        for invocation, old_invocation in zip(
                            entry["invocations"], old_entry["invocations"], strict=True
                        ):
                            for key in [
                                "ordinal",
                                "status",
                                "committed",
                                "rollback_exact",
                                "seed_used",
                                "unknown_work",
                                "work",
                            ]:
                                require(
                                    encoded(invocation[key])
                                    == encoded(old_invocation[key]),
                                    "original invocation outcome or work differs",
                                )
                            require(
                                invocation["committed"]
                                and not invocation["unknown_work"],
                                "uncommitted or unknown original work",
                            )
                            path_work.update(invocation["work"])
                            name = f"{entry['target_index']:03d}-{invocation['ordinal']}-step.json"
                            require(
                                (base / arm / name).read_bytes()
                                == (original / arm / name).read_bytes(),
                                "original step bytes differ",
                            )
                            steps += 1
                    require(
                        dict(path_work) == audited_path["work"],
                        "audited path work differs",
                    )
                    phase_work.update(path_work)
            require(
                dict(phase_work) == report[phase + "_work"]["known_work"],
                "reported phase work differs",
            )
            total.update(phase_work)
        rows.append(audit["slots"][0])
    require(
        steps == 10164 and histories == 42, "complete four-case path coverage required"
    )
    timings = {}
    for case in ["validation", "holdout"]:
        paths = [row["cases"][case]["paths"] for row in rows]
        timings[case] = dict(
            path_wall_seconds={
                arm: distribution([p[arm]["wall_seconds"] for p in paths])
                for arm in ["reference", "secant", "proposal", "fresh-reference"]
            },
            paired_reference_over_policy=distribution(
                [
                    p["reference"]["wall_seconds"] / p["proposal"]["wall_seconds"]
                    for p in paths
                ]
            ),
            paired_secant_minus_policy_seconds=distribution(
                [
                    p["secant"]["wall_seconds"] - p["proposal"]["wall_seconds"]
                    for p in paths
                ]
            ),
            proposal_decisions=[
                row["cases"][case]["proposal_decisions"] for row in rows
            ],
        )
    return dict(
        schema_version="rc-learning-retained-repetitions-original-summary.v1",
        verifier_source_sha256=digest(Path(__file__).read_bytes()),
        source_revision=plan["source_revision"],
        pilot_inventory_sha256=seal["inventory_sha256"],
        exact_original_step_pairs=steps,
        exact_history_checkpoint_pairs=histories,
        all_fresh_policy_and_training_sample_bytes_exact=True,
        total_work=dict(total),
        whole_driver_wall_seconds=suite["whole_driver_wall_seconds"],
        numerical_worker_parent_wall_seconds=sum(
            r["parent_wall_ns"] for r in suite["outcomes"]
        )
        / 1e9,
        audit_parent_wall_seconds=sum(
            r["audit"]["parent_wall_seconds"] for r in suite["outcomes"]
        ),
        slots=rows,
        evaluation_summary=timings,
        verification_wall_seconds=(perf_counter_ns() - started) / 1e9,
        verification_newton_fit_material_compile_or_commit_calls=0,
        cost_scopes_are_nested_not_additive=True,
        independent_physical_validation=False,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    require(not args.output.exists(), "output already exists")
    summary = verify(args.root)
    with args.output.open("x") as stream:
        json.dump(summary, stream, indent=2, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    main()
