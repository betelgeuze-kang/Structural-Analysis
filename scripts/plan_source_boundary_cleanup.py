#!/usr/bin/env python3
"""Plan source-boundary cleanup candidates without mutating Git state."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess


GENERATED_BOUNDARY_PREFIXES = (
    "implementation/phase1/stress/",
    "implementation/phase1/workspace/",
    "implementation/phase1/output/",
)
BUILD_OUTPUT_PREFIXES = (
    "implementation/phase1/rust_hip_md3bead_hook/target/",
    "node_modules/",
    "dist/",
)
BUILD_OUTPUT_PARTS = {
    "__pycache__",
}
BUILD_OUTPUT_SUFFIXES = (
    ".pyc",
)
BUCKETS = (
    "build_output",
    "generated_boundary",
    "large_file",
    "private_secret",
)
DEFAULT_LARGE_FILE_THRESHOLD_MIB = 25.0
BYTES_PER_MIB = 1024 * 1024
SCHEMA_VERSION = "source-boundary-cleanup-plan.v1"


def _git_files() -> list[str]:
    raw = subprocess.check_output(["git", "ls-files", "-z"])
    return [item for item in raw.decode("utf-8", "replace").split("\0") if item]


def _read_tracked_files(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    separator = "\0" if "\0" in text else "\n"
    return [item.strip() for item in text.split(separator) if item.strip()]


def _path_size(path: str) -> int | None:
    file_path = Path(path)
    if not file_path.is_file():
        return None
    return file_path.stat().st_size


def _is_private_pem(path: str) -> bool:
    return path.endswith(".pem") and not path.endswith(".pub.pem")


def _is_build_output(path: str) -> bool:
    return (
        any(path.startswith(prefix) for prefix in BUILD_OUTPUT_PREFIXES)
        or bool(set(Path(path).parts) & BUILD_OUTPUT_PARTS)
        or path.endswith(BUILD_OUTPUT_SUFFIXES)
    )


def classify_path(path: str, *, size_bytes: int | None, large_file_threshold_bytes: int) -> list[str]:
    buckets: list[str] = []
    if _is_build_output(path):
        buckets.append("build_output")
    if any(path.startswith(prefix) for prefix in GENERATED_BOUNDARY_PREFIXES):
        buckets.append("generated_boundary")
    if size_bytes is not None and size_bytes >= large_file_threshold_bytes:
        buckets.append("large_file")
    if _is_private_pem(path):
        buckets.append("private_secret")
    return buckets


def recommended_action(buckets: list[str]) -> str:
    if "private_secret" in buckets:
        return "manual_review"
    if "build_output" in buckets or "generated_boundary" in buckets:
        return "remove_from_git"
    if "large_file" in buckets:
        return "externalize_or_allowlist"
    return "manual_review"


def build_plan(files: list[str], *, large_file_threshold_mib: float = DEFAULT_LARGE_FILE_THRESHOLD_MIB) -> dict[str, object]:
    large_file_threshold_bytes = int(large_file_threshold_mib * BYTES_PER_MIB)
    records: list[dict[str, int | str | list[str] | None]] = []
    counts_by_bucket = dict.fromkeys(BUCKETS, 0)
    total_candidate_bytes = 0

    for path in sorted(files):
        size_bytes = _path_size(path)
        buckets = classify_path(
            path,
            size_bytes=size_bytes,
            large_file_threshold_bytes=large_file_threshold_bytes,
        )
        if not buckets:
            continue
        for bucket in buckets:
            counts_by_bucket[bucket] += 1
        if size_bytes is not None:
            total_candidate_bytes += size_bytes
        records.append(
            {
                "path": path,
                "bytes": size_bytes,
                "buckets": buckets,
                "recommended_action": recommended_action(buckets),
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "contract_pass": not records,
        "reason_code": "PASS" if not records else "ERR_SOURCE_BOUNDARY_CLEANUP_CANDIDATES",
        "counts_by_bucket": {
            bucket: count
            for bucket, count in counts_by_bucket.items()
            if count
        },
        "large_file_threshold_bytes": large_file_threshold_bytes,
        "records": records,
        "total_candidate_bytes": total_candidate_bytes,
        "total_candidate_files": len(records),
        "total_tracked_files": len(files),
    }


def _format_bytes(value: object) -> str:
    if value is None:
        return "missing"
    size = int(value)
    if size >= BYTES_PER_MIB:
        return f"{size / BYTES_PER_MIB:.2f} MiB"
    if size >= 1024:
        return f"{size / 1024:.1f} KiB"
    return f"{size} B"


def build_markdown(plan: dict[str, object]) -> str:
    records = plan.get("records")
    candidate_records = records if isinstance(records, list) else []
    lines = [
        "# Source Boundary Cleanup Plan",
        "",
        f"- `contract_pass`: `{bool(plan.get('contract_pass'))}`",
        f"- `reason_code`: `{plan.get('reason_code', '')}`",
        f"- `total_tracked_files`: `{plan.get('total_tracked_files', 0)}`",
        f"- `total_candidate_files`: `{plan.get('total_candidate_files', 0)}`",
        f"- `total_candidate_bytes`: `{_format_bytes(plan.get('total_candidate_bytes', 0))}`",
        f"- `large_file_threshold_bytes`: `{plan.get('large_file_threshold_bytes', 0)}`",
        "",
        "## Counts By Bucket",
        "",
    ]
    counts = plan.get("counts_by_bucket")
    if isinstance(counts, dict) and counts:
        for bucket, count in sorted(counts.items()):
            lines.append(f"- `{bucket}`: `{count}`")
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Candidates",
            "",
            "| Path | Bytes | Buckets | Recommended Action |",
            "|---|---:|---|---|",
        ]
    )
    if candidate_records:
        for record in candidate_records:
            if not isinstance(record, dict):
                continue
            buckets = record.get("buckets")
            bucket_label = ", ".join(str(item) for item in buckets) if isinstance(buckets, list) else ""
            lines.append(
                "| "
                f"{record.get('path', '')} | "
                f"{_format_bytes(record.get('bytes'))} | "
                f"{bucket_label or 'none'} | "
                f"{record.get('recommended_action', '')} |"
            )
    else:
        lines.append("| none | 0 B | none | none |")
    return "\n".join(lines) + "\n"


def _write_pathspec(path: Path, records: list[dict[str, object]]) -> None:
    paths = [
        str(record["path"])
        for record in records
        if record["recommended_action"] == "remove_from_git"
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"{item}\n" for item in paths), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="print JSON diagnostics (default)")
    parser.add_argument(
        "--tracked-files",
        type=Path,
        help="read newline-separated tracked paths from a fixture instead of running git ls-files",
    )
    parser.add_argument(
        "--large-file-threshold-mib",
        type=float,
        default=DEFAULT_LARGE_FILE_THRESHOLD_MIB,
        help="classify tracked files at or above this size as large_file",
    )
    parser.add_argument(
        "--write-pathspec",
        type=Path,
        help="write remove_from_git paths for git rm --cached --pathspec-from-file",
    )
    parser.add_argument("--out", type=Path, help="write JSON diagnostics to a file")
    parser.add_argument("--out-md", type=Path, help="write Markdown diagnostics to a file")
    parser.add_argument(
        "--fail-on-candidates",
        action="store_true",
        help="return non-zero when any cleanup candidates are present",
    )
    args = parser.parse_args(argv)

    files = _read_tracked_files(args.tracked_files) if args.tracked_files else _git_files()
    plan = build_plan(files, large_file_threshold_mib=args.large_file_threshold_mib)
    if args.write_pathspec:
        _write_pathspec(args.write_pathspec, plan["records"])
    text = json.dumps(plan, indent=2, sort_keys=True)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    if args.out_md:
        args.out_md.parent.mkdir(parents=True, exist_ok=True)
        args.out_md.write_text(build_markdown(plan), encoding="utf-8")
    print(text)
    return 1 if args.fail_on_candidates and not bool(plan["contract_pass"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
