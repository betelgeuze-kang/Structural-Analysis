#!/usr/bin/env python3
"""Fail closed when a follow-up changes N1's transitive evidence inputs."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess
from typing import Any, Iterable, Sequence


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_AGGREGATE = Path(
    "implementation/phase1/release_evidence/productization/"
    "n1_cpu_mathematical_closure_gate.json"
)
HASH_PREFIX = "sha256:"


class N1EvidenceBoundaryError(ValueError):
    """Raised when the N1 evidence boundary cannot be proven intact."""


@dataclass(frozen=True, order=True)
class BoundInput:
    path: str
    checksum: str
    source_commit_sha: str
    source_receipt: str


@dataclass(frozen=True)
class BoundaryIssue:
    code: str
    path: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "path": self.path, "detail": self.detail}


@dataclass(frozen=True)
class N1EvidenceBoundaryReport:
    baseline_ref: str
    aggregate_path: str
    bound_inputs: tuple[BoundInput, ...]
    issues: tuple[BoundaryIssue, ...]

    @property
    def contract_pass(self) -> bool:
        return not self.issues

    @property
    def bound_path_count(self) -> int:
        return len({row.path for row in self.bound_inputs})

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "n1-evidence-boundary-report.v1",
            "contract_pass": self.contract_pass,
            "baseline_ref": self.baseline_ref,
            "aggregate_path": self.aggregate_path,
            "bound_path_count": self.bound_path_count,
            "binding_count": len(self.bound_inputs),
            "bound_paths": sorted({row.path for row in self.bound_inputs}),
            "issues": [row.to_dict() for row in self.issues],
        }


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise N1EvidenceBoundaryError(f"duplicate_json_key:{key}")
        value[key] = item
    return value


def _reject_constant(value: str) -> Any:
    raise N1EvidenceBoundaryError(f"non_finite_json_value:{value}")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_strict_object,
            parse_constant=_reject_constant,
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise N1EvidenceBoundaryError(f"receipt_unreadable:{path}") from exc
    if type(value) is not dict:
        raise N1EvidenceBoundaryError(f"receipt_object_required:{path}")
    return value


def _sha256(value: bytes) -> str:
    return HASH_PREFIX + hashlib.sha256(value).hexdigest()


def _hash(value: Any, *, field: str) -> str:
    if (
        type(value) is not str
        or not value.startswith(HASH_PREFIX)
        or len(value) != len(HASH_PREFIX) + 64
        or any(character not in "0123456789abcdef" for character in value[7:])
    ):
        raise N1EvidenceBoundaryError(f"invalid_hash:{field}")
    return value


def _commit(value: Any, *, field: str) -> str:
    if (
        type(value) is not str
        or len(value) != 40
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise N1EvidenceBoundaryError(f"invalid_source_commit:{field}")
    return value


def _repo_path(value: Any, *, field: str) -> str:
    if type(value) is not str or not value:
        raise N1EvidenceBoundaryError(f"invalid_repo_path:{field}")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != value:
        raise N1EvidenceBoundaryError(f"unsafe_repo_path:{field}:{value}")
    return value


def _input_bindings(
    checksums: Any,
    *,
    source_commit_sha: str,
    source_receipt: str,
) -> list[BoundInput]:
    if type(checksums) is not dict or not checksums:
        raise N1EvidenceBoundaryError(
            f"input_checksums_object_required:{source_receipt}"
        )
    return [
        BoundInput(
            path=_repo_path(path, field=f"{source_receipt}.input_checksums"),
            checksum=_hash(
                checksum,
                field=f"{source_receipt}.input_checksums.{path}",
            ),
            source_commit_sha=source_commit_sha,
            source_receipt=source_receipt,
        )
        for path, checksum in checksums.items()
    ]


def collect_transitive_bound_inputs(
    *,
    repo_root: Path = ROOT,
    aggregate_path: Path = DEFAULT_AGGREGATE,
) -> tuple[BoundInput, ...]:
    """Collect aggregate inputs and every declared upstream receipt input."""

    repo_root = repo_root.resolve()
    aggregate_relative = _repo_path(aggregate_path.as_posix(), field="aggregate_path")
    aggregate = _read_json(repo_root / aggregate_relative)
    aggregate_source = aggregate.get("aggregate_source")
    if type(aggregate_source) is not dict:
        raise N1EvidenceBoundaryError("aggregate_source_object_required")
    aggregate_commit = _commit(
        aggregate_source.get("source_commit_sha"),
        field="aggregate_source.source_commit_sha",
    )
    bindings = _input_bindings(
        aggregate_source.get("input_checksums"),
        source_commit_sha=aggregate_commit,
        source_receipt=aggregate_relative,
    )
    aggregate_checksums = {row.path: row.checksum for row in bindings}

    sources = aggregate.get("sources")
    if type(sources) is not dict or not sources:
        raise N1EvidenceBoundaryError("aggregate_sources_object_required")
    for source_name, descriptor in sorted(sources.items()):
        if type(descriptor) is not dict:
            raise N1EvidenceBoundaryError(
                f"aggregate_source_descriptor_invalid:{source_name}"
            )
        receipt_path = _repo_path(
            descriptor.get("path"), field=f"sources.{source_name}.path"
        )
        descriptor_hash = _hash(
            descriptor.get("file_sha256"),
            field=f"sources.{source_name}.file_sha256",
        )
        if aggregate_checksums.get(receipt_path) != descriptor_hash:
            raise N1EvidenceBoundaryError(
                f"upstream_receipt_not_directly_bound:{receipt_path}"
            )
        receipt = _read_json(repo_root / receipt_path)
        receipt_commit = _commit(
            receipt.get("source_commit_sha"),
            field=f"{receipt_path}.source_commit_sha",
        )
        bindings.extend(
            _input_bindings(
                receipt.get("input_checksums"),
                source_commit_sha=receipt_commit,
                source_receipt=receipt_path,
            )
        )
    return tuple(sorted(set(bindings)))


def _git(
    repo_root: Path,
    arguments: Sequence[str],
    *,
    text: bool = False,
) -> bytes | str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=text,
    )
    if result.returncode != 0:
        stderr = result.stderr if text else result.stderr.decode("utf-8", "replace")
        raise N1EvidenceBoundaryError(
            f"git_command_failed:{' '.join(arguments)}:{stderr.strip()}"
        )
    return result.stdout


def _source_bytes(repo_root: Path, commit_sha: str, path: str) -> bytes:
    value = _git(repo_root, ["cat-file", "blob", f"{commit_sha}:{path}"])
    assert isinstance(value, bytes)
    return value


def _is_ancestor(repo_root: Path, ancestor: str) -> bool:
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", ancestor, "HEAD"],
        cwd=repo_root,
        check=False,
        capture_output=True,
    )
    if result.returncode not in (0, 1):
        raise N1EvidenceBoundaryError(f"git_ancestry_probe_failed:{ancestor}")
    return result.returncode == 0


def _diff_records(repo_root: Path, baseline_ref: str) -> list[tuple[str, ...]]:
    value = _git(
        repo_root,
        [
            "diff",
            "--name-status",
            "-z",
            "--find-renames",
            f"{baseline_ref}...HEAD",
        ],
    )
    assert isinstance(value, bytes)
    tokens = value.decode("utf-8", "strict").split("\0")
    if tokens and tokens[-1] == "":
        tokens.pop()
    records: list[tuple[str, ...]] = []
    index = 0
    while index < len(tokens):
        status = tokens[index]
        index += 1
        path_count = 2 if status.startswith(("R", "C")) else 1
        if index + path_count > len(tokens):
            raise N1EvidenceBoundaryError("malformed_git_diff_name_status")
        paths = tuple(tokens[index : index + path_count])
        index += path_count
        records.append((status, *paths))
    return records


def inspect_n1_evidence_boundary(
    *,
    baseline_ref: str,
    repo_root: Path = ROOT,
    aggregate_path: Path = DEFAULT_AGGREGATE,
) -> N1EvidenceBoundaryReport:
    repo_root = repo_root.resolve()
    if type(baseline_ref) is not str or not baseline_ref.strip():
        raise N1EvidenceBoundaryError("baseline_ref_required")
    _git(repo_root, ["rev-parse", "--verify", f"{baseline_ref}^{{commit}}"])
    bindings = collect_transitive_bound_inputs(
        repo_root=repo_root,
        aggregate_path=aggregate_path,
    )
    issues: list[BoundaryIssue] = []
    checksums_by_path: dict[str, set[str]] = {}
    for row in bindings:
        checksums_by_path.setdefault(row.path, set()).add(row.checksum)
        if not _is_ancestor(repo_root, row.source_commit_sha):
            issues.append(
                BoundaryIssue(
                    "source_commit_not_ancestor",
                    row.path,
                    row.source_commit_sha,
                )
            )
        try:
            source_checksum = _sha256(
                _source_bytes(repo_root, row.source_commit_sha, row.path)
            )
        except N1EvidenceBoundaryError as exc:
            issues.append(BoundaryIssue("source_object_missing", row.path, str(exc)))
        else:
            if source_checksum != row.checksum:
                issues.append(
                    BoundaryIssue(
                        "source_checksum_drift",
                        row.path,
                        f"expected={row.checksum} actual={source_checksum}",
                    )
                )

    for path, checksums in sorted(checksums_by_path.items()):
        if len(checksums) != 1:
            issues.append(
                BoundaryIssue(
                    "conflicting_transitive_checksums",
                    path,
                    ",".join(sorted(checksums)),
                )
            )
            continue
        target = repo_root / path
        if not target.is_file():
            issues.append(BoundaryIssue("workspace_input_missing", path, "missing"))
            continue
        workspace_checksum = _sha256(target.read_bytes())
        expected = next(iter(checksums))
        if workspace_checksum != expected:
            issues.append(
                BoundaryIssue(
                    "workspace_checksum_drift",
                    path,
                    f"expected={expected} actual={workspace_checksum}",
                )
            )

    bound_paths = set(checksums_by_path)
    for record in _diff_records(repo_root, baseline_ref):
        status, *paths = record
        for path in paths:
            if path in bound_paths:
                issues.append(
                    BoundaryIssue(
                        "bound_path_changed_in_followup_diff",
                        path,
                        status,
                    )
                )

    unique_issues = tuple(
        BoundaryIssue(*values)
        for values in sorted({(row.code, row.path, row.detail) for row in issues})
    )
    return N1EvidenceBoundaryReport(
        baseline_ref=baseline_ref,
        aggregate_path=aggregate_path.as_posix(),
        bound_inputs=bindings,
        issues=unique_issues,
    )


def assert_n1_evidence_boundary(**kwargs: Any) -> N1EvidenceBoundaryReport:
    report = inspect_n1_evidence_boundary(**kwargs)
    if not report.contract_pass:
        first = report.issues[0]
        raise N1EvidenceBoundaryError(
            f"n1_evidence_boundary_failed:{first.code}:{first.path}:{first.detail}"
        )
    return report


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--aggregate", type=Path, default=DEFAULT_AGGREGATE)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)
    report = inspect_n1_evidence_boundary(
        baseline_ref=args.baseline,
        repo_root=args.repo_root,
        aggregate_path=args.aggregate,
    )
    if args.json:
        print(json.dumps(report.to_dict(), sort_keys=True, allow_nan=False))
    else:
        print(
            f"{'PASS' if report.contract_pass else 'FAIL'} | "
            f"bound_paths={report.bound_path_count} | issues={len(report.issues)}"
        )
        for issue in report.issues:
            print(f"{issue.code}: {issue.path}: {issue.detail}")
    return 0 if report.contract_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
