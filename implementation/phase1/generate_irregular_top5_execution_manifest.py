#!/usr/bin/env python3
"""Generate the top-5 irregular structure execution manifest."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE_CATALOG = REPO_ROOT / "implementation/phase1/open_data/irregular/irregular_structure_source_catalog.json"
DEFAULT_PRIORITY = REPO_ROOT / "implementation/phase1/open_data/irregular/priority_irregular_structure_families.json"
DEFAULT_TRIAGE = REPO_ROOT / "implementation/phase1/open_data/irregular/irregular_structure_triage_report.json"
DEFAULT_COLLECTION = REPO_ROOT / "implementation/phase1/open_data/irregular/irregular_structure_collection_report.json"
DEFAULT_OUT = REPO_ROOT / "implementation/phase1/open_data/irregular/irregular_top5_execution_manifest.json"


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


EXECUTABLE_FORMATS = {
    "mgt",
    "mcb",
    "meb",
    "mmbx",
    "tcl",
    "json_graph",
    "npz",
    "csv_tables",
    "ifc",
    "step",
    "iges",
    "dxf",
    "model_text",
}
NON_EXECUTABLE_SUFFIXES = {
    ".pdf",
    ".md",
    ".html",
    ".htm",
    ".txt",
}
STRONG_EXECUTABLE_SUFFIXES = {
    ".mgt",
    ".mcb",
    ".meb",
    ".mmbx",
    ".tcl",
    ".inp",
    ".ifc",
    ".step",
    ".stp",
    ".iges",
    ".igs",
    ".dxf",
    ".csv",
    ".npz",
}


def _artifact_path(path: str | Path) -> str:
    return str(path or "").strip()


def _collection_rows_by_source_id(collection_report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = collection_report.get("records") if isinstance(collection_report.get("records"), list) else []
    return {
        str(row.get("source_id", "") or "").strip(): row
        for row in rows
        if isinstance(row, dict) and str(row.get("source_id", "") or "").strip()
    }


def _collection_artifact_path(row: dict[str, Any]) -> str:
    artifacts = row.get("artifacts") if isinstance(row.get("artifacts"), dict) else {}
    return _artifact_path(artifacts.get("copied_source_path", ""))


def _is_executable_asset(*, path: str, primary_format: str, collection_row: dict[str, Any] | None = None) -> bool:
    normalized = _artifact_path(path)
    if not normalized:
        return False
    suffix = Path(normalized).suffix.lower()
    if suffix in NON_EXECUTABLE_SUFFIXES:
        return False
    if suffix in STRONG_EXECUTABLE_SUFFIXES:
        return True
    metadata = collection_row.get("metadata") if isinstance(collection_row, dict) else {}
    provider_asset_kind = str((metadata or {}).get("provider_asset_kind", "") or "").strip().lower()
    if provider_asset_kind.endswith("_pdf"):
        return False
    if primary_format in EXECUTABLE_FORMATS:
        if primary_format == "json_graph":
            return suffix == ".json"
        return True
    return False


def _score_record(row: dict[str, Any]) -> tuple[int, int, int, int, str]:
    executable_path = str(row.get("_execution_path", "") or "").strip()
    reference_path = str(row.get("_reference_path", "") or "").strip()
    authority_fit = str(row.get("authority_fit", "") or "").strip().lower()
    authority_score = {"very-high": 4, "high": 3, "medium-high": 2, "medium": 1}.get(authority_fit, 0)
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    benchmark_canonical_eligible = metadata.get("benchmark_canonical_eligible", True)
    source_kind = str(row.get("source_kind", "") or "").strip().lower()
    evidence_class = str(row.get("evidence_class", "") or "").strip().lower()
    if _has_explicit_bridge_evidence(row):
        benchmark_priority = 1
    elif benchmark_canonical_eligible is False or source_kind == "repo_local_native_binary_support":
        benchmark_priority = 2
    elif source_kind in {"public_native_source", "repo_local_source"} or evidence_class in {
        "public_native_mgt",
        "repo_local_text_model",
        "official_benchmark_native_text",
    }:
        benchmark_priority = 0
    else:
        benchmark_priority = 3
    return (
        0 if executable_path else 1,
        0 if reference_path else 1,
        benchmark_priority,
        -authority_score,
        int(row.get("priority", 999) or 999),
        str(row.get("source_id", "") or ""),
    )


def _looks_bridged_path(value: object) -> bool:
    return "/bridged/" in str(value or "").replace("\\", "/").lower()


def _has_bridge_report(value: object) -> bool:
    values = value if isinstance(value, list) else [value]
    return any(Path(str(item or "").strip()).name == "bridge_report.json" for item in values)


def _has_explicit_bridge_evidence(row: dict[str, Any]) -> bool:
    source_kind = str(row.get("source_kind", "") or "").strip().lower()
    evidence_class = str(row.get("evidence_class", "") or "").strip().lower()
    if "bridged" in source_kind or "bridged" in evidence_class:
        return True
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    bridge_report_path = str(metadata.get("bridge_report_path", "") or "").strip()
    companion_paths = row.get("companion_paths") if isinstance(row.get("companion_paths"), list) else []
    candidate_paths = [
        row.get("local_path", ""),
        row.get("_execution_path", ""),
        row.get("_reference_path", ""),
    ]
    return any(_looks_bridged_path(path) for path in candidate_paths) and _has_bridge_report(
        [*companion_paths, bridge_report_path]
    )


def _ready_execution_mode(row: dict[str, Any]) -> str:
    source_kind = str(row.get("source_kind", "") or "").strip().lower()
    evidence_class = str(row.get("evidence_class", "") or "").strip().lower()
    primary_format = _record_primary_format(row).strip().lower()
    execution_path = str(row.get("_execution_path", row.get("local_path", "")) or "").strip()
    suffix = Path(execution_path).suffix.lower()
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    benchmark_canonical_eligible = metadata.get("benchmark_canonical_eligible", True)
    if _has_explicit_bridge_evidence(row):
        return "ready_local_bridged_now"
    if benchmark_canonical_eligible is False or source_kind == "repo_local_native_binary_support":
        return "reference_collected_only"
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
        return "ready_local_canonical_now"
    if "proxy" in source_kind or "proxy" in evidence_class or primary_format in {"csv_tables", "npz"}:
        return "ready_local_proxy_now"
    if source_kind in {"public_native_source", "repo_local_source"} or evidence_class in {
        "public_native_mgt",
        "repo_local_text_model",
    }:
        return "ready_local_canonical_now"
    return "ready_local_canonical_now"


def _native_support_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    support_rows: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        source_kind = str(row.get("source_kind", "") or "").strip().lower()
        metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        if source_kind == "repo_local_native_binary_support" or str(metadata.get("native_local_scope", "") or "").strip() == "native_roundtrip_only":
            support_rows.append(row)
    return support_rows


def _official_support_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    support_rows: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        source_kind = str(row.get("source_kind", "") or "").strip().lower()
        evidence_class = str(row.get("evidence_class", "") or "").strip().lower()
        if source_kind == "official_remote_candidate" or evidence_class in {
            "official_benchmark_remote",
            "official_reference_remote",
        }:
            support_rows.append(row)
    return support_rows


def generate_manifest(*, source_catalog: dict[str, Any], priority_manifest: dict[str, Any], triage_report: dict[str, Any], collection_report: dict[str, Any], source_catalog_path: Path, priority_path: Path, triage_path: Path, collection_path: Path) -> dict[str, Any]:
    source_families = source_catalog.get("structure_families") if isinstance(source_catalog.get("structure_families"), list) else []
    source_records = source_catalog.get("source_records") if isinstance(source_catalog.get("source_records"), list) else []
    triage_summary = triage_report.get("summary") if isinstance(triage_report.get("summary"), dict) else {}
    collection_summary = collection_report.get("summary") if isinstance(collection_report.get("summary"), dict) else {}

    families_by_id = {
        str(row.get("id", "") or "").strip(): row
        for row in source_families
        if isinstance(row, dict) and str(row.get("id", "") or "").strip()
    }
    records_by_family: dict[str, list[dict[str, Any]]] = {}
    for row in source_records:
        if not isinstance(row, dict):
            continue
        family_id = str(row.get("family_id", "") or "").strip()
        if family_id:
            records_by_family.setdefault(family_id, []).append(row)
    collection_rows_by_source_id = _collection_rows_by_source_id(collection_report)

    priority_families = [
        row for row in (priority_manifest.get("families") if isinstance(priority_manifest.get("families"), list) else []) if isinstance(row, dict)
    ]
    selected = sorted(priority_families, key=lambda row: (int(row.get("priority", 999) or 999), str(row.get("id", "") or "")))[:5]

    top5_rows: list[dict[str, Any]] = []
    for family in selected:
        family_id = str(family.get("id", "") or "").strip()
        family_summary = families_by_id.get(family_id, {})
        raw_family_records = records_by_family.get(family_id, [])
        family_records: list[dict[str, Any]] = []
        execution_ready_source_count = 0
        reference_collected_source_count = 0
        for base_row in raw_family_records:
            row = dict(base_row)
            source_id = str(row.get("source_id", "") or "").strip()
            collection_row = collection_rows_by_source_id.get(source_id, {})
            primary_format = _record_primary_format(row)
            collection_status = str(
                collection_row.get("status", row.get("collection_status", "")) or ""
            ).strip()
            local_path = _artifact_path(row.get("local_path", ""))
            copied_path = _collection_artifact_path(collection_row)
            execution_path = local_path if _is_executable_asset(path=local_path, primary_format=primary_format) else ""
            if not execution_path and copied_path and _is_executable_asset(path=copied_path, primary_format=primary_format, collection_row=collection_row):
                execution_path = copied_path
            reference_path = copied_path or local_path
            if execution_path:
                execution_ready_source_count += 1
            elif collection_status == "collected" and reference_path:
                reference_collected_source_count += 1
            row["_execution_path"] = execution_path
            row["_reference_path"] = reference_path
            row["_collection_status_effective"] = collection_status
            family_records.append(row)
        family_records = sorted(family_records, key=_score_record)
        source_record_count = int(family_summary.get("source_record_count", len(family_records)) or len(family_records))
        local_ready_source_count = execution_ready_source_count
        if execution_ready_source_count > 0:
            execution_mode = "ready_local_now"
        elif reference_collected_source_count > 0:
            execution_mode = "reference_collected_only"
        else:
            execution_mode = "remote_source_hunt_needed"
        chosen = family_records[0] if family_records else {}
        if execution_ready_source_count > 0:
            execution_mode = _ready_execution_mode(chosen)
        native_support_rows = _native_support_rows(family_records)
        native_support_ids = [
            str(row.get("source_id", "") or "").strip()
            for row in native_support_rows
            if str(row.get("source_id", "") or "").strip()
        ]
        native_support_formats = sorted(
            {
                _record_primary_format(row)
                for row in native_support_rows
                if _record_primary_format(row)
            }
        )
        native_support_local_paths = [
            str(row.get("_execution_path", "") or row.get("local_path", "") or "").strip()
            for row in native_support_rows
            if str(row.get("_execution_path", "") or row.get("local_path", "") or "").strip()
        ]
        official_support_rows = _official_support_rows(family_records)
        official_support_ids = [
            str(row.get("source_id", "") or "").strip()
            for row in official_support_rows
            if str(row.get("source_id", "") or "").strip()
        ]
        native_support_summary = ""
        if native_support_ids:
            native_support_summary = (
                f"native MEB support via {', '.join(native_support_ids)}"
                if "meb" in native_support_formats
                else f"native support via {', '.join(native_support_ids)}"
            )
        official_support_summary = ""
        if official_support_ids:
            official_support_summary = f"official benchmark documentation via {', '.join(official_support_ids)}"
        support_summary = native_support_summary
        if official_support_summary:
            support_summary = (
                f"{support_summary}; {official_support_summary}"
                if support_summary
                else official_support_summary
            )
        execution_mode_label = execution_mode
        if execution_mode == "ready_local_bridged_now" and native_support_summary:
            execution_mode_label = f"{execution_mode} + native_meb_support"
        if execution_mode == "ready_local_bridged_now" and official_support_summary:
            execution_mode_label = f"{execution_mode_label} + official_docs"
        top5_rows.append(
            {
                "family_id": family_id,
                "priority": int(family.get("priority", family_summary.get("priority", 0)) or 0),
                "execution_mode": execution_mode,
                "execution_mode_label": execution_mode_label,
                "source_record_count": source_record_count,
                "local_ready_source_count": local_ready_source_count,
                "execution_ready_source_count": execution_ready_source_count,
                "reference_collected_source_count": reference_collected_source_count,
                "remote_candidate_source_count": max(source_record_count - local_ready_source_count, 0),
                "authority_fit": str(family_summary.get("authority_fit", family.get("authority_fit", "")) or ""),
                "ai_learning_fit": str(family_summary.get("ai_learning_fit", family.get("ai_learning_fit", "")) or ""),
                "recommended_kpi_or_validation_angle": str(family_summary.get("recommended_kpi_or_validation_angle", family.get("recommended_kpi_or_validation_angle", "")) or ""),
                "irregularity_tags": [str(tag).strip() for tag in (family_summary.get("irregularity_tags") if isinstance(family_summary.get("irregularity_tags"), list) else family.get("irregularity_tags", [])) if str(tag).strip()],
                "why_it_matters": str(family_summary.get("why_it_matters", family.get("why_it_matters", "")) or ""),
                "recommended_source_id": str(chosen.get("source_id", "") or ""),
                "recommended_source_title": str(chosen.get("title", "") or ""),
                "recommended_source_kind": str(chosen.get("source_kind", "") or ""),
                "recommended_evidence_class": str(chosen.get("evidence_class", "") or ""),
                "recommended_source_format": _record_primary_format(chosen),
                "recommended_local_path": str(chosen.get("_execution_path", "") or ""),
                "recommended_reference_path": str(chosen.get("_reference_path", "") or ""),
                "recommended_collection_status": str(chosen.get("_collection_status_effective", chosen.get("collection_status", "")) or ""),
                "recommended_source_urls": [str(url).strip() for url in (chosen.get("source_urls") if isinstance(chosen.get("source_urls"), list) else []) if str(url).strip()],
                "source_ids": [str(row.get("source_id", "") or "").strip() for row in family_records if str(row.get("source_id", "") or "").strip()],
                "source_formats": sorted({_record_primary_format(row) for row in family_records if _record_primary_format(row)}),
                "local_paths": [str(row.get("_execution_path", "") or "").strip() for row in family_records if str(row.get("_execution_path", "") or "").strip()],
                "reference_paths": [str(row.get("_reference_path", "") or "").strip() for row in family_records if str(row.get("_reference_path", "") or "").strip()],
                "collection_statuses": sorted({str(row.get("_collection_status_effective", row.get("collection_status", "")) or "").strip() for row in family_records if str(row.get("_collection_status_effective", row.get("collection_status", "")) or "").strip()}),
                "native_support_source_ids": native_support_ids,
                "native_support_formats": native_support_formats,
                "native_support_local_paths": native_support_local_paths,
                "native_support_summary": support_summary,
                "official_support_source_ids": official_support_ids,
                "official_support_summary": official_support_summary,
            }
        )

    summary = {
        "family_count": int((source_catalog.get("summary") or {}).get("family_count", len(source_families)) or len(source_families)),
        "source_record_count": int((source_catalog.get("summary") or {}).get("source_record_count", len(source_records)) or len(source_records)),
        "native_roundtrip_candidate_count": int(triage_summary.get("native_roundtrip_candidate_count", 0) or 0),
        "solver_benchmark_candidate_count": int(triage_summary.get("solver_benchmark_candidate_count", 0) or 0),
        "ai_learning_candidate_count": int(triage_summary.get("ai_learning_candidate_count", 0) or 0),
        "quick_start_local_source_count": int(triage_summary.get("quick_start_local_source_count", 0) or 0),
        "collected_count": int(collection_summary.get("collected_count", 0) or 0),
        "metadata_only_remote_candidate_count": int(collection_summary.get("metadata_only_remote_candidate_count", 0) or 0),
        "top5_count": len(top5_rows),
        "top5_local_ready_count": sum(
            1 for row in top5_rows if str(row.get("execution_mode", "") or "").startswith("ready_local")
        ),
        "top5_proxy_ready_count": sum(1 for row in top5_rows if row.get("execution_mode") == "ready_local_proxy_now"),
        "top5_bridged_ready_count": sum(1 for row in top5_rows if row.get("execution_mode") == "ready_local_bridged_now"),
        "top5_canonical_ready_count": sum(1 for row in top5_rows if row.get("execution_mode") == "ready_local_canonical_now"),
        "top5_reference_collected_count": sum(1 for row in top5_rows if row.get("execution_mode") == "reference_collected_only"),
        "top5_remote_needed_count": sum(1 for row in top5_rows if row.get("execution_mode") == "remote_source_hunt_needed"),
    }
    contract_pass = len(top5_rows) >= 1
    summary_line = (
        "Irregular top5 execution manifest: "
        f"{'PASS' if contract_pass else 'CHECK'} | top5={summary['top5_count']} | "
        f"local_ready={summary['top5_local_ready_count']} | remote_needed={summary['top5_remote_needed_count']} | "
        f"proxy_ready={summary['top5_proxy_ready_count']} | "
        f"bridged_ready={summary['top5_bridged_ready_count']} | "
        f"canonical_ready={summary['top5_canonical_ready_count']} | "
        f"reference_collected={summary['top5_reference_collected_count']} | "
        f"native_roundtrip_candidates={summary['native_roundtrip_candidate_count']} | "
        f"solver_candidates={summary['solver_benchmark_candidate_count']} | ai_candidates={summary['ai_learning_candidate_count']}"
    )
    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "track_name": str(source_catalog.get("track_name", "") or "irregular_structure_corpus_track"),
        "source_catalog_path": str(source_catalog_path),
        "priority_manifest_path": str(priority_path),
        "triage_report_path": str(triage_path),
        "collection_report_path": str(collection_path),
        "summary": summary,
        "summary_line": summary_line,
        "contract_pass": contract_pass,
        "reason_code": "PASS" if contract_pass else "ERR_INVALID_INPUT",
        "reason": "irregular top5 execution manifest generated" if contract_pass else "irregular top5 execution manifest inputs incomplete",
        "top5_families": top5_rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-catalog", "--catalog", dest="source_catalog", default=str(DEFAULT_SOURCE_CATALOG))
    parser.add_argument("--priority-families", default=str(DEFAULT_PRIORITY))
    parser.add_argument("--triage-report", default=str(DEFAULT_TRIAGE))
    parser.add_argument("--collection-report", default=str(DEFAULT_COLLECTION))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()

    source_catalog_path = Path(args.source_catalog)
    priority_path = Path(args.priority_families)
    triage_path = Path(args.triage_report)
    collection_path = Path(args.collection_report)
    out = Path(args.out)

    payload = generate_manifest(
        source_catalog=_load_json(source_catalog_path),
        priority_manifest=_load_json(priority_path),
        triage_report=_load_json(triage_path),
        collection_report=_load_json(collection_path),
        source_catalog_path=source_catalog_path,
        priority_path=priority_path,
        triage_path=triage_path,
        collection_path=collection_path,
    )
    _write_json(out, payload)
    print(f"Wrote irregular top5 execution manifest: {out}")
    raise SystemExit(0 if bool(payload.get("contract_pass", False)) else 1)


if __name__ == "__main__":
    main()
