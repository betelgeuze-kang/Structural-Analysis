"""Compare already validated public planar artifacts without replay authority.

Only the five terminal SI row groups receive numerical tolerances. Canonical
JSON equality preserves signed zero and is separate from original file bytes;
checkpoint equality compares the supplied original bytes. Neither comparison
performs source validation, checkpoint replay or independent structural V&V.
"""

from __future__ import annotations

from fractions import Fraction
import hashlib
import json
import math
import re
from typing import Any


SI_ROWS = (
    "node_displacements",
    "support_reactions",
    "member_end_forces",
    "section_results",
    "fiber_results",
)
_HASH = re.compile(r"sha256:[0-9a-f]{64}\Z")
_MAX_MISMATCH_PATHS = 32
_MODEL_HASHES = (
    "model_ir_content_hash",
    "model_ir_semantic_hash",
    "model_ir_provenance_hash",
    "canonical_model_checksum",
)
_CHECKPOINT_IDENTITIES = (
    "root_state_hash",
    "terminal_state_hash",
    "chain_hash",
    "terminal_epoch",
    "terminal_load_factor",
)


def _digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _json_bytes(value: Any) -> bytes:
    def validate(item: Any) -> None:
        if type(item) is dict:
            if any(type(key) is not str for key in item):
                raise ValueError("result JSON keys must be strings")
            for child in item.values():
                validate(child)
        elif type(item) is list:
            for child in item:
                validate(child)
        elif type(item) is float:
            if not math.isfinite(item):
                raise ValueError("result JSON numbers must be finite")
        elif item is not None and type(item) not in (str, bool, int):
            raise ValueError("result must contain plain JSON values")

    try:
        validate(value)
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (RecursionError, UnicodeError) as error:
        raise ValueError("result is not bounded valid JSON") from error


def _validate_tolerances(value: dict) -> dict[str, tuple[float, float]]:
    if type(value) is not dict or set(value) != set(SI_ROWS):
        raise ValueError("tolerances must contain exactly the five SI row groups")
    result = {}
    for group in SI_ROWS:
        row = value[group]
        if type(row) is not dict or set(row) != {"absolute", "relative"}:
            raise ValueError(f"{group} requires exactly absolute and relative")
        numbers = []
        for key in ("absolute", "relative"):
            number = row[key]
            try:
                valid = (
                    type(number) in (int, float)
                    and number >= 0
                    and math.isfinite(number)
                )
            except OverflowError:
                valid = False
            if not valid:
                raise ValueError(f"{group}.{key} must be finite and nonnegative")
            numbers.append(float(number))
        result[group] = tuple(numbers)
    return result


def _source(value: dict, side: str, reasons: list[str]) -> dict | None:
    if type(value) is not dict:
        raise ValueError(f"{side} result must be a plain JSON object")
    if (
        value.get("schema_version") != "planar-frame-result.v1"
        or value.get("profile") != "planar_frame_verified_alpha.v1"
    ):
        reasons.append(f"{side}_public_planar_profile_unavailable")
        return None
    source = value.get("result_ir")
    if (
        value.get("status") != "converged"
        or value.get("converged") is not True
        or type(source) is not dict
        or source.get("schema_version") != "unified-nonlinear-frame-result.v1"
        or source.get("profile") != "corotational_connected_frame2d.v1"
        or source.get("status") != "ready"
        or source.get("contract_pass") is not True
    ):
        reasons.append(f"{side}_converged_result_unavailable")
        return None
    return source


def _model_identity(source: dict) -> tuple[str, ...] | None:
    binding = source.get("contract_bindings")
    adapter = binding.get("source_model_ir_adapter") if type(binding) is dict else None
    if type(adapter) is not dict:
        return None
    hashes = tuple(adapter.get(key) for key in _MODEL_HASHES)
    if not all(type(value) is str and _HASH.fullmatch(value) for value in hashes):
        return None
    if (
        source.get("canonical_model_checksum") != hashes[-1]
        or source.get("input_checksum") != hashes[0]
    ):
        return None
    return hashes


def _checkpoint(source: dict | None, data: bytes | None, side: str) -> dict | None:
    if data is not None and type(data) is not bytes:
        raise ValueError(f"{side} checkpoint must be bytes or None")
    descriptor = source.get("checkpoint") if source is not None else None
    if type(descriptor) is not dict or descriptor.get("available") is not True:
        if data is not None:
            raise ValueError(f"{side} checkpoint has no available descriptor")
        return None
    if (
        any(
            type(descriptor.get(key)) is not str or not _HASH.fullmatch(descriptor[key])
            for key in (*_CHECKPOINT_IDENTITIES[:3], "artifact_hash")
        )
        or type(descriptor.get("terminal_epoch")) is not int
        or descriptor["terminal_epoch"] < 1
        or type(descriptor.get("terminal_load_factor")) is not float
        or type(descriptor.get("artifact_byte_length")) is not int
        or descriptor["artifact_byte_length"] < 1
    ):
        raise ValueError(f"{side} checkpoint descriptor is invalid")
    if data is not None and (
        len(data) != descriptor["artifact_byte_length"]
        or _digest(data) != descriptor["artifact_hash"]
    ):
        raise ValueError(f"{side} checkpoint bytes differ from its descriptor")
    return descriptor


def _has_float(value: Any) -> bool:
    if type(value) is float:
        return True
    if type(value) is dict:
        return any(_has_float(child) for child in value.values())
    if type(value) is list:
        return any(_has_float(child) for child in value)
    return False


