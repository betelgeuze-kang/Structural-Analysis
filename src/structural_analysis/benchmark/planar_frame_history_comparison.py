"""Pure comparison of caller-replayed accepted histories, without solver authority."""

from __future__ import annotations

import math
import re
from typing import Any

from structural_analysis.benchmark.planar_frame_backend_comparison import (
    SI_ROWS,
    _float_difference,
    _has_float,
    _json_bytes,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash


HISTORY_GROUPS = (*SI_ROWS, "material_states")
HISTORY_SCHEMA = "planar-frame-accepted-history.v1"
HISTORY_CLAIM_BOUNDARY = {
    "source_checkpoint_bytes_bound": True,
    "each_transition_reassembled": True,
    "newton_reexecuted": False,
    "independent_external_vv": False,
    "release_eligible": False,
}
_HASH = re.compile(r"sha256:[0-9a-f]{64}\Z")
_BACKENDS = (
    "numpy_linalg_solve_dense",
    "scipy_sparse_spsolve_cpu",
    "scipy_sparse_splu_cpu_exact_1536",
)
_MODEL_KEYS = {
    "model_ir_content_hash",
    "model_ir_semantic_hash",
    "model_ir_provenance_hash",
    "canonical_model_checksum",
}


def _fields(value: Any, names: set[str], path: str) -> None:
    if type(value) is not dict or set(value) != names:
        raise ValueError(f"{path}: exact object fields required")


def _hash(value: Any, path: str) -> None:
    if type(value) is not str or _HASH.fullmatch(value) is None:
        raise ValueError(f"{path}: lowercase sha256 required")


def _integer(value: Any, low: int, high: int | None, path: str) -> None:
    if type(value) is not int or value < low or (high is not None and value > high):
        raise ValueError(f"{path}: integer outside supported range")


def _tolerances(value: Any) -> dict[str, tuple[float, float]]:
    _fields(value, set(HISTORY_GROUPS), "tolerances")
    result = {}
    for name, row in value.items():
        _fields(row, {"absolute", "relative"}, f"tolerances/{name}")
        numbers = []
        for key in ("absolute", "relative"):
            number = row[key]
            try:
                valid = (
                    type(number) in (int, float)
                    and math.isfinite(number)
                    and number >= 0
                )
            except OverflowError:
                valid = False
            if not valid:
                raise ValueError(
                    f"tolerances/{name}/{key}: finite nonnegative number required"
                )
            numbers.append(float(number))
        result[name] = tuple(numbers)
    return result


def _material_rows(value: Any, path: str) -> tuple:
    if type(value) is not list or not value:
        raise ValueError(f"{path}: nonempty material rows required")
    identities = []
    for index, row in enumerate(value):
        at = f"{path}/{index}"
        _fields(
            row,
            {
                "member_id",
                "integration_point_index",
                "fiber_index",
                "fiber_id",
                "material_kind",
                "state",
            },
            at,
        )
        for key in ("member_id", "fiber_id"):
            if type(row[key]) is not str or not row[key]:
                raise ValueError(f"{at}/{key}: nonempty string required")
        for key in ("integration_point_index", "fiber_index"):
            _integer(row[key], 0, None, f"{at}/{key}")
        if row["material_kind"] not in ("steel", "concrete"):
            raise ValueError(f"{at}: unsupported material kind")
        state = row["state"]
        if type(state) is not dict or "state_hash" in state or not _has_float(state):
            raise ValueError(
                f"{at}/state: numeric material state without state_hash required"
            )
        identities.append(
            tuple(
                row[key]
                for key in (
                    "member_id",
                    "integration_point_index",
                    "fiber_index",
                    "fiber_id",
                    "material_kind",
                )
            )
        )
    if len(set(identities)) != len(identities):
        raise ValueError(f"{path}: duplicate material identity")
    return tuple(identities)


def _validate_history(value: Any, side: str) -> bytes:
    encoded = _json_bytes(value)
    _fields(
        value,
        {
            "schema_version",
            "source_result_hash",
            "model_identity",
            "configuration",
            "checkpoint_identity",
            "root",
            "steps",
            "history_hash",
            "claim_boundary",
        },
        side,
    )
    if value["schema_version"] != HISTORY_SCHEMA:
        raise ValueError(f"{side}: unsupported history schema")
    _hash(value["source_result_hash"], f"{side}/source_result_hash")
    _hash(value["history_hash"], f"{side}/history_hash")
    if value["history_hash"] != canonical_hash(
        {k: v for k, v in value.items() if k != "history_hash"}
    ):
        raise ValueError(f"{side}: history hash mismatch")
    if _json_bytes(value["claim_boundary"]) != _json_bytes(HISTORY_CLAIM_BOUNDARY):
        raise ValueError(f"{side}: claim boundary mismatch")
    _fields(value["model_identity"], _MODEL_KEYS, f"{side}/model_identity")
    for key, item in value["model_identity"].items():
        _hash(item, f"{side}/model_identity/{key}")
    config = value["configuration"]
    _fields(
        config,
        {
            "control",
            "load_steps",
            "residual_tolerance",
            "increment_tolerance_m",
            "maximum_iterations",
            "matrix_backend",
        },
        f"{side}/configuration",
    )
    if config["control"] != "load_control" or config["matrix_backend"] not in _BACKENDS:
        raise ValueError(f"{side}: unsupported configuration")
    _integer(config["load_steps"], 2, 64, f"{side}/configuration/load_steps")
    _integer(
        config["maximum_iterations"], 1, 200, f"{side}/configuration/maximum_iterations"
    )
    for key in ("residual_tolerance", "increment_tolerance_m"):
        number = config[key]
        try:
            valid = (
                type(number) in (int, float) and math.isfinite(number) and number > 0
            )
        except OverflowError:
            valid = False
        if not valid:
            raise ValueError(
                f"{side}/configuration/{key}: finite positive number required"
            )
    checkpoint = value["checkpoint_identity"]
    _fields(
        checkpoint,
        {
            "available",
            "storage_profile",
            "chain_hash",
            "artifact_hash",
            "artifact_byte_length",
            "root_state_hash",
            "terminal_state_hash",
            "terminal_epoch",
            "terminal_load_factor",
            "complete_ancestry_included",
            "prefix_replay_required",
        },
        f"{side}/checkpoint_identity",
    )
    if (
        any(
            checkpoint[key] is not True
            for key in (
                "available",
                "complete_ancestry_included",
                "prefix_replay_required",
            )
        )
        or checkpoint["storage_profile"]
        != "canonical-signed-zero-preserving-utf8-json.v1"
    ):
        raise ValueError(f"{side}: complete canonical checkpoint descriptor required")
    for key in (
        "chain_hash",
        "artifact_hash",
        "root_state_hash",
        "terminal_state_hash",
    ):
        _hash(checkpoint[key], f"{side}/checkpoint_identity/{key}")
    _integer(
        checkpoint["artifact_byte_length"],
        1,
        None,
        f"{side}/checkpoint_identity/artifact_byte_length",
    )
    _integer(
        checkpoint["terminal_epoch"],
        2,
        64,
        f"{side}/checkpoint_identity/terminal_epoch",
    )
    if (
        checkpoint["terminal_epoch"] != config["load_steps"]
        or type(checkpoint["terminal_load_factor"]) is not float
        or checkpoint["terminal_load_factor"] != 1.0
    ):
        raise ValueError(
            f"{side}: terminal checkpoint differs from full configured path"
        )
    root = value["root"]
    _fields(
        root,
        {
            "epoch",
            "step_index",
            "load_factor",
            "state_hash",
            "global_displacements",
            "material_states",
        },
        f"{side}/root",
    )
    if (
        type(root["epoch"]) is not int
        or root["epoch"] != 0
        or type(root["step_index"]) is not int
        or root["step_index"] != 0
        or type(root["load_factor"]) is not float
        or root["load_factor"] != 0.0
    ):
        raise ValueError(f"{side}: exact genesis indices and load required")
    _hash(root["state_hash"], f"{side}/root/state_hash")
    if root["state_hash"] != checkpoint["root_state_hash"]:
        raise ValueError(f"{side}: root state binding mismatch")
    coordinates = root["global_displacements"]
    if (
        type(coordinates) is not list
        or not coordinates
        or len(coordinates) % 3
        or any(type(x) is not float for x in coordinates)
    ):
        raise ValueError(f"{side}: complete float three-DOF root coordinates required")
    material_order = _material_rows(
        root["material_states"], f"{side}/root/material_states"
    )
    steps = value["steps"]
    if type(steps) is not list or len(steps) != config["load_steps"]:
        raise ValueError(f"{side}: every configured accepted step required")
    previous_hash = root["state_hash"]
    group_counts = None
    for index, step in enumerate(steps, 1):
        at = f"{side}/steps/{index - 1}"
        _fields(
            step,
            {
                "epoch",
                "step_index",
                "load_factor",
                "parent_state_hash",
                "state_hash",
                "si_rows",
                "material_states",
            },
            at,
        )
        if (
            type(step["epoch"]) is not int
            or step["epoch"] != index
            or type(step["step_index"]) is not int
            or step["step_index"] != index
            or type(step["load_factor"]) is not float
            or step["load_factor"] != index / config["load_steps"]
        ):
            raise ValueError(f"{at}: exact full accepted schedule required")
        _hash(step["state_hash"], f"{at}/state_hash")
        if step["parent_state_hash"] != previous_hash:
            raise ValueError(f"{at}: preceding accepted parent binding mismatch")
        previous_hash = step["state_hash"]
        _fields(step["si_rows"], set(SI_ROWS), f"{at}/si_rows")
        for group, rows in step["si_rows"].items():
            if (
                type(rows) is not list
                or not rows
                or any(type(row) is not dict or not _has_float(row) for row in rows)
            ):
                raise ValueError(f"{at}/{group}: nonempty numeric rows required")
        counts = tuple(len(step["si_rows"][group]) for group in SI_ROWS)
        if counts[0] != len(coordinates) // 3 or (
            group_counts is not None and counts != group_counts
        ):
            raise ValueError(f"{at}: response row coverage changed")
        group_counts = counts
        if (
            _material_rows(step["material_states"], f"{at}/material_states")
            != material_order
        ):
            raise ValueError(f"{at}: material identity order changed")
    if previous_hash != checkpoint["terminal_state_hash"]:
        raise ValueError(f"{side}: terminal state binding mismatch")
    return encoded


