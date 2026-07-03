#!/usr/bin/env python3
"""Build the PocketMD Lite top-k source acquisition plan."""

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

from materialize_pocketmd_lite_operator_intake_from_rows import (  # noqa: E402
    SOURCE_RECEIPT_REQUIREMENTS,
    row_value_contract,
)
from materialize_pocketmd_lite_topk_survival_report import (  # noqa: E402
    REQUIRED_CASE_FIELDS,
    TOP_K_RANK_PREFIX_POLICY,
    TOP_K_SCOPE_POLICY,
    TOPK_ROW_QUALITY_CRITERIA,
    UPSTREAM_TOP_K_RECEIPT_FIELDS,
)
from release_evidence_metadata import release_evidence_metadata  # noqa: E402


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_OUT = PRODUCTIZATION / "pocketmd_lite_source_acquisition_plan.json"
DEFAULT_OUT_MD = DEFAULT_OUT.with_suffix(".md")
DEFAULT_ROWS_OUT = PRODUCTIZATION / "pocketmd_lite_topk_rows.json"
DEFAULT_OPERATOR_INTAKE = PRODUCTIZATION / "pocketmd_lite_operator_intake.json"
DEFAULT_OPERATOR_TEMPLATE = PRODUCTIZATION / "pocketmd_lite_operator_template.json"
DEFAULT_REFINEMENT_EXECUTION_PLAN = (
    PRODUCTIZATION / "pocketmd_lite_refinement_execution_plan.json"
)
DEFAULT_SURVIVAL_REPORT = PRODUCTIZATION / "pocketmd_lite_topk_survival_report.json"
DEFAULT_SURFACE = (
    Path("implementation/phase1/release_evidence/surface")
    / "pocketmd_lite_science_product_surface.json"
)
REFINEMENT_EXECUTION_PLAN_SCHEMA_VERSION = (
    "pocketmd-lite-refinement-execution-plan.v1"
)

SCHEMA_VERSION = "pocketmd-lite-source-acquisition-plan.v1"
SUPPORTED_ROW_FORMATS = ["csv", "tsv", "json", "jsonl", "ndjson"]
PHASE4_REFINEMENT_RECEIPT_PROMOTION_POLICY = {
    "operator_attached_rows_required": True,
    "upstream_top_k_scope_receipts_required": True,
    "lite_refinement_metric_receipts_required": True,
    "operator_input_source_receipt_required": True,
    "per_row_sha256_receipt_required": True,
    "synthetic_fixture_rows_promote_to_phase4": False,
    "summary_only_metrics_promote_to_phase4": False,
    "broad_all_atom_or_fep_claims_unlocked": False,
}
PHASE4_CRITERIA_BY_RECEIPT_ROLE = {
    "upstream_top_k_candidate_scope_receipt": [
        "top_k_refinement_rows_present",
        "top_k_refinement_case_coverage",
    ],
    "lite_refinement_run_receipt": [
        "local_min_survival_materialized",
        "report_blockers_resolved",
    ],
    "interaction_persistence_receipt": [
        "contact_persistence_materialized",
        "h_bond_persistence_materialized",
        "clash_relief_materialized",
        "report_blockers_resolved",
    ],
    "uncertainty_interval_receipt": [
        "uncertainty_summary_materialized",
        "report_blockers_resolved",
    ],
}


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _required_flat_row_fields() -> list[str]:
    fields: list[str] = []
    for field in REQUIRED_CASE_FIELDS:
        if field == "uncertainty_interval":
            fields.extend(["uncertainty_low", "uncertainty_high", "uncertainty_unit"])
        else:
            fields.append(field)
    return fields


def _minimum_rows_by_case() -> list[dict[str, Any]]:
    min_case_count = int(TOPK_ROW_QUALITY_CRITERIA["min_real_refinement_case_count"])
    min_rank_coverage = int(
        TOPK_ROW_QUALITY_CRITERIA["min_top_k_rank_coverage_per_case"]
    )
    return [
        {
            "case_id": f"pocketmd_lite_case_{case_index:03d}",
            "minimum_candidate_rows": int(
                TOPK_ROW_QUALITY_CRITERIA["min_candidate_count_per_case"]
            ),
            "required_top_k_rank_prefix": list(range(1, min_rank_coverage + 1)),
            "candidate_scope": "upstream_ranked_top_k_candidates_only",
        }
        for case_index in range(1, min_case_count + 1)
    ]


