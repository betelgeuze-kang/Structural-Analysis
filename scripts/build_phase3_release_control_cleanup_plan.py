#!/usr/bin/env python3
"""Build the Phase 3 release-control cleanup plan from git-clean-clone evidence."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
for candidate in (SCRIPT_DIR, SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from release_evidence_metadata import git_head, input_checksums  # noqa: E402


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_GIT_CLEAN_CLONE_RECEIPT = (
    PRODUCTIZATION / "phase3_benchmark_factory_seed_git_clean_clone_reproduction.json"
)
DEFAULT_OUT = PRODUCTIZATION / "phase3_release_control_cleanup_plan.json"
CLEANUP_CANDIDATE_SET_SOURCE = (
    "phase3_benchmark_factory_seed_git_clean_clone_reproduction."
    "release_control_cleanup_plan"
)
CLEANUP_CANDIDATE_SET_SCOPE = (
    "Phase 3 seed git-clean-clone reproduction required-input set only; "
    "it is not an exhaustive current-worktree dirty-path inventory."
)


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _strip_volatile(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {
            key: _strip_volatile(value)
            for key, value in payload.items()
            if key not in {"generated_at"}
        }
    if isinstance(payload, list):
        return [_strip_volatile(item) for item in payload]
    return payload


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object.")
    return payload


def _decision_for_path(path: str, role: str, *, dirty: bool) -> str:
    if dirty:
        return "resolve_or_commit_dirty_tracked_input"
    if role == "generated_productization_evidence":
        return "track_generated_productization_evidence"
    if role == "reproduction_build_script":
        return "track_reproduction_builder_or_runner"
    if role == "focused_test":
        return "track_focused_regression_test"
    if role == "package_config_core_package":
        return "track_package_config_or_core_package"
    if role == "source_input_report":
        return "track_source_input_or_report"
    return "classify_before_tracking"


def _path_rows(cleanup_plan: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    dirty_paths = set(cleanup_plan.get("resolve_or_commit_dirty_tracked_paths") or [])
    role_by_path: dict[str, str] = {}
    for role, summary in (cleanup_plan.get("blocker_summary_by_role") or {}).items():
        if not isinstance(summary, dict):
            continue
        for key in ("untracked_or_missing_paths", "dirty_paths"):
            for path in summary.get(key) or []:
                role_by_path[str(path)] = str(role)
    for path in cleanup_plan.get("candidate_release_control_commit_set") or []:
        path = str(path)
        role = role_by_path.get(path, "unknown_required_input")
        dirty = path in dirty_paths
        rows.append(
            {
                "path": path,
                "role": role,
                "git_state": "dirty_tracked" if dirty else "untracked_or_missing_required",
                "recommended_action": _decision_for_path(path, role, dirty=dirty),
            }
        )
    return sorted(rows, key=lambda row: row["path"])


def _paths_by_git_state(path_rows: list[dict[str, Any]]) -> dict[str, list[str]]:
    track_or_add = [
        str(row["path"])
        for row in path_rows
        if row.get("git_state") == "untracked_or_missing_required"
    ]
    resolve_or_commit = [
        str(row["path"])
        for row in path_rows
        if row.get("git_state") == "dirty_tracked"
    ]
    return {
        "track_or_add_required_paths": sorted(track_or_add),
        "resolve_or_commit_dirty_tracked_paths": sorted(resolve_or_commit),
    }


def _human_handoff(path_rows: list[dict[str, Any]], verification_commands: list[Any]) -> dict[str, Any]:
    paths_by_state = _paths_by_git_state(path_rows)
    track_or_add = paths_by_state["track_or_add_required_paths"]
    resolve_or_commit = paths_by_state["resolve_or_commit_dirty_tracked_paths"]
    candidate_paths = sorted({*track_or_add, *resolve_or_commit})
    command_args: list[list[str]] = []
    if track_or_add:
        command_args.append(["git", "add", "--", *track_or_add])
    if resolve_or_commit:
        command_args.append(["git", "add", "--", *resolve_or_commit])
    if candidate_paths:
        command_args.append(["git", "status", "--short", "--", *candidate_paths])
    command_args.extend(
        ["bash", "-lc", str(command)]
        for command in verification_commands
        if str(command).strip()
    )
    return {
        "status": "blocked_until_human_git_action" if candidate_paths else "ready",
        "codex_executed_commands": False,
        "remote_mutation_required": False,
        "push_or_release_command_included": False,
        "track_or_add_required_paths": track_or_add,
        "resolve_or_commit_dirty_tracked_paths": resolve_or_commit,
        "candidate_release_control_commit_set": candidate_paths,
        "candidate_release_control_commit_set_count": len(candidate_paths),
        "suggested_local_command_args": command_args,
        "suggested_commit_message": (
            "Track Phase 3 benchmark factory release-control evidence"
            if candidate_paths
            else ""
        ),
        "next_action": (
            "owner_review_then_track_or_commit_required_inputs"
            if candidate_paths
            else "rerun_git_clean_clone_reproduction"
        ),
        "claim_boundary": (
            "These command argv arrays are a human handoff only. Codex did not run git add, "
            "commit, push, release, or mutate remote state. The owner must review dirty tracked "
            "inputs before staging them."
        ),
    }


def build_phase3_release_control_cleanup_plan(
    *,
    repo_root: Path = ROOT,
    git_clean_clone_receipt: Path = DEFAULT_GIT_CLEAN_CLONE_RECEIPT,
    source_commit_sha: str | None = None,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    receipt_path = git_clean_clone_receipt if git_clean_clone_receipt.is_absolute() else repo_root / git_clean_clone_receipt
    git_receipt = _load_json(receipt_path)
    cleanup_plan = git_receipt.get("release_control_cleanup_plan")
    cleanup_plan = cleanup_plan if isinstance(cleanup_plan, dict) else {}
    path_rows = _path_rows(cleanup_plan)
    paths_by_state = _paths_by_git_state(path_rows)
    role_counts: dict[str, int] = {}
    action_counts: dict[str, int] = {}
    for row in path_rows:
        role_counts[row["role"]] = role_counts.get(row["role"], 0) + 1
        action_counts[row["recommended_action"]] = action_counts.get(row["recommended_action"], 0) + 1
    git_gate_blocked = git_receipt.get("status") != "pass"
    candidate_release_control_commit_set = sorted(
        row["path"] for row in path_rows
    )
    next_verification_commands = cleanup_plan.get("next_verification_commands", [])
    next_verification_commands = (
        next_verification_commands
        if isinstance(next_verification_commands, list)
        else []
    )
    return {
        "schema_version": "phase3-release-control-cleanup-plan.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit_sha": source_commit_sha or git_head(repo_root),
        "status": "blocked" if git_gate_blocked else "ready",
        "contract_pass": not git_gate_blocked and not path_rows,
        "phase3_closure_claim": False,
        "developer_preview_release_candidate_claim": False,
        "codex_commit_or_push_performed": False,
        "human_git_action_required": bool(path_rows),
        "git_clean_clone_receipt_path": str(git_clean_clone_receipt),
        "git_clean_clone_status": git_receipt.get("status"),
        "git_clean_clone_contract_pass": bool(git_receipt.get("contract_pass")),
        "candidate_set_source": CLEANUP_CANDIDATE_SET_SOURCE,
        "candidate_set_scope": CLEANUP_CANDIDATE_SET_SCOPE,
        "current_worktree_diagnostics_included": False,
        "current_worktree_diagnostic_source": (
            "product_readiness_snapshot.state_consistency.worktree"
        ),
        "candidate_release_control_commit_set_count": len(path_rows),
        "candidate_release_control_commit_set": candidate_release_control_commit_set,
        "track_or_add_required_paths": paths_by_state["track_or_add_required_paths"],
        "resolve_or_commit_dirty_tracked_paths": paths_by_state[
            "resolve_or_commit_dirty_tracked_paths"
        ],
        "path_role_counts": dict(sorted(role_counts.items())),
        "recommended_action_counts": dict(sorted(action_counts.items())),
        "path_rows": path_rows,
        "blocker_summary_by_role": cleanup_plan.get("blocker_summary_by_role", {}),
        "next_verification_commands": next_verification_commands,
        "human_handoff": _human_handoff(path_rows, next_verification_commands),
        "input_checksums": input_checksums(
            [
                Path("scripts/build_phase3_release_control_cleanup_plan.py"),
                git_clean_clone_receipt,
            ],
            repo_root=repo_root,
        ),
        "claim_boundary": (
            "This receipt organizes local Git cleanup needed for Phase 3 seed git-clean-clone "
            "replay. Its candidate set is not an exhaustive current-worktree dirty-path inventory; "
            "the product readiness snapshot carries the current-worktree diagnostic separately. "
            "It does not commit, push, release, promote Developer Preview readiness, or close "
            "Phase 3. Dirty tracked paths require owner review before they are bundled with the "
            "release-control evidence set."
        ),
    }


def write_phase3_release_control_cleanup_plan(
    *,
    repo_root: Path = ROOT,
    out_path: Path = DEFAULT_OUT,
    git_clean_clone_receipt: Path = DEFAULT_GIT_CLEAN_CLONE_RECEIPT,
    source_commit_sha: str | None = None,
) -> dict[str, Any]:
    payload = build_phase3_release_control_cleanup_plan(
        repo_root=repo_root,
        git_clean_clone_receipt=git_clean_clone_receipt,
        source_commit_sha=source_commit_sha,
    )
    resolved = out_path if out_path.is_absolute() else repo_root / out_path
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(_json_text(payload), encoding="utf-8")
    return payload


def check_phase3_release_control_cleanup_plan(
    *,
    repo_root: Path = ROOT,
    out_path: Path = DEFAULT_OUT,
    git_clean_clone_receipt: Path = DEFAULT_GIT_CLEAN_CLONE_RECEIPT,
    source_commit_sha: str | None = None,
) -> tuple[bool, str]:
    expected = build_phase3_release_control_cleanup_plan(
        repo_root=repo_root,
        git_clean_clone_receipt=git_clean_clone_receipt,
        source_commit_sha=source_commit_sha,
    )
    resolved = out_path if out_path.is_absolute() else repo_root / out_path
    if not resolved.exists():
        return False, f"phase3_release_control_cleanup_plan_missing:{out_path.as_posix()}"
    try:
        existing = _load_json(resolved)
    except Exception as exc:
        return False, f"phase3_release_control_cleanup_plan_unreadable:{out_path.as_posix()}:{exc.__class__.__name__}"
    if _strip_volatile(existing) != _strip_volatile(expected):
        return False, "phase3_release_control_cleanup_plan_mismatch"
    return True, "phase3_release_control_cleanup_plan_consistent"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--git-clean-clone-receipt", type=Path, default=DEFAULT_GIT_CLEAN_CLONE_RECEIPT)
    parser.add_argument("--source-commit-sha", default=None)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.check:
        ok, message = check_phase3_release_control_cleanup_plan(
            out_path=args.out,
            git_clean_clone_receipt=args.git_clean_clone_receipt,
            source_commit_sha=args.source_commit_sha,
        )
        print(f"Phase 3 release-control cleanup plan check: {message}")
        return 0 if ok else 1
    payload = write_phase3_release_control_cleanup_plan(
        out_path=args.out,
        git_clean_clone_receipt=args.git_clean_clone_receipt,
        source_commit_sha=args.source_commit_sha,
    )
    if args.json:
        print(_json_text(payload), end="")
    else:
        print(
            "Phase 3 release-control cleanup plan: "
            f"{payload['status']} | paths={payload['candidate_release_control_commit_set_count']} | "
            f"human_git_action={payload['human_git_action_required']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
