#!/usr/bin/env python3
"""Validate one leakage-resistant validation dataset split manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCHEMA = ROOT / "schemas/validation-dataset-split.v1.schema.json"
LOCKED_ROLES = {"locked_validation", "blind_prediction"}
TRAINING_ROLES = {"calibration", "development_regression"}


def _load_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def validate_split(
    manifest: dict[str, Any],
    *,
    schema: dict[str, Any],
) -> dict[str, Any]:
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    schema_errors = sorted(
        (error.message for error in validator.iter_errors(manifest)),
        key=str,
    )
    contract_errors: list[str] = []
    group_roles: dict[str, str] = {}
    sample_roles: dict[str, str] = {}
    seen_group_keys: set[str] = set()
    seen_sample_ids: set[str] = set()

    license_payload = manifest.get("license")
    training_allowed = (
        license_payload.get("training_allowed")
        if isinstance(license_payload, dict)
        else None
    )

    groups = manifest.get("groups")
    if isinstance(groups, list):
        for index, group in enumerate(groups):
            if not isinstance(group, dict):
                continue
            role = group.get("role")
            group_key = group.get("group_key")
            if isinstance(group_key, str) and isinstance(role, str):
                if group_key in seen_group_keys:
                    contract_errors.append(f"duplicate_group_key:{group_key}")
                seen_group_keys.add(group_key)
                previous_role = group_roles.get(group_key)
                if previous_role is not None and previous_role != role:
                    contract_errors.append(
                        f"group_key_cross_role_leakage:{group_key}:{previous_role}:{role}"
                    )
                group_roles.setdefault(group_key, role)
            sample_ids = group.get("sample_ids")
            if isinstance(sample_ids, list) and isinstance(role, str):
                for sample_id in sample_ids:
                    if not isinstance(sample_id, str):
                        continue
                    if sample_id in seen_sample_ids:
                        contract_errors.append(f"duplicate_sample_id:{sample_id}")
                    seen_sample_ids.add(sample_id)
                    previous_role = sample_roles.get(sample_id)
                    if previous_role is not None and previous_role != role:
                        contract_errors.append(
                            f"sample_cross_role_leakage:{sample_id}:{previous_role}:{role}"
                        )
                    sample_roles.setdefault(sample_id, role)
            if role in TRAINING_ROLES and training_allowed is False:
                contract_errors.append(
                    f"training_role_not_permitted_by_license:{index}:{role}"
                )
            if role in LOCKED_ROLES and not group.get("parameters_frozen_at"):
                contract_errors.append(
                    f"locked_role_requires_parameters_frozen_at:{index}:{role}"
                )
            if role in LOCKED_ROLES and not group.get("parameter_snapshot_sha256"):
                contract_errors.append(
                    f"locked_role_requires_parameter_snapshot_sha256:{index}:{role}"
                )
            if role == "blind_prediction" and group.get("results_disclosed") is not False:
                contract_errors.append(
                    f"blind_prediction_results_must_be_undisclosed:{index}"
                )
            if role in TRAINING_ROLES and group.get("results_disclosed") is not True:
                contract_errors.append(
                    f"development_role_results_must_be_disclosed:{index}:{role}"
                )

    schema_pass = not schema_errors
    contract_pass = schema_pass and not contract_errors
    roles = sorted(set(group_roles.values()))
    return {
        "schema_version": "validation-dataset-split-validation.v1",
        "schema_pass": schema_pass,
        "contract_pass": contract_pass,
        "group_count": len(group_roles),
        "sample_count": len(sample_roles),
        "roles": roles,
        "locked_validation_present": "locked_validation" in roles,
        "blind_prediction_present": "blind_prediction" in roles,
        "schema_errors": schema_errors,
        "contract_errors": sorted(set(contract_errors)),
        "claim_boundary": (
            "Validation prevents declared split leakage only and grants no numerical, "
            "experimental-validation, public-support, design, or release authority."
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--require-locked-validation", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = validate_split(
        _load_object(args.manifest),
        schema=_load_object(args.schema),
    )
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    if not report["contract_pass"]:
        return 1
    if args.require_locked_validation and not report["locked_validation_present"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
