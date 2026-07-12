#!/usr/bin/env python3
"""Verify that a Phase 1 evidence head differs from its source only by evidence files."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_ONLY_PREFIX = (
    "implementation/phase1/release_evidence/productization/phase1_core_api_"
)
EVIDENCE_ONLY_EXACT_PATHS = frozenset(
    {
        "implementation/phase1/release_evidence/productization/developer_preview_readiness.json",
        "implementation/phase1/release_evidence/productization/developer_preview_readiness.md",
        "implementation/phase1/release_evidence/productization/developer_preview_rc_status.json",
        "implementation/phase1/release_evidence/productization/developer_preview_rc_status.md",
        "implementation/phase1/release_evidence/productization/release_evidence_freshness_report.json",
        "implementation/phase1/release_evidence/productization/release_evidence_freshness_report.md",
        "implementation/phase1/release_evidence/productization/pm_release_gate_report.json",
        "implementation/phase1/release_evidence/productization/pm_release_gate_report.md",
        "implementation/phase1/release_evidence/productization/pm_release_blocker_action_register.json",
        "implementation/phase1/release_evidence/productization/pm_release_blocker_action_register.md",
        "implementation/phase1/release_evidence/productization/product_readiness_snapshot.json",
        "implementation/phase1/release_evidence/productization/structural_product_development_roadmap.json",
        "implementation/phase1/release_evidence/productization/structural_product_development_roadmap.md",
    }
)


def _git(
    repo_root: Path,
    *args: str,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=check,
        text=True,
        capture_output=True,
    )


def _is_evidence_path(path: str) -> bool:
    return path.startswith(EVIDENCE_ONLY_PREFIX) or path in EVIDENCE_ONLY_EXACT_PATHS


def verify_source_state(
    *,
    repo_root: Path,
    source_commit: str,
    head_commit: str,
) -> dict[str, Any]:
    source = source_commit.strip()
    head = head_commit.strip()
    blockers: list[str] = []

    if not source:
        blockers.append("source_commit_missing")
    if not head:
        blockers.append("head_commit_missing")

    ancestor = False
    changed_paths: list[str] = []
    if not blockers:
        ancestor_result = _git(
            repo_root,
            "merge-base",
            "--is-ancestor",
            source,
            head,
            check=False,
        )
        ancestor = ancestor_result.returncode == 0
        if not ancestor:
            blockers.append("source_commit_not_ancestor_of_head")
        else:
            diff = _git(repo_root, "diff", "--name-only", f"{source}..{head}")
            changed_paths = sorted(
                row.strip()
                for row in diff.stdout.splitlines()
                if row.strip()
            )

    disallowed_paths = sorted(
        path for path in changed_paths if not _is_evidence_path(path)
    )
    blockers.extend(
        f"non_evidence_path_changed_after_source:{path}"
        for path in disallowed_paths
    )
    blockers = sorted(dict.fromkeys(blockers))

    return {
        "schema_version": "phase1-evidence-source-state-receipt.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "pass" if not blockers else "blocked",
        "contract_pass": not blockers,
        "source_commit_sha": source,
        "verified_head_sha": head,
        "source_is_ancestor": ancestor,
        "changed_path_count": len(changed_paths),
        "changed_paths": changed_paths,
        "disallowed_paths": disallowed_paths,
        "blockers": blockers,
        "policy": {
            "mode": "source_commit_then_evidence_only_commit",
            "allowed_prefix": EVIDENCE_ONLY_PREFIX,
            "allowed_exact_paths": sorted(EVIDENCE_ONLY_EXACT_PATHS),
        },
        "claim_boundary": (
            "This receipt proves only that every committed path after the recorded "
            "source commit belongs to the declared generated Phase 1/readiness evidence "
            "surface. It does not prove scientific correctness beyond the generators "
            "and focused tests executed by the authoritative evidence workflow."
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--head-commit", default="HEAD")
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = args.repo_root.resolve()
    head = args.head_commit
    if head == "HEAD":
        head = _git(repo_root, "rev-parse", "HEAD").stdout.strip()
    payload = verify_source_state(
        repo_root=repo_root,
        source_commit=args.source_commit,
        head_commit=head,
    )
    rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    if args.out:
        out = args.out if args.out.is_absolute() else repo_root / args.out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(rendered + "\n", encoding="utf-8")
    if args.json or not args.out:
        print(rendered)
    return 1 if args.fail_blocked and not payload["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