def _float_difference(a: float, b: float, absolute: float, relative: float):
    difference = abs(a - b)
    threshold = max(abs(a), abs(b)) * relative + absolute
    if math.isfinite(difference) and math.isfinite(threshold):
        return difference <= threshold, difference
    # Finite endpoints can overflow subtraction or tolerance arithmetic. Avoid
    # inf <= inf granting a false match, without rounding/clamping the inputs.
    exact_difference = abs(Fraction(a) - Fraction(b))
    exact_threshold = max(abs(Fraction(a)), abs(Fraction(b))) * Fraction(relative)
    exact_threshold += Fraction(absolute)
    return exact_difference <= exact_threshold, difference


def _group_report(left: Any, right: Any) -> dict:
    return {
        "match": None,
        "left_row_count": len(left) if type(left) is list else None,
        "right_row_count": len(right) if type(right) is list else None,
        "float_leaf_count": 0,
        "exact_leaf_count": 0,
        "mismatch_count": 0,
        "mismatch_paths": [],
        "mismatch_paths_truncated": False,
        "maximum_absolute_difference": None,
        "absolute_difference_overflow": False,
    }


def _compare_group(left: list, right: list, group: str, limits: tuple, row: dict):
    def mismatch(path: str) -> None:
        row["mismatch_count"] += 1
        if len(row["mismatch_paths"]) < _MAX_MISMATCH_PATHS:
            row["mismatch_paths"].append(path)
        else:
            row["mismatch_paths_truncated"] = True

    def compare(a: Any, b: Any, path: str) -> None:
        if type(a) is not type(b):
            mismatch(path)
        elif type(a) is dict:
            for key in sorted(set(a) | set(b)):
                child = path + "/" + key.replace("~", "~0").replace("/", "~1")
                if key not in a or key not in b:
                    mismatch(child)
                else:
                    compare(a[key], b[key], child)
        elif type(a) is list:
            if len(a) != len(b):
                mismatch(path + "/length")
            for index, (first, second) in enumerate(zip(a, b)):
                compare(first, second, f"{path}/{index}")
        elif type(a) is float:
            row["float_leaf_count"] += 1
            close, difference = _float_difference(a, b, *limits)
            if not math.isfinite(difference):
                row["absolute_difference_overflow"] = True
                row["maximum_absolute_difference"] = None
            elif not row["absolute_difference_overflow"]:
                row["maximum_absolute_difference"] = max(
                    row["maximum_absolute_difference"] or 0.0, difference
                )
            if not close:
                mismatch(path)
        else:
            row["exact_leaf_count"] += 1
            if a != b:
                mismatch(path)

    compare(left, right, f"/result_ir/{group}")
    row["match"] = row["mismatch_count"] == 0


def compare_planar_frame_results(
    left: dict,
    right: dict,
    *,
    tolerances: dict,
    left_checkpoint: bytes | None,
    right_checkpoint: bytes | None,
) -> dict:
    """Compare terminal rows from caller-validated same-model public results.

    Invalid tolerances/JSON/checkpoint bindings raise ``ValueError``. Missing
    successful source identities or response groups return an unavailable
    comparison, even if both incomplete payloads happen to be identical.
    """
    limits = _validate_tolerances(tolerances)
    reasons: list[str] = []
    left_source = _source(left, "left", reasons)
    right_source = _source(right, "right", reasons)
    left_json, right_json = _json_bytes(left), _json_bytes(right)
    left_cp = _checkpoint(left_source, left_checkpoint, "left")
    right_cp = _checkpoint(right_source, right_checkpoint, "right")
    groups = {
        group: _group_report(
            left_source.get(group) if left_source else None,
            right_source.get(group) if right_source else None,
        )
        for group in SI_ROWS
    }
    if left_source is not None and right_source is not None:
        left_identity = _model_identity(left_source)
        right_identity = _model_identity(right_source)
        if left_identity is None or right_identity is None:
            reasons.append("source_model_identity_unavailable")
        elif left_identity != right_identity:
            reasons.append("source_model_identity_mismatch")
        for side, source in (("left", left_source), ("right", right_source)):
            for group in SI_ROWS:
                values = source.get(group)
                if (
                    type(values) is not list
                    or not values
                    or any(
                        type(row) is not dict or not _has_float(row) for row in values
                    )
                ):
                    reasons.append(f"{side}_{group}_nonempty_numeric_rows_required")
    if not reasons:
        for group in SI_ROWS:
            _compare_group(
                left_source[group],
                right_source[group],
                group,
                limits[group],
                groups[group],
            )
    checkpoint_identities = {"available": left_cp is not None and right_cp is not None}
    checkpoint_identities.update(
        {
            key + "_equal": (
                type(left_cp[key]) is type(right_cp[key])
                and left_cp[key] == right_cp[key]
                if checkpoint_identities["available"]
                else None
            )
            for key in _CHECKPOINT_IDENTITIES
        }
    )
    return {
        "schema_version": "planar-frame-backend-comparison.v1",
        "comparison_available": not reasons,
        "unavailable_reasons": reasons,
        "physical_si_match": all(row["match"] for row in groups.values())
        if not reasons
        else None,
        "groups": groups,
        "whole_result_json_equal": left_json == right_json,
        "left_result_json_sha256": _digest(left_json),
        "right_result_json_sha256": _digest(right_json),
        "checkpoint_bytes_equal": (
            left_checkpoint == right_checkpoint
            if left_checkpoint is not None and right_checkpoint is not None
            else None
        ),
        "checkpoint_identity_comparison": checkpoint_identities,
        "scope": "terminal_public_si_rows_in_order;exact_checkpoint_bytes_and_declared_identity_only;no_independent_replay",
        "independent_external_vv": False,
        "full_history_float_comparison_performed": False,
    }
