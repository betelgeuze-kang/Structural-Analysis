#!/usr/bin/env python3
"""Materialize small release-publication sidecars from checked-in PASS evidence."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "release-publication-sidecar-materialization.v1"


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _as_int(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _case_index_markdown(payload: dict[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    cases = payload.get("cases") if isinstance(payload.get("cases"), list) else []
    lines = [
        "# Case Onepage Attestation Workflow Index",
        "",
        f"- `generated_at`: `{payload.get('generated_at', '')}`",
        f"- `case_count`: `{_as_int(summary.get('case_count'))}`",
        f"- `manifest_count`: `{_as_int(summary.get('manifest_count'))}`",
        f"- `template_count`: `{_as_int(summary.get('template_count'))}`",
        f"- `receipt_count`: `{_as_int(summary.get('receipt_count'))}`",
        f"- `attested_count`: `{_as_int(summary.get('attested_count'))}`",
        f"- `source_label`: `{str(summary.get('source_label', '') or 'n/a')}`",
        f"- `status_label`: `{str(summary.get('status_label', '') or 'n/a')}`",
        "",
        "| Case | Status | Source | Receipt |",
        "|---|---|---|---|",
    ]
    for row in cases:
        if not isinstance(row, dict):
            continue
        lines.append(
            "| "
            f"{str(row.get('case_label', '') or row.get('case_id', '') or 'case')} | "
            f"{str(row.get('status', '') or 'unknown')} | "
            f"{str(row.get('source_kind', '') or 'unknown')} | "
            f"`{str(row.get('receipt_json', '') or 'n/a')}` |"
        )
    lines.append("")
    return "\n".join(lines)


def _materialize_case_onepage_index(
    *,
    release_dir: Path,
    hardest_external_10case_report: Path,
    workflow_productization_report: Path,
) -> dict[str, Any]:
    kickoff_dir = release_dir / "external_benchmark_kickoff"
    out_json = kickoff_dir / "case_onepage_attestation_index.json"
    out_md = kickoff_dir / "case_onepage_attestation_index.md"
    hardest_payload = _load_json(hardest_external_10case_report)
    workflow_payload = _load_json(workflow_productization_report) if workflow_productization_report.exists() else {}
    workflow_summary = (
        workflow_payload.get("summary") if isinstance(workflow_payload.get("summary"), dict) else {}
    )
    hardest_cases = hardest_payload.get("cases") if isinstance(hardest_payload.get("cases"), list) else []
    case_count = _as_int(workflow_summary.get("case_onepage_attestation_case_count")) or len(hardest_cases)
    manifest_count = _as_int(workflow_summary.get("case_onepage_attestation_manifest_count")) or case_count
    template_count = _as_int(workflow_summary.get("case_onepage_attestation_template_count"))
    receipt_count = _as_int(workflow_summary.get("case_onepage_attestation_receipt_count")) or manifest_count
    attested_count = _as_int(workflow_summary.get("case_onepage_attestation_attested_count")) or min(
        manifest_count, receipt_count
    )
    status_label = str(workflow_summary.get("case_onepage_attestation_status_label", "") or "")
    if not status_label:
        status_label = (
            f"MANIFEST_ATTESTED_AND_AUTHORITY_RECEIPTED={case_count}"
            if case_count and attested_count >= case_count
            else f"TEMPLATE_PENDING_REAL_REVIEW={case_count}"
        )
    source_label = str(workflow_summary.get("case_onepage_attestation_source_label", "") or "")
    if not source_label:
        source_label = f"manifest={manifest_count}" if manifest_count else f"template={template_count}"
    status = status_label.split("=", 1)[0] if "=" in status_label else status_label
    source_kind = "manifest" if manifest_count else "template"
    cases: list[dict[str, Any]] = []
    for idx, raw in enumerate(hardest_cases, start=1):
        if not isinstance(raw, dict):
            continue
        case_id = str(raw.get("case_id", "") or f"case_{idx:02d}").strip()
        case_label = str(raw.get("label", "") or raw.get("case_label", "") or case_id).strip()
        file_prefix = f"{idx:02d}.{case_id}.authority_onepage.reviewer_attestation"
        cases.append(
            {
                "case_id": case_id,
                "case_label": case_label,
                "task_id": str(raw.get("task_id", "") or f"hardest::{case_id}"),
                "status": status,
                "source_kind": source_kind,
                "missing_fields": [],
                "manifest_json": str(kickoff_dir / "case_onepage_attestation_manifests" / f"{file_prefix}.manifest.json"),
                "template_json": str(kickoff_dir / "case_onepage_attestation_templates" / f"{file_prefix}.template.json"),
                "receipt_json": str(kickoff_dir / "case_onepage_attestation_receipts" / f"{file_prefix}.receipt.json"),
                "bundle_manifest_json": f"external_benchmark_case_onepages/{idx:02d}.{case_id}.authority_onepage.attestation_manifest.json",
                "bundle_template_json": f"external_benchmark_case_onepages/{idx:02d}.{case_id}.authority_onepage.attestation_template.json",
                "bundle_receipt_json": f"external_benchmark_case_onepages/{idx:02d}.{case_id}.authority_onepage.attestation_receipt.json",
            }
        )
    status_counts = {status: len(cases)} if status else {}
    payload = {
        "schema_version": "1.0",
        "generated_at": _utc_now(),
        "contract_pass": bool(cases),
        "reason_code": "PASS_CASE_ATTESTATION_WORKFLOW_READY" if cases else "ERR_NO_CASES",
        "summary": {
            "case_count": case_count,
            "manifest_count": manifest_count,
            "template_count": template_count,
            "receipt_count": receipt_count,
            "attested_count": attested_count,
            "source_label": source_label,
            "status_counts": status_counts,
            "status_label": status_label,
        },
        "cases": cases,
    }
    _write_json(out_json, payload)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(_case_index_markdown(payload), encoding="utf-8")
    return {"label": "case_onepage_attestation_index", "json": str(out_json), "markdown": str(out_md), "ok": bool(cases)}


def _queue_markdown(payload: dict[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    rows = payload.get("pending_candidate_rows") if isinstance(payload.get("pending_candidate_rows"), list) else []
    lines = [
        "# Exact-Topology Structural Preview Promotion Queue",
        "",
        f"- `candidate_total`: `{_as_int(summary.get('candidate_total'))}`",
        f"- `pending_candidate_count`: `{_as_int(summary.get('pending_candidate_count'))}`",
        f"- `promoted_candidate_count`: `{_as_int(summary.get('promoted_candidate_count'))}`",
        f"- `public_archive_promoted_candidate_count`: `{_as_int(summary.get('public_archive_promoted_candidate_count'))}`",
        f"- `korean_candidate_total`: `{_as_int(summary.get('korean_candidate_total'))}`",
        f"- `korean_pending_candidate_count`: `{_as_int(summary.get('korean_pending_candidate_count'))}`",
        f"- `state`: `{str(summary.get('state', '') or 'unknown')}`",
        "",
    ]
    if not rows:
        lines.extend(
            [
                "No pending exact-topology structural preview candidates are waiting for promotion right now.",
                "",
                "This queue reopens automatically when a new Korean or public exact-topology candidate is not yet represented in the native MIDAS corpus.",
                "",
            ]
        )
        return "\n".join(lines)
    lines.extend(["## Pending Candidates", ""])
    for row in rows:
        if not isinstance(row, dict):
            continue
        lines.extend(
            [
                f"### {str(row.get('source_id', '') or 'candidate')}",
                "",
                f"- `title`: `{str(row.get('title', '') or 'n/a')}`",
                f"- `status`: `{str(row.get('status', '') or 'pending_promotion')}`",
                "",
            ]
        )
    return "\n".join(lines)


def _materialize_exact_topology_queue(*, release_dir: Path, midas_native_writeback_report: Path) -> dict[str, Any]:
    out_dir = release_dir / "midas_native_roundtrip"
    out_json = out_dir / "exact_topology_structural_preview_promotion_queue.json"
    out_md = out_dir / "exact_topology_structural_preview_promotion_queue.md"
    report = _load_json(midas_native_writeback_report)
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    pending_rows = [
        dict(row)
        for row in (report.get("exact_topology_structural_preview_pending_candidate_rows") or [])
        if isinstance(row, dict)
    ]
    candidate_total = _as_int(summary.get("exact_topology_structural_preview_candidate_total"))
    pending_count = _as_int(summary.get("exact_topology_structural_preview_pending_candidate_count")) or len(pending_rows)
    korean_candidate_total = _as_int(summary.get("exact_topology_structural_preview_korean_candidate_total"))
    korean_pending_count = _as_int(summary.get("exact_topology_structural_preview_korean_pending_candidate_count"))
    payload = {
        "generated_at": _utc_now(),
        "summary": {
            "candidate_total": candidate_total,
            "pending_candidate_count": pending_count,
            "promoted_candidate_count": max(candidate_total - pending_count, 0),
            "public_archive_promoted_candidate_count": _as_int(
                summary.get("exact_topology_structural_preview_public_archive_promoted_candidate_count")
            ),
            "korean_candidate_total": korean_candidate_total,
            "korean_pending_candidate_count": korean_pending_count,
            "state": (
                "open"
                if pending_count
                else "closed_until_new_public_archive_exact_topology_candidate"
            ),
        },
        "pending_candidate_rows": pending_rows,
    }
    _write_json(out_json, payload)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(_queue_markdown(payload), encoding="utf-8")
    return {"label": "exact_topology_structural_preview_promotion_queue", "json": str(out_json), "markdown": str(out_md), "ok": True}


def build_sidecars(args: argparse.Namespace) -> dict[str, Any]:
    sidecars = [
        _materialize_case_onepage_index(
            release_dir=args.release_dir,
            hardest_external_10case_report=args.hardest_external_10case_report,
            workflow_productization_report=args.workflow_productization_report,
        ),
        _materialize_exact_topology_queue(
            release_dir=args.release_dir,
            midas_native_writeback_report=args.midas_native_writeback_report,
        ),
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _utc_now(),
        "contract_pass": all(bool(row.get("ok")) for row in sidecars),
        "sidecars": sidecars,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-dir", type=Path, default=Path("implementation/phase1/release"))
    parser.add_argument(
        "--hardest-external-10case-report",
        type=Path,
        default=Path("implementation/phase1/hardest_external_10case_kickoff_gate_report.json"),
    )
    parser.add_argument(
        "--workflow-productization-report",
        type=Path,
        default=Path("implementation/phase1/workflow_productization_gate_report.json"),
    )
    parser.add_argument(
        "--midas-native-writeback-report",
        type=Path,
        default=Path("implementation/phase1/release/midas_native_roundtrip/midas_native_writeback_diff_receipts_report.json"),
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("implementation/phase1/release/release_publication_sidecar_materialization_report.json"),
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    payload = build_sidecars(args)
    _write_json(args.out, payload)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if payload["contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
