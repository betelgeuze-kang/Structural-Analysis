#!/usr/bin/env python3
"""Build the operator intake packet for GPCR hard-decoy closure."""

from __future__ import annotations

import argparse
import csv
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
    ACTUAL_CLOSURE_CRITERION_ID,
    EXIT_CRITERIA,
    PLACEHOLDER_PROVENANCE_PREFIXES,
    PLACEHOLDER_SOURCE_TEXT_MARKERS,
    PLACEHOLDER_SOURCE_URL_MARKERS,
    PLACEHOLDER_SOURCE_URL_PREFIXES,
    RAW_RANKING_SOURCE_RECEIPT_FIELDS,
    REQUIRED_ACTUAL_CLOSURE_RAW_ROW_FIELDS,
    RAW_ROW_QUALITY_CRITERIA,
    REQUIRED_TARGETS,
    SCHEMA_VERSION as SUITE_REPORT_SCHEMA_VERSION,
)


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
SURFACE_DIR = Path("implementation/phase1/release_evidence/surface")

DEFAULT_OPERATOR_TEMPLATE = PRODUCTIZATION / "gpcr_hard_decoy_operator_template.json"
DEFAULT_OPERATOR_TEMPLATE_IMPORTER = Path(
    "scripts/materialize_gpcr_hard_decoy_operator_template_from_rows.py"
)
DEFAULT_SUITE_REPORT = PRODUCTIZATION / "gpcr_hard_decoy_suite_report.json"
DEFAULT_EVIDENCE_SURFACE = SURFACE_DIR / "gpcr_hard_decoy_evidence_surface.json"
DEFAULT_PRODUCT_REPORT = PRODUCTIZATION / "gpcr_hard_decoy_product_report.json"
DEFAULT_PRODUCT_CAPABILITIES = SURFACE_DIR / "product_capabilities_surface.json"
DEFAULT_GOAL_BOTTLENECK = PRODUCTIZATION / "goal_bottleneck_roadmap_surface.json"
DEFAULT_OUT = PRODUCTIZATION / "gpcr_hard_decoy_operator_intake_packet.json"
DEFAULT_OUT_MD = DEFAULT_OUT.with_suffix(".md")
DEFAULT_ROW_TEMPLATE_DIR = PRODUCTIZATION
DEFAULT_RAW_ROW_TEMPLATE_FILENAME = "gpcr_hard_decoy_rows_template.csv"
DEFAULT_RAW_ROW_INPUT_CANDIDATES = [
    str(PRODUCTIZATION / f"gpcr_hard_decoy_rows.{suffix}")
    for suffix in ("json", "jsonl", "ndjson", "csv", "tsv")
]

