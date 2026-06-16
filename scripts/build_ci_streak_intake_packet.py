#!/usr/bin/env python3
"""Build an owner handoff packet for CI consecutive-pass release evidence."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "ci-streak-intake-packet.v1"
DEFAULT_MANIFEST = Path("implementation/phase1/release_evidence/productization/ci_consecutive_pass_manifest.json")
DEFAULT_GITHUB_ACTIONS_EVIDENCE = Path(
    "implementation/phase1/release_evidence/productization/github_actions_ci_streak_evidence.json"
)
DEFAULT_OUT = Path("implementation/phase1/release_evidence/productization/ci_streak_intake_packet.json")
DEFAULT_OUT_MD = Path("implementation/phase1/release_evidence/productization/ci_streak_intake_packet.md")


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _lane_row(lane: str, manifest: dict[str, Any], github_actions: dict[str, Any]) -> dict[str, Any]:
    manifest_lanes = _as_dict(manifest.get("lanes"))
    github_lanes = _as_dict(github_actions.get("lanes"))
    manifest_lane = _as_dict(manifest_lanes.get(lane))
    github_lane = _as_dict(github_lanes.get(lane))
    threshold = _as_int(manifest_lane.get("threshold"), _as_int(manifest.get("threshold"), 30))
    consecutive = _as_int(manifest_lane.get("consecutive_pass_count"))
    github_consecutive = _as_int(github_lane.get("consecutive_pass_count"))
    missing = max(0, threshold - consecutive)
    threshold_pass = bool(manifest_lane.get("threshold_pass", False))
    blockers = [str(item) for item in manifest_lane.get("blockers", []) if isinstance(item, str)]
    if not threshold_pass and not blockers:
        blockers = [f"{lane}_ci_{threshold}_consecutive_pass_evidence_missing"]
    return {
        "lane": lane,
        "threshold": threshold,
        "threshold_pass": threshold_pass,
        "consecutive_pass_count": consecutive,
        "missing_consecutive_pass_count": missing,
        "local_consecutive_pass_count": _as_int(manifest_lane.get("local_consecutive_pass_count")),
        "github_actions_consecutive_pass_count": github_consecutive,
        "github_actions_threshold_pass": bool(github_lane.get("threshold_pass", False)),
        "streak_source": str(manifest_lane.get("streak_source", "")),
        "owner_action": str(manifest_lane.get("owner_action", "")),
        "claim_boundary": str(manifest_lane.get("claim_boundary", "")),
        "blockers": blockers,
    }


def build_packet(
    *,
    manifest_path: Path = DEFAULT_MANIFEST,
    github_actions_evidence_path: Path = DEFAULT_GITHUB_ACTIONS_EVIDENCE,
) -> dict[str, Any]:
    manifest = _load_json(manifest_path)
    github_actions = _load_json(github_actions_evidence_path)
    lane_rows = [
        _lane_row("pr", manifest, github_actions),
        _lane_row("nightly", manifest, github_actions),
    ]
    blockers = [
        f"{row['lane']}:{blocker}"
        for row in lane_rows
        for blocker in row["blockers"]
        if not row["threshold_pass"]
    ]
    contract_pass = bool(manifest.get("contract_pass", False) and not blockers)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now_utc_iso(),
        "contract_pass": contract_pass,
        "reason_code": "PASS" if contract_pass else "ERR_CI_STREAK_EVIDENCE_INCOMPLETE",
        "ci_consecutive_pass_manifest": str(manifest_path),
        "github_actions_ci_streak_evidence": str(github_actions_evidence_path),
        "summary": {
            "threshold": _as_int(manifest.get("threshold"), 30),
            "lane_count": len(lane_rows),
            "lane_pass_count": sum(1 for row in lane_rows if row["threshold_pass"]),
            "open_blocker_count": len(blockers),
            "pr_missing_consecutive_pass_count": next(
                row["missing_consecutive_pass_count"] for row in lane_rows if row["lane"] == "pr"
            ),
            "nightly_missing_consecutive_pass_count": next(
                row["missing_consecutive_pass_count"] for row in lane_rows if row["lane"] == "nightly"
            ),
        },
        "lane_rows": lane_rows,
        "current_blockers": blockers,
        "validation_commands": [
            f"python3 scripts/build_github_actions_ci_streak_evidence.py --out {DEFAULT_GITHUB_ACTIONS_EVIDENCE}",
            f"python3 scripts/build_ci_consecutive_pass_manifest.py --out {DEFAULT_MANIFEST}",
            f"python3 scripts/build_ci_streak_intake_packet.py --out {DEFAULT_OUT}",
            "python3 scripts/report_pm_release_gate.py "
            " --out implementation/phase1/release_evidence/productization/pm_release_gate_report.json"
            " --out-md implementation/phase1/release_evidence/productization/pm_release_gate_report.md",
            "python3 scripts/build_pm_release_blocker_action_register.py "
            " --out implementation/phase1/release_evidence/productization/pm_release_blocker_action_register.json"
            " --out-md implementation/phase1/release_evidence/productization/pm_release_blocker_action_register.md",
        ],
        "claim_boundary": (
            "This packet is an owner handoff checklist for CI streak evidence. It does not convert local "
            "gate artifacts into release streak credit; PR and nightly release credit still require tracked "
            "consecutive-pass evidence for the configured release window."
        ),
    }


def _markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# CI Streak Intake Packet",
        "",
        f"- `contract_pass`: `{payload['contract_pass']}`",
        f"- `reason_code`: `{payload['reason_code']}`",
        f"- `ci_consecutive_pass_manifest`: `{payload['ci_consecutive_pass_manifest']}`",
        f"- `github_actions_ci_streak_evidence`: `{payload['github_actions_ci_streak_evidence']}`",
        "",
        "| Lane | Streak | Missing | Source | Pass | Owner Action |",
        "|---|---:|---:|---|---|---|",
    ]
    for row in payload["lane_rows"]:
        lines.append(
            f"| `{row['lane']}` | `{row['consecutive_pass_count']}/{row['threshold']}` | "
            f"`{row['missing_consecutive_pass_count']}` | `{row['streak_source']}` | "
            f"`{row['threshold_pass']}` | {row['owner_action']} |"
        )
    lines.extend(["", "## Validation Commands", ""])
    for command in payload["validation_commands"]:
        lines.append(f"- `{command}`")
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--github-actions-evidence", type=Path, default=DEFAULT_GITHUB_ACTIONS_EVIDENCE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_packet(
        manifest_path=args.manifest,
        github_actions_evidence_path=args.github_actions_evidence,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.out_md is not None:
        args.out_md.parent.mkdir(parents=True, exist_ok=True)
        args.out_md.write_text(_markdown(payload), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) if args.json else _markdown(payload))
    return 1 if args.fail_blocked and not payload["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
