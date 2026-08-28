#!/usr/bin/env python3
"""Validate one bounded third-party material permission inventory."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any, Sequence

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCHEMA = ROOT / "schemas/third-party-material-inventory.v1.schema.json"
_PATTERN_MARKERS = frozenset("*?[]")


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


def _has_pattern_marker(value: str) -> bool:
    return any(marker in value for marker in _PATTERN_MARKERS)


def _scope_descriptor(
    value: str,
    *,
    allow_recursive: bool,
) -> tuple[str, tuple[str, ...]] | None:
    parts = PurePosixPath(value).parts
    if not _has_pattern_marker(value):
        return ("literal", parts)
    if (
        allow_recursive
        and len(parts) >= 2
        and parts[-1] == "**"
        and all(not _has_pattern_marker(part) for part in parts[:-1])
    ):
        return ("recursive", parts[:-1])
    return None


def _repo_relative_path_errors(
    value: Any,
    *,
    field: str,
    material_id: str,
    allow_glob: bool,
) -> list[str]:
    prefix = f"{field}:{material_id}"
    if not isinstance(value, str) or not value:
        return [f"repo_relative_path_invalid:{prefix}:empty_or_non_string"]
    if "\\" in value:
        return [f"repo_relative_path_invalid:{prefix}:backslash_forbidden"]
    if "\x00" in value:
        return [f"repo_relative_path_invalid:{prefix}:nul_forbidden"]
    path = PurePosixPath(value)
    parts = path.parts
    if path.is_absolute() or value.startswith("/"):
        return [f"repo_relative_path_invalid:{prefix}:absolute_forbidden"]
    if (
        path.as_posix() != value
        or not parts
        or any(part in {"", ".", ".."} for part in parts)
        or (parts and ":" in parts[0])
    ):
        return [f"repo_relative_path_invalid:{prefix}:non_canonical_or_traversal"]
    descriptor = _scope_descriptor(value, allow_recursive=allow_glob)
    if descriptor is None:
        grammar = "path_glob_grammar_invalid" if allow_glob else "glob_forbidden"
        return [f"repo_relative_path_invalid:{prefix}:{grammar}"]

    errors: list[str] = []
    _, literal_prefix = descriptor

    candidate = ROOT
    for part in literal_prefix:
        candidate /= part
        if candidate.is_symlink():
            errors.append(
                f"repo_path_symlink_risk:{prefix}:{candidate.relative_to(ROOT)}"
            )
            break
    try:
        candidate.resolve(strict=False).relative_to(ROOT.resolve())
    except ValueError:
        errors.append(f"repo_relative_path_invalid:{prefix}:escapes_repository")
    return errors


def _is_prefix(left: tuple[str, ...], right: tuple[str, ...]) -> bool:
    return len(left) <= len(right) and right[: len(left)] == left


def _scopes_overlap(
    left: tuple[str, tuple[str, ...]],
    right: tuple[str, tuple[str, ...]],
) -> bool:
    left_kind, left_parts = left
    right_kind, right_parts = right
    if left_kind == "literal" and right_kind == "literal":
        return left_parts == right_parts
    if left_kind == "recursive" and right_kind == "recursive":
        return _is_prefix(left_parts, right_parts) or _is_prefix(
            right_parts, left_parts
        )
    if left_kind == "recursive":
        return _is_prefix(left_parts, right_parts)
    return _is_prefix(right_parts, left_parts)


def _load_object(path: Path) -> dict[str, Any]:
    payload = json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=_reject_duplicate_object_pairs,
        parse_constant=_reject_nonfinite_constant,
    )
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def validate_inventory(
    inventory: dict[str, Any],
    *,
    schema: dict[str, Any],
) -> dict[str, Any]:
    validator = Draft202012Validator(schema)
    schema_errors = sorted(
        (error.message for error in validator.iter_errors(inventory)),
        key=str,
    )
    schema_errors.extend(
        f"non_finite_json_number:{path}" for path in _nonfinite_paths(inventory)
    )
    schema_errors = sorted(set(schema_errors))
    contract_errors: list[str] = []
    seen_ids: set[str] = set()
    seen_paths: dict[str, str] = {}
    path_rows: list[tuple[str, str, tuple[str, tuple[str, ...]]]] = []
    approved_count = 0
    restricted_count = 0
    unreviewed_count = 0

    entries = inventory.get("entries")
    if isinstance(entries, list):
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict):
                continue
            material_id = entry.get("material_id")
            if isinstance(material_id, str):
                if material_id in seen_ids:
                    contract_errors.append(f"duplicate_material_id:{material_id}")
                seen_ids.add(material_id)
            else:
                material_id = f"row-{index}"

            paths = entry.get("path_globs")
            if isinstance(paths, list):
                for path_glob in paths:
                    if not isinstance(path_glob, str):
                        continue
                    path_errors = _repo_relative_path_errors(
                        path_glob,
                        field="path_glob",
                        material_id=material_id,
                        allow_glob=True,
                    )
                    contract_errors.extend(path_errors)
                    previous = seen_paths.get(path_glob)
                    if previous is not None:
                        contract_errors.append(
                            f"duplicate_path_glob:{path_glob}:{previous}:{material_id}"
                        )
                    else:
                        seen_paths[path_glob] = material_id
                    descriptor = (
                        None
                        if path_errors
                        else _scope_descriptor(
                            path_glob,
                            allow_recursive=True,
                        )
                    )
                    for previous_glob, previous_id, previous_descriptor in path_rows:
                        if descriptor is not None and _scopes_overlap(
                            previous_descriptor,
                            descriptor,
                        ):
                            contract_errors.append(
                                "overlapping_path_glob:"
                                f"{previous_glob}:{previous_id}:{path_glob}:{material_id}"
                            )
                    if descriptor is not None:
                        path_rows.append((path_glob, material_id, descriptor))

            status = entry.get("review_status")
            if status == "approved":
                approved_count += 1
            elif status == "restricted":
                restricted_count += 1
            elif status == "unreviewed":
                unreviewed_count += 1

            evidence = entry.get("evidence_reference")
            if evidence is not None:
                contract_errors.extend(
                    _repo_relative_path_errors(
                        evidence,
                        field="evidence_reference",
                        material_id=material_id,
                        allow_glob=False,
                    )
                )
            license_identifier = entry.get("license_identifier")
            permissions = entry.get("permissions")
            asserted_permissions: list[str] = []
            if isinstance(permissions, dict):
                asserted_permissions = sorted(
                    key for key, value in permissions.items() if value is True
                )
                if (
                    permissions.get("redistribution") is True
                    and permissions.get("use") is not True
                ):
                    contract_errors.append(f"redistribution_requires_use:{material_id}")
                if (
                    permissions.get("derivative_works") is True
                    and permissions.get("use") is not True
                ):
                    contract_errors.append(
                        f"derivative_works_requires_use:{material_id}"
                    )
                if (
                    permissions.get("training") is True
                    and permissions.get("use") is not True
                ):
                    contract_errors.append(f"training_requires_use:{material_id}")

            if asserted_permissions and status != "approved":
                contract_errors.append(
                    f"permission_asserted_without_approved_review:{material_id}:"
                    + ",".join(asserted_permissions)
                )
            if (status == "approved" or asserted_permissions) and not (
                isinstance(evidence, str) and evidence.strip()
            ):
                contract_errors.append(f"permission_evidence_missing:{material_id}")
            if status == "approved" and (
                not isinstance(license_identifier, str)
                or license_identifier.strip().lower()
                in {"", "unknown", "none", "no-license"}
            ):
                contract_errors.append(
                    f"approved_license_identifier_missing_or_ambiguous:{material_id}"
                )
            if status == "approved" and not asserted_permissions:
                contract_errors.append(
                    f"approved_row_asserts_no_permission:{material_id}"
                )

    schema_pass = not schema_errors
    contract_pass = schema_pass and not contract_errors
    return {
        "schema_version": "third-party-material-inventory-validation.v1",
        "schema_pass": schema_pass,
        "contract_pass": contract_pass,
        "entry_count": len(entries) if isinstance(entries, list) else 0,
        "approved_count": approved_count,
        "restricted_count": restricted_count,
        "unreviewed_count": unreviewed_count,
        "schema_errors": schema_errors,
        "contract_errors": sorted(set(contract_errors)),
        "claim_boundary": (
            "Validation records declared inventory consistency only and grants no "
            "software-use, data-use, redistribution, derivative-work, training, "
            "legal, open-source, commercial, or release authority."
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inventory", type=Path)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--out", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = validate_inventory(
        _load_object(args.inventory),
        schema=_load_object(args.schema),
    )
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if report["contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
