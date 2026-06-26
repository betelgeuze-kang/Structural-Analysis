from __future__ import annotations

import importlib.util
import shutil
import subprocess
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts/run_phase3_benchmark_factory_git_clean_clone_reproduction.py"
SRC_ROOT = REPO_ROOT / "src"
for candidate in (REPO_ROOT / "scripts", SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

spec = importlib.util.spec_from_file_location("run_phase3_benchmark_factory_git_clean_clone_reproduction", SCRIPT_PATH)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def _init_minimal_git_repo(repo_root: Path) -> None:
    subprocess.run(["git", "init"], cwd=repo_root, check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "config", "user.email", "phase3-test@example.com"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Phase 3 Test"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )


def _seed_clean_repo(repo_root: Path) -> str:
    for rel in module.REQUIRED_GIT_CLEAN_CLONE_INPUTS:
        src = REPO_ROOT / rel
        dst = repo_root / rel
        if not src.exists():
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)
    subprocess.run(["git", "add", "-A"], cwd=repo_root, check=True, capture_output=True, text=True)
    commit = subprocess.run(
        ["git", "commit", "-m", "seed phase3 git clean clone fixture"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    assert commit.returncode == 0
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo_root, text=True).strip()


def test_required_git_clean_clone_inputs_have_known_path_roles() -> None:
    for rel in module.REQUIRED_GIT_CLEAN_CLONE_INPUTS:
        role = module._required_path_role(rel)
        assert role in module.REQUIRED_PATH_ROLES


def test_required_path_blocker_summary_by_role_groups_blockers() -> None:
    preflight = {
        "untracked_or_missing_paths": [
            "scripts/build_phase3_benchmark_factory_artifacts.py",
            "implementation/phase1/release_evidence/productization/phase3_benchmark_factory_seed_manifest.json",
        ],
        "dirty_paths": ["pyproject.toml"],
    }
    path_roles = {
        "scripts/build_phase3_benchmark_factory_artifacts.py": module.PATH_ROLE_REPRODUCTION_BUILD_SCRIPT,
        "implementation/phase1/release_evidence/productization/phase3_benchmark_factory_seed_manifest.json": (
            module.PATH_ROLE_GENERATED_PRODUCTIZATION_EVIDENCE
        ),
        "pyproject.toml": module.PATH_ROLE_PACKAGE_CONFIG_CORE_PACKAGE,
    }

    summary = module._required_path_blocker_summary_by_role(preflight, path_roles)

    assert summary[module.PATH_ROLE_REPRODUCTION_BUILD_SCRIPT] == {
        "untracked_or_missing_paths": ["scripts/build_phase3_benchmark_factory_artifacts.py"],
        "dirty_paths": [],
        "blocker_count": 1,
    }
    assert summary[module.PATH_ROLE_GENERATED_PRODUCTIZATION_EVIDENCE]["blocker_count"] == 1
    assert summary[module.PATH_ROLE_PACKAGE_CONFIG_CORE_PACKAGE]["dirty_paths"] == ["pyproject.toml"]
    assert summary[module.PATH_ROLE_SOURCE_INPUT_REPORT]["blocker_count"] == 0
    assert summary[module.PATH_ROLE_FOCUSED_TEST]["blocker_count"] == 0


def test_git_preflight_blocks_untracked_required_path(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _init_minimal_git_repo(repo_root)
    tracked = repo_root / "pyproject.toml"
    shutil.copy2(REPO_ROOT / "pyproject.toml", tracked)
    untracked = repo_root / "scripts/build_phase3_benchmark_factory_artifacts.py"
    untracked.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(REPO_ROOT / "scripts/build_phase3_benchmark_factory_artifacts.py", untracked)
    subprocess.run(["git", "add", "pyproject.toml"], cwd=repo_root, check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "commit", "-m", "tracked only pyproject"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )

    preflight = module._preflight_git_clean_clone(
        repo_root,
        [Path("pyproject.toml"), Path("scripts/build_phase3_benchmark_factory_artifacts.py")],
    )

    assert preflight["pass"] is False
    assert "scripts/build_phase3_benchmark_factory_artifacts.py" in preflight["untracked_or_missing_paths"]
    assert "scripts/build_phase3_benchmark_factory_artifacts.py" not in preflight["dirty_paths"]
    assert any(blocker.startswith("required_path_not_tracked:") for blocker in preflight["blockers"])
    assert not any(blocker.startswith("required_path_has_uncommitted_changes:") for blocker in preflight["blockers"])
    action_summary = module._preflight_action_summary(preflight)
    assert action_summary["required_commit_or_add_path_count"] == 1
    assert action_summary["required_commit_or_add_paths"] == [
        "scripts/build_phase3_benchmark_factory_artifacts.py"
    ]
    assert action_summary["required_commit_or_add_role_counts"] == {
        module.PATH_ROLE_REPRODUCTION_BUILD_SCRIPT: 1
    }
    assert action_summary["required_commit_or_add_path_roles"] == [
        {
            "path": "scripts/build_phase3_benchmark_factory_artifacts.py",
            "role": module.PATH_ROLE_REPRODUCTION_BUILD_SCRIPT,
        }
    ]
    assert action_summary["required_dirty_tracked_path_count"] == 0
    assert action_summary["required_dirty_tracked_paths"] == []
    assert action_summary["required_dirty_tracked_role_counts"] == {}
    assert action_summary["required_dirty_tracked_path_roles"] == []
    assert action_summary["can_replay_from_git_head_without_local_worktree"] is False
    assert action_summary["next_action"] == "track_or_commit_required_inputs_then_rerun"


def test_git_preflight_blocks_dirty_required_path(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _init_minimal_git_repo(repo_root)
    tracked = repo_root / "pyproject.toml"
    shutil.copy2(REPO_ROOT / "pyproject.toml", tracked)
    subprocess.run(["git", "add", "pyproject.toml"], cwd=repo_root, check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "commit", "-m", "tracked pyproject"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    tracked.write_text(tracked.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    preflight = module._preflight_git_clean_clone(repo_root, [Path("pyproject.toml")])

    assert preflight["pass"] is False
    assert "pyproject.toml" in preflight["dirty_paths"]
    assert any(blocker.startswith("required_path_has_uncommitted_changes:") for blocker in preflight["blockers"])


def test_git_clean_clone_reproduction_runs_local_clone_replay(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _init_minimal_git_repo(repo_root)
    source_commit = _seed_clean_repo(repo_root)
    bundle_path = (
        repo_root
        / "implementation/phase1/release_evidence/productization/phase3_benchmark_factory_seed_reproducibility_bundle.json"
    )

    payload = module.build_phase3_git_clean_clone_reproduction(
        repo_root=repo_root,
        bundle_path=bundle_path,
        source_commit_sha=source_commit,
    )

    assert payload["status"] == "pass"
    assert payload["contract_pass"] is True
    assert payload["git_clean_clone_preflight_pass"] is True
    assert payload["git_clean_clone_executed"] is True
    assert payload["git_clean_clone_execution_mode"] == "local_git_clone_no_local"
    assert payload["phase3_closure_claim"] is False
    assert payload["developer_preview_release_candidate_claim"] is False
    assert all(
        payload["required_input_path_roles"][path] in module.REQUIRED_PATH_ROLES
        for path in payload["required_git_clean_clone_inputs"]
    )
    assert payload["required_path_blocker_summary_by_role"][module.PATH_ROLE_FOCUSED_TEST]["blocker_count"] == 0
    assert payload["release_control_cleanup_plan"]["status"] == "ready"
    assert payload["release_control_cleanup_plan"]["codex_commit_or_push_performed"] is False
    assert payload["release_control_cleanup_plan"]["human_git_action_required"] is False
    assert payload["release_control_cleanup_plan"]["git_clean_clone_gate_can_pass_after_cleanup"] is True
    assert payload["release_control_cleanup_plan"]["candidate_release_control_commit_set"] == []
    assert payload["release_control_cleanup_plan"]["candidate_release_control_commit_set_count"] == 0
    assert payload["stable_artifact_checksums_match"] is True
    assert payload["generated_stable_artifact_checksums"] == payload["expected_stable_artifact_checksums"]
    assert payload["preflight_action_summary"]["required_commit_or_add_path_count"] == 0
    assert payload["preflight_action_summary"]["required_commit_or_add_paths"] == []
    assert payload["preflight_action_summary"]["required_commit_or_add_role_counts"] == {}
    assert payload["preflight_action_summary"]["required_commit_or_add_path_roles"] == []
    assert payload["preflight_action_summary"]["required_dirty_tracked_path_count"] == 0
    assert payload["preflight_action_summary"]["required_dirty_tracked_paths"] == []
    assert payload["preflight_action_summary"]["required_dirty_tracked_role_counts"] == {}
    assert payload["preflight_action_summary"]["required_dirty_tracked_path_roles"] == []
    assert payload["preflight_action_summary"]["can_replay_from_git_head_without_local_worktree"] is True
    assert payload["preflight_action_summary"]["next_action"] == "rerun_git_clean_clone_reproduction"
    assert len(payload["command_results"]) >= 1
    assert all(row["return_code"] == 0 for row in payload["command_results"])
    assert "not Linux/Windows parity" in payload["claim_boundary"]
    assert "not full Phase 3 closure" in payload["claim_boundary"]


def test_git_clean_clone_reproduction_blocks_when_preflight_fails(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _init_minimal_git_repo(repo_root)
    source_commit = _seed_clean_repo(repo_root)
    dirty_target = repo_root / "scripts/build_phase3_benchmark_factory_artifacts.py"
    dirty_target.write_text(dirty_target.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    bundle_path = (
        repo_root
        / "implementation/phase1/release_evidence/productization/phase3_benchmark_factory_seed_reproducibility_bundle.json"
    )

    payload = module.build_phase3_git_clean_clone_reproduction(
        repo_root=repo_root,
        bundle_path=bundle_path,
        source_commit_sha=source_commit,
    )

    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is False
    assert payload["git_clean_clone_preflight_pass"] is False
    assert payload["git_clean_clone_executed"] is False
    assert payload["command_results"] == []
    assert payload["required_path_blocker_summary_by_role"][module.PATH_ROLE_REPRODUCTION_BUILD_SCRIPT][
        "dirty_paths"
    ] == ["scripts/build_phase3_benchmark_factory_artifacts.py"]
    assert (
        payload["required_path_blocker_summary_by_role"][module.PATH_ROLE_REPRODUCTION_BUILD_SCRIPT][
            "blocker_count"
        ]
        == 1
    )
    cleanup_plan = payload["release_control_cleanup_plan"]
    assert cleanup_plan["status"] == "blocked"
    assert cleanup_plan["codex_commit_or_push_performed"] is False
    assert cleanup_plan["human_git_action_required"] is True
    assert cleanup_plan["git_clean_clone_gate_can_pass_after_cleanup"] is False
    assert cleanup_plan["candidate_release_control_commit_set"] == [
        "scripts/build_phase3_benchmark_factory_artifacts.py"
    ]
    assert cleanup_plan["candidate_release_control_commit_set_count"] == 1
    assert cleanup_plan["track_or_add_required_paths"] == []
    assert cleanup_plan["resolve_or_commit_dirty_tracked_paths"] == [
        "scripts/build_phase3_benchmark_factory_artifacts.py"
    ]
    assert cleanup_plan["blocker_summary_by_role"] == payload["required_path_blocker_summary_by_role"]
    assert "Codex did not commit" in cleanup_plan["claim_boundary"]
    assert payload["preflight_action_summary"]["required_commit_or_add_path_count"] == 0
    assert payload["preflight_action_summary"]["required_dirty_tracked_path_count"] == 1
    assert payload["preflight_action_summary"]["required_dirty_tracked_paths"] == [
        "scripts/build_phase3_benchmark_factory_artifacts.py"
    ]
    assert payload["preflight_action_summary"]["required_dirty_tracked_role_counts"] == {
        module.PATH_ROLE_REPRODUCTION_BUILD_SCRIPT: 1
    }
    assert payload["preflight_action_summary"]["required_dirty_tracked_path_roles"] == [
        {
            "path": "scripts/build_phase3_benchmark_factory_artifacts.py",
            "role": module.PATH_ROLE_REPRODUCTION_BUILD_SCRIPT,
        }
    ]
    assert payload["preflight_action_summary"]["can_replay_from_git_head_without_local_worktree"] is False
    assert (
        payload["preflight_action_summary"]["next_action"]
        == "resolve_or_commit_dirty_required_inputs_then_rerun"
    )
    assert any(
        blocker.startswith("required_path_has_uncommitted_changes:")
        for blocker in payload["blockers"]
    )
