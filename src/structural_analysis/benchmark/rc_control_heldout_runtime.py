"""Admitted, single-slot RC held-out execution and conservative cost accounting.

This is a software contract. A source review and an eligible selected policy
must be supplied before any evaluation case can execute. Each slot is called
in its own fresh process; the read-only audit keeps missing slots in the
declared denominator. Neither a path ratio nor this audit proves net benefit.
"""

from pathlib import Path
import json
import os
import re
import subprocess
from threading import Lock
from time import perf_counter_ns, process_time_ns, time_ns

import numpy as np

from structural_analysis.benchmark import rc_control_learning as learning
from structural_analysis.benchmark.rc_control_design import _bytes, _save, _sha
from structural_analysis.benchmark.fiber_frame_runtime import _numeric_payload_difference
from structural_analysis.benchmark.rc_control_runtime_selection import (
    _runtime_score,
    _static_material_model_gate,
)
from structural_analysis.benchmark.rc_control_seed_runtime import _physical_mismatch_locations


_PROCESS_STARTED_NS = time_ns()
_PROCESS_SLOT_LOCK = Lock()
_CLAIMED_PROCESS_ID = None
_HASH = re.compile(r"sha256:[0-9a-f]{64}")


def _actual_proposal_count(report):
    return sum(
        entry.get("proposal_decision") == "proposed"
        and entry.get("proposal") is not None
        and bool(entry.get("invocations"))
        and entry["invocations"][0].get("seed_used") is True
        and entry["invocations"][0].get("status") in ("returned", "raised")
        for entry in report["arms"]["proposal"]["entries"]
    )


def _receipt_inventory(root, plan_hash, slot_index):
    """Hash every original slot file except the inventory and its outcome."""
    files = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("slot receipt symlink is not an original file")
        if path.is_dir():
            continue
        relative = path.relative_to(root).as_posix()
        if relative in ("receipt-inventory.json", "outcome.json"):
            continue
        payload = path.read_bytes()
        files.append({"path": relative, "sha256": _sha(payload), "bytes": len(payload)})
    result = {
        "schema_version": "rc-heldout-receipt-inventory.v1",
        "plan_hash": plan_hash,
        "slot_index": slot_index,
        "file_count": len(files),
        "total_bytes": sum(row["bytes"] for row in files),
        "files": files,
    }
    result["inventory_hash"] = _sha(_bytes(result))
    return result


def _complete_history(path):
    return ([path["preload_response"]] if path.get("preload_response") is not None
            else []) + path["response_history"]


def _audit_original_histories(report, paths):
    """Recompute the producer's full-history verdict from original path files."""
    fresh = paths["fresh-reference"]
    reference = paths["reference"]
    fresh_history = _complete_history(fresh)
    for name, arm in paths.items():
        if name == "fresh-reference":
            continue
        arm_history = _complete_history(arm)
        structure, maximum_absolute, maximum_relative, within = (
            _numeric_payload_difference(
                fresh_history, arm_history,
                absolute_tolerance=report["absolute_tolerance"],
                relative_tolerance=report["relative_tolerance"],
            )
        )
        recomputed = {
            "full_history_pass": fresh["status"] == arm["status"] == "complete"
            and structure and within,
            "structure_match": structure,
            "mismatch_locations": _physical_mismatch_locations(
                fresh_history, arm_history,
                absolute_tolerance=report["absolute_tolerance"],
                relative_tolerance=report["relative_tolerance"],
            ),
            "physical_values_within_tolerance": within,
            "maximum_absolute_difference_mixed_SI_fields": maximum_absolute
            if np.isfinite(maximum_absolute) else None,
            "maximum_relative_difference": maximum_relative
            if np.isfinite(maximum_relative) else None,
            "exact_terminal_checkpoint": _bytes(fresh["terminal_checkpoint"])
            == _bytes(arm["terminal_checkpoint"]),
        }
        if report["comparisons"].get(name) != recomputed:
            raise ValueError("stored comparison differs from original full histories")
    if set(report["comparisons"]) != set(paths) - {"fresh-reference"} or (
        report["reference_repeat_exact"] is not (
            report["comparisons"]["reference"]["full_history_pass"]
            and report["comparisons"]["reference"]["exact_terminal_checkpoint"]
            and _bytes(_complete_history(reference)) == _bytes(fresh_history)
        )
    ):
        raise ValueError("fresh-reference repeat differs from original full histories")


