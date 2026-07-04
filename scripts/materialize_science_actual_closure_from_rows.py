#!/usr/bin/env python3
"""Materialize row-driven science closure audits from operator row files."""

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

import materialize_gpcr_hard_decoy_operator_template_from_rows as gpcr_rows  # noqa: E402
import materialize_gpcr_hard_decoy_suite_report as gpcr_suite  # noqa: E402
import materialize_pocketmd_lite_operator_intake_from_rows as pocketmd_rows  # noqa: E402
import materialize_pocketmd_lite_topk_survival_report as pocketmd_survival  # noqa: E402
import materialize_public_benchmark_phase2_from_rows as public_phase2  # noqa: E402
from release_evidence_metadata import release_evidence_metadata  # noqa: E402


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
SURFACE_DIR = Path("implementation/phase1/release_evidence/surface")

DEFAULT_OUT = PRODUCTIZATION / "science_actual_closure_row_audit.json"
DEFAULT_GPCR_TEMPLATE = PRODUCTIZATION / "gpcr_hard_decoy_operator_template.json"
DEFAULT_GPCR_REPORT = PRODUCTIZATION / "gpcr_hard_decoy_suite_report.json"
DEFAULT_GPCR_SURFACE = SURFACE_DIR / "gpcr_hard_decoy_evidence_surface.json"
DEFAULT_POCKETMD_INTAKE = PRODUCTIZATION / "pocketmd_lite_operator_intake.json"
DEFAULT_POCKETMD_REPORT = PRODUCTIZATION / "pocketmd_lite_topk_survival_report.json"
DEFAULT_POCKETMD_SURFACE = SURFACE_DIR / "pocketmd_lite_science_product_surface.json"
DEFAULT_POCKETMD_CONTRACT = PRODUCTIZATION / "pocketmd_lite_contract.json"
DEFAULT_PUBLIC_PHASE2_AUDIT = PRODUCTIZATION / "public_benchmark_phase2_row_audit.json"
DEFAULT_PUBLIC_SOURCE_ACQUISITION_PLAN = (
    PRODUCTIZATION / "public_benchmark_phase2_source_acquisition_plan.json"
)
DEFAULT_PUBLIC_SOURCE_ACCESS_PREFLIGHT_RECEIPT = (
    PRODUCTIZATION / "public_benchmark_source_access_preflight_receipt.json"
)
DEFAULT_PUBLIC_EXTERNAL_RECEIPTS_VALIDATION = (
    PRODUCTIZATION / "public_benchmark_external_receipts_validation.json"
)
DEFAULT_POCKETMD_SOURCE_ACQUISITION_PLAN = (
    PRODUCTIZATION / "pocketmd_lite_source_acquisition_plan.json"
)

