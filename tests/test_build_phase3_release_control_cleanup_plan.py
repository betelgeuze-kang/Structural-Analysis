from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts/build_phase3_release_control_cleanup_plan.py"
SRC_ROOT = REPO_ROOT / "src"
for candidate in (REPO_ROOT / "scripts", SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

spec = importlib.util.spec_from_file_location("build_phase3_release_control_cleanup_plan", SCRIPT_PATH)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def test_phase3_release_control_cleanup_plan_accepts_clean_git_clone_gate() -> None:
    payload = module.build_phase3_release_control_cleanup_plan(repo_root=REPO_ROOT)

    assert payload["status"] == "ready"
    assert payload["contract_pass"] is True
    assert payload["phase3_closure_claim"] is False
    assert payload["developer_preview_release_candidate_claim"] is False
    assert payload["codex_commit_or_push_performed"] is False
    assert payload["human_git_action_required"] is False
    assert payload["git_clean_clone_status"] == "pass"
    assert payload["git_clean_clone_contract_pass"] is True
    assert (
        payload["candidate_set_source"]
        == "phase3_benchmark_factory_seed_git_clean_clone_reproduction.release_control_cleanup_plan"
    )
    assert "not an exhaustive current-worktree" in payload["candidate_set_scope"]
    assert payload["current_worktree_diagnostics_included"] is False
    assert (
        payload["current_worktree_diagnostic_source"]
        == "product_readiness_snapshot.state_consistency.worktree"
    )
    candidate_paths = payload["candidate_release_control_commit_set"]
    track_or_add = payload["track_or_add_required_paths"]
    resolve_or_commit = payload["resolve_or_commit_dirty_tracked_paths"]
    assert candidate_paths == []
    assert track_or_add == []
    assert resolve_or_commit == []
    assert payload["candidate_release_control_commit_set_count"] == len(candidate_paths)
    assert candidate_paths == sorted({*track_or_add, *resolve_or_commit})
    assert payload["candidate_release_control_commit_set_count"] == len(track_or_add) + len(
        resolve_or_commit
    )
    assert payload["path_rows"] == sorted(payload["path_rows"], key=lambda row: row["path"])
    assert {row["path"] for row in payload["path_rows"]} == set(candidate_paths)
    assert {
        row["path"]
        for row in payload["path_rows"]
        if row["git_state"] == "untracked_or_missing_required"
    } == set(track_or_add)
    assert {
        row["path"]
        for row in payload["path_rows"]
        if row["git_state"] == "dirty_tracked"
    } == set(resolve_or_commit)
    assert sum(payload["path_role_counts"].values()) == len(candidate_paths)
    assert sum(payload["recommended_action_counts"].values()) == len(candidate_paths)
    for row in payload["path_rows"]:
        if row["git_state"] == "dirty_tracked":
            assert row["recommended_action"] == "resolve_or_commit_dirty_tracked_input"
        else:
            assert row["recommended_action"].startswith("track_")
    blocker_summary = payload["blocker_summary_by_role"]
    for role, summary in blocker_summary.items():
        untracked = summary["untracked_or_missing_paths"]
        dirty = summary["dirty_paths"]
        assert summary["blocker_count"] == len(untracked) + len(dirty)
        assert set(untracked).issubset(track_or_add)
        assert set(dirty).issubset(resolve_or_commit)
        for path in untracked:
            assert any(row["path"] == path and row["role"] == role for row in payload["path_rows"])
        for path in dirty:
            assert any(row["path"] == path and row["role"] == role for row in payload["path_rows"])
    handoff = payload["human_handoff"]
    assert handoff["status"] == "ready"
    assert handoff["codex_executed_commands"] is False
    assert handoff["remote_mutation_required"] is False
    assert handoff["push_or_release_command_included"] is False
    assert handoff["track_or_add_required_paths"] == payload["track_or_add_required_paths"]
    assert handoff["resolve_or_commit_dirty_tracked_paths"] == payload[
        "resolve_or_commit_dirty_tracked_paths"
    ]
    assert handoff["candidate_release_control_commit_set_count"] == len(candidate_paths)
    add_commands = [
        command
        for command in handoff["suggested_local_command_args"]
        if command[:3] == ["git", "add", "--"]
    ]
    if track_or_add:
        assert ["git", "add", "--", *track_or_add] in add_commands
    if resolve_or_commit:
        assert ["git", "add", "--", *resolve_or_commit] in add_commands
    assert not any(command[:2] == ["git", "push"] for command in handoff["suggested_local_command_args"])
    assert not any(command[:2] == ["gh", "release"] for command in handoff["suggested_local_command_args"])
    assert handoff["next_action"] == "rerun_git_clean_clone_reproduction"
    assert "does not commit" in payload["claim_boundary"]
    assert "not an exhaustive current-worktree dirty-path inventory" in payload["claim_boundary"]
    assert "Dirty tracked paths require owner review" in payload["claim_boundary"]


def test_phase3_release_control_cleanup_plan_check_detects_missing_output(tmp_path: Path) -> None:
    ok, message = module.check_phase3_release_control_cleanup_plan(
        repo_root=REPO_ROOT,
        out_path=tmp_path / "missing.json",
    )

    assert ok is False
    assert message.startswith("phase3_release_control_cleanup_plan_missing:")


def test_phase3_release_control_cleanup_plan_check_detects_drift(tmp_path: Path) -> None:
    out = tmp_path / "cleanup.json"
    module.write_phase3_release_control_cleanup_plan(repo_root=REPO_ROOT, out_path=out)
    payload = json.loads(out.read_text(encoding="utf-8"))
    payload["codex_commit_or_push_performed"] = True
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    ok, message = module.check_phase3_release_control_cleanup_plan(repo_root=REPO_ROOT, out_path=out)

    assert ok is False
    assert message == "phase3_release_control_cleanup_plan_mismatch"