def _selected_policy(selection, source_revision):
    if (
        type(selection) is not dict
        or selection.get("result_hash")
        != _sha(_bytes({k: v for k, v in selection.items() if k != "result_hash"}))
        or selection.get("source_revision") != source_revision
        or selection.get("selected_strategy") != "learned_svd"
        or selection.get("validation_or_holdout_execution") is not False
        or selection.get("selected_policy") is None
    ):
        raise ValueError("frozen, source-bound learned development selection required")
    policy = learning.RCControlSeedPolicy(_bytes(selection["selected_policy"]).decode())
    return policy


def declare_heldout_runtime(
    cases,
    selection,
    source_records,
    *,
    source_revision,
    evaluation_case_ids,
    arithmetic_profile="binary64",
    repetitions=3,
    minimum_relative_improvement=0.01,
):
    """Predeclare an entire admitted cohort without executing a solver.

    Source records are reviewed inputs, not a replacement for auditing the
    original source bytes and rights receipt. All train, validation and holdout
    cases enter the existing conservative connected-shape split screen.
    """
    if type(source_revision) is not str or not re.fullmatch(r"[0-9a-f]{40}", source_revision):
        raise ValueError("exact source revision required")
    if repetitions not in (3, 6) or type(repetitions) is not int:
        raise ValueError("three or six balanced repetitions required")
    if (
        type(minimum_relative_improvement) not in (int, float)
        or not 0 <= minimum_relative_improvement < 1
    ):
        raise ValueError("predeclared relative threshold required")
    policy = _selected_policy(selection, source_revision)
    cases = tuple(cases)
    learning._preflight(cases, arithmetic_profile)
    by_id = {case.case_id: case for case in cases}
    admitted = sorted(c.case_id for c in cases if c.split != "train")
    if (
        type(evaluation_case_ids) not in (tuple, list)
        or list(evaluation_case_ids) != admitted
        or not admitted
        or type(source_records) is not dict
        or set(source_records) != set(by_id)
    ):
        raise ValueError("exact declared evaluation and source roster required")
    lineage_splits = {}
    rows = []
    for case in sorted(cases, key=lambda c: c.case_id):
        record = source_records[case.case_id]
        if (
            type(record) is not dict
            or set(record) != {
                "original_record_hash", "rights_review_hash", "lineage_group_id",
                "rights_status", "source_role",
            }
            or any(
                type(record[key]) is not str or not _HASH.fullmatch(record[key])
                for key in ("original_record_hash", "rights_review_hash")
            )
            or type(record["lineage_group_id"]) is not str
            or not record["lineage_group_id"]
            or record["rights_status"] != (
                "training_permitted" if case.split == "train" else "evaluation_permitted"
            )
            or record["source_role"] != "original"
        ):
            raise ValueError("reviewed original source and rights bindings required")
        lineage_splits.setdefault(record["lineage_group_id"], set()).add(case.split)
        rows.append({
            "case_id": case.case_id,
            "split": case.split,
            "project_id": case.project_id,
            "geometry_family_id": case.geometry_family_id,
            "load_history_id": case.load_history_id,
            "model_hash": case.model.canonical_model_checksum,
            "request_hash": _sha(_bytes(case.request.to_dict())),
            "source": record,
        })
    if any(len(splits) != 1 for splits in lineage_splits.values()):
        raise ValueError("source lineage group crosses development and evaluation splits")
    order = ["reference", "secant", "proposal"]
    schedule = [
        {"slot_index": len(admitted) * repetition + case_index,
         "case_id": case_id, "repetition_index": repetition,
         "arm_order": order[repetition % 3:] + order[:repetition % 3]}
        for repetition in range(repetitions)
        for case_index, case_id in enumerate(admitted)
    ]
    plan = {
        "schema_version": "rc-heldout-runtime-plan.v1",
        "source_revision": source_revision,
        "selection_result_hash": selection["result_hash"],
        "policy_hash": policy.policy_hash,
        "arithmetic_profile": arithmetic_profile,
        "cases": rows,
        "evaluation_case_ids": admitted,
        "schedule": schedule,
        "repetitions": repetitions,
        "warmup_repetitions": 0,
        "fresh_process_per_slot": True,
        "failure_denominator": len(schedule),
        "proposal_abstention_strategy": "secant",
        "static_model_abstention": policy.to_dict().get("feature_profile")
        == learning.MATERIAL_FEATURE_PROFILE,
        "absolute_tolerance": 1e-10,
        "relative_tolerance": 1e-8,
        "minimum_relative_improvement": minimum_relative_improvement,
        "decision_rule": "retain secant unless every declared slot has complete verified histories, known work, an actual learned proposal and fully audited lifecycle costs, then require net improvement above threshold",
        "training_cost_reuse_assumption": None,
        "break_even_eligible": False,
        "cost_scopes": {
            "enclosing": ["slot_total"],
            "nested_in_slot": ["policy_loading", "preflight", "model_gate", "benchmark", "receipt_inventory", "slot_io"],
            "nested_in_benchmark": ["material_capture", "inference", "solver_attempts", "recovery", "step_report_io", "full_path_verification"],
            "outside_slot": ["process_startup", "label_generation", "training_fits", "development_selection", "separate_audit"],
        },
        "source_rights_and_lineage_independently_authenticated": False,
        "physical_validation": False,
        "automatic_promotion": False,
    }
    plan["plan_hash"] = _sha(_bytes(plan))
    return plan


