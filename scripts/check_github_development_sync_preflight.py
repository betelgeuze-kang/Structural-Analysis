#!/usr/bin/env python3
"""Read-only preflight for syncing local development state to GitHub."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import check_git_remote_safety  # noqa: E402


DEFAULT_FEATURE_REF = "origin/codex/create-architecture-definition-document-for-hybrid-ai"
DEFAULT_MAIN_REF = "origin/main"
DEFAULT_FETCH_REMOTE = "origin"
IGNORED_WORKTREE_STATUS_PREFIXES = (
    "implementation/phase1/release_evidence/productization/",
)


def _git_output(args: list[str], *, cwd: Path = Path(".")) -> str:
    return subprocess.check_output(
        ["git", *args],
        cwd=cwd,
        text=True,
        stderr=subprocess.DEVNULL,
    ).strip()


def _git_success(args: list[str], *, cwd: Path = Path(".")) -> bool:
    return (
        subprocess.run(
            ["git", *args],
            cwd=cwd,
            text=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        ).returncode
        == 0
    )


def refresh_remote_refs(remote: str = DEFAULT_FETCH_REMOTE, *, cwd: Path = Path(".")) -> bool:
    return _git_success(["fetch", remote], cwd=cwd)


def _ahead_count(base_ref: str, *, cwd: Path = Path(".")) -> int:
    text = _git_output(["rev-list", "--count", f"{base_ref}..HEAD"], cwd=cwd)
    return int(text)


def _current_upstream_ref(*, cwd: Path = Path(".")) -> str:
    try:
        return _git_output(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], cwd=cwd)
    except Exception:
        return DEFAULT_FEATURE_REF


def _remote_branch_name(remote_ref: str, *, remote: str = DEFAULT_FETCH_REMOTE) -> str:
    prefix = f"{remote}/"
    if remote_ref.startswith(prefix):
        return remote_ref[len(prefix):]
    return remote_ref


def _status_path(line: str) -> str:
    text = line[3:].strip() if len(line) > 3 else ""
    if " -> " in text:
        text = text.rsplit(" -> ", 1)[-1].strip()
    return text.strip('"')


def _ignored_worktree_status_line(line: str) -> bool:
    path = _status_path(line)
    return any(path.startswith(prefix) for prefix in IGNORED_WORKTREE_STATUS_PREFIXES)


def split_worktree_status(status_short: str) -> tuple[str, str]:
    ignored: list[str] = []
    effective: list[str] = []
    for line in str(status_short or "").splitlines():
        if not line.strip():
            continue
        if _ignored_worktree_status_line(line):
            ignored.append(line)
        else:
            effective.append(line)
    return "\n".join(effective), "\n".join(ignored)


def collect_git_state(
    *,
    cwd: Path = Path("."),
    feature_ref: str | None = None,
    main_ref: str = DEFAULT_MAIN_REF,
) -> dict[str, Any]:
    resolved_feature_ref = feature_ref or _current_upstream_ref(cwd=cwd)
    return {
        "branch": _git_output(["rev-parse", "--abbrev-ref", "HEAD"], cwd=cwd),
        "local_head_sha": _git_output(["rev-parse", "HEAD"], cwd=cwd),
        "remote_feature_ref": resolved_feature_ref,
        "remote_feature_sha": _git_output(["rev-parse", resolved_feature_ref], cwd=cwd),
        "remote_main_ref": main_ref,
        "remote_main_sha": _git_output(["rev-parse", main_ref], cwd=cwd),
        "remote_safety": check_git_remote_safety.build_report(
            _git_output(["remote", "-v"], cwd=cwd)
        ),
        "worktree_status_short": _git_output(["status", "--short"], cwd=cwd),
        "feature_ahead_count": _ahead_count(resolved_feature_ref, cwd=cwd),
        "main_ahead_count": _ahead_count(main_ref, cwd=cwd),
        "feature_fast_forward_possible": _git_success(
            ["merge-base", "--is-ancestor", resolved_feature_ref, "HEAD"], cwd=cwd
        ),
        "main_fast_forward_possible": _git_success(
            ["merge-base", "--is-ancestor", main_ref, "HEAD"], cwd=cwd
        ),
    }


def build_report(
    state: dict[str, Any],
    *,
    remote_mutation_approved: bool = False,
    remote_fetch_attempted: bool = False,
    remote_fetch_ok: bool | None = None,
) -> dict[str, Any]:
    effective_worktree_status, ignored_worktree_status = split_worktree_status(
        str(state.get("worktree_status_short", "") or "")
    )
    worktree_clean = not bool(effective_worktree_status.strip())
    feature_ahead_count = int(state.get("feature_ahead_count", 0) or 0)
    main_ahead_count = int(state.get("main_ahead_count", 0) or 0)
    feature_ff = bool(state.get("feature_fast_forward_possible", False))
    main_ff = bool(state.get("main_fast_forward_possible", False))
    remote_safety = state.get("remote_safety") if isinstance(state.get("remote_safety"), dict) else {}
    remote_safety_ok = bool(remote_safety.get("ok", False))
    local_head = str(state.get("local_head_sha", "") or "")
    remote_feature = str(state.get("remote_feature_sha", "") or "")
    remote_main = str(state.get("remote_main_sha", "") or "")
    remote_feature_ref = str(state.get("remote_feature_ref", "") or DEFAULT_FEATURE_REF)
    feature_branch = _remote_branch_name(remote_feature_ref)
    feature_synced = local_head == remote_feature
    main_synced = local_head == remote_main
    remote_sync_needed = bool(feature_ahead_count or main_ahead_count or not feature_synced or not main_synced)
    feature_push_command = (
        "git push origin "
        f"{str(state.get('branch', '') or 'HEAD')}:"
        f"{feature_branch}"
    )
    main_push_command = "git push origin HEAD:main"
    pending_remote_updates: list[dict[str, str]] = []
    if not feature_synced:
        pending_remote_updates.append(
            {
                "target": str(state.get("remote_feature_ref", "") or DEFAULT_FEATURE_REF),
                "action": "push current HEAD to feature",
                "command": feature_push_command,
                "rollback": f"restore feature to previous remote SHA {remote_feature} with an approved restore action",
            }
        )
    if not main_synced:
        pending_remote_updates.append(
            {
                "target": str(state.get("remote_main_ref", "") or DEFAULT_MAIN_REF),
                "action": "fast-forward push current HEAD to main",
                "command": main_push_command,
                "rollback": f"restore main to previous remote SHA {remote_main} with an approved revert/restore action",
            }
        )
    pending_targets = [item["target"] for item in pending_remote_updates]
    pending_actions = [item["action"] for item in pending_remote_updates]
    pending_rollbacks = [item["rollback"] for item in pending_remote_updates]
    if not pending_targets:
        r4_risk = "No remote mutation remains."
    elif any(target == str(state.get("remote_main_ref", "") or DEFAULT_MAIN_REF) for target in pending_targets):
        r4_risk = "Main CI and external reviewers immediately see the current commits."
    else:
        r4_risk = "External reviewers of the feature branch immediately see the current commits."
    preflight_pass = bool(
        local_head
        and remote_feature
        and remote_main
        and worktree_clean
        and remote_safety_ok
        and feature_ff
        and main_ff
        and (not remote_fetch_attempted or remote_fetch_ok is True)
    )
    remote_sync_authorized = bool(preflight_pass and (not remote_sync_needed or remote_mutation_approved))
    blockers: list[str] = []
    if not worktree_clean:
        blockers.append("worktree_not_clean")
    if not remote_safety_ok:
        blockers.append("remote_safety_failed")
    if remote_fetch_attempted and remote_fetch_ok is not True:
        blockers.append("remote_fetch_failed")
    if not feature_ff:
        blockers.append("feature_remote_not_ancestor_of_head")
    if not main_ff:
        blockers.append("main_remote_not_ancestor_of_head")
    if remote_sync_needed and not remote_mutation_approved:
        blockers.append("remote_mutation_approval_required")
    status = "synced"
    if blockers:
        status = "approval_required" if blockers == ["remote_mutation_approval_required"] else "blocked"
    elif remote_sync_needed:
        status = "ready_to_push"

    return {
        "schema_version": "github-development-sync-preflight.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "contract_pass": remote_sync_authorized and not blockers,
        "preflight_pass": preflight_pass,
        "remote_mutation_approved": remote_mutation_approved,
        "remote_fetch_attempted": remote_fetch_attempted,
        "remote_fetch_ok": remote_fetch_ok,
        "remote_sync_needed": remote_sync_needed,
        "reason_code": "PASS" if remote_sync_authorized and not blockers else "ERR_GITHUB_SYNC_NOT_COMPLETE",
        "blockers": blockers,
        "state": {
            **state,
            "effective_worktree_status_short": effective_worktree_status,
            "ignored_worktree_status_short": ignored_worktree_status,
        },
        "pending_remote_updates": pending_remote_updates,
        "checks": {
            "worktree_clean": worktree_clean,
            "worktree_only_ignored_evidence_dirty": bool(
                ignored_worktree_status and not effective_worktree_status
            ),
            "remote_safety_ok": remote_safety_ok,
            "remote_fetch_ok": remote_fetch_ok,
            "feature_fast_forward_possible": feature_ff,
            "main_fast_forward_possible": main_ff,
            "feature_synced_to_head": feature_synced,
            "main_synced_to_head": main_synced,
            "explicit_remote_mutation_approval": remote_mutation_approved,
        },
        "commands": {
            "feature_push": feature_push_command,
            "main_fast_forward_push": main_push_command,
            "post_push_verify": (
                "git fetch origin && git rev-parse HEAD "
                f"{state.get('remote_feature_ref')} {state.get('remote_main_ref')}"
            ),
        },
        "r4_disclosure": {
            "target": pending_targets,
            "action": "; ".join(pending_actions) if pending_actions else "no remote mutation required",
            "impact": (
                "GitHub pending refs become externally visible at the local development state."
                if pending_targets
                else "No GitHub ref update is needed; feature and main already match local HEAD."
            ),
            "risk": r4_risk,
            "rollback": "; ".join(pending_rollbacks) if pending_rollbacks else "no rollback needed",
            "verification": "fetch origin and compare remote feature/main refs with local HEAD after push",
        },
        "claim_boundary": (
            "This preflight is read-only. It does not push, merge, publish, or mutate GitHub. "
            "A remote update still requires explicit human R4 approval."
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--feature-ref", default=None)
    parser.add_argument("--main-ref", default=DEFAULT_MAIN_REF)
    parser.add_argument("--fetch", action="store_true")
    parser.add_argument("--fetch-remote", default=DEFAULT_FETCH_REMOTE)
    parser.add_argument("--remote-mutation-approved", action="store_true")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    remote_fetch_ok = refresh_remote_refs(args.fetch_remote) if args.fetch else None
    payload = build_report(
        collect_git_state(feature_ref=args.feature_ref, main_ref=args.main_ref),
        remote_mutation_approved=args.remote_mutation_approved,
        remote_fetch_attempted=args.fetch,
        remote_fetch_ok=remote_fetch_ok,
    )
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        state = payload["state"]
        print(
            "github-development-sync-preflight: "
            f"{payload['status'].upper()} | "
            f"feature_ahead={state['feature_ahead_count']} | "
            f"main_ahead={state['main_ahead_count']} | "
            f"preflight_pass={payload['preflight_pass']}"
        )
    return 1 if args.fail_blocked and not payload["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
