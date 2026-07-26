#!/usr/bin/env python3
"""Generate and inspect the non-promoting Lee-frame verification candidate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.build_verification_hierarchy_status import (
    build_verification_hierarchy_status,
)
from structural_analysis.benchmark.lee_frame_verification_candidate import (
    write_lee_frame_verification_candidate_bundle,
)


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--candidate-dir",
        type=Path,
        default=(
            ROOT / "implementation/phase1/release_evidence/productization/"
            "verification_candidates/lee_frame"
        ),
    )
    parser.add_argument(
        "--manifest-out",
        type=Path,
        default=(
            ROOT / "implementation/phase1/release_evidence/productization/"
            "verification_hierarchy_evidence.candidate.json"
        ),
    )
    parser.add_argument(
        "--status-out",
        type=Path,
        default=None,
        help="Optional candidate hierarchy status output.",
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--fail-credit",
        action="store_true",
        help="Fail if the candidate unexpectedly receives hierarchy credit.",
    )
    args = parser.parse_args()

    bundle = write_lee_frame_verification_candidate_bundle(
        ROOT,
        candidate_dir=args.candidate_dir,
        manifest_path=args.manifest_out,
    )
    status = build_verification_hierarchy_status(
        repo_root=ROOT,
        operator_evidence_path=bundle.manifest_path,
    )
    payload = {
        "candidate_bundle": bundle.to_dict(),
        "hierarchy": status,
    }
    if args.status_out is not None:
        args.status_out.parent.mkdir(parents=True, exist_ok=True)
        args.status_out.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        level3 = next(row for row in status["level_rows"] if row["level"] == 3)
        print(
            "Lee-frame V&V candidate: "
            f"intrinsic={level3['intrinsic_contract_pass']} | "
            f"promotion={level3['promotion_contract_pass']} | "
            f"highest={status['highest_verified_level']} | "
            f"candidate_manifest={bundle.manifest_path}"
        )
    if args.fail_credit:
        evidence_row = next(
            row
            for row in status["evidence_rows"]
            if row["evidence_id"] == bundle.evidence["evidence_id"]
        )
        if evidence_row["ready_for_hierarchy_credit"]:
            return 2
        if status["highest_verified_level"] > 1:
            return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