SCHEMA_VERSION = "science-actual-closure-row-audit.v1"
PUBLIC_BENCHMARK_COMPONENT_ID = "public_benchmark_phase2_actual_closure"
GPCR_COMPONENT_ID = "gpcr_hard_decoy_actual_closure"
POCKETMD_COMPONENT_ID = "pocketmd_lite_topk_actual_closure"
DEFAULT_ROW_INPUT_CANDIDATES = {
    "subset_rows": tuple(public_phase2.DEFAULT_ROW_INPUT_CANDIDATES["subset_rows"]),
    "pose_rows": tuple(public_phase2.DEFAULT_ROW_INPUT_CANDIDATES["pose_rows"]),
    "enrichment_rows": tuple(public_phase2.DEFAULT_ROW_INPUT_CANDIDATES["enrichment_rows"]),
    "vina_gnina_rows": tuple(public_phase2.DEFAULT_ROW_INPUT_CANDIDATES["vina_gnina_rows"]),
    "gpcr_rows": tuple(
        PRODUCTIZATION / f"gpcr_hard_decoy_rows.{suffix}"
        for suffix in ("json", "jsonl", "ndjson", "csv", "tsv")
    ),
    "pocketmd_rows": tuple(
        PRODUCTIZATION / f"pocketmd_lite_topk_rows.{suffix}"
        for suffix in ("json", "jsonl", "ndjson", "csv", "tsv")
    ),
}


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _resolve(repo_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def _write_json(repo_root: Path, path: Path, payload: dict[str, Any]) -> None:
    resolved = _resolve(repo_root, path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(_json_text(payload), encoding="utf-8")


def _load_optional_json(repo_root: Path, path: Path) -> dict[str, Any]:
    resolved = _resolve(repo_root, path)
    if not resolved.exists():
        return {}
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _source_acquisition_summary(
    payload: dict[str, Any],
    *,
    artifact: Path,
    source_access_receipt: dict[str, Any] | None = None,
    source_access_receipt_artifact: Path | None = None,
    external_receipts_validation: dict[str, Any] | None = None,
    external_receipts_validation_artifact: Path | None = None,
) -> dict[str, Any]:
    receipt_summary = _source_access_receipt_summary(
        source_access_receipt or {},
        artifact=source_access_receipt_artifact,
    )
    external_receipts_summary = _external_receipts_validation_summary(
        external_receipts_validation or {},
        artifact=external_receipts_validation_artifact,
    )
    if not payload:
        return {
            "artifact": str(artifact),
            "present": False,
            "status": "missing",
            "contract_pass": None,
            "blocker_count": 0,
            "blockers": [],
            "operator_next_actions": [],
            "summary": {},
            "source_access_preflight_receipt_summary": receipt_summary,
            "external_receipts_validation_summary": external_receipts_summary,
            "phase4_completion_audit": {},
        }
    raw_blockers = payload.get("blockers", [])
    blockers = (
        [str(row) for row in raw_blockers if str(row)]
        if isinstance(raw_blockers, list)
        else []
    )
    embedded_external_receipts = payload.get("external_receipts_validation")
    if isinstance(embedded_external_receipts, dict) and embedded_external_receipts:
        external_receipts_summary = _external_receipts_validation_summary(
            {
                **embedded_external_receipts,
                "summary_source": "source_acquisition_plan",
            },
            artifact=external_receipts_validation_artifact,
        )
    else:
        external_receipts_summary = {
            **external_receipts_summary,
            "summary_source": "external_validation_artifact",
        }
    summary = payload.get("summary")
    if not isinstance(summary, dict):
        summary = {}
    missing_row_input_actions = [
        row
        for row in payload.get("missing_row_input_actions", [])
        if isinstance(row, dict)
    ] if isinstance(payload.get("missing_row_input_actions"), list) else []
    operator_next_actions = [
        str(row)
        for row in payload.get("operator_next_actions", [])
        if str(row)
    ] if isinstance(payload.get("operator_next_actions"), list) else []
    phase2_row_closure_matrix = [
        row
        for row in payload.get("phase2_row_closure_matrix", [])
        if isinstance(row, dict)
    ] if isinstance(payload.get("phase2_row_closure_matrix"), list) else []
    phase2_exit_criteria = [
        row
        for row in payload.get("phase2_exit_criteria", [])
        if isinstance(row, dict)
    ] if isinstance(payload.get("phase2_exit_criteria"), list) else []
    phase4_candidate_slot_matrix = [
        row
        for row in payload.get("phase4_candidate_slot_matrix", [])
        if isinstance(row, dict)
    ] if isinstance(payload.get("phase4_candidate_slot_matrix"), list) else []
    phase4_metric_closure_matrix = [
        row
        for row in payload.get("phase4_metric_closure_matrix", [])
        if isinstance(row, dict)
    ] if isinstance(payload.get("phase4_metric_closure_matrix"), list) else []
    phase4_completion_audit = payload.get("phase4_completion_audit")
    if not isinstance(phase4_completion_audit, dict):
        phase4_completion_audit = {}
    vina_gnina_runtime_readiness = payload.get("vina_gnina_runtime_readiness")
    if not isinstance(vina_gnina_runtime_readiness, dict):
        vina_gnina_runtime_readiness = {}
    vina_gnina_runtime_readiness_summary = _vina_gnina_runtime_readiness_summary(
        vina_gnina_runtime_readiness
    )
    official_source_receipt_plan = payload.get("official_source_receipt_plan")
    if not isinstance(official_source_receipt_plan, dict):
        official_source_receipt_plan = {}
    source_access_preflight_rows = [
        row
        for row in official_source_receipt_plan.get(
            "source_access_preflight_rows", []
        )
        if isinstance(row, dict)
    ] if isinstance(
        official_source_receipt_plan.get("source_access_preflight_rows"),
        list,
    ) else []
    vina_gnina_case_input_slot_matrix = [
        row
        for row in vina_gnina_runtime_readiness.get("case_input_slot_matrix", [])
        if isinstance(row, dict)
    ] if isinstance(
        vina_gnina_runtime_readiness.get("case_input_slot_matrix"),
        list,
    ) else []
    vina_gnina_engine_run_slot_matrix = [
        row
        for row in vina_gnina_runtime_readiness.get("engine_run_slot_matrix", [])
        if isinstance(row, dict)
    ] if isinstance(
        vina_gnina_runtime_readiness.get("engine_run_slot_matrix"),
        list,
    ) else []
    return {
        "artifact": str(artifact),
        "present": True,
        "status": str(payload.get("status") or ""),
        "contract_pass": payload.get("contract_pass"),
        "blocker_count": int(payload.get("blocker_count") or len(blockers)),
        "blockers": blockers,
        "operator_next_actions": operator_next_actions,
        "missing_row_input_action_count": int(
            payload.get("missing_row_input_action_count")
            or len(missing_row_input_actions)
        ),
        "missing_row_input_actions": missing_row_input_actions,
        "phase2_row_closure_matrix_count": int(
            payload.get("phase2_row_closure_matrix_count")
            or len(phase2_row_closure_matrix)
        ),
        "phase2_row_closure_matrix": phase2_row_closure_matrix,
        "phase2_exit_criterion_count": int(
            payload.get("phase2_exit_criterion_count")
            or len(phase2_exit_criteria)
        ),
        "phase2_exit_criteria": phase2_exit_criteria,
        "source_access_preflight_count": int(
            official_source_receipt_plan.get("source_access_preflight_count")
            or len(source_access_preflight_rows)
        ),
        "source_access_preflight_rows": source_access_preflight_rows,
        "source_access_preflight_receipt_artifact": str(
            official_source_receipt_plan.get(
                "source_access_preflight_receipt_artifact"
            )
            or ""
        ),
        "source_access_preflight_receipt_markdown_artifact": str(
            official_source_receipt_plan.get(
                "source_access_preflight_receipt_markdown_artifact"
            )
            or ""
        ),
        "source_access_preflight_receipt_command": str(
            official_source_receipt_plan.get(
                "source_access_preflight_receipt_command"
            )
            or ""
        ),
        "source_access_network_probe_command": str(
            official_source_receipt_plan.get("source_access_network_probe_command")
            or ""
        ),
        "source_access_preflight_receipt_summary": receipt_summary,
        "external_receipts_validation_summary": external_receipts_summary,
        "phase4_candidate_slot_matrix_count": int(
            payload.get("phase4_candidate_slot_matrix_count")
            or len(phase4_candidate_slot_matrix)
        ),
        "phase4_missing_candidate_slot_count": int(
            payload.get("phase4_missing_candidate_slot_count")
            or sum(1 for row in phase4_candidate_slot_matrix if row.get("missing"))
        ),
        "phase4_candidate_slot_matrix": phase4_candidate_slot_matrix,
        "phase4_metric_closure_matrix_count": int(
            payload.get("phase4_metric_closure_matrix_count")
            or len(phase4_metric_closure_matrix)
        ),
        "phase4_metric_closure_matrix": phase4_metric_closure_matrix,
        "phase4_completion_audit": phase4_completion_audit,
        "vina_gnina_case_input_slot_matrix_count": int(
            vina_gnina_runtime_readiness.get("case_input_slot_matrix_count")
            or len(vina_gnina_case_input_slot_matrix)
        ),
        "vina_gnina_blocked_case_input_slot_count": int(
            vina_gnina_runtime_readiness.get("blocked_case_input_slot_count")
            or sum(
                1
                for row in vina_gnina_case_input_slot_matrix
                if row.get("status") != "ready"
            )
        ),
        "vina_gnina_case_input_slot_matrix": vina_gnina_case_input_slot_matrix,
        "vina_gnina_engine_run_slot_matrix_count": int(
            vina_gnina_runtime_readiness.get("engine_run_slot_matrix_count")
            or len(vina_gnina_engine_run_slot_matrix)
        ),
        "vina_gnina_blocked_engine_run_slot_count": int(
            vina_gnina_runtime_readiness.get("blocked_engine_run_slot_count")
            or sum(
                1
                for row in vina_gnina_engine_run_slot_matrix
                if row.get("status") != "ready_for_engine_execution"
            )
        ),
        "vina_gnina_engine_run_slot_matrix": vina_gnina_engine_run_slot_matrix,
        "vina_gnina_runtime_readiness": vina_gnina_runtime_readiness_summary,
        "summary": summary,
    }


def _vina_gnina_runtime_readiness_summary(payload: dict[str, Any]) -> dict[str, Any]:
    if not payload:
        return {}
    missing_engine_ids = [
        str(row) for row in payload.get("missing_engine_ids", []) if str(row)
    ] if isinstance(payload.get("missing_engine_ids"), list) else []
    operator_unblock_packet = payload.get("operator_unblock_packet")
    if not isinstance(operator_unblock_packet, dict):
        operator_unblock_packet = {}
    return {
        "artifact": str(payload.get("artifact") or ""),
        "status": str(payload.get("status") or ""),
        "contract_pass": payload.get("contract_pass"),
        "execution_plan_ready": bool(payload.get("execution_plan_ready")),
        "runtime_ready_for_engine_execution": bool(
            payload.get("runtime_ready_for_engine_execution")
        ),
        "operator_execution_ready": bool(payload.get("operator_execution_ready")),
        "adapter_rows_ready": bool(payload.get("adapter_rows_ready")),
        "case_count": int(payload.get("case_count") or 0),
        "required_engine_run_count": int(
            payload.get("required_engine_run_count") or 0
        ),
        "ready_engine_run_slot_count": int(
            payload.get("ready_engine_run_slot_count") or 0
        ),
        "case_input_slot_matrix_count": int(
            payload.get("case_input_slot_matrix_count") or 0
        ),
        "blocked_case_input_slot_count": int(
            payload.get("blocked_case_input_slot_count") or 0
        ),
        "engine_run_slot_matrix_count": int(
            payload.get("engine_run_slot_matrix_count") or 0
        ),
        "blocked_engine_run_slot_count": int(
            payload.get("blocked_engine_run_slot_count") or 0
        ),
        "missing_engine_ids": missing_engine_ids,
        "adapter_row_preflight_status": str(
            payload.get("adapter_row_preflight_status") or ""
        ),
        "operator_unblock_packet": _compact_vina_gnina_unblock_packet(
            operator_unblock_packet
        ),
        "command": str(payload.get("command") or ""),
    }


def _compact_vina_gnina_unblock_packet(payload: dict[str, Any]) -> dict[str, Any]:
    if not payload:
        return {}
    commands = payload.get("commands")
    if not isinstance(commands, dict):
        commands = {}
    return {
        "status": str(payload.get("status") or ""),
        "input_manifest_template_artifact": str(
            payload.get("input_manifest_template_artifact") or ""
        ),
        "input_manifest_template_preflight_artifact": str(
            payload.get("input_manifest_template_preflight_artifact") or ""
        ),
        "input_manifest_template_preflight_markdown_artifact": str(
            payload.get("input_manifest_template_preflight_markdown_artifact") or ""
        ),
        "expected_rows_artifact": str(payload.get("expected_rows_artifact") or ""),
        "case_input_slot_count": int(payload.get("case_input_slot_count") or 0),
        "blocked_case_input_slot_count": int(
            payload.get("blocked_case_input_slot_count") or 0
        ),
        "required_engine_run_count": int(
            payload.get("required_engine_run_count") or 0
        ),
        "ready_engine_run_slot_count": int(
            payload.get("ready_engine_run_slot_count") or 0
        ),
        "blocked_engine_run_slot_count": int(
            payload.get("blocked_engine_run_slot_count") or 0
        ),
        "missing_engine_ids": [
            str(row) for row in payload.get("missing_engine_ids", []) if str(row)
        ] if isinstance(payload.get("missing_engine_ids"), list) else [],
        "adapter_row_preflight_status": str(
            payload.get("adapter_row_preflight_status") or ""
        ),
        "operator_sequence": [
            str(row) for row in payload.get("operator_sequence", []) if str(row)
        ] if isinstance(payload.get("operator_sequence"), list) else [],
        "commands": {str(key): str(value) for key, value in commands.items()},
    }


def _external_receipts_validation_summary(
    payload: dict[str, Any],
    *,
    artifact: Path | None,
) -> dict[str, Any]:
    if not artifact:
        return {}
    if not payload:
        return {
            "artifact": str(artifact),
            "present": False,
            "status": "missing",
            "public_benchmark_external_receipts_ready": False,
            "summary": {},
        }
    receipt_coverage = payload.get("receipt_coverage")
    if not isinstance(receipt_coverage, dict):
        receipt_coverage = {}
    expected_artifact_role_count = int(
        receipt_coverage.get("expected_artifact_role_count")
        or payload.get("expected_artifact_role_count")
        or 0
    )
    materialized_artifact_role_count = int(
        receipt_coverage.get("materialized_artifact_role_count")
        or payload.get("materialized_artifact_role_count")
        or 0
    )
    receipt_complete_artifact_role_count = int(
        receipt_coverage.get("receipt_complete_artifact_role_count")
        or payload.get("receipt_complete_artifact_role_count")
        or 0
    )
    missing_expected_artifact_roles = receipt_coverage.get(
        "missing_expected_artifact_roles"
    )
    if not isinstance(missing_expected_artifact_roles, list):
        missing_expected_artifact_roles = payload.get(
            "missing_expected_artifact_roles", []
        )
    return {
        "artifact": str(artifact),
        "present": True,
        "summary_source": str(payload.get("summary_source") or ""),
        "status": str(payload.get("status") or ""),
        "contract_pass": payload.get("contract_pass"),
        "public_benchmark_external_receipts_ready": bool(
            payload.get("public_benchmark_external_receipts_ready")
        ),
        "materialized_row_count": int(payload.get("materialized_row_count") or 0),
        "receipt_complete_row_count": int(
            payload.get("receipt_complete_row_count") or 0
        ),
        "receipt_blocked_row_count": int(
            payload.get("receipt_blocked_row_count") or 0
        ),
        "blocker_count": int(payload.get("blocker_count") or 0),
        "blockers": [
            str(row) for row in payload.get("blockers", []) if str(row)
        ] if isinstance(payload.get("blockers"), list) else [],
        "expected_artifact_role_count": expected_artifact_role_count,
        "materialized_artifact_role_count": materialized_artifact_role_count,
        "receipt_complete_artifact_role_count": receipt_complete_artifact_role_count,
        "missing_expected_artifact_roles": [
            str(row)
            for row in missing_expected_artifact_roles
            if str(row)
        ] if isinstance(missing_expected_artifact_roles, list) else [],
        "claim_boundary": str(payload.get("claim_boundary") or ""),
    }


def _source_access_receipt_summary(
    payload: dict[str, Any],
    *,
    artifact: Path | None,
) -> dict[str, Any]:
    if not artifact:
        return {}
    if not payload:
        return {
            "artifact": str(artifact),
            "present": False,
            "status": "missing",
            "contract_pass": None,
            "network_probe_performed": False,
            "source_access_ready": False,
            "summary": {},
        }
    summary = payload.get("summary")
    if not isinstance(summary, dict):
        summary = {}
    return {
        "artifact": str(artifact),
        "present": True,
        "status": str(payload.get("status") or ""),
        "contract_pass": payload.get("contract_pass"),
        "network_probe_performed": bool(payload.get("network_probe_performed")),
        "source_access_ready": bool(payload.get("source_access_ready")),
        "source_access_probe_row_count": int(
            payload.get("source_access_preflight_count")
            or summary.get("source_access_probe_row_count")
            or 0
        ),
        "reachable_count": int(summary.get("reachable_count") or 0),
        "blocked_count": int(summary.get("blocked_count") or 0),
        "not_run_count": int(summary.get("not_run_count") or 0),
        "generated_at": str(payload.get("generated_at") or ""),
        "source_plan_artifact": str(payload.get("source_plan_artifact") or ""),
        "summary": summary,
        "claim_boundary": str(payload.get("claim_boundary") or ""),
    }


def _upstream_source_acquisition_context(repo_root: Path) -> dict[str, Any]:
    public_plan = _load_optional_json(repo_root, DEFAULT_PUBLIC_SOURCE_ACQUISITION_PLAN)
    public_source_access_receipt = _load_optional_json(
        repo_root,
        DEFAULT_PUBLIC_SOURCE_ACCESS_PREFLIGHT_RECEIPT,
    )
    public_external_receipts_validation = _load_optional_json(
        repo_root,
        DEFAULT_PUBLIC_EXTERNAL_RECEIPTS_VALIDATION,
    )
    pocketmd_plan = _load_optional_json(
        repo_root,
        DEFAULT_POCKETMD_SOURCE_ACQUISITION_PLAN,
    )
    return {
        "public_benchmark_phase2": _source_acquisition_summary(
            public_plan,
            artifact=DEFAULT_PUBLIC_SOURCE_ACQUISITION_PLAN,
            source_access_receipt=public_source_access_receipt,
            source_access_receipt_artifact=(
                DEFAULT_PUBLIC_SOURCE_ACCESS_PREFLIGHT_RECEIPT
            ),
            external_receipts_validation=public_external_receipts_validation,
            external_receipts_validation_artifact=(
                DEFAULT_PUBLIC_EXTERNAL_RECEIPTS_VALIDATION
            ),
        ),
        "pocketmd_lite": _source_acquisition_summary(
            pocketmd_plan,
            artifact=DEFAULT_POCKETMD_SOURCE_ACQUISITION_PLAN,
        ),
    }


def _upstream_source_blockers(
    upstream_source_acquisition: dict[str, dict[str, Any]],
) -> list[str]:
    blockers: list[str] = []
    for source_id, source_summary in upstream_source_acquisition.items():
        if not isinstance(source_summary, dict):
            continue
        blockers.extend(
            f"{source_id}_source_acquisition::{blocker}"
            for blocker in source_summary.get("blockers", [])
            if str(blocker)
        )
    return blockers


def _candidate_path_strings(row_input_id: str) -> list[str]:
    return [str(path) for path in DEFAULT_ROW_INPUT_CANDIDATES[row_input_id]]


def _resolve_row_input(
    *,
    repo_root: Path,
    row_input_id: str,
    explicit_path: Path | None,
) -> tuple[Path | None, dict[str, Any]]:
    candidates = DEFAULT_ROW_INPUT_CANDIDATES[row_input_id]
    if explicit_path is not None:
        return explicit_path, {
            "row_input_id": row_input_id,
            "explicit_path": str(explicit_path),
            "resolved_path": str(explicit_path),
            "auto_detected": False,
            "candidate_paths": _candidate_path_strings(row_input_id),
            "missing": False,
        }
    for candidate in candidates:
        resolved_candidate = _resolve(repo_root, candidate)
        if resolved_candidate.exists():
            return candidate, {
                "row_input_id": row_input_id,
                "explicit_path": "",
                "resolved_path": str(candidate),
                "auto_detected": True,
                "candidate_paths": _candidate_path_strings(row_input_id),
                "missing": False,
            }
    return None, {
        "row_input_id": row_input_id,
        "explicit_path": "",
        "resolved_path": "",
        "auto_detected": False,
        "candidate_paths": _candidate_path_strings(row_input_id),
        "missing": True,
    }


def _gpcr_row_intake_contract(
    *,
    template_out: Path,
    report_out: Path,
    surface_out: Path,
) -> dict[str, Any]:
    return {
        "component_id": "gpcr_hard_decoy_actual_closure",
        "row_input_id": "gpcr_rows",
        "accepted_formats": list(gpcr_rows.SUPPORTED_ROW_FORMATS),
        "default_row_path_candidates": _candidate_path_strings("gpcr_rows"),
        "auto_detection_policy": (
            "When --gpcr-rows is omitted, the runner uses the first existing "
            "default row path candidate and records it in row_input_resolution."
        ),
        "required_targets": list(gpcr_suite.REQUIRED_TARGETS),
        "required_flat_row_fields": [
            "target_id",
            *gpcr_suite.RAW_RANKING_ROW_FIELDS,
        ],
        "optional_flat_row_fields": ["score_direction"],
        "accepted_score_direction_values": [
            "higher_is_better",
            "lower_is_better",
        ],
        "default_score_direction": gpcr_rows.DEFAULT_SCORE_DIRECTION,
        "row_integrity_policy": {
            "required_unique_row_keys": {
                "raw_hard_decoy_rows": ["target_id", "molecule_id"]
            },
            "purpose": (
                "Duplicate molecules within a GPCR target cannot be used to inflate "
                "positive/decoy counts or Phase 3 hard-decoy ranking metrics."
            ),
        },
        "source_receipt_required_fields": [
            "source_id",
            "source_url",
            "source_license",
            "source_artifact_sha256",
        ],
        "source_actuality_policy": {
            "placeholder_source_text_markers_rejected": list(
                gpcr_suite.PLACEHOLDER_SOURCE_TEXT_MARKERS
            ),
            "placeholder_source_url_markers_rejected": list(
                gpcr_suite.PLACEHOLDER_SOURCE_URL_MARKERS
            ),
            "placeholder_source_url_prefixes_rejected": list(
                gpcr_suite.PLACEHOLDER_SOURCE_URL_PREFIXES
            ),
            "source_artifact_sha256_policy": (
                "sha256:<64 hex> and must match the attached raw hard-decoy row artifact"
            ),
        },
        "raw_row_quality_minimums": dict(gpcr_suite.RAW_ROW_QUALITY_CRITERIA),
        "numeric_value_policy": {
            "score": "must parse to a finite float; NaN and Infinity are rejected",
        },
        "boolean_label_policy": {
            "is_positive": (
                "must parse to a boolean; exactly one of is_positive/is_decoy "
                "must be true per molecule row"
            ),
            "is_decoy": (
                "must parse to a boolean; exactly one of is_positive/is_decoy "
                "must be true per molecule row"
            ),
        },
        "score_direction_policy": (
            "Each target must use one consistent score_direction value; mixed "
            "higher_is_better/lower_is_better rows for the same target are rejected."
        ),
        "unexpected_target_policy": (
            "Rows for targets outside the required DRD2/HTR2A/OPRM1 set are "
            "recorded as unexpected_targets and do not count toward actual closure."
        ),
        "phase3_exit_criteria": dict(gpcr_suite.EXIT_CRITERIA),
        "actual_closure_criterion_id": gpcr_suite.ACTUAL_CLOSURE_CRITERION_ID,
        "expected_outputs": {
            "operator_template": str(template_out),
            "suite_report": str(report_out),
            "evidence_surface": str(surface_out),
        },
        "materialization_command": (
            "python3 scripts/materialize_science_actual_closure_from_rows.py "
            "--gpcr-rows <gpcr-hard-decoy-rows.csv|tsv|json|jsonl|ndjson> "
            "--source-id <source-id> --source-url <source-url> "
            "--source-license <license> --fail-blocked"
        ),
        "claim_boundary": (
            "GPCR Phase 3 actual closure requires operator-attached raw hard-decoy "
            "ranking rows for every required target plus a verifiable source receipt. "
            "Summary metrics or fixture rows do not satisfy actual closure."
        ),
    }


def _pocketmd_row_intake_contract(
    *,
    intake_out: Path,
    report_out: Path,
    surface_out: Path,
    contract_path: Path,
    max_top_k: int,
) -> dict[str, Any]:
    return {
        "component_id": "pocketmd_lite_topk_actual_closure",
        "row_input_id": "pocketmd_rows",
        "accepted_formats": list(pocketmd_rows.SUPPORTED_ROW_FORMATS),
        "default_row_path_candidates": _candidate_path_strings("pocketmd_rows"),
        "auto_detection_policy": (
            "When --pocketmd-rows is omitted, the runner uses the first existing "
            "default row path candidate and records it in row_input_resolution."
        ),
        "max_top_k": max_top_k,
        "required_case_fields": list(pocketmd_survival.REQUIRED_CASE_FIELDS),
        "uncertainty_field_modes": [
            "uncertainty_interval:{low,high,unit}",
            "uncertainty_low+uncertainty_high+uncertainty_unit",
        ],
        "numeric_value_policy": {
            "pre_refinement_energy_proxy": (
                "must parse to a finite float; NaN and Infinity are rejected"
            ),
            "post_refinement_energy_proxy": (
                "must parse to a finite float; NaN and Infinity are rejected"
            ),
            "contact_persistence_rate": (
                "must parse to a finite float in [0, 1]; NaN and Infinity are rejected"
            ),
            "h_bond_persistence_rate": (
                "must parse to a finite float in [0, 1]; NaN and Infinity are rejected"
            ),
            "uncertainty_interval.low": (
                "must parse to a finite float; NaN and Infinity are rejected"
            ),
            "uncertainty_interval.high": (
                "must parse to a finite float and be >= low; NaN and Infinity are rejected"
            ),
        },
        "integer_value_policy": {
            "top_k_rank": (
                "must parse to a positive integer <= max_top_k and form a "
                "contiguous rank prefix starting at 1 for each case"
            ),
            "clash_count_before": "must parse to a non-negative integer",
            "clash_count_after": "must parse to a non-negative integer",
        },
        "boolean_value_policy": {
            "local_min_survived": "must parse to a boolean value",
        },
        "required_summary_metrics": list(pocketmd_survival.REQUIRED_SUMMARY_METRICS),
        "required_component_metrics": list(pocketmd_survival.REQUIRED_METRICS),
        "top_k_row_quality_minimums": dict(
            pocketmd_survival.TOPK_ROW_QUALITY_CRITERIA
        ),
        "top_k_rank_prefix_policy": pocketmd_survival.TOP_K_RANK_PREFIX_POLICY,
        "row_integrity_policy": {
            "required_unique_row_keys": {
                "top_k_refinement_rows": [
                    ["case_id", "top_k_rank"],
                    ["case_id", "candidate_id"],
                ]
            },
            "purpose": (
                "Duplicate PocketMD Lite top-k ranks or candidate identities cannot "
                "be used to inflate case, candidate, or survival counts."
            ),
        },
        "source_receipt_required_fields": [
            "source_id",
            "source_url",
            "source_license",
            "source_artifact_sha256",
            "per_row_source_checksum",
            "per_row_provenance_ref",
        ],
        "per_row_source_actuality_policy": {
            "placeholder_provenance_prefixes_rejected": list(
                pocketmd_survival.PLACEHOLDER_PROVENANCE_PREFIXES
            ),
            "placeholder_markers_rejected": list(
                pocketmd_survival.PLACEHOLDER_SOURCE_TEXT_MARKERS
            ),
            "source_checksum_policy": (
                "sha256:<64 hex> and not a repeated placeholder digest"
            ),
        },
        "blocked_claims_that_remain_locked": list(pocketmd_survival.BLOCKED_CLAIMS),
        "expected_outputs": {
            "operator_intake": str(intake_out),
            "topk_survival_report": str(report_out),
            "science_surface": str(surface_out),
        },
        "contract_path": str(contract_path),
        "materialization_command": (
            "python3 scripts/materialize_science_actual_closure_from_rows.py "
            "--pocketmd-rows <pocketmd-lite-topk-rows.csv|tsv|json|jsonl|ndjson> "
            "--source-id <source-id> --source-url <source-url> "
            "--source-license <license> --fail-blocked"
        ),
        "claim_boundary": (
            "PocketMD Lite closure is limited to top-k local refinement rows with "
            "local-min survival, contact persistence, H-bond persistence, clash "
            "relief, and uncertainty summaries. It does not unlock broad all-atom "
            "MD, FEP, long-timescale dynamics, or de novo binding claims."
        ),
    }


def _missing_component(component_id: str, blocker: str, expected_mode: str) -> dict[str, Any]:
    return {
        "component_id": component_id,
        "status": "operator_evidence_required",
        "contract_pass": False,
        "materialized": False,
        "blockers": [blocker],
        "expected_rows_mode": expected_mode,
        "outputs": {},
    }


def _gpcr_missing_phase3_criteria() -> list[dict[str, Any]]:
    targets = list(gpcr_suite.REQUIRED_TARGETS)
    return [
        {
            "criterion_id": "ranking_pr_auc_ci_low_min",
            "pass": False,
            "required": f">={gpcr_suite.EXIT_CRITERIA['ranking_pr_auc_ci_low_min']}",
            "current_by_target": {target: None for target in targets},
            "failed_targets": targets,
            "blockers": [
                f"{target}:ranking_pr_auc_ci_low_required" for target in targets
            ],
        },
        {
            "criterion_id": "top20_hit_rate_min",
            "pass": False,
            "required": f">={gpcr_suite.EXIT_CRITERIA['top20_hit_rate_min']}",
            "current_by_target": {target: None for target in targets},
            "failed_targets": targets,
            "blockers": [f"{target}:top20_hit_rate_required" for target in targets],
        },
        {
            "criterion_id": "decoys_above_positive_count_max",
            "pass": False,
            "required": f"<={gpcr_suite.EXIT_CRITERIA['decoys_above_positive_count_max']}",
            "current_by_target": {target: None for target in targets},
            "failed_targets": targets,
            "blockers": [
                f"{target}:decoys_above_positive_count_required" for target in targets
            ],
        },
        {
            "criterion_id": "no_positive_out_anchored_by_top_decoys",
            "pass": False,
            "required": bool(
                gpcr_suite.EXIT_CRITERIA[
                    "positive_out_anchored_by_top_decoys_allowed"
                ]
            ),
            "current_by_target": {target: None for target in targets},
            "failed_targets": targets,
            "blockers": [
                f"{target}:positive_out_anchored_by_top_decoys_required"
                for target in targets
            ],
        },
        {
            "criterion_id": gpcr_suite.ACTUAL_CLOSURE_CRITERION_ID,
            "pass": False,
            "required": "computed_from_raw_hard_decoy_rows_with_quality_minimums",
            "current_by_target": {target: "missing" for target in targets},
            "failed_targets": targets,
            "blockers": [
                f"{target}:hard_decoy_rows_required_for_actual_closure"
                for target in targets
            ],
        },
    ]


def _pocketmd_missing_phase4_criteria() -> list[dict[str, Any]]:
    summary = {
        "real_refinement_case_count": 0,
        "top_k_candidate_count": 0,
        "top_k_row_quality": {
            "contract_pass": False,
            "minimums": dict(pocketmd_survival.TOPK_ROW_QUALITY_CRITERIA),
        },
        "local_min_survival_rate": None,
        "contact_persistence_rate_median": None,
        "h_bond_persistence_rate_median": None,
        "clash_relief_rate": None,
        "uncertainty_width_median": None,
    }
    gate = pocketmd_survival.build_phase4_exit_gate(
        summary=summary,
        blockers=list(pocketmd_survival.EMPTY_INTAKE_BLOCKERS),
        product_surface_ready=False,
        first_blocked_target="top_k_refinement_operator_intake",
    )
    return [row for row in gate.get("criteria", []) if isinstance(row, dict)]


def _component_criteria(component: dict[str, Any]) -> list[dict[str, Any]]:
    component_id = str(component.get("component_id") or "")
    if component_id == PUBLIC_BENCHMARK_COMPONENT_ID:
        rows = component.get("phase2_requirements")
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
        return []
    if component_id == GPCR_COMPONENT_ID:
        rows = component.get("phase3_exit_gate_criteria")
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
        return _gpcr_missing_phase3_criteria()
    if component_id == POCKETMD_COMPONENT_ID:
        rows = component.get("phase4_exit_gate_criteria")
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
        return _pocketmd_missing_phase4_criteria()
    return []


def _actual_closure_requirements(
    components: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    requirements: list[dict[str, Any]] = []
    for component in components:
        component_id = str(component.get("component_id") or "")
        if component_id == PUBLIC_BENCHMARK_COMPONENT_ID:
            scope = "public_benchmark_phase2_exit_gate"
            row_input_id = "public_benchmark_phase2_rows"
            expected_rows_mode = "operator_attached_public_benchmark_rows"
            requirement_kind = "phase2_exit_criterion"
            extra = {
                "required_phase2_components": [
                    dict(row)
                    for row in public_phase2.harness_bundle.PHASE2_REQUIRED_COMPONENTS
                ],
                "phase2_row_closure_matrix_count": int(
                    component.get("phase2_row_closure_matrix_count") or 0
                ),
            }
        elif component_id == GPCR_COMPONENT_ID:
            scope = "gpcr_phase3_exit_gate"
            row_input_id = "gpcr_rows"
            expected_rows_mode = "raw_hard_decoy_rows"
            requirement_kind = "phase3_exit_criterion"
            extra = {
                "required_targets": list(gpcr_suite.REQUIRED_TARGETS),
                "raw_row_quality_minimums": dict(gpcr_suite.RAW_ROW_QUALITY_CRITERIA),
            }
        elif component_id == POCKETMD_COMPONENT_ID:
            scope = "pocketmd_lite_phase4_exit_gate"
            row_input_id = "pocketmd_rows"
            expected_rows_mode = "raw_top_k_refinement_rows"
            requirement_kind = "phase4_exit_criterion"
            extra = {
                "top_k_row_quality_minimums": dict(
                    pocketmd_survival.TOPK_ROW_QUALITY_CRITERIA
                ),
                "blocked_claims_that_remain_locked": list(
                    pocketmd_survival.BLOCKED_CLAIMS
                ),
            }
        else:
            continue

        for criterion in _component_criteria(component):
            blockers = [
                str(item) for item in criterion.get("blockers", []) if str(item)
            ]
            criterion_pass = bool(
                criterion.get("pass")
                if "pass" in criterion
                else criterion.get("ready")
            )
            row = {
                "component_id": component_id,
                "scope": scope,
                "requirement_kind": requirement_kind,
                "criterion_id": str(criterion.get("criterion_id") or ""),
                "pass": criterion_pass,
                "materialized": bool(component.get("materialized")),
                "row_input_id": row_input_id,
                "expected_rows_mode": expected_rows_mode,
                "required": criterion.get("required"),
                "blockers": blockers,
                "blocker_count": len(blockers),
            }
            for key in (
                "current",
                "current_by_target",
                "failed_targets",
                "required_row_inputs",
                "missing_row_inputs",
                "component_id",
            ):
                if key in criterion:
                    output_key = "phase2_component_id" if key == "component_id" else key
                    row[output_key] = criterion[key]
            if component_id == PUBLIC_BENCHMARK_COMPONENT_ID:
                row["row_input_ids"] = [
                    str(item) for item in row.get("required_row_inputs", [])
                ]
            row.update(extra)
            requirements.append(row)
    return requirements


def _actual_closure_requirement_summary(
    requirements: list[dict[str, Any]],
    *,
    missing_row_inputs: list[str],
) -> dict[str, Any]:
    blocked_component_ids = sorted(
        {
            str(row.get("component_id") or "")
            for row in requirements
            if not bool(row.get("pass")) and str(row.get("component_id") or "")
        }
    )
    gpcr_rows = [
        row for row in requirements if row.get("component_id") == GPCR_COMPONENT_ID
    ]
    pocketmd_rows = [
        row for row in requirements if row.get("component_id") == POCKETMD_COMPONENT_ID
    ]
    public_rows = [
        row
        for row in requirements
        if row.get("component_id") == PUBLIC_BENCHMARK_COMPONENT_ID
    ]
    return {
        "required_component_count": 3,
        "ready_component_count": len(
            {
                component_id
                for component_id in (
                    PUBLIC_BENCHMARK_COMPONENT_ID,
                    GPCR_COMPONENT_ID,
                    POCKETMD_COMPONENT_ID,
                )
                if any(
                    row.get("component_id") == component_id for row in requirements
                )
                and all(
                    bool(row.get("pass"))
                    for row in requirements
                    if row.get("component_id") == component_id
                )
            }
        ),
        "requirement_count": len(requirements),
        "passing_requirement_count": sum(
            1 for row in requirements if bool(row.get("pass"))
        ),
        "blocked_requirement_count": sum(
            1 for row in requirements if not bool(row.get("pass"))
        ),
        "blocked_component_ids": blocked_component_ids,
        "missing_row_inputs": missing_row_inputs,
        "missing_row_input_count": len(missing_row_inputs),
        "public_benchmark_phase2_requirement_count": len(public_rows),
        "public_benchmark_phase2_passing_requirement_count": sum(
            1 for row in public_rows if bool(row.get("pass"))
        ),
        "gpcr_phase3_requirement_count": len(gpcr_rows),
        "gpcr_phase3_passing_requirement_count": sum(
            1 for row in gpcr_rows if bool(row.get("pass"))
        ),
        "pocketmd_phase4_requirement_count": len(pocketmd_rows),
        "pocketmd_phase4_passing_requirement_count": sum(
            1 for row in pocketmd_rows if bool(row.get("pass"))
        ),
        "actual_closure_ready": not blocked_component_ids and not missing_row_inputs,
    }


def _component_requirement_summary(
    requirements: list[dict[str, Any]],
    *,
    component_id: str,
) -> dict[str, Any]:
    rows = [
        row
        for row in requirements
        if str(row.get("component_id") or "") == component_id
    ]
    failed_criteria = [
        str(row.get("criterion_id") or "")
        for row in rows
        if not bool(row.get("pass"))
    ]
    blocker_count = sum(
        len([blocker for blocker in row.get("blockers", []) if str(blocker)])
        for row in rows
    )
    return {
        "component_id": component_id,
        "requirement_count": len(rows),
        "passing_requirement_count": sum(1 for row in rows if bool(row.get("pass"))),
        "blocked_requirement_count": len(failed_criteria),
        "failed_criteria": failed_criteria,
        "failed_criterion_count": len(failed_criteria),
        "blocker_count": blocker_count,
        "actual_closure_ready": bool(rows) and not failed_criteria,
    }


def _requirement_row_input_ids(requirement: dict[str, Any]) -> list[str]:
    row_input_ids = requirement.get("row_input_ids")
    if isinstance(row_input_ids, list):
        return sorted({str(item) for item in row_input_ids if str(item)})
    row_input_id = str(requirement.get("row_input_id") or "")
    return [row_input_id] if row_input_id else []


def _completion_requirement_rows(
    requirements: list[dict[str, Any]],
    *,
    component_id: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for requirement in requirements:
        if str(requirement.get("component_id") or "") != component_id:
            continue
        row = {
            "criterion_id": str(requirement.get("criterion_id") or ""),
            "pass": bool(requirement.get("pass")),
            "required": requirement.get("required"),
            "row_input_ids": _requirement_row_input_ids(requirement),
            "blockers": [
                str(item) for item in requirement.get("blockers", []) if str(item)
            ],
        }
        for key in ("current", "current_by_target", "failed_targets"):
            if key in requirement:
                row[key] = requirement[key]
        rows.append(row)
    return rows


def _component_completion_audits(
    components: list[dict[str, Any]],
    requirements: list[dict[str, Any]],
    row_closure_matrix: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    completion_rows: list[dict[str, Any]] = []
    for component in components:
        component_id = str(component.get("component_id") or "")
        requirement_rows = _completion_requirement_rows(
            requirements,
            component_id=component_id,
        )
        missing_row_inputs = [
            str(row.get("row_input_id") or "")
            for row in row_closure_matrix
            if str(row.get("actual_closure_component_id") or "") == component_id
            and bool(row.get("missing"))
            and str(row.get("row_input_id") or "")
        ]
        provided_row_inputs = [
            str(row.get("row_input_id") or "")
            for row in row_closure_matrix
            if str(row.get("actual_closure_component_id") or "") == component_id
            and not bool(row.get("missing"))
            and str(row.get("row_input_id") or "")
        ]
        passed_criteria = [
            str(row.get("criterion_id") or "") for row in requirement_rows if row["pass"]
        ]
        failed_criteria = [
            str(row.get("criterion_id") or "")
            for row in requirement_rows
            if not row["pass"]
        ]
        actual_closure_ready = bool(component.get("actual_closure_ready"))
        if actual_closure_ready:
            status = "complete"
        elif missing_row_inputs:
            status = "operator_rows_required"
        else:
            status = "blocked"
        completion_rows.append(
            {
                "component_id": component_id,
                "status": status,
                "actual_closure_ready": actual_closure_ready,
                "contract_pass": bool(component.get("contract_pass")),
                "materialized": bool(component.get("materialized")),
                "requirement_pass_count": len(passed_criteria),
                "requirement_count": len(requirement_rows),
                "passed_criteria": passed_criteria,
                "failed_criteria": failed_criteria,
                "missing_row_inputs": missing_row_inputs,
                "provided_row_inputs": provided_row_inputs,
                "blockers": [
                    str(item) for item in component.get("blockers", []) if str(item)
                ],
                "criteria": requirement_rows,
            }
        )
    return completion_rows


def _science_completion_audit(
    *,
    components: list[dict[str, Any]],
    requirements: list[dict[str, Any]],
    row_closure_matrix: list[dict[str, Any]],
    missing_row_inputs: list[str],
    blockers: list[str],
    upstream_source_blockers: list[str],
    requirement_summary: dict[str, Any],
) -> dict[str, Any]:
    component_audits = _component_completion_audits(
        components,
        requirements,
        row_closure_matrix,
    )
    complete_component_ids = [
        row["component_id"] for row in component_audits if row["status"] == "complete"
    ]
    blocked_component_ids = [
        row["component_id"] for row in component_audits if row["status"] != "complete"
    ]
    actual_closure_ready = (
        bool(requirement_summary.get("actual_closure_ready"))
        and not blockers
        and not upstream_source_blockers
    )
    return {
        "status": "complete" if actual_closure_ready else "operator_evidence_required",
        "actual_closure_ready": actual_closure_ready,
        "complete_component_count": len(complete_component_ids),
        "required_component_count": len(component_audits),
        "complete_component_ids": complete_component_ids,
        "blocked_component_ids": blocked_component_ids,
        "missing_row_inputs": missing_row_inputs,
        "missing_row_input_count": len(missing_row_inputs),
        "requirement_pass_count": int(
            requirement_summary.get("passing_requirement_count") or 0
        ),
        "requirement_count": int(requirement_summary.get("requirement_count") or 0),
        "blocker_count": len(blockers),
        "upstream_source_blocker_count": len(upstream_source_blockers),
        "component_audits": component_audits,
        "claim_boundary": (
            "This completion audit summarizes already-materialized requirement rows "
            "and row-input resolution only; it does not promote missing operator "
            "rows, proxy rows, or source-acquisition plans into actual closure."
        ),
    }


def _attach_component_requirement_summaries(
    components: list[dict[str, Any]],
    requirements: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for component in components:
        component_id = str(component.get("component_id") or "")
        component_requirements = [
            row
            for row in requirements
            if str(row.get("component_id") or "") == component_id
        ]
        enriched.append(
            {
                **component,
                "actual_closure_ready": bool(component_requirements)
                and all(bool(row.get("pass")) for row in component_requirements),
                "failed_criteria": [
                    str(row.get("criterion_id") or "")
                    for row in component_requirements
                    if not bool(row.get("pass"))
                ],
                "requirement_summary": _component_requirement_summary(
                    requirements,
                    component_id=component_id,
                ),
            }
        )
    return enriched


def _criteria_for_component(
    requirements: list[dict[str, Any]],
    *,
    component_id: str,
) -> list[str]:
    return [
        str(row.get("criterion_id") or "")
        for row in requirements
        if str(row.get("component_id") or "") == component_id
        and str(row.get("criterion_id") or "")
    ]


def _public_row_closure_rows(public: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in public.get("phase2_row_closure_matrix", []):
        if not isinstance(row, dict):
            continue
        row_input_id = str(row.get("row_input_id") or "")
        phase2_blockers = [
            str(item) for item in row.get("operator_blockers_if_missing", []) if str(item)
        ]
        rows.append(
            {
                **row,
                "actual_closure_component_id": PUBLIC_BENCHMARK_COMPONENT_ID,
                "expected_rows_mode": "operator_attached_public_benchmark_rows",
                "closes_actual_closure_criteria": [
                    str(item)
                    for item in row.get("closes_phase2_criteria", [])
                    if str(item)
                ],
                "phase2_operator_blockers_if_missing": phase2_blockers,
                "operator_blockers_if_missing": [
                    f"{PUBLIC_BENCHMARK_COMPONENT_ID}::{blocker}"
                    for blocker in phase2_blockers
                ],
                "row_contract_ref": f"row_intake_contracts.{row_input_id}",
            }
        )
    return rows


def _science_row_closure_matrix(
    *,
    public: dict[str, Any],
    row_input_resolution: dict[str, dict[str, Any]],
    row_intake_contracts: dict[str, Any],
    actual_closure_requirements: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows = _public_row_closure_rows(public)
    component_specs = [
        (
            "gpcr_rows",
            GPCR_COMPONENT_ID,
            "GPCR hard-decoy raw ranking rows",
            "raw_hard_decoy_rows",
            [
                "materialize_gpcr_hard_decoy_operator_template_from_rows",
                "materialize_gpcr_hard_decoy_suite_report",
                "build_gpcr_evidence_surface",
            ],
        ),
        (
            "pocketmd_rows",
            POCKETMD_COMPONENT_ID,
            "PocketMD Lite top-k refinement rows",
            "raw_top_k_refinement_rows",
            [
                "materialize_pocketmd_lite_operator_intake_from_rows",
                "materialize_pocketmd_lite_topk_survival_report",
                "build_pocketmd_lite_science_product_surface",
            ],
        ),
    ]
    for (
        row_input_id,
        component_id,
        description,
        expected_rows_mode,
        materialization_chain,
    ) in component_specs:
        resolution = row_input_resolution.get(row_input_id, {})
        if not isinstance(resolution, dict):
            resolution = {}
        contract = row_intake_contracts.get(row_input_id, {})
        if not isinstance(contract, dict):
            contract = {}
        missing = bool(resolution.get("missing"))
        criteria = _criteria_for_component(
            actual_closure_requirements,
            component_id=component_id,
        )
        rows.append(
            {
                "row_input_id": row_input_id,
                "description": description,
                "status": "missing" if missing else "provided",
                "missing": missing,
                "provided_path": str(resolution.get("resolved_path") or ""),
                "resolved_path": str(resolution.get("resolved_path") or ""),
                "auto_detected": bool(resolution.get("auto_detected")),
                "default_row_path_candidates": list(
                    contract.get("default_row_path_candidates")
                    or _candidate_path_strings(row_input_id)
                ),
                "accepted_formats": list(contract.get("accepted_formats") or []),
                "actual_closure_component_id": component_id,
                "expected_rows_mode": expected_rows_mode,
                "closes_actual_closure_criteria": criteria,
                "materialization_chain": materialization_chain,
                "row_contract_ref": f"row_intake_contracts.{row_input_id}",
                "operator_blockers_if_missing": [
                    f"{component_id}::{row_input_id}_not_provided"
                ],
                "claim_boundary": (
                    "This row documents which science closure criteria a real "
                    "operator-attached row file can unblock; it is not evidence by "
                    "itself."
                ),
            }
        )
    return rows


def _operator_next_actions(
    *,
    missing_row_inputs: list[str],
    contract_pass: bool,
    blockers: list[str],
    upstream_source_blockers: list[str],
) -> list[str]:
    if contract_pass:
        return [
            "review_ready_science_actual_closure_row_audit",
            "refresh_release_freshness_after_science_closure",
        ]
    attach_actions = [f"attach_{row_input_id}" for row_input_id in missing_row_inputs]
    source_actions = []
    if (
        "vina_gnina_rows" in missing_row_inputs
        and any(
            blocker.startswith("public_benchmark_phase2_source_acquisition::")
            for blocker in upstream_source_blockers
        )
    ):
        source_actions.append(
            "resolve_public_benchmark_phase2_source_acquisition_blockers"
        )
    if (
        "pocketmd_rows" in missing_row_inputs
        and any(
            blocker.startswith("pocketmd_lite_source_acquisition::")
            for blocker in upstream_source_blockers
        )
    ):
        source_actions.append("resolve_pocketmd_lite_source_acquisition_blockers")
    follow_up_actions = [
        "run_science_actual_closure_row_materializer",
        "review_science_actual_closure_row_audit",
    ]
    if blockers and not missing_row_inputs:
        follow_up_actions.insert(0, "resolve_science_actual_closure_row_blockers")
    return attach_actions + source_actions + follow_up_actions


def _comma_join(values: list[Any]) -> str:
    rendered = [str(value) for value in values if str(value)]
    return ", ".join(rendered) if rendered else "none"


def _markdown(payload: dict[str, Any]) -> str:
    summary = payload.get("summary")
    if not isinstance(summary, dict):
        summary = {}
    completion_audit = payload.get("completion_audit")
    if not isinstance(completion_audit, dict):
        completion_audit = {}
    missing_row_inputs = [
        str(item) for item in payload.get("missing_row_inputs", []) if str(item)
    ]
    upstream_source_blockers = [
        str(item) for item in payload.get("upstream_source_blockers", []) if str(item)
    ]
    lines = [
        "# Science Actual Closure Row Audit",
        "",
        f"- `status`: `{payload.get('status', '')}`",
        f"- `contract_pass`: `{payload.get('contract_pass', False)}`",
        f"- `component_ready_count`: `{payload.get('component_ready_count', 0)}/{payload.get('component_count', 0)}`",
        f"- `requirement_pass_count`: `{summary.get('passing_requirement_count', 0)}/{summary.get('requirement_count', 0)}`",
        f"- `completion_audit_status`: `{completion_audit.get('status', '')}`",
        f"- `missing_row_inputs`: `{_comma_join(missing_row_inputs)}`",
        f"- `upstream_source_blockers`: `{_comma_join(upstream_source_blockers)}`",
        "",
        "| Completion Component | Status | Requirements | Missing Row Inputs | Failed Criteria |",
        "|---|---|---|---|---|",
    ]
    for component in completion_audit.get("component_audits", []):
        if not isinstance(component, dict):
            continue
        lines.append(
            "| "
            f"`{component.get('component_id', '')}` | "
            f"`{component.get('status', '')}` | "
            f"`{component.get('requirement_pass_count', 0)}/{component.get('requirement_count', 0)}` | "
            f"`{_comma_join(component.get('missing_row_inputs', []))}` | "
            f"`{_comma_join(component.get('failed_criteria', []))}` |"
        )
    lines.extend(
        [
        "",
        "| Row Input | Status | Component | Closes Criteria | Default Path |",
        "|---|---|---|---|---|",
        ]
    )
    for row in payload.get("row_closure_matrix", []):
        if not isinstance(row, dict):
            continue
        default_paths = row.get("default_row_path_candidates")
        default_path = ""
        if isinstance(default_paths, list) and default_paths:
            default_path = str(default_paths[0])
        lines.append(
            "| "
            f"`{row.get('row_input_id', '')}` | "
            f"`{row.get('status', '')}` | "
            f"`{row.get('actual_closure_component_id', '')}` | "
            f"`{_comma_join(row.get('closes_actual_closure_criteria', []))}` | "
            f"`{default_path}` |"
        )
    lines.extend(
        [
            "",
            "| Component | Status | Failed Criteria | Blocker Count |",
            "|---|---|---|---|",
        ]
    )
    for component in payload.get("components", []):
        if not isinstance(component, dict):
            continue
        requirement_summary = component.get("requirement_summary")
        if not isinstance(requirement_summary, dict):
            requirement_summary = {}
        lines.append(
            "| "
            f"`{component.get('component_id', '')}` | "
            f"`{component.get('status', '')}` | "
            f"`{_comma_join(component.get('failed_criteria', []))}` | "
            f"`{requirement_summary.get('blocker_count', len(component.get('blockers', [])))}` |"
        )
    next_actions = [str(item) for item in payload.get("operator_next_actions", [])]
    lines.extend(
        [
            "",
            f"- `operator_next_actions`: `{_comma_join(next_actions)}`",
            "",
            str(payload.get("claim_boundary", "")),
            "",
        ]
    )
    return "\n".join(lines)


def _resolve_out_md(out: Path, out_md: Path | None) -> Path:
    return out.with_suffix(".md") if out_md is None else out_md


def _materialize_public_benchmark(
    *,
    subset_rows_path: Path | None,
    pose_rows_path: Path | None,
    enrichment_rows_path: Path | None,
    vina_gnina_rows_path: Path | None,
    repo_root: Path,
    audit_out: Path,
    operator_bundle_out: Path,
    out_dir: Path,
    harness_report_out: Path,
    artifact_bundle_out: Path,
    target_subset_case_count: int | None,
) -> dict[str, Any]:
    try:
        audit = public_phase2.build_public_benchmark_phase2_row_audit(
            repo_root=repo_root,
            subset_rows_path=subset_rows_path,
            pose_rows_path=pose_rows_path,
            enrichment_rows_path=enrichment_rows_path,
            vina_gnina_rows_path=vina_gnina_rows_path,
            target_subset_case_count=target_subset_case_count,
            operator_bundle_out=operator_bundle_out,
            out_dir=out_dir,
            harness_report_out=harness_report_out,
            artifact_bundle_out=artifact_bundle_out,
        )
        _write_json(repo_root, audit_out, audit)
    except Exception as exc:
        return _component_error(
            PUBLIC_BENCHMARK_COMPONENT_ID,
            exc,
            "operator_attached_public_benchmark_rows",
        )

    phase2_exit_gate = audit.get("phase2_exit_gate")
    if not isinstance(phase2_exit_gate, dict):
        phase2_exit_gate = {}
    blockers = [str(item) for item in audit.get("blockers", []) if str(item)]
    return {
        "component_id": PUBLIC_BENCHMARK_COMPONENT_ID,
        "status": str(audit.get("status") or ""),
        "contract_pass": bool(audit.get("contract_pass")),
        "materialized": bool(audit.get("phase2_ready")),
        "expected_rows_mode": "operator_attached_public_benchmark_rows",
        "phase2_ready": bool(audit.get("phase2_ready")),
        "phase2_exit_gate_status": str(phase2_exit_gate.get("status") or ""),
        "phase2_exit_gate_criteria": [
            row for row in phase2_exit_gate.get("criteria", []) if isinstance(row, dict)
        ],
        "phase2_failed_criteria": [
            str(item) for item in phase2_exit_gate.get("failed_criteria", [])
        ],
        "phase2_requirements": [
            row for row in audit.get("phase2_requirements", []) if isinstance(row, dict)
        ],
        "phase2_requirement_summary": dict(
            audit.get("phase2_requirement_summary") or {}
        ),
        "phase2_row_closure_matrix": [
            row
            for row in audit.get("phase2_row_closure_matrix", [])
            if isinstance(row, dict)
        ],
        "phase2_row_closure_matrix_count": int(
            audit.get("phase2_row_closure_matrix_count") or 0
        ),
        "missing_row_inputs": [
            str(item) for item in audit.get("missing_row_inputs", []) if str(item)
        ],
        "blockers": blockers,
        "outputs": {
            "phase2_row_audit": str(audit_out),
            **(
                dict(audit.get("outputs") or {})
                if isinstance(audit.get("outputs"), dict)
                else {}
            ),
        },
    }


def _component_error(component_id: str, exc: Exception, expected_mode: str) -> dict[str, Any]:
    return {
        "component_id": component_id,
        "status": "blocked",
        "contract_pass": False,
        "materialized": False,
        "blockers": [f"{component_id}_materialization_failed:{exc}"],
        "expected_rows_mode": expected_mode,
        "outputs": {},
    }


def _source_receipt_with_existing_defaults(
    *,
    repo_root: Path,
    artifact_path: Path,
    source_id: str,
    source_url: str,
    source_license: str,
    source_version: str,
) -> dict[str, str]:
    existing = _load_optional_json(repo_root, artifact_path)
    existing_source = existing.get("operator_input_source")
    if not isinstance(existing_source, dict):
        existing_source = {}
    return {
        "source_id": source_id or str(existing_source.get("source_id") or ""),
        "source_url": source_url or str(existing_source.get("source_url") or ""),
        "source_license": source_license
        or str(existing_source.get("source_license") or ""),
        "source_version": source_version
        or str(existing_source.get("source_version") or ""),
    }


def _materialize_gpcr(
    *,
    rows_path: Path | None,
    repo_root: Path,
    template_out: Path,
    report_out: Path,
    surface_out: Path,
    source_id: str,
    source_url: str,
    source_license: str,
    source_version: str,
) -> dict[str, Any]:
    if rows_path is None:
        return _missing_component(
            GPCR_COMPONENT_ID,
            "gpcr_hard_decoy_rows_not_provided",
            "raw_hard_decoy_rows",
        )
    try:
        source_receipt = _source_receipt_with_existing_defaults(
            repo_root=repo_root,
            artifact_path=template_out,
            source_id=source_id,
            source_url=source_url,
            source_license=source_license,
            source_version=source_version,
        )
        template = gpcr_rows.build_gpcr_hard_decoy_operator_template_from_rows(
            rows_path=rows_path,
            repo_root=repo_root,
            source_id=source_receipt["source_id"],
            source_url=source_receipt["source_url"],
            source_license=source_receipt["source_license"],
            source_version=source_receipt["source_version"],
        )
        _write_json(repo_root, template_out, template)
        report = gpcr_suite.materialize_gpcr_hard_decoy_suite_report(
            template,
            repo_root=repo_root,
            intake_path=template_out,
        )
        _write_json(repo_root, report_out, report)
        surface = gpcr_suite.build_gpcr_evidence_surface(
            report,
            report_path=report_out,
            repo_root=repo_root,
        )
        _write_json(repo_root, surface_out, surface)
    except Exception as exc:
        return _component_error(
            GPCR_COMPONENT_ID,
            exc,
            "raw_hard_decoy_rows",
        )

    phase3_exit_gate = report.get("phase3_exit_gate")
    if not isinstance(phase3_exit_gate, dict):
        phase3_exit_gate = {}
    blockers = [str(item) for item in report.get("blockers", []) if str(item)]
    return {
        "component_id": "gpcr_hard_decoy_actual_closure",
        "status": str(report.get("status") or ""),
        "contract_pass": bool(report.get("contract_pass")),
        "materialized": True,
        "expected_rows_mode": "raw_hard_decoy_rows",
        "rows_path": str(rows_path),
        "target_pass_count": int(report.get("target_pass_count") or 0),
        "target_count": int(report.get("target_count") or 0),
        "phase3_exit_gate_status": str(phase3_exit_gate.get("status") or ""),
        "phase3_exit_gate_criteria": [
            row for row in phase3_exit_gate.get("criteria", []) if isinstance(row, dict)
        ],
        "phase3_failed_criteria": [
            str(item) for item in phase3_exit_gate.get("failed_criteria", [])
        ],
        "blockers": blockers,
        "outputs": {
            "operator_template": str(template_out),
            "suite_report": str(report_out),
            "evidence_surface": str(surface_out),
        },
    }


def _materialize_pocketmd(
    *,
    rows_path: Path | None,
    repo_root: Path,
    intake_out: Path,
    report_out: Path,
    surface_out: Path,
    contract_path: Path,
    source_id: str,
    source_url: str,
    source_license: str,
    source_version: str,
    max_top_k: int,
) -> dict[str, Any]:
    if rows_path is None:
        return _missing_component(
            POCKETMD_COMPONENT_ID,
            "pocketmd_lite_topk_rows_not_provided",
            "raw_top_k_refinement_rows",
        )
    try:
        intake = pocketmd_rows.build_pocketmd_lite_operator_intake_from_rows(
            rows_path=rows_path,
            repo_root=repo_root,
            source_id=source_id,
            source_url=source_url,
            source_license=source_license,
            source_version=source_version,
            max_top_k=max_top_k,
        )
        _write_json(repo_root, intake_out, intake)
        contract = _load_optional_json(repo_root, contract_path)
        resolved_contract = _resolve(repo_root, contract_path)
        report = pocketmd_survival.materialize_pocketmd_lite_topk_survival_report(
            intake,
            contract=contract,
            repo_root=repo_root,
            intake_path=intake_out,
            contract_path=contract_path if resolved_contract.exists() else None,
        )
        _write_json(repo_root, report_out, report)
        surface = pocketmd_survival.build_pocketmd_lite_science_product_surface(
            report,
            contract=contract,
            report_path=report_out,
            contract_path=contract_path if resolved_contract.exists() else None,
            repo_root=repo_root,
        )
        _write_json(repo_root, surface_out, surface)
    except Exception as exc:
        return _component_error(
            POCKETMD_COMPONENT_ID,
            exc,
            "raw_top_k_refinement_rows",
        )

    phase4_exit_gate = report.get("phase4_exit_gate")
    if not isinstance(phase4_exit_gate, dict):
        phase4_exit_gate = {}
    blockers = [str(item) for item in report.get("blockers", []) if str(item)]
    return {
        "component_id": "pocketmd_lite_topk_actual_closure",
        "status": str(report.get("status") or ""),
        "contract_pass": bool(report.get("contract_pass")),
        "materialized": True,
        "expected_rows_mode": "raw_top_k_refinement_rows",
        "rows_path": str(rows_path),
        "real_refinement_case_count": int(report.get("real_refinement_case_count") or 0),
        "top_k_candidate_count": int(report.get("top_k_candidate_count") or 0),
        "phase4_exit_gate_status": str(phase4_exit_gate.get("status") or ""),
        "phase4_exit_gate_criteria": [
            row for row in phase4_exit_gate.get("criteria", []) if isinstance(row, dict)
        ],
        "phase4_failed_criteria": [
            str(item) for item in phase4_exit_gate.get("failed_criteria", [])
        ],
        "blockers": blockers,
        "outputs": {
            "operator_intake": str(intake_out),
            "topk_survival_report": str(report_out),
            "science_surface": str(surface_out),
        },
    }


def build_science_actual_closure_audit(
    *,
    repo_root: Path = ROOT,
    subset_rows_path: Path | None = None,
    pose_rows_path: Path | None = None,
    enrichment_rows_path: Path | None = None,
    vina_gnina_rows_path: Path | None = None,
    public_phase2_audit_out: Path = DEFAULT_PUBLIC_PHASE2_AUDIT,
    public_operator_bundle_out: Path = public_phase2.DEFAULT_OPERATOR_BUNDLE_OUT,
    public_out_dir: Path = public_phase2.DEFAULT_OUT_DIR,
    public_harness_report_out: Path = public_phase2.DEFAULT_HARNESS_REPORT_OUT,
    public_artifact_bundle_out: Path = public_phase2.DEFAULT_ARTIFACT_BUNDLE_OUT,
    public_target_subset_case_count: int | None = None,
    gpcr_rows_path: Path | None = None,
    pocketmd_rows_path: Path | None = None,
    gpcr_template_out: Path = DEFAULT_GPCR_TEMPLATE,
    gpcr_report_out: Path = DEFAULT_GPCR_REPORT,
    gpcr_surface_out: Path = DEFAULT_GPCR_SURFACE,
    pocketmd_intake_out: Path = DEFAULT_POCKETMD_INTAKE,
    pocketmd_report_out: Path = DEFAULT_POCKETMD_REPORT,
    pocketmd_surface_out: Path = DEFAULT_POCKETMD_SURFACE,
    pocketmd_contract_path: Path = DEFAULT_POCKETMD_CONTRACT,
    source_id: str = "",
    source_url: str = "",
    source_license: str = "",
    source_version: str = "",
    pocketmd_max_top_k: int = pocketmd_rows.DEFAULT_MAX_TOP_K,
) -> dict[str, Any]:
    subset_rows_path, subset_row_resolution = _resolve_row_input(
        repo_root=repo_root,
        row_input_id="subset_rows",
        explicit_path=subset_rows_path,
    )
    pose_rows_path, pose_row_resolution = _resolve_row_input(
        repo_root=repo_root,
        row_input_id="pose_rows",
        explicit_path=pose_rows_path,
    )
    enrichment_rows_path, enrichment_row_resolution = _resolve_row_input(
        repo_root=repo_root,
        row_input_id="enrichment_rows",
        explicit_path=enrichment_rows_path,
    )
    vina_gnina_rows_path, vina_gnina_row_resolution = _resolve_row_input(
        repo_root=repo_root,
        row_input_id="vina_gnina_rows",
        explicit_path=vina_gnina_rows_path,
    )
    gpcr_rows_path, gpcr_row_resolution = _resolve_row_input(
        repo_root=repo_root,
        row_input_id="gpcr_rows",
        explicit_path=gpcr_rows_path,
    )
    pocketmd_rows_path, pocketmd_row_resolution = _resolve_row_input(
        repo_root=repo_root,
        row_input_id="pocketmd_rows",
        explicit_path=pocketmd_rows_path,
    )
    row_input_resolution = {
        "subset_rows": subset_row_resolution,
        "pose_rows": pose_row_resolution,
        "enrichment_rows": enrichment_row_resolution,
        "vina_gnina_rows": vina_gnina_row_resolution,
        "gpcr_rows": gpcr_row_resolution,
        "pocketmd_rows": pocketmd_row_resolution,
    }
    upstream_source_acquisition = _upstream_source_acquisition_context(repo_root)
    upstream_source_blockers = _upstream_source_blockers(upstream_source_acquisition)
    public = _materialize_public_benchmark(
        subset_rows_path=None
        if subset_row_resolution.get("auto_detected")
        else subset_rows_path,
        pose_rows_path=None if pose_row_resolution.get("auto_detected") else pose_rows_path,
        enrichment_rows_path=None
        if enrichment_row_resolution.get("auto_detected")
        else enrichment_rows_path,
        vina_gnina_rows_path=None
        if vina_gnina_row_resolution.get("auto_detected")
        else vina_gnina_rows_path,
        repo_root=repo_root,
        audit_out=public_phase2_audit_out,
        operator_bundle_out=public_operator_bundle_out,
        out_dir=public_out_dir,
        harness_report_out=public_harness_report_out,
        artifact_bundle_out=public_artifact_bundle_out,
        target_subset_case_count=public_target_subset_case_count,
    )
    public_audit = _load_optional_json(repo_root, public_phase2_audit_out)
    public_row_intake_contracts = public_audit.get("row_intake_contracts")
    if not isinstance(public_row_intake_contracts, dict):
        public_row_intake_contracts = {}
    row_intake_contracts = {
        **public_row_intake_contracts,
        "gpcr_rows": _gpcr_row_intake_contract(
            template_out=gpcr_template_out,
            report_out=gpcr_report_out,
            surface_out=gpcr_surface_out,
        ),
        "pocketmd_rows": _pocketmd_row_intake_contract(
            intake_out=pocketmd_intake_out,
            report_out=pocketmd_report_out,
            surface_out=pocketmd_surface_out,
            contract_path=pocketmd_contract_path,
            max_top_k=pocketmd_max_top_k,
        ),
    }
    gpcr = _materialize_gpcr(
        rows_path=gpcr_rows_path,
        repo_root=repo_root,
        template_out=gpcr_template_out,
        report_out=gpcr_report_out,
        surface_out=gpcr_surface_out,
        source_id=source_id,
        source_url=source_url,
        source_license=source_license,
        source_version=source_version,
    )
    pocketmd = _materialize_pocketmd(
        rows_path=pocketmd_rows_path,
        repo_root=repo_root,
        intake_out=pocketmd_intake_out,
        report_out=pocketmd_report_out,
        surface_out=pocketmd_surface_out,
        contract_path=pocketmd_contract_path,
        source_id=source_id,
        source_url=source_url,
        source_license=source_license,
        source_version=source_version,
        max_top_k=pocketmd_max_top_k,
    )
    components = [public, gpcr, pocketmd]
    missing_row_inputs = [
        row_input_id
        for row_input_id, rows_path in (
            ("subset_rows", subset_rows_path),
            ("pose_rows", pose_rows_path),
            ("enrichment_rows", enrichment_rows_path),
            ("vina_gnina_rows", vina_gnina_rows_path),
            ("gpcr_rows", gpcr_rows_path),
            ("pocketmd_rows", pocketmd_rows_path),
        )
        if rows_path is None
    ]
    actual_closure_requirements = _actual_closure_requirements(components)
    components = _attach_component_requirement_summaries(
        components,
        actual_closure_requirements,
    )
    component_requirement_summaries = [
        component["requirement_summary"]
        for component in components
        if isinstance(component.get("requirement_summary"), dict)
    ]
    requirement_summary = _actual_closure_requirement_summary(
        actual_closure_requirements,
        missing_row_inputs=missing_row_inputs,
    )
    blockers = [
        f"{component['component_id']}::{blocker}"
        for component in components
        for blocker in component.get("blockers", [])
    ]
    contract_pass = all(bool(component.get("contract_pass")) for component in components)
    row_closure_matrix = _science_row_closure_matrix(
        public=public,
        row_input_resolution=row_input_resolution,
        row_intake_contracts=row_intake_contracts,
        actual_closure_requirements=actual_closure_requirements,
    )
    completion_audit = _science_completion_audit(
        components=components,
        requirements=actual_closure_requirements,
        row_closure_matrix=row_closure_matrix,
        missing_row_inputs=missing_row_inputs,
        blockers=blockers,
        upstream_source_blockers=upstream_source_blockers,
        requirement_summary=requirement_summary,
    )
    operator_next_actions = _operator_next_actions(
        missing_row_inputs=missing_row_inputs,
        contract_pass=contract_pass,
        blockers=blockers,
        upstream_source_blockers=upstream_source_blockers,
    )
    input_paths = [
        Path("scripts/materialize_science_actual_closure_from_rows.py"),
        Path("scripts/materialize_public_benchmark_phase2_from_rows.py"),
        Path("scripts/materialize_public_benchmark_operator_bundle_from_rows.py"),
        Path("scripts/materialize_public_benchmark_harness_bundle.py"),
        Path("scripts/materialize_gpcr_hard_decoy_operator_template_from_rows.py"),
        Path("scripts/materialize_gpcr_hard_decoy_suite_report.py"),
        Path("scripts/materialize_pocketmd_lite_operator_intake_from_rows.py"),
        Path("scripts/materialize_pocketmd_lite_topk_survival_report.py"),
    ]
    for path in (
        subset_rows_path,
        pose_rows_path,
        enrichment_rows_path,
        vina_gnina_rows_path,
    ):
        if path is not None:
            input_paths.append(path)
    if gpcr_rows_path is not None:
        input_paths.append(gpcr_rows_path)
    if pocketmd_rows_path is not None:
        input_paths.append(pocketmd_rows_path)
    for path in (
        DEFAULT_PUBLIC_SOURCE_ACQUISITION_PLAN,
        DEFAULT_PUBLIC_SOURCE_ACCESS_PREFLIGHT_RECEIPT,
        DEFAULT_PUBLIC_EXTERNAL_RECEIPTS_VALIDATION,
        DEFAULT_POCKETMD_SOURCE_ACQUISITION_PLAN,
    ):
        if _resolve(repo_root, path).exists():
            input_paths.append(path)
    return {
        "schema_version": SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=input_paths,
            reused_evidence=False,
            reuse_policy="science_actual_closure_audit_from_operator_rows",
            repo_root=repo_root,
        ),
        "status": "ready" if contract_pass else "operator_evidence_required",
        "contract_pass": contract_pass,
        "blockers": blockers,
        "summary": {
            "component_count": len(components),
            "component_ready_count": sum(
                1 for component in components if component.get("contract_pass")
            ),
            "blocker_count": len(blockers),
            "upstream_source_context_count": sum(
                1
                for row in upstream_source_acquisition.values()
                if isinstance(row, dict) and row.get("present")
            ),
            "upstream_source_blocker_count": len(upstream_source_blockers),
            **requirement_summary,
        },
        "component_count": len(components),
        "component_ready_count": sum(1 for component in components if component.get("contract_pass")),
        "components": components,
        "missing_row_inputs": missing_row_inputs,
        "row_input_resolution": row_input_resolution,
        "row_intake_contracts": row_intake_contracts,
        "row_closure_matrix": row_closure_matrix,
        "row_closure_matrix_count": len(row_closure_matrix),
        "upstream_source_acquisition": upstream_source_acquisition,
        "upstream_source_blockers": upstream_source_blockers,
        "operator_next_actions": operator_next_actions,
        "component_requirement_summaries": component_requirement_summaries,
        "actual_closure_requirements": actual_closure_requirements,
        "actual_closure_requirement_summary": requirement_summary,
        "completion_audit": completion_audit,
        "required_actual_closures": [
            PUBLIC_BENCHMARK_COMPONENT_ID,
            GPCR_COMPONENT_ID,
            POCKETMD_COMPONENT_ID,
        ],
        "claim_boundary": (
            "This runner only materializes operator-attached raw rows through the "
            "existing Public Benchmark, GPCR, and PocketMD Lite materializers. It "
            "does not download benchmark data, generate docking scores, run MD, "
            "infer missing metrics, or treat fixture/proxy rows as actual science "
            "closure evidence."
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--subset-rows", type=Path)
    parser.add_argument("--pose-rows", type=Path)
    parser.add_argument("--enrichment-rows", type=Path)
    parser.add_argument("--vina-gnina-rows", type=Path)
    parser.add_argument("--public-phase2-audit-out", type=Path, default=DEFAULT_PUBLIC_PHASE2_AUDIT)
    parser.add_argument("--public-operator-bundle-out", type=Path, default=public_phase2.DEFAULT_OPERATOR_BUNDLE_OUT)
    parser.add_argument("--public-out-dir", type=Path, default=public_phase2.DEFAULT_OUT_DIR)
    parser.add_argument("--public-harness-report-out", type=Path, default=public_phase2.DEFAULT_HARNESS_REPORT_OUT)
    parser.add_argument("--public-artifact-bundle-out", type=Path, default=public_phase2.DEFAULT_ARTIFACT_BUNDLE_OUT)
    parser.add_argument("--public-target-subset-case-count", type=int)
    parser.add_argument("--gpcr-rows", type=Path)
    parser.add_argument("--pocketmd-rows", type=Path)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--out-md", type=Path)
    parser.add_argument("--gpcr-template-out", type=Path, default=DEFAULT_GPCR_TEMPLATE)
    parser.add_argument("--gpcr-report-out", type=Path, default=DEFAULT_GPCR_REPORT)
    parser.add_argument("--gpcr-surface-out", type=Path, default=DEFAULT_GPCR_SURFACE)
    parser.add_argument("--pocketmd-intake-out", type=Path, default=DEFAULT_POCKETMD_INTAKE)
    parser.add_argument("--pocketmd-report-out", type=Path, default=DEFAULT_POCKETMD_REPORT)
    parser.add_argument("--pocketmd-surface-out", type=Path, default=DEFAULT_POCKETMD_SURFACE)
    parser.add_argument("--pocketmd-contract", type=Path, default=DEFAULT_POCKETMD_CONTRACT)
    parser.add_argument("--source-id", default="")
    parser.add_argument("--source-url", default="")
    parser.add_argument("--source-license", default="")
    parser.add_argument("--source-version", default="")
    parser.add_argument("--pocketmd-max-top-k", type=int, default=pocketmd_rows.DEFAULT_MAX_TOP_K)
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_science_actual_closure_audit(
        repo_root=args.repo_root,
        subset_rows_path=args.subset_rows,
        pose_rows_path=args.pose_rows,
        enrichment_rows_path=args.enrichment_rows,
        vina_gnina_rows_path=args.vina_gnina_rows,
        public_phase2_audit_out=args.public_phase2_audit_out,
        public_operator_bundle_out=args.public_operator_bundle_out,
        public_out_dir=args.public_out_dir,
        public_harness_report_out=args.public_harness_report_out,
        public_artifact_bundle_out=args.public_artifact_bundle_out,
        public_target_subset_case_count=args.public_target_subset_case_count,
        gpcr_rows_path=args.gpcr_rows,
        pocketmd_rows_path=args.pocketmd_rows,
        gpcr_template_out=args.gpcr_template_out,
        gpcr_report_out=args.gpcr_report_out,
        gpcr_surface_out=args.gpcr_surface_out,
        pocketmd_intake_out=args.pocketmd_intake_out,
        pocketmd_report_out=args.pocketmd_report_out,
        pocketmd_surface_out=args.pocketmd_surface_out,
        pocketmd_contract_path=args.pocketmd_contract,
        source_id=args.source_id,
        source_url=args.source_url,
        source_license=args.source_license,
        source_version=args.source_version,
        pocketmd_max_top_k=args.pocketmd_max_top_k,
    )
    _write_json(args.repo_root, args.out, payload)
    out_md = _resolve_out_md(args.out, args.out_md)
    resolved_out_md = _resolve(args.repo_root, out_md)
    resolved_out_md.parent.mkdir(parents=True, exist_ok=True)
    resolved_out_md.write_text(_markdown(payload), encoding="utf-8")
    print(
        "science-actual-closure-row-audit: "
        f"{payload['status']} | ready={payload['component_ready_count']}/"
        f"{payload['component_count']} | blockers={len(payload['blockers'])}"
    )
    return 1 if args.fail_blocked and not payload["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
