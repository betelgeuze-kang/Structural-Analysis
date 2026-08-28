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
_GLOB_MARKERS = frozenset("*?[")


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


def _has_glob(value: str) -> bool:
    return any(marker in value for marker in _GLOB_MARKERS)


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
    if not allow_glob and _has_glob(value):
        return [f"repo_relative_path_invalid:{prefix}:glob_forbidden"]

    errors: list[str] = []
    if allow_glob and _has_glob(value):
        literal_prefix: list[str] = []
        for part in parts:
            if _has_glob(part):
                break
            literal_prefix.append(part)
        if len(literal_prefix) < 2:
            errors.append(f"path_glob_too_broad:{material_id}:{value}")
    else:
        literal_prefix = list(parts)

    candidate = ROOT
    for part in literal_prefix:
        candidate /= part
        if candidate.is_symlink():
            errors.append(
                f"repo_path_symlink_risk:{prefix}:{candidate.relative_to(ROOT)}"
            )
            break
    try:
        (ROOT / path).resolve(strict=False).relative_to(ROOT.resolve())
    except ValueError:
        errors.append(f"repo_relative_path_invalid:{prefix}:escapes_repository")

    if allow_glob and not errors:
        try:
            matches = ROOT.glob(value)
            for match in matches:
                relative = match.relative_to(ROOT)
                cursor = ROOT
                for part in relative.parts:
                    cursor /= part
                    if cursor.is_symlink():
                        errors.append(
                            f"repo_path_symlink_risk:{prefix}:{relative.as_posix()}"
                        )
                        break
                if errors:
                    break
        except (OSError, ValueError):
            errors.append(f"repo_relative_path_invalid:{prefix}:glob_not_safe")
    return errors


def _recursive_glob_prefix(value: str) -> str | None:
    for suffix in ("/**/*", "/**"):
        if value.endswith(suffix):
            prefix = value[: -len(suffix)].rstrip("/")
            if prefix and not _has_glob(prefix):
                return prefix
    return None


def _fixed_glob_prefix(value: str) -> tuple[str, ...]:
    result: list[str] = []
    for part in PurePosixPath(value).parts:
        if _has_glob(part):
            break
        result.append(part)
    return tuple(result)


def _glob_covers(left: str, right: str) -> bool:
    try:
        recursive_prefix = _recursive_glob_prefix(left)
        if recursive_prefix is not None:
            return right == recursive_prefix or right.startswith(recursive_prefix + "/")
        if not _has_glob(right):
            return PurePosixPath(right).match(left)
        if _has_glob(left):
            left_prefix = _fixed_glob_prefix(left)
            right_prefix = _fixed_glob_prefix(right)
            if left_prefix == right_prefix:
                return True
            if left.endswith("/*") and right_prefix[: len(left_prefix)] == left_prefix:
                return len(right_prefix) == len(left_prefix) + 1
        return False
    except (OSError, ValueError):
        return True


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
    path_rows: list[tuple[str, str]] = []
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
                    contract_errors.extend(
                        _repo_relative_path_errors(
                            path_glob,
                            field="path_glob",
                            material_id=material_id,
                            allow_glob=True,
                        )
                    )
                    previous = seen_paths.get(path_glob)
                    if previous is not None:
                        contract_errors.append(
                            f"duplicate_path_glob:{path_glob}:{previous}:{material_id}"
                        )
                    else:
                        seen_paths[path_glob] = material_id
                    for previous_glob, previous_id in path_rows:
                        if _glob_covers(previous_glob, path_glob) or _glob_covers(
                            path_glob, previous_glob
                        ):
                            contract_errors.append(
                                "overlapping_path_glob:"
                                f"{previous_glob}:{previous_id}:{path_glob}:{material_id}"
                            )
                    path_rows.append((path_glob, material_id))

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