def _phase4_refinement_receipt_roles() -> list[dict[str, Any]]:
    common_row_receipts = [
        "provenance_ref",
        "source_checksum",
        "operator_input_source.source_artifact",
        "operator_input_source.source_artifact_sha256",
        "operator_input_source.source_id",
        "operator_input_source.source_url",
        "operator_input_source.source_license",
    ]
    return [
        {
            "receipt_role_id": "upstream_top_k_candidate_scope_receipt",
            "status": "operator_receipt_required",
            "source_role": "upstream_ranked_top_k_candidate_set",
            "required_fields": [
                "case_id",
                "candidate_id",
                "top_k_rank",
                "upstream_top_k_provenance_ref",
                "upstream_top_k_source_checksum",
            ],
            "required_quality_gates": [
                "top_k_rank_prefix_starts_at_1_per_case",
                "top_k_rank_is_contiguous_with_no_cherry_picked_gaps",
                "top_k_rank_does_not_exceed_20",
                "minimum_case_and_candidate_coverage_satisfied",
            ],
            "closes_phase4_criteria": list(
                PHASE4_CRITERIA_BY_RECEIPT_ROLE[
                    "upstream_top_k_candidate_scope_receipt"
                ]
            ),
            "operator_must_attach": [
                "upstream top-k ranking provenance reference for every candidate",
                "upstream top-k source checksum for every candidate",
                "case-level rank prefix coverage evidence",
            ],
        },
        {
            "receipt_role_id": "lite_refinement_run_receipt",
            "status": "operator_receipt_required",
            "source_role": "bounded_lite_refinement_run",
            "required_fields": [
                "pre_refinement_energy_proxy",
                "post_refinement_energy_proxy",
                "local_min_survived",
                *common_row_receipts,
            ],
            "required_quality_gates": [
                "finite_pre_and_post_refinement_energy_proxy_values",
                "boolean_local_min_survived_value",
                "non_placeholder_row_provenance_and_sha256_checksum",
                "operator_input_source_receipt_matches_attached_rows",
            ],
            "closes_phase4_criteria": list(
                PHASE4_CRITERIA_BY_RECEIPT_ROLE["lite_refinement_run_receipt"]
            ),
            "operator_must_attach": [
                "Lite refinement run provenance reference",
                "row-level source checksum",
                "operator input source artifact checksum",
            ],
        },
        {
            "receipt_role_id": "interaction_persistence_receipt",
            "status": "operator_receipt_required",
            "source_role": "contact_hbond_clash_metric_rows",
            "required_fields": [
                "contact_persistence_rate",
                "h_bond_persistence_rate",
                "clash_count_before",
                "clash_count_after",
                *common_row_receipts,
            ],
            "required_quality_gates": [
                "contact_and_hbond_rates_are_finite_fractions",
                "clash_counts_are_non_negative_integers",
                "clash_relief_is_computed_from_before_after_counts",
                "metric_rows_share_the_bounded_top_k_candidate_scope",
            ],
            "closes_phase4_criteria": list(
                PHASE4_CRITERIA_BY_RECEIPT_ROLE["interaction_persistence_receipt"]
            ),
            "operator_must_attach": [
                "contact persistence computation receipt",
                "H-bond persistence computation receipt",
                "clash counting computation receipt",
            ],
        },
        {
            "receipt_role_id": "uncertainty_interval_receipt",
            "status": "operator_receipt_required",
            "source_role": "candidate_uncertainty_interval_rows",
            "required_fields": [
                "uncertainty_low",
                "uncertainty_high",
                "uncertainty_unit",
                *common_row_receipts,
            ],
            "required_quality_gates": [
                "uncertainty_interval_has_finite_low_and_high",
                "uncertainty_high_is_not_below_low",
                "uncertainty_unit_is_nonblank",
                "uncertainty_rows_share_the_bounded_top_k_candidate_scope",
            ],
            "closes_phase4_criteria": list(
                PHASE4_CRITERIA_BY_RECEIPT_ROLE["uncertainty_interval_receipt"]
            ),
            "operator_must_attach": [
                "uncertainty estimation method receipt",
                "candidate-level uncertainty interval rows",
                "row-level source checksum",
            ],
        },
    ]


