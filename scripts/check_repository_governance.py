#!/usr/bin/env python3
"""Check repository governance files and protected ownership rules."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REQUIRED_FILES = (
    Path("LICENSE"),
    Path("SECURITY.md"),
    Path("CONTRIBUTING.md"),
    Path(".github/CODEOWNERS"),
)
REQUIRED_CODEOWNER_PATTERNS = (
    "* ",
    "/.betelgeuze/ ",
    "/implementation/phase1/release_evidence/productization/ ",
    "/docs/commercial-structural-solver-product-gap-ledger.md ",
    "/docs/structural-analysis-ai-engine-gap-ledger.md ",
    "/src/structural_analysis/engine_v2/contracts/ ",
    "/src/structural_analysis/ai/ ",
    "/src/workbench-v2/ ",
)


def build_report(repo_root: Path) -> dict[str, Any]:
    root = repo_root.resolve()
    blockers: list[str] = []
    for relative in REQUIRED_FILES:
        path = root / relative
        if not path.is_file():
            blockers.append(f"missing_required_file:{relative.as_posix()}")
        elif not path.read_text(encoding="utf-8").strip():
            blockers.append(f"empty_required_file:{relative.as_posix()}")

    license_text = (
        (root / "LICENSE").read_text(encoding="utf-8")
        if (root / "LICENSE").is_file()
        else ""
    )
    normalized_license = " ".join(license_text.split())
    if "No permission is granted" not in normalized_license:
        blockers.append("license_permission_boundary_missing")
    if "not evidence of product-license approval" not in normalized_license:
        blockers.append("license_readiness_claim_boundary_missing")

    security_text = (
        (root / "SECURITY.md").read_text(encoding="utf-8")
        if (root / "SECURITY.md").is_file()
        else ""
    )
    for required in ("private vulnerability reporting", "engineering-safety"):
        if required not in security_text:
            blockers.append(f"security_policy_requirement_missing:{required}")

    contributing_text = (
        (root / "CONTRIBUTING.md").read_text(encoding="utf-8")
        if (root / "CONTRIBUTING.md").is_file()
        else ""
    )
    normalized_contributing = " ".join(contributing_text.split())
    for required in ("focused tests", "fallback", "source commit and checksums"):
        if required not in normalized_contributing:
            blockers.append(f"contributing_requirement_missing:{required}")

    codeowners_text = (
        (root / ".github/CODEOWNERS").read_text(encoding="utf-8")
        if (root / ".github/CODEOWNERS").is_file()
        else ""
    )
    for pattern in REQUIRED_CODEOWNER_PATTERNS:
        if not any(
            line.startswith(pattern) and "@" in line
            for line in codeowners_text.splitlines()
        ):
            blockers.append(f"codeowners_pattern_missing:{pattern.strip()}")

    blockers = sorted(dict.fromkeys(blockers))
    return {
        "schema_version": "repository-governance-check.v1",
        "status": "pass" if not blockers else "blocked",
        "contract_pass": not blockers,
        "required_files": [path.as_posix() for path in REQUIRED_FILES],
        "protected_codeowner_patterns": list(REQUIRED_CODEOWNER_PATTERNS),
        "license_posture": "all_rights_reserved_no_license_granted",
        "product_license_approval_claimed": False,
        "blockers": blockers,
        "claim_boundary": (
            "This check proves repository governance files and ownership rules "
            "exist. It does not prove legal approval, commercial-use rights, "
            "support SLA, security certification, or release readiness."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = build_report(args.repo_root)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"repository governance: {report['status']}")
        for blocker in report["blockers"]:
            print(f"- {blocker}")
    return 0 if report["contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
