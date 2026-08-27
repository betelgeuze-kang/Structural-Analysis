#!/usr/bin/env python3
"""Validate one bounded community reproduction receipt."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCHEMA = ROOT / "schemas/community-reproduction-receipt.v1.schema.json"


def _load_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def validate_receipt(
    receipt: dict[str, Any],
    *,
    schema: dict[str, Any],
) -> dict[str, Any]:
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    schema_errors = sorted(
        (error.message for error in validator.iter_errors(receipt)),
        key=str,
    )
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
    independent = isinstance(attestation, dict) and bool(
        attestation.get("independent_from_repository_author")
    )
    signed = isinstance(attestation, dict) and bool(
        attestation.get("signed_at") and attestation.get("signature_reference")
    )

    return {
        "schema_version": "community-reproduction-validation.v1",
        "schema_pass": schema_pass,
        "contract_pass": contract_pass,
        "execution_pass": execution_pass,
        "independent_operator": independent,
        "signed_receipt": signed,
        "eligible_for_community_reproduction_credit": bool(
            contract_pass and execution_pass and independent and signed
        ),
        "schema_errors": schema_errors,
        "contract_errors": sorted(contract_errors),
        "claim_boundary": (
            "Validation records one receipt only and grants no product, design, "
            "hardware, external-V&V, public-support, or release authority."
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
    if args.require_independent and not report[
        "eligible_for_community_reproduction_credit"
    ]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