def _phase4_refinement_receipt_plan() -> dict[str, Any]:
    receipt_roles = _phase4_refinement_receipt_roles()
    covered_criteria = sorted(
        {
            criterion
            for row in receipt_roles
            for criterion in row["closes_phase4_criteria"]
        }
    )
    return {
        "plan_id": "pocketmd_lite_phase4_refinement_receipt_plan",
        "status": "operator_receipts_required",
        "receipt_role_count": len(receipt_roles),
        "receipt_roles": receipt_roles,
        "covered_phase4_criteria": covered_criteria,
        "covered_phase4_criterion_count": len(covered_criteria),
        "preserved_phase4_criteria": ["broad_all_atom_fep_claims_locked"],
        "promotion_policy": dict(PHASE4_REFINEMENT_RECEIPT_PROMOTION_POLICY),
        "claim_boundary": (
            "Receipt roles identify the operator evidence required for bounded "
            "PocketMD Lite top-k refinement only. They do not create rows, run "
            "refinement, or unlock broad all-atom MD/FEP claims."
        ),
    }


def _refinement_execution_plan_command() -> str:
    return (
        "python3 scripts/build_pocketmd_lite_refinement_execution_plan.py "
        f"--out {DEFAULT_REFINEMENT_EXECUTION_PLAN}"
    )


def _refinement_execution_plan_summary(
    minimum_rows_by_case: list[dict[str, Any]],
) -> dict[str, Any]:
    required_candidate_slot_count = sum(
        len(row.get("required_top_k_rank_prefix") or [])
        for row in minimum_rows_by_case
    )
    return {
        "artifact": str(DEFAULT_REFINEMENT_EXECUTION_PLAN),
        "schema_version": REFINEMENT_EXECUTION_PLAN_SCHEMA_VERSION,
        "status": "operator_refinement_rows_required",
        "execution_plan_ready": True,
        "operator_rows_ready": False,
        "survival_report_ready": False,
        "actual_closure_ready": False,
        "required_case_count": len(minimum_rows_by_case),
        "required_candidate_slot_count": required_candidate_slot_count,
        "command": _refinement_execution_plan_command(),
        "claim_boundary": (
            "The execution plan enumerates the bounded top-k case/rank slots "
            "operator rows must fill. It does not synthesize rows or promote "
            "PocketMD Lite closure without the survival materializer."
        ),
    }


