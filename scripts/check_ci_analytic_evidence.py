#!/usr/bin/env python3
"""Diagnose strict analytic replay and evidence changes without rewriting inputs."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACT = Path(
    "implementation/phase1/release_evidence/productization/"
    "analytic_frame_verification.json"
)
REPORT_VERSION = "ci-analytic-evidence-audit.v1"
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _snapshot(repo_root: Path, relative_paths: list[str]) -> dict[str, str]:
    root = repo_root.resolve()
    result = {}
    for name in sorted(set(relative_paths)):
        candidate = (root / name).resolve()
        if Path(name).is_absolute() or not candidate.is_relative_to(root):
            result[name] = "outside_repository"
            continue
        try:
            result[name] = _file_hash(candidate)
        except OSError as exc:
            result[name] = f"unreadable:{type(exc).__name__}"
    return result


def _changes(before: dict[str, str], after: dict[str, str]) -> list[dict[str, Any]]:
    return [
        {"path": name, "before": before.get(name), "after": after.get(name)}
        for name in sorted(before.keys() | after.keys())
        if before.get(name) != after.get(name)
    ]


def audit(repo_root: Path, baseline: dict[str, Any] | None = None) -> dict[str, Any]:
    from structural_analysis.benchmark.analytic_frame import (
        _SOURCE_PATHS,
        validate_analytic_frame_verification_artifact,
    )

    root = repo_root.resolve()
    paths = [path.as_posix() for path in _SOURCE_PATHS]
    paths.append(DEFAULT_ARTIFACT.as_posix())
    before = _snapshot(root, paths)
    error = None
    try:
        payload = json.loads((root / DEFAULT_ARTIFACT).read_text(encoding="utf-8"))
        validate_analytic_frame_verification_artifact(
            payload, repo_root=root, require_current_sources=True, rerun=True
        )
    except Exception as exc:
        # Emit a diagnostic and FAIL; never substitute a rebuilt receipt.
        error = f"{type(exc).__name__}:{exc}"
    after = _snapshot(root, paths)
    replay_changes = _changes(before, after)
    baseline_error = None
    baseline_changes = []
    if baseline is not None:
        if (
            baseline.get("schema_version") != REPORT_VERSION
            or baseline.get("audit_passed") is not True
            or not isinstance(baseline.get("files"), dict)
            or not baseline["files"]
            or not all(isinstance(k, str) and isinstance(v, str)
                       for k, v in baseline["files"].items())
        ):
            baseline_error = "invalid_or_failed_baseline"
        else:
            baseline_changes = _changes(baseline["files"], before)
    return {
        "schema_version": REPORT_VERSION,
        "audit_passed": not (error or replay_changes or baseline_error or baseline_changes),
        "validation_error": error,
        "changes_during_replay": replay_changes,
        "baseline_error": baseline_error,
        "changes_since_baseline": baseline_changes,
        "files": after,
        "release_authority": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    baseline = None
    if args.baseline is not None:
        try:
            baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
            if not isinstance(baseline, dict):
                baseline = {}
        except (OSError, ValueError):
            baseline = {}
    report = audit(args.repo_root, baseline)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=args.repo_root,
        capture_output=True, text=True, check=False,
    )
    report["checkout_sha"] = head.stdout.strip() if head.returncode == 0 else None
    report["github_sha"] = os.environ.get("GITHUB_SHA")
    report["python_version"] = sys.version
    text = json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True) + "\n"
    print(text, end="")
    if args.out is not None:
        output = args.out.resolve()
        protected = [(args.repo_root / name).resolve() for name in report["files"]]
        if output in protected:
            raise ValueError("audit_output_would_overwrite_evidence_or_source")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
    return 0 if report["audit_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
