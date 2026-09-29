"""Read-only, stdlib-only audit of a prospective RC force-floor packet.

This checks recorded bytes, provenance, arithmetic, and original solver artifact
claims. It does not execute a solver or provide independent physical validation.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import subprocess


PROTOCOL_SCHEMA = "experimental-rc-control-force-floor-protocol.v1"
PREDECLARATION_SCHEMA = "experimental-rc-control-force-floor-predeclaration.v1"
RUNNER_SCHEMA = "experimental-rc-control-force-floor-runner-receipt.v1"
PLAN_SCHEMA = "experimental-rc-control-force-floor-price-search-plan.v1"
SEARCH_SCHEMA = "experimental-rc-control-force-floor-price-search.v1"
COMPARISON_SCHEMA = "experimental-rc-control-design-comparison.v2"
AUDIT_SCHEMA = "experimental-rc-control-force-floor-packet-audit.v1"
INVENTORY_SCHEMA = "experimental-rc-control-force-floor-packet-inventory.v1"
COST_SCHEMA = "rc-control-candidate-cost-optimality.v3"
ROLES = ("model", "request", "experiment", "floor_plan")
QUANTITY_SCOPE = "gross_concrete_and_straight_authored_longitudinal_rebar.v1"
EXCLUDED_ITEMS = [
    "transverse_reinforcement",
    "laps_anchorage_hooks",
    "waste",
    "formwork",
    "labor",
    "fabrication",
    "transport",
    "tax",
]
ROW_ARTIFACT_FILES = (
    "model.json",
    "analysis-started.json",
    "analysis-outcome.json",
    "result.json",
    "checkpoint.json",
    "verification-started.json",
    "verification-outcome.json",
    "verification.json",
)


class AuditError(ValueError):
    """A packet claim cannot be derived from its frozen inputs and originals."""


def require(condition, message):
    if not condition:
        raise AuditError(message)


def canonical(value):
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def sha(data):
    return "sha256:" + hashlib.sha256(data).hexdigest()


def same(left, right):
    return canonical(left) == canonical(right)


def decode(data, label):
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise AuditError(f"{label}: duplicate JSON key {key}")
            value[key] = item
        return value

    def nonfinite(token):
        raise AuditError(f"{label}: non-finite JSON token {token}")

    try:
        return json.loads(data, object_pairs_hook=unique, parse_constant=nonfinite)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise AuditError(f"{label}: invalid JSON: {error}") from error


def relative_path(path):
    require(type(path) is str and path and "\\" not in path, "unsafe packet path")
    parts = PurePosixPath(path).parts
    require(
        parts
        and parts[0] not in ("/", "..")
        and all(part not in ("", ".", "..") for part in parts)
        and str(PurePosixPath(path)) == path,
        f"unsafe packet path: {path}",
    )
    return path


def file_bytes(root, relative, *, maximum=128 * 1024 * 1024):
    path = root / relative_path(relative)
    require(
        path.is_file() and not path.is_symlink(), f"missing or linked file: {relative}"
    )
    require(path.stat().st_size <= maximum, f"oversize file: {relative}")
    return path.read_bytes()


def load(root, relative):
    return decode(file_bytes(root, relative), relative)


def check_self_hash(value, field, label):
    require(
        type(value) is dict
        and value.get(field)
        == sha(canonical({key: item for key, item in value.items() if key != field})),
        f"{label}: self hash mismatch",
    )


def git_blob(source, revision, relative):
    relative_path(relative)
    require(re.fullmatch(r"[0-9a-f]{40}", revision) is not None, "invalid Git revision")
    proc = subprocess.run(
        ["git", "-C", str(source), "show", f"{revision}:{relative}"],
        capture_output=True,
        check=False,
    )
    require(proc.returncode == 0, f"committed blob unavailable: {relative}")
    return proc.stdout


def check_inventory(packet):
    inventory = load(packet, "inventory.json")
    require(
        inventory.get("schema_version") == INVENTORY_SCHEMA, "inventory schema mismatch"
    )
    files = inventory.get("files")
    require(type(files) is list, "inventory files missing")
    expected = []
    for path in packet.rglob("*"):
        require(not path.is_symlink(), f"packet contains symbolic link: {path.name}")
        if path.is_dir():
            continue
        require(path.is_file(), f"packet contains non-file: {path.name}")
        relative = path.relative_to(packet).as_posix()
        require(relative != "audit.json", "audit output found inside packet")
        if relative == "inventory.json":
            continue
        data = file_bytes(packet, relative)
        expected.append([relative, len(data), sha(data)])
    expected.sort(key=lambda row: row[0])
    require(same(files, expected), "packet inventory differs from present files")
    require(
        inventory.get("inventory_sha256") == sha(canonical(files)),
        "inventory hash mismatch",
    )
    return inventory


def check_packet_paths(inventory, plan, ordering, shortlist):
    """Close the inventory over exactly the declared search execution paths."""
    expected = {
        "plan.json",
        "runner.json",
        "search/plan.json",
        "search/result.json",
        *(f"inputs/{role}.json" for role in ROLES),
        *(f"search/pool/{row['candidate_id']}.json" for row in plan["pool"]),
    }
    for name, candidate_ids in (
        ("price_order", ["baseline", *shortlist]),
        ("exhaustive_oracle", ["baseline", *ordering]),
    ):
        expected.update(
            {
                f"search/{name}-started.json",
                f"search/{name}-outcome.json",
                f"search/{name}/request.json",
                f"search/{name}/comparison.json",
            }
        )
        expected.update(
            f"search/{name}/{candidate_id}/{filename}"
            for candidate_id in candidate_ids
            for filename in ROW_ARTIFACT_FILES
        )
    actual = {row[0] for row in inventory["files"]}
    require(
        actual == expected and len(inventory["files"]) == len(expected),
        "packet contains undeclared or missing execution files",
    )


def check_artifact(packet, prefix, artifact):
    require(
        type(artifact) is dict and set(artifact) == {"path", "byte_length", "sha256"},
        "row artifact descriptor incomplete",
    )
    relative = prefix + "/" + relative_path(artifact["path"])
    data = file_bytes(packet, relative)
    require(
        type(artifact["byte_length"]) is int and artifact["byte_length"] == len(data),
        f"row artifact byte length differs: {relative}",
    )
    require(artifact["sha256"] == sha(data), f"row artifact hash differs: {relative}")
    return decode(data, relative)


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def quantities_from_model(model):
    nodes = {row["id"]: row["coordinates"] for row in model["nodes"]}
    sections = {row["id"]: row for row in model["sections"]}
    members = []
    for member in model["elements"]:
        section = sections[member["section"]]
        length = math.dist(nodes[member["nodes"][0]], nodes[member["nodes"][1]])
        common = section["bar_area_m2"]
        top, bottom = (
            section.get("top_bar_area_m2", common),
            section.get("bottom_bar_area_m2", common),
        )
        intermediate = sum(
            layer["bar_count"] for layer in section.get("intermediate_steel_layers", [])
        )
        if top == common and bottom == common:
            bar_area = (
                section["top_bar_count"] + section["bottom_bar_count"] + intermediate
            ) * common
        else:
            bar_area = math.fsum(
                (
                    section["top_bar_count"] * top,
                    section["bottom_bar_count"] * bottom,
                    intermediate * common,
                )
            )
        members.append(
            {
                "member_id": member["id"],
                "section_id": member["section"],
                "length_m": length,
                "gross_concrete_volume_m3": section["width_m"]
                * section["depth_m"]
                * length,
                "longitudinal_rebar_volume_m3": bar_area * length,
                "longitudinal_rebar_mass_kg": bar_area * length * 7850.0,
            }
        )
    value = {
        "schema_version": "public-rc-fiber-member-quantities.v1",
        "model_checksum": sha(canonical(model)),
        "scope": QUANTITY_SCOPE,
        "rebar_density_kg_per_m3": 7850.0,
        "concrete_basis": "gross_section_volume_without_rebar_displacement_deduction",
        "reinforcement_basis": "authored_longitudinal_bars_times_member_length",
        "detailed_takeoff": False,
        "excluded_items": EXCLUDED_ITEMS,
        "members": members,
        "totals": {
            name: math.fsum(row[name] for row in members)
            for name in (
                "gross_concrete_volume_m3",
                "longitudinal_rebar_volume_m3",
                "longitudinal_rebar_mass_kg",
            )
        },
    }
    return value | {"quantity_hash": sha(canonical(value))}


def estimate_from_quantities(quantities, prices, price_hash):
    members = [
        {
            "member_id": row["member_id"],
            "concrete": row["gross_concrete_volume_m3"] * prices["concrete_per_m3"],
            "longitudinal_rebar": row["longitudinal_rebar_mass_kg"]
            * prices["rebar_per_kg"],
        }
        for row in quantities["members"]
    ]
    return {
        "scope": QUANTITY_SCOPE,
        "currency": prices["currency"],
        "price_table_hash": price_hash,
        "quantity_hash": quantities["quantity_hash"],
        "members": members,
        "total": math.fsum(
            row["concrete"] + row["longitudinal_rebar"] for row in members
        ),
        "excluded_items": EXCLUDED_ITEMS,
        "verified_quote": False,
        "confirmed_currency_savings": False,
    }


def performance_from_history(result):
    history = result["response_history"]
    require(type(history) is list and history, "original result history absent")
    points = [point for response in history for point in response["fiber_results"]]
    steel = [
        point["material_state"] for point in points if point["material_kind"] == "steel"
    ]
    concrete = [
        point["material_state"]
        for point in points
        if point["material_kind"] == "concrete"
    ]
    return {
        "maximum_translation_m": max(
            math.hypot(node["UX_m"], node["UY_m"], node["UZ_m"])
            for response in history
            for node in response["node_displacements"]
        ),
        "maximum_absolute_fiber_strain": max(abs(point["strain"]) for point in points),
        "terminal_maximum_translation_m": max(
            math.hypot(node["UX_m"], node["UY_m"], node["UZ_m"])
            for node in history[-1]["node_displacements"]
        ),
        "terminal_maximum_absolute_fiber_strain": max(
            abs(point["strain"]) for point in history[-1]["fiber_results"]
        ),
        "maximum_steel_accumulated_plastic_strain": max(
            (state["accumulated_plastic_strain"] for state in steel), default=None
        ),
        "maximum_concrete_tensile_damage": max(
            (state["tensile_damage"] for state in concrete), default=None
        ),
        "maximum_concrete_compressive_damage": max(
            (state["compressive_damage"] for state in concrete), default=None
        ),
        "terminal_load_factor": history[-1]["load_factor"],
        "minimum_load_factor": min(row["load_factor"] for row in history),
        "maximum_load_factor": max(row["load_factor"] for row in history),
        "accepted_epoch_count": len(history),
    }


def expected_result_request(request, *, reuse_line_search_assembly):
    solver = request["solver_config"]
    configuration = {
        "profile": "small-displacement-rc-fiber-direct-control.v1",
        "newton": solver["newton"],
        "control_tolerance_m": solver["control_tolerance_m"],
        "load_factor_coordinate_scale_m": solver["load_factor_coordinate_scale_m"],
        "control_row_weight": "F_reference*residual_tolerance/control_tolerance_m",
        "augmented_coordinates": "[q_free_m,load_factor_coordinate_scale_m*lambda]",
    }
    expected = {
        "targets_m": request["targets_m"],
        "control_global_dof": request["control_global_dof"],
        "configuration": configuration,
        "configuration_hash": sha(canonical(configuration)),
        "allow_reversals": request["allow_reversals"],
        "maximum_reversals": request["maximum_reversals"],
        "maximum_targets": request["maximum_targets"],
        "restart_input_sha256": None,
        "experimental_pin_roller_beam": True,
    }
    if reuse_line_search_assembly:
        expected["line_search_assembly_reuse"] = (
            "rc-control-immediate-line-search-reuse.v1"
        )
    return expected


def indexed_factor(result, request, floor, model):
    targets = request["targets_m"]
    index, target = floor["target_index"], floor["target_control_displacement_m"]
    history, path = result["response_history"], result["path"]
    attempts = path["attempts"]
    require(
        len(history) == len(targets) == len(attempts)
        and path["accepted_target_prefix_m"] == targets,
        "original target history incomplete",
    )
    for i, (attempt, response) in enumerate(zip(attempts, history)):
        require(
            attempt.get("committed") is True
            and attempt.get("target_control_displacement_m") == targets[i]
            and response.get("checkpoint_hash")
            == attempt.get("accepted_checkpoint_hash")
            and response.get("source_step_hash")
            == (attempt.get("step") or {}).get("step_hash"),
            "original accepted target binding mismatch",
        )
    response, attempt = history[index], attempts[index]
    checkpoint = attempt["step"]["accepted_checkpoint"]
    factor = response["load_factor"]
    require(
        finite(factor)
        and attempt["target_control_displacement_m"] == target
        and checkpoint["state_hash"] == attempt["accepted_checkpoint_hash"]
        and checkpoint["parent_state_hash"] == attempt["parent_checkpoint_hash"]
        and response["parent_checkpoint_hash"] == attempt["parent_checkpoint_hash"]
        and checkpoint["load_factor"] == factor,
        "signed load factor differs from accepted target checkpoint",
    )
    control = result["control"]
    dof = request["control_global_dof"]
    require(
        type(dof) is int and 0 <= dof < len(model["nodes"]) * 3,
        "frozen control degree of freedom outside model",
    )
    coordinate = ("UX", "UY", "RZ")[dof % 3]
    node_id = model["nodes"][dof // 3]["id"]
    nodes = [row for row in response["node_displacements"] if row["node_id"] == node_id]
    displacements = checkpoint["global_displacements"]
    tolerance = request["solver_config"]["control_tolerance_m"]
    require(
        control["global_dof"] == dof
        and coordinate in ("UX", "UY")
        and control["component"] == coordinate
        and control["node_id"] == node_id
        and len(nodes) == 1
        and type(displacements) is list
        and 0 <= dof < len(displacements)
        and finite(nodes[0].get(coordinate + "_m"))
        and finite(displacements[dof])
        and abs(nodes[0][coordinate + "_m"] - target) <= tolerance
        and abs(displacements[dof] - target) <= tolerance,
        "force response coordinate differs from authored target",
    )
    return factor


def screens_from_performance(performance, plan, factor):
    limits = dict(plan["history_limits"]) | dict(plan["material_limits"])
    if plan["terminal_limits"] is not None:
        limits.update(
            {"terminal_" + key: value for key, value in plan["terminal_limits"].items()}
        )
    screens = {
        key: {
            "value": performance[key],
            "limit": limit,
            "status": "unavailable"
            if performance[key] is None
            else "pass"
            if performance[key] <= limit
            else "fail",
        }
        for key, limit in limits.items()
    }
    minimum = plan["force_response_floor"]["minimum_load_factor"]
    screens["load_factor_at_target"] = {
        "value": factor,
        "limit": minimum,
        "status": "pass" if factor >= minimum else "fail",
        "comparison": "at_least",
    }
    return screens


def check_provenance(source, packet):
    pre = load(packet, "plan.json")
    runner = load(packet, "runner.json")
    require(
        pre.get("schema_version") == PREDECLARATION_SCHEMA,
        "predeclaration schema mismatch",
    )
    require(
        runner.get("schema_version") == RUNNER_SCHEMA, "runner receipt schema mismatch"
    )
    check_self_hash(pre, "plan_hash", "predeclaration")
    check_self_hash(runner, "report_hash", "runner receipt")
    revision, protocol_commit = pre.get("source_revision"), pre.get("protocol_commit")
    require(
        type(revision) is str and re.fullmatch(r"[0-9a-f]{40}", revision),
        "source revision invalid",
    )
    require(
        type(protocol_commit) is str and re.fullmatch(r"[0-9a-f]{40}", protocol_commit),
        "protocol commit invalid",
    )
    ancestor = subprocess.run(
        [
            "git",
            "-C",
            str(source),
            "merge-base",
            "--is-ancestor",
            protocol_commit,
            revision,
        ],
        capture_output=True,
        check=False,
    )
    require(ancestor.returncode == 0, "protocol commit is not an ancestor of source")
    protocol_path = pre["protocol_path"]
    require(
        type(protocol_path) is str and protocol_path.startswith("examples/research/"),
        "protocol path outside research inputs",
    )
    protocol_bytes = git_blob(source, protocol_commit, protocol_path)
    require(
        protocol_bytes == git_blob(source, revision, protocol_path),
        "source changed committed protocol bytes",
    )
    require(
        pre["protocol_sha256"] == sha(protocol_bytes),
        "protocol committed byte hash mismatch",
    )
    protocol = decode(protocol_bytes, protocol_path)
    require(
        protocol.get("schema_version") == PROTOCOL_SCHEMA, "protocol schema mismatch"
    )
    require(
        pre.get("source_checkout_clean") is True
        and runner.get("clean_source_checkout") is True,
        "clean source checkout receipt missing",
    )
    for key in (
        "source_revision",
        "protocol_commit",
        "protocol_path",
        "protocol_sha256",
        "input_paths",
        "input_sha256",
    ):
        require(same(runner.get(key), pre.get(key)), f"runner {key} binding mismatch")
    refs = protocol.get("inputs")
    paths, digests = pre.get("input_paths"), pre.get("input_sha256")
    require(
        type(refs) is dict
        and type(paths) is dict
        and type(digests) is dict
        and set(refs) == set(paths) == set(digests) == set(ROLES),
        "protocol input roster mismatch",
    )
    inputs = {}
    for role in ROLES:
        ref = refs[role]
        require(
            type(ref) is dict
            and set(ref) == {"path", "sha256"}
            and paths[role] == ref["path"]
            and digests[role] == ref["sha256"],
            f"protocol {role} binding mismatch",
        )
        data = file_bytes(packet, f"inputs/{role}.json")
        require(sha(data) == ref["sha256"], f"packet input changed: {role}")
        require(
            data == git_blob(source, protocol_commit, ref["path"])
            and data == git_blob(source, revision, ref["path"]),
            f"packet {role} differs from committed input",
        )
        inputs[role] = decode(data, f"inputs/{role}.json")
    runner_bytes = git_blob(
        source, revision, "scripts/run_rc_force_floor_prospective.py"
    )
    require(
        pre.get("runner_sha256") == sha(runner_bytes),
        "runner committed byte hash mismatch",
    )
    for key in ("full_analysis_budget", "reuse_line_search_assembly"):
        require(
            same(pre.get(key), protocol.get(key)),
            f"predeclaration {key} differs from protocol",
        )
    require(
        pre.get("search_mode") == "price_order_then_exhaustive_oracle",
        "prospective search mode mismatch",
    )
    require(
        type(pre["full_analysis_budget"]) is int
        and type(pre["reuse_line_search_assembly"]) is bool,
        "invalid frozen budget or reuse flag",
    )
    for key in (
        "independent_physical_validation",
        "learned_policy_used",
        "ai_benefit_claimed",
    ):
        require(runner.get(key) is False, f"runner {key} overclaims evidence")
    return pre, runner, inputs


def normalized_candidate(candidate):
    return {
        "candidate_id": candidate["candidate_id"],
        "changes": [
            {key: value for key, value in change.items() if value is not None}
            for change in candidate["changes"]
        ],
    }


def check_search_plan(packet, pre, inputs):
    plan = load(packet, "search/plan.json")
    require(plan.get("schema_version") == PLAN_SCHEMA, "search plan schema mismatch")
    check_self_hash(plan, "plan_hash", "search plan")
    require(
        plan.get("source_revision") == pre["source_revision"]
        and plan.get("source_revision_is_attestation") is False,
        "search source revision mismatch",
    )
    binding = {
        key: pre[key]
        for key in (
            "protocol_commit",
            "protocol_path",
            "protocol_sha256",
            "input_sha256",
        )
    }
    require(
        same(plan.get("protocol_binding"), binding), "search protocol binding mismatch"
    )
    model, request, experiment, floor_input = (inputs[role] for role in ROLES)
    floor = {
        key: value for key, value in floor_input.items() if key != "schema_version"
    }
    require(
        floor_input.get("schema_version")
        == "experimental-rc-control-force-response-floor.v1"
        and set(floor)
        == {"target_index", "target_control_displacement_m", "minimum_load_factor"},
        "floor input schema or fields mismatch",
    )
    index = floor["target_index"]
    require(
        type(index) is int
        and 0 <= index < len(request["targets_m"])
        and floor["target_control_displacement_m"] == request["targets_m"][index]
        and finite(floor["minimum_load_factor"])
        and floor["minimum_load_factor"] > 0,
        "frozen floor target or limit invalid",
    )
    require(
        same(plan.get("force_response_floor"), floor),
        "search force floor differs from input",
    )
    require(
        same(plan.get("control_request"), request), "search request differs from input"
    )
    require(
        request.get("experimental_pin_roller_beam") is True
        and not request.get("constant_nodal_loads")
        and model["units"]["force"] == "kN"
        and bool(model["loads"]),
        "force-floor loading scope invalid",
    )
    require(
        experiment.get("schema_version") == "rc-fiber-design-experiment.v3",
        "experiment schema mismatch",
    )
    require(
        [normalized_candidate(row) for row in plan["candidates"]]
        == [normalized_candidate(row) for row in experiment["candidates"]],
        "search candidate roster differs from input",
    )
    for plan_key, experiment_key in (
        ("history_limits", "history_limits"),
        ("material_limits", "material_history_limits"),
        ("terminal_limits", "terminal_limits"),
        ("prices", "prices"),
    ):
        declared = experiment.get(experiment_key)
        if plan_key == "prices":
            require(type(declared) is dict, "declared prices missing")
            declared = dict(declared)
            for key in ("concrete_per_m3", "rebar_per_kg"):
                require(finite(declared.get(key)), "declared price invalid")
                declared[key] = float(declared[key])
        elif declared is not None:
            require(
                type(declared) is dict
                and all(finite(value) for value in declared.values()),
                f"declared {plan_key} invalid",
            )
            declared = {key: float(value) for key, value in declared.items()}
        require(
            same(plan.get(plan_key), declared),
            f"search {plan_key} differs from input",
        )
    prices = plan["prices"]
    require(
        finite(prices["concrete_per_m3"])
        and prices["concrete_per_m3"] >= 0
        and finite(prices["rebar_per_kg"])
        and prices["rebar_per_kg"] >= 0,
        "invalid declared synthetic price",
    )
    price_hash = sha(
        canonical({"schema_version": "declared-rc-material-prices.v1", **prices})
    )
    require(plan.get("price_table_hash") == price_hash, "price table hash mismatch")
    require(
        plan.get("full_analysis_budget_including_baseline")
        == pre["full_analysis_budget"]
        and plan.get("line_search_assembly_reuse") is pre["reuse_line_search_assembly"]
        and plan.get("oracle_after_online_arm") is True
        and plan.get("learned_policy_used") is False,
        "search budget or execution mode differs from protocol",
    )
    candidates = experiment["candidates"]
    ids = ["baseline", *(row["candidate_id"] for row in candidates)]
    require(
        len(set(ids)) == len(ids) and 2 <= pre["full_analysis_budget"] <= len(ids),
        "candidate denominator or budget invalid",
    )
    require(
        [row["candidate_id"] for row in plan["pool"]] == ids,
        "pool IDs differ from experiment",
    )
    baseline = load(packet, "search/pool/baseline.json")
    require(same(baseline, model), "baseline pool model differs from committed input")
    require(
        plan["baseline_checksum"] == sha(canonical(baseline)),
        "baseline model checksum mismatch",
    )
    models, estimates = {}, {}
    for pool_row in plan["pool"]:
        candidate_id = pool_row["candidate_id"]
        pool_model = load(packet, f"search/pool/{candidate_id}.json")
        expected_model = deepcopy(baseline)
        if candidate_id != "baseline":
            candidate = next(
                row for row in candidates if row["candidate_id"] == candidate_id
            )
            sections = {row["id"]: row for row in expected_model["sections"]}
            for change in candidate["changes"]:
                require(
                    change["section_id"] in sections,
                    "candidate changes unknown section",
                )
                sections[change["section_id"]].update(
                    {
                        key: value
                        for key, value in change.items()
                        if key != "section_id" and value is not None
                    }
                )
        require(
            same(pool_model, expected_model),
            f"{candidate_id}: pool physical model mismatch",
        )
        descriptor = pool_row["model_artifact"]
        require(
            descriptor
            == {
                "path": f"pool/{candidate_id}.json",
                "byte_length": len(
                    file_bytes(packet, f"search/pool/{candidate_id}.json")
                ),
                "sha256": sha(file_bytes(packet, f"search/pool/{candidate_id}.json")),
            },
            f"{candidate_id}: pool artifact descriptor mismatch",
        )
        checksum = sha(canonical(pool_model))
        require(
            pool_row["model_checksum"] == checksum,
            f"{candidate_id}: model checksum mismatch",
        )
        quantities = quantities_from_model(pool_model)
        estimate = estimate_from_quantities(quantities, prices, price_hash)
        require(
            same(pool_row["quantities"], quantities),
            f"{candidate_id}: quantities differ from model",
        )
        require(
            same(pool_row["material_estimate"], estimate),
            f"{candidate_id}: estimate differs from quantities",
        )
        models[candidate_id], estimates[candidate_id] = pool_model, estimate
    ordering = sorted(
        ids[1:],
        key=lambda candidate_id: (estimates[candidate_id]["total"], candidate_id),
    )
    shortlist = ordering[: pre["full_analysis_budget"] - 1]
    require(
        plan.get("plans")
        == {"price_order": {"ordering": ordering, "shortlist": shortlist}},
        "frozen price ordering or shortlist changed",
    )
    require(
        len({row["model_checksum"] for row in plan["pool"]}) == len(ids),
        "pool contains duplicate physical models",
    )
    return plan, models, estimates, ordering, shortlist


def work_from_rows(rows):
    invocations = [item for row in rows for item in row["invocations"]]
    counts = {}
    for invocation in invocations:
        require(
            invocation.get("status") == "returned"
            and invocation.get("unknown_execution_work") is False
            and type(invocation.get("work")) is dict,
            "original numerical invocation incomplete or work unknown",
        )
        work = invocation["work"]
        for key in (
            "attempted_step_count",
            "known_linear_solve_count",
            "known_newton_iteration_count",
            "unknown_solver_work_attempt_count",
        ):
            value = work.get(key)
            require(
                type(value) is int and value >= 0,
                f"numerical work counter unknown: {key}",
            )
            counts[key] = counts.get(key, 0) + value
        require(
            work["unknown_solver_work_attempt_count"] == 0,
            "solver reports unknown attempted work",
        )
    return {
        "known_counters": counts,
        "unknown_work": False,
        "api_invocation_count": len(invocations),
    }


def check_row(packet, name, row, plan, model, estimate):
    candidate_id = row["candidate_id"]
    prefix = f"search/{name}"
    artifacts = row.get("artifacts")
    require(
        type(artifacts) is dict, f"{name}/{candidate_id}: missing original artifacts"
    )
    required = {
        "model",
        "analysis_started",
        "analysis_outcome",
        "result",
        "checkpoint",
        "verification_started",
        "verification_outcome",
        "verification",
    }
    require(
        set(artifacts) == required,
        f"{name}/{candidate_id}: complete artifact roster required",
    )
    values = {}
    for key in required:
        descriptor = artifacts[key]
        require(
            type(descriptor) is dict,
            f"{name}/{candidate_id}: artifact descriptor invalid: {key}",
        )
        filename = {
            "model": "model.json",
            "analysis_started": "analysis-started.json",
            "analysis_outcome": "analysis-outcome.json",
            "result": "result.json",
            "checkpoint": "checkpoint.json",
            "verification_started": "verification-started.json",
            "verification_outcome": "verification-outcome.json",
            "verification": "verification.json",
        }[key]
        require(
            descriptor.get("path") == f"{candidate_id}/{filename}",
            f"{name}/{candidate_id}: artifact path changed: {key}",
        )
        values[key] = check_artifact(packet, prefix, descriptor)
    require(
        same(values["model"], model),
        f"{name}/{candidate_id}: row model differs from frozen pool",
    )
    require(
        same(row.get("quantities"), quantities_from_model(model)),
        f"{name}/{candidate_id}: row quantities differ from model",
    )
    require(
        same(row.get("material_estimate"), estimate),
        f"{name}/{candidate_id}: row estimate differs from frozen pool",
    )
    invocations = row.get("invocations")
    require(
        type(invocations) is list and len(invocations) == 2,
        f"{name}/{candidate_id}: analysis and replay invocations required",
    )
    for phase, invocation in zip(("analysis", "verification"), invocations):
        require(
            invocation.get("phase") == phase
            and invocation.get("status") == "returned"
            and invocation.get("unknown_execution_work") is False,
            f"{name}/{candidate_id}: {phase} did not return known work",
        )
        require(
            same(values[phase + "_outcome"], invocation)
            and values[phase + "_started"].get("status") == "started"
            and values[phase + "_started"].get("unknown_execution_work") is True,
            f"{name}/{candidate_id}: {phase} invocation receipt mismatch",
        )
    work_from_rows([row])
    result, checkpoint, verification = (
        values[key] for key in ("result", "checkpoint", "verification")
    )
    check_self_hash(result, "result_hash", f"{name}/{candidate_id} result")
    require(
        result.get("contract_pass") is True
        and result.get("model", {}).get("canonical_model_checksum")
        == sha(canonical(model))
        and same(
            result.get("request"),
            expected_result_request(
                plan["control_request"],
                reuse_line_search_assembly=plan["line_search_assembly_reuse"],
            ),
        ),
        f"{name}/{candidate_id}: original result contract or source binding differs",
    )
    require(
        same(result.get("metrics", {}).get("control_work"), invocations[0]["work"])
        and same(
            result.get("path", {}).get("metrics", {}).get("total_work"),
            invocations[0]["work"],
        )
        and invocations[0]["work"]["attempted_step_count"]
        >= len(plan["control_request"]["targets_m"]),
        f"{name}/{candidate_id}: original solver work differs from accepted path",
    )
    checkpoint_bytes = file_bytes(
        packet, prefix + "/" + artifacts["checkpoint"]["path"]
    )
    require(
        result.get("checkpoint")
        == {"sha256": sha(checkpoint_bytes), "byte_length": len(checkpoint_bytes)}
        and type(checkpoint) is dict,
        f"{name}/{candidate_id}: final checkpoint binding mismatch",
    )
    require(
        verification.get("status") == "valid_artifact"
        and all(
            verification.get(key) is True
            for key in (
                "artifact_contract_pass",
                "contract_pass",
                "physical_path_complete",
                "fresh_source_execution_invoked",
                "solver_replay_performed",
            )
        )
        and verification.get("verified_result_hash") == result["result_hash"]
        and verification.get("errors") == []
        and verification.get("unavailable_execution_work") is False
        and same(verification.get("replay_control_work"), invocations[1]["work"])
        and row.get("full_reference_verification_pass") is True
        and row.get("status") == "verified",
        f"{name}/{candidate_id}: full fresh replay incomplete",
    )
    factor = indexed_factor(
        result, plan["control_request"], plan["force_response_floor"], model
    )
    performance = performance_from_history(result)
    performance["load_factor_at_target"] = factor
    screens = screens_from_performance(performance, plan, factor)
    require(
        same(row.get("performance"), performance),
        f"{name}/{candidate_id}: performance differs from original result",
    )
    require(
        same(row.get("screens"), screens),
        f"{name}/{candidate_id}: screens differ from original result",
    )
    eligible = all(screen["status"] == "pass" for screen in screens.values())
    require(
        row.get("selection_eligible") is eligible,
        f"{name}/{candidate_id}: selection eligibility differs from screens",
    )
    return eligible


def check_comparison(packet, name, plan, models, estimates, candidate_ids):
    prefix = f"search/{name}"
    identity = load(packet, prefix + "/request.json")
    report = load(packet, prefix + "/comparison.json")
    require(
        report.get("schema_version") == COMPARISON_SCHEMA,
        f"{name}: comparison schema mismatch",
    )
    check_self_hash(report, "report_hash", f"{name} comparison")
    require(
        report.get("request_hash") == sha(canonical(identity)),
        f"{name}: comparison request hash mismatch",
    )
    for key in (
        "source_revision",
        "baseline_checksum",
        "control_request",
        "force_response_floor",
        "history_limits",
        "material_limits",
        "terminal_limits",
        "prices",
        "price_table_hash",
    ):
        require(
            same(identity.get(key), plan.get(key))
            and same(report.get(key), plan.get(key)),
            f"{name}: {key} differs from frozen plan",
        )
    by_id = {row["candidate_id"]: row for row in plan["candidates"]}
    chosen = [by_id[candidate_id] for candidate_id in candidate_ids[1:]]
    require(
        same(identity.get("candidates"), chosen)
        and same(report.get("candidates"), chosen),
        f"{name}: comparison candidate subset differs from frozen plan",
    )
    require(
        identity.get("schema_version") == COMPARISON_SCHEMA,
        f"{name}: request schema mismatch",
    )
    if plan["line_search_assembly_reuse"]:
        require(
            identity.get("line_search_assembly_reuse")
            == "rc-control-immediate-line-search-reuse.v1",
            f"{name}: line-search reuse request mismatch",
        )
    else:
        require(
            "line_search_assembly_reuse" not in identity,
            f"{name}: unplanned line-search reuse",
        )
    rows = report.get("rows")
    require(
        type(rows) is list
        and all(type(row) is dict for row in rows)
        and [row.get("candidate_id") for row in rows] == candidate_ids,
        f"{name}: complete comparison row order mismatch",
    )
    eligible = {}
    for row in rows:
        candidate_id = row["candidate_id"]
        eligible[candidate_id] = check_row(
            packet, name, row, plan, models[candidate_id], estimates[candidate_id]
        )
    expected_selected = min(
        (candidate_id for candidate_id in candidate_ids if eligible[candidate_id]),
        key=lambda candidate_id: (estimates[candidate_id]["total"], candidate_id),
        default=None,
    )
    require(
        report.get("selected_candidate_id") == expected_selected,
        f"{name}: selected candidate differs from original screens and prices",
    )
    require(
        report.get("candidate_denominator") == len(candidate_ids)
        and report.get("verified_count") == len(candidate_ids)
        and report.get("status") == "complete"
        and report.get("selection_status")
        == (
            "selected"
            if expected_selected is not None
            else "no_verified_feasible_candidate"
        ),
        f"{name}: comparison completion or selection status mismatch",
    )
    return report, eligible


def expected_cost_audit(
    plan, price_report, oracle_report, estimates, price_eligible, oracle_eligible
):
    ids = [row["candidate_id"] for row in plan["pool"]]
    feasible = [candidate_id for candidate_id in ids if oracle_eligible[candidate_id]]
    status = "complete" if feasible else "no_feasible_candidate"
    minimum = min(
        (estimates[candidate_id]["total"] for candidate_id in feasible), default=None
    )
    winners = (
        sorted(
            candidate_id
            for candidate_id in feasible
            if estimates[candidate_id]["total"] == minimum
        )
        if minimum is not None
        else None
    )
    selected = price_report["selected_candidate_id"]
    arm_status = status
    if status == "complete":
        arm_status = (
            "no_verified_selection"
            if selected is None
            else "selection_not_confirmed_by_oracle"
            if not oracle_eligible[selected]
            else "compared"
        )
    selected_estimate = estimates[selected]["total"] if selected is not None else None
    gap = selected_estimate - minimum if arm_status == "compared" else None
    requested = {"baseline", *plan["plans"]["price_order"]["shortlist"]}
    missed = (
        [
            candidate_id
            for candidate_id in ids
            if candidate_id not in requested
            and oracle_eligible[candidate_id]
            and estimates[candidate_id]["total"] < selected_estimate
        ]
        if arm_status == "compared"
        else None
    )
    arm = {
        "status": arm_status,
        "selected_candidate_id": selected,
        "selected_estimate": selected_estimate,
        "selected_minus_pool_minimum_estimate": gap,
        "matches_pool_minimum": None if gap is None else gap == 0,
        "missed_cheaper_feasible_count": None if missed is None else len(missed),
        "missed_cheaper_feasible_candidate_ids": missed,
        "missed_cheaper_false_negative_count": None,
        "missed_cheaper_false_negative_candidate_ids": None,
    }
    first = next(iter(estimates.values()))
    return {
        "schema_version": COST_SCHEMA,
        "status": status,
        "candidate_denominator": len(ids),
        "baseline_included": True,
        "price_table_hash": plan["price_table_hash"],
        "currency": first["currency"],
        "quantity_scope": first["scope"],
        "oracle_comparison_hash": oracle_report["report_hash"],
        "oracle_unverifiable_candidate_ids": [],
        "pool_minimum_feasible_estimate": minimum,
        "pool_minimum_feasible_candidate_ids": winners,
        "arms": {"price_order": arm},
        "global_design_optimality_proved": False,
        "confirmed_currency_savings": False,
        "independent_physical_validation": False,
        "force_response_floor": plan["force_response_floor"],
    }


def audit_contents(source, packet):
    inventory = check_inventory(packet)
    pre, runner, inputs = check_provenance(source, packet)
    plan, models, estimates, ordering, shortlist = check_search_plan(
        packet, pre, inputs
    )
    check_packet_paths(inventory, plan, ordering, shortlist)
    require(
        runner.get("outer_plan_hash") == pre["plan_hash"]
        and runner.get("outer_plan_sha256") == sha(file_bytes(packet, "plan.json"))
        and runner.get("runner_sha256") == pre["runner_sha256"]
        and runner.get("full_analysis_budget") == pre["full_analysis_budget"]
        and runner.get("reuse_line_search_assembly")
        is pre["reuse_line_search_assembly"],
        "runner predeclaration binding mismatch",
    )
    require(
        runner.get("search_plan_hash") == plan["plan_hash"]
        and runner.get("search_plan_sha256")
        == sha(file_bytes(packet, "search/plan.json")),
        "runner search plan binding mismatch",
    )
    ids = [row["candidate_id"] for row in plan["pool"]]
    comparisons = {}
    for name, candidates in (
        ("price_order", ["baseline", *shortlist]),
        ("exhaustive_oracle", ["baseline", *ordering]),
    ):
        started = load(packet, f"search/{name}-started.json")
        outcome = load(packet, f"search/{name}-outcome.json")
        require(
            started.get("status") == "started"
            and started.get("plan_hash") == plan["plan_hash"]
            and started.get("candidate_ids") == candidates
            and started.get("unknown_work_until_outcome") is True,
            f"{name}: frozen start receipt mismatch",
        )
        report, eligible = check_comparison(
            packet, name, plan, models, estimates, candidates
        )
        work = work_from_rows(report["rows"])
        require(
            outcome.get("status") == "completed"
            and outcome.get("comparison_hash") == report["report_hash"]
            and outcome.get("comparison_path") == f"{name}/comparison.json"
            and outcome.get("request_count") == len(candidates)
            and outcome.get("selected_candidate_id") == report["selected_candidate_id"]
            and same(outcome.get("execution_work"), work)
            and outcome.get("unknown_work_until_outcome") is False,
            f"{name}: comparison outcome or work unknown",
        )
        comparisons[name] = (report, eligible, outcome)
    price, price_eligible, price_outcome = comparisons["price_order"]
    oracle, oracle_eligible, oracle_outcome = comparisons["exhaustive_oracle"]
    require(set(oracle_eligible) == set(ids), "oracle candidate coverage incomplete")
    cost = expected_cost_audit(
        plan, price, oracle, estimates, price_eligible, oracle_eligible
    )
    result = load(packet, "search/result.json")
    require(
        result.get("schema_version") == SEARCH_SCHEMA, "search report schema mismatch"
    )
    check_self_hash(result, "report_hash", "search report")
    require(
        runner.get("search_report_hash") == result["report_hash"]
        and runner.get("search_report_sha256")
        == sha(file_bytes(packet, "search/result.json")),
        "runner search report binding mismatch",
    )
    require(
        result.get("source_revision") == pre["source_revision"]
        and result.get("plan_hash") == plan["plan_hash"]
        and same(result.get("force_response_floor"), plan["force_response_floor"])
        and result.get("candidate_denominator") == len(ids)
        and result.get("arms") == {"price_order": price_outcome}
        and result.get("oracle") == oracle_outcome,
        "search result identity or comparison receipt mismatch",
    )
    require(
        same(result.get("candidate_cost_optimality_audit"), cost),
        "V3 cost gap or oracle winner differs from original rows",
    )
    claims = result.get("claims") or {}
    require(
        claims.get("known_pool_cost_optimality_only") is True
        and claims.get("learned_policy_used") is False
        and claims.get("net_ai_savings_proved") is False
        and claims.get("independent_physical_validation") is False
        and claims.get("confirmed_currency_savings") is False,
        "search result overclaims evidence",
    )
    return {
        "source_revision": pre["source_revision"],
        "protocol_commit": pre["protocol_commit"],
        "protocol_sha256": pre["protocol_sha256"],
        "search_plan_hash": plan["plan_hash"],
        "search_report_hash": result["report_hash"],
        "oracle_comparison_hash": oracle["report_hash"],
        "candidate_denominator": len(ids),
        "selected_candidate_id": price["selected_candidate_id"],
        "oracle_selected_candidate_id": oracle["selected_candidate_id"],
        "pool_minimum_feasible_estimate": cost["pool_minimum_feasible_estimate"],
        "selected_minus_pool_minimum_estimate": cost["arms"]["price_order"][
            "selected_minus_pool_minimum_estimate"
        ],
        "cost_audit_status": cost["status"],
    }


def audit_packet(source, packet):
    """Return a bounded report; neither source nor packet is changed."""
    source, packet = Path(source).resolve(), Path(packet).resolve()
    report = {
        "schema_version": AUDIT_SCHEMA,
        "status": "incomplete_or_unverifiable",
        "packet_path": str(packet),
        "violations": [],
        "unknown_execution_work": True,
        "independent_physical_validation": False,
        "confirmed_currency_savings": False,
        "net_ai_savings_proved": False,
    }
    try:
        require(
            packet.is_dir() and source.is_dir(), "source or packet directory missing"
        )
        details = audit_contents(source, packet)
    except (
        AuditError,
        KeyError,
        TypeError,
        IndexError,
        ValueError,
        OSError,
        AttributeError,
        OverflowError,
    ) as error:
        report["violations"].append(str(error))
        return report
    report.update(details)
    report["status"] = "verified_packet_integrity"
    report["unknown_execution_work"] = False
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--packet", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    result = audit_packet(args.source, args.packet)
    data = canonical(result) + b"\n"
    if args.output is None:
        print(data.decode("utf-8"), end="")
    else:
        output = args.output.resolve()
        packet = args.packet.resolve()
        if output == packet or packet in output.parents:
            parser.error("audit output must be outside packet")
        with output.open("xb") as stream:
            stream.write(data)
    return 0 if result["status"] == "verified_packet_integrity" else 1


if __name__ == "__main__":
    raise SystemExit(main())