def build_pocketmd_lite_source_acquisition_plan(
    *,
    repo_root: Path = ROOT,
) -> dict[str, Any]:
    blockers = [
        "pocketmd_lite_topk_rows_not_acquired",
        "upstream_top_k_candidate_receipts_not_attached",
        "lite_refinement_metric_receipts_not_attached",
    ]
    required_flat_row_fields = _required_flat_row_fields()
    minimum_rows_by_case = _minimum_rows_by_case()
    min_total = int(TOPK_ROW_QUALITY_CRITERIA["min_total_top_k_candidate_count"])
    min_cases = int(TOPK_ROW_QUALITY_CRITERIA["min_real_refinement_case_count"])
    phase4_refinement_receipt_plan = _phase4_refinement_receipt_plan()
    refinement_execution_plan = _refinement_execution_plan_summary(
        minimum_rows_by_case
    )
    return {
        "schema_version": SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=[
                Path("scripts/build_pocketmd_lite_source_acquisition_plan.py"),
                Path("scripts/build_pocketmd_lite_refinement_execution_plan.py"),
                Path("scripts/materialize_pocketmd_lite_operator_intake_from_rows.py"),
                Path("scripts/materialize_pocketmd_lite_topk_survival_report.py"),
            ],
            reused_evidence=False,
            reuse_policy="pocketmd_lite_source_acquisition_plan",
            repo_root=repo_root,
        ),
        "status": "operator_acquisition_required",
        "contract_pass": True,
        "actual_closure_ready": False,
        "source_scope": "bounded_top_k_lite_refinement_rows",
        "supported_source_formats": list(SUPPORTED_ROW_FORMATS),
        "required_case_fields": list(REQUIRED_CASE_FIELDS),
        "required_flat_row_fields": required_flat_row_fields,
        "upstream_top_k_receipt_fields": list(UPSTREAM_TOP_K_RECEIPT_FIELDS),
        "top_k_rank_prefix_policy": TOP_K_RANK_PREFIX_POLICY,
        "top_k_scope_policy": TOP_K_SCOPE_POLICY,
        "top_k_row_quality_minimums": dict(TOPK_ROW_QUALITY_CRITERIA),
        "minimum_rows_by_case": minimum_rows_by_case,
        "phase4_refinement_receipt_plan": phase4_refinement_receipt_plan,
        "refinement_execution_plan": refinement_execution_plan,
        "phase4_refinement_receipt_promotion_policy": dict(
            PHASE4_REFINEMENT_RECEIPT_PROMOTION_POLICY
        ),
        "row_artifact_contract": {
            "default_output": str(DEFAULT_ROWS_OUT),
            "operator_intake_output": str(DEFAULT_OPERATOR_INTAKE),
            "required_case_count": min_cases,
            "required_total_candidate_rows": min_total,
            "required_candidate_rows_per_case": int(
                TOPK_ROW_QUALITY_CRITERIA["min_candidate_count_per_case"]
            ),
            "required_top_k_rank_coverage_per_case": int(
                TOPK_ROW_QUALITY_CRITERIA["min_top_k_rank_coverage_per_case"]
            ),
            "required_flat_row_fields": required_flat_row_fields,
            "accepted_formats": list(SUPPORTED_ROW_FORMATS),
            "row_value_contract": row_value_contract(max_top_k=20),
            "source_receipt_requirements": dict(SOURCE_RECEIPT_REQUIREMENTS),
        },
        "metric_receipt_contract": [
            {
                "metric_id": "local_min_survival_rate",
                "required_row_fields": ["local_min_survived"],
                "required_value_policy": "boolean per top-k candidate",
            },
            {
                "metric_id": "contact_persistence_rate",
                "required_row_fields": ["contact_persistence_rate"],
                "required_value_policy": "finite fraction from 0.0 to 1.0",
            },
            {
                "metric_id": "h_bond_persistence_rate",
                "required_row_fields": ["h_bond_persistence_rate"],
                "required_value_policy": "finite fraction from 0.0 to 1.0",
            },
            {
                "metric_id": "clash_relief_rate",
                "required_row_fields": ["clash_count_before", "clash_count_after"],
                "required_value_policy": "non-negative integer clash counts",
            },
            {
                "metric_id": "uncertainty_width_median",
                "required_row_fields": [
                    "uncertainty_low",
                    "uncertainty_high",
                    "uncertainty_unit",
                ],
                "required_value_policy": (
                    "finite interval with high >= low and nonblank unit"
                ),
            },
        ],
        "operator_acquisition_checklist": [
            "review_phase4_refinement_receipt_plan",
            "build_pocketmd_lite_refinement_execution_plan",
            "select_upstream_ranked_top_k_candidate_sets",
            "attach_upstream_top_k_provenance_and_checksum_for_every_candidate",
            "run_bounded_lite_refinement_for_top_k_candidates_only",
            "write_local_min_contact_hbond_clash_uncertainty_rows",
            "attach_row_source_receipts_with_license_url_and_artifact_sha256",
            "write_pocketmd_lite_topk_rows_at_default_dropzone",
            "run_pocketmd_lite_raw_row_importer_and_survival_materializer",
            "refresh_science_actual_closure_from_rows",
        ],
        "commands": {
            "write_plan": (
                "python3 scripts/build_pocketmd_lite_source_acquisition_plan.py"
            ),
            "build_refinement_execution_plan": _refinement_execution_plan_command(),
            "import_rows": (
                "python3 scripts/materialize_pocketmd_lite_operator_intake_from_rows.py "
                f"--rows {DEFAULT_ROWS_OUT} --out {DEFAULT_OPERATOR_INTAKE} "
                "--source-id <source-id> --source-url <source-url> "
                "--source-license <license>"
            ),
            "materialize_survival": (
                "python3 scripts/materialize_pocketmd_lite_topk_survival_report.py "
                f"--intake {DEFAULT_OPERATOR_INTAKE} "
                f"--contract {PRODUCTIZATION / 'pocketmd_lite_contract.json'} "
                f"--out-report {DEFAULT_SURVIVAL_REPORT} --out-surface {DEFAULT_SURFACE} "
                "--fail-blocked"
            ),
            "science_actual_closure": (
                "python3 scripts/materialize_science_actual_closure_from_rows.py "
                "--fail-blocked"
            ),
        },
        "blockers": blockers,
        "blocker_count": len(blockers),
        "summary": {
            "required_case_count": min_cases,
            "required_total_candidate_rows": min_total,
            "required_candidate_rows_per_case": int(
                TOPK_ROW_QUALITY_CRITERIA["min_candidate_count_per_case"]
            ),
            "minimum_rows_by_case_count": len(minimum_rows_by_case),
            "phase4_refinement_receipt_plan_status": (
                phase4_refinement_receipt_plan["status"]
            ),
            "phase4_refinement_receipt_role_count": (
                phase4_refinement_receipt_plan["receipt_role_count"]
            ),
            "covered_phase4_criterion_count": (
                phase4_refinement_receipt_plan[
                    "covered_phase4_criterion_count"
                ]
            ),
            "refinement_execution_plan_status": refinement_execution_plan["status"],
            "refinement_execution_plan_ready": refinement_execution_plan[
                "execution_plan_ready"
            ],
            "required_candidate_slot_count": refinement_execution_plan[
                "required_candidate_slot_count"
            ],
            "operator_rows_ready": refinement_execution_plan["operator_rows_ready"],
            "actual_closure_ready": False,
            "blocker_count": len(blockers),
        },
        "claim_boundary": (
            "This plan records the row, metric, and receipt contract needed to acquire "
            "PocketMD Lite top-k refinement evidence. It does not synthesize rows, run "
            "Lite refinement, infer missing metrics, or unlock broad all-atom MD/FEP "
            "claims before the materializer verifies real operator evidence."
        ),
    }


