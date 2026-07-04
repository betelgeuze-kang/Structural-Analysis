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
    DEFAULT_MAX_TOP_K,
    SOURCE_RECEIPT_REQUIREMENTS,
    _normalize_row,
    _read_source_rows,
    _validate_topk_integrity,
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
DEFAULT_ROWS_TEMPLATE = PRODUCTIZATION / "pocketmd_lite_topk_rows_template.csv"
DEFAULT_ROWS_TEMPLATE_PREFLIGHT = (
    PRODUCTIZATION / "pocketmd_lite_topk_rows_template_preflight.json"
)
DEFAULT_ROWS_TEMPLATE_PREFLIGHT_MD = DEFAULT_ROWS_TEMPLATE_PREFLIGHT.with_suffix(".md")
DEFAULT_OPERATOR_INTAKE = PRODUCTIZATION / "pocketmd_lite_operator_intake.json"
DEFAULT_OPERATOR_TEMPLATE = PRODUCTIZATION / "pocketmd_lite_operator_template.json"
DEFAULT_REFINEMENT_EXECUTION_PLAN = (
    PRODUCTIZATION / "pocketmd_lite_refinement_execution_plan.json"
)
DEFAULT_ROWS_FROM_RECEIPT_BUNDLE_REPORT = (
    PRODUCTIZATION / "pocketmd_lite_topk_rows_from_receipt_bundle_report.json"
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
PHASE4_METRIC_CRITERIA = {
    "local_min_survival_materialized": {
        "metric_id": "local_min_survival_rate",
        "materialized_report_field": "local_min_survival_rate",
    },
    "contact_persistence_materialized": {
        "metric_id": "contact_persistence_rate",
        "materialized_report_field": "contact_persistence_summary",
    },
    "h_bond_persistence_materialized": {
        "metric_id": "h_bond_persistence_rate",
        "materialized_report_field": "h_bond_persistence_summary",
    },
    "clash_relief_materialized": {
        "metric_id": "clash_relief_rate",
        "materialized_report_field": "clash_relief_summary",
    },
    "uncertainty_summary_materialized": {
        "metric_id": "uncertainty_width_median",
        "materialized_report_field": "uncertainty_width_summary",
    },
}
POCKETMD_RECEIPT_METRIC_FAMILIES = (
    {
        "metric_family_id": "local_min_survival",
        "product_requirement": "local-min survival and energy proxy movement are recorded",
        "phase4_criterion_id": "local_min_survival_materialized",
        "required_receipt_fields": [
            "pre_refinement_energy_proxy",
            "post_refinement_energy_proxy",
            "local_min_survived",
        ],
    },
    {
        "metric_family_id": "contact_persistence",
        "product_requirement": "contact persistence is recorded",
        "phase4_criterion_id": "contact_persistence_materialized",
        "required_receipt_fields": ["contact_persistence_rate"],
    },
    {
        "metric_family_id": "h_bond_persistence",
        "product_requirement": "H-bond persistence is recorded",
        "phase4_criterion_id": "h_bond_persistence_materialized",
        "required_receipt_fields": ["h_bond_persistence_rate"],
    },
    {
        "metric_family_id": "clash_relief",
        "product_requirement": "clash relief before/after counts are recorded",
        "phase4_criterion_id": "clash_relief_materialized",
        "required_receipt_fields": ["clash_count_before", "clash_count_after"],
    },
    {
        "metric_family_id": "uncertainty",
        "product_requirement": "uncertainty interval bounds are recorded",
        "phase4_criterion_id": "uncertainty_summary_materialized",
        "required_receipt_fields": ["uncertainty_low", "uncertainty_high"],
    },
)
PHASE4_COMPLETION_REQUIREMENTS = [
    {
        "requirement_id": "bounded_top_k_scope_contract",
        "product_requirement": "PocketMD Lite applies only to upstream top-k candidates",
        "phase4_criterion_id": "broad_all_atom_fep_claims_locked",
        "evidence_kind": "contract_guard",
    },
    {
        "requirement_id": "top_k_refinement_rows_present",
        "product_requirement": "top-k candidate refinement rows are present",
        "phase4_criterion_id": "top_k_refinement_rows_present",
        "evidence_kind": "row_coverage",
    },
    {
        "requirement_id": "top_k_refinement_case_coverage",
        "product_requirement": "top-k candidate case/rank coverage is complete",
        "phase4_criterion_id": "top_k_refinement_case_coverage",
        "evidence_kind": "row_coverage",
    },
    {
        "requirement_id": "local_min_survival_reported",
        "product_requirement": "local-min survival is reported",
        "phase4_criterion_id": "local_min_survival_materialized",
        "evidence_kind": "survival_summary_metric",
        "summary_field": "local_min_survival_rate",
        "blocker_id": "pocketmd_lite_local_min_survival_rows_missing",
    },
    {
        "requirement_id": "contact_persistence_reported",
        "product_requirement": "contact persistence is reported",
        "phase4_criterion_id": "contact_persistence_materialized",
        "evidence_kind": "survival_summary_metric",
        "summary_field": "contact_persistence_rate_median",
        "blocker_id": "pocketmd_lite_contact_persistence_rows_missing",
    },
    {
        "requirement_id": "h_bond_persistence_reported",
        "product_requirement": "H-bond persistence is reported",
        "phase4_criterion_id": "h_bond_persistence_materialized",
        "evidence_kind": "survival_summary_metric",
        "summary_field": "h_bond_persistence_rate_median",
        "blocker_id": "pocketmd_lite_h_bond_persistence_rows_missing",
    },
    {
        "requirement_id": "clash_relief_reported",
        "product_requirement": "clash relief is reported",
        "phase4_criterion_id": "clash_relief_materialized",
        "evidence_kind": "survival_summary_metric",
        "summary_field": "clash_relief_rate",
        "blocker_id": "pocketmd_lite_clash_relief_rows_missing",
    },
    {
        "requirement_id": "uncertainty_reported",
        "product_requirement": "uncertainty interval summary is reported",
        "phase4_criterion_id": "uncertainty_summary_materialized",
        "evidence_kind": "survival_summary_metric",
        "summary_field": "uncertainty_width_median",
        "blocker_id": "pocketmd_lite_uncertainty_rows_missing",
    },
    {
        "requirement_id": "broad_all_atom_fep_claims_locked",
        "product_requirement": "broad all-atom MD/FEP claims remain locked",
        "phase4_criterion_id": "broad_all_atom_fep_claims_locked",
        "evidence_kind": "contract_guard",
    },
]


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


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


def _receipt_metric_family_completion_plan(
    receipt_completion_action_plan: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    plan: list[dict[str, Any]] = []
    receipt_count = len(receipt_completion_action_plan)
    for family in POCKETMD_RECEIPT_METRIC_FAMILIES:
        required_fields = [
            str(field)
            for field in _as_list(family.get("required_receipt_fields"))
            if str(field)
        ]
        blocked_receipts: list[dict[str, Any]] = []
        missing_field_occurrence_count = 0
        for receipt in receipt_completion_action_plan:
            missing_fields = [
                field
                for field in required_fields
                if field
                in {
                    str(item)
                    for item in _as_list(
                        receipt.get("completion_missing_required_fields")
                    )
                }
            ]
            if not missing_fields:
                continue
            missing_field_occurrence_count += len(missing_fields)
            blocked_receipts.append(
                {
                    "case_id": str(receipt.get("case_id") or ""),
                    "top_k_rank": int(receipt.get("top_k_rank") or 0),
                    "run_key": str(receipt.get("run_key") or ""),
                    "receipt_ref": str(receipt.get("receipt_ref") or ""),
                    "missing_receipt_fields": missing_fields,
                    "operator_completion_action": str(
                        receipt.get("operator_completion_action") or ""
                    ),
                }
            )
        blocked_count = len(blocked_receipts)
        plan.append(
            {
                "metric_family_id": str(family.get("metric_family_id") or ""),
                "product_requirement": str(
                    family.get("product_requirement") or ""
                ),
                "phase4_criterion_id": str(
                    family.get("phase4_criterion_id") or ""
                ),
                "status": "blocked" if blocked_count else "ready",
                "required_receipt_fields": required_fields,
                "receipt_count": receipt_count,
                "complete_receipt_count": max(0, receipt_count - blocked_count),
                "blocked_receipt_count": blocked_count,
                "missing_field_occurrence_count": missing_field_occurrence_count,
                "first_blocked_receipt": (
                    blocked_receipts[0] if blocked_receipts else {}
                ),
                "blocked_receipts": blocked_receipts,
                "operator_completion_action": (
                    "fill_metric_family_receipt_fields_for_"
                    f"{family.get('metric_family_id')}"
                    if blocked_count
                    else "review_metric_family_receipts"
                ),
            }
        )
    return plan


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


def _required_slot_keys(
    minimum_rows_by_case: list[dict[str, Any]],
) -> set[tuple[str, int]]:
    slots: set[tuple[str, int]] = set()
    for row in minimum_rows_by_case:
        case_id = str(row.get("case_id") or "")
        ranks = row.get("required_top_k_rank_prefix")
        if not case_id or not isinstance(ranks, list):
            continue
        for rank in ranks:
            try:
                slots.add((case_id, int(rank)))
            except (TypeError, ValueError):
                continue
    return slots


def _rank_prefixes(rows: list[dict[str, Any]]) -> dict[str, list[int]]:
    case_ids = sorted({str(row.get("case_id") or "") for row in rows if row.get("case_id")})
    return {
        case_id: sorted(
            {
                int(row["top_k_rank"])
                for row in rows
                if row.get("case_id") == case_id and row.get("top_k_rank") is not None
            }
        )
        for case_id in case_ids
    }


def _raw_row_candidate_status(
    repo_root: Path,
    *,
    rows_out: Path = DEFAULT_ROWS_OUT,
    minimum_rows_by_case: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    candidates = [
        PRODUCTIZATION / f"pocketmd_lite_topk_rows.{suffix}"
        for suffix in ("json", "jsonl", "ndjson", "csv", "tsv")
    ]
    if str(rows_out) not in {str(path) for path in candidates}:
        candidates.insert(0, rows_out)

    rows = []
    seen_paths: set[str] = set()
    selected_path = ""
    selected_resolved_path: Path | None = None
    for path in candidates:
        path_key = str(path)
        if path_key in seen_paths:
            continue
        seen_paths.add(path_key)
        resolved = path if path.is_absolute() else repo_root / path
        if resolved.is_file() and selected_resolved_path is None:
            selected_path = str(path)
            selected_resolved_path = resolved
        rows.append(
            {
                "path": str(path),
                "exists": resolved.exists(),
                "is_file": resolved.is_file(),
            }
        )

    detected_paths = [str(row["path"]) for row in rows if row["is_file"]]
    required_slots = _required_slot_keys(minimum_rows_by_case or _minimum_rows_by_case())
    selected_row_count = 0
    normalized_rows: list[dict[str, Any]] = []
    validation_error = ""
    status = "row_artifact_missing"
    blocker = "pocketmd_lite_topk_rows_not_acquired"
    if selected_resolved_path is not None:
        try:
            raw_rows = _read_source_rows(selected_resolved_path)
            selected_row_count = len(raw_rows)
            if not raw_rows:
                status = "row_artifact_detected_empty"
                blocker = "pocketmd_lite_topk_rows_empty"
            else:
                normalized_rows = [
                    _normalize_row(
                        row,
                        row_index=index,
                        max_top_k=DEFAULT_MAX_TOP_K,
                    )
                    for index, row in enumerate(raw_rows, start=1)
                ]
                _validate_topk_integrity(normalized_rows)
                observed_slots = {
                    (str(row["case_id"]), int(row["top_k_rank"]))
                    for row in normalized_rows
                }
                missing_slots = sorted(required_slots - observed_slots)
                if missing_slots:
                    status = "row_artifact_detected_incomplete_coverage"
                    blocker = "pocketmd_lite_required_topk_slots_missing"
                else:
                    status = "row_artifact_detected_validated"
                    blocker = ""
        except Exception as exc:
            status = "row_artifact_detected_invalid"
            blocker = "pocketmd_lite_topk_rows_invalid"
            validation_error = str(exc)

    observed_slots = {
        (str(row["case_id"]), int(row["top_k_rank"]))
        for row in normalized_rows
    }
    missing_slots = sorted(required_slots - observed_slots)
    return {
        "status": status,
        "default_rows_out": str(rows_out),
        "candidate_paths": rows,
        "detected_row_artifact_count": len(detected_paths),
        "first_detected_path": detected_paths[0] if detected_paths else "",
        "selected_path": selected_path,
        "selected_row_count": selected_row_count,
        "validated_row_count": len(normalized_rows),
        "validated_case_count": len({str(row["case_id"]) for row in normalized_rows}),
        "covered_required_slot_count": len(required_slots - set(missing_slots)),
        "required_candidate_slot_count": len(required_slots),
        "missing_required_slots": [
            {"case_id": case_id, "top_k_rank": rank}
            for case_id, rank in missing_slots
        ],
        "case_top_k_rank_prefixes": _rank_prefixes(normalized_rows),
        "coverage_ready": bool(required_slots) and not missing_slots and not blocker,
        "validation_error": validation_error,
        "blocker": blocker,
    }


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


def _phase4_candidate_slot_matrix(
    *,
    minimum_rows_by_case: list[dict[str, Any]],
    raw_row_candidate_status: dict[str, Any],
) -> list[dict[str, Any]]:
    missing_slots = {
        (str(row.get("case_id") or ""), int(row.get("top_k_rank") or 0))
        for row in raw_row_candidate_status.get("missing_required_slots", [])
        if isinstance(row, dict)
    }
    case_rank_prefixes = raw_row_candidate_status.get("case_top_k_rank_prefixes")
    if not isinstance(case_rank_prefixes, dict):
        case_rank_prefixes = {}
    rows: list[dict[str, Any]] = []
    for row in minimum_rows_by_case:
        case_id = str(row.get("case_id") or "")
        ranks = row.get("required_top_k_rank_prefix")
        if not case_id or not isinstance(ranks, list):
            continue
        observed_ranks = {
            int(rank)
            for rank in case_rank_prefixes.get(case_id, [])
            if str(rank)
        }
        for raw_rank in ranks:
            try:
                rank = int(raw_rank)
            except (TypeError, ValueError):
                continue
            missing = (case_id, rank) in missing_slots or rank not in observed_ranks
            rows.append(
                {
                    "slot_id": f"{case_id}_rank_{rank}",
                    "case_id": case_id,
                    "top_k_rank": rank,
                    "status": "missing" if missing else "provided",
                    "missing": missing,
                    "candidate_scope": str(
                        row.get("candidate_scope")
                        or "upstream_ranked_top_k_candidates_only"
                    ),
                    "required_receipt_roles": [
                        "upstream_top_k_candidate_scope_receipt",
                        "lite_refinement_run_receipt",
                        "interaction_persistence_receipt",
                        "uncertainty_interval_receipt",
                    ],
                    "required_metric_fields": [
                        "local_min_survived",
                        "contact_persistence_rate",
                        "h_bond_persistence_rate",
                        "clash_count_before",
                        "clash_count_after",
                        "uncertainty_low",
                        "uncertainty_high",
                        "uncertainty_unit",
                    ],
                    "closes_phase4_criteria": [
                        "top_k_refinement_rows_present",
                        "top_k_refinement_case_coverage",
                        "local_min_survival_materialized",
                        "contact_persistence_materialized",
                        "h_bond_persistence_materialized",
                        "clash_relief_materialized",
                        "uncertainty_summary_materialized",
                        "report_blockers_resolved",
                    ],
                    "operator_action": (
                        "attach_pocketmd_rows_at_"
                        f"{DEFAULT_ROWS_OUT}"
                        if missing
                        else "review_validated_pocketmd_lite_rows_and_attach_receipts"
                    ),
                    "claim_boundary": (
                        "This slot maps one required case/rank candidate to the "
                        "bounded PocketMD Lite metric rows it must carry. It is "
                        "not evidence until real top-k rows and receipts pass."
                    ),
                }
            )
    return rows


def _phase4_metric_closure_matrix(
    *,
    metric_receipt_contract: list[dict[str, Any]],
    phase4_refinement_receipt_plan: dict[str, Any],
    raw_row_candidate_status: dict[str, Any],
) -> list[dict[str, Any]]:
    metric_contracts = {
        str(row.get("metric_id") or ""): row
        for row in metric_receipt_contract
        if isinstance(row, dict)
    }
    receipt_roles = [
        row
        for row in phase4_refinement_receipt_plan.get("receipt_roles", [])
        if isinstance(row, dict)
    ]
    criteria = [
        "top_k_refinement_rows_present",
        "top_k_refinement_case_coverage",
        "local_min_survival_materialized",
        "contact_persistence_materialized",
        "h_bond_persistence_materialized",
        "clash_relief_materialized",
        "uncertainty_summary_materialized",
        "report_blockers_resolved",
    ]
    rows: list[dict[str, Any]] = []
    for criterion_id in criteria:
        closing_roles = [
            str(row.get("receipt_role_id") or "")
            for row in receipt_roles
            if criterion_id in list(row.get("closes_phase4_criteria") or [])
        ]
        metric_id = str(PHASE4_METRIC_CRITERIA.get(criterion_id, {}).get("metric_id") or "")
        metric_contract = metric_contracts.get(metric_id, {})
        rows.append(
            {
                "criterion_id": criterion_id,
                "status": "blocked",
                "metric_id": metric_id,
                "required_row_fields": list(
                    metric_contract.get("required_row_fields") or []
                ),
                "required_value_policy": str(
                    metric_contract.get("required_value_policy") or ""
                ),
                "receipt_roles": closing_roles,
                "materialized_report_field": str(
                    PHASE4_METRIC_CRITERIA.get(criterion_id, {}).get(
                        "materialized_report_field"
                    )
                    or ""
                ),
                "current": {
                    "row_artifact_detected": (
                        int(
                            raw_row_candidate_status.get(
                                "detected_row_artifact_count"
                            )
                            or 0
                        )
                        > 0
                    ),
                    "coverage_ready": bool(
                        raw_row_candidate_status.get("coverage_ready")
                    ),
                    "validated_row_count": int(
                        raw_row_candidate_status.get("validated_row_count") or 0
                    ),
                    "covered_required_slot_count": int(
                        raw_row_candidate_status.get("covered_required_slot_count")
                        or 0
                    ),
                    "required_candidate_slot_count": int(
                        raw_row_candidate_status.get("required_candidate_slot_count")
                        or 0
                    ),
                },
                "blockers": [
                    str(raw_row_candidate_status.get("blocker") or "")
                    or "pocketmd_lite_topk_rows_not_acquired",
                    "upstream_top_k_candidate_receipts_not_attached",
                    "lite_refinement_metric_receipts_not_attached",
                ],
                "claim_boundary": (
                    "This row maps a PocketMD Lite Phase 4 criterion to the "
                    "row fields and receipt roles that can close it. It is not "
                    "closure evidence until the rows and receipts materialize."
                ),
            }
        )
    return rows


def _phase4_metric_receipt_actions(
    phase4_metric_closure_matrix: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        {
            "criterion_id": str(row.get("criterion_id") or ""),
            "status": str(row.get("status") or ""),
            "metric_id": str(row.get("metric_id") or ""),
            "required_row_fields": list(row.get("required_row_fields") or []),
            "required_value_policy": str(row.get("required_value_policy") or ""),
            "receipt_roles": list(row.get("receipt_roles") or []),
            "materialized_report_field": str(
                row.get("materialized_report_field") or ""
            ),
            "blockers": list(row.get("blockers") or []),
        }
        for row in phase4_metric_closure_matrix
        if isinstance(row, dict)
    ]


def _survival_report_status(repo_root: Path) -> dict[str, Any]:
    report = _load_json(repo_root, DEFAULT_SURVIVAL_REPORT)
    summary = _as_dict(report.get("summary"))
    operator_input_source_receipt = _as_dict(
        report.get("operator_input_source_receipt")
    )
    blockers = [
        str(row) for row in report.get("blockers", []) if str(row)
    ] if isinstance(report.get("blockers"), list) else []
    return {
        "artifact": str(DEFAULT_SURVIVAL_REPORT),
        "present": bool(report),
        "status": str(report.get("status") or "missing"),
        "contract_pass": bool(report.get("contract_pass")),
        "product_surface_ready": bool(report.get("product_surface_ready")),
        "first_blocked_target": str(report.get("first_blocked_target") or ""),
        "blocker_count": len(blockers),
        "blockers": blockers,
        "summary": summary,
        "operator_input_source_receipt": operator_input_source_receipt,
    }


def _phase4_completion_audit(
    *,
    raw_row_candidate_status: dict[str, Any],
    phase4_refinement_receipt_plan: dict[str, Any],
    survival_report_status: dict[str, Any],
) -> dict[str, Any]:
    survival_summary = _as_dict(survival_report_status.get("summary"))
    survival_blockers = set(
        str(row)
        for row in survival_report_status.get("blockers", [])
        if str(row)
    )
    rows_present = (
        int(raw_row_candidate_status.get("detected_row_artifact_count") or 0) > 0
    )
    coverage_ready = bool(raw_row_candidate_status.get("coverage_ready"))
    raw_row_blocker = str(raw_row_candidate_status.get("blocker") or "")
    guard_pass = (
        TOP_K_SCOPE_POLICY.startswith("PocketMD Lite refinement rows are bounded")
        and PHASE4_REFINEMENT_RECEIPT_PROMOTION_POLICY[
            "broad_all_atom_or_fep_claims_unlocked"
        ]
        is False
        and "broad_all_atom_fep_claims_locked"
        in phase4_refinement_receipt_plan.get("preserved_phase4_criteria", [])
    )
    requirement_rows: list[dict[str, Any]] = []
    for requirement in PHASE4_COMPLETION_REQUIREMENTS:
        evidence_kind = str(requirement["evidence_kind"])
        blockers: list[str] = []
        current: dict[str, Any]
        required: dict[str, Any]
        requirement_pass = False
        if evidence_kind == "contract_guard":
            requirement_pass = guard_pass
            current = {
                "top_k_scope_policy_present": bool(TOP_K_SCOPE_POLICY),
                "broad_all_atom_or_fep_claims_unlocked": (
                    PHASE4_REFINEMENT_RECEIPT_PROMOTION_POLICY[
                        "broad_all_atom_or_fep_claims_unlocked"
                    ]
                ),
                "preserved_phase4_criteria": list(
                    phase4_refinement_receipt_plan.get(
                        "preserved_phase4_criteria", []
                    )
                ),
            }
            required = {
                "top_k_scope_policy_present": True,
                "broad_all_atom_or_fep_claims_unlocked": False,
                "preserved_phase4_criteria_contains": (
                    "broad_all_atom_fep_claims_locked"
                ),
            }
            if not requirement_pass:
                blockers.append("pocketmd_lite_top_k_scope_contract_not_enforced")
        elif evidence_kind == "row_coverage":
            if requirement["requirement_id"] == "top_k_refinement_rows_present":
                requirement_pass = rows_present and coverage_ready
                current = {
                    "row_artifact_detected": rows_present,
                    "validated_row_count": int(
                        raw_row_candidate_status.get("validated_row_count") or 0
                    ),
                    "required_candidate_slot_count": int(
                        raw_row_candidate_status.get(
                            "required_candidate_slot_count"
                        )
                        or 0
                    ),
                }
            else:
                requirement_pass = coverage_ready
                current = {
                    "coverage_ready": coverage_ready,
                    "covered_required_slot_count": int(
                        raw_row_candidate_status.get("covered_required_slot_count")
                        or 0
                    ),
                    "required_candidate_slot_count": int(
                        raw_row_candidate_status.get(
                            "required_candidate_slot_count"
                        )
                        or 0
                    ),
                }
            required = {
                "coverage_ready": True,
                "min_real_refinement_case_count": int(
                    TOPK_ROW_QUALITY_CRITERIA["min_real_refinement_case_count"]
                ),
                "min_total_top_k_candidate_count": int(
                    TOPK_ROW_QUALITY_CRITERIA["min_total_top_k_candidate_count"]
                ),
            }
            if not requirement_pass:
                blockers.extend(
                    [
                        raw_row_blocker
                        or "pocketmd_lite_topk_candidate_rows_missing",
                        "pocketmd_lite_topk_candidate_rows_missing",
                    ]
                )
        else:
            summary_field = str(requirement.get("summary_field") or "")
            blocker_id = str(requirement.get("blocker_id") or "")
            metric_value = survival_summary.get(summary_field)
            requirement_pass = (
                metric_value is not None
                and blocker_id not in survival_blockers
                and bool(survival_report_status.get("contract_pass"))
            )
            current = {
                "survival_report_status": str(
                    survival_report_status.get("status") or ""
                ),
                "survival_report_contract_pass": bool(
                    survival_report_status.get("contract_pass")
                ),
                "summary_field": summary_field,
                "summary_value": metric_value,
            }
            required = {
                "survival_report_contract_pass": True,
                "summary_field_non_null": True,
                "blocker_absent": blocker_id,
            }
            if not requirement_pass:
                blockers.append(blocker_id)
                if raw_row_blocker:
                    blockers.append(raw_row_blocker)
        blockers = list(dict.fromkeys(row for row in blockers if row))
        requirement_rows.append(
            {
                **requirement,
                "status": "ready" if requirement_pass else "blocked",
                "pass": requirement_pass,
                "current": current,
                "required": required,
                "blockers": blockers,
                "claim_boundary": (
                    "This audit row records whether the PocketMD Lite Phase 4 "
                    "requirement is closed by live row/source evidence. It does "
                    "not synthesize refinement metrics."
                ),
            }
        )
    blocked_rows = [row for row in requirement_rows if not bool(row["pass"])]
    remaining_blockers = list(
        dict.fromkeys(
            str(blocker)
            for row in blocked_rows
            for blocker in row.get("blockers", [])
            if str(blocker)
        )
    )
    if not blocked_rows:
        status = "ready"
    elif not coverage_ready:
        status = "operator_topk_rows_required"
    else:
        status = "metric_receipts_required"
    return {
        "status": status,
        "pass": not blocked_rows,
        "actual_closure_ready": (
            not blocked_rows
            and bool(survival_report_status.get("product_surface_ready"))
        ),
        "requirement_count": len(requirement_rows),
        "ready_requirement_count": len(requirement_rows) - len(blocked_rows),
        "blocked_requirement_count": len(blocked_rows),
        "blocked_requirement_ids": [
            str(row["requirement_id"]) for row in blocked_rows
        ],
        "remaining_row_inputs": [] if coverage_ready else ["pocketmd_rows"],
        "remaining_blockers": remaining_blockers,
        "remaining_operator_action": (
            "run_pocketmd_lite_raw_row_importer_and_survival_materializer"
            if coverage_ready
            else f"attach_pocketmd_rows_at_{DEFAULT_ROWS_OUT}"
        ),
        "survival_report": survival_report_status,
        "requirements": requirement_rows,
        "claim_boundary": (
            "This audit proves only the PocketMD Lite top-k refinement closure "
            "state. Full closure still requires real bounded top-k rows, source "
            "receipts, local-min/contact/H-bond/clash/uncertainty metrics, and "
            "a passing survival report."
        ),
    }


def _phase4_actual_evidence_audit(
    *,
    raw_row_candidate_status: dict[str, Any],
    phase4_completion_audit: dict[str, Any],
    survival_report_status: dict[str, Any],
    template_preflight_summary: dict[str, Any],
) -> dict[str, Any]:
    required_slot_count = int(
        raw_row_candidate_status.get("required_candidate_slot_count") or 0
    )
    covered_slot_count = int(
        raw_row_candidate_status.get("covered_required_slot_count") or 0
    )
    missing_slots = [
        row
        for row in raw_row_candidate_status.get("missing_required_slots", [])
        if isinstance(row, dict)
    ]
    row_slot_ready = bool(raw_row_candidate_status.get("coverage_ready"))
    required_role_receipt_count = required_slot_count * len(
        PHASE4_CRITERIA_BY_RECEIPT_ROLE
    )
    role_receipt_plan_count = int(
        template_preflight_summary.get("role_receipt_plan_count") or 0
    )
    role_receipt_blocked_count = int(
        template_preflight_summary.get("role_receipt_blocked_count") or 0
    )
    role_receipts_ready = (
        bool(template_preflight_summary.get("present"))
        and role_receipt_plan_count >= required_role_receipt_count
        and role_receipt_blocked_count == 0
    )

    operator_source_receipt = _as_dict(
        survival_report_status.get("operator_input_source_receipt")
    )
    operator_source_receipt_blockers = [
        str(row)
        for row in operator_source_receipt.get("blockers", [])
        if str(row)
    ] if isinstance(operator_source_receipt.get("blockers"), list) else []
    operator_source_receipt_ready = bool(
        operator_source_receipt.get("contract_pass")
    )
    template_source_requirement_count = int(
        template_preflight_summary.get(
            "operator_input_source_receipt_requirement_count"
        )
        or 0
    )
    required_source_receipt_field_count = len(
        SOURCE_RECEIPT_REQUIREMENTS.get("required_fields", [])
    )
    template_source_blocked_count = int(
        template_preflight_summary.get(
            "operator_input_source_receipt_blocked_count"
        )
        or 0
    )
    template_source_receipt_ready = (
        bool(template_preflight_summary.get("present"))
        and template_source_requirement_count >= required_source_receipt_field_count
        and template_source_blocked_count == 0
    )

    survival_summary = _as_dict(survival_report_status.get("summary"))
    survival_blockers = {
        str(row)
        for row in survival_report_status.get("blockers", [])
        if str(row)
    }
    metric_rows: list[dict[str, Any]] = []
    for requirement in PHASE4_COMPLETION_REQUIREMENTS:
        if requirement.get("evidence_kind") != "survival_summary_metric":
            continue
        summary_field = str(requirement.get("summary_field") or "")
        blocker_id = str(requirement.get("blocker_id") or "")
        current_value = survival_summary.get(summary_field)
        metric_ready = (
            current_value is not None
            and blocker_id not in survival_blockers
            and bool(survival_report_status.get("contract_pass"))
        )
        metric_rows.append(
            {
                "requirement_id": str(requirement["requirement_id"]),
                "phase4_criterion_id": str(requirement["phase4_criterion_id"]),
                "summary_field": summary_field,
                "current": current_value,
                "required": "present",
                "status": "ready" if metric_ready else "blocked",
                "pass": metric_ready,
                "blockers": [] if metric_ready else [blocker_id],
            }
        )
    missing_metric_rows = [row for row in metric_rows if not bool(row["pass"])]
    metric_summary_ready = bool(metric_rows) and not missing_metric_rows

    component_rows = [
        {
            "component_id": "bounded_top_k_row_slots",
            "status": "ready" if row_slot_ready else "blocked",
            "pass": row_slot_ready,
            "current": {
                "raw_row_candidate_status": str(
                    raw_row_candidate_status.get("status") or ""
                ),
                "covered_required_slot_count": covered_slot_count,
                "required_candidate_slot_count": required_slot_count,
                "missing_required_slot_count": len(missing_slots),
            },
            "required": {
                "coverage_ready": True,
                "required_candidate_slot_count": required_slot_count,
            },
            "blockers": (
                []
                if row_slot_ready
                else [
                    str(raw_row_candidate_status.get("blocker") or ""),
                    "pocketmd_lite_topk_candidate_rows_missing",
                ]
            ),
        },
        {
            "component_id": "per_candidate_role_receipts",
            "status": "ready" if role_receipts_ready else "blocked",
            "pass": role_receipts_ready,
            "current": {
                "template_preflight_status": str(
                    template_preflight_summary.get("status") or ""
                ),
                "role_receipt_plan_count": role_receipt_plan_count,
                "role_receipt_blocked_count": role_receipt_blocked_count,
            },
            "required": {
                "role_receipt_plan_count": required_role_receipt_count,
                "role_receipt_blocked_count": 0,
            },
            "blockers": [] if role_receipts_ready else [
                "pocketmd_lite_per_candidate_role_receipts_incomplete"
            ],
        },
        {
            "component_id": "operator_input_source_receipt",
            "status": (
                "ready"
                if operator_source_receipt_ready and template_source_receipt_ready
                else "blocked"
            ),
            "pass": operator_source_receipt_ready and template_source_receipt_ready,
            "current": {
                "survival_report_receipt_contract_pass": (
                    operator_source_receipt_ready
                ),
                "survival_report_receipt_status": str(
                    operator_source_receipt.get("status") or ""
                ),
                "survival_report_receipt_blocker_count": len(
                    operator_source_receipt_blockers
                ),
                "template_preflight_requirement_count": (
                    template_source_requirement_count
                ),
                "template_preflight_blocked_count": template_source_blocked_count,
            },
            "required": {
                "survival_report_receipt_contract_pass": True,
                "template_preflight_requirement_count": (
                    required_source_receipt_field_count
                ),
                "template_preflight_blocked_count": 0,
            },
            "blockers": (
                []
                if operator_source_receipt_ready and template_source_receipt_ready
                else list(
                    dict.fromkeys(
                        [
                            *operator_source_receipt_blockers,
                            "pocketmd_lite_operator_input_source_receipt_incomplete",
                        ]
                    )
                )
            ),
        },
        {
            "component_id": "survival_metric_summary",
            "status": "ready" if metric_summary_ready else "blocked",
            "pass": metric_summary_ready,
            "current": {
                "survival_report_status": str(
                    survival_report_status.get("status") or ""
                ),
                "survival_report_contract_pass": bool(
                    survival_report_status.get("contract_pass")
                ),
                "reported_metric_count": len(metric_rows)
                - len(missing_metric_rows),
                "required_metric_count": len(metric_rows),
            },
            "required": {
                "survival_report_contract_pass": True,
                "required_metric_count": len(metric_rows),
                "missing_metric_count": 0,
            },
            "blockers": list(
                dict.fromkeys(
                    str(blocker)
                    for row in missing_metric_rows
                    for blocker in row.get("blockers", [])
                    if str(blocker)
                )
            ),
        },
    ]
    component_rows = [
        {
            **row,
            "blockers": list(
                dict.fromkeys(
                    str(blocker)
                    for blocker in row.get("blockers", [])
                    if str(blocker)
                )
            ),
        }
        for row in component_rows
    ]
    blocked_components = [row for row in component_rows if not bool(row["pass"])]
    remaining_blockers = list(
        dict.fromkeys(
            [
                *[
                    str(blocker)
                    for blocker in phase4_completion_audit.get(
                        "remaining_blockers", []
                    )
                    if str(blocker)
                ],
                *[
                    str(blocker)
                    for row in blocked_components
                    for blocker in row.get("blockers", [])
                    if str(blocker)
                ],
            ]
        )
    )
    if not blocked_components and bool(
        phase4_completion_audit.get("actual_closure_ready")
    ):
        status = "ready"
    elif not row_slot_ready:
        status = "operator_topk_rows_required"
    elif not role_receipts_ready or not template_source_receipt_ready:
        status = "source_receipts_required"
    elif not metric_summary_ready:
        status = "metric_receipts_required"
    else:
        status = "survival_materializer_required"
    return {
        "status": status,
        "pass": not blocked_components,
        "actual_closure_ready": (
            not blocked_components
            and bool(phase4_completion_audit.get("actual_closure_ready"))
        ),
        "component_count": len(component_rows),
        "ready_component_count": len(component_rows) - len(blocked_components),
        "blocked_component_count": len(blocked_components),
        "blocked_component_ids": [
            str(row["component_id"]) for row in blocked_components
        ],
        "remaining_blockers": remaining_blockers,
        "remaining_evidence": [
            str(row["component_id"]) for row in blocked_components
        ],
        "row_slot_coverage": {
            "status": "ready" if row_slot_ready else "blocked",
            "pass": row_slot_ready,
            "required_candidate_slot_count": required_slot_count,
            "covered_required_slot_count": covered_slot_count,
            "missing_required_slot_count": len(missing_slots),
            "missing_required_slots": missing_slots,
            "raw_row_candidate_status": raw_row_candidate_status,
        },
        "template_preflight_evidence": {
            "present": bool(template_preflight_summary.get("present")),
            "artifact": str(template_preflight_summary.get("artifact") or ""),
            "status": str(template_preflight_summary.get("status") or ""),
            "top_k_template_ready": bool(
                template_preflight_summary.get("top_k_template_ready")
            ),
            "role_receipt_plan_count": role_receipt_plan_count,
            "role_receipt_blocked_count": role_receipt_blocked_count,
            "operator_input_source_receipt_requirement_count": (
                template_source_requirement_count
            ),
            "operator_input_source_receipt_blocked_count": (
                template_source_blocked_count
            ),
            "first_blocked_role_receipt": _as_dict(
                template_preflight_summary.get("first_blocked_role_receipt")
            ),
            "first_blocked_operator_input_source_receipt": _as_dict(
                template_preflight_summary.get(
                    "first_blocked_operator_input_source_receipt"
                )
            ),
        },
        "operator_input_source_receipt": {
            "status": str(operator_source_receipt.get("status") or "missing"),
            "contract_pass": operator_source_receipt_ready,
            "blocker_count": len(operator_source_receipt_blockers),
            "blockers": operator_source_receipt_blockers,
        },
        "survival_metric_summary": {
            "status": "ready" if metric_summary_ready else "blocked",
            "pass": metric_summary_ready,
            "reported_metric_count": len(metric_rows) - len(missing_metric_rows),
            "required_metric_count": len(metric_rows),
            "missing_metric_count": len(missing_metric_rows),
            "metrics": metric_rows,
        },
        "components": component_rows,
        "claim_boundary": (
            "This audit summarizes actual PocketMD Lite closure evidence only. "
            "It keeps top-k scope, source receipts, survival metrics, and broad "
            "all-atom/FEP claim locks visible without fabricating operator rows."
        ),
    }


def _first_blocked_row(rows: list[Any]) -> dict[str, Any]:
    for row in rows:
        if isinstance(row, dict) and row.get("status") != "ready":
            return row
    return {}


def _template_preflight_summary(repo_root: Path) -> dict[str, Any]:
    payload = _load_json(repo_root, DEFAULT_ROWS_TEMPLATE_PREFLIGHT)
    if not payload:
        return {
            "present": False,
            "artifact": str(DEFAULT_ROWS_TEMPLATE_PREFLIGHT),
            "markdown_artifact": str(DEFAULT_ROWS_TEMPLATE_PREFLIGHT_MD),
            "status": "missing",
            "role_receipt_plan_count": 0,
            "role_receipt_blocked_count": 0,
            "operator_input_source_receipt_requirement_count": 0,
            "operator_input_source_receipt_blocked_count": 0,
            "first_blocked_role_receipt": {},
            "first_blocked_operator_input_source_receipt": {},
        }
    role_receipt_plan = [
        row for row in payload.get("role_receipt_plan", []) if isinstance(row, dict)
    ]
    operator_input_source_receipt_plan = [
        row
        for row in payload.get("operator_input_source_receipt_plan", [])
        if isinstance(row, dict)
    ]
    summary = payload.get("summary")
    if not isinstance(summary, dict):
        summary = {}
    return {
        "present": True,
        "artifact": str(DEFAULT_ROWS_TEMPLATE_PREFLIGHT),
        "markdown_artifact": str(DEFAULT_ROWS_TEMPLATE_PREFLIGHT_MD),
        "status": str(payload.get("status") or ""),
        "top_k_template_ready": bool(payload.get("top_k_template_ready")),
        "expected_rows_detected": bool(payload.get("expected_rows_detected")),
        "role_receipt_plan_count": int(
            summary.get("role_receipt_plan_count") or len(role_receipt_plan)
        ),
        "role_receipt_blocked_count": int(
            summary.get("role_receipt_blocked_count")
            or sum(1 for row in role_receipt_plan if row.get("status") != "ready")
        ),
        "operator_input_source_receipt_requirement_count": int(
            summary.get("operator_input_source_receipt_requirement_count")
            or len(operator_input_source_receipt_plan)
        ),
        "operator_input_source_receipt_blocked_count": int(
            summary.get("operator_input_source_receipt_blocked_count")
            or sum(
                1
                for row in operator_input_source_receipt_plan
                if row.get("status") != "ready"
            )
        ),
        "first_blocked_role_receipt": _first_blocked_row(role_receipt_plan),
        "first_blocked_operator_input_source_receipt": _first_blocked_row(
            operator_input_source_receipt_plan
        ),
    }


def _refinement_execution_plan_command() -> str:
    return (
        "python3 scripts/build_pocketmd_lite_refinement_execution_plan.py "
        f"--out {DEFAULT_REFINEMENT_EXECUTION_PLAN}"
    )


def _rows_from_receipt_bundle_report_summary(repo_root: Path) -> dict[str, Any]:
    payload = _load_json(repo_root, DEFAULT_ROWS_FROM_RECEIPT_BUNDLE_REPORT)
    if not payload:
        return {
            "present": False,
            "artifact": str(DEFAULT_ROWS_FROM_RECEIPT_BUNDLE_REPORT),
            "status": "missing",
            "rows_materialized": False,
            "receipt_count": 0,
            "ready_receipt_count": 0,
            "row_count": 0,
            "blocker_count": 0,
            "first_incomplete_receipt": {},
            "receipt_completion_action_plan": [],
            "receipt_metric_family_completion_plan": [],
            "receipt_metric_family_count": 0,
            "receipt_metric_family_blocked_count": 0,
            "receipt_metric_family_missing_field_occurrence_count": 0,
            "incomplete_receipt_count": 0,
            "unique_missing_required_fields": [],
            "unique_missing_required_field_count": 0,
            "total_missing_required_field_count": 0,
        }
    row_statuses = [
        row for row in payload.get("row_statuses", []) if isinstance(row, dict)
    ]
    summary = payload.get("summary")
    if not isinstance(summary, dict):
        summary = {}
    receipt_completion_action_plan = [
        row
        for row in _as_list(payload.get("receipt_completion_action_plan"))
        if isinstance(row, dict)
    ]
    receipt_metric_family_completion_plan = (
        _receipt_metric_family_completion_plan(receipt_completion_action_plan)
    )
    return {
        "present": True,
        "artifact": str(DEFAULT_ROWS_FROM_RECEIPT_BUNDLE_REPORT),
        "status": str(payload.get("status") or ""),
        "rows_materialized": bool(payload.get("rows_materialized")),
        "receipt_count": int(payload.get("receipt_count") or 0),
        "ready_receipt_count": int(payload.get("ready_receipt_count") or 0),
        "row_count": int(payload.get("row_count") or 0),
        "blocker_count": int(summary.get("blocker_count") or 0),
        "first_incomplete_receipt": _as_dict(
            payload.get("first_incomplete_receipt")
        )
        or _first_blocked_row(row_statuses),
        "receipt_completion_action_plan": receipt_completion_action_plan,
        "receipt_metric_family_completion_plan": (
            receipt_metric_family_completion_plan
        ),
        "receipt_metric_family_count": len(receipt_metric_family_completion_plan),
        "receipt_metric_family_blocked_count": sum(
            1
            for row in receipt_metric_family_completion_plan
            if row.get("status") != "ready"
        ),
        "receipt_metric_family_missing_field_occurrence_count": sum(
            int(row.get("missing_field_occurrence_count") or 0)
            for row in receipt_metric_family_completion_plan
        ),
        "incomplete_receipt_count": int(
            payload.get("incomplete_receipt_count")
            or summary.get("incomplete_receipt_count")
            or 0
        ),
        "unique_missing_required_fields": [
            str(field)
            for field in _as_list(payload.get("unique_missing_required_fields"))
            if str(field)
        ],
        "unique_missing_required_field_count": int(
            payload.get("unique_missing_required_field_count")
            or summary.get("unique_missing_required_field_count")
            or 0
        ),
        "total_missing_required_field_count": int(
            payload.get("total_missing_required_field_count")
            or summary.get("total_missing_required_field_count")
            or 0
        ),
    }


def _refinement_execution_plan_summary(
    minimum_rows_by_case: list[dict[str, Any]],
    *,
    operator_rows_ready: bool,
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
        "operator_rows_ready": operator_rows_ready,
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


def _pocketmd_rows_operator_action(
    *,
    raw_row_candidate_status: dict[str, Any],
    minimum_rows_by_case: list[dict[str, Any]],
    phase4_metric_closure_matrix: list[dict[str, Any]],
    required_flat_row_fields: list[str],
    template_preflight_summary: dict[str, Any],
    rows_from_receipt_bundle_report_summary: dict[str, Any],
    commands: dict[str, str],
) -> dict[str, Any]:
    row_blocker = str(raw_row_candidate_status.get("blocker") or "")
    required_candidate_slot_count = sum(
        len(row.get("required_top_k_rank_prefix") or [])
        for row in minimum_rows_by_case
    )
    operator_action = (
        "review_validated_pocketmd_lite_rows_and_attach_receipts"
        if raw_row_candidate_status.get("coverage_ready")
        else f"attach_pocketmd_rows_at_{DEFAULT_ROWS_OUT}"
    )
    phase4_metric_receipt_actions = _phase4_metric_receipt_actions(
        phase4_metric_closure_matrix
    )
    return {
        "row_input_id": "pocketmd_rows",
        "status": "provided" if raw_row_candidate_status.get("coverage_ready") else "missing",
        "operator_action": operator_action,
        "default_row_artifact": str(DEFAULT_ROWS_OUT),
        "template_artifact": str(DEFAULT_ROWS_TEMPLATE),
        "accepted_formats": list(SUPPORTED_ROW_FORMATS),
        "required_case_count": len(minimum_rows_by_case),
        "required_candidate_slot_count": required_candidate_slot_count,
        "required_total_candidate_rows": int(
            TOPK_ROW_QUALITY_CRITERIA["min_total_top_k_candidate_count"]
        ),
        "required_candidate_rows_per_case": int(
            TOPK_ROW_QUALITY_CRITERIA["min_candidate_count_per_case"]
        ),
        "required_top_k_rank_coverage_per_case": int(
            TOPK_ROW_QUALITY_CRITERIA["min_top_k_rank_coverage_per_case"]
        ),
        "required_flat_row_fields": list(required_flat_row_fields),
        "required_minimum_rows_by_case": minimum_rows_by_case,
        "raw_row_candidate_status": raw_row_candidate_status,
        "row_preflight_action_packet": {
            "status": str(
                raw_row_candidate_status.get("status") or "row_artifact_missing"
            ),
            "expected_rows_artifact": str(DEFAULT_ROWS_OUT),
            "supported_candidate_paths": [
                str(row.get("path") or "")
                for row in raw_row_candidate_status.get("candidate_paths", [])
                if isinstance(row, dict)
            ],
            "detected_row_artifact_count": int(
                raw_row_candidate_status.get("detected_row_artifact_count") or 0
            ),
            "selected_path": str(raw_row_candidate_status.get("selected_path") or ""),
            "selected_row_count": int(
                raw_row_candidate_status.get("selected_row_count") or 0
            ),
            "validated_row_count": int(
                raw_row_candidate_status.get("validated_row_count") or 0
            ),
            "validated_case_count": int(
                raw_row_candidate_status.get("validated_case_count") or 0
            ),
            "covered_required_slot_count": int(
                raw_row_candidate_status.get("covered_required_slot_count") or 0
            ),
            "required_candidate_slot_count": int(
                raw_row_candidate_status.get("required_candidate_slot_count") or 0
            ),
            "missing_required_slots": [
                row
                for row in raw_row_candidate_status.get("missing_required_slots", [])
                if isinstance(row, dict)
            ],
            "validation_error": str(
                raw_row_candidate_status.get("validation_error") or ""
            ),
            "blocker": row_blocker,
            "template_preflight_artifact": str(DEFAULT_ROWS_TEMPLATE_PREFLIGHT),
            "template_preflight_markdown_artifact": str(
                DEFAULT_ROWS_TEMPLATE_PREFLIGHT_MD
            ),
            "template_preflight_summary": template_preflight_summary,
            "review_template_command": commands["review_row_template"],
            "build_template_preflight_command": commands[
                "build_row_template_preflight"
            ],
            "materialize_rows_from_template_command": commands[
                "materialize_rows_from_template"
            ],
            "import_rows_command": commands["import_rows"],
            "verify_science_actual_closure_command": (
                commands["science_actual_closure"]
            ),
            "template_safety_policy": {
                "template_is_not_evidence": True,
                "operator_rows_must_be_real_top_k_refinement_outputs": True,
                "placeholder_or_fixture_rows_do_not_promote": True,
                "preflight_does_not_run_refinement": True,
                "broad_all_atom_or_fep_claims_remain_locked": True,
            },
        },
        "top_k_rows_action_packet": {
            "status": (
                "operator_rows_ready"
                if raw_row_candidate_status.get("coverage_ready")
                else "operator_rows_required"
            ),
            "template_artifact": str(DEFAULT_ROWS_TEMPLATE),
            "template_preflight_artifact": str(DEFAULT_ROWS_TEMPLATE_PREFLIGHT),
            "template_preflight_markdown_artifact": str(
                DEFAULT_ROWS_TEMPLATE_PREFLIGHT_MD
            ),
            "expected_rows_artifact": str(DEFAULT_ROWS_OUT),
            "role_receipt_plan_summary": {
                "role_receipt_plan_count": int(
                    template_preflight_summary.get("role_receipt_plan_count") or 0
                ),
                "role_receipt_blocked_count": int(
                    template_preflight_summary.get("role_receipt_blocked_count") or 0
                ),
                "first_blocked_role_receipt": dict(
                    template_preflight_summary.get("first_blocked_role_receipt") or {}
                ),
            },
            "operator_input_source_receipt_plan_summary": {
                "requirement_count": int(
                    template_preflight_summary.get(
                        "operator_input_source_receipt_requirement_count"
                    )
                    or 0
                ),
                "blocked_count": int(
                    template_preflight_summary.get(
                        "operator_input_source_receipt_blocked_count"
                    )
                    or 0
                ),
                "first_blocked_receipt": dict(
                    template_preflight_summary.get(
                        "first_blocked_operator_input_source_receipt"
                    )
                    or {}
                ),
            },
            "rows_from_receipt_bundle_report": (
                rows_from_receipt_bundle_report_summary
            ),
            "supported_candidate_paths": [
                str(row.get("path") or "")
                for row in raw_row_candidate_status.get("candidate_paths", [])
                if isinstance(row, dict)
            ],
            "review_template_command": commands["review_row_template"],
            "build_template_preflight_command": commands[
                "build_row_template_preflight"
            ],
            "materialize_rows_from_template_command": commands[
                "materialize_rows_from_template"
            ],
            "materialize_rows_from_receipt_bundle_command": commands[
                "materialize_rows_from_receipt_bundle"
            ],
            "import_rows_command": commands["import_rows"],
            "materialize_survival_command": commands["materialize_survival"],
            "verify_science_actual_closure_command": (
                commands["science_actual_closure"]
            ),
            "operator_must_fill_or_verify": [
                *required_flat_row_fields,
                "operator_input_source.source_artifact",
                "operator_input_source.source_artifact_sha256",
                "operator_input_source.source_id",
                "operator_input_source.source_url",
                "operator_input_source.source_license",
            ],
            "required_receipt_roles": [
                "upstream_top_k_candidate_scope_receipt",
                "lite_refinement_run_receipt",
                "interaction_persistence_receipt",
                "uncertainty_interval_receipt",
            ],
            "phase4_metric_receipt_action_count": len(
                phase4_metric_receipt_actions
            ),
            "phase4_metric_receipt_actions": phase4_metric_receipt_actions,
            "template_safety_policy": {
                "template_is_not_evidence": True,
                "expected_rows_must_be_operator_reviewed": True,
                "placeholder_or_fixture_rows_do_not_promote": True,
                "summary_only_metrics_do_not_promote": True,
                "broad_all_atom_or_fep_claims_remain_locked": True,
            },
            "claim_boundary": (
                "The top-k rows scaffold is an operator checklist. It does not "
                "prove bounded Lite refinement until real candidate rows, "
                "source receipts, metric receipts, importer validation, and "
                "survival materialization all pass."
            ),
        },
        "closes_phase4_criteria": [
            "top_k_refinement_rows_present",
            "top_k_refinement_case_coverage",
            "local_min_survival_materialized",
            "contact_persistence_materialized",
            "h_bond_persistence_materialized",
            "clash_relief_materialized",
            "uncertainty_summary_materialized",
            "report_blockers_resolved",
        ],
        "required_receipt_roles": [
            "upstream_top_k_candidate_scope_receipt",
            "lite_refinement_run_receipt",
            "interaction_persistence_receipt",
            "uncertainty_interval_receipt",
        ],
        "operator_blockers_if_missing": [row_blocker] if row_blocker else [],
        "commands": {
            "review_row_template": commands["review_row_template"],
            "build_row_template_preflight": commands[
                "build_row_template_preflight"
            ],
            "materialize_rows_from_template": commands[
                "materialize_rows_from_template"
            ],
            "materialize_rows_from_receipt_bundle": commands[
                "materialize_rows_from_receipt_bundle"
            ],
            "import_rows": commands["import_rows"],
            "materialize_survival": commands["materialize_survival"],
            "science_actual_closure": commands["science_actual_closure"],
        },
        "claim_boundary": (
            "This action identifies the PocketMD Lite top-k row input needed for "
            "Phase 4 actual closure. It is not closure evidence until real rows "
            "and source receipts pass the importer and survival materializer."
        ),
    }


def build_pocketmd_lite_source_acquisition_plan(
    *,
    repo_root: Path = ROOT,
    rows_out: Path = DEFAULT_ROWS_OUT,
) -> dict[str, Any]:
    required_flat_row_fields = _required_flat_row_fields()
    minimum_rows_by_case = _minimum_rows_by_case()
    raw_row_candidate_status = _raw_row_candidate_status(
        repo_root,
        rows_out=rows_out,
        minimum_rows_by_case=minimum_rows_by_case,
    )
    row_artifact_detected = raw_row_candidate_status["detected_row_artifact_count"] > 0
    operator_rows_ready = bool(raw_row_candidate_status["coverage_ready"])
    blockers = []
    row_blocker = str(raw_row_candidate_status.get("blocker") or "")
    if row_blocker:
        blockers.append(row_blocker)
    blockers.extend(
        [
            "upstream_top_k_candidate_receipts_not_attached",
            "lite_refinement_metric_receipts_not_attached",
        ]
    )
    min_total = int(TOPK_ROW_QUALITY_CRITERIA["min_total_top_k_candidate_count"])
    min_cases = int(TOPK_ROW_QUALITY_CRITERIA["min_real_refinement_case_count"])
    phase4_refinement_receipt_plan = _phase4_refinement_receipt_plan()
    metric_receipt_contract = [
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
    ]
    phase4_candidate_slot_matrix = _phase4_candidate_slot_matrix(
        minimum_rows_by_case=minimum_rows_by_case,
        raw_row_candidate_status=raw_row_candidate_status,
    )
    phase4_metric_closure_matrix = _phase4_metric_closure_matrix(
        metric_receipt_contract=metric_receipt_contract,
        phase4_refinement_receipt_plan=phase4_refinement_receipt_plan,
        raw_row_candidate_status=raw_row_candidate_status,
    )
    survival_report_status = _survival_report_status(repo_root)
    phase4_completion_audit = _phase4_completion_audit(
        raw_row_candidate_status=raw_row_candidate_status,
        phase4_refinement_receipt_plan=phase4_refinement_receipt_plan,
        survival_report_status=survival_report_status,
    )
    template_preflight_summary = _template_preflight_summary(repo_root)
    rows_from_receipt_bundle_report_summary = (
        _rows_from_receipt_bundle_report_summary(repo_root)
    )
    phase4_actual_evidence_audit = _phase4_actual_evidence_audit(
        raw_row_candidate_status=raw_row_candidate_status,
        phase4_completion_audit=phase4_completion_audit,
        survival_report_status=survival_report_status,
        template_preflight_summary=template_preflight_summary,
    )
    refinement_execution_plan = _refinement_execution_plan_summary(
        minimum_rows_by_case,
        operator_rows_ready=operator_rows_ready,
    )
    commands = {
        "write_plan": (
            "python3 scripts/build_pocketmd_lite_source_acquisition_plan.py"
        ),
        "review_row_template": f"sed -n '1,20p' {DEFAULT_ROWS_TEMPLATE}",
        "build_row_template_preflight": (
            "python3 scripts/build_pocketmd_lite_topk_rows_template_preflight.py "
            f"--out {DEFAULT_ROWS_TEMPLATE_PREFLIGHT} "
            f"--out-md {DEFAULT_ROWS_TEMPLATE_PREFLIGHT_MD}"
        ),
        "materialize_rows_from_template": (
            "python3 scripts/materialize_pocketmd_lite_topk_rows_from_template.py "
            f"--template {DEFAULT_ROWS_TEMPLATE} --out-rows {DEFAULT_ROWS_OUT} "
            f"--out-report {PRODUCTIZATION / 'pocketmd_lite_topk_rows_from_template_report.json'} "
            "--fail-blocked"
        ),
        "materialize_rows_from_receipt_bundle": (
            "python3 scripts/materialize_pocketmd_lite_topk_rows_from_receipt_bundle.py "
            f"--receipt-bundle {PRODUCTIZATION / 'pocketmd_lite_refinement_receipt_bundle.json'} "
            f"--out-rows {DEFAULT_ROWS_OUT} "
            f"--out-report {DEFAULT_ROWS_FROM_RECEIPT_BUNDLE_REPORT} "
            "--fail-blocked"
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
            f"--pocketmd-rows {DEFAULT_ROWS_OUT} "
            "--source-id <source-id> --source-url <source-url> "
            "--source-license <license> "
            "--fail-blocked"
        ),
    }
    pocketmd_rows_operator_action = _pocketmd_rows_operator_action(
        raw_row_candidate_status=raw_row_candidate_status,
        minimum_rows_by_case=minimum_rows_by_case,
        phase4_metric_closure_matrix=phase4_metric_closure_matrix,
        required_flat_row_fields=required_flat_row_fields,
        template_preflight_summary=template_preflight_summary,
        rows_from_receipt_bundle_report_summary=(
            rows_from_receipt_bundle_report_summary
        ),
        commands=commands,
    )
    missing_row_input_actions = (
        [pocketmd_rows_operator_action]
        if not raw_row_candidate_status.get("coverage_ready")
        else []
    )
    operator_next_actions = [
        "review_phase4_refinement_receipt_plan",
        "build_pocketmd_lite_refinement_execution_plan",
        "build_pocketmd_lite_topk_rows_template_preflight",
        "select_upstream_ranked_top_k_candidate_sets",
        "attach_upstream_top_k_provenance_and_checksum_for_every_candidate",
        "run_bounded_lite_refinement_for_top_k_candidates_only",
        "write_local_min_contact_hbond_clash_uncertainty_rows",
        "attach_row_source_receipts_with_license_url_and_artifact_sha256",
        "write_pocketmd_lite_topk_rows_at_default_dropzone",
        "materialize_completed_template_to_pocketmd_lite_topk_rows",
        "run_pocketmd_lite_raw_row_importer_and_survival_materializer",
        "refresh_science_actual_closure_from_rows",
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=[
                Path("scripts/build_pocketmd_lite_source_acquisition_plan.py"),
                Path("scripts/build_pocketmd_lite_refinement_execution_plan.py"),
                Path("scripts/build_pocketmd_lite_topk_rows_template_preflight.py"),
                Path(
                    "scripts/materialize_pocketmd_lite_topk_rows_from_receipt_bundle.py"
                ),
                Path("scripts/materialize_pocketmd_lite_operator_intake_from_rows.py"),
                Path("scripts/materialize_pocketmd_lite_topk_survival_report.py"),
                DEFAULT_ROWS_TEMPLATE,
                DEFAULT_ROWS_TEMPLATE_PREFLIGHT,
                DEFAULT_ROWS_FROM_RECEIPT_BUNDLE_REPORT,
                DEFAULT_SURVIVAL_REPORT,
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
        "raw_row_candidate_status": raw_row_candidate_status,
        "phase4_refinement_receipt_plan": phase4_refinement_receipt_plan,
        "phase4_candidate_slot_matrix": phase4_candidate_slot_matrix,
        "phase4_candidate_slot_matrix_count": len(phase4_candidate_slot_matrix),
        "phase4_missing_candidate_slot_count": sum(
            1 for row in phase4_candidate_slot_matrix if row["missing"]
        ),
        "phase4_metric_closure_matrix": phase4_metric_closure_matrix,
        "phase4_metric_closure_matrix_count": len(phase4_metric_closure_matrix),
        "phase4_completion_audit": phase4_completion_audit,
        "phase4_actual_evidence_audit": phase4_actual_evidence_audit,
        "survival_report": survival_report_status,
        "refinement_execution_plan": refinement_execution_plan,
        "template_preflight_summary": template_preflight_summary,
        "rows_from_receipt_bundle_report_summary": (
            rows_from_receipt_bundle_report_summary
        ),
        "phase4_refinement_receipt_promotion_policy": dict(
            PHASE4_REFINEMENT_RECEIPT_PROMOTION_POLICY
        ),
        "row_artifact_contract": {
            "default_output": str(rows_out),
            "template_artifact": str(DEFAULT_ROWS_TEMPLATE),
            "template_preflight_artifact": str(DEFAULT_ROWS_TEMPLATE_PREFLIGHT),
            "template_preflight_markdown_artifact": str(
                DEFAULT_ROWS_TEMPLATE_PREFLIGHT_MD
            ),
            "template_preflight_command": commands["build_row_template_preflight"],
            "template_usage_policy": (
                "The template enumerates required columns and minimum case/rank "
                "slots only. Operators must replace placeholder blanks with real "
                "top-k refinement rows and receipts before writing rows to the "
                "default output."
            ),
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
            "raw_row_candidate_status": raw_row_candidate_status,
            "row_value_contract": row_value_contract(max_top_k=20),
            "source_receipt_requirements": dict(SOURCE_RECEIPT_REQUIREMENTS),
        },
        "metric_receipt_contract": metric_receipt_contract,
        "operator_acquisition_checklist": operator_next_actions,
        "operator_next_actions": operator_next_actions,
        "commands": commands,
        "pocketmd_rows_operator_action": pocketmd_rows_operator_action,
        "missing_row_input_actions": missing_row_input_actions,
        "missing_row_input_action_count": len(missing_row_input_actions),
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
            "phase4_candidate_slot_matrix_count": len(phase4_candidate_slot_matrix),
            "phase4_missing_candidate_slot_count": sum(
                1 for row in phase4_candidate_slot_matrix if row["missing"]
            ),
            "phase4_metric_closure_matrix_count": len(
                phase4_metric_closure_matrix
            ),
            "phase4_completion_audit_status": phase4_completion_audit["status"],
            "phase4_completion_requirement_count": (
                phase4_completion_audit["requirement_count"]
            ),
            "phase4_completion_ready_requirement_count": (
                phase4_completion_audit["ready_requirement_count"]
            ),
            "phase4_completion_blocked_requirement_count": (
                phase4_completion_audit["blocked_requirement_count"]
            ),
            "phase4_actual_evidence_audit_status": (
                phase4_actual_evidence_audit["status"]
            ),
            "phase4_actual_evidence_ready_component_count": (
                phase4_actual_evidence_audit["ready_component_count"]
            ),
            "phase4_actual_evidence_blocked_component_count": (
                phase4_actual_evidence_audit["blocked_component_count"]
            ),
            "phase4_actual_evidence_missing_metric_count": (
                phase4_actual_evidence_audit["survival_metric_summary"][
                    "missing_metric_count"
                ]
            ),
            "survival_report_status": survival_report_status["status"],
            "survival_report_blocker_count": survival_report_status[
                "blocker_count"
            ],
            "template_preflight_status": template_preflight_summary["status"],
            "template_preflight_role_receipt_plan_count": (
                template_preflight_summary["role_receipt_plan_count"]
            ),
            "template_preflight_role_receipt_blocked_count": (
                template_preflight_summary["role_receipt_blocked_count"]
            ),
            "template_preflight_operator_input_source_receipt_requirement_count": (
                template_preflight_summary[
                    "operator_input_source_receipt_requirement_count"
                ]
            ),
            "template_preflight_operator_input_source_receipt_blocked_count": (
                template_preflight_summary[
                    "operator_input_source_receipt_blocked_count"
                ]
            ),
            "rows_from_receipt_bundle_report_status": (
                rows_from_receipt_bundle_report_summary["status"]
            ),
            "rows_from_receipt_bundle_ready_receipt_count": (
                rows_from_receipt_bundle_report_summary["ready_receipt_count"]
            ),
            "rows_from_receipt_bundle_incomplete_receipt_count": (
                rows_from_receipt_bundle_report_summary[
                    "incomplete_receipt_count"
                ]
            ),
            "rows_from_receipt_bundle_missing_required_field_count": int(
                rows_from_receipt_bundle_report_summary.get(
                    "first_incomplete_receipt", {}
                ).get("completion_missing_required_field_count")
                or 0
            ),
            "rows_from_receipt_bundle_unique_missing_required_field_count": (
                rows_from_receipt_bundle_report_summary[
                    "unique_missing_required_field_count"
                ]
            ),
            "rows_from_receipt_bundle_total_missing_required_field_count": (
                rows_from_receipt_bundle_report_summary[
                    "total_missing_required_field_count"
                ]
            ),
            "rows_from_receipt_bundle_metric_family_count": (
                rows_from_receipt_bundle_report_summary[
                    "receipt_metric_family_count"
                ]
            ),
            "rows_from_receipt_bundle_metric_family_blocked_count": (
                rows_from_receipt_bundle_report_summary[
                    "receipt_metric_family_blocked_count"
                ]
            ),
            "rows_from_receipt_bundle_metric_family_missing_field_occurrence_count": (
                rows_from_receipt_bundle_report_summary[
                    "receipt_metric_family_missing_field_occurrence_count"
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
            "raw_row_artifact_detected": row_artifact_detected,
            "raw_row_candidate_status": raw_row_candidate_status["status"],
            "validated_row_count": raw_row_candidate_status["validated_row_count"],
            "covered_required_slot_count": raw_row_candidate_status[
                "covered_required_slot_count"
            ],
            "detected_row_artifact_count": raw_row_candidate_status[
                "detected_row_artifact_count"
            ],
            "missing_row_input_action_count": len(missing_row_input_actions),
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
        f"- `phase4_candidate_slot_matrix_count`: `{payload['phase4_candidate_slot_matrix_count']}`",
        f"- `phase4_missing_candidate_slot_count`: `{payload['phase4_missing_candidate_slot_count']}`",
        f"- `phase4_metric_closure_matrix_count`: `{payload['phase4_metric_closure_matrix_count']}`",
        "- `phase4_completion_audit_status`: "
        f"`{payload['phase4_completion_audit']['status']}`",
        "- `phase4_completion_ready_requirement_count`: "
        f"`{payload['phase4_completion_audit']['ready_requirement_count']}`",
        "- `phase4_completion_blocked_requirement_count`: "
        f"`{payload['phase4_completion_audit']['blocked_requirement_count']}`",
        "- `phase4_actual_evidence_audit_status`: "
        f"`{payload['phase4_actual_evidence_audit']['status']}`",
        "- `phase4_actual_evidence_blocked_component_count`: "
        f"`{payload['phase4_actual_evidence_audit']['blocked_component_count']}`",
        f"- `survival_report_status`: `{payload['survival_report']['status']}`",
        "- `survival_report_blocker_count`: "
        f"`{payload['survival_report']['blocker_count']}`",
        f"- `template_preflight_status`: `{payload['template_preflight_summary']['status']}`",
        "- `template_preflight_role_receipt_blocked_count`: "
        f"`{payload['template_preflight_summary']['role_receipt_blocked_count']}`",
        "- `template_preflight_operator_input_source_receipt_blocked_count`: "
        f"`{payload['template_preflight_summary']['operator_input_source_receipt_blocked_count']}`",
        "- `rows_from_receipt_bundle_report_status`: "
        f"`{payload['rows_from_receipt_bundle_report_summary']['status']}`",
        "- `rows_from_receipt_bundle_ready_receipt_count`: "
        f"`{payload['rows_from_receipt_bundle_report_summary']['ready_receipt_count']}`",
        "- `rows_from_receipt_bundle_metric_family_blocked_count`: "
        f"`{payload['rows_from_receipt_bundle_report_summary']['receipt_metric_family_blocked_count']}`",
        f"- `row_template_artifact`: `{payload['row_artifact_contract']['template_artifact']}`",
        "",
        "## Operator Next Actions",
        "",
        "| Step | Action |",
        "|---:|---|",
    ]
    for index, action in enumerate(payload.get("operator_next_actions", []), start=1):
        lines.append(f"| {index} | `{action}` |")
    completion_audit = _as_dict(payload.get("phase4_completion_audit"))
    completion_requirements = [
        row
        for row in completion_audit.get("requirements", [])
        if isinstance(row, dict)
    ] if isinstance(completion_audit.get("requirements"), list) else []
    if completion_audit:
        lines.extend(
            [
                "",
                "## Phase 4 Completion Audit",
                "",
                f"- `status`: `{completion_audit.get('status')}`",
                f"- `actual_closure_ready`: `{completion_audit.get('actual_closure_ready')}`",
                f"- `remaining_row_inputs`: `{', '.join(completion_audit.get('remaining_row_inputs', []))}`",
                f"- `remaining_operator_action`: `{completion_audit.get('remaining_operator_action')}`",
                "",
                "| Requirement | Product Requirement | Status | Pass | Blockers |",
                "|---|---|---|---|---|",
            ]
        )
        for row in completion_requirements:
            blockers = ", ".join(
                f"`{blocker}`"
                for blocker in row.get("blockers", [])
                if str(blocker)
            )
            lines.append(
                f"| `{row.get('requirement_id', '')}` | "
                f"{row.get('product_requirement', '')} | "
                f"`{row.get('status', '')}` | `{row.get('pass')}` | "
                f"{blockers or '`none`'} |"
            )
    actual_evidence_audit = _as_dict(payload.get("phase4_actual_evidence_audit"))
    evidence_components = [
        row
        for row in actual_evidence_audit.get("components", [])
        if isinstance(row, dict)
    ] if isinstance(actual_evidence_audit.get("components"), list) else []
    if actual_evidence_audit:
        template_evidence = _as_dict(
            actual_evidence_audit.get("template_preflight_evidence")
        )
        metric_summary = _as_dict(
            actual_evidence_audit.get("survival_metric_summary")
        )
        lines.extend(
            [
                "",
                "## Phase 4 Actual Evidence Audit",
                "",
                f"- `status`: `{actual_evidence_audit.get('status')}`",
                f"- `actual_closure_ready`: `{actual_evidence_audit.get('actual_closure_ready')}`",
                "- `remaining_evidence`: "
                f"`{', '.join(actual_evidence_audit.get('remaining_evidence', []))}`",
                "- `role_receipt_blocked_count`: "
                f"`{template_evidence.get('role_receipt_blocked_count')}`",
                "- `operator_input_source_receipt_blocked_count`: "
                f"`{template_evidence.get('operator_input_source_receipt_blocked_count')}`",
                "- `missing_metric_count`: "
                f"`{metric_summary.get('missing_metric_count')}`",
                "",
                "| Component | Status | Pass | Current | Required | Blockers |",
                "|---|---|---|---|---|---|",
            ]
        )
        for row in evidence_components:
            current = json.dumps(
                _as_dict(row.get("current")),
                ensure_ascii=False,
                sort_keys=True,
            )
            required = json.dumps(
                _as_dict(row.get("required")),
                ensure_ascii=False,
                sort_keys=True,
            )
            blockers = ", ".join(
                f"`{blocker}`"
                for blocker in row.get("blockers", [])
                if str(blocker)
            )
            lines.append(
                f"| `{row.get('component_id', '')}` | "
                f"`{row.get('status', '')}` | `{row.get('pass')}` | "
                f"`{current}` | `{required}` | {blockers or '`none`'} |"
            )
    lines.extend(
        [
            "",
            "| Case | Minimum Rows | Required Rank Prefix | Scope |",
            "|---|---:|---|---|",
        ]
    )
    for row in payload["minimum_rows_by_case"]:
        ranks = ",".join(str(rank) for rank in row["required_top_k_rank_prefix"])
        lines.append(
            f"| `{row['case_id']}` | {row['minimum_candidate_rows']} | "
            f"`{ranks}` | `{row['candidate_scope']}` |"
        )
    lines.extend(
        [
            "",
            "## Phase 4 Candidate Slot Matrix",
            "",
            "| Slot | Case | Rank | Status | Required Metric Fields |",
            "|---|---|---|---|---|",
        ]
    )
    for row in payload["phase4_candidate_slot_matrix"]:
        metric_fields = ", ".join(
            f"`{field}`" for field in row["required_metric_fields"]
        )
        lines.append(
            f"| `{row['slot_id']}` | `{row['case_id']}` | "
            f"`{row['top_k_rank']}` | `{row['status']}` | {metric_fields} |"
        )
    lines.extend(
        [
            "",
            "## Phase 4 Metric Closure Matrix",
            "",
            "| Criterion | Metric | Status | Required Fields | Receipt Roles |",
            "|---|---|---|---|---|",
        ]
    )
    for row in payload["phase4_metric_closure_matrix"]:
        fields = ", ".join(
            f"`{field}`" for field in row.get("required_row_fields", [])
        )
        receipt_roles = ", ".join(
            f"`{role}`" for role in row.get("receipt_roles", [])
        )
        lines.append(
            f"| `{row['criterion_id']}` | `{row.get('metric_id', '')}` | "
            f"`{row['status']}` | {fields or '`row_coverage_and_receipts`'} | "
            f"{receipt_roles or '`all_required_roles`'} |"
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
    missing_actions = [
        row
        for row in payload.get("missing_row_input_actions", [])
        if isinstance(row, dict)
    ]
    if missing_actions:
        lines.extend(["", "## Missing Row Input Actions", ""])
        lines.extend(
            [
                "| Row Input | Action | Default Artifact | Required Slots |",
                "|---|---|---|---:|",
            ]
        )
        for row in missing_actions:
            lines.append(
                f"| `{row.get('row_input_id', '')}` | "
                f"`{row.get('operator_action', '')}` | "
                f"`{row.get('default_row_artifact', '')}` | "
                f"{row.get('required_candidate_slot_count', 0)} |"
            )
        row_preflight_packets = [
            row.get("row_preflight_action_packet")
            for row in missing_actions
            if isinstance(row.get("row_preflight_action_packet"), dict)
        ]
        if row_preflight_packets:
            lines.extend(["", "### PocketMD Row Preflight Action", ""])
            for action in row_preflight_packets:
                if not isinstance(action, dict):
                    continue
                safety_policy = action.get("template_safety_policy")
                if not isinstance(safety_policy, dict):
                    safety_policy = {}
                supported_paths = ", ".join(
                    f"`{path}`"
                    for path in action.get("supported_candidate_paths", [])
                    if str(path)
                )
                lines.extend(
                    [
                        f"- `status`: `{action.get('status')}`",
                        f"- `expected_rows_artifact`: `{action.get('expected_rows_artifact')}`",
                        f"- `template_preflight_artifact`: `{action.get('template_preflight_artifact')}`",
                        f"- `template_preflight_markdown_artifact`: `{action.get('template_preflight_markdown_artifact')}`",
                        f"- `build_template_preflight_command`: `{action.get('build_template_preflight_command')}`",
                        f"- `supported_candidate_paths`: {supported_paths}",
                        f"- `detected_row_artifact_count`: `{action.get('detected_row_artifact_count')}`",
                        f"- `selected_path`: `{action.get('selected_path')}`",
                        f"- `validated_row_count`: `{action.get('validated_row_count')}`",
                        f"- `covered_required_slot_count`: `{action.get('covered_required_slot_count')}/{action.get('required_candidate_slot_count')}`",
                        f"- `missing_required_slot_count`: `{len(action.get('missing_required_slots', []))}`",
                        f"- `validation_error`: `{action.get('validation_error')}`",
                        f"- `blocker`: `{action.get('blocker')}`",
                        "- `template_preflight_role_receipt_blocked_count`: "
                        f"`{_as_dict(action.get('template_preflight_summary')).get('role_receipt_blocked_count')}`",
                        "- `template_preflight_operator_input_source_receipt_blocked_count`: "
                        f"`{_as_dict(action.get('template_preflight_summary')).get('operator_input_source_receipt_blocked_count')}`",
                        f"- `import_rows_command`: `{action.get('import_rows_command')}`",
                        f"- `verify_science_actual_closure_command`: `{action.get('verify_science_actual_closure_command')}`",
                        f"- `operator_rows_must_be_real_top_k_refinement_outputs`: `{safety_policy.get('operator_rows_must_be_real_top_k_refinement_outputs')}`",
                        f"- `preflight_does_not_run_refinement`: `{safety_policy.get('preflight_does_not_run_refinement')}`",
                    ]
                )
        row_action_packets = [
            row.get("top_k_rows_action_packet")
            for row in missing_actions
            if isinstance(row.get("top_k_rows_action_packet"), dict)
        ]
        if row_action_packets:
            lines.extend(["", "### PocketMD Top-k Rows Action", ""])
            for action in row_action_packets:
                if not isinstance(action, dict):
                    continue
                safety_policy = action.get("template_safety_policy")
                if not isinstance(safety_policy, dict):
                    safety_policy = {}
                required_fields = ", ".join(
                    f"`{field}`"
                    for field in action.get("operator_must_fill_or_verify", [])
                )
                receipt_roles = ", ".join(
                    f"`{role}`"
                    for role in action.get("required_receipt_roles", [])
                )
                phase4_metric_receipt_actions = [
                    row
                    for row in action.get("phase4_metric_receipt_actions", [])
                    if isinstance(row, dict)
                ]
                rows_from_receipt_bundle_report = (
                    action.get("rows_from_receipt_bundle_report")
                    if isinstance(action.get("rows_from_receipt_bundle_report"), dict)
                    else {}
                )
                metric_family_completion_plan = [
                    row
                    for row in rows_from_receipt_bundle_report.get(
                        "receipt_metric_family_completion_plan", []
                    )
                    if isinstance(row, dict)
                ]
                first_metric_family_blocker = (
                    metric_family_completion_plan[0]
                    if metric_family_completion_plan
                    else {}
                )
                role_receipt_summary = (
                    action.get("role_receipt_plan_summary")
                    if isinstance(action.get("role_receipt_plan_summary"), dict)
                    else {}
                )
                input_source_receipt_summary = (
                    action.get("operator_input_source_receipt_plan_summary")
                    if isinstance(
                        action.get("operator_input_source_receipt_plan_summary"),
                        dict,
                    )
                    else {}
                )
                first_blocked_role = (
                    role_receipt_summary.get("first_blocked_role_receipt")
                    if isinstance(
                        role_receipt_summary.get("first_blocked_role_receipt"),
                        dict,
                    )
                    else {}
                )
                first_blocked_source_receipt = (
                    input_source_receipt_summary.get("first_blocked_receipt")
                    if isinstance(
                        input_source_receipt_summary.get("first_blocked_receipt"),
                        dict,
                    )
                    else {}
                )
                lines.extend(
                    [
                        f"- `status`: `{action.get('status')}`",
                        f"- `template_artifact`: `{action.get('template_artifact')}`",
                        f"- `template_preflight_artifact`: `{action.get('template_preflight_artifact')}`",
                        f"- `build_template_preflight_command`: `{action.get('build_template_preflight_command')}`",
                        f"- `expected_rows_artifact`: `{action.get('expected_rows_artifact')}`",
                        f"- `review_template_command`: `{action.get('review_template_command')}`",
                        f"- `import_rows_command`: `{action.get('import_rows_command')}`",
                        f"- `materialize_survival_command`: `{action.get('materialize_survival_command')}`",
                        f"- `verify_science_actual_closure_command`: `{action.get('verify_science_actual_closure_command')}`",
                        f"- `operator_must_fill_or_verify`: {required_fields}",
                        f"- `required_receipt_roles`: {receipt_roles}",
                        f"- `role_receipt_blocked_count`: `{role_receipt_summary.get('role_receipt_blocked_count')}`",
                        f"- `first_blocked_role_receipt`: `{first_blocked_role.get('role_id', '')}` / `{first_blocked_role.get('candidate_id', '')}`",
                        f"- `operator_input_source_receipt_blocked_count`: `{input_source_receipt_summary.get('blocked_count')}`",
                        f"- `first_blocked_operator_input_source_receipt`: `{first_blocked_source_receipt.get('field', '')}`",
                        f"- `phase4_metric_receipt_action_count`: `{action.get('phase4_metric_receipt_action_count')}`",
                        f"- `receipt_metric_family_blocked_count`: `{rows_from_receipt_bundle_report.get('receipt_metric_family_blocked_count')}`",
                        f"- `first_receipt_metric_family_blocker`: `{first_metric_family_blocker.get('metric_family_id', '')}` / `{first_metric_family_blocker.get('blocked_receipt_count', '')}`",
                        f"- `template_is_not_evidence`: `{safety_policy.get('template_is_not_evidence')}`",
                        f"- `placeholder_or_fixture_rows_do_not_promote`: `{safety_policy.get('placeholder_or_fixture_rows_do_not_promote')}`",
                        f"- `summary_only_metrics_do_not_promote`: `{safety_policy.get('summary_only_metrics_do_not_promote')}`",
                    ]
                )
                if phase4_metric_receipt_actions:
                    lines.extend(
                        [
                            "",
                            "#### PocketMD Phase 4 Receipt Closure Actions",
                            "",
                            "| Criterion | Metric | Receipt Roles | Required Row Fields | Blockers |",
                            "|---|---|---|---|---|",
                        ]
                    )
                    for metric_action in phase4_metric_receipt_actions:
                        receipt_roles = ", ".join(
                            f"`{role}`"
                            for role in metric_action.get("receipt_roles", [])
                            if str(role)
                        )
                        required_row_fields = ", ".join(
                            f"`{field}`"
                            for field in metric_action.get(
                                "required_row_fields", []
                            )
                            if str(field)
                        )
                        blockers = ", ".join(
                            f"`{blocker}`"
                            for blocker in metric_action.get("blockers", [])
                            if str(blocker)
                        )
                        lines.append(
                            f"| `{metric_action.get('criterion_id', '')}` | "
                            f"`{metric_action.get('metric_id', '')}` | "
                            f"{receipt_roles or '`none`'} | "
                            f"{required_row_fields or '`none`'} | "
                            f"{blockers or '`none`'} |"
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
    rows_out: Path = DEFAULT_ROWS_OUT,
) -> dict[str, Any]:
    payload = build_pocketmd_lite_source_acquisition_plan(
        repo_root=repo_root,
        rows_out=rows_out,
    )
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
    parser.add_argument("--rows-out", type=Path, default=DEFAULT_ROWS_OUT)
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
        rows_out=args.rows_out,
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