def _group() -> dict:
    return {
        "match": None,
        "float_leaf_count": 0,
        "exact_leaf_count": 0,
        "mismatch_count": 0,
        "mismatch_paths": [],
        "mismatch_paths_truncated": False,
        "maximum_absolute_difference": None,
        "absolute_difference_overflow": False,
    }


def _compare(left: Any, right: Any, path: str, limits: tuple, report: dict) -> bool:
    before = report["mismatch_count"]

    def mismatch(at: str) -> None:
        report["mismatch_count"] += 1
        if len(report["mismatch_paths"]) < 32:
            report["mismatch_paths"].append(at)
        else:
            report["mismatch_paths_truncated"] = True

    def walk(a: Any, b: Any, at: str) -> None:
        if type(a) is not type(b):
            mismatch(at)
        elif type(a) is dict:
            for key in sorted(set(a) | set(b)):
                child = at + "/" + key.replace("~", "~0").replace("/", "~1")
                if key not in a or key not in b:
                    mismatch(child)
                else:
                    walk(a[key], b[key], child)
        elif type(a) is list:
            if len(a) != len(b):
                mismatch(at + "/length")
            for index, (first, second) in enumerate(zip(a, b)):
                walk(first, second, f"{at}/{index}")
        elif type(a) is float:
            report["float_leaf_count"] += 1
            close, difference = _float_difference(a, b, *limits)
            if not math.isfinite(difference):
                report["absolute_difference_overflow"] = True
                report["maximum_absolute_difference"] = None
            elif not report["absolute_difference_overflow"]:
                report["maximum_absolute_difference"] = max(
                    report["maximum_absolute_difference"] or 0.0, difference
                )
            if not close:
                mismatch(at)
        else:
            report["exact_leaf_count"] += 1
            if a != b:
                mismatch(at)

    walk(left, right, path)
    report["match"] = report["mismatch_count"] == 0
    return report["mismatch_count"] == before