def _markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# PocketMD Lite Source Acquisition Plan",
        "",
        f"- `status`: `{payload['status']}`",
        f"- `contract_pass`: `{payload['contract_pass']}`",
        f"- `actual_closure_ready`: `{payload['actual_closure_ready']}`",
        f"- `blocker_count`: `{payload['blocker_count']}`",
        f"- `phase4_refinement_receipt_plan_status`: `{payload['phase4_refinement_receipt_plan']['status']}`",
        f"- `phase4_refinement_receipt_role_count`: `{payload['phase4_refinement_receipt_plan']['receipt_role_count']}`",
        f"- `refinement_execution_plan`: `{payload['refinement_execution_plan']['artifact']}`",
        f"- `refinement_execution_plan_status`: `{payload['refinement_execution_plan']['status']}`",
        f"- `required_candidate_slot_count`: `{payload['refinement_execution_plan']['required_candidate_slot_count']}`",
        "",
        "| Case | Minimum Rows | Required Rank Prefix | Scope |",
        "|---|---:|---|---|",
    ]
    for row in payload["minimum_rows_by_case"]:
        ranks = ",".join(str(rank) for rank in row["required_top_k_rank_prefix"])
        lines.append(
            f"| `{row['case_id']}` | {row['minimum_candidate_rows']} | "
            f"`{ranks}` | `{row['candidate_scope']}` |"
        )
    lines.extend(["", "## Phase 4 Receipt Roles", ""])
    lines.extend(["| Receipt Role | Source Role | Closes Criteria |", "|---|---|---|"])
    for row in payload["phase4_refinement_receipt_plan"]["receipt_roles"]:
        closes = ", ".join(
            f"`{criterion}`" for criterion in row["closes_phase4_criteria"]
        )
        lines.append(
            f"| `{row['receipt_role_id']}` | `{row['source_role']}` | {closes} |"
        )
    lines.extend(["", "## Commands", ""])
    for key, command in payload["commands"].items():
        lines.append(f"- `{key}`: `{command}`")
    lines.extend(["", str(payload["claim_boundary"]), ""])
    return "\n".join(lines)


def render_pocketmd_lite_source_acquisition_markdown(payload: dict[str, Any]) -> str:
    return _markdown(payload)


def write_pocketmd_lite_source_acquisition_plan(
    *,
    repo_root: Path = ROOT,
    out: Path = DEFAULT_OUT,
    out_md: Path = DEFAULT_OUT_MD,
) -> dict[str, Any]:
    payload = build_pocketmd_lite_source_acquisition_plan(repo_root=repo_root)
    resolved_out = out if out.is_absolute() else repo_root / out
    resolved_out.parent.mkdir(parents=True, exist_ok=True)
    resolved_out.write_text(_json_text(payload), encoding="utf-8")
    resolved_md = out_md if out_md.is_absolute() else repo_root / out_md
    resolved_md.parent.mkdir(parents=True, exist_ok=True)
    resolved_md.write_text(
        render_pocketmd_lite_source_acquisition_markdown(payload),
        encoding="utf-8",
    )
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = write_pocketmd_lite_source_acquisition_plan(
        repo_root=args.repo_root,
        out=args.out,
        out_md=args.out_md,
    )
    if args.json:
        print(_json_text(payload), end="")
    else:
        print(
            "pocketmd-lite-source-acquisition-plan: "
            f"{payload['status']} | cases={payload['summary']['required_case_count']} | "
            f"candidate_rows={payload['summary']['required_total_candidate_rows']} | "
            f"blockers={payload['blocker_count']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
