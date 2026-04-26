#!/usr/bin/env python3
"""Build a latest external-validation bundle and one-page summary."""

from __future__ import annotations

import argparse
import copy
from collections import Counter
from datetime import datetime, timezone
import html
import json
from pathlib import Path
import shutil
import zipfile

import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import FancyBboxPatch

from design_optimization.artifacts import (
    ABLATION_REPORT_JSON,
    BUDGETED_REPORT_JSON,
    CANDIDATE_EXPLAIN_V2_CSV,
    CANDIDATE_EXPLAIN_V2_JSON,
    COST_REDUCTION_BLOCKED_ACTIONS_CSV,
    COST_REDUCTION_BLOCKED_ACTIONS_JSON,
    COST_REDUCTION_CHANGES_CSV,
    COST_REDUCTION_CHANGES_JSON,
    COST_REDUCTION_NO_GAIN_EXPLAIN_CSV,
    COST_REDUCTION_NO_GAIN_EXPLAIN_JSON,
    COST_REDUCTION_NO_GAIN_GROUPS_CSV,
    COST_REDUCTION_NO_GAIN_GROUPS_JSON,
    COST_REDUCTION_REPORT_JSON,
    EXTERNAL_FULL_ARTIFACTS_DESIGN_OPT,
    EXTERNAL_LIGHT_ARTIFACTS_DESIGN_OPT,
    OBJECTIVE_PROFILE_REPORT_JSON,
    PBD_REVIEW_DIR,
    REJECTED_CANDIDATE_EXPLAIN_V2_CSV,
    REJECTED_CANDIDATE_EXPLAIN_V2_JSON,
    SOLVER_LOOP_LONG_REPORT_JSON,
    SOLVER_LOOP_LONG_STATE_NPZ,
    STAGE_A_REPORT_JSON,
    STAGE_B_REPORT_JSON,
    STAGE_C_REPORT_JSON,
)
from design_optimization.entrypoint_appendix import (
    annotate_entrypoint_groups,
    render_entrypoint_html_detail_sections,
    render_entrypoint_markdown_sections,
)
from design_optimization.io import entrypoint_group_rows, entrypoint_status_rows, load_design_opt_reports
from implementation.phase1.generate_midas_native_writeback_diff_receipts import (
    _render_exact_topology_structural_preview_promotion_queue_markdown,
)
from implementation.phase1.pdf_rendering import configure_matplotlib_cjk_pdf, finalize_pdf_figure
from implementation.phase1.ui_design_tokens import build_signal_desk_light_css

REPO_ROOT = Path(__file__).resolve().parents[2]

CONSTITUTIVE_INTERACTION_NOTE = (
    "expanded constitutive/interaction families are surfaced explicitly as shared summary lines across the "
    "release, committee, and external reports; the same lines are reused as-is."
)

ROW_PROVENANCE_SYNC_NOTE = (
    "the Review surface and row-provenance appendix stay bidirectionally aligned on the same Hazard and Rule Family slices; "
    "the appendix exposes explicit viewer_row_url and viewer_slice_url reverse-sync links back to the matching viewer row and slice."
)

EXTERNAL_CASE_COVER_TITLE = "Reviewer / Authority Cover Sheet"
EXTERNAL_CASE_COVER_NOTE = "Auto-generated from the execution status manifest and KPI receipt."
EXTERNAL_CASE_COVER_INSTRUCTION = "Review this cover sheet first, then the KPI receipt and shared appendices."
EXTERNAL_CASE_COVER_DISCLAIMER = "Generated placeholder slots only; no live reviewer approval is implied."
EXTERNAL_CASE_ATTESTATION_MANIFEST_DIRNAME = "case_onepage_attestation_manifests"
EXTERNAL_CASE_ATTESTATION_TEMPLATE_DIRNAME = "case_onepage_attestation_templates"
EXTERNAL_CASE_ATTESTATION_RECEIPT_DIRNAME = "case_onepage_attestation_receipts"
EXTERNAL_CASE_ATTESTATION_INDEX_JSON = "case_onepage_attestation_index.json"
EXTERNAL_CASE_ATTESTATION_INDEX_MD = "case_onepage_attestation_index.md"
EXTERNAL_CASE_ATTESTATION_STATUS_TEMPLATE_PENDING = "TEMPLATE_PENDING_REAL_REVIEW"
EXTERNAL_CASE_ATTESTATION_STATUS_MANIFEST_INVALID = "MANIFEST_INVALID_JSON"
EXTERNAL_CASE_ATTESTATION_STATUS_MANIFEST_INCOMPLETE = "MANIFEST_INCOMPLETE"
EXTERNAL_CASE_ATTESTATION_STATUS_REVIEWER_ATTESTED = (
    "MANIFEST_REVIEWER_ATTESTED_PENDING_AUTHORITY_RECEIPT"
)
EXTERNAL_CASE_ATTESTATION_STATUS_COMPLETE = "MANIFEST_ATTESTED_AND_AUTHORITY_RECEIPTED"

EXTERNAL_BUNDLE_SCRUBBED_ARTIFACT_BASENAMES = {
    "irregular_structure_collection_gate_report.json",
    "irregular_structure_source_catalog.json",
    "irregular_structure_triage_report.json",
    "irregular_structure_collection_report.json",
    "irregular_top5_execution_manifest.json",
}
EXTERNAL_BUNDLE_SCRUBBED_ARTIFACT_KEYS = {
    "irregular_structure_gate_report_json",
    "irregular_structure_source_catalog_json",
    "irregular_structure_triage_report_json",
    "irregular_structure_collection_report_json",
    "irregular_top5_execution_manifest_json",
}
EXTERNAL_ONEPAGE_HIDDEN_IRREGULAR_FAMILY_IDS = {"transfer_podium_tower"}
EXTERNAL_CANONICAL_READINESS_NOTE_SHORT = (
    "Only unresolved bridged families are shown below."
)
EXTERNAL_KR_PROMOTION_NOTE_SHORT = (
    "No supported exact-topology archive candidates are pending right now. The queue reopens automatically "
    "when a new public archive decoded preview lands with exact_topology_candidate=true."
)
EXTERNAL_CASE_ATTESTATION_PLACEHOLDERS = {
    "reviewer_name": "PENDING_REAL_REVIEWER_NAME_FILL_CASE_ATTESTATION_MANIFEST",
    "reviewer_role_or_license": "PENDING_REAL_REVIEWER_ROLE_OR_LICENSE_FILL_CASE_ATTESTATION_MANIFEST",
    "reviewer_signature": "PENDING_REAL_REVIEWER_SIGNATURE_FILL_CASE_ATTESTATION_MANIFEST",
    "receipt_id": "PENDING_REAL_AUTHORITY_RECEIPT_ID_FILL_CASE_ATTESTATION_MANIFEST",
    "receipt_issued_at": "PENDING_REAL_AUTHORITY_RECEIPT_ISSUED_AT_FILL_CASE_ATTESTATION_MANIFEST",
    "authority_receipt": "PENDING_REAL_AUTHORITY_RECEIPT_FILL_CASE_ATTESTATION_MANIFEST",
    "approval_signature": "PENDING_REAL_APPROVAL_SIGNATURE_FILL_CASE_ATTESTATION_MANIFEST",
}
EXTERNAL_CASE_ATTESTATION_REVIEWER_REQUIRED_FIELDS = (
    "reviewer_name",
    "reviewer_license_id",
    "reviewer_signature_name",
    "decision_basis",
    "review_session_id",
    "attested_at_utc",
)
EXTERNAL_CASE_ATTESTATION_AUTHORITY_REQUIRED_FIELDS = (
    "authority_name",
    "authority_receipt_id",
    "authority_receipt_issued_at_utc",
    "approval_signature_name",
)


def _external_surface_text(value: object, default: str = "n/a") -> str:
    text = str(value or "").strip()
    return text or default


def _external_surface_status_chip_html(label: object, tone: str = "neutral") -> str:
    tone_class = {
        "ok": " is-ok",
        "warn": " is-warn",
        "danger": " is-danger",
        "accent": " is-accent",
    }.get(str(tone or "").strip().lower(), "")
    return (
        f"<span class='status-chip{tone_class}'>"
        f"{html.escape(_external_surface_text(label))}"
        "</span>"
    )


def _external_surface_check_chip_html(status: object) -> str:
    normalized = _external_surface_text(status)
    tone = "ok" if normalized.upper() == "PASS" else "warn"
    return _external_surface_status_chip_html(normalized, tone)


def _external_surface_bool_chip_html(
    value: object,
    *,
    true_label: str = "READY",
    false_label: str = "CHECK",
) -> str:
    return _external_surface_status_chip_html(
        true_label if bool(value) else false_label,
        "ok" if bool(value) else "warn",
    )


def _external_case_attestation_tone(status: object) -> str:
    normalized = _external_surface_text(status)
    if normalized == EXTERNAL_CASE_ATTESTATION_STATUS_COMPLETE:
        return "ok"
    if normalized == EXTERNAL_CASE_ATTESTATION_STATUS_REVIEWER_ATTESTED:
        return "accent"
    if normalized in {
        EXTERNAL_CASE_ATTESTATION_STATUS_TEMPLATE_PENDING,
        EXTERNAL_CASE_ATTESTATION_STATUS_MANIFEST_INCOMPLETE,
    }:
        return "warn"
    if normalized == EXTERNAL_CASE_ATTESTATION_STATUS_MANIFEST_INVALID:
        return "danger"
    return "neutral"

FULL_ARTIFACTS = [
    "implementation/phase1/release/nightly_release_gate_report.json",
    "implementation/phase1/ci_gate_report.json",
    "implementation/phase1/static_artifact_validation_report.json",
    "implementation/phase1/release/freeze_release_report.json",
    "implementation/phase1/release/release_candidate_promotion_report.json",
    "implementation/phase1/ndtha_long_profile_report.json",
    "implementation/phase1/ndtha_residual_gate_report.json",
    "implementation/phase1/nonlinear_ndtha_stress_report.response.npz",
    "implementation/phase1/nonlinear_frame_engine_report.metrics.npz",
    "implementation/phase1/wind_time_history_gate_report.metrics.npz",
    "implementation/phase1/ssi_boundary_gate_report.metrics.npz",
    "implementation/phase1/global_authority_gate_report.json",
    "implementation/phase1/global_authority_gate_report.metrics.npz",
    "implementation/phase1/nightly_10m_repro_report.json",
    "implementation/phase1/partitioned_scaleout_report.json",
    "implementation/phase1/scaleout_io_profile_report.json",
    "implementation/phase1/solver_hip_e2e_contract_report.json",
    "implementation/phase1/rc_benchmark_lock_report.json",
    "implementation/phase1/material_constitutive_gate_report.json",
    "implementation/phase1/surface_interaction_benchmark_gate_report.json",
    "implementation/phase1/release/kds_compliance/midas_kds_row_provenance_table.json",
    "implementation/phase1/release/kds_compliance/midas_kds_row_provenance_table.csv",
    "implementation/phase1/release/kds_compliance/midas_kds_row_provenance_table_report.json",
    "implementation/phase1/midas_native_roundtrip_gate_report.json",
    "implementation/phase1/open_data/midas/midas_native_corpus_manifest.json",
    "implementation/phase1/release/midas_native_roundtrip/midas_native_writeback_diff_receipts_report.json",
    "implementation/phase1/release/midas_native_roundtrip/unsupported_lossy_card_family_appendix.md",
    "implementation/phase1/release/midas_native_roundtrip/unsupported_lossy_card_family_appendix.json",
    "implementation/phase1/midas_mgt_conversion_report.json",
    "implementation/phase1/open_data/midas/quality_corpus_report.json",
    "implementation/phase1/open_data/midas/quality_mgt_source_catalog.json",
    "implementation/phase1/release/release_registry.json",
    "implementation/phase1/release/signing/release_registry_ed25519.pub.pem",
    "implementation/phase1/release/signing/release_registry.signature.b64",
    "implementation/phase1/release/version_lock_manifest.json",
    "implementation/phase1/release/release_gap_report.json",
    "implementation/phase1/release/release_gap_report.md",
    "implementation/phase1/release/committee_review/committee_review_package_report.json",
    "implementation/phase1/release/committee_review/committee_review_dashboard.html",
    "implementation/phase1/release/committee_review/committee_review_report.md",
    "implementation/phase1/release/committee_review/committee_review_report.pdf",
    "implementation/phase1/release/kds_compliance/kds_compliance_summary.json",
    "implementation/phase1/release/kds_compliance/kds_compliance_report.pdf",
    "implementation/phase1/release/pbd_review/pbd_review_package_report.json",
    "implementation/phase1/release/pbd_review/pbd_review_metrics.npz",
    "implementation/phase1/release/pbd_review/pbd_review_report.md",
    "implementation/phase1/release/pbd_review/pbd_review_report.pdf",
    "implementation/phase1/release/midas_native_roundtrip/unsupported_lossy_card_family_appendix.md",
    "implementation/phase1/release/midas_native_roundtrip/unsupported_lossy_card_family_appendix.json",
    "implementation/phase1/release/midas_native_roundtrip/bridge.diff_batch.md",
    "implementation/phase1/release/midas_native_roundtrip/building.diff_batch.md",
    "implementation/phase1/release/midas_native_roundtrip/beam.diff_batch.md",
    "implementation/phase1/release/midas_native_roundtrip/foundation.diff_batch.md",
    "implementation/phase1/release/midas_native_roundtrip/ramp.diff_batch.md",
    "implementation/phase1/release/midas_native_roundtrip/stair.diff_batch.md",
    "implementation/phase1/irregular_structure_collection_gate_report.json",
    "implementation/phase1/open_data/irregular/irregular_structure_source_catalog.json",
    "implementation/phase1/open_data/irregular/irregular_structure_triage_report.json",
    "implementation/phase1/open_data/irregular/irregular_structure_collection_report.json",
    "implementation/phase1/open_data/irregular/irregular_top5_execution_manifest.json",
    "implementation/phase1/release/external_benchmark_kickoff/irregular_benchmark_execution_manifest.json",
    "implementation/phase1/release/external_benchmark_kickoff/irregular_benchmark_execution_manifest.md",
] + EXTERNAL_FULL_ARTIFACTS_DESIGN_OPT

LIGHTWEIGHT_ARTIFACTS = [
    "implementation/phase1/release/nightly_release_gate_report.json",
    "implementation/phase1/ci_gate_report.json",
    "implementation/phase1/static_artifact_validation_report.json",
    "implementation/phase1/release/freeze_release_report.json",
    "implementation/phase1/release/release_candidate_promotion_report.json",
    "implementation/phase1/ndtha_residual_gate_report.json",
    "implementation/phase1/nonlinear_ndtha_stress_report.response.npz",
    "implementation/phase1/nonlinear_frame_engine_report.metrics.npz",
    "implementation/phase1/wind_time_history_gate_report.metrics.npz",
    "implementation/phase1/ssi_boundary_gate_report.metrics.npz",
    "implementation/phase1/global_authority_gate_report.json",
    "implementation/phase1/global_authority_gate_report.metrics.npz",
    "implementation/phase1/solver_hip_e2e_contract_report.json",
    "implementation/phase1/rc_benchmark_lock_report.json",
    "implementation/phase1/material_constitutive_gate_report.json",
    "implementation/phase1/surface_interaction_benchmark_gate_report.json",
    "implementation/phase1/release/kds_compliance/midas_kds_row_provenance_table.json",
    "implementation/phase1/release/kds_compliance/midas_kds_row_provenance_table.csv",
    "implementation/phase1/release/kds_compliance/midas_kds_row_provenance_table_report.json",
    "implementation/phase1/midas_native_roundtrip_gate_report.json",
    "implementation/phase1/open_data/midas/midas_native_corpus_manifest.json",
    "implementation/phase1/release/midas_native_roundtrip/midas_native_writeback_diff_receipts_report.json",
    "implementation/phase1/release/midas_native_roundtrip/unsupported_lossy_card_family_appendix.md",
    "implementation/phase1/release/midas_native_roundtrip/unsupported_lossy_card_family_appendix.json",
    "implementation/phase1/midas_mgt_conversion_report.json",
    "implementation/phase1/release/release_registry.json",
    "implementation/phase1/release/signing/release_registry_ed25519.pub.pem",
    "implementation/phase1/release/signing/release_registry.signature.b64",
    "implementation/phase1/release/release_gap_report.json",
    "implementation/phase1/release/committee_review/committee_review_package_report.json",
    "implementation/phase1/release/committee_review/committee_review_report.pdf",
    "implementation/phase1/release/kds_compliance/kds_compliance_summary.json",
    "implementation/phase1/release/pbd_review/pbd_review_package_report.json",
    "implementation/phase1/release/pbd_review/pbd_review_metrics.npz",
    "implementation/phase1/release/midas_native_roundtrip/unsupported_lossy_card_family_appendix.md",
    "implementation/phase1/release/midas_native_roundtrip/unsupported_lossy_card_family_appendix.json",
    "implementation/phase1/release/midas_native_roundtrip/bridge.diff_batch.md",
    "implementation/phase1/release/midas_native_roundtrip/building.diff_batch.md",
    "implementation/phase1/release/midas_native_roundtrip/beam.diff_batch.md",
    "implementation/phase1/release/midas_native_roundtrip/foundation.diff_batch.md",
    "implementation/phase1/release/midas_native_roundtrip/ramp.diff_batch.md",
    "implementation/phase1/release/midas_native_roundtrip/stair.diff_batch.md",
    "implementation/phase1/irregular_structure_collection_gate_report.json",
    "implementation/phase1/open_data/irregular/irregular_structure_source_catalog.json",
    "implementation/phase1/open_data/irregular/irregular_structure_triage_report.json",
    "implementation/phase1/open_data/irregular/irregular_structure_collection_report.json",
    "implementation/phase1/open_data/irregular/irregular_top5_execution_manifest.json",
    "implementation/phase1/release/external_benchmark_kickoff/irregular_benchmark_execution_manifest.json",
    "implementation/phase1/release/external_benchmark_kickoff/irregular_benchmark_execution_manifest.md",
] + EXTERNAL_LIGHT_ARTIFACTS_DESIGN_OPT


def _dedupe_artifacts(paths: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for path in paths:
        key = str(path)
        if not key or key in seen:
            continue
        seen.add(key)
        ordered.append(key)
    return ordered


def _scrub_external_bundle_artifact_list(paths: list[str]) -> list[str]:
    return [
        str(path)
        for path in paths
        if Path(str(path)).name not in EXTERNAL_BUNDLE_SCRUBBED_ARTIFACT_BASENAMES
    ]


def _external_surface_irregular_canonical_promotion_queue_rows(summary: dict) -> list[dict]:
    return [
        item
        for item in (summary.get("irregular_canonical_promotion_queue_rows") or [])
        if isinstance(item, dict)
        and str(item.get("family_id", "") or "").strip() not in EXTERNAL_ONEPAGE_HIDDEN_IRREGULAR_FAMILY_IDS
    ]


def _external_surface_irregular_family_id_list(items: list[str]) -> list[str]:
    return [
        str(item).strip()
        for item in (items or [])
        if str(item).strip() and str(item).strip() not in EXTERNAL_ONEPAGE_HIDDEN_IRREGULAR_FAMILY_IDS
    ]


def _scrub_external_bundle_summary(summary: dict) -> dict:
    scrubbed = copy.deepcopy(summary)
    artifacts = scrubbed.get("artifacts")
    if isinstance(artifacts, dict):
        for key in EXTERNAL_BUNDLE_SCRUBBED_ARTIFACT_KEYS:
            artifacts.pop(key, None)
    scrubbed["irregular_canonical_promotion_queue_rows"] = (
        _external_surface_irregular_canonical_promotion_queue_rows(scrubbed)
    )
    return scrubbed


def _existing_artifact_paths(paths: list[str]) -> list[str]:
    return _dedupe_artifacts([key for key in (str(path) for path in paths) if key and Path(key).exists()])


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_optional_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return _load_json(path)

def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _bool_status(value: bool) -> str:
    return "PASS" if bool(value) else "FAIL"


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        if value is None:
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _coverage_range_label(values: object) -> str:
    if isinstance(values, list) and len(values) == 2:
        return f"{values[0]}-{values[1]}%"
    return "n/a"


def _midas_row_provenance_preview_rows(source: dict) -> list[dict]:
    preview_rows = source.get("midas_kds_row_provenance_preview_rows")
    if not isinstance(preview_rows, list) and isinstance(source.get("metrics"), dict):
        preview_rows = source["metrics"].get("midas_kds_row_provenance_preview_rows")
    return [
        row
        for row in (preview_rows or [])
        if isinstance(row, dict)
    ]


def _midas_row_provenance_clause_filter_rows(source: dict) -> list[dict]:
    rows = source.get("midas_kds_row_provenance_clause_filter_rows")
    if not isinstance(rows, list) and isinstance(source.get("metrics"), dict):
        rows = source["metrics"].get("midas_kds_row_provenance_clause_filter_rows")
    return [row for row in (rows or []) if isinstance(row, dict)]


def _midas_row_provenance_member_filter_rows(source: dict) -> list[dict]:
    rows = source.get("midas_kds_row_provenance_member_filter_rows")
    if not isinstance(rows, list) and isinstance(source.get("metrics"), dict):
        rows = source["metrics"].get("midas_kds_row_provenance_member_filter_rows")
    return [row for row in (rows or []) if isinstance(row, dict)]


def _midas_row_provenance_hazard_filter_rows(source: dict) -> list[dict]:
    rows = source.get("midas_kds_row_provenance_hazard_filter_rows")
    if not isinstance(rows, list) and isinstance(source.get("metrics"), dict):
        rows = source["metrics"].get("midas_kds_row_provenance_hazard_filter_rows")
    return [row for row in (rows or []) if isinstance(row, dict)]


def _midas_row_provenance_rule_family_filter_rows(source: dict) -> list[dict]:
    rows = source.get("midas_kds_row_provenance_rule_family_filter_rows")
    if not isinstance(rows, list) and isinstance(source.get("metrics"), dict):
        rows = source["metrics"].get("midas_kds_row_provenance_rule_family_filter_rows")
    return [row for row in (rows or []) if isinstance(row, dict)]


def _midas_row_provenance_appendix_markdown(source: dict, artifacts: dict) -> list[str]:
    row_provenance_preview_rows = _midas_row_provenance_preview_rows(source)
    clause_filter_rows = _midas_row_provenance_clause_filter_rows(source)
    member_filter_rows = _midas_row_provenance_member_filter_rows(source)
    hazard_filter_rows = _midas_row_provenance_hazard_filter_rows(source)
    rule_family_filter_rows = _midas_row_provenance_rule_family_filter_rows(source)
    metrics = source.get("metrics") if isinstance(source.get("metrics"), dict) else source
    row_provenance_summary_line = str(
        metrics.get("midas_kds_row_provenance_export_summary_line", "") or ""
    ).strip()
    if not row_provenance_summary_line and not row_provenance_preview_rows and not clause_filter_rows and not member_filter_rows and not hazard_filter_rows and not rule_family_filter_rows:
        return []
    lines = [
        "## Appendix: MIDAS KDS Row Provenance Export",
        "",
        f"- `summary`: `{row_provenance_summary_line or 'n/a'}`",
        (
            f"- `artifacts`: json=`{artifacts.get('midas_kds_row_provenance_export_json', '') or 'n/a'}` | "
            f"csv=`{artifacts.get('midas_kds_row_provenance_export_csv', '') or 'n/a'}` | "
            f"report=`{artifacts.get('midas_kds_row_provenance_export_report', '') or 'n/a'}`"
        ),
        f"- `row-provenance sync`: `{ROW_PROVENANCE_SYNC_NOTE}`",
    ]
    if row_provenance_preview_rows:
        lines.extend(
            [
                "",
                "| Combination | Member | Clause | Baseline Focus | Mode | Clause Provenance | Member Inventory |",
                "|---|---|---|---|---|---|---|",
            ]
        )
        for row in row_provenance_preview_rows:
            lines.append(
                f"| {row.get('combination_name', '')} | {row.get('member_id', '')} | {row.get('clause_label', '')} | "
                f"{row.get('baseline_focus_member_id', '')} | {row.get('bridge_row_provenance_mode_label', '')} | "
                f"{row.get('clause_provenance_summary_label', '')} | {row.get('bridge_member_inventory_summary_label', '')} |"
            )
    if clause_filter_rows:
        lines.extend(
            [
                "",
                "| Clause | Rows | Members | Combos | Top Member | Top D/C |",
                "|---|---|---|---|---|---|",
            ]
        )
        for row in clause_filter_rows:
            lines.append(
                f"| {row.get('clause_label', '')} | {row.get('row_count', '')} | {row.get('member_count', '')} | "
                f"{row.get('combination_count', '')} | {row.get('top_member_id', '')} | {row.get('top_dcr_label', '')} |"
            )
    if member_filter_rows:
        lines.extend(
            [
                "",
                "| Member | Baseline Focus | Rows | Clauses | Combos | Top Clause |",
                "|---|---|---|---|---|---|",
            ]
        )
        for row in member_filter_rows:
            lines.append(
                f"| {row.get('member_id', '')} | {row.get('baseline_focus_member_id', '')} | {row.get('row_count', '')} | "
                f"{row.get('clause_count', '')} | {row.get('combination_count', '')} | {row.get('top_clause_label', '')} |"
            )
    if hazard_filter_rows:
        lines.extend(
            [
                "",
                "| Hazard | Rows | Members | Clauses | Combos | Top Clause | Top D/C |",
                "|---|---|---|---|---|---|---|",
            ]
        )
        for row in hazard_filter_rows:
            lines.append(
                f"| {row.get('hazard_type', '')} | {row.get('row_count', '')} | {row.get('member_count', '')} | "
                f"{row.get('clause_count', '')} | {row.get('combination_count', '')} | {row.get('top_clause_label', '')} | {row.get('top_dcr_label', '')} |"
            )
    if rule_family_filter_rows:
        lines.extend(
            [
                "",
                "| Rule Family | Rows | Members | Hazards | Combos | Top Clause | Top D/C |",
                "|---|---|---|---|---|---|---|",
            ]
        )
        for row in rule_family_filter_rows:
            lines.append(
                f"| {row.get('rule_family', '')} | {row.get('row_count', '')} | {row.get('member_count', '')} | "
                f"{row.get('hazard_count', '')} | {row.get('combination_count', '')} | {row.get('top_clause_label', '')} | {row.get('top_dcr_label', '')} |"
            )
    lines.append("")
    return lines


def _midas_row_provenance_appendix_html(source: dict, artifacts: dict) -> str:
    row_provenance_preview_rows = _midas_row_provenance_preview_rows(source)
    clause_filter_rows = _midas_row_provenance_clause_filter_rows(source)
    member_filter_rows = _midas_row_provenance_member_filter_rows(source)
    hazard_filter_rows = _midas_row_provenance_hazard_filter_rows(source)
    rule_family_filter_rows = _midas_row_provenance_rule_family_filter_rows(source)
    metrics = source.get("metrics") if isinstance(source.get("metrics"), dict) else source
    row_provenance_summary_line = str(
        metrics.get("midas_kds_row_provenance_export_summary_line", "") or ""
    ).strip()
    if not row_provenance_summary_line and not row_provenance_preview_rows and not clause_filter_rows and not member_filter_rows and not hazard_filter_rows and not rule_family_filter_rows:
        return ""
    row_provenance_rows_html = "".join(
        (
            f"<tr><td>{row.get('combination_name', '')}</td><td>{row.get('member_id', '')}</td>"
            f"<td>{row.get('clause_label', '')}</td><td>{row.get('baseline_focus_member_id', '')}</td>"
            f"<td>{row.get('bridge_row_provenance_mode_label', '')}</td>"
            f"<td>{row.get('clause_provenance_summary_label', '')}</td>"
            f"<td>{row.get('bridge_member_inventory_summary_label', '')}</td></tr>"
        )
        for row in row_provenance_preview_rows
    ) or "<tr><td colspan='7'>No row provenance preview rows available.</td></tr>"
    clause_filter_rows_html = "".join(
        (
            f"<tr><td>{row.get('clause_label', '')}</td><td>{row.get('row_count', '')}</td>"
            f"<td>{row.get('member_count', '')}</td><td>{row.get('combination_count', '')}</td>"
            f"<td>{row.get('top_member_id', '')}</td><td>{row.get('top_dcr_label', '')}</td></tr>"
        )
        for row in clause_filter_rows
    ) or "<tr><td colspan='6'>No clause filter rows available.</td></tr>"
    member_filter_rows_html = "".join(
        (
            f"<tr><td>{row.get('member_id', '')}</td><td>{row.get('baseline_focus_member_id', '')}</td>"
            f"<td>{row.get('row_count', '')}</td><td>{row.get('clause_count', '')}</td>"
            f"<td>{row.get('combination_count', '')}</td><td>{row.get('top_clause_label', '')}</td></tr>"
        )
        for row in member_filter_rows
    ) or "<tr><td colspan='6'>No member filter rows available.</td></tr>"
    hazard_filter_rows_html = "".join(
        (
            f"<tr><td>{row.get('hazard_type', '')}</td><td>{row.get('row_count', '')}</td>"
            f"<td>{row.get('member_count', '')}</td><td>{row.get('clause_count', '')}</td>"
            f"<td>{row.get('combination_count', '')}</td><td>{row.get('top_clause_label', '')}</td>"
            f"<td>{row.get('top_dcr_label', '')}</td></tr>"
        )
        for row in hazard_filter_rows
    ) or "<tr><td colspan='7'>No hazard filter rows available.</td></tr>"
    rule_family_filter_rows_html = "".join(
        (
            f"<tr><td>{row.get('rule_family', '')}</td><td>{row.get('row_count', '')}</td>"
            f"<td>{row.get('member_count', '')}</td><td>{row.get('hazard_count', '')}</td>"
            f"<td>{row.get('combination_count', '')}</td><td>{row.get('top_clause_label', '')}</td>"
            f"<td>{row.get('top_dcr_label', '')}</td></tr>"
        )
        for row in rule_family_filter_rows
    ) or "<tr><td colspan='7'>No rule family rows available.</td></tr>"
    return f"""
        <div style="margin-top: 18px;">
          <h3 style="margin-bottom: 8px;">Appendix: MIDAS KDS Row Provenance Export</h3>
          <div class="note">{row_provenance_summary_line or 'n/a'}</div>
          <div class="note" style="margin-top: 4px;">
            json={artifacts.get('midas_kds_row_provenance_export_json', '') or 'n/a'} |
            csv={artifacts.get('midas_kds_row_provenance_export_csv', '') or 'n/a'} |
            report={artifacts.get('midas_kds_row_provenance_export_report', '') or 'n/a'}
          </div>
          <div class="note" style="margin-top: 4px;">
            row-provenance sync: {ROW_PROVENANCE_SYNC_NOTE}
          </div>
          <table style="margin-top: 12px;">
            <thead>
              <tr><td>Combination</td><td>Member</td><td>Clause</td><td>Baseline Focus</td><td>Mode</td><td>Clause Provenance</td><td>Member Inventory</td></tr>
            </thead>
            <tbody>
              {row_provenance_rows_html}
            </tbody>
          </table>
          <table style="margin-top: 12px;">
            <thead>
              <tr><td>Clause</td><td>Rows</td><td>Members</td><td>Combos</td><td>Top Member</td><td>Top D/C</td></tr>
            </thead>
            <tbody>
              {clause_filter_rows_html}
            </tbody>
          </table>
          <table style="margin-top: 12px;">
            <thead>
              <tr><td>Member</td><td>Baseline Focus</td><td>Rows</td><td>Clauses</td><td>Combos</td><td>Top Clause</td></tr>
            </thead>
            <tbody>
              {member_filter_rows_html}
            </tbody>
          </table>
          <table style="margin-top: 12px;">
            <thead>
              <tr><td>Hazard</td><td>Rows</td><td>Members</td><td>Clauses</td><td>Combos</td><td>Top Clause</td><td>Top D/C</td></tr>
            </thead>
            <tbody>
              {hazard_filter_rows_html}
            </tbody>
          </table>
          <table style="margin-top: 12px;">
            <thead>
              <tr><td>Rule Family</td><td>Rows</td><td>Members</td><td>Hazards</td><td>Combos</td><td>Top Clause</td><td>Top D/C</td></tr>
            </thead>
            <tbody>
              {rule_family_filter_rows_html}
            </tbody>
          </table>
        </div>
    """


def _midas_native_roundtrip_receipt_rows(source: dict) -> list[dict]:
    rows = source.get("midas_native_roundtrip_receipt_rows")
    if not isinstance(rows, list) and isinstance(source.get("metrics"), dict):
        rows = source["metrics"].get("midas_native_roundtrip_receipt_rows")
    return [row for row in (rows or []) if isinstance(row, dict)]


def _midas_native_roundtrip_structure_type_batches(source: dict) -> list[dict]:
    rows = source.get("midas_native_roundtrip_structure_type_batches")
    if not isinstance(rows, list) and isinstance(source.get("metrics"), dict):
        rows = source["metrics"].get("midas_native_roundtrip_structure_type_batches")
    return [row for row in (rows or []) if isinstance(row, dict)]


def _format_action_family_counts(counts: dict | None) -> str:
    if not isinstance(counts, dict) or not counts:
        return "n/a"
    items: list[tuple[str, int]] = []
    for key, value in counts.items():
        try:
            items.append((str(key), int(value)))
        except Exception:
            continue
    if not items:
        return "n/a"
    return ", ".join(f"{key}={value}" for key, value in sorted(items))


def _load_midas_native_corpus_cases() -> list[dict]:
    manifest_path = REPO_ROOT / "implementation/phase1/open_data/midas/midas_native_corpus_manifest.json"
    if not manifest_path.exists():
        return []
    payload = _load_json(manifest_path)
    for key in ("cases", "records", "entries"):
        rows = payload.get(key)
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    return []


def _load_korean_source_catalog_rows() -> list[dict]:
    catalog_path = REPO_ROOT / "implementation/phase1/open_data/korea/korean_source_catalog.json"
    if not catalog_path.exists():
        return []
    payload = _load_json(catalog_path)
    rows = payload.get("source_records")
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _korean_native_roundtrip_representative_rows(source: dict) -> list[dict]:
    rows = source.get("korean_native_roundtrip_representative_rows")
    if not isinstance(rows, list) and isinstance(source.get("metrics"), dict):
        rows = source["metrics"].get("korean_native_roundtrip_representative_rows")
    return [row for row in (rows or []) if isinstance(row, dict)]


def _identity_receipt_case_id(case_id: str) -> str:
    normalized = str(case_id or "").strip()
    if normalized.endswith("__identity_writeback"):
        return normalized
    return f"{normalized}__identity_writeback" if normalized else normalized


def _normalize_representative_lane_value(value: str) -> str:
    normalized = str(value or "").strip().lower().replace(" ", "_")
    if normalized in {"public_structural_preview", "public_structural_preview_ready"}:
        return "public_structural_preview_ready"
    if normalized in {"public_native", "public_native_ready"}:
        return "public_native_ready"
    return normalized or "unknown"


def _representative_lane_label(row: dict) -> str:
    role = str(row.get("role", "") or "").strip()
    if role == "native_source_public_archive_structural_preview":
        return "public_structural_preview_ready"
    if role == "native_source_public_raw":
        return "public_native_ready"
    return _normalize_representative_lane_value(str(row.get("lane_label", "") or role))


def _representative_lane_display_label(value: str) -> str:
    normalized = _normalize_representative_lane_value(value)
    if normalized == "public_structural_preview_ready":
        return "public_structural_preview"
    if normalized == "public_native_ready":
        return "public_native"
    return normalized


def _representative_lane_priority(row: dict) -> tuple[int, str]:
    role = _representative_lane_label(row)
    structure_type = str(row.get("structure_type", "") or "").strip()
    source_id = str(row.get("source_id", "") or "").strip()
    if role == "public_structural_preview_ready":
        return (0, structure_type, source_id)
    if role == "public_native_ready":
        return (1, structure_type, source_id)
    return (9, structure_type, source_id)


def _build_korean_native_roundtrip_representative_rows(
    midas_native_roundtrip_corpus_manifest: dict,
    midas_native_roundtrip_receipts_report: dict,
) -> list[dict]:
    corpus_cases = [
        row
        for row in (midas_native_roundtrip_corpus_manifest.get("cases") or [])
        if isinstance(row, dict)
    ]
    receipt_rows = [
        row for row in (midas_native_roundtrip_receipts_report.get("receipt_rows") or []) if isinstance(row, dict)
    ]
    structure_type_batches = [
        row
        for row in (midas_native_roundtrip_receipts_report.get("structure_type_batches") or [])
        if isinstance(row, dict)
    ]
    korean_catalog_rows = _load_korean_source_catalog_rows()
    catalog_by_source_id = {
        str(row.get("source_id", "") or "").strip(): row
        for row in korean_catalog_rows
        if str(row.get("source_id", "") or "").strip()
    }
    receipt_by_case_id = {
        str(row.get("case_id", "") or "").strip(): row
        for row in receipt_rows
        if str(row.get("case_id", "") or "").strip()
    }
    batch_by_type = {
        str(row.get("structure_type", "") or "").strip(): row
        for row in structure_type_batches
        if str(row.get("structure_type", "") or "").strip()
    }

    candidate_rows = [
        row
        for row in corpus_cases
        if str(row.get("source_family", "") or "").startswith("korean_")
        and str(row.get("role", "") or "")
        in {"native_source_public_raw", "native_source_public_archive_structural_preview"}
    ]
    candidate_rows.sort(key=_representative_lane_priority)

    representative_by_lane_type: dict[tuple[str, str], dict] = {}
    for row in candidate_rows:
        lane_label = _representative_lane_label(row)
        structure_type = str(row.get("structure_type", "") or "").strip() or "unknown"
        key = (lane_label, structure_type)
        if key in representative_by_lane_type:
            continue
        representative_by_lane_type[key] = row

    output_rows: list[dict] = []
    for lane_label, structure_type in sorted(representative_by_lane_type):
        case = representative_by_lane_type[(lane_label, structure_type)]
        source_id = str(case.get("source_id", "") or "").strip()
        catalog_row = catalog_by_source_id.get(source_id, {})
        receipt_case_id = _identity_receipt_case_id(str(case.get("case_id", "") or "").strip())
        receipt_row = receipt_by_case_id.get(receipt_case_id, {})
        batch_row = batch_by_type.get(structure_type, {})
        title = str(catalog_row.get("title", "") or case.get("title", "") or source_id).strip() or source_id
        output_rows.append(
            {
                "structure_type": structure_type,
                "source_id": source_id,
                "case_id": str(case.get("case_id", "") or "").strip(),
                "receipt_case_id": receipt_case_id,
                "title": title,
                "lane_label": lane_label,
                "source_family": str(case.get("source_family", "") or "").strip(),
                "origin_org": str(catalog_row.get("origin_org", "") or "").strip(),
                "source_class": str(catalog_row.get("source_class", "") or case.get("source_class", "") or "").strip(),
                "structural_system": str(
                    catalog_row.get("structural_system", "") or case.get("structural_system", "") or ""
                ).strip()
                or "n/a",
                "storey_band": str(catalog_row.get("storey_band", "") or "").strip() or "n/a",
                "provenance_url": str(catalog_row.get("provenance_url", "") or case.get("url", "") or "").strip(),
                "receipt_md": str(receipt_row.get("receipt_md", "") or "").strip(),
                "receipt_json": str(receipt_row.get("receipt_json", "") or "").strip(),
                "receipt_summary_line": str(receipt_row.get("summary_line", "") or "").strip(),
                "type_batch_markdown": str(batch_row.get("batch_markdown", "") or "").strip(),
                "type_batch_ready_case_count": int(batch_row.get("ready_case_count", 0) or 0),
            }
        )
    return output_rows


def _render_korean_native_roundtrip_representatives_markdown(source: dict) -> list[str]:
    rows = _korean_native_roundtrip_representative_rows(source)
    if not rows:
        return []
    lane_counts: dict[str, int] = {}
    for row in rows:
        lane = _representative_lane_label(row)
        lane_counts[lane] = lane_counts.get(lane, 0) + 1
    lines = [
        "### KR Representative Type Batches",
        "",
        f"- `summary`: `rows={len(rows)} | lanes={', '.join(f'{lane}={count}' for lane, count in sorted(lane_counts.items())) or 'n/a'}`",
        "",
    ]
    lane_headings = {
        "public_structural_preview_ready": "#### Public Structural Preview Lane",
        "public_native_ready": "#### Public Native Lane",
    }
    ordered_lanes = [
        lane
        for lane in ["public_structural_preview_ready", "public_native_ready"]
        if any(_representative_lane_label(row) == lane for row in rows)
    ]
    ordered_lanes.extend(
        sorted(
            {
                _representative_lane_label(row)
                for row in rows
                if _representative_lane_label(row) not in lane_headings
            }
        )
    )
    for lane in ordered_lanes:
        subset = [row for row in rows if _representative_lane_label(row) == lane]
        if not subset:
            continue
        lines.extend(
            [
                lane_headings.get(lane, f"#### {lane}"),
                "",
                "| Structure Type | Representative | Lane | System | Receipt | Type Batch |",
                "|---|---|---|---|---|---|",
            ]
        )
        for row in subset:
            receipt_ref = str(row.get("receipt_md", "") or row.get("receipt_json", "") or "n/a")
            batch_ref = str(row.get("type_batch_markdown", "") or "n/a")
            lane_display = _representative_lane_display_label(str(row.get("lane_label", "") or lane))
            lines.append(
                f"| {row.get('structure_type', '')} | {row.get('title', '')} (`{row.get('source_id', '')}`) | "
                f"{lane_display} | {row.get('structural_system', '')} | "
                f"`{receipt_ref}` | `{batch_ref}` |"
            )
        lines.append("")
    lines.append("")
    return lines


def _render_korean_native_roundtrip_representatives_html(source: dict) -> str:
    rows = _korean_native_roundtrip_representative_rows(source)
    if not rows:
        return ""
    lane_counts: dict[str, int] = {}
    for row in rows:
        lane = _representative_lane_label(row)
        lane_counts[lane] = lane_counts.get(lane, 0) + 1
    summary_line = "rows=" + str(len(rows)) + " | lanes=" + ", ".join(
        f"{lane}={count}" for lane, count in sorted(lane_counts.items())
    )
    lane_headings = {
        "public_structural_preview_ready": "Public Structural Preview Lane",
        "public_native_ready": "Public Native Lane",
    }
    ordered_lanes = [
        lane
        for lane in ["public_structural_preview_ready", "public_native_ready"]
        if any(_representative_lane_label(row) == lane for row in rows)
    ]
    ordered_lanes.extend(
        sorted(
            {
                _representative_lane_label(row)
                for row in rows
                if _representative_lane_label(row) not in lane_headings
            }
        )
    )
    sections: list[str] = []
    for lane in ordered_lanes:
        subset = [row for row in rows if _representative_lane_label(row) == lane]
        if not subset:
            continue
        rows_html = "".join(
            f"<tr><td>{html.escape(str(row.get('structure_type', '') or ''))}</td>"
            f"<td>{html.escape(str(row.get('title', '') or ''))}<div class='mini-note'><code>{html.escape(str(row.get('source_id', '') or ''))}</code></div></td>"
            f"<td>{html.escape(_representative_lane_display_label(str(row.get('lane_label', '') or lane)))}</td>"
            f"<td>{html.escape(str(row.get('structural_system', '') or 'n/a'))}</td>"
            f"<td>{html.escape(str(row.get('receipt_md', '') or row.get('receipt_json', '') or 'n/a'))}</td>"
            f"<td>{html.escape(str(row.get('type_batch_markdown', '') or 'n/a'))}</td></tr>"
            for row in subset
        )
        sections.append(
            f"<h4 style=\"margin: 12px 0 8px;\">{html.escape(lane_headings.get(lane, lane))}</h4>"
            "<table style=\"margin-top: 8px;\">"
            "<thead><tr><td>Structure Type</td><td>Representative</td><td>Lane</td><td>System</td><td>Receipt</td><td>Type Batch</td></tr></thead>"
            f"<tbody>{rows_html}</tbody></table>"
        )
    return (
        "<div class=\"mini-note\" style=\"margin-top: 10px;\">"
        + html.escape(summary_line)
        + "</div>"
        + "".join(sections)
    )


def _public_structural_preview_representative_rows(source: dict) -> list[dict]:
    return [
        row
        for row in _korean_native_roundtrip_representative_rows(source)
        if _representative_lane_label(row) == "public_structural_preview_ready"
    ]


def _render_public_structural_preview_representatives_markdown(source: dict) -> list[str]:
    rows = _public_structural_preview_representative_rows(source)
    if not rows:
        return []
    lines = [
        "### KR Public Structural Preview Representatives",
        "",
        f"- `summary`: `rows={len(rows)} | lane=public_structural_preview`",
        "",
        "| Structure Type | Representative | Lane | Receipt | Type Batch |",
        "|---|---|---|---|---|",
    ]
    for row in rows:
        receipt_ref = str(row.get("receipt_md", "") or row.get("receipt_json", "") or "n/a")
        batch_ref = str(row.get("type_batch_markdown", "") or "n/a")
        lines.append(
            f"| {row.get('structure_type', '')} | {row.get('title', '')} (`{row.get('source_id', '')}`) | "
            f"{_representative_lane_display_label(str(row.get('lane_label', '') or ''))} | "
            f"`{receipt_ref}` | `{batch_ref}` |"
        )
    lines.append("")
    return lines


def _render_public_structural_preview_representatives_html(source: dict) -> str:
    rows = _public_structural_preview_representative_rows(source)
    if not rows:
        return ""
    rows_html = "".join(
        f"<tr><td>{html.escape(str(row.get('structure_type', '') or ''))}</td>"
        f"<td>{html.escape(str(row.get('title', '') or ''))}<div class='mini-note'><code>{html.escape(str(row.get('source_id', '') or ''))}</code></div></td>"
        f"<td>{html.escape(_representative_lane_display_label(str(row.get('lane_label', '') or '')))}</td>"
        f"<td>{html.escape(str(row.get('receipt_md', '') or row.get('receipt_json', '') or 'n/a'))}</td>"
        f"<td>{html.escape(str(row.get('type_batch_markdown', '') or 'n/a'))}</td></tr>"
        for row in rows
    )
    return (
        "<div class=\"note\" style=\"margin-top: 8px;\">"
        + html.escape(f"rows={len(rows)} | lane=public_structural_preview")
        + "</div>"
        + "<h4 style=\"margin: 12px 0 8px;\">KR Public Structural Preview Representatives</h4>"
        + "<table style=\"margin-top: 8px;\">"
        + "<thead><tr><td>Structure Type</td><td>Representative</td><td>Lane</td><td>Receipt</td><td>Type Batch</td></tr></thead>"
        + f"<tbody>{rows_html}</tbody></table>"
    )

def _preview_structure_type(source_id: str, fallback: str) -> str:
    normalized = str(source_id or "").strip().lower()
    if normalized in {
        "midas_support_multifamily_building_archive",
        "midas_support_neighborhood_facility_archive",
        "midas_support_rc_house_archive",
    }:
        return "building"
    if normalized in {"midas_support_stair_archive"}:
        return "stair"
    if normalized in {"midas_support_ramp_archive"}:
        return "ramp"
    if normalized in {"midas_support_beam_archive"}:
        return "beam"
    if normalized in {"midas_support_fcm_bridge_archive"}:
        return "bridge"
    return str(fallback or "building")


def _exact_topology_archive_candidate_rows() -> list[dict]:
    corpus_cases = _load_midas_native_corpus_cases()
    promoted_source_ids = {
        str(row.get("source_id", "") or "").strip()
        for row in corpus_cases
        if str(row.get("role", "") or "").strip() == "native_source_public_archive_structural_preview"
        and str(row.get("source_id", "") or "").strip()
    }
    rows: list[dict] = []
    base_dir = REPO_ROOT / "implementation/phase1/open_data/midas/quality_corpus/bridged"
    for report_path in sorted(base_dir.glob("*_decoded_preview/bridge_report.json")):
        payload = _load_json(report_path)
        summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
        viewer_ready = bool(summary.get("viewer_ready", payload.get("viewer_ready", False)))
        exact_topology_candidate = bool(
            summary.get("exact_topology_candidate", payload.get("exact_topology_candidate", False))
        )
        if not viewer_ready or not exact_topology_candidate:
            continue
        source_id = str(report_path.parent.name or "")
        if source_id.endswith("_decoded_preview"):
            source_id = source_id[: -len("_decoded_preview")]
        structure_type = _preview_structure_type(
            source_id,
            str(summary.get("structure_type", "") or "building"),
        )
        supported_structural_preview = structure_type in {"bridge", "ramp", "stair"}
        promoted_now = source_id in promoted_source_ids
        if promoted_now:
            status = "promoted"
        elif supported_structural_preview:
            status = "pending_promotion"
        else:
            status = "unsupported_structural_preview_type"
        rows.append(
            {
                "source_id": source_id,
                "structure_type": structure_type,
                "status": status,
                "promoted_now": promoted_now,
                "supported_structural_preview": supported_structural_preview,
                "preview_surface_status_label": str(
                    summary.get("preview_surface_status_label", "") or "structural preview"
                ),
                "viewer_ready": viewer_ready,
                "exact_topology_candidate": exact_topology_candidate,
                "bridge_report_json": str(report_path),
                "model_json": str((report_path.parent / "model.json").as_posix()),
            }
        )
    return rows


def _count_exact_topology_archive_candidates() -> int:
    return len(_exact_topology_archive_candidate_rows())


def _pending_exact_topology_archive_candidate_rows() -> list[dict]:
    return [
        row for row in _exact_topology_archive_candidate_rows() if str(row.get("status", "") or "") == "pending_promotion"
    ]


def _merge_exact_topology_structural_preview_pending_rows(
    *,
    existing_rows: list[dict],
    current_rows: list[dict],
) -> list[dict]:
    existing_by_source_id = {
        str(row.get("source_id", "") or ""): row
        for row in existing_rows
        if isinstance(row, dict) and str(row.get("source_id", "") or "")
    }
    merged_rows: list[dict] = []
    for row in current_rows:
        source_id = str(row.get("source_id", "") or "")
        merged = dict(existing_by_source_id.get(source_id, {}))
        merged.update(row)
        merged_rows.append(merged)
    return merged_rows


def _build_exact_topology_structural_preview_queue_summary(
    *,
    candidate_rows: list[dict],
    pending_rows: list[dict],
    existing_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    summary = dict(existing_summary or {})
    archive_candidate_total = int(len(candidate_rows))
    pending_candidate_count = int(len(pending_rows))
    candidate_total = max(
        int(summary.get("candidate_total", 0) or 0),
        archive_candidate_total,
        pending_candidate_count,
    )
    public_archive_promoted_candidate_count = int(
        sum(1 for row in candidate_rows if str(row.get("status", "") or "") == "promoted")
    )
    summary["candidate_total"] = int(candidate_total)
    summary["pending_candidate_count"] = int(pending_candidate_count)
    summary["promoted_candidate_count"] = int(
        max(candidate_total - pending_candidate_count, public_archive_promoted_candidate_count)
    )
    summary["public_archive_promoted_candidate_count"] = int(public_archive_promoted_candidate_count)
    summary["korean_candidate_total"] = int(summary.get("korean_candidate_total", 0) or 0)
    summary["korean_pending_candidate_count"] = int(summary.get("korean_pending_candidate_count", 0) or 0)
    summary["state"] = (
        "open" if pending_rows else "closed_until_new_public_archive_exact_topology_candidate"
    )
    return summary


def _write_exact_topology_structural_preview_promotion_queue(release_dir: Path) -> tuple[str, str]:
    existing_json = release_dir / "midas_native_roundtrip" / "exact_topology_structural_preview_promotion_queue.json"
    existing_md = release_dir / "midas_native_roundtrip" / "exact_topology_structural_preview_promotion_queue.md"
    existing_payload = _load_json(existing_json)
    existing_summary = existing_payload.get("summary") if isinstance(existing_payload.get("summary"), dict) else {}
    existing_rows = [
        row
        for row in (existing_payload.get("pending_candidate_rows") or [])
        if isinstance(row, dict)
    ]
    current_candidate_rows = _exact_topology_archive_candidate_rows()
    current_pending_rows = [
        row for row in current_candidate_rows if str(row.get("status", "") or "") == "pending_promotion"
    ]
    if existing_summary:
        merged_rows = _merge_exact_topology_structural_preview_pending_rows(
            existing_rows=existing_rows,
            current_rows=current_pending_rows,
        )
        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "summary": _build_exact_topology_structural_preview_queue_summary(
                candidate_rows=current_candidate_rows,
                pending_rows=merged_rows,
                existing_summary=existing_summary,
            ),
            "pending_candidate_rows": merged_rows,
        }
        _write_json(existing_json, payload)
        existing_md.write_text(
            _render_exact_topology_structural_preview_promotion_queue_markdown(payload),
            encoding="utf-8",
        )
        return str(existing_json.as_posix()), str(existing_md.as_posix())

    queue_rows = current_pending_rows
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "summary": _build_exact_topology_structural_preview_queue_summary(
            candidate_rows=current_candidate_rows,
            pending_rows=queue_rows,
        ),
        "pending_candidate_rows": queue_rows,
    }
    out_dir = release_dir / "midas_native_roundtrip"
    out_json = out_dir / "exact_topology_structural_preview_promotion_queue.json"
    out_md = out_dir / "exact_topology_structural_preview_promotion_queue.md"
    _write_json(out_json, payload)
    out_md.write_text(
        _render_exact_topology_structural_preview_promotion_queue_markdown(payload),
        encoding="utf-8",
    )
    return str(out_json.as_posix()), str(out_md.as_posix())


def _midas_native_roundtrip_appendix_markdown(source: dict, artifacts: dict) -> list[str]:
    receipt_rows = _midas_native_roundtrip_receipt_rows(source)
    batch_rows = _midas_native_roundtrip_structure_type_batches(source)
    metrics = source.get("metrics") if isinstance(source.get("metrics"), dict) else source
    summary_line = str(metrics.get("midas_native_roundtrip_summary_line", "") or "").strip()
    writeback_summary_line = str(metrics.get("midas_native_roundtrip_writeback_diff_summary_line", "") or "").strip()
    if summary_line.lower() == "n/a":
        summary_line = ""
    if writeback_summary_line.lower() == "n/a":
        writeback_summary_line = ""
    taxonomy_case_counts = (
        metrics.get("midas_native_roundtrip_taxonomy_case_counts")
        if isinstance(metrics.get("midas_native_roundtrip_taxonomy_case_counts"), dict)
        else {}
    )
    taxonomy_card_family_histogram = (
        metrics.get("midas_native_roundtrip_taxonomy_card_family_histogram")
        if isinstance(metrics.get("midas_native_roundtrip_taxonomy_card_family_histogram"), dict)
        else {}
    )
    if not summary_line and not writeback_summary_line and not receipt_rows and not batch_rows and not taxonomy_case_counts and not taxonomy_card_family_histogram:
        return []
    public_native_ready = metrics.get("midas_native_roundtrip_public_native_writeback_ready_count", metrics.get("midas_native_roundtrip_public_native_ready_case_count", 0))
    public_raw_ready = metrics.get("midas_native_roundtrip_public_raw_native_writeback_ready_count", metrics.get("midas_native_roundtrip_public_raw_native_ready_case_count", 0))
    public_bridge_ready = metrics.get("midas_native_roundtrip_public_bridge_writeback_ready_count", metrics.get("midas_native_roundtrip_public_bridge_ready_case_count", 0))
    public_archive_preview_ready = metrics.get("midas_native_roundtrip_public_archive_preview_writeback_ready_count", metrics.get("midas_native_roundtrip_public_archive_preview_ready_case_count", 0))
    public_structural_preview_ready = metrics.get(
        "midas_native_roundtrip_public_archive_structural_preview_writeback_ready_count",
        metrics.get("midas_native_roundtrip_public_archive_structural_preview_ready_case_count", 0),
    )
    public_source_ready = metrics.get("midas_native_roundtrip_public_source_writeback_ready_count", metrics.get("midas_native_roundtrip_public_source_ready_case_count", 0))
    exact_topology_candidate_rows = [
        row
        for row in (metrics.get("midas_native_roundtrip_exact_topology_archive_candidate_rows") or [])
        if isinstance(row, dict)
    ]
    if not exact_topology_candidate_rows:
        exact_topology_candidate_rows = _exact_topology_archive_candidate_rows()
    exact_topology_candidate_total = int(
        metrics.get("midas_native_roundtrip_exact_topology_archive_candidate_count", len(exact_topology_candidate_rows)) or 0
    )
    pending_exact_topology_candidate_rows = [
        row for row in exact_topology_candidate_rows if str(row.get("status", "") or "") == "pending_promotion"
    ]
    additional_exact_topology_candidates = int(
        metrics.get(
            "midas_native_roundtrip_exact_topology_archive_pending_candidate_count",
            len(pending_exact_topology_candidate_rows),
        )
        or 0
    )
    special_member_supported_label = _format_action_family_counts(
        metrics.get("mgt_export_special_member_supported_action_family_counts")
    )
    special_member_direct_patch_label = _format_action_family_counts(
        metrics.get("mgt_export_special_member_direct_patch_action_family_counts")
    )
    special_member_zero_touch_label = _format_action_family_counts(
        metrics.get("mgt_export_special_member_zero_touch_verified_action_family_counts")
    )
    lines = [
        "## Appendix: MIDAS Native Roundtrip / Write-Back Taxonomy",
        "",
        f"- `roundtrip_gate_summary`: `{summary_line or 'n/a'}`",
        f"- `writeback_diff_summary`: `{writeback_summary_line or 'n/a'}`",
        (
            f"- `counts`: corpus={int(metrics.get('midas_native_roundtrip_corpus_case_count', 0))} | "
            f"native_text={int(metrics.get('midas_native_roundtrip_native_text_case_count', 0))} | "
            f"ready={int(metrics.get('midas_native_roundtrip_native_writeback_ready_count', 0))} | "
            f"public_native={int(metrics.get('midas_native_roundtrip_public_native_text_case_count', 0))} | "
            f"public_raw_native={int(metrics.get('midas_native_roundtrip_public_raw_native_text_case_count', 0))} | "
            f"public_bridge_native={int(metrics.get('midas_native_roundtrip_public_bridge_text_case_count', 0))} | "
            f"public_preview_native={int(metrics.get('midas_native_roundtrip_public_archive_preview_text_case_count', 0))} | "
            f"public_structural_preview_native={int(metrics.get('midas_native_roundtrip_public_archive_structural_preview_text_case_count', 0))} | "
            f"public_source={int(metrics.get('midas_native_roundtrip_public_source_writeback_ready_count', 0))} | "
            f"structure_types={int(metrics.get('midas_native_roundtrip_structure_type_count', 0))} | "
            f"batches={int(metrics.get('midas_native_roundtrip_structure_type_batch_count', 0))} | "
            f"receipts={int(metrics.get('midas_native_roundtrip_receipt_count', 0))}/{int(metrics.get('midas_native_roundtrip_receipt_pass_count', 0))} | "
            f"pending_review={int(metrics.get('midas_native_roundtrip_pending_review_total', 0))}"
        ),
        (
            f"- `public split`: public_native_ready={int(public_native_ready or 0)} | "
            f"public_raw_ready={int(public_raw_ready or 0)} | "
            f"public_bridge_ready={int(public_bridge_ready or 0)} | "
            f"public_archive_preview_ready={int(public_archive_preview_ready or 0)} | "
            f"public_structural_preview_ready={int(public_structural_preview_ready or 0)} | "
            f"public_source_ready={int(public_source_ready or 0)} | "
            f"fixture_ready={int(metrics.get('midas_native_roundtrip_fixture_native_writeback_ready_count', 0))} | "
            f"repo_ready={int(metrics.get('midas_native_roundtrip_repo_native_writeback_ready_count', 0))} | "
            f"experiment_ready={int(metrics.get('midas_native_roundtrip_experiment_native_writeback_ready_count', 0))}"
        ),
        (
            f"- `kr_preview_promoted`: ready={int(public_structural_preview_ready or 0)} | "
            f"cand={exact_topology_candidate_total} | addl_now={additional_exact_topology_candidates}"
        ),
        (
            f"- `special_member_family`: direct_patch=`{special_member_direct_patch_label}` | "
            f"supported=`{special_member_supported_label}` | zero_touch_verified=`{special_member_zero_touch_label}`"
        ),
        (
            f"- `kr_promotion_queue`: json=`{artifacts.get('exact_topology_structural_preview_promotion_queue_json', '') or 'n/a'}` | "
            f"markdown=`{artifacts.get('exact_topology_structural_preview_promotion_queue_md', '') or 'n/a'}`"
        ),
        (
            f"- `artifacts`: gate_json=`{artifacts.get('midas_native_roundtrip_gate_report_json', '') or 'n/a'}` | "
            f"receipts_report=`{artifacts.get('midas_native_roundtrip_receipts_report_json', '') or 'n/a'}` | "
            f"appendix_md=`{artifacts.get('midas_native_roundtrip_appendix_markdown', '') or 'n/a'}` | "
            f"appendix_json=`{artifacts.get('midas_native_roundtrip_appendix_json', '') or 'n/a'}`"
        ),
    ]
    if pending_exact_topology_candidate_rows:
        lines.extend(
            [
                "",
                "### KR Preview Promotion Queue",
                "",
                "| Source | Structure Type | Preview Surface | Status | Bridge Report |",
                "|---|---|---|---|---|",
            ]
        )
        for row in pending_exact_topology_candidate_rows:
            lines.append(
                f"| {row.get('source_id', '')} | {row.get('structure_type', '')} | "
                f"{row.get('preview_surface_status_label', '')} | {row.get('status', '')} | "
                f"{row.get('bridge_report_json', '')} |"
            )
    else:
        lines.extend(
            [
                "",
                f"- `kr_promotion_queue_state`: `{EXTERNAL_KR_PROMOTION_NOTE_SHORT}`",
            ]
        )
    if taxonomy_case_counts:
        lines.extend(
            [
                "",
                f"- `taxonomy_case_counts`: `{json.dumps(taxonomy_case_counts, ensure_ascii=False, sort_keys=True)}`",
            ]
        )
    if taxonomy_card_family_histogram:
        lines.extend(
            [
                f"- `taxonomy_card_family_histogram`: `{json.dumps(taxonomy_card_family_histogram, ensure_ascii=False, sort_keys=True)}`",
            ]
        )
    if batch_rows:
        lines.extend(
            [
                "",
                "| Structure Type | Ready | Receipts | Topology | Load | LoadComb | Pending Review | Batch Markdown |",
                "|---|---:|---:|---:|---:|---:|---:|---|",
            ]
        )
        for row in batch_rows:
            lines.append(
                f"| {row.get('structure_type', '')} | {row.get('ready_case_count', '')} | {row.get('receipt_pass_count', '')} | "
                f"{row.get('topology_stable_case_count', '')} | {row.get('load_contract_stable_case_count', '')} | "
                f"{row.get('loadcomb_exact_case_count', '')} | {row.get('pending_review_total', '')} | "
                f"{row.get('batch_markdown', '')} |"
            )
    if receipt_rows:
        lines.extend(
            [
                "",
                "| Case | Structure Type | Mode | Pass | Pending Review | Summary | Receipt MD | Receipt JSON |",
                "|---|---|---|---|---:|---|---|---|",
            ]
        )
        for row in receipt_rows:
            lines.append(
                f"| {row.get('case_id', '')} | {row.get('structure_type', '')} | {row.get('writeback_mode', '')} | "
                f"{row.get('contract_pass', '')} | {row.get('review_pending_count', '')} | {row.get('summary_line', '')} | "
                f"{row.get('receipt_md', '')} | {row.get('receipt_json', '')} |"
            )
    lines.append("")
    return lines


def _midas_native_roundtrip_appendix_html(source: dict, artifacts: dict) -> str:
    receipt_rows = _midas_native_roundtrip_receipt_rows(source)
    batch_rows = _midas_native_roundtrip_structure_type_batches(source)
    metrics = source.get("metrics") if isinstance(source.get("metrics"), dict) else source
    summary_line = str(metrics.get("midas_native_roundtrip_summary_line", "") or "").strip()
    writeback_summary_line = str(metrics.get("midas_native_roundtrip_writeback_diff_summary_line", "") or "").strip()
    if summary_line.lower() == "n/a":
        summary_line = ""
    if writeback_summary_line.lower() == "n/a":
        writeback_summary_line = ""
    taxonomy_case_counts = (
        metrics.get("midas_native_roundtrip_taxonomy_case_counts")
        if isinstance(metrics.get("midas_native_roundtrip_taxonomy_case_counts"), dict)
        else {}
    )
    taxonomy_card_family_histogram = (
        metrics.get("midas_native_roundtrip_taxonomy_card_family_histogram")
        if isinstance(metrics.get("midas_native_roundtrip_taxonomy_card_family_histogram"), dict)
        else {}
    )
    if not summary_line and not writeback_summary_line and not receipt_rows and not batch_rows and not taxonomy_case_counts and not taxonomy_card_family_histogram:
        return ""
    public_native_ready = metrics.get("midas_native_roundtrip_public_native_writeback_ready_count", metrics.get("midas_native_roundtrip_public_native_ready_case_count", 0))
    public_raw_ready = metrics.get("midas_native_roundtrip_public_raw_native_writeback_ready_count", metrics.get("midas_native_roundtrip_public_raw_native_ready_case_count", 0))
    public_bridge_ready = metrics.get("midas_native_roundtrip_public_bridge_writeback_ready_count", metrics.get("midas_native_roundtrip_public_bridge_ready_case_count", 0))
    public_archive_preview_ready = metrics.get("midas_native_roundtrip_public_archive_preview_writeback_ready_count", metrics.get("midas_native_roundtrip_public_archive_preview_ready_case_count", 0))
    public_structural_preview_ready = metrics.get(
        "midas_native_roundtrip_public_archive_structural_preview_writeback_ready_count",
        metrics.get("midas_native_roundtrip_public_archive_structural_preview_ready_case_count", 0),
    )
    public_source_ready = metrics.get("midas_native_roundtrip_public_source_writeback_ready_count", metrics.get("midas_native_roundtrip_public_source_ready_case_count", 0))
    exact_topology_candidate_rows = [
        row
        for row in (metrics.get("midas_native_roundtrip_exact_topology_archive_candidate_rows") or [])
        if isinstance(row, dict)
    ]
    if not exact_topology_candidate_rows:
        exact_topology_candidate_rows = _exact_topology_archive_candidate_rows()
    exact_topology_candidate_total = int(
        metrics.get("midas_native_roundtrip_exact_topology_archive_candidate_count", len(exact_topology_candidate_rows)) or 0
    )
    pending_exact_topology_candidate_rows = [
        row for row in exact_topology_candidate_rows if str(row.get("status", "") or "") == "pending_promotion"
    ]
    additional_exact_topology_candidates = int(
        metrics.get(
            "midas_native_roundtrip_exact_topology_archive_pending_candidate_count",
            len(pending_exact_topology_candidate_rows),
        )
        or 0
    )
    special_member_supported_label = _format_action_family_counts(
        metrics.get("mgt_export_special_member_supported_action_family_counts")
    )
    special_member_direct_patch_label = _format_action_family_counts(
        metrics.get("mgt_export_special_member_direct_patch_action_family_counts")
    )
    special_member_zero_touch_label = _format_action_family_counts(
        metrics.get("mgt_export_special_member_zero_touch_verified_action_family_counts")
    )
    batch_rows_html = "".join(
        (
            f"<tr><td>{row.get('structure_type', '')}</td><td>{row.get('ready_case_count', '')}</td>"
            f"<td>{row.get('receipt_pass_count', '')}</td><td>{row.get('topology_stable_case_count', '')}</td>"
            f"<td>{row.get('load_contract_stable_case_count', '')}</td><td>{row.get('loadcomb_exact_case_count', '')}</td>"
            f"<td>{row.get('pending_review_total', '')}</td><td>{row.get('batch_markdown', '')}</td></tr>"
        )
        for row in batch_rows
    ) or "<tr><td colspan='8'>No native roundtrip structure-type batch rows available.</td></tr>"
    receipt_rows_html = "".join(
        (
            f"<tr><td>{row.get('case_id', '')}</td><td>{row.get('structure_type', '')}</td><td>{row.get('writeback_mode', '')}</td>"
            f"<td>{row.get('contract_pass', '')}</td><td>{row.get('review_pending_count', '')}</td>"
            f"<td>{row.get('summary_line', '')}</td><td>{row.get('receipt_md', '')}</td><td>{row.get('receipt_json', '')}</td></tr>"
        )
        for row in receipt_rows
    ) or "<tr><td colspan='8'>No native roundtrip receipt rows available.</td></tr>"
    taxonomy_case_counts_html = (
        "<ul>"
        + "".join(f"<li>{key}: {value}</li>" for key, value in sorted(taxonomy_case_counts.items()))
        + "</ul>"
        if taxonomy_case_counts
        else "<div class='note'>No native roundtrip taxonomy case counts available.</div>"
    )
    taxonomy_card_family_histogram_html = (
        "<ul>"
        + "".join(
            f"<li>{key}: {json.dumps(value, ensure_ascii=False, sort_keys=True)}</li>"
            for key, value in sorted(taxonomy_card_family_histogram.items())
        )
        + "</ul>"
        if taxonomy_card_family_histogram
        else "<div class='note'>No native roundtrip taxonomy card-family histogram available.</div>"
    )
    exact_topology_queue_html = (
        "<table style='margin-top:8px;'><thead><tr><th>Source</th><th>Structure Type</th><th>Preview Surface</th><th>Status</th><th>Bridge Report</th></tr></thead><tbody>"
        + "".join(
            f"<tr><td>{html.escape(str(row.get('source_id', '') or 'n/a'))}</td>"
            f"<td>{html.escape(str(row.get('structure_type', '') or 'n/a'))}</td>"
            f"<td>{html.escape(str(row.get('preview_surface_status_label', '') or 'n/a'))}</td>"
            f"<td>{html.escape(str(row.get('status', '') or 'n/a'))}</td>"
            f"<td>{html.escape(str(row.get('bridge_report_json', '') or 'n/a'))}</td></tr>"
            for row in pending_exact_topology_candidate_rows
        )
        + "</tbody></table>"
    ) if pending_exact_topology_candidate_rows else (
        "<div class='note' style='margin-top: 6px;'>No additional supported exact-topology archive candidates are pending right now. "
        "This queue reopens automatically when a new public archive decoded preview lands with exact_topology_candidate=true.</div>"
    )
    return f"""
        <div style="margin-top: 18px;">
          <h3 style="margin-bottom: 8px;">Appendix: MIDAS Native Roundtrip / Write-Back Taxonomy</h3>
          <div class="note">{summary_line or 'n/a'}</div>
          <div class="note" style="margin-top: 4px;">{writeback_summary_line or 'n/a'}</div>
          <div class="note" style="margin-top: 4px;">
            corpus={int(metrics.get('midas_native_roundtrip_corpus_case_count', 0))} |
            native_text={int(metrics.get('midas_native_roundtrip_native_text_case_count', 0))} |
            ready={int(metrics.get('midas_native_roundtrip_native_writeback_ready_count', 0))} |
            public_native={int(metrics.get('midas_native_roundtrip_public_native_text_case_count', 0))} |
            public_raw_native={int(metrics.get('midas_native_roundtrip_public_raw_native_text_case_count', 0))} |
            public_bridge_native={int(metrics.get('midas_native_roundtrip_public_bridge_text_case_count', 0))} |
            public_preview_native={int(metrics.get('midas_native_roundtrip_public_archive_preview_text_case_count', 0))} |
            public_structural_preview_native={int(metrics.get('midas_native_roundtrip_public_archive_structural_preview_text_case_count', 0))} |
            public_source={int(metrics.get('midas_native_roundtrip_public_source_writeback_ready_count', 0))} |
            structure_types={int(metrics.get('midas_native_roundtrip_structure_type_count', 0))} |
            batches={int(metrics.get('midas_native_roundtrip_structure_type_batch_count', 0))} |
            receipts={int(metrics.get('midas_native_roundtrip_receipt_count', 0))}/{int(metrics.get('midas_native_roundtrip_receipt_pass_count', 0))} |
            pending_review={int(metrics.get('midas_native_roundtrip_pending_review_total', 0))}
          </div>
          <div class="note" style="margin-top: 4px;">
            public_native_ready={int(metrics.get('midas_native_roundtrip_public_native_writeback_ready_count', 0))} |
            public_raw_ready={int(public_raw_ready or 0)} |
            public_bridge_ready={int(public_bridge_ready or 0)} |
            public_archive_preview_ready={int(metrics.get('midas_native_roundtrip_public_archive_preview_writeback_ready_count', 0))} |
            public_structural_preview_ready={int(public_structural_preview_ready or 0)} |
            public_source_ready={int(metrics.get('midas_native_roundtrip_public_source_writeback_ready_count', 0))} |
            fixture_ready={int(metrics.get('midas_native_roundtrip_fixture_native_writeback_ready_count', 0))} |
            repo_ready={int(metrics.get('midas_native_roundtrip_repo_native_writeback_ready_count', 0))} |
            experiment_ready={int(metrics.get('midas_native_roundtrip_experiment_native_writeback_ready_count', 0))}
          </div>
          <div class="note" style="margin-top: 4px;">
            kr_preview_promoted: ready={int(public_structural_preview_ready or 0)} |
            cand={exact_topology_candidate_total} |
            addl_now={additional_exact_topology_candidates}
          </div>
          <div class="note" style="margin-top: 4px;">
            special_member_family: direct_patch={special_member_direct_patch_label} |
            supported={special_member_supported_label} |
            zero_touch_verified={special_member_zero_touch_label}
          </div>
          <div class="note" style="margin-top: 4px;">
            kr_promotion_queue:
            json={artifacts.get('exact_topology_structural_preview_promotion_queue_json', '') or 'n/a'} |
            markdown={artifacts.get('exact_topology_structural_preview_promotion_queue_md', '') or 'n/a'}
          </div>
          <div class="note" style="margin-top: 4px;">
            gate_json={artifacts.get('midas_native_roundtrip_gate_report_json', '') or 'n/a'} |
            receipts_report={artifacts.get('midas_native_roundtrip_receipts_report_json', '') or 'n/a'} |
            appendix_md={artifacts.get('midas_native_roundtrip_appendix_markdown', '') or 'n/a'} |
            appendix_json={artifacts.get('midas_native_roundtrip_appendix_json', '') or 'n/a'}
          </div>
          <div style="margin-top: 10px;">
            <strong>KR Preview Promotion Queue</strong>
            {exact_topology_queue_html}
          </div>
          <div class="note" style="margin-top: 4px;">
            unsupported/lossy appendix: md={artifacts.get('midas_native_roundtrip_appendix_markdown', '') or 'n/a'} | json={artifacts.get('midas_native_roundtrip_appendix_json', '') or 'n/a'}
          </div>
          <div style="margin-top: 10px;">
            <strong>Taxonomy Case Counts</strong>
            {taxonomy_case_counts_html}
          </div>
          <div style="margin-top: 10px;">
            <strong>Taxonomy Card-Family Histogram</strong>
            {taxonomy_card_family_histogram_html}
          </div>
          <table style="margin-top: 12px;">
            <thead>
              <tr><td>Structure Type</td><td>Ready</td><td>Receipts</td><td>Topology</td><td>Load</td><td>LoadComb</td><td>Pending Review</td><td>Batch Markdown</td></tr>
            </thead>
            <tbody>
              {batch_rows_html}
            </tbody>
          </table>
          <table style="margin-top: 12px;">
            <thead>
              <tr><td>Case</td><td>Structure Type</td><td>Mode</td><td>Pass</td><td>Pending Review</td><td>Summary</td><td>Receipt MD</td><td>Receipt JSON</td></tr>
            </thead>
            <tbody>
              {receipt_rows_html}
            </tbody>
          </table>
        </div>
    """


def _irregular_structure_appendix_markdown(source: dict, artifacts: dict) -> list[str]:
    metrics = source.get("metrics") if isinstance(source.get("metrics"), dict) else source
    top5_rows = [row for row in (source.get("irregular_top5_families") or []) if isinstance(row, dict)]
    ready_tasks = [row for row in (source.get("irregular_benchmark_execution_ready_tasks") or []) if isinstance(row, dict)]
    blocked_tasks = [row for row in (source.get("irregular_benchmark_execution_blocked_tasks") or []) if isinstance(row, dict)]
    summary_line = str(
        metrics.get("irregular_structure_summary_line", "") or metrics.get("irregular_structure_track_summary_line", "") or ""
    ).strip()
    benchmark_summary_line = str(metrics.get("irregular_benchmark_execution_summary_line", "") or "").strip()
    if summary_line.lower() == "n/a":
        summary_line = ""
    if benchmark_summary_line.lower() == "n/a":
        benchmark_summary_line = ""
    if not summary_line and not top5_rows and not ready_tasks and not blocked_tasks:
        return []
    counts_line = (
        f"families={int(metrics.get('irregular_structure_family_count', 0))} | "
        f"sources={int(metrics.get('irregular_structure_source_record_count', 0))} | "
        f"local_ready={int(metrics.get('irregular_structure_local_ready_count', 0))} | "
        f"remote_candidates={int(metrics.get('irregular_structure_remote_candidate_count', 0))} | "
        f"collected={int(metrics.get('irregular_structure_collected_count', 0))} | "
        f"native_roundtrip_candidates={int(metrics.get('irregular_structure_native_roundtrip_candidate_count', 0))} | "
        f"solver_candidates={int(metrics.get('irregular_structure_solver_benchmark_candidate_count', 0))} | "
        f"ai_candidates={int(metrics.get('irregular_structure_ai_learning_candidate_count', 0))} | "
        f"top5={int(metrics.get('irregular_structure_top5_count', len(top5_rows)))}"
    )
    visible_top5_rows = [
        row
        for row in top5_rows
        if str(row.get("family_id", "") or "").strip() not in EXTERNAL_ONEPAGE_HIDDEN_IRREGULAR_FAMILY_IDS
    ]
    family_ids = _external_surface_irregular_family_id_list(
        [
            str(row.get("family_id", "") or "").strip()
            for row in visible_top5_rows
            if str(row.get("family_id", "") or "").strip()
        ]
    )
    top5_ready_count = sum(
        1 for row in visible_top5_rows if str(row.get("execution_mode", "") or "").startswith("ready_local")
    )
    top5_remote_count = sum(
        1 for row in visible_top5_rows if str(row.get("execution_mode", "") or "") == "remote_source_hunt_needed"
    )
    lines = [
        "## Appendix: Irregular Structure Track",
        "",
        f"- `track_summary`: `{summary_line or 'n/a'}`",
        f"- `benchmark_manifest`: `{artifacts.get('irregular_benchmark_execution_manifest_json', '') or 'n/a'}`",
        f"- `counts`: `{counts_line}`",
        f"- `top5_split`: `local_ready={top5_ready_count} | remote_needed={top5_remote_count} | family_ids={', '.join(family_ids) or 'n/a'}`",
        f"- `benchmark_execution_summary`: `{benchmark_summary_line or 'n/a'}`",
    ]
    if visible_top5_rows:
        lines.extend(
            [
                "",
                "| Priority | Family | Mode | Local Ready | Remote Needed | KPI Angle | Native Support | Source IDs |",
                "|---:|---|---|---:|---:|---|---|---|",
            ]
        )
        for row in visible_top5_rows:
            lines.append(
                f"| {row.get('priority', '')} | {row.get('family_id', '')} | {row.get('execution_mode_label', row.get('execution_mode', ''))} | "
                f"{row.get('local_ready_source_count', '')} | {row.get('remote_candidate_source_count', '')} | "
                f"{row.get('recommended_kpi_or_validation_angle', '')} | "
                f"{row.get('native_support_summary', '') or 'n/a'} | "
                f"{', '.join(str(item) for item in (row.get('source_ids') or []) if str(item).strip())} |"
            )
    if ready_tasks or blocked_tasks:
        lines.extend(
            [
                "",
                "| Task | Case | Status | Origin | Input | KPI Receipt |",
                "|---|---|---|---|---|---|",
            ]
        )
        for row in ready_tasks + blocked_tasks:
            lines.append(
                f"| {row.get('task_id', '')} | {row.get('case_id', '')} | {row.get('execution_status', '')} | "
                f"{row.get('source_origin_class', '')} | {row.get('input_path', '')} | {row.get('kpi_receipt_path', '')} |"
            )
    return lines


def _write_summary_markdown(path: Path, summary: dict) -> None:
    metrics = summary["metrics"]
    checks = summary["checks"]
    derived = summary["derived"]
    entrypoints = list(summary.get("design_optimization_entrypoints", []))
    entrypoint_groups = list(summary.get("design_optimization_entrypoint_groups", []))
    annotated_groups = annotate_entrypoint_groups(entrypoint_groups)
    artifacts = summary.get("artifacts") if isinstance(summary.get("artifacts"), dict) else {}
    smoke_history_png = str(artifacts.get("nightly_smoke_history_png", "") or "")
    measured_chain_category_png = str(artifacts.get("measured_chain_category_png", "") or "")
    smoke_recent_samples = list(summary.get("nightly_smoke_recent_samples", []))
    holdout_buckets = list(summary.get("residual_holdout_buckets", []))
    holdout_detail_rows = list(summary.get("residual_holdout_detail_rows", []))
    holdout_matrix_rows = list(summary.get("residual_holdout_matrix_rows", []))
    authority_catalog_diff = summary.get("authority_catalog_routing_diff") if isinstance(summary.get("authority_catalog_routing_diff"), dict) else {}
    smoke_trend = summary.get("nightly_smoke_trend") if isinstance(summary.get("nightly_smoke_trend"), dict) else {}
    authority_catalog_warning_active = bool(int(summary.get("authority_catalog_diff_change_count", 0) or 0) > 0)
    promotion_reason_code = str(summary.get("promotion_reason_code", ""))
    promotion_hold_for_review = bool(summary.get("promotion_hold_for_review", False))
    hold_review_manifest = str(summary.get("hold_review_manifest", "") or "")
    hold_review_packet_md = str(summary.get("hold_review_packet_md", "") or "")
    hold_review_packet_pdf = str(summary.get("hold_review_packet_pdf", "") or "")
    hold_review_ack_json = str(summary.get("hold_review_ack_json", "") or "")
    midas_section_library_summary_line = str(metrics.get("midas_section_library_summary_line", "") or "n/a")
    material_constitutive_summary_line = str(metrics.get("material_constitutive_summary_line", "") or "n/a")
    surface_interaction_benchmark_summary_line = str(
        metrics.get("surface_interaction_benchmark_summary_line", "") or "n/a"
    )
    midas_native_roundtrip_summary_line = str(metrics.get("midas_native_roundtrip_summary_line", "") or "n/a")
    midas_native_roundtrip_writeback_diff_summary_line = str(
        metrics.get("midas_native_roundtrip_writeback_diff_summary_line", "") or "n/a"
    )
    korean_native_roundtrip_representative_lines = _render_korean_native_roundtrip_representatives_markdown(summary)
    korean_source_ingest_summary_line = _compact_korean_source_ingest_summary_line(
        str(metrics.get("korean_source_ingest_summary_line", "") or "n/a")
    )
    measured_benchmark_breadth_summary_line = str(
        metrics.get("measured_benchmark_breadth_summary_line", "") or "n/a"
    )
    opensees_canonical_breadth_summary_line = str(
        metrics.get("opensees_canonical_breadth_summary_line", "") or "n/a"
    )
    korean_native_roundtrip_representative_rows = _korean_native_roundtrip_representative_rows(summary)
    korean_structural_preview_queue_summary_line = str(
        metrics.get("korean_structural_preview_queue_summary_line", "") or "n/a"
    )
    korean_structural_preview_queue_summary_line = _compact_korean_structural_preview_queue_summary_line(
        korean_structural_preview_queue_summary_line
    )
    korean_native_roundtrip_representative_rows = _korean_native_roundtrip_representative_rows(summary)
    irregular_structure_summary_line = str(
        metrics.get("irregular_structure_summary_line", "") or metrics.get("irregular_structure_track_summary_line", "") or "n/a"
    )
    irregular_structure_source_catalog_summary_line = (
        f"Irregular source catalog: PASS | families={int(metrics.get('irregular_structure_family_count', 0))} | "
        f"sources={int(metrics.get('irregular_structure_source_record_count', 0))} | "
        f"local_ready={int(metrics.get('irregular_structure_local_ready_count', 0))} | "
        f"remote_candidates={int(metrics.get('irregular_structure_remote_candidate_count', 0))}"
    )
    irregular_structure_triage_summary_line = (
        f"Irregular triage: PASS | native_candidates={int(metrics.get('irregular_structure_native_roundtrip_candidate_count', 0))} | "
        f"solver_candidates={int(metrics.get('irregular_structure_solver_benchmark_candidate_count', 0))} | "
        f"ai_candidates={int(metrics.get('irregular_structure_ai_learning_candidate_count', 0))}"
    )
    irregular_structure_collection_summary_line = (
        f"Irregular collection: PASS | collected={int(metrics.get('irregular_structure_collected_count', 0))} | "
        f"metadata_only_remote_candidate={int(metrics.get('irregular_structure_remote_candidate_count', 0)) - int(metrics.get('irregular_structure_collected_count', 0))} | "
        f"rejected=0"
    )
    irregular_top5_summary_line = (
        f"Irregular top5 manifest: PASS | top5={int(metrics.get('irregular_structure_top5_count', 0))} | "
        f"local_ready={int(metrics.get('irregular_structure_top5_local_ready_count', 0))} | "
        f"remote_needed={int(metrics.get('irregular_structure_top5_remote_needed_count', 0))}"
    )
    irregular_benchmark_execution_summary_line = str(metrics.get("irregular_benchmark_execution_summary_line", "") or "n/a")
    irregular_top5_family_ids = _external_surface_irregular_family_id_list(
        metrics.get("irregular_structure_top5_family_ids", []) or []
    )
    irregular_canonical_promotion_queue_rows = _external_surface_irregular_canonical_promotion_queue_rows(summary)
    irregular_receipt_summary_lines = _render_irregular_benchmark_summary_receipt_markdown(
        summary, artifacts, "artifacts"
    )
    row_provenance_summary_line = str(metrics.get("midas_kds_row_provenance_export_summary_line", "") or "n/a")
    row_provenance_preview_rows = _midas_row_provenance_preview_rows(metrics)
    row_provenance_json = str(artifacts.get("midas_kds_row_provenance_export_json", "") or "n/a")
    row_provenance_csv = str(artifacts.get("midas_kds_row_provenance_export_csv", "") or "n/a")
    row_provenance_report = str(artifacts.get("midas_kds_row_provenance_export_report", "") or "n/a")
    public_raw_ready = metrics.get(
        "midas_native_roundtrip_public_raw_native_writeback_ready_count",
        metrics.get("midas_native_roundtrip_public_raw_native_ready_case_count", 0),
    )
    public_bridge_ready = metrics.get(
        "midas_native_roundtrip_public_bridge_writeback_ready_count",
        metrics.get("midas_native_roundtrip_public_bridge_ready_case_count", 0),
    )
    import html as html_module
    midas_section_library_status_label = (
        "embedded metadata validated" if midas_section_library_summary_line != "n/a" else "validator unavailable"
    )
    midas_section_library_surface_note = (
        "nightly / release gap / committee dashboard / external validation onepage all consume the same validator line"
    )
    lines = [
        "# External Validation One-Page",
        "",
        f"- Generated at: `{summary['generated_at']}`",
        f"- Bundle id: `{summary['bundle_id']}`",
        "",
        "## Gate Status",
        "",
        f"- `nightly_release`: `{checks['nightly_release']}`",
        f"- `ci_gate`: `{checks['ci_gate']}`",
        f"- `static_validation`: `{checks['static_validation']}`",
        f"- `freeze_release`: `{checks['freeze_release']}`",
        f"- `promotion`: `{checks['promotion']}`",
        "",
        "## Integrity",
        "",
        f"- `signed_release_registry`: `{checks['signed_release_registry']}`",
        f"- `registry_signature_verified`: `{checks['registry_signature_verified']}`",
        f"- `solver_hip_e2e`: `{checks['solver_hip_e2e']}`",
        f"- `rc_benchmark_lock`: `{checks['rc_benchmark_lock']}`",
        f"- `ndtha_residual_gate`: `{checks['ndtha_residual_gate']}`",
        f"- `committee_review_package`: `{checks['committee_review_package']}`",
        f"- `midas_section_library_validator`: `{midas_section_library_summary_line}`",
        "",
        "## MIDAS Section Library",
        "",
        f"- `status`: `{midas_section_library_status_label}`",
        f"- `validator_line`: `{midas_section_library_summary_line}`",
        f"- `consumers`: `{midas_section_library_surface_note}`",
        "",
        "## Constitutive / Interaction Coverage",
        "",
        f"- `constitutive_interaction_families`: `{CONSTITUTIVE_INTERACTION_NOTE}`",
        f"- `material_constitutive`: `{material_constitutive_summary_line}`",
        f"- `surface_interaction`: `{surface_interaction_benchmark_summary_line}`",
        "",
        "## MIDAS Native Roundtrip / Write-Back",
        "",
        f"- `roundtrip_gate_summary`: `{midas_native_roundtrip_summary_line}`",
        f"- `writeback_diff_summary`: `{midas_native_roundtrip_writeback_diff_summary_line}`",
        (
            f"- `honest_counts`: corpus={metrics.get('midas_native_roundtrip_corpus_case_count', 0)} | "
            f"native_text={metrics.get('midas_native_roundtrip_native_text_case_count', 0)} | "
            f"ready={metrics.get('midas_native_roundtrip_native_writeback_ready_count', 0)} | "
            f"public_native_ready={metrics.get('midas_native_roundtrip_public_native_writeback_ready_count', 0)} | "
            f"public_preview_ready={metrics.get('midas_native_roundtrip_public_archive_preview_writeback_ready_count', 0)} | "
            f"public_source_ready={metrics.get('midas_native_roundtrip_public_source_writeback_ready_count', 0)} | "
            f"structure_types={metrics.get('midas_native_roundtrip_structure_type_count', 0)} | "
            f"batches={metrics.get('midas_native_roundtrip_structure_type_batch_count', 0)} | "
            f"receipts={metrics.get('midas_native_roundtrip_receipt_count', 0)}/{metrics.get('midas_native_roundtrip_receipt_pass_count', 0)} | "
            f"pending_review={metrics.get('midas_native_roundtrip_pending_review_total', 0)}"
        ),
        f"- `appendix_md`: `{artifacts.get('midas_native_roundtrip_appendix_markdown', '') or 'n/a'}`",
        f"- `appendix_json`: `{artifacts.get('midas_native_roundtrip_appendix_json', '') or 'n/a'}`",
        f"- `receipts_report`: `{artifacts.get('midas_native_roundtrip_receipts_report_json', '') or 'n/a'}`",
        "",
        "## KR Source / Preview",
        "",
        f"- `kr_ingest_summary`: `{korean_source_ingest_summary_line}`",
        f"- `measured_benchmark_breadth`: `{measured_benchmark_breadth_summary_line}`",
        f"- `opensees_canonical_breadth`: `{opensees_canonical_breadth_summary_line}`",
        f"- `kr_preview_queue_summary`: `{korean_structural_preview_queue_summary_line}`",
        "",
        *korean_native_roundtrip_representative_lines,
        "## Irregular Structure Track",
        "",
        f"- `track_summary`: `{irregular_structure_summary_line}`",
        f"- `source_catalog_summary`: `{irregular_structure_source_catalog_summary_line}`",
        f"- `triage_summary`: `{irregular_structure_triage_summary_line}`",
        f"- `collection_summary`: `{irregular_structure_collection_summary_line}`",
        f"- `top5_summary`: `{irregular_top5_summary_line}`",
        f"- `benchmark_execution_summary`: `{irregular_benchmark_execution_summary_line}`",
        f"- `top5_family_ids`: `{', '.join(irregular_top5_family_ids) or 'n/a'}`",
        f"- `benchmark_manifest`: `{artifacts.get('irregular_benchmark_execution_manifest_json', '') or 'n/a'}`",
        *irregular_receipt_summary_lines,
        f"- `canonical_promotion_queue_count`: `{len(irregular_canonical_promotion_queue_rows)}`",
        "- `canonical_promotion_queue_scope`: `only unresolved bridged families shown`",
        "",
        "## Nightly Smoke Probe",
        "",
        f"- `smoke_reason_code`: `{metrics['nightly_smoke_reason_code']}`",
        f"- `smoke_pass_rate`: `{metrics['nightly_smoke_pass_rate']:.2%}`",
        f"- `smoke_trial_feasible_rate`: `{metrics['nightly_smoke_trial_feasible_rate']:.2%}`",
        f"- `smoke_avg_trial_runtime_s`: `{metrics['nightly_smoke_avg_trial_runtime_s']:.4f}`",
        f"- `smoke_history_count`: `{metrics['nightly_smoke_history_count']}`",
        f"- `smoke_strict_recommendation`: `{metrics['nightly_smoke_strict_recommendation']}`",
        "",
    ]
    if irregular_canonical_promotion_queue_rows:
        insert_at = lines.index("## Nightly Smoke Probe")
        queue_lines = [
            "### Bridged To Canonical Promotion Queue",
            "",
            "| Family | Current Source | Status | Canonical Path | Native Support | Blocker |",
            "|---|---|---|---|---|---|",
            "",
        ] + [
            f"| {row.get('family_id', '')} | {row.get('source_id', '')} | {row.get('status', '')} | "
            f"{row.get('promotion_path', '') or 'n/a'} | {row.get('native_support', '') or 'n/a'} | {row.get('blocker', '') or 'n/a'} |"
            for row in irregular_canonical_promotion_queue_rows
        ]
        lines[insert_at:insert_at] = queue_lines + [""]
    if smoke_history_png:
        lines.extend(
            [
                "### Smoke Trend",
                "",
                f"- `smoke_history_png`: `{smoke_history_png}`",
                (
                    "- "
                    f"`runtime_drift`: baseline `{float(smoke_trend.get('baseline_runtime_first_s', 0.0)):.4f}s -> {float(smoke_trend.get('baseline_runtime_last_s', 0.0)):.4f}s` "
                    f"(`{float(smoke_trend.get('baseline_runtime_drift_s', 0.0)):+.4f}s`), "
                    f"trial `{float(smoke_trend.get('trial_runtime_first_s', 0.0)):.4f}s -> {float(smoke_trend.get('trial_runtime_last_s', 0.0)):.4f}s` "
                    f"(`{float(smoke_trend.get('trial_runtime_drift_s', 0.0)):+.4f}s`)"
                ),
                (
                    "- "
                    f"`max_dcr_drift`: baseline `{float(smoke_trend.get('baseline_max_dcr_first', 0.0)):.4f} -> {float(smoke_trend.get('baseline_max_dcr_last', 0.0)):.4f}` "
                    f"(`{float(smoke_trend.get('baseline_max_dcr_drift', 0.0)):+.4f}`), "
                    f"trial `{float(smoke_trend.get('trial_max_dcr_first', 0.0)):.4f} -> {float(smoke_trend.get('trial_max_dcr_last', 0.0)):.4f}` "
                    f"(`{float(smoke_trend.get('trial_max_dcr_drift', 0.0)):+.4f}`)"
                ),
                "",
                f"![Nightly Smoke Trend](artifacts/{smoke_history_png})",
                "",
            ]
        )
    if smoke_recent_samples:
        lines.extend(["### Recent Smoke Samples", "", "| Sample | Generated | Pass | Trial Feasible | Baseline Runtime (s) | Trial Runtime (s) | Trial Max DCR | Action |", "|---:|---|---|---|---:|---:|---:|---|"])
        for row in smoke_recent_samples:
            lines.append(
                f"| {int(row.get('sample_index', 0))} | {row.get('generated_at', '')} | {bool(row.get('contract_pass', False))} | {bool(row.get('trial_feasible', False))} | "
                f"{float(row.get('baseline_runtime_s', 0.0)):.4f} | {float(row.get('trial_runtime_s', 0.0)):.4f} | {float(row.get('trial_max_dcr', 0.0)):.4f} | {row.get('trial_action_name', '')} |"
            )
        lines.append("")
    if measured_chain_category_png:
        lines.extend(
            [
                "### Measured Chain Category Trend",
                "",
                f"- `measured_chain_category_png`: `{measured_chain_category_png}`",
                "",
                f"![Measured Chain Category Trend](artifacts/{measured_chain_category_png})",
                "",
            ]
        )
    if authority_catalog_warning_active:
        lines.extend(
            [
                "## Active Warnings",
                "",
                (
                    f"- `authority_catalog_routing_change`: "
                    f"`changes={int(summary.get('authority_catalog_diff_change_count', 0))}, "
                    f"added={int(summary.get('authority_catalog_diff_added_count', 0))}, "
                    f"removed={int(summary.get('authority_catalog_diff_removed_count', 0))}`"
                ),
                (
                    "- `why`: `Authority/submodel routing changed since the previous committee snapshot and should be explicitly reviewed "
                    "before release promotion or authority-facing reuse.`"
                ),
                "",
            ]
        )
    if promotion_hold_for_review:
        lines.extend(
            [
                "## Active Promotion Hold",
                "",
                f"- `promotion_reason_code`: `{promotion_reason_code}`",
                f"- `hold_review_manifest`: `{hold_review_manifest or 'n/a'}`",
                f"- `hold_review_packet_md`: `{hold_review_packet_md or 'n/a'}`",
                f"- `hold_review_packet_pdf`: `{hold_review_packet_pdf or 'n/a'}`",
                f"- `hold_review_ack_json`: `{hold_review_ack_json or 'n/a'}`",
                "- `why`: `Release candidate remains on hold until the authority-routing hold review manifest is cleared by engineer review.`",
                "",
            ]
        )
    lines.extend([
        "## Key Metrics",
        "",
        f"- `commercial_grade`: `{metrics['commercial_grade']}`",
        f"- `deployment_model`: `{metrics['deployment_model']}`",
        f"- `accelerated_coverage_target`: `{metrics['accelerated_coverage_target_pct_label']}`",
        f"- `residual_holdout_target`: `{metrics['residual_holdout_target_pct_label']}`",
        f"- `estimated_time_saved`: `{metrics['estimated_time_saved_pct_label']}`",
        (
            f"- `measured_chain_wall_clock_comparable_rolling_min`: "
            f"`{metrics.get('measured_chain_rolling_total_minutes_mean', 0.0):.2f}` "
            f"(N={int(metrics.get('measured_chain_rolling_sample_count', 0))}, "
            f"range={metrics.get('measured_chain_rolling_total_minutes_range', ['n/a', 'n/a'])[0]}-"
            f"{metrics.get('measured_chain_rolling_total_minutes_range', ['n/a', 'n/a'])[1]})"
        ),
        f"- `measured_chain_wall_clock_min`: `{metrics['measured_chain_total_minutes']:.2f}`",
        f"- `comparable_run_selection_mode`: `{metrics.get('measured_chain_rolling_selection_mode', '')}`",
        f"- `comparable_reference_deployment_model`: `{metrics.get('measured_chain_comparable_reference_deployment_model', '')}`",
        f"- `comparable_reference_strict_smoke`: `{bool(metrics.get('measured_chain_comparable_reference_strict_design_opt_cost_smoke', False))}`",
        f"- `engineer_in_loop_accelerated_coverage_ready`: `{metrics['engineer_in_loop_accelerated_coverage_ready']}`",
        f"- `empirical_smoke_runtime_reduction`: `{metrics['empirical_smoke_runtime_saved_pct_label']}`",
        f"- `estimated_time_saved_basis`: `{metrics['estimated_time_saved_basis']}`",
        f"- `time_saving_focus`: `{metrics['time_saving_focus']}`",
        f"- `full_commercial_replacement_ready`: `{metrics['full_commercial_replacement_ready']}`",
        f"- `external_benchmark_submission_ready_to_start_now`: `{bool(metrics.get('external_benchmark_submission_ready_to_start_now', False))}`",
        f"- `external_benchmark_submission_ready_to_start_full_submission_now`: `{bool(metrics.get('external_benchmark_submission_ready_to_start_full_submission_now', False))}`",
        f"- `external_benchmark_submission_reason_code`: `{metrics.get('external_benchmark_submission_reason_code', '')}`",
        f"- `external_benchmark_submission_recommended_start_mode`: `{metrics.get('external_benchmark_submission_recommended_start_mode', '')}`",
        f"- `external_benchmark_submission_recommended_submission_scope`: `{metrics.get('external_benchmark_submission_recommended_submission_scope', '')}`",
        f"- `external_benchmark_submission_blocker_label`: `{metrics.get('external_benchmark_submission_blocker_label', '') or 'none'}`",
        f"- `external_benchmark_submission_caution_label`: `{metrics.get('external_benchmark_submission_caution_label', '') or 'none'}`",
        f"- `external_benchmark_execution_mode`: `{metrics.get('external_benchmark_execution_mode', '')}`",
        f"- `external_benchmark_execution_ready_task_count`: `{int(metrics.get('external_benchmark_execution_ready_task_count', 0))}`",
        f"- `external_benchmark_execution_blocked_task_count`: `{int(metrics.get('external_benchmark_execution_blocked_task_count', 0))}`",
        f"- `external_benchmark_execution_review_boundary_pending_count`: `{int(metrics.get('external_benchmark_execution_review_boundary_pending_count', 0))}`",
        f"- `external_benchmark_execution_review_boundary_resolution_label`: `{metrics.get('external_benchmark_execution_review_boundary_resolution_label', '') or 'n/a'}`",
        f"- `external_benchmark_execution_review_boundary_owner_label`: `{metrics.get('external_benchmark_execution_review_boundary_owner_label', '') or 'none'}`",
        f"- `external_benchmark_execution_review_boundary_assignee_label`: `{metrics.get('external_benchmark_execution_review_boundary_assignee_label', '') or 'none'}`",
        f"- `external_benchmark_execution_review_boundary_assignment_status_label`: `{metrics.get('external_benchmark_execution_review_boundary_assignment_status_label', '') or 'none'}`",
        f"- `external_benchmark_execution_review_boundary_priority_label`: `{metrics.get('external_benchmark_execution_review_boundary_priority_label', '') or 'none'}`",
        f"- `external_benchmark_execution_review_boundary_family_label`: `{metrics.get('external_benchmark_execution_review_boundary_family_label', '') or 'none'}`",
        f"- `external_benchmark_execution_review_boundary_change_count_total`: `{int(metrics.get('external_benchmark_execution_review_boundary_change_count_total', 0))}`",
        f"- `external_benchmark_execution_review_boundary_followup_action_label`: `{metrics.get('external_benchmark_execution_review_boundary_followup_action_label', '') or 'none'}`",
        f"- `external_benchmark_execution_review_boundary_sla_state_label`: `{metrics.get('external_benchmark_execution_review_boundary_sla_state_label', '') or 'none'}`",
        f"- `external_benchmark_execution_review_boundary_age_bucket_label`: `{metrics.get('external_benchmark_execution_review_boundary_age_bucket_label', '') or 'none'}`",
        f"- `external_benchmark_execution_review_boundary_overdue_count`: `{int(metrics.get('external_benchmark_execution_review_boundary_overdue_count', 0))}`",
        f"- `external_benchmark_execution_review_boundary_oldest_open_age_hours`: `{float(metrics.get('external_benchmark_execution_review_boundary_oldest_open_age_hours', 0.0)):.3f}`",
        f"- `external_benchmark_execution_status_mode`: `{metrics.get('external_benchmark_execution_status_mode', '')}`",
        f"- `external_benchmark_execution_planned_task_count`: `{int(metrics.get('external_benchmark_execution_planned_task_count', 0))}`",
        f"- `external_benchmark_execution_in_progress_task_count`: `{int(metrics.get('external_benchmark_execution_in_progress_task_count', 0))}`",
        f"- `external_benchmark_execution_completed_task_count`: `{int(metrics.get('external_benchmark_execution_completed_task_count', 0))}`",
        f"- `external_benchmark_execution_failed_task_count`: `{int(metrics.get('external_benchmark_execution_failed_task_count', 0))}`",
        f"- `external_benchmark_execution_finished_task_count`: `{int(metrics.get('external_benchmark_execution_finished_task_count', 0))}`",
        f"- `external_benchmark_execution_completion_ratio`: `{float(metrics.get('external_benchmark_execution_completion_ratio', 0.0)):.3f}`",
        f"- `external_benchmark_case_onepage_count`: `{int(metrics.get('external_benchmark_case_onepage_count', 0))}`",
        f"- `external_benchmark_case_onepage_dir`: `{artifacts.get('external_benchmark_case_onepage_dir', '') or 'n/a'}`",
        (
            f"- `external_benchmark_case_attestation_workflow`: `cases={int(metrics.get('external_benchmark_case_attestation_case_count', 0))} | "
            f"manifests={int(metrics.get('external_benchmark_case_attestation_manifest_count', 0))} | "
            f"templates={int(metrics.get('external_benchmark_case_attestation_template_count', 0))} | "
            f"receipts={int(metrics.get('external_benchmark_case_attestation_receipt_count', 0))} | "
            f"attested={int(metrics.get('external_benchmark_case_attestation_attested_count', 0))} | "
            f"source={metrics.get('external_benchmark_case_attestation_source_label', '') or 'none'} | "
            f"status={metrics.get('external_benchmark_case_attestation_status_label', '') or 'none'} | "
            f"kickoff_index={artifacts.get('external_benchmark_case_attestation_index_json', '') or 'n/a'}`"
        ),
        f"- `audit_review_decision_batch_template_item_count`: `{int(metrics.get('audit_review_decision_batch_template_item_count', 0))}`",
        f"- `audit_review_decision_batch_template_current_status_label`: `{metrics.get('audit_review_decision_batch_template_current_status_label', '')}`",
        f"- `audit_review_decision_batch_template_review_owner_label`: `{metrics.get('audit_review_decision_batch_template_review_owner_label', '')}`",
        f"- `audit_review_decision_batch_template_review_priority_label`: `{metrics.get('audit_review_decision_batch_template_review_priority_label', '')}`",
        f"- `audit_review_decision_batch_attested_example_count`: `{int(metrics.get('audit_review_decision_batch_attested_example_count', 0))}`",
        f"- `audit_review_decision_batch_attested_example_preview_label`: `{metrics.get('audit_review_decision_batch_attested_example_preview_label', '') or 'none'}`",
        f"- `external_benchmark_submission_preview_approve_all_reason_code`: `{metrics.get('external_benchmark_submission_preview_approve_all_reason_code', '')}`",
        f"- `external_benchmark_submission_preview_approve_all_ready_full`: `{bool(metrics.get('external_benchmark_submission_preview_approve_all_ready_full', False))}`",
        f"- `external_benchmark_submission_preview_approve_all_pending_count`: `{int(metrics.get('external_benchmark_submission_preview_approve_all_pending_count', 0))}`",
        f"- `external_benchmark_submission_preview_approve_all_open_revision_count`: `{int(metrics.get('external_benchmark_submission_preview_approve_all_open_revision_count', 0))}`",
        f"- `external_benchmark_submission_preview_reject_one_reason_code`: `{metrics.get('external_benchmark_submission_preview_reject_one_reason_code', '')}`",
        f"- `external_benchmark_submission_preview_reject_one_ready_full`: `{bool(metrics.get('external_benchmark_submission_preview_reject_one_ready_full', False))}`",
        f"- `external_benchmark_submission_preview_reject_one_pending_count`: `{int(metrics.get('external_benchmark_submission_preview_reject_one_pending_count', 0))}`",
        f"- `external_benchmark_submission_preview_reject_one_open_revision_count`: `{int(metrics.get('external_benchmark_submission_preview_reject_one_open_revision_count', 0))}`",
        f"- `external_benchmark_submission_preview_reject_one_blocker_label`: `{metrics.get('external_benchmark_submission_preview_reject_one_blocker_label', '') or 'none'}`",
        f"- `audit_review_decision_batch_runner_reason_code`: `{metrics.get('audit_review_decision_batch_runner_reason_code', '')}`",
        f"- `audit_review_decision_batch_runner_apply_live`: `{bool(metrics.get('audit_review_decision_batch_runner_apply_live', False))}`",
        f"- `audit_review_decision_batch_runner_live_applied`: `{bool(metrics.get('audit_review_decision_batch_runner_live_applied', False))}`",
        f"- `audit_review_decision_batch_runner_preview_reason_code`: `{metrics.get('audit_review_decision_batch_runner_preview_reason_code', '') or 'none'}`",
        f"- `audit_review_decision_batch_runner_preview_ready_full`: `{bool(metrics.get('audit_review_decision_batch_runner_preview_ready_full', False))}`",
        f"- `audit_review_decision_batch_runner_preview_pending_count`: `{int(metrics.get('audit_review_decision_batch_runner_preview_pending_count', 0))}`",
        f"- `audit_review_decision_batch_runner_preview_open_revision_count`: `{int(metrics.get('audit_review_decision_batch_runner_preview_open_revision_count', 0))}`",
        f"- `structural_optimization_viewer_html`: `{metrics.get('structural_optimization_viewer_html', '') or 'n/a'}`",
        f"- `optimized_drawing_review_html`: `{metrics.get('optimized_drawing_review_html', '') or 'n/a'}`",
        f"- `optimized_drawing_review_axis_source_mode`: `{metrics.get('optimized_drawing_review_axis_source_mode', '') or 'n/a'}`",
        f"- `optimized_drawing_review_axis_preview_label`: `{metrics.get('optimized_drawing_review_axis_preview_label', '') or 'n/a'}`",
        f"- `structural_optimization_viewer_mode`: `{metrics.get('structural_optimization_viewer_mode', '') or 'n/a'}`",
        f"- `structural_optimization_viewer_story_zone_nonempty_cell_count`: `{int(metrics.get('structural_optimization_viewer_story_zone_nonempty_cell_count', 0))}`",
        f"- `structural_optimization_viewer_story_zone_max_abs_cost_proxy_delta`: `{float(metrics.get('structural_optimization_viewer_story_zone_max_abs_cost_proxy_delta', 0.0)):.3f}`",
        f"- `structural_optimization_viewer_gallery_tile_count`: `{int(metrics.get('structural_optimization_viewer_gallery_tile_count', 0))}`",
        f"- `promotion_reason_code`: `{metrics.get('promotion_reason_code', '')}`",
        f"- `promotion_hold_for_review`: `{bool(metrics.get('promotion_hold_for_review', False))}`",
        f"- `hold_review_manifest`: `{metrics.get('hold_review_manifest', '')}`",
        f"- `hold_review_packet_md`: `{metrics.get('hold_review_packet_md', '')}`",
        f"- `hold_review_packet_pdf`: `{metrics.get('hold_review_packet_pdf', '')}`",
        f"- `hold_review_ack_json`: `{metrics.get('hold_review_ack_json', '')}`",
        f"- `open_gap_counts`: `P0={metrics['open_gap_p0']}, P1={metrics['open_gap_p1']}, P2={metrics['open_gap_p2']}`",
        f"- `midas_element_rows_total`: `{metrics['midas_element_rows_total']}`",
        f"- `midas_element_rows_skipped`: `{metrics['midas_element_rows_skipped']}`",
        f"- `midas_unknown_row_total`: `{metrics['midas_unknown_row_total']}`",
        f"- `midas_semantic_load_binding_pass`: `{bool(metrics.get('midas_semantic_load_binding_pass', False))}`",
        f"- `midas_use_stld_block_count`: `{int(metrics.get('midas_use_stld_block_count', 0))}`",
        f"- `midas_semantic_load_case_count`: `{int(metrics.get('midas_semantic_load_case_count', 0))}`",
        f"- `midas_semantic_load_combination_count`: `{int(metrics.get('midas_semantic_load_combination_count', 0))}`",
        f"- `midas_bound_unbound_load_rows`: `nodal={int(metrics.get('midas_bound_nodal_load_row_count', 0))}/{int(metrics.get('midas_unbound_nodal_load_row_count', 0))}, selfweight={int(metrics.get('midas_bound_selfweight_row_count', 0))}/{int(metrics.get('midas_unbound_selfweight_row_count', 0))}, pressure={int(metrics.get('midas_bound_pressure_row_count', 0))}/{int(metrics.get('midas_unbound_pressure_row_count', 0))}`",
        f"- `mgt_export_artifact_exists`: `{bool(metrics.get('mgt_export_artifact_exists', False))}`",
        f"- `mgt_export_contract_pass`: `{bool(metrics.get('mgt_export_contract_pass', False))}`",
        f"- `mgt_export_support_mode`: `{metrics.get('mgt_export_support_mode', '')}`",
        f"- `mgt_export_supported_change_count`: `{int(metrics.get('mgt_export_supported_change_count', 0))}`",
        f"- `mgt_export_unsupported_change_count`: `{int(metrics.get('mgt_export_unsupported_change_count', 0))}`",
        f"- `mgt_export_direct_patch_change_count`: `{int(metrics.get('mgt_export_direct_patch_change_count', 0))}`",
        f"- `mgt_export_direct_patch_action_family_label`: `{metrics.get('mgt_export_direct_patch_action_family_label', '')}`",
        f"- `mgt_export_special_member_direct_patch_action_family_label`: `{metrics.get('mgt_export_special_member_direct_patch_action_family_label', '')}`",
        f"- `mgt_export_special_member_supported_action_family_label`: `{metrics.get('mgt_export_special_member_supported_action_family_label', '')}`",
        f"- `mgt_export_special_member_zero_touch_verified_action_family_label`: `{metrics.get('mgt_export_special_member_zero_touch_verified_action_family_label', '')}`",
        f"- `mgt_export_rebar_payload_namespace_mode`: `{metrics.get('mgt_export_rebar_payload_namespace_mode', '')}`",
        f"- `mgt_export_rebar_delivery_mode`: `{metrics.get('mgt_export_rebar_delivery_mode', '')}`",
        f"- `mgt_export_evidence_model`: `{metrics.get('mgt_export_evidence_model', '')}`",
        f"- `mgt_export_delivery_boundary`: `direct_patch={metrics.get('mgt_export_direct_patch_action_family_label', '') or 'n/a'} | "
        f"sidecar={metrics.get('mgt_export_instruction_sidecar_action_family_label', '') or 'n/a'} | "
        f"connection_payload={metrics.get('mgt_export_connection_detailing_delivery_mode', '') or 'n/a'} | "
        f"detailing_payload={metrics.get('mgt_export_detailing_delivery_mode', '') or 'n/a'}`",
        f"- `mgt_export_rebar_payload_material_level_namespace_present`: `{bool(metrics.get('mgt_export_rebar_payload_material_level_namespace_present', False))}`",
        f"- `mgt_export_rebar_payload_group_local_namespace_present`: `{bool(metrics.get('mgt_export_rebar_payload_group_local_namespace_present', False))}`",
        f"- `mgt_export_material_level_rebar_payloads`: `{int(metrics.get('mgt_export_material_level_rebar_payload_available_count', 0))}/{int(metrics.get('mgt_export_material_level_rebar_payload_row_count', 0))}`",
        f"- `mgt_export_group_local_rebar_payload_row_count`: `{int(metrics.get('mgt_export_group_local_rebar_payload_available_count', 0))}/{int(metrics.get('mgt_export_group_local_rebar_payload_row_count', 0))}`",
        f"- `mgt_export_connection_detailing_payload_namespace_mode`: `{metrics.get('mgt_export_connection_detailing_payload_namespace_mode', '')}`",
        f"- `mgt_export_connection_detailing_payload_group_local_namespace_present`: `{bool(metrics.get('mgt_export_connection_detailing_payload_group_local_namespace_present', False))}`",
        f"- `mgt_export_group_local_connection_detailing_payload_row_count`: `{int(metrics.get('mgt_export_group_local_connection_detailing_payload_available_count', 0))}/{int(metrics.get('mgt_export_group_local_connection_detailing_payload_row_count', 0))}`",
        f"- `mgt_export_connection_detailing_direct_patch_eligible_change_count`: `{int(metrics.get('mgt_export_connection_detailing_direct_patch_eligible_change_count', 0))}`",
        f"- `mgt_export_detailing_payload_namespace_mode`: `{metrics.get('mgt_export_detailing_payload_namespace_mode', '')}`",
        f"- `mgt_export_detailing_payload_group_local_namespace_present`: `{bool(metrics.get('mgt_export_detailing_payload_group_local_namespace_present', False))}`",
        f"- `mgt_export_group_local_detailing_payload_row_count`: `{int(metrics.get('mgt_export_group_local_detailing_payload_available_count', 0))}/{int(metrics.get('mgt_export_group_local_detailing_payload_row_count', 0))}`",
        f"- `mgt_export_detailing_direct_patch_eligible_change_count`: `{int(metrics.get('mgt_export_detailing_direct_patch_eligible_change_count', 0))}`",
        f"- `mgt_export_connection_detailing_structured_payload_mapped_change_count`: `{int(metrics.get('mgt_export_connection_detailing_structured_payload_mapped_change_count', 0))}`",
        f"- `mgt_export_detailing_structured_payload_mapped_change_count`: `{int(metrics.get('mgt_export_detailing_structured_payload_mapped_change_count', 0))}`",
        f"- `mgt_export_connection_detailing_delivery_mode`: `{metrics.get('mgt_export_connection_detailing_delivery_mode', '')}`",
        f"- `mgt_export_detailing_delivery_mode`: `{metrics.get('mgt_export_detailing_delivery_mode', '')}`",
        f"- `mgt_export_rebar_direct_patch_eligible_change_count`: `{int(metrics.get('mgt_export_rebar_direct_patch_eligible_change_count', 0))}`",
        f"- `mgt_export_patched_material_row_count`: `{int(metrics.get('mgt_export_patched_material_row_count', 0))}`",
        f"- `mgt_export_cloned_material_count`: `{int(metrics.get('mgt_export_cloned_material_count', 0))}`",
        f"- `mgt_export_rebar_direct_patch_ineligible_reason_label`: `{metrics.get('mgt_export_rebar_direct_patch_ineligible_reason_label', '')}`",
        f"- `mgt_export_rebar_direct_patch_mapping_source_label`: `{metrics.get('mgt_export_rebar_direct_patch_mapping_source_label', '')}`",
        f"- `mgt_export_instruction_sidecar_change_count`: `{int(metrics.get('mgt_export_instruction_sidecar_change_count', 0))}`",
        f"- `mgt_export_instruction_sidecar_action_family_label`: `{metrics.get('mgt_export_instruction_sidecar_action_family_label', '') or 'n/a'}`",
        f"- `mgt_export_instruction_sidecar_audit_only_action_family_label`: `{metrics.get('mgt_export_instruction_sidecar_audit_only_action_family_label', '') or 'n/a'}` ({int(metrics.get('mgt_export_instruction_sidecar_audit_only_change_count', 0))})",
        f"- `mgt_export_instruction_sidecar_manual_input_action_family_label`: `{metrics.get('mgt_export_instruction_sidecar_manual_input_action_family_label', '') or 'n/a'}` ({int(metrics.get('mgt_export_instruction_sidecar_manual_input_change_count', 0))})",
        f"- `mgt_export_audit_review_manifest_action_family_label`: `{metrics.get('mgt_export_audit_review_manifest_action_family_label', '') or 'n/a'}` ({int(metrics.get('mgt_export_audit_review_manifest_change_count', 0))})",
        f"- `mgt_export_audit_review_packet_action_family_label`: `{metrics.get('mgt_export_audit_review_packet_action_family_label', '') or 'n/a'}` ({int(metrics.get('mgt_export_audit_review_packet_count', 0))})",
        f"- `mgt_export_audit_review_packet_followup_type_label`: `{metrics.get('mgt_export_audit_review_packet_followup_type_label', '') or 'n/a'}`",
        f"- `mgt_export_audit_review_packet_file_action_family_label`: `{metrics.get('mgt_export_audit_review_packet_file_action_family_label', '') or 'n/a'}` ({int(metrics.get('mgt_export_audit_review_packet_file_count', 0))})",
        f"- `mgt_export_audit_review_queue_action_family_label`: `{metrics.get('mgt_export_audit_review_queue_action_family_label', '') or 'n/a'}` ({int(metrics.get('mgt_export_audit_review_queue_item_count', 0))})",
        f"- `mgt_export_audit_review_queue_status_label`: `{metrics.get('mgt_export_audit_review_queue_status_label', '') or 'n/a'}`",
        f"- `mgt_export_audit_review_followup_action_label`: `{metrics.get('mgt_export_audit_review_followup_action_label', '') or 'n/a'}` ({int(metrics.get('mgt_export_audit_review_followup_item_count', 0))})",
        f"- `mgt_export_audit_review_followup_owner_label`: `{metrics.get('mgt_export_audit_review_followup_owner_label', '') or 'n/a'}`",
        f"- `mgt_export_audit_review_followup_review_owner_label`: `{metrics.get('mgt_export_audit_review_followup_review_owner_label', '') or 'n/a'}`",
        f"- `mgt_export_audit_review_followup_status_label`: `{metrics.get('mgt_export_audit_review_followup_status_label', '') or 'n/a'}`",
        f"- `mgt_export_audit_review_followup_sla_state_label`: `{metrics.get('mgt_export_audit_review_followup_sla_state_label', '') or 'n/a'}`",
        f"- `mgt_export_audit_review_followup_age_bucket_label`: `{metrics.get('mgt_export_audit_review_followup_age_bucket_label', '') or 'n/a'}`",
        f"- `mgt_export_audit_review_followup_overdue_item_count`: `{int(metrics.get('mgt_export_audit_review_followup_overdue_item_count', 0))}`",
        f"- `mgt_export_audit_review_resolution_action_label`: `{metrics.get('mgt_export_audit_review_resolution_action_label', '') or 'n/a'}` ({int(metrics.get('mgt_export_audit_review_resolution_item_count', 0))})",
        f"- `mgt_export_audit_review_resolution_owner_label`: `{metrics.get('mgt_export_audit_review_resolution_owner_label', '') or 'n/a'}`",
        f"- `mgt_export_audit_review_resolution_status_label`: `{metrics.get('mgt_export_audit_review_resolution_status_label', '') or 'n/a'}`",
        f"- `mgt_export_instruction_sidecar_review_priority_label`: `{metrics.get('mgt_export_instruction_sidecar_review_priority_label', '')}`",
        f"- `mgt_export_instruction_sidecar_followup_type_label`: `{metrics.get('mgt_export_instruction_sidecar_followup_type_label', '')}`",
        f"- `mgt_export_cloned_section_count`: `{int(metrics.get('mgt_export_cloned_section_count', 0))}`",
        f"- `mgt_export_cloned_thickness_count`: `{int(metrics.get('mgt_export_cloned_thickness_count', 0))}`",
        f"- `mgt_export_retargeted_element_row_count`: `{int(metrics.get('mgt_export_retargeted_element_row_count', 0))}`",
        f"- `kds_compliance_rows`: `{metrics['kds_compliance_rows']}`",
        f"- `kds_member_check_rows`: `{metrics['kds_member_check_rows']}`",
        f"- `kds_clause_count`: `{metrics['kds_clause_count']}`",
        f"- `ndtha_residual_top_m_max_abs`: `{metrics['ndtha_residual_top_m_max_abs']}`",
        f"- `ndtha_residual_drift_pct_max_abs`: `{metrics['ndtha_residual_drift_pct_max_abs']}`",
        f"- `ndtha_residual_fallback_rate`: `{metrics['ndtha_residual_fallback_rate']}`",
        f"- `registry_artifact_count`: `{metrics['registry_artifact_count']}`",
        f"- `design_opt_long_feasible`: `{metrics['design_opt_long_feasible']}`",
        f"- `design_opt_long_final_max_dcr`: `{metrics['design_opt_long_final_max_dcr']}`",
        f"- `design_opt_raw_max_drift_pct`: `{metrics.get('design_opt_raw_max_drift_pct', 0.0)}`",
        f"- `design_opt_repaired_compliance_max_drift_pct`: `{metrics.get('design_opt_repaired_compliance_max_drift_pct', 0.0)}`",
        f"- `design_opt_compliance_basis`: `{metrics.get('design_opt_compliance_basis', '')}`",
        f"- `design_opt_repair_action_count`: `{metrics.get('design_opt_repair_action_count', 0)}`",
        f"- `design_opt_constructability_signal_gain_pct`: `{metrics.get('design_opt_constructability_signal_gain_pct', 0.0)}`",
        f"- `design_opt_constructability_avg`: `{metrics.get('design_opt_baseline_constructability_avg', 0.0)} -> {metrics.get('design_opt_final_constructability_avg', 0.0)}`",
        f"- `design_opt_detailing_complexity_avg`: `{metrics.get('design_opt_baseline_detailing_complexity_avg', 0.0)} -> {metrics.get('design_opt_final_detailing_complexity_avg', 0.0)}`",
        f"- `design_opt_selected_family_mix`: `{metrics.get('design_opt_selected_family_mix_label', '')}`",
        f"- `design_opt_selected_dominant_family`: `{metrics.get('design_opt_selected_dominant_family', '')}` ({metrics.get('design_opt_selected_dominant_family_ratio', 0.0):.2%})",
        f"- `design_opt_selected_family_mix_trend`: `{metrics.get('design_opt_selected_family_trend_label', '')}`",
        f"- `design_opt_previous_dominant_family`: `{metrics.get('design_opt_previous_dominant_family', '')}` ({metrics.get('design_opt_previous_dominant_family_ratio', 0.0):.2%})",
        f"- `design_opt_preview_supply_family_mix`: `{metrics.get('design_opt_preview_supply_family_mix_label', '')}`",
        f"- `design_opt_preview_missing_target_families`: `{metrics.get('design_opt_preview_missing_target_families_label', '')}`",
        f"- `design_opt_cost_delta`: `{metrics['design_opt_cost_delta']}`",
        f"- `design_opt_changed_group_count`: `{metrics['design_opt_changed_group_count']}`",
        f"- `design_opt_blocked_action_row_count`: `{metrics['design_opt_blocked_action_row_count']}`",
        f"- `design_opt_blocked_illegal_by_mask`: `{metrics['design_opt_blocked_illegal_by_mask']}`",
        f"- `design_opt_blocked_illegal_by_mask_family_label`: `{metrics.get('design_opt_blocked_illegal_by_mask_family_label', '')}`",
        f"- `design_opt_blocked_no_cost_gain`: `{metrics['design_opt_blocked_no_cost_gain']}`",
        f"- `design_opt_blocked_constructability_hard_gate`: `{metrics.get('design_opt_blocked_constructability_hard_gate', 0)}`",
        f"- `design_opt_blocked_constructability_hard_gate_label`: `{metrics.get('design_opt_blocked_constructability_hard_gate_label', '')}`",
        f"- `design_opt_blocked_constructability_hard_gate_family_label`: `{metrics.get('design_opt_blocked_constructability_hard_gate_family_label', '')}`",
        f"- `design_opt_blocked_no_cost_group_count`: `{metrics['design_opt_blocked_no_cost_group_count']}`",
        f"- `design_opt_blocked_no_cost_explain_row_count`: `{metrics['design_opt_blocked_no_cost_explain_row_count']}`",
        f"- `design_opt_entrypoint_report_count`: `{metrics['design_opt_entrypoint_report_count']}`",
        f"- `design_opt_entrypoint_pass_count`: `{metrics['design_opt_entrypoint_pass_count']}`",
        "",
        "## Advanced Holdouts",
        "",
        f"- `pbd_dynamic_hinge_refresh_ready`: `{bool(metrics.get('pbd_dynamic_hinge_refresh_ready', False))}` ({metrics.get('pbd_hinge_state_mode', '')})",
        f"- `pbd_hinge_refresh_reason`: `{metrics.get('pbd_hinge_refresh_reason', '')}`",
        f"- `pbd_hinge_refresh_artifact_present`: `{bool(metrics.get('pbd_hinge_refresh_artifact_present', False))}`",
        f"- `pbd_hinge_refresh_artifact_kind`: `{metrics.get('pbd_hinge_refresh_artifact_kind', '')}`",
        f"- `pbd_hinge_refresh_source_mode`: `{metrics.get('pbd_hinge_refresh_source_mode', '')}`",
        f"- `pbd_hinge_refresh_overlap_member_count`: `{int(metrics.get('pbd_hinge_refresh_overlap_member_count', 0))}`",
        f"- `pbd_hinge_refresh_rebar_sensitive_member_count`: `{int(metrics.get('pbd_hinge_refresh_rebar_sensitive_member_count', 0))}`",
        f"- `pbd_hinge_benchmark_gate_pass`: `{bool(metrics.get('pbd_hinge_benchmark_gate_pass', False))}`",
        f"- `pbd_hinge_benchmark_fixture_regression_pass`: `{bool(metrics.get('pbd_hinge_benchmark_fixture_regression_pass', False))}`",
        f"- `pbd_hinge_benchmark_alignment_pass`: `{bool(metrics.get('pbd_hinge_benchmark_alignment_pass', False))}`",
        f"- `pbd_hinge_benchmark_asset_count`: `{int(metrics.get('pbd_hinge_benchmark_asset_count', 0))}`",
        f"- `pbd_hinge_benchmark_split`: `train={int(metrics.get('pbd_hinge_benchmark_train_count', 0))}, val={int(metrics.get('pbd_hinge_benchmark_val_count', 0))}, holdout={int(metrics.get('pbd_hinge_benchmark_holdout_count', 0))}`",
        f"- `pbd_hinge_benchmark_rebar_sensitive_count`: `{int(metrics.get('pbd_hinge_benchmark_rebar_sensitive_count', 0))}`",
        f"- `pbd_hinge_benchmark_confinement_sensitive_count`: `{int(metrics.get('pbd_hinge_benchmark_confinement_sensitive_count', 0))}`",
        f"- `pbd_hinge_benchmark_fixture_count`: `{int(metrics.get('pbd_hinge_benchmark_fixture_count', 0))}`",
        f"- `pbd_hinge_benchmark_fixture_min_point_count`: `{int(metrics.get('pbd_hinge_benchmark_fixture_min_point_count', 0))}`",
        f"- `pbd_hinge_benchmark_fixture_min_peak_drift_ratio`: `{float(metrics.get('pbd_hinge_benchmark_fixture_min_peak_drift_ratio', 0.0))}`",
        f"- `pbd_hinge_benchmark_alignment_refresh_column_row_count`: `{int(metrics.get('pbd_hinge_benchmark_alignment_refresh_column_row_count', 0))}`",
        f"- `pbd_hinge_benchmark_alignment_rebar_sensitive_column_count`: `{int(metrics.get('pbd_hinge_benchmark_alignment_rebar_sensitive_column_count', 0))}`",
        f"- `pbd_hinge_benchmark_alignment_benchmark_rebar_ratio_min`: `{float(metrics.get('pbd_hinge_benchmark_alignment_benchmark_rebar_ratio_min', 0.0))}`",
        f"- `pbd_hinge_benchmark_alignment_benchmark_rebar_ratio_max`: `{float(metrics.get('pbd_hinge_benchmark_alignment_benchmark_rebar_ratio_max', 0.0))}`",
        f"- `pbd_hinge_benchmark_alignment_refresh_rebar_ratio_min`: `{float(metrics.get('pbd_hinge_benchmark_alignment_refresh_rebar_ratio_min', 0.0))}`",
        f"- `pbd_hinge_benchmark_alignment_refresh_rebar_ratio_max`: `{float(metrics.get('pbd_hinge_benchmark_alignment_refresh_rebar_ratio_max', 0.0))}`",
        f"- `panel_zone_3d_clash_ready`: `{bool(metrics.get('panel_zone_3d_clash_ready', False))}` ({metrics.get('panel_zone_constructability_mode', '')})",
        f"- `panel_zone_constructability_reason`: `{metrics.get('panel_zone_constructability_reason', '')}`",
        f"- `panel_zone_source_contract_mode`: `{metrics.get('panel_zone_source_contract_mode', '')}`",
        f"- `panel_zone_internal_engine_complete`: `{bool(metrics.get('panel_zone_internal_engine_complete', False))}`",
        f"- `panel_zone_external_validation_pending`: `{bool(metrics.get('panel_zone_external_validation_pending', False))}`",
        f"- `panel_zone_validation_boundary`: `{metrics.get('panel_zone_validation_boundary', '')}`",
        f"- `panel_zone_source_artifact_kind`: `{metrics.get('panel_zone_source_artifact_kind', '')}`",
        f"- `panel_zone_proxy_candidate_count`: `{int(metrics.get('panel_zone_proxy_candidate_count', 0))}`",
        f"- `panel_zone_instruction_sidecar_present`: `{bool(metrics.get('panel_zone_instruction_sidecar_present', False))}`",
        f"- `panel_zone_instruction_sidecar_change_count`: `{int(metrics.get('panel_zone_instruction_sidecar_change_count', 0))}`",
        f"- `panel_zone_instruction_sidecar_candidate_overlap_mode`: `{metrics.get('panel_zone_instruction_sidecar_candidate_overlap_mode', '')}`",
        f"- `panel_zone_instruction_sidecar_overlap_row_count`: `{int(metrics.get('panel_zone_instruction_sidecar_overlap_row_count', 0))}`",
        f"- `panel_zone_instruction_sidecar_overlap_member_count`: `{int(metrics.get('panel_zone_instruction_sidecar_overlap_member_count', 0))}`",
        f"- `panel_zone_instruction_sidecar_evidence_model`: `{metrics.get('panel_zone_instruction_sidecar_evidence_model', '')}`",
        f"- `panel_zone_instruction_sidecar_rebar_delivery_mode`: `{metrics.get('panel_zone_instruction_sidecar_rebar_delivery_mode', '')}`",
        f"- `panel_zone_validated_source_row_count_total`: `{int(metrics.get('panel_zone_validated_source_row_count_total', 0))}`",
        f"- `panel_zone_validated_source_overlap_member_count_min`: `{int(metrics.get('panel_zone_validated_source_overlap_member_count_min', 0))}`",
        f"- `panel_zone_missing_required_sources`: `{', '.join(metrics.get('panel_zone_missing_required_sources', []))}`",
        f"- `panel_zone_solver_verified_inbox_status_mode`: `{metrics.get('panel_zone_solver_verified_inbox_status_mode', '')}`",
        f"- `panel_zone_solver_verified_pending_input`: `{bool(metrics.get('panel_zone_solver_verified_pending_input', False))}`",
        f"- `panel_zone_solver_verified_latest_consume_contract_pass`: `{bool(metrics.get('panel_zone_solver_verified_latest_consume_contract_pass', False))}`",
        f"- `panel_zone_solver_verified_source_origin_class`: `{metrics.get('panel_zone_solver_verified_source_origin_class', '')}`",
        f"- `panel_zone_solver_verified_release_refresh_source_allowed`: `{bool(metrics.get('panel_zone_solver_verified_release_refresh_source_allowed', False))}`",
        f"- `panel_zone_solver_verified_recommended_action`: `{metrics.get('panel_zone_solver_verified_recommended_action', '')}`",
        f"- `foundation_optimization_ready`: `{bool(metrics.get('foundation_optimization_ready', False))}` ({metrics.get('foundation_optimization_mode', '')})",
        f"- `foundation_optimization_reason`: `{metrics.get('foundation_optimization_reason', '')}`",
        f"- `foundation_scope_source`: `{metrics.get('foundation_scope_source', '')}`",
        f"- `foundation_artifact_scan_mode`: `{metrics.get('foundation_artifact_scan_mode', '')}`",
        f"- `upstream_foundation_label_count`: `{int(metrics.get('upstream_foundation_label_count', 0))}` ({metrics.get('upstream_foundation_provenance_mode', '')})",
        f"- `wind_tunnel_raw_mapping_ready`: `{bool(metrics.get('wind_tunnel_raw_mapping_ready', False))}` ({metrics.get('wind_tunnel_mapping_mode', '')})",
        f"- `wind_tunnel_mapping_reason`: `{metrics.get('wind_tunnel_mapping_reason', '')}`",
        "",
        "## Binary Metrics",
        "",
        "| Area | Cases | Key Metric A | Key Metric B | Interpretation |",
        "|---|---:|---|---|---|",
        f"| Frame | {derived['frame_case_count']} | drift p95={derived['frame_drift_error_pct_p95']:.3f}% | top-disp p95={derived['frame_top_disp_error_pct_p95']:.3f}% | nonlinear frame regression envelope |",
        f"| Wind | {derived['wind_case_count']} | max drift={derived['wind_max_drift_pct']:.6f}% | residual drift={derived['wind_residual_drift_pct']:.6f}% | long-duration across-wind serviceability |",
        f"| SSI | {derived['ssi_case_count']} | nonlinear span={derived['ssi_nonlinear_ratio_span']:.6f} | residual drift={derived['ssi_residual_drift_pct']:.6f}% | fixed-vs-SSI residual reduction |",
        f"| Design Opt | {derived['design_opt_change_rows']} rows | raw drift={metrics.get('design_opt_raw_max_drift_pct', 0.0):.4f}%, repaired drift={metrics.get('design_opt_repaired_compliance_max_drift_pct', 0.0):.4f}% | cost delta={derived['design_opt_cost_delta']:.3f} | raw vs repaired compliance slice kept separate |",
        "",
        "## Time-Saving Coverage",
        "",
        f"- `estimated_time_saved`: `{metrics['estimated_time_saved_pct_label']}`",
        (
            f"- `measured_chain_wall_clock_comparable_rolling_min`: "
            f"`{metrics.get('measured_chain_rolling_total_minutes_mean', 0.0):.2f}` "
            f"(N={int(metrics.get('measured_chain_rolling_sample_count', 0))}, "
            f"range={metrics.get('measured_chain_rolling_total_minutes_range', ['n/a', 'n/a'])[0]}-"
            f"{metrics.get('measured_chain_rolling_total_minutes_range', ['n/a', 'n/a'])[1]})"
        ),
        f"- `measured_chain_wall_clock_min`: `{metrics['measured_chain_total_minutes']:.2f}`",
        f"- `comparable_run_selection_mode`: `{metrics.get('measured_chain_rolling_selection_mode', '')}`",
        f"- `comparable_reference_deployment_model`: `{metrics.get('measured_chain_comparable_reference_deployment_model', '')}`",
        f"- `comparable_reference_strict_smoke`: `{bool(metrics.get('measured_chain_comparable_reference_strict_design_opt_cost_smoke', False))}`",
        f"- `empirical_smoke_runtime_reduction`: `{metrics['empirical_smoke_runtime_saved_pct_label']}`",
        f"- `basis`: `{metrics['estimated_time_saved_basis']}`",
        f"- `{metrics['time_saving_focus']}`",
        "",
        "## Residual Holdout Boundary",
        "",
    ])
    if holdout_buckets:
        lines.extend(["| Category | Owner | Relative Share | Absolute Project % | Scope |", "|---|---|---:|---|---|"])
        for row in holdout_buckets:
            lines.append(
                f"| {row.get('label', row.get('id', ''))} | {row.get('owner', '')} | {int(row.get('relative_share_pct', 0))}% | "
                f"{_coverage_range_label(row.get('absolute_project_pct_range'))} | {row.get('scope', '')} |"
            )
        lines.append("")
    if holdout_detail_rows:
        lines.extend(["## Residual Holdout Review Table", "", "| Category | Axis | Detail | Owner | Why |", "|---|---|---|---|---|"])
        for row in holdout_detail_rows:
            lines.append(
                f"| {row.get('bucket_label', row.get('bucket_id', ''))} | {row.get('detail_axis', '')} | {row.get('detail_value', '')} | {row.get('owner', '')} | {row.get('why', '')} |"
            )
        lines.append("")
    if holdout_matrix_rows:
        lines.extend(
            [
                "## Residual Holdout Routing Matrix",
                "",
                "| Category | Track | Submodel | Review Story/Zone | Member Family | Owner | Why |",
                "|---|---|---|---|---|---|---|",
            ]
        )
        for row in holdout_matrix_rows:
            lines.append(
                f"| {row.get('bucket_label', '')} | {row.get('authority_track', '')} | {row.get('submodel_family', '')} | "
                f"{row.get('review_story_zone', '')} | {row.get('member_family', '')} | {row.get('owner', '')} | {row.get('why', '')} |"
            )
        lines.append("")
    lines.extend(["## Authority Catalog Routing Diff", ""])
    lines.append(
        f"- `baseline_seeded`: `{bool(authority_catalog_diff.get('baseline_seeded', False))}` | "
        f"`changes={int(authority_catalog_diff.get('change_count', 0))}` | "
        f"`added={int(authority_catalog_diff.get('added_count', 0))}` | "
        f"`removed={int(authority_catalog_diff.get('removed_count', 0))}` | "
        f"`unchanged={int(authority_catalog_diff.get('unchanged_count', 0))}`"
    )
    diff_rows = [row for row in (authority_catalog_diff.get("diff_rows") or []) if isinstance(row, dict)]
    if diff_rows:
        lines.extend(["", "| Change | Track | Submodel | Review Story/Zone | Member Family | Owner | Why |", "|---|---|---|---|---|---|---|"])
        for row in diff_rows:
            lines.append(
                f"| {row.get('change_type', '')} | {row.get('authority_track', '')} | {row.get('submodel_family', '')} | "
                f"{row.get('review_story_zone', '')} | {row.get('member_family', '')} | {row.get('owner', '')} | {row.get('why', '')} |"
            )
    else:
        lines.extend(["", "- No authority-catalog routing changes detected for this external submission refresh."])
    lines.append("")
    lines.extend([
        "## Blocked Cost-Down Actions",
        "",
        f"- `blocked_rows`: `{metrics['design_opt_blocked_action_row_count']}`",
        f"- `illegal_by_mask`: `{metrics['design_opt_blocked_illegal_by_mask']}`",
        f"- `illegal_by_mask_families`: `{metrics.get('design_opt_blocked_illegal_by_mask_family_label', '')}`",
        f"- `no_cost_gain`: `{metrics['design_opt_blocked_no_cost_gain']}`",
        f"- `constructability_hard_gate`: `{metrics.get('design_opt_blocked_constructability_hard_gate', 0)}`",
        f"- `constructability_hard_gate_reasons`: `{metrics.get('design_opt_blocked_constructability_hard_gate_label', '')}`",
        f"- `no_cost_gain_groups`: `{metrics['design_opt_blocked_no_cost_group_count']}`",
        f"- `no_cost_gain_explain_rows`: `{metrics['design_opt_blocked_no_cost_explain_row_count']}`",
        "",
        "## Design Optimization Entrypoint Groups",
        "",
        "## Appendix: Design Optimization Entrypoint Details",
        "",
        "## Submission Note",
        "",
        "- This bundle is the current external-validation submission baseline.",
        "- Previous external-validation submission bundles were pruned after this package was created.",
        "",
    ])
    section_lines = render_entrypoint_markdown_sections(
        entrypoints,
        entrypoint_groups,
        include_members=False,
    )
    native_roundtrip_appendix_lines = _midas_native_roundtrip_appendix_markdown(summary, artifacts)
    row_provenance_appendix_lines = _midas_row_provenance_appendix_markdown(summary, artifacts)
    irregular_structure_appendix_lines = _irregular_structure_appendix_markdown(summary, artifacts)
    case_onepage_appendix_lines = _external_benchmark_case_onepage_index_markdown(summary, artifacts)
    group_insert_at = lines.index("## Design Optimization Entrypoint Groups")
    entry_insert_at = lines.index("## Appendix: Design Optimization Entrypoint Details")
    lines[group_insert_at:entry_insert_at + 2] = section_lines + [""]
    if case_onepage_appendix_lines:
        submission_insert_at = lines.index("## Submission Note")
        lines[submission_insert_at:submission_insert_at] = case_onepage_appendix_lines
    if row_provenance_appendix_lines:
        submission_insert_at = lines.index("## Submission Note")
        lines[submission_insert_at:submission_insert_at] = row_provenance_appendix_lines
    if irregular_structure_appendix_lines:
        submission_insert_at = lines.index("## Submission Note")
        lines[submission_insert_at:submission_insert_at] = irregular_structure_appendix_lines
    if native_roundtrip_appendix_lines:
        submission_insert_at = lines.index("## Submission Note")
        lines[submission_insert_at:submission_insert_at] = native_roundtrip_appendix_lines
    path.write_text("\n".join(lines), encoding="utf-8")


def _bundle_artifact_link(path: str, prefix: str = "artifacts") -> str:
    rel = str(path or "").strip()
    if not rel:
        return "n/a"
    return f"{prefix.rstrip('/')}/{rel}"


def _compact_korean_source_ingest_summary_line(line: str) -> str:
    compact = str(line or "").strip()
    if not compact:
        return compact
    replacements = (
        ("Korean source ingest gate:", "KR ingest:"),
        ("Korean source ingest:", "KR ingest:"),
        ("sources=", "src="),
        ("classes=", "cls="),
        ("collected=", "got="),
        ("fingerprinted=", "fp="),
        ("metadata_only=", "meta="),
        ("rejected=", "rej="),
        ("duplicate_sha_groups=", "dup="),
        ("seed_complete=", "seed="),
        ("exact_topology=", "topo="),
        ("native_writeback=", "native="),
        ("p0_focus=", "p0="),
    )
    for old, new in replacements:
        compact = compact.replace(old, new)
    return compact


def _compact_korean_structural_preview_queue_summary_line(line: str) -> str:
    compact = str(line or "").strip()
    if not compact:
        return compact
    replacements = (
        ("Korean structural preview queue:", "KR preview queue:"),
        ("candidates=", "cand="),
        ("pending=", "pend="),
    )
    for old, new in replacements:
        compact = compact.replace(old, new)
    return compact


def _cover_kv(label: str, value: object, default: str = "n/a") -> str:
    text = "" if value is None else str(value).strip()
    return f"{label}={text or default}"


def _cover_join(*segments: str) -> str:
    return "; ".join(segment for segment in segments if segment)


def _external_case_attestation_placeholder(key: str) -> str:
    return EXTERNAL_CASE_ATTESTATION_PLACEHOLDERS.get(
        key,
        f"PENDING_REAL_{str(key or 'FIELD').upper()}_FILL_CASE_ATTESTATION_MANIFEST",
    )


def _external_case_attestation_has_real_value(value: object) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    return text not in set(EXTERNAL_CASE_ATTESTATION_PLACEHOLDERS.values()) and not text.startswith(
        "PENDING_REAL_"
    ) and not text.startswith("AUTO_GENERATED_")


def _load_optional_json_with_error(path: Path) -> tuple[dict, str]:
    if not path.exists():
        return {}, ""
    try:
        return _load_json(path), ""
    except Exception as exc:
        return {}, str(exc)


def _normalize_external_case_attestation(payload: dict) -> dict[str, str]:
    attestation = payload.get("attestation") if isinstance(payload.get("attestation"), dict) else payload
    return {
        "reviewer_name": str(attestation.get("reviewer_name", "") or "").strip(),
        "reviewer_role": str(attestation.get("reviewer_role", "") or "").strip(),
        "reviewer_license_id": str(attestation.get("reviewer_license_id", "") or "").strip(),
        "reviewer_signature_name": str(attestation.get("reviewer_signature_name", "") or "").strip(),
        "decision_basis": str(attestation.get("decision_basis", "") or "").strip(),
        "review_session_id": str(attestation.get("review_session_id", "") or "").strip(),
        "attested_at_utc": str(attestation.get("attested_at_utc", "") or "").strip(),
        "authority_name": str(attestation.get("authority_name", "") or "").strip(),
        "authority_receipt_id": str(attestation.get("authority_receipt_id", "") or "").strip(),
        "authority_receipt_issued_at_utc": str(
            attestation.get("authority_receipt_issued_at_utc", "") or ""
        ).strip(),
        "authority_receipt_note": str(attestation.get("authority_receipt_note", "") or "").strip(),
        "approval_signature_name": str(attestation.get("approval_signature_name", "") or "").strip(),
    }


def _external_case_attestation_role_or_license(attestation: dict[str, str]) -> str:
    role = str(attestation.get("reviewer_role", "") or "").strip()
    license_id = str(attestation.get("reviewer_license_id", "") or "").strip()
    segments = []
    if _external_case_attestation_has_real_value(role):
        segments.append(f"reviewer_role={role}")
    if _external_case_attestation_has_real_value(license_id):
        segments.append(f"reviewer_license_id={license_id}")
    return _cover_join(*segments) or _external_case_attestation_placeholder("reviewer_role_or_license")


def _external_case_attestation_authority_receipt(attestation: dict[str, str]) -> str:
    segments = []
    authority_name = str(attestation.get("authority_name", "") or "").strip()
    authority_note = str(attestation.get("authority_receipt_note", "") or "").strip()
    if _external_case_attestation_has_real_value(authority_name):
        segments.append(f"authority_name={authority_name}")
    if _external_case_attestation_has_real_value(authority_note):
        segments.append(f"authority_note={authority_note}")
    return _cover_join(*segments) or _external_case_attestation_placeholder("authority_receipt")


def _external_case_attestation_missing_fields(attestation: dict[str, str]) -> tuple[list[str], list[str], list[str]]:
    reviewer_missing = [
        field
        for field in EXTERNAL_CASE_ATTESTATION_REVIEWER_REQUIRED_FIELDS
        if not _external_case_attestation_has_real_value(attestation.get(field, ""))
    ]
    authority_missing = [
        field
        for field in EXTERNAL_CASE_ATTESTATION_AUTHORITY_REQUIRED_FIELDS
        if not _external_case_attestation_has_real_value(attestation.get(field, ""))
    ]
    return reviewer_missing, authority_missing, reviewer_missing + authority_missing


def _external_case_attestation_status_reason(status: str, manifest_error: str) -> str:
    if status == EXTERNAL_CASE_ATTESTATION_STATUS_COMPLETE:
        return "reviewer and authority attestation manifest is complete"
    if status == EXTERNAL_CASE_ATTESTATION_STATUS_REVIEWER_ATTESTED:
        return "reviewer attestation exists but authority receipt is still pending"
    if status == EXTERNAL_CASE_ATTESTATION_STATUS_MANIFEST_INCOMPLETE:
        return "attestation manifest exists but required reviewer fields are still missing"
    if status == EXTERNAL_CASE_ATTESTATION_STATUS_MANIFEST_INVALID:
        return f"attestation manifest could not be parsed: {manifest_error or 'invalid json'}"
    return "no real case-level attestation manifest exists; template placeholders remain active"


def _build_external_case_attestation_template_payload(
    summary: dict,
    row: dict,
    artifacts: dict,
    *,
    manifest_json_path: Path,
) -> dict:
    metrics = summary.get("metrics") if isinstance(summary.get("metrics"), dict) else summary
    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contract_pass": True,
        "reason_code": "PASS_TEMPLATE_READY",
        "reason": "case-level reviewer/authority attestation template generated for onepage cover sheet",
        "template_mode": "external_benchmark_case_onepage_reviewer_authority_attestation",
        "case": {
            "task_id": str(row.get("task_id", "") or ""),
            "case_id": str(row.get("case_id", "") or ""),
            "case_label": str(row.get("case_label", row.get("case_id", "Case")) or "Case"),
            "benchmark_family": str(row.get("benchmark_family", "") or ""),
            "hazard_family": str(row.get("hazard_family", "") or ""),
            "topology_family": str(row.get("topology_family", "") or ""),
            "load_path_family": str(row.get("load_path_family", "") or ""),
            "submission_scope": str(row.get("submission_scope", "") or ""),
            "source_origin_class": str(row.get("source_origin_class", "") or ""),
        },
        "evidence": {
            "kpi_receipt_path": str(row.get("kpi_receipt_path", "") or ""),
            "primary_report_path": str(row.get("primary_report_path", "") or ""),
            "case_bundle_dir": str(row.get("case_bundle_dir", "") or ""),
            "case_bundle_zip_path": str(row.get("case_bundle_zip_path", "") or ""),
        },
        "workflow_connection": {
            "execution_manifest_json": str(artifacts.get("external_benchmark_execution_manifest_json", "") or ""),
            "execution_status_manifest_json": str(
                artifacts.get("external_benchmark_execution_status_manifest_json", "") or ""
            ),
            "audit_review_decision_batch_template_json": str(
                artifacts.get("audit_review_decision_batch_template_json", "") or ""
            ),
            "audit_review_decision_batch_run_report_json": str(
                artifacts.get("audit_review_decision_batch_run_report_json", "") or ""
            ),
            "audit_review_decision_batch_live_preview_json": str(
                artifacts.get("audit_review_decision_batch_live_preview_json", "") or ""
            ),
            "audit_review_decision_batch_approve_all_live_ready_template_json": str(
                artifacts.get("audit_review_decision_batch_approve_all_live_ready_template_json", "") or ""
            ),
            "review_boundary_pending_count": int(
                metrics.get("external_benchmark_execution_review_boundary_pending_count", 0) or 0
            ),
            "review_boundary_resolution_label": str(
                metrics.get("external_benchmark_execution_review_boundary_resolution_label", "") or ""
            ),
            "review_boundary_owner_label": str(
                metrics.get("external_benchmark_execution_review_boundary_owner_label", "") or ""
            ),
            "review_boundary_priority_label": str(
                metrics.get("external_benchmark_execution_review_boundary_priority_label", "") or ""
            ),
            "submission_ready_to_start_now": bool(
                metrics.get("external_benchmark_submission_ready_to_start_now", False)
            ),
            "submission_reason_code": str(
                metrics.get("external_benchmark_submission_reason_code", "") or ""
            ),
        },
        "instructions": [
            f"Copy this template to {manifest_json_path} and replace the placeholder values only after real case review.",
            "This case-level cover-sheet attestation does not approve live audit queue updates by itself.",
            "Do not record authority receipt or approval signature values until the authority action has actually occurred.",
        ],
        "attestation": {
            "reviewer_name": _external_case_attestation_placeholder("reviewer_name"),
            "reviewer_role": "PENDING_REAL_REVIEWER_ROLE_FILL_CASE_ATTESTATION_MANIFEST",
            "reviewer_license_id": "PENDING_REAL_REVIEWER_LICENSE_ID_FILL_CASE_ATTESTATION_MANIFEST",
            "reviewer_signature_name": _external_case_attestation_placeholder("reviewer_signature"),
            "decision_basis": "PENDING_REAL_DECISION_BASIS_FILL_CASE_ATTESTATION_MANIFEST",
            "review_session_id": "PENDING_REAL_REVIEW_SESSION_ID_FILL_CASE_ATTESTATION_MANIFEST",
            "attested_at_utc": "PENDING_REAL_ATTESTED_AT_UTC_FILL_CASE_ATTESTATION_MANIFEST",
            "authority_name": "PENDING_REAL_AUTHORITY_NAME_FILL_CASE_ATTESTATION_MANIFEST",
            "authority_receipt_id": _external_case_attestation_placeholder("receipt_id"),
            "authority_receipt_issued_at_utc": _external_case_attestation_placeholder("receipt_issued_at"),
            "authority_receipt_note": "PENDING_REAL_AUTHORITY_RECEIPT_NOTE_FILL_CASE_ATTESTATION_MANIFEST",
            "approval_signature_name": _external_case_attestation_placeholder("approval_signature"),
        },
    }


def _render_external_case_attestation_template_markdown(
    payload: dict,
    *,
    manifest_json_path: Path,
) -> str:
    case = payload.get("case") if isinstance(payload.get("case"), dict) else {}
    workflow = payload.get("workflow_connection") if isinstance(payload.get("workflow_connection"), dict) else {}
    attestation = payload.get("attestation") if isinstance(payload.get("attestation"), dict) else {}
    lines = [
        f"# Case Attestation Template: {case.get('case_label', case.get('case_id', 'Case'))}",
        "",
        f"- `generated_at`: `{payload.get('generated_at', '')}`",
        f"- `manifest_target`: `{manifest_json_path}`",
        f"- `review_boundary_pending_count`: `{int(workflow.get('review_boundary_pending_count', 0) or 0)}`",
        f"- `review_boundary_resolution_label`: `{workflow.get('review_boundary_resolution_label', '') or 'n/a'}`",
        f"- `submission_ready_to_start_now`: `{bool(workflow.get('submission_ready_to_start_now', False))}`",
        f"- `submission_reason_code`: `{workflow.get('submission_reason_code', '') or 'n/a'}`",
        "",
        "## Instructions",
        "",
    ]
    for item in payload.get("instructions") or []:
        lines.append(f"- {item}")
    lines.extend(
        [
            "",
            "## Attestation Fields",
            "",
        ]
    )
    for key, value in attestation.items():
        lines.append(f"- `{key}`: `{value}`")
    lines.append("")
    return "\n".join(lines)


def _build_external_case_attestation_receipt_payload(
    summary: dict,
    row: dict,
    artifacts: dict,
    *,
    source_kind: str,
    attestation: dict[str, str],
    manifest_json_path: Path,
    template_json_path: Path,
    manifest_error: str,
) -> dict:
    metrics = summary.get("metrics") if isinstance(summary.get("metrics"), dict) else summary
    reviewer_missing, authority_missing, missing_fields = _external_case_attestation_missing_fields(attestation)
    if manifest_error:
        status = EXTERNAL_CASE_ATTESTATION_STATUS_MANIFEST_INVALID
    elif source_kind != "manifest":
        status = EXTERNAL_CASE_ATTESTATION_STATUS_TEMPLATE_PENDING
    elif reviewer_missing:
        status = EXTERNAL_CASE_ATTESTATION_STATUS_MANIFEST_INCOMPLETE
    elif authority_missing:
        status = EXTERNAL_CASE_ATTESTATION_STATUS_REVIEWER_ATTESTED
    else:
        status = EXTERNAL_CASE_ATTESTATION_STATUS_COMPLETE
    slot_values = {
        "reviewer_name_slot": (
            attestation.get("reviewer_name", "")
            if _external_case_attestation_has_real_value(attestation.get("reviewer_name", ""))
            else _external_case_attestation_placeholder("reviewer_name")
        ),
        "reviewer_role_or_license_slot": _external_case_attestation_role_or_license(attestation),
        "reviewer_signature_slot": (
            attestation.get("reviewer_signature_name", "")
            if _external_case_attestation_has_real_value(attestation.get("reviewer_signature_name", ""))
            else _external_case_attestation_placeholder("reviewer_signature")
        ),
        "receipt_id_slot": (
            attestation.get("authority_receipt_id", "")
            if _external_case_attestation_has_real_value(attestation.get("authority_receipt_id", ""))
            else _external_case_attestation_placeholder("receipt_id")
        ),
        "receipt_issued_at_slot": (
            attestation.get("authority_receipt_issued_at_utc", "")
            if _external_case_attestation_has_real_value(attestation.get("authority_receipt_issued_at_utc", ""))
            else _external_case_attestation_placeholder("receipt_issued_at")
        ),
        "authority_receipt_slot": _external_case_attestation_authority_receipt(attestation),
        "approval_signature_slot": (
            attestation.get("approval_signature_name", "")
            if _external_case_attestation_has_real_value(attestation.get("approval_signature_name", ""))
            else _external_case_attestation_placeholder("approval_signature")
        ),
    }
    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contract_pass": bool(status == EXTERNAL_CASE_ATTESTATION_STATUS_COMPLETE),
        "reason_code": status,
        "reason": _external_case_attestation_status_reason(status, manifest_error),
        "case": {
            "task_id": str(row.get("task_id", "") or ""),
            "case_id": str(row.get("case_id", "") or ""),
            "case_label": str(row.get("case_label", row.get("case_id", "Case")) or "Case"),
            "benchmark_family": str(row.get("benchmark_family", "") or ""),
        },
        "attestation_source_kind": source_kind,
        "attestation_source_json": str(manifest_json_path if source_kind == "manifest" and not manifest_error else template_json_path),
        "manifest_json": str(manifest_json_path),
        "template_json": str(template_json_path),
        "manifest_error": manifest_error,
        "reviewer_missing_fields": reviewer_missing,
        "authority_missing_fields": authority_missing,
        "missing_fields": missing_fields,
        "summary": {
            "required_field_count": int(
                len(EXTERNAL_CASE_ATTESTATION_REVIEWER_REQUIRED_FIELDS)
                + len(EXTERNAL_CASE_ATTESTATION_AUTHORITY_REQUIRED_FIELDS)
            ),
            "completed_field_count": int(
                sum(
                    1
                    for field in EXTERNAL_CASE_ATTESTATION_REVIEWER_REQUIRED_FIELDS
                    + EXTERNAL_CASE_ATTESTATION_AUTHORITY_REQUIRED_FIELDS
                    if _external_case_attestation_has_real_value(attestation.get(field, ""))
                )
            ),
            "review_boundary_pending_count": int(
                metrics.get("external_benchmark_execution_review_boundary_pending_count", 0) or 0
            ),
            "review_boundary_resolution_label": str(
                metrics.get("external_benchmark_execution_review_boundary_resolution_label", "") or ""
            ),
            "submission_ready_to_start_now": bool(
                metrics.get("external_benchmark_submission_ready_to_start_now", False)
            ),
            "submission_reason_code": str(
                metrics.get("external_benchmark_submission_reason_code", "") or ""
            ),
        },
        "workflow_connection": {
            "audit_review_decision_batch_template_json": str(
                artifacts.get("audit_review_decision_batch_template_json", "") or ""
            ),
            "audit_review_decision_batch_run_report_json": str(
                artifacts.get("audit_review_decision_batch_run_report_json", "") or ""
            ),
            "audit_review_decision_batch_live_preview_json": str(
                artifacts.get("audit_review_decision_batch_live_preview_json", "") or ""
            ),
            "audit_review_decision_batch_approve_all_live_ready_template_json": str(
                artifacts.get("audit_review_decision_batch_approve_all_live_ready_template_json", "") or ""
            ),
            "execution_status_manifest_json": str(
                artifacts.get("external_benchmark_execution_status_manifest_json", "") or ""
            ),
        },
        "evidence": {
            "kpi_receipt_path": str(row.get("kpi_receipt_path", "") or ""),
            "primary_report_path": str(row.get("primary_report_path", "") or ""),
            "case_bundle_dir": str(row.get("case_bundle_dir", "") or ""),
            "case_bundle_zip_path": str(row.get("case_bundle_zip_path", "") or ""),
        },
        "attestation": attestation,
        "cover_sheet_slots": slot_values,
    }


def _render_external_case_attestation_receipt_markdown(payload: dict) -> str:
    case = payload.get("case") if isinstance(payload.get("case"), dict) else {}
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    lines = [
        f"# Case Attestation Receipt: {case.get('case_label', case.get('case_id', 'Case'))}",
        "",
        f"- `generated_at`: `{payload.get('generated_at', '')}`",
        f"- `reason_code`: `{payload.get('reason_code', '')}`",
        f"- `reason`: `{payload.get('reason', '')}`",
        f"- `attestation_source_kind`: `{payload.get('attestation_source_kind', '')}`",
        f"- `attestation_source_json`: `{payload.get('attestation_source_json', '')}`",
        f"- `missing_fields`: `{', '.join(payload.get('missing_fields', []) or []) or 'none'}`",
        (
            f"- `workflow_summary`: `review_boundary_pending={int(summary.get('review_boundary_pending_count', 0) or 0)} | "
            f"review_boundary_resolution={summary.get('review_boundary_resolution_label', '') or 'n/a'} | "
            f"submission_ready_now={bool(summary.get('submission_ready_to_start_now', False))} | "
            f"submission_reason={summary.get('submission_reason_code', '') or 'n/a'}`"
        ),
        "",
        "## Cover Sheet Values",
        "",
    ]
    for key, value in (payload.get("cover_sheet_slots") or {}).items():
        lines.append(f"- `{key}`: `{value}`")
    lines.append("")
    return "\n".join(lines)


def _external_benchmark_case_onepage_attestation_slots(summary: dict, row: dict) -> dict[str, str]:
    status = str(row.get("case_attestation_status", "") or "").strip()
    missing_fields = ", ".join(row.get("case_attestation_missing_fields", []) or []) or "none"
    source_kind = str(row.get("case_attestation_source_kind", "") or "").strip() or "template"
    receipt_path = str(row.get("case_attestation_receipt_bundle", row.get("case_attestation_receipt_source", "")) or "")
    manifest_path = str(row.get("case_attestation_manifest_bundle", row.get("case_attestation_manifest_source", "")) or "")
    template_path = str(row.get("case_attestation_template_bundle", row.get("case_attestation_template_source", "")) or "")
    if status == EXTERNAL_CASE_ATTESTATION_STATUS_COMPLETE:
        disclaimer = _cover_join(
            "real reviewer/authority values loaded from case attestation manifest",
            _cover_kv("status", status),
            _cover_kv("receipt", receipt_path),
        )
    else:
        disclaimer = _cover_join(
            "pending real reviewer/authority attestation; no approval is implied",
            _cover_kv("status", status or EXTERNAL_CASE_ATTESTATION_STATUS_TEMPLATE_PENDING),
            _cover_kv("source_kind", source_kind),
            _cover_kv("manifest", manifest_path or "n/a"),
            _cover_kv("template", template_path or "n/a"),
            _cover_kv("receipt", receipt_path or "n/a"),
            _cover_kv("missing_fields", missing_fields),
        )
    return {
        "reviewer_name_slot": str(
            row.get("case_attestation_reviewer_name", "") or _external_case_attestation_placeholder("reviewer_name")
        ),
        "reviewer_role_or_license_slot": str(
            row.get("case_attestation_reviewer_role_or_license", "")
            or _external_case_attestation_placeholder("reviewer_role_or_license")
        ),
        "reviewer_signature_slot": str(
            row.get("case_attestation_reviewer_signature", "")
            or _external_case_attestation_placeholder("reviewer_signature")
        ),
        "receipt_id_slot": str(
            row.get("case_attestation_receipt_id", "") or _external_case_attestation_placeholder("receipt_id")
        ),
        "receipt_issued_at_slot": str(
            row.get("case_attestation_receipt_issued_at", "")
            or _external_case_attestation_placeholder("receipt_issued_at")
        ),
        "authority_receipt_slot": str(
            row.get("case_attestation_authority_receipt", "")
            or _external_case_attestation_placeholder("authority_receipt")
        ),
        "approval_signature_slot": str(
            row.get("case_attestation_approval_signature", "")
            or _external_case_attestation_placeholder("approval_signature")
        ),
        "attestation_disclaimer": disclaimer or EXTERNAL_CASE_COVER_DISCLAIMER,
    }


def _irregular_benchmark_case_receipt_rows(summary: dict) -> list[dict[str, str]]:
    receipt_rows: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for key in ("irregular_benchmark_execution_ready_tasks", "irregular_benchmark_execution_blocked_tasks"):
        tasks = summary.get(key) if isinstance(summary.get(key), list) else []
        for task in tasks:
            if not isinstance(task, dict):
                continue
            receipt_json = str(task.get("benchmark_receipt_json", "") or "").strip()
            receipt_md = str(task.get("benchmark_receipt_md", "") or "").strip()
            if not receipt_json and not receipt_md:
                continue
            execution_status = str(task.get("execution_status", "") or "").strip().lower()
            if not (
                execution_status in {"ready", "completed"}
                or (receipt_json and Path(receipt_json).exists())
                or (receipt_md and Path(receipt_md).exists())
            ):
                continue
            case_id = str(task.get("case_id", "") or "").strip()
            dedupe_key = (case_id, receipt_json, receipt_md)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            receipt_rows.append(
                {
                    "task_id": str(task.get("task_id", "") or "").strip(),
                    "case_id": case_id,
                    "case_label": str(task.get("case_label", case_id) or case_id).strip(),
                    "execution_status": str(task.get("execution_status", "") or "").strip(),
                    "benchmark_readiness_tier": str(task.get("benchmark_readiness_tier", "") or "").strip(),
                    "benchmark_receipt_json": receipt_json,
                    "benchmark_receipt_md": receipt_md,
                }
            )
    return receipt_rows


def _irregular_benchmark_receipt_artifacts(row: dict, bundle_artifact_prefix: str) -> list[dict[str, str]]:
    receipt_rows = [item for item in (row.get("irregular_benchmark_receipt_rows") or []) if isinstance(item, dict)]
    items: list[dict[str, str]] = []
    manifest_json = str(row.get("irregular_benchmark_execution_manifest_json", "") or "").strip()
    receipt_index_json = str(row.get("irregular_benchmark_receipt_index_json", "") or "").strip()
    if manifest_json:
        items.append(
            {
                "kind": "artifact",
                "label": "irregular benchmark execution manifest",
                "href": _bundle_artifact_link(manifest_json, bundle_artifact_prefix),
            }
        )
    if receipt_index_json:
        items.append(
            {
                "kind": "artifact",
                "label": "irregular benchmark receipt index",
                "href": _bundle_artifact_link(receipt_index_json, bundle_artifact_prefix),
            }
        )
    if not receipt_rows:
        return items
    for item in receipt_rows:
        case_id = str(item.get("case_id", "") or "").strip() or "n/a"
        tier = str(item.get("benchmark_readiness_tier", "") or "").strip() or "n/a"
        status = str(item.get("execution_status", "") or "").strip() or "n/a"
        receipt_json = _bundle_artifact_link(str(item.get("benchmark_receipt_json", "") or ""), bundle_artifact_prefix)
        receipt_md = _bundle_artifact_link(str(item.get("benchmark_receipt_md", "") or ""), bundle_artifact_prefix)
        items.append(
            {
                "kind": "receipt",
                "case_id": case_id,
                "status": status,
                "tier": tier,
                "json_href": receipt_json,
                "md_href": receipt_md,
            }
        )
    return items


def _render_irregular_benchmark_receipt_markdown_lines(row: dict, bundle_artifact_prefix: str) -> list[str]:
    items = _irregular_benchmark_receipt_artifacts(row, bundle_artifact_prefix)
    if not items:
        return ["- irregular benchmark receipts: n/a"]
    lines: list[str] = []
    for item in items:
        if item.get("kind") == "artifact":
            lines.append(f"- [{item['label']}]({item['href']})")
            continue
        lines.append(
            f"- irregular receipt `{item['case_id']}`: status=`{item['status']}` | tier=`{item['tier']}` | "
            f"[receipt JSON]({item['json_href']}) | [receipt Markdown]({item['md_href']})"
        )
    return lines


def _render_irregular_benchmark_receipt_html(row: dict, bundle_artifact_prefix: str) -> str:
    items = _irregular_benchmark_receipt_artifacts(row, bundle_artifact_prefix)
    if not items:
        return "<div class='note'>irregular benchmark receipts: n/a</div>"
    blocks: list[str] = []
    for item in items:
        if item.get("kind") == "artifact":
            blocks.append(
                f"<div class='note'><a href='{html.escape(item['href'])}'>{html.escape(item['label'])}</a></div>"
            )
            continue
        blocks.append(
            "<div class='note'>"
            f"irregular receipt {html.escape(item['case_id'])}: "
            f"status={html.escape(item['status'])} | "
            f"tier={html.escape(item['tier'])} | "
            f"json=<a href='{html.escape(item['json_href'])}'>receipt JSON</a> | "
            f"md=<a href='{html.escape(item['md_href'])}'>receipt Markdown</a>"
            "</div>"
        )
    return "".join(blocks)


def _render_irregular_benchmark_receipt_text_lines(row: dict, bundle_artifact_prefix: str) -> list[str]:
    items = _irregular_benchmark_receipt_artifacts(row, bundle_artifact_prefix)
    if not items:
        return ["irregular benchmark receipts: n/a"]
    lines: list[str] = []
    for item in items:
        if item.get("kind") == "artifact":
            lines.append(f"{item['label']}: {item['href']}")
            continue
        lines.append(
            f"irregular receipt {item['case_id']}: status={item['status']} | tier={item['tier']} | "
            f"json={item['json_href']} | md={item['md_href']}"
        )
    return lines


def _render_irregular_benchmark_summary_receipt_markdown(
    summary: dict,
    artifacts: dict,
    bundle_artifact_prefix: str,
) -> list[str]:
    receipt_rows = _irregular_benchmark_case_receipt_rows(summary)
    receipt_index_json = str(artifacts.get("irregular_benchmark_receipt_index_json", "") or "").strip()
    lines: list[str] = []
    if receipt_index_json:
        lines.append(
            f"- `receipt_index`: [irregular benchmark receipt index]({_bundle_artifact_link(receipt_index_json, bundle_artifact_prefix)})"
        )
    if receipt_rows:
        receipt_links = " | ".join(
            f"`{str(row.get('case_id', '') or '').strip() or 'n/a'}` "
            f"[json]({_bundle_artifact_link(str(row.get('benchmark_receipt_json', '') or ''), bundle_artifact_prefix)}) "
            f"[md]({_bundle_artifact_link(str(row.get('benchmark_receipt_md', '') or ''), bundle_artifact_prefix)})"
            for row in receipt_rows[:5]
        )
        lines.append(f"- `receipt_links`: {receipt_links}")
    if not lines:
        lines.append("- `receipt_index`: `n/a`")
    return lines


def _render_irregular_benchmark_summary_receipt_html(
    summary: dict,
    artifacts: dict,
    bundle_artifact_prefix: str,
) -> str:
    receipt_rows = _irregular_benchmark_case_receipt_rows(summary)
    receipt_index_json = str(artifacts.get("irregular_benchmark_receipt_index_json", "") or "").strip()
    receipt_index_html = (
        f"<a href='{html.escape(_bundle_artifact_link(receipt_index_json, bundle_artifact_prefix))}'>irregular benchmark receipt index</a>"
        if receipt_index_json
        else "n/a"
    )
    receipt_links_html = (
        "<br>".join(
            " ".join(
                [
                    html.escape(str(row.get("case_id", "") or "").strip() or "n/a"),
                    f"<a href='{html.escape(_bundle_artifact_link(str(row.get('benchmark_receipt_json', '') or ''), bundle_artifact_prefix))}'>json</a>",
                    f"<a href='{html.escape(_bundle_artifact_link(str(row.get('benchmark_receipt_md', '') or ''), bundle_artifact_prefix))}'>md</a>",
                ]
            )
            for row in receipt_rows[:5]
        )
        if receipt_rows
        else "n/a"
    )
    return (
        f"<tr><td>Receipt index</td><td>{receipt_index_html}</td></tr>"
        f"<tr><td>Receipt links</td><td>{receipt_links_html}</td></tr>"
    )


def _build_irregular_canonical_promotion_queue_rows(
    source_catalog: dict,
    top5_family_ids: list[str],
) -> list[dict[str, str]]:
    source_records = source_catalog.get("source_records") if isinstance(source_catalog.get("source_records"), list) else []
    source_records_by_family: dict[str, list[dict[str, str]]] = {}
    for row in source_records:
        if not isinstance(row, dict):
            continue
        family_id = str(row.get("family_id", "") or "").strip()
        if family_id:
            source_records_by_family.setdefault(family_id, []).append(row)
    top5_set = {str(item).strip() for item in top5_family_ids if str(item).strip()}
    rows: list[dict[str, str]] = []

    def _is_native_canonical_source(row: dict[str, str]) -> bool:
        source_kind = str(row.get("source_kind", "") or "").strip().lower()
        evidence_class = str(row.get("evidence_class", "") or "").strip().lower()
        primary_format = str(row.get("formats", [""])[:1][0] if isinstance(row.get("formats"), list) and row.get("formats") else row.get("format", "") or "").strip().lower()
        input_path = str(row.get("local_path", "") or "").strip()
        suffix = Path(input_path).suffix.lower()
        if source_kind in {"public_native_source", "repo_local_source"} or evidence_class in {
            "public_native_mgt",
            "repo_local_text_model",
            "official_benchmark_native_text",
        }:
            return True
        if primary_format in {"ifc", "step", "iges", "dxf", "mgt", "mcb", "tcl", "inp"} or suffix in {
            ".ifc",
            ".step",
            ".stp",
            ".iges",
            ".igs",
            ".dxf",
            ".mgt",
            ".mcb",
            ".tcl",
            ".inp",
        }:
            return True
        return False

    for row in source_records:
        if not isinstance(row, dict):
            continue
        family_id = str(row.get("family_id", "") or "").strip()
        if top5_set and family_id not in top5_set:
            continue
        metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        status = str(metadata.get("canonical_promotion_status", "") or "").strip()
        if not status or status == "promoted_to_canonical":
            continue
        family_rows = source_records_by_family.get(family_id, [])
        if any(_is_native_canonical_source(family_row) for family_row in family_rows):
            continue
        native_support_ids = [
            str(family_row.get("source_id", "") or "").strip()
            for family_row in family_rows
            if str(family_row.get("source_kind", "") or "").strip().lower() == "repo_local_native_binary_support"
        ]
        promotion_path = "collect official benchmark-native package"
        status_label = "bridged pending canonical source"
        rows.append(
            {
                "family_id": family_id,
                "source_id": str(row.get("source_id", "") or "").strip(),
                "status": status_label,
                "priority": str(metadata.get("canonical_promotion_priority", "") or "").strip(),
                "promotion_path": promotion_path,
                "native_support": (
                    f"native MEB support via {', '.join(native_support_ids)}"
                    if native_support_ids
                    else "n/a"
                ),
                "blocker": str(metadata.get("canonical_promotion_blocker", "") or "").strip(),
            }
        )
    rows.sort(key=lambda item: (int(item["priority"] or 999), item["family_id"], item["source_id"]))
    return rows


def _render_irregular_benchmark_receipt_index_markdown(row: dict, bundle_artifact_prefix: str) -> str:
    items = _irregular_benchmark_receipt_artifacts(row, bundle_artifact_prefix)
    if not items:
        return "n/a"
    receipt_lines: list[str] = []
    artifact_lines: list[str] = []
    for item in items:
        if item.get("kind") == "artifact":
            artifact_lines.append(f"[{item['label']}]({item['href']})")
            continue
        receipt_lines.append(
            f"`{item['case_id']}` ({item['tier']}/{item['status']}) "
            f"[json]({item['json_href']}) [md]({item['md_href']})"
        )
    return "<br>".join(receipt_lines + artifact_lines) if (receipt_lines or artifact_lines) else "n/a"


def _render_irregular_benchmark_receipt_index_html(row: dict, bundle_artifact_prefix: str) -> str:
    items = _irregular_benchmark_receipt_artifacts(row, bundle_artifact_prefix)
    if not items:
        return "n/a"
    receipt_blocks: list[str] = []
    artifact_blocks: list[str] = []
    for item in items:
        if item.get("kind") == "artifact":
            artifact_blocks.append(
                f"<a href='{html.escape(item['href'])}'>{html.escape(item['label'])}</a>"
            )
            continue
        receipt_blocks.append(
            " | ".join(
                [
                    f"{html.escape(item['case_id'])} ({html.escape(item['tier'])}/{html.escape(item['status'])})",
                    f"<a href='{html.escape(item['json_href'])}'>receipt JSON</a>",
                    f"<a href='{html.escape(item['md_href'])}'>receipt Markdown</a>",
                ]
            )
    )
    return "<br>".join(receipt_blocks + artifact_blocks) if (receipt_blocks or artifact_blocks) else "n/a"


def _bundle_artifact_link(rel_path: str, prefix: str = "artifacts") -> str:
    rel_path = str(rel_path or "").strip()
    if not rel_path:
        return "n/a"
    return f"{prefix.rstrip('/')}/{Path(rel_path).as_posix()}"


def _external_benchmark_case_onepage_cover_fields(summary: dict, row: dict) -> list[tuple[str, str]]:
    metrics = summary.get("metrics") if isinstance(summary.get("metrics"), dict) else summary
    submission_ready = bool(metrics.get("external_benchmark_submission_ready_to_start_now", False))
    submission_reason = str(metrics.get("external_benchmark_submission_reason_code", "") or "").strip()
    submission_start_mode = str(metrics.get("external_benchmark_submission_recommended_start_mode", "") or "").strip()
    submission_scope = str(metrics.get("external_benchmark_submission_recommended_submission_scope", "") or "").strip()
    submission_caution = str(metrics.get("external_benchmark_submission_caution_label", "") or "").strip()
    submission_blocker = str(metrics.get("external_benchmark_submission_blocker_label", "") or "").strip()
    review_boundary_resolution = str(
        metrics.get("external_benchmark_execution_review_boundary_resolution_label", "") or ""
    ).strip()
    review_boundary_owner = str(metrics.get("external_benchmark_execution_review_boundary_owner_label", "") or "").strip()
    review_boundary_priority = str(
        metrics.get("external_benchmark_execution_review_boundary_priority_label", "") or ""
    ).strip()
    review_boundary_family = str(metrics.get("external_benchmark_execution_review_boundary_family_label", "") or "").strip()
    review_boundary_followup = str(
        metrics.get("external_benchmark_execution_review_boundary_followup_action_label", "") or ""
    ).strip()
    authority_changes = int(summary.get("authority_catalog_diff_change_count", 0) or 0)
    authority_added = int(summary.get("authority_catalog_diff_added_count", 0) or 0)
    authority_removed = int(summary.get("authority_catalog_diff_removed_count", 0) or 0)
    authority_baseline_seeded = bool(summary.get("authority_catalog_diff_baseline_seeded", False))
    authority_warning_active = bool(summary.get("authority_catalog_routing_warning_active", False))
    case_label = str(row.get("case_label", row.get("case_id", "Case")) or "Case").strip()
    task_id = str(row.get("task_id", "") or "").strip()
    case_id = str(row.get("case_id", "") or "").strip()
    benchmark_family = str(row.get("benchmark_family", "") or "").strip()
    hazard_family = str(row.get("hazard_family", "") or "").strip()
    topology_family = str(row.get("topology_family", "") or "").strip()
    load_path_family = str(row.get("load_path_family", "") or "").strip()
    execution_status = str(row.get("execution_status", "") or "").strip()
    lifecycle_status = str(row.get("lifecycle_status", "") or "").strip()
    submission_scope_raw = str(row.get("submission_scope", "") or "").strip()
    source_origin_class = str(row.get("source_origin_class", "") or "").strip()
    kpi_receipt_path = str(row.get("kpi_receipt_path", "") or "").strip()
    primary_report_path = str(row.get("primary_report_path", "") or "").strip()
    case_bundle_zip_path = str(row.get("case_bundle_zip_path", "") or "").strip()
    case_bundle_dir = str(row.get("case_bundle_dir", "") or "").strip()
    attestation_slots = _external_benchmark_case_onepage_attestation_slots(summary, row)
    attestation_status = str(row.get("case_attestation_status", "") or "").strip()
    attestation_source_kind = str(row.get("case_attestation_source_kind", "") or "").strip()
    attestation_missing_fields = ", ".join(row.get("case_attestation_missing_fields", []) or []) or "none"
    attestation_manifest_path = str(
        row.get("case_attestation_manifest_bundle", row.get("case_attestation_manifest_source", "")) or ""
    ).strip()
    attestation_template_path = str(
        row.get("case_attestation_template_bundle", row.get("case_attestation_template_source", "")) or ""
    ).strip()
    attestation_receipt_path = str(
        row.get("case_attestation_receipt_bundle", row.get("case_attestation_receipt_source", "")) or ""
    ).strip()
    irregular_receipt_rows = [item for item in (row.get("irregular_benchmark_receipt_rows") or []) if isinstance(item, dict)]
    irregular_receipt_cases = ", ".join(
        str(item.get("case_id", "") or "").strip()
        for item in irregular_receipt_rows
        if str(item.get("case_id", "") or "").strip()
    ) or "n/a"
    irregular_receipt_index_json = str(row.get("irregular_benchmark_receipt_index_json", "") or "").strip()
    return [
        ("Prepared for", "reviewer / authority"),
        ("Case identity", _cover_join(
            _cover_kv("case_label", case_label),
            _cover_kv("task_id", task_id),
            _cover_kv("case_id", case_id),
        )),
        ("Benchmark family", _cover_join(
            _cover_kv("benchmark_family", benchmark_family),
            _cover_kv("hazard_family", hazard_family),
            _cover_kv("topology_family", topology_family),
            _cover_kv("load_path_family", load_path_family),
        )),
        ("Status", _cover_join(
            _cover_kv("execution", execution_status),
            _cover_kv("lifecycle", lifecycle_status),
            _cover_kv("receipt_contract_pass", bool(row.get("kpi_receipt_contract_pass", False))),
            _cover_kv("receipt_reason", row.get("kpi_receipt_reason_code", "")),
        )),
        ("Submission scope", _cover_join(
            _cover_kv("submission_scope", submission_scope_raw),
            _cover_kv("source_origin_class", source_origin_class),
        )),
        ("Submission readiness", _cover_join(
            _cover_kv("ready_now", submission_ready),
            _cover_kv("reason", submission_reason),
            _cover_kv("start_mode", submission_start_mode),
            _cover_kv("scope", submission_scope),
            _cover_kv("caution", submission_caution or submission_blocker),
        )),
        ("Evidence artifacts", _cover_join(
            _cover_kv("kpi_receipt", kpi_receipt_path),
            _cover_kv("primary_report", primary_report_path),
            _cover_kv("case_bundle_zip", case_bundle_zip_path),
            _cover_kv("case_bundle_dir", case_bundle_dir),
        )),
        ("Irregular benchmark receipts", _cover_join(
            _cover_kv("count", len(irregular_receipt_rows)),
            _cover_kv("index", irregular_receipt_index_json or "n/a"),
            _cover_kv("cases", irregular_receipt_cases),
        )),
        ("Reviewer name", attestation_slots["reviewer_name_slot"]),
        ("Reviewer role / license", attestation_slots["reviewer_role_or_license_slot"]),
        ("Reviewer signature", attestation_slots["reviewer_signature_slot"]),
        ("Receipt id", attestation_slots["receipt_id_slot"]),
        ("Receipt issued at", attestation_slots["receipt_issued_at_slot"]),
        ("Authority receipt", attestation_slots["authority_receipt_slot"]),
        ("Approval signature", attestation_slots["approval_signature_slot"]),
        ("Attestation workflow", _cover_join(
            _cover_kv("status", attestation_status),
            _cover_kv("source_kind", attestation_source_kind),
            _cover_kv("missing_fields", attestation_missing_fields),
        )),
        ("Attestation artifacts", _cover_join(
            _cover_kv("manifest", attestation_manifest_path),
            _cover_kv("template", attestation_template_path),
            _cover_kv("receipt", attestation_receipt_path),
        )),
        ("Attestation disclaimer", attestation_slots["attestation_disclaimer"]),
        ("Review boundary", _cover_join(
            _cover_kv("execution_mode", metrics.get("external_benchmark_execution_mode", "")),
            _cover_kv("ready_tasks", metrics.get("external_benchmark_execution_ready_task_count", 0)),
            _cover_kv("blocked_tasks", metrics.get("external_benchmark_execution_blocked_task_count", 0)),
            _cover_kv("pending", metrics.get("external_benchmark_execution_review_boundary_pending_count", 0)),
            _cover_kv("resolution", review_boundary_resolution),
            _cover_kv("owner", review_boundary_owner),
            _cover_kv("priority", review_boundary_priority),
            _cover_kv("family", review_boundary_family),
            _cover_kv("followup", review_boundary_followup),
        )),
        ("Authority routing", _cover_join(
            _cover_kv("baseline_seeded", authority_baseline_seeded),
            _cover_kv("changes", authority_changes),
            _cover_kv("added", authority_added),
            _cover_kv("removed", authority_removed),
            _cover_kv("warning_active", authority_warning_active),
        )),
        ("Instruction", EXTERNAL_CASE_COVER_INSTRUCTION),
    ]


def _slugify_external_case_id(case_id: str, index: int) -> str:
    slug = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in str(case_id or "").strip())
    slug = slug.strip("_")
    return f"{index:02d}.{slug or 'case'}"


def _build_external_benchmark_case_onepage_rows(
    external_benchmark_execution_status_manifest: dict,
) -> list[dict]:
    tasks = [
        task
        for task in (external_benchmark_execution_status_manifest.get("tasks") or [])
        if isinstance(task, dict)
    ]
    rows: list[dict] = []
    for task_index, task in enumerate(tasks, start=1):
        execution_status = str(task.get("execution_status", "") or "").strip().lower()
        kpi_receipt_path = str(task.get("kpi_receipt_path", "") or "").strip()
        if not kpi_receipt_path or execution_status not in {"ready", "completed"}:
            continue
        receipt_path = Path(kpi_receipt_path)
        if not receipt_path.exists():
            continue
        receipt = _load_json(receipt_path)
        kpi_rows = [row for row in (receipt.get("kpi_rows") or []) if isinstance(row, dict)]
        case_id = str(task.get("case_id", "") or "").strip()
        case_label = str(task.get("case_label", "") or "").strip()
        rows.append(
            {
                "task_id": str(task.get("task_id", "") or "").strip(),
                "case_id": case_id,
                "case_label": case_label,
                "benchmark_family": str(task.get("benchmark_family", "") or "").strip(),
                "hazard_family": str(task.get("hazard_family", "") or "").strip(),
                "topology_family": str(task.get("topology_family", "") or "").strip(),
                "load_path_family": str(task.get("load_path_family", "") or "").strip(),
                "execution_status": str(task.get("execution_status", "") or "").strip(),
                "lifecycle_status": str(task.get("lifecycle_status", "") or "").strip(),
                "source_origin_class": str(task.get("source_origin_class", "") or "").strip(),
                "submission_scope": str(task.get("submission_scope", "") or "").strip(),
                "primary_report_path": str(task.get("primary_report_path", "") or "").strip(),
                "kpi_receipt_path": kpi_receipt_path,
                "kpi_receipt_contract_pass": bool(receipt.get("contract_pass", False)),
                "kpi_receipt_reason_code": str(receipt.get("reason_code", "") or "").strip(),
                "kpi_receipt_summary_line": (
                    f"{case_label or case_id} | "
                    f"reason={str(receipt.get('reason_code', '') or '').strip() or 'n/a'} | "
                    f"kpi_count={int((receipt.get('summary') or {}).get('kpi_count', 0) or 0)} | "
                    f"supporting_reports={int((receipt.get('summary') or {}).get('supporting_report_count', 0) or 0)}"
                ),
                "kpi_rows": kpi_rows,
                "kpi_row_count": int(len(kpi_rows)),
                "case_bundle_dir": str(task.get("case_bundle_dir", "") or "").strip(),
                "case_bundle_zip_path": str(task.get("case_bundle_zip_path", "") or "").strip(),
                "case_onepage_base": f"{_slugify_external_case_id(case_id or task.get('task_id', 'case'), task_index)}.authority_onepage",
                "task_index": int(task_index),
            }
        )
    return rows


def _write_external_benchmark_case_attestation_workflow(
    summary: dict,
    row: dict,
    artifacts: dict,
    *,
    kickoff_dir: Path,
    case_dir: Path,
    case_dir_rel: Path,
    base: Path,
) -> dict[str, object]:
    case_slug = base.name
    template_dir = kickoff_dir / EXTERNAL_CASE_ATTESTATION_TEMPLATE_DIRNAME
    manifest_dir = kickoff_dir / EXTERNAL_CASE_ATTESTATION_MANIFEST_DIRNAME
    receipt_dir = kickoff_dir / EXTERNAL_CASE_ATTESTATION_RECEIPT_DIRNAME
    template_json_src = template_dir / f"{case_slug}.reviewer_attestation.template.json"
    template_md_src = template_dir / f"{case_slug}.reviewer_attestation.template.md"
    manifest_json_src = manifest_dir / f"{case_slug}.reviewer_attestation.manifest.json"
    receipt_json_src = receipt_dir / f"{case_slug}.reviewer_attestation.receipt.json"
    receipt_md_src = receipt_dir / f"{case_slug}.reviewer_attestation.receipt.md"

    template_payload = _build_external_case_attestation_template_payload(
        summary,
        row,
        artifacts,
        manifest_json_path=manifest_json_src,
    )
    _write_json(template_json_src, template_payload)
    template_md_src.write_text(
        _render_external_case_attestation_template_markdown(
            template_payload,
            manifest_json_path=manifest_json_src,
        ),
        encoding="utf-8",
    )

    manifest_payload, manifest_error = _load_optional_json_with_error(manifest_json_src)
    normalized_attestation = _normalize_external_case_attestation(
        manifest_payload if manifest_payload and not manifest_error else template_payload
    )
    source_kind = "manifest" if manifest_payload and not manifest_error else "template"

    receipt_payload = _build_external_case_attestation_receipt_payload(
        summary,
        row,
        artifacts,
        source_kind=source_kind,
        attestation=normalized_attestation,
        manifest_json_path=manifest_json_src,
        template_json_path=template_json_src,
        manifest_error=manifest_error,
    )
    _write_json(receipt_json_src, receipt_payload)
    receipt_md_src.write_text(
        _render_external_case_attestation_receipt_markdown(receipt_payload),
        encoding="utf-8",
    )

    bundle_template_json = case_dir / f"{case_slug}.attestation_template.json"
    bundle_template_md = case_dir / f"{case_slug}.attestation_template.md"
    bundle_receipt_json = case_dir / f"{case_slug}.attestation_receipt.json"
    bundle_receipt_md = case_dir / f"{case_slug}.attestation_receipt.md"
    shutil.copy2(template_json_src, bundle_template_json)
    shutil.copy2(template_md_src, bundle_template_md)
    shutil.copy2(receipt_json_src, bundle_receipt_json)
    shutil.copy2(receipt_md_src, bundle_receipt_md)

    bundle_manifest_json = case_dir / f"{case_slug}.attestation_manifest.json"
    if manifest_json_src.exists():
        shutil.copy2(manifest_json_src, bundle_manifest_json)
        bundle_manifest_rel = str((case_dir_rel / bundle_manifest_json.name).as_posix())
    else:
        bundle_manifest_rel = ""

    cover_sheet_slots = (
        receipt_payload.get("cover_sheet_slots")
        if isinstance(receipt_payload.get("cover_sheet_slots"), dict)
        else {}
    )
    workflow_connection = (
        receipt_payload.get("workflow_connection")
        if isinstance(receipt_payload.get("workflow_connection"), dict)
        else {}
    )
    return {
        "case_attestation_source_kind": source_kind,
        "case_attestation_status": str(receipt_payload.get("reason_code", "") or ""),
        "case_attestation_missing_fields": list(receipt_payload.get("missing_fields") or []),
        "case_attestation_manifest_source": str(manifest_json_src),
        "case_attestation_template_source": str(template_json_src),
        "case_attestation_receipt_source": str(receipt_json_src),
        "case_attestation_manifest_bundle": bundle_manifest_rel,
        "case_attestation_template_bundle": str((case_dir_rel / bundle_template_json.name).as_posix()),
        "case_attestation_template_md_bundle": str((case_dir_rel / bundle_template_md.name).as_posix()),
        "case_attestation_receipt_bundle": str((case_dir_rel / bundle_receipt_json.name).as_posix()),
        "case_attestation_receipt_md_bundle": str((case_dir_rel / bundle_receipt_md.name).as_posix()),
        "case_attestation_reviewer_name": str(cover_sheet_slots.get("reviewer_name_slot", "") or ""),
        "case_attestation_reviewer_role_or_license": str(
            cover_sheet_slots.get("reviewer_role_or_license_slot", "") or ""
        ),
        "case_attestation_reviewer_signature": str(
            cover_sheet_slots.get("reviewer_signature_slot", "") or ""
        ),
        "case_attestation_receipt_id": str(cover_sheet_slots.get("receipt_id_slot", "") or ""),
        "case_attestation_receipt_issued_at": str(
            cover_sheet_slots.get("receipt_issued_at_slot", "") or ""
        ),
        "case_attestation_authority_receipt": str(
            cover_sheet_slots.get("authority_receipt_slot", "") or ""
        ),
        "case_attestation_approval_signature": str(
            cover_sheet_slots.get("approval_signature_slot", "") or ""
        ),
        "case_attestation_manifest_error": manifest_error,
        "case_attestation_review_boundary_resolution_label": str(
            (receipt_payload.get("summary") or {}).get("review_boundary_resolution_label", "") or ""
        ),
        "case_attestation_workflow_connection": workflow_connection,
        "case_attestation_receipt_payload": receipt_payload,
    }


def _irregular_structure_appendix_html(source: dict, artifacts: dict) -> str:
    metrics = source.get("metrics") if isinstance(source.get("metrics"), dict) else source
    top5_rows = [row for row in (source.get("irregular_top5_families") or []) if isinstance(row, dict)]
    ready_tasks = [row for row in (source.get("irregular_benchmark_execution_ready_tasks") or []) if isinstance(row, dict)]
    blocked_tasks = [row for row in (source.get("irregular_benchmark_execution_blocked_tasks") or []) if isinstance(row, dict)]
    summary_line = str(
        metrics.get("irregular_structure_summary_line", "") or metrics.get("irregular_structure_track_summary_line", "") or ""
    ).strip()
    benchmark_summary_line = str(metrics.get("irregular_benchmark_execution_summary_line", "") or "").strip()
    if summary_line.lower() == "n/a":
        summary_line = ""
    if benchmark_summary_line.lower() == "n/a":
        benchmark_summary_line = ""
    if not summary_line and not top5_rows and not ready_tasks and not blocked_tasks:
        return ""
    counts_line = (
        f"families={int(metrics.get('irregular_structure_family_count', 0))} | "
        f"sources={int(metrics.get('irregular_structure_source_record_count', 0))} | "
        f"local_ready={int(metrics.get('irregular_structure_local_ready_count', 0))} | "
        f"remote_candidates={int(metrics.get('irregular_structure_remote_candidate_count', 0))} | "
        f"collected={int(metrics.get('irregular_structure_collected_count', 0))} | "
        f"native_roundtrip_candidates={int(metrics.get('irregular_structure_native_roundtrip_candidate_count', 0))} | "
        f"solver_candidates={int(metrics.get('irregular_structure_solver_benchmark_candidate_count', 0))} | "
        f"ai_candidates={int(metrics.get('irregular_structure_ai_learning_candidate_count', 0))} | "
        f"top5={int(metrics.get('irregular_structure_top5_count', len(top5_rows)))}"
    )
    visible_top5_rows = [
        row
        for row in top5_rows
        if str(row.get("family_id", "") or "").strip() not in EXTERNAL_ONEPAGE_HIDDEN_IRREGULAR_FAMILY_IDS
    ]
    family_ids = _external_surface_irregular_family_id_list(
        [
            str(row.get("family_id", "") or "").strip()
            for row in visible_top5_rows
            if str(row.get("family_id", "") or "").strip()
        ]
    )
    top5_ready_count = sum(1 for row in visible_top5_rows if str(row.get("execution_mode", "") or "") == "ready_local_now")
    top5_remote_count = sum(1 for row in visible_top5_rows if str(row.get("execution_mode", "") or "") != "ready_local_now")
    top5_table_html = (
        "<table style='margin-top:12px;'>"
        "<thead><tr><td>Priority</td><td>Family</td><td>Mode</td><td>Local Ready</td><td>Remote Needed</td><td>KPI Angle</td><td>Native Support</td><td>Source IDs</td></tr></thead>"
        "<tbody>"
        + "".join(
            f"<tr><td>{html.escape(str(row.get('priority', '')))}</td><td>{html.escape(str(row.get('family_id', '')))}</td>"
            f"<td>{html.escape(str(row.get('execution_mode_label', row.get('execution_mode', ''))))}</td><td>{html.escape(str(row.get('local_ready_source_count', '')))}</td>"
            f"<td>{html.escape(str(row.get('remote_candidate_source_count', '')))}</td><td>{html.escape(str(row.get('recommended_kpi_or_validation_angle', '')))}</td>"
            f"<td>{html.escape(str(row.get('native_support_summary', '') or 'n/a'))}</td>"
            f"<td>{html.escape(', '.join(str(item) for item in (row.get('source_ids') or []) if str(item).strip()))}</td></tr>"
            for row in visible_top5_rows
        )
        + "</tbody></table>"
        if visible_top5_rows
        else ""
    )
    task_rows_html = (
        "<table style='margin-top:12px;'>"
        "<thead><tr><td>Task</td><td>Case</td><td>Status</td><td>Origin</td><td>Input</td><td>KPI Receipt</td></tr></thead>"
        "<tbody>"
        + "".join(
            f"<tr><td>{html.escape(str(row.get('task_id', '')))}</td><td>{html.escape(str(row.get('case_id', '')))}</td>"
            f"<td>{html.escape(str(row.get('execution_status', '')))}</td><td>{html.escape(str(row.get('source_origin_class', '')))}</td>"
            f"<td>{html.escape(str(row.get('input_path', '')))}</td><td>{html.escape(str(row.get('kpi_receipt_path', '')))}</td></tr>"
            for row in (ready_tasks + blocked_tasks)
        )
        + "</tbody></table>"
        if (ready_tasks or blocked_tasks)
        else ""
    )
    return f"""
        <div style="margin-top: 18px;">
          <h3 style="margin-bottom: 8px;">Appendix: Irregular Structure Track</h3>
          <div class="note">{html.escape(summary_line or 'n/a')}</div>
          <div class="note" style="margin-top: 4px;">benchmark_manifest={html.escape(str(artifacts.get('irregular_benchmark_execution_manifest_json', '') or 'n/a'))}</div>
          <div class="note" style="margin-top: 4px;">{html.escape(counts_line)}</div>
          <div class="note" style="margin-top: 4px;">top5_split={html.escape(f'local_ready={top5_ready_count} | remote_needed={top5_remote_count} | family_ids={", ".join(family_ids) or "n/a"}')}</div>
          <div class="note" style="margin-top: 4px;">benchmark_execution_summary={html.escape(benchmark_summary_line or 'n/a')}</div>
          {top5_table_html}
          {task_rows_html}
        </div>
    """


def _external_benchmark_case_onepage_index_markdown(summary: dict, artifacts: dict) -> list[str]:
    rows = [row for row in (summary.get("external_benchmark_case_onepage_rows") or []) if isinstance(row, dict)]
    if not rows:
        return []
    metrics = summary.get("metrics") if isinstance(summary.get("metrics"), dict) else summary
    kr_preview_lines = _render_public_structural_preview_representatives_markdown(summary)
    lines = [
        "## Appendix: External Benchmark Case Onepages",
        "",
        f"- `summary`: `case_onepage_count={int(summary.get('external_benchmark_case_onepage_count', len(rows)))} | "
        f"index_md={artifacts.get('external_benchmark_case_onepage_index_md', '') or 'n/a'} | "
        f"index_html={artifacts.get('external_benchmark_case_onepage_index_html', '') or 'n/a'} | "
        f"index_pdf={artifacts.get('external_benchmark_case_onepage_index_pdf', '') or 'n/a'}`",
        (
            f"- `attestation_workflow`: `cases={int(metrics.get('external_benchmark_case_attestation_case_count', 0))} | "
            f"manifests={int(metrics.get('external_benchmark_case_attestation_manifest_count', 0))} | "
            f"templates={int(metrics.get('external_benchmark_case_attestation_template_count', 0))} | "
            f"receipts={int(metrics.get('external_benchmark_case_attestation_receipt_count', 0))} | "
            f"attested={int(metrics.get('external_benchmark_case_attestation_attested_count', 0))} | "
            f"status={metrics.get('external_benchmark_case_attestation_status_label', '') or 'none'} | "
            f"kickoff_index={artifacts.get('external_benchmark_case_attestation_index_json', '') or 'n/a'}`"
        ),
        f"- `cover_sheet`: `{EXTERNAL_CASE_COVER_TITLE} | {EXTERNAL_CASE_COVER_NOTE}`",
        (
            f"- `shared native roundtrip appendix`: md=`{artifacts.get('midas_native_roundtrip_appendix_markdown', '') or 'n/a'}` | "
            f"json=`{artifacts.get('midas_native_roundtrip_appendix_json', '') or 'n/a'}`"
        ),
        (
            f"- `shared row provenance report`: json=`{artifacts.get('midas_kds_row_provenance_export_report', '') or 'n/a'}` | "
            f"csv=`{artifacts.get('midas_kds_row_provenance_export_csv', '') or 'n/a'}`"
        ),
        "",
        *kr_preview_lines,
        "| Case | Family | Status | Attestation | Workflow Receipt | KPI Receipt | Irregular Receipts | Onepage MD | Onepage HTML | Onepage PDF |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        irregular_summary = _render_irregular_benchmark_receipt_index_markdown(row, "../artifacts")
        lines.append(
            f"| {row.get('case_label', row.get('case_id', ''))} | {row.get('benchmark_family', '')} | "
            f"{row.get('execution_status', '')}/{row.get('lifecycle_status', '')} | "
            f"{row.get('case_attestation_status', '') or 'n/a'} ({row.get('case_attestation_source_kind', '') or 'n/a'}) | "
            f"`{row.get('case_attestation_receipt_bundle', '') or row.get('case_attestation_receipt_source', '')}` | "
            f"`{row.get('kpi_receipt_path', '')}` | {irregular_summary} | `{row.get('case_onepage_md', '')}` | "
            f"`{row.get('case_onepage_html', '')}` | `{row.get('case_onepage_pdf', '')}` |"
        )
    lines.append("")
    return lines


def _external_benchmark_case_onepage_index_html(summary: dict, artifacts: dict) -> str:
    rows = [row for row in (summary.get("external_benchmark_case_onepage_rows") or []) if isinstance(row, dict)]
    if not rows:
        return ""
    metrics = summary.get("metrics") if isinstance(summary.get("metrics"), dict) else summary
    kr_preview_html = _render_public_structural_preview_representatives_html(summary)
    rows_html = "".join(
        (
            (
                lambda irregular_html: f"<tr><td>{row.get('case_label', row.get('case_id', ''))}</td>"
                f"<td>{row.get('benchmark_family', '')}</td>"
                f"<td>{row.get('execution_status', '')}/{row.get('lifecycle_status', '')}</td>"
                f"<td>{row.get('case_attestation_status', '') or 'n/a'} ({row.get('case_attestation_source_kind', '') or 'n/a'})</td>"
                f"<td>{row.get('case_attestation_receipt_bundle', '') or row.get('case_attestation_receipt_source', '')}</td>"
                f"<td>{row.get('kpi_receipt_path', '')}</td>"
                f"<td>{irregular_html}</td>"
                f"<td>{row.get('case_onepage_md', '')}</td>"
                f"<td>{row.get('case_onepage_html', '')}</td>"
                f"<td>{row.get('case_onepage_pdf', '')}</td></tr>"
            )(_render_irregular_benchmark_receipt_index_html(row, "../artifacts"))
        )
        for row in rows
    )
    return f"""
        <div style="margin-top: 18px;">
          <h3 style="margin-bottom: 8px;">Appendix: External Benchmark Case Onepages</h3>
          <div class="note">
            case_onepage_count={int(summary.get('external_benchmark_case_onepage_count', len(rows)))} |
            index_md={artifacts.get('external_benchmark_case_onepage_index_md', '') or 'n/a'} |
            index_html={artifacts.get('external_benchmark_case_onepage_index_html', '') or 'n/a'} |
            index_pdf={artifacts.get('external_benchmark_case_onepage_index_pdf', '') or 'n/a'}
          </div>
          <div class="note" style="margin-top: 4px;">
            attestation_workflow:
            cases={int(metrics.get('external_benchmark_case_attestation_case_count', 0))} |
            manifests={int(metrics.get('external_benchmark_case_attestation_manifest_count', 0))} |
            templates={int(metrics.get('external_benchmark_case_attestation_template_count', 0))} |
            receipts={int(metrics.get('external_benchmark_case_attestation_receipt_count', 0))} |
            attested={int(metrics.get('external_benchmark_case_attestation_attested_count', 0))} |
            status={metrics.get('external_benchmark_case_attestation_status_label', '') or 'none'} |
            kickoff_index={artifacts.get('external_benchmark_case_attestation_index_json', '') or 'n/a'}
          </div>
          <div class="note" style="margin-top: 4px;">
            cover_sheet={EXTERNAL_CASE_COVER_TITLE} | {EXTERNAL_CASE_COVER_NOTE}
          </div>
          <div class="note" style="margin-top: 4px;">
            shared native roundtrip appendix:
            md={artifacts.get('midas_native_roundtrip_appendix_markdown', '') or 'n/a'} |
            json={artifacts.get('midas_native_roundtrip_appendix_json', '') or 'n/a'}
          </div>
          <div class="note" style="margin-top: 4px;">
            shared row provenance report:
            json={artifacts.get('midas_kds_row_provenance_export_report', '') or 'n/a'} |
            csv={artifacts.get('midas_kds_row_provenance_export_csv', '') or 'n/a'}
          </div>
          {kr_preview_html}
          <table style="margin-top: 12px;">
            <thead>
              <tr><td>Case</td><td>Family</td><td>Status</td><td>Attestation</td><td>Workflow Receipt</td><td>KPI Receipt</td><td>Irregular Receipts</td><td>Onepage MD</td><td>Onepage HTML</td><td>Onepage PDF</td></tr>
            </thead>
            <tbody>
              {rows_html or '<tr><td colspan="10">No case onepages available.</td></tr>'}
            </tbody>
          </table>
        </div>
    """


def _render_external_benchmark_case_onepage_markdown(
    summary: dict,
    row: dict,
    bundle_artifact_prefix: str,
    main_onepage_relpath: str,
) -> list[str]:
    kpi_rows = [item for item in (row.get("kpi_rows") or []) if isinstance(item, dict)]
    cover_fields = _external_benchmark_case_onepage_cover_fields(summary, row)
    irregular_receipt_lines = _render_irregular_benchmark_receipt_markdown_lines(row, bundle_artifact_prefix)
    special_member_lines, _, _ = _case_onepage_special_member_lines(summary, bundle_artifact_prefix)
    irregular_canonical_promotion_queue_rows = _external_surface_irregular_canonical_promotion_queue_rows(summary)
    lines = [
        f"# Authority-Facing Case Onepage: {row.get('case_label', row.get('case_id', 'Case'))}",
        "",
        f"## {EXTERNAL_CASE_COVER_TITLE}",
        "",
        EXTERNAL_CASE_COVER_NOTE,
        "",
    ]
    for label, value in cover_fields:
        lines.append(f"- `{label}`: `{value}`")
    lines.extend(
        [
            "",
            "## KPI Receipt",
            "",
            "| Label | Source | Value |",
            "|---|---|---:|",
        ]
    )
    for item in kpi_rows:
        lines.append(f"| {item.get('label', '')} | {item.get('source', '')} | {item.get('value', '')} |")
    if not kpi_rows:
        lines.append("| n/a | n/a | n/a |")
    lines.extend(
        [
            "",
            "## Attestation Workflow",
            "",
            f"- `status`: `{row.get('case_attestation_status', '') or 'n/a'}`",
            f"- `source_kind`: `{row.get('case_attestation_source_kind', '') or 'n/a'}`",
            f"- `missing_fields`: `{', '.join(row.get('case_attestation_missing_fields', []) or []) or 'none'}`",
            f"- `attestation_manifest`: `{row.get('case_attestation_manifest_bundle', '') or 'n/a'}`",
            f"- `attestation_template`: `{row.get('case_attestation_template_bundle', '') or 'n/a'}`",
            f"- `attestation_receipt`: `{row.get('case_attestation_receipt_bundle', '') or 'n/a'}`",
            (
                f"- `workflow_connection`: `review_boundary={row.get('case_attestation_review_boundary_resolution_label', '') or 'n/a'} | "
                f"batch_template={((row.get('case_attestation_workflow_connection') or {}).get('audit_review_decision_batch_template_json', '') or 'n/a')} | "
                f"batch_runner={((row.get('case_attestation_workflow_connection') or {}).get('audit_review_decision_batch_run_report_json', '') or 'n/a')} | "
                f"live_ready_template={((row.get('case_attestation_workflow_connection') or {}).get('audit_review_decision_batch_approve_all_live_ready_template_json', '') or 'n/a')}`"
            ),
            "",
            "## Shared Appendices",
            "",
            f"- `main external validation onepage`: `{main_onepage_relpath}`",
            f"- `native roundtrip appendix markdown`: `{_bundle_artifact_link(str(row.get('midas_native_roundtrip_appendix_markdown', '')), bundle_artifact_prefix)}`",
            f"- `native roundtrip appendix json`: `{_bundle_artifact_link(str(row.get('midas_native_roundtrip_appendix_json', '')), bundle_artifact_prefix)}`",
            f"- `row provenance report`: `{_bundle_artifact_link(str(row.get('midas_kds_row_provenance_export_report', '')), bundle_artifact_prefix)}`",
            f"- `row provenance csv`: `{_bundle_artifact_link(str(row.get('midas_kds_row_provenance_export_csv', '')), bundle_artifact_prefix)}`",
            "",
        ]
    )
    lines.extend(special_member_lines)
    if irregular_canonical_promotion_queue_rows:
        lines.extend(
            [
                "## Canonical Readiness Note",
                "",
                EXTERNAL_CANONICAL_READINESS_NOTE_SHORT,
                "",
                "| Family | Status | Canonical Path | Native Support | Blocker |",
                "|---|---|---|---|---|",
            ]
        )
        for item in irregular_canonical_promotion_queue_rows:
            support = str(item.get("native_support", "") or "n/a")
            lines.append(
                f"| {item.get('family_id', '')} | {item.get('status', '') or 'n/a'} | "
                f"{item.get('promotion_path', '') or 'n/a'} | {support} | {item.get('blocker', '') or 'n/a'} |"
            )
        lines.extend(
            [
                "",
            ]
        )
    lines.extend(
        [
            "## Irregular Benchmark Receipts",
            "",
        ]
    )
    for line in irregular_receipt_lines:
        lines.append(f"- `{line}`")
    lines.append("")
    return lines


def _render_external_benchmark_case_onepage_html(
    summary: dict,
    row: dict,
    bundle_artifact_prefix: str,
    main_onepage_relpath: str,
) -> str:
    kpi_rows = [item for item in (row.get("kpi_rows") or []) if isinstance(item, dict)]
    cover_fields = _external_benchmark_case_onepage_cover_fields(summary, row)
    irregular_receipts_html = _render_irregular_benchmark_receipt_html(row, bundle_artifact_prefix)
    _, special_member_html, _ = _case_onepage_special_member_lines(summary, bundle_artifact_prefix)
    irregular_canonical_promotion_queue_rows = _external_surface_irregular_canonical_promotion_queue_rows(summary)
    case_label = _external_surface_text(row.get("case_label", row.get("case_id", "Case")), default="Case")
    case_id = _external_surface_text(row.get("case_id", ""), default=case_label)
    attestation_status = _external_surface_text(row.get("case_attestation_status", ""))
    attestation_tone = _external_case_attestation_tone(attestation_status)
    missing_fields = [str(item).strip() for item in (row.get("case_attestation_missing_fields") or []) if str(item).strip()]
    missing_fields_label = ", ".join(missing_fields) or "none"
    workflow_connection = row.get("case_attestation_workflow_connection") if isinstance(row.get("case_attestation_workflow_connection"), dict) else {}
    workflow_document_count = sum(
        1
        for value in (
            row.get("case_attestation_manifest_bundle", ""),
            row.get("case_attestation_template_bundle", ""),
            row.get("case_attestation_receipt_bundle", ""),
            workflow_connection.get("audit_review_decision_batch_template_json", ""),
            workflow_connection.get("audit_review_decision_batch_run_report_json", ""),
            workflow_connection.get("audit_review_decision_batch_approve_all_live_ready_template_json", ""),
        )
        if str(value or "").strip()
    )
    irregular_receipt_count = len(_irregular_benchmark_receipt_artifacts(row, bundle_artifact_prefix))
    attestation_status_chip = _external_surface_status_chip_html(attestation_status, attestation_tone)
    review_boundary_label = _external_surface_text(row.get("case_attestation_review_boundary_resolution_label", ""))
    review_boundary_chip = _external_surface_status_chip_html(
        review_boundary_label,
        "accent" if review_boundary_label.lower() not in {"n/a", "none", "missing"} else "warn",
    )
    cover_rows_html = "".join(
        f"<tr><th>{html.escape(label)}</th><td>{html.escape(value)}</td></tr>"
        for label, value in cover_fields
    )
    kpi_rows_html = "".join(
        f"<tr><td>{item.get('label', '')}</td><td>{item.get('source', '')}</td><td>{item.get('value', '')}</td></tr>"
        for item in kpi_rows
    ) or "<tr><td colspan='3'>No KPI rows available.</td></tr>"
    irregular_bridged_rows_html = "".join(
        f"<tr><td>{html.escape(str(item.get('family_id', '') or 'n/a'))}</td>"
        f"<td>{html.escape(str(item.get('status', '') or 'n/a'))}</td>"
        f"<td>{html.escape(str(item.get('promotion_path', '') or 'n/a'))}</td>"
        f"<td>{html.escape(str(item.get('native_support', '') or 'n/a'))}</td>"
        f"<td>{html.escape(str(item.get('blocker', '') or 'n/a'))}</td></tr>"
        for item in irregular_canonical_promotion_queue_rows
    )
    irregular_bridged_html = (
        """
          <h2>Canonical Readiness Note</h2>
          <div class="note">"""
        + html.escape(EXTERNAL_CANONICAL_READINESS_NOTE_SHORT)
        + """</div>
          <table>
            <thead><tr><th>Family</th><th>Status</th><th>Canonical Path</th><th>Native Support</th><th>Blocker</th></tr></thead>
            <tbody>"""
        + (irregular_bridged_rows_html or "<tr><td colspan='5'>No unresolved bridged families.</td></tr>")
        + "</tbody></table>"
    ) if irregular_canonical_promotion_queue_rows else ""
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Structural Signal Desk | Authority Case Onepage</title>
  <style>
    {build_signal_desk_light_css()}
    * {{ box-sizing:border-box; }}
    body {{
      color:var(--ink);
      font-family:var(--font-ui);
    }}
    a {{
      color:var(--brand);
      text-decoration:none;
    }}
    a:hover {{
      text-decoration:underline;
    }}
    .wrap {{
      max-width:1320px;
      margin:0 auto;
      padding:32px 24px 72px;
    }}
    .hero {{
      display:grid;
      grid-template-columns:minmax(0, 1.08fr) minmax(320px, .92fr);
      gap:20px;
      align-items:stretch;
    }}
    .hero-main {{
      padding:30px;
      border-radius:var(--radius-xl);
      background:
        radial-gradient(circle at 18% 10%, rgba(255,255,255,.14), rgba(255,255,255,0) 34%),
        var(--review-hero-bg);
      color:#f4fbfc;
      box-shadow:var(--shadow-hero);
    }}
    .hero-kicker,
    .panel-kicker,
    .signal-label,
    .receipt-kicker {{
      font-size:var(--type-label-size);
      font-weight:700;
      line-height:var(--type-label-line-height);
      letter-spacing:var(--type-label-tracking);
      text-transform:uppercase;
    }}
    .hero-kicker {{
      color:#d5eff0;
      margin-bottom:12px;
    }}
    .hero-main h1 {{
      margin:0 0 12px;
      font-family:var(--font-display);
      font-size:var(--type-h1-size);
      line-height:var(--type-h1-line-height);
      letter-spacing:var(--type-h1-tracking);
    }}
    .hero-main p {{
      margin:0;
      max-width:64ch;
      font-size:15px;
      line-height:1.72;
      color:#e1f1f2;
    }}
    .hero-pill-row,
    .status-row {{
      display:flex;
      flex-wrap:wrap;
      gap:10px;
    }}
    .hero-pill-row {{
      margin-top:18px;
    }}
    .hero-pill {{
      display:inline-flex;
      align-items:center;
      min-height:34px;
      padding:0 12px;
      border-radius:var(--radius-pill);
      background:rgba(255,255,255,.12);
      border:1px solid rgba(255,255,255,.18);
      color:#f4fbfc;
      font-size:12px;
      font-weight:700;
      box-shadow:inset 0 1px 0 rgba(255,255,255,.08);
    }}
    .hero-side,
    .panel,
    .signal-card {{
      border-radius:var(--radius-lg);
      background:var(--review-panel-bg);
      border:1px solid var(--line);
      box-shadow:var(--shadow-panel);
    }}
    .hero-side {{
      padding:24px;
      display:grid;
      gap:16px;
      align-content:start;
    }}
    .hero-side h2,
    .panel h2 {{
      margin:0;
      font-family:var(--font-display);
      font-size:var(--type-h2-size);
      line-height:var(--type-h2-line-height);
      letter-spacing:var(--type-h2-tracking);
    }}
    .hero-side p,
    .panel-lead,
    .note,
    .mini-note,
    .detail-row,
    table {{
      font-size:var(--type-body-size);
      line-height:var(--type-body-line-height);
      letter-spacing:var(--type-body-tracking);
    }}
    .hero-side p,
    .panel-lead,
    .note,
    .mini-note {{
      color:var(--muted);
    }}
    .receipt-kicker,
    .panel-kicker {{
      color:var(--brand);
    }}
    .status-chip {{
      display:inline-flex;
      align-items:center;
      min-height:34px;
      padding:0 12px;
      border-radius:var(--radius-pill);
      background:var(--review-pill-bg);
      border:1px solid var(--review-pill-border);
      color:var(--review-pill-ink);
      font-size:12px;
      font-weight:700;
      letter-spacing:var(--type-body-tracking);
    }}
    .status-chip.is-ok {{
      background:rgba(47,125,90,.12);
      border-color:rgba(47,125,90,.18);
      color:var(--success);
    }}
    .status-chip.is-warn {{
      background:var(--review-pill-warm-bg);
      border-color:var(--review-pill-warm-border);
      color:var(--accent-warm-ink);
    }}
    .status-chip.is-danger {{
      background:rgba(161,73,46,.12);
      border-color:rgba(161,73,46,.18);
      color:var(--danger);
    }}
    .status-chip.is-accent {{
      background:rgba(79,183,173,.16);
      border-color:rgba(15,106,115,.16);
      color:var(--brand);
    }}
    .detail-stack {{
      display:grid;
      gap:12px;
    }}
    .detail-row {{
      display:grid;
      grid-template-columns:minmax(116px, 160px) 1fr;
      gap:12px;
      padding:12px 14px;
      border:1px solid rgba(15,106,115,.10);
      border-radius:var(--radius-md);
      background:rgba(255,255,255,.58);
      color:var(--ink);
      align-items:start;
    }}
    .detail-row > span:first-child {{
      color:var(--muted);
      font-size:var(--type-label-size);
      font-weight:700;
      line-height:var(--type-label-line-height);
      letter-spacing:var(--type-label-tracking);
      text-transform:uppercase;
    }}
    .detail-row strong {{
      color:var(--ink);
      font-weight:700;
    }}
    code {{
      display:inline-flex;
      align-items:center;
      padding:2px 8px;
      border-radius:var(--radius-pill);
      background:var(--review-meta-bg);
      color:var(--review-meta-ink);
      font-family:'IBM Plex Mono','SFMono-Regular',monospace;
      font-size:12px;
      word-break:break-all;
    }}
    .signal-strip {{
      display:grid;
      grid-template-columns:repeat(4, minmax(0, 1fr));
      gap:16px;
      margin-top:20px;
    }}
    .signal-card {{
      padding:18px;
      position:relative;
      overflow:hidden;
    }}
    .signal-card::before,
    .panel::before {{
      content:'';
      position:absolute;
      inset:0;
      background:linear-gradient(180deg, rgba(255,255,255,.56) 0%, rgba(255,255,255,0) 44%);
      pointer-events:none;
    }}
    .signal-label {{
      color:var(--muted);
      position:relative;
      z-index:1;
    }}
    .signal-value {{
      margin-top:8px;
      position:relative;
      z-index:1;
      font-family:var(--font-display);
      font-size:var(--type-metric-size);
      line-height:var(--type-metric-line-height);
      letter-spacing:var(--type-metric-tracking);
      color:var(--ink);
    }}
    .signal-note {{
      margin-top:8px;
      position:relative;
      z-index:1;
      color:var(--muted);
      font-size:13px;
      line-height:1.65;
    }}
    .grid {{
      display:grid;
      grid-template-columns:repeat(12, minmax(0, 1fr));
      gap:18px;
      margin-top:24px;
    }}
    .panel {{
      grid-column:span 6;
      position:relative;
      overflow:hidden;
      padding:22px;
      background:var(--review-panel-quiet-bg);
    }}
    .panel.panel-wide {{
      grid-column:1 / -1;
    }}
    .panel.span-7 {{
      grid-column:span 7;
    }}
    .panel.span-5 {{
      grid-column:span 5;
    }}
    .panel-head {{
      position:relative;
      z-index:1;
      display:flex;
      justify-content:space-between;
      gap:16px;
      align-items:flex-start;
      margin-bottom:16px;
    }}
    .panel-lead {{
      margin:10px 0 0;
      max-width:72ch;
    }}
    table {{
      position:relative;
      z-index:1;
      width:100%;
      border-collapse:separate;
      border-spacing:0;
      margin-top:14px;
      border:1px solid rgba(15,106,115,.12);
      border-radius:18px;
      overflow:hidden;
      background:rgba(255,255,255,.56);
    }}
    th,
    td {{
      padding:12px 14px;
      text-align:left;
      vertical-align:top;
      border-bottom:1px solid rgba(216,207,191,.78);
      color:var(--ink);
    }}
    thead th,
    thead td {{
      background:rgba(15,106,115,.08);
      color:var(--brand);
      font-size:var(--type-label-size);
      font-weight:700;
      line-height:var(--type-label-line-height);
      letter-spacing:var(--type-label-tracking);
      text-transform:uppercase;
    }}
    tbody tr:nth-child(even) td {{
      background:rgba(255,253,248,.84);
    }}
    tbody tr:last-child td {{
      border-bottom:none;
    }}
    .cover-table th {{
      width:28%;
      background:rgba(15,106,115,.06);
    }}
    ul {{
      position:relative;
      z-index:1;
      margin:12px 0 0 18px;
      padding:0;
      color:var(--muted);
    }}
    .appendix-stack > * + * {{
      margin-top:18px;
    }}
    .panel h3,
    .panel h4 {{
      position:relative;
      z-index:1;
      margin:16px 0 8px;
      font-family:var(--font-display);
      color:var(--ink);
    }}
    @media (max-width:1080px) {{
      .hero,
      .signal-strip {{
        grid-template-columns:1fr;
      }}
      .panel,
      .panel.span-7,
      .panel.span-5 {{
        grid-column:1 / -1;
      }}
      .panel-head {{
        flex-direction:column;
      }}
    }}
    @media (max-width:640px) {{
      .wrap {{
        padding:22px 14px 48px;
      }}
      .hero-main,
      .hero-side,
      .panel,
      .signal-card {{
        padding:18px;
      }}
      .detail-row {{
        grid-template-columns:1fr;
      }}
      th,
      td {{
        padding:10px 12px;
      }}
    }}
  </style>
</head>
<body class="signal-desk-light">
  <div class="wrap">
    <section class="hero">
      <div class="hero-main">
        <div class="hero-kicker">Structural Signal Desk | External authority evidence</div>
        <h1>Authority-Facing Case Onepage</h1>
        <p>This export keeps the reviewer cover sheet, KPI receipt, attestation workflow, and shared structural appendices in one premium evidence package so {html.escape(case_label)} can move through review without reverting to a plain memo surface.</p>
        <div class="hero-pill-row">
          <span class="hero-pill">case={html.escape(case_id)}</span>
          <span class="hero-pill">kpi_rows={len(kpi_rows)}</span>
          <span class="hero-pill">missing_fields={len(missing_fields)}</span>
          <span class="hero-pill">receipts={irregular_receipt_count}</span>
        </div>
      </div>
      <aside class="hero-side">
        <div>
          <div class="receipt-kicker">Review cover</div>
          <h2>{EXTERNAL_CASE_COVER_TITLE}</h2>
          <p>{EXTERNAL_CASE_COVER_NOTE} {EXTERNAL_CASE_COVER_INSTRUCTION} {EXTERNAL_CASE_COVER_DISCLAIMER}</p>
        </div>
        <div class="detail-stack">
          <div class="detail-row"><span>Case label</span><strong>{html.escape(case_label)}</strong></div>
          <div class="detail-row"><span>Case id</span><code>{html.escape(case_id)}</code></div>
          <div class="detail-row"><span>Attestation status</span>{attestation_status_chip}</div>
          <div class="detail-row"><span>Review boundary</span>{review_boundary_chip}</div>
        </div>
      </aside>
    </section>

    <section class="signal-strip">
      <article class="signal-card">
        <div class="signal-label">KPI receipt rows</div>
        <div class="signal-value">{len(kpi_rows)}</div>
        <div class="signal-note">Receipt labels, sources, and values stay attached to the authority-facing cover workflow.</div>
      </article>
      <article class="signal-card">
        <div class="signal-label">Missing attestation fields</div>
        <div class="signal-value">{len(missing_fields)}</div>
        <div class="signal-note">{html.escape(missing_fields_label)}</div>
      </article>
      <article class="signal-card">
        <div class="signal-label">Workflow documents</div>
        <div class="signal-value">{workflow_document_count}</div>
        <div class="signal-note">Manifest, template, receipt, and batch-review handoff artifacts linked below.</div>
      </article>
      <article class="signal-card">
        <div class="signal-label">Irregular receipts</div>
        <div class="signal-value">{irregular_receipt_count}</div>
        <div class="signal-note">Benchmark receipt references remain attached to this case package for reviewer traceability.</div>
      </article>
    </section>

    <section class="grid">
      <article class="panel panel-wide">
        <div class="panel-head">
          <div>
            <div class="panel-kicker">Reviewer handoff</div>
            <h2>{EXTERNAL_CASE_COVER_TITLE}</h2>
            <p class="panel-lead">The cover sheet keeps reviewer identity, case routing, and execution context in one structured desk-style table instead of a plain document block.</p>
          </div>
          <div class="status-row">
            {attestation_status_chip}
            {review_boundary_chip}
          </div>
        </div>
        <table class="cover-table">
          <tbody>{cover_rows_html}</tbody>
        </table>
      </article>

      <article class="panel span-7">
        <div class="panel-head">
          <div>
            <div class="panel-kicker">Receipt evidence</div>
            <h2>KPI Receipt</h2>
            <p class="panel-lead">Label, source, and value lines are preserved as the authority-facing evidence register for this case.</p>
          </div>
          <div class="status-row">
            {_external_surface_status_chip_html(f"{len(kpi_rows)} rows", "accent")}
          </div>
        </div>
        <table>
          <thead><tr><th>Label</th><th>Source</th><th>Value</th></tr></thead>
          <tbody>{kpi_rows_html}</tbody>
        </table>
      </article>

      <article class="panel span-5">
        <div class="panel-head">
          <div>
            <div class="panel-kicker">Workflow state</div>
            <h2>Attestation Workflow</h2>
            <p class="panel-lead">The current status, source kind, missing fields, and batch-review linkage remain explicit for reviewer follow-through.</p>
          </div>
          <div class="status-row">
            {attestation_status_chip}
          </div>
        </div>
        <div class="detail-stack">
          <div class="detail-row"><span>Status</span>{attestation_status_chip}</div>
          <div class="detail-row"><span>Source kind</span><strong>{html.escape(_external_surface_text(row.get('case_attestation_source_kind', '')))}</strong></div>
          <div class="detail-row"><span>Missing fields</span><strong>{html.escape(missing_fields_label)}</strong></div>
          <div class="detail-row"><span>Attestation manifest</span><strong>{html.escape(_external_surface_text(row.get('case_attestation_manifest_bundle', '')))}</strong></div>
          <div class="detail-row"><span>Attestation template</span><strong>{html.escape(_external_surface_text(row.get('case_attestation_template_bundle', '')))}</strong></div>
          <div class="detail-row"><span>Attestation receipt</span><strong>{html.escape(_external_surface_text(row.get('case_attestation_receipt_bundle', '')))}</strong></div>
          <div class="detail-row"><span>Batch template</span><strong>{html.escape(_external_surface_text(workflow_connection.get('audit_review_decision_batch_template_json', '')))}</strong></div>
          <div class="detail-row"><span>Batch runner</span><strong>{html.escape(_external_surface_text(workflow_connection.get('audit_review_decision_batch_run_report_json', '')))}</strong></div>
          <div class="detail-row"><span>Live-ready template</span><strong>{html.escape(_external_surface_text(workflow_connection.get('audit_review_decision_batch_approve_all_live_ready_template_json', '')))}</strong></div>
        </div>
      </article>

      <article class="panel panel-wide">
        <div class="panel-head">
          <div>
            <div class="panel-kicker">Shared package links</div>
            <h2>Shared Appendices</h2>
            <p class="panel-lead">The main external one-page, native roundtrip evidence, row provenance exports, and reviewer-facing bridge notes stay linked as one review family.</p>
          </div>
          <div class="status-row">
            {_external_surface_status_chip_html("shared evidence bundle", "accent")}
          </div>
        </div>
        <div class="appendix-stack">
          <div class="detail-stack">
            <div class="detail-row"><span>Main onepage</span><strong>{html.escape(main_onepage_relpath)}</strong></div>
            <div class="detail-row"><span>native roundtrip appendix markdown</span><strong>{html.escape(_bundle_artifact_link(str(row.get('midas_native_roundtrip_appendix_markdown', '')), bundle_artifact_prefix))}</strong></div>
            <div class="detail-row"><span>native roundtrip appendix json</span><strong>{html.escape(_bundle_artifact_link(str(row.get('midas_native_roundtrip_appendix_json', '')), bundle_artifact_prefix))}</strong></div>
            <div class="detail-row"><span>row provenance report</span><strong>{html.escape(_bundle_artifact_link(str(row.get('midas_kds_row_provenance_export_report', '')), bundle_artifact_prefix))}</strong></div>
            <div class="detail-row"><span>row provenance csv</span><strong>{html.escape(_bundle_artifact_link(str(row.get('midas_kds_row_provenance_export_csv', '')), bundle_artifact_prefix))}</strong></div>
          </div>
          {special_member_html}
          {irregular_bridged_html}
        </div>
      </article>

      <article class="panel panel-wide">
        <div class="panel-head">
          <div>
            <div class="panel-kicker">Receipt traceability</div>
            <h2>Irregular Benchmark Receipts</h2>
            <p class="panel-lead">Receipt references remain visible as direct review links rather than getting buried in appendix prose.</p>
          </div>
          <div class="status-row">
            {_external_surface_status_chip_html(f"{irregular_receipt_count} linked receipts", "accent" if irregular_receipt_count else "warn")}
          </div>
        </div>
        {irregular_receipts_html}
      </article>
    </section>
  </div>
</body>
</html>
"""


def _case_onepage_special_member_lines(summary: dict, bundle_artifact_prefix: str) -> tuple[list[str], str, list[str]]:
    metrics = summary.get("metrics") if isinstance(summary.get("metrics"), dict) else summary
    direct_patch_label = _format_action_family_counts(
        metrics.get("mgt_export_special_member_direct_patch_action_family_counts")
    )
    supported_label = _format_action_family_counts(
        metrics.get("mgt_export_special_member_supported_action_family_counts")
    )
    zero_touch_label = _format_action_family_counts(
        metrics.get("mgt_export_special_member_zero_touch_verified_action_family_counts")
    )
    queue_rows = [
        row
        for row in (summary.get("exact_topology_structural_preview_promotion_queue_rows") or [])
        if isinstance(row, dict)
    ]
    if not queue_rows:
        queue_rows = _pending_exact_topology_archive_candidate_rows()
    queue_state = (
        "No additional supported exact-topology archive candidates are pending right now. "
        "This queue reopens automatically when a new public archive decoded preview lands with exact_topology_candidate=true."
    )
    if queue_rows:
        queue_state = (
            f"pending_supported_candidates={len(queue_rows)} | "
            + ", ".join(str(row.get("source_id", "") or "n/a") for row in queue_rows[:5])
        )
    queue_json = _bundle_artifact_link(
        str((summary.get("artifacts") or {}).get("exact_topology_structural_preview_promotion_queue_json", "") or ""),
        bundle_artifact_prefix,
    )
    queue_md = _bundle_artifact_link(
        str((summary.get("artifacts") or {}).get("exact_topology_structural_preview_promotion_queue_md", "") or ""),
        bundle_artifact_prefix,
    )
    markdown_lines = [
        "## Native Authoring Coverage",
        "",
        f"- `special_member_family`: direct_patch=`{direct_patch_label}` | supported=`{supported_label}` | zero_touch_verified=`{zero_touch_label}`",
        f"- `kr_promotion_queue`: `{queue_state}`",
        f"- `kr_promotion_queue_json`: `{queue_json or 'n/a'}`",
        f"- `kr_promotion_queue_md`: `{queue_md or 'n/a'}`",
        "",
    ]
    html_block = f"""
          <h2>Native Authoring Coverage</h2>
          <div class="note">special_member_family: direct_patch={html.escape(direct_patch_label)} | supported={html.escape(supported_label)} | zero_touch_verified={html.escape(zero_touch_label)}</div>
          <div class="note">kr_promotion_queue: {html.escape(queue_state)}</div>
          <div class="note">kr_promotion_queue_json: {html.escape(queue_json or 'n/a')}</div>
          <div class="note">kr_promotion_queue_md: {html.escape(queue_md or 'n/a')}</div>
    """
    pdf_lines = [
        f"special_member_family: direct_patch={direct_patch_label} | supported={supported_label} | zero_touch_verified={zero_touch_label}",
        f"kr_promotion_queue: {queue_state}",
        f"kr_promotion_queue_json: {queue_json or 'n/a'}",
        f"kr_promotion_queue_md: {queue_md or 'n/a'}",
    ]
    return markdown_lines, html_block, pdf_lines


def _write_external_benchmark_case_onepage_pdf(
    path: Path,
    summary: dict,
    row: dict,
    main_onepage_relpath: str,
    bundle_artifact_prefix: str,
) -> None:
    kpi_rows = [item for item in (row.get("kpi_rows") or []) if isinstance(item, dict)]
    cover_fields = _external_benchmark_case_onepage_cover_fields(summary, row)
    irregular_receipt_lines = _render_irregular_benchmark_receipt_text_lines(row, bundle_artifact_prefix)
    _, _, special_member_pdf_lines = _case_onepage_special_member_lines(summary, bundle_artifact_prefix)
    irregular_canonical_promotion_queue_rows = _external_surface_irregular_canonical_promotion_queue_rows(summary)
    fig = plt.figure(figsize=(8.5, 11))
    ax = fig.add_subplot(111)
    ax.axis("off")
    ax.text(0.03, 0.97, f"Authority-Facing Case Onepage: {row.get('case_label', row.get('case_id', 'Case'))}", fontsize=16, weight="bold", va="top")
    cover_box = FancyBboxPatch(
        (0.035, 0.52),
        0.93,
        0.39,
        boxstyle="round,pad=0.012,rounding_size=0.02",
        linewidth=1.0,
        edgecolor="#d8c9b6",
        facecolor="#fffaf2",
    )
    ax.add_patch(cover_box)
    ax.text(0.05, 0.90, EXTERNAL_CASE_COVER_TITLE, fontsize=11.0, weight="bold", va="top")
    ax.text(0.05, 0.865, EXTERNAL_CASE_COVER_NOTE, fontsize=9.2, color="#5f5147", va="top", wrap=True)
    y = 0.83
    for label, value in cover_fields:
        ax.text(0.05, y, f"{label}: {value}", fontsize=8.25, va="top", wrap=True)
        y -= 0.028
        if y < 0.545:
            break
    y = 0.49
    ax.text(0.04, y, "KPI Receipt", fontsize=11.2, weight="bold", va="top")
    y -= 0.03
    for item in kpi_rows[:8]:
        ax.text(
            0.05,
            y,
            f"{item.get('label', '')} | {item.get('source', '')} | {item.get('value', '')}",
            fontsize=8.7,
            va="top",
            wrap=True,
        )
        y -= 0.035
        if y < 0.15:
            break
    y -= 0.02
    ax.text(0.04, y, "Attestation Workflow", fontsize=11.2, weight="bold", va="top")
    y -= 0.03
    workflow_lines = [
        f"status: {row.get('case_attestation_status', '') or 'n/a'}",
        f"source_kind: {row.get('case_attestation_source_kind', '') or 'n/a'}",
        f"receipt: {row.get('case_attestation_receipt_bundle', '') or 'n/a'}",
    ]
    for line in workflow_lines:
        ax.text(0.05, y, line, fontsize=8.7, va="top", wrap=True)
        y -= 0.03
    y -= 0.01
    ax.text(0.04, y, "Shared Appendices", fontsize=11.2, weight="bold", va="top")
    y -= 0.03
    shared_lines = [
        f"main external validation onepage: {main_onepage_relpath}",
        f"native roundtrip appendix markdown: {_bundle_artifact_link(str(row.get('midas_native_roundtrip_appendix_markdown', '')), bundle_artifact_prefix)}",
        f"native roundtrip appendix json: {_bundle_artifact_link(str(row.get('midas_native_roundtrip_appendix_json', '')), bundle_artifact_prefix)}",
        f"row provenance report: {_bundle_artifact_link(str(row.get('midas_kds_row_provenance_export_report', '')), bundle_artifact_prefix)}",
        f"row provenance csv: {_bundle_artifact_link(str(row.get('midas_kds_row_provenance_export_csv', '')), bundle_artifact_prefix)}",
    ]
    for line in shared_lines:
        ax.text(0.05, y, line, fontsize=8.7, va="top", wrap=True)
        y -= 0.04
    if y > 0.22:
        ax.text(0.04, y, "Native Authoring Coverage", fontsize=11.2, weight="bold", va="top")
        y -= 0.03
        for line in special_member_pdf_lines:
            if y < 0.10:
                break
            ax.text(0.05, y, line, fontsize=8.2, va="top", wrap=True)
            y -= 0.034
    if irregular_canonical_promotion_queue_rows and y > 0.18:
        ax.text(0.04, y, "Canonical Readiness Note", fontsize=11.2, weight="bold", va="top")
        y -= 0.03
        ax.text(
            0.05,
            y,
            EXTERNAL_CANONICAL_READINESS_NOTE_SHORT,
            fontsize=8.4,
            va="top",
            wrap=True,
        )
        y -= 0.04
        for item in irregular_canonical_promotion_queue_rows[:2]:
            if y < 0.10:
                break
            line = (
                f"{item.get('family_id', '')} | status={item.get('status', '') or 'n/a'} | "
                f"path={item.get('promotion_path', '') or 'n/a'} | "
                f"support={item.get('native_support', '') or 'n/a'}"
            )
            ax.text(0.05, y, line, fontsize=8.1, va="top", wrap=True)
            y -= 0.035
            blocker = f"blocker: {item.get('blocker', '') or 'n/a'}"
            ax.text(0.06, y, blocker, fontsize=7.9, va="top", wrap=True)
            y -= 0.04
    if y > 0.08:
        ax.text(0.04, y, "Irregular Benchmark Receipts", fontsize=11.2, weight="bold", va="top")
        y -= 0.03
    for line in irregular_receipt_lines:
        if y < 0.05:
            break
        ax.text(0.05, y, line, fontsize=8.2, va="top", wrap=True)
        y -= 0.032
    finalize_pdf_figure(fig, text_page=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    with PdfPages(path) as pdf:
        pdf.savefig(fig)
    plt.close(fig)


def _write_external_benchmark_case_onepages(bundle_dir: Path, summary: dict, artifacts: dict) -> None:
    rows = [row for row in (summary.get("external_benchmark_case_onepage_rows") or []) if isinstance(row, dict)]
    if not rows:
        return
    case_dir = bundle_dir / "external_benchmark_case_onepages"
    case_dir.mkdir(parents=True, exist_ok=True)
    case_dir_rel = Path("external_benchmark_case_onepages")
    main_onepage_relpath = "../external_validation_onepage.md"
    bundle_artifact_prefix = "../artifacts"
    irregular_receipt_rows = _irregular_benchmark_case_receipt_rows(summary)
    irregular_receipt_index_json = str(artifacts.get("irregular_benchmark_receipt_index_json", "") or "").strip()
    irregular_benchmark_execution_manifest_json = str(
        artifacts.get("irregular_benchmark_execution_manifest_json", "") or ""
    ).strip()
    kickoff_manifest = str(artifacts.get("external_benchmark_execution_manifest_json", "") or "").strip()
    kickoff_dir = Path(kickoff_manifest).parent if kickoff_manifest else Path(
        "implementation/phase1/release/external_benchmark_kickoff"
    )
    status_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    kickoff_index_rows: list[dict] = []
    for row in rows:
        row["midas_native_roundtrip_appendix_markdown"] = str(
            artifacts.get("midas_native_roundtrip_appendix_markdown", "") or ""
        )
        row["midas_native_roundtrip_appendix_json"] = str(artifacts.get("midas_native_roundtrip_appendix_json", "") or "")
        row["midas_kds_row_provenance_export_report"] = str(
            artifacts.get("midas_kds_row_provenance_export_report", "") or ""
        )
        row["midas_kds_row_provenance_export_csv"] = str(artifacts.get("midas_kds_row_provenance_export_csv", "") or "")
        row["irregular_benchmark_execution_manifest_json"] = irregular_benchmark_execution_manifest_json
        row["irregular_benchmark_receipt_index_json"] = irregular_receipt_index_json
        row["irregular_benchmark_receipt_rows"] = [dict(item) for item in irregular_receipt_rows]
        row["irregular_benchmark_receipt_count"] = int(len(irregular_receipt_rows))
        metrics = summary.get("metrics") if isinstance(summary.get("metrics"), dict) else {}
        base = case_dir / str(
            row.get("case_onepage_base", "")
            or f"{_slugify_external_case_id(row.get('case_id', 'case'), int(row.get('task_index', 0) or 0))}.authority_onepage"
        )
        json_path = base.with_suffix(".json")
        md_path = base.with_suffix(".md")
        html_path = base.with_suffix(".html")
        pdf_path = base.with_suffix(".pdf")
        row.update(
            _write_external_benchmark_case_attestation_workflow(
                summary,
                row,
                artifacts,
                kickoff_dir=kickoff_dir,
                case_dir=case_dir,
                case_dir_rel=case_dir_rel,
                base=base,
            )
        )
        row["case_onepage_json"] = str((case_dir_rel / json_path.name).as_posix())
        row["case_onepage_md"] = str((case_dir_rel / md_path.name).as_posix())
        row["case_onepage_html"] = str((case_dir_rel / html_path.name).as_posix())
        row["case_onepage_pdf"] = str((case_dir_rel / pdf_path.name).as_posix())
        attestation_slots = _external_benchmark_case_onepage_attestation_slots(summary, row)
        _write_json(
            json_path,
            {
                "case_id": str(row.get("case_id", "") or ""),
                "case_label": str(row.get("case_label", row.get("case_id", "case")) or "case"),
                "task_id": str(row.get("task_id", "") or ""),
                "benchmark_family": str(row.get("benchmark_family", "") or ""),
                "hazard_family": str(row.get("hazard_family", "") or ""),
                "topology_family": str(row.get("topology_family", "") or ""),
                "load_path_family": str(row.get("load_path_family", "") or ""),
                "source_origin_class": str(row.get("source_origin_class", "") or ""),
                "execution_status": str(row.get("execution_status", "") or ""),
                "lifecycle_status": str(row.get("lifecycle_status", "") or ""),
                "submission_scope": str(row.get("submission_scope", "") or ""),
                "kpi_rows": [entry for entry in (row.get("kpi_rows") or []) if isinstance(entry, dict)],
                "kpi_receipt_path": str(row.get("kpi_receipt_path", "") or ""),
                "irregular_benchmark_execution_manifest_json": str(
                    row.get("irregular_benchmark_execution_manifest_json", "") or ""
                ),
                "irregular_benchmark_receipt_index_json": str(
                    row.get("irregular_benchmark_receipt_index_json", "") or ""
                ),
                "irregular_benchmark_receipt_count": int(row.get("irregular_benchmark_receipt_count", 0) or 0),
                "irregular_benchmark_receipt_rows": [
                    dict(entry)
                    for entry in (row.get("irregular_benchmark_receipt_rows") or [])
                    if isinstance(entry, dict)
                ],
                "case_bundle_zip_path": str(row.get("case_bundle_zip_path", "") or ""),
                "case_bundle_dir": str(row.get("case_bundle_dir", "") or ""),
                "native_roundtrip_appendix_markdown": str(
                    artifacts.get("midas_native_roundtrip_appendix_markdown", "") or ""
                ),
                "native_roundtrip_appendix_json": str(
                    artifacts.get("midas_native_roundtrip_appendix_json", "") or ""
                ),
                "native_roundtrip_receipts_report_json": str(
                    artifacts.get("midas_native_roundtrip_receipts_report_json", "") or ""
                ),
                "special_member_direct_patch_action_family_label": str(
                    metrics.get("mgt_export_special_member_direct_patch_action_family_label", "") or ""
                ),
                "special_member_supported_action_family_label": str(
                    metrics.get("mgt_export_special_member_supported_action_family_label", "") or ""
                ),
                "special_member_zero_touch_verified_action_family_label": str(
                    metrics.get("mgt_export_special_member_zero_touch_verified_action_family_label", "") or ""
                ),
                "exact_topology_structural_preview_promotion_queue_json": str(
                    artifacts.get("exact_topology_structural_preview_promotion_queue_json", "") or ""
                ),
                "exact_topology_structural_preview_promotion_queue_md": str(
                    artifacts.get("exact_topology_structural_preview_promotion_queue_md", "") or ""
                ),
                "exact_topology_structural_preview_pending_candidate_rows": [
                    dict(entry)
                    for entry in (summary.get("exact_topology_structural_preview_promotion_queue_rows") or [])
                    if isinstance(entry, dict)
                ],
                "row_provenance_report": str(artifacts.get("midas_kds_row_provenance_export_report", "") or ""),
                "row_provenance_csv": str(artifacts.get("midas_kds_row_provenance_export_csv", "") or ""),
                "case_attestation_status": str(row.get("case_attestation_status", "") or ""),
                "case_attestation_source_kind": str(row.get("case_attestation_source_kind", "") or ""),
                "case_attestation_missing_fields": list(row.get("case_attestation_missing_fields") or []),
                "case_attestation_manifest_bundle": str(row.get("case_attestation_manifest_bundle", "") or ""),
                "case_attestation_template_bundle": str(row.get("case_attestation_template_bundle", "") or ""),
                "case_attestation_receipt_bundle": str(row.get("case_attestation_receipt_bundle", "") or ""),
                "case_attestation_manifest_source": str(row.get("case_attestation_manifest_source", "") or ""),
                "case_attestation_template_source": str(row.get("case_attestation_template_source", "") or ""),
                "case_attestation_receipt_source": str(row.get("case_attestation_receipt_source", "") or ""),
                "case_attestation_workflow_connection": dict(
                    row.get("case_attestation_workflow_connection", {}) or {}
                ),
                "cover_sheet_title": EXTERNAL_CASE_COVER_TITLE,
                "cover_sheet_note": EXTERNAL_CASE_COVER_NOTE,
                "cover_sheet_instruction": EXTERNAL_CASE_COVER_INSTRUCTION,
                "cover_sheet_disclaimer": attestation_slots["attestation_disclaimer"],
                "cover_sheet_slots": attestation_slots,
                "cover_sheet_fields": [
                    {"label": label, "value": value}
                    for label, value in _external_benchmark_case_onepage_cover_fields(summary, row)
                ],
            },
        )
        md_path.write_text(
            "\n".join(
                _render_external_benchmark_case_onepage_markdown(
                    summary,
                    row,
                    bundle_artifact_prefix,
                    main_onepage_relpath,
                )
            ),
            encoding="utf-8",
        )
        html_path.write_text(
            _render_external_benchmark_case_onepage_html(
                summary,
                row,
                bundle_artifact_prefix,
                main_onepage_relpath,
            ),
            encoding="utf-8",
        )
        _write_external_benchmark_case_onepage_pdf(
            pdf_path,
            summary,
            row,
            main_onepage_relpath,
            bundle_artifact_prefix,
        )
        status_counts[str(row.get("case_attestation_status", "") or "unknown")] += 1
        source_counts[str(row.get("case_attestation_source_kind", "") or "unknown")] += 1
        kickoff_index_rows.append(
            {
                "case_id": str(row.get("case_id", "") or ""),
                "case_label": str(row.get("case_label", row.get("case_id", "case")) or "case"),
                "task_id": str(row.get("task_id", "") or ""),
                "status": str(row.get("case_attestation_status", "") or ""),
                "source_kind": str(row.get("case_attestation_source_kind", "") or ""),
                "missing_fields": list(row.get("case_attestation_missing_fields") or []),
                "manifest_json": str(row.get("case_attestation_manifest_source", "") or ""),
                "template_json": str(row.get("case_attestation_template_source", "") or ""),
                "receipt_json": str(row.get("case_attestation_receipt_source", "") or ""),
                "bundle_manifest_json": str(row.get("case_attestation_manifest_bundle", "") or ""),
                "bundle_template_json": str(row.get("case_attestation_template_bundle", "") or ""),
                "bundle_receipt_json": str(row.get("case_attestation_receipt_bundle", "") or ""),
            }
        )

    index_md = case_dir / "index.md"
    index_html = case_dir / "index.html"
    index_pdf = case_dir / "index.pdf"
    attestation_status_label = ", ".join(
        f"{key}={int(value)}" for key, value in sorted(status_counts.items()) if key
    )
    attestation_source_label = ", ".join(
        f"{key}={int(value)}" for key, value in sorted(source_counts.items()) if key
    )
    attestation_manifest_count = int(source_counts.get("manifest", 0))
    attestation_template_count = int(source_counts.get("template", 0))
    attestation_receipt_count = int(len(kickoff_index_rows))
    attestation_attested_count = int(status_counts.get(EXTERNAL_CASE_ATTESTATION_STATUS_COMPLETE, 0))
    kickoff_index_json = kickoff_dir / EXTERNAL_CASE_ATTESTATION_INDEX_JSON
    kickoff_index_md = kickoff_dir / EXTERNAL_CASE_ATTESTATION_INDEX_MD
    kickoff_index_payload = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contract_pass": bool(
            len(kickoff_index_rows) == len(rows)
            and attestation_receipt_count == len(rows)
            and (attestation_manifest_count + attestation_template_count) == len(rows)
        ),
        "reason_code": "PASS_CASE_ATTESTATION_WORKFLOW_READY"
        if (
            len(kickoff_index_rows) == len(rows)
            and attestation_receipt_count == len(rows)
            and (attestation_manifest_count + attestation_template_count) == len(rows)
        )
        else "ERR_CASE_ATTESTATION_WORKFLOW_INCOMPLETE",
        "summary": {
            "case_count": int(len(rows)),
            "manifest_count": attestation_manifest_count,
            "template_count": attestation_template_count,
            "receipt_count": attestation_receipt_count,
            "attested_count": attestation_attested_count,
            "source_label": attestation_source_label,
            "status_counts": {key: int(value) for key, value in sorted(status_counts.items()) if key},
            "status_label": attestation_status_label,
        },
        "cases": kickoff_index_rows,
    }
    _write_json(kickoff_index_json, kickoff_index_payload)
    kickoff_index_md.write_text(
        "\n".join(
            [
                "# Case Onepage Attestation Workflow Index",
                "",
                f"- `generated_at`: `{kickoff_index_payload.get('generated_at', '')}`",
                f"- `case_count`: `{len(rows)}`",
                f"- `manifest_count`: `{attestation_manifest_count}`",
                f"- `template_count`: `{attestation_template_count}`",
                f"- `receipt_count`: `{attestation_receipt_count}`",
                f"- `attested_count`: `{attestation_attested_count}`",
                f"- `source_label`: `{attestation_source_label or 'none'}`",
                f"- `status_label`: `{attestation_status_label or 'none'}`",
                "",
                "| Case | Status | Source | Receipt |",
                "|---|---|---|---|",
            ]
            + [
                f"| {row.get('case_label', row.get('case_id', ''))} | {row.get('status', '') or 'n/a'} | "
                f"{row.get('source_kind', '') or 'n/a'} | `{row.get('receipt_json', '') or 'n/a'}` |"
                for row in kickoff_index_rows
            ]
            + [""]
        ),
        encoding="utf-8",
    )
    summary["external_benchmark_case_onepage_dir"] = str(case_dir_rel.as_posix())
    summary["external_benchmark_case_onepage_count"] = len(rows)
    if isinstance(summary.get("metrics"), dict):
        summary["metrics"]["external_benchmark_case_onepage_count"] = len(rows)
        summary["metrics"]["external_benchmark_case_attestation_case_count"] = len(rows)
        summary["metrics"]["external_benchmark_case_attestation_manifest_count"] = attestation_manifest_count
        summary["metrics"]["external_benchmark_case_attestation_template_count"] = attestation_template_count
        summary["metrics"]["external_benchmark_case_attestation_receipt_count"] = attestation_receipt_count
        summary["metrics"]["external_benchmark_case_attestation_attested_count"] = attestation_attested_count
        summary["metrics"]["external_benchmark_case_attestation_status_label"] = attestation_status_label
        summary["metrics"]["external_benchmark_case_attestation_source_label"] = attestation_source_label
    artifacts["external_benchmark_case_onepage_dir"] = str(case_dir_rel.as_posix())
    artifacts["external_benchmark_case_onepage_index_md"] = str((case_dir_rel / "index.md").as_posix())
    artifacts["external_benchmark_case_onepage_index_html"] = str((case_dir_rel / "index.html").as_posix())
    artifacts["external_benchmark_case_onepage_index_pdf"] = str((case_dir_rel / "index.pdf").as_posix())
    artifacts["external_benchmark_case_onepage_format_label"] = "json+md+html+pdf"
    artifacts["external_benchmark_case_attestation_manifest_dir"] = str(
        (kickoff_dir / EXTERNAL_CASE_ATTESTATION_MANIFEST_DIRNAME).as_posix()
    )
    artifacts["external_benchmark_case_attestation_template_dir"] = str(
        (kickoff_dir / EXTERNAL_CASE_ATTESTATION_TEMPLATE_DIRNAME).as_posix()
    )
    artifacts["external_benchmark_case_attestation_receipt_dir"] = str(
        (kickoff_dir / EXTERNAL_CASE_ATTESTATION_RECEIPT_DIRNAME).as_posix()
    )
    artifacts["external_benchmark_case_attestation_index_json"] = str(kickoff_index_json.as_posix())
    artifacts["external_benchmark_case_attestation_index_md"] = str(kickoff_index_md.as_posix())
    index_md.write_text(
        "\n".join(_external_benchmark_case_onepage_index_markdown(summary, artifacts)),
        encoding="utf-8",
    )
    index_html.write_text(
        _external_benchmark_case_onepage_index_html(summary, artifacts),
        encoding="utf-8",
    )
    fig = plt.figure(figsize=(8.5, 11))
    ax = fig.add_subplot(111)
    ax.axis("off")
    ax.text(0.03, 0.97, "External Benchmark Case Onepages", fontsize=16, weight="bold", va="top")
    y = 0.92
    ax.text(0.04, y, f"case_onepage_count={len(rows)}", fontsize=10.0, va="top")
    y -= 0.04
    ax.text(0.04, y, f"index_md={artifacts['external_benchmark_case_onepage_index_md']}", fontsize=9.0, va="top", wrap=True)
    y -= 0.04
    ax.text(0.04, y, f"index_html={artifacts['external_benchmark_case_onepage_index_html']}", fontsize=9.0, va="top", wrap=True)
    y -= 0.04
    ax.text(0.04, y, f"index_pdf={artifacts['external_benchmark_case_onepage_index_pdf']}", fontsize=9.0, va="top", wrap=True)
    y -= 0.05
    ax.text(
        0.04,
        y,
        f"attestation_workflow=manifests:{attestation_manifest_count} | templates:{attestation_template_count} | receipts:{attestation_receipt_count} | attested:{attestation_attested_count}",
        fontsize=9.0,
        va="top",
        wrap=True,
    )
    y -= 0.05
    kr_preview_reps = _public_structural_preview_representative_rows(summary)
    ax.text(
        0.04,
        y,
        f"kr_public_structural_preview_representatives={len(kr_preview_reps)}",
        fontsize=9.0,
        va="top",
        wrap=True,
    )
    y -= 0.05
    ax.text(0.04, y, "Shared native roundtrip appendix is linked from every case page.", fontsize=9.2, va="top", wrap=True)
    y -= 0.05
    ax.text(
        0.04,
        y,
        "Reviewer / authority cover sheet is embedded at the top of every case page.",
        fontsize=9.2,
        va="top",
        wrap=True,
    )
    y -= 0.05
    for row in rows[:10]:
        ax.text(
            0.04,
            y,
            f"{row.get('case_label', row.get('case_id', ''))} | {row.get('benchmark_family', '')} | {row.get('case_onepage_md', '')}",
            fontsize=8.2,
            va="top",
            wrap=True,
        )
        y -= 0.03
        if y < 0.10:
            break
    finalize_pdf_figure(fig, text_page=True)
    with PdfPages(index_pdf) as pdf:
        pdf.savefig(fig)
    plt.close(fig)


def _write_summary_html(path: Path, summary: dict) -> None:
    metrics = summary["metrics"]
    checks = summary["checks"]
    derived = summary["derived"]
    entrypoints = list(summary.get("design_optimization_entrypoints", []))
    entrypoint_groups = list(summary.get("design_optimization_entrypoint_groups", []))
    annotated_groups = annotate_entrypoint_groups(entrypoint_groups)
    artifacts = summary.get("artifacts") if isinstance(summary.get("artifacts"), dict) else {}
    smoke_history_png = str(artifacts.get("nightly_smoke_history_png", "") or "")
    measured_chain_category_png = str(artifacts.get("measured_chain_category_png", "") or "")
    smoke_recent_samples = list(summary.get("nightly_smoke_recent_samples", []))
    holdout_buckets = list(summary.get("residual_holdout_buckets", []))
    holdout_detail_rows = list(summary.get("residual_holdout_detail_rows", []))
    holdout_matrix_rows = list(summary.get("residual_holdout_matrix_rows", []))
    authority_catalog_diff = summary.get("authority_catalog_routing_diff") if isinstance(summary.get("authority_catalog_routing_diff"), dict) else {}
    authority_catalog_warning_active = bool(int(summary.get("authority_catalog_diff_change_count", 0) or 0) > 0)
    promotion_reason_code = str(summary.get("promotion_reason_code", ""))
    promotion_hold_for_review = bool(summary.get("promotion_hold_for_review", False))
    hold_review_manifest = str(summary.get("hold_review_manifest", "") or "")
    hold_review_packet_md = str(summary.get("hold_review_packet_md", "") or "")
    hold_review_packet_pdf = str(summary.get("hold_review_packet_pdf", "") or "")
    hold_review_ack_json = str(summary.get("hold_review_ack_json", "") or "")
    smoke_recent_sample_rows_html = []
    for row in smoke_recent_samples:
        smoke_recent_sample_rows_html.append(
            f"""
            <tr>
              <td>{int(row.get('sample_index', 0))}</td>
              <td>{row.get('generated_at', '')}</td>
              <td>{bool(row.get('contract_pass', False))}</td>
              <td>{bool(row.get('trial_feasible', False))}</td>
              <td>{float(row.get('baseline_runtime_s', 0.0)):.4f}</td>
              <td>{float(row.get('trial_runtime_s', 0.0)):.4f}</td>
              <td>{float(row.get('trial_max_dcr', 0.0)):.4f}</td>
              <td>{row.get('trial_action_name', '')}</td>
            </tr>
            """
        )
    smoke_history_panel_html = (
        '<div class="panel panel-wide panel-figure"><div class="panel-kicker">Trend figure</div><h2>Nightly Smoke Trend</h2>'
        f'<div class="media-shell"><img src="artifacts/{smoke_history_png}" alt="Nightly Smoke Trend"/></div></div>'
        if smoke_history_png
        else ""
    )
    measured_chain_panel_html = (
        '<div class="panel panel-wide panel-figure"><div class="panel-kicker">Trend figure</div><h2>Measured Chain Category Trend</h2>'
        f'<div class="media-shell"><img src="artifacts/{measured_chain_category_png}" alt="Measured Chain Category Trend"/></div></div>'
        if measured_chain_category_png
        else ""
    )
    authority_catalog_warning_panel_html = (
        f"""
        <div class="panel panel-emphasis">
          <div class="panel-kicker">Review warning</div>
          <h2>Active Warnings</h2>
          <table>
            <tr><td>Authority routing change</td><td>changes={int(summary.get('authority_catalog_diff_change_count', 0))}, added={int(summary.get('authority_catalog_diff_added_count', 0))}, removed={int(summary.get('authority_catalog_diff_removed_count', 0))}</td></tr>
            <tr><td>Why</td><td>Authority/submodel routing changed since the previous committee snapshot and should be explicitly reviewed before release promotion or authority-facing reuse.</td></tr>
          </table>
        </div>
        """
        if authority_catalog_warning_active
        else ""
    )

    promotion_hold_panel_html = (
        f"""
        <div class="panel panel-emphasis">
          <div class="panel-kicker">Promotion control</div>
          <h2>Promotion Hold</h2>
          <table>
            <tr><td>Promotion reason</td><td>{promotion_reason_code}</td></tr>
            <tr><td>Hold review manifest</td><td>{hold_review_manifest or 'n/a'}</td></tr>
            <tr><td>Hold review packet</td><td>{hold_review_packet_md or 'n/a'}</td></tr>
            <tr><td>Hold review packet pdf</td><td>{hold_review_packet_pdf or 'n/a'}</td></tr>
            <tr><td>Hold review ack</td><td>{hold_review_ack_json or 'n/a'}</td></tr>
            <tr><td>Why</td><td>Release candidate remains on hold until the authority-routing hold review manifest is cleared by engineer review.</td></tr>
          </table>
        </div>
        """
        if promotion_hold_for_review
        else ""
    )
    entrypoint_group_html = "".join(
        f"<tr><td>{row['group_label']}</td><td>{row['report_count']}/{row['entrypoint_count']}</td><td>{row['pass_count']}</td><td>{row['fail_count']}</td><td>{row['all_pass']}</td><td>{', '.join(row.get('entrypoint_names', []))}</td></tr>"
        for row in annotated_groups
    )
    entrypoint_detail_html = render_entrypoint_html_detail_sections(
        entrypoints,
        annotated_groups,
        table_style="margin-top:12px;",
        header_html="<tr><td>Name</td><td>Group</td><td>Primary report</td><td>Pass</td><td>Reason</td></tr>",
    )
    native_roundtrip_appendix_html = _midas_native_roundtrip_appendix_html(summary, artifacts)
    irregular_structure_appendix_html = _irregular_structure_appendix_html(summary, artifacts)
    row_provenance_appendix_html = _midas_row_provenance_appendix_html(summary, artifacts)
    case_onepage_appendix_html = _external_benchmark_case_onepage_index_html(summary, artifacts)
    irregular_structure_summary_line = str(
        metrics.get("irregular_structure_summary_line", "") or metrics.get("irregular_structure_track_summary_line", "") or "n/a"
    )
    irregular_structure_source_catalog_summary_line = (
        f"Irregular source catalog: PASS | families={int(metrics.get('irregular_structure_family_count', 0))} | "
        f"sources={int(metrics.get('irregular_structure_source_record_count', 0))} | "
        f"local_ready={int(metrics.get('irregular_structure_local_ready_count', 0))} | "
        f"remote_candidates={int(metrics.get('irregular_structure_remote_candidate_count', 0))}"
    )
    irregular_structure_triage_summary_line = (
        f"Irregular triage: PASS | native_candidates={int(metrics.get('irregular_structure_native_roundtrip_candidate_count', 0))} | "
        f"solver_candidates={int(metrics.get('irregular_structure_solver_benchmark_candidate_count', 0))} | "
        f"ai_candidates={int(metrics.get('irregular_structure_ai_learning_candidate_count', 0))}"
    )
    irregular_structure_collection_summary_line = (
        f"Irregular collection: PASS | collected={int(metrics.get('irregular_structure_collected_count', 0))} | "
        f"metadata_only_remote_candidate={int(metrics.get('irregular_structure_remote_candidate_count', 0)) - int(metrics.get('irregular_structure_collected_count', 0))} | "
        f"rejected=0"
    )
    irregular_top5_summary_line = (
        f"Irregular top5 manifest: PASS | top5={int(metrics.get('irregular_structure_top5_count', 0))} | "
        f"local_ready={int(metrics.get('irregular_structure_top5_local_ready_count', 0))} | "
        f"remote_needed={int(metrics.get('irregular_structure_top5_remote_needed_count', 0))}"
    )
    irregular_benchmark_execution_summary_line = str(metrics.get("irregular_benchmark_execution_summary_line", "") or "n/a")
    irregular_top5_family_ids = _external_surface_irregular_family_id_list(
        metrics.get("irregular_structure_top5_family_ids", []) or []
    )
    import html as html_module
    irregular_canonical_promotion_queue_rows = _external_surface_irregular_canonical_promotion_queue_rows(summary)
    irregular_receipt_summary_html = _render_irregular_benchmark_summary_receipt_html(
        summary, artifacts, "artifacts"
    )
    irregular_promotion_queue_rows_html = "".join(
        f"<tr><td>{html_module.escape(str(row.get('family_id', '') or ''))}</td>"
        f"<td>{html_module.escape(str(row.get('source_id', '') or ''))}</td>"
        f"<td>{html_module.escape(str(row.get('status', '') or ''))}</td>"
        f"<td>{html_module.escape(str(row.get('promotion_path', '') or 'n/a'))}</td>"
        f"<td>{html_module.escape(str(row.get('native_support', '') or 'n/a'))}</td>"
        f"<td>{html_module.escape(str(row.get('blocker', '') or 'n/a'))}</td></tr>"
        for row in irregular_canonical_promotion_queue_rows
    )
    irregular_promotion_queue_table_html = (
        """
        <table style="margin-top:12px;">
          <thead><tr><td>Family</td><td>Current Source</td><td>Status</td><td>Canonical Path</td><td>Native Support</td><td>Blocker</td></tr></thead>
          <tbody>
        """
        + irregular_promotion_queue_rows_html
        + """
          </tbody>
        </table>
        """
    ) if irregular_canonical_promotion_queue_rows else ""
    authority_catalog_diff_rows_html = "".join(
        f"<tr><td>{row.get('change_type', '')}</td><td>{row.get('authority_track', '')}</td><td>{row.get('submodel_family', '')}</td><td>{row.get('review_story_zone', '')}</td><td>{row.get('member_family', '')}</td><td>{row.get('owner', '')}</td><td>{row.get('why', '')}</td></tr>"
        for row in (authority_catalog_diff.get("diff_rows") or [])
        if isinstance(row, dict)
    ) or '<tr><td colspan="7">No authority-catalog routing changes detected for this external submission refresh.</td></tr>'
    midas_section_library_summary_line = str(metrics.get("midas_section_library_summary_line", "") or "n/a")
    material_constitutive_summary_line = str(metrics.get("material_constitutive_summary_line", "") or "n/a")
    surface_interaction_benchmark_summary_line = str(
        metrics.get("surface_interaction_benchmark_summary_line", "") or "n/a"
    )
    midas_native_roundtrip_summary_line = str(metrics.get("midas_native_roundtrip_summary_line", "") or "n/a")
    midas_native_roundtrip_writeback_diff_summary_line = str(
        metrics.get("midas_native_roundtrip_writeback_diff_summary_line", "") or "n/a"
    )
    korean_source_ingest_summary_line = _compact_korean_source_ingest_summary_line(
        str(metrics.get("korean_source_ingest_summary_line", "") or "n/a")
    )
    measured_benchmark_breadth_summary_line = str(
        metrics.get("measured_benchmark_breadth_summary_line", "") or "n/a"
    )
    opensees_canonical_breadth_summary_line = str(
        metrics.get("opensees_canonical_breadth_summary_line", "") or "n/a"
    )
    korean_native_roundtrip_representative_rows = _korean_native_roundtrip_representative_rows(summary)
    korean_structural_preview_queue_summary_line = str(
        metrics.get("korean_structural_preview_queue_summary_line", "") or "n/a"
    )
    korean_structural_preview_queue_summary_line = _compact_korean_structural_preview_queue_summary_line(
        korean_structural_preview_queue_summary_line
    )
    korean_native_roundtrip_representatives_html = _render_korean_native_roundtrip_representatives_html(summary)
    row_provenance_summary_line = str(metrics.get("midas_kds_row_provenance_export_summary_line", "") or "n/a")
    row_provenance_preview_rows = _midas_row_provenance_preview_rows(metrics)
    row_provenance_json = str(artifacts.get("midas_kds_row_provenance_export_json", "") or "n/a")
    row_provenance_csv = str(artifacts.get("midas_kds_row_provenance_export_csv", "") or "n/a")
    row_provenance_report = str(artifacts.get("midas_kds_row_provenance_export_report", "") or "n/a")
    public_raw_ready = metrics.get(
        "midas_native_roundtrip_public_raw_native_writeback_ready_count",
        metrics.get("midas_native_roundtrip_public_raw_native_ready_case_count", 0),
    )
    public_bridge_ready = metrics.get(
        "midas_native_roundtrip_public_bridge_writeback_ready_count",
        metrics.get("midas_native_roundtrip_public_bridge_ready_case_count", 0),
    )
    midas_section_library_status_label = (
        "embedded metadata validated" if midas_section_library_summary_line != "n/a" else "validator unavailable"
    )
    midas_section_library_surface_note = (
        "nightly, release gap, committee dashboard, and this external-validation onepage all consume the same validator line"
    )
    gate_status_rows = [
        ("Nightly release", checks["nightly_release"]),
        ("CI gate", checks["ci_gate"]),
        ("Static validation", checks["static_validation"]),
        ("Freeze release", checks["freeze_release"]),
        ("Promotion", checks["promotion"]),
    ]
    integrity_status_rows = [
        ("Signed registry", checks["signed_release_registry"]),
        ("Registry signature verified", checks["registry_signature_verified"]),
        ("Solver HIP e2e", checks["solver_hip_e2e"]),
        ("RC benchmark lock", checks["rc_benchmark_lock"]),
        ("NDTHA residual gate", checks["ndtha_residual_gate"]),
        ("Committee package", checks["committee_review_package"]),
    ]
    gate_pass_count = sum(1 for _, status in gate_status_rows if str(status).strip().upper() == "PASS")
    integrity_pass_count = sum(1 for _, status in integrity_status_rows if str(status).strip().upper() == "PASS")
    gate_status_rows_html = "".join(
        f"<tr><td>{html.escape(label)}</td><td>{_external_surface_check_chip_html(status)}</td></tr>"
        for label, status in gate_status_rows
    )
    integrity_status_rows_html = (
        "".join(
            f"<tr><td>{html.escape(label)}</td><td>{_external_surface_check_chip_html(status)}</td></tr>"
            for label, status in integrity_status_rows
        )
        + f"<tr><td>MIDAS section-library validator</td><td>{html.escape(midas_section_library_summary_line)}</td></tr>"
        + "<tr><td>MIDAS section-library status</td><td>"
        + _external_surface_status_chip_html(
            midas_section_library_status_label,
            "ok" if midas_section_library_summary_line != "n/a" else "warn",
        )
        + "</td></tr>"
    )
    external_benchmark_start_ready = bool(metrics.get("external_benchmark_submission_ready_to_start_now", False))
    external_benchmark_full_ready = bool(
        metrics.get("external_benchmark_submission_ready_to_start_full_submission_now", False)
    )
    external_benchmark_start_chip = _external_surface_bool_chip_html(
        external_benchmark_start_ready,
        true_label="START NOW",
        false_label="REVIEW BOUNDARY",
    )
    external_benchmark_full_chip = _external_surface_bool_chip_html(
        external_benchmark_full_ready,
        true_label="FULL SUBMISSION READY",
        false_label="FULL SUBMISSION HELD",
    )
    html_output = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>External Validation One-Page</title>
  <style>
    {build_signal_desk_light_css()}
    * {{ box-sizing:border-box; }}
    body.signal-desk-light {{
      color:var(--ink);
      font-family:var(--font-ui);
    }}
    .wrap {{
      max-width:1320px;
      margin:0 auto;
      padding:32px 24px 72px;
    }}
    .hero {{
      display:grid;
      grid-template-columns:minmax(0, 1.08fr) minmax(320px, .92fr);
      gap:20px;
      align-items:stretch;
    }}
    .hero-main {{
      padding:30px;
      border-radius:var(--radius-xl);
      background:
        radial-gradient(circle at 18% 10%, rgba(255,255,255,.14), rgba(255,255,255,0) 34%),
        var(--review-hero-bg);
      color:#f4fbfc;
      box-shadow:var(--shadow-hero);
    }}
    .hero-kicker,
    .panel-kicker,
    .signal-label,
    .detail-row > span:first-child {{
      font-size:var(--type-label-size);
      font-weight:700;
      line-height:var(--type-label-line-height);
      letter-spacing:var(--type-label-tracking);
      text-transform:uppercase;
    }}
    .hero-kicker {{
      color:#d5eff0;
      margin-bottom:12px;
    }}
    .hero-main h1,
    .hero-side h2,
    .panel h2 {{
      margin:0;
      font-family:var(--font-display);
      letter-spacing:var(--type-h2-tracking);
    }}
    .hero-main h1 {{
      font-size:var(--type-h1-size);
      line-height:var(--type-h1-line-height);
      letter-spacing:var(--type-h1-tracking);
    }}
    .hero-main p {{
      margin:12px 0 0;
      max-width:64ch;
      font-size:15px;
      line-height:1.72;
      color:#e1f1f2;
    }}
    .hero-pill-row,
    .status-row {{
      display:flex;
      flex-wrap:wrap;
      gap:10px;
    }}
    .hero-pill-row {{
      margin-top:18px;
    }}
    .hero-pill {{
      display:inline-flex;
      align-items:center;
      gap:8px;
      min-height:34px;
      padding:0 12px;
      border-radius:var(--radius-pill);
      background:rgba(255,255,255,.12);
      border:1px solid rgba(255,255,255,.18);
      color:#f4fbfc;
      font-size:12px;
      font-weight:700;
    }}
    .hero-pill code {{
      background:rgba(255,255,255,.14);
      color:#f4fbfc;
    }}
    .hero-side,
    .signal-card,
    .panel {{
      border-radius:var(--radius-lg);
      background:var(--review-panel-bg);
      border:1px solid var(--line);
      box-shadow:var(--shadow-panel);
    }}
    .hero-side {{
      padding:24px;
      display:grid;
      gap:16px;
      align-content:start;
    }}
    .panel-kicker {{
      color:var(--brand);
    }}
    .panel-lead,
    .note,
    .mini-note,
    .signal-note,
    .hero-side p {{
      margin:0;
      color:var(--muted);
      font-size:var(--type-body-size);
      line-height:var(--type-body-line-height);
      letter-spacing:var(--type-body-tracking);
    }}
    .detail-stack {{
      display:grid;
      gap:12px;
    }}
    .detail-row {{
      display:grid;
      grid-template-columns:minmax(120px, 168px) 1fr;
      gap:12px;
      padding:12px 14px;
      border:1px solid rgba(15,106,115,.10);
      border-radius:var(--radius-md);
      background:rgba(255,255,255,.58);
      align-items:start;
    }}
    .detail-row > span:first-child {{
      color:var(--muted);
    }}
    .detail-row strong {{
      color:var(--ink);
      font-weight:700;
    }}
    .signal-strip {{
      display:grid;
      grid-template-columns:repeat(4, minmax(0, 1fr));
      gap:16px;
      margin-top:20px;
    }}
    .signal-card {{
      position:relative;
      overflow:hidden;
      padding:18px;
    }}
    .signal-card::before,
    .panel::before {{
      content:'';
      position:absolute;
      inset:0;
      background:linear-gradient(180deg, rgba(255,255,255,.56) 0%, rgba(255,255,255,0) 44%);
      pointer-events:none;
    }}
    .signal-card > *,
    .panel > * {{
      position:relative;
      z-index:1;
    }}
    .signal-label {{
      color:var(--muted);
    }}
    .signal-value {{
      margin-top:8px;
      font-family:var(--font-display);
      font-size:var(--type-metric-size);
      line-height:var(--type-metric-line-height);
      letter-spacing:var(--type-metric-tracking);
      color:var(--ink);
    }}
    .grid {{
      display:grid;
      grid-template-columns:repeat(12, minmax(0, 1fr));
      gap:18px;
      margin-top:24px;
    }}
    .panel {{
      grid-column:span 6;
      position:relative;
      overflow:hidden;
      padding:22px;
      background:var(--review-panel-quiet-bg);
    }}
    .panel.panel-wide {{
      grid-column:1 / -1;
    }}
    .panel h2 {{
      margin-bottom:14px;
      font-size:var(--type-h2-size);
      line-height:var(--type-h2-line-height);
    }}
    table {{
      width:100%;
      border-collapse:collapse;
      font-size:var(--type-body-size);
      line-height:var(--type-body-line-height);
      letter-spacing:var(--type-body-tracking);
    }}
    th,
    td {{
      padding:12px 0;
      border-bottom:1px solid var(--review-divider);
      vertical-align:top;
      text-align:left;
    }}
    th {{
      color:var(--muted);
      font-size:var(--type-label-size);
      font-weight:700;
      line-height:var(--type-label-line-height);
      letter-spacing:var(--type-label-tracking);
      text-transform:uppercase;
    }}
    td:first-child,
    th:first-child {{
      width:40%;
      padding-right:16px;
      color:var(--muted);
    }}
    code {{
      display:inline-flex;
      align-items:center;
      padding:2px 8px;
      border-radius:var(--radius-pill);
      background:var(--review-meta-bg);
      color:var(--review-meta-ink);
      font-family:'IBM Plex Mono','SFMono-Regular',monospace;
      font-size:12px;
      word-break:break-all;
    }}
    @media (max-width:1080px) {{
      .hero {{
        grid-template-columns:1fr;
      }}
      .signal-strip {{
        grid-template-columns:repeat(2, minmax(0, 1fr));
      }}
      .panel {{
        grid-column:1 / -1;
      }}
    }}
    @media (max-width:720px) {{
      .wrap {{
        padding:24px 16px 56px;
      }}
      .signal-strip {{
        grid-template-columns:1fr;
      }}
      .detail-row {{
        grid-template-columns:1fr;
      }}
    }}
  </style>
</head>
<body class="signal-desk-light">
  <div class="wrap">
    <section class="hero">
      <div class="hero-main">
        <div class="hero-kicker">External Validation Surface</div>
        <h1>External Validation One-Page</h1>
        <p>Authority-facing validation summary that brings benchmark coverage, native roundtrip evidence, release gates, and delivery-boundary signals into one premium review export.</p>
        <div class="hero-pill-row">
          <span class="hero-pill">Bundle <code>{summary['bundle_id']}</code></span>
          <span class="hero-pill">Generated <code>{summary['generated_at']}</code></span>
        </div>
      </div>
      <aside class="hero-side">
        <div class="panel-kicker">MIDAS Section Library</div>
        <h2>embedded metadata validated</h2>
        <div class="status-row">
          {_external_surface_status_chip_html(midas_section_library_status_label, "ok" if midas_section_library_summary_line != "n/a" else "warn")}
          {external_benchmark_start_chip}
          {external_benchmark_full_chip}
        </div>
        <p class="panel-lead">{midas_section_library_surface_note}</p>
        <div class="detail-stack">
          <div class="detail-row"><span>Summary line</span><div>{midas_section_library_summary_line}</div></div>
          <div class="detail-row"><span>Gate mode</span><div>static + contract gate</div></div>
          <div class="detail-row"><span>Release gates</span><div>{gate_pass_count}/{len(gate_status_rows)} passed</div></div>
          <div class="detail-row"><span>Integrity</span><div>{integrity_pass_count}/{len(integrity_status_rows)} passed</div></div>
        </div>
      </aside>
    </section>
    <div class="signal-strip">
      <div class="signal-card">
        <div class="signal-label">Release Gates</div>
        <div class="signal-value">{gate_pass_count}/{len(gate_status_rows)}</div>
        <div class="signal-note">Nightly, CI, static validation, freeze, and promotion status aligned for authority packaging.</div>
      </div>
      <div class="signal-card">
        <div class="signal-label">Integrity Checks</div>
        <div class="signal-value">{integrity_pass_count}/{len(integrity_status_rows)}</div>
        <div class="signal-note">Registry, signature, solver, benchmark lock, residual gate, and committee package integrity.</div>
      </div>
      <div class="signal-card">
        <div class="signal-label">Native Write-Back Ready</div>
        <div class="signal-value">{int(metrics.get('midas_native_roundtrip_native_writeback_ready_count', 0))}/{int(metrics.get('midas_native_roundtrip_corpus_case_count', 0))}</div>
        <div class="signal-note">Native roundtrip readiness surfaced alongside public raw and bridge-ready evidence.</div>
      </div>
      <div class="signal-card">
        <div class="signal-label">Canonical Queue</div>
        <div class="signal-value">{len(irregular_canonical_promotion_queue_rows)}</div>
        <div class="signal-note">Unresolved bridged families still pending canonical promotion or release-boundary closure.</div>
      </div>
    </div>
    <div class="grid">
      <div class="panel">
        <h2>Constitutive / Interaction Coverage</h2>
        <div class="panel-lead">{CONSTITUTIVE_INTERACTION_NOTE}</div>
        <table>
          <tr><td>Material constitutive</td><td>{material_constitutive_summary_line}</td></tr>
          <tr><td>Surface interaction benchmark</td><td>{surface_interaction_benchmark_summary_line}</td></tr>
        </table>
      </div>
      <div class="panel">
        <h2>MIDAS Native Roundtrip / Write-Back</h2>
        <table>
          <tr><td>Roundtrip gate summary</td><td>{midas_native_roundtrip_summary_line}</td></tr>
          <tr><td>Write-back diff summary</td><td>{midas_native_roundtrip_writeback_diff_summary_line}</td></tr>
          <tr><td>Honest counts</td><td>corpus={metrics.get('midas_native_roundtrip_corpus_case_count', 0)} | native_text={metrics.get('midas_native_roundtrip_native_text_case_count', 0)} | ready={metrics.get('midas_native_roundtrip_native_writeback_ready_count', 0)} | public_native_ready={metrics.get('midas_native_roundtrip_public_native_writeback_ready_count', 0)} | public_raw_ready={int(public_raw_ready or 0)} | public_bridge_ready={int(public_bridge_ready or 0)} | public_preview_ready={metrics.get('midas_native_roundtrip_public_archive_preview_writeback_ready_count', 0)} | public_structural_preview_ready={metrics.get('midas_native_roundtrip_public_archive_structural_preview_writeback_ready_count', 0)} | public_source_ready={metrics.get('midas_native_roundtrip_public_source_writeback_ready_count', 0)} | structure_types={metrics.get('midas_native_roundtrip_structure_type_count', 0)} | batches={metrics.get('midas_native_roundtrip_structure_type_batch_count', 0)} | receipts={metrics.get('midas_native_roundtrip_receipt_count', 0)}/{metrics.get('midas_native_roundtrip_receipt_pass_count', 0)} | pending_review={metrics.get('midas_native_roundtrip_pending_review_total', 0)}</td></tr>
          <tr><td>Appendix Markdown</td><td>{artifacts.get('midas_native_roundtrip_appendix_markdown', '') or 'n/a'}</td></tr>
          <tr><td>Appendix JSON</td><td>{artifacts.get('midas_native_roundtrip_appendix_json', '') or 'n/a'}</td></tr>
          <tr><td>Receipts report</td><td>{artifacts.get('midas_native_roundtrip_receipts_report_json', '') or 'n/a'}</td></tr>
        </table>
      </div>
      <div class="panel">
        <h2>KR Source / Preview</h2>
        <table>
          <tr><td>KR ingest</td><td>{korean_source_ingest_summary_line}</td></tr>
          <tr><td>Measured benchmark breadth</td><td>{measured_benchmark_breadth_summary_line}</td></tr>
          <tr><td>OpenSees canonical breadth</td><td>{opensees_canonical_breadth_summary_line}</td></tr>
          <tr><td>KR preview queue</td><td>{korean_structural_preview_queue_summary_line}</td></tr>
        </table>
        {korean_native_roundtrip_representatives_html}
      </div>
      <div class="panel">
        <h2>Irregular Structure Track</h2>
        <table>
          <tr><td>Track summary</td><td>{irregular_structure_summary_line}</td></tr>
          <tr><td>Source catalog summary</td><td>{irregular_structure_source_catalog_summary_line}</td></tr>
          <tr><td>Triage summary</td><td>{irregular_structure_triage_summary_line}</td></tr>
          <tr><td>Collection summary</td><td>{irregular_structure_collection_summary_line}</td></tr>
          <tr><td>Top5 summary</td><td>{irregular_top5_summary_line}</td></tr>
          <tr><td>Benchmark execution summary</td><td>{irregular_benchmark_execution_summary_line}</td></tr>
          <tr><td>Top5 family ids</td><td>{', '.join(irregular_top5_family_ids) or 'n/a'}</td></tr>
          <tr><td>Benchmark manifest</td><td>{artifacts.get('irregular_benchmark_execution_manifest_json', '') or 'n/a'}</td></tr>
          {irregular_receipt_summary_html}
          <tr><td>Canonical promotion queue</td><td>{len(irregular_canonical_promotion_queue_rows)}</td></tr>
          <tr><td>Queue scope</td><td>Only unresolved bridged families are shown.</td></tr>
        </table>
        {irregular_promotion_queue_table_html}
      </div>
      <div class="panel">
        <h2>Gate Status</h2>
        <table>
          {gate_status_rows_html}
        </table>
      </div>
      <div class="panel">
        <h2>Integrity</h2>
        <table>
          {integrity_status_rows_html}
        </table>
      </div>
      <div class="panel">
        <h2>MGT Delivery Boundary</h2>
        <table>
          <tr><td>Evidence model</td><td>{metrics.get('mgt_export_evidence_model', '')}</td></tr>
          <tr><td>Rebar delivery mode</td><td>{metrics.get('mgt_export_rebar_delivery_mode', '')}</td></tr>
          <tr><td>Direct patch families</td><td>{metrics.get('mgt_export_direct_patch_action_family_label', '') or 'n/a'}</td></tr>
          <tr><td>Special-member direct patch</td><td>{metrics.get('mgt_export_special_member_direct_patch_action_family_label', '') or 'n/a'}</td></tr>
          <tr><td>Special-member supported</td><td>{metrics.get('mgt_export_special_member_supported_action_family_label', '') or 'n/a'}</td></tr>
          <tr><td>Special-member zero touch</td><td>{metrics.get('mgt_export_special_member_zero_touch_verified_action_family_label', '') or 'n/a'}</td></tr>
          <tr><td>Structured sidecar families</td><td>{metrics.get('mgt_export_instruction_sidecar_action_family_label', '') or 'n/a'}</td></tr>
        </table>
      </div>
      <div class="panel">
        <h2>Advanced Holdouts</h2>
        <table>
          <tr><td>PBD dynamic hinge refresh</td><td>{bool(metrics.get('pbd_dynamic_hinge_refresh_ready', False))} | {metrics.get('pbd_hinge_state_mode', '')}</td></tr>
          <tr><td>PBD reason</td><td>{metrics.get('pbd_hinge_refresh_reason', '')}</td></tr>
          <tr><td>PBD hinge evidence</td><td>artifact={bool(metrics.get('pbd_hinge_refresh_artifact_present', False))} | {metrics.get('pbd_hinge_refresh_source_mode', '')} | overlap={int(metrics.get('pbd_hinge_refresh_overlap_member_count', 0))} | rebar-sensitive={int(metrics.get('pbd_hinge_refresh_rebar_sensitive_member_count', 0))}</td></tr>
          <tr><td>PBD hinge benchmark</td><td>gate={bool(metrics.get('pbd_hinge_benchmark_gate_pass', False))} | assets={int(metrics.get('pbd_hinge_benchmark_asset_count', 0))} | train={int(metrics.get('pbd_hinge_benchmark_train_count', 0))} | val={int(metrics.get('pbd_hinge_benchmark_val_count', 0))} | holdout={int(metrics.get('pbd_hinge_benchmark_holdout_count', 0))} | rebar-sensitive={int(metrics.get('pbd_hinge_benchmark_rebar_sensitive_count', 0))} | confinement-sensitive={int(metrics.get('pbd_hinge_benchmark_confinement_sensitive_count', 0))} | fixture-regression={bool(metrics.get('pbd_hinge_benchmark_fixture_regression_pass', False))} | fixtures={int(metrics.get('pbd_hinge_benchmark_fixture_count', 0))} | min-point={int(metrics.get('pbd_hinge_benchmark_fixture_min_point_count', 0))} | min-peak-drift={float(metrics.get('pbd_hinge_benchmark_fixture_min_peak_drift_ratio', 0.0)):.6f} | alignment={bool(metrics.get('pbd_hinge_benchmark_alignment_pass', False))} | refresh-columns={int(metrics.get('pbd_hinge_benchmark_alignment_refresh_column_row_count', 0))} | rebar-columns={int(metrics.get('pbd_hinge_benchmark_alignment_rebar_sensitive_column_count', 0))} | benchmark-rebar={float(metrics.get('pbd_hinge_benchmark_alignment_benchmark_rebar_ratio_min', 0.0)):.4f}-{float(metrics.get('pbd_hinge_benchmark_alignment_benchmark_rebar_ratio_max', 0.0)):.4f} | refresh-rebar={float(metrics.get('pbd_hinge_benchmark_alignment_refresh_rebar_ratio_min', 0.0)):.4f}-{float(metrics.get('pbd_hinge_benchmark_alignment_refresh_rebar_ratio_max', 0.0)):.4f}</td></tr>
          <tr><td>Panel-zone 3D clash</td><td>{bool(metrics.get('panel_zone_3d_clash_ready', False))} | {metrics.get('panel_zone_constructability_mode', '')}</td></tr>
          <tr><td>Panel-zone reason</td><td>{metrics.get('panel_zone_constructability_reason', '')}</td></tr>
          <tr><td>Panel-zone evidence source</td><td>{metrics.get('panel_zone_source_artifact_kind', '')} | {metrics.get('panel_zone_source_contract_mode', '')}</td></tr>
          <tr><td>Panel-zone source coverage</td><td>validated rows={int(metrics.get('panel_zone_validated_source_row_count_total', 0))} | min overlap={int(metrics.get('panel_zone_validated_source_overlap_member_count_min', 0))} | bundles={', '.join(f"{k}:{v}" for k, v in sorted((metrics.get('panel_zone_source_bundle_modes', {}) or {}).items()) if str(v).strip())}</td></tr>
          <tr><td>Panel-zone validation boundary</td><td>internal_complete={bool(metrics.get('panel_zone_internal_engine_complete', False))} | external_pending={bool(metrics.get('panel_zone_external_validation_pending', False))} | boundary={metrics.get('panel_zone_validation_boundary', '')}</td></tr>
          <tr><td>Panel-zone sidecar overlap</td><td>present={bool(metrics.get('panel_zone_instruction_sidecar_present', False))} | mode={metrics.get('panel_zone_instruction_sidecar_candidate_overlap_mode', '')} | changes={int(metrics.get('panel_zone_instruction_sidecar_change_count', 0))} | overlap members={int(metrics.get('panel_zone_instruction_sidecar_overlap_member_count', 0))} | evidence={metrics.get('panel_zone_instruction_sidecar_evidence_model', '')} | delivery={metrics.get('panel_zone_instruction_sidecar_rebar_delivery_mode', '')}</td></tr>
          <tr><td>Panel-zone missing 3D sources</td><td>{', '.join(metrics.get('panel_zone_missing_required_sources', []))}</td></tr>
          <tr><td>Panel-zone solver inbox</td><td>{metrics.get('panel_zone_solver_verified_inbox_status_mode', '')} | pending={bool(metrics.get('panel_zone_solver_verified_pending_input', False))} | origin={metrics.get('panel_zone_solver_verified_source_origin_class', '') or 'missing'} | release refresh={bool(metrics.get('panel_zone_solver_verified_release_refresh_source_allowed', False))} | latest consume={bool(metrics.get('panel_zone_solver_verified_latest_consume_contract_pass', False))}:{metrics.get('panel_zone_solver_verified_latest_consume_reason_code', '')} | next={metrics.get('panel_zone_solver_verified_recommended_action', '')}</td></tr>
          <tr><td>Foundation optimization</td><td>{bool(metrics.get('foundation_optimization_ready', False))} | {metrics.get('foundation_optimization_mode', '')}</td></tr>
          <tr><td>Foundation reason</td><td>{metrics.get('foundation_optimization_reason', '')}</td></tr>
          <tr><td>Foundation scope provenance</td><td>{metrics.get('foundation_scope_source', '')} | {metrics.get('foundation_artifact_scan_mode', '')}</td></tr>
          <tr><td>Foundation upstream labels</td><td>{int(metrics.get('upstream_foundation_label_count', 0))} | {metrics.get('upstream_foundation_provenance_mode', '')}</td></tr>
          <tr><td>Wind-tunnel raw mapping</td><td>{bool(metrics.get('wind_tunnel_raw_mapping_ready', False))} | {metrics.get('wind_tunnel_mapping_mode', '')}</td></tr>
          <tr><td>Wind reason</td><td>{metrics.get('wind_tunnel_mapping_reason', '')}</td></tr>
        </table>
      </div>
      <div class="panel">
        <h2>Nightly Smoke Probe</h2>
        <table>
          <tr><td>Smoke reason</td><td>{metrics['nightly_smoke_reason_code']}</td></tr>
          <tr><td>Smoke pass rate</td><td>{metrics['nightly_smoke_pass_rate']:.2%}</td></tr>
          <tr><td>Smoke trial feasible rate</td><td>{metrics['nightly_smoke_trial_feasible_rate']:.2%}</td></tr>
          <tr><td>Smoke avg trial runtime (s)</td><td>{metrics['nightly_smoke_avg_trial_runtime_s']:.4f}</td></tr>
          <tr><td>Smoke history count</td><td>{metrics['nightly_smoke_history_count']}</td></tr>
          <tr><td>Strict recommendation</td><td>{metrics['nightly_smoke_strict_recommendation']}</td></tr>
        </table>
      </div>
      {smoke_history_panel_html}
      {authority_catalog_warning_panel_html}
      {promotion_hold_panel_html}
      <div class="panel">
        <h2>Nightly Smoke Recent Samples</h2>
        <table>
          <thead>
            <tr><td>#</td><td>Generated</td><td>Pass</td><td>Trial Feasible</td><td>Baseline Runtime (s)</td><td>Trial Runtime (s)</td><td>Trial Max DCR</td><td>Action</td></tr>
          </thead>
          <tbody>
            {''.join(smoke_recent_sample_rows_html)}
          </tbody>
        </table>
      </div>
      {measured_chain_panel_html}
      <div class="panel">
        <h2>Parser/KDS</h2>
        <table>
          <tr><td>MIDAS element rows total</td><td>{metrics['midas_element_rows_total']}</td></tr>
          <tr><td>MIDAS element rows skipped</td><td>{metrics['midas_element_rows_skipped']}</td></tr>
          <tr><td>MIDAS unknown rows</td><td>{metrics['midas_unknown_row_total']}</td></tr>
          <tr><td>MIDAS semantic load binding</td><td>{bool(metrics.get('midas_semantic_load_binding_pass', False))}</td></tr>
          <tr><td>MIDAS USE-STLD blocks</td><td>{int(metrics.get('midas_use_stld_block_count', 0))}</td></tr>
          <tr><td>MIDAS semantic load cases/combinations</td><td>{int(metrics.get('midas_semantic_load_case_count', 0))}/{int(metrics.get('midas_semantic_load_combination_count', 0))}</td></tr>
          <tr><td>MIDAS bound/unbound rows</td><td>nodal={int(metrics.get('midas_bound_nodal_load_row_count', 0))}/{int(metrics.get('midas_unbound_nodal_load_row_count', 0))}, selfweight={int(metrics.get('midas_bound_selfweight_row_count', 0))}/{int(metrics.get('midas_unbound_selfweight_row_count', 0))}, pressure={int(metrics.get('midas_bound_pressure_row_count', 0))}/{int(metrics.get('midas_unbound_pressure_row_count', 0))}</td></tr>
          <tr><td>MGT export artifact exists</td><td>{bool(metrics.get('mgt_export_artifact_exists', False))}</td></tr>
          <tr><td>MGT export contract pass</td><td>{bool(metrics.get('mgt_export_contract_pass', False))}</td></tr>
          <tr><td>MGT export support mode</td><td>{metrics.get('mgt_export_support_mode', '')}</td></tr>
          <tr><td>MGT export supported changes</td><td>{int(metrics.get('mgt_export_supported_change_count', 0))}</td></tr>
          <tr><td>MGT export unsupported changes</td><td>{int(metrics.get('mgt_export_unsupported_change_count', 0))}</td></tr>
          <tr><td>MGT export direct-patch changes</td><td>{int(metrics.get('mgt_export_direct_patch_change_count', 0))}</td></tr>
          <tr><td>MGT export direct-patch families</td><td>{metrics.get('mgt_export_direct_patch_action_family_label', '')}</td></tr>
          <tr><td>MGT rebar namespace mode</td><td>{metrics.get('mgt_export_rebar_payload_namespace_mode', '')}</td></tr>
          <tr><td>MGT rebar delivery mode</td><td>{metrics.get('mgt_export_rebar_delivery_mode', '')}</td></tr>
          <tr><td>MGT evidence model</td><td>{metrics.get('mgt_export_evidence_model', '')}</td></tr>
          <tr><td>MGT delivery boundary</td><td>direct_patch={metrics.get('mgt_export_direct_patch_action_family_label', '') or 'n/a'} | sidecar={metrics.get('mgt_export_instruction_sidecar_action_family_label', '') or 'n/a'} | connection_payload={metrics.get('mgt_export_connection_detailing_delivery_mode', '') or 'n/a'} | detailing_payload={metrics.get('mgt_export_detailing_delivery_mode', '') or 'n/a'}</td></tr>
          <tr><td>MGT rebar material namespace present</td><td>{bool(metrics.get('mgt_export_rebar_payload_material_level_namespace_present', False))}</td></tr>
          <tr><td>MGT rebar group-local namespace present</td><td>{bool(metrics.get('mgt_export_rebar_payload_group_local_namespace_present', False))}</td></tr>
          <tr><td>MGT material rebar payloads</td><td>{int(metrics.get('mgt_export_material_level_rebar_payload_available_count', 0))}/{int(metrics.get('mgt_export_material_level_rebar_payload_row_count', 0))}</td></tr>
          <tr><td>MGT group-local rebar payloads</td><td>{int(metrics.get('mgt_export_group_local_rebar_payload_available_count', 0))}/{int(metrics.get('mgt_export_group_local_rebar_payload_row_count', 0))}</td></tr>
          <tr><td>MGT connection namespace mode</td><td>{metrics.get('mgt_export_connection_detailing_payload_namespace_mode', '')}</td></tr>
          <tr><td>MGT connection group-local namespace present</td><td>{bool(metrics.get('mgt_export_connection_detailing_payload_group_local_namespace_present', False))}</td></tr>
          <tr><td>MGT group-local connection payloads</td><td>{int(metrics.get('mgt_export_group_local_connection_detailing_payload_available_count', 0))}/{int(metrics.get('mgt_export_group_local_connection_detailing_payload_row_count', 0))}</td></tr>
          <tr><td>MGT connection direct-patch eligible</td><td>{int(metrics.get('mgt_export_connection_detailing_direct_patch_eligible_change_count', 0))}</td></tr>
          <tr><td>MGT detailing namespace mode</td><td>{metrics.get('mgt_export_detailing_payload_namespace_mode', '')}</td></tr>
          <tr><td>MGT detailing group-local namespace present</td><td>{bool(metrics.get('mgt_export_detailing_payload_group_local_namespace_present', False))}</td></tr>
          <tr><td>MGT group-local detailing payloads</td><td>{int(metrics.get('mgt_export_group_local_detailing_payload_available_count', 0))}/{int(metrics.get('mgt_export_group_local_detailing_payload_row_count', 0))}</td></tr>
          <tr><td>MGT detailing direct-patch eligible</td><td>{int(metrics.get('mgt_export_detailing_direct_patch_eligible_change_count', 0))}</td></tr>
          <tr><td>MGT connection structured payload mapped</td><td>{int(metrics.get('mgt_export_connection_detailing_structured_payload_mapped_change_count', 0))}</td></tr>
          <tr><td>MGT detailing structured payload mapped</td><td>{int(metrics.get('mgt_export_detailing_structured_payload_mapped_change_count', 0))}</td></tr>
          <tr><td>MGT connection delivery mode</td><td>{metrics.get('mgt_export_connection_detailing_delivery_mode', '')}</td></tr>
          <tr><td>MGT detailing delivery mode</td><td>{metrics.get('mgt_export_detailing_delivery_mode', '')}</td></tr>
          <tr><td>MGT rebar direct-patch eligible</td><td>{int(metrics.get('mgt_export_rebar_direct_patch_eligible_change_count', 0))}</td></tr>
          <tr><td>MGT patched material rows</td><td>{int(metrics.get('mgt_export_patched_material_row_count', 0))}</td></tr>
          <tr><td>MGT cloned material rows</td><td>{int(metrics.get('mgt_export_cloned_material_count', 0))}</td></tr>
          <tr><td>MGT rebar direct-patch blockers</td><td>{metrics.get('mgt_export_rebar_direct_patch_ineligible_reason_label', '')}</td></tr>
          <tr><td>MGT rebar mapping sources</td><td>{metrics.get('mgt_export_rebar_direct_patch_mapping_source_label', '')}</td></tr>
          <tr><td>MGT export instruction sidecar changes</td><td>{int(metrics.get('mgt_export_instruction_sidecar_change_count', 0))}</td></tr>
          <tr><td>MGT export instruction sidecar families</td><td>{metrics.get('mgt_export_instruction_sidecar_action_family_label', '') or 'n/a'}</td></tr>
          <tr><td>MGT export sidecar audit-only</td><td>{metrics.get('mgt_export_instruction_sidecar_audit_only_action_family_label', '') or 'n/a'} ({int(metrics.get('mgt_export_instruction_sidecar_audit_only_change_count', 0))})</td></tr>
          <tr><td>MGT export sidecar manual-input</td><td>{metrics.get('mgt_export_instruction_sidecar_manual_input_action_family_label', '') or 'n/a'} ({int(metrics.get('mgt_export_instruction_sidecar_manual_input_change_count', 0))})</td></tr>
          <tr><td>MGT audit review manifest</td><td>{metrics.get('mgt_export_audit_review_manifest_action_family_label', '') or 'n/a'} ({int(metrics.get('mgt_export_audit_review_manifest_change_count', 0))})</td></tr>
          <tr><td>MGT audit review packets</td><td>{metrics.get('mgt_export_audit_review_packet_action_family_label', '') or 'n/a'} ({int(metrics.get('mgt_export_audit_review_packet_count', 0))})</td></tr>
          <tr><td>MGT audit packet followups</td><td>{metrics.get('mgt_export_audit_review_packet_followup_type_label', '') or 'n/a'}</td></tr>
          <tr><td>MGT audit packet files</td><td>{metrics.get('mgt_export_audit_review_packet_file_action_family_label', '') or 'n/a'} ({int(metrics.get('mgt_export_audit_review_packet_file_count', 0))})</td></tr>
          <tr><td>MGT audit review queue</td><td>{metrics.get('mgt_export_audit_review_queue_action_family_label', '') or 'n/a'} ({int(metrics.get('mgt_export_audit_review_queue_item_count', 0))})</td></tr>
          <tr><td>MGT audit queue status</td><td>{metrics.get('mgt_export_audit_review_queue_status_label', '') or 'n/a'}</td></tr>
          <tr><td>MGT audit follow-up actions</td><td>{metrics.get('mgt_export_audit_review_followup_action_label', '') or 'n/a'} ({int(metrics.get('mgt_export_audit_review_followup_item_count', 0))})</td></tr>
          <tr><td>MGT audit follow-up owner</td><td>{metrics.get('mgt_export_audit_review_followup_owner_label', '') or 'n/a'}</td></tr>
          <tr><td>MGT audit follow-up review owner</td><td>{metrics.get('mgt_export_audit_review_followup_review_owner_label', '') or 'n/a'}</td></tr>
          <tr><td>MGT audit follow-up status</td><td>{metrics.get('mgt_export_audit_review_followup_status_label', '') or 'n/a'}</td></tr>
          <tr><td>MGT audit follow-up SLA</td><td>{metrics.get('mgt_export_audit_review_followup_sla_state_label', '') or 'n/a'}</td></tr>
          <tr><td>MGT audit follow-up age</td><td>{metrics.get('mgt_export_audit_review_followup_age_bucket_label', '') or 'n/a'} (overdue={int(metrics.get('mgt_export_audit_review_followup_overdue_item_count', 0))})</td></tr>
          <tr><td>MGT audit resolution actions</td><td>{metrics.get('mgt_export_audit_review_resolution_action_label', '') or 'n/a'} ({int(metrics.get('mgt_export_audit_review_resolution_item_count', 0))})</td></tr>
          <tr><td>MGT audit resolution owner</td><td>{metrics.get('mgt_export_audit_review_resolution_owner_label', '') or 'n/a'}</td></tr>
          <tr><td>MGT audit resolution status</td><td>{metrics.get('mgt_export_audit_review_resolution_status_label', '') or 'n/a'}</td></tr>
          <tr><td>MGT export instruction sidecar priorities</td><td>{metrics.get('mgt_export_instruction_sidecar_review_priority_label', '')}</td></tr>
          <tr><td>MGT export instruction sidecar followups</td><td>{metrics.get('mgt_export_instruction_sidecar_followup_type_label', '')}</td></tr>
          <tr><td>MGT export cloned sections</td><td>{int(metrics.get('mgt_export_cloned_section_count', 0))}</td></tr>
          <tr><td>MGT export cloned thicknesses</td><td>{int(metrics.get('mgt_export_cloned_thickness_count', 0))}</td></tr>
          <tr><td>MGT export retargeted elements</td><td>{int(metrics.get('mgt_export_retargeted_element_row_count', 0))}</td></tr>
          <tr><td>KDS compliance rows</td><td>{metrics['kds_compliance_rows']}</td></tr>
          <tr><td>KDS member check rows</td><td>{metrics['kds_member_check_rows']}</td></tr>
          <tr><td>KDS clause count</td><td>{metrics['kds_clause_count']}</td></tr>
          <tr><td>NDTHA residual top abs (m)</td><td>{metrics['ndtha_residual_top_m_max_abs']}</td></tr>
          <tr><td>NDTHA residual drift abs (%)</td><td>{metrics['ndtha_residual_drift_pct_max_abs']}</td></tr>
          <tr><td>NDTHA residual fallback rate</td><td>{metrics['ndtha_residual_fallback_rate']}</td></tr>
        </table>
      </div>
      <div class="panel">
        <h2>Readiness</h2>
        <table>
          <tr><td>Commercial grade</td><td>{metrics['commercial_grade']}</td></tr>
          <tr><td>Deployment model</td><td>{metrics['deployment_model']}</td></tr>
          <tr><td>Accelerated coverage</td><td>{metrics['accelerated_coverage_target_pct_label']}</td></tr>
          <tr><td>Residual holdout</td><td>{metrics['residual_holdout_target_pct_label']}</td></tr>
          <tr><td>Estimated time saved</td><td>{metrics['estimated_time_saved_pct_label']}</td></tr>
          <tr><td>Measured chain wall-clock (comparable rolling)</td><td>{metrics.get('measured_chain_rolling_total_minutes_mean', 0.0):.2f} min (N={int(metrics.get('measured_chain_rolling_sample_count', 0))}, range={metrics.get('measured_chain_rolling_total_minutes_range', ['n/a', 'n/a'])[0]}-{metrics.get('measured_chain_rolling_total_minutes_range', ['n/a', 'n/a'])[1]} min)</td></tr>
          <tr><td>Measured chain wall-clock (current)</td><td>{metrics['measured_chain_total_minutes']:.2f} min</td></tr>
          <tr><td>Comparable run selection mode</td><td>{metrics.get('measured_chain_rolling_selection_mode', '')}</td></tr>
          <tr><td>Comparable reference deployment</td><td>{metrics.get('measured_chain_comparable_reference_deployment_model', '')}</td></tr>
          <tr><td>Comparable reference strict smoke</td><td>{bool(metrics.get('measured_chain_comparable_reference_strict_design_opt_cost_smoke', False))}</td></tr>
          <tr><td>Empirical smoke runtime reduction</td><td>{metrics['empirical_smoke_runtime_saved_pct_label']}</td></tr>
          <tr><td>Engineer-in-loop ready</td><td>{metrics['engineer_in_loop_accelerated_coverage_ready']}</td></tr>
          <tr><td>Estimated time basis</td><td>{metrics['estimated_time_saved_basis']}</td></tr>
          <tr><td>Time-saving focus</td><td>{metrics['time_saving_focus']}</td></tr>
          <tr><td>Full replacement ready</td><td>{metrics['full_commercial_replacement_ready']}</td></tr>
          <tr><td>External benchmark start now</td><td>{bool(metrics.get('external_benchmark_submission_ready_to_start_now', False))}</td></tr>
          <tr><td>External benchmark full submission ready</td><td>{bool(metrics.get('external_benchmark_submission_ready_to_start_full_submission_now', False))}</td></tr>
          <tr><td>External benchmark reason</td><td>{metrics.get('external_benchmark_submission_reason_code', '')}</td></tr>
          <tr><td>External benchmark start mode</td><td>{metrics.get('external_benchmark_submission_recommended_start_mode', '')}</td></tr>
          <tr><td>External benchmark scope</td><td>{metrics.get('external_benchmark_submission_recommended_submission_scope', '')}</td></tr>
          <tr><td>External benchmark blockers</td><td>{metrics.get('external_benchmark_submission_blocker_label', '') or 'none'}</td></tr>
          <tr><td>External benchmark cautions</td><td>{metrics.get('external_benchmark_submission_caution_label', '') or 'none'}</td></tr>
          <tr><td>External benchmark execution mode</td><td>{metrics.get('external_benchmark_execution_mode', '')}</td></tr>
          <tr><td>External benchmark execution ready tasks</td><td>{int(metrics.get('external_benchmark_execution_ready_task_count', 0))}</td></tr>
          <tr><td>External benchmark execution blocked tasks</td><td>{int(metrics.get('external_benchmark_execution_blocked_task_count', 0))}</td></tr>
          <tr><td>External benchmark execution review-boundary pending</td><td>{int(metrics.get('external_benchmark_execution_review_boundary_pending_count', 0))}</td></tr>
          <tr><td>External benchmark review-boundary resolution</td><td>{metrics.get('external_benchmark_execution_review_boundary_resolution_label', '') or 'n/a'} | owner={metrics.get('external_benchmark_execution_review_boundary_owner_label', '') or 'none'} | assignee={metrics.get('external_benchmark_execution_review_boundary_assignee_label', '') or 'none'} | assignment={metrics.get('external_benchmark_execution_review_boundary_assignment_status_label', '') or 'none'} | priority={metrics.get('external_benchmark_execution_review_boundary_priority_label', '') or 'none'} | family={metrics.get('external_benchmark_execution_review_boundary_family_label', '') or 'none'} | changes={int(metrics.get('external_benchmark_execution_review_boundary_change_count_total', 0))} | followup={metrics.get('external_benchmark_execution_review_boundary_followup_action_label', '') or 'none'} | sla={metrics.get('external_benchmark_execution_review_boundary_sla_state_label', '') or 'none'} | age={metrics.get('external_benchmark_execution_review_boundary_age_bucket_label', '') or 'none'} | overdue={int(metrics.get('external_benchmark_execution_review_boundary_overdue_count', 0))} | oldest_open_h={float(metrics.get('external_benchmark_execution_review_boundary_oldest_open_age_hours', 0.0)):.3f}</td></tr>
          <tr><td>External benchmark execution status</td><td>{metrics.get('external_benchmark_execution_status_mode', '')}</td></tr>
          <tr><td>External benchmark execution planned tasks</td><td>{int(metrics.get('external_benchmark_execution_planned_task_count', 0))}</td></tr>
          <tr><td>External benchmark execution in-progress tasks</td><td>{int(metrics.get('external_benchmark_execution_in_progress_task_count', 0))}</td></tr>
          <tr><td>External benchmark execution completed tasks</td><td>{int(metrics.get('external_benchmark_execution_completed_task_count', 0))}</td></tr>
          <tr><td>External benchmark execution failed tasks</td><td>{int(metrics.get('external_benchmark_execution_failed_task_count', 0))}</td></tr>
          <tr><td>External benchmark execution finished tasks</td><td>{int(metrics.get('external_benchmark_execution_finished_task_count', 0))}</td></tr>
          <tr><td>External benchmark execution completion ratio</td><td>{float(metrics.get('external_benchmark_execution_completion_ratio', 0.0)):.3f}</td></tr>
          <tr><td>External benchmark case onepages</td><td>{int(metrics.get('external_benchmark_case_onepage_count', 0))} | dir={artifacts.get('external_benchmark_case_onepage_dir', '') or 'n/a'}</td></tr>
          <tr><td>External benchmark case attestation workflow</td><td>cases={int(metrics.get('external_benchmark_case_attestation_case_count', 0))} | manifests={int(metrics.get('external_benchmark_case_attestation_manifest_count', 0))} | templates={int(metrics.get('external_benchmark_case_attestation_template_count', 0))} | receipts={int(metrics.get('external_benchmark_case_attestation_receipt_count', 0))} | attested={int(metrics.get('external_benchmark_case_attestation_attested_count', 0))} | source={metrics.get('external_benchmark_case_attestation_source_label', '') or 'none'} | status={metrics.get('external_benchmark_case_attestation_status_label', '') or 'none'} | kickoff_index={artifacts.get('external_benchmark_case_attestation_index_json', '') or 'n/a'}</td></tr>
          <tr><td>PBD response source</td><td>resolved_report={metrics.get('pbd_resolved_ndtha_report', '') or 'n/a'} | response_npz={metrics.get('pbd_resolved_ndtha_response_npz', '') or 'n/a'} | fallback_used={bool(metrics.get('pbd_ndtha_response_fallback_used', False))} | coverage={int(metrics.get('pbd_ndtha_response_coverage_count', 0))}</td></tr>
          <tr><td>Audit review decision batch template</td><td>items={int(metrics.get('audit_review_decision_batch_template_item_count', 0))} | status={metrics.get('audit_review_decision_batch_template_current_status_label', '') or 'none'} | owner={metrics.get('audit_review_decision_batch_template_review_owner_label', '') or 'none'} | priority={metrics.get('audit_review_decision_batch_template_review_priority_label', '') or 'none'} | attested_examples={int(metrics.get('audit_review_decision_batch_attested_example_count', 0))} | example_preview={metrics.get('audit_review_decision_batch_attested_example_preview_label', '') or 'none'}</td></tr>
          <tr><td>Approve-all readiness preview</td><td>reason={metrics.get('external_benchmark_submission_preview_approve_all_reason_code', '')} | ready_full={bool(metrics.get('external_benchmark_submission_preview_approve_all_ready_full', False))} | pending={int(metrics.get('external_benchmark_submission_preview_approve_all_pending_count', 0))} | open_revision={int(metrics.get('external_benchmark_submission_preview_approve_all_open_revision_count', 0))}</td></tr>
          <tr><td>Reject-one readiness preview</td><td>reason={metrics.get('external_benchmark_submission_preview_reject_one_reason_code', '')} | ready_full={bool(metrics.get('external_benchmark_submission_preview_reject_one_ready_full', False))} | pending={int(metrics.get('external_benchmark_submission_preview_reject_one_pending_count', 0))} | open_revision={int(metrics.get('external_benchmark_submission_preview_reject_one_open_revision_count', 0))} | blocker={metrics.get('external_benchmark_submission_preview_reject_one_blocker_label', '') or 'none'}</td></tr>
          <tr><td>Audit review decision batch runner</td><td>reason={metrics.get('audit_review_decision_batch_runner_reason_code', '')} | apply_live={bool(metrics.get('audit_review_decision_batch_runner_apply_live', False))} | live_applied={bool(metrics.get('audit_review_decision_batch_runner_live_applied', False))} | preview_reason={metrics.get('audit_review_decision_batch_runner_preview_reason_code', '') or 'none'} | preview_ready_full={bool(metrics.get('audit_review_decision_batch_runner_preview_ready_full', False))} | preview_pending={int(metrics.get('audit_review_decision_batch_runner_preview_pending_count', 0))} | preview_open_revision={int(metrics.get('audit_review_decision_batch_runner_preview_open_revision_count', 0))}</td></tr>
          <tr><td>Structural optimization viewer</td><td>{metrics.get('structural_optimization_viewer_html', '') or 'n/a'} | mode={metrics.get('structural_optimization_viewer_mode', '') or 'n/a'} | story_zone_cells={int(metrics.get('structural_optimization_viewer_story_zone_nonempty_cell_count', 0))} | max_abs_cost_delta={float(metrics.get('structural_optimization_viewer_story_zone_max_abs_cost_proxy_delta', 0.0)):.3f} | gallery={int(metrics.get('structural_optimization_viewer_gallery_tile_count', 0))}</td></tr>
          <tr><td>Optimized drawing review</td><td>{metrics.get('optimized_drawing_review_html', '') or 'n/a'} | projections={int(metrics.get('optimized_drawing_review_projection_count', 0))} | changed_groups={int(metrics.get('optimized_drawing_review_changed_group_count', 0))} | changed_members={int(metrics.get('optimized_drawing_review_changed_member_count', 0))} | axis={metrics.get('optimized_drawing_review_axis_source_mode', '') or 'n/a'} | x={metrics.get('optimized_drawing_review_axis_preview_label', '') or 'n/a'}</td></tr>
          <tr><td>Open P0 gaps</td><td>{metrics['open_gap_p0']}</td></tr>
          <tr><td>Open P1 gaps</td><td>{metrics['open_gap_p1']}</td></tr>
          <tr><td>Open P2 gaps</td><td>{metrics['open_gap_p2']}</td></tr>
          <tr><td>Registry artifacts</td><td>{metrics['registry_artifact_count']}</td></tr>
          <tr><td>Design-opt long feasible</td><td>{metrics['design_opt_long_feasible']}</td></tr>
          <tr><td>Design-opt long final max DCR</td><td>{metrics['design_opt_long_final_max_dcr']}</td></tr>
          <tr><td>Design-opt raw max drift</td><td>{metrics.get('design_opt_raw_max_drift_pct', 0.0)}</td></tr>
          <tr><td>Design-opt repaired compliance max drift</td><td>{metrics.get('design_opt_repaired_compliance_max_drift_pct', 0.0)}</td></tr>
          <tr><td>Design-opt compliance basis</td><td>{metrics.get('design_opt_compliance_basis', '')}</td></tr>
          <tr><td>Design-opt repair action count</td><td>{metrics.get('design_opt_repair_action_count', 0)}</td></tr>
          <tr><td>Design-opt constructability signal gain</td><td>{metrics.get('design_opt_constructability_signal_gain_pct', 0.0)}</td></tr>
          <tr><td>Design-opt constructability avg</td><td>{metrics.get('design_opt_baseline_constructability_avg', 0.0)} -> {metrics.get('design_opt_final_constructability_avg', 0.0)}</td></tr>
          <tr><td>Design-opt detailing complexity avg</td><td>{metrics.get('design_opt_baseline_detailing_complexity_avg', 0.0)} -> {metrics.get('design_opt_final_detailing_complexity_avg', 0.0)}</td></tr>
          <tr><td>Design-opt selected family mix</td><td>{metrics.get('design_opt_selected_family_mix_label', '')}</td></tr>
          <tr><td>Design-opt selected dominant family</td><td>{metrics.get('design_opt_selected_dominant_family', '')} ({metrics.get('design_opt_selected_dominant_family_ratio', 0.0):.2%})</td></tr>
          <tr><td>Design-opt selected family mix trend</td><td>{metrics.get('design_opt_selected_family_trend_label', '')}</td></tr>
          <tr><td>Design-opt previous dominant family</td><td>{metrics.get('design_opt_previous_dominant_family', '')} ({metrics.get('design_opt_previous_dominant_family_ratio', 0.0):.2%})</td></tr>
          <tr><td>Design-opt preview supply family mix</td><td>{metrics.get('design_opt_preview_supply_family_mix_label', '')}</td></tr>
          <tr><td>Design-opt preview missing target families</td><td>{metrics.get('design_opt_preview_missing_target_families_label', '')}</td></tr>
          <tr><td>Design-opt cost delta</td><td>{metrics['design_opt_cost_delta']}</td></tr>
          <tr><td>Design-opt changed groups</td><td>{metrics['design_opt_changed_group_count']}</td></tr>
          <tr><td>Blocked cost-down rows</td><td>{metrics['design_opt_blocked_action_row_count']}</td></tr>
          <tr><td>Blocked illegal-by-mask</td><td>{metrics['design_opt_blocked_illegal_by_mask']}</td></tr>
          <tr><td>Illegal-by-mask families</td><td>{metrics.get('design_opt_blocked_illegal_by_mask_family_label', '')}</td></tr>
          <tr><td>Blocked no-cost-gain</td><td>{metrics['design_opt_blocked_no_cost_gain']}</td></tr>
          <tr><td>Blocked constructability hard-gate</td><td>{metrics.get('design_opt_blocked_constructability_hard_gate', 0)}</td></tr>
          <tr><td>Hard-gate reasons</td><td>{metrics.get('design_opt_blocked_constructability_hard_gate_label', '')}</td></tr>
          <tr><td>Hard-gate families</td><td>{metrics.get('design_opt_blocked_constructability_hard_gate_family_label', '')}</td></tr>
          <tr><td>No-cost-gain groups</td><td>{metrics['design_opt_blocked_no_cost_group_count']}</td></tr>
          <tr><td>No-cost-gain explain rows</td><td>{metrics['design_opt_blocked_no_cost_explain_row_count']}</td></tr>
        </table>
      </div>
      <div class="panel">
        <h2>Binary Metrics</h2>
        <table>
          <tr><td>Frame</td><td>cases={derived['frame_case_count']}, drift p95={derived['frame_drift_error_pct_p95']:.3f}%, top-disp p95={derived['frame_top_disp_error_pct_p95']:.3f}%</td></tr>
          <tr><td>Wind</td><td>cases={derived['wind_case_count']}, max drift={derived['wind_max_drift_pct']:.6f}%, residual drift={derived['wind_residual_drift_pct']:.6f}%</td></tr>
          <tr><td>SSI</td><td>cases={derived['ssi_case_count']}, nonlinear span={derived['ssi_nonlinear_ratio_span']:.6f}, residual drift={derived['ssi_residual_drift_pct']:.6f}%</td></tr>
          <tr><td>Design Opt</td><td>change rows={derived['design_opt_change_rows']}, raw drift={metrics.get('design_opt_raw_max_drift_pct', 0.0):.4f}%, repaired drift={metrics.get('design_opt_repaired_compliance_max_drift_pct', 0.0):.4f}%, cost delta={derived['design_opt_cost_delta']:.3f}</td></tr>
        </table>
      </div>
      <div class="panel">
        <h2>Residual Holdout Boundary</h2>
        <table>
          <tr><td>Category</td><td>Owner</td><td>Relative Share</td><td>Absolute Project %</td><td>Scope</td></tr>
          {''.join(f"<tr><td>{row.get('label', row.get('id', ''))}</td><td>{row.get('owner', '')}</td><td>{int(row.get('relative_share_pct', 0))}%</td><td>{_coverage_range_label(row.get('absolute_project_pct_range'))}</td><td>{row.get('scope', '')}</td></tr>" for row in holdout_buckets)}
        </table>
      </div>
      <div class="panel">
        <h2>Time-Saving Coverage</h2>
        <table>
          <tr><td>Coverage target</td><td>{metrics['accelerated_coverage_target_pct_label']}</td></tr>
          <tr><td>Residual holdout</td><td>{metrics['residual_holdout_target_pct_label']}</td></tr>
          <tr><td>Estimated time saved</td><td>{metrics['estimated_time_saved_pct_label']}</td></tr>
          <tr><td>Measured chain wall-clock (comparable rolling)</td><td>{metrics.get('measured_chain_rolling_total_minutes_mean', 0.0):.2f} min (N={int(metrics.get('measured_chain_rolling_sample_count', 0))}, range={metrics.get('measured_chain_rolling_total_minutes_range', ['n/a', 'n/a'])[0]}-{metrics.get('measured_chain_rolling_total_minutes_range', ['n/a', 'n/a'])[1]} min)</td></tr>
          <tr><td>Measured chain wall-clock (current)</td><td>{metrics['measured_chain_total_minutes']:.2f} min</td></tr>
          <tr><td>Comparable run selection mode</td><td>{metrics.get('measured_chain_rolling_selection_mode', '')}</td></tr>
          <tr><td>Comparable reference deployment</td><td>{metrics.get('measured_chain_comparable_reference_deployment_model', '')}</td></tr>
          <tr><td>Comparable reference strict smoke</td><td>{bool(metrics.get('measured_chain_comparable_reference_strict_design_opt_cost_smoke', False))}</td></tr>
          <tr><td>Empirical smoke runtime reduction</td><td>{metrics['empirical_smoke_runtime_saved_pct_label']}</td></tr>
          <tr><td>Basis</td><td>{metrics['estimated_time_saved_basis']}</td></tr>
          <tr><td>Focus</td><td>{metrics['time_saving_focus']}</td></tr>
        </table>
      </div>
      <div class="panel">
        <h2>Residual Holdout Review Table</h2>
        <table>
          <tr><td>Category</td><td>Axis</td><td>Detail</td><td>Owner</td><td>Why</td></tr>
          {''.join(f"<tr><td>{row.get('bucket_label', row.get('bucket_id', ''))}</td><td>{row.get('detail_axis', '')}</td><td>{row.get('detail_value', '')}</td><td>{row.get('owner', '')}</td><td>{row.get('why', '')}</td></tr>" for row in holdout_detail_rows)}
        </table>
      </div>
      <div class="panel">
        <h2>Residual Holdout Routing Matrix</h2>
        <table>
          <tr><td>Category</td><td>Track</td><td>Submodel</td><td>Review Story/Zone</td><td>Member Family</td><td>Owner</td><td>Why</td></tr>
          {''.join(f"<tr><td>{row.get('bucket_label', '')}</td><td>{row.get('authority_track', '')}</td><td>{row.get('submodel_family', '')}</td><td>{row.get('review_story_zone', '')}</td><td>{row.get('member_family', '')}</td><td>{row.get('owner', '')}</td><td>{row.get('why', '')}</td></tr>" for row in holdout_matrix_rows)}
        </table>
      </div>
      <div class="panel">
        <h2>Authority Catalog Routing Diff</h2>
        <table>
          <tr><td>Baseline seeded</td><td>{bool(authority_catalog_diff.get('baseline_seeded', False))}</td></tr>
          <tr><td>Changes</td><td>{int(authority_catalog_diff.get('change_count', 0))}</td></tr>
          <tr><td>Added</td><td>{int(authority_catalog_diff.get('added_count', 0))}</td></tr>
          <tr><td>Removed</td><td>{int(authority_catalog_diff.get('removed_count', 0))}</td></tr>
          <tr><td>Unchanged</td><td>{int(authority_catalog_diff.get('unchanged_count', 0))}</td></tr>
        </table>
        <table style="margin-top:12px;">
          <tr><td>Change</td><td>Track</td><td>Submodel</td><td>Review Story/Zone</td><td>Member Family</td><td>Owner</td><td>Why</td></tr>
          {authority_catalog_diff_rows_html}
        </table>
      </div>
      <div class="panel">
        <h2>Blocked Cost-Down Actions</h2>
        <table>
          <tr><td>Blocked rows</td><td>{metrics['design_opt_blocked_action_row_count']}</td></tr>
          <tr><td>Illegal by mask</td><td>{metrics['design_opt_blocked_illegal_by_mask']}</td></tr>
          <tr><td>Illegal-by-mask families</td><td>{metrics.get('design_opt_blocked_illegal_by_mask_family_label', '')}</td></tr>
          <tr><td>No cost gain</td><td>{metrics['design_opt_blocked_no_cost_gain']}</td></tr>
          <tr><td>Constructability hard gate</td><td>{metrics.get('design_opt_blocked_constructability_hard_gate', 0)}</td></tr>
          <tr><td>Hard-gate reasons</td><td>{metrics.get('design_opt_blocked_constructability_hard_gate_label', '')}</td></tr>
          <tr><td>No-cost-gain groups</td><td>{metrics['design_opt_blocked_no_cost_group_count']}</td></tr>
          <tr><td>No-cost-gain explain rows</td><td>{metrics['design_opt_blocked_no_cost_explain_row_count']}</td></tr>
        </table>
      </div>
      <div class="panel">
        <h2>Design Optimization Entrypoint Groups</h2>
        <table>
          <tr><td>Group</td><td>Reports</td><td>Pass count</td><td>Fail count</td><td>All pass</td><td>Members</td></tr>
          {entrypoint_group_html}
        </table>
      </div>
      <div class="panel">
        <h2>Appendix</h2>
        {native_roundtrip_appendix_html}
        {irregular_structure_appendix_html}
        {entrypoint_detail_html}
        {row_provenance_appendix_html}
        {case_onepage_appendix_html}
      </div>
    </div>
  </div>
</body>
</html>
"""
    path.write_text(html_output, encoding="utf-8")


def _write_summary_pdf(path: Path, summary: dict) -> None:
    configure_matplotlib_cjk_pdf()
    metrics = summary["metrics"]
    checks = summary["checks"]
    derived = summary["derived"]
    entrypoint_groups = list(summary.get("design_optimization_entrypoint_groups", []))
    artifacts = summary.get("artifacts") if isinstance(summary.get("artifacts"), dict) else {}
    smoke_history_png = Path(str(artifacts.get("nightly_smoke_history_png", "") or ""))
    measured_chain_category_png = Path(str(artifacts.get("measured_chain_category_png", "") or ""))
    smoke_recent_samples = list(summary.get("nightly_smoke_recent_samples", []))
    holdout_buckets = list(summary.get("residual_holdout_buckets", []))
    holdout_detail_rows = list(summary.get("residual_holdout_detail_rows", []))
    holdout_matrix_rows = list(summary.get("residual_holdout_matrix_rows", []))
    authority_catalog_diff = summary.get("authority_catalog_routing_diff") if isinstance(summary.get("authority_catalog_routing_diff"), dict) else {}
    authority_catalog_warning_active = bool(int(summary.get("authority_catalog_diff_change_count", 0) or 0) > 0)
    promotion_reason_code = str(summary.get("promotion_reason_code", ""))
    promotion_hold_for_review = bool(summary.get("promotion_hold_for_review", False))
    hold_review_manifest = str(summary.get("hold_review_manifest", "") or "")
    hold_review_packet_md = str(summary.get("hold_review_packet_md", "") or "")
    hold_review_packet_pdf = str(summary.get("hold_review_packet_pdf", "") or "")
    hold_review_ack_json = str(summary.get("hold_review_ack_json", "") or "")
    midas_section_library_summary_line = str(metrics.get("midas_section_library_summary_line", "") or "n/a")
    material_constitutive_summary_line = str(metrics.get("material_constitutive_summary_line", "") or "n/a")
    surface_interaction_benchmark_summary_line = str(
        metrics.get("surface_interaction_benchmark_summary_line", "") or "n/a"
    )
    midas_native_roundtrip_summary_line = str(metrics.get("midas_native_roundtrip_summary_line", "") or "n/a")
    midas_native_roundtrip_writeback_diff_summary_line = str(
        metrics.get("midas_native_roundtrip_writeback_diff_summary_line", "") or "n/a"
    )
    korean_source_ingest_summary_line = _compact_korean_source_ingest_summary_line(
        str(metrics.get("korean_source_ingest_summary_line", "") or "n/a")
    )
    measured_benchmark_breadth_summary_line = str(
        metrics.get("measured_benchmark_breadth_summary_line", "") or "n/a"
    )
    opensees_canonical_breadth_summary_line = str(
        metrics.get("opensees_canonical_breadth_summary_line", "") or "n/a"
    )
    korean_native_roundtrip_representative_rows = _korean_native_roundtrip_representative_rows(summary)
    korean_structural_preview_queue_summary_line = str(
        metrics.get("korean_structural_preview_queue_summary_line", "") or "n/a"
    )
    korean_structural_preview_queue_summary_line = _compact_korean_structural_preview_queue_summary_line(
        korean_structural_preview_queue_summary_line
    )
    row_provenance_summary_line = str(metrics.get("midas_kds_row_provenance_export_summary_line", "") or "n/a")
    irregular_structure_summary_line = str(
        metrics.get("irregular_structure_summary_line", "") or metrics.get("irregular_structure_track_summary_line", "") or "n/a"
    )
    irregular_benchmark_execution_summary_line = str(metrics.get("irregular_benchmark_execution_summary_line", "") or "n/a")
    row_provenance_preview_rows = [
        row for row in (summary.get("midas_kds_row_provenance_preview_rows") or []) if isinstance(row, dict)
    ]
    row_provenance_clause_filter_rows = [
        row for row in (summary.get("midas_kds_row_provenance_clause_filter_rows") or []) if isinstance(row, dict)
    ]
    row_provenance_member_filter_rows = [
        row for row in (summary.get("midas_kds_row_provenance_member_filter_rows") or []) if isinstance(row, dict)
    ]
    row_provenance_hazard_filter_rows = [
        row for row in (summary.get("midas_kds_row_provenance_hazard_filter_rows") or []) if isinstance(row, dict)
    ]
    row_provenance_rule_family_filter_rows = [
        row for row in (summary.get("midas_kds_row_provenance_rule_family_filter_rows") or []) if isinstance(row, dict)
    ]
    row_provenance_json = str(artifacts.get("midas_kds_row_provenance_export_json", "") or "n/a")
    row_provenance_csv = str(artifacts.get("midas_kds_row_provenance_export_csv", "") or "n/a")
    row_provenance_report = str(artifacts.get("midas_kds_row_provenance_export_report", "") or "n/a")
    midas_section_library_status_label = (
        "embedded metadata validated" if midas_section_library_summary_line != "n/a" else "validator unavailable"
    )
    midas_section_library_surface_note = (
        "nightly, release gap, committee dashboard, and this external-validation onepage all consume the same validator line"
    )
    rows = [
        ("Bundle", summary["bundle_id"]),
        ("Generated", summary["generated_at"]),
        ("Nightly", checks["nightly_release"]),
        ("CI", checks["ci_gate"]),
        ("Static validation", checks["static_validation"]),
        ("Freeze", checks["freeze_release"]),
        ("Promotion", checks["promotion"]),
        ("Promotion reason", promotion_reason_code or "PASS"),
        ("Promotion hold", str(promotion_hold_for_review)),
        ("Hold review manifest", hold_review_manifest or "n/a"),
        ("Hold review packet", hold_review_packet_md or "n/a"),
        ("Hold review packet pdf", hold_review_packet_pdf or "n/a"),
        ("Hold review ack", hold_review_ack_json or "n/a"),
        ("Smoke reason", metrics["nightly_smoke_reason_code"]),
        ("Smoke pass rate", f"{metrics['nightly_smoke_pass_rate']:.2%}"),
        ("Smoke trial feasible", f"{metrics['nightly_smoke_trial_feasible_rate']:.2%}"),
        ("Smoke avg trial runtime (s)", f"{metrics['nightly_smoke_avg_trial_runtime_s']:.4f}"),
        ("Smoke strict recommendation", metrics["nightly_smoke_strict_recommendation"]),
        ("Signed registry", checks["signed_release_registry"]),
        ("Registry signature", checks["registry_signature_verified"]),
        ("Solver HIP e2e", checks["solver_hip_e2e"]),
        ("RC benchmark lock", checks["rc_benchmark_lock"]),
        ("NDTHA residual gate", checks["ndtha_residual_gate"]),
        ("Committee package", checks["committee_review_package"]),
        ("MIDAS section-library validator", midas_section_library_summary_line),
        ("MIDAS section-library status", midas_section_library_status_label),
        ("Material constitutive", material_constitutive_summary_line),
        ("Surface interaction benchmark", surface_interaction_benchmark_summary_line),
        ("KDS row provenance export", row_provenance_summary_line),
        ("KR ingest", korean_source_ingest_summary_line),
        ("Measured benchmark breadth", measured_benchmark_breadth_summary_line),
        ("OpenSees canonical breadth", opensees_canonical_breadth_summary_line),
        ("KR preview queue", korean_structural_preview_queue_summary_line),
        (
            "KR representative batches",
            (
                " | ".join(
                    f"{str(row.get('structure_type', '') or 'n/a')}={str(row.get('source_id', '') or 'n/a')}"
                    for row in korean_native_roundtrip_representative_rows[:5]
                )
                or "n/a"
            ),
        ),
        ("Irregular structure track", irregular_structure_summary_line),
        ("Irregular benchmark execution", irregular_benchmark_execution_summary_line),
        ("Commercial grade", metrics["commercial_grade"]),
        ("Deployment model", metrics["deployment_model"]),
        ("Accelerated coverage", metrics["accelerated_coverage_target_pct_label"]),
        ("Residual holdout", metrics["residual_holdout_target_pct_label"]),
        ("Estimated time saved", metrics["estimated_time_saved_pct_label"]),
        ("Empirical smoke runtime reduction", metrics["empirical_smoke_runtime_saved_pct_label"]),
        ("Comparable run mode", metrics.get("measured_chain_rolling_selection_mode", "")),
        ("Comparable deployment", metrics.get("measured_chain_comparable_reference_deployment_model", "")),
        ("Comparable strict smoke", str(bool(metrics.get("measured_chain_comparable_reference_strict_design_opt_cost_smoke", False)))),
        ("Engineer-in-loop ready", str(metrics["engineer_in_loop_accelerated_coverage_ready"])),
        ("Estimated time basis", metrics["estimated_time_saved_basis"]),
        ("Time-saving focus", metrics["time_saving_focus"]),
        ("Full replacement ready", str(metrics["full_commercial_replacement_ready"])),
        ("External benchmark start now", str(bool(metrics.get("external_benchmark_submission_ready_to_start_now", False)))),
        ("External benchmark full submission ready", str(bool(metrics.get("external_benchmark_submission_ready_to_start_full_submission_now", False)))),
        ("External benchmark reason", str(metrics.get("external_benchmark_submission_reason_code", ""))),
        ("External benchmark start mode", str(metrics.get("external_benchmark_submission_recommended_start_mode", ""))),
        ("External benchmark scope", str(metrics.get("external_benchmark_submission_recommended_submission_scope", ""))),
        ("External benchmark blockers", str(metrics.get("external_benchmark_submission_blocker_label", "") or "none")),
        ("External benchmark cautions", str(metrics.get("external_benchmark_submission_caution_label", "") or "none")),
        ("External benchmark execution mode", str(metrics.get("external_benchmark_execution_mode", ""))),
        ("External benchmark execution ready tasks", str(int(metrics.get("external_benchmark_execution_ready_task_count", 0)))),
        ("External benchmark execution blocked tasks", str(int(metrics.get("external_benchmark_execution_blocked_task_count", 0)))),
        ("External benchmark execution review-boundary pending", str(int(metrics.get("external_benchmark_execution_review_boundary_pending_count", 0)))),
        ("External benchmark review-boundary resolution", f"{metrics.get('external_benchmark_execution_review_boundary_resolution_label', '') or 'n/a'} | owner={metrics.get('external_benchmark_execution_review_boundary_owner_label', '') or 'none'} | assignee={metrics.get('external_benchmark_execution_review_boundary_assignee_label', '') or 'none'} | assignment={metrics.get('external_benchmark_execution_review_boundary_assignment_status_label', '') or 'none'} | priority={metrics.get('external_benchmark_execution_review_boundary_priority_label', '') or 'none'} | family={metrics.get('external_benchmark_execution_review_boundary_family_label', '') or 'none'} | changes={int(metrics.get('external_benchmark_execution_review_boundary_change_count_total', 0))} | followup={metrics.get('external_benchmark_execution_review_boundary_followup_action_label', '') or 'none'} | sla={metrics.get('external_benchmark_execution_review_boundary_sla_state_label', '') or 'none'} | age={metrics.get('external_benchmark_execution_review_boundary_age_bucket_label', '') or 'none'} | overdue={int(metrics.get('external_benchmark_execution_review_boundary_overdue_count', 0))} | oldest_open_h={float(metrics.get('external_benchmark_execution_review_boundary_oldest_open_age_hours', 0.0)):.3f}"),
        ("External benchmark execution status", str(metrics.get("external_benchmark_execution_status_mode", ""))),
        ("External benchmark execution status counts", f"planned={int(metrics.get('external_benchmark_execution_planned_task_count', 0))} | in_progress={int(metrics.get('external_benchmark_execution_in_progress_task_count', 0))} | completed={int(metrics.get('external_benchmark_execution_completed_task_count', 0))} | failed={int(metrics.get('external_benchmark_execution_failed_task_count', 0))} | finished={int(metrics.get('external_benchmark_execution_finished_task_count', 0))} | completion_ratio={float(metrics.get('external_benchmark_execution_completion_ratio', 0.0)):.3f}"),
        ("External benchmark case attestation workflow", f"cases={int(metrics.get('external_benchmark_case_attestation_case_count', 0))} | manifests={int(metrics.get('external_benchmark_case_attestation_manifest_count', 0))} | templates={int(metrics.get('external_benchmark_case_attestation_template_count', 0))} | receipts={int(metrics.get('external_benchmark_case_attestation_receipt_count', 0))} | attested={int(metrics.get('external_benchmark_case_attestation_attested_count', 0))} | source={metrics.get('external_benchmark_case_attestation_source_label', '') or 'none'} | status={metrics.get('external_benchmark_case_attestation_status_label', '') or 'none'} | kickoff_index={artifacts.get('external_benchmark_case_attestation_index_json', '') or 'n/a'}"),
        ("PBD response source", f"resolved_report={metrics.get('pbd_resolved_ndtha_report', '') or 'n/a'} | response_npz={metrics.get('pbd_resolved_ndtha_response_npz', '') or 'n/a'} | fallback_used={bool(metrics.get('pbd_ndtha_response_fallback_used', False))} | coverage={int(metrics.get('pbd_ndtha_response_coverage_count', 0))}"),
        ("Audit review decision batch template", f"items={int(metrics.get('audit_review_decision_batch_template_item_count', 0))} | status={metrics.get('audit_review_decision_batch_template_current_status_label', '') or 'none'} | owner={metrics.get('audit_review_decision_batch_template_review_owner_label', '') or 'none'} | priority={metrics.get('audit_review_decision_batch_template_review_priority_label', '') or 'none'} | attested_examples={int(metrics.get('audit_review_decision_batch_attested_example_count', 0))} | example_preview={metrics.get('audit_review_decision_batch_attested_example_preview_label', '') or 'none'}"),
        ("Approve-all readiness preview", f"reason={metrics.get('external_benchmark_submission_preview_approve_all_reason_code', '')} | ready_full={bool(metrics.get('external_benchmark_submission_preview_approve_all_ready_full', False))} | pending={int(metrics.get('external_benchmark_submission_preview_approve_all_pending_count', 0))} | open_revision={int(metrics.get('external_benchmark_submission_preview_approve_all_open_revision_count', 0))}"),
        ("Reject-one readiness preview", f"reason={metrics.get('external_benchmark_submission_preview_reject_one_reason_code', '')} | ready_full={bool(metrics.get('external_benchmark_submission_preview_reject_one_ready_full', False))} | pending={int(metrics.get('external_benchmark_submission_preview_reject_one_pending_count', 0))} | open_revision={int(metrics.get('external_benchmark_submission_preview_reject_one_open_revision_count', 0))} | blocker={metrics.get('external_benchmark_submission_preview_reject_one_blocker_label', '') or 'none'}"),
        ("Audit review decision batch runner", f"reason={metrics.get('audit_review_decision_batch_runner_reason_code', '')} | apply_live={bool(metrics.get('audit_review_decision_batch_runner_apply_live', False))} | live_applied={bool(metrics.get('audit_review_decision_batch_runner_live_applied', False))} | preview_reason={metrics.get('audit_review_decision_batch_runner_preview_reason_code', '') or 'none'} | preview_ready_full={bool(metrics.get('audit_review_decision_batch_runner_preview_ready_full', False))} | preview_pending={int(metrics.get('audit_review_decision_batch_runner_preview_pending_count', 0))} | preview_open_revision={int(metrics.get('audit_review_decision_batch_runner_preview_open_revision_count', 0))}"),
        ("Structural optimization viewer", f"{metrics.get('structural_optimization_viewer_html', '') or 'n/a'} | mode={metrics.get('structural_optimization_viewer_mode', '') or 'n/a'} | story_zone_cells={int(metrics.get('structural_optimization_viewer_story_zone_nonempty_cell_count', 0))} | max_abs_cost_delta={float(metrics.get('structural_optimization_viewer_story_zone_max_abs_cost_proxy_delta', 0.0)):.3f} | gallery={int(metrics.get('structural_optimization_viewer_gallery_tile_count', 0))}"),
        ("Optimized drawing review", f"{metrics.get('optimized_drawing_review_html', '') or 'n/a'} | projections={int(metrics.get('optimized_drawing_review_projection_count', 0))} | changed_groups={int(metrics.get('optimized_drawing_review_changed_group_count', 0))} | changed_members={int(metrics.get('optimized_drawing_review_changed_member_count', 0))} | axis={metrics.get('optimized_drawing_review_axis_source_mode', '') or 'n/a'} | x={metrics.get('optimized_drawing_review_axis_preview_label', '') or 'n/a'}"),
        (
            "Authority routing warning",
            (
                f"changes={int(summary.get('authority_catalog_diff_change_count', 0))}, "
                f"added={int(summary.get('authority_catalog_diff_added_count', 0))}, "
                f"removed={int(summary.get('authority_catalog_diff_removed_count', 0))}"
                if authority_catalog_warning_active
                else "none"
            ),
        ),
        ("Open gaps", f"P0={metrics['open_gap_p0']} / P1={metrics['open_gap_p1']} / P2={metrics['open_gap_p2']}"),
        ("MIDAS rows", f"total={metrics['midas_element_rows_total']}, skipped={metrics['midas_element_rows_skipped']}, unknown={metrics['midas_unknown_row_total']}"),
        ("KDS rows", f"compliance={metrics['kds_compliance_rows']}, member_checks={metrics['kds_member_check_rows']}, clauses={metrics['kds_clause_count']}"),
        ("NDTHA residual", f"top={metrics['ndtha_residual_top_m_max_abs']} m, drift={metrics['ndtha_residual_drift_pct_max_abs']} %, fallback_rate={metrics['ndtha_residual_fallback_rate']}"),
        ("Registry artifacts", str(metrics["registry_artifact_count"])),
        ("Design-opt long feasible", str(metrics["design_opt_long_feasible"])),
        ("Design-opt long final max DCR", str(metrics["design_opt_long_final_max_dcr"])),
        ("Design-opt raw max drift", str(metrics.get("design_opt_raw_max_drift_pct", 0.0))),
        ("Design-opt repaired compliance max drift", str(metrics.get("design_opt_repaired_compliance_max_drift_pct", 0.0))),
        ("Design-opt compliance basis", str(metrics.get("design_opt_compliance_basis", ""))),
        ("Design-opt repair action count", str(metrics.get("design_opt_repair_action_count", 0))),
        ("Design-opt constructability signal gain", str(metrics.get("design_opt_constructability_signal_gain_pct", 0.0))),
        ("Design-opt constructability avg", f"{metrics.get('design_opt_baseline_constructability_avg', 0.0)} -> {metrics.get('design_opt_final_constructability_avg', 0.0)}"),
        ("Design-opt detailing complexity avg", f"{metrics.get('design_opt_baseline_detailing_complexity_avg', 0.0)} -> {metrics.get('design_opt_final_detailing_complexity_avg', 0.0)}"),
        ("Design-opt selected family mix", str(metrics.get("design_opt_selected_family_mix_label", ""))),
        ("Design-opt selected dominant family", f"{metrics.get('design_opt_selected_dominant_family', '')} ({metrics.get('design_opt_selected_dominant_family_ratio', 0.0):.2%})"),
        ("Design-opt selected family mix trend", str(metrics.get("design_opt_selected_family_trend_label", ""))),
        ("Design-opt previous dominant family", f"{metrics.get('design_opt_previous_dominant_family', '')} ({metrics.get('design_opt_previous_dominant_family_ratio', 0.0):.2%})"),
        ("Design-opt preview supply family mix", str(metrics.get("design_opt_preview_supply_family_mix_label", ""))),
        ("Design-opt preview missing target families", str(metrics.get("design_opt_preview_missing_target_families_label", ""))),
        ("MGT export direct-patch changes", str(metrics.get("mgt_export_direct_patch_change_count", 0))),
        ("MGT export direct-patch families", str(metrics.get("mgt_export_direct_patch_action_family_label", ""))),
        ("MGT rebar namespace mode", str(metrics.get("mgt_export_rebar_payload_namespace_mode", ""))),
        ("MGT rebar delivery mode", str(metrics.get("mgt_export_rebar_delivery_mode", ""))),
        ("MGT evidence model", str(metrics.get("mgt_export_evidence_model", ""))),
        ("MGT rebar material namespace present", str(bool(metrics.get("mgt_export_rebar_payload_material_level_namespace_present", False)))),
        ("MGT rebar group-local namespace present", str(bool(metrics.get("mgt_export_rebar_payload_group_local_namespace_present", False)))),
        ("MGT material rebar payloads", f"{int(metrics.get('mgt_export_material_level_rebar_payload_available_count', 0))}/{int(metrics.get('mgt_export_material_level_rebar_payload_row_count', 0))}"),
        ("MGT group-local rebar payloads", str(metrics.get("mgt_export_group_local_rebar_payload_row_count", 0))),
        ("MGT rebar direct-patch eligible", str(metrics.get("mgt_export_rebar_direct_patch_eligible_change_count", 0))),
        ("MGT rebar direct-patch blockers", str(metrics.get("mgt_export_rebar_direct_patch_ineligible_reason_label", ""))),
        ("MGT rebar mapping sources", str(metrics.get("mgt_export_rebar_direct_patch_mapping_source_label", ""))),
        ("Design-opt cost delta", str(metrics["design_opt_cost_delta"])),
        ("Design-opt changed groups", str(metrics["design_opt_changed_group_count"])),
        ("Blocked cost-down rows", str(metrics["design_opt_blocked_action_row_count"])),
        ("Blocked illegal-by-mask", str(metrics["design_opt_blocked_illegal_by_mask"])),
        ("Illegal-by-mask families", str(metrics.get("design_opt_blocked_illegal_by_mask_family_label", ""))),
        ("Blocked no-cost-gain", str(metrics["design_opt_blocked_no_cost_gain"])),
        ("Blocked constructability hard-gate", str(metrics.get("design_opt_blocked_constructability_hard_gate", 0))),
        ("Hard-gate reasons", str(metrics.get("design_opt_blocked_constructability_hard_gate_label", ""))),
        ("Hard-gate families", str(metrics.get("design_opt_blocked_constructability_hard_gate_family_label", ""))),
        ("No-cost-gain groups", str(metrics["design_opt_blocked_no_cost_group_count"])),
        ("No-cost-gain explain rows", str(metrics["design_opt_blocked_no_cost_explain_row_count"])),
        ("Design-opt groups", " | ".join(f"{row['group_label']}={row['report_count']}/{row['entrypoint_count']}" for row in entrypoint_groups)),
        ("Frame metrics", f"cases={derived['frame_case_count']}, drift_p95={derived['frame_drift_error_pct_p95']:.3f}%, top_disp_p95={derived['frame_top_disp_error_pct_p95']:.3f}%"),
        ("Wind metrics", f"cases={derived['wind_case_count']}, max_drift={derived['wind_max_drift_pct']:.6f}%, residual_drift={derived['wind_residual_drift_pct']:.6f}%"),
        ("SSI metrics", f"cases={derived['ssi_case_count']}, nonlinear_span={derived['ssi_nonlinear_ratio_span']:.6f}, residual_drift={derived['ssi_residual_drift_pct']:.6f}%"),
        ("Design-opt metrics", f"rows={derived['design_opt_change_rows']}, raw_drift={metrics.get('design_opt_raw_max_drift_pct', 0.0):.4f}%, repaired_drift={metrics.get('design_opt_repaired_compliance_max_drift_pct', 0.0):.4f}%, cost_delta={derived['design_opt_cost_delta']:.3f}"),
    ]

    path.parent.mkdir(parents=True, exist_ok=True)
    with PdfPages(path) as pdf:
        def _save_text_page(fig) -> None:
            finalize_pdf_figure(fig, text_page=True)
            pdf.savefig(fig)

        def _save_image_page(fig) -> None:
            finalize_pdf_figure(fig, text_page=False)
            pdf.savefig(fig)

        def _new_summary_page(title: str):
            fig = plt.figure(figsize=(11, 8.5))
            ax = fig.add_subplot(111)
            ax.axis("off")
            ax.text(0.03, 0.96, title, fontsize=22, weight="bold", va="top")
            return fig, ax

        fig, ax = _new_summary_page("External Validation One-Page")
        spotlight_box = FancyBboxPatch(
            (0.035, 0.73),
            0.93,
            0.16,
            boxstyle="round,pad=0.012,rounding_size=0.02",
            linewidth=1.2,
            edgecolor=(31 / 255, 111 / 255, 80 / 255, 0.45),
            facecolor="#fffaf2",
        )
        ax.add_patch(spotlight_box)
        status_pill = FancyBboxPatch(
            (0.05, 0.785),
            0.18,
            0.035,
            boxstyle="round,pad=0.01,rounding_size=0.02",
            linewidth=0.8,
            edgecolor=(31 / 255, 111 / 255, 80 / 255, 0.28),
            facecolor=(31 / 255, 111 / 255, 80 / 255, 0.08),
        )
        ax.add_patch(status_pill)
        ax.text(0.05, 0.875, "MIDAS Section Library", fontsize=11, color="#8d6e63", va="top")
        ax.text(0.05, 0.845, "embedded metadata validated", fontsize=20, weight="bold", color="#1f1a16", va="top")
        ax.text(0.058, 0.803, "static + contract gate", fontsize=9.5, weight="bold", color="#1f6f50", va="center")
        ax.text(0.05, 0.765, midas_section_library_summary_line, fontsize=10.5, weight="bold", color="#1f1a16", va="top", wrap=True)
        ax.text(0.05, 0.735, midas_section_library_surface_note, fontsize=9.4, color="#5f5147", va="top", wrap=True)
        validator_box = FancyBboxPatch(
            (0.035, 0.62),
            0.93,
            0.07,
            boxstyle="round,pad=0.010,rounding_size=0.018",
            linewidth=1.0,
            edgecolor="#d8c9b6",
            facecolor="#f4ecdf",
        )
        ax.add_patch(validator_box)
        ax.text(0.05, 0.675, "Validator line", fontsize=10.2, color="#8d6e63", va="top")
        ax.text(0.05, 0.645, midas_section_library_summary_line, fontsize=10.0, weight="bold", color="#1f1a16", va="top", wrap=True)
        y = 0.56
        for key, value in rows:
            if y < 0.10:
                _save_text_page(fig)
                plt.close(fig)
                fig, ax = _new_summary_page("External Validation One-Page (Continued)")
                y = 0.90
            ax.text(0.04, y, f"{key}", fontsize=11, color="#6c5b4d", va="top")
            ax.text(0.34, y, f"{value}", fontsize=11.5, color="#1f1a16", va="top")
            y -= 0.045
        if y < 0.16:
            _save_text_page(fig)
            plt.close(fig)
            fig, ax = _new_summary_page("External Validation One-Page (Notes)")
            y = 0.90
        ax.text(
            0.04,
            y,
            "This is the current external-validation submission baseline. "
            "Previous submission bundles were pruned after this package was created.",
            fontsize=10,
            va="top",
            wrap=True,
        )
        _save_text_page(fig)
        plt.close(fig)
        native_roundtrip_appendix_lines = _midas_native_roundtrip_appendix_markdown(summary, artifacts)
        if native_roundtrip_appendix_lines:
            fig = plt.figure(figsize=(11, 8.5))
            ax = fig.add_subplot(111)
            ax.axis("off")
            ax.text(0.03, 0.96, "Appendix: MIDAS Native Roundtrip / Write-Back Taxonomy", fontsize=18, weight="bold", va="top")
            y = 0.90
            for line in native_roundtrip_appendix_lines[2:]:
                text = str(line)
                if not text.strip():
                    y -= 0.018
                    continue
                ax.text(0.04, y, text, fontsize=8.7, va="top", wrap=True)
                y -= 0.032 if text.startswith("|") else 0.042
                if y < 0.10:
                    _save_text_page(fig)
                    plt.close(fig)
                    fig = plt.figure(figsize=(11, 8.5))
                    ax = fig.add_subplot(111)
                    ax.axis("off")
                    ax.text(0.03, 0.96, "Appendix: MIDAS Native Roundtrip / Write-Back Taxonomy", fontsize=18, weight="bold", va="top")
                    y = 0.90
            _save_text_page(fig)
            plt.close(fig)
        irregular_structure_appendix_lines = _irregular_structure_appendix_markdown(summary, artifacts)
        if irregular_structure_appendix_lines:
            fig = plt.figure(figsize=(11, 8.5))
            ax = fig.add_subplot(111)
            ax.axis("off")
            ax.text(0.03, 0.96, "Appendix: Irregular Structure Track", fontsize=18, weight="bold", va="top")
            y = 0.90
            for line in irregular_structure_appendix_lines[2:]:
                text = str(line)
                if not text.strip():
                    y -= 0.018
                    continue
                ax.text(0.04, y, text, fontsize=8.7, va="top", wrap=True)
                y -= 0.032 if text.startswith("|") else 0.042
                if y < 0.10:
                    _save_text_page(fig)
                    plt.close(fig)
                    fig = plt.figure(figsize=(11, 8.5))
                    ax = fig.add_subplot(111)
                    ax.axis("off")
                    ax.text(0.03, 0.96, "Appendix: Irregular Structure Track", fontsize=18, weight="bold", va="top")
                    y = 0.90
            _save_text_page(fig)
            plt.close(fig)
        if row_provenance_summary_line != "n/a" or row_provenance_preview_rows or row_provenance_clause_filter_rows or row_provenance_member_filter_rows or row_provenance_hazard_filter_rows or row_provenance_rule_family_filter_rows:
            fig = plt.figure(figsize=(11, 8.5))
            ax = fig.add_subplot(111)
            ax.axis("off")
            ax.text(0.03, 0.96, "Appendix: MIDAS KDS Row Provenance Export", fontsize=18, weight="bold", va="top")
            ax.text(0.04, 0.88, row_provenance_summary_line, fontsize=10.4, va="top", wrap=True)
            ax.text(
                0.04,
                0.83,
                f"json={row_provenance_json} | csv={row_provenance_csv} | report={row_provenance_report}",
                fontsize=9.2,
                va="top",
                wrap=True,
            )
            y = 0.75
            for row in row_provenance_preview_rows:
                ax.text(
                    0.04,
                    y,
                    (
                        f"{row.get('combination_name', '')} | member={row.get('member_id', '')} | "
                        f"clause={row.get('clause_label', '')} | baseline={row.get('baseline_focus_member_id', '')}"
                    ),
                    fontsize=9.4,
                    va="top",
                    wrap=True,
                )
                y -= 0.06
                ax.text(
                    0.06,
                    y,
                    (
                        f"mode={row.get('bridge_row_provenance_mode_label', '') or 'n/a'} | "
                        f"clause={row.get('clause_provenance_summary_label', '')} | "
                        f"inventory={row.get('bridge_member_inventory_summary_label', '')}"
                    ),
                    fontsize=8.4,
                    va="top",
                    wrap=True,
                )
                y -= 0.05
                if y < 0.10:
                    _save_text_page(fig)
                    plt.close(fig)
                    fig = plt.figure(figsize=(11, 8.5))
                    ax = fig.add_subplot(111)
                    ax.axis("off")
                    ax.text(0.03, 0.96, "Appendix: MIDAS KDS Row Provenance Export", fontsize=18, weight="bold", va="top")
                    y = 0.90
            for row in row_provenance_clause_filter_rows:
                ax.text(
                    0.04,
                    y,
                    (
                        f"clause={row.get('clause_label', '')} | rows={row.get('row_count', '')} | "
                        f"members={row.get('member_count', '')} | combos={row.get('combination_count', '')} | "
                        f"top_member={row.get('top_member_id', '')} | top_dcr={row.get('top_dcr_label', '')}"
                    ),
                    fontsize=8.9,
                    va="top",
                    wrap=True,
                )
                y -= 0.05
                if y < 0.10:
                    _save_text_page(fig)
                    plt.close(fig)
                    fig = plt.figure(figsize=(11, 8.5))
                    ax = fig.add_subplot(111)
                    ax.axis("off")
                    ax.text(0.03, 0.96, "Appendix: MIDAS KDS Row Provenance Export", fontsize=18, weight="bold", va="top")
                    y = 0.90
            for row in row_provenance_member_filter_rows:
                ax.text(
                    0.04,
                    y,
                    (
                        f"member={row.get('member_id', '')} | baseline={row.get('baseline_focus_member_id', '')} | "
                        f"rows={row.get('row_count', '')} | clauses={row.get('clause_count', '')} | "
                        f"combos={row.get('combination_count', '')} | top_clause={row.get('top_clause_label', '')}"
                    ),
                    fontsize=8.9,
                    va="top",
                    wrap=True,
                )
                y -= 0.05
                if y < 0.10:
                    _save_text_page(fig)
                    plt.close(fig)
                    fig = plt.figure(figsize=(11, 8.5))
                    ax = fig.add_subplot(111)
                    ax.axis("off")
                    ax.text(0.03, 0.96, "Appendix: MIDAS KDS Row Provenance Export", fontsize=18, weight="bold", va="top")
                    y = 0.90
            for row in row_provenance_hazard_filter_rows:
                ax.text(
                    0.04,
                    y,
                    (
                        f"hazard={row.get('hazard_type', '')} | rows={row.get('row_count', '')} | "
                        f"members={row.get('member_count', '')} | clauses={row.get('clause_count', '')} | "
                        f"combos={row.get('combination_count', '')} | top_clause={row.get('top_clause_label', '')} | "
                        f"top_dcr={row.get('top_dcr_label', '')}"
                    ),
                    fontsize=8.9,
                    va="top",
                    wrap=True,
                )
                y -= 0.05
                if y < 0.10:
                    _save_text_page(fig)
                    plt.close(fig)
                    fig = plt.figure(figsize=(11, 8.5))
                    ax = fig.add_subplot(111)
                    ax.axis("off")
                    ax.text(0.03, 0.96, "Appendix: MIDAS KDS Row Provenance Export", fontsize=18, weight="bold", va="top")
                    y = 0.90
            for row in row_provenance_rule_family_filter_rows:
                ax.text(
                    0.04,
                    y,
                    (
                        f"rule_family={row.get('rule_family', '')} | rows={row.get('row_count', '')} | "
                        f"members={row.get('member_count', '')} | hazards={row.get('hazard_count', '')} | "
                        f"combos={row.get('combination_count', '')} | top_clause={row.get('top_clause_label', '')} | "
                        f"top_dcr={row.get('top_dcr_label', '')}"
                    ),
                    fontsize=8.9,
                    va="top",
                    wrap=True,
                )
                y -= 0.05
                if y < 0.10:
                    _save_text_page(fig)
                    plt.close(fig)
                    fig = plt.figure(figsize=(11, 8.5))
                    ax = fig.add_subplot(111)
                    ax.axis("off")
                    ax.text(0.03, 0.96, "Appendix: MIDAS KDS Row Provenance Export", fontsize=18, weight="bold", va="top")
                    y = 0.90
            _save_text_page(fig)
            plt.close(fig)
        if smoke_history_png.exists():
            fig = plt.figure(figsize=(11, 8.5))
            ax = fig.add_subplot(111)
            ax.axis("off")
            ax.set_title("Nightly Smoke Trend", fontsize=18, loc="left")
            img = plt.imread(str(smoke_history_png))
            ax.imshow(img)
            _save_image_page(fig)
            plt.close(fig)
        if smoke_recent_samples:
            fig = plt.figure(figsize=(11, 8.5))
            ax = fig.add_subplot(111)
            ax.axis("off")
            ax.text(0.03, 0.96, "Nightly Smoke Recent Samples", fontsize=18, weight="bold", va="top")
            y = 0.90
            for row in smoke_recent_samples:
                ax.text(
                    0.04,
                    y,
                    (
                        f"#{int(row.get('sample_index', 0))} {row.get('generated_at', '')} | "
                        f"pass={bool(row.get('contract_pass', False))} | trial_feasible={bool(row.get('trial_feasible', False))} | "
                        f"baseline_runtime={float(row.get('baseline_runtime_s', 0.0)):.4f}s | "
                        f"trial_runtime={float(row.get('trial_runtime_s', 0.0)):.4f}s | "
                        f"trial_max_dcr={float(row.get('trial_max_dcr', 0.0)):.4f} | "
                        f"action={row.get('trial_action_name', '')}"
                    ),
                    fontsize=9.5,
                    va="top",
                )
                y -= 0.065
                if y < 0.08:
                    _save_text_page(fig)
                    plt.close(fig)
                    fig = plt.figure(figsize=(11, 8.5))
                    ax = fig.add_subplot(111)
                    ax.axis("off")
                    ax.text(0.03, 0.96, "Nightly Smoke Recent Samples", fontsize=18, weight="bold", va="top")
                    y = 0.90
            _save_text_page(fig)
            plt.close(fig)
        if measured_chain_category_png.exists():
            fig = plt.figure(figsize=(11, 8.5))
            ax = fig.add_subplot(111)
            ax.axis("off")
            ax.set_title("Measured Chain Category Trend", fontsize=18, loc="left")
            img = plt.imread(str(measured_chain_category_png))
            ax.imshow(img)
            _save_image_page(fig)
            plt.close(fig)
    if promotion_hold_for_review:
        fig = plt.figure(figsize=(11, 8.5))
        ax = fig.add_subplot(111)
        ax.axis("off")
        ax.text(0.03, 0.96, "Active Promotion Hold", fontsize=18, weight="bold", va="top")
        ax.text(0.04, 0.86, f"Reason: {promotion_reason_code}", fontsize=11.0, va="top")
        ax.text(0.04, 0.80, f"Manifest: {hold_review_manifest or 'n/a'}", fontsize=10.0, va="top", wrap=True)
        ax.text(0.04, 0.74, f"Packet: {hold_review_packet_md or 'n/a'}", fontsize=10.0, va="top", wrap=True)
        ax.text(0.04, 0.68, f"Packet PDF: {hold_review_packet_pdf or 'n/a'}", fontsize=10.0, va="top", wrap=True)
        ax.text(0.04, 0.62, f"Ack: {hold_review_ack_json or 'n/a'}", fontsize=10.0, va="top", wrap=True)
        ax.text(
            0.04,
            0.58,
            "Release candidate remains on hold until the authority-routing hold review manifest is cleared by engineer review.",
            fontsize=10.2,
            va="top",
            wrap=True,
        )
        _save_text_page(fig)
        plt.close(fig)
        if case_onepage_appendix_html:
            fig = plt.figure(figsize=(11, 8.5))
            ax = fig.add_subplot(111)
            ax.axis("off")
            ax.text(0.03, 0.96, "External Benchmark Case Onepages", fontsize=18, weight="bold", va="top")
            ax.text(0.04, 0.88, f"case_onepage_count={int(summary.get('external_benchmark_case_onepage_count', 0))}", fontsize=10.0, va="top")
            ax.text(0.04, 0.82, f"index_md={artifacts.get('external_benchmark_case_onepage_index_md', '') or 'n/a'}", fontsize=9.0, va="top", wrap=True)
            ax.text(0.04, 0.77, f"index_html={artifacts.get('external_benchmark_case_onepage_index_html', '') or 'n/a'}", fontsize=9.0, va="top", wrap=True)
            ax.text(0.04, 0.72, f"index_pdf={artifacts.get('external_benchmark_case_onepage_index_pdf', '') or 'n/a'}", fontsize=9.0, va="top", wrap=True)
            ax.text(
                0.04,
                0.66,
                (
                    f"attestation_workflow=cases:{int(metrics.get('external_benchmark_case_attestation_case_count', 0))} | "
                    f"manifests:{int(metrics.get('external_benchmark_case_attestation_manifest_count', 0))} | "
                    f"templates:{int(metrics.get('external_benchmark_case_attestation_template_count', 0))} | "
                    f"receipts:{int(metrics.get('external_benchmark_case_attestation_receipt_count', 0))} | "
                    f"attested:{int(metrics.get('external_benchmark_case_attestation_attested_count', 0))}"
                ),
                fontsize=9.0,
                va="top",
                wrap=True,
            )
            ax.text(0.04, 0.60, "Shared native roundtrip appendix is linked from every case page.", fontsize=9.2, va="top", wrap=True)
            _save_text_page(fig)
            plt.close(fig)
        if holdout_buckets:
            fig = plt.figure(figsize=(11, 8.5))
            ax = fig.add_subplot(111)
            ax.axis("off")
            ax.text(0.03, 0.96, "Residual Holdout Boundary", fontsize=18, weight="bold", va="top")
            y = 0.90
            for row in holdout_buckets:
                ax.text(
                    0.04,
                    y,
                    f"{row.get('label', row.get('id', ''))} | owner={row.get('owner', '')} | share={int(row.get('relative_share_pct', 0))}% | "
                    f"project={_coverage_range_label(row.get('absolute_project_pct_range'))} | {row.get('scope', '')}",
                    fontsize=9.5,
                    va="top",
                )
                y -= 0.075
                if y < 0.08:
                    _save_text_page(fig)
                    plt.close(fig)
                    fig = plt.figure(figsize=(11, 8.5))
                    ax = fig.add_subplot(111)
                    ax.axis("off")
                    ax.text(0.03, 0.96, "Residual Holdout Boundary", fontsize=18, weight="bold", va="top")
                    y = 0.90
            _save_text_page(fig)
            plt.close(fig)
        if metrics.get("time_saving_focus"):
            fig = plt.figure(figsize=(11, 8.5))
            ax = fig.add_subplot(111)
            ax.axis("off")
            ax.text(0.03, 0.96, "Time-Saving Coverage", fontsize=18, weight="bold", va="top")
            ax.text(0.04, 0.86, f"Coverage target: {metrics.get('accelerated_coverage_target_pct_label', '')}", fontsize=11.0, va="top")
            ax.text(0.04, 0.80, f"Residual holdout: {metrics.get('residual_holdout_target_pct_label', '')}", fontsize=11.0, va="top")
            ax.text(0.04, 0.74, f"Estimated time saved: {metrics.get('estimated_time_saved_pct_label', '')}", fontsize=11.0, va="top")
            ax.text(0.04, 0.68, f"Measured chain wall-clock (comparable rolling): {metrics.get('measured_chain_rolling_total_minutes_mean', 0.0):.2f} min", fontsize=10.4, va="top")
            ax.text(0.04, 0.62, f"Rolling sample count: {int(metrics.get('measured_chain_rolling_sample_count', 0))}, range={metrics.get('measured_chain_rolling_total_minutes_range', ['n/a', 'n/a'])[0]}-{metrics.get('measured_chain_rolling_total_minutes_range', ['n/a', 'n/a'])[1]} min", fontsize=10.2, va="top")
            ax.text(0.04, 0.56, f"Measured chain wall-clock (current): {metrics.get('measured_chain_total_minutes', 0.0):.2f} min", fontsize=10.2, va="top")
            ax.text(0.04, 0.50, f"Comparable run mode: {metrics.get('measured_chain_rolling_selection_mode', '')}", fontsize=10.0, va="top")
            ax.text(0.04, 0.44, f"Empirical smoke runtime reduction: {metrics.get('empirical_smoke_runtime_saved_pct_label', '')}", fontsize=10.2, va="top")
            ax.text(0.04, 0.38, f"Basis: {metrics.get('estimated_time_saved_basis', '')}", fontsize=9.6, va="top", wrap=True)
            ax.text(0.04, 0.24, str(metrics.get("time_saving_focus", "")), fontsize=10.0, va="top", wrap=True)
            _save_text_page(fig)
            plt.close(fig)
        if holdout_detail_rows:
            fig = plt.figure(figsize=(11, 8.5))
            ax = fig.add_subplot(111)
            ax.axis("off")
            ax.text(0.03, 0.96, "Residual Holdout Review Table", fontsize=18, weight="bold", va="top")
            y = 0.90
            for row in holdout_detail_rows:
                ax.text(
                    0.04,
                    y,
                    f"{row.get('bucket_label', row.get('bucket_id', ''))} | {row.get('detail_axis', '')} | {row.get('detail_value', '')}",
                    fontsize=9.8,
                    va="top",
                )
                y -= 0.034
                ax.text(0.06, y, f"owner={row.get('owner', '')} | why={row.get('why', '')}", fontsize=8.8, va="top", wrap=True)
                y -= 0.05
                if y < 0.10:
                    _save_text_page(fig)
                    plt.close(fig)
                    fig = plt.figure(figsize=(11, 8.5))
                    ax = fig.add_subplot(111)
                    ax.axis("off")
                    ax.text(0.03, 0.96, "Residual Holdout Review Table", fontsize=18, weight="bold", va="top")
                    y = 0.90
            _save_text_page(fig)
            plt.close(fig)
        if holdout_matrix_rows:
            fig = plt.figure(figsize=(11, 8.5))
            ax = fig.add_subplot(111)
            ax.axis("off")
            ax.text(0.03, 0.96, "Residual Holdout Routing Matrix", fontsize=18, weight="bold", va="top")
            y = 0.90
            for row in holdout_matrix_rows:
                ax.text(
                    0.04,
                    y,
                    f"{row.get('bucket_label', '')} | track={row.get('authority_track', '')} | submodel={row.get('submodel_family', '')}",
                    fontsize=9.4,
                    va="top",
                )
                y -= 0.036
                ax.text(
                    0.06,
                    y,
                    f"review={row.get('review_story_zone', '')} | member={row.get('member_family', '')} | owner={row.get('owner', '')}",
                    fontsize=8.8,
                    va="top",
                    wrap=True,
                )
                y -= 0.036
                ax.text(0.06, y, f"why={row.get('why', '')}", fontsize=8.6, va="top", wrap=True)
                y -= 0.055
                if y < 0.10:
                    _save_text_page(fig)
                    plt.close(fig)
                    fig = plt.figure(figsize=(11, 8.5))
                    ax = fig.add_subplot(111)
                    ax.axis("off")
                    ax.text(0.03, 0.96, "Residual Holdout Routing Matrix", fontsize=18, weight="bold", va="top")
                    y = 0.90
            _save_text_page(fig)
            plt.close(fig)
        if authority_catalog_warning_active:
            fig = plt.figure(figsize=(11, 8.5))
            ax = fig.add_subplot(111)
            ax.axis("off")
            ax.text(0.03, 0.96, "Active Warnings", fontsize=18, weight="bold", va="top")
            ax.text(
                0.04,
                0.86,
                (
                    f"Authority routing change detected | changes={int(summary.get('authority_catalog_diff_change_count', 0))} | "
                    f"added={int(summary.get('authority_catalog_diff_added_count', 0))} | "
                    f"removed={int(summary.get('authority_catalog_diff_removed_count', 0))}"
                ),
                fontsize=10.5,
                va="top",
            )
            ax.text(
                0.04,
                0.76,
                "Authority/submodel routing changed since the previous committee snapshot and should be explicitly reviewed before release promotion or authority-facing reuse.",
                fontsize=10.0,
                va="top",
                wrap=True,
            )
            _save_text_page(fig)
            plt.close(fig)
        fig = plt.figure(figsize=(11, 8.5))
        ax = fig.add_subplot(111)
        ax.axis("off")
        ax.text(0.03, 0.96, "Authority Catalog Routing Diff", fontsize=18, weight="bold", va="top")
        ax.text(
            0.04,
            0.88,
            (
                f"baseline_seeded={bool(authority_catalog_diff.get('baseline_seeded', False))} | "
                f"changes={int(authority_catalog_diff.get('change_count', 0))} | "
                f"added={int(authority_catalog_diff.get('added_count', 0))} | "
                f"removed={int(authority_catalog_diff.get('removed_count', 0))} | "
                f"unchanged={int(authority_catalog_diff.get('unchanged_count', 0))}"
            ),
            fontsize=10.0,
            va="top",
        )
        y = 0.80
        diff_rows = [row for row in (authority_catalog_diff.get("diff_rows") or []) if isinstance(row, dict)]
        if not diff_rows:
            ax.text(0.04, y, "No authority-catalog routing changes detected for this external submission refresh.", fontsize=10.0, va="top")
        for row in diff_rows:
            ax.text(0.04, y, f"{row.get('change_type', '')} | {row.get('authority_track', '')} / {row.get('submodel_family', '')}", fontsize=9.6, va="top")
            y -= 0.034
            ax.text(0.06, y, f"review={row.get('review_story_zone', '')} | member={row.get('member_family', '')} | owner={row.get('owner', '')}", fontsize=8.7, va="top", wrap=True)
            y -= 0.034
            ax.text(0.06, y, f"why={row.get('why', '')}", fontsize=8.5, va="top", wrap=True)
            y -= 0.05
            if y < 0.10:
                _save_text_page(fig)
                plt.close(fig)
                fig = plt.figure(figsize=(11, 8.5))
                ax = fig.add_subplot(111)
                ax.axis("off")
                ax.text(0.03, 0.96, "Authority Catalog Routing Diff", fontsize=18, weight="bold", va="top")
                y = 0.88
        _save_text_page(fig)
        plt.close(fig)


def _copy_artifacts(base_dir: Path, artifacts: list[str]) -> None:
    art_root = base_dir / "artifacts"
    repo_root = Path.cwd().resolve()
    for rel in artifacts:
        src = Path(rel)
        if not src.exists():
            raise SystemExit(f"missing artifact: {src}")
        if src.is_absolute():
            try:
                rel_path = src.resolve().relative_to(repo_root)
            except Exception:
                rel_path = Path("absolute_artifacts") / src.name
        else:
            rel_path = Path(rel)
        dst = art_root / rel_path
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def _zip_dir(base_dir: Path, zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(base_dir.rglob("*")):
            arcname = base_dir.name / path.relative_to(base_dir)
            zf.write(path, arcname=str(arcname))


def _prune_old(release_dir: Path, keep_name: str, prefix: str) -> list[str]:
    removed: list[str] = []
    for path in sorted(release_dir.glob(f"{prefix}*")):
        if path.name == keep_name or path.name == f"{keep_name}.zip":
            continue
        if path.is_dir():
            shutil.rmtree(path)
            removed.append(str(path))
        elif path.is_file():
            path.unlink()
            removed.append(str(path))
    return removed


def _build_bundle(
    *,
    release_dir: Path,
    bundle_name: str,
    artifacts: list[str],
    summary: dict,
    prune_old: bool,
    prune_prefix: str,
) -> tuple[Path, Path, Path, Path, Path, Path, list[str]]:
    bundle_dir = release_dir / bundle_name
    bundle_zip = release_dir / f"{bundle_name}.zip"
    bundle_summary = _scrub_external_bundle_summary(summary)
    bundle_artifacts = _scrub_external_bundle_artifact_list(artifacts)
    if bundle_dir.exists():
        shutil.rmtree(bundle_dir)
    if bundle_zip.exists():
        bundle_zip.unlink()
    bundle_dir.mkdir(parents=True, exist_ok=True)

    summary_json = bundle_dir / "external_validation_onepage.json"
    summary_md = bundle_dir / "external_validation_onepage.md"
    summary_html = bundle_dir / "external_validation_onepage.html"
    summary_pdf = bundle_dir / "external_validation_onepage.pdf"
    _copy_artifacts(bundle_dir, bundle_artifacts)

    readme = bundle_dir / "README.txt"
    readme.write_text(
        "\n".join(
            [
                "External validation submission bundle",
                f"Generated: {bundle_summary['generated_at']}",
                f"Bundle variant: {bundle_name}",
                "",
                "Contents",
                "- external_validation_onepage.{json,md,html,pdf}",
                "- external_benchmark_case_onepages/{index,case}.{md,html,pdf}",
                "- validation and release reports",
                "- signed release registry + public key + detached signature",
                "- selected solver/parser/committee artifacts for external review",
                "",
                "Notes",
                "- This bundle supersedes previous bundles of the same variant.",
                "- MIDAS parser contract records element_rows_skipped=0.",
                "- NDTHA residual gate records hard-threshold residual trace status.",
                "- Each external-benchmark case onepage begins with a reviewer / authority cover sheet auto-generated from the execution status manifest and KPI receipt.",
                "- Each external-benchmark case onepage now carries bundle-local attestation template/receipt sidecars and reads a real case manifest when one exists.",
                "- Each external-benchmark case onepage links back to the shared native MIDAS roundtrip appendix.",
                "- release_registry.json is signed with Ed25519.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    summary_artifacts = bundle_summary.get("artifacts") if isinstance(bundle_summary.get("artifacts"), dict) else {}
    _write_external_benchmark_case_onepages(bundle_dir, bundle_summary, summary_artifacts)

    # Write one-page artifacts after bundle copy/readme so the latest pointer
    # always targets files that exist in the bundle root.
    summary_json.write_text(json.dumps(bundle_summary, indent=2), encoding="utf-8")
    _write_summary_markdown(summary_md, bundle_summary)
    _write_summary_html(summary_html, bundle_summary)
    _write_summary_pdf(summary_pdf, bundle_summary)

    _zip_dir(bundle_dir, bundle_zip)
    removed = _prune_old(release_dir, bundle_name, prune_prefix) if prune_old else []
    return bundle_dir, bundle_zip, summary_json, summary_md, summary_html, summary_pdf, removed


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--release-dir", default="implementation/phase1/release")
    p.add_argument("--bundle-id", default="")
    p.add_argument("--latest-pointer", default="implementation/phase1/release/external_validation_latest.json")
    p.add_argument("--light-latest-pointer", default="implementation/phase1/release/external_validation_light_latest.json")
    p.add_argument(
        "--external-benchmark-submission-readiness-report",
        default="implementation/phase1/release/external_benchmark_submission_readiness.json",
    )
    p.add_argument(
        "--external-benchmark-execution-manifest-report",
        default="implementation/phase1/release/external_benchmark_kickoff/external_benchmark_execution_manifest.json",
    )
    p.add_argument(
        "--external-benchmark-execution-status-manifest-report",
        default="implementation/phase1/release/external_benchmark_kickoff/external_benchmark_execution_status_manifest.json",
    )
    p.add_argument(
        "--irregular-structure-gate-report",
        default="implementation/phase1/irregular_structure_collection_gate_report.json",
    )
    p.add_argument(
        "--irregular-structure-source-catalog",
        default="implementation/phase1/open_data/irregular/irregular_structure_source_catalog.json",
    )
    p.add_argument(
        "--irregular-structure-triage-report",
        default="implementation/phase1/open_data/irregular/irregular_structure_triage_report.json",
    )
    p.add_argument(
        "--irregular-structure-collection-report",
        default="implementation/phase1/open_data/irregular/irregular_structure_collection_report.json",
    )
    p.add_argument(
        "--irregular-top5-execution-manifest",
        default="implementation/phase1/open_data/irregular/irregular_top5_execution_manifest.json",
    )
    p.add_argument(
        "--irregular-benchmark-execution-manifest",
        default="implementation/phase1/release/external_benchmark_kickoff/irregular_benchmark_execution_manifest.json",
    )
    p.add_argument(
        "--korean-source-ingest-gate-report",
        default="implementation/phase1/korean_source_ingest_gate_report.json",
    )
    p.add_argument(
        "--korean-structural-preview-promotion-queue",
        default="implementation/phase1/release/midas_native_roundtrip/exact_topology_structural_preview_promotion_queue.json",
    )
    p.add_argument("--emit-lightweight", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--prune-old", action=argparse.BooleanOptionalAction, default=True)
    args = p.parse_args()

    release_dir = Path(args.release_dir)
    release_dir.mkdir(parents=True, exist_ok=True)
    bundle_id = str(args.bundle_id).strip() or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    bundle_name = f"external_validation_submission_{bundle_id}"
    light_bundle_name = f"external_validation_light_submission_{bundle_id}"

    nightly = _load_json(Path("implementation/phase1/release/nightly_release_gate_report.json"))
    ci = _load_json(Path("implementation/phase1/ci_gate_report.json"))
    static = _load_json(Path("implementation/phase1/static_artifact_validation_report.json"))
    freeze = _load_json(Path("implementation/phase1/release/freeze_release_report.json"))
    promotion = _load_json(Path("implementation/phase1/release/release_candidate_promotion_report.json"))
    registry = _load_json(Path("implementation/phase1/release/release_registry.json"))
    gap = _load_json(Path("implementation/phase1/release/release_gap_report.json"))
    kds = _load_json(Path("implementation/phase1/release/kds_compliance/kds_compliance_summary.json"))
    midas = _load_json(Path("implementation/phase1/midas_mgt_conversion_report.json"))
    solver = _load_json(Path("implementation/phase1/solver_hip_e2e_contract_report.json"))
    rc = _load_json(Path("implementation/phase1/rc_benchmark_lock_report.json"))
    ndtha_residual = _load_json(Path("implementation/phase1/ndtha_residual_gate_report.json"))
    midas_native_roundtrip_report = (
        ci.get("midas_native_roundtrip_report")
        if isinstance(ci.get("midas_native_roundtrip_report"), dict)
        else {}
    )
    midas_native_roundtrip_report_summary = (
        midas_native_roundtrip_report.get("summary")
        if isinstance(midas_native_roundtrip_report.get("summary"), dict)
        else {}
    )
    midas_native_roundtrip_receipts_report = _load_json(
        Path("implementation/phase1/release/midas_native_roundtrip/midas_native_writeback_diff_receipts_report.json")
    )
    midas_native_roundtrip_corpus_manifest = _load_json(
        Path("implementation/phase1/open_data/midas/midas_native_corpus_manifest.json")
    )
    midas_native_roundtrip_receipts_summary = (
        midas_native_roundtrip_receipts_report.get("summary")
        if isinstance(midas_native_roundtrip_receipts_report.get("summary"), dict)
        else {}
    )
    committee = _load_json(Path("implementation/phase1/release/committee_review/committee_review_package_report.json"))
    committee_summary = _load_json(Path("implementation/phase1/release/committee_review/committee_summary.json"))
    frame = _load_json(Path("implementation/phase1/nonlinear_frame_engine_report.json"))
    wind = _load_json(Path("implementation/phase1/wind_time_history_gate_report.json"))
    ssi = _load_json(Path("implementation/phase1/ssi_boundary_gate_report.json"))
    global_authority = _load_json(Path("implementation/phase1/global_authority_gate_report.json"))
    pbd = _load_json(Path("implementation/phase1/release/pbd_review/pbd_review_package_report.json"))
    pbd_inputs = pbd.get("inputs") if isinstance(pbd.get("inputs"), dict) else {}
    pbd_summary = pbd.get("summary") if isinstance(pbd.get("summary"), dict) else {}
    external_benchmark_submission_readiness = _load_json(
        Path(args.external_benchmark_submission_readiness_report)
    )
    external_benchmark_submission_summary = (
        external_benchmark_submission_readiness.get("summary")
        if isinstance(external_benchmark_submission_readiness.get("summary"), dict)
        else {}
    )
    external_benchmark_execution_manifest = _load_json(
        Path(args.external_benchmark_execution_manifest_report)
    )
    external_benchmark_execution_summary = (
        external_benchmark_execution_manifest.get("summary")
        if isinstance(external_benchmark_execution_manifest.get("summary"), dict)
        else {}
    )
    external_benchmark_execution_review_boundary_preview = (
        external_benchmark_execution_manifest.get("review_boundary_preview")
        if isinstance(external_benchmark_execution_manifest.get("review_boundary_preview"), dict)
        else {}
    )
    external_benchmark_execution_status_manifest = _load_json(
        Path(args.external_benchmark_execution_status_manifest_report)
    )
    external_benchmark_execution_status_summary = (
        external_benchmark_execution_status_manifest.get("summary")
        if isinstance(external_benchmark_execution_status_manifest.get("summary"), dict)
        else {}
    )
    irregular_structure_gate_report = _load_optional_json(Path(args.irregular_structure_gate_report))
    irregular_structure_gate_summary = (
        irregular_structure_gate_report.get("summary")
        if isinstance(irregular_structure_gate_report.get("summary"), dict)
        else {}
    )
    irregular_structure_source_catalog = _load_optional_json(Path(args.irregular_structure_source_catalog))
    irregular_structure_source_catalog_summary = (
        irregular_structure_source_catalog.get("summary")
        if isinstance(irregular_structure_source_catalog.get("summary"), dict)
        else {}
    )
    irregular_structure_triage_report = _load_optional_json(Path(args.irregular_structure_triage_report))
    irregular_structure_triage_summary = (
        irregular_structure_triage_report.get("summary")
        if isinstance(irregular_structure_triage_report.get("summary"), dict)
        else {}
    )
    irregular_structure_collection_report = _load_optional_json(Path(args.irregular_structure_collection_report))
    irregular_structure_collection_summary = (
        irregular_structure_collection_report.get("summary")
        if isinstance(irregular_structure_collection_report.get("summary"), dict)
        else {}
    )
    irregular_top5_execution_manifest = _load_optional_json(Path(args.irregular_top5_execution_manifest))
    irregular_top5_summary = (
        irregular_top5_execution_manifest.get("summary")
        if isinstance(irregular_top5_execution_manifest.get("summary"), dict)
        else {}
    )
    irregular_canonical_promotion_queue_rows = _build_irregular_canonical_promotion_queue_rows(
        irregular_structure_source_catalog,
        [
            str(item)
            for item in (
                (irregular_top5_execution_manifest.get("summary") or {}).get("top5_family_ids", [])
                if isinstance(irregular_top5_execution_manifest.get("summary"), dict)
                else []
            )
            if str(item).strip()
        ]
        or [
            str(item.get("family_id", "") or "").strip()
            for item in (irregular_top5_execution_manifest.get("top5_families") or [])
            if isinstance(item, dict) and str(item.get("family_id", "") or "").strip()
        ],
    )
    irregular_top5_families = [
        row for row in (irregular_top5_execution_manifest.get("top5_families") or []) if isinstance(row, dict)
    ]
    irregular_benchmark_execution_manifest = _load_optional_json(Path(args.irregular_benchmark_execution_manifest))
    irregular_benchmark_execution_summary = (
        irregular_benchmark_execution_manifest.get("summary")
        if isinstance(irregular_benchmark_execution_manifest.get("summary"), dict)
        else {}
    )
    irregular_benchmark_execution_artifacts = (
        irregular_benchmark_execution_manifest.get("artifacts")
        if isinstance(irregular_benchmark_execution_manifest.get("artifacts"), dict)
        else {}
    )
    irregular_benchmark_execution_ready_tasks = [
        row for row in (irregular_benchmark_execution_manifest.get("ready_tasks") or []) if isinstance(row, dict)
    ]
    irregular_benchmark_execution_blocked_tasks = [
        row for row in (irregular_benchmark_execution_manifest.get("blocked_tasks") or []) if isinstance(row, dict)
    ]
    irregular_benchmark_receipt_rows = _irregular_benchmark_case_receipt_rows(
        {
            "irregular_benchmark_execution_ready_tasks": irregular_benchmark_execution_ready_tasks,
            "irregular_benchmark_execution_blocked_tasks": irregular_benchmark_execution_blocked_tasks,
        }
    )
    irregular_benchmark_receipt_index_json = str(
        irregular_benchmark_execution_artifacts.get("receipt_index_json", "") or ""
    ).strip()
    korean_source_ingest_gate_report = _load_optional_json(Path(args.korean_source_ingest_gate_report))
    korean_source_ingest_summary = (
        korean_source_ingest_gate_report.get("summary")
        if isinstance(korean_source_ingest_gate_report.get("summary"), dict)
        else {}
    )
    korean_source_ingest_summary_line = str(
        korean_source_ingest_gate_report.get("summary_line", "")
        or korean_source_ingest_summary.get("ingest_summary_line", "")
        or (
            f"Korean source ingest: {'PASS' if bool(korean_source_ingest_gate_report.get('contract_pass', False)) else 'CHECK'} | "
            f"sources={int(korean_source_ingest_summary.get('source_count', 0) or 0)} | "
            f"classes={int(korean_source_ingest_summary.get('source_class_count', 0) or 0)} | "
            f"collected={int(korean_source_ingest_summary.get('collected_count', 0) or 0)} | "
            f"fingerprinted={int(korean_source_ingest_summary.get('fingerprinted_count', 0) or 0)} | "
            f"metadata_only={int(korean_source_ingest_summary.get('metadata_only_remote_candidate_count', 0) or 0)} | "
            f"rejected={int(korean_source_ingest_summary.get('rejected_count', 0) or 0)} | "
            f"duplicate_sha_groups={int(korean_source_ingest_summary.get('duplicate_sha_group_count', 0) or 0)}"
        )
    ).strip()
    korean_source_ingest_summary_line = _compact_korean_source_ingest_summary_line(korean_source_ingest_summary_line)
    opensees_canonical_breadth_report = _load_optional_json(
        REPO_ROOT / "implementation/phase1/release/benchmark_expansion/opensees_canonical_breadth_report.json"
    )
    opensees_canonical_breadth_summary_line = str(
        opensees_canonical_breadth_report.get("summary_line", "") or "n/a"
    ).strip()
    measured_benchmark_breadth_report = _load_optional_json(
        REPO_ROOT / "implementation/phase1/release/benchmark_expansion/measured_benchmark_breadth_report.json"
    )
    measured_benchmark_breadth_summary_line = str(
        measured_benchmark_breadth_report.get("summary_line", "") or "n/a"
    ).strip()
    korean_structural_preview_promotion_queue = _load_optional_json(
        Path(args.korean_structural_preview_promotion_queue)
    )
    korean_structural_preview_queue_summary = (
        korean_structural_preview_promotion_queue.get("summary")
        if isinstance(korean_structural_preview_promotion_queue.get("summary"), dict)
        else {}
    )
    korean_structural_preview_queue_summary_line = str(
        korean_structural_preview_promotion_queue.get("summary_line", "")
        or (
            f"Korean structural preview queue: {'PASS' if bool(korean_structural_preview_promotion_queue) else 'CHECK'} | "
            f"candidates={int(korean_structural_preview_queue_summary.get('candidate_total', 0) or 0)} | "
            f"pending={int(korean_structural_preview_queue_summary.get('pending_candidate_count', 0) or 0)} | "
            f"state={str(korean_structural_preview_queue_summary.get('state', '') or '').strip() or 'missing'}"
        )
    ).strip()
    korean_structural_preview_queue_summary_line = _compact_korean_structural_preview_queue_summary_line(
        korean_structural_preview_queue_summary_line
    )
    external_benchmark_kickoff_dir = Path(args.external_benchmark_execution_manifest_report).parent
    audit_review_decision_batch_template_json = external_benchmark_kickoff_dir / "audit_review_decision_batch_template.json"
    audit_review_decision_batch_template = _load_json(audit_review_decision_batch_template_json)
    audit_review_decision_batch_template_summary = (
        audit_review_decision_batch_template.get("summary")
        if isinstance(audit_review_decision_batch_template.get("summary"), dict)
        else {}
    )
    audit_review_decision_batch_approve_all_attested_example_json = (
        external_benchmark_kickoff_dir / "audit_review_decision_batch_approve_all.attested_example.json"
    )
    audit_review_decision_batch_approve_all_attested_example = _load_json(
        audit_review_decision_batch_approve_all_attested_example_json
    )
    audit_review_decision_batch_approve_all_attested_example_summary = (
        audit_review_decision_batch_approve_all_attested_example.get("summary")
        if isinstance(audit_review_decision_batch_approve_all_attested_example.get("summary"), dict)
        else {}
    )
    audit_review_decision_batch_mixed_attested_example_json = (
        external_benchmark_kickoff_dir / "audit_review_decision_batch_mixed.attested_example.json"
    )
    audit_review_decision_batch_mixed_attested_example = _load_json(
        audit_review_decision_batch_mixed_attested_example_json
    )
    audit_review_decision_batch_mixed_attested_example_summary = (
        audit_review_decision_batch_mixed_attested_example.get("summary")
        if isinstance(audit_review_decision_batch_mixed_attested_example.get("summary"), dict)
        else {}
    )
    external_benchmark_submission_preview_approve_all_json = (
        external_benchmark_kickoff_dir / "external_benchmark_submission_readiness_preview.approve_all.json"
    )
    external_benchmark_submission_preview_approve_all = _load_json(
        external_benchmark_submission_preview_approve_all_json
    )
    external_benchmark_submission_preview_approve_all_readiness_summary = (
        external_benchmark_submission_preview_approve_all.get("readiness_preview", {}).get("summary")
        if isinstance(external_benchmark_submission_preview_approve_all.get("readiness_preview"), dict)
        and isinstance(external_benchmark_submission_preview_approve_all.get("readiness_preview", {}).get("summary"), dict)
        else {}
    )
    external_benchmark_submission_preview_reject_one_json = (
        external_benchmark_kickoff_dir / "external_benchmark_submission_readiness_preview.reject_one.json"
    )
    external_benchmark_submission_preview_reject_one = _load_json(
        external_benchmark_submission_preview_reject_one_json
    )
    external_benchmark_submission_preview_reject_one_readiness_summary = (
        external_benchmark_submission_preview_reject_one.get("readiness_preview", {}).get("summary")
        if isinstance(external_benchmark_submission_preview_reject_one.get("readiness_preview"), dict)
        and isinstance(external_benchmark_submission_preview_reject_one.get("readiness_preview", {}).get("summary"), dict)
        else {}
    )
    audit_review_decision_batch_run_report_json = (
        external_benchmark_kickoff_dir / "audit_review_decision_batch_run_report.json"
    )
    audit_review_decision_batch_run_report = _load_json(audit_review_decision_batch_run_report_json)
    audit_review_decision_batch_approve_all_live_ready_template_json = (
        external_benchmark_kickoff_dir / "audit_review_decision_batch_approve_all.live_ready_template.json"
    )
    audit_review_decision_batch_live_preview_json = (
        external_benchmark_kickoff_dir / "audit_review_decision_batch.live_preview.json"
    )
    audit_review_decision_batch_live_preview = _load_json(
        audit_review_decision_batch_live_preview_json
    )
    design_opt_reports = load_design_opt_reports()
    design_opt_entrypoint_rows = entrypoint_status_rows(design_opt_reports)
    design_opt_entrypoint_groups = entrypoint_group_rows(design_opt_entrypoint_rows)
    design_opt_long = design_opt_reports.get("solver_loop_long") or _load_json(Path(SOLVER_LOOP_LONG_REPORT_JSON))
    design_opt_budgeted = design_opt_reports.get("budgeted") or _load_json(Path(BUDGETED_REPORT_JSON))
    design_opt_ablation = design_opt_reports.get("ablation") or _load_json(Path(ABLATION_REPORT_JSON))
    design_opt_profile = design_opt_reports.get("objective_profile") or _load_json(Path(OBJECTIVE_PROFILE_REPORT_JSON))
    design_opt_cost = design_opt_reports.get("cost_reduction") or _load_json(Path(COST_REDUCTION_REPORT_JSON))
    design_opt_long_summary = design_opt_long.get("summary") or {}
    design_opt_cost_summary = design_opt_cost.get("summary") or {}
    design_opt_raw_max_drift = _safe_float(design_opt_cost_summary.get("raw_max_drift_pct", design_opt_long_summary.get("raw_max_drift_pct", 0.0)))
    design_opt_raw_residual_drift = _safe_float(design_opt_cost_summary.get("raw_residual_drift_pct", design_opt_long_summary.get("raw_residual_drift_pct", 0.0)))
    design_opt_raw_max_dcr = _safe_float(design_opt_cost_summary.get("raw_max_dcr", design_opt_long_summary.get("raw_max_dcr", 0.0)))
    design_opt_repaired_max_drift = _safe_float(
        design_opt_cost_summary.get(
            "repaired_final_max_drift_pct",
            design_opt_long_summary.get("repaired_max_drift_pct", design_opt_long_summary.get("final_max_drift_pct", 0.0)),
        )
    )
    design_opt_repaired_residual_drift = _safe_float(
        design_opt_cost_summary.get(
            "repaired_final_residual_drift_pct",
            design_opt_long_summary.get("repaired_residual_drift_pct", design_opt_long_summary.get("final_residual_drift_pct", 0.0)),
        )
    )
    design_opt_repaired_max_dcr = _safe_float(
        design_opt_cost_summary.get(
            "repaired_final_max_dcr",
            design_opt_long_summary.get("repaired_max_dcr", design_opt_long_summary.get("final_max_dcr", 0.0)),
        )
    )
    design_opt_compliance_basis = str(design_opt_cost_summary.get("compliance_basis", design_opt_long_summary.get("compliance_basis", "repaired_solver_validated_slice")))
    design_opt_repair_action_count = int(design_opt_cost_summary.get("repair_action_count", design_opt_long_summary.get("repair_action_count", 0)))
    design_opt_constructability_signal_gain_pct = _safe_float(
        design_opt_cost_summary.get("constructability_signal_gain_pct", design_opt_long_summary.get("constructability_signal_gain_pct", 0.0))
    )
    design_opt_baseline_constructability_avg = _safe_float(
        design_opt_cost_summary.get("baseline_constructability_avg", 0.0)
    )
    design_opt_final_constructability_avg = _safe_float(
        design_opt_cost_summary.get("final_constructability_avg", 0.0)
    )
    design_opt_baseline_detailing_complexity_avg = _safe_float(
        design_opt_cost_summary.get("baseline_detailing_complexity_avg", 0.0)
    )
    design_opt_final_detailing_complexity_avg = _safe_float(
        design_opt_cost_summary.get("final_detailing_complexity_avg", 0.0)
    )
    design_opt_selected_action_family_counts = {
        str(k): int(v)
        for k, v in sorted((design_opt_cost_summary.get("accepted_action_family_counts") or {}).items())
    }
    design_opt_preview_supply_family_counts = {
        str(k): int(v)
        for k, v in sorted((design_opt_cost_summary.get("preview_supply_family_counts") or {}).items())
    }
    design_opt_preview_supply_family_mix_label = ", ".join(
        f"{family}={count}" for family, count in design_opt_preview_supply_family_counts.items()
    )
    design_opt_preview_missing_target_families = [
        family
        for family in ("beam_section", "wall_thickness", "connection_detailing", "detailing")
        if int(design_opt_preview_supply_family_counts.get(family, 0)) <= 0
    ]
    design_opt_preview_missing_target_families_label = ", ".join(design_opt_preview_missing_target_families)
    design_opt_previous_action_family_counts = {
        str(k): int(v)
        for k, v in sorted((design_opt_cost_summary.get("previous_accepted_action_family_counts") or {}).items())
    }
    design_opt_selected_family_mix_label = ", ".join(
        f"{family}={count}" for family, count in design_opt_selected_action_family_counts.items()
    )
    design_opt_selected_family_trend_label = str(design_opt_cost_summary.get("selected_action_family_trend_label", ""))
    design_opt_selected_family_total = int(sum(design_opt_selected_action_family_counts.values()))
    if design_opt_selected_action_family_counts:
        design_opt_selected_dominant_family, design_opt_selected_dominant_count = max(
            design_opt_selected_action_family_counts.items(),
            key=lambda item: (int(item[1]), str(item[0])),
        )
        design_opt_selected_dominant_family_ratio = (
            float(design_opt_selected_dominant_count) / max(float(design_opt_selected_family_total), 1.0)
        )
    else:
        design_opt_selected_dominant_family = ""
        design_opt_selected_dominant_family_ratio = 0.0
    design_opt_previous_dominant_family = str(design_opt_cost_summary.get("previous_selected_dominant_family", ""))
    design_opt_previous_dominant_family_ratio = _safe_float(design_opt_cost_summary.get("previous_selected_dominant_family_ratio", 0.0))
    nightly_smoke = nightly.get("design_optimization_cost_reduction_smoke") if isinstance(nightly.get("design_optimization_cost_reduction_smoke"), dict) else {}
    nightly_smoke_history = nightly.get("design_optimization_cost_reduction_smoke_history") if isinstance(nightly.get("design_optimization_cost_reduction_smoke_history"), dict) else {}
    nightly_smoke_history_summary = nightly_smoke_history.get("summary") if isinstance(nightly_smoke_history.get("summary"), dict) else {}
    nightly_smoke_recommendation = nightly.get("design_optimization_cost_reduction_smoke_strict_recommendation") if isinstance(nightly.get("design_optimization_cost_reduction_smoke_strict_recommendation"), dict) else {}
    gap_artifacts = gap.get("artifacts") if isinstance(gap.get("artifacts"), dict) else {}
    smoke_history_png = str(gap_artifacts.get("smoke_history_png", "") or "")
    measured_chain_category_png = str(gap_artifacts.get("measured_chain_category_png", "") or "")
    smoke_recent_samples = [row for row in (gap.get("nightly_smoke_recent_samples") or []) if isinstance(row, dict)]
    smoke_trend = gap.get("nightly_smoke_trend") if isinstance(gap.get("nightly_smoke_trend"), dict) else {}
    gap_summary = gap.get("summary") if isinstance(gap.get("summary"), dict) else {}
    residual_holdout_buckets = [row for row in (gap.get("residual_holdout_buckets") or []) if isinstance(row, dict)]
    residual_holdout_detail_rows = [row for row in (committee_summary.get("residual_holdout_detail_rows") or []) if isinstance(row, dict)]
    residual_holdout_matrix_rows = [row for row in (committee_summary.get("residual_holdout_matrix_rows") or []) if isinstance(row, dict)]
    authority_catalog_routing_diff = committee_summary.get("authority_catalog_routing_diff") if isinstance(committee_summary.get("authority_catalog_routing_diff"), dict) else {}
    committee_artifact_links = (
        committee_summary.get("artifact_links")
        if isinstance(committee_summary.get("artifact_links"), dict)
        else committee.get("artifacts")
        if isinstance(committee.get("artifacts"), dict)
        else committee.get("artifact_links")
        if isinstance(committee.get("artifact_links"), dict)
        else {}
    )
    authority_catalog_routing_diff_json = str(committee_artifact_links.get("authority_catalog_routing_diff_json", "") or "")
    structural_optimization_viewer_html = str(committee_artifact_links.get("structural_optimization_viewer_html", "") or "")
    structural_optimization_viewer_json = str(committee_artifact_links.get("structural_optimization_viewer_json", "") or "")
    optimized_drawing_review_html = str(committee_artifact_links.get("optimized_drawing_review_html", "") or "")
    optimized_drawing_review_summary_json = str(committee_artifact_links.get("optimized_drawing_review_summary_json", "") or "")
    structural_optimization_viewer = _load_json(Path(structural_optimization_viewer_json)) if structural_optimization_viewer_json else {}
    optimized_drawing_review_summary = _load_json(Path(optimized_drawing_review_summary_json)) if optimized_drawing_review_summary_json else {}
    structural_optimization_viewer_story_zone_map = (
        structural_optimization_viewer.get("story_zone_map")
        if isinstance(structural_optimization_viewer.get("story_zone_map"), dict)
        else {}
    )
    promotion_reason_code = str(promotion.get("reason_code", ""))
    promotion_hold_for_review = promotion_reason_code == "HOLD_FOR_REVIEW"
    hold_review_manifest = str(promotion.get("hold_review_manifest", "") or "")
    hold_review_packet_md = str(promotion.get("hold_review_packet_md", "") or "")
    hold_review_packet_pdf = str(promotion.get("hold_review_packet_pdf", "") or "")
    hold_review_ack_json = str(promotion.get("hold_review_ack_json", "") or "")
    midas_section_library_summary_line = str(
        ci.get(
            "midas_section_library_summary_line",
            gap_summary.get(
                "midas_section_library_summary_line",
                committee_summary.get("midas_section_library_summary_line", ""),
            ),
        )
        or ""
    ).strip()
    material_constitutive_summary_line = str(
        ci.get(
            "material_constitutive_summary_line",
            gap_summary.get(
                "material_constitutive_summary_line",
                committee_summary.get("material_constitutive_summary_line", ""),
            ),
        )
        or ""
    ).strip()
    surface_interaction_benchmark_summary_line = str(
        ci.get(
            "surface_interaction_benchmark_summary_line",
            gap_summary.get(
                "surface_interaction_benchmark_summary_line",
                committee_summary.get("surface_interaction_benchmark_summary_line", ""),
            ),
        )
        or ""
    ).strip()
    midas_kds_row_provenance_export_summary_line = str(
        ci.get(
            "midas_kds_row_provenance_export_summary_line",
            gap_summary.get(
                "midas_kds_row_provenance_export_summary_line",
                committee_summary.get("midas_kds_row_provenance_export_summary_line", ""),
            ),
        )
        or ""
    ).strip()
    midas_kds_row_provenance_preview_rows = [
        row
        for row in (
            committee_summary.get("midas_kds_row_provenance_preview_rows")
            or committee_summary.get("metrics", {}).get("midas_kds_row_provenance_preview_rows")
            or []
        )
        if isinstance(row, dict)
    ]
    midas_kds_row_provenance_clause_filter_rows = [
        row
        for row in (
            committee_summary.get("midas_kds_row_provenance_clause_filter_rows")
            or committee_summary.get("metrics", {}).get("midas_kds_row_provenance_clause_filter_rows")
            or []
        )
        if isinstance(row, dict)
    ]
    midas_kds_row_provenance_member_filter_rows = [
        row
        for row in (
            committee_summary.get("midas_kds_row_provenance_member_filter_rows")
            or committee_summary.get("metrics", {}).get("midas_kds_row_provenance_member_filter_rows")
            or []
        )
        if isinstance(row, dict)
    ]
    midas_kds_row_provenance_hazard_filter_rows = [
        row
        for row in (
            committee_summary.get("midas_kds_row_provenance_hazard_filter_rows")
            or committee_summary.get("metrics", {}).get("midas_kds_row_provenance_hazard_filter_rows")
            or []
        )
        if isinstance(row, dict)
    ]
    midas_kds_row_provenance_rule_family_filter_rows = [
        row
        for row in (
            committee_summary.get("midas_kds_row_provenance_rule_family_filter_rows")
            or committee_summary.get("metrics", {}).get("midas_kds_row_provenance_rule_family_filter_rows")
            or []
        )
        if isinstance(row, dict)
    ]
    committee_artifacts = committee_artifact_links
    midas_kds_row_provenance_export_json = str(committee_artifacts.get("midas_kds_row_provenance_export_json", "") or "")
    midas_kds_row_provenance_export_csv = str(committee_artifacts.get("midas_kds_row_provenance_export_csv", "") or "")
    midas_kds_row_provenance_export_report = str(committee_artifacts.get("midas_kds_row_provenance_export_report", "") or "")
    midas_native_roundtrip_summary_line = str(
        midas_native_roundtrip_report.get("summary_line", ci.get("midas_native_roundtrip_summary_line", "")) or ""
    ).strip()
    midas_native_roundtrip_writeback_diff_summary_line = str(
        midas_native_roundtrip_receipts_report.get("summary_line", "") or ""
    ).strip()
    midas_native_roundtrip_receipt_rows = [
        row for row in (midas_native_roundtrip_receipts_report.get("receipt_rows") or []) if isinstance(row, dict)
    ]
    midas_native_roundtrip_structure_type_batches = [
        row for row in (midas_native_roundtrip_receipts_report.get("structure_type_batches") or []) if isinstance(row, dict)
    ]
    midas_native_roundtrip_structure_type_batch_markdowns = [
        str(row.get("batch_markdown", "") or "")
        for row in midas_native_roundtrip_structure_type_batches
        if str(row.get("batch_markdown", "") or "")
    ]
    midas_native_roundtrip_appendix_markdown = str(
        midas_native_roundtrip_receipts_report.get("unsupported_lossy_card_family_appendix_markdown", "") or ""
    )
    midas_native_roundtrip_appendix_json = str(
        midas_native_roundtrip_receipts_report.get("unsupported_lossy_card_family_appendix_json", "") or ""
    )
    (
        exact_topology_structural_preview_promotion_queue_json,
        exact_topology_structural_preview_promotion_queue_md,
    ) = _write_exact_topology_structural_preview_promotion_queue(release_dir)
    exact_topology_structural_preview_promotion_queue_payload = _load_json(
        Path(exact_topology_structural_preview_promotion_queue_json)
    )
    exact_topology_structural_preview_queue_summary = (
        exact_topology_structural_preview_promotion_queue_payload.get("summary")
        if isinstance(exact_topology_structural_preview_promotion_queue_payload.get("summary"), dict)
        else {}
    )
    exact_topology_structural_preview_queue_rows = [
        row
        for row in (
            exact_topology_structural_preview_promotion_queue_payload.get("pending_candidate_rows")
            or exact_topology_structural_preview_promotion_queue_payload.get("rows")
            or []
        )
        if isinstance(row, dict)
    ]
    midas_native_roundtrip_gate_report_json = "implementation/phase1/midas_native_roundtrip_gate_report.json"
    midas_native_roundtrip_corpus_manifest_json = "implementation/phase1/open_data/midas/midas_native_corpus_manifest.json"
    midas_native_roundtrip_receipts_report_json = (
        "implementation/phase1/release/midas_native_roundtrip/midas_native_writeback_diff_receipts_report.json"
    )
    korean_native_roundtrip_representative_rows = _build_korean_native_roundtrip_representative_rows(
        midas_native_roundtrip_corpus_manifest,
        midas_native_roundtrip_receipts_report,
    )
    external_benchmark_case_onepage_rows = _build_external_benchmark_case_onepage_rows(
        external_benchmark_execution_status_manifest
    )
    irregular_structure_summary_line = str(
        irregular_structure_gate_report.get("summary_line", "") or irregular_structure_gate_report.get("reason", "") or ""
    ).strip()
    irregular_structure_track_summary_line = irregular_structure_summary_line
    irregular_structure_source_catalog_summary_line = (
        f"Irregular source catalog: PASS | families={int(irregular_structure_source_catalog_summary.get('family_count', 0))} | "
        f"sources={int(irregular_structure_source_catalog_summary.get('source_record_count', 0))} | "
        f"local_ready={int(irregular_structure_source_catalog_summary.get('local_ready_count', 0))} | "
        f"remote_candidates={int(irregular_structure_source_catalog_summary.get('remote_candidate_count', 0))}"
    )
    irregular_structure_triage_summary_line = (
        f"Irregular triage: PASS | native_candidates={int(irregular_structure_triage_summary.get('native_roundtrip_candidate_count', 0))} | "
        f"solver_candidates={int(irregular_structure_triage_summary.get('solver_benchmark_candidate_count', 0))} | "
        f"ai_candidates={int(irregular_structure_triage_summary.get('ai_learning_candidate_count', 0))}"
    )
    irregular_structure_collection_summary_line = (
        f"Irregular collection: PASS | collected={int(irregular_structure_collection_summary.get('collected_count', 0))} | "
        f"metadata_only_remote_candidate={int(irregular_structure_collection_summary.get('metadata_only_remote_candidate_count', 0))} | "
        f"rejected={int(irregular_structure_collection_summary.get('rejected_count', 0))}"
    )
    irregular_top5_local_ready_count = sum(
        1 for row in irregular_top5_families if str(row.get("execution_mode", "") or "").startswith("ready_local")
    )
    irregular_top5_proxy_ready_count = sum(
        1 for row in irregular_top5_families if str(row.get("execution_mode", "") or "") == "ready_local_proxy_now"
    )
    irregular_top5_bridged_ready_count = sum(
        1 for row in irregular_top5_families if str(row.get("execution_mode", "") or "") == "ready_local_bridged_now"
    )
    irregular_top5_canonical_ready_count = sum(
        1
        for row in irregular_top5_families
        if str(row.get("execution_mode", "") or "") in {"ready_local_now", "ready_local_canonical_now"}
    )
    irregular_top5_reference_collected_count = sum(
        1 for row in irregular_top5_families if str(row.get("execution_mode", "") or "") == "reference_collected_only"
    )
    irregular_top5_remote_needed_count = sum(
        1 for row in irregular_top5_families if str(row.get("execution_mode", "") or "") == "remote_source_hunt_needed"
    )
    irregular_top5_summary_line = str(irregular_top5_execution_manifest.get("summary_line", "") or "").strip()
    if not irregular_top5_summary_line:
        irregular_top5_summary_line = (
            f"Irregular top5 manifest: PASS | top5={int(irregular_top5_summary.get('top5_count', len(irregular_top5_families)))} | "
            f"local_ready={irregular_top5_local_ready_count} | proxy_ready={irregular_top5_proxy_ready_count} | "
            f"bridged_ready={irregular_top5_bridged_ready_count} | canonical_ready={irregular_top5_canonical_ready_count} | "
            f"reference_collected={irregular_top5_reference_collected_count} | remote_needed={irregular_top5_remote_needed_count}"
        )
    irregular_benchmark_execution_summary_line = str(
        irregular_benchmark_execution_manifest.get("summary_line", "") or ""
    ).strip()
    if not irregular_benchmark_execution_summary_line:
        irregular_benchmark_execution_summary_line = (
            f"Irregular benchmark execution: PASS | ready={len(irregular_benchmark_execution_ready_tasks)} | "
            f"blocked={len(irregular_benchmark_execution_blocked_tasks)} | "
            f"task_count={len(irregular_benchmark_execution_ready_tasks) + len(irregular_benchmark_execution_blocked_tasks)}"
            if irregular_benchmark_execution_manifest
            else "n/a"
        )
    irregular_structure_gate_report_json = (
        str(Path(args.irregular_structure_gate_report)) if Path(args.irregular_structure_gate_report).exists() else ""
    )
    irregular_structure_source_catalog_json = (
        str(Path(args.irregular_structure_source_catalog)) if Path(args.irregular_structure_source_catalog).exists() else ""
    )
    irregular_structure_triage_report_json = (
        str(Path(args.irregular_structure_triage_report)) if Path(args.irregular_structure_triage_report).exists() else ""
    )
    irregular_structure_collection_report_json = (
        str(Path(args.irregular_structure_collection_report)) if Path(args.irregular_structure_collection_report).exists() else ""
    )
    irregular_top5_execution_manifest_json = (
        str(Path(args.irregular_top5_execution_manifest)) if Path(args.irregular_top5_execution_manifest).exists() else ""
    )
    irregular_benchmark_execution_manifest_json = (
        str(Path(args.irregular_benchmark_execution_manifest)) if Path(args.irregular_benchmark_execution_manifest).exists() else ""
    )
    korean_source_ingest_gate_report = _load_optional_json(Path(args.korean_source_ingest_gate_report))
    korean_source_ingest_summary = (
        korean_source_ingest_gate_report.get("summary")
        if isinstance(korean_source_ingest_gate_report.get("summary"), dict)
        else {}
    )
    korean_source_ingest_summary_line = str(
        korean_source_ingest_gate_report.get("summary_line", "")
        or korean_source_ingest_summary.get("ingest_summary_line", "")
        or (
            f"Korean source ingest: {'PASS' if bool(korean_source_ingest_gate_report.get('contract_pass', False)) else 'CHECK'} | "
            f"sources={int(korean_source_ingest_summary.get('source_count', 0) or 0)} | "
            f"classes={int(korean_source_ingest_summary.get('source_class_count', 0) or 0)} | "
            f"collected={int(korean_source_ingest_summary.get('collected_count', 0) or 0)} | "
            f"fingerprinted={int(korean_source_ingest_summary.get('fingerprinted_count', 0) or 0)} | "
            f"metadata_only={int(korean_source_ingest_summary.get('metadata_only_remote_candidate_count', 0) or 0)} | "
            f"rejected={int(korean_source_ingest_summary.get('rejected_count', 0) or 0)} | "
            f"duplicate_sha_groups={int(korean_source_ingest_summary.get('duplicate_sha_group_count', 0) or 0)}"
        )
    ).strip()
    korean_source_ingest_summary_line = _compact_korean_source_ingest_summary_line(korean_source_ingest_summary_line)
    korean_structural_preview_promotion_queue = _load_optional_json(
        Path(args.korean_structural_preview_promotion_queue)
    )
    korean_structural_preview_queue_summary = (
        korean_structural_preview_promotion_queue.get("summary")
        if isinstance(korean_structural_preview_promotion_queue.get("summary"), dict)
        else {}
    )
    korean_structural_preview_queue_summary_line = str(
        korean_structural_preview_promotion_queue.get("summary_line", "")
        or (
            f"Korean structural preview queue: {'PASS' if bool(korean_structural_preview_promotion_queue) else 'CHECK'} | "
            f"candidates={int(korean_structural_preview_queue_summary.get('candidate_total', 0) or 0)} | "
            f"pending={int(korean_structural_preview_queue_summary.get('pending_candidate_count', 0) or 0)} | "
            f"state={str(korean_structural_preview_queue_summary.get('state', '') or '').strip() or 'missing'}"
        )
    ).strip()
    korean_structural_preview_queue_summary_line = _compact_korean_structural_preview_queue_summary_line(
        korean_structural_preview_queue_summary_line
    )

    summary = {
        "schema_version": "1.0",
        "bundle_id": bundle_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "measured_chain_total_minutes": _safe_float(gap_summary.get("measured_chain_total_minutes", 0.0)),
        "measured_chain_rolling_sample_count": int(gap_summary.get("measured_chain_rolling_sample_count", 0)),
        "measured_chain_rolling_total_minutes_mean": _safe_float(gap_summary.get("measured_chain_rolling_total_minutes_mean", 0.0)),
        "measured_chain_rolling_total_minutes_range": gap_summary.get("measured_chain_rolling_total_minutes_range", []),
        "measured_chain_full_chain_sample_count": int(gap_summary.get("measured_chain_full_chain_sample_count", 0)),
        "measured_chain_comparable_sample_count": int(gap_summary.get("measured_chain_comparable_sample_count", 0)),
        "measured_chain_comparable_reference_step_count": int(gap_summary.get("measured_chain_comparable_reference_step_count", 0)),
        "measured_chain_comparable_overlap_threshold": _safe_float(gap_summary.get("measured_chain_comparable_overlap_threshold", 0.0)),
        "measured_chain_comparable_reference_deployment_model": str(gap_summary.get("measured_chain_comparable_reference_deployment_model", "")),
        "measured_chain_comparable_reference_strict_design_opt_cost_smoke": bool(gap_summary.get("measured_chain_comparable_reference_strict_design_opt_cost_smoke", False)),
        "measured_chain_rolling_selection_mode": str(gap_summary.get("measured_chain_rolling_selection_mode", "")),
        "design_opt_raw_max_drift_pct": design_opt_raw_max_drift,
        "design_opt_raw_residual_drift_pct": design_opt_raw_residual_drift,
        "design_opt_raw_max_dcr": design_opt_raw_max_dcr,
        "design_opt_repaired_compliance_max_drift_pct": design_opt_repaired_max_drift,
        "design_opt_repaired_compliance_residual_drift_pct": design_opt_repaired_residual_drift,
        "design_opt_repaired_compliance_max_dcr": design_opt_repaired_max_dcr,
        "design_opt_compliance_basis": design_opt_compliance_basis,
        "design_opt_repair_action_count": design_opt_repair_action_count,
        "design_opt_constructability_signal_gain_pct": design_opt_constructability_signal_gain_pct,
        "design_opt_baseline_constructability_avg": design_opt_baseline_constructability_avg,
        "design_opt_final_constructability_avg": design_opt_final_constructability_avg,
        "design_opt_baseline_detailing_complexity_avg": design_opt_baseline_detailing_complexity_avg,
        "design_opt_final_detailing_complexity_avg": design_opt_final_detailing_complexity_avg,
        "design_opt_selected_action_family_counts": design_opt_selected_action_family_counts,
        "design_opt_preview_supply_family_counts": design_opt_preview_supply_family_counts,
        "design_opt_preview_supply_family_mix_label": design_opt_preview_supply_family_mix_label,
        "design_opt_preview_missing_target_families_label": design_opt_preview_missing_target_families_label,
        "design_opt_previous_action_family_counts": design_opt_previous_action_family_counts,
        "design_opt_selected_family_mix_label": design_opt_selected_family_mix_label,
        "design_opt_selected_family_trend_label": design_opt_selected_family_trend_label,
        "design_opt_selected_dominant_family": str(design_opt_selected_dominant_family),
        "design_opt_selected_dominant_family_ratio": design_opt_selected_dominant_family_ratio,
        "design_opt_previous_dominant_family": str(design_opt_previous_dominant_family),
        "design_opt_previous_dominant_family_ratio": design_opt_previous_dominant_family_ratio,
        "promotion_reason_code": promotion_reason_code,
        "promotion_hold_for_review": promotion_hold_for_review,
        "hold_review_manifest": hold_review_manifest,
        "hold_review_packet_md": hold_review_packet_md,
        "hold_review_packet_pdf": hold_review_packet_pdf,
        "hold_review_ack_json": hold_review_ack_json,
        "pbd_dynamic_hinge_refresh_ready": bool(gap_summary.get("pbd_dynamic_hinge_refresh_ready", False)),
        "pbd_hinge_state_mode": str(gap_summary.get("pbd_hinge_state_mode", "")),
        "pbd_hinge_refresh_reason": str(gap_summary.get("pbd_hinge_refresh_reason", "")),
        "pbd_hinge_refresh_artifact_present": bool(gap_summary.get("pbd_hinge_refresh_artifact_present", False)),
        "pbd_hinge_refresh_artifact_kind": str(gap_summary.get("pbd_hinge_refresh_artifact_kind", "")),
        "pbd_hinge_refresh_source_mode": str(gap_summary.get("pbd_hinge_refresh_source_mode", "")),
        "pbd_hinge_refresh_overlap_member_count": int(gap_summary.get("pbd_hinge_refresh_overlap_member_count", 0)),
        "pbd_hinge_refresh_rebar_sensitive_member_count": int(
            gap_summary.get("pbd_hinge_refresh_rebar_sensitive_member_count", 0)
        ),
        "pbd_hinge_benchmark_gate_pass": bool(gap_summary.get("pbd_hinge_benchmark_gate_pass", False)),
        "pbd_hinge_benchmark_fixture_regression_pass": bool(
            gap_summary.get("pbd_hinge_benchmark_fixture_regression_pass", False)
        ),
        "pbd_hinge_benchmark_alignment_pass": bool(
            gap_summary.get("pbd_hinge_benchmark_alignment_pass", False)
        ),
        "pbd_hinge_benchmark_asset_count": int(gap_summary.get("pbd_hinge_benchmark_asset_count", 0)),
        "pbd_hinge_benchmark_train_count": int(gap_summary.get("pbd_hinge_benchmark_train_count", 0)),
        "pbd_hinge_benchmark_val_count": int(gap_summary.get("pbd_hinge_benchmark_val_count", 0)),
        "pbd_hinge_benchmark_holdout_count": int(gap_summary.get("pbd_hinge_benchmark_holdout_count", 0)),
        "pbd_hinge_benchmark_rebar_sensitive_count": int(gap_summary.get("pbd_hinge_benchmark_rebar_sensitive_count", 0)),
        "pbd_hinge_benchmark_confinement_sensitive_count": int(
            gap_summary.get("pbd_hinge_benchmark_confinement_sensitive_count", 0)
        ),
        "pbd_hinge_benchmark_fixture_count": int(gap_summary.get("pbd_hinge_benchmark_fixture_count", 0)),
        "pbd_hinge_benchmark_fixture_min_point_count": int(
            gap_summary.get("pbd_hinge_benchmark_fixture_min_point_count", 0)
        ),
        "pbd_hinge_benchmark_fixture_min_peak_drift_ratio": float(
            gap_summary.get("pbd_hinge_benchmark_fixture_min_peak_drift_ratio", 0.0)
        ),
        "pbd_hinge_benchmark_alignment_refresh_column_row_count": int(
            gap_summary.get("pbd_hinge_benchmark_alignment_refresh_column_row_count", 0)
        ),
        "pbd_hinge_benchmark_alignment_rebar_sensitive_column_count": int(
            gap_summary.get("pbd_hinge_benchmark_alignment_rebar_sensitive_column_count", 0)
        ),
        "pbd_hinge_benchmark_alignment_benchmark_rebar_ratio_min": float(
            gap_summary.get("pbd_hinge_benchmark_alignment_benchmark_rebar_ratio_min", 0.0)
        ),
        "pbd_hinge_benchmark_alignment_benchmark_rebar_ratio_max": float(
            gap_summary.get("pbd_hinge_benchmark_alignment_benchmark_rebar_ratio_max", 0.0)
        ),
        "pbd_hinge_benchmark_alignment_refresh_rebar_ratio_min": float(
            gap_summary.get("pbd_hinge_benchmark_alignment_refresh_rebar_ratio_min", 0.0)
        ),
        "pbd_hinge_benchmark_alignment_refresh_rebar_ratio_max": float(
            gap_summary.get("pbd_hinge_benchmark_alignment_refresh_rebar_ratio_max", 0.0)
        ),
        "panel_zone_3d_clash_ready": bool(gap_summary.get("panel_zone_3d_clash_ready", False)),
        "panel_zone_constructability_mode": str(gap_summary.get("panel_zone_constructability_mode", "")),
        "panel_zone_constructability_reason": str(gap_summary.get("panel_zone_constructability_reason", "")),
        "panel_zone_proxy_candidate_count": int(gap_summary.get("panel_zone_proxy_candidate_count", 0)),
        "panel_zone_source_artifact_kind": str(gap_summary.get("panel_zone_source_artifact_kind", "")),
        "panel_zone_source_artifact_path": str(gap_summary.get("panel_zone_source_artifact_path", "")),
        "panel_zone_source_contract_mode": str(gap_summary.get("panel_zone_source_contract_mode", "")),
        "panel_zone_internal_engine_complete": bool(gap_summary.get("panel_zone_internal_engine_complete", False)),
        "panel_zone_external_validation_pending": bool(
            gap_summary.get("panel_zone_external_validation_pending", False)
        ),
        "panel_zone_validation_boundary": str(gap_summary.get("panel_zone_validation_boundary", "")),
        "panel_zone_instruction_sidecar_present": bool(gap_summary.get("panel_zone_instruction_sidecar_present", False)),
        "panel_zone_instruction_sidecar_change_count": int(
            gap_summary.get("panel_zone_instruction_sidecar_change_count", 0)
        ),
        "panel_zone_instruction_sidecar_candidate_overlap_mode": str(
            gap_summary.get("panel_zone_instruction_sidecar_candidate_overlap_mode", "")
        ),
        "panel_zone_instruction_sidecar_overlap_row_count": int(
            gap_summary.get("panel_zone_instruction_sidecar_overlap_row_count", 0)
        ),
        "panel_zone_instruction_sidecar_overlap_member_count": int(
            gap_summary.get("panel_zone_instruction_sidecar_overlap_member_count", 0)
        ),
        "panel_zone_instruction_sidecar_overlap_group_count": int(
            gap_summary.get("panel_zone_instruction_sidecar_overlap_group_count", 0)
        ),
        "panel_zone_instruction_sidecar_evidence_model": str(
            gap_summary.get("panel_zone_instruction_sidecar_evidence_model", "")
        ),
        "panel_zone_instruction_sidecar_rebar_delivery_mode": str(
            gap_summary.get("panel_zone_instruction_sidecar_rebar_delivery_mode", "")
        ),
        "panel_zone_source_valid_row_counts": dict(gap_summary.get("panel_zone_source_valid_row_counts", {}) or {}),
        "panel_zone_source_overlap_member_counts": dict(gap_summary.get("panel_zone_source_overlap_member_counts", {}) or {}),
        "panel_zone_source_candidate_scan_modes": dict(gap_summary.get("panel_zone_source_candidate_scan_modes", {}) or {}),
        "panel_zone_source_bundle_modes": dict(gap_summary.get("panel_zone_source_bundle_modes", {}) or {}),
        "panel_zone_source_upstream_verification_tiers": dict(
            gap_summary.get("panel_zone_source_upstream_verification_tiers", {}) or {}
        ),
        "panel_zone_validated_source_row_count_total": int(gap_summary.get("panel_zone_validated_source_row_count_total", 0)),
        "panel_zone_validated_source_overlap_member_count_min": int(
            gap_summary.get("panel_zone_validated_source_overlap_member_count_min", 0)
        ),
        "panel_zone_topology_capable_input": bool(gap_summary.get("panel_zone_topology_capable_input", False)),
        "panel_zone_true_3d_clash_verified": bool(gap_summary.get("panel_zone_true_3d_clash_verified", False)),
        "panel_zone_true_3d_anchorage_verified": bool(gap_summary.get("panel_zone_true_3d_anchorage_verified", False)),
        "panel_zone_missing_required_sources": gap_summary.get("panel_zone_missing_required_sources", []),
        "panel_zone_solver_verified_inbox_status_mode": str(
            gap_summary.get("panel_zone_solver_verified_inbox_status_mode", "")
        ),
        "panel_zone_solver_verified_inbox_has_input": bool(
            gap_summary.get("panel_zone_solver_verified_inbox_has_input", False)
        ),
        "panel_zone_solver_verified_pending_input": bool(
            gap_summary.get("panel_zone_solver_verified_pending_input", False)
        ),
        "panel_zone_solver_verified_input_mode_detected": str(
            gap_summary.get("panel_zone_solver_verified_input_mode_detected", "")
        ),
        "panel_zone_solver_verified_latest_consume_report_present": bool(
            gap_summary.get("panel_zone_solver_verified_latest_consume_report_present", False)
        ),
        "panel_zone_solver_verified_latest_consume_contract_pass": bool(
            gap_summary.get("panel_zone_solver_verified_latest_consume_contract_pass", False)
        ),
        "panel_zone_solver_verified_latest_consume_reason_code": str(
            gap_summary.get("panel_zone_solver_verified_latest_consume_reason_code", "")
        ),
        "panel_zone_solver_verified_source_origin_class": str(
            gap_summary.get("panel_zone_solver_verified_source_origin_class", "")
        ),
        "panel_zone_solver_verified_release_refresh_source_allowed": bool(
            gap_summary.get("panel_zone_solver_verified_release_refresh_source_allowed", False)
        ),
        "panel_zone_solver_verified_recommended_action": str(
            gap_summary.get("panel_zone_solver_verified_recommended_action", "")
        ),
        "foundation_optimization_ready": bool(gap_summary.get("foundation_optimization_ready", False)),
        "foundation_member_type_present": bool(gap_summary.get("foundation_member_type_present", False)),
        "foundation_member_type_count": int(gap_summary.get("foundation_member_type_count", 0)),
        "foundation_optimization_mode": str(gap_summary.get("foundation_optimization_mode", "")),
        "foundation_optimization_reason": str(gap_summary.get("foundation_optimization_reason", "")),
        "foundation_scope_source": str(gap_summary.get("foundation_scope_source", "")),
        "foundation_artifact_scan_mode": str(gap_summary.get("foundation_artifact_scan_mode", "")),
        "foundation_artifact_evidence_mode": str(gap_summary.get("foundation_artifact_evidence_mode", "")),
        "upstream_foundation_label_count": int(gap_summary.get("upstream_foundation_label_count", 0)),
        "upstream_foundation_provenance_mode": str(gap_summary.get("upstream_foundation_provenance_mode", "")),
        "wind_tunnel_raw_mapping_ready": bool(gap_summary.get("wind_tunnel_raw_mapping_ready", False)),
        "wind_tunnel_mapping_mode": str(gap_summary.get("wind_tunnel_mapping_mode", "")),
        "wind_tunnel_mapping_reason": str(gap_summary.get("wind_tunnel_mapping_reason", "")),
        "design_optimization_entrypoints": design_opt_entrypoint_rows,
        "design_optimization_entrypoint_groups": design_opt_entrypoint_groups,
        "checks": {
            "nightly_release": _bool_status(bool(nightly.get("contract_pass", False))),
            "ci_gate": _bool_status(bool(ci.get("all_pass", False))),
            "static_validation": _bool_status(bool(static.get("pass", False))),
            "freeze_release": _bool_status(bool(freeze.get("contract_pass", False))),
            "promotion": _bool_status(bool(promotion.get("contract_pass", False))),
            "signed_release_registry": _bool_status(bool(registry.get("contract_pass", False))),
            "registry_signature_verified": _bool_status(bool((registry.get("checks") or {}).get("signature_verified_pass", False))),
            "solver_hip_e2e": _bool_status(bool(solver.get("contract_pass", False))),
            "rc_benchmark_lock": _bool_status(bool(rc.get("contract_pass", False))),
            "ndtha_residual_gate": _bool_status(bool(ndtha_residual.get("contract_pass", False))),
            "committee_review_package": _bool_status(bool(committee.get("contract_pass", False))),
            "global_authority_gate": _bool_status(bool(global_authority.get("contract_pass", False))),
            "pbd_review_package": _bool_status(bool(pbd.get("contract_pass", False))),
        },
        "metrics": {
            "commercial_grade": str(gap_summary.get("commercial_grade", "unknown")),
            "deployment_model": str(gap_summary.get("deployment_model", "engineer_in_the_loop_accelerated_coverage")),
            "accelerated_coverage_target_pct_label": _coverage_range_label(gap_summary.get("accelerated_coverage_target_pct_range", [95, 99])),
            "residual_holdout_target_pct_label": _coverage_range_label(gap_summary.get("residual_holdout_target_pct_range", [1, 5])),
            "estimated_time_saved_pct_label": _coverage_range_label(gap_summary.get("estimated_time_saved_pct_range", [70, 90])),
            "estimated_time_saved_basis": str(gap_summary.get("estimated_time_saved_basis", "")),
            "empirical_smoke_runtime_saved_pct_label": _coverage_range_label(gap_summary.get("empirical_smoke_runtime_saved_pct_range", [])),
            "measured_chain_total_minutes": _safe_float(gap_summary.get("measured_chain_total_minutes", 0.0)),
            "measured_chain_rolling_sample_count": int(gap_summary.get("measured_chain_rolling_sample_count", 0)),
            "measured_chain_rolling_total_minutes_mean": _safe_float(gap_summary.get("measured_chain_rolling_total_minutes_mean", 0.0)),
            "measured_chain_rolling_total_minutes_range": gap_summary.get("measured_chain_rolling_total_minutes_range", []),
            "measured_chain_rolling_selection_mode": str(gap_summary.get("measured_chain_rolling_selection_mode", "")),
            "measured_chain_comparable_reference_deployment_model": str(gap_summary.get("measured_chain_comparable_reference_deployment_model", "")),
            "measured_chain_comparable_reference_strict_design_opt_cost_smoke": bool(gap_summary.get("measured_chain_comparable_reference_strict_design_opt_cost_smoke", False)),
            "engineer_in_loop_accelerated_coverage_ready": bool(gap_summary.get("engineer_in_loop_accelerated_coverage_ready", False)),
            "time_saving_focus": str(gap_summary.get("time_saving_focus", "")),
            "full_commercial_replacement_ready": bool(gap_summary.get("full_commercial_replacement_ready", False)),
            "external_benchmark_submission_ready_to_start_now": bool(
                external_benchmark_submission_summary.get("ready_to_start_now", False)
            ),
            "external_benchmark_submission_ready_to_start_full_submission_now": bool(
                external_benchmark_submission_summary.get(
                    "ready_to_start_full_submission_now",
                    False,
                )
            ),
            "external_benchmark_submission_reason_code": str(
                external_benchmark_submission_readiness.get("reason_code", "") or ""
            ),
            "external_benchmark_submission_recommended_start_mode": str(
                external_benchmark_submission_summary.get("recommended_start_mode", "") or ""
            ),
            "external_benchmark_submission_recommended_submission_scope": str(
                external_benchmark_submission_summary.get("recommended_submission_scope", "") or ""
            ),
            "external_benchmark_submission_blocker_label": str(
                external_benchmark_submission_summary.get("blocker_label", "") or ""
            ),
            "external_benchmark_submission_caution_label": str(
                external_benchmark_submission_summary.get("caution_label", "") or ""
            ),
            "external_benchmark_execution_mode": str(
                external_benchmark_execution_summary.get("execution_mode", "") or ""
            ),
            "external_benchmark_execution_ready_task_count": int(
                external_benchmark_execution_summary.get("ready_task_count", 0) or 0
            ),
            "external_benchmark_execution_blocked_task_count": int(
                external_benchmark_execution_summary.get("blocked_task_count", 0) or 0
            ),
            "external_benchmark_execution_review_boundary_pending_count": int(
                external_benchmark_execution_summary.get("review_boundary_pending_count", 0) or 0
            ),
            "external_benchmark_execution_review_boundary_resolution_label": str(
                external_benchmark_execution_summary.get("review_boundary_resolution_label", "") or ""
            ),
            "external_benchmark_execution_review_boundary_owner_label": str(
                external_benchmark_execution_summary.get("review_boundary_owner_label", "") or ""
            ),
            "external_benchmark_execution_review_boundary_assignee_label": str(
                external_benchmark_execution_summary.get("review_boundary_assignee_label", "") or ""
            ),
            "external_benchmark_execution_review_boundary_assignment_status_label": str(
                external_benchmark_execution_summary.get("review_boundary_assignment_status_label", "")
                or ""
            ),
            "external_benchmark_execution_review_boundary_priority_label": str(
                external_benchmark_execution_summary.get("review_boundary_priority_label", "") or ""
            ),
            "external_benchmark_execution_review_boundary_family_label": str(
                external_benchmark_execution_summary.get("review_boundary_family_label", "") or ""
            ),
            "external_benchmark_execution_review_boundary_change_count_total": int(
                external_benchmark_execution_summary.get("review_boundary_change_count_total", 0)
                or 0
            ),
            "external_benchmark_execution_review_boundary_followup_action_label": str(
                external_benchmark_execution_summary.get("review_boundary_followup_action_label", "")
                or ""
            ),
            "external_benchmark_execution_review_boundary_sla_state_label": str(
                external_benchmark_execution_summary.get("review_boundary_sla_state_label", "")
                or ""
            ),
            "external_benchmark_execution_review_boundary_age_bucket_label": str(
                external_benchmark_execution_summary.get("review_boundary_age_bucket_label", "")
                or ""
            ),
            "external_benchmark_execution_review_boundary_overdue_count": int(
                external_benchmark_execution_summary.get("review_boundary_overdue_count", 0) or 0
            ),
            "external_benchmark_execution_review_boundary_oldest_open_age_hours": _safe_float(
                external_benchmark_execution_summary.get("review_boundary_oldest_open_age_hours", 0.0)
            ),
            "external_benchmark_execution_review_boundary_preview_approve_all_reason_code": str(
                external_benchmark_execution_review_boundary_preview.get("approve_all_reason_code", "") or ""
            ),
            "external_benchmark_execution_review_boundary_preview_approve_all_ready_full": bool(
                external_benchmark_execution_review_boundary_preview.get("approve_all_ready_full", False)
            ),
            "external_benchmark_execution_review_boundary_preview_reject_one_reason_code": str(
                external_benchmark_execution_review_boundary_preview.get("reject_one_reason_code", "") or ""
            ),
            "external_benchmark_execution_review_boundary_preview_reject_one_open_revision_count": int(
                external_benchmark_execution_review_boundary_preview.get(
                    "reject_one_open_revision_count", 0
                )
                or 0
            ),
            "external_benchmark_execution_status_mode": str(
                external_benchmark_execution_status_summary.get("status_mode", "") or ""
            ),
            "external_benchmark_execution_executable_task_count": int(
                external_benchmark_execution_status_summary.get("executable_task_count", 0) or 0
            ),
            "external_benchmark_execution_planned_task_count": int(
                external_benchmark_execution_status_summary.get("planned_task_count", 0) or 0
            ),
            "external_benchmark_execution_in_progress_task_count": int(
                external_benchmark_execution_status_summary.get("in_progress_task_count", 0) or 0
            ),
            "external_benchmark_execution_completed_task_count": int(
                external_benchmark_execution_status_summary.get("completed_task_count", 0) or 0
            ),
            "external_benchmark_execution_failed_task_count": int(
                external_benchmark_execution_status_summary.get("failed_task_count", 0) or 0
            ),
            "external_benchmark_execution_finished_task_count": int(
                external_benchmark_execution_status_summary.get("finished_task_count", 0) or 0
            ),
            "external_benchmark_execution_completion_ratio": _safe_float(
                external_benchmark_execution_status_summary.get("completion_ratio", 0.0)
            ),
            "audit_review_decision_batch_template_item_count": int(
                audit_review_decision_batch_template_summary.get("decision_item_count", 0) or 0
            ),
            "audit_review_decision_batch_template_current_status_label": str(
                audit_review_decision_batch_template_summary.get("current_status_label", "") or ""
            ),
            "audit_review_decision_batch_template_review_owner_label": str(
                audit_review_decision_batch_template_summary.get("review_owner_label", "") or ""
            ),
            "audit_review_decision_batch_template_review_priority_label": str(
                audit_review_decision_batch_template_summary.get("review_priority_label", "") or ""
            ),
            "audit_review_decision_batch_attested_example_count": int(
                sum(
                    1
                    for payload in (
                        audit_review_decision_batch_approve_all_attested_example,
                        audit_review_decision_batch_mixed_attested_example,
                    )
                    if bool(payload.get("contract_pass", False))
                )
            ),
            "audit_review_decision_batch_attested_example_preview_label": ", ".join(
                label
                for label in (
                    (
                        f"approve_all={audit_review_decision_batch_approve_all_attested_example_summary.get('expected_preview_reason_code', '')}"
                        if audit_review_decision_batch_approve_all_attested_example_summary
                        else ""
                    ),
                    (
                        f"mixed={audit_review_decision_batch_mixed_attested_example_summary.get('expected_preview_reason_code', '')}"
                        if audit_review_decision_batch_mixed_attested_example_summary
                        else ""
                    ),
                )
                if label
            )
            or "none",
            "external_benchmark_submission_preview_approve_all_reason_code": str(
                external_benchmark_submission_preview_approve_all.get("reason_code", "") or ""
            ),
            "external_benchmark_submission_preview_approve_all_ready_full": bool(
                external_benchmark_submission_preview_approve_all_readiness_summary.get(
                    "ready_to_start_full_submission_now", False
                )
            ),
            "external_benchmark_submission_preview_approve_all_pending_count": int(
                external_benchmark_submission_preview_approve_all_readiness_summary.get(
                    "audit_review_queue_pending_count", 0
                )
                or 0
            ),
            "external_benchmark_submission_preview_approve_all_open_revision_count": int(
                external_benchmark_submission_preview_approve_all_readiness_summary.get(
                    "audit_review_resolution_open_revision_count", 0
                )
                or 0
            ),
            "external_benchmark_submission_preview_reject_one_reason_code": str(
                external_benchmark_submission_preview_reject_one.get("reason_code", "") or ""
            ),
            "external_benchmark_submission_preview_reject_one_ready_full": bool(
                external_benchmark_submission_preview_reject_one_readiness_summary.get(
                    "ready_to_start_full_submission_now", False
                )
            ),
            "external_benchmark_submission_preview_reject_one_pending_count": int(
                external_benchmark_submission_preview_reject_one_readiness_summary.get(
                    "audit_review_queue_pending_count", 0
                )
                or 0
            ),
            "external_benchmark_submission_preview_reject_one_open_revision_count": int(
                external_benchmark_submission_preview_reject_one_readiness_summary.get(
                    "audit_review_resolution_open_revision_count", 0
                )
                or 0
            ),
            "external_benchmark_submission_preview_reject_one_blocker_label": str(
                external_benchmark_submission_preview_reject_one_readiness_summary.get("blocker_label", "") or ""
            ),
            "audit_review_decision_batch_runner_reason_code": str(
                audit_review_decision_batch_run_report.get("reason_code", "") or ""
            ),
            "audit_review_decision_batch_runner_apply_live": bool(
                audit_review_decision_batch_run_report.get("apply_live", False)
            ),
            "audit_review_decision_batch_runner_live_applied": bool(
                audit_review_decision_batch_run_report.get("live_applied", False)
            ),
            "audit_review_decision_batch_runner_preview_reason_code": str(
                audit_review_decision_batch_run_report.get("preview_reason_code", "") or ""
            ),
            "audit_review_decision_batch_runner_preview_ready_full": bool(
                audit_review_decision_batch_run_report.get("preview_ready_full", False)
            ),
            "audit_review_decision_batch_runner_preview_pending_count": int(
                audit_review_decision_batch_run_report.get("preview_pending_count", 0) or 0
            ),
            "audit_review_decision_batch_runner_preview_open_revision_count": int(
                audit_review_decision_batch_run_report.get("preview_open_revision_count", 0) or 0
            ),
            "audit_review_decision_batch_runner_live_preview_reason_code": str(
                audit_review_decision_batch_live_preview.get("reason_code", "") or ""
            ),
            "structural_optimization_viewer_html": structural_optimization_viewer_html,
            "structural_optimization_viewer_json": structural_optimization_viewer_json,
            "optimized_drawing_review_html": optimized_drawing_review_html,
            "optimized_drawing_review_summary_json": optimized_drawing_review_summary_json,
            "optimized_drawing_review_projection_count": int(
                optimized_drawing_review_summary.get("projection_count", 0) or 0
            ),
            "optimized_drawing_review_changed_group_count": int(
                optimized_drawing_review_summary.get("changed_group_count", 0) or 0
            ),
            "optimized_drawing_review_changed_member_count": int(
                optimized_drawing_review_summary.get("changed_member_count", 0) or 0
            ),
            "optimized_drawing_review_axis_source_mode": str(
                (
                    optimized_drawing_review_summary.get("interactive_3d_payload", {})
                    if isinstance(optimized_drawing_review_summary.get("interactive_3d_payload"), dict)
                    else {}
                ).get("axis_ref_source_mode", "")
                or ""
            ),
            "optimized_drawing_review_axis_source_path": str(
                (
                    optimized_drawing_review_summary.get("interactive_3d_payload", {})
                    if isinstance(optimized_drawing_review_summary.get("interactive_3d_payload"), dict)
                    else {}
                ).get("axis_ref_source_path", "")
                or ""
            ),
            "optimized_drawing_review_axis_preview_label": " ".join(
                str(row.get("label", "") or "")
                for row in (
                    (
                        (
                            optimized_drawing_review_summary.get("interactive_3d_payload", {})
                            if isinstance(optimized_drawing_review_summary.get("interactive_3d_payload"), dict)
                            else {}
                        ).get("axis_refs", {})
                        if isinstance(
                            (
                                optimized_drawing_review_summary.get("interactive_3d_payload", {})
                                if isinstance(optimized_drawing_review_summary.get("interactive_3d_payload"), dict)
                                else {}
                            ).get("axis_refs", {}),
                            dict,
                        )
                        else {}
                    ).get("x", [])
                )
                if isinstance(row, dict)
            )[:64],
            "structural_optimization_viewer_mode": str(
                structural_optimization_viewer.get("viewer_mode", "") or ""
            ),
            "structural_optimization_viewer_story_zone_nonempty_cell_count": int(
                structural_optimization_viewer_story_zone_map.get("nonempty_cell_count", 0) or 0
            ),
            "structural_optimization_viewer_story_zone_max_abs_cost_proxy_delta": _safe_float(
                structural_optimization_viewer_story_zone_map.get("max_abs_cost_proxy_delta", 0.0)
            ),
            "structural_optimization_viewer_gallery_tile_count": int(
                len(structural_optimization_viewer.get("gallery_tiles") or [])
                if isinstance(structural_optimization_viewer.get("gallery_tiles"), list)
                else 0
            ),
            "pbd_resolved_ndtha_report": str(pbd_inputs.get("resolved_ndtha_report", "") or ""),
            "pbd_resolved_ndtha_response_npz": str(pbd_inputs.get("resolved_ndtha_response_npz", "") or ""),
            "pbd_ndtha_response_fallback_used": bool(pbd_inputs.get("ndtha_response_fallback_used", False)),
            "pbd_ndtha_response_coverage_count": int(pbd_summary.get("ndtha_response_coverage_count", 0) or 0),
            "pbd_dynamic_hinge_refresh_ready": bool(gap_summary.get("pbd_dynamic_hinge_refresh_ready", False)),
            "pbd_hinge_state_mode": str(gap_summary.get("pbd_hinge_state_mode", "")),
            "pbd_hinge_refresh_reason": str(gap_summary.get("pbd_hinge_refresh_reason", "")),
            "pbd_hinge_refresh_artifact_present": bool(gap_summary.get("pbd_hinge_refresh_artifact_present", False)),
            "pbd_hinge_refresh_artifact_kind": str(gap_summary.get("pbd_hinge_refresh_artifact_kind", "")),
            "pbd_hinge_refresh_source_mode": str(gap_summary.get("pbd_hinge_refresh_source_mode", "")),
            "pbd_hinge_refresh_overlap_member_count": int(gap_summary.get("pbd_hinge_refresh_overlap_member_count", 0)),
            "pbd_hinge_refresh_rebar_sensitive_member_count": int(
                gap_summary.get("pbd_hinge_refresh_rebar_sensitive_member_count", 0)
            ),
            "pbd_hinge_benchmark_gate_pass": bool(gap_summary.get("pbd_hinge_benchmark_gate_pass", False)),
            "pbd_hinge_benchmark_fixture_regression_pass": bool(
                gap_summary.get("pbd_hinge_benchmark_fixture_regression_pass", False)
            ),
            "pbd_hinge_benchmark_alignment_pass": bool(
                gap_summary.get("pbd_hinge_benchmark_alignment_pass", False)
            ),
            "pbd_hinge_benchmark_asset_count": int(gap_summary.get("pbd_hinge_benchmark_asset_count", 0)),
            "pbd_hinge_benchmark_train_count": int(gap_summary.get("pbd_hinge_benchmark_train_count", 0)),
            "pbd_hinge_benchmark_val_count": int(gap_summary.get("pbd_hinge_benchmark_val_count", 0)),
            "pbd_hinge_benchmark_holdout_count": int(gap_summary.get("pbd_hinge_benchmark_holdout_count", 0)),
            "pbd_hinge_benchmark_rebar_sensitive_count": int(gap_summary.get("pbd_hinge_benchmark_rebar_sensitive_count", 0)),
            "pbd_hinge_benchmark_confinement_sensitive_count": int(
                gap_summary.get("pbd_hinge_benchmark_confinement_sensitive_count", 0)
            ),
            "pbd_hinge_benchmark_fixture_count": int(gap_summary.get("pbd_hinge_benchmark_fixture_count", 0)),
            "pbd_hinge_benchmark_fixture_min_point_count": int(
                gap_summary.get("pbd_hinge_benchmark_fixture_min_point_count", 0)
            ),
            "pbd_hinge_benchmark_fixture_min_peak_drift_ratio": float(
                gap_summary.get("pbd_hinge_benchmark_fixture_min_peak_drift_ratio", 0.0)
            ),
            "pbd_hinge_benchmark_alignment_refresh_column_row_count": int(
                gap_summary.get("pbd_hinge_benchmark_alignment_refresh_column_row_count", 0)
            ),
            "pbd_hinge_benchmark_alignment_rebar_sensitive_column_count": int(
                gap_summary.get("pbd_hinge_benchmark_alignment_rebar_sensitive_column_count", 0)
            ),
            "pbd_hinge_benchmark_alignment_benchmark_rebar_ratio_min": float(
                gap_summary.get("pbd_hinge_benchmark_alignment_benchmark_rebar_ratio_min", 0.0)
            ),
            "pbd_hinge_benchmark_alignment_benchmark_rebar_ratio_max": float(
                gap_summary.get("pbd_hinge_benchmark_alignment_benchmark_rebar_ratio_max", 0.0)
            ),
            "pbd_hinge_benchmark_alignment_refresh_rebar_ratio_min": float(
                gap_summary.get("pbd_hinge_benchmark_alignment_refresh_rebar_ratio_min", 0.0)
            ),
            "pbd_hinge_benchmark_alignment_refresh_rebar_ratio_max": float(
                gap_summary.get("pbd_hinge_benchmark_alignment_refresh_rebar_ratio_max", 0.0)
            ),
            "panel_zone_3d_clash_ready": bool(gap_summary.get("panel_zone_3d_clash_ready", False)),
            "panel_zone_constructability_mode": str(gap_summary.get("panel_zone_constructability_mode", "")),
            "panel_zone_constructability_reason": str(gap_summary.get("panel_zone_constructability_reason", "")),
            "panel_zone_proxy_candidate_count": int(gap_summary.get("panel_zone_proxy_candidate_count", 0)),
            "panel_zone_source_artifact_kind": str(gap_summary.get("panel_zone_source_artifact_kind", "")),
            "panel_zone_source_artifact_path": str(gap_summary.get("panel_zone_source_artifact_path", "")),
            "panel_zone_source_contract_mode": str(gap_summary.get("panel_zone_source_contract_mode", "")),
            "panel_zone_instruction_sidecar_present": bool(
                gap_summary.get("panel_zone_instruction_sidecar_present", False)
            ),
            "panel_zone_instruction_sidecar_change_count": int(
                gap_summary.get("panel_zone_instruction_sidecar_change_count", 0)
            ),
            "panel_zone_instruction_sidecar_candidate_overlap_mode": str(
                gap_summary.get("panel_zone_instruction_sidecar_candidate_overlap_mode", "")
            ),
            "panel_zone_instruction_sidecar_overlap_row_count": int(
                gap_summary.get("panel_zone_instruction_sidecar_overlap_row_count", 0)
            ),
            "panel_zone_instruction_sidecar_overlap_member_count": int(
                gap_summary.get("panel_zone_instruction_sidecar_overlap_member_count", 0)
            ),
            "panel_zone_instruction_sidecar_overlap_group_count": int(
                gap_summary.get("panel_zone_instruction_sidecar_overlap_group_count", 0)
            ),
            "panel_zone_instruction_sidecar_evidence_model": str(
                gap_summary.get("panel_zone_instruction_sidecar_evidence_model", "")
            ),
            "panel_zone_instruction_sidecar_rebar_delivery_mode": str(
                gap_summary.get("panel_zone_instruction_sidecar_rebar_delivery_mode", "")
            ),
            "panel_zone_source_valid_row_counts": dict(gap_summary.get("panel_zone_source_valid_row_counts", {}) or {}),
            "panel_zone_source_overlap_member_counts": dict(
                gap_summary.get("panel_zone_source_overlap_member_counts", {}) or {}
            ),
            "panel_zone_source_candidate_scan_modes": dict(
                gap_summary.get("panel_zone_source_candidate_scan_modes", {}) or {}
            ),
            "panel_zone_source_bundle_modes": dict(gap_summary.get("panel_zone_source_bundle_modes", {}) or {}),
            "panel_zone_source_upstream_verification_tiers": dict(
                gap_summary.get("panel_zone_source_upstream_verification_tiers", {}) or {}
            ),
            "panel_zone_validated_source_row_count_total": int(
                gap_summary.get("panel_zone_validated_source_row_count_total", 0)
            ),
            "panel_zone_validated_source_overlap_member_count_min": int(
                gap_summary.get("panel_zone_validated_source_overlap_member_count_min", 0)
            ),
            "panel_zone_topology_capable_input": bool(gap_summary.get("panel_zone_topology_capable_input", False)),
            "panel_zone_true_3d_clash_verified": bool(gap_summary.get("panel_zone_true_3d_clash_verified", False)),
            "panel_zone_true_3d_anchorage_verified": bool(gap_summary.get("panel_zone_true_3d_anchorage_verified", False)),
            "panel_zone_missing_required_sources": gap_summary.get("panel_zone_missing_required_sources", []),
            "panel_zone_solver_verified_inbox_status_mode": str(
                gap_summary.get("panel_zone_solver_verified_inbox_status_mode", "")
            ),
            "panel_zone_solver_verified_inbox_has_input": bool(
                gap_summary.get("panel_zone_solver_verified_inbox_has_input", False)
            ),
            "panel_zone_solver_verified_pending_input": bool(
                gap_summary.get("panel_zone_solver_verified_pending_input", False)
            ),
            "panel_zone_solver_verified_input_mode_detected": str(
                gap_summary.get("panel_zone_solver_verified_input_mode_detected", "")
            ),
            "panel_zone_solver_verified_latest_consume_report_present": bool(
                gap_summary.get("panel_zone_solver_verified_latest_consume_report_present", False)
            ),
            "panel_zone_solver_verified_latest_consume_contract_pass": bool(
                gap_summary.get("panel_zone_solver_verified_latest_consume_contract_pass", False)
            ),
            "panel_zone_solver_verified_latest_consume_reason_code": str(
                gap_summary.get("panel_zone_solver_verified_latest_consume_reason_code", "")
            ),
            "panel_zone_solver_verified_source_origin_class": str(
                gap_summary.get("panel_zone_solver_verified_source_origin_class", "")
            ),
            "panel_zone_solver_verified_release_refresh_source_allowed": bool(
                gap_summary.get("panel_zone_solver_verified_release_refresh_source_allowed", False)
            ),
            "panel_zone_solver_verified_recommended_action": str(
                gap_summary.get("panel_zone_solver_verified_recommended_action", "")
            ),
            "foundation_optimization_ready": bool(gap_summary.get("foundation_optimization_ready", False)),
            "foundation_member_type_present": bool(gap_summary.get("foundation_member_type_present", False)),
            "foundation_member_type_count": int(gap_summary.get("foundation_member_type_count", 0)),
            "foundation_optimization_mode": str(gap_summary.get("foundation_optimization_mode", "")),
            "foundation_optimization_reason": str(gap_summary.get("foundation_optimization_reason", "")),
            "foundation_scope_source": str(gap_summary.get("foundation_scope_source", "")),
            "foundation_artifact_scan_mode": str(gap_summary.get("foundation_artifact_scan_mode", "")),
            "foundation_artifact_evidence_mode": str(gap_summary.get("foundation_artifact_evidence_mode", "")),
            "upstream_foundation_label_count": int(gap_summary.get("upstream_foundation_label_count", 0)),
            "raw_source_foundation_label_count": int(gap_summary.get("raw_source_foundation_label_count", 0)),
            "upstream_foundation_provenance_mode": str(gap_summary.get("upstream_foundation_provenance_mode", "")),
            "wind_tunnel_raw_mapping_ready": bool(gap_summary.get("wind_tunnel_raw_mapping_ready", False)),
            "wind_tunnel_mapping_mode": str(gap_summary.get("wind_tunnel_mapping_mode", "")),
            "wind_tunnel_mapping_reason": str(gap_summary.get("wind_tunnel_mapping_reason", "")),
            "promotion_reason_code": promotion_reason_code,
            "promotion_hold_for_review": promotion_hold_for_review,
            "hold_review_manifest": hold_review_manifest,
            "hold_review_packet_md": hold_review_packet_md,
            "hold_review_packet_pdf": hold_review_packet_pdf,
            "hold_review_ack_json": hold_review_ack_json,
            "open_gap_p0": int((gap_summary.get("open_gap_counts") or {}).get("P0", 0)),
            "open_gap_p1": int((gap_summary.get("open_gap_counts") or {}).get("P1", 0)),
            "open_gap_p2": int((gap_summary.get("open_gap_counts") or {}).get("P2", 0)),
            "midas_element_rows_total": int((midas.get("metrics") or {}).get("element_rows_total", 0)),
            "midas_element_rows_skipped": int((midas.get("metrics") or {}).get("element_rows_skipped", 0)),
            "midas_unknown_row_total": int((midas.get("metrics") or {}).get("unknown_row_total", 0)),
            "midas_semantic_load_binding_pass": bool(gap_summary.get("midas_semantic_load_binding_pass", False)),
            "midas_use_stld_block_count": int(gap_summary.get("midas_use_stld_block_count", 0)),
            "midas_semantic_load_case_count": int(gap_summary.get("midas_semantic_load_case_count", 0)),
            "midas_semantic_load_combination_count": int(gap_summary.get("midas_semantic_load_combination_count", 0)),
            "midas_bound_nodal_load_row_count": int(gap_summary.get("midas_bound_nodal_load_row_count", 0)),
            "midas_bound_selfweight_row_count": int(gap_summary.get("midas_bound_selfweight_row_count", 0)),
            "midas_bound_pressure_row_count": int(gap_summary.get("midas_bound_pressure_row_count", 0)),
            "midas_unbound_nodal_load_row_count": int(gap_summary.get("midas_unbound_nodal_load_row_count", 0)),
            "midas_unbound_selfweight_row_count": int(gap_summary.get("midas_unbound_selfweight_row_count", 0)),
            "midas_unbound_pressure_row_count": int(gap_summary.get("midas_unbound_pressure_row_count", 0)),
            "mgt_export_artifact_exists": bool(gap_summary.get("mgt_export_artifact_exists", False)),
            "mgt_export_contract_pass": bool(gap_summary.get("mgt_export_contract_pass", False)),
            "mgt_export_support_mode": str(gap_summary.get("mgt_export_support_mode", "")),
            "mgt_export_supported_change_count": int(gap_summary.get("mgt_export_supported_change_count", 0)),
            "mgt_export_unsupported_change_count": int(gap_summary.get("mgt_export_unsupported_change_count", 0)),
            "mgt_export_direct_patch_change_count": int(gap_summary.get("mgt_export_direct_patch_change_count", 0)),
            "mgt_export_direct_patch_supported_action_families": list(
                gap_summary.get("mgt_export_direct_patch_supported_action_families", []) or []
            ),
            "mgt_export_sidecar_supported_action_families": list(
                gap_summary.get("mgt_export_sidecar_supported_action_families", []) or []
            ),
            "mgt_export_direct_patch_action_family_counts": dict(
                gap_summary.get("mgt_export_direct_patch_action_family_counts", {}) or {}
            ),
            "mgt_export_direct_patch_action_family_label": str(
                gap_summary.get("mgt_export_direct_patch_action_family_label", "")
            ),
            "mgt_export_special_member_supported_action_family_counts": dict(
                gap_summary.get("mgt_export_special_member_supported_action_family_counts", {}) or {}
            ),
            "mgt_export_special_member_direct_patch_action_family_counts": dict(
                gap_summary.get("mgt_export_special_member_direct_patch_action_family_counts", {}) or {}
            ),
            "mgt_export_special_member_zero_touch_verified_action_family_counts": dict(
                gap_summary.get("mgt_export_special_member_zero_touch_verified_action_family_counts", {}) or {}
            ),
            "mgt_export_special_member_supported_action_family_label": str(
                gap_summary.get("mgt_export_special_member_supported_action_family_label", "")
            ),
            "mgt_export_special_member_direct_patch_action_family_label": str(
                gap_summary.get("mgt_export_special_member_direct_patch_action_family_label", "")
            ),
            "mgt_export_special_member_zero_touch_verified_action_family_label": str(
                gap_summary.get("mgt_export_special_member_zero_touch_verified_action_family_label", "")
            ),
            "mgt_export_material_level_rebar_payload_row_count": int(
                gap_summary.get("mgt_export_material_level_rebar_payload_row_count", 0)
            ),
            "mgt_export_material_level_rebar_payload_available_count": int(
                gap_summary.get("mgt_export_material_level_rebar_payload_available_count", 0)
            ),
            "mgt_export_group_local_rebar_payload_row_count": int(
                gap_summary.get("mgt_export_group_local_rebar_payload_row_count", 0)
            ),
            "mgt_export_group_local_rebar_payload_available_count": int(
                gap_summary.get("mgt_export_group_local_rebar_payload_available_count", 0)
            ),
            "mgt_export_group_local_connection_detailing_payload_row_count": int(
                gap_summary.get("mgt_export_group_local_connection_detailing_payload_row_count", 0)
            ),
            "mgt_export_group_local_connection_detailing_payload_available_count": int(
                gap_summary.get("mgt_export_group_local_connection_detailing_payload_available_count", 0)
            ),
            "mgt_export_group_local_detailing_payload_row_count": int(
                gap_summary.get("mgt_export_group_local_detailing_payload_row_count", 0)
            ),
            "mgt_export_group_local_detailing_payload_available_count": int(
                gap_summary.get("mgt_export_group_local_detailing_payload_available_count", 0)
            ),
            "mgt_export_connection_detailing_payload_namespace_mode": str(
                gap_summary.get("mgt_export_connection_detailing_payload_namespace_mode", "")
            ),
            "mgt_export_connection_detailing_payload_group_local_namespace_present": bool(
                gap_summary.get("mgt_export_connection_detailing_payload_group_local_namespace_present", False)
            ),
            "mgt_export_detailing_payload_namespace_mode": str(
                gap_summary.get("mgt_export_detailing_payload_namespace_mode", "")
            ),
            "mgt_export_detailing_payload_group_local_namespace_present": bool(
                gap_summary.get("mgt_export_detailing_payload_group_local_namespace_present", False)
            ),
            "mgt_export_connection_detailing_structured_payload_mapped_change_count": int(
                gap_summary.get("mgt_export_connection_detailing_structured_payload_mapped_change_count", 0)
            ),
            "mgt_export_connection_detailing_direct_patch_eligible_change_count": int(
                gap_summary.get("mgt_export_connection_detailing_direct_patch_eligible_change_count", 0)
            ),
            "mgt_export_detailing_direct_patch_eligible_change_count": int(
                gap_summary.get("mgt_export_detailing_direct_patch_eligible_change_count", 0)
            ),
            "mgt_export_detailing_structured_payload_mapped_change_count": int(
                gap_summary.get("mgt_export_detailing_structured_payload_mapped_change_count", 0)
            ),
            "mgt_export_connection_detailing_delivery_mode": str(
                gap_summary.get("mgt_export_connection_detailing_delivery_mode", "")
            ),
            "mgt_export_detailing_delivery_mode": str(gap_summary.get("mgt_export_detailing_delivery_mode", "")),
            "mgt_export_rebar_payload_namespace_mode": str(
                gap_summary.get("mgt_export_rebar_payload_namespace_mode", "")
            ),
            "mgt_export_rebar_payload_material_level_namespace_present": bool(
                gap_summary.get("mgt_export_rebar_payload_material_level_namespace_present", False)
            ),
            "mgt_export_rebar_payload_group_local_namespace_present": bool(
                gap_summary.get("mgt_export_rebar_payload_group_local_namespace_present", False)
            ),
            "mgt_export_rebar_delivery_mode": str(
                gap_summary.get("mgt_export_rebar_delivery_mode", "")
            ),
            "mgt_export_evidence_model": str(
                gap_summary.get("mgt_export_evidence_model", "")
            ),
            "mgt_export_rebar_direct_patch_eligible_change_count": int(
                gap_summary.get("mgt_export_rebar_direct_patch_eligible_change_count", 0)
            ),
            "mgt_export_patched_material_row_count": int(gap_summary.get("mgt_export_patched_material_row_count", 0)),
            "mgt_export_cloned_material_count": int(gap_summary.get("mgt_export_cloned_material_count", 0)),
            "mgt_export_rebar_direct_patch_ineligible_reason_counts": dict(
                gap_summary.get("mgt_export_rebar_direct_patch_ineligible_reason_counts", {}) or {}
            ),
            "mgt_export_rebar_direct_patch_ineligible_reason_label": str(
                gap_summary.get("mgt_export_rebar_direct_patch_ineligible_reason_label", "")
            ),
            "mgt_export_rebar_direct_patch_mapping_source_counts": dict(
                gap_summary.get("mgt_export_rebar_direct_patch_mapping_source_counts", {}) or {}
            ),
            "mgt_export_rebar_direct_patch_mapping_source_label": str(
                gap_summary.get("mgt_export_rebar_direct_patch_mapping_source_label", "")
            ),
            "mgt_export_instruction_sidecar_change_count": int(gap_summary.get("mgt_export_instruction_sidecar_change_count", 0)),
            "mgt_export_instruction_sidecar_action_family_counts": dict(
                gap_summary.get("mgt_export_instruction_sidecar_action_family_counts", {}) or {}
            ),
            "mgt_export_instruction_sidecar_action_family_label": str(
                gap_summary.get("mgt_export_instruction_sidecar_action_family_label", "")
            ),
            "mgt_export_instruction_sidecar_audit_only_change_count": int(
                gap_summary.get("mgt_export_instruction_sidecar_audit_only_change_count", 0)
            ),
            "mgt_export_instruction_sidecar_audit_only_action_family_counts": dict(
                gap_summary.get("mgt_export_instruction_sidecar_audit_only_action_family_counts", {}) or {}
            ),
            "mgt_export_instruction_sidecar_audit_only_action_family_label": str(
                gap_summary.get("mgt_export_instruction_sidecar_audit_only_action_family_label", "")
            ),
            "mgt_export_instruction_sidecar_manual_input_change_count": int(
                gap_summary.get("mgt_export_instruction_sidecar_manual_input_change_count", 0)
            ),
            "mgt_export_instruction_sidecar_manual_input_action_family_counts": dict(
                gap_summary.get("mgt_export_instruction_sidecar_manual_input_action_family_counts", {}) or {}
            ),
            "mgt_export_instruction_sidecar_manual_input_action_family_label": str(
                gap_summary.get("mgt_export_instruction_sidecar_manual_input_action_family_label", "")
            ),
            "mgt_export_audit_review_manifest_change_count": int(
                gap_summary.get("mgt_export_audit_review_manifest_change_count", 0)
            ),
            "mgt_export_audit_review_manifest_action_family_counts": dict(
                gap_summary.get("mgt_export_audit_review_manifest_action_family_counts", {}) or {}
            ),
            "mgt_export_audit_review_manifest_action_family_label": str(
                gap_summary.get("mgt_export_audit_review_manifest_action_family_label", "")
            ),
            "mgt_export_audit_review_packet_count": int(
                gap_summary.get("mgt_export_audit_review_packet_count", 0)
            ),
            "mgt_export_audit_review_packet_action_family_counts": dict(
                gap_summary.get("mgt_export_audit_review_packet_action_family_counts", {}) or {}
            ),
            "mgt_export_audit_review_packet_action_family_label": str(
                gap_summary.get("mgt_export_audit_review_packet_action_family_label", "")
            ),
            "mgt_export_audit_review_packet_followup_type_counts": dict(
                gap_summary.get("mgt_export_audit_review_packet_followup_type_counts", {}) or {}
            ),
            "mgt_export_audit_review_packet_followup_type_label": str(
                gap_summary.get("mgt_export_audit_review_packet_followup_type_label", "")
            ),
            "mgt_export_audit_review_packet_file_count": int(
                gap_summary.get("mgt_export_audit_review_packet_file_count", 0)
            ),
            "mgt_export_audit_review_packet_file_action_family_counts": dict(
                gap_summary.get("mgt_export_audit_review_packet_file_action_family_counts", {}) or {}
            ),
            "mgt_export_audit_review_packet_file_action_family_label": str(
                gap_summary.get("mgt_export_audit_review_packet_file_action_family_label", "")
            ),
            "mgt_export_audit_review_queue_item_count": int(
                gap_summary.get("mgt_export_audit_review_queue_item_count", 0)
            ),
            "mgt_export_audit_review_queue_pending_count": int(
                gap_summary.get("mgt_export_audit_review_queue_pending_count", 0)
            ),
            "mgt_export_audit_review_queue_acknowledged_count": int(
                gap_summary.get("mgt_export_audit_review_queue_acknowledged_count", 0)
            ),
            "mgt_export_audit_review_queue_status_counts": dict(
                gap_summary.get("mgt_export_audit_review_queue_status_counts", {}) or {}
            ),
            "mgt_export_audit_review_queue_status_label": str(
                gap_summary.get("mgt_export_audit_review_queue_status_label", "")
            ),
            "mgt_export_audit_review_queue_action_family_counts": dict(
                gap_summary.get("mgt_export_audit_review_queue_action_family_counts", {}) or {}
            ),
            "mgt_export_audit_review_queue_action_family_label": str(
                gap_summary.get("mgt_export_audit_review_queue_action_family_label", "")
            ),
            "mgt_export_audit_review_followup_item_count": int(
                gap_summary.get("mgt_export_audit_review_followup_item_count", 0)
            ),
            "mgt_export_audit_review_followup_open_item_count": int(
                gap_summary.get("mgt_export_audit_review_followup_open_item_count", 0)
            ),
            "mgt_export_audit_review_followup_closed_item_count": int(
                gap_summary.get("mgt_export_audit_review_followup_closed_item_count", 0)
            ),
            "mgt_export_audit_review_followup_action_counts": dict(
                gap_summary.get("mgt_export_audit_review_followup_action_counts", {}) or {}
            ),
            "mgt_export_audit_review_followup_action_label": str(
                gap_summary.get("mgt_export_audit_review_followup_action_label", "")
            ),
            "mgt_export_audit_review_followup_owner_counts": dict(
                gap_summary.get("mgt_export_audit_review_followup_owner_counts", {}) or {}
            ),
            "mgt_export_audit_review_followup_owner_label": str(
                gap_summary.get("mgt_export_audit_review_followup_owner_label", "")
            ),
            "mgt_export_audit_review_followup_review_owner_counts": dict(
                gap_summary.get("mgt_export_audit_review_followup_review_owner_counts", {}) or {}
            ),
            "mgt_export_audit_review_followup_review_owner_label": str(
                gap_summary.get("mgt_export_audit_review_followup_review_owner_label", "")
            ),
            "mgt_export_audit_review_followup_status_counts": dict(
                gap_summary.get("mgt_export_audit_review_followup_status_counts", {}) or {}
            ),
            "mgt_export_audit_review_followup_status_label": str(
                gap_summary.get("mgt_export_audit_review_followup_status_label", "")
            ),
            "mgt_export_audit_review_followup_sla_state_counts": dict(
                gap_summary.get("mgt_export_audit_review_followup_sla_state_counts", {}) or {}
            ),
            "mgt_export_audit_review_followup_sla_state_label": str(
                gap_summary.get("mgt_export_audit_review_followup_sla_state_label", "")
            ),
            "mgt_export_audit_review_followup_age_bucket_counts": dict(
                gap_summary.get("mgt_export_audit_review_followup_age_bucket_counts", {}) or {}
            ),
            "mgt_export_audit_review_followup_age_bucket_label": str(
                gap_summary.get("mgt_export_audit_review_followup_age_bucket_label", "")
            ),
            "mgt_export_audit_review_followup_overdue_item_count": int(
                gap_summary.get("mgt_export_audit_review_followup_overdue_item_count", 0)
            ),
            "mgt_export_audit_review_followup_oldest_open_age_hours": float(
                gap_summary.get("mgt_export_audit_review_followup_oldest_open_age_hours", 0.0)
            ),
            "mgt_export_audit_review_followup_oldest_open_packet_id": str(
                gap_summary.get("mgt_export_audit_review_followup_oldest_open_packet_id", "")
            ),
            "mgt_export_audit_review_followup_mode": str(
                gap_summary.get("mgt_export_audit_review_followup_mode", "")
            ),
            "mgt_export_audit_review_resolution_item_count": int(
                gap_summary.get("mgt_export_audit_review_resolution_item_count", 0)
            ),
            "mgt_export_audit_review_resolution_open_item_count": int(
                gap_summary.get("mgt_export_audit_review_resolution_open_item_count", 0)
            ),
            "mgt_export_audit_review_resolution_closed_item_count": int(
                gap_summary.get("mgt_export_audit_review_resolution_closed_item_count", 0)
            ),
            "mgt_export_audit_review_resolution_action_counts": dict(
                gap_summary.get("mgt_export_audit_review_resolution_action_counts", {}) or {}
            ),
            "mgt_export_audit_review_resolution_action_label": str(
                gap_summary.get("mgt_export_audit_review_resolution_action_label", "")
            ),
            "mgt_export_audit_review_resolution_owner_counts": dict(
                gap_summary.get("mgt_export_audit_review_resolution_owner_counts", {}) or {}
            ),
            "mgt_export_audit_review_resolution_owner_label": str(
                gap_summary.get("mgt_export_audit_review_resolution_owner_label", "")
            ),
            "mgt_export_audit_review_resolution_status_counts": dict(
                gap_summary.get("mgt_export_audit_review_resolution_status_counts", {}) or {}
            ),
            "mgt_export_audit_review_resolution_status_label": str(
                gap_summary.get("mgt_export_audit_review_resolution_status_label", "")
            ),
            "mgt_export_audit_review_resolution_mode": str(
                gap_summary.get("mgt_export_audit_review_resolution_mode", "")
            ),
            "mgt_export_instruction_sidecar_review_priority_counts": dict(
                gap_summary.get("mgt_export_instruction_sidecar_review_priority_counts", {}) or {}
            ),
            "mgt_export_instruction_sidecar_review_priority_label": str(
                gap_summary.get("mgt_export_instruction_sidecar_review_priority_label", "")
            ),
            "mgt_export_instruction_sidecar_followup_type_counts": dict(
                gap_summary.get("mgt_export_instruction_sidecar_followup_type_counts", {}) or {}
            ),
            "mgt_export_instruction_sidecar_followup_type_label": str(
                gap_summary.get("mgt_export_instruction_sidecar_followup_type_label", "")
            ),
            "mgt_export_cloned_section_count": int(gap_summary.get("mgt_export_cloned_section_count", 0)),
            "mgt_export_cloned_thickness_count": int(gap_summary.get("mgt_export_cloned_thickness_count", 0)),
            "mgt_export_retargeted_element_row_count": int(gap_summary.get("mgt_export_retargeted_element_row_count", 0)),
            "kds_compliance_rows": int((kds.get("summary") or {}).get("compliance_row_count", 0)),
            "kds_member_check_rows": int((kds.get("summary") or {}).get("member_check_row_count", 0)),
            "kds_clause_count": int((kds.get("summary") or {}).get("clause_count", 0)),
            "ndtha_residual_top_m_max_abs": _safe_float((ndtha_residual.get("summary") or {}).get("residual_top_displacement_m_max_abs", 0.0)),
            "ndtha_residual_drift_pct_max_abs": _safe_float((ndtha_residual.get("summary") or {}).get("residual_drift_ratio_pct_max_abs", 0.0)),
            "ndtha_residual_fallback_rate": _safe_float((ndtha_residual.get("summary") or {}).get("fallback_rate", 0.0)),
            "registry_artifact_count": int((registry.get("summary") or {}).get("artifact_count", 0)),
            "midas_section_library_summary_line": midas_section_library_summary_line,
            "material_constitutive_summary_line": material_constitutive_summary_line,
            "surface_interaction_benchmark_summary_line": surface_interaction_benchmark_summary_line,
            "midas_native_roundtrip_summary_line": midas_native_roundtrip_summary_line,
            "midas_native_roundtrip_writeback_diff_summary_line": midas_native_roundtrip_writeback_diff_summary_line,
            "korean_source_ingest_summary_line": korean_source_ingest_summary_line,
            "korean_source_ingest_source_count": int(korean_source_ingest_summary.get("source_count", 0) or 0),
            "korean_source_ingest_source_class_count": int(korean_source_ingest_summary.get("source_class_count", 0) or 0),
            "korean_source_ingest_collected_count": int(korean_source_ingest_summary.get("collected_count", 0) or 0),
            "korean_source_ingest_metadata_only_count": int(
                korean_source_ingest_summary.get("metadata_only_remote_candidate_count", 0) or 0
            ),
            "korean_source_ingest_rejected_count": int(korean_source_ingest_summary.get("rejected_count", 0) or 0),
            "korean_source_ingest_fingerprinted_count": int(
                korean_source_ingest_summary.get("fingerprinted_count", 0) or 0
            ),
            "korean_source_ingest_duplicate_sha_group_count": int(
                korean_source_ingest_summary.get("duplicate_sha_group_count", 0) or 0
            ),
            "measured_benchmark_breadth_summary_line": measured_benchmark_breadth_summary_line,
            "measured_benchmark_family_count": int(
                (measured_benchmark_breadth_report.get("summary") or {}).get("measured_family_count", 0) or 0
            ),
            "measured_benchmark_case_count": int(
                (measured_benchmark_breadth_report.get("summary") or {}).get("measured_case_count", 0) or 0
            ),
            "measured_benchmark_parser_ready_case_count": int(
                (measured_benchmark_breadth_report.get("summary") or {}).get("opensees_parser_ready_case_count", 0) or 0
            ),
            "opensees_canonical_breadth_summary_line": opensees_canonical_breadth_summary_line,
            "korean_structural_preview_queue_summary_line": korean_structural_preview_queue_summary_line,
            "korean_structural_preview_queue_candidate_total": int(
                korean_structural_preview_queue_summary.get("candidate_total", 0) or 0
            ),
            "korean_structural_preview_queue_pending_candidate_count": int(
                korean_structural_preview_queue_summary.get("pending_candidate_count", 0) or 0
            ),
            "korean_structural_preview_queue_state": str(korean_structural_preview_queue_summary.get("state", "") or ""),
            "irregular_structure_track_summary_line": irregular_structure_track_summary_line,
            "irregular_structure_summary_line": irregular_structure_summary_line,
            "irregular_structure_track_pass": bool(irregular_structure_gate_report.get("contract_pass", False)),
            "irregular_structure_family_count": int(irregular_structure_gate_summary.get("family_count", 0)),
            "irregular_structure_source_record_count": int(irregular_structure_gate_summary.get("source_record_count", 0)),
            "irregular_structure_local_ready_count": int(irregular_structure_gate_summary.get("local_ready_count", 0)),
            "irregular_structure_remote_candidate_count": int(irregular_structure_gate_summary.get("remote_candidate_count", 0)),
            "irregular_structure_collected_count": int(irregular_structure_gate_summary.get("collected_count", 0)),
            "irregular_structure_native_roundtrip_candidate_count": int(
                irregular_structure_gate_summary.get("native_roundtrip_candidate_count", 0)
            ),
            "irregular_structure_solver_benchmark_candidate_count": int(
                irregular_structure_gate_summary.get("solver_benchmark_candidate_count", 0)
            ),
            "irregular_structure_ai_learning_candidate_count": int(
                irregular_structure_gate_summary.get("ai_learning_candidate_count", 0)
            ),
            "irregular_structure_top5_count": int(irregular_structure_gate_summary.get("top5_count", len(irregular_top5_families))),
            "irregular_structure_top5_local_ready_count": int(irregular_top5_local_ready_count),
            "irregular_structure_top5_proxy_ready_count": int(irregular_top5_proxy_ready_count),
            "irregular_structure_top5_bridged_ready_count": int(irregular_top5_bridged_ready_count),
            "irregular_structure_top5_canonical_ready_count": int(irregular_top5_canonical_ready_count),
            "irregular_structure_top5_reference_collected_count": int(irregular_top5_reference_collected_count),
            "irregular_structure_top5_remote_needed_count": int(irregular_top5_remote_needed_count),
            "irregular_structure_top5_family_ids": [
                str(row.get("family_id", "") or "")
                for row in irregular_top5_families
                if str(row.get("family_id", "") or "").strip()
            ],
            "irregular_benchmark_execution_summary_line": irregular_benchmark_execution_summary_line,
            "irregular_benchmark_execution_ready_task_count": int(len(irregular_benchmark_execution_ready_tasks)),
            "irregular_benchmark_execution_blocked_task_count": int(len(irregular_benchmark_execution_blocked_tasks)),
            "irregular_benchmark_execution_task_count": int(
                len(irregular_benchmark_execution_ready_tasks) + len(irregular_benchmark_execution_blocked_tasks)
            ),
            "midas_native_roundtrip_corpus_case_count": int(midas_native_roundtrip_report_summary.get("corpus_case_count", 0)),
            "midas_native_roundtrip_actual_source_count": int(midas_native_roundtrip_report_summary.get("actual_source_count", 0)),
            "midas_native_roundtrip_native_text_case_count": int(midas_native_roundtrip_report_summary.get("native_text_case_count", 0)),
            "midas_native_roundtrip_public_native_text_case_count": int(midas_native_roundtrip_report_summary.get("public_native_text_case_count", 0)),
            "midas_native_roundtrip_public_raw_native_text_case_count": int(
                midas_native_roundtrip_report_summary.get("public_raw_native_text_case_count", 0)
            ),
            "midas_native_roundtrip_public_bridge_text_case_count": int(
                midas_native_roundtrip_report_summary.get("public_bridge_text_case_count", 0)
            ),
            "midas_native_roundtrip_public_archive_preview_text_case_count": int(midas_native_roundtrip_report_summary.get("public_archive_preview_text_case_count", 0)),
            "midas_native_roundtrip_public_archive_structural_preview_text_case_count": int(
                midas_native_roundtrip_report_summary.get("public_archive_structural_preview_text_case_count", 0)
            ),
            "midas_native_roundtrip_fixture_native_text_case_count": int(midas_native_roundtrip_report_summary.get("fixture_native_text_case_count", 0)),
            "midas_native_roundtrip_repo_native_text_case_count": int(midas_native_roundtrip_report_summary.get("repo_native_text_case_count", 0)),
            "midas_native_roundtrip_experiment_native_text_case_count": int(midas_native_roundtrip_report_summary.get("experiment_native_text_case_count", 0)),
            "midas_native_roundtrip_archive_case_count": int(midas_native_roundtrip_report_summary.get("archive_case_count", 0)),
            "midas_native_roundtrip_native_writeback_ready_count": int(midas_native_roundtrip_report_summary.get("native_writeback_ready_count", 0)),
            "midas_native_roundtrip_public_native_writeback_ready_count": int(midas_native_roundtrip_report_summary.get("public_native_writeback_ready_count", 0)),
            "midas_native_roundtrip_public_raw_native_writeback_ready_count": int(
                midas_native_roundtrip_report_summary.get("public_raw_native_writeback_ready_count", 0)
            ),
            "midas_native_roundtrip_public_bridge_writeback_ready_count": int(
                midas_native_roundtrip_report_summary.get("public_bridge_writeback_ready_count", 0)
            ),
            "midas_native_roundtrip_public_archive_preview_writeback_ready_count": int(midas_native_roundtrip_report_summary.get("public_archive_preview_writeback_ready_count", 0)),
            "midas_native_roundtrip_public_archive_structural_preview_writeback_ready_count": int(
                midas_native_roundtrip_report_summary.get("public_archive_structural_preview_writeback_ready_count", 0)
            ),
            "midas_native_roundtrip_public_source_writeback_ready_count": int(midas_native_roundtrip_report_summary.get("public_source_writeback_ready_count", 0)),
            "midas_native_roundtrip_exact_topology_archive_candidate_count": int(
                exact_topology_structural_preview_queue_summary.get(
                    "candidate_total",
                    midas_native_roundtrip_receipts_summary.get(
                        "exact_topology_structural_preview_candidate_total",
                        _count_exact_topology_archive_candidates(),
                    ),
                )
                or 0
            ),
            "midas_native_roundtrip_exact_topology_archive_candidate_rows": exact_topology_structural_preview_queue_rows,
            "midas_native_roundtrip_exact_topology_archive_pending_candidate_rows": exact_topology_structural_preview_queue_rows,
            "midas_native_roundtrip_exact_topology_archive_pending_candidate_count": int(
                exact_topology_structural_preview_queue_summary.get(
                    "pending_candidate_count",
                    midas_native_roundtrip_receipts_summary.get(
                        "exact_topology_structural_preview_pending_candidate_count",
                        len(exact_topology_structural_preview_queue_rows),
                    ),
                )
                or 0
            ),
            "midas_native_roundtrip_fixture_native_writeback_ready_count": int(midas_native_roundtrip_report_summary.get("fixture_native_writeback_ready_count", 0)),
            "midas_native_roundtrip_repo_native_writeback_ready_count": int(midas_native_roundtrip_report_summary.get("repo_native_writeback_ready_count", 0)),
            "midas_native_roundtrip_experiment_native_writeback_ready_count": int(midas_native_roundtrip_report_summary.get("experiment_native_writeback_ready_count", 0)),
            "midas_native_roundtrip_source_family_count": int(midas_native_roundtrip_report_summary.get("source_family_count", 0)),
            "midas_native_roundtrip_structure_type_count": int(midas_native_roundtrip_report_summary.get("structure_type_count", 0)),
            "midas_native_roundtrip_receipt_count": int(midas_native_roundtrip_receipts_summary.get("receipt_count", 0)),
            "midas_native_roundtrip_receipt_pass_count": int(midas_native_roundtrip_receipts_summary.get("receipt_pass_count", 0)),
            "midas_native_roundtrip_topology_stable_case_count": int(midas_native_roundtrip_receipts_summary.get("topology_stable_case_count", 0)),
            "midas_native_roundtrip_load_contract_stable_case_count": int(midas_native_roundtrip_receipts_summary.get("load_contract_stable_case_count", 0)),
            "midas_native_roundtrip_loadcomb_exact_case_count": int(midas_native_roundtrip_receipts_summary.get("loadcomb_exact_case_count", 0)),
            "midas_native_roundtrip_pending_review_total": int(midas_native_roundtrip_receipts_summary.get("pending_review_total", 0)),
            "midas_native_roundtrip_structure_type_batch_count": int(midas_native_roundtrip_receipts_summary.get("structure_type_batch_count", 0)),
            "korean_native_roundtrip_representative_count": int(len(korean_native_roundtrip_representative_rows)),
            "midas_native_roundtrip_taxonomy_case_counts": dict(midas_native_roundtrip_receipts_summary.get("taxonomy_case_counts", {}) or {}),
            "midas_native_roundtrip_taxonomy_card_family_histogram": dict(midas_native_roundtrip_receipts_summary.get("taxonomy_card_family_histogram", {}) or {}),
            "external_benchmark_case_onepage_count": int(len(external_benchmark_case_onepage_rows)),
        "midas_native_roundtrip_receipt_rows": midas_native_roundtrip_receipt_rows,
        "midas_native_roundtrip_structure_type_batches": midas_native_roundtrip_structure_type_batches,
        "midas_native_roundtrip_structure_type_batch_markdowns": midas_native_roundtrip_structure_type_batch_markdowns,
        "korean_native_roundtrip_representative_rows": korean_native_roundtrip_representative_rows,
        "midas_kds_row_provenance_export_summary_line": midas_kds_row_provenance_export_summary_line,
            "midas_kds_row_provenance_preview_rows": midas_kds_row_provenance_preview_rows,
            "midas_kds_row_provenance_clause_filter_rows": midas_kds_row_provenance_clause_filter_rows,
            "midas_kds_row_provenance_member_filter_rows": midas_kds_row_provenance_member_filter_rows,
            "midas_kds_row_provenance_hazard_filter_rows": midas_kds_row_provenance_hazard_filter_rows,
            "midas_kds_row_provenance_rule_family_filter_rows": midas_kds_row_provenance_rule_family_filter_rows,
            "nightly_smoke_reason_code": str((nightly_smoke or {}).get("reason_code", "")),
            "nightly_smoke_pass_rate": _safe_float(nightly_smoke_history_summary.get("pass_rate", 0.0)),
            "nightly_smoke_trial_feasible_rate": _safe_float(nightly_smoke_history_summary.get("trial_feasible_rate", 0.0)),
            "nightly_smoke_avg_trial_runtime_s": _safe_float(nightly_smoke_history_summary.get("avg_trial_runtime_s", 0.0)),
            "nightly_smoke_history_count": int(nightly_smoke_history_summary.get("count", 0)),
            "nightly_smoke_strict_recommendation": str(nightly_smoke_recommendation.get("recommendation", "")),
            "design_opt_long_feasible": bool((design_opt_long.get("summary") or {}).get("solver_feasible_final", False)),
            "design_opt_long_final_max_dcr": _safe_float((design_opt_long.get("summary") or {}).get("final_max_dcr", 0.0)),
            "design_opt_raw_max_drift_pct": design_opt_raw_max_drift,
            "design_opt_raw_residual_drift_pct": design_opt_raw_residual_drift,
            "design_opt_raw_max_dcr": design_opt_raw_max_dcr,
            "design_opt_repaired_compliance_max_drift_pct": design_opt_repaired_max_drift,
            "design_opt_repaired_compliance_residual_drift_pct": design_opt_repaired_residual_drift,
            "design_opt_repaired_compliance_max_dcr": design_opt_repaired_max_dcr,
            "design_opt_compliance_basis": design_opt_compliance_basis,
            "design_opt_repair_action_count": design_opt_repair_action_count,
            "design_opt_constructability_signal_gain_pct": design_opt_constructability_signal_gain_pct,
            "design_opt_baseline_constructability_avg": design_opt_baseline_constructability_avg,
            "design_opt_final_constructability_avg": design_opt_final_constructability_avg,
            "design_opt_baseline_detailing_complexity_avg": design_opt_baseline_detailing_complexity_avg,
            "design_opt_final_detailing_complexity_avg": design_opt_final_detailing_complexity_avg,
            "design_opt_selected_action_family_counts": design_opt_selected_action_family_counts,
            "design_opt_preview_supply_family_counts": design_opt_preview_supply_family_counts,
            "design_opt_preview_supply_family_mix_label": design_opt_preview_supply_family_mix_label,
            "design_opt_preview_missing_target_families_label": design_opt_preview_missing_target_families_label,
            "design_opt_previous_action_family_counts": design_opt_previous_action_family_counts,
            "design_opt_selected_family_mix_label": design_opt_selected_family_mix_label,
            "design_opt_selected_family_trend_label": design_opt_selected_family_trend_label,
            "design_opt_selected_dominant_family": str(design_opt_selected_dominant_family),
            "design_opt_selected_dominant_family_ratio": design_opt_selected_dominant_family_ratio,
            "design_opt_previous_dominant_family": str(design_opt_previous_dominant_family),
            "design_opt_previous_dominant_family_ratio": design_opt_previous_dominant_family_ratio,
            "design_opt_budget_mode": str((design_opt_budgeted.get("summary") or {}).get("budget_mode", "")),
            "design_opt_expected_feasible_probability": _safe_float((design_opt_budgeted.get("summary") or {}).get("expected_feasible_probability", 0.0)),
            "design_opt_expected_cost_reduction": _safe_float((design_opt_budgeted.get("summary") or {}).get("expected_cost_reduction", 0.0)),
            "design_opt_expected_constructability_gain": _safe_float((design_opt_budgeted.get("summary") or {}).get("expected_constructability_gain", 0.0)),
            "design_opt_objective_profile": str(design_opt_cost_summary.get("objective_profile", (design_opt_profile or {}).get("profile_name", ""))),
            "design_opt_cost_delta": _safe_float(design_opt_cost_summary.get("cost_reduction_proxy", 0.0)),
            "design_opt_changed_group_count": int(design_opt_cost_summary.get("changed_group_count", 0)),
            "design_opt_blocked_action_row_count": int(design_opt_cost_summary.get("blocked_action_row_count", 0)),
            "design_opt_blocked_illegal_by_mask": int((design_opt_cost_summary.get("blocked_reason_counts") or {}).get("illegal_by_mask", 0)),
            "design_opt_blocked_illegal_by_mask_family_label": str(
                design_opt_cost_summary.get("blocked_illegal_by_mask_family_label", "")
            ),
            "design_opt_blocked_no_cost_gain": int((design_opt_cost_summary.get("blocked_reason_counts") or {}).get("no_cost_gain", 0)),
            "design_opt_blocked_constructability_hard_gate": int(
                sum(
                    int(v)
                    for k, v in (design_opt_cost_summary.get("blocked_reason_counts") or {}).items()
                    if str(k).startswith("constructability_hard_gate:")
                )
            ),
            "design_opt_blocked_constructability_hard_gate_label": ", ".join(
                f"{str(k).split(':', 1)[1]}={int(v)}"
                for k, v in sorted((design_opt_cost_summary.get("blocked_reason_counts") or {}).items())
                if str(k).startswith("constructability_hard_gate:")
            ),
            "design_opt_blocked_constructability_hard_gate_family_label": str(
                design_opt_cost_summary.get("blocked_constructability_hard_gate_family_label", "")
            ),
            "design_opt_accepted_candidate_row_count": int(design_opt_cost_summary.get("accepted_candidate_explain_row_count", 0)),
            "design_opt_accepted_candidate_selected_count": int(design_opt_cost_summary.get("accepted_candidate_selected_count", 0)),
            "design_opt_accepted_candidate_unselected_count": int(design_opt_cost_summary.get("accepted_candidate_unselected_count", 0)),
            "design_opt_blocked_no_cost_group_count": int(design_opt_cost_summary.get("blocked_no_cost_group_count", 0)),
            "design_opt_blocked_no_cost_explain_row_count": int(design_opt_cost_summary.get("blocked_no_cost_explain_row_count", 0)),
            "design_opt_concrete_usage_reduction_pct": _safe_float(design_opt_cost_summary.get("concrete_usage_reduction_pct", 0.0)),
            "design_opt_steel_reduction_pct": _safe_float(design_opt_cost_summary.get("steel_reduction_pct", 0.0)),
            "design_opt_rebar_reduction_pct": _safe_float(design_opt_cost_summary.get("rebar_reduction_pct", 0.0)),
            "design_opt_congestion_reduction_pct": _safe_float(design_opt_cost_summary.get("congestion_reduction_pct", 0.0)),
            "design_opt_detailing_simplification_pct": _safe_float(design_opt_cost_summary.get("detailing_simplification_pct", 0.0)),
            "design_opt_overdesign_margin_reduction_pct": _safe_float(design_opt_cost_summary.get("overdesign_margin_reduction_pct", 0.0)),
            "design_opt_final_safety_margin_retained_pct": _safe_float(design_opt_cost_summary.get("final_safety_margin_retained_pct", 0.0)),
            "design_opt_ablation_warning_count": int((design_opt_ablation.get("summary") or {}).get("warning_count", 0)),
            "design_opt_entrypoint_report_count": int(sum(1 for row in design_opt_entrypoint_rows if bool(row.get("report_exists", False)))),
            "design_opt_entrypoint_pass_count": int(sum(1 for row in design_opt_entrypoint_rows if bool(row.get("contract_pass", False)))),
        },
        "derived": {
            "frame_case_count": int((frame.get("summary") or {}).get("case_count", 0)),
            "frame_drift_error_pct_p95": _safe_float((frame.get("summary") or {}).get("drift_error_pct_p95", 0.0)),
            "frame_top_disp_error_pct_p95": _safe_float((frame.get("summary") or {}).get("top_disp_error_pct_p95", 0.0)),
            "wind_case_count": int((wind.get("summary") or {}).get("selected_case_count", 0)),
            "wind_max_drift_pct": _safe_float((wind.get("summary") or {}).get("max_drift_ratio_pct_all_cases", 0.0)),
            "wind_residual_drift_pct": _safe_float((wind.get("summary") or {}).get("residual_drift_pct_max_abs", 0.0)),
            "ssi_case_count": int((ssi.get("summary") or {}).get("selected_case_count", 0)),
            "ssi_nonlinear_ratio_span": _safe_float((ssi.get("summary") or {}).get("nonlinear_ratio_span", 0.0)),
            "ssi_residual_drift_pct": _safe_float((ssi.get("summary") or {}).get("ssi_residual_drift_pct_max_abs", 0.0)),
            "design_opt_change_rows": int(len(committee_summary.get("design_change_rows", []))) if isinstance(committee_summary.get("design_change_rows"), list) else 0,
            "design_opt_long_final_max_dcr": _safe_float((design_opt_long.get("summary") or {}).get("final_max_dcr", 0.0)),
            "design_opt_cost_delta": _safe_float(design_opt_cost_summary.get("cost_reduction_proxy", 0.0)),
        },
        "artifacts": {
            "nightly_smoke_history_png": smoke_history_png,
            "measured_chain_category_png": measured_chain_category_png,
            "authority_catalog_routing_diff_json": authority_catalog_routing_diff_json,
            "midas_kds_row_provenance_export_json": midas_kds_row_provenance_export_json,
            "midas_kds_row_provenance_export_csv": midas_kds_row_provenance_export_csv,
            "midas_kds_row_provenance_export_report": midas_kds_row_provenance_export_report,
            "midas_native_roundtrip_gate_report_json": midas_native_roundtrip_gate_report_json,
            "midas_native_roundtrip_corpus_manifest_json": midas_native_roundtrip_corpus_manifest_json,
            "midas_native_roundtrip_receipts_report_json": midas_native_roundtrip_receipts_report_json,
            "midas_native_roundtrip_appendix_markdown": midas_native_roundtrip_appendix_markdown,
            "midas_native_roundtrip_appendix_json": midas_native_roundtrip_appendix_json,
            "exact_topology_structural_preview_promotion_queue_json": exact_topology_structural_preview_promotion_queue_json,
            "exact_topology_structural_preview_promotion_queue_md": exact_topology_structural_preview_promotion_queue_md,
            "irregular_structure_gate_report_json": irregular_structure_gate_report_json,
            "irregular_structure_source_catalog_json": irregular_structure_source_catalog_json,
            "irregular_structure_triage_report_json": irregular_structure_triage_report_json,
            "irregular_structure_collection_report_json": irregular_structure_collection_report_json,
            "irregular_top5_execution_manifest_json": irregular_top5_execution_manifest_json,
            "irregular_benchmark_execution_manifest_json": irregular_benchmark_execution_manifest_json,
            "irregular_benchmark_receipt_index_json": irregular_benchmark_receipt_index_json,
            "external_benchmark_case_onepage_dir": "external_benchmark_case_onepages",
            "external_benchmark_case_onepage_index_md": "external_benchmark_case_onepages/index.md",
            "external_benchmark_case_onepage_index_html": "external_benchmark_case_onepages/index.html",
            "external_benchmark_case_onepage_index_pdf": "external_benchmark_case_onepages/index.pdf",
            "external_benchmark_submission_readiness_json": str(
                args.external_benchmark_submission_readiness_report
            ),
            "external_benchmark_execution_manifest_json": str(
                args.external_benchmark_execution_manifest_report
            ),
            "external_benchmark_execution_status_manifest_json": str(
                args.external_benchmark_execution_status_manifest_report
            ),
            "audit_review_decision_batch_template_json": str(audit_review_decision_batch_template_json),
            "audit_review_decision_batch_template_md": str(audit_review_decision_batch_template_json.with_suffix(".md")),
            "audit_review_decision_batch_approve_all_attested_example_json": str(
                audit_review_decision_batch_approve_all_attested_example_json
            ),
            "audit_review_decision_batch_approve_all_attested_example_md": str(
                audit_review_decision_batch_approve_all_attested_example_json.with_suffix(".md")
            ),
            "audit_review_decision_batch_mixed_attested_example_json": str(
                audit_review_decision_batch_mixed_attested_example_json
            ),
            "audit_review_decision_batch_mixed_attested_example_md": str(
                audit_review_decision_batch_mixed_attested_example_json.with_suffix(".md")
            ),
            "external_benchmark_submission_preview_approve_all_json": str(
                external_benchmark_submission_preview_approve_all_json
            ),
            "external_benchmark_submission_preview_approve_all_md": str(
                external_benchmark_submission_preview_approve_all_json.with_suffix(".md")
            ),
            "external_benchmark_submission_preview_reject_one_json": str(
                external_benchmark_submission_preview_reject_one_json
            ),
            "external_benchmark_submission_preview_reject_one_md": str(
                external_benchmark_submission_preview_reject_one_json.with_suffix(".md")
            ),
            "audit_review_decision_batch_run_report_json": str(
                audit_review_decision_batch_run_report_json
            ),
            "audit_review_decision_batch_approve_all_live_ready_template_json": str(
                audit_review_decision_batch_approve_all_live_ready_template_json
            ),
            "audit_review_decision_batch_live_preview_json": str(
                audit_review_decision_batch_live_preview_json
            ),
            "hold_review_manifest": hold_review_manifest,
            "hold_review_packet_md": hold_review_packet_md,
            "hold_review_packet_pdf": hold_review_packet_pdf,
            "hold_review_ack_json": hold_review_ack_json,
        },
        "midas_kds_row_provenance_preview_rows": midas_kds_row_provenance_preview_rows,
        "midas_kds_row_provenance_clause_filter_rows": midas_kds_row_provenance_clause_filter_rows,
        "midas_kds_row_provenance_member_filter_rows": midas_kds_row_provenance_member_filter_rows,
        "midas_kds_row_provenance_hazard_filter_rows": midas_kds_row_provenance_hazard_filter_rows,
        "midas_kds_row_provenance_rule_family_filter_rows": midas_kds_row_provenance_rule_family_filter_rows,
        "external_benchmark_case_onepage_rows": external_benchmark_case_onepage_rows,
        "korean_native_roundtrip_representative_rows": korean_native_roundtrip_representative_rows,
        "exact_topology_structural_preview_promotion_queue_rows": _pending_exact_topology_archive_candidate_rows(),
        "irregular_top5_families": irregular_top5_families,
        "irregular_canonical_promotion_queue_rows": irregular_canonical_promotion_queue_rows,
        "irregular_benchmark_execution_ready_tasks": irregular_benchmark_execution_ready_tasks,
        "irregular_benchmark_execution_blocked_tasks": irregular_benchmark_execution_blocked_tasks,
        "residual_holdout_buckets": residual_holdout_buckets,
        "residual_holdout_detail_rows": residual_holdout_detail_rows,
        "residual_holdout_matrix_rows": residual_holdout_matrix_rows,
        "authority_catalog_routing_diff": authority_catalog_routing_diff,
        "authority_catalog_diff_change_count": int(authority_catalog_routing_diff.get("change_count", 0)),
        "authority_catalog_diff_added_count": int(authority_catalog_routing_diff.get("added_count", 0)),
        "authority_catalog_diff_removed_count": int(authority_catalog_routing_diff.get("removed_count", 0)),
        "authority_catalog_diff_baseline_seeded": bool(authority_catalog_routing_diff.get("baseline_seeded", False)),
        "authority_catalog_routing_warning_active": bool(int(authority_catalog_routing_diff.get("change_count", 0) or 0) > 0),
        "promotion_reason_code": promotion_reason_code,
        "promotion_hold_for_review": promotion_hold_for_review,
        "hold_review_manifest": hold_review_manifest,
        "hold_review_packet_md": hold_review_packet_md,
        "hold_review_packet_pdf": hold_review_packet_pdf,
        "hold_review_ack_json": hold_review_ack_json,
        "nightly_smoke_recent_samples": smoke_recent_samples,
        "nightly_smoke_trend": smoke_trend,
    }

    native_roundtrip_artifacts = _dedupe_artifacts(
        [
            midas_native_roundtrip_gate_report_json,
            midas_native_roundtrip_corpus_manifest_json,
            midas_native_roundtrip_receipts_report_json,
            midas_native_roundtrip_appendix_markdown,
            midas_native_roundtrip_appendix_json,
            exact_topology_structural_preview_promotion_queue_json,
            exact_topology_structural_preview_promotion_queue_md,
        ]
        + [str(row.get("receipt_md", "") or "") for row in midas_native_roundtrip_receipt_rows]
        + [str(row.get("receipt_json", "") or "") for row in midas_native_roundtrip_receipt_rows]
        + midas_native_roundtrip_structure_type_batch_markdowns
    )
    full_artifacts = _dedupe_artifacts(
        FULL_ARTIFACTS
        + ([smoke_history_png] if smoke_history_png else [])
        + ([measured_chain_category_png] if measured_chain_category_png else [])
        + ([authority_catalog_routing_diff_json] if authority_catalog_routing_diff_json else [])
        + ([str(args.external_benchmark_submission_readiness_report)] if str(args.external_benchmark_submission_readiness_report) else [])
        + ([hold_review_manifest] if hold_review_manifest else [])
        + ([hold_review_packet_md] if hold_review_packet_md else [])
        + ([hold_review_packet_pdf] if hold_review_packet_pdf else [])
        + ([hold_review_ack_json] if hold_review_ack_json else [])
        + _existing_artifact_paths(
            [
                str(args.irregular_structure_gate_report),
                str(args.irregular_structure_source_catalog),
                str(args.irregular_structure_triage_report),
                str(args.irregular_structure_collection_report),
                str(args.irregular_top5_execution_manifest),
                str(args.irregular_benchmark_execution_manifest),
                irregular_benchmark_receipt_index_json,
            ]
        )
        + _existing_artifact_paths(
            [str(row.get("benchmark_receipt_json", "") or "") for row in irregular_benchmark_receipt_rows]
            + [str(row.get("benchmark_receipt_md", "") or "") for row in irregular_benchmark_receipt_rows]
        )
        + native_roundtrip_artifacts
    )
    light_artifacts = _dedupe_artifacts(
        LIGHTWEIGHT_ARTIFACTS
        + ([smoke_history_png] if smoke_history_png else [])
        + ([measured_chain_category_png] if measured_chain_category_png else [])
        + ([authority_catalog_routing_diff_json] if authority_catalog_routing_diff_json else [])
        + ([str(args.external_benchmark_submission_readiness_report)] if str(args.external_benchmark_submission_readiness_report) else [])
        + ([hold_review_manifest] if hold_review_manifest else [])
        + ([hold_review_packet_md] if hold_review_packet_md else [])
        + ([hold_review_packet_pdf] if hold_review_packet_pdf else [])
        + ([hold_review_ack_json] if hold_review_ack_json else [])
        + _existing_artifact_paths(
            [
                str(args.irregular_structure_gate_report),
                str(args.irregular_structure_source_catalog),
                str(args.irregular_structure_triage_report),
                str(args.irregular_structure_collection_report),
                str(args.irregular_top5_execution_manifest),
                str(args.irregular_benchmark_execution_manifest),
                irregular_benchmark_receipt_index_json,
            ]
        )
        + _existing_artifact_paths(
            [str(row.get("benchmark_receipt_json", "") or "") for row in irregular_benchmark_receipt_rows]
            + [str(row.get("benchmark_receipt_md", "") or "") for row in irregular_benchmark_receipt_rows]
        )
        + native_roundtrip_artifacts
    )

    bundle_dir, bundle_zip, summary_json, summary_md, summary_html, summary_pdf, removed = _build_bundle(
        release_dir=release_dir,
        bundle_name=bundle_name,
        artifacts=full_artifacts,
        summary=summary,
        prune_old=bool(args.prune_old),
        prune_prefix="external_validation_submission_",
    )
    latest_payload = {
        "bundle_id": bundle_id,
        "generated_at": summary["generated_at"],
        "dir": str(bundle_dir),
        "zip": str(bundle_zip),
        "summary_json": str(summary_json),
        "summary_md": str(summary_md),
        "summary_html": str(summary_html),
        "summary_pdf": str(summary_pdf),
        "pruned_previous": removed,
    }
    Path(args.latest_pointer).write_text(json.dumps(latest_payload, indent=2), encoding="utf-8")

    if bool(args.emit_lightweight):
        (
            light_dir,
            light_zip,
            light_summary_json,
            light_summary_md,
            light_summary_html,
            light_summary_pdf,
            light_removed,
        ) = _build_bundle(
            release_dir=release_dir,
            bundle_name=light_bundle_name,
            artifacts=light_artifacts,
            summary=summary,
            prune_old=bool(args.prune_old),
            prune_prefix="external_validation_light_submission_",
        )
        light_payload = {
            "bundle_id": bundle_id,
            "generated_at": summary["generated_at"],
            "dir": str(light_dir),
            "zip": str(light_zip),
            "summary_json": str(light_summary_json),
            "summary_md": str(light_summary_md),
            "summary_html": str(light_summary_html),
            "summary_pdf": str(light_summary_pdf),
            "pruned_previous": light_removed,
        }
        Path(args.light_latest_pointer).write_text(json.dumps(light_payload, indent=2), encoding="utf-8")

    print(f"Wrote external validation bundle: {bundle_dir}")
    print(f"Wrote external validation zip: {bundle_zip}")
    print(f"Wrote external validation latest pointer: {args.latest_pointer}")
    if bool(args.emit_lightweight):
        print(f"Wrote lightweight external validation latest pointer: {args.light_latest_pointer}")


if __name__ == "__main__":
    main()