def compare_planar_frame_histories(
    left: dict, right: dict, *, tolerances: dict
) -> dict:
    """Compare complete caller-replayed histories; never replay or infer authority.

    Malformed histories and tolerances raise ValueError. Individually valid
    histories with differing model/configuration domains return unavailable.
    Floating material states receive their own tolerance; all other JSON leaf
    types, identities, order and key membership remain exact. State hashes and
    artifact identities are reported separately from the numerical comparison.
    """
    limits = _tolerances(tolerances)
    left_bytes = _validate_history(left, "left")
    right_bytes = _validate_history(right, "right")
    reasons = []
    if left["model_identity"] != right["model_identity"]:
        reasons.append("model_identity_mismatch")
    configs = [
        {k: v for k, v in row["configuration"].items() if k != "matrix_backend"}
        for row in (left, right)
    ]
    if _json_bytes(configs[0]) != _json_bytes(configs[1]):
        reasons.append("configuration_except_backend_mismatch")
    groups = {name: _group() for name in HISTORY_GROUPS}
    root_comparison = {
        "match": None,
        "node_displacements_match": None,
        "material_states_match": None,
    }
    step_comparisons = []
    if not reasons:
        for group, key in (
            ("node_displacements", "global_displacements"),
            ("material_states", "material_states"),
        ):
            root_comparison[group + "_match"] = _compare(
                left["root"][key],
                right["root"][key],
                "/root/" + key,
                limits[group],
                groups[group],
            )
        root_comparison["match"] = (
            root_comparison["node_displacements_match"]
            and root_comparison["material_states_match"]
        )
        for index, (first, second) in enumerate(
            zip(left["steps"], right["steps"], strict=True)
        ):
            compared = {}
            for group in HISTORY_GROUPS:
                material = group == "material_states"
                a, b = (
                    (first[group], second[group])
                    if material
                    else (first["si_rows"][group], second["si_rows"][group])
                )
                path = f"/steps/{index}/" + (group if material else "si_rows/" + group)
                compared[group] = _compare(a, b, path, limits[group], groups[group])
            step_comparisons.append(
                {
                    "epoch": index + 1,
                    "load_factor": first["load_factor"],
                    "match": all(compared.values()),
                    "groups": compared,
                }
            )
    identities = {
        "source_result_hash_equal": left["source_result_hash"]
        == right["source_result_hash"],
        "history_hash_equal": left["history_hash"] == right["history_hash"],
        **{
            key + "_equal": left["checkpoint_identity"][key]
            == right["checkpoint_identity"][key]
            for key in (
                "artifact_hash",
                "chain_hash",
                "root_state_hash",
                "terminal_state_hash",
            )
        },
        "steps": [
            {
                "epoch": a["epoch"],
                "state_hash_equal": a["state_hash"] == b["state_hash"],
                "parent_state_hash_equal": a["parent_state_hash"]
                == b["parent_state_hash"],
            }
            for a, b in zip(left["steps"], right["steps"])
        ],
    }
    return {
        "schema_version": "planar-frame-history-comparison.v1",
        "comparison_available": not reasons,
        "unavailable_reasons": reasons,
        "full_history_match": all(row["match"] for row in groups.values())
        if not reasons
        else None,
        "full_history_float_comparison_performed": not reasons,
        "groups": groups,
        "root_comparison": root_comparison,
        "step_counts": {
            "left": len(left["steps"]),
            "right": len(right["steps"]),
            "compared": len(step_comparisons),
        },
        "step_comparisons": step_comparisons,
        "identity_comparison": identities,
        "whole_history_json_equal": left_bytes == right_bytes,
        "checkpoint_bytes_comparison_performed": False,
        "numerical_match_requires_hash_equality": False,
        "scope": "genesis_displacements_and_material_states_plus_every_accepted_step_si_and_material_state;caller_owns_source_checkpoint_and_transition_replay_validation",
        "independent_external_vv": False,
        "release_eligible": False,
    }
