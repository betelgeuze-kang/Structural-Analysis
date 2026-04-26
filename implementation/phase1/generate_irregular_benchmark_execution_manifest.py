#!/usr/bin/env python3
"""Promote the irregular top-5 shortlist into a benchmark execution manifest."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

REPO_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_SOURCE_CATALOG = Path(
    "implementation/phase1/open_data/irregular/irregular_structure_source_catalog.json"
)
DEFAULT_COLLECTION_REPORT = Path(
    "implementation/phase1/open_data/irregular/irregular_structure_collection_report.json"
)
DEFAULT_TOP5_MANIFEST = Path(
    "implementation/phase1/open_data/irregular/irregular_top5_execution_manifest.json"
)
DEFAULT_OUT = Path(
    "implementation/phase1/release/external_benchmark_kickoff/irregular_benchmark_execution_manifest.json"
)
DEFAULT_MARKDOWN_OUT = Path(
    "implementation/phase1/release/external_benchmark_kickoff/irregular_benchmark_execution_manifest.md"
)
DEFAULT_RECEIPTS_DIR = Path(
    "implementation/phase1/release/external_benchmark_kickoff/irregular_benchmark_receipts"
)
DEFAULT_RUNS_DIR = Path(
    "implementation/phase1/release/external_benchmark_kickoff/runs"
)
REFERENCE_ONLY_EXECUTION_MODE = "reference_collected_only"
REMOTE_NEEDED_EXECUTION_MODE = "remote_source_hunt_needed"


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _load_optional_json(path: Path) -> dict[str, Any]:
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


def _source_rows_by_id(source_catalog: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = (
        source_catalog.get("source_records")
        if isinstance(source_catalog.get("source_records"), list)
        else []
    )
    return {
        str(row.get("source_id", "") or ""): row
        for row in rows
        if isinstance(row, dict) and str(row.get("source_id", "") or "").strip()
    }


def _collection_rows_by_id(collection_report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = (
        collection_report.get("records")
        if isinstance(collection_report.get("records"), list)
        else []
    )
    return {
        str(row.get("source_id", "") or ""): row
        for row in rows
        if isinstance(row, dict) and str(row.get("source_id", "") or "").strip()
    }


def _copied_source_path(collection_row: dict[str, Any]) -> str:
    artifacts = (
        collection_row.get("artifacts")
        if isinstance(collection_row.get("artifacts"), dict)
        else {}
    )
    return str(artifacts.get("copied_source_path", "") or "").strip()


def _is_executable_path(path: str, *, source_format: str) -> bool:
    normalized = str(path or "").strip()
    if not normalized:
        return False
    suffix = Path(normalized).suffix.lower()
    if suffix in {".pdf", ".md", ".html", ".htm", ".txt"}:
        return False
    if suffix in {
        ".mgt",
        ".mcb",
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
    }:
        return True
    return source_format in {
        "mgt",
        "mcb",
        "tcl",
        "model_text",
        "ifc",
        "step",
        "iges",
        "dxf",
        "csv_tables",
        "npz",
        "json_graph",
    } and suffix == ".json"


def _is_ready_execution_mode(value: object) -> bool:
    return str(value or "").strip().startswith("ready_local")


def _readiness_tier_from_mode(value: object) -> str:
    mode = str(value or "").strip().lower()
    if "canonical" in mode:
        return "canonical"
    if "bridged" in mode:
        return "bridged"
    return "proxy"


def _looks_bridged_path(value: object) -> bool:
    return "/bridged/" in str(value or "").replace("\\", "/").lower()


def _has_bridge_report(value: object) -> bool:
    values = value if isinstance(value, (list, tuple)) else [value]
    return any(Path(str(item or "").strip()).name == "bridge_report.json" for item in values)


def _readiness_tier_from_source(
    *,
    source_kind: object,
    evidence_class: object,
    source_format: object,
    input_path: object,
    companion_paths: object = (),
) -> str:
    source_kind_text = str(source_kind or "").strip().lower()
    evidence_class_text = str(evidence_class or "").strip().lower()
    source_format_text = str(source_format or "").strip().lower()
    input_path_text = str(input_path or "").strip()
    suffix = Path(input_path_text).suffix.lower()
    if (
        source_kind_text == "repo_local_bridged"
        or evidence_class_text == "repo_local_bridged_graph"
        or (_looks_bridged_path(input_path_text) and _has_bridge_report(companion_paths))
    ):
        return "bridged"
    if source_kind_text in {"public_native_source", "repo_local_source"} or evidence_class_text in {
        "public_native_mgt",
        "repo_local_text_model",
    }:
        return "canonical"
    if source_format_text in {"ifc", "step", "iges", "dxf", "mgt", "mcb", "meb", "mmbx", "tcl", "inp"} or suffix in {
        ".ifc",
        ".step",
        ".stp",
        ".iges",
        ".igs",
        ".dxf",
        ".mgt",
        ".mcb",
        ".meb",
        ".mmbx",
        ".tcl",
        ".inp",
    }:
        return "canonical"
    return "proxy"


def _relative_repo_path(path: str | Path) -> str:
    text = str(path).strip()
    if not text:
        return ""
    resolved = Path(text)
    if not resolved.is_absolute():
        resolved = (REPO_ROOT / resolved).resolve()
    else:
        resolved = resolved.resolve()
    try:
        return str(resolved.relative_to(REPO_ROOT))
    except Exception:
        return text


def _resolve_repo_path(path: str | Path) -> Path:
    candidate = Path(str(path))
    if candidate.is_absolute():
        return candidate
    return REPO_ROOT / candidate


def _path_exists(path: str) -> bool:
    return bool(path) and _resolve_repo_path(path).exists()


def _path_sha256(path: str) -> str:
    resolved = _resolve_repo_path(path)
    if not resolved.exists() or not resolved.is_file():
        return ""
    digest = hashlib.sha256()
    with resolved.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact_record(path: str) -> dict[str, Any]:
    return {
        "path": path,
        "exists": _path_exists(path),
        "sha256": _path_sha256(path),
    }


def _receipt_statement(tier: str) -> tuple[str, str]:
    if tier == "canonical":
        return (
            "Local input is the benchmark-native model artifact, so this receipt may be treated as canonical.",
            "Canonical is reserved for native/local benchmark sources without proxy or bridge-only substitutions.",
        )
    if tier == "bridged":
        return (
            "Local input is executable, but it is a bridged transformation of an upstream benchmark or source model.",
            "Bridged means adapter or conversion evidence exists and must not be presented as the untouched canonical source.",
        )
    return (
        "Local input is execution-ready but remains proxy/reference evidence rather than a canonical benchmark model.",
        "Proxy means the current input rehearses the target irregular behavior, but does not replace the original benchmark source.",
    )


def _audit_asof_date() -> str:
    return datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat()


def _benchmark_readiness_tier(
    *,
    execution_mode: object,
    source_kind: object,
    evidence_class: object,
    source_format: object,
    input_path: object,
    companion_paths: object = (),
) -> str:
    mode = str(execution_mode or "").strip().lower()
    if any(token in mode for token in ("canonical", "bridged", "proxy")):
        return _readiness_tier_from_mode(mode)
    return _readiness_tier_from_source(
        source_kind=source_kind,
        evidence_class=evidence_class,
        source_format=source_format,
        input_path=input_path,
        companion_paths=companion_paths,
    )


def _source_origin_class(*, benchmark_readiness_tier: str, has_local_input: bool) -> str:
    if not has_local_input:
        return "remote_irregular_candidate"
    tier = str(benchmark_readiness_tier or "").strip().lower()
    if tier == "canonical":
        return "collected_remote_canonical_irregular"
    if tier == "bridged":
        return "repo_local_bridged_irregular"
    if tier == "proxy":
        return "repo_local_proxy_irregular"
    return "repo_local_irregular"


def _int_value(value: object, default: int = 0) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return default


def _nonempty_paths(*values: object) -> list[str]:
    seen: set[str] = set()
    paths: list[str] = []
    for value in values:
        if isinstance(value, (list, tuple)):
            items = value
        else:
            items = [value]
        for item in items:
            path = str(item or "").strip()
            if path and path not in seen:
                seen.add(path)
                paths.append(path)
    return paths


def _top5_row_readiness_tier(row: dict[str, Any]) -> str:
    if not _is_ready_execution_mode(row.get("execution_mode")):
        return ""
    local_paths = _nonempty_paths(row.get("recommended_local_path"), row.get("local_paths") or [])
    return _benchmark_readiness_tier(
        execution_mode=row.get("execution_mode"),
        source_kind=row.get("recommended_source_kind"),
        evidence_class=row.get("recommended_evidence_class"),
        source_format=row.get("recommended_source_format"),
        input_path=local_paths[0] if local_paths else "",
        companion_paths=row.get("companion_paths") or [],
    )


def _top5_counts(top5_rows: list[dict[str, Any]], *, fallback_summary: dict[str, Any]) -> dict[str, Any]:
    rows = [row for row in top5_rows if isinstance(row, dict)]
    if not rows:
        local_ready_count = _int_value(
            fallback_summary.get("top5_local_ready_count", fallback_summary.get("local_ready_count", 0))
        )
        proxy_ready_count = _int_value(fallback_summary.get("top5_proxy_ready_count", 0))
        bridged_ready_count = _int_value(fallback_summary.get("top5_bridged_ready_count", 0))
        canonical_ready_count = _int_value(fallback_summary.get("top5_canonical_ready_count", 0))
        return {
            "top5_count": _int_value(fallback_summary.get("top5_count", 0)),
            "top5_local_ready_count": local_ready_count,
            "top5_proxy_ready_count": proxy_ready_count,
            "top5_bridged_ready_count": bridged_ready_count,
            "top5_canonical_ready_count": canonical_ready_count,
            "top5_reference_collected_count": _int_value(
                fallback_summary.get("top5_reference_collected_count", 0)
            ),
            "top5_remote_needed_count": _int_value(fallback_summary.get("top5_remote_needed_count", 0)),
            "top5_readiness_counts": {
                "canonical": canonical_ready_count,
                "bridged": bridged_ready_count,
                "proxy": proxy_ready_count,
            },
        }

    counts = {
        "top5_count": len(rows),
        "top5_local_ready_count": 0,
        "top5_proxy_ready_count": 0,
        "top5_bridged_ready_count": 0,
        "top5_canonical_ready_count": 0,
        "top5_reference_collected_count": 0,
        "top5_remote_needed_count": 0,
    }
    for row in rows:
        execution_mode = str(row.get("execution_mode", "") or "").strip()
        if _is_ready_execution_mode(execution_mode):
            counts["top5_local_ready_count"] += 1
            tier = _top5_row_readiness_tier(row) or "proxy"
            counts[f"top5_{tier}_ready_count"] += 1
        elif execution_mode == REFERENCE_ONLY_EXECUTION_MODE:
            counts["top5_reference_collected_count"] += 1
        elif execution_mode == REMOTE_NEEDED_EXECUTION_MODE:
            counts["top5_remote_needed_count"] += 1
    counts["top5_readiness_counts"] = {
        "canonical": counts["top5_canonical_ready_count"],
        "bridged": counts["top5_bridged_ready_count"],
        "proxy": counts["top5_proxy_ready_count"],
    }
    return counts


def _receipt_paths(task_id: str, *, receipt_root: Path = DEFAULT_RECEIPTS_DIR) -> tuple[str, str]:
    case_id = str(task_id or "").split("::", 1)[-1].strip() or "unknown"
    return (
        _relative_repo_path(receipt_root / f"{case_id}.benchmark_receipt.json"),
        _relative_repo_path(receipt_root / f"{case_id}.benchmark_receipt.md"),
    )


def build_irregular_benchmark_execution_manifest(
    *,
    source_catalog: dict[str, Any],
    collection_report: dict[str, Any],
    top5_manifest: dict[str, Any],
    source_catalog_path: str,
    collection_report_path: str,
    top5_manifest_path: str,
) -> dict[str, Any]:
    source_rows_by_id = _source_rows_by_id(source_catalog)
    collection_rows_by_id = _collection_rows_by_id(collection_report)
    top5_rows = (
        top5_manifest.get("top5_families")
        if isinstance(top5_manifest.get("top5_families"), list)
        else []
    )
    collection_summary = (
        collection_report.get("summary")
        if isinstance(collection_report.get("summary"), dict)
        else {}
    )
    top5_summary = top5_manifest.get("summary") if isinstance(top5_manifest.get("summary"), dict) else {}
    top5_counts = _top5_counts(top5_rows, fallback_summary=top5_summary)

    ready_tasks: list[dict[str, Any]] = []
    blocked_tasks: list[dict[str, Any]] = []
    for row in top5_rows:
        if not isinstance(row, dict):
            continue
        family_id = str(row.get("family_id", "") or "").strip()
        recommended_source_id = str(row.get("recommended_source_id", "") or "").strip()
        recommended_source_row = source_rows_by_id.get(recommended_source_id, {})
        recommended_source_metadata = (
            recommended_source_row.get("metadata")
            if isinstance(recommended_source_row.get("metadata"), dict)
            else {}
        )
        source_ids = [
            str(source_id).strip()
            for source_id in (row.get("source_ids") or [])
            if str(source_id).strip()
        ]
        if recommended_source_id and recommended_source_id not in source_ids:
            source_ids.insert(0, recommended_source_id)
        catalog_rows = [
            source_rows_by_id[source_id]
            for source_id in source_ids
            if source_id in source_rows_by_id
        ]
        collection_rows = [
            collection_rows_by_id[source_id]
            for source_id in source_ids
            if source_id in collection_rows_by_id
        ]
        local_paths = [
            str(path).strip()
            for path in (row.get("local_paths") or [])
            if str(path).strip()
        ]
        recommended_local_path = str(row.get("recommended_local_path", "") or "").strip()
        if recommended_local_path and recommended_local_path not in local_paths:
            local_paths.insert(0, recommended_local_path)
        reference_paths = [
            str(path).strip()
            for path in (row.get("reference_paths") or [])
            if str(path).strip()
        ]
        recommended_reference_path = str(row.get("recommended_reference_path", "") or "").strip()
        if recommended_reference_path and recommended_reference_path not in reference_paths:
            reference_paths.insert(0, recommended_reference_path)
        for collection_row in collection_rows:
            copied_path = _copied_source_path(collection_row)
            if copied_path and copied_path not in reference_paths:
                reference_paths.append(copied_path)
        source_urls = sorted(
            {
                str(url).strip()
                for catalog_row in catalog_rows
                for url in (catalog_row.get("source_urls") or [])
                if str(url).strip()
            }
        )
        source_urls.extend(
            [
                str(url).strip()
                for url in (row.get("recommended_source_urls") or [])
                if str(url).strip()
            ]
        )
        source_urls = sorted(dict.fromkeys(source_urls))
        companion_paths = sorted(
            {
                str(path).strip()
                for catalog_row in catalog_rows
                for path in (catalog_row.get("companion_paths") or [])
                if str(path).strip()
            }
        )
        collection_source_report_paths = sorted(
            {
                _relative_repo_path(
                    str(
                        (
                            collection_row.get("artifacts")
                            if isinstance(collection_row.get("artifacts"), dict)
                            else {}
                        ).get("source_report_path", "")
                        or ""
                    ).strip()
                )
                for collection_row in collection_rows
                if str(
                    (
                        collection_row.get("artifacts")
                        if isinstance(collection_row.get("artifacts"), dict)
                        else {}
                    ).get("source_report_path", "")
                    or ""
                ).strip()
            }
        )
        collection_source_metadata_paths = sorted(
            {
                _relative_repo_path(
                    str(
                        (
                            collection_row.get("artifacts")
                            if isinstance(collection_row.get("artifacts"), dict)
                            else {}
                        ).get("source_metadata_path", "")
                        or ""
                    ).strip()
                )
                for collection_row in collection_rows
                if str(
                    (
                        collection_row.get("artifacts")
                        if isinstance(collection_row.get("artifacts"), dict)
                        else {}
                    ).get("source_metadata_path", "")
                    or ""
                ).strip()
            }
        )
        supporting_paths = [
            source_catalog_path,
            collection_report_path,
            top5_manifest_path,
        ]
        ready_mode = _is_ready_execution_mode(row.get("execution_mode"))
        recommended_source_kind = str(row.get("recommended_source_kind", "") or "").strip().lower()
        recommended_evidence_class = str(row.get("recommended_evidence_class", "") or "").strip().lower()
        source_format = str(row.get("recommended_source_format", "") or "").strip()
        input_path = local_paths[0] if local_paths else ""
        benchmark_readiness_tier = _benchmark_readiness_tier(
            execution_mode=row.get("execution_mode"),
            source_kind=recommended_source_kind,
            evidence_class=recommended_evidence_class,
            source_format=source_format,
            input_path=input_path,
            companion_paths=companion_paths,
        )
        task_id = f"irregular::{family_id}"
        benchmark_receipt_json, benchmark_receipt_md = _receipt_paths(task_id)
        execution_row = {
            "task_id": task_id,
            "case_id": family_id,
            "top5_execution_mode": str(row.get("execution_mode", "") or "").strip(),
            "case_label": str(row.get("why_it_matters", "") or family_id),
            "phase": "irregular_case",
            "benchmark_family": family_id,
            "hazard_family": "irregularity_proxy",
            "topology_family": family_id,
            "load_path_family": ",".join(
                str(tag).strip()
                for tag in (row.get("irregularity_tags") or [])
                if str(tag).strip()
            ),
            "submission_scope": "irregular_structure_benchmark_program",
            "source_origin_class": _source_origin_class(
                benchmark_readiness_tier=benchmark_readiness_tier,
                has_local_input=bool(local_paths),
            ),
            "input_path": input_path,
            "primary_report_path": input_path,
            "benchmark_readiness_tier": benchmark_readiness_tier,
            "reference_paths": reference_paths,
            "supporting_report_paths": supporting_paths,
            "source_ids": source_ids,
            "source_urls": source_urls,
            "recommended_source_kind": recommended_source_kind,
            "recommended_evidence_class": recommended_evidence_class,
            "recommended_source_format": source_format,
            "companion_paths": companion_paths,
            "collection_source_report_paths": collection_source_report_paths,
            "collection_source_metadata_paths": collection_source_metadata_paths,
            "source_collection_statuses": sorted(
                {
                    str(
                        collection_row.get(
                            "status",
                            collection_row.get("collection_status", ""),
                        )
                        or ""
                    ).strip()
                    for collection_row in collection_rows
                    if str(
                        collection_row.get(
                            "status",
                            collection_row.get("collection_status", ""),
                        )
                        or ""
                    ).strip()
                }
            ),
            "authority_fit": str(row.get("authority_fit", "") or ""),
            "ai_learning_fit": str(row.get("ai_learning_fit", "") or ""),
            "kpi_specs": [
                str(row.get("recommended_kpi_or_validation_angle", "") or "").strip()
            ]
            if str(row.get("recommended_kpi_or_validation_angle", "") or "").strip()
            else [],
            "native_support_summary": str(row.get("native_support_summary", "") or "").strip(),
            "official_support_summary": str(row.get("official_support_summary", "") or "").strip(),
            "bridged_current_source_id": recommended_source_id,
            "bridged_promotion_blocker": str(
                recommended_source_metadata.get("canonical_promotion_blocker", "") or ""
            ).strip(),
            "benchmark_receipt_json": benchmark_receipt_json,
            "benchmark_receipt_md": benchmark_receipt_md,
        }
        executable_paths = [
            path for path in local_paths if _is_executable_path(path, source_format=source_format)
        ]
        if ready_mode and "proxy" in recommended_source_kind and local_paths and not executable_paths:
            executable_paths = local_paths[:]
        if ready_mode and executable_paths:
            execution_row["input_path"] = executable_paths[0]
            execution_row["primary_report_path"] = executable_paths[0]
            execution_row["execution_status"] = "ready"
            ready_tasks.append(execution_row)
        else:
            execution_row["execution_status"] = "blocked"
            if reference_paths:
                execution_row["blocker_reason"] = "materialize_executable_model"
                execution_row["required_action"] = "materialize_executable_model"
            else:
                execution_row["blocker_reason"] = "collect_remote_source"
                execution_row["required_action"] = "collect_remote_source"
            blocked_tasks.append(execution_row)

    ready_task_count = len(ready_tasks)
    blocked_task_count = len(blocked_tasks)
    contract_pass = ready_task_count >= 1 and (ready_task_count + blocked_task_count) >= 1
    summary = {
        "recommended_start_mode": (
            "start_now_local_irregular_benchmark" if ready_task_count >= 1 else "collect_remote_first"
        ),
        "submission_scope": "irregular_structure_benchmark_program",
        "execution_mode": "limited" if ready_task_count >= 1 else "blocked",
        "case_task_count": ready_task_count + blocked_task_count,
        "ready_task_count": ready_task_count,
        "blocked_task_count": blocked_task_count,
        "task_count": ready_task_count + blocked_task_count,
        "top5_count": top5_counts["top5_count"],
        "top5_local_ready_count": top5_counts["top5_local_ready_count"],
        "top5_proxy_ready_count": top5_counts["top5_proxy_ready_count"],
        "top5_bridged_ready_count": top5_counts["top5_bridged_ready_count"],
        "top5_canonical_ready_count": top5_counts["top5_canonical_ready_count"],
        "top5_reference_collected_count": top5_counts["top5_reference_collected_count"],
        "top5_remote_needed_count": top5_counts["top5_remote_needed_count"],
        "top5_readiness_counts": dict(top5_counts["top5_readiness_counts"]),
        "collection_collected_count": int(collection_summary.get("collected_count", 0) or 0),
        "collection_metadata_only_remote_candidate_count": int(
            collection_summary.get("metadata_only_remote_candidate_count", 0) or 0
        ),
        "ready_canonical_task_count": sum(
            1
            for row in ready_tasks
            if str(row.get("benchmark_readiness_tier", "") or "") == "canonical"
        ),
        "ready_bridged_task_count": sum(
            1
            for row in ready_tasks
            if str(row.get("benchmark_readiness_tier", "") or "") == "bridged"
        ),
        "ready_proxy_task_count": sum(
            1
            for row in ready_tasks
            if str(row.get("benchmark_readiness_tier", "") or "") == "proxy"
        ),
    }
    summary_line = (
        "Irregular benchmark execution: "
        f"{'PASS' if contract_pass else 'CHECK'} | ready={ready_task_count} | "
        f"blocked={blocked_task_count} | task_count={ready_task_count + blocked_task_count} | "
        f"canonical={summary['ready_canonical_task_count']} | bridged={summary['ready_bridged_task_count']} | proxy={summary['ready_proxy_task_count']} | "
        f"top5={summary['top5_count']} | top5_local_ready={summary['top5_local_ready_count']} | top5_proxy_ready={summary['top5_proxy_ready_count']} | "
        f"top5_bridged_ready={summary['top5_bridged_ready_count']} | top5_canonical_ready={summary['top5_canonical_ready_count']} | "
        f"top5_reference_collected={summary['top5_reference_collected_count']} | top5_remote_needed={summary['top5_remote_needed_count']}"
    )
    payload = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contract_pass": contract_pass,
        "reason_code": "PASS_EXECUTION_MANIFEST_READY" if contract_pass else "ERR_EXECUTION_START_BLOCKED",
        "summary": summary,
        "summary_line": summary_line,
        "task_count": ready_task_count + blocked_task_count,
        "ready_tasks": ready_tasks,
        "blocked_tasks": blocked_tasks,
        "tasks": ready_tasks + blocked_tasks,
        "artifacts": {
            "source_catalog_json": source_catalog_path,
            "collection_report_json": collection_report_path,
            "top5_execution_manifest_json": top5_manifest_path,
        },
    }
    return payload


def attach_irregular_benchmark_receipts(
    payload: dict[str, Any],
    *,
    receipt_root: Path = DEFAULT_RECEIPTS_DIR,
) -> dict[str, Any]:
    ready_tasks = payload.get("ready_tasks") if isinstance(payload.get("ready_tasks"), list) else []
    receipt_root.mkdir(parents=True, exist_ok=True)
    receipt_index_rows: list[dict[str, Any]] = []
    for row in ready_tasks:
        if not isinstance(row, dict):
            continue
        tier = str(row.get("benchmark_readiness_tier", "") or "proxy")
        statement, guardrail = _receipt_statement(tier)
        json_rel, md_rel = _receipt_paths(str(row.get("task_id", "") or ""), receipt_root=receipt_root)
        json_path = _resolve_repo_path(json_rel)
        md_path = _resolve_repo_path(md_rel)
        input_path = str(row.get("input_path", "") or "")
        reference_paths = [
            str(path).strip()
            for path in (row.get("reference_paths") or [])
            if str(path).strip()
        ]
        companion_paths = [
            str(path).strip()
            for path in (row.get("companion_paths") or [])
            if str(path).strip()
        ]
        collection_report_paths = [
            str(path).strip()
            for path in (row.get("collection_source_report_paths") or [])
            if str(path).strip()
        ]
        collection_metadata_paths = [
            str(path).strip()
            for path in (row.get("collection_source_metadata_paths") or [])
            if str(path).strip()
        ]
        receipt = {
            "schema_version": "1.0",
            "report_type": "irregular_benchmark_receipt",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "task_id": str(row.get("task_id", "") or ""),
            "case_id": str(row.get("case_id", "") or ""),
            "case_label": str(row.get("case_label", "") or ""),
            "benchmark_family": str(row.get("benchmark_family", "") or ""),
            "benchmark_readiness_tier": tier,
            "execution_status": str(row.get("execution_status", "") or ""),
            "readiness_statement": statement,
            "non_overstatement_guardrail": guardrail,
            "source_origin_class": str(row.get("source_origin_class", "") or ""),
            "recommended_source_kind": str(row.get("recommended_source_kind", "") or ""),
            "recommended_evidence_class": str(row.get("recommended_evidence_class", "") or ""),
            "recommended_source_format": str(row.get("recommended_source_format", "") or ""),
            "input_artifact": _artifact_record(input_path),
            "reference_artifacts": [_artifact_record(path) for path in reference_paths],
            "companion_artifacts": [_artifact_record(path) for path in companion_paths],
            "collection_source_reports": [_artifact_record(path) for path in collection_report_paths],
            "collection_source_metadata": [_artifact_record(path) for path in collection_metadata_paths],
            "supporting_report_paths": [
                _artifact_record(str(path).strip())
                for path in (row.get("supporting_report_paths") or [])
                if str(path).strip()
            ],
            "source_ids": list(row.get("source_ids") or []),
            "source_urls": list(row.get("source_urls") or []),
            "source_collection_statuses": list(row.get("source_collection_statuses") or []),
            "kpi_specs": list(row.get("kpi_specs") or []),
        }
        if tier == "bridged":
            audit_note = ""
            if "peer_transfer_podium_tower_remote" in list(row.get("source_ids") or []):
                audit_note = (
                    f"official benchmark documentation checked, native package not found as of {_audit_asof_date()}"
                )
            receipt["why_still_bridged"] = {
                "current_source_id": str(row.get("bridged_current_source_id", "") or ""),
                "native_support_summary": str(row.get("native_support_summary", "") or ""),
                "official_support_summary": str(row.get("official_support_summary", "") or ""),
                "canonical_upgrade_path": "collect official benchmark-native package",
                "blocker": str(row.get("bridged_promotion_blocker", "") or ""),
                "audit_note": audit_note,
            }
        _write_json(json_path, receipt)
        md_lines = [
            f"# Irregular Benchmark Receipt: {receipt['case_id']}",
            "",
            f"- `benchmark_readiness_tier`: `{tier}`",
            f"- `execution_status`: `{receipt['execution_status']}`",
            f"- `input_artifact`: `{receipt['input_artifact']['path']}`",
            f"- `source_origin_class`: `{receipt['source_origin_class']}`",
            f"- `recommended_source_kind`: `{receipt['recommended_source_kind']}`",
            f"- `recommended_evidence_class`: `{receipt['recommended_evidence_class']}`",
            f"- `readiness_statement`: `{statement}`",
            f"- `non_overstatement_guardrail`: `{guardrail}`",
            "",
            "## KPI",
            "",
        ]
        if tier == "bridged":
            why = receipt.get("why_still_bridged") if isinstance(receipt.get("why_still_bridged"), dict) else {}
            md_lines.extend(
                [
                    "## Why Still Bridged",
                    "",
                    f"- `current_source_id`: `{why.get('current_source_id', '') or 'n/a'}`",
                    f"- `native_support_summary`: `{why.get('native_support_summary', '') or 'n/a'}`",
                    f"- `official_support_summary`: `{why.get('official_support_summary', '') or 'n/a'}`",
                    f"- `canonical_upgrade_path`: `{why.get('canonical_upgrade_path', '') or 'n/a'}`",
                    f"- `blocker`: `{why.get('blocker', '') or 'n/a'}`",
                    f"- `audit_note`: `{why.get('audit_note', '') or 'n/a'}`",
                ]
            )
            md_lines.append("")
        for spec in receipt["kpi_specs"]:
            md_lines.append(f"- `{spec}`")
        md_lines.extend(["", "## Supporting Artifacts", ""])
        for artifact in (
            receipt["reference_artifacts"]
            + receipt["companion_artifacts"]
            + receipt["collection_source_reports"]
            + receipt["collection_source_metadata"]
        ):
            md_lines.append(
                f"- `{artifact['path']}` | exists=`{artifact['exists']}` | sha256=`{artifact['sha256'] or 'n/a'}`"
            )
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
        row["benchmark_receipt_json"] = json_rel
        row["benchmark_receipt_md"] = md_rel
        receipt_index_rows.append(
            {
                "task_id": receipt["task_id"],
                "case_id": receipt["case_id"],
                "benchmark_readiness_tier": tier,
                "benchmark_receipt_json": json_rel,
                "benchmark_receipt_md": md_rel,
            }
        )
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    summary["receipt_count"] = len(receipt_index_rows)
    summary["receipt_canonical_count"] = sum(
        1 for row in receipt_index_rows if row.get("benchmark_readiness_tier") == "canonical"
    )
    summary["receipt_bridged_count"] = sum(
        1 for row in receipt_index_rows if row.get("benchmark_readiness_tier") == "bridged"
    )
    summary["receipt_proxy_count"] = sum(
        1 for row in receipt_index_rows if row.get("benchmark_readiness_tier") == "proxy"
    )
    payload["summary_line"] = (
        "Irregular benchmark execution: "
        f"{'PASS' if bool(payload.get('contract_pass', False)) else 'CHECK'} | "
        f"ready={int(summary.get('ready_task_count', 0) or 0)} | "
        f"blocked={int(summary.get('blocked_task_count', 0) or 0)} | "
        f"task_count={int(summary.get('task_count', 0) or 0)} | "
        f"canonical={int(summary.get('ready_canonical_task_count', 0) or 0)} | "
        f"bridged={int(summary.get('ready_bridged_task_count', 0) or 0)} | "
        f"proxy={int(summary.get('ready_proxy_task_count', 0) or 0)} | "
        f"receipts={int(summary.get('receipt_count', 0) or 0)}"
    )
    artifacts = payload.get("artifacts") if isinstance(payload.get("artifacts"), dict) else {}
    artifacts["receipt_root_dir"] = _relative_repo_path(receipt_root)
    artifacts["receipt_index_json"] = _relative_repo_path(receipt_root / "receipt_index.json")
    payload["artifacts"] = artifacts
    _write_json(_resolve_repo_path(artifacts["receipt_index_json"]), {"receipts": receipt_index_rows})
    return payload


def _build_markdown(payload: dict[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    lines = [
        "# Irregular Benchmark Execution Manifest",
        "",
        f"- `generated_at`: `{payload.get('generated_at', '')}`",
        f"- `execution_mode`: `{summary.get('execution_mode', '')}`",
        f"- `submission_scope`: `{summary.get('submission_scope', '')}`",
        f"- `ready_task_count`: `{summary.get('ready_task_count', 0)}`",
        f"- `blocked_task_count`: `{summary.get('blocked_task_count', 0)}`",
        f"- `summary_line`: `{payload.get('summary_line', '') or 'n/a'}`",
        "",
        "## Ready Tasks",
        "",
    ]
    for row in payload.get("ready_tasks", []):
        lines.append(
            f"- `{row.get('task_id', '')}` | tier=`{row.get('benchmark_readiness_tier', '') or 'n/a'}` | "
            f"input=`{row.get('input_path', '') or 'n/a'}` | "
            f"receipt=`{row.get('benchmark_receipt_json', '') or 'n/a'}` | "
            f"kpi=`{', '.join(row.get('kpi_specs', [])) or 'n/a'}`"
        )
    lines.extend(["", "## Blocked Tasks", ""])
    for row in payload.get("blocked_tasks", []):
        lines.append(
            f"- `{row.get('task_id', '')}` | blocker=`{row.get('blocker_reason', '')}` | "
            f"action=`{row.get('required_action', '')}` | sources=`{', '.join(row.get('source_urls', [])) or 'n/a'}`"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-catalog", default=str(DEFAULT_SOURCE_CATALOG))
    parser.add_argument("--collection-report", default=str(DEFAULT_COLLECTION_REPORT))
    parser.add_argument("--top5-manifest", default=str(DEFAULT_TOP5_MANIFEST))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--markdown-out", default=str(DEFAULT_MARKDOWN_OUT))
    parser.add_argument("--receipt-root", default=str(DEFAULT_RECEIPTS_DIR))
    args = parser.parse_args(argv)

    source_catalog_path = Path(args.source_catalog)
    collection_report_path = Path(args.collection_report)
    top5_manifest_path = Path(args.top5_manifest)
    out_path = Path(args.out)
    markdown_out_path = Path(args.markdown_out)
    receipt_root_path = Path(args.receipt_root)

    payload = build_irregular_benchmark_execution_manifest(
        source_catalog=_load_json(source_catalog_path),
        collection_report=_load_json(collection_report_path),
        top5_manifest=_load_json(top5_manifest_path),
        source_catalog_path=str(source_catalog_path),
        collection_report_path=str(collection_report_path),
        top5_manifest_path=str(top5_manifest_path),
    )
    payload = attach_irregular_benchmark_receipts(payload, receipt_root=receipt_root_path)
    _write_json(out_path, payload)
    markdown_out_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_out_path.write_text(_build_markdown(payload), encoding="utf-8")
    print(f"Wrote irregular benchmark execution manifest: {out_path}")
    return 0 if bool(payload.get("contract_pass", False)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
