#!/usr/bin/env python3
"""Build a CI pass-streak manifest from local PR/nightly gate artifacts."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


DEFAULT_OUT = Path("implementation/phase1/release_evidence/productization/ci_consecutive_pass_manifest.json")
DEFAULT_PR_REPORTS = [
    Path("implementation/phase1/ci_gate_report.pr.json"),
    Path("implementation/phase1/ci_gate_report.pr_recheck.json"),
]
DEFAULT_NIGHTLY_REPORTS = [
    Path("implementation/phase1/ci_gate_report.nightly.json"),
]
DEFAULT_NIGHTLY_GLOB_ROOT = Path("implementation/phase1/release")
DEFAULT_GITHUB_ACTIONS_EVIDENCE = Path(
    "implementation/phase1/release_evidence/productization/github_actions_ci_streak_evidence.json"
)


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _reason_pass(payload: dict[str, Any]) -> bool:
    return bool(
        payload.get("contract_pass") is True
        or payload.get("pass") is True
        or str(payload.get("reason_code", "")).strip().upper() == "PASS"
    )


def _github_lane_streak(payload: dict[str, Any], lane: str) -> int:
    lanes = payload.get("lanes")
    if not isinstance(lanes, dict):
        return 0
    lane_payload = lanes.get(lane)
    if not isinstance(lane_payload, dict):
        return 0
    try:
        return int(lane_payload.get("consecutive_pass_count", 0) or 0)
    except Exception:
        return 0


def _lane_owner_action(label: str, threshold: int, consecutive: int) -> str:
    if consecutive >= threshold:
        return "No release action required; consecutive pass threshold is satisfied."
    missing = max(0, threshold - consecutive)
    if label == "pr":
        return (
            f"Collect {missing} additional consecutive successful PR CI run(s); keep the pull_request CI lane "
            "green and refresh github_actions_ci_streak_evidence before release signoff."
        )
    if label == "nightly":
        return (
            f"Collect {missing} additional consecutive successful nightly CI run(s); keep the scheduled/nightly "
            "lane green and refresh github_actions_ci_streak_evidence before release signoff."
        )
    return f"Collect {missing} additional consecutive successful CI run(s) before release signoff."


def _lane_claim_boundary(label: str) -> str:
    if label == "pr":
        return (
            "Local PR gate reports prove command-level readiness; release streak credit requires tracked PR CI "
            "evidence for the consecutive-pass window."
        )
    if label == "nightly":
        return (
            "Local nightly artifacts prove command-level readiness; release streak credit requires tracked "
            "nightly CI evidence for the consecutive-pass window."
        )
    return "Local CI artifacts prove command-level readiness; release streak credit requires tracked CI evidence."


def _lane(label: str, reports: list[Path], threshold: int, github_actions_evidence: dict[str, Any]) -> dict[str, Any]:
    seen: set[Path] = set()
    rows: list[dict[str, Any]] = []
    for report in reports:
        path = report.resolve()
        if path in seen:
            continue
        seen.add(path)
        payload = _load_json(report)
        ok = _reason_pass(payload)
        rows.append(
            {
                "path": str(report),
                "exists": report.exists(),
                "reason_code": str(payload.get("reason_code", "")),
                "contract_pass": payload.get("contract_pass"),
                "pass": ok,
            }
        )
    local_consecutive = 0
    for row in reversed(rows):
        if not row["pass"]:
            break
        local_consecutive += 1
    github_consecutive = _github_lane_streak(github_actions_evidence, label)
    consecutive = max(local_consecutive, github_consecutive)
    threshold_pass = consecutive >= threshold
    return {
        "lane": label,
        "threshold": threshold,
        "report_count": len(rows),
        "pass_count": sum(1 for row in rows if row["pass"]),
        "local_consecutive_pass_count": local_consecutive,
        "github_actions_consecutive_pass_count": github_consecutive,
        "consecutive_pass_count": consecutive,
        "missing_consecutive_pass_count": max(0, threshold - consecutive),
        "threshold_pass": threshold_pass,
        "streak_source": "github_actions" if github_consecutive >= local_consecutive and github_consecutive else "local_artifacts",
        "owner_action": _lane_owner_action(label, threshold, consecutive),
        "claim_boundary": _lane_claim_boundary(label),
        "rows": rows,
    }


def build_manifest(
    *,
    threshold: int,
    pr_reports: list[Path],
    nightly_reports: list[Path],
    github_actions_evidence_path: Path | None = None,
) -> dict[str, Any]:
    github_actions_evidence = _load_json(github_actions_evidence_path) if github_actions_evidence_path else {}
    lanes = {
        "pr": _lane("pr", pr_reports, threshold, github_actions_evidence),
        "nightly": _lane("nightly", nightly_reports, threshold, github_actions_evidence),
    }
    return {
        "schema_version": "ci-consecutive-pass-manifest.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "threshold": threshold,
        "contract_pass": all(row["threshold_pass"] for row in lanes.values()),
        "evidence_sources": {
            "local_pr_report_count": len(pr_reports),
            "local_nightly_report_count": len(nightly_reports),
            "github_actions_evidence_path": str(github_actions_evidence_path or ""),
            "github_actions_evidence_available": bool(github_actions_evidence),
            "github_actions_schema_version": str(github_actions_evidence.get("schema_version", "")),
        },
        "lanes": lanes,
        "summary": {
            "pr_consecutive_pass_count": lanes["pr"]["consecutive_pass_count"],
            "nightly_consecutive_pass_count": lanes["nightly"]["consecutive_pass_count"],
            "github_actions_pr_consecutive_pass_count": lanes["pr"]["github_actions_consecutive_pass_count"],
            "github_actions_nightly_consecutive_pass_count": lanes["nightly"][
                "github_actions_consecutive_pass_count"
            ],
            "pr_threshold_pass": lanes["pr"]["threshold_pass"],
            "nightly_threshold_pass": lanes["nightly"]["threshold_pass"],
            "pr_missing_consecutive_pass_count": lanes["pr"]["missing_consecutive_pass_count"],
            "nightly_missing_consecutive_pass_count": lanes["nightly"]["missing_consecutive_pass_count"],
            "pr_owner_action": lanes["pr"]["owner_action"],
            "nightly_owner_action": lanes["nightly"]["owner_action"],
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--threshold", type=int, default=30)
    parser.add_argument("--github-actions-evidence", type=Path, default=DEFAULT_GITHUB_ACTIONS_EVIDENCE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    nightly_reports = [
        *DEFAULT_NIGHTLY_REPORTS,
        *sorted(DEFAULT_NIGHTLY_GLOB_ROOT.glob("phase3_nightly_hardening_*/ci_gate_report.json")),
    ]
    payload = build_manifest(
        threshold=args.threshold,
        pr_reports=DEFAULT_PR_REPORTS,
        nightly_reports=nightly_reports,
        github_actions_evidence_path=args.github_actions_evidence,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) if args.json else payload["summary"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
