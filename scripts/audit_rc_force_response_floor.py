"""Posthoc fixed-displacement load-factor floor over a sealed RC oracle packet.

This checks stored fresh-replay receipts; it does not execute a solver, change a
v1 search selection, or establish ultimate strength or learned-policy benefit.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re


PLAN_SCHEMA = "experimental-rc-fixed-displacement-force-response-floor-plan.v1"
REPORT_SCHEMA = "experimental-rc-fixed-displacement-force-response-floor-report.v1"
AUDIT_SCHEMA = "experimental-rc-fixed-displacement-force-response-floor-audit.v1"
HASH = re.compile(r"sha256:[0-9a-f]{64}\Z")
REVISION = re.compile(r"[0-9a-f]{40}\Z")
MAX_JSON_BYTES = 16 * 1024 * 1024


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def sha(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def read_bounded(path: Path) -> bytes:
    with path.open("rb") as stream:
        raw = stream.read(MAX_JSON_BYTES + 1)
    require(len(raw) <= MAX_JSON_BYTES, f"JSON file exceeds bound: {path}")
    return raw


def decode(raw: bytes, path: Path) -> dict:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key in {path}: {key}")
            result[key] = value
        return result

    def nonfinite(value):
        raise ValueError(f"nonfinite JSON token in {path}: {value}")

    require(len(raw) <= MAX_JSON_BYTES, f"JSON file exceeds bound: {path}")
    result = json.loads(raw, object_pairs_hook=unique, parse_constant=nonfinite)
    require(type(result) is dict, f"JSON object required: {path}")
    return result


def load(path: Path) -> dict:
    return decode(read_bounded(path), path)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def hashed_object(value: dict, key: str) -> bool:
    return type(value.get(key)) is str and value[key] == sha(canonical({
        name: item for name, item in value.items() if name != key
    }))


def checked_ref(root: Path, ref: dict, prefix: str) -> dict:
    require(type(ref) is dict and set(ref) == {"path", "byte_length", "sha256"},
            f"{prefix}: invalid artifact reference")
    relative = ref["path"]
    require(type(relative) is str and not Path(relative).is_absolute()
            and ".." not in Path(relative).parts
            and type(ref["sha256"]) is str and HASH.fullmatch(ref["sha256"])
            and type(ref["byte_length"]) is int and 0 <= ref["byte_length"] <= MAX_JSON_BYTES,
            f"{prefix}: invalid artifact path or digest")
    path = root / relative
    require(path.is_file() and not path.is_symlink()
            and path.resolve().is_relative_to(root.resolve()),
            f"{prefix}: artifact missing or escapes packet")
    raw = read_bounded(path)
    require(len(raw) == ref["byte_length"] and sha(raw) == ref["sha256"],
            f"{prefix}: artifact bytes differ")
    return decode(raw, path)


def packet_inventory(packet: Path) -> tuple[int, str]:
    files = []
    for path in packet.rglob("*"):
        require(not path.is_symlink(), "packet contains a symlink")
        if path.is_file() and path.name != "audit.json":
            raw = path.read_bytes()
            files.append((path, len(raw), sha(raw)))
    # Match the original auditor's Path ordering, which differs from sorting
    # string paths at a directory/file boundary such as search/ vs search-.
    files.sort(key=lambda item: item[0])
    inventory = [[str(path.relative_to(packet)), size, digest]
                 for path, size, digest in files]
    return len(files), sha(canonical(inventory))


def validate_plan(plan: dict, request: dict, source_revision: str,
                  audit_sha256: str) -> None:
    require(set(plan) == {"schema_version", "source_revision", "audit_receipt_sha256",
                          "target_index", "target_displacement_m", "minimum_load_factor",
                          "evaluation_timing"}, "exact floor plan fields required")
    require(plan["schema_version"] == PLAN_SCHEMA and plan["evaluation_timing"] == "posthoc",
            "this version supports posthoc diagnosis only")
    require(type(plan["source_revision"]) is str and REVISION.fullmatch(plan["source_revision"])
            and plan["source_revision"] == source_revision,
            "floor plan source revision differs")
    require(type(plan["audit_receipt_sha256"]) is str
            and plan["audit_receipt_sha256"] == audit_sha256,
            "floor plan does not pin the passing audit receipt")
    index = plan["target_index"]
    targets = request.get("targets_m")
    require(type(index) is int and type(targets) is list and 0 <= index < len(targets),
            "exact target index required")
    target = plan["target_displacement_m"]
    require(type(target) in (int, float) and math.isfinite(target)
            and target == targets[index], "target displacement differs from request")
    floor = plan["minimum_load_factor"]
    require(type(floor) in (int, float) and math.isfinite(floor) and floor > 0,
            "positive finite load-factor floor required")
    require(request.get("experimental_pin_roller_beam") is True
            and not request.get("constant_nodal_loads"),
            "pilot floor requires pin/roller reference loading without preload")


def verified_load_factor(row: dict, comparison: dict, directory: Path,
                         request: dict, index: int, target: float) -> float:
    cid = row["candidate_id"]
    require(row.get("status") == "verified" and row.get("failure") is None
            and row.get("full_reference_verification_pass") is True,
            f"{cid}: complete verified row required")
    artifacts = row.get("artifacts")
    require(type(artifacts) is dict and "result" in artifacts and "verification" in artifacts,
            f"{cid}: result and verification references required")
    for role in ("result", "verification"):
        require(artifacts[role].get("path") == f"{cid}/{role}.json",
                f"{cid}: unexpected {role} artifact path")
    result = checked_ref(directory, artifacts["result"], f"{cid}/result")
    verification = checked_ref(directory, artifacts["verification"], f"{cid}/verification")
    require(hashed_object(result, "result_hash")
            and result.get("schema_version") == "bounded-rc-fiber-direct-control-result.v1"
            and result.get("status") == "ready"
            and result.get("contract_pass") is True and result.get("failure") is None
            and result.get("unsupported_features") == [],
            f"{cid}: original result is incomplete or resealed incorrectly")
    require(verification.get("schema_version") == "bounded-rc-fiber-direct-control-validation.v1"
            and verification.get("status") == "valid_artifact"
            and all(verification.get(key) is True for key in (
                "contract_pass", "artifact_contract_pass", "fresh_source_execution_invoked",
                "solver_replay_performed", "physical_path_complete"))
            and verification.get("unavailable_execution_work") is False
            and verification.get("verified_result_hash") == result["result_hash"]
            and verification.get("errors") == [],
            f"{cid}: stored fresh replay receipt is unavailable or unbound")
    authored = result.get("request", {})
    require(authored.get("control_global_dof") == request["control_global_dof"]
            and authored.get("targets_m") == request["targets_m"]
            and authored.get("experimental_pin_roller_beam") is True
            and authored.get("allow_reversals") == request.get("allow_reversals")
            and authored.get("maximum_reversals") == request.get("maximum_reversals")
            and authored.get("maximum_targets") == request.get("maximum_targets")
            and authored.get("configuration", {}).get("newton") == request["solver_config"]["newton"]
            and authored.get("configuration", {}).get("control_tolerance_m")
            == request["solver_config"]["control_tolerance_m"]
            and authored.get("configuration", {}).get("load_factor_coordinate_scale_m")
            == request["solver_config"]["load_factor_coordinate_scale_m"],
            f"{cid}: original result request differs")
    history = result.get("response_history")
    path = result.get("path") or {}
    attempts = path.get("attempts")
    require(type(history) is list and len(history) == len(request["targets_m"])
            and path.get("schema_version") == "stateful-fiber-frame2d-control-path.v1"
            and path.get("status") == "ready"
            and hashed_object(path, "path_hash")
            and path.get("targets_m") == request["targets_m"]
            and path.get("accepted_target_prefix_m") == request["targets_m"]
            and type(attempts) is list and len(attempts) == len(history),
            f"{cid}: accepted target history incomplete")
    attempt, response = attempts[index], history[index]
    step = attempt.get("step") or {}
    checkpoint = step.get("accepted_checkpoint") or {}
    require(attempt.get("committed") is True
            and attempt.get("target_control_displacement_m") == target
            and response.get("checkpoint_hash") == attempt.get("accepted_checkpoint_hash")
            and checkpoint.get("state_hash") == attempt.get("accepted_checkpoint_hash")
            and response.get("source_step_hash") == step.get("step_hash")
            and response.get("parent_checkpoint_hash") == attempt.get("parent_checkpoint_hash")
            and checkpoint.get("parent_state_hash") == attempt.get("parent_checkpoint_hash"),
            f"{cid}: target attempt and response differ")
    control = result.get("control") or {}
    require(control.get("global_dof") == request["control_global_dof"]
            and control.get("component") in ("UX", "UY")
            and type(control.get("node_id")) is str,
            f"{cid}: control coordinate is unsupported")
    displacements = [node for node in response.get("node_displacements", ())
                     if node.get("node_id") == control["node_id"]]
    require(len(displacements) == 1, f"{cid}: controlled node missing")
    coordinate = displacements[0][control["component"] + "_m"]
    tolerance = request["solver_config"]["control_tolerance_m"]
    require(type(coordinate) in (int, float) and math.isfinite(coordinate)
            and abs(coordinate - target) <= tolerance,
            f"{cid}: target displacement not verified")
    factor = response.get("load_factor")
    require(type(factor) in (int, float) and math.isfinite(factor),
            f"{cid}: finite signed load factor required")
    global_displacements = checkpoint.get("global_displacements")
    control_dof = request["control_global_dof"]
    require(type(global_displacements) is list and type(control_dof) is int
            and 0 <= control_dof < len(global_displacements)
            and checkpoint.get("load_factor") == factor
            and type(global_displacements[control_dof]) in (int, float)
            and math.isfinite(global_displacements[control_dof])
            and abs(global_displacements[control_dof] - target) <= tolerance,
            f"{cid}: accepted checkpoint differs from target response")
    require(row.get("selection_eligible") is True
            and all(screen.get("status") == "pass" for screen in row.get("screens", {}).values()),
            f"{cid}: original v1 physical screens failed")
    return factor


def require_positive_baseline_factor(outcomes: list[dict]) -> None:
    baseline = [row for row in outcomes if row["candidate_id"] == "baseline"]
    require(len(baseline) == 1 and baseline[0]["load_factor_at_target"] > 0,
            "baseline load factor must be positive in the reference-load direction")


def build_report(packet: Path, plan_path: Path, audit_path: Path) -> dict:
    packet = packet.resolve()
    require(packet.is_dir(), "packet directory required")
    plan_raw = read_bounded(plan_path)
    plan = decode(plan_raw, plan_path)
    audit_raw = read_bounded(audit_path)
    audit = decode(audit_raw, audit_path)
    audit_sha = sha(audit_raw)
    require(audit.get("schema") == "synthetic-rc-pin-roller-heldout-replication-audit.v1"
            and audit.get("pass") is True and audit.get("violations") == [],
            "passing original packet audit receipt required")
    count, inventory_sha = packet_inventory(packet)
    require(audit.get("packet_file_count_excluding_audit") == count
            and audit.get("packet_file_inventory_sha256") == inventory_sha,
            "packet bytes differ from pinned audit inventory")
    pre_raw = read_bounded(packet / "plan.json")
    pre = decode(pre_raw, packet / "plan.json")
    search_plan = load(packet / "search/plan.json")
    search = load(packet / "search/result.json")
    directory = packet / "search/exhaustive_oracle"
    comparison = load(directory / "comparison.json")
    require(sha(pre_raw) == audit.get("frozen_plan_sha256")
            and pre.get("source_revision") == audit.get("source_revision")
            and search_plan.get("source_revision") == pre["source_revision"]
            and search.get("source_revision") == pre["source_revision"],
            "source and frozen plan binding differs")
    require(hashed_object(search_plan, "plan_hash")
            and search_plan["plan_hash"] == audit.get("search_plan_hash")
            and hashed_object(search, "report_hash")
            and search["report_hash"] == audit.get("search_report_hash")
            and search.get("plan_hash") == search_plan["plan_hash"],
            "search plan/result digest binding differs")
    require(hashed_object(comparison, "report_hash")
            and comparison.get("schema_version") == "experimental-rc-control-design-comparison.v1"
            and comparison.get("status") == "complete"
            and comparison.get("source_revision_is_attestation") is False
            and search["oracle"]["comparison_hash"] == comparison["report_hash"]
            and comparison.get("source_revision") == pre["source_revision"],
            "complete original v1 oracle comparison required")
    request = search_plan["control_request"]
    require(request == comparison.get("control_request")
            and request == load(packet / "inputs/request.json")
            and search_plan.get("oracle_after_online_arms") is True,
            "exact authored request and later oracle required")
    validate_plan(plan, request, pre["source_revision"], audit_sha)
    pool = search_plan["pool"]
    rows = comparison["rows"]
    ids = [row["candidate_id"] for row in pool]
    require(ids == [row["candidate_id"] for row in rows]
            and len(ids) == len(set(ids)) and ids.count("baseline") == 1
            and len(rows) == search["candidate_denominator"]
            and comparison.get("verified_count") == len(rows)
            and comparison.get("candidate_denominator") == len(rows)
            and audit["comparisons"]["exhaustive_oracle"]["row_count"] == len(rows)
            and audit["comparisons"]["exhaustive_oracle"]["failed_candidate_ids"] == []
            and audit["comparisons"]["exhaustive_oracle"]["unknown_work_candidate_ids"] == [],
            "exhaustive verified denominator required")
    baseline_model = load(packet / "inputs/online-model.json")
    reference_loads = baseline_model.get("loads")
    force_unit = baseline_model.get("units", {}).get("force")
    require(type(reference_loads) is list and force_unit == "kN"
            and reference_loads, "declared kN reference loads required")
    outcomes = []
    for row, pool_row in zip(rows, pool, strict=True):
        cid = row["candidate_id"]
        model = checked_ref(directory, row["artifacts"]["model"], f"{cid}/model")
        require(model.get("loads") == reference_loads
                and model.get("units", {}).get("force") == force_unit
                and row["artifacts"]["model"]["sha256"] == pool_row["model_artifact"]["sha256"]
                and row["material_estimate"] == pool_row["material_estimate"],
                f"{cid}: reference load pattern differs")
        factor = verified_load_factor(row, comparison, directory, request,
                                      plan["target_index"], plan["target_displacement_m"])
        price = row["material_estimate"]["total"]
        require(type(price) in (int, float) and math.isfinite(price) and price >= 0,
                f"{cid}: finite synthetic estimate required")
        outcomes.append({"candidate_id": cid, "load_factor_at_target": factor,
                         "floor_status": "pass" if factor >= plan["minimum_load_factor"] else "fail",
                         "original_scoped_synthetic_estimate": price})
    require_positive_baseline_factor(outcomes)
    passing = [row for row in outcomes if row["floor_status"] == "pass"]
    cheapest = min(passing, key=lambda row: (
        row["original_scoped_synthetic_estimate"], row["candidate_id"]
    )) if passing else None
    report = {
        "schema_version": REPORT_SCHEMA,
        "evaluation_timing": "posthoc",
        "source_revision": pre["source_revision"],
        "floor_plan_sha256": sha(plan_raw),
        "original_audit_receipt_sha256": audit_sha,
        "original_packet_inventory_sha256": inventory_sha,
        "original_search_report_hash": search["report_hash"],
        "original_oracle_comparison_hash": comparison["report_hash"],
        "target_index": plan["target_index"],
        "target_displacement_m": plan["target_displacement_m"],
        "minimum_load_factor": plan["minimum_load_factor"],
        "load_factor_unit": "dimensionless",
        "load_factor_meaning": "signed_multiplier_of_fixed_model_reference_nodal_loads",
        "reference_loads": reference_loads,
        "reference_force_unit": force_unit,
        "rows": outcomes,
        "posthoc_oracle_floor_pass_candidate_ids": [row["candidate_id"] for row in passing],
        "posthoc_oracle_cheapest_floor_pass_candidate_id": (
            None if cheapest is None else cheapest["candidate_id"]
        ),
        "posthoc_oracle_cheapest_floor_pass_synthetic_estimate": (
            None if cheapest is None else cheapest["original_scoped_synthetic_estimate"]
        ),
        "original_v1_oracle_selected_candidate_id": comparison["selected_candidate_id"],
        "original_v1_search_selection_unchanged": True,
        "online_arms_not_reevaluated": True,
        "learned_policy_predicted_this_floor": False,
        "physical_claim": "verified_same_engine_fixed_displacement_load_response_only",
    }
    report["report_hash"] = sha(canonical(report))
    return report


def audit_report(packet: Path, plan: Path, receipt: Path, report_path: Path) -> dict:
    expected = build_report(packet, plan, receipt)
    report_raw = read_bounded(report_path)
    supplied = decode(report_raw, report_path)
    require(canonical(supplied) == canonical(expected),
            "floor report differs from original-result derivation")
    seal = {"schema_version": AUDIT_SCHEMA, "pass": True,
            "report_sha256": sha(report_raw),
            "report_hash": expected["report_hash"],
            "original_audit_receipt_sha256": expected["original_audit_receipt_sha256"],
            "original_packet_inventory_sha256": expected["original_packet_inventory_sha256"],
            "derivation": "recomputed_from_original_result_and_stored_fresh_replay_receipt",
            "evaluation_timing": "posthoc"}
    seal["audit_hash"] = sha(canonical(seal))
    return seal


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("report", "audit"))
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--original-audit", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.resolve().is_relative_to(args.packet.resolve()),
            "sidecar output must stay outside the original packet")
    if args.mode == "report":
        require(args.report is None, "report mode does not accept --report")
        result = build_report(args.packet, args.plan, args.original_audit)
    else:
        require(args.report is not None, "audit mode requires --report")
        result = audit_report(args.packet, args.plan, args.original_audit, args.report)
    with args.output.open("xb") as stream:
        stream.write(canonical(result) + b"\n")
    print(json.dumps({"schema_version": result["schema_version"],
                      "report_hash": result.get("report_hash"),
                      "pass": result.get("pass")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
