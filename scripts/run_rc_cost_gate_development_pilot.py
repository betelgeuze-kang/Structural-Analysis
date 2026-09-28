"""Frozen, synthetic development pilot for a cheap RC warm-start guard.

This deliberately cannot run the two reserved RC selection cases. It uses only
the original training-case fold files and creates two new synthetic development
cases from the same authored model template. Passing this pilot is neither an
eligible held-out result nor evidence of independent physical generalization.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import os
import subprocess
import sys
from time import perf_counter_ns, process_time_ns

from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    decode_bounded_rc_fiber_direct_control_request,
)
from structural_analysis.benchmark import rc_control_learning as learning
from structural_analysis.benchmark.rc_control_design import _bytes, _save, _sha
from structural_analysis.benchmark.rc_control_heldout_runtime import (
    _actual_proposal_count,
    _audit_original_histories,
)
from structural_analysis.benchmark.rc_control_runtime_selection import (
    _runtime_score,
    _static_material_model_gate,
)
from structural_analysis.io.neutral.loader import load_neutral_json_bytes


SCHEMA = "rc-cost-gate-synthetic-development-pilot.v1"
ARITHMETIC = "retained-twofold-refinement.v1"
ORIGINAL_SOURCE = "7a41a1566a605ed1529563619cbc70dbbd0eef17"
ORIGINAL_INVENTORY = "e47a96cf34c52b3a088f15eba08a890e745da6096a7a43b5127f78df8ca2b7c0"
ORIGINAL_RESULT = "sha256:ce95bc6c4cd81d815156b733764811366b48153348f8ae108d5ba9bb67df7eac"
ORIGINAL_POLICY = "sha256:748ca448dc4aacea36bea9d6672057aa3d76c15ff1d8ac6db6f9ff53e40e8e48"
CASE_SPECS = (
    # Coordinates are m; displacement targets are mm. These names are new
    # development examples, not independent measured projects.
    ("development-pilot-f", 2.85, 2.30,
     (-0.75, -2.25, -4.50, -9.45, -4.20, 1.80, 6.15, 8.025, 3.15, -2.85, -6.45, 0.0)),
    ("development-pilot-g", 3.10, 2.55,
     (-0.75, -2.25, -4.50, -10.50, -4.05, 1.65, 6.45, 8.475, 3.15, -2.70, -7.35, 0.0)),
)
GATE = {
    "rule": "allow learned proposal only for target indices 2 through 10 of 12",
    "excluded_indices": [0, 1, 11],
    "input": "accepted target count and declared target count before material capture",
    "fallback": "secant",
    "reason": "retrospective development work made first eligible and terminal targets cost-negative; this is a new pilot hypothesis",
}


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(path: Path) -> dict:
    return json.loads(path.read_bytes())


def _clean_head() -> str:
    root = Path(__file__).resolve().parents[1]
    head = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    dirty = subprocess.check_output(["git", "-C", str(root), "status", "--porcelain"], text=True)
    if dirty:
        raise ValueError("pilot requires an exact clean committed source")
    return head


def _verified_packet_bytes(packet: Path, entries: dict, relative: str) -> bytes:
    row = entries.get(relative)
    if row is None:
        raise ValueError(f"original packet inventory omits {relative}")
    payload = (packet / relative).read_bytes()
    if (row.get("byte_length") != len(payload)
            or row.get("sha256") != hashlib.sha256(payload).hexdigest()):
        raise ValueError(f"original packet file differs from inventory: {relative}")
    return payload


def _inputs(packet: Path):
    inventory_bytes = (packet / "inventory.json").read_bytes()
    if hashlib.sha256(inventory_bytes).hexdigest() != ORIGINAL_INVENTORY:
        raise ValueError("original development packet inventory changed")
    inventory = json.loads(inventory_bytes)
    entries = {row["path"]: row for row in inventory["files"]}
    if len(entries) != len(inventory["files"]):
        raise ValueError("duplicate original packet inventory paths")
    selection = json.loads(_verified_packet_bytes(
        packet, entries, "study/selection/result.json"
    ))
    if (
        selection.get("source_revision") != ORIGINAL_SOURCE
        or selection.get("result_hash") != ORIGINAL_RESULT
        or selection.get("selected_strategy") != "secant"
        or selection.get("selected_policy") is not None
        or selection.get("validation_or_holdout_execution") is not False
        or selection.get("result_hash") != _sha(_bytes({
            key: value for key, value in selection.items() if key != "result_hash"
        }))
    ):
        raise ValueError("original rejected development selection changed")
    policy_bytes = _verified_packet_bytes(packet, entries, "study/pooled-policy.json")
    policy = learning.RCControlSeedPolicy(policy_bytes.decode())
    if policy.policy_hash != ORIGINAL_POLICY:
        raise ValueError("unpromoted source policy changed")
    folds = [
        row for row in selection["folds"]
        if row["ridge"] == 1e4 and row["repetition_index"] == 0
    ]
    expected = {
        f"train-{group}-amp{amplitude}"
        for group in "abcde" for amplitude in ("050", "100", "150")
    }
    if len(folds) != 15 or {row["withheld_training_case"] for row in folds} != expected:
        raise ValueError("exact non-reserved original training roster required")
    train = []
    for fold in folds:
        case_id = fold["withheld_training_case"]
        prefix = f"study/selection/fold-{fold['index']:04d}"
        model = load_neutral_json_bytes(
            _verified_packet_bytes(packet, entries, f"{prefix}/model.json"),
            source_path=f"memory://{case_id}.json"
        )
        request = decode_bounded_rc_fiber_direct_control_request(
            json.loads(_verified_packet_bytes(
                packet, entries, f"{prefix}/request.json"
            ))["request"]
        )
        group = case_id.split("-amp")[0]
        train.append(learning.RCControlLearningCase(
            case_id, f"synthetic-{group}", f"synthetic-{group}",
            f"synthetic-{group}", "train", model, request,
        ))
    base = next(row for row in folds if row["withheld_training_case"] == "train-d-amp150")
    base_prefix = f"study/selection/fold-{base['index']:04d}"
    model_template = json.loads(_verified_packet_bytes(
        packet, entries, f"{base_prefix}/model.json"
    ))
    request_template = decode_bounded_rc_fiber_direct_control_request(
        json.loads(_verified_packet_bytes(
            packet, entries, f"{base_prefix}/request.json"
        ))["request"]
    )
    pilot = []
    for case_id, width, height, millimetres in CASE_SPECS:
        payload = json.loads(json.dumps(model_template))
        for node in payload["nodes"]:
            if node["id"] == "N2":
                node["coordinates"] = [width, 0.0, 0.0]
            elif node["id"] == "N3":
                node["coordinates"] = [width, height, 0.0]
        model = load_neutral_json_bytes(
            _bytes(payload), source_path=f"memory://{case_id}.json"
        )
        request = replace(
            request_template, targets_m=tuple(value / 1000 for value in millimetres)
        )
        pilot.append(learning.RCControlLearningCase(
            case_id, f"synthetic-{case_id}", f"synthetic-{case_id}",
            f"synthetic-{case_id}", "validation", model, request,
        ))
    cases = train + pilot
    prepared = learning._preflight(cases, ARITHMETIC)
    gates = {case.case_id: _static_material_model_gate(policy, prepared[case.case_id][2])
             for case in pilot}
    return cases, pilot, prepared, gates, policy, selection


def _case_rows(cases, gates):
    return [
        {
            "case_id": case.case_id,
            "split": case.split,
            "project_id": case.project_id,
            "geometry_family_id": case.geometry_family_id,
            "load_history_id": case.load_history_id,
            "model_hash": case.model.canonical_model_checksum,
            "request_hash": _sha(_bytes(case.request.to_dict())),
            "static_model_gate": gates[case.case_id]["status"] if case.case_id in gates else None,
        }
        for case in sorted(cases, key=lambda c: c.case_id)
    ]


def allow_cost_gate(context, target_count):
    """Decide before material capture using only accepted-prefix length."""
    if type(target_count) is not int or target_count != 12:
        raise ValueError("exact predeclared twelve-target pilot required")
    target_index = len(context.accepted_targets_m) - 1
    if not 0 <= target_index < target_count:
        raise ValueError("pilot accepted prefix exceeds declared target roster")
    return 2 <= target_index < target_count - 1


def _inventory(folder: Path):
    files = []
    for path in sorted(folder.rglob("*")):
        if path.is_symlink():
            raise ValueError("pilot receipt symlink is not an original file")
        if not path.is_file() or path.name == "inventory.json":
            continue
        files.append({"path": path.relative_to(folder).as_posix(),
                      "bytes": path.stat().st_size, "sha256": "sha256:" + _file_hash(path)})
    result = {"files": files, "file_count": len(files),
              "total_bytes": sum(row["bytes"] for row in files)}
    result["inventory_hash"] = _sha(_bytes(result))
    return result


def prepare(packet: Path, root: Path):
    source_revision = _clean_head()
    cases, pilot, _, gates, policy, selection = _inputs(packet)
    if any(gate["status"] != "not_rejected" for gate in gates.values()):
        raise ValueError("declared pilot models must pass the necessary static range screen")
    orders = ("reference", "secant", "proposal")
    schedule = [
        {"slot_index": repeat * len(pilot) + case_index,
         "case_id": case.case_id, "repetition_index": repeat,
         "arm_order": list(orders[repeat:] + orders[:repeat])}
        for repeat in range(3) for case_index, case in enumerate(pilot)
    ]
    plan = {
        "schema_version": SCHEMA,
        "source_revision": source_revision,
        "source_packet": str(packet.resolve()),
        "source_packet_inventory_sha256": ORIGINAL_INVENTORY,
        "source_selection_result_hash": selection["result_hash"],
        "source_policy_file_sha256": _file_hash(packet / "study/pooled-policy.json"),
        "policy_hash": policy.policy_hash,
        "policy_status": "development metadata fit, previously rejected for whole-path selection",
        "arithmetic_profile": ARITHMETIC,
        "cases": _case_rows(cases, gates),
        "development_case_ids": [case.case_id for case in pilot],
        "source_lineage": "all authored from one public RC L-frame example template",
        "independent_source_lineage": False,
        "training_or_reserved_case_execution": False,
        "guard": GATE,
        "guard_hash": _sha(_bytes(GATE)),
        "schedule": schedule,
        "failure_denominator": len(schedule),
        "warmup_repetitions": 0,
        "absolute_tolerance": 1e-10,
        "relative_tolerance": 1e-8,
        "minimum_relative_improvement": 0.01,
        "decision_rule": "diagnostic pilot only: every slot fully verified with known work and at least one seeded learned proposal, then equal-case mean scored path ratio < 0.99; no promotion",
        "all_lifecycle_costs_known": False,
        "net_benefit_proved": False,
    }
    plan["plan_hash"] = _sha(_bytes(plan))
    root.mkdir(parents=True, exist_ok=False)
    _save(root, "plan.json", _bytes(plan))
    return plan


def _read_plan(root: Path):
    plan = _json(root / "plan.json")
    if (
        plan.get("schema_version") != SCHEMA
        or plan.get("plan_hash") != _sha(_bytes({
            key: value for key, value in plan.items() if key != "plan_hash"
        }))
    ):
        raise ValueError("frozen pilot plan changed")
    return plan


def run_slot(root: Path, index: int):
    plan = _read_plan(root)
    if _clean_head() != plan["source_revision"]:
        raise ValueError("pilot source revision changed")
    if type(index) is not int or not 0 <= index < len(plan["schedule"]):
        raise ValueError("declared slot required")
    wall, cpu = perf_counter_ns(), process_time_ns()
    slot = plan["schedule"][index]
    packet = Path(plan["source_packet"])
    loading_wall, loading_cpu = perf_counter_ns(), process_time_ns()
    cases, pilot, prepared, gates, policy, selection = _inputs(packet)
    loading = {"wall_ns": perf_counter_ns() - loading_wall,
               "cpu_ns": process_time_ns() - loading_cpu}
    if (
        _case_rows(cases, gates) != plan["cases"]
        or policy.policy_hash != plan["policy_hash"]
        or selection["result_hash"] != plan["source_selection_result_hash"]
        or _file_hash(packet / "study/pooled-policy.json") != plan["source_policy_file_sha256"]
    ):
        raise ValueError("pilot inputs changed before numerical execution")
    case = next(case for case in pilot if case.case_id == slot["case_id"])
    gate = gates[case.case_id]
    if gate["status"] != "not_rejected":
        raise ValueError("pilot model static gate changed")
    _, compiled, features, _, _ = prepared[case.case_id]
    folder = root / f"slot-{index:04d}"
    folder.mkdir(exist_ok=False)
    started = {"status": "started", "plan_hash": plan["plan_hash"],
               "slot": slot, "pid": os.getpid(), "unknown_work_until_outcome": True}
    _save(folder, "started.json", _bytes(started))
    outcome = dict(started)
    outcome["cost_ledger"] = {"input_loading_and_preflight": loading,
                              "process_startup": None,
                              "historical_label_generation": None,
                              "historical_policy_fit": None,
                              "historical_development_selection": None}
    try:
        def allow(context):
            return allow_cost_gate(context, len(case.request.targets_m))

        def propose(context):
            return policy.propose(
                context, features, compiled.problem.free_global_dofs,
                case.request.solver_config.contract_hash,
                arithmetic_profile=ARITHMETIC,
                load_factor_coordinate_scale_m=case.request.solver_config.load_factor_coordinate_scale_m,
            )

        benchmark_wall, benchmark_cpu = perf_counter_ns(), process_time_ns()
        report = learning.benchmark_rc_control_seed_paths(
            case.model, case.request,
            source_revision=plan["source_revision"],
            output_directory=folder / "benchmark",
            proposal=propose, proposal_identity=policy.policy_hash,
            proposal_guard=allow, proposal_guard_identity=plan["guard_hash"],
            proposal_abstention_strategy="secant",
            arm_order=tuple(slot["arm_order"]),
            absolute_tolerance=plan["absolute_tolerance"],
            relative_tolerance=plan["relative_tolerance"],
            capture_material_state=True, material_capture_scope="proposal-only",
            **learning._arithmetic_kwargs(ARITHMETIC),
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
        outcome.update(status="completed", report_hash=report["report_hash"],
                       score=score,
                       unknown_work_until_outcome=score["execution_work"]["unknown_work"])
    except Exception as exc:
        outcome.update(status="raised", exception_kind=type(exc).__name__,
                       unknown_work_until_outcome=True)
    outcome["wall_ns"] = perf_counter_ns() - wall
    outcome["cpu_ns"] = process_time_ns() - cpu
    outcome["cost_ledger"]["enclosing_slot"] = {
        "wall_ns": outcome["wall_ns"], "cpu_ns": outcome["cpu_ns"],
        "nested_scopes_are_not_additive": True,
        "excludes_outcome_and_inventory_write": True,
    }
    _save(folder, "outcome.json", _bytes(outcome))
    _save(folder, "inventory.json", _bytes(_inventory(folder)))
    return outcome


def _audit_slot_contract(plan: dict, slot: dict, report: dict) -> None:
    if plan.get("guard") != GATE or plan.get("guard_hash") != _sha(_bytes(GATE)):
        raise ValueError("original pilot guard differs from frozen rule")
    cases = [row for row in plan["cases"] if row["case_id"] == slot["case_id"]]
    if (len(cases) != 1 or slot["case_id"] not in plan["development_case_ids"]
            or cases[0]["split"] != "validation"
            or cases[0]["static_model_gate"] != "not_rejected"):
        raise ValueError("pilot slot does not bind one declared development case")
    request = report.get("request")
    if (report.get("model_checksum") != cases[0]["model_hash"]
            or not isinstance(request, dict)
            or _sha(_bytes(request)) != cases[0]["request_hash"]):
        raise ValueError("pilot report model or request differs from scheduled case")
    if (type(report.get("absolute_tolerance")) is not float
            or type(report.get("relative_tolerance")) is not float
            or report["absolute_tolerance"] != plan["absolute_tolerance"]
            or report["relative_tolerance"] != plan["relative_tolerance"]
            or plan["arithmetic_profile"] != ARITHMETIC
            or any(report.get(key) != value for key, value in
                   learning._arithmetic_kwargs(ARITHMETIC).items())
            or report.get("capture_material_state") is not True
            or report.get("material_capture_scope") != "proposal-only"
            or report.get("proposal_requested") is not True
            or report.get("proposal_abstention_strategy") != "secant"):
        raise ValueError("pilot report comparison or execution config changed")
    targets = request.get("targets_m")
    entries = report.get("arms", {}).get("proposal", {}).get("entries")
    if (not isinstance(targets, list) or len(targets) != 12
            or not isinstance(entries, list) or len(entries) != len(targets)):
        raise ValueError("pilot report target or guard roster changed")
    for index, entry in enumerate(entries):
        expected_allow = 2 <= index <= 10
        guard = entry.get("proposal_guard", {})
        if (type(entry.get("target_index")) is not int
                or entry["target_index"] != index
                or entry.get("target_m") != targets[index]
                or guard.get("status") != "returned"
                or guard.get("allow_proposal") is not expected_allow):
            raise ValueError("pilot report per-target guard differs from frozen rule")
        if not expected_allow and entry.get("proposal_decision") != (
                "abstained_to_reference" if index == 0 else "abstained_to_secant"):
            raise ValueError("pilot report declined-target strategy changed")


def audit(root: Path, *, write: bool = True):
    started_wall, started_cpu = perf_counter_ns(), process_time_ns()
    plan = _read_plan(root)
    rows = []
    for slot in plan["schedule"]:
        folder = root / f"slot-{slot['slot_index']:04d}"
        if not (folder / "outcome.json").exists():
            rows.append({"slot": slot, "status": "missing", "ratio": None,
                         "actual_proposals": 0, "unknown_work": True})
            continue
        outcome = _json(folder / "outcome.json")
        if (
            outcome.get("plan_hash") != plan["plan_hash"]
            or outcome.get("slot") != slot
            or _json(folder / "inventory.json") != _inventory(folder)
        ):
            raise ValueError("original pilot slot receipt changed")
        ratio = None
        actual = 0
        if outcome["status"] == "completed":
            report = _json(folder / "benchmark/comparison.json")
            if (
                report.get("report_hash") != outcome["report_hash"]
                or report.get("report_hash") != _sha(_bytes({
                    key: value for key, value in report.items() if key != "report_hash"
                }))
                or report["source_revision"] != plan["source_revision"]
                or report["proposal_identity"] != plan["policy_hash"]
                or report["proposal_guard"]["identity"] != plan["guard_hash"]
                or report["arm_order"] != slot["arm_order"]
            ):
                raise ValueError("pilot report binding changed")
            _audit_slot_contract(plan, slot, report)
            paths = {}
            for name in (*slot["arm_order"], "fresh-reference"):
                path = _json(folder / "benchmark" / name / "path.json")
                summary = report["fresh_reference"] if name == "fresh-reference" else report["arms"][name]
                if (
                    path["path_hash"] != _sha(_bytes({
                        key: value for key, value in path.items() if key != "path_hash"
                    }))
                    or summary != {key: value for key, value in path.items()
                                   if key not in ("response_history", "terminal_checkpoint",
                                                  "preload_response")}
                ):
                    raise ValueError("pilot original path differs from report")
                paths[name] = path
            _audit_original_histories(report, paths)
            decisions = [
                {"target_m": row["target_m"], "decision": row["proposal_decision"]}
                for row in report["arms"]["proposal"]["entries"]
            ]
            score = _runtime_score(report, decisions)
            score["actual_proposed_count"] = _actual_proposal_count(report)
            if score != outcome["score"]:
                raise ValueError("pilot score differs from original paths")
            if (
                score["full_comparison_pass"]
                and score["execution_work"]["unknown_work"] is False
                and score["actual_proposed_count"] > 0
            ):
                ratio = score["proposal_over_secant_path_wall_ratio"]
            actual = score["actual_proposed_count"]
        rows.append({"slot": slot, "status": outcome["status"], "ratio": ratio,
                     "actual_proposals": actual,
                     "unknown_work": outcome["unknown_work_until_outcome"],
                     "enclosing_slot_wall_ns": outcome.get("wall_ns"),
                     "enclosing_slot_cpu_ns": outcome.get("cpu_ns")})
    by_case = []
    for case_id in plan["development_case_ids"]:
        selected = [row for row in rows if row["slot"]["case_id"] == case_id]
        ratios = [row["ratio"] for row in selected]
        by_case.append({"case_id": case_id, "ratios": ratios,
                        "actual_proposals": sum(row["actual_proposals"] for row in selected),
                        "mean_ratio": sum(ratios) / len(ratios)
                        if all(ratio is not None for ratio in ratios) else None})
    candidate = (
        all(row["mean_ratio"] is not None for row in by_case)
        and sum(row["mean_ratio"] for row in by_case) / len(by_case)
        < 1 - plan["minimum_relative_improvement"]
    )
    result = {"schema_version": "rc-cost-gate-synthetic-development-audit.v1",
              "plan_hash": plan["plan_hash"], "failure_denominator": plan["failure_denominator"],
              "slots": rows, "cases": by_case,
              "equal_case_mean_ratio": sum(row["mean_ratio"] for row in by_case) / len(by_case)
              if all(row["mean_ratio"] is not None for row in by_case) else None,
              "predeclared_path_screen_pass": candidate,
              "actual_total_evaluation_cost_known": False,
              "independent_source_lineage": False,
              "heldout_executed": False,
              "policy_promoted": False,
              "net_benefit_proved": False,
              "separate_audit_wall_ns": perf_counter_ns() - started_wall,
              "separate_audit_cpu_ns": process_time_ns() - started_cpu}
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
    reviewing.add_argument("--verify-only", action="store_true",
                           help="recompute without rewriting the frozen audit receipt")
    args = parser.parse_args()
    if args.command == "prepare":
        result = prepare(args.packet, args.output)
    elif args.command == "slot":
        result = run_slot(args.output, args.index)
    else:
        result = audit(args.output, write=not args.verify_only)
    print(json.dumps(result, sort_keys=True))
    if args.command == "slot" and result["status"] != "completed":
        return 1
    if args.command == "audit" and result["predeclared_path_screen_pass"] is not True:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