SCHEMA_VERSION = "gpcr-hard-decoy-operator-intake-packet.v1"
GPCR_PRODUCT_REPORT_ROUTE = "/product/gpcr-hard-decoy-suite-report"
GPCR_OPERATOR_INTAKE_ROUTE = "/product/gpcr-hard-decoy-suite-report/operator-intake"
REQUIRED_OPERATOR_FIELDS = (
    "target_id",
    "ranking_pr_auc_ci_low",
    "top20_hit_rate",
    "decoys_above_positive_count",
    "positive_out_anchored_by_top_decoys",
    "score_direction",
    "hard_decoy_rows",
)
PHASE3_EXIT_CRITERIA_BY_FIELD = {
    "ranking_pr_auc_ci_low": "ranking_pr_auc_ci_low_min",
    "top20_hit_rate": "top20_hit_rate_min",
    "decoys_above_positive_count": "decoys_above_positive_count_max",
    "positive_out_anchored_by_top_decoys": "no_positive_out_anchored_by_top_decoys",
    "hard_decoy_rows": ACTUAL_CLOSURE_CRITERION_ID,
}
RAW_HARD_DECOY_ROW_FIELDS = REQUIRED_ACTUAL_CLOSURE_RAW_ROW_FIELDS
ROW_SOURCE_RECEIPT_REQUIREMENTS = {
    "required_row_fields": list(RAW_RANKING_SOURCE_RECEIPT_FIELDS),
    "source_checksum_policy": (
        "source_checksum must be sha256:<64 hex> and not a repeated placeholder digest"
    ),
    "provenance_ref_policy": (
        "provenance_ref must be nonblank and must not use local, fixture, mock, "
        "synthetic, placeholder, test, or file-only provenance prefixes"
    ),
    "placeholder_provenance_prefixes_rejected": list(PLACEHOLDER_PROVENANCE_PREFIXES),
}
RAW_ROW_VALUE_CONTRACT = {
    "target_id_policy": (
        "target_id must be one of DRD2, HTR2A, or OPRM1; out-of-scope target "
        "rows are rejected before suite materialization."
    ),
    "score_direction_policy": (
        "score_direction must be higher_is_better or lower_is_better, with "
        "exactly one direction per target."
    ),
    "numeric_value_policy": {
        "score": "must parse to a finite float; NaN and Infinity are rejected",
    },
    "boolean_label_policy": (
        "is_positive and is_decoy must parse to booleans and be mutually exclusive."
    ),
    "row_integrity_policy": (
        "molecule_id must be nonblank, non-placeholder, and unique within each target."
    ),
}
SOURCE_RECEIPT_REQUIREMENTS = {
    "mode": "raw_hard_decoy_rows",
    "required_fields": [
        "source_id",
        "source_url",
        "source_license",
        "source_artifact",
        "source_artifact_sha256",
    ],
    "source_artifact_sha256_policy": (
        "must be a sha256:<hex> reference matching the attached raw row artifact"
    ),
    "placeholder_block_policy": {
        "text_markers": list(PLACEHOLDER_SOURCE_TEXT_MARKERS),
        "url_markers": list(PLACEHOLDER_SOURCE_URL_MARKERS),
        "url_prefixes": list(PLACEHOLDER_SOURCE_URL_PREFIXES),
    },
}


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _csv_cell(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if value is None:
        return ""
    return value


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _load_json(repo_root: Path, path: Path) -> dict[str, Any]:
    resolved = path if path.is_absolute() else repo_root / path
    if not resolved.exists():
        return {}
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _input_paths() -> list[Path]:
    return [
        Path("scripts/build_gpcr_hard_decoy_operator_intake_packet.py"),
        Path("scripts/materialize_gpcr_hard_decoy_suite_report.py"),
        DEFAULT_OPERATOR_TEMPLATE_IMPORTER,
        DEFAULT_OPERATOR_TEMPLATE,
        DEFAULT_SUITE_REPORT,
        DEFAULT_EVIDENCE_SURFACE,
    ]


def _raw_row_template_path(row_template_dir: Path) -> Path:
    return row_template_dir / DEFAULT_RAW_ROW_TEMPLATE_FILENAME


def _raw_row_template_headers() -> list[str]:
    return [
        "target_id",
        "molecule_id",
        "score",
        "is_positive",
        "is_decoy",
        "score_direction",
        "source_checksum",
        "provenance_ref",
    ]


def _raw_row_template_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    positive_count = int(RAW_ROW_QUALITY_CRITERIA["min_positive_count_per_target"])
    decoy_count = int(RAW_ROW_QUALITY_CRITERIA["min_decoy_count_per_target"])
    for target_id in REQUIRED_TARGETS:
        target_key = target_id.lower()
        for index in range(1, positive_count + 1):
            rows.append(
                {
                    "target_id": target_id,
                    "molecule_id": f"{target_key}_positive_{index:03d}",
                    "score": None,
                    "is_positive": True,
                    "is_decoy": False,
                    "score_direction": "higher_is_better",
                    "source_checksum": None,
                    "provenance_ref": None,
                }
            )
        for index in range(1, decoy_count + 1):
            rows.append(
                {
                    "target_id": target_id,
                    "molecule_id": f"{target_key}_decoy_{index:03d}",
                    "score": None,
                    "is_positive": False,
                    "is_decoy": True,
                    "score_direction": "higher_is_better",
                    "source_checksum": None,
                    "provenance_ref": None,
                }
            )
    return [{key: _csv_cell(value) for key, value in row.items()} for row in rows]


def _target_template(target_id: str) -> dict[str, Any]:
    return {
        "target_id": target_id,
        "ranking_pr_auc_ci_low": None,
        "top20_hit_rate": None,
        "decoys_above_positive_count": None,
        "positive_out_anchored_by_top_decoys": None,
        "score_direction": "higher_is_better",
        "hard_decoy_rows": [
            {
                "molecule_id": "positive_001",
                "score": None,
                "is_positive": True,
                "is_decoy": False,
                "source_checksum": None,
                "provenance_ref": None,
            },
            {
                "molecule_id": "decoy_001",
                "score": None,
                "is_positive": False,
                "is_decoy": True,
                "source_checksum": None,
                "provenance_ref": None,
            },
        ],
    }


def _target_slot(target_id: str) -> dict[str, Any]:
    return {
        "slot_id": f"{target_id.lower()}_hard_decoy_metrics",
        "target_id": target_id,
        "status": "operator_input_required",
        "required": True,
        "template_artifact": str(DEFAULT_OPERATOR_TEMPLATE),
        "required_fields": list(REQUIRED_OPERATOR_FIELDS),
        "exit_criteria": EXIT_CRITERIA,
        "template": _target_template(target_id),
        "owner_actions": [
            "attach authoritative hard-decoy evaluation metrics for this target",
            "keep ranking_pr_auc_ci_low as the lower confidence bound",
            "keep top20_hit_rate as a fraction, not a percent",
            "verify decoys_above_positive_count is zero",
            "verify positive_out_anchored_by_top_decoys is false",
        ],
    }


def _target_rows_by_id(payload: dict[str, Any], key: str) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for row in _as_list(payload.get(key)):
        if not isinstance(row, dict):
            continue
        target_id = str(row.get("target_id") or "").strip().upper()
        if target_id:
            rows[target_id] = row
    return rows


def _target_missing_fields(row: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    for field in REQUIRED_OPERATOR_FIELDS:
        if field == "target_id":
            continue
        if row.get(field) is None:
            missing.append(field)
    return missing


def _target_blocked_criteria(
    *,
    target_id: str,
    suite: dict[str, Any],
) -> list[str]:
    criteria = [
        row
        for row in _as_list(_as_dict(suite.get("phase3_exit_gate")).get("criteria"))
        if isinstance(row, dict)
    ]
    blocked = [
        str(row.get("criterion_id") or "")
        for row in criteria
        if target_id in [str(item) for item in _as_list(row.get("failed_targets"))]
    ]
    return [
        criterion
        for criterion in blocked
        if criterion
    ] or list(PHASE3_EXIT_CRITERIA_BY_FIELD.values())


def _target_execution_preflight_checklist(
    *,
    template: dict[str, Any],
    suite: dict[str, Any],
    materialize_command: str,
) -> list[dict[str, Any]]:
    template_rows = _target_rows_by_id(template, "targets")
    suite_rows = _target_rows_by_id(suite, "target_rows")
    rows: list[dict[str, Any]] = []
    for index, target_id in enumerate(REQUIRED_TARGETS, start=1):
        template_row = template_rows.get(target_id, {"target_id": target_id})
        suite_row = suite_rows.get(target_id, {})
        blockers = [str(row) for row in _as_list(suite_row.get("blockers"))]
        missing_fields = _target_missing_fields(template_row)
        current_values = {
            field: template_row.get(field)
            for field in REQUIRED_OPERATOR_FIELDS
            if field != "target_id"
        }
        current_ready = bool(
            suite_row.get("status") == "pass"
            and suite_row.get("contract_pass") is True
            and not blockers
        )
        first_blocker = (
            blockers[0]
            if blockers
            else (
                f"{target_id}:{missing_fields[0]}_required"
                if missing_fields
                else ""
            )
        )
        rows.append(
            {
                "target_priority": index,
                "target_id": target_id,
                "slot_id": f"{target_id.lower()}_hard_decoy_metrics",
                "status": "ready" if current_ready else "operator_input_required",
                "current_ready": current_ready,
                "phase3_blocked": not current_ready,
                "blocked_phase3_criteria": _target_blocked_criteria(
                    target_id=target_id,
                    suite=suite,
                )
                if not current_ready
                else [],
                "missing_operator_fields": missing_fields,
                "current_values": current_values,
                "suite_status": str(suite_row.get("status") or "missing"),
                "suite_contract_pass": suite_row.get("contract_pass"),
                "root_cause_tags": [
                    str(row) for row in _as_list(suite_row.get("root_cause_tags"))
                ],
                "first_blocker": first_blocker,
                "blockers": blockers,
                "minimum_evidence": {
                    "target_id": target_id,
                    "required_operator_fields": list(REQUIRED_OPERATOR_FIELDS),
                    "required_hard_decoy_row_fields": list(RAW_HARD_DECOY_ROW_FIELDS),
                    "criterion_by_field": dict(PHASE3_EXIT_CRITERIA_BY_FIELD),
                    "thresholds": {
                        "ranking_pr_auc_ci_low": f">={EXIT_CRITERIA['ranking_pr_auc_ci_low_min']}",
                        "top20_hit_rate": f">={EXIT_CRITERIA['top20_hit_rate_min']}",
                        "decoys_above_positive_count": f"<={EXIT_CRITERIA['decoys_above_positive_count_max']}",
                        "positive_out_anchored_by_top_decoys": EXIT_CRITERIA[
                            "positive_out_anchored_by_top_decoys_allowed"
                        ],
                        "hard_decoy_rows": (
                            "computed_from_raw_hard_decoy_rows_with_quality_minimums"
                        ),
                    },
                    "raw_row_quality_minimums": dict(RAW_ROW_QUALITY_CRITERIA),
                    "raw_row_value_contract": dict(RAW_ROW_VALUE_CONTRACT),
                    "row_source_receipt_requirements": dict(
                        ROW_SOURCE_RECEIPT_REQUIREMENTS
                    ),
                    "source_receipt_requirements": dict(SOURCE_RECEIPT_REQUIREMENTS),
                },
                "materialization_command": materialize_command,
                "validation_command": materialize_command,
                "claim_boundary": (
                    "This row is a read-only preflight over the current GPCR operator "
                    "template and suite report. It does not infer missing metrics or "
                    "promote broad GPCR claims."
                ),
            }
        )
    return rows


def _gate_unblock_plan(*, materialize_command: str) -> list[dict[str, Any]]:
    return [
        {
            "slot_id": f"{target_id.lower()}_hard_decoy_metrics",
            "target_id": target_id,
            "status": "operator_input_required",
            "template_artifact": str(DEFAULT_OPERATOR_TEMPLATE),
            "unblocks_phase3_criteria": list(PHASE3_EXIT_CRITERIA_BY_FIELD.values()),
            "minimum_evidence": {
                "target_id": target_id,
                "required_operator_fields": list(REQUIRED_OPERATOR_FIELDS),
                "required_hard_decoy_row_fields": list(RAW_HARD_DECOY_ROW_FIELDS),
                "criterion_by_field": dict(PHASE3_EXIT_CRITERIA_BY_FIELD),
                "thresholds": {
                    "ranking_pr_auc_ci_low": f">={EXIT_CRITERIA['ranking_pr_auc_ci_low_min']}",
                    "top20_hit_rate": f">={EXIT_CRITERIA['top20_hit_rate_min']}",
                    "decoys_above_positive_count": f"<={EXIT_CRITERIA['decoys_above_positive_count_max']}",
                    "positive_out_anchored_by_top_decoys": EXIT_CRITERIA[
                        "positive_out_anchored_by_top_decoys_allowed"
                    ],
                    "hard_decoy_rows": (
                        "computed_from_raw_hard_decoy_rows_with_quality_minimums"
                    ),
                },
                "raw_row_quality_minimums": dict(RAW_ROW_QUALITY_CRITERIA),
                "raw_row_value_contract": dict(RAW_ROW_VALUE_CONTRACT),
                "row_source_receipt_requirements": dict(
                    ROW_SOURCE_RECEIPT_REQUIREMENTS
                ),
                "source_receipt_requirements": dict(SOURCE_RECEIPT_REQUIREMENTS),
            },
            "materialization_steps": [
                "materialize_gpcr_hard_decoy_suite_report",
                "refresh_gpcr_hard_decoy_product_report",
                "refresh_product_capabilities_surface",
                "refresh_goal_bottleneck_roadmap_surface",
            ],
            "materialization_command": materialize_command,
            "validation_command": materialize_command,
        }
        for target_id in REQUIRED_TARGETS
    ]


def _phase3_raw_row_closure_matrix(
    *,
    import_command: str,
    materialize_command: str,
    row_template_artifact: str,
) -> list[dict[str, Any]]:
    criteria = list(PHASE3_EXIT_CRITERIA_BY_FIELD.values())
    rows: list[dict[str, Any]] = []
    for target_id in REQUIRED_TARGETS:
        rows.append(
            {
                "row_input_id": "gpcr_hard_decoy_rows",
                "target_id": target_id,
                "slot_id": f"{target_id.lower()}_hard_decoy_metrics",
                "status": "operator_input_required",
                "default_row_path_candidates": list(DEFAULT_RAW_ROW_INPUT_CANDIDATES),
                "row_template_artifact": row_template_artifact,
                "accepted_formats": ["json", "jsonl", "ndjson", "csv", "tsv"],
                "required_flat_row_fields": [
                    "target_id",
                    *RAW_HARD_DECOY_ROW_FIELDS,
                ],
                "required_target_values": {
                    "target_id": target_id,
                    "score_direction": "higher_is_better or lower_is_better",
                    "hard_decoy_rows": (
                        "computed_from_raw_hard_decoy_rows_with_quality_minimums"
                    ),
                },
                "raw_row_quality_minimums": dict(RAW_ROW_QUALITY_CRITERIA),
                "row_source_receipt_requirements": dict(
                    ROW_SOURCE_RECEIPT_REQUIREMENTS
                ),
                "source_receipt_requirements": dict(SOURCE_RECEIPT_REQUIREMENTS),
                "closes_phase3_criteria": criteria,
                "criterion_by_field": dict(PHASE3_EXIT_CRITERIA_BY_FIELD),
                "thresholds": {
                    "ranking_pr_auc_ci_low": f">={EXIT_CRITERIA['ranking_pr_auc_ci_low_min']}",
                    "top20_hit_rate": f">={EXIT_CRITERIA['top20_hit_rate_min']}",
                    "decoys_above_positive_count": f"<={EXIT_CRITERIA['decoys_above_positive_count_max']}",
                    "positive_out_anchored_by_top_decoys": EXIT_CRITERIA[
                        "positive_out_anchored_by_top_decoys_allowed"
                    ],
                    "hard_decoy_rows": (
                        "computed_from_raw_hard_decoy_rows_with_quality_minimums"
                    ),
                },
                "materialization_chain": [
                    "materialize_gpcr_hard_decoy_operator_template_from_rows",
                    "materialize_gpcr_hard_decoy_suite_report",
                    "refresh_gpcr_hard_decoy_product_report",
                    "refresh_product_capabilities_surface",
                    "refresh_goal_bottleneck_roadmap_surface",
                ],
                "import_command": import_command,
                "materialization_command": materialize_command,
                "claim_boundary": (
                    "This matrix row maps operator-attached raw hard-decoy rows to "
                    "the target-specific Phase 3 criteria they can unblock. It is not "
                    "actual closure evidence until source receipts verify and the suite "
                    "materializer computes passing metrics for every required target."
                ),
            }
        )
    return rows


def build_gpcr_hard_decoy_operator_intake_packet(
    *,
    repo_root: Path = ROOT,
    row_template_dir: Path = DEFAULT_ROW_TEMPLATE_DIR,
) -> dict[str, Any]:
    template = _load_json(repo_root, DEFAULT_OPERATOR_TEMPLATE)
    suite = _load_json(repo_root, DEFAULT_SUITE_REPORT)
    surface = _load_json(repo_root, DEFAULT_EVIDENCE_SURFACE)
    blockers = [str(row) for row in _as_list(suite.get("blockers") or surface.get("blockers"))]
    first_blocked_target = str(
        suite.get("first_blocked_target") or surface.get("first_blocked_target") or "DRD2"
    )
    root_cause_tags = [
        str(row)
        for row in _as_list(suite.get("root_cause_tags") or surface.get("root_cause_tags"))
    ]

    materialize_command = (
        "python3 scripts/materialize_gpcr_hard_decoy_suite_report.py "
        f"--intake {DEFAULT_OPERATOR_TEMPLATE} "
        f"--out-report {DEFAULT_SUITE_REPORT} "
        f"--out-surface {DEFAULT_EVIDENCE_SURFACE} --fail-blocked"
    )
    import_template_command = (
        f"python3 {DEFAULT_OPERATOR_TEMPLATE_IMPORTER} "
        "--rows <gpcr_hard_decoy_raw_rows.csv|json|tsv> "
        f"--out {DEFAULT_OPERATOR_TEMPLATE}"
    )
    row_template_artifact = str(_raw_row_template_path(row_template_dir))
    row_template_artifacts = {
        "gpcr_hard_decoy_rows": row_template_artifact,
    }
    refresh_product_report_command = (
        "python3 scripts/build_gpcr_hard_decoy_product_report.py "
        f"--out {DEFAULT_PRODUCT_REPORT}"
    )
    refresh_capabilities_command = (
        "python3 scripts/build_product_capabilities_surface.py "
        f"--out {DEFAULT_PRODUCT_CAPABILITIES}"
    )
    refresh_goal_command = (
        "python3 scripts/build_goal_bottleneck_roadmap_surface.py "
        f"--out {DEFAULT_GOAL_BOTTLENECK}"
    )
    gate_unblock_plan = _gate_unblock_plan(materialize_command=materialize_command)
    phase3_raw_row_closure_matrix = _phase3_raw_row_closure_matrix(
        import_command=import_template_command,
        materialize_command=materialize_command,
        row_template_artifact=row_template_artifact,
    )
    target_execution_preflight = _target_execution_preflight_checklist(
        template=template,
        suite=suite,
        materialize_command=materialize_command,
    )
    first_target_preflight_blocker = next(
        (row for row in target_execution_preflight if not row["current_ready"]),
        {},
    )

    return {
        "schema_version": SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=_input_paths(),
            reused_evidence=True,
            reuse_policy="gpcr_hard_decoy_operator_intake_packet_from_template_and_suite_contracts",
            repo_root=repo_root,
        ),
        "packet_id": "gpcr_hard_decoy_operator_intake_packet",
        "status": "ready_for_operator_input",
        "reason_code": "PASS_INTAKE_PACKET",
        "contract_pass": True,
        "read_model_ready": True,
        "route": GPCR_OPERATOR_INTAKE_ROUTE,
        "read_model": {
            "route": GPCR_OPERATOR_INTAKE_ROUTE,
            "alternate_routes": [GPCR_PRODUCT_REPORT_ROUTE, "/product/capabilities"],
            "artifact": str(DEFAULT_OUT),
            "mutation_allowed": False,
        },
        "broad_gpcr_family_claim_safe": False,
        "owner_input_required": True,
        "required_targets": list(REQUIRED_TARGETS),
        "required_operator_fields": list(REQUIRED_OPERATOR_FIELDS),
        "exit_criteria": EXIT_CRITERIA,
        "target_slots": [_target_slot(target_id) for target_id in REQUIRED_TARGETS],
        "required_slot_count": len(REQUIRED_TARGETS),
        "gate_unblock_plan": gate_unblock_plan,
        "gate_unblock_plan_count": len(gate_unblock_plan),
        "phase3_raw_row_closure_matrix": phase3_raw_row_closure_matrix,
        "phase3_raw_row_closure_matrix_count": len(phase3_raw_row_closure_matrix),
        "row_template_artifact_count": len(row_template_artifacts),
        "row_template_artifacts": row_template_artifacts,
        "target_execution_preflight": target_execution_preflight,
        "target_execution_preflight_count": len(target_execution_preflight),
        "first_target_execution_preflight_blocker": first_target_preflight_blocker,
        "minimum_target_count": len(REQUIRED_TARGETS),
        "minimum_metric_field_count_per_target": 4,
        "minimum_raw_hard_decoy_row_fields": list(RAW_HARD_DECOY_ROW_FIELDS),
        "minimum_raw_hard_decoy_row_quality": dict(RAW_ROW_QUALITY_CRITERIA),
        "operator_template": {
            "artifact": str(DEFAULT_OPERATOR_TEMPLATE),
            "schema_version": str(template.get("schema_version") or "gpcr-hard-decoy-operator-intake.v1"),
            "required_targets": [str(row) for row in _as_list(template.get("required_targets"))]
            or list(REQUIRED_TARGETS),
            "targets_json_pointer": "/targets",
        },
        "raw_row_import": {
            "step_id": "materialize_gpcr_hard_decoy_operator_template_from_rows",
            "command": import_template_command,
            "produces": str(DEFAULT_OPERATOR_TEMPLATE),
            "accepted_formats": ["csv", "tsv", "json"],
            "default_row_path_candidates": DEFAULT_RAW_ROW_INPUT_CANDIDATES,
            "auto_detecting_actual_closure_command": (
                "python3 scripts/materialize_science_actual_closure_from_rows.py "
                "--fail-blocked"
            ),
            "closure_matrix_ref": "phase3_raw_row_closure_matrix",
            "closes_phase3_criteria": list(PHASE3_EXIT_CRITERIA_BY_FIELD.values()),
            "required_row_fields": list(RAW_HARD_DECOY_ROW_FIELDS),
            "required_flat_row_fields": [
                "target_id",
                *RAW_HARD_DECOY_ROW_FIELDS,
            ],
            "minimum_row_quality_per_target": dict(RAW_ROW_QUALITY_CRITERIA),
            "raw_row_value_contract": dict(RAW_ROW_VALUE_CONTRACT),
            "row_source_receipt_requirements": dict(ROW_SOURCE_RECEIPT_REQUIREMENTS),
            "source_receipt_requirements": dict(SOURCE_RECEIPT_REQUIREMENTS),
            "optional_row_fields": ["score_direction"],
            "required_targets": list(REQUIRED_TARGETS),
            "default_score_direction": "higher_is_better",
            "row_template_artifacts": row_template_artifacts,
            "row_template_headers": _raw_row_template_headers(),
            "claim_boundary": (
                "This import step only groups operator-attached raw ranking rows into "
                "the template. The suite materializer still computes all metrics and "
                "keeps Phase 3 locked unless every target passes."
            ),
        },
        "raw_row_dropzone": {
            "status": "ready_for_operator_rows",
            "auto_detection_policy": (
                "Place real GPCR hard-decoy row files at the default paths, then run "
                "the raw-row importer followed by the suite materializer."
            ),
            "default_row_path_candidates": DEFAULT_RAW_ROW_INPUT_CANDIDATES,
            "row_template_artifacts": row_template_artifacts,
            "materialization_command": import_template_command,
            "required_row_inputs": ["gpcr_hard_decoy_rows"],
        },
        "current_suite_status": {
            "artifact": str(DEFAULT_SUITE_REPORT),
            "schema_version": str(suite.get("schema_version") or SUITE_REPORT_SCHEMA_VERSION),
            "status": str(suite.get("status") or ""),
            "target_count": int(suite.get("target_count") or len(REQUIRED_TARGETS)),
            "target_pass_count": int(suite.get("target_pass_count") or 0),
            "first_blocked_target": first_blocked_target,
            "root_cause_tags": root_cause_tags,
            "blocker_count": len(blockers),
        },
        "materialization_sequence": [
            {
                "step_id": "materialize_gpcr_hard_decoy_operator_template_from_rows",
                "command": import_template_command,
                "produces": str(DEFAULT_OPERATOR_TEMPLATE),
            },
            {
                "step_id": "materialize_gpcr_hard_decoy_suite_report",
                "schema_version": SUITE_REPORT_SCHEMA_VERSION,
                "command": materialize_command,
                "produces": str(DEFAULT_SUITE_REPORT),
            },
            {
                "step_id": "refresh_gpcr_hard_decoy_product_report",
                "schema_version": "gpcr-hard-decoy-product-report.v1",
                "command": refresh_product_report_command,
                "produces": str(DEFAULT_PRODUCT_REPORT),
            },
            {
                "step_id": "refresh_product_capabilities_surface",
                "schema_version": "product-capabilities-surface.v1",
                "command": refresh_capabilities_command,
                "produces": str(DEFAULT_PRODUCT_CAPABILITIES),
            },
            {
                "step_id": "refresh_goal_bottleneck_roadmap_surface",
                "schema_version": "goal-bottleneck-roadmap-surface.v1",
                "command": refresh_goal_command,
                "produces": str(DEFAULT_GOAL_BOTTLENECK),
            },
        ],
        "acceptance_criteria": [
            "gpcr_hard_decoy_suite_report.target_pass_count == 3",
            "gpcr_hard_decoy_suite_report.broad_gpcr_family_claim_safe == true",
            "gpcr_hard_decoy_suite_report.blockers == []",
            (
                "gpcr_hard_decoy_suite_report.phase3_exit_gate."
                "raw_hard_decoy_rows_actual_closure == pass"
            ),
            "gpcr_hard_decoy_product_report.science_claim_status == ready",
            "gpcr_hard_decoy_evidence_surface.locked == false",
        ],
        "linked_artifacts": {
            "operator_template": str(DEFAULT_OPERATOR_TEMPLATE),
            "suite_report": str(DEFAULT_SUITE_REPORT),
            "evidence_surface": str(DEFAULT_EVIDENCE_SURFACE),
            "product_report": str(DEFAULT_PRODUCT_REPORT),
            "product_capabilities_surface": str(DEFAULT_PRODUCT_CAPABILITIES),
            "goal_bottleneck_roadmap_surface": str(DEFAULT_GOAL_BOTTLENECK),
            "row_templates": row_template_artifacts,
        },
        "next_actions": [
            "attach_gpcr_hard_decoy_raw_row_file",
            "materialize_gpcr_hard_decoy_operator_template_from_rows",
            "fill_gpcr_hard_decoy_operator_intake_packet",
            "fill_drd2_htr2a_oprm1_operator_template_values",
            "run_gpcr_hard_decoy_materializer",
            "refresh_gpcr_hard_decoy_product_report",
            "regenerate_product_capabilities_surface",
            "regenerate_goal_bottleneck_roadmap_surface",
        ],
        "summary": {
            "required_slot_count": len(REQUIRED_TARGETS),
            "gate_unblock_plan_count": len(gate_unblock_plan),
            "phase3_raw_row_closure_matrix_count": len(
                phase3_raw_row_closure_matrix
            ),
            "row_template_artifact_count": len(row_template_artifacts),
            "row_template_artifacts": row_template_artifacts,
            "minimum_target_count": len(REQUIRED_TARGETS),
            "minimum_metric_field_count_per_target": 4,
            "current_blocker_count": len(blockers),
            "first_blocked_target": first_blocked_target,
            "target_execution_preflight_count": len(target_execution_preflight),
            "first_target_execution_preflight_target": str(
                first_target_preflight_blocker.get("target_id") or ""
            ),
            "first_target_execution_preflight_blocker": str(
                first_target_preflight_blocker.get("first_blocker") or ""
            ),
            "broad_gpcr_family_claim_safe": False,
        },
        "summary_line": (
            "GPCR hard-decoy operator intake packet: READY | "
            f"targets={len(REQUIRED_TARGETS)} | first_blocked_target={first_blocked_target}"
        ),
        "claim_boundary": (
            "This packet is an owner-facing intake contract for GPCR hard-decoy metrics. "
            "It does not generate docking results, infer missing values, or promote broad "
            "GPCR claims. DRD2, HTR2A, and OPRM1 must all provide raw hard-decoy rows "
            "and pass the numeric exit criteria."
        ),
    }


def _markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# GPCR Hard-Decoy Operator Intake Packet",
        "",
        f"- `contract_pass`: `{payload['contract_pass']}`",
        f"- `status`: `{payload['status']}`",
        f"- `broad_gpcr_family_claim_safe`: `{payload['broad_gpcr_family_claim_safe']}`",
        f"- `first_blocked_target`: `{payload['summary']['first_blocked_target']}`",
        f"- `claim_boundary`: {payload['claim_boundary']}",
        "",
        "| Target | Status | Required Fields |",
        "|---|---|---|",
    ]
    for slot in payload["target_slots"]:
        lines.append(
            f"| `{slot['target_id']}` | `{slot['status']}` | "
            f"`{', '.join(slot['required_fields'])}` |"
        )
    lines.extend(["", "## Gate Unblock Plan", "", "| Target | Criteria | Minimum Evidence |"])
    lines.append("|---|---|---|")
    for row in payload["gate_unblock_plan"]:
        criteria = ", ".join(
            f"`{criterion}`" for criterion in row["unblocks_phase3_criteria"]
        )
        minimum = json.dumps(row["minimum_evidence"], ensure_ascii=False, sort_keys=True)
        lines.append(f"| `{row['target_id']}` | {criteria} | `{minimum}` |")
    lines.extend(
        [
            "",
            "## Phase 3 Raw Row Closure Matrix",
            "",
            "| Target | Row Input | Closes Criteria | Minimum Rows | CSV Starter |",
            "|---|---|---|---|---|",
        ]
    )
    for row in payload["phase3_raw_row_closure_matrix"]:
        criteria = ", ".join(
            f"`{criterion}`" for criterion in row["closes_phase3_criteria"]
        )
        minimums = json.dumps(
            row["raw_row_quality_minimums"],
            ensure_ascii=False,
            sort_keys=True,
        )
        lines.append(
            f"| `{row['target_id']}` | `{row['row_input_id']}` | "
            f"{criteria} | `{minimums}` | `{row['row_template_artifact']}` |"
        )
    lines.extend(
        [
            "",
            "## Raw Row Import",
            "",
            f"- `command`: `{payload['raw_row_import']['command']}`",
            f"- `required_flat_row_fields`: `"
            f"{', '.join(payload['raw_row_import']['required_flat_row_fields'])}`",
            f"- `raw_row_value_contract`: `"
            f"{json.dumps(payload['raw_row_import']['raw_row_value_contract'], ensure_ascii=False, sort_keys=True)}`",
            f"- `source_receipt_requirements`: `"
            f"{json.dumps(payload['raw_row_import']['source_receipt_requirements'], ensure_ascii=False, sort_keys=True)}`",
            f"- `row_template_artifacts`: `"
            f"{json.dumps(payload['raw_row_import']['row_template_artifacts'], ensure_ascii=False, sort_keys=True)}`",
        ]
    )
    lines.extend(
        [
            "",
            "## Target Execution Preflight",
            "",
            "| Target | Ready | Missing Fields | First Blocker |",
            "|---|---|---|---|",
        ]
    )
    for row in payload["target_execution_preflight"]:
        missing = ", ".join(
            f"`{field}`" for field in row["missing_operator_fields"]
        )
        lines.append(
            f"| `{row['target_id']}` | `{row['current_ready']}` | "
            f"{missing or '`none`'} | `{row['first_blocker']}` |"
        )
    lines.extend(["", "## Materialization Sequence", ""])
    for step in payload["materialization_sequence"]:
        lines.append(f"- `{step['step_id']}`: `{step['command']}`")
    lines.extend(["", "## Acceptance Criteria", ""])
    for criterion in payload["acceptance_criteria"]:
        lines.append(f"- `{criterion}`")
    lines.append("")
    return "\n".join(lines)


