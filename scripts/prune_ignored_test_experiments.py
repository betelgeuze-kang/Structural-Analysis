#!/usr/bin/env python3
"""Prune old ignored test runs without racing an active writer."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXPERIMENT_ROOT = Path("implementation/phase1/experiments/by_test")
RUN_DIR_PATTERN = re.compile(r"^[0-9]{8}T[0-9]{6}Z$")


@dataclass(frozen=True)
class TreeStats:
    byte_count: int
    latest_mtime_ns: int


def _resolved(repo_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def _relative(repo_root: Path, path: Path) -> str:
    return path.resolve().relative_to(repo_root.resolve()).as_posix()


def _tree_stats(path: Path) -> TreeStats:
    byte_count = 0
    latest_mtime_ns = path.lstat().st_mtime_ns
    for current_root, directories, files in os.walk(path, followlinks=False):
        root = Path(current_root)
        for name in directories:
            current = root / name
            stat = current.lstat()
            latest_mtime_ns = max(latest_mtime_ns, stat.st_mtime_ns)
        for name in files:
            current = root / name
            stat = current.lstat()
            latest_mtime_ns = max(latest_mtime_ns, stat.st_mtime_ns)
            byte_count += stat.st_size
    return TreeStats(byte_count=byte_count, latest_mtime_ns=latest_mtime_ns)


def _git_safety_blockers(repo_root: Path, experiment_root: Path) -> list[str]:
    try:
        relative = _relative(repo_root, experiment_root)
    except ValueError:
        return ["experiment_root_outside_repository"]
    ignored = subprocess.run(
        ["git", "check-ignore", "-q", "--", relative],
        cwd=repo_root,
        check=False,
    ).returncode == 0
    tracked = subprocess.run(
        ["git", "ls-files", "--", relative],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    blockers: list[str] = []
    if not ignored:
        blockers.append("experiment_root_not_git_ignored")
    if tracked:
        blockers.append("experiment_root_contains_tracked_files")
    return blockers


def _latest_manifest_run(
    gate_dir: Path, repo_root: Path
) -> tuple[Path | None, str | None]:
    manifest = gate_dir / "latest_manifest.json"
    if not manifest.is_file():
        return None, None
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None, f"latest_manifest_invalid:{gate_dir.name}"
    value = payload.get("latest_run_dir") if isinstance(payload, dict) else None
    if not isinstance(value, str) or not value:
        return None, f"latest_manifest_run_missing:{gate_dir.name}"
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = repo_root / candidate
    candidate = candidate.resolve()
    try:
        candidate.relative_to(gate_dir.resolve())
    except ValueError:
        return None, f"latest_manifest_target_outside_gate:{gate_dir.name}"
    if not RUN_DIR_PATTERN.fullmatch(candidate.name):
        return None, f"latest_manifest_target_invalid:{gate_dir.name}"
    if not candidate.is_dir():
        return None, f"latest_manifest_target_missing:{gate_dir.name}"
    return candidate, None


def build_cleanup_plan(
    *,
    repo_root: Path = ROOT,
    experiment_root: Path = DEFAULT_EXPERIMENT_ROOT,
    keep_runs_per_gate: int = 2,
    minimum_idle_seconds: int = 300,
    now: datetime | None = None,
) -> dict[str, Any]:
    if keep_runs_per_gate < 1:
        raise ValueError("keep_runs_per_gate_must_be_positive")
    if minimum_idle_seconds < 0:
        raise ValueError("minimum_idle_seconds_must_be_nonnegative")
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("now_must_be_timezone_aware")
    root = _resolved(repo_root, experiment_root).resolve()
    blockers = _git_safety_blockers(repo_root, root)
    if not root.is_dir():
        blockers.append("experiment_root_missing")
        return {
            "schema_version": "ignored-test-experiment-cleanup-plan.v1",
            "status": "blocked",
            "experiment_root": str(root),
            "keep_runs_per_gate": keep_runs_per_gate,
            "minimum_idle_seconds": minimum_idle_seconds,
            "observed_idle_seconds": None,
            "preserved_runs": [],
            "candidates": [],
            "candidate_count": 0,
            "candidate_bytes": 0,
            "blockers": sorted(set(blockers)),
        }

    run_rows: list[tuple[Path, TreeStats]] = []
    preserved: set[Path] = set()
    for gate_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        timestamp_entries = [
            path
            for path in gate_dir.iterdir()
            if RUN_DIR_PATTERN.fullmatch(path.name)
        ]
        for path in timestamp_entries:
            if path.is_symlink():
                blockers.append(
                    f"timestamp_run_symlink:{_relative(repo_root, path)}"
                )
        runs = sorted(
            path.resolve()
            for path in timestamp_entries
            if path.is_dir() and not path.is_symlink()
        )
        preserved.update(runs[-keep_runs_per_gate:])
        latest, latest_blocker = _latest_manifest_run(gate_dir, repo_root)
        if latest_blocker is not None:
            blockers.append(latest_blocker)
        if latest is not None:
            preserved.add(latest)
        run_rows.extend((path, _tree_stats(path)) for path in runs)

    root_stats = _tree_stats(root)
    newest_mtime_ns = root_stats.latest_mtime_ns
    observed_idle_seconds = max(
        0.0, current.timestamp() - newest_mtime_ns / 1_000_000_000
    )
    if observed_idle_seconds < minimum_idle_seconds:
        blockers.append("recent_experiment_activity")

    candidates = [
        {
            "path": _relative(repo_root, path),
            "byte_count": stats.byte_count,
            "latest_mtime_ns": stats.latest_mtime_ns,
        }
        for path, stats in run_rows
        if path not in preserved
    ]
    return {
        "schema_version": "ignored-test-experiment-cleanup-plan.v1",
        "status": "ready" if not blockers else "blocked",
        "experiment_root": _relative(repo_root, root),
        "keep_runs_per_gate": keep_runs_per_gate,
        "minimum_idle_seconds": minimum_idle_seconds,
        "observed_idle_seconds": observed_idle_seconds,
        "newest_activity_mtime_ns": newest_mtime_ns,
        "preserved_runs": sorted(_relative(repo_root, path) for path in preserved),
        "candidates": candidates,
        "candidate_count": len(candidates),
        "candidate_bytes": sum(int(row["byte_count"]) for row in candidates),
        "blockers": sorted(set(blockers)),
    }


def apply_cleanup_plan(
    plan: dict[str, Any], *, repo_root: Path = ROOT
) -> dict[str, Any]:
    if plan.get("status") != "ready" or plan.get("blockers"):
        raise ValueError("cleanup_plan_not_ready")
    candidates = plan.get("candidates")
    if not isinstance(candidates, list):
        raise ValueError("cleanup_plan_candidates_invalid")
    resolved: list[tuple[Path, TreeStats]] = []
    experiment_root = _resolved(
        repo_root, Path(str(plan["experiment_root"]))
    ).resolve()
    if _git_safety_blockers(repo_root, experiment_root):
        raise ValueError("cleanup_git_safety_changed_after_plan")
    current_root_stats = _tree_stats(experiment_root)
    if current_root_stats.latest_mtime_ns != plan.get("newest_activity_mtime_ns"):
        raise ValueError("experiment_activity_changed_after_plan")
    preserved = {
        _resolved(repo_root, Path(str(path))).resolve()
        for path in plan.get("preserved_runs", [])
    }
    for row in candidates:
        if not isinstance(row, dict):
            raise ValueError("cleanup_plan_candidate_invalid")
        path = _resolved(repo_root, Path(str(row.get("path") or ""))).resolve()
        try:
            path.relative_to(experiment_root)
        except ValueError as exc:
            raise ValueError("cleanup_candidate_outside_experiment_root") from exc
        if (
            not path.is_dir()
            or path.is_symlink()
            or not RUN_DIR_PATTERN.fullmatch(path.name)
        ):
            raise ValueError("cleanup_candidate_not_timestamp_directory")
        if path in preserved:
            raise ValueError("cleanup_candidate_is_preserved")
        stats = _tree_stats(path)
        if (
            stats.byte_count != row.get("byte_count")
            or stats.latest_mtime_ns != row.get("latest_mtime_ns")
        ):
            raise ValueError("experiment_activity_changed_after_plan")
        resolved.append((path, stats))
    for path, _stats in resolved:
        shutil.rmtree(path)
    result = dict(plan)
    result.update(
        {
            "schema_version": "ignored-test-experiment-cleanup-result.v1",
            "status": "applied",
            "deleted_count": len(resolved),
            "deleted_bytes": sum(stats.byte_count for _path, stats in resolved),
        }
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--experiment-root", type=Path, default=DEFAULT_EXPERIMENT_ROOT)
    parser.add_argument("--keep-runs-per-gate", type=int, default=2)
    parser.add_argument("--minimum-idle-seconds", type=int, default=300)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    plan = build_cleanup_plan(
        repo_root=args.repo_root,
        experiment_root=args.experiment_root,
        keep_runs_per_gate=args.keep_runs_per_gate,
        minimum_idle_seconds=args.minimum_idle_seconds,
    )
    result = plan
    if args.apply:
        try:
            result = apply_cleanup_plan(plan, repo_root=args.repo_root)
        except ValueError as exc:
            result = {**plan, "status": "blocked", "apply_error": str(exc)}
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            f"ignored experiment cleanup: {result['status']} | "
            f"candidates={result['candidate_count']} | "
            f"bytes={result['candidate_bytes']}"
        )
        for blocker in result.get("blockers", []):
            print(f"- {blocker}")
        if result.get("apply_error"):
            print(f"- {result['apply_error']}")
    return 0 if result.get("status") in {"ready", "applied"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