def _require_clean_source(source_revision):
    root = Path(__file__).resolve().parents[3]
    head = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    dirty = subprocess.check_output(["git", "-C", str(root), "status", "--porcelain"], text=True)
    if head != source_revision or dirty:
        raise ValueError("execution requires the exact clean committed source")


def run_heldout_slot(plan, cases, selection, *, slot_index, output_directory):
    """Execute one declared slot; call once per fresh process, outside the repo.

    A raised benchmark leaves a terminal unknown-work record and its original
    partial path files. No later slot is silently substituted for it.
    """
    if plan.get("plan_hash") != _sha(_bytes({k: v for k, v in plan.items() if k != "plan_hash"})):
        raise ValueError("held-out plan hash mismatch")
    if type(slot_index) is not int or not 0 <= slot_index < len(plan["schedule"]):
        raise ValueError("declared slot index required")
    if plan["selection_result_hash"] != selection.get("result_hash"):
        raise ValueError("development selection changed")
    wall, cpu = perf_counter_ns(), process_time_ns()
    lw, lc = perf_counter_ns(), process_time_ns()
    policy = _selected_policy(selection, plan["source_revision"])
    policy_load_cost = {"wall_ns": perf_counter_ns() - lw,
                        "cpu_ns": process_time_ns() - lc}
    if policy.policy_hash != plan["policy_hash"]:
        raise ValueError("selected policy changed")
    cases = tuple(cases)
    pw, pc = perf_counter_ns(), process_time_ns()
    prepared = learning._preflight(cases, plan["arithmetic_profile"])
    preflight_cost = {"wall_ns": perf_counter_ns() - pw,
                      "cpu_ns": process_time_ns() - pc}
    declared = {row["case_id"]: row for row in plan["cases"]}
    if set(prepared) != set(declared):
        raise ValueError("case roster changed")
    for case in cases:
        row = declared[case.case_id]
        if (
            row["split"] != case.split
            or row["project_id"] != case.project_id
            or row["geometry_family_id"] != case.geometry_family_id
            or row["load_history_id"] != case.load_history_id
            or row["model_hash"] != case.model.canonical_model_checksum
            or row["request_hash"] != _sha(_bytes(case.request.to_dict()))
        ):
            raise ValueError("held-out case input changed")
    _require_clean_source(plan["source_revision"])
    slot = plan["schedule"][slot_index]
    case = next(c for c in cases if c.case_id == slot["case_id"])
    if case.split == "train":
        raise ValueError("held-out slot cannot execute training case")
    root = Path(output_directory)
    if root.name != f"slot-{slot_index:04d}":
        raise ValueError("slot output directory must bind its declared index")
    global _CLAIMED_PROCESS_ID
    with _PROCESS_SLOT_LOCK:
        if _CLAIMED_PROCESS_ID == os.getpid():
            raise ValueError("each held-out slot requires a fresh process")
        _CLAIMED_PROCESS_ID = os.getpid()
    root.mkdir(parents=True, exist_ok=False)
    process_identity = [os.getpid(), _PROCESS_STARTED_NS]
    started = {
        "plan_hash": plan["plan_hash"], "slot": slot,
        "process_identity": process_identity, "status": "started",
        "unknown_work_until_outcome": True,
    }
    _save(root, "started.json", _bytes(started))
    decisions = []
    outcome = dict(started)
    outcome["cost_ledger"] = {
        "process_startup": None, "label_generation": None,
        "training_fits": None, "development_selection": None,
        "separate_audit": None, "preflight": preflight_cost,
        "policy_loading": policy_load_cost, "slot_io": None,
        "material_capture": None, "inference": None,
        "solver_attempts": None, "recovery": None,
        "step_report_io": None, "full_path_verification": None,
    }
    report = None
    try:
        loaded = policy
        _, compiled, features, _, _ = prepared[case.case_id]
        gate = None
        if plan["static_model_abstention"]:
            gw, gc = perf_counter_ns(), process_time_ns()
            gate = _static_material_model_gate(loaded, features)
            outcome["cost_ledger"]["model_gate"] = {
                "wall_ns": perf_counter_ns() - gw, "cpu_ns": process_time_ns() - gc,
            }
            _save(root, "model-gate.json", _bytes(gate))
        static_abstain = gate is not None and gate["status"] == "rejected"

        def propose(context):
            value = None if static_abstain else loaded.propose(
                context, features, compiled.problem.free_global_dofs,
                case.request.solver_config.contract_hash,
                arithmetic_profile=plan["arithmetic_profile"],
                load_factor_coordinate_scale_m=case.request.solver_config.load_factor_coordinate_scale_m,
            )
            decisions.append({
                "target_m": context.target_m,
                "decision": "proposed" if value is not None else
                ("abstained_to_secant" if learning.secant_seed(context) is not None
                 else "abstained_to_reference"),
            })
            return value

        bw, bc = perf_counter_ns(), process_time_ns()
        report = learning.benchmark_rc_control_seed_paths(
            case.model, case.request,
            source_revision=plan["source_revision"],
            output_directory=root / "benchmark",
            proposal=propose, proposal_identity=loaded.policy_hash,
            proposal_abstention_strategy="secant",
            arm_order=tuple(slot["arm_order"]),
            absolute_tolerance=plan["absolute_tolerance"],
            relative_tolerance=plan["relative_tolerance"],
            capture_material_state=plan["static_model_abstention"] and not static_abstain,
            material_capture_scope="proposal-only"
            if plan["static_model_abstention"] and not static_abstain else "all-arms",
            **learning._arithmetic_kwargs(plan["arithmetic_profile"]),
        )
        outcome["cost_ledger"]["benchmark"] = {
            "wall_ns": perf_counter_ns() - bw, "cpu_ns": process_time_ns() - bc,
            "includes_all_four_paths_and_verification": True,
        }
        if _bytes(loaded.to_dict()) != _bytes(selection["selected_policy"]):
            raise ValueError("loaded policy changed during execution")
        score = _runtime_score(
            report, decisions,
            proposal_setup_wall_ns=outcome["cost_ledger"].get("model_gate", {}).get("wall_ns", 0),
        )
        score["actual_proposed_count"] = _actual_proposal_count(report)
        outcome.update(
            status="completed", unknown_work_until_outcome=score["execution_work"]["unknown_work"],
            report_hash=report["report_hash"], score=score,
        )
    except Exception as exc:
        outcome.update(status="raised", exception_kind=type(exc).__name__,
                       unknown_work_until_outcome=True)
    finally:
        outcome["decisions"] = decisions
        iw, ic = perf_counter_ns(), process_time_ns()
        inventory = _receipt_inventory(root, plan["plan_hash"], slot_index)
        _save(root, "receipt-inventory.json", _bytes(inventory))
        outcome["cost_ledger"]["receipt_inventory"] = {
            "wall_ns": perf_counter_ns() - iw, "cpu_ns": process_time_ns() - ic,
        }
        outcome["wall_ns"] = perf_counter_ns() - wall
        outcome["cpu_ns"] = process_time_ns() - cpu
        outcome["cost_ledger"]["enclosing_slot"] = {
            "wall_ns": outcome["wall_ns"], "cpu_ns": outcome["cpu_ns"],
            "nested_scopes_are_not_additive": True,
            "excludes_final_outcome_write": True,
        }
        outcome["receipt_inventory_hash"] = inventory["inventory_hash"]
        _save(root, "outcome.json", _bytes(outcome))
    return outcome


