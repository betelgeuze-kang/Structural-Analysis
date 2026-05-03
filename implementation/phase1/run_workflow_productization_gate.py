#!/usr/bin/env python3
"""Track workflow/interoperability productization readiness for accelerated coverage releases."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any

from runtime_contracts import InputContractError, validate_input_contract

REPO_ROOT = Path(__file__).resolve().parents[2]

REASONS = {
    "PASS": "workflow/interoperability productization evidence is present for signed release, audit/approval flow, viewer review and results-explorer traceability, provenance export, and bounded round-trip delivery",
    "ERR_INVALID_INPUT": "invalid workflow productization gate input",
    "ERR_SIGNED_RELEASE": "signed release registry evidence is incomplete",
    "ERR_AUTHORING_AUTOMATION": "authoring automation evidence is incomplete",
    "ERR_AUDIT_APPROVAL": "audit or approval workflow evidence is incomplete",
    "ERR_AUDIT_ACTIONS": "audit queue/followup/resolution automation evidence is incomplete",
    "ERR_AUTO_APPROVED_SUBSET": "auto-approved package subset evidence is incomplete",
    "ERR_SIGNED_SUBMISSION_BUNDLE": "signed submission bundle evidence is incomplete",
    "ERR_VIEWER_RESULTS": "viewer results/review surface evidence is incomplete",
    "ERR_RESULTS_EXPLORER_TRACEABILITY": "results explorer traceability/rerun/audit evidence is incomplete",
    "ERR_PROVENANCE_EXPORT": "row provenance export evidence is incomplete",
    "ERR_NATIVE_MIDAS_ROUNDTRIP": "native MIDAS roundtrip/write-back evidence is incomplete",
    "ERR_BOUNDED_ROUNDTRIP": "bounded interoperability round-trip evidence is incomplete",
    "ERR_IRREGULAR_STRUCTURE_TRACK": "irregular structure track evidence is incomplete",
}

INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "release_registry_report",
        "midas_interoperability_report",
        "midas_native_roundtrip_report",
        "row_provenance_export_report",
        "viewer_json",
        "viewer_html",
        "irregular_structure_source_catalog",
        "irregular_structure_priority_families",
        "irregular_structure_triage_report",
        "irregular_structure_collection_report",
        "irregular_structure_gate_report",
        "irregular_top5_execution_manifest",
        "korean_source_ingest_gate_report",
        "korean_structural_preview_promotion_queue",
        "out",
    ],
    "properties": {
        "release_registry_report": {"type": "string", "minLength": 1},
        "midas_interoperability_report": {"type": "string", "minLength": 1},
        "midas_native_roundtrip_report": {"type": "string", "minLength": 1},
        "row_provenance_export_report": {"type": "string", "minLength": 1},
        "viewer_json": {"type": "string", "minLength": 1},
        "viewer_html": {"type": "string", "minLength": 1},
        "irregular_structure_source_catalog": {"type": "string", "minLength": 1},
        "irregular_structure_priority_families": {"type": "string", "minLength": 1},
        "irregular_structure_triage_report": {"type": "string", "minLength": 1},
        "irregular_structure_collection_report": {"type": "string", "minLength": 1},
        "irregular_structure_gate_report": {"type": "string", "minLength": 1},
        "irregular_top5_execution_manifest": {"type": "string", "minLength": 1},
        "irregular_benchmark_execution_manifest": {"type": "string", "minLength": 1},
        "korean_source_ingest_gate_report": {"type": "string", "minLength": 1},
        "korean_structural_preview_promotion_queue": {"type": "string", "minLength": 1},
        "out": {"type": "string", "minLength": 1},
    },
}


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


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


def _normalize_int(value: Any, fallback: int = 0) -> int:
    try:
        if value in (None, ""):
            raise ValueError
        return int(value)
    except Exception:
        return int(fallback)


def _extract_contact_coupling_surface(
    summary_label: str,
    *,
    support_family_count: Any = None,
    proxy_family_count: Any = None,
    assembled_depth_value: Any = None,
) -> dict[str, Any]:
    text = str(summary_label or "").strip()
    match = re.search(
        r"support families=(\d+)\s*\|\s*proxy families=(\d+)\s*\|\s*assembled depth=(\d+)",
        text,
    )
    parsed_support_family_count = int(match.group(1)) if match else 0
    parsed_proxy_family_count = int(match.group(2)) if match else 0
    parsed_assembled_depth_value = int(match.group(3)) if match else 0
    try:
        normalized_support_family_count = int(
            support_family_count if support_family_count not in (None, "") else parsed_support_family_count
        )
    except Exception:
        normalized_support_family_count = parsed_support_family_count
    try:
        normalized_proxy_family_count = int(
            proxy_family_count if proxy_family_count not in (None, "") else parsed_proxy_family_count
        )
    except Exception:
        normalized_proxy_family_count = parsed_proxy_family_count
    try:
        normalized_assembled_depth_value = int(
            assembled_depth_value if assembled_depth_value not in (None, "") else parsed_assembled_depth_value
        )
    except Exception:
        normalized_assembled_depth_value = parsed_assembled_depth_value
    coupling_summary_label = ""
    if normalized_support_family_count or normalized_proxy_family_count or normalized_assembled_depth_value:
        coupling_summary_label = (
            f"support families={normalized_support_family_count} | "
            f"proxy families={normalized_proxy_family_count} | "
            f"assembled depth={normalized_assembled_depth_value}"
        )
    coupling_pass = bool(
        not coupling_summary_label
        or (
            normalized_support_family_count > 0
            and normalized_proxy_family_count > 0
            and normalized_assembled_depth_value > 0
        )
    )
    return {
        "summary_label": coupling_summary_label,
        "support_family_count": normalized_support_family_count,
        "proxy_family_count": normalized_proxy_family_count,
        "assembled_depth_value": normalized_assembled_depth_value,
        "pass": coupling_pass,
    }


def _extract_general_fe_contact_surface(
    summary_line: str,
    *,
    surface_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    text = str(summary_line or "").strip()
    payload = surface_payload if isinstance(surface_payload, dict) else {}

    coupling_match = re.search(r"coupling_depth=(\d+)", text)
    support_match = re.search(r"support_families=(\d+)(?:/(\d+))?", text)
    proxy_match = re.search(r"proxy_families=(\d+)(?:/(\d+))?", text)
    parsed_coupling_depth_value = int(coupling_match.group(1)) if coupling_match else 0
    parsed_support_family_count = int(support_match.group(1)) if support_match else 0
    parsed_support_family_expected_count = (
        int(support_match.group(2)) if support_match and support_match.group(2) else parsed_support_family_count
    )
    parsed_proxy_family_count = int(proxy_match.group(1)) if proxy_match else 0
    parsed_proxy_family_expected_count = (
        int(proxy_match.group(2)) if proxy_match and proxy_match.group(2) else parsed_proxy_family_count
    )

    coupling_depth_value = _normalize_int(
        payload.get("coupling_depth_value", payload.get("coupling_depth_score")),
        fallback=parsed_coupling_depth_value,
    )
    support_family_count = _normalize_int(
        payload.get("support_family_count", payload.get("support_search_family_count")),
        fallback=parsed_support_family_count,
    )
    support_family_expected_count = _normalize_int(
        payload.get(
            "support_family_expected_count",
            payload.get(
                "support_family_requirement_count",
                payload.get("support_search_family_requirement_count"),
            ),
        ),
        fallback=parsed_support_family_expected_count,
    )
    proxy_family_count = _normalize_int(
        payload.get("proxy_family_count", payload.get("node_to_surface_proxy_family_count")),
        fallback=parsed_proxy_family_count,
    )
    proxy_family_expected_count = _normalize_int(
        payload.get(
            "proxy_family_expected_count",
            payload.get(
                "proxy_family_requirement_count",
                payload.get("node_to_surface_proxy_family_requirement_count"),
            ),
        ),
        fallback=parsed_proxy_family_expected_count,
    )

    normalized_summary_line = text
    if not normalized_summary_line:
        for key in ("summary_line", "summary_label"):
            candidate = str(payload.get(key, "") or "").strip()
            if candidate:
                normalized_summary_line = candidate
                break

    support_label = ""
    if support_family_count or support_family_expected_count:
        support_total = support_family_expected_count or support_family_count
        support_label = f"{support_family_count}/{support_total}"
    proxy_label = ""
    if proxy_family_count or proxy_family_expected_count:
        proxy_total = proxy_family_expected_count or proxy_family_count
        proxy_label = f"{proxy_family_count}/{proxy_total}"

    compact_summary_label = str(payload.get("compact_summary_label", "") or "").strip()
    if not compact_summary_label:
        compact_parts = [
            part
            for part in (
                f"coupling depth={coupling_depth_value}" if coupling_depth_value else "",
                f"support families={support_label}" if support_label else "",
                f"proxy families={proxy_label}" if proxy_label else "",
            )
            if part
        ]
        compact_summary_label = " | ".join(compact_parts)

    surface_pass = bool(
        not compact_summary_label
        or (
            coupling_depth_value > 0
            and support_family_count > 0
            and proxy_family_count > 0
            and (
                not support_family_expected_count
                or support_family_count >= support_family_expected_count
            )
            and (
                not proxy_family_expected_count
                or proxy_family_count >= proxy_family_expected_count
            )
        )
    )
    if not normalized_summary_line and compact_summary_label:
        summary_parts = [
            part
            for part in (
                f"coupling_depth={coupling_depth_value}" if coupling_depth_value else "",
                f"support_families={support_label}" if support_label else "",
                f"proxy_families={proxy_label}" if proxy_label else "",
            )
            if part
        ]
        if summary_parts:
            normalized_summary_line = (
                f"General FE contact matrix: {'PASS' if surface_pass else 'CHECK'} | "
                + " | ".join(summary_parts)
            )

    return {
        "summary_line": normalized_summary_line,
        "compact_summary_label": compact_summary_label,
        "coupling_depth_value": coupling_depth_value,
        "support_family_count": support_family_count,
        "support_family_expected_count": support_family_expected_count,
        "proxy_family_count": proxy_family_count,
        "proxy_family_expected_count": proxy_family_expected_count,
        "pass": surface_pass,
    }


def _resolve_repo_path(path_like: str, *, base_dir: Path) -> Path:
    candidate = Path(str(path_like))
    if candidate.is_absolute():
        return candidate
    if str(candidate).startswith("implementation/"):
        return REPO_ROOT / candidate
    return base_dir / candidate


def _repo_release_scoped(path: Path) -> bool:
    try:
        path.resolve().relative_to((REPO_ROOT / "implementation/phase1/release").resolve())
        return True
    except Exception:
        return False


def _load_repo_mgt_export_summary_if_available(*, release_registry_path: Path) -> dict[str, Any]:
    if not _repo_release_scoped(release_registry_path):
        return {}
    payload = _load_json(
        REPO_ROOT / "implementation/phase1/open_data/midas/midas_generator_33.optimized.export_report.json"
    )
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    return summary if isinstance(summary, dict) else {}


def _count_exact_topology_archive_candidates() -> int:
    count = 0
    base_dir = REPO_ROOT / "implementation/phase1/open_data/midas/quality_corpus/bridged"
    for report_path in sorted(base_dir.glob("*_decoded_preview/bridge_report.json")):
        payload = _load_json(report_path)
        if not payload:
            continue
        if not bool(payload.get("viewer_ready", False)):
            continue
        if not bool(payload.get("exact_topology_candidate", False)):
            continue
        count += 1
    return count


def _collect_generated_workflow_artifacts(
    *,
    release_registry_report: dict[str, Any],
    release_registry_path: Path,
) -> dict[str, Any]:
    base_dir = release_registry_path.parent
    signature = release_registry_report.get("signature") if isinstance(release_registry_report.get("signature"), dict) else {}
    registry_body = (
        release_registry_report.get("registry_body")
        if isinstance(release_registry_report.get("registry_body"), dict)
        else {}
    )
    artifact_rows = registry_body.get("artifacts") if isinstance(registry_body.get("artifacts"), list) else []

    signature_paths = []
    for key in ("public_key_path", "signature_out"):
        raw = str(signature.get(key, "") or "").strip()
        if raw:
            signature_paths.append(_resolve_repo_path(raw, base_dir=base_dir))

    release_artifact_paths = []
    for row in artifact_rows:
        if not isinstance(row, dict):
            continue
        raw = str(row.get("path", "") or "").strip()
        if not raw:
            continue
        release_artifact_paths.append(_resolve_repo_path(raw, base_dir=base_dir))

    kickoff_dir = base_dir / "external_benchmark_kickoff"
    generated_authoring_paths = [
        kickoff_dir / "audit_review_decision_batch_template.json",
        kickoff_dir / "audit_review_decision_batch_template.md",
        kickoff_dir / "audit_review_decision_batch_approve_all.attested_example.json",
        kickoff_dir / "audit_review_decision_batch_approve_all.attested_example.md",
        kickoff_dir / "audit_review_decision_batch_mixed.attested_example.json",
        kickoff_dir / "audit_review_decision_batch_mixed.attested_example.md",
    ]
    generated_audit_paths = [
        kickoff_dir / "audit_review_decision_batch.live_preview.json",
        kickoff_dir / "audit_review_decision_batch.live_preview.md",
        kickoff_dir / "audit_review_decision_batch_run_report.json",
        kickoff_dir / "audit_review_decision_batch_preview_artifacts_report.json",
        kickoff_dir / "external_benchmark_execution_manifest.json",
        kickoff_dir / "external_benchmark_execution_status_manifest.json",
        kickoff_dir / "case_onepage_attestation_index.json",
        kickoff_dir / "case_onepage_attestation_index.md",
    ]
    generated_auto_approved_subset_paths = [
        kickoff_dir / "audit_review_decision_batch_approve_all.preview.json",
        kickoff_dir / "external_benchmark_submission_readiness_preview.approve_all.json",
        kickoff_dir / "external_benchmark_submission_readiness_preview.approve_all.md",
    ]
    latest_validation_path = base_dir / "external_validation_latest.json"
    latest_validation_payload = _load_json(latest_validation_path)
    generated_signed_submission_bundle_paths: list[Path] = [latest_validation_path]
    latest_bundle_summary_metrics: dict[str, Any] = {}
    latest_bundle_summary_path: Path | None = None
    latest_bundle_dir: Path | None = None
    if latest_validation_payload:
        for key in ("zip", "summary_json", "summary_md", "summary_html", "summary_pdf"):
            raw = str(latest_validation_payload.get(key, "") or "").strip()
            if raw:
                resolved = _resolve_repo_path(raw, base_dir=base_dir)
                generated_signed_submission_bundle_paths.append(resolved)
                if key == "summary_json" and resolved.exists():
                    latest_bundle_summary_path = resolved
                    latest_bundle_summary = _load_json(resolved)
                    metrics = (
                        latest_bundle_summary.get("metrics")
                        if isinstance(latest_bundle_summary.get("metrics"), dict)
                        else {}
                    )
                    latest_bundle_summary_metrics = metrics if isinstance(metrics, dict) else {}
        bundle_dir_raw = str(latest_validation_payload.get("dir", "") or "").strip()
        if bundle_dir_raw:
            bundle_dir = _resolve_repo_path(bundle_dir_raw, base_dir=base_dir)
            latest_bundle_dir = bundle_dir
            generated_signed_submission_bundle_paths.append(bundle_dir / "README.txt")

    signature_existing = [path for path in signature_paths if path.exists()]
    release_artifacts_existing = [path for path in release_artifact_paths if path.exists()]
    authoring_existing = [path for path in generated_authoring_paths if path.exists()]
    audit_existing = [path for path in generated_audit_paths if path.exists()]
    auto_approved_existing = [path for path in generated_auto_approved_subset_paths if path.exists()]
    signed_bundle_existing = [path for path in generated_signed_submission_bundle_paths if path.exists()]
    case_attestation_index_path = kickoff_dir / "case_onepage_attestation_index.json"
    case_attestation_index = _load_json(case_attestation_index_path)
    case_attestation_summary = (
        case_attestation_index.get("summary")
        if isinstance(case_attestation_index.get("summary"), dict)
        else {}
    )
    case_attestation_summary_source_path = str(case_attestation_index_path)
    case_attestation_summary_source_label = "kickoff_index_fallback"
    if latest_bundle_summary_metrics:
        case_attestation_summary = {
            "case_count": int(
                latest_bundle_summary_metrics.get("external_benchmark_case_attestation_case_count", 0) or 0
            ),
            "manifest_count": int(
                latest_bundle_summary_metrics.get("external_benchmark_case_attestation_manifest_count", 0) or 0
            ),
            "template_count": int(
                latest_bundle_summary_metrics.get("external_benchmark_case_attestation_template_count", 0) or 0
            ),
            "receipt_count": int(
                latest_bundle_summary_metrics.get("external_benchmark_case_attestation_receipt_count", 0) or 0
            ),
            "attested_count": int(
                latest_bundle_summary_metrics.get("external_benchmark_case_attestation_attested_count", 0) or 0
            ),
            "source_label": str(
                latest_bundle_summary_metrics.get("external_benchmark_case_attestation_source_label", "") or ""
            ),
            "status_label": str(
                latest_bundle_summary_metrics.get("external_benchmark_case_attestation_status_label", "") or ""
            ),
        }
        case_attestation_summary_source_path = str(latest_bundle_summary_path or latest_validation_path)
        case_attestation_summary_source_label = "latest_bundle_summary"
    elif latest_bundle_dir is not None:
        case_dir = latest_bundle_dir / "external_benchmark_case_onepages"
        if case_dir.exists():
            template_count = len(list(case_dir.glob("*.attestation_template.json")))
            manifest_count = len(list(case_dir.glob("*.attestation_manifest.json")))
            receipt_count = len(list(case_dir.glob("*.attestation_receipt.json")))
            case_count = len(
                [path for path in case_dir.glob("*.json") if ".attestation_" not in path.name]
            )
            attested_count = min(manifest_count, receipt_count)
            if case_count and attested_count == case_count:
                status_label = f"MANIFEST_ATTESTED_AND_AUTHORITY_RECEIPTED={case_count}"
                source_label = f"manifest={manifest_count}"
            elif case_count and template_count == case_count:
                status_label = f"TEMPLATE_PENDING_REAL_REVIEW={case_count}"
                source_label = f"template={template_count}"
            else:
                status_label = "PARTIAL_ATTESTATION_STATE"
                source_label = "bundle_case_dir_counted"
            case_attestation_summary = {
                "case_count": case_count,
                "manifest_count": manifest_count,
                "template_count": template_count,
                "receipt_count": receipt_count,
                "attested_count": attested_count,
                "source_label": source_label,
                "status_label": status_label,
            }
            case_attestation_summary_source_path = str(case_dir)
            case_attestation_summary_source_label = "latest_bundle_case_dir"
    return {
        "signature_path_count": len(signature_paths),
        "signature_existing_count": len(signature_existing),
        "release_registry_artifact_count": len(release_artifact_paths),
        "release_registry_artifact_existing_count": len(release_artifacts_existing),
        "authoring_generated_artifact_count": len(generated_authoring_paths),
        "authoring_generated_artifact_existing_count": len(authoring_existing),
        "audit_generated_artifact_count": len(generated_audit_paths),
        "audit_generated_artifact_existing_count": len(audit_existing),
        "auto_approved_subset_artifact_count": len(generated_auto_approved_subset_paths),
        "auto_approved_subset_artifact_existing_count": len(auto_approved_existing),
        "signed_submission_bundle_artifact_count": len(generated_signed_submission_bundle_paths),
        "signed_submission_bundle_artifact_existing_count": len(signed_bundle_existing),
        "signature_paths": [str(path) for path in signature_paths],
        "release_registry_artifact_paths": [str(path) for path in release_artifact_paths],
        "authoring_generated_artifact_paths": [str(path) for path in generated_authoring_paths],
        "audit_generated_artifact_paths": [str(path) for path in generated_audit_paths],
        "auto_approved_subset_artifact_paths": [str(path) for path in generated_auto_approved_subset_paths],
        "signed_submission_bundle_artifact_paths": [str(path) for path in generated_signed_submission_bundle_paths],
        "signed_submission_bundle_id": str(latest_validation_payload.get("bundle_id", "") or ""),
        "signed_submission_bundle_dir": str(latest_bundle_dir or ""),
        "case_onepage_attestation_index_path": str(case_attestation_index_path),
        "case_onepage_attestation_index_exists": bool(case_attestation_index_path.exists()),
        "case_onepage_attestation_summary_source_path": str(case_attestation_summary_source_path),
        "case_onepage_attestation_summary_source_label": str(case_attestation_summary_source_label),
        "case_onepage_attestation_case_count": int(case_attestation_summary.get("case_count", 0) or 0),
        "case_onepage_attestation_manifest_count": int(case_attestation_summary.get("manifest_count", 0) or 0),
        "case_onepage_attestation_template_count": int(case_attestation_summary.get("template_count", 0) or 0),
        "case_onepage_attestation_receipt_count": int(case_attestation_summary.get("receipt_count", 0) or 0),
        "case_onepage_attestation_attested_count": int(case_attestation_summary.get("attested_count", 0) or 0),
        "case_onepage_attestation_source_label": str(case_attestation_summary.get("source_label", "") or ""),
        "case_onepage_attestation_status_label": str(case_attestation_summary.get("status_label", "") or ""),
    }


def _collect_results_explorer_traceability(
    *,
    viewer_json: dict[str, Any],
) -> dict[str, Any]:
    results_explorer = viewer_json.get("results_explorer") if isinstance(viewer_json.get("results_explorer"), dict) else {}
    case_context = viewer_json.get("case_context") if isinstance(viewer_json.get("case_context"), dict) else {}
    traceability = (
        results_explorer.get("traceability") if isinstance(results_explorer.get("traceability"), dict) else {}
    )

    def _report_rows(key: str) -> list[dict[str, Any]]:
        rows = traceability.get(key) if isinstance(traceability.get(key), list) else []
        return [row for row in rows if isinstance(row, dict)]

    def _report_labels(rows: list[dict[str, Any]]) -> list[str]:
        return [
            str(row.get("label", "") or "").strip()
            for row in rows
            if str(row.get("label", "") or "").strip()
        ]

    source_reports = _report_rows("source_reports")
    audit_reports = _report_rows("audit_reports")
    output_reports = _report_rows("output_reports")
    source_labels = _report_labels(source_reports)
    audit_labels = _report_labels(audit_reports)
    output_labels = _report_labels(output_reports)
    ndtha_response = results_explorer.get("ndtha_response") if isinstance(results_explorer.get("ndtha_response"), dict) else {}
    geometry_crosswalk = (
        results_explorer.get("geometry_crosswalk") if isinstance(results_explorer.get("geometry_crosswalk"), dict) else {}
    )
    contact_material_integration = (
        results_explorer.get("contact_material_integration")
        if isinstance(results_explorer.get("contact_material_integration"), dict)
        else {}
    )
    general_fe_contact_surface_payload: dict[str, Any] = {}
    for candidate in (
        traceability.get("general_fe_contact_matrix_surface"),
        results_explorer.get("general_fe_contact_matrix_surface"),
        results_explorer.get("general_fe_contact_matrix"),
        case_context.get("general_fe_contact_matrix_surface"),
        viewer_json.get("general_fe_contact_matrix_surface"),
    ):
        if isinstance(candidate, dict):
            general_fe_contact_surface_payload = candidate
            break
    surface_sequence = [
        str(item).strip()
        for item in (traceability.get("surface_sequence") if isinstance(traceability.get("surface_sequence"), list) else [])
        if str(item).strip()
    ]
    surface_chain_label = str(traceability.get("surface_chain_label", "") or "").strip()
    surface_summary_label = str(traceability.get("surface_summary_label", "") or "").strip()
    surface_depth_summary_label = str(traceability.get("surface_depth_summary_label", "") or "").strip()
    surface_detail_summary_label = str(traceability.get("surface_detail_summary_label", "") or "").strip()
    ndtha_step_series_depth_label = str(
        traceability.get("ndtha_step_series_depth_label", "")
        or ndtha_response.get("step_series_depth_label", "")
        or ""
    ).strip()
    ndtha_material_depth_label = str(
        traceability.get("ndtha_material_depth_label", "")
        or ndtha_response.get("material_effect_depth_label", "")
        or ""
    ).strip()
    geometry_full_crosswalk_depth_label = str(
        traceability.get("geometry_full_crosswalk_depth_label", "")
        or geometry_crosswalk.get("full_crosswalk_depth_label", "")
        or ""
    ).strip()
    geometry_full_crosswalk_detail_label = str(
        traceability.get("geometry_full_crosswalk_detail_label", "")
        or geometry_crosswalk.get("full_crosswalk_detail_label", "")
        or ""
    ).strip()
    contact_material_depth_summary_label = str(
        traceability.get("contact_material_depth_summary_label", "")
        or contact_material_integration.get("summary_label", "")
        or results_explorer.get("contact_material_depth_summary_label", "")
        or ""
    ).strip()
    contact_coupling_surface = _extract_contact_coupling_surface(
        contact_material_depth_summary_label,
        support_family_count=contact_material_integration.get("support_family_count"),
        proxy_family_count=contact_material_integration.get("proxy_family_count"),
        assembled_depth_value=contact_material_integration.get("assembled_depth_value"),
    )
    contact_coupling_summary_label = str(contact_coupling_surface.get("summary_label", "") or "").strip()
    general_fe_contact_matrix_summary_line = str(
        traceability.get("general_fe_contact_matrix_summary_line", "")
        or results_explorer.get("general_fe_contact_matrix_summary_line", "")
        or case_context.get("general_fe_contact_matrix_summary_line", "")
        or viewer_json.get("general_fe_contact_matrix_summary_line", "")
        or ""
    ).strip()
    general_fe_contact_surface = _extract_general_fe_contact_surface(
        general_fe_contact_matrix_summary_line,
        surface_payload=general_fe_contact_surface_payload,
    )
    general_fe_contact_matrix_summary_line = str(
        general_fe_contact_surface.get("summary_line", "") or general_fe_contact_matrix_summary_line
    ).strip()
    if not surface_depth_summary_label:
        depth_parts = [
            part
            for part in (
                f"NDTHA step-series depth={ndtha_step_series_depth_label}" if ndtha_step_series_depth_label else "",
                (
                    f"geometry full-crosswalk depth={geometry_full_crosswalk_depth_label}"
                    if geometry_full_crosswalk_depth_label
                    else ""
                ),
            )
            if part
        ]
        surface_depth_summary_label = " | ".join(depth_parts)
    if not surface_detail_summary_label:
        detail_parts = [
            part
            for part in (
                f"NDTHA material depth={ndtha_material_depth_label}" if ndtha_material_depth_label else "",
                (
                    f"geometry full-crosswalk detail={geometry_full_crosswalk_detail_label}"
                    if geometry_full_crosswalk_detail_label
                    else ""
                ),
            )
            if part
        ]
        surface_detail_summary_label = " | ".join(detail_parts)
    rerun_label = str(traceability.get("rerun_label", "") or "").strip()
    rerun_command = str(traceability.get("rerun_command", "") or "").strip()

    expected_surface_sequences = (
        ["time-history", "envelope", "mode-shape"],
        ["time-history", "envelope", "ndtha-response", "mode-shape"],
    )
    surface_sequence_pass = any(
        surface_sequence[: len(expected)] == expected for expected in expected_surface_sequences
    )

    traceability_pass = bool(
        isinstance(results_explorer, dict)
        and isinstance(traceability, dict)
        and bool(traceability.get("available", False))
        and surface_chain_label
        and surface_summary_label
        and rerun_label
        and rerun_command
        and len(source_reports) >= 3
        and len(audit_reports) >= 4
        and len(output_reports) >= 2
        and {"Time-History Report", "Envelope Report", "Mode-Shape Report"}.issubset(set(source_labels))
        and {"Release Gap JSON", "Execution Manifest", "Execution Status", "Change Summary JSON"}.issubset(set(audit_labels))
        and {"Viewer HTML", "Gallery One-Page HTML"}.issubset(set(output_labels))
        and surface_sequence_pass
        and "generate_structural_optimization_visualization_viewer.py" in rerun_command
    )
    ndtha_step_series_depth_pass = bool(
        not ndtha_step_series_depth_label or ndtha_step_series_depth_label.replace(".", "", 1).isdigit()
    )
    ndtha_material_depth_pass = bool(
        not ndtha_material_depth_label or ndtha_material_depth_label.replace(".", "", 1).isdigit()
    )
    geometry_full_crosswalk_depth_pass = bool(
        not geometry_full_crosswalk_depth_label or geometry_full_crosswalk_depth_label.replace(".", "", 1).isdigit()
    )
    geometry_full_crosswalk_detail_pass = bool(
        not geometry_full_crosswalk_detail_label
        or (
            "full member=" in geometry_full_crosswalk_detail_label
            and "full section=" in geometry_full_crosswalk_detail_label
            and "full load=" in geometry_full_crosswalk_detail_label
        )
    )
    contact_material_depth_pass = bool(
        not contact_material_depth_summary_label
        or (
            "support families=" in contact_material_depth_summary_label
            and "proxy families=" in contact_material_depth_summary_label
            and "assembled depth=" in contact_material_depth_summary_label
            and "NDTHA/material depth=" in contact_material_depth_summary_label
        )
    )
    contact_coupling_pass = bool(contact_coupling_surface.get("pass", True))
    general_fe_contact_surface_pass = bool(general_fe_contact_surface.get("pass", True))

    return {
        "results_explorer_available": bool(results_explorer),
        "results_explorer_traceability_available": bool(traceability.get("available", False)),
        "results_explorer_traceability_pass": traceability_pass,
        "results_explorer_traceability_surface_sequence": surface_sequence,
        "results_explorer_traceability_surface_chain_label": surface_chain_label,
        "results_explorer_traceability_surface_summary_label": surface_summary_label,
        "results_explorer_traceability_surface_depth_summary_label": surface_depth_summary_label,
        "results_explorer_traceability_surface_detail_summary_label": surface_detail_summary_label,
        "results_explorer_traceability_ndtha_step_series_depth_label": ndtha_step_series_depth_label,
        "results_explorer_traceability_ndtha_material_depth_label": ndtha_material_depth_label,
        "results_explorer_traceability_geometry_full_crosswalk_depth_label": geometry_full_crosswalk_depth_label,
        "results_explorer_traceability_geometry_full_crosswalk_detail_label": geometry_full_crosswalk_detail_label,
        "results_explorer_traceability_contact_coupling_summary_label": contact_coupling_summary_label,
        "results_explorer_traceability_contact_support_family_count": int(
            contact_coupling_surface.get("support_family_count", 0) or 0
        ),
        "results_explorer_traceability_contact_proxy_family_count": int(
            contact_coupling_surface.get("proxy_family_count", 0) or 0
        ),
        "results_explorer_traceability_contact_assembled_depth_value": int(
            contact_coupling_surface.get("assembled_depth_value", 0) or 0
        ),
        "results_explorer_traceability_contact_material_depth_summary_label": contact_material_depth_summary_label,
        "results_explorer_traceability_general_fe_contact_matrix_summary_line": general_fe_contact_matrix_summary_line,
        "results_explorer_traceability_general_fe_contact_compact_summary_label": str(
            general_fe_contact_surface.get("compact_summary_label", "") or ""
        ),
        "results_explorer_traceability_general_fe_contact_coupling_depth_value": int(
            general_fe_contact_surface.get("coupling_depth_value", 0) or 0
        ),
        "results_explorer_traceability_general_fe_contact_support_family_count": int(
            general_fe_contact_surface.get("support_family_count", 0) or 0
        ),
        "results_explorer_traceability_general_fe_contact_support_family_expected_count": int(
            general_fe_contact_surface.get("support_family_expected_count", 0) or 0
        ),
        "results_explorer_traceability_general_fe_contact_proxy_family_count": int(
            general_fe_contact_surface.get("proxy_family_count", 0) or 0
        ),
        "results_explorer_traceability_general_fe_contact_proxy_family_expected_count": int(
            general_fe_contact_surface.get("proxy_family_expected_count", 0) or 0
        ),
        "results_explorer_traceability_rerun_label": rerun_label,
        "results_explorer_traceability_rerun_command": rerun_command,
        "results_explorer_traceability_source_report_count": len(source_reports),
        "results_explorer_traceability_audit_report_count": len(audit_reports),
        "results_explorer_traceability_output_report_count": len(output_reports),
        "results_explorer_traceability_source_report_labels": source_labels,
        "results_explorer_traceability_audit_report_labels": audit_labels,
        "results_explorer_traceability_output_report_labels": output_labels,
        "results_explorer_ndtha_step_series_depth_pass": ndtha_step_series_depth_pass,
        "results_explorer_ndtha_material_depth_pass": ndtha_material_depth_pass,
        "results_explorer_geometry_full_crosswalk_depth_pass": geometry_full_crosswalk_depth_pass,
        "results_explorer_geometry_full_crosswalk_detail_pass": geometry_full_crosswalk_detail_pass,
        "results_explorer_contact_coupling_pass": contact_coupling_pass,
        "results_explorer_contact_material_depth_pass": contact_material_depth_pass,
        "results_explorer_general_fe_contact_surface_pass": general_fe_contact_surface_pass,
    }


def _collect_irregular_structure_artifacts(
    *,
    source_catalog_path: Path,
    priority_families_path: Path,
    triage_report_path: Path,
    collection_report_path: Path,
    irregular_gate_report_path: Path,
    irregular_top5_manifest_path: Path,
    irregular_benchmark_execution_manifest_path: Path | None = None,
) -> dict[str, Any]:
    source_catalog = _load_json(source_catalog_path)
    priority_manifest = _load_json(priority_families_path)
    triage_report = _load_json(triage_report_path)
    collection_report = _load_json(collection_report_path)
    stored_gate_report = _load_json(irregular_gate_report_path)
    stored_top5_manifest = _load_json(irregular_top5_manifest_path)

    source_families = source_catalog.get("structure_families") if isinstance(source_catalog.get("structure_families"), list) else []
    source_records = source_catalog.get("source_records") if isinstance(source_catalog.get("source_records"), list) else []
    families_by_id: dict[str, dict[str, Any]] = {
        str(row.get("id", "")).strip(): row
        for row in source_families
        if isinstance(row, dict) and str(row.get("id", "")).strip()
    }
    records_by_family: dict[str, list[dict[str, Any]]] = {}
    for row in source_records:
        if not isinstance(row, dict):
            continue
        family_id = str(row.get("family_id", "") or "").strip()
        if not family_id:
            continue
        records_by_family.setdefault(family_id, []).append(row)

    def _record_primary_format(row: dict[str, Any]) -> str:
        primary = str(row.get("primary_format", "") or "").strip()
        if primary:
            return primary
        formats = row.get("formats") if isinstance(row.get("formats"), list) else []
        for fmt in formats:
            text = str(fmt or "").strip()
            if text:
                return text
        return ""

    priority_families = [
        row for row in (priority_manifest.get("families") if isinstance(priority_manifest.get("families"), list) else [])
        if isinstance(row, dict)
    ]
    stored_top5_rows = (
        stored_top5_manifest.get("top5_families")
        if isinstance(stored_top5_manifest.get("top5_families"), list)
        else []
    )
    top5_rows: list[dict[str, Any]] = []
    if stored_top5_rows:
        top5_rows = [row for row in stored_top5_rows if isinstance(row, dict)]
    else:
        for family in priority_families[:5]:
            family_id = str(family.get("id", "") or "").strip()
            family_summary = families_by_id.get(family_id, {})
            family_records = records_by_family.get(family_id, [])
            source_ids = [str(row.get("source_id", "") or "").strip() for row in family_records if str(row.get("source_id", "") or "").strip()]
            source_formats = sorted({fmt for fmt in (_record_primary_format(row) for row in family_records) if fmt})
            local_paths = sorted({str(row.get("local_path", "") or "").strip() for row in family_records if str(row.get("local_path", "") or "").strip()})
            collection_statuses = sorted(
                {str(row.get("collection_status", "") or "").strip() for row in family_records if str(row.get("collection_status", "") or "").strip()}
            )
            local_ready_source_count = int(family_summary.get("local_ready_source_count", 0) or 0)
            source_record_count = int(family_summary.get("source_record_count", len(family_records)) or len(family_records))
            top5_rows.append(
                {
                    "family_id": family_id,
                    "priority": int(family.get("priority", 0) or 0),
                    "execution_mode": "ready_local_now" if local_ready_source_count > 0 else "remote_source_hunt_needed",
                    "source_record_count": source_record_count,
                    "local_ready_source_count": local_ready_source_count,
                    "remote_candidate_source_count": max(source_record_count - local_ready_source_count, 0),
                    "authority_fit": str(family_summary.get("authority_fit", family.get("authority_fit", "")) or ""),
                    "ai_learning_fit": str(family_summary.get("ai_learning_fit", family.get("ai_learning_fit", "")) or ""),
                    "recommended_kpi_or_validation_angle": str(
                        family_summary.get(
                            "recommended_kpi_or_validation_angle",
                            family.get("recommended_kpi_or_validation_angle", ""),
                        )
                        or ""
                    ),
                    "irregularity_tags": [
                        str(tag).strip()
                        for tag in (
                            family_summary.get("irregularity_tags")
                            if isinstance(family_summary.get("irregularity_tags"), list)
                            else family.get("irregularity_tags", [])
                        )
                        if str(tag).strip()
                    ],
                    "why_it_matters": str(family_summary.get("why_it_matters", family.get("why_it_matters", "")) or ""),
                    "source_ids": source_ids,
                    "source_formats": source_formats,
                    "local_paths": local_paths,
                    "collection_statuses": collection_statuses,
                }
            )

    irregular_summary = {
        "track_name": str(priority_manifest.get("track_name", "") or source_catalog.get("track_name", "") or "irregular_structure_corpus_track"),
        "family_count": int((source_catalog.get("summary") or {}).get("family_count", len(source_families)) or len(source_families)),
        "source_record_count": int((source_catalog.get("summary") or {}).get("source_record_count", len(source_records)) or len(source_records)),
        "local_ready_count": int((source_catalog.get("summary") or {}).get("local_ready_count", 0) or 0),
        "remote_candidate_count": int((source_catalog.get("summary") or {}).get("remote_candidate_count", 0) or 0),
        "authority_high_like_count": int((source_catalog.get("summary") or {}).get("authority_high_like_count", 0) or 0),
        "ai_high_like_count": int((source_catalog.get("summary") or {}).get("ai_high_like_count", 0) or 0),
        "native_roundtrip_candidate_count": int((triage_report.get("summary") or {}).get("native_roundtrip_candidate_count", 0) or 0),
        "solver_benchmark_candidate_count": int((triage_report.get("summary") or {}).get("solver_benchmark_candidate_count", 0) or 0),
        "ai_learning_candidate_count": int((triage_report.get("summary") or {}).get("ai_learning_candidate_count", 0) or 0),
        "quick_start_local_source_count": int((triage_report.get("summary") or {}).get("quick_start_local_source_count", 0) or 0),
        "collected_count": int((collection_report.get("summary") or {}).get("collected_count", 0) or 0),
        "metadata_only_remote_candidate_count": int((collection_report.get("summary") or {}).get("metadata_only_remote_candidate_count", 0) or 0),
        "top5_count": int(
            (stored_top5_manifest.get("summary") or {}).get("top5_count", len(top5_rows)) or len(top5_rows)
        ),
    }
    irregular_benchmark_execution_manifest = (
        _load_json(irregular_benchmark_execution_manifest_path)
        if irregular_benchmark_execution_manifest_path is not None
        else {}
    )
    irregular_benchmark_execution_summary = (
        irregular_benchmark_execution_manifest.get("summary")
        if isinstance(irregular_benchmark_execution_manifest.get("summary"), dict)
        else {}
    )
    irregular_benchmark_ready_task_count = int(
        irregular_benchmark_execution_summary.get("ready_task_count", 0) or 0
    )
    irregular_benchmark_blocked_task_count = int(
        irregular_benchmark_execution_summary.get("blocked_task_count", 0) or 0
    )
    irregular_benchmark_execution_summary_line = str(
        irregular_benchmark_execution_manifest.get("summary_line", "") or ""
    ).strip()
    if not irregular_benchmark_execution_summary_line:
        irregular_benchmark_execution_summary_line = (
            "Irregular benchmark execution: "
            f"{'PASS' if bool(irregular_benchmark_execution_manifest.get('contract_pass', False)) else 'CHECK'} | "
            f"mode={str(irregular_benchmark_execution_summary.get('execution_mode', '') or 'missing')} | "
            f"ready={irregular_benchmark_ready_task_count} | "
            f"blocked={irregular_benchmark_blocked_task_count} | "
            f"manifest={irregular_benchmark_execution_manifest_path.name if irregular_benchmark_execution_manifest_path else 'missing'}"
        )
    summary_line = (
        str(stored_gate_report.get("summary_line", "") or "").strip()
        or (
            "Irregular structure track: "
            f"{'PASS' if bool(source_families and priority_families) else 'CHECK'} | "
            f"families={irregular_summary['family_count']} | "
            f"sources={irregular_summary['source_record_count']} | "
            f"local_ready={irregular_summary['local_ready_count']} | "
            f"remote_candidates={irregular_summary['remote_candidate_count']} | "
            f"native_roundtrip_candidates={irregular_summary['native_roundtrip_candidate_count']} | "
            f"solver_candidates={irregular_summary['solver_benchmark_candidate_count']} | "
            f"ai_candidates={irregular_summary['ai_learning_candidate_count']} | "
            f"top5={irregular_summary['top5_count']} | "
            f"gate={irregular_gate_report_path.name} | "
            f"manifest={irregular_top5_manifest_path.name}"
        )
    )

    manifest_payload = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "track_name": irregular_summary["track_name"],
        "source_catalog_path": str(source_catalog_path),
        "priority_manifest_path": str(priority_families_path),
        "collection_report_path": str(collection_report_path),
        "triage_report_path": str(triage_report_path),
        "summary": irregular_summary,
        "top5_families": top5_rows,
    }
    gate_payload = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "track_name": irregular_summary["track_name"],
        "source_catalog_path": str(source_catalog_path),
        "priority_manifest_path": str(priority_families_path),
        "collection_report_path": str(collection_report_path),
        "triage_report_path": str(triage_report_path),
        "irregular_top5_manifest_path": str(irregular_top5_manifest_path),
        "summary": irregular_summary | {
            "irregular_gate_report_path": str(irregular_gate_report_path),
            "irregular_top5_execution_manifest_path": str(irregular_top5_manifest_path),
            "collection_status_counts": (collection_report.get("summary") or {}).get("status_counts", {}),
        },
        "top5_preview": top5_rows,
        "summary_line": summary_line,
        "contract_pass": bool(source_families and priority_families),
        "reason_code": "PASS" if bool(source_families and priority_families) else "ERR_INVALID_INPUT",
        "reason": (
            "irregular structure track manifest generated"
            if bool(source_families and priority_families)
            else "irregular structure track inputs missing"
        ),
    }
    irregular_gate_report_path.parent.mkdir(parents=True, exist_ok=True)
    irregular_top5_manifest_path.parent.mkdir(parents=True, exist_ok=True)
    if not stored_gate_report:
        _write_json(irregular_gate_report_path, gate_payload)
    if not stored_top5_manifest:
        _write_json(irregular_top5_manifest_path, manifest_payload)

    return {
        "irregular_structure_track_pass": bool(gate_payload["contract_pass"]),
        "irregular_structure_track_summary_line": summary_line,
        "irregular_structure_family_count": irregular_summary["family_count"],
        "irregular_structure_source_record_count": irregular_summary["source_record_count"],
        "irregular_structure_local_ready_count": irregular_summary["local_ready_count"],
        "irregular_structure_remote_candidate_count": irregular_summary["remote_candidate_count"],
        "irregular_structure_native_roundtrip_candidate_count": irregular_summary["native_roundtrip_candidate_count"],
        "irregular_structure_solver_benchmark_candidate_count": irregular_summary["solver_benchmark_candidate_count"],
        "irregular_structure_ai_learning_candidate_count": irregular_summary["ai_learning_candidate_count"],
        "irregular_structure_top5_count": irregular_summary["top5_count"],
        "irregular_structure_gate_report_path": str(irregular_gate_report_path),
        "irregular_top5_execution_manifest_path": str(irregular_top5_manifest_path),
        "irregular_benchmark_execution_manifest_path": str(
            irregular_benchmark_execution_manifest_path or ""
        ),
        "irregular_top5_families": top5_rows,
        "irregular_gate_report": gate_payload,
        "irregular_top5_execution_manifest": manifest_payload,
        "irregular_benchmark_execution_manifest": irregular_benchmark_execution_manifest,
        "irregular_benchmark_execution_ready_task_count": irregular_benchmark_ready_task_count,
        "irregular_benchmark_execution_blocked_task_count": irregular_benchmark_blocked_task_count,
        "irregular_benchmark_execution_canonical_task_count": int(
            irregular_benchmark_execution_summary.get("ready_canonical_task_count", 0) or 0
        ),
        "irregular_benchmark_execution_bridged_task_count": int(
            irregular_benchmark_execution_summary.get("ready_bridged_task_count", 0) or 0
        ),
        "irregular_benchmark_execution_proxy_task_count": int(
            irregular_benchmark_execution_summary.get("ready_proxy_task_count", 0) or 0
        ),
        "irregular_benchmark_execution_summary_line": irregular_benchmark_execution_summary_line,
        "irregular_collection_report_path": str(collection_report_path),
        "irregular_source_catalog_path": str(source_catalog_path),
        "irregular_priority_manifest_path": str(priority_families_path),
        "irregular_triage_report_path": str(triage_report_path),
    }


def run_workflow_productization_gate(
    *,
    release_registry_report: dict[str, Any],
    release_registry_path: Path,
    midas_interoperability_report: dict[str, Any],
    midas_native_roundtrip_report: dict[str, Any],
    row_provenance_export_report: dict[str, Any],
    viewer_json: dict[str, Any],
    viewer_html_text: str,
    irregular_structure_source_catalog_path: Path,
    irregular_structure_priority_families_path: Path,
    irregular_structure_triage_report_path: Path,
    irregular_structure_collection_report_path: Path,
    irregular_structure_gate_report_path: Path,
    irregular_top5_execution_manifest_path: Path,
    irregular_benchmark_execution_manifest_path: Path | None = None,
    korean_source_ingest_gate_report_path: Path | None = None,
    korean_structural_preview_promotion_queue_path: Path | None = None,
) -> dict[str, Any]:
    registry_checks = release_registry_report.get("checks") if isinstance(release_registry_report.get("checks"), dict) else {}
    registry_summary = release_registry_report.get("summary") if isinstance(release_registry_report.get("summary"), dict) else {}
    registry_signature = release_registry_report.get("signature") if isinstance(release_registry_report.get("signature"), dict) else {}
    interoperability_summary = (
        midas_interoperability_report.get("summary") if isinstance(midas_interoperability_report.get("summary"), dict) else {}
    )
    native_roundtrip_summary = (
        midas_native_roundtrip_report.get("summary")
        if isinstance(midas_native_roundtrip_report.get("summary"), dict)
        else {}
    )
    native_roundtrip_checks = (
        midas_native_roundtrip_report.get("checks")
        if isinstance(midas_native_roundtrip_report.get("checks"), dict)
        else {}
    )
    mgt_export_summary = _load_repo_mgt_export_summary_if_available(release_registry_path=release_registry_path)
    special_member_supported_action_family_counts = (
        dict(mgt_export_summary.get("special_member_supported_action_family_counts", {}) or {})
        if isinstance(mgt_export_summary.get("special_member_supported_action_family_counts"), dict)
        else {}
    )
    special_member_direct_patch_action_family_counts = (
        dict(mgt_export_summary.get("special_member_direct_patch_action_family_counts", {}) or {})
        if isinstance(mgt_export_summary.get("special_member_direct_patch_action_family_counts"), dict)
        else {}
    )
    special_member_zero_touch_verified_action_family_counts = (
        dict(mgt_export_summary.get("special_member_instruction_sidecar_zero_touch_verified_action_family_counts", {}) or {})
        if isinstance(
            mgt_export_summary.get("special_member_instruction_sidecar_zero_touch_verified_action_family_counts"), dict
        )
        else {}
    )
    exact_topology_archive_candidate_count = _count_exact_topology_archive_candidates()
    provenance_summary = (
        row_provenance_export_report.get("summary") if isinstance(row_provenance_export_report.get("summary"), dict) else {}
    )
    generated_artifacts = _collect_generated_workflow_artifacts(
        release_registry_report=release_registry_report,
        release_registry_path=release_registry_path,
    )
    results_explorer_traceability = _collect_results_explorer_traceability(viewer_json=viewer_json)
    geometry_full_crosswalk_aggregate_label = str(
        results_explorer_traceability.get("results_explorer_traceability_geometry_full_crosswalk_aggregate_label", "") or ""
    ).strip()
    if not geometry_full_crosswalk_aggregate_label:
        geometry_full_crosswalk_aggregate_label = str(
            results_explorer_traceability.get("results_explorer_traceability_geometry_full_crosswalk_detail_label", "") or ""
        ).strip()
    existing_surface_depth_summary_label = str(
        results_explorer_traceability.get("results_explorer_traceability_surface_depth_summary_label", "") or ""
    ).strip()
    if geometry_full_crosswalk_aggregate_label and "geometry full-crosswalk aggregate=" not in existing_surface_depth_summary_label:
        results_explorer_traceability["results_explorer_traceability_surface_depth_summary_label"] = (
            f"{existing_surface_depth_summary_label} | geometry full-crosswalk aggregate={geometry_full_crosswalk_aggregate_label}"
        )
    if geometry_full_crosswalk_aggregate_label:
        results_explorer_traceability["results_explorer_traceability_geometry_full_crosswalk_aggregate_label"] = (
            geometry_full_crosswalk_aggregate_label
        )
    irregular_artifacts = _collect_irregular_structure_artifacts(
        source_catalog_path=irregular_structure_source_catalog_path,
        priority_families_path=irregular_structure_priority_families_path,
        triage_report_path=irregular_structure_triage_report_path,
        collection_report_path=irregular_structure_collection_report_path,
        irregular_gate_report_path=irregular_structure_gate_report_path,
        irregular_top5_manifest_path=irregular_top5_execution_manifest_path,
        irregular_benchmark_execution_manifest_path=irregular_benchmark_execution_manifest_path,
    )
    korean_source_ingest_gate_report_path = (
        korean_source_ingest_gate_report_path
        if korean_source_ingest_gate_report_path is not None
        else REPO_ROOT / "implementation/phase1/korean_source_ingest_gate_report.json"
    )
    korean_structural_preview_promotion_queue_path = (
        korean_structural_preview_promotion_queue_path
        if korean_structural_preview_promotion_queue_path is not None
        else REPO_ROOT / "implementation/phase1/release/midas_native_roundtrip/exact_topology_structural_preview_promotion_queue.json"
    )
    korean_source_ingest_gate_report = (
        _load_json(korean_source_ingest_gate_report_path) if korean_source_ingest_gate_report_path.exists() else {}
    )
    korean_source_ingest_summary = (
        korean_source_ingest_gate_report.get("summary")
        if isinstance(korean_source_ingest_gate_report.get("summary"), dict)
        else {}
    )
    korean_source_ingest_summary_line = str(
        korean_source_ingest_gate_report.get("summary_line", "")
        or korean_source_ingest_summary.get("ingest_summary_line", "")
        or ""
    ).strip()
    if not korean_source_ingest_summary_line:
        korean_source_ingest_summary_line = (
            "Korean source ingest: "
            f"{'PASS' if bool(korean_source_ingest_gate_report.get('contract_pass', False)) else 'CHECK'} | "
            f"sources={int(korean_source_ingest_summary.get('source_count', 0) or 0)} | "
            f"classes={int(korean_source_ingest_summary.get('source_class_count', 0) or 0)} | "
            f"collected={int(korean_source_ingest_summary.get('collected_count', 0) or 0)} | "
            f"fingerprinted={int(korean_source_ingest_summary.get('fingerprinted_count', 0) or 0)} | "
            f"metadata_only={int(korean_source_ingest_summary.get('metadata_only_remote_candidate_count', 0) or 0)} | "
            f"rejected={int(korean_source_ingest_summary.get('rejected_count', 0) or 0)} | "
            f"duplicate_sha_groups={int(korean_source_ingest_summary.get('duplicate_sha_group_count', 0) or 0)} | "
            f"seed_complete={int(korean_source_ingest_summary.get('seed_metadata_complete_count', 0) or 0)} | "
            f"exact_topology={int(korean_source_ingest_summary.get('exact_topology_candidate_count', 0) or 0)} | "
            f"native_writeback={int(korean_source_ingest_summary.get('native_writeback_candidate_count', 0) or 0)} | "
            f"p0_focus={int(korean_source_ingest_summary.get('p0_focus_candidate_count', 0) or 0)}"
        )
    korean_source_ingest_summary_line = _compact_korean_source_ingest_summary_line(korean_source_ingest_summary_line)
    korean_structural_preview_queue_report = (
        _load_json(korean_structural_preview_promotion_queue_path)
        if korean_structural_preview_promotion_queue_path.exists()
        else {}
    )
    korean_structural_preview_queue_summary = (
        korean_structural_preview_queue_report.get("summary")
        if isinstance(korean_structural_preview_queue_report.get("summary"), dict)
        else {}
    )
    korean_structural_preview_queue_candidate_total = int(
        korean_structural_preview_queue_summary.get("candidate_total", 0) or 0
    )
    korean_structural_preview_queue_pending_candidate_count = int(
        korean_structural_preview_queue_summary.get("pending_candidate_count", 0) or 0
    )
    korean_structural_preview_queue_state = str(korean_structural_preview_queue_summary.get("state", "") or "").strip()
    korean_structural_preview_queue_summary_line = (
        f"Korean structural preview queue: {'PASS' if bool(korean_structural_preview_queue_report) else 'CHECK'} | "
        f"candidates={korean_structural_preview_queue_candidate_total} | "
        f"pending={korean_structural_preview_queue_pending_candidate_count} | "
        f"state={korean_structural_preview_queue_state or 'missing'}"
    )
    korean_structural_preview_queue_summary_line = _compact_korean_structural_preview_queue_summary_line(
        korean_structural_preview_queue_summary_line
    )
    generated_artifacts.update(
        {
            "irregular_structure_track_pass": bool(irregular_artifacts.get("irregular_structure_track_pass", False)),
            "irregular_structure_track_summary_line": str(
                irregular_artifacts.get("irregular_structure_track_summary_line", "") or ""
            ),
            "irregular_structure_family_count": int(irregular_artifacts.get("irregular_structure_family_count", 0) or 0),
            "irregular_structure_source_record_count": int(
                irregular_artifacts.get("irregular_structure_source_record_count", 0) or 0
            ),
            "irregular_structure_local_ready_count": int(
                irregular_artifacts.get("irregular_structure_local_ready_count", 0) or 0
            ),
            "irregular_structure_remote_candidate_count": int(
                irregular_artifacts.get("irregular_structure_remote_candidate_count", 0) or 0
            ),
            "irregular_structure_native_roundtrip_candidate_count": int(
                irregular_artifacts.get("irregular_structure_native_roundtrip_candidate_count", 0) or 0
            ),
            "irregular_structure_solver_benchmark_candidate_count": int(
                irregular_artifacts.get("irregular_structure_solver_benchmark_candidate_count", 0) or 0
            ),
            "irregular_structure_ai_learning_candidate_count": int(
                irregular_artifacts.get("irregular_structure_ai_learning_candidate_count", 0) or 0
            ),
            "irregular_structure_top5_count": int(irregular_artifacts.get("irregular_structure_top5_count", 0) or 0),
            "irregular_structure_gate_report_path": str(
                irregular_artifacts.get("irregular_structure_gate_report_path", "") or ""
            ),
            "irregular_top5_execution_manifest_path": str(
                irregular_artifacts.get("irregular_top5_execution_manifest_path", "") or ""
            ),
            "irregular_benchmark_execution_manifest_path": str(
                irregular_artifacts.get("irregular_benchmark_execution_manifest_path", "") or ""
            ),
            "irregular_benchmark_execution_canonical_task_count": int(
                irregular_artifacts.get("irregular_benchmark_execution_canonical_task_count", 0) or 0
            ),
            "irregular_benchmark_execution_bridged_task_count": int(
                irregular_artifacts.get("irregular_benchmark_execution_bridged_task_count", 0) or 0
            ),
            "irregular_benchmark_execution_proxy_task_count": int(
                irregular_artifacts.get("irregular_benchmark_execution_proxy_task_count", 0) or 0
            ),
            "irregular_collection_report_path": str(
                irregular_artifacts.get("irregular_collection_report_path", "") or ""
            ),
            "irregular_source_catalog_path": str(irregular_artifacts.get("irregular_source_catalog_path", "") or ""),
            "irregular_priority_manifest_path": str(
                irregular_artifacts.get("irregular_priority_manifest_path", "") or ""
            ),
            "irregular_triage_report_path": str(irregular_artifacts.get("irregular_triage_report_path", "") or ""),
            "korean_source_ingest_gate_report_path": str(korean_source_ingest_gate_report_path),
            "korean_structural_preview_promotion_queue_path": str(korean_structural_preview_promotion_queue_path),
        }
    )

    signed_release_pass = bool(
        release_registry_report.get("contract_pass", False)
        and bool(registry_checks.get("public_key_written_pass", False))
        and bool(registry_checks.get("signature_generated_pass", False))
        and bool(registry_checks.get("signature_verified_pass", False))
        and bool(str(registry_signature.get("public_key_path", "") or "").strip())
        and generated_artifacts["signature_path_count"] >= 2
        and generated_artifacts["signature_existing_count"] >= 2
    )
    authoring_action_automation_pass = bool(
        int(registry_summary.get("mgt_export_direct_patch_change_count", 0) or 0) >= 1
        and int(registry_summary.get("mgt_export_group_local_connection_detailing_payload_available_count", 0) or 0) >= 1
        and int(registry_summary.get("mgt_export_group_local_detailing_payload_available_count", 0) or 0) >= 1
        and int(registry_summary.get("mgt_export_group_local_rebar_payload_available_count", 0) or 0) >= 1
        and int(registry_summary.get("mgt_export_connection_detailing_structured_payload_mapped_change_count", 0) or 0) >= 1
        and int(registry_summary.get("mgt_export_detailing_structured_payload_mapped_change_count", 0) or 0) >= 1
        and str(registry_summary.get("mgt_export_support_mode", "") or "").strip() != ""
        and str(registry_summary.get("mgt_export_evidence_model", "") or "").strip() != ""
        and generated_artifacts["release_registry_artifact_existing_count"] >= 3
        and generated_artifacts["authoring_generated_artifact_existing_count"] >= 6
    )
    zero_touch_connection_delivery_mode = str(
        registry_summary.get("mgt_export_connection_detailing_delivery_mode", "") or ""
    ).strip()
    zero_touch_detailing_delivery_mode = str(
        registry_summary.get("mgt_export_detailing_delivery_mode", "") or ""
    ).strip()
    zero_touch_native_authoring_count = 0
    if zero_touch_connection_delivery_mode == "direct_patch_native_authoring_zero_touch_verified":
        zero_touch_native_authoring_count += int(
            registry_summary.get("mgt_export_connection_detailing_structured_payload_mapped_change_count", 0) or 0
        )
    if zero_touch_detailing_delivery_mode == "direct_patch_native_authoring_zero_touch_verified":
        zero_touch_native_authoring_count += int(
            registry_summary.get("mgt_export_detailing_structured_payload_mapped_change_count", 0) or 0
        )
    zero_touch_native_authoring_pass = bool(
        str(registry_summary.get("mgt_export_support_mode", "") or "").strip()
        == "native_authoring_supported_changeset"
        and "zero_touch_verification_manifest"
        in str(registry_summary.get("mgt_export_evidence_model", "") or "").strip()
        and zero_touch_connection_delivery_mode == "direct_patch_native_authoring_zero_touch_verified"
        and zero_touch_detailing_delivery_mode == "direct_patch_native_authoring_zero_touch_verified"
        and zero_touch_native_authoring_count >= 1
        and int(registry_summary.get("mgt_export_instruction_sidecar_audit_only_change_count", 0) or 0) == 0
        and int(registry_summary.get("mgt_export_instruction_sidecar_manual_input_change_count", 0) or 0) == 0
        and int(registry_summary.get("mgt_export_audit_review_queue_pending_count", 0) or 0) == 0
    )
    preview_approve_all_reason_code = str(
        registry_summary.get("external_benchmark_submission_preview_approve_all_reason_code", "") or ""
    ).strip()
    preview_reject_one_reason_code = str(
        registry_summary.get("external_benchmark_submission_preview_reject_one_reason_code", "") or ""
    ).strip()
    zero_touch_no_open_decision_items_pass = bool(
        zero_touch_native_authoring_pass
        and int(registry_summary.get("audit_review_decision_batch_template_item_count", 0) or 0) == 0
        and str(registry_summary.get("audit_review_decision_batch_runner_reason_code", "") or "").strip()
        == "PASS_ZERO_TOUCH_NO_OPEN_DECISION_ITEMS"
        and preview_approve_all_reason_code == "PASS_NO_OPEN_DECISION_ITEMS"
        and preview_reject_one_reason_code == "PASS_NO_OPEN_DECISION_ITEMS"
    )
    audit_preview_ready = bool(
        (
            int(registry_summary.get("audit_review_decision_batch_template_item_count", 0) or 0) >= 1
            and str(registry_summary.get("audit_review_decision_batch_runner_reason_code", "") or "").strip() == "PASS"
            and preview_approve_all_reason_code != ""
            and preview_reject_one_reason_code != ""
        )
        or zero_touch_no_open_decision_items_pass
    )
    legacy_audit_approval_pass = bool(
        int(registry_summary.get("mgt_export_audit_review_packet_count", 0) or 0) >= 1
        and int(registry_summary.get("mgt_export_audit_review_followup_item_count", 0) or 0) >= 1
        and int(registry_summary.get("mgt_export_audit_review_resolution_item_count", 0) or 0) >= 1
    )
    audit_approval_pass = bool(audit_preview_ready and (legacy_audit_approval_pass or zero_touch_native_authoring_pass))
    legacy_audit_action_automation_pass = bool(
        int(registry_summary.get("mgt_export_audit_review_queue_item_count", 0) or 0) >= 1
        and int(registry_summary.get("mgt_export_audit_review_followup_item_count", 0) or 0) >= 1
        and int(registry_summary.get("mgt_export_audit_review_resolution_item_count", 0) or 0) >= 1
        and str(registry_summary.get("mgt_export_audit_review_queue_status_label", "") or "").strip() != ""
        and str(registry_summary.get("mgt_export_audit_review_followup_status_label", "") or "").strip() != ""
        and str(registry_summary.get("mgt_export_audit_review_resolution_status_label", "") or "").strip() != ""
        and bool(registry_summary.get("audit_review_decision_batch_runner_preview_ready_full", False))
    )
    audit_action_automation_pass = bool(
        (legacy_audit_action_automation_pass or zero_touch_native_authoring_pass)
        and generated_artifacts["audit_generated_artifact_existing_count"] >= 6
    )
    auto_approved_subset_pass = bool(
        (
            preview_approve_all_reason_code in {"PASS", "PASS_START_NOW_FULL"}
            and bool(registry_summary.get("external_benchmark_submission_preview_approve_all_ready_full", False))
        )
        or zero_touch_no_open_decision_items_pass
    ) and bool(
        int(registry_summary.get("external_benchmark_submission_preview_approve_all_pending_count", 0) or 0) == 0
        and int(registry_summary.get("external_benchmark_submission_preview_approve_all_open_revision_count", 0) or 0) == 0
        and generated_artifacts["auto_approved_subset_artifact_existing_count"] >= 3
    )
    approve_all_preview_ready_full_effective = bool(
        registry_summary.get("external_benchmark_submission_preview_approve_all_ready_full", False)
    ) or zero_touch_no_open_decision_items_pass
    signed_submission_bundle_pass = bool(
        signed_release_pass
        and auto_approved_subset_pass
        and generated_artifacts["signed_submission_bundle_artifact_existing_count"] >= 6
        and str(generated_artifacts.get("signed_submission_bundle_id", "") or "").strip() != ""
    )
    viewer_results_pass = bool(
        isinstance(viewer_json.get("commercial_parity_summary"), dict)
        and isinstance(viewer_json.get("benchmark_execution"), dict)
        and isinstance(viewer_json.get("detail_context"), dict)
        and isinstance(viewer_json.get("results_explorer"), dict)
        and "Results Explorer" in viewer_html_text
        and "Code-Check Drilldown" in viewer_html_text
        and "MIDAS Load Combination Browser" in viewer_html_text
        and "Reviewer appendix surface" in viewer_html_text
        and "current slice csv" in viewer_html_text
    )
    results_explorer_traceability_pass = bool(
        results_explorer_traceability.get("results_explorer_traceability_pass", False)
    )
    provenance_export_pass = bool(
        row_provenance_export_report.get("contract_pass", False)
        and int(provenance_summary.get("row_count", provenance_summary.get("rows", 0)) or 0) >= 1
        and int(provenance_summary.get("exact_row_count", provenance_summary.get("exact_rows", 0)) or 0) >= 1
    )
    native_midas_roundtrip_pass = bool(
        midas_native_roundtrip_report.get("contract_pass", False)
        and bool(native_roundtrip_checks.get("corpus_manifest_present_pass", False))
        and bool(native_roundtrip_checks.get("native_text_case_present_pass", False))
        and bool(native_roundtrip_checks.get("native_writeback_ready_pass", False))
        and bool(native_roundtrip_checks.get("diff_receipt_coverage_pass", False))
        and bool(native_roundtrip_checks.get("per_case_writeback_pass", False))
        and bool(native_roundtrip_checks.get("topology_stability_pass", False))
        and bool(native_roundtrip_checks.get("load_contract_stability_pass", False))
        and bool(native_roundtrip_checks.get("loadcomb_exact_roundtrip_pass", False))
        and bool(native_roundtrip_checks.get("unknown_rows_zero_pass", False))
    )
    bounded_roundtrip_pass = bool(
        midas_interoperability_report.get("contract_pass", False)
        and bool(interoperability_summary.get("loadcomb_roundtrip_pass", False))
        and str(interoperability_summary.get("bounded_subset_mode", "") or "").strip() != ""
        and int(interoperability_summary.get("preview_file_present_count", 0) or 0) >= 1
    )
    irregular_structure_track_pass = bool(irregular_artifacts.get("irregular_structure_track_pass", False))

    checks = {
        "signed_release_registry_pass": signed_release_pass,
        "authoring_action_automation_pass": authoring_action_automation_pass,
        "audit_approval_flow_pass": audit_approval_pass,
        "audit_action_automation_pass": audit_action_automation_pass,
        "auto_approved_subset_pass": auto_approved_subset_pass,
        "signed_submission_bundle_pass": signed_submission_bundle_pass,
        "viewer_results_surface_pass": viewer_results_pass,
        "results_explorer_traceability_pass": results_explorer_traceability_pass,
        "results_explorer_ndtha_step_series_depth_pass": results_explorer_traceability.get(
            "results_explorer_ndtha_step_series_depth_pass", True
        ),
        "results_explorer_ndtha_material_depth_pass": results_explorer_traceability.get(
            "results_explorer_ndtha_material_depth_pass", True
        ),
        "results_explorer_geometry_full_crosswalk_depth_pass": results_explorer_traceability.get(
            "results_explorer_geometry_full_crosswalk_depth_pass", True
        ),
        "results_explorer_geometry_full_crosswalk_detail_pass": results_explorer_traceability.get(
            "results_explorer_geometry_full_crosswalk_detail_pass", True
        ),
        "results_explorer_contact_coupling_pass": results_explorer_traceability.get(
            "results_explorer_contact_coupling_pass", True
        ),
        "results_explorer_contact_material_depth_pass": results_explorer_traceability.get(
            "results_explorer_contact_material_depth_pass", True
        ),
        "results_explorer_general_fe_contact_surface_pass": results_explorer_traceability.get(
            "results_explorer_general_fe_contact_surface_pass", True
        ),
        "provenance_export_pass": provenance_export_pass,
        "native_midas_roundtrip_pass": native_midas_roundtrip_pass,
        "bounded_roundtrip_pass": bounded_roundtrip_pass,
        "irregular_structure_track_pass": irregular_structure_track_pass,
    }
    contract_pass = bool(all(checks.values()))
    if not signed_release_pass:
        reason_code = "ERR_SIGNED_RELEASE"
    elif not authoring_action_automation_pass:
        reason_code = "ERR_AUTHORING_AUTOMATION"
    elif not audit_approval_pass:
        reason_code = "ERR_AUDIT_APPROVAL"
    elif not audit_action_automation_pass:
        reason_code = "ERR_AUDIT_ACTIONS"
    elif not auto_approved_subset_pass:
        reason_code = "ERR_AUTO_APPROVED_SUBSET"
    elif not signed_submission_bundle_pass:
        reason_code = "ERR_SIGNED_SUBMISSION_BUNDLE"
    elif not viewer_results_pass:
        reason_code = "ERR_VIEWER_RESULTS"
    elif not results_explorer_traceability_pass:
        reason_code = "ERR_RESULTS_EXPLORER_TRACEABILITY"
    elif not provenance_export_pass:
        reason_code = "ERR_PROVENANCE_EXPORT"
    elif not native_midas_roundtrip_pass:
        reason_code = "ERR_NATIVE_MIDAS_ROUNDTRIP"
    elif not bounded_roundtrip_pass:
        reason_code = "ERR_BOUNDED_ROUNDTRIP"
    elif not irregular_structure_track_pass:
        reason_code = "ERR_IRREGULAR_STRUCTURE_TRACK"
    else:
        reason_code = "PASS"

    summary = {
        "deployment_model": str(registry_summary.get("deployment_model", "") or ""),
        "audit_packet_count": int(registry_summary.get("mgt_export_audit_review_packet_count", 0) or 0),
        "audit_followup_count": int(registry_summary.get("mgt_export_audit_review_followup_item_count", 0) or 0),
        "audit_resolution_count": int(registry_summary.get("mgt_export_audit_review_resolution_item_count", 0) or 0),
        "audit_queue_count": int(registry_summary.get("mgt_export_audit_review_queue_item_count", 0) or 0),
        "zero_touch_native_authoring_pass": zero_touch_native_authoring_pass,
        "zero_touch_native_authoring_count": int(zero_touch_native_authoring_count),
        "zero_touch_no_open_decision_items_pass": zero_touch_no_open_decision_items_pass,
        "zero_touch_connection_delivery_mode": zero_touch_connection_delivery_mode,
        "zero_touch_detailing_delivery_mode": zero_touch_detailing_delivery_mode,
        "audit_flow_mode": (
            "zero_touch_native_authoring"
            if zero_touch_native_authoring_pass and not legacy_audit_approval_pass
            else "legacy_audit_packets"
            if legacy_audit_approval_pass and not zero_touch_native_authoring_pass
            else "mixed"
            if zero_touch_native_authoring_pass and legacy_audit_approval_pass
            else "incomplete"
        ),
        "approve_all_preview_ready_full": approve_all_preview_ready_full_effective,
        "direct_patch_change_count": int(registry_summary.get("mgt_export_direct_patch_change_count", 0) or 0),
        "authoring_payload_available_count": int(
            registry_summary.get("mgt_export_group_local_connection_detailing_payload_available_count", 0) or 0
        )
        + int(registry_summary.get("mgt_export_group_local_detailing_payload_available_count", 0) or 0)
        + int(registry_summary.get("mgt_export_group_local_rebar_payload_available_count", 0) or 0),
        "generated_release_artifact_count": int(generated_artifacts["release_registry_artifact_existing_count"]),
        "generated_authoring_artifact_count": int(generated_artifacts["authoring_generated_artifact_existing_count"]),
        "generated_audit_artifact_count": int(generated_artifacts["audit_generated_artifact_existing_count"]),
        "generated_auto_approved_subset_count": int(generated_artifacts["auto_approved_subset_artifact_existing_count"]),
        "generated_signed_submission_bundle_count": int(
            generated_artifacts["signed_submission_bundle_artifact_existing_count"]
        ),
        "case_onepage_attestation_case_count": int(
            generated_artifacts.get("case_onepage_attestation_case_count", 0) or 0
        ),
        "case_onepage_attestation_manifest_count": int(
            generated_artifacts.get("case_onepage_attestation_manifest_count", 0) or 0
        ),
        "case_onepage_attestation_template_count": int(
            generated_artifacts.get("case_onepage_attestation_template_count", 0) or 0
        ),
        "case_onepage_attestation_receipt_count": int(
            generated_artifacts.get("case_onepage_attestation_receipt_count", 0) or 0
        ),
        "case_onepage_attestation_attested_count": int(
            generated_artifacts.get("case_onepage_attestation_attested_count", 0) or 0
        ),
        "case_onepage_attestation_summary_source_path": str(
            generated_artifacts.get("case_onepage_attestation_summary_source_path", "") or ""
        ),
        "case_onepage_attestation_summary_source_label": str(
            generated_artifacts.get("case_onepage_attestation_summary_source_label", "") or ""
        ),
        "case_onepage_attestation_source_label": str(
            generated_artifacts.get("case_onepage_attestation_source_label", "") or ""
        ),
        "case_onepage_attestation_status_label": str(
            generated_artifacts.get("case_onepage_attestation_status_label", "") or ""
        ),
        "approve_all_preview_reason_code": str(
            registry_summary.get("external_benchmark_submission_preview_approve_all_reason_code", "") or ""
        ),
        "signed_submission_bundle_id": str(generated_artifacts.get("signed_submission_bundle_id", "") or ""),
        "viewer_mode": str(viewer_json.get("viewer_mode", "") or ""),
        "results_explorer_traceability_available": bool(
            results_explorer_traceability.get("results_explorer_traceability_available", False)
        ),
        "results_explorer_traceability_pass": results_explorer_traceability_pass,
        "results_explorer_traceability_surface_sequence": [
            str(item)
            for item in results_explorer_traceability.get("results_explorer_traceability_surface_sequence", [])
            if str(item).strip()
        ],
        "results_explorer_traceability_surface_chain_label": str(
            results_explorer_traceability.get("results_explorer_traceability_surface_chain_label", "") or ""
        ),
        "results_explorer_traceability_surface_summary_label": str(
            results_explorer_traceability.get("results_explorer_traceability_surface_summary_label", "") or ""
        ),
        "results_explorer_traceability_surface_depth_summary_label": str(
            results_explorer_traceability.get("results_explorer_traceability_surface_depth_summary_label", "") or ""
        ),
        "results_explorer_traceability_surface_detail_summary_label": str(
            results_explorer_traceability.get("results_explorer_traceability_surface_detail_summary_label", "") or ""
        ),
        "results_explorer_traceability_ndtha_step_series_depth_label": str(
            results_explorer_traceability.get("results_explorer_traceability_ndtha_step_series_depth_label", "") or ""
        ),
        "results_explorer_traceability_ndtha_material_depth_label": str(
            results_explorer_traceability.get("results_explorer_traceability_ndtha_material_depth_label", "") or ""
        ),
        "results_explorer_traceability_geometry_full_crosswalk_depth_label": str(
            results_explorer_traceability.get("results_explorer_traceability_geometry_full_crosswalk_depth_label", "") or ""
        ),
        "results_explorer_traceability_geometry_full_crosswalk_detail_label": str(
            results_explorer_traceability.get("results_explorer_traceability_geometry_full_crosswalk_detail_label", "") or ""
        ),
        "results_explorer_traceability_geometry_full_crosswalk_aggregate_label": str(
            results_explorer_traceability.get("results_explorer_traceability_geometry_full_crosswalk_aggregate_label", "") or ""
        ),
        "results_explorer_traceability_contact_coupling_summary_label": str(
            results_explorer_traceability.get("results_explorer_traceability_contact_coupling_summary_label", "") or ""
        ),
        "results_explorer_traceability_contact_support_family_count": int(
            results_explorer_traceability.get("results_explorer_traceability_contact_support_family_count", 0) or 0
        ),
        "results_explorer_traceability_contact_proxy_family_count": int(
            results_explorer_traceability.get("results_explorer_traceability_contact_proxy_family_count", 0) or 0
        ),
        "results_explorer_traceability_contact_assembled_depth_value": int(
            results_explorer_traceability.get("results_explorer_traceability_contact_assembled_depth_value", 0) or 0
        ),
        "results_explorer_traceability_contact_material_depth_summary_label": str(
            results_explorer_traceability.get("results_explorer_traceability_contact_material_depth_summary_label", "") or ""
        ),
        "results_explorer_traceability_general_fe_contact_matrix_summary_line": str(
            results_explorer_traceability.get(
                "results_explorer_traceability_general_fe_contact_matrix_summary_line", ""
            )
            or ""
        ),
        "results_explorer_traceability_general_fe_contact_compact_summary_label": str(
            results_explorer_traceability.get(
                "results_explorer_traceability_general_fe_contact_compact_summary_label", ""
            )
            or ""
        ),
        "results_explorer_traceability_general_fe_contact_coupling_depth_value": int(
            results_explorer_traceability.get(
                "results_explorer_traceability_general_fe_contact_coupling_depth_value", 0
            )
            or 0
        ),
        "results_explorer_traceability_general_fe_contact_support_family_count": int(
            results_explorer_traceability.get(
                "results_explorer_traceability_general_fe_contact_support_family_count", 0
            )
            or 0
        ),
        "results_explorer_traceability_general_fe_contact_support_family_expected_count": int(
            results_explorer_traceability.get(
                "results_explorer_traceability_general_fe_contact_support_family_expected_count", 0
            )
            or 0
        ),
        "results_explorer_traceability_general_fe_contact_proxy_family_count": int(
            results_explorer_traceability.get(
                "results_explorer_traceability_general_fe_contact_proxy_family_count", 0
            )
            or 0
        ),
        "results_explorer_traceability_general_fe_contact_proxy_family_expected_count": int(
            results_explorer_traceability.get(
                "results_explorer_traceability_general_fe_contact_proxy_family_expected_count", 0
            )
            or 0
        ),
        "results_explorer_ndtha_step_series_depth_pass": bool(
            results_explorer_traceability.get("results_explorer_ndtha_step_series_depth_pass", True)
        ),
        "results_explorer_ndtha_material_depth_pass": bool(
            results_explorer_traceability.get("results_explorer_ndtha_material_depth_pass", True)
        ),
        "results_explorer_geometry_full_crosswalk_depth_pass": bool(
            results_explorer_traceability.get("results_explorer_geometry_full_crosswalk_depth_pass", True)
        ),
        "results_explorer_geometry_full_crosswalk_detail_pass": bool(
            results_explorer_traceability.get("results_explorer_geometry_full_crosswalk_detail_pass", True)
        ),
        "results_explorer_contact_coupling_pass": bool(
            results_explorer_traceability.get("results_explorer_contact_coupling_pass", True)
        ),
        "results_explorer_contact_material_depth_pass": bool(
            results_explorer_traceability.get("results_explorer_contact_material_depth_pass", True)
        ),
        "results_explorer_general_fe_contact_surface_pass": bool(
            results_explorer_traceability.get("results_explorer_general_fe_contact_surface_pass", True)
        ),
        "results_explorer_traceability_rerun_label": str(
            results_explorer_traceability.get("results_explorer_traceability_rerun_label", "") or ""
        ),
        "results_explorer_traceability_rerun_command": str(
            results_explorer_traceability.get("results_explorer_traceability_rerun_command", "") or ""
        ),
        "results_explorer_traceability_source_report_count": int(
            results_explorer_traceability.get("results_explorer_traceability_source_report_count", 0) or 0
        ),
        "results_explorer_traceability_audit_report_count": int(
            results_explorer_traceability.get("results_explorer_traceability_audit_report_count", 0) or 0
        ),
        "results_explorer_traceability_output_report_count": int(
            results_explorer_traceability.get("results_explorer_traceability_output_report_count", 0) or 0
        ),
        "results_explorer_traceability_source_report_labels": [
            str(item)
            for item in results_explorer_traceability.get("results_explorer_traceability_source_report_labels", [])
            if str(item).strip()
        ],
        "results_explorer_traceability_audit_report_labels": [
            str(item)
            for item in results_explorer_traceability.get("results_explorer_traceability_audit_report_labels", [])
            if str(item).strip()
        ],
        "results_explorer_traceability_output_report_labels": [
            str(item)
            for item in results_explorer_traceability.get("results_explorer_traceability_output_report_labels", [])
            if str(item).strip()
        ],
        "roundtrip_mode": str(interoperability_summary.get("bounded_subset_mode", "") or ""),
        "native_roundtrip_corpus_case_count": int(native_roundtrip_summary.get("corpus_case_count", 0) or 0),
        "native_roundtrip_ready_case_count": int(native_roundtrip_summary.get("native_writeback_ready_count", 0) or 0),
        "native_roundtrip_public_ready_case_count": int(native_roundtrip_summary.get("public_native_writeback_ready_count", 0) or 0),
        "native_roundtrip_public_preview_ready_case_count": int(
            native_roundtrip_summary.get("public_archive_preview_writeback_ready_count", 0) or 0
        ),
        "native_roundtrip_public_structural_preview_text_case_count": int(
            native_roundtrip_summary.get("public_archive_structural_preview_text_case_count", 0) or 0
        ),
        "native_roundtrip_public_structural_preview_ready_case_count": int(
            native_roundtrip_summary.get("public_archive_structural_preview_writeback_ready_count", 0) or 0
        ),
        "native_roundtrip_public_source_ready_case_count": int(
            native_roundtrip_summary.get("public_source_writeback_ready_count", 0) or 0
        ),
        "native_roundtrip_exact_topology_archive_candidate_count": int(exact_topology_archive_candidate_count),
        "native_roundtrip_additional_exact_topology_archive_candidate_count": int(
            max(
                exact_topology_archive_candidate_count
                - int(native_roundtrip_summary.get("public_archive_structural_preview_writeback_ready_count", 0) or 0),
                0,
            )
        ),
        "native_roundtrip_fixture_ready_case_count": int(native_roundtrip_summary.get("fixture_native_writeback_ready_count", 0) or 0),
        "native_roundtrip_repo_ready_case_count": int(native_roundtrip_summary.get("repo_native_writeback_ready_count", 0) or 0),
        "native_roundtrip_experiment_ready_case_count": int(native_roundtrip_summary.get("experiment_native_writeback_ready_count", 0) or 0),
        "native_roundtrip_receipt_count": int(native_roundtrip_summary.get("receipt_count", 0) or 0),
        "native_roundtrip_source_family_count": int(native_roundtrip_summary.get("source_family_count", 0) or 0),
        "native_roundtrip_structure_type_batch_count": int(native_roundtrip_summary.get("structure_type_batch_count", 0) or 0),
        "native_roundtrip_pending_review_total": int(native_roundtrip_summary.get("pending_review_total", 0) or 0),
        "native_roundtrip_taxonomy_case_counts": (
            native_roundtrip_summary.get("taxonomy_case_counts")
            if isinstance(native_roundtrip_summary.get("taxonomy_case_counts"), dict)
            else {}
        ),
        "native_authoring_special_member_supported_action_family_counts": special_member_supported_action_family_counts,
        "native_authoring_special_member_direct_patch_action_family_counts": special_member_direct_patch_action_family_counts,
        "native_authoring_special_member_zero_touch_verified_action_family_counts": (
            special_member_zero_touch_verified_action_family_counts
        ),
        "remaining_limits": [str(item) for item in (interoperability_summary.get("remaining_limits") or []) if str(item).strip()],
        "exact_row_count": int(provenance_summary.get("exact_row_count", provenance_summary.get("exact_rows", 0)) or 0),
        "irregular_structure_track_pass": irregular_structure_track_pass,
        "irregular_structure_track_summary_line": str(irregular_artifacts.get("irregular_structure_track_summary_line", "") or ""),
        "irregular_structure_family_count": int(irregular_artifacts.get("irregular_structure_family_count", 0) or 0),
        "irregular_structure_source_record_count": int(irregular_artifacts.get("irregular_structure_source_record_count", 0) or 0),
        "irregular_structure_local_ready_count": int(irregular_artifacts.get("irregular_structure_local_ready_count", 0) or 0),
        "irregular_structure_remote_candidate_count": int(irregular_artifacts.get("irregular_structure_remote_candidate_count", 0) or 0),
        "irregular_structure_native_roundtrip_candidate_count": int(
            irregular_artifacts.get("irregular_structure_native_roundtrip_candidate_count", 0) or 0
        ),
        "irregular_structure_solver_benchmark_candidate_count": int(
            irregular_artifacts.get("irregular_structure_solver_benchmark_candidate_count", 0) or 0
        ),
        "irregular_structure_ai_learning_candidate_count": int(
            irregular_artifacts.get("irregular_structure_ai_learning_candidate_count", 0) or 0
        ),
        "irregular_structure_top5_count": int(irregular_artifacts.get("irregular_structure_top5_count", 0) or 0),
        "irregular_structure_top5_family_ids": [
            str(row.get("family_id", "") or "")
            for row in (irregular_artifacts.get("irregular_top5_families") or [])
            if isinstance(row, dict) and str(row.get("family_id", "") or "").strip()
        ],
        "irregular_benchmark_execution_ready_task_count": int(
            irregular_artifacts.get("irregular_benchmark_execution_ready_task_count", 0) or 0
        ),
        "irregular_benchmark_execution_blocked_task_count": int(
            irregular_artifacts.get("irregular_benchmark_execution_blocked_task_count", 0) or 0
        ),
        "irregular_benchmark_execution_summary_line": str(
            irregular_artifacts.get("irregular_benchmark_execution_summary_line", "") or ""
        ),
        "irregular_benchmark_execution_canonical_task_count": int(
            irregular_artifacts.get("irregular_benchmark_execution_canonical_task_count", 0) or 0
        ),
        "irregular_benchmark_execution_bridged_task_count": int(
            irregular_artifacts.get("irregular_benchmark_execution_bridged_task_count", 0) or 0
        ),
        "irregular_benchmark_execution_proxy_task_count": int(
            irregular_artifacts.get("irregular_benchmark_execution_proxy_task_count", 0) or 0
        ),
        "irregular_structure_gate_report_path": str(irregular_artifacts.get("irregular_structure_gate_report_path", "") or ""),
        "irregular_top5_execution_manifest_path": str(
            irregular_artifacts.get("irregular_top5_execution_manifest_path", "") or ""
        ),
        "irregular_benchmark_execution_manifest_path": str(
            irregular_artifacts.get("irregular_benchmark_execution_manifest_path", "") or ""
        ),
        "irregular_collection_report_path": str(irregular_artifacts.get("irregular_collection_report_path", "") or ""),
        "irregular_source_catalog_path": str(irregular_artifacts.get("irregular_source_catalog_path", "") or ""),
        "irregular_priority_manifest_path": str(irregular_artifacts.get("irregular_priority_manifest_path", "") or ""),
        "irregular_triage_report_path": str(irregular_artifacts.get("irregular_triage_report_path", "") or ""),
        "korean_source_ingest_summary_line": korean_source_ingest_summary_line,
        "korean_source_ingest_source_count": int(korean_source_ingest_summary.get("source_count", 0) or 0),
        "korean_source_ingest_source_class_count": int(korean_source_ingest_summary.get("source_class_count", 0) or 0),
        "korean_source_ingest_collected_count": int(korean_source_ingest_summary.get("collected_count", 0) or 0),
        "korean_source_ingest_metadata_only_count": int(
            korean_source_ingest_summary.get("metadata_only_remote_candidate_count", 0) or 0
        ),
        "korean_source_ingest_rejected_count": int(korean_source_ingest_summary.get("rejected_count", 0) or 0),
        "korean_source_ingest_fingerprinted_count": int(korean_source_ingest_summary.get("fingerprinted_count", 0) or 0),
        "korean_source_ingest_duplicate_sha_group_count": int(
            korean_source_ingest_summary.get("duplicate_sha_group_count", 0) or 0
        ),
        "korean_source_ingest_seed_metadata_complete_count": int(
            korean_source_ingest_summary.get("seed_metadata_complete_count", 0) or 0
        ),
        "korean_source_ingest_exact_topology_candidate_count": int(
            korean_source_ingest_summary.get("exact_topology_candidate_count", 0) or 0
        ),
        "korean_source_ingest_native_writeback_candidate_count": int(
            korean_source_ingest_summary.get("native_writeback_candidate_count", 0) or 0
        ),
        "korean_source_ingest_p0_focus_candidate_count": int(
            korean_source_ingest_summary.get("p0_focus_candidate_count", 0) or 0
        ),
        "korean_source_ingest_gate_report_path": str(korean_source_ingest_gate_report_path),
        "korean_structural_preview_queue_summary_line": korean_structural_preview_queue_summary_line,
        "korean_structural_preview_queue_candidate_total": korean_structural_preview_queue_candidate_total,
        "korean_structural_preview_queue_pending_candidate_count": korean_structural_preview_queue_pending_candidate_count,
        "korean_structural_preview_queue_state": korean_structural_preview_queue_state,
        "korean_structural_preview_promotion_queue_path": str(korean_structural_preview_promotion_queue_path),
    }
    summary_line = (
        "Workflow/interoperability productization: "
        f"{'PASS' if contract_pass else 'CHECK'} | "
        f"authoring=yes(direct_patch={summary['direct_patch_change_count']},payloads={summary['authoring_payload_available_count']},generated={summary['generated_authoring_artifact_count']},special_members={len(summary['native_authoring_special_member_direct_patch_action_family_counts'])}/{len(summary['native_authoring_special_member_supported_action_family_counts'])},zero_touch_special={len(summary['native_authoring_special_member_zero_touch_verified_action_family_counts'])}) | "
        f"signed=yes(artifacts={summary['generated_release_artifact_count']}) | audit=yes(mode={summary['audit_flow_mode']},packets={summary['audit_packet_count']},followup={summary['audit_followup_count']},resolution={summary['audit_resolution_count']},zero_touch={summary['zero_touch_native_authoring_count']}) | "
        f"audit_actions=yes(queue={summary['audit_queue_count']},generated={summary['generated_audit_artifact_count']},zero_touch={summary['zero_touch_native_authoring_count']}) | "
        f"case_attestation=yes(cases={summary['case_onepage_attestation_case_count']},manifests={summary['case_onepage_attestation_manifest_count']},templates={summary['case_onepage_attestation_template_count']},receipts={summary['case_onepage_attestation_receipt_count']},attested={summary['case_onepage_attestation_attested_count']},status={summary['case_onepage_attestation_status_label'] or 'none'}) | "
        f"auto_approved=yes(reason={summary['approve_all_preview_reason_code'] or 'n/a'},generated={summary['generated_auto_approved_subset_count']}) | "
        f"submission_bundle=yes(bundle={summary['signed_submission_bundle_id'] or 'missing'},generated={summary['generated_signed_submission_bundle_count']}) | "
        f"approval=yes(approve_all_ready={summary['approve_all_preview_ready_full']}) | "
        f"viewer=yes(results+review) | "
        f"results_explorer=yes(traceability={'pass' if summary['results_explorer_traceability_pass'] else 'check'},source={summary['results_explorer_traceability_source_report_count']},audit={summary['results_explorer_traceability_audit_report_count']},output={summary['results_explorer_traceability_output_report_count']},rerun={summary['results_explorer_traceability_rerun_label'] or 'n/a'},depths={summary['results_explorer_traceability_surface_depth_summary_label'] or 'n/a'},details={summary['results_explorer_traceability_surface_detail_summary_label'] or 'n/a'},general_fe_contact_matrix={summary['results_explorer_traceability_general_fe_contact_matrix_summary_line'] or 'n/a'},coupling={summary['results_explorer_traceability_contact_coupling_summary_label'] or 'n/a'},contact_material={summary['results_explorer_traceability_contact_material_depth_summary_label'] or 'n/a'}) | "
        f"native_roundtrip=yes(corpus={summary['native_roundtrip_corpus_case_count']},ready={summary['native_roundtrip_ready_case_count']},public={summary['native_roundtrip_public_source_ready_case_count']},native_public={summary['native_roundtrip_public_ready_case_count']},preview_public={summary['native_roundtrip_public_preview_ready_case_count']},structural_preview_public={summary['native_roundtrip_public_structural_preview_ready_case_count']},fixture={summary['native_roundtrip_fixture_ready_case_count']},repo={summary['native_roundtrip_repo_ready_case_count']},experiment={summary['native_roundtrip_experiment_ready_case_count']},receipts={summary['native_roundtrip_receipt_count']},types={summary['native_roundtrip_structure_type_batch_count']},taxonomy=exact:{int((summary['native_roundtrip_taxonomy_case_counts'] or {}).get('preserved_exact', 0) or 0)},canonical:{int((summary['native_roundtrip_taxonomy_case_counts'] or {}).get('canonical_rewrite', 0) or 0)},lossy:{int((summary['native_roundtrip_taxonomy_case_counts'] or {}).get('lossy_rewrite', 0) or 0)}) | "
        f"irregular_structure_track=yes(families={summary['irregular_structure_family_count']},sources={summary['irregular_structure_source_record_count']},local_ready={summary['irregular_structure_local_ready_count']},remote_candidates={summary['irregular_structure_remote_candidate_count']},native_candidates={summary['irregular_structure_native_roundtrip_candidate_count']},solver_candidates={summary['irregular_structure_solver_benchmark_candidate_count']},ai_candidates={summary['irregular_structure_ai_learning_candidate_count']},top5={summary['irregular_structure_top5_count']},exec_ready={summary['irregular_benchmark_execution_ready_task_count']},exec_blocked={summary['irregular_benchmark_execution_blocked_task_count']},exec_canonical={summary['irregular_benchmark_execution_canonical_task_count']},exec_bridged={summary['irregular_benchmark_execution_bridged_task_count']},exec_proxy={summary['irregular_benchmark_execution_proxy_task_count']},gate={Path(summary['irregular_structure_gate_report_path']).name if summary['irregular_structure_gate_report_path'] else 'missing'},manifest={Path(summary['irregular_top5_execution_manifest_path']).name if summary['irregular_top5_execution_manifest_path'] else 'missing'},exec_manifest={Path(summary['irregular_benchmark_execution_manifest_path']).name if summary['irregular_benchmark_execution_manifest_path'] else 'missing'}) | "
        f"korean_source_ingest=yes(sources={summary['korean_source_ingest_source_count']},classes={summary['korean_source_ingest_source_class_count']},collected={summary['korean_source_ingest_collected_count']},fingerprinted={summary['korean_source_ingest_fingerprinted_count']},metadata_only={summary['korean_source_ingest_metadata_only_count']},rejected={summary['korean_source_ingest_rejected_count']},dup_sha={summary['korean_source_ingest_duplicate_sha_group_count']},seed_complete={summary['korean_source_ingest_seed_metadata_complete_count']},exact_topology={summary['korean_source_ingest_exact_topology_candidate_count']},native_writeback={summary['korean_source_ingest_native_writeback_candidate_count']},p0_focus={summary['korean_source_ingest_p0_focus_candidate_count']}) | "
        f"korean_structural_preview_queue=yes(candidates={summary['korean_structural_preview_queue_candidate_total']},pending={summary['korean_structural_preview_queue_pending_candidate_count']},state={summary['korean_structural_preview_queue_state'] or 'missing'}) | "
        f"roundtrip={summary['roundtrip_mode'] or 'missing'} | "
        f"exact_rows={summary['exact_row_count']}"
    )
    return {
        "schema_version": "1.0",
        "run_id": "phase1-workflow-productization-gate",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
        "summary": summary,
        "generated_artifacts": generated_artifacts,
        "summary_line": summary_line,
        "contract_pass": contract_pass,
        "reason_code": reason_code,
        "reason": REASONS[reason_code],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release-registry-report", default="implementation/phase1/release/release_registry.json")
    parser.add_argument("--midas-interoperability-report", default="implementation/phase1/midas_interoperability_gate_report.json")
    parser.add_argument("--midas-native-roundtrip-report", default="implementation/phase1/midas_native_roundtrip_gate_report.json")
    parser.add_argument(
        "--row-provenance-export-report",
        default="implementation/phase1/release/kds_compliance/midas_kds_row_provenance_table_report.json",
    )
    parser.add_argument("--viewer-json", default="implementation/phase1/release/visualization/structural_optimization_viewer.json")
    parser.add_argument("--viewer-html", default="implementation/phase1/release/visualization/structural_optimization_viewer.html")
    parser.add_argument(
        "--irregular-structure-source-catalog",
        default="implementation/phase1/open_data/irregular/irregular_structure_source_catalog.json",
    )
    parser.add_argument(
        "--irregular-structure-priority-families",
        default="implementation/phase1/open_data/irregular/priority_irregular_structure_families.json",
    )
    parser.add_argument(
        "--irregular-structure-triage-report",
        default="implementation/phase1/open_data/irregular/irregular_structure_triage_report.json",
    )
    parser.add_argument(
        "--irregular-structure-collection-report",
        default="implementation/phase1/open_data/irregular/irregular_structure_collection_report.json",
    )
    parser.add_argument(
        "--irregular-structure-gate-report",
        default="implementation/phase1/irregular_structure_collection_gate_report.json",
    )
    parser.add_argument(
        "--irregular-top5-execution-manifest",
        default="implementation/phase1/open_data/irregular/irregular_top5_execution_manifest.json",
    )
    parser.add_argument(
        "--irregular-benchmark-execution-manifest",
        default="implementation/phase1/release/external_benchmark_kickoff/irregular_benchmark_execution_manifest.json",
    )
    parser.add_argument(
        "--korean-source-ingest-gate-report",
        default="implementation/phase1/korean_source_ingest_gate_report.json",
    )
    parser.add_argument(
        "--korean-structural-preview-promotion-queue",
        default="implementation/phase1/release/midas_native_roundtrip/exact_topology_structural_preview_promotion_queue.json",
    )
    parser.add_argument("--out", default="implementation/phase1/workflow_productization_gate_report.json")
    args = parser.parse_args()

    input_payload = {
        "release_registry_report": str(args.release_registry_report),
        "midas_interoperability_report": str(args.midas_interoperability_report),
        "midas_native_roundtrip_report": str(args.midas_native_roundtrip_report),
        "row_provenance_export_report": str(args.row_provenance_export_report),
        "viewer_json": str(args.viewer_json),
        "viewer_html": str(args.viewer_html),
        "irregular_structure_source_catalog": str(args.irregular_structure_source_catalog),
        "irregular_structure_priority_families": str(args.irregular_structure_priority_families),
        "irregular_structure_triage_report": str(args.irregular_structure_triage_report),
        "irregular_structure_collection_report": str(args.irregular_structure_collection_report),
        "irregular_structure_gate_report": str(args.irregular_structure_gate_report),
        "irregular_top5_execution_manifest": str(args.irregular_top5_execution_manifest),
        "irregular_benchmark_execution_manifest": str(args.irregular_benchmark_execution_manifest),
        "korean_source_ingest_gate_report": str(args.korean_source_ingest_gate_report),
        "korean_structural_preview_promotion_queue": str(args.korean_structural_preview_promotion_queue),
        "out": str(args.out),
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        validate_input_contract(input_payload, INPUT_SCHEMA, label="phase1.run_workflow_productization_gate")
        viewer_html_text = Path(args.viewer_html).read_text(encoding="utf-8") if Path(args.viewer_html).exists() else ""
        report = run_workflow_productization_gate(
            release_registry_report=_load_json(Path(args.release_registry_report)),
            release_registry_path=Path(args.release_registry_report),
            midas_interoperability_report=_load_json(Path(args.midas_interoperability_report)),
            midas_native_roundtrip_report=_load_json(Path(args.midas_native_roundtrip_report)),
            row_provenance_export_report=_load_json(Path(args.row_provenance_export_report)),
            viewer_json=_load_json(Path(args.viewer_json)),
            viewer_html_text=viewer_html_text,
            irregular_structure_source_catalog_path=Path(args.irregular_structure_source_catalog),
            irregular_structure_priority_families_path=Path(args.irregular_structure_priority_families),
            irregular_structure_triage_report_path=Path(args.irregular_structure_triage_report),
            irregular_structure_collection_report_path=Path(args.irregular_structure_collection_report),
            irregular_structure_gate_report_path=Path(args.irregular_structure_gate_report),
            irregular_top5_execution_manifest_path=Path(args.irregular_top5_execution_manifest),
            irregular_benchmark_execution_manifest_path=Path(args.irregular_benchmark_execution_manifest),
            korean_source_ingest_gate_report_path=Path(args.korean_source_ingest_gate_report),
            korean_structural_preview_promotion_queue_path=Path(args.korean_structural_preview_promotion_queue),
        )
        report["inputs"] = input_payload
    except (InputContractError, ValueError, FileNotFoundError) as exc:
        report = {
            "schema_version": "1.0",
            "run_id": "phase1-workflow-productization-gate",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": input_payload,
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": f"{REASONS['ERR_INVALID_INPUT']}: {exc}",
        }
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote workflow productization gate report: {out}")
    raise SystemExit(0 if bool(report.get('contract_pass', False)) else 1)


if __name__ == "__main__":
    main()
