#!/usr/bin/env python3
"""CI helper: run delivery evidence bundle and require ready status."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def build_gap_status_command(*, gap_json: Path, productization_dir: Path) -> list[str]:
    return [
        sys.executable,
        str(REPO_ROOT / "scripts/report_gap_closure_status.py"),
        "--productization-dir",
        str(productization_dir),
        "--output-json",
        str(gap_json),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--bundle-json",
        type=Path,
        default=REPO_ROOT
        / "implementation/phase1/release_evidence/productization/delivery_evidence_bundle.json",
    )
    parser.add_argument(
        "--allow-review-required",
        action="store_true",
        help="Exit 0 when bundle status is review_required (default: require ready).",
    )
    parser.add_argument("--enrich-changes", action="store_true")
    parser.add_argument(
        "--check-existing",
        action="store_true",
        help="Validate existing bundle/gap JSON without rerunning the full delivery orchestrator.",
    )
    parser.add_argument(
        "--gap-json",
        type=Path,
        default=REPO_ROOT / "implementation/phase1/release_evidence/productization/gap_closure_status.json",
    )
    args = parser.parse_args()

    if not args.check_existing:
        cmd = [
            sys.executable,
            str(REPO_ROOT / "scripts/run_delivery_evidence_bundle.py"),
            "--output-json",
            str(args.bundle_json),
        ]
        if args.enrich_changes:
            cmd.append("--enrich-changes")
        proc = subprocess.run(cmd, cwd=REPO_ROOT, check=False, capture_output=True, text=True)
        if proc.returncode != 0:
            print(proc.stdout + proc.stderr, file=sys.stderr)
            return proc.returncode

        gap_proc = subprocess.run(
            build_gap_status_command(
                gap_json=args.gap_json,
                productization_dir=args.bundle_json.parent,
            ),
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        if gap_proc.returncode != 0:
            print(gap_proc.stdout + gap_proc.stderr, file=sys.stderr)
            return gap_proc.returncode

    if not args.bundle_json.is_file():
        print(f"ci-delivery: missing bundle: {args.bundle_json}", file=sys.stderr)
        return 2

    bundle = json.loads(args.bundle_json.read_text(encoding="utf-8"))
    status = str(bundle.get("status") or "")
    print(f"ci-delivery: bundle_status={status}")
    gap_status = ""
    if args.gap_json.is_file():
        gap = json.loads(args.gap_json.read_text(encoding="utf-8"))
        gap_status = str(gap.get("delivery_status") or "")
        print(f"ci-delivery: gap_delivery_status={gap_status}")

    if status == "ready" and (not gap_status or gap_status == "ready"):
        return 0
    if status == "review_required" and args.allow_review_required:
        print("ci-delivery: review_required allowed by flag", file=sys.stderr)
        return 0
    print(f"ci-delivery: blockers={bundle.get('blockers')}", file=sys.stderr)
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
