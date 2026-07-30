from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "prune_ignored_test_experiments.py"
SPEC = importlib.util.spec_from_file_location(
    "prune_ignored_test_experiments_tests", SCRIPT
)
assert SPEC is not None and SPEC.loader is not None
pruner = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = pruner
SPEC.loader.exec_module(pruner)


def _repo(tmp_path: Path) -> tuple[Path, Path]:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / ".gitignore").write_text("experiments/\n", encoding="utf-8")
    root = tmp_path / "experiments" / "by_test"
    root.mkdir(parents=True)
    return tmp_path, root


def _run(
    root: Path, gate: str, name: str, *, timestamp: int, size: int = 16
) -> Path:
    target = root / gate / name
    target.mkdir(parents=True)
    payload = target / "payload.bin"
    payload.write_bytes(b"x" * size)
    for path in (payload, target):
        os.utime(path, ns=(timestamp * 1_000_000_000,) * 2)
    return target


def _now(timestamp: int = 4_000_000_000) -> datetime:
    return datetime.fromtimestamp(timestamp, tz=timezone.utc)


def test_plan_preserves_retention_and_latest_manifest_target(tmp_path: Path) -> None:
    repo, root = _repo(tmp_path)
    runs = [
        _run(root, "gate", f"20260101T00000{index}Z", timestamp=1_000 + index)
        for index in range(1, 5)
    ]
    latest_manifest = root / "gate" / "latest_manifest.json"
    latest_manifest.write_text(
        json.dumps(
            {
                "latest_run_dir": runs[2].relative_to(repo).as_posix(),
            }
        ),
        encoding="utf-8",
    )
    os.utime(latest_manifest, ns=(1_100 * 1_000_000_000,) * 2)

    plan = pruner.build_cleanup_plan(
        repo_root=repo,
        experiment_root=root,
        keep_runs_per_gate=1,
        minimum_idle_seconds=300,
        now=_now(),
    )

    assert plan["status"] == "ready"
    assert plan["candidate_count"] == 2
    assert [Path(row["path"]).name for row in plan["candidates"]] == [
        runs[0].name,
        runs[1].name,
    ]
    assert {Path(path).name for path in plan["preserved_runs"]} == {
        runs[2].name,
        runs[3].name,
    }


def test_plan_blocks_recent_activity(tmp_path: Path) -> None:
    repo, root = _repo(tmp_path)
    _run(root, "gate", "20260101T000001Z", timestamp=3_999_999_990)

    plan = pruner.build_cleanup_plan(
        repo_root=repo,
        experiment_root=root,
        minimum_idle_seconds=300,
        now=_now(),
    )

    assert plan["status"] == "blocked"
    assert "recent_experiment_activity" in plan["blockers"]


def test_plan_blocks_tracked_experiment_files(tmp_path: Path) -> None:
    repo, root = _repo(tmp_path)
    run = _run(root, "gate", "20260101T000001Z", timestamp=1_000)
    subprocess.run(
        ["git", "add", "-f", str((run / "payload.bin").relative_to(repo))],
        cwd=repo,
        check=True,
    )

    plan = pruner.build_cleanup_plan(
        repo_root=repo,
        experiment_root=root,
        minimum_idle_seconds=0,
        now=_now(),
    )

    assert plan["status"] == "blocked"
    assert "experiment_root_contains_tracked_files" in plan["blockers"]


def test_apply_deletes_only_planned_old_runs(tmp_path: Path) -> None:
    repo, root = _repo(tmp_path)
    old = _run(root, "gate", "20260101T000001Z", timestamp=1_000, size=32)
    kept = _run(root, "gate", "20260101T000002Z", timestamp=1_001, size=64)

    plan = pruner.build_cleanup_plan(
        repo_root=repo,
        experiment_root=root,
        keep_runs_per_gate=1,
        minimum_idle_seconds=300,
        now=_now(),
    )
    result = pruner.apply_cleanup_plan(plan, repo_root=repo)

    assert result["status"] == "applied"
    assert result["deleted_count"] == 1
    assert result["deleted_bytes"] == 32
    assert not old.exists()
    assert kept.is_dir()


def test_apply_rejects_candidate_activity_after_plan(tmp_path: Path) -> None:
    repo, root = _repo(tmp_path)
    old = _run(root, "gate", "20260101T000001Z", timestamp=1_000)
    _run(root, "gate", "20260101T000002Z", timestamp=1_001)
    plan = pruner.build_cleanup_plan(
        repo_root=repo,
        experiment_root=root,
        keep_runs_per_gate=1,
        minimum_idle_seconds=300,
        now=_now(),
    )
    (old / "late-write.txt").write_text("changed", encoding="utf-8")

    with pytest.raises(ValueError, match="experiment_activity_changed_after_plan"):
        pruner.apply_cleanup_plan(plan, repo_root=repo)

    assert old.is_dir()


def test_apply_rejects_new_run_created_after_plan(tmp_path: Path) -> None:
    repo, root = _repo(tmp_path)
    old = _run(root, "gate", "20260101T000001Z", timestamp=1_000)
    _run(root, "gate", "20260101T000002Z", timestamp=1_001)
    plan = pruner.build_cleanup_plan(
        repo_root=repo,
        experiment_root=root,
        keep_runs_per_gate=1,
        minimum_idle_seconds=300,
        now=_now(),
    )
    _run(root, "gate", "20260101T000003Z", timestamp=3_999_999_500)

    with pytest.raises(ValueError, match="experiment_activity_changed_after_plan"):
        pruner.apply_cleanup_plan(plan, repo_root=repo)

    assert old.is_dir()


def test_invalid_latest_manifest_blocks_cleanup(tmp_path: Path) -> None:
    repo, root = _repo(tmp_path)
    _run(root, "gate", "20260101T000001Z", timestamp=1_000)
    manifest = root / "gate" / "latest_manifest.json"
    manifest.write_text("{not-json", encoding="utf-8")
    os.utime(manifest, ns=(1_100 * 1_000_000_000,) * 2)

    plan = pruner.build_cleanup_plan(
        repo_root=repo,
        experiment_root=root,
        minimum_idle_seconds=300,
        now=_now(),
    )

    assert plan["status"] == "blocked"
    assert "latest_manifest_invalid:gate" in plan["blockers"]
