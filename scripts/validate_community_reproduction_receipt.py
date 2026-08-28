#!/usr/bin/env python3
"""Validate one bounded community reproduction receipt."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Sequence

from jsonschema import Draft202012Validator, FormatChecker, SchemaError


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCHEMA = ROOT / "schemas/community-reproduction-receipt.v1.schema.json"
OFFICIAL_SCHEMA_ID = (
    "https://example.invalid/structural-analysis/"
    "community-reproduction-receipt.v1.schema.json"
)
OFFICIAL_SCHEMA_VERSION = "community-reproduction-receipt.v1"
OFFICIAL_CLAIM_BOUNDARY = (
    "Receipt validation records one reproduction only and grants no product, "
    "design, hardware, external-V&V, public-support, or release authority."
)
OFFICIAL_SCHEMA_CANONICAL_SHA256 = (
    "d71e0b4b319d393b0dd83089ffa015c0e2d94c77b677dc628ec3020564099698"
)


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


def _nonfinite_paths(value: Any, path: str = "$") -> list[str]:
    if isinstance(value, float) and not math.isfinite(value):
        return [path]
    if isinstance(value, dict):
        return [
            nested
            for key, item in value.items()
            for nested in _nonfinite_paths(item, f"{path}.{key}")
        ]
    if isinstance(value, list):
        return [
            nested
            for index, item in enumerate(value)
            for nested in _nonfinite_paths(item, f"{path}[{index}]")
        ]
    return []


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _load_object(path: Path) -> dict[str, Any]:
    payload = json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=_reject_duplicate_object_pairs,
        parse_constant=_reject_nonfinite_constant,
    )
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def _official_schema_errors(schema: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError:
        errors.append("official_schema_shape_mismatch")
    try:
        schema_sha256 = _canonical_sha256(schema)
    except (TypeError, ValueError):
        schema_sha256 = "invalid"
    if schema_sha256 != OFFICIAL_SCHEMA_CANONICAL_SHA256:
        errors.append("official_schema_sha256_mismatch")
    if schema.get("$id") != OFFICIAL_SCHEMA_ID:
        errors.append("official_schema_id_mismatch")
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        properties = {}
    version_schema = properties.get("schema_version")
    if not isinstance(version_schema, dict) or version_schema.get("const") != (
        OFFICIAL_SCHEMA_VERSION
    ):
        errors.append("official_schema_version_const_mismatch")
    boundary_schema = properties.get("claim_boundary")
    if not isinstance(boundary_schema, dict) or boundary_schema.get("const") != (
        OFFICIAL_CLAIM_BOUNDARY
    ):
        errors.append("official_schema_claim_boundary_const_mismatch")
    return sorted(set(errors))


def validate_receipt(
    receipt: dict[str, Any],
    *,
    schema: dict[str, Any],
) -> dict[str, Any]:
    schema_identity_errors = _official_schema_errors(schema)
    official_schema = _load_object(DEFAULT_SCHEMA)
    official_schema_errors = _official_schema_errors(official_schema)
    validator = Draft202012Validator(
        official_schema,
        format_checker=FormatChecker(),
    )
    schema_errors = sorted(
        (error.message for error in validator.iter_errors(receipt)),
        key=str,
    )
    schema_errors.extend(schema_identity_errors)
    schema_errors.extend(f"bundled_{error}" for error in official_schema_errors)
    schema_errors.extend(
        f"non_finite_json_number:{path}" for path in _nonfinite_paths(receipt)
    )
    schema_errors = sorted(set(schema_errors))
    contract_errors: list[str] = []

    environment = receipt.get("environment")
    execution = receipt.get("execution")
    attestation = receipt.get("attestation")
    if isinstance(environment, dict) and isinstance(execution, dict):
        if execution.get("backend") == "hip":
            if not environment.get("rocm_version"):
                contract_errors.append("hip_backend_requires_rocm_version")
            if not environment.get("gpu_architecture"):
                contract_errors.append("hip_backend_requires_gpu_architecture")
            if not environment.get("gpu_device_uuid"):
                contract_errors.append("hip_backend_requires_gpu_device_uuid")
    if isinstance(attestation, dict) and attestation.get(
        "independent_from_repository_author"
    ):
        if not attestation.get("signed_at"):
            contract_errors.append("independent_receipt_requires_signed_at")
        if not attestation.get("signature_reference"):
            contract_errors.append("independent_receipt_requires_signature_reference")

    schema_pass = not schema_errors
    contract_pass = schema_pass and not contract_errors
    execution_pass = isinstance(execution, dict) and execution.get("exit_code") == 0
    independent_claimed = isinstance(attestation, dict) and bool(
        attestation.get("independent_from_repository_author")
    )
    signature_claimed = isinstance(attestation, dict) and bool(
        attestation.get("signed_at") and attestation.get("signature_reference")
    )
    credit_blockers = [
        *([] if contract_pass else ["receipt_contract_invalid"]),
        *([] if execution_pass else ["execution_not_successful"]),
        (
            "independent_operator_identity_not_verified"
            if independent_claimed
            else "independent_operator_claim_missing"
        ),
        (
            "signature_not_cryptographically_verified"
            if signature_claimed
            else "verifiable_signature_receipt_missing"
        ),
    ]

    return {
        "schema_version": "community-reproduction-validation.v1",
        "schema_pass": schema_pass,
        "contract_pass": contract_pass,
        "execution_pass": execution_pass,
        "independent_operator_claimed": independent_claimed,
        "signature_claimed": signature_claimed,
        "independent_operator_verified": False,
        "signature_verified": False,
        "eligible_for_community_reproduction_credit": False,
        "credit_blockers": credit_blockers,
        "schema_errors": schema_errors,
        "contract_errors": sorted(contract_errors),
        "claim_boundary": (
            "Validation records one self-declared receipt only. Independent operator "
            "identity and signature authenticity require separately verifiable "
            "receipts, which this v1 contract does not attach; no community "
            "reproduction credit, product, design, hardware, external-V&V, "
            "public-support, or release authority is granted."
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt", type=Path)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--require-independent", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = validate_receipt(
        _load_object(args.receipt),
        schema=_load_object(args.schema),
    )
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    if not report["contract_pass"]:
        return 1
    if (
        args.require_independent
        and not report["eligible_for_community_reproduction_credit"]
    ):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
