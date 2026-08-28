#!/usr/bin/env python3
"""Build the fail-closed 60-case Native Frame Alpha PM-1 inventory."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from pathlib import PurePosixPath
import sys
from typing import Any

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSIONS = {
    "structural-native-frame3d-modelir-parity-pack.v2": (
        "native-frame3d-reference-inventory.v2",
        Path(
            "src/structural_analysis/schemas/native_frame3d_modelir_parity_pack_v2.schema.json"
        ),
        Path(
            "src/structural_analysis/schemas/native_frame3d_reference_inventory_v2.schema.json"
        ),
    ),
    "structural-native-frame3d-modelir-parity-pack.v3": (
        "native-frame3d-reference-inventory.v3",
        Path(
            "src/structural_analysis/schemas/native_frame3d_modelir_parity_pack_v3.schema.json"
        ),
        Path(
            "src/structural_analysis/schemas/native_frame3d_reference_inventory_v3.schema.json"
        ),
    ),
    "structural-native-frame3d-modelir-parity-pack.v4": (
        "native-frame3d-reference-inventory.v4",
        Path(
            "src/structural_analysis/schemas/native_frame3d_modelir_parity_pack_v4.schema.json"
        ),
        Path(
            "src/structural_analysis/schemas/native_frame3d_reference_inventory_v4.schema.json"
        ),
    ),
}

FAMILIES: dict[str, tuple[str, ...]] = {
    "basic_response": (
        "basic_axial_tension",
        "basic_axial_compression",
        "basic_torsion",
        "basic_strong_axis_bending",
        "basic_weak_axis_bending",
        "basic_biaxial_bending",
        "basic_transverse_shear_y",
        "basic_transverse_shear_z",
        "two_member_spatial_chain",
        "planar_portal_multi_support",
        "alpha_upper_moment_frame",
        "alpha_upper_braced_frame",
    ),
    "orientation_local_axis": (
        "rotated_offset_mixed_load",
        "spatial_corner_roll_offset",
        "orientation_roll_quarter_turn",
        "orientation_skew_xy",
        "orientation_skew_xyz",
        "orientation_reversed_vertical",
        "alpha_upper_irregular_spatial",
        "orientation_mixed_roll_chain",
    ),
    "member_load_self_weight": (
        "continuous_line_multiple_support",
        "member_load_uniform_qx",
        "member_load_uniform_qy",
        "member_load_uniform_qz",
        "member_load_uniform_combined",
        "self_weight_global_x",
        "self_weight_global_y",
        "self_weight_global_z",
        "self_weight_skew_gravity",
        "member_load_multi_member_distribution",
    ),
    "release_rigid_offset": (
        "released_uniform_member_load",
        "release_i_rx",
        "release_i_ry",
        "release_i_rz",
        "release_j_rx",
        "release_j_ry",
        "release_j_rz",
        "rigid_offset_i_j",
        "alpha_upper_multiple_support",
        "alpha_upper_mixed_feature",
    ),
    "load_combination": (
        "nested_linear_combination",
        "combination_positive_factors",
        "combination_negative_factor",
        "combination_zero_factor",
        "combination_repeated_pattern",
        "combination_three_level_nested",
        "combination_self_weight_member_load",
        "combination_multi_member_mixed",
    ),
    "negative_metamorphic": (
        "metamorphic_node_renumbering",
        "metamorphic_member_ordering",
        "metamorphic_coordinate_rotation",
        "metamorphic_unit_conversion",
        "metamorphic_load_scaling",
        "metamorphic_member_direction_reversal",
        "metamorphic_symmetry",
        "metamorphic_case_replay_determinism",
        "negative_duplicate_stable_id",
        "negative_unknown_field",
        "negative_cyclic_combination",
        "negative_singular_model",
    ),
}

ALPHA_UPPER_ENVELOPE = (
    "alpha_upper_moment_frame",
    "alpha_upper_braced_frame",
    "alpha_upper_irregular_spatial",
    "alpha_upper_multiple_support",
    "alpha_upper_mixed_feature",
)

EXPECTED_PARITY_CASE_IDS_V2 = (
    "rotated_offset_mixed_load",
    "released_uniform_member_load",
    "nested_linear_combination",
    "two_member_spatial_chain",
    "planar_portal_multi_support",
    "spatial_corner_roll_offset",
    "continuous_line_multiple_support",
)
EXPECTED_PARITY_CASE_IDS_V3 = EXPECTED_PARITY_CASE_IDS_V2 + ALPHA_UPPER_ENVELOPE
EXPECTED_PARITY_CASE_IDS_V4 = (
    EXPECTED_PARITY_CASE_IDS_V3
    + FAMILIES["basic_response"][:8]
    + FAMILIES["negative_metamorphic"]
)


def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _reject_duplicate_object_pairs(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def _reject_nonfinite_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number is forbidden: {value}")


def _load_json(path: Path) -> dict[str, Any]:
    if path.is_symlink():
        raise ValueError(f"symlink JSON input is forbidden: {path}")
    if not path.is_file():
        raise ValueError(f"regular JSON file required: {path}")
    payload = json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=_reject_duplicate_object_pairs,
        parse_constant=_reject_nonfinite_constant,
    )
    if not isinstance(payload, dict):
        raise ValueError(f"JSON object required: {path}")
    return payload


def _zero_sha256_paths(value: Any, path: str = "$") -> list[str]:
    zero_hash = "sha256:" + "0" * 64
    if value == zero_hash:
        return [path]
    if isinstance(value, dict):
        return [
            nested
            for key, item in value.items()
            for nested in _zero_sha256_paths(item, f"{path}.{key}")
        ]
    if isinstance(value, list):
        return [
            nested
            for index, item in enumerate(value)
            for nested in _zero_sha256_paths(item, f"{path}[{index}]")
        ]
    return []


def _read_regular_file(path: Path, *, label: str) -> bytes:
    absolute = path.absolute()
    cursor = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        cursor /= part
        if cursor.is_symlink():
            raise ValueError(f"{label} symlink input is forbidden: {path}")
    if not path.is_file():
        raise ValueError(f"{label} regular file required: {path}")
    return path.read_bytes()


def _current_repo_file(path_value: str) -> Path:
    if "\\" in path_value:
        raise ValueError(
            f"current source path uses a forbidden backslash: {path_value}"
        )
    relative = PurePosixPath(path_value)
    if (
        relative.is_absolute()
        or relative.as_posix() != path_value
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise ValueError(
            f"current source path is not canonical repo-relative: {path_value}"
        )
    candidate = ROOT
    for part in relative.parts:
        candidate /= part
        if candidate.is_symlink():
            raise ValueError(f"current source path contains a symlink: {path_value}")
    try:
        candidate.resolve(strict=False).relative_to(ROOT.resolve())
    except ValueError as error:
        raise ValueError(
            f"current source path escapes repository: {path_value}"
        ) from error
    if not candidate.is_file():
        raise ValueError(f"current source regular file required: {path_value}")
    return candidate


def _validate_current_receipt_bindings(
    parity: dict[str, Any],
    *,
    native_cli_path: Path,
) -> None:
    zero_hash_paths = _zero_sha256_paths(parity)
    if zero_hash_paths:
        raise ValueError(
            "zero SHA-256 evidence digest is forbidden: " + ", ".join(zero_hash_paths)
        )

    native_cli_bytes = _read_regular_file(native_cli_path, label="native CLI")
    observed_native_hash = _sha256_bytes(native_cli_bytes)
    if parity.get("native_cli_sha256") != observed_native_hash:
        raise ValueError("parity receipt native CLI hash does not match current binary")

    source_rows = parity.get("reference_source_hashes")
    if not isinstance(source_rows, list):
        raise ValueError("parity receipt current source hash rows are required")
    for row in source_rows:
        if not isinstance(row, dict):
            raise ValueError("parity receipt current source hash row must be an object")
        path_value = row.get("path")
        if not isinstance(path_value, str):
            raise ValueError("parity receipt current source path must be a string")
        current_path = _current_repo_file(path_value)
        observed_source_hash = _sha256_bytes(current_path.read_bytes())
        if row.get("content_hash") != observed_source_hash:
            raise ValueError(
                f"parity receipt source hash does not match current file: {path_value}"
            )


def build_inventory(
    parity_receipt_path: Path,
    *,
    native_cli_path: Path,
) -> dict[str, Any]:
    parity_bytes = _read_regular_file(parity_receipt_path, label="parity receipt")
    parity = json.loads(
        parity_bytes,
        object_pairs_hook=_reject_duplicate_object_pairs,
        parse_constant=_reject_nonfinite_constant,
    )
    if not isinstance(parity, dict):
        raise ValueError("parity receipt JSON root must be an object")
    parity_schema_version = parity.get("schema_version")
    try:
        schema_version, parity_schema_path, schema_path = SCHEMA_VERSIONS[
            parity_schema_version
        ]
    except (KeyError, TypeError) as error:
        raise ValueError(
            "expanded v2, alpha-upper v3, or PM-1 core v4 parity receipt required"
        ) from error
    parity_schema = _load_json(ROOT / parity_schema_path)
    Draft202012Validator(parity_schema).validate(parity)
    _validate_current_receipt_bindings(parity, native_cli_path=native_cli_path)
    expected_case_ids = {
        "structural-native-frame3d-modelir-parity-pack.v2": EXPECTED_PARITY_CASE_IDS_V2,
        "structural-native-frame3d-modelir-parity-pack.v3": EXPECTED_PARITY_CASE_IDS_V3,
        "structural-native-frame3d-modelir-parity-pack.v4": EXPECTED_PARITY_CASE_IDS_V4,
    }[parity_schema_version]
    is_v4 = parity_schema_version.endswith(".v4")

    family_by_case = {
        case_id: family for family, case_ids in FAMILIES.items() for case_id in case_ids
    }
    if len(family_by_case) != 60:
        raise ValueError("PM-1 inventory must contain 60 unique stable case ids")
    parity_case_ids = [row["case_id"] for row in parity["cases"]]
    if len(parity_case_ids) != len(set(parity_case_ids)):
        raise ValueError("expanded v2 parity receipt contains duplicate case ids")
    if set(parity_case_ids) != set(expected_case_ids):
        raise ValueError("parity receipt case set mismatch")
    verified = {row["case_id"]: row for row in parity["cases"]}
    if not set(verified) <= set(family_by_case):
        raise ValueError("parity receipt contains a case outside the PM-1 inventory")

    cases: list[dict[str, Any]] = []
    for family, case_ids in FAMILIES.items():
        for case_id in case_ids:
            receipt = verified.get(case_id)
            cases.append(
                {
                    "case_id": case_id,
                    "primary_family": family,
                    "execution_status": "verified" if receipt else "planned",
                    "credit_eligible": receipt is not None,
                    "evidence": (
                        (
                            {
                                "verification_kind": receipt["verification_kind"],
                                "receipt_row_sha256": _sha256_bytes(
                                    _canonical_bytes(receipt)
                                ),
                            }
                            if is_v4
                            else {
                                "model_content_hash": receipt["model_content_hash"],
                                "model_semantic_hash": receipt["model_semantic_hash"],
                                "model_provenance_hash": receipt[
                                    "model_provenance_hash"
                                ],
                                "result_hash": receipt["result_hash"],
                                "python_reference_hash": receipt[
                                    "python_reference_hash"
                                ],
                            }
                        )
                        if receipt
                        else None
                    ),
                }
            )

    verified_count = len(verified)
    upper_verified = sum(case_id in verified for case_id in ALPHA_UPPER_ENVELOPE)
    payload = {
        "schema_version": schema_version,
        "status": "complete" if verified_count == 60 else "partial",
        "target_case_count": 60,
        "verified_case_count": verified_count,
        "remaining_case_count": 60 - verified_count,
        "family_targets": {
            family: len(case_ids) for family, case_ids in FAMILIES.items()
        },
        **(
            {
                "family_verified_counts": {
                    family: sum(case_id in verified for case_id in case_ids)
                    for family, case_ids in FAMILIES.items()
                },
                "verification_kind_counts": {
                    kind: sum(
                        receipt["verification_kind"] == kind
                        for receipt in verified.values()
                    )
                    for kind in (
                        "numerical_differential",
                        "metamorphic_invariance",
                        "fail_closed_negative",
                    )
                },
            }
            if is_v4
            else {}
        ),
        "parity_receipt": {
            "schema_version": parity["schema_version"],
            "sha256": _sha256_bytes(parity_bytes),
        },
        "alpha_upper_envelope": {
            "target_case_count": 5,
            "verified_case_count": upper_verified,
            "case_ids": list(ALPHA_UPPER_ENVELOPE),
            "scale_claim": "bounded_alpha_upper_envelope_not_industry_medium_scale",
        },
        "cases": cases,
        "authority": {
            "implementation_verification": "partial_bounded_cross_implementation",
            "commercial_code_comparison": "not_evaluated",
            "physical_validation": "not_established",
            "engineering_design": "not_authoritative",
            "release_readiness": "not_authoritative",
        },
        "claim_boundary": (
            "thirty_two_of_sixty_linear_frame_alpha_cases_verified_basic_twelve_of_"
            "twelve_negative_metamorphic_twelve_of_twelve_alpha_upper_five_of_five_"
            "not_industry_medium_no_modal_buckling_commercial_or_physical_validation_credit"
            if is_v4
            else "twelve_of_sixty_linear_frame_alpha_cases_verified_alpha_upper_five_of_five_"
            "not_industry_medium_no_modal_buckling_commercial_or_physical_validation_credit"
            if parity_schema_version.endswith(".v3")
            else "seven_of_sixty_linear_frame_alpha_cases_verified_no_modal_buckling_"
            "commercial_or_physical_validation_credit"
        ),
    }
    schema = _load_json(ROOT / schema_path)
    Draft202012Validator(schema).validate(payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parity-receipt", type=Path, required=True)
    parser.add_argument("--native-cli", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    payload = build_inventory(
        args.parity_receipt,
        native_cli_path=args.native_cli,
    )
    encoded = (
        json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")
    if args.output is None:
        sys.stdout.buffer.write(encoded)
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
