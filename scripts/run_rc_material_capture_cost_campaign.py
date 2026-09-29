"""Source-bound F/G development comparison of optional material layout reuse.

Each slot is one fresh process. This diagnostic never opens reserved cases or
changes the existing learned-policy selection.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from time import perf_counter_ns, process_time_ns

import run_rc_cost_gate_development_pilot as pilot
from structural_analysis.benchmark import rc_control_learning as learning
from structural_analysis.benchmark.rc_control_design import _bytes, _save, _sha
from structural_analysis.benchmark.rc_control_heldout_runtime import (
    _actual_proposal_count,
    _audit_original_histories,
)
from structural_analysis.benchmark.rc_control_runtime_selection import _runtime_score


SCHEMA = "rc-material-layout-cost-development.v1"
MODES = ("uncached", "cached")
_PROCESS_SLOT_USED = False


def _schedule(case_ids):
    if case_ids != [spec[0] for spec in pilot.CASE_SPECS]:
        raise ValueError("exact F/G development roster required")
    arms = ("reference", "secant", "proposal")
    rows = []
    for repetition in range(3):
        order = arms[repetition:] + arms[:repetition]
        for case_index, case_id in enumerate(case_ids):
            modes = MODES if (repetition + case_index) % 2 == 0 else MODES[::-1]
            for mode in modes:
                rows.append(
                    {
                        "slot_index": len(rows),
                        "case_id": case_id,
                        "repetition_index": repetition,
                        "mode": mode,
                        "arm_order": list(order),
                    }
                )
    return rows


def _read_plan(root):
    plan = pilot._json(root / "plan.json")
    if (
        plan.get("schema_version") != SCHEMA
        or plan.get("plan_hash")
        != _sha(
            _bytes({key: value for key, value in plan.items() if key != "plan_hash"})
        )
        or plan.get("schedule") != _schedule(plan.get("development_case_ids"))
        or plan.get("failure_denominator") != 12
        or plan.get("guard") != pilot.GATE
        or plan.get("guard_hash") != _sha(_bytes(pilot.GATE))
        or plan.get("minimum_relative_improvement") != 0.01
        or plan.get("absolute_tolerance") != 1e-10
        or plan.get("relative_tolerance") != 1e-8
        or plan.get("arithmetic_profile") != pilot.ARITHMETIC
        or plan.get("source_packet_inventory_sha256") != pilot.ORIGINAL_INVENTORY
        or plan.get("policy_hash") != pilot.ORIGINAL_POLICY
        or plan.get("training_or_reserved_case_execution") is not False
        or plan.get("independent_source_lineage") is not False
    ):
        raise ValueError("frozen material-capture plan changed")
    return plan


def _inputs(plan):
    packet = Path(plan["source_packet"])
    cases, development, prepared, gates, policy, selection = pilot._inputs(packet)
    if (
        pilot._case_rows(cases, gates) != plan["cases"]
        or [case.case_id for case in development] != plan["development_case_ids"]
        or any(gate["status"] != "not_rejected" for gate in gates.values())
        or policy.policy_hash != plan["policy_hash"]
        or selection["result_hash"] != plan["source_selection_result_hash"]
        or pilot._file_hash(packet / "study/pooled-policy.json")
        != plan["source_policy_file_sha256"]
    ):
        raise ValueError("source-bound development inputs changed")
    return cases, development, prepared, gates, policy, selection


def prepare(packet: Path, root: Path):
    source_revision = pilot._clean_head()
    checkout = Path(__file__).resolve().parents[1]
    if root.resolve().is_relative_to(checkout):
        raise ValueError("campaign packet must be outside the source checkout")
    cases, development, _, gates, policy, selection = pilot._inputs(packet)
    if any(gate["status"] != "not_rejected" for gate in gates.values()):
        raise ValueError("F/G models must pass the static model screen")
    case_ids = [case.case_id for case in development]
    plan = {
        "schema_version": SCHEMA,
        "source_revision": source_revision,
        "source_packet": str(packet.resolve()),
        "source_packet_inventory_sha256": pilot.ORIGINAL_INVENTORY,
        "source_selection_result_hash": selection["result_hash"],
        "source_policy_file_sha256": pilot._file_hash(
            packet / "study/pooled-policy.json"
        ),
        "policy_hash": policy.policy_hash,
        "policy_status": "unpromoted development metadata fit; selected strategy remains secant",
        "arithmetic_profile": pilot.ARITHMETIC,
        "cases": pilot._case_rows(cases, gates),
        "development_case_ids": case_ids,
        "source_lineage": "all cases descend from one authored public RC example template",
        "independent_source_lineage": False,
        "training_or_reserved_case_execution": False,
        "guard": pilot.GATE,
        "guard_hash": _sha(_bytes(pilot.GATE)),
        "schedule": _schedule(case_ids),
        "failure_denominator": 12,
        "warmup_repetitions": 0,
        "absolute_tolerance": 1e-10,
        "relative_tolerance": 1e-8,
        "minimum_relative_improvement": 0.01,
        "diagnostic_rule": "each mode: all six slots complete, original full histories and known work, positive seeded proposals, equal-case mean proposal/secant path ratio < 0.99; no promotion",
        "cost_scopes": [
            "input_loading_and_preflight",
            "benchmark_enclosing_four_paths",
            "per_arm_path",
            "committed_material_capture",
            "proposal_callback",
            "guard_callback",
            "solver_attempts",
            "recovery",
            "slot_enclosing",
            "separate_read_only_audit",
        ],
        "historical_training_and_selection_costs_known_here": False,
        "net_benefit_proved": False,
    }
    plan["plan_hash"] = _sha(_bytes(plan))
    root.mkdir(parents=True, exist_ok=False)
    _save(root, "plan.json", _bytes(plan))
    return plan


def run_slot(root: Path, index: int):
    global _PROCESS_SLOT_USED
    if _PROCESS_SLOT_USED:
        raise ValueError("one material-capture slot per fresh process required")
    _PROCESS_SLOT_USED = True
    plan = _read_plan(root)
    if pilot._clean_head() != plan["source_revision"]:
        raise ValueError("campaign requires its exact clean committed source")
    if type(index) is not int or not 0 <= index < len(plan["schedule"]):
        raise ValueError("declared slot index required")
    slot = plan["schedule"][index]
    wall, cpu = perf_counter_ns(), process_time_ns()
    loading_wall, loading_cpu = perf_counter_ns(), process_time_ns()
    _, development, prepared, _, policy, _ = _inputs(plan)
    loading = {
        "wall_ns": perf_counter_ns() - loading_wall,
        "cpu_ns": process_time_ns() - loading_cpu,
    }
    case = next(case for case in development if case.case_id == slot["case_id"])
    _, compiled, features, _, _ = prepared[case.case_id]
    folder = root / f"slot-{index:04d}"
    folder.mkdir(exist_ok=False)
    started = {
        "status": "started",
        "plan_hash": plan["plan_hash"],
        "slot": slot,
        "pid": os.getpid(),
        "unknown_work_until_outcome": True,
    }
    _save(folder, "started.json", _bytes(started))
    outcome = dict(started)
    outcome["cost_ledger"] = {
        "input_loading_and_preflight": loading,
        "process_startup": None,
        "historical_label_generation": None,
        "historical_policy_fit": None,
        "historical_development_selection": None,
    }
    try:

        def allow(context):
            return pilot.allow_cost_gate(context, len(case.request.targets_m))

        def propose(context):
            return policy.propose(
                context,
                features,
                compiled.problem.free_global_dofs,
                case.request.solver_config.contract_hash,
                arithmetic_profile=pilot.ARITHMETIC,
                load_factor_coordinate_scale_m=(
                    case.request.solver_config.load_factor_coordinate_scale_m
                ),
            )

        benchmark_wall, benchmark_cpu = perf_counter_ns(), process_time_ns()
        report = learning.benchmark_rc_control_seed_paths(
            case.model,
            case.request,
            source_revision=plan["source_revision"],
            output_directory=folder / "benchmark",
            proposal=propose,
            proposal_identity=policy.policy_hash,
            proposal_guard=allow,
            proposal_guard_identity=plan["guard_hash"],
            proposal_abstention_strategy="secant",
            arm_order=tuple(slot["arm_order"]),
            absolute_tolerance=plan["absolute_tolerance"],
            relative_tolerance=plan["relative_tolerance"],
            capture_material_state=True,
            material_capture_scope="proposal-only",
            material_snapshot_layout_reuse=slot["mode"] == "cached",
            **learning._arithmetic_kwargs(pilot.ARITHMETIC),
        )
        outcome["cost_ledger"]["benchmark"] = {
            "wall_ns": perf_counter_ns() - benchmark_wall,
            "cpu_ns": process_time_ns() - benchmark_cpu,
            "includes_reference_secant_proposal_fresh_reference": True,
        }
        decisions = [
            {"target_m": row["target_m"], "decision": row["proposal_decision"]}
            for row in report["arms"]["proposal"]["entries"]
        ]
        score = _runtime_score(report, decisions)
        score["actual_proposed_count"] = _actual_proposal_count(report)
        outcome.update(
            status="completed",
            report_hash=report["report_hash"],
            score=score,
            unknown_work_until_outcome=score["execution_work"]["unknown_work"],
        )
    except Exception as exc:
        outcome.update(
            status="raised",
            exception_kind=type(exc).__name__,
            unknown_work_until_outcome=True,
        )
    outcome["wall_ns"] = perf_counter_ns() - wall
    outcome["cpu_ns"] = process_time_ns() - cpu
    outcome["cost_ledger"]["enclosing_slot"] = {
        "wall_ns": outcome["wall_ns"],
        "cpu_ns": outcome["cpu_ns"],
        "nested_scopes_are_not_additive": True,
        "excludes_outcome_and_inventory_write": True,
    }
    _save(folder, "outcome.json", _bytes(outcome))
    _save(folder, "inventory.json", _bytes(pilot._inventory(folder)))
    return outcome


def _original_paths(folder, report, slot):
    paths = {}
    for name in (*slot["arm_order"], "fresh-reference"):
        path = pilot._json(folder / "benchmark" / name / "path.json")
        summary = (
            report["fresh_reference"]
            if name == "fresh-reference"
            else report["arms"][name]
        )
        if path["path_hash"] != _sha(
            _bytes({key: value for key, value in path.items() if key != "path_hash"})
        ) or summary != {
            key: value
            for key, value in path.items()
            if key
            not in ("response_history", "terminal_checkpoint", "preload_response")
        }:
            raise ValueError("original development path differs from report")
        paths[name] = path
    _audit_original_histories(report, paths)
    return paths


def _costs(report):
    entries = report["arms"]["proposal"]["entries"]
    if (
        len(entries) != 12
        or sum("committed_material_capture" in row for row in entries) != 9
    ):
        raise ValueError("fixed guarded proposal capture roster changed")

    def timed_sum(rows, key):
        values = [row[key] for row in rows]
        if any(type(value) is not int or value < 0 for value in values):
            raise ValueError("nonnegative observed timing required")
        return sum(values)

    return {
        "capture_wall_ns": timed_sum(
            [
                row["committed_material_capture"]
                for row in entries
                if "committed_material_capture" in row
            ],
            "wall_ns",
        ),
        "capture_cpu_ns": timed_sum(
            [
                row["committed_material_capture"]
                for row in entries
                if "committed_material_capture" in row
            ],
            "cpu_ns",
        ),
        "proposal_callback_wall_ns": timed_sum(entries, "proposal_wall_ns"),
        "guard_callback_wall_ns": timed_sum(
            [row["proposal_guard"] for row in entries], "wall_ns"
        ),
        "solver_attempt_wall_ns": timed_sum(
            [attempt for row in entries for attempt in row["invocations"]], "wall_ns"
        ),
        "recovery_wall_ns": timed_sum(
            [row for row in entries if "recovery_wall_ns" in row], "recovery_wall_ns"
        ),
        "proposal_path_wall_ns": report["arms"]["proposal"]["wall_ns"],
        "secant_path_wall_ns": report["arms"]["secant"]["wall_ns"],
    }


def _proposal_bytes_match(left: Path, right: Path) -> bool:
    left_folder = left / "benchmark/proposal"
    right_folder = right / "benchmark/proposal"
    names = sorted(path.name for path in left_folder.glob("*-context.json")) + sorted(
        path.name for path in left_folder.glob("*-step.json")
    )
    other_names = sorted(
        path.name for path in right_folder.glob("*-context.json")
    ) + sorted(path.name for path in right_folder.glob("*-step.json"))
    return (
        names == other_names
        and sum(name.endswith("-context.json") for name in names) == 12
        and all(
            (left_folder / name).read_bytes() == (right_folder / name).read_bytes()
            for name in names
        )
    )


def audit(root: Path, *, write=True):
    audit_wall, audit_cpu = perf_counter_ns(), process_time_ns()
    plan = _read_plan(root)
    if pilot._clean_head() != plan["source_revision"]:
        raise ValueError("audit requires the exact clean numerical source")
    _inputs(plan)
    rows = []
    observed = {}
    pids = set()
    for slot in plan["schedule"]:
        folder = root / f"slot-{slot['slot_index']:04d}"
        if not (folder / "outcome.json").exists():
            rows.append(
                {
                    "slot": slot,
                    "status": "missing",
                    "ratio": None,
                    "actual_proposals": 0,
                    "unknown_work": True,
                    "costs": None,
                }
            )
            continue
        outcome = pilot._json(folder / "outcome.json")
        started = pilot._json(folder / "started.json")
        if (
            outcome.get("plan_hash") != plan["plan_hash"]
            or outcome.get("slot") != slot
            or started.get("plan_hash") != plan["plan_hash"]
            or started.get("slot") != slot
            or outcome.get("pid") != started.get("pid")
            or type(outcome.get("pid")) is not int
            or outcome["pid"] in pids
            or pilot._json(folder / "inventory.json") != pilot._inventory(folder)
        ):
            raise ValueError("original capture-cost slot receipt changed")
        pids.add(outcome["pid"])
        ratio = None
        actual = 0
        costs = None
        if outcome["status"] == "completed":
            report = pilot._json(folder / "benchmark/comparison.json")
            if (
                report.get("report_hash") != outcome["report_hash"]
                or report["report_hash"]
                != _sha(
                    _bytes(
                        {
                            key: value
                            for key, value in report.items()
                            if key != "report_hash"
                        }
                    )
                )
                or report.get("source_revision") != plan["source_revision"]
                or report.get("proposal_identity") != plan["policy_hash"]
                or report.get("proposal_guard", {}).get("identity")
                != plan["guard_hash"]
                or report.get("arm_order") != slot["arm_order"]
                or (report.get("material_snapshot_layout_reuse") is True)
                != (slot["mode"] == "cached")
            ):
                raise ValueError("capture-cost report binding changed")
            pilot._audit_slot_contract(plan, slot, report)
            _original_paths(folder, report, slot)
            decisions = [
                {"target_m": row["target_m"], "decision": row["proposal_decision"]}
                for row in report["arms"]["proposal"]["entries"]
            ]
            score = _runtime_score(report, decisions)
            score["actual_proposed_count"] = _actual_proposal_count(report)
            if score != outcome["score"]:
                raise ValueError("capture-cost score differs from original paths")
            actual = score["actual_proposed_count"]
            if (
                score["full_comparison_pass"]
                and not score["execution_work"]["unknown_work"]
                and actual > 0
            ):
                ratio = score["proposal_over_secant_path_wall_ratio"]
            costs = _costs(report)
            observed[(slot["case_id"], slot["repetition_index"], slot["mode"])] = folder
        rows.append(
            {
                "slot": slot,
                "status": outcome["status"],
                "ratio": ratio,
                "actual_proposals": actual,
                "unknown_work": outcome["unknown_work_until_outcome"],
                "costs": costs,
                "enclosing_slot_wall_ns": outcome.get("wall_ns"),
                "enclosing_slot_cpu_ns": outcome.get("cpu_ns"),
            }
        )
    pair_rows = []
    for repetition in range(3):
        for case_id in plan["development_case_ids"]:
            paired = {
                mode: next(
                    row
                    for row in rows
                    if row["slot"]["case_id"] == case_id
                    and row["slot"]["repetition_index"] == repetition
                    and row["slot"]["mode"] == mode
                )
                for mode in MODES
            }
            available = all(paired[mode]["ratio"] is not None for mode in MODES)
            exact = None
            if available:
                folders = [observed[(case_id, repetition, mode)] for mode in MODES]
                exact = _proposal_bytes_match(*folders)
            pair_rows.append(
                {
                    "case_id": case_id,
                    "repetition_index": repetition,
                    "both_eligible": available,
                    "contexts_and_steps_exact": exact,
                    "capture_wall_ratio_cached_over_uncached": (
                        paired["cached"]["costs"]["capture_wall_ns"]
                        / paired["uncached"]["costs"]["capture_wall_ns"]
                        if available
                        and exact
                        and paired["uncached"]["costs"]["capture_wall_ns"] > 0
                        else None
                    ),
                    "proposal_path_wall_ratio_cached_over_uncached": (
                        paired["cached"]["costs"]["proposal_path_wall_ns"]
                        / paired["uncached"]["costs"]["proposal_path_wall_ns"]
                        if available
                        and exact
                        and paired["uncached"]["costs"]["proposal_path_wall_ns"] > 0
                        else None
                    ),
                }
            )
    mode_rows = []
    for mode in MODES:
        cases = []
        for case_id in plan["development_case_ids"]:
            selected = [
                row
                for row in rows
                if row["slot"]["mode"] == mode and row["slot"]["case_id"] == case_id
            ]
            ratios = [row["ratio"] for row in selected]
            cases.append(
                {
                    "case_id": case_id,
                    "ratios": ratios,
                    "mean_ratio": sum(ratios) / len(ratios)
                    if all(ratio is not None for ratio in ratios)
                    else None,
                    "actual_proposals": sum(
                        row["actual_proposals"] for row in selected
                    ),
                }
            )
        mean = (
            sum(row["mean_ratio"] for row in cases) / len(cases)
            if all(row["mean_ratio"] is not None for row in cases)
            else None
        )
        mode_rows.append(
            {
                "mode": mode,
                "cases": cases,
                "equal_case_mean_ratio": mean,
                "predeclared_path_screen_pass": (
                    mean is not None
                    and mean < 1 - plan["minimum_relative_improvement"]
                    and all(
                        row["actual_proposals"] > 0 and row["ratio"] is not None
                        for row in rows
                        if row["slot"]["mode"] == mode
                    )
                    and all(
                        row["contexts_and_steps_exact"] is True for row in pair_rows
                    )
                ),
            }
        )
    result = {
        "schema_version": "rc-material-layout-cost-development-audit.v1",
        "plan_hash": plan["plan_hash"],
        "source_revision": plan["source_revision"],
        "failure_denominator": plan["failure_denominator"],
        "slots": rows,
        "pairs": pair_rows,
        "modes": mode_rows,
        "all_pairs_exact": all(
            row["contexts_and_steps_exact"] is True for row in pair_rows
        ),
        "actual_total_evaluation_cost_known": False,
        "historical_training_and_selection_costs_known_here": False,
        "independent_source_lineage": False,
        "heldout_executed": False,
        "policy_promoted": False,
        "net_benefit_proved": False,
        "separate_audit_wall_ns": perf_counter_ns() - audit_wall,
        "separate_audit_cpu_ns": process_time_ns() - audit_cpu,
    }
    if write:
        _save(root, "audit.json", _bytes(result))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    declaring = sub.add_parser("prepare")
    declaring.add_argument("--packet", required=True, type=Path)
    declaring.add_argument("--output", required=True, type=Path)
    running = sub.add_parser("slot")
    running.add_argument("--output", required=True, type=Path)
    running.add_argument("--index", required=True, type=int)
    reviewing = sub.add_parser("audit")
    reviewing.add_argument("--output", required=True, type=Path)
    reviewing.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    if args.command == "prepare":
        result = prepare(args.packet, args.output)
    elif args.command == "slot":
        result = run_slot(args.output, args.index)
    else:
        result = audit(args.output, write=not args.verify_only)
    print(json.dumps(result, sort_keys=True))
    return 1 if args.command == "slot" and result["status"] != "completed" else 0


if __name__ == "__main__":
    sys.exit(main())
