#!/usr/bin/env python3
"""Retired non-structural science-surface seed writer for structural releases."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from release_evidence_metadata import release_evidence_metadata  # noqa: E402


SCHEMA_VERSION = "structural-release-non-structural-surface-seed-guard.v1"
DEFAULT_SURFACE_DIR = Path("implementation/phase1/release_evidence/surface")


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def build_science_evidence_surface_seeds(*, repo_root: Path = ROOT) -> dict[str, dict[str, Any]]:
    """Return no release-surface seeds for the structural-analysis product scope."""

    return {}


def build_surface_seed_guard(
    *,
    repo_root: Path = ROOT,
    surface_dir: Path = DEFAULT_SURFACE_DIR,
    family: str = "all",
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=[Path("scripts/build_science_evidence_surface_seeds.py")],
            reused_evidence=False,
            reuse_policy="non_structural_surface_seed_generation_retired_from_structural_release",
            repo_root=repo_root,
        ),
        "status": "retired_from_structural_release_surface",
        "contract_pass": True,
        "requested_family": family,
        "surface_dir": surface_dir.as_posix(),
        "surfaces_written": [],
        "surface_written_count": 0,
        "structural_release_surface_mutated": False,
        "next_actions": [
            "keep_non_structural_surface_artifacts_quarantined_until_owner_delete_or_extract_decision",
            "use_structural_scope_owner_decision_application_plan_for_cleanup",
        ],
        "claim_boundary": (
            "This compatibility command intentionally writes no science evidence "
            "surface seeds into the building structural-analysis release surface. "
            "Legacy non-structural artifacts remain governed by the structural "
            "scope owner-review and quarantine workflow."
        ),
    }


def write_science_evidence_surface_seeds(
    *,
    repo_root: Path = ROOT,
    surface_dir: Path = DEFAULT_SURFACE_DIR,
    family: str = "all",
) -> dict[str, dict[str, Any]]:
    build_surface_seed_guard(repo_root=repo_root, surface_dir=surface_dir, family=family)
    return {}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--surface-dir", type=Path, default=DEFAULT_SURFACE_DIR)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument(
        "--family",
        default="all",
        help="Accepted for legacy compatibility; no structural release seeds are written.",
    )
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    surfaces = write_science_evidence_surface_seeds(
        repo_root=args.repo_root,
        surface_dir=args.surface_dir,
        family=args.family,
    )
    guard = build_surface_seed_guard(
        repo_root=args.repo_root,
        surface_dir=args.surface_dir,
        family=args.family,
    )
    if args.json:
        print(_json_text({"surfaces": surfaces, "guard": guard}), end="")
    else:
        print(
            "science-evidence-surface-seeds: retired_from_structural_release_surface | "
            "surfaces_written=0"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
