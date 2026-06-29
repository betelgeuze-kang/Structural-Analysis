#!/usr/bin/env python3
"""Build locked science evidence surface seeds for release-cockpit routing."""

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
from materialize_gpcr_hard_decoy_suite_report import (  # noqa: E402
    SCHEMA_VERSION as GPCR_HARD_DECOY_MATERIALIZER_SCHEMA_VERSION,
)


SCHEMA_VERSION = "science-evidence-surface-seed.v1"
DEFAULT_SURFACE_DIR = Path("implementation/phase1/release_evidence/surface")
FAMILY_CHOICES = ("all", "h_bond_backmap", "gpcr_hard_decoy")


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _base_surface(
    *,
    surface_id: str,
    status: str,
    reason_code: str,
    summary_line: str,
    blockers: list[str],
    repo_root: Path,
    extra_input_paths: list[Path] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=[
                Path("scripts/build_science_evidence_surface_seeds.py"),
                *(extra_input_paths or []),
            ],
            reused_evidence=False,
            reuse_policy="locked_science_evidence_surface_seed_from_goal_contract",
            repo_root=repo_root,
        ),
        "surface_id": surface_id,
        "status": status,
        "reason_code": reason_code,
        "contract_pass": False,
        "locked": True,
        "claim_locked": True,
        "blockers": blockers,
        "summary_line": summary_line,
        "claim_boundary": (
            "This is a release-cockpit science evidence surface seed. It makes the "
            "blocked science claim visible to PM routing, but it does not attach "
            "authoritative experimental receipts or promote a release claim."
        ),
    }


def build_h_bond_backmap_surface(*, repo_root: Path = ROOT) -> dict[str, Any]:
    blockers = [
        "h_bond_backmap_authoritative_receipts_required",
        "h_bond_backmap_operator_handoff_not_attached",
    ]
    required_receipts = [
        "operator_attached_h_bond_backmap_cases",
        "contact_persistence_or_backmap_accuracy_rows",
        "reviewer_reproduction_command",
    ]
    operator_evidence_gap_register = [
        {
            "slot_priority": 1,
            "slot_id": "operator_attached_h_bond_backmap_cases",
            "status": "operator_input_required",
            "h_bond_surface_blocked": True,
            "blocked_h_bond_criteria": [
                "authoritative_h_bond_backmap_cases_attached",
                "source_receipts_attached",
            ],
            "first_next_action": "attach authoritative H-bond BackMap case rows",
            "minimum_evidence": {
                "required_fields": [
                    "case_id",
                    "receptor_id",
                    "ligand_id",
                    "source_system_ref",
                    "donor_acceptor_map_ref",
                    "provenance_ref",
                    "source_checksum",
                ],
            },
        },
        {
            "slot_priority": 2,
            "slot_id": "contact_persistence_or_backmap_accuracy_rows",
            "status": "operator_input_required",
            "h_bond_surface_blocked": True,
            "blocked_h_bond_criteria": [
                "contact_persistence_or_backmap_accuracy_rows_attached",
            ],
            "first_next_action": (
                "attach measured contact persistence or BackMap accuracy rows"
            ),
            "minimum_evidence": {
                "required_fields": [
                    "case_id",
                    "contact_persistence_rate",
                    "backmap_accuracy_rate",
                    "h_bond_distance_error_angstrom_median",
                    "h_bond_angle_error_degree_median",
                    "source_checksum",
                ],
            },
        },
        {
            "slot_priority": 3,
            "slot_id": "reviewer_reproduction_command",
            "status": "operator_input_required",
            "h_bond_surface_blocked": True,
            "blocked_h_bond_criteria": ["reviewer_reproduction_command_attached"],
            "first_next_action": "attach a reviewer reproduction command",
            "minimum_evidence": {
                "required_fields": [
                    "command",
                    "expected_outputs",
                    "environment_ref",
                    "source_checksum",
                ],
            },
        },
    ]
    return {
        **_base_surface(
            surface_id="h_bond_backmap_evidence_surface",
            status="locked",
            reason_code="ERR_H_BOND_BACKMAP_EVIDENCE_LOCKED",
            summary_line="H-Bond BackMap evidence surface: LOCKED | authoritative receipts required",
            blockers=blockers,
            repo_root=repo_root,
        ),
        "science_surface_family": "h_bond",
        "surface_scope": "h_bond_backmap",
        "first_blocked_target": "operator_attached_h_bond_backmap_cases",
        "root_cause_tags": [
            "operator_receipts_required",
            "operator_handoff_required",
        ],
        "required_receipts": required_receipts,
        "operator_evidence_gap_count": len(operator_evidence_gap_register),
        "first_operator_evidence_gap": operator_evidence_gap_register[0],
        "operator_evidence_gap_register": operator_evidence_gap_register,
        "next_actions": [
            "attach_h_bond_backmap_operator_receipts",
            "materialize_h_bond_backmap_evidence_rows",
            "regenerate_pm_release_gate_report",
        ],
    }


