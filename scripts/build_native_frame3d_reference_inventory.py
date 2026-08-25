#!/usr/bin/env python3
"""Build the fail-closed 60-case Native Frame Alpha PM-1 inventory."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "native-frame3d-reference-inventory.v2"
PARITY_SCHEMA_VERSION = "structural-native-frame3d-modelir-parity-pack.v2"
SCHEMA_PATH = Path(
    "src/structural_analysis/schemas/native_frame3d_reference_inventory_v2.schema.json"
)
PARITY_SCHEMA_PATH = Path(
    "src/structural_analysis/schemas/native_frame3d_modelir_parity_pack_v2.schema.json"
)

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

EXPECTED_PARITY_CASE_IDS = (
    "rotated_offset_mixed_load",
    "released_uniform_member_load",
    "nested_linear_combination",
    "two_member_spatial_chain",
    "planar_portal_multi_support",
    "spatial_corner_roll_offset",
    "continuous_line_multiple_support",
)


def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON object required: {path}")
    return payload


def build_inventory(parity_receipt_path: Path) -> dict[str, Any]:
    parity_bytes = parity_receipt_path.read_bytes()
    parity = json.loads(parity_bytes)
    parity_schema = _load_json(ROOT / PARITY_SCHEMA_PATH)
    Draft202012Validator(parity_schema).validate(parity)
    if parity["schema_version"] != PARITY_SCHEMA_VERSION:
        raise ValueError("expanded v2 parity receipt required")

    family_by_case = {
        case_id: family
        for family, case_ids in FAMILIES.items()
        for case_id in case_ids
    }
    if len(family_by_case) != 60:
        raise ValueError("PM-1 inventory must contain 60 unique stable case ids")
    parity_case_ids = [row["case_id"] for row in parity["cases"]]
    if len(parity_case_ids) != len(set(parity_case_ids)):
        raise ValueError("expanded v2 parity receipt contains duplicate case ids")
    if set(parity_case_ids) != set(EXPECTED_PARITY_CASE_IDS):
        raise ValueError("expanded v2 parity receipt case set mismatch")
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
                        {
                            "model_content_hash": receipt["model_content_hash"],
                            "model_semantic_hash": receipt["model_semantic_hash"],
                            "model_provenance_hash": receipt["model_provenance_hash"],
                            "result_hash": receipt["result_hash"],
                            "python_reference_hash": receipt["python_reference_hash"],
                        }
                        if receipt
                        else None
                    ),
                }
            )

    verified_count = len(verified)
    upper_verified = sum(case_id in verified for case_id in ALPHA_UPPER_ENVELOPE)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "status": "complete" if verified_count == 60 else "partial",
        "target_case_count": 60,
        "verified_case_count": verified_count,
        "remaining_case_count": 60 - verified_count,
        "family_targets": {
            family: len(case_ids) for family, case_ids in FAMILIES.items()
        },
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
            "seven_of_sixty_linear_frame_alpha_cases_verified_no_modal_buckling_"
            "commercial_or_physical_validation_credit"
        ),
    }
    schema = _load_json(ROOT / SCHEMA_PATH)
    Draft202012Validator(schema).validate(payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parity-receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    payload = build_inventory(args.parity_receipt.resolve())
    encoded = (
        json.dumps(payload, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))
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
