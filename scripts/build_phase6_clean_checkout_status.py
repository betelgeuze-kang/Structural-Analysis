#!/usr/bin/env python3
"""Build a conservative Phase 6 clean-checkout reproduction status receipt."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from release_evidence_metadata import release_evidence_metadata  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_OUT = PRODUCTIZATION / "phase6_clean_checkout_status.json"
PHASE3_CLEAN_CHECKOUT = PRODUCTIZATION / "phase3_benchmark_factory_seed_clean_checkout_reproduction.json"
PHASE3_GIT_CLEAN_CLONE = PRODUCTIZATION / "phase3_benchmark_factory_seed_git_clean_clone_reproduction.json"
PHASE3_RELEASE_CONTROL_CLEANUP_PLAN = PRODUCTIZATION / "phase3_release_control_cleanup_plan.json"
PHASE3_REPRO_BUNDLE = PRODUCTIZATION / "phase3_benchmark_factory_seed_reproducibility_bundle.json"
SCHEMA_VERSION = "phase6-clean-checkout-status.v1"


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


def _load_json(repo_root: Path, path: Path) -> dict[str, Any]:
    resolved = path if path.is_absolute() else repo_root / path
    if not resolved.exists():
        return {}
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _blockers(payload: dict[str, Any]) -> list[str]:
    return [str(blocker) for blocker in _as_list(payload.get("blockers")) if str(blocker)]


def _contract_ready(payload: dict[str, Any]) -> bool:
    return bool(payload.get("contract_pass") is True or str(payload.get("status", "")).lower() in {"pass", "ready"})


def _blocker_counts(blockers: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for blocker in blockers:
        key = blocker.split(":", 1)[0]
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def build_phase6_clean_checkout_status(*, repo_root: Path = ROOT) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    clean = _load_json(repo_root, PHASE3_CLEAN_CHECKOUT)
    git_clone = _load_json(repo_root, PHASE3_GIT_CLEAN_CLONE)
    cleanup = _load_json(repo_root, PHASE3_RELEASE_CONTROL_CLEANUP_PLAN)

    clean_ready = bool(_contract_ready(clean) and clean.get("clean_checkout_executed") is True)
    git_ready = bool(_contract_ready(git_clone) and git_clone.get("git_clean_clone_executed") is True)
    human_git_action_required = bool(cleanup.get("human_git_action_required") is True)
    cleanup_ready = bool(cleanup.get("contract_pass") is True and not human_git_action_required)
    candidate_count = int(cleanup.get("candidate_release_control_commit_set_count", 0) or 0)
    git_blockers = _blockers(git_clone)
    clean_blockers = _blockers(clean)

    blockers: list[str] = []
    if not clean_ready:
        blockers.append("local_clean_checkout_reproduction_not_passed")
        blockers.extend(f"local_clean_checkout:{blocker}" for blocker in clean_blockers)
    if not git_ready:
        blockers.append("git_clean_clone_reproduction_not_passed")
        blockers.extend(git_blockers)
    if human_git_action_required:
        blockers.append("human_git_action_required_for_release_control_inputs")
    if candidate_count:
        blockers.append(f"release_control_commit_set_pending:{candidate_count}")
    blockers = sorted(dict.fromkeys(blockers))
    contract_pass = bool(clean_ready and git_ready and cleanup_ready and not blockers)
    human_handoff = _as_dict(cleanup.get("human_handoff"))

    return {
        "schema_version": SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=[
                PHASE3_REPRO_BUNDLE,
                PHASE3_CLEAN_CHECKOUT,
                PHASE3_GIT_CLEAN_CLONE,
                PHASE3_RELEASE_CONTROL_CLEANUP_PLAN,
                Path("scripts/build_phase6_clean_checkout_status.py"),
            ],
            reused_evidence=True,
            reuse_policy="phase6_clean_checkout_status_aggregates_phase3_replay_and_release_control_cleanup_receipts",
            repo_root=repo_root,
        ),
        "status": "ready" if contract_pass else "blocked",
        "contract_pass": contract_pass,
        "developer_preview_release_candidate_claim": contract_pass,
        "local_clean_checkout_gate": {
            "status": "ready" if clean_ready else "blocked",
            "contract_pass": clean_ready,
            "receipt": PHASE3_CLEAN_CHECKOUT.as_posix(),
            "clean_checkout_executed": bool(clean.get("clean_checkout_executed") is True),
            "blockers": clean_blockers,
            "claim_boundary": str(clean.get("claim_boundary", "")),
        },
        "git_clean_clone_gate": {
            "status": "ready" if git_ready else "blocked",
            "contract_pass": git_ready,
            "receipt": PHASE3_GIT_CLEAN_CLONE.as_posix(),
            "git_clean_clone_executed": bool(git_clone.get("git_clean_clone_executed") is True),
            "required_input_count": len(_as_list(git_clone.get("required_git_clean_clone_inputs"))),
            "blocker_count": len(git_blockers),
            "blocker_counts": _blocker_counts(git_blockers),
            "blockers": git_blockers,
            "claim_boundary": str(git_clone.get("claim_boundary", "")),
        },
        "release_control_cleanup_gate": {
            "status": "ready" if cleanup_ready else "blocked",
            "contract_pass": cleanup_ready,
            "receipt": PHASE3_RELEASE_CONTROL_CLEANUP_PLAN.as_posix(),
            "human_git_action_required": human_git_action_required,
            "codex_commit_or_push_performed": bool(cleanup.get("codex_commit_or_push_performed") is True),
            "candidate_release_control_commit_set_count": candidate_count,
            "recommended_action_counts": _as_dict(cleanup.get("recommended_action_counts")),
            "path_role_counts": _as_dict(cleanup.get("path_role_counts")),
            "human_handoff_status": str(human_handoff.get("status", "")),
            "human_handoff_next_action": str(human_handoff.get("next_action", "")),
            "next_verification_commands": _as_list(cleanup.get("next_verification_commands")),
            "claim_boundary": str(cleanup.get("claim_boundary", "")),
        },
        "readiness_inputs": {
            "reproducibility_bundle": PHASE3_REPRO_BUNDLE.as_posix(),
            "clean_checkout_reproduction": PHASE3_CLEAN_CHECKOUT.as_posix(),
            "git_clean_clone_reproduction": PHASE3_GIT_CLEAN_CLONE.as_posix(),
            "release_control_cleanup_plan": PHASE3_RELEASE_CONTROL_CLEANUP_PLAN.as_posix(),
        },
        "blockers": blockers,
        "owner_action": (
            "Review the release-control cleanup plan, track or commit required inputs "
            "after human review, rerun the git clean-clone reproduction receipt, and "
            "rerun this Phase 6 clean-checkout status before promoting the RC gate."
        ),
        "summary_line": (
            "Phase 6 clean checkout: "
            f"{'READY' if contract_pass else 'BLOCKED'} | local={clean_ready} | "
            f"git_clone={git_ready} | cleanup_pending={candidate_count}"
        ),
        "claim_boundary": (
            "This receipt aggregates clean-checkout and git-clean-clone replay evidence "
            "for the RC benchmark regeneration gate. It does not run git add, commit, "
            "push, reset, checkout, or cleanup commands; it does not prove Linux/Windows "
            "parity, close full Phase 3, or promote Developer Preview RC readiness."
        ),
    }


def write_phase6_clean_checkout_status(
    *,
    repo_root: Path = ROOT,
    out_path: Path = DEFAULT_OUT,
) -> dict[str, Any]:
    payload = build_phase6_clean_checkout_status(repo_root=repo_root)
    resolved = out_path if out_path.is_absolute() else repo_root / out_path
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(_json_text(payload), encoding="utf-8")
    return payload


def check_phase6_clean_checkout_status(
    *,
    repo_root: Path = ROOT,
    out_path: Path = DEFAULT_OUT,
) -> tuple[bool, str]:
    expected = build_phase6_clean_checkout_status(repo_root=repo_root)
    resolved = out_path if out_path.is_absolute() else repo_root / out_path
    if not resolved.exists():
        return False, f"phase6_clean_checkout_status_missing:{out_path.as_posix()}"
    try:
        existing = json.loads(resolved.read_text(encoding="utf-8"))
    except Exception as exc:
        return False, f"phase6_clean_checkout_status_unreadable:{exc.__class__.__name__}"
    if _strip_volatile(existing) != _strip_volatile(expected):
        return False, "phase6_clean_checkout_status_mismatch"
    return True, "phase6_clean_checkout_status_consistent"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.check:
        ok, message = check_phase6_clean_checkout_status(out_path=args.out)
        print(f"Phase 6 clean checkout status check: {message}")
        return 0 if ok else 1
    payload = write_phase6_clean_checkout_status(out_path=args.out)
    if args.json:
        print(_json_text(payload), end="")
    else:
        print(payload["summary_line"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