def build_gpcr_hard_decoy_surface(*, repo_root: Path = ROOT) -> dict[str, Any]:
    blockers = [
        "drd2_htr2a_oprm1_operator_values_required",
        "gpcr_hard_decoy_materializer_not_run_on_real_values",
        "broad_gpcr_family_claim_locked",
    ]
    return {
        **_base_surface(
            surface_id="gpcr_hard_decoy_evidence_surface",
            status="locked",
            reason_code="ERR_BROAD_GPCR_CLAIM_LOCKED",
            summary_line=(
                "GPCR hard-decoy evidence surface: LOCKED | "
                "DRD2/HTR2A/OPRM1 numeric criteria missing"
            ),
            blockers=blockers,
            repo_root=repo_root,
            extra_input_paths=[Path("scripts/materialize_gpcr_hard_decoy_suite_report.py")],
        ),
        "science_surface_family": "gpcr",
        "surface_scope": "broad_gpcr_hard_decoy",
        "target_families": ["DRD2", "HTR2A", "OPRM1"],
        "first_blocked_target": "DRD2",
        "root_cause_tags": ["operator_values_required"],
        "exit_criteria": {
            "ranking_pr_auc_ci_low_min": 0.45,
            "top20_hit_rate_min": 0.20,
            "decoys_above_positive_count_max": 0,
            "positive_out_anchored_by_top_decoys_allowed": False,
        },
        "materializer": {
            "schema_version": GPCR_HARD_DECOY_MATERIALIZER_SCHEMA_VERSION,
            "status": "ready_for_operator_intake",
            "materialization_command": (
                "python3 scripts/materialize_gpcr_hard_decoy_suite_report.py "
                "--intake implementation/phase1/release_evidence/productization/"
                "gpcr_hard_decoy_operator_template.json "
                "--out-report implementation/phase1/release_evidence/productization/"
                "gpcr_hard_decoy_suite_report.json "
                "--out-surface implementation/phase1/release_evidence/surface/"
                "gpcr_hard_decoy_evidence_surface.json --fail-blocked"
            ),
            "claim_boundary": (
                "The materializer evaluates operator-attached DRD2/HTR2A/OPRM1 hard-decoy "
                "metrics against numeric exit criteria. It does not generate metrics or "
                "unlock broad GPCR claims without all target rows passing."
            ),
        },
        "suite_report": (
            "implementation/phase1/release_evidence/productization/"
            "gpcr_hard_decoy_suite_report.json"
        ),
        "next_actions": [
            "fill_drd2_htr2a_oprm1_operator_template_values",
            "run_gpcr_hard_decoy_materializer",
            "regenerate_product_gpcr_hard_decoy_suite_report",
            "regenerate_pm_release_gate_report",
        ],
    }


def build_science_evidence_surface_seeds(*, repo_root: Path = ROOT) -> dict[str, dict[str, Any]]:
    return {
        "h_bond_backmap": build_h_bond_backmap_surface(repo_root=repo_root),
        "gpcr_hard_decoy": build_gpcr_hard_decoy_surface(repo_root=repo_root),
    }


def write_science_evidence_surface_seeds(
    *,
    repo_root: Path = ROOT,
    surface_dir: Path = DEFAULT_SURFACE_DIR,
    family: str = "all",
) -> dict[str, dict[str, Any]]:
    surfaces = build_science_evidence_surface_seeds(repo_root=repo_root)
    if family != "all":
        if family not in surfaces:
            raise ValueError(f"Unknown science evidence surface family: {family}")
        surfaces = {family: surfaces[family]}
    outputs = {
        "h_bond_backmap": surface_dir / "h_bond_backmap_evidence_surface.json",
        "gpcr_hard_decoy": surface_dir / "gpcr_hard_decoy_evidence_surface.json",
    }
    for key in surfaces:
        raw_path = outputs[key]
        path = raw_path if raw_path.is_absolute() else repo_root / raw_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_json_text(surfaces[key]), encoding="utf-8")
    return surfaces


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--surface-dir", type=Path, default=DEFAULT_SURFACE_DIR)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument(
        "--family",
        choices=FAMILY_CHOICES,
        default="all",
        help="Limit writes to one science surface family; default writes all seed surfaces.",
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
    if args.json:
        print(_json_text({"surfaces": surfaces}), end="")
    else:
        print(
            "science-evidence-surface-seeds: "
            f"locked_surfaces={len(surfaces)} | "
            f"families={','.join(surfaces)}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