def write_gpcr_hard_decoy_row_template_csv(
    *,
    packet: dict[str, Any],
    repo_root: Path = ROOT,
) -> dict[str, Path]:
    raw_paths = _as_dict(packet.get("row_template_artifacts"))
    raw_path = str(raw_paths.get("gpcr_hard_decoy_rows") or "")
    if not raw_path:
        return {}
    path = Path(raw_path)
    resolved = path if path.is_absolute() else repo_root / path
    resolved.parent.mkdir(parents=True, exist_ok=True)
    headers = _raw_row_template_headers()
    rows = _raw_row_template_rows()
    with resolved.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow({header: row.get(header, "") for header in headers})
    return {"gpcr_hard_decoy_rows": resolved}


def write_gpcr_hard_decoy_operator_intake_packet(
    *,
    repo_root: Path = ROOT,
    out: Path = DEFAULT_OUT,
    out_md: Path = DEFAULT_OUT_MD,
    row_template_dir: Path = DEFAULT_ROW_TEMPLATE_DIR,
) -> dict[str, Any]:
    payload = build_gpcr_hard_decoy_operator_intake_packet(
        repo_root=repo_root,
        row_template_dir=row_template_dir,
    )
    resolved_out = out if out.is_absolute() else repo_root / out
    resolved_out.parent.mkdir(parents=True, exist_ok=True)
    resolved_out.write_text(_json_text(payload), encoding="utf-8")
    resolved_md = out_md if out_md.is_absolute() else repo_root / out_md
    resolved_md.parent.mkdir(parents=True, exist_ok=True)
    resolved_md.write_text(_markdown(payload), encoding="utf-8")
    write_gpcr_hard_decoy_row_template_csv(packet=payload, repo_root=repo_root)
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    parser.add_argument("--row-template-dir", type=Path, default=DEFAULT_ROW_TEMPLATE_DIR)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = write_gpcr_hard_decoy_operator_intake_packet(
        repo_root=args.repo_root,
        out=args.out,
        out_md=args.out_md,
        row_template_dir=args.row_template_dir,
    )
    print(_json_text(payload), end="") if args.json else print(payload["summary_line"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
