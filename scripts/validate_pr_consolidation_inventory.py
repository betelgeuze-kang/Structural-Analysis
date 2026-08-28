#!/usr/bin/env python3
"""Validate the bounded open-PR consolidation inventory."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INVENTORY = ROOT / "docs/open-pr-consolidation-inventory.v3.json"
SUPPORTED_SCHEMA_VERSIONS = {
    "open-pr-consolidation-inventory.v1",
    "open-pr-consolidation-inventory.v2",
    "open-pr-consolidation-inventory.v3",
    "open-pr-consolidation-inventory.v4",
}
PREVIOUS_SNAPSHOT_CONTRACTS = {
    "open-pr-consolidation-inventory.v2": (
        "open-pr-consolidation-inventory.v1",
        "docs/open-pr-consolidation-inventory.v1.json",
    ),
    "open-pr-consolidation-inventory.v3": (
        "open-pr-consolidation-inventory.v2",
        "docs/open-pr-consolidation-inventory.v2.json",
    ),
    "open-pr-consolidation-inventory.v4": (
        "open-pr-consolidation-inventory.v3",
        "docs/open-pr-consolidation-inventory.v3.json",
    ),
}
REQUIRED_ENTRY_FIELDS = {
    "pr_number",
    "integration_line",
    "base_class",
    "disposition",
    "replacement_destination",
    "unique_scope",
    "close_condition",
}
SAFE_DISPOSITIONS = {
    "preserve-until-replacement",
    "retain-as-historical-evidence-source",
    "extract-unique-code",
    "extract-after-linear-slice",
    "merge-when-required-checks-pass",
}
V3_CLOSURE_RESOLUTIONS = {
    "merged",
    "superseded_by_pull_requests",
    "retired_out_of_scope",
}
V4_CLOSURE_RESOLUTIONS = V3_CLOSURE_RESOLUTIONS | {"merged_via_pull_request"}
CANONICAL_CLAIM_BOUNDARIES = {
    "open-pr-consolidation-inventory.v1": (
        "This inventory is repository planning metadata. It does not merge code, "
        "prove numerical correctness, create external V&V or hardware credit, "
        "approve licensing, or grant public, design, paid-pilot, or release authority."
    ),
    "open-pr-consolidation-inventory.v2": (
        "This inventory is repository planning metadata. It does not merge code, "
        "prove numerical correctness, create external V&V or hardware credit, "
        "approve licensing, close pull requests, or grant public, design, paid-pilot, "
        "or release authority."
    ),
    "open-pr-consolidation-inventory.v3": (
        "This inventory is repository planning metadata. It does not merge code, "
        "prove numerical correctness, create external V&V or hardware credit, "
        "approve licensing, delete branches, or grant public, design, paid-pilot, "
        "or release authority."
    ),
    "open-pr-consolidation-inventory.v4": (
        "This inventory is repository planning metadata captured at a declared "
        "snapshot time. It does not prove live GitHub state, merge code, prove "
        "numerical correctness, create external V&V or hardware credit, approve "
        "licensing, delete branches, or grant public, design, paid-pilot, or "
        "release authority."
    ),
}


def load_inventory(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("inventory root must be an object")
    return payload


class LocalGitRepository:
    """Read-only local Git queries used by the v4 ancestry contract."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def _run(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment.update(
            {
                "GIT_NO_LAZY_FETCH": "1",
                "GIT_NO_REPLACE_OBJECTS": "1",
            }
        )
        try:
            return subprocess.run(
                ["git", "-C", str(self.root), *arguments],
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
                env=environment,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return subprocess.CompletedProcess(
                args=["git", "-C", str(self.root), *arguments],
                returncode=128,
                stdout="",
                stderr=str(exc),
            )

    def is_repository(self) -> bool:
        result = self._run("rev-parse", "--git-dir")
        return result.returncode == 0

    def has_commit(self, commit: str) -> bool:
        result = self._run("cat-file", "-e", f"{commit}^{{commit}}")
        return result.returncode == 0

    def is_ancestor(self, ancestor: str, descendant: str) -> bool:
        result = self._run("merge-base", "--is-ancestor", ancestor, descendant)
        return result.returncode == 0

    def parents(self, commit: str) -> tuple[str, ...] | None:
        result = self._run("show", "--no-patch", "--format=%P", commit)
        if result.returncode != 0:
            return None
        return tuple(result.stdout.strip().split())


def _validate_local_ancestry(
    repository: LocalGitRepository | None,
    *,
    ancestor: object,
    descendant: object,
    label: str,
    errors: list[str],
) -> None:
    if not _is_git_sha(ancestor) or not _is_git_sha(descendant):
        return
    if repository is None or not repository.is_repository():
        errors.append("local_git_repository_unavailable")
        return
    missing = [
        commit for commit in (ancestor, descendant) if not repository.has_commit(commit)
    ]
    if missing:
        errors.extend(
            f"local_git_commit_missing:{label}:{commit}" for commit in missing
        )
        return
    if not repository.is_ancestor(ancestor, descendant):
        errors.append(f"local_git_ancestry_failed:{label}:{ancestor}:{descendant}")


def _validate_merge_parent(
    repository: LocalGitRepository | None,
    *,
    merged_head: object,
    merge_commit: object,
    label: str,
    errors: list[str],
) -> None:
    if not _is_git_sha(merged_head) or not _is_git_sha(merge_commit):
        return
    if repository is None or not repository.is_repository():
        errors.append("local_git_repository_unavailable")
        return
    if not repository.has_commit(merged_head) or not repository.has_commit(
        merge_commit
    ):
        return
    parents = repository.parents(merge_commit)
    if parents is None or len(parents) < 2:
        errors.append(f"local_git_merge_commit_invalid:{label}:{merge_commit}")
        return
    if merged_head not in parents:
        errors.append(
            f"local_git_merge_parent_missing:{label}:{merged_head}:{merge_commit}"
        )


def _parse_utc_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return None
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        return None
    return parsed.replace(tzinfo=timezone.utc)


def _is_utc_timestamp(value: object) -> bool:
    return _parse_utc_timestamp(value) is not None


def _is_positive_int(value: object) -> bool:
    return type(value) is int and value > 0


def _is_git_sha(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 40
        and all(character in "0123456789abcdef" for character in value)
    )


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _validate_v3_closure_row(
    row: dict[str, Any],
    *,
    number: int,
    schema_version: object,
    errors: list[str],
) -> None:
    if not _is_utc_timestamp(row.get("closed_at")):
        errors.append(f"closed_since_previous_closed_at_invalid:{number}")
    reason = row.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        errors.append(f"closed_since_previous_reason_missing:{number}")
    resolution = row.get("resolution")
    allowed_resolutions = (
        V4_CLOSURE_RESOLUTIONS
        if schema_version == "open-pr-consolidation-inventory.v4"
        else V3_CLOSURE_RESOLUTIONS
    )
    if resolution not in allowed_resolutions:
        errors.append(f"closed_since_previous_resolution_invalid:{number}")
        return
    if resolution in {"merged", "merged_via_pull_request"}:
        if row.get("merged") is not True:
            errors.append(f"closed_since_previous_merge_invalid:{number}")
        if not _is_utc_timestamp(row.get("merged_at")):
            errors.append(f"closed_since_previous_merged_at_invalid:{number}")
        if not _is_git_sha(row.get("merge_commit")):
            errors.append(f"closed_since_previous_merge_commit_invalid:{number}")
        return
    if row.get("merged") is not False:
        errors.append(f"closed_since_previous_unmerged_flag_invalid:{number}")
    if resolution == "superseded_by_pull_requests":
        replacements = row.get("superseded_by_pull_requests")
        if (
            not isinstance(replacements, list)
            or not replacements
            or not all(_is_positive_int(replacement) for replacement in replacements)
        ):
            errors.append(f"closed_since_previous_replacements_invalid:{number}")
        elif len(replacements) != len(set(replacements)):
            errors.append(f"closed_since_previous_replacements_duplicate:{number}")
        elif number in replacements:
            errors.append(f"closed_since_previous_replacements_self_reference:{number}")
        return
    scope_issue = row.get("scope_decision_issue")
    if not _is_positive_int(scope_issue):
        errors.append(f"closed_since_previous_scope_decision_invalid:{number}")


def _validate_v4_closure_row(
    row: dict[str, Any],
    *,
    number: int,
    source_commit: object,
    repository: LocalGitRepository | None,
    errors: list[str],
) -> None:
    head_commit = row.get("head_commit")
    if not _is_git_sha(head_commit):
        errors.append(f"closed_since_previous_head_commit_invalid:{number}")
        return

    resolution = row.get("resolution")
    if resolution == "merged":
        merge_commit = row.get("merge_commit")
        _validate_local_ancestry(
            repository,
            ancestor=head_commit,
            descendant=merge_commit,
            label=f"merged_head_to_merge:{number}",
            errors=errors,
        )
        _validate_merge_parent(
            repository,
            merged_head=head_commit,
            merge_commit=merge_commit,
            label=f"merged_head_to_merge:{number}",
            errors=errors,
        )
        _validate_local_ancestry(
            repository,
            ancestor=merge_commit,
            descendant=source_commit,
            label=f"merged_commit_to_source:{number}",
            errors=errors,
        )
        return

    if resolution == "merged_via_pull_request":
        proof = row.get("merged_via_pull_request_proof")
        if not isinstance(proof, dict):
            errors.append(f"closed_since_previous_merge_carrier_proof_missing:{number}")
            return
        carrier_number = proof.get("carrier_pr_number")
        if not _is_positive_int(carrier_number) or carrier_number == number:
            errors.append(f"closed_since_previous_merge_carrier_pr_invalid:{number}")
        carrier_head = proof.get("carrier_head_commit")
        if not _is_git_sha(carrier_head):
            errors.append(f"closed_since_previous_merge_carrier_head_invalid:{number}")
            return
        carrier_merge = proof.get("carrier_merge_commit")
        if not _is_git_sha(carrier_merge):
            errors.append(f"closed_since_previous_merge_carrier_commit_invalid:{number}")
            return
        if row.get("merge_commit") != carrier_merge:
            errors.append(f"closed_since_previous_merge_carrier_commit_mismatch:{number}")
        _validate_local_ancestry(
            repository,
            ancestor=head_commit,
            descendant=carrier_head,
            label=f"merged_head_to_carrier_head:{number}",
            errors=errors,
        )
        _validate_merge_parent(
            repository,
            merged_head=carrier_head,
            merge_commit=carrier_merge,
            label=f"carrier_head_to_merge:{number}",
            errors=errors,
        )
        _validate_local_ancestry(
            repository,
            ancestor=carrier_merge,
            descendant=source_commit,
            label=f"carrier_merge_to_source:{number}",
            errors=errors,
        )
        return

    if resolution == "superseded_by_pull_requests":
        proof = row.get("supersession_proof")
        if not isinstance(proof, dict):
            errors.append(f"closed_since_previous_supersession_proof_missing:{number}")
            return
        replacement_number = proof.get("replacement_pr_number")
        replacements = row.get("superseded_by_pull_requests")
        if not _is_positive_int(replacement_number) or replacement_number not in (
            replacements if isinstance(replacements, list) else []
        ):
            errors.append(
                f"closed_since_previous_supersession_proof_pr_invalid:{number}"
            )
        replacement_merge = proof.get("replacement_merge_commit")
        if not _is_git_sha(replacement_merge):
            errors.append(
                f"closed_since_previous_replacement_merge_commit_invalid:{number}"
            )
            return
        replacement_head = proof.get("replacement_head_commit")
        if not _is_git_sha(replacement_head):
            errors.append(
                f"closed_since_previous_replacement_head_commit_invalid:{number}"
            )
            return
        _validate_local_ancestry(
            repository,
            ancestor=head_commit,
            descendant=replacement_head,
            label=f"superseded_head_to_replacement_head:{number}",
            errors=errors,
        )
        _validate_merge_parent(
            repository,
            merged_head=replacement_head,
            merge_commit=replacement_merge,
            label=f"replacement_head_to_merge:{number}",
            errors=errors,
        )
        _validate_local_ancestry(
            repository,
            ancestor=replacement_merge,
            descendant=source_commit,
            label=f"replacement_merge_to_source:{number}",
            errors=errors,
        )
        return

    if resolution == "retired_out_of_scope":
        _validate_local_ancestry(
            repository,
            ancestor=head_commit,
            descendant=head_commit,
            label=f"retired_head_exists:{number}",
            errors=errors,
        )


def validate_inventory(
    payload: dict[str, Any], *, repository_root: Path | None = ROOT
) -> dict[str, Any]:
    errors: list[str] = []
    schema_version = payload.get("schema_version")
    if schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        errors.append("invalid_schema_version")
    snapshot_at = _parse_utc_timestamp(payload.get("snapshot_at"))
    if snapshot_at is None:
        errors.append("invalid_snapshot_at")
    source_commit = payload.get("source_commit")
    if not _is_git_sha(source_commit):
        errors.append("invalid_source_commit")
    repository = (
        LocalGitRepository(repository_root)
        if schema_version == "open-pr-consolidation-inventory.v4"
        and repository_root is not None
        else None
    )
    if schema_version == "open-pr-consolidation-inventory.v4":
        _validate_local_ancestry(
            repository,
            ancestor=source_commit,
            descendant=source_commit,
            label="source_commit_exists",
            errors=errors,
        )
    if payload.get("active_implementation_pr_target") != 4:
        errors.append("active_implementation_pr_target_must_equal_4")

    snapshot_numbers = payload.get("snapshot_open_pr_numbers")
    entries = payload.get("entries")
    if not isinstance(snapshot_numbers, list) or not all(
        _is_positive_int(number) for number in snapshot_numbers
    ):
        errors.append("invalid_snapshot_open_pr_numbers")
        snapshot_numbers = []
    if len(snapshot_numbers) != len(set(snapshot_numbers)):
        errors.append("duplicate_snapshot_open_pr_number")

    entry_numbers: list[int] = []
    integration_lines: set[str] = set()
    if not isinstance(entries, list):
        errors.append("entries_must_be_array")
        entries = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            errors.append(f"entry_not_object:{index}")
            continue
        missing = sorted(REQUIRED_ENTRY_FIELDS - entry.keys())
        if missing:
            errors.append(f"entry_missing_fields:{index}:{','.join(missing)}")
        pr_number = entry.get("pr_number")
        if not _is_positive_int(pr_number):
            errors.append(f"invalid_pr_number:{index}")
        else:
            entry_numbers.append(pr_number)
        integration_line = entry.get("integration_line")
        if not isinstance(integration_line, str) or not integration_line.strip():
            errors.append(f"invalid_integration_line:{index}")
        else:
            integration_lines.add(integration_line)
        base_class = entry.get("base_class")
        disposition = entry.get("disposition")
        if base_class not in {"current-main", "legacy-stack"}:
            errors.append(f"invalid_base_class:{index}")
        if disposition not in SAFE_DISPOSITIONS:
            errors.append(f"unsafe_or_unknown_disposition:{index}")
        if (
            base_class == "legacy-stack"
            and disposition == "merge-when-required-checks-pass"
        ):
            errors.append(f"legacy_stack_merge_disposition_invalid:{index}")
        unique_scope = entry.get("unique_scope")
        if (
            not isinstance(unique_scope, list)
            or not unique_scope
            or not all(isinstance(item, str) and item.strip() for item in unique_scope)
        ):
            errors.append(f"invalid_unique_scope:{index}")
        close_condition = entry.get("close_condition")
        if not isinstance(close_condition, str) or not close_condition.strip():
            errors.append(f"missing_close_condition:{index}")
        replacement = entry.get("replacement_destination")
        if not isinstance(replacement, str) or not replacement.strip():
            errors.append(f"missing_replacement_destination:{index}")

    if len(entry_numbers) != len(set(entry_numbers)):
        errors.append("duplicate_entry_pr_number")
    if set(entry_numbers) != set(snapshot_numbers):
        missing_entries = sorted(set(snapshot_numbers) - set(entry_numbers))
        unexpected_entries = sorted(set(entry_numbers) - set(snapshot_numbers))
        if missing_entries:
            errors.append(
                "snapshot_prs_missing_entries:" + ",".join(map(str, missing_entries))
            )
        if unexpected_entries:
            errors.append(
                "entries_not_in_snapshot:" + ",".join(map(str, unexpected_entries))
            )

    if schema_version in PREVIOUS_SNAPSHOT_CONTRACTS:
        previous_schema, previous_path = PREVIOUS_SNAPSHOT_CONTRACTS[schema_version]
        previous_snapshot = payload.get("previous_snapshot")
        previous_numbers: list[int] = []
        previous_snapshot_at: datetime | None = None
        if not isinstance(previous_snapshot, dict):
            errors.append("previous_snapshot_missing")
        else:
            if previous_snapshot.get("schema_version") != previous_schema:
                errors.append("previous_snapshot_schema_invalid")
            if previous_snapshot.get("path") != previous_path:
                errors.append("previous_snapshot_path_invalid")
            raw_previous_numbers = previous_snapshot.get("snapshot_open_pr_numbers")
            if not isinstance(raw_previous_numbers, list) or not all(
                _is_positive_int(number) for number in raw_previous_numbers
            ):
                errors.append("previous_snapshot_numbers_invalid")
            else:
                previous_numbers = raw_previous_numbers
                if len(previous_numbers) != len(set(previous_numbers)):
                    errors.append("previous_snapshot_numbers_duplicate")
            referenced_path = ROOT / previous_path
            try:
                referenced_bytes = referenced_path.read_bytes()
                referenced_snapshot = json.loads(referenced_bytes)
            except (OSError, ValueError, json.JSONDecodeError):
                errors.append("previous_snapshot_file_unreadable")
            else:
                if not isinstance(referenced_snapshot, dict):
                    errors.append("previous_snapshot_file_unreadable")
                    referenced_snapshot = {}
                if referenced_snapshot.get("schema_version") != previous_schema:
                    errors.append("previous_snapshot_file_schema_mismatch")
                if (
                    referenced_snapshot.get("snapshot_open_pr_numbers")
                    != raw_previous_numbers
                ):
                    errors.append("previous_snapshot_file_numbers_mismatch")
                previous_snapshot_at = _parse_utc_timestamp(
                    referenced_snapshot.get("snapshot_at")
                )
                if previous_snapshot_at is None:
                    errors.append("previous_snapshot_file_snapshot_at_invalid")
                if schema_version == "open-pr-consolidation-inventory.v4":
                    expected_hash = previous_snapshot.get("content_sha256")
                    if not _is_sha256(expected_hash):
                        errors.append("previous_snapshot_content_sha256_invalid")
                    elif hashlib.sha256(referenced_bytes).hexdigest() != expected_hash:
                        errors.append("previous_snapshot_content_sha256_mismatch")

        if (
            snapshot_at is not None
            and previous_snapshot_at is not None
            and snapshot_at <= previous_snapshot_at
        ):
            errors.append("snapshot_at_not_after_previous_snapshot")

        added_numbers = payload.get("added_since_previous")
        if not isinstance(added_numbers, list) or not all(
            _is_positive_int(number) for number in added_numbers
        ):
            errors.append("added_since_previous_invalid")
            added_numbers = []
        elif len(added_numbers) != len(set(added_numbers)):
            errors.append("added_since_previous_duplicate")

        closed_rows = payload.get("closed_since_previous")
        closed_numbers: list[int] = []
        if not isinstance(closed_rows, list):
            errors.append("closed_since_previous_invalid")
            closed_rows = []
        for index, row in enumerate(closed_rows):
            if not isinstance(row, dict):
                errors.append(f"closed_since_previous_entry_invalid:{index}")
                continue
            number = row.get("pr_number")
            if not _is_positive_int(number):
                errors.append(f"closed_since_previous_number_invalid:{index}")
                continue
            closed_numbers.append(number)
            if row.get("state") != "closed":
                errors.append(f"closed_since_previous_state_invalid:{number}")
            if schema_version == "open-pr-consolidation-inventory.v2":
                if row.get("merged") is not True:
                    errors.append(f"closed_since_previous_merge_invalid:{number}")
                merged_at = row.get("merged_at")
                if not _is_utc_timestamp(merged_at):
                    errors.append(f"closed_since_previous_merged_at_invalid:{number}")
            else:
                _validate_v3_closure_row(
                    row,
                    number=number,
                    schema_version=schema_version,
                    errors=errors,
                )
                if schema_version == "open-pr-consolidation-inventory.v4":
                    _validate_v4_closure_row(
                        row,
                        number=number,
                        source_commit=source_commit,
                        repository=repository,
                        errors=errors,
                    )
            closed_at = _parse_utc_timestamp(row.get("closed_at"))
            if closed_at is not None:
                if (
                    previous_snapshot_at is not None
                    and closed_at <= previous_snapshot_at
                ):
                    errors.append(
                        f"closed_since_previous_not_after_previous_snapshot:{number}"
                    )
                if snapshot_at is not None and closed_at > snapshot_at:
                    errors.append(f"closed_since_previous_after_snapshot:{number}")
            merged_at = _parse_utc_timestamp(row.get("merged_at"))
            if merged_at is not None:
                if (
                    previous_snapshot_at is not None
                    and merged_at <= previous_snapshot_at
                ):
                    errors.append(
                        f"merged_since_previous_not_after_previous_snapshot:{number}"
                    )
                if snapshot_at is not None and merged_at > snapshot_at:
                    errors.append(f"merged_since_previous_after_snapshot:{number}")
        if len(closed_numbers) != len(set(closed_numbers)):
            errors.append("closed_since_previous_duplicate")

        previous_set = set(previous_numbers)
        added_set = set(added_numbers)
        closed_set = set(closed_numbers)
        if previous_set & added_set:
            errors.append("added_since_previous_already_in_previous")
        known_since_previous = previous_set | added_set
        if not closed_set <= known_since_previous:
            errors.append("closed_since_previous_not_in_previous_or_added")
        reconciled_numbers = (previous_set | added_set) - closed_set
        if reconciled_numbers != set(snapshot_numbers):
            errors.append("snapshot_delta_reconciliation_failed")

    if schema_version in {
        "open-pr-consolidation-inventory.v3",
        "open-pr-consolidation-inventory.v4",
    }:
        active_numbers = payload.get("active_implementation_pr_numbers")
        if not isinstance(active_numbers, list) or not all(
            _is_positive_int(number) for number in active_numbers
        ):
            errors.append("active_implementation_pr_numbers_invalid")
            active_numbers = []
        if len(active_numbers) != len(set(active_numbers)):
            errors.append("active_implementation_pr_numbers_duplicate")
        if not set(active_numbers) <= set(snapshot_numbers):
            errors.append("active_implementation_pr_not_open")
        if len(active_numbers) > payload.get("active_implementation_pr_target", 0):
            errors.append("active_implementation_pr_target_exceeded")
        entry_active_numbers: list[int] = []
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict):
                continue
            if not isinstance(entry.get("active_implementation"), bool):
                errors.append(f"entry_active_implementation_invalid:{index}")
            elif entry["active_implementation"]:
                entry_active_numbers.append(entry["pr_number"])
        if set(entry_active_numbers) != set(active_numbers):
            errors.append("active_implementation_pr_inventory_inconsistent")

    claim_boundary = payload.get("claim_boundary")
    if claim_boundary != CANONICAL_CLAIM_BOUNDARIES.get(schema_version):
        errors.append("claim_boundary_missing_or_unsafe")

    return {
        "schema_version": (
            "open-pr-consolidation-inventory-validation.v4"
            if schema_version == "open-pr-consolidation-inventory.v4"
            else "open-pr-consolidation-inventory-validation.v3"
        ),
        "contract_pass": not errors,
        "entry_count": len(entry_numbers),
        "snapshot_count": len(snapshot_numbers),
        "integration_lines": sorted(integration_lines),
        "errors": sorted(set(errors)),
        "claim_boundary": (
            "Validation confirms planning inventory consistency only and creates no "
            "numerical, external-V&V, hardware, licensing, merge, or release authority."
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inventory", nargs="?", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=ROOT,
        help="local Git repository used for fail-closed v4 ancestry checks",
    )
    parser.add_argument("--out", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = validate_inventory(
        load_inventory(args.inventory), repository_root=args.repository_root
    )
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if report["contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