def summarize_heldout_runtime(plan, outcomes):
    """Retain all slots in the denominator; publish no net-benefit claim."""
    if plan.get("plan_hash") != _sha(_bytes({k: v for k, v in plan.items() if k != "plan_hash"})):
        raise ValueError("held-out plan hash mismatch")
    if type(outcomes) is not dict or set(outcomes) - set(range(len(plan["schedule"]))):
        raise ValueError("only declared slot outcomes allowed")
    rows = []
    processes = set()
    for slot in plan["schedule"]:
        outcome = outcomes.get(slot["slot_index"])
        if outcome is None:
            rows.append({"slot": slot, "status": "missing", "unknown_work": True,
                         "actual_learned_proposals": 0, "path_ratio": None,
                         "known_slot_wall_ns": None, "known_slot_cpu_ns": None})
            continue
        if outcome.get("plan_hash") != plan["plan_hash"] or outcome.get("slot") != slot:
            raise ValueError("outcome does not match declared slot")
        process = tuple(outcome.get("process_identity", ()))
        if len(process) != 2 or process in processes:
            raise ValueError("each held-out slot requires a distinct fresh process")
        processes.add(process)
        score = outcome.get("score") if outcome.get("status") == "completed" else None
        eligible = bool(
            score and score.get("full_comparison_pass") is True
            and score.get("execution_work", {}).get("unknown_work") is False
            and outcome.get("unknown_work_until_outcome") is False
            and score.get("actual_proposed_count", 0) > 0
        )
        rows.append({
            "slot": slot, "status": outcome.get("status"),
            "unknown_work": outcome.get("unknown_work_until_outcome", True),
            "actual_learned_proposals": score.get("actual_proposed_count", 0) if score else 0,
            "path_ratio": score["proposal_over_secant_path_wall_ratio"] if eligible else None,
            "known_slot_wall_ns": outcome.get("wall_ns"),
            "known_slot_cpu_ns": outcome.get("cpu_ns"),
        })
    by_case = []
    for case_id in plan["evaluation_case_ids"]:
        case_rows = [row for row in rows if row["slot"]["case_id"] == case_id]
        ratios = [row["path_ratio"] for row in case_rows]
        by_case.append({
            "case_id": case_id, "paired_path_ratios": ratios,
            "statuses": [row["status"] for row in case_rows],
            "actual_learned_proposals": sum(row["actual_learned_proposals"] for row in case_rows),
            "complete_verified_repetitions": sum(ratio is not None for ratio in ratios),
            "mean_path_ratio": sum(ratios) / len(ratios)
            if all(ratio is not None for ratio in ratios) else None,
        })
    return {
        "schema_version": "rc-heldout-runtime-summary.v1",
        "plan_hash": plan["plan_hash"],
        "declared_denominator": plan["failure_denominator"],
        "slots": rows,
        "cases": by_case,
        "complete_verified_slots": sum(row["path_ratio"] is not None for row in rows),
        "failed_or_ineligible_slots": sum(row["path_ratio"] is None for row in rows),
        "unknown_or_missing_slots": sum(row["unknown_work"] for row in rows),
        "actual_learned_proposals": sum(row["actual_learned_proposals"] for row in rows),
        "known_slot_wall_ns": sum(row["known_slot_wall_ns"] or 0 for row in rows),
        "known_slot_cpu_ns": sum(row["known_slot_cpu_ns"] or 0 for row in rows),
        "actual_total_evaluation_wall_ns": None,
        "unknown_evaluation_cost": True,
        "cost_note": "known slot times exclude process startup and prior label, fit, selection and separate audit costs; nested path and component timers are not additive",
        "path_ratios_are_diagnostic_only": True,
        "lifecycle_costs_audited": False,
        "net_benefit_proved": False,
        "selected_strategy": "secant",
    }


def _read_receipt(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate receipt key: {key}")
            result[key] = value
        return result
    return json.loads(path.read_bytes(), object_pairs_hook=unique)


def audit_heldout_receipts(plan, root):
    """Read original slot files and reject changed report, policy or inputs.

    Missing and raised slots remain in the denominator. This audit does not
    authenticate external source rights, independent physics or lifecycle cost.
    """
    audit_wall, audit_cpu = perf_counter_ns(), process_time_ns()
    root = Path(root)
    outcomes = {}
    rows = {row["case_id"]: row for row in plan["cases"]}
    for slot in plan["schedule"]:
        index = slot["slot_index"]
        folder = root / f"slot-{index:04d}"
        if not folder.exists():
            continue
        if not (folder / "started.json").exists():
            continue
        started = _read_receipt(folder / "started.json")
        if (
            started.get("plan_hash") != plan["plan_hash"]
            or started.get("slot") != slot
            or started.get("status") != "started"
            or started.get("unknown_work_until_outcome") is not True
        ):
            raise ValueError("slot start does not match declared plan")
        if not (folder / "outcome.json").exists():
            outcomes[index] = {
                **started, "status": "interrupted",
                "unknown_work_until_outcome": True,
            }
            continue
        outcome = _read_receipt(folder / "outcome.json")
        if (
            any(outcome.get(key) != started.get(key)
                   for key in ("plan_hash", "slot", "process_identity"))
        ):
            raise ValueError("slot start and outcome binding mismatch")
        inventory = _read_receipt(folder / "receipt-inventory.json")
        if inventory != _receipt_inventory(folder, plan["plan_hash"], index) or (
            outcome.get("receipt_inventory_hash") != inventory["inventory_hash"]
        ):
            raise ValueError("original slot receipt inventory mismatch")
        ledger = outcome.get("cost_ledger", {})
        enclosure = ledger.get("enclosing_slot", {})
        if any(
            type(outcome.get(key)) is not int or outcome[key] < 0
            or enclosure.get(key) != outcome[key]
            for key in ("wall_ns", "cpu_ns")
        ):
            raise ValueError("measured enclosing slot costs required")
        receipt_cost = ledger.get("receipt_inventory", {})
        if any(
            type(receipt_cost.get(key)) is not int
            or not 0 <= receipt_cost[key] <= outcome[key]
            for key in ("wall_ns", "cpu_ns")
        ):
            raise ValueError("receipt inventory cost exceeds enclosing slot")
        if outcome.get("status") == "completed":
            report = _read_receipt(folder / "benchmark" / "comparison.json")
            if (
                report.get("schema_version") != "experimental-rc-control-seed-comparison.v2"
                or report.get("report_hash") != _sha(_bytes({
                    key: value for key, value in report.items() if key != "report_hash"
                }))
                or outcome.get("report_hash") != report["report_hash"]
                or report.get("source_revision") != plan["source_revision"]
                or report.get("model_checksum") != rows[slot["case_id"]]["model_hash"]
                or _sha(_bytes(report.get("request"))) != rows[slot["case_id"]]["request_hash"]
                or report.get("proposal_identity") != plan["policy_hash"]
                or report.get("arm_order") != slot["arm_order"]
                or report.get("absolute_tolerance") != plan["absolute_tolerance"]
                or report.get("relative_tolerance") != plan["relative_tolerance"]
            ):
                raise ValueError("full-path original report binding mismatch")
            benchmark_cost = ledger.get("benchmark", {})
            if any(
                type(benchmark_cost.get(key)) is not int
                or not 0 <= report["whole_study_" + key] <= benchmark_cost[key] <= outcome[key]
                for key in ("wall_ns", "cpu_ns")
            ):
                raise ValueError("whole benchmark cost exceeds enclosing slot")
            if set(report["arms"]) != set(slot["arm_order"]):
                raise ValueError("full-path arm roster differs from declared slot")
            paths = {}
            for arm_name in (*slot["arm_order"], "fresh-reference"):
                path = _read_receipt(folder / "benchmark" / arm_name / "path.json")
                paths[arm_name] = path
                summary = (report["fresh_reference"] if arm_name == "fresh-reference"
                           else report["arms"][arm_name])
                if (
                    path.get("schema_version") not in (
                        "experimental-rc-control-seed-path.v1",
                        "experimental-rc-control-seed-path.v2",
                    )
                    or
                    path.get("path_hash") != _sha(_bytes({
                        key: value for key, value in path.items() if key != "path_hash"
                    }))
                    or summary != {key: value for key, value in path.items()
                                   if key not in ("response_history", "terminal_checkpoint",
                                                  "preload_response")}
                ):
                    raise ValueError("original path file differs from comparison report")
            _audit_original_histories(report, paths)
            gate = outcome.get("cost_ledger", {}).get("model_gate")
            score = _runtime_score(
                report, outcome.get("decisions", []),
                proposal_setup_wall_ns=gate["wall_ns"] if gate is not None else 0,
            )
            score["actual_proposed_count"] = _actual_proposal_count(report)
            if score != outcome.get("score") or (
                outcome.get("unknown_work_until_outcome")
                != score["execution_work"]["unknown_work"]
            ):
                raise ValueError("stored path score differs from original report")
        elif outcome.get("status") != "raised" or outcome.get("unknown_work_until_outcome") is not True:
            raise ValueError("terminal completed or raised slot outcome required")
        outcomes[index] = outcome
    summary = summarize_heldout_runtime(plan, outcomes)
    summary["separate_audit"] = {
        "wall_ns": perf_counter_ns() - audit_wall,
        "cpu_ns": process_time_ns() - audit_cpu,
        "scope": "read, hash and recheck original slot receipts; excludes summary write",
    }
    return summary
