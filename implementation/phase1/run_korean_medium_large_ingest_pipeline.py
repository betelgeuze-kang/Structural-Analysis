#!/usr/bin/env python3
"""Regenerate catalog, collect artifacts, and check attached medium/large MGT headers."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from implementation.phase1.open_data.korea.korean_building_scale import (  # noqa: E402
    building_scale_band,
    is_medium_or_large,
)

KOREA_DIR = REPO_ROOT / "implementation" / "phase1" / "open_data" / "korea"
DEFAULT_CATALOG = KOREA_DIR / "korean_source_catalog.json"
DEFAULT_COLLECTION_REPORT = KOREA_DIR / "korean_public_structure_collection_report.json"
DEFAULT_RECEIPT = KOREA_DIR / "korean_medium_large_ingest_receipt.json"
ARTIFACT_ROOT = KOREA_DIR / "collected" / "artifacts"
CURATED_ROOT = KOREA_DIR / "curated"
MGT_HEADER_MARKERS = ("*VERSION", "*UNIT")
MIN_MGT_BYTES = 500
BENCHMARK_MGT = REPO_ROOT / "implementation/phase1/open_data/midas/midas_generator_33.optimized.mgt"
PRIVATE_REAL_DRAWING_MANIFEST = (
    REPO_ROOT / "private_corpus/real_drawings/private_real_drawing_corpus_manifest.json"
)
LOCAL_CANDIDATE_EXTENSIONS = {".mgt", ".ifc", ".pdf", ".zip"}


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _attach_provenance(mgt_path: Path, benchmark_sha: str) -> str:
    if not benchmark_sha or not mgt_path.is_file():
        return "unknown"
    if _sha256_file(mgt_path) == benchmark_sha:
        return "repo_benchmark_bridge"
    return "operator_attached"


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected object json: {path}")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _resolve_repo_path(path_text: str) -> Path | None:
    text = str(path_text or "").strip()
    if not text:
        return None
    path = Path(text)
    return path if path.is_absolute() else REPO_ROOT / path


def _regenerate_catalog(*, skip_regenerate: bool) -> None:
    if skip_regenerate:
        return
    script = KOREA_DIR / "generate_korean_source_catalog.py"
    subprocess.run([sys.executable, str(script)], cwd=REPO_ROOT, check=True)


def _run_collector(*, catalog_path: Path, skip_collect: bool) -> dict[str, Any]:
    if skip_collect:
        if DEFAULT_COLLECTION_REPORT.is_file():
            return _load_json(DEFAULT_COLLECTION_REPORT)
        return {}
    script = KOREA_DIR / "collect_korean_public_structures.py"
    subprocess.run(
        [sys.executable, str(script), "--catalog", str(catalog_path)],
        cwd=REPO_ROOT,
        check=True,
    )
    return _load_json(DEFAULT_COLLECTION_REPORT)


def _find_mgt_artifact(source_id: str) -> Path | None:
    artifact_dir = ARTIFACT_ROOT / source_id
    if not artifact_dir.is_dir():
        return None
    for path in sorted(artifact_dir.iterdir()):
        if path.is_file() and path.suffix.lower() == ".mgt":
            return path
    return None


def _check_mgt_header(path: Path) -> tuple[bool, list[str]]:
    blockers: list[str] = []
    if not path.is_file():
        blockers.append("mgt_file_missing")
        return False, blockers
    size = path.stat().st_size
    if size <= MIN_MGT_BYTES:
        blockers.append(f"mgt_file_too_small:{size}")
    try:
        head = path.read_text(encoding="utf-8", errors="replace")[:4096]
    except OSError as exc:
        blockers.append(f"mgt_read_error:{exc}")
        return False, blockers
    if not any(marker in head for marker in MGT_HEADER_MARKERS):
        blockers.append("mgt_header_missing_version_or_unit")
    return len(blockers) == 0, blockers


def _operator_action_row(
    *,
    record: dict[str, Any],
    entry: dict[str, Any],
) -> dict[str, Any] | None:
    source_id = str(entry.get("source_id") or "")
    source_format = str(entry.get("format") or record.get("format") or "").lower()
    target_dir = ARTIFACT_ROOT / source_id
    blockers = [str(item) for item in entry.get("blockers", [])]
    provenance = str(entry.get("attach_provenance") or "")
    attached = bool(entry.get("attached"))
    action_type = ""
    expected_artifacts: list[str] = []
    acceptance_checks: list[str] = []
    if source_format == "mgt":
        expected_artifacts = [f"{source_id}.mgt"]
        acceptance_checks = [
            "file_size_gt_500_bytes",
            "mgt_header_contains_VERSION_or_UNIT",
            "sha256_differs_from_repo_benchmark_bridge",
            "roundtrip_parse_contract_pass_when_enabled",
        ]
        if provenance == "repo_benchmark_bridge":
            action_type = "replace_repo_benchmark_bridge_mgt_with_operator_real_mgt"
        elif not attached or "awaiting_manual_mgt_attach" in blockers:
            action_type = "attach_operator_real_mgt"
        elif any(item.startswith("mgt_file_too_small:") for item in blockers):
            action_type = "replace_placeholder_mgt_with_operator_real_mgt"
        elif not bool(entry.get("mgt_header_ok")):
            action_type = "replace_invalid_mgt_with_header_valid_mgt"
    elif source_format == "ifc":
        expected_artifacts = [f"{source_id}.ifc"]
        acceptance_checks = [
            "ifc_file_exists",
            "ifc_not_metadata_only",
            "curated_local_ifc_reference_exists_when_required",
        ]
        if not attached:
            action_type = "attach_operator_real_ifc"
        elif "curated_local_ifc_missing" in blockers:
            action_type = "attach_missing_curated_local_ifc"
    elif source_format in {"pdf", "zip"}:
        expected_artifacts = [f"{source_id}.{source_format}", f"{source_id}.mgt"]
        acceptance_checks = [
            "source_artifact_exists_or_pdf_derived_mgt_exists",
            "derived_mgt_header_valid_if_mgt_attached",
            "artifact_not_metadata_only",
        ]
        if not attached:
            action_type = f"attach_operator_real_{source_format}_or_pdf_derived_mgt"
    elif not attached:
        expected_artifacts = [f"{source_id}.*"]
        acceptance_checks = ["artifact_exists", "artifact_not_metadata_only"]
        action_type = "attach_operator_real_artifact"
    if not action_type:
        return None
    return {
        "source_id": source_id,
        "format": source_format,
        "storey_band": entry.get("storey_band", ""),
        "scale": entry.get("scale", ""),
        "action_type": action_type,
        "target_directory": str(target_dir),
        "expected_artifacts": expected_artifacts,
        "current_blockers": blockers,
        "current_attach_provenance": provenance,
        "acceptance_checks": acceptance_checks,
    }


def _operator_action_packet(
    *,
    operator_action_queue: list[dict[str, Any]],
    operator_action_type_counts: dict[str, int],
    operator_attached_real_mgt_header_ok_target: int,
    operator_attached_real_mgt_header_ok_remaining: int,
    metadata_only_source_ids: list[str],
    repo_benchmark_bridge_source_ids: list[str],
) -> dict[str, Any]:
    rows = [row for row in operator_action_queue if isinstance(row, dict)]
    by_action_type: dict[str, list[str]] = {}
    target_directories: list[str] = []
    acceptance_checks: set[str] = set()
    for row in rows:
        action_type = str(row.get("action_type") or "unknown")
        source_id = str(row.get("source_id") or "")
        if source_id:
            by_action_type.setdefault(action_type, []).append(source_id)
        target_dir = str(row.get("target_directory") or "")
        if target_dir:
            target_directories.append(target_dir)
        for check in row.get("acceptance_checks", []):
            if check:
                acceptance_checks.add(str(check))
    next_actions = [
        {
            "source_id": str(row.get("source_id") or ""),
            "action_type": str(row.get("action_type") or ""),
            "target_directory": str(row.get("target_directory") or ""),
            "expected_artifacts": list(row.get("expected_artifacts") or []),
            "acceptance_checks": list(row.get("acceptance_checks") or []),
        }
        for row in rows[:10]
    ]
    return {
        "schema_version": "korean-medium-large-operator-action-packet.v1",
        "status": "pending" if rows else "ready",
        "action_count": int(len(rows)),
        "action_type_counts": dict(sorted(operator_action_type_counts.items())),
        "source_ids_by_action_type": {
            key: sorted(values) for key, values in sorted(by_action_type.items())
        },
        "target_directory_count": int(len(set(target_directories))),
        "acceptance_check_inventory": sorted(acceptance_checks),
        "metadata_only_source_ids": list(metadata_only_source_ids),
        "repo_benchmark_bridge_source_ids": list(repo_benchmark_bridge_source_ids),
        "operator_attached_real_mgt_header_ok_target": int(
            operator_attached_real_mgt_header_ok_target
        ),
        "operator_attached_real_mgt_header_ok_remaining": int(
            operator_attached_real_mgt_header_ok_remaining
        ),
        "next_actions": next_actions,
        "claim_boundary": (
            "This packet is an operator action checklist. It does not count local "
            "or repo candidate files as G7 evidence until each source is matched, "
            "rights are cleared where required, and the acceptance checks pass."
        ),
    }


def _local_private_candidate_artifacts(
    *,
    manifest_path: Path | None = None,
) -> dict[str, Any]:
    manifest_path = manifest_path or PRIVATE_REAL_DRAWING_MANIFEST
    if not manifest_path.is_file():
        return {
            "summary": {
                "local_private_candidate_count": 0,
                "existing_local_private_candidate_count": 0,
                "kr_local_private_candidate_count": 0,
                "mgt_local_private_candidate_count": 0,
                "mgt_header_ok_local_private_candidate_count": 0,
                "g7_counted_local_private_candidate_count": 0,
                "raw_redistribution_blocked_candidate_count": 0,
                "non_kr_candidate_count": 0,
                "catalog_source_unmatched_candidate_count": 0,
            },
            "rows": [],
        }
    payload = _load_json(manifest_path)
    projects = payload.get("projects")
    rows: list[dict[str, Any]] = []
    if not isinstance(projects, list):
        projects = []
    for project in projects:
        if not isinstance(project, dict):
            continue
        project_id = str(project.get("project_id") or "")
        jurisdiction = str(project.get("jurisdiction") or "")
        source_family = str(project.get("source_family") or "")
        files = project.get("files")
        if not isinstance(files, list):
            continue
        for file_row in files:
            if not isinstance(file_row, dict):
                continue
            file_name = str(file_row.get("file_name") or "")
            extension = str(file_row.get("file_type") or Path(file_name).suffix).lower()
            if extension not in LOCAL_CANDIDATE_EXTENSIONS:
                continue
            private_path = str(file_row.get("private_path") or "")
            resolved = _resolve_repo_path(private_path)
            exists = bool(resolved is not None and resolved.is_file())
            raw_allowed = bool(file_row.get("raw_redistribution_allowed"))
            blockers: list[str] = ["not_catalog_source_matched"]
            if not exists:
                blockers.append("candidate_file_missing")
            if jurisdiction != "KR":
                blockers.append("not_korean_jurisdiction")
            if not raw_allowed:
                blockers.append("raw_redistribution_not_allowed")
            mgt_header_ok = False
            mgt_header_blockers: list[str] = []
            if extension == ".mgt" and resolved is not None and resolved.is_file():
                mgt_header_ok, mgt_header_blockers = _check_mgt_header(resolved)
                blockers.extend(mgt_header_blockers)
            rows.append(
                {
                    "project_id": project_id,
                    "jurisdiction": jurisdiction,
                    "source_family": source_family,
                    "file_name": file_name,
                    "file_type": extension,
                    "bytes": int(file_row.get("bytes") or 0),
                    "role": file_row.get("role"),
                    "private_path": private_path,
                    "exists": exists,
                    "raw_redistribution_allowed": raw_allowed,
                    "model_optimization_candidate": bool(
                        file_row.get("model_optimization_candidate")
                    ),
                    "drawing_review_candidate": bool(file_row.get("drawing_review_candidate")),
                    "mgt_header_ok": bool(mgt_header_ok),
                    "mgt_header_blockers": mgt_header_blockers,
                    "counted_in_g7": False,
                    "g7_non_count_reason": "private_or_unmatched_candidate_only",
                    "promotion_blockers": blockers,
                }
            )
    summary = {
        "local_private_candidate_count": len(rows),
        "existing_local_private_candidate_count": sum(1 for row in rows if row["exists"]),
        "kr_local_private_candidate_count": sum(
            1 for row in rows if row["jurisdiction"] == "KR"
        ),
        "mgt_local_private_candidate_count": sum(
            1 for row in rows if row["file_type"] == ".mgt"
        ),
        "mgt_header_ok_local_private_candidate_count": sum(
            1 for row in rows if row["file_type"] == ".mgt" and row["mgt_header_ok"]
        ),
        "g7_counted_local_private_candidate_count": sum(
            1 for row in rows if row["counted_in_g7"]
        ),
        "raw_redistribution_blocked_candidate_count": sum(
            1 for row in rows if "raw_redistribution_not_allowed" in row["promotion_blockers"]
        ),
        "non_kr_candidate_count": sum(
            1 for row in rows if "not_korean_jurisdiction" in row["promotion_blockers"]
        ),
        "catalog_source_unmatched_candidate_count": sum(
            1 for row in rows if "not_catalog_source_matched" in row["promotion_blockers"]
        ),
    }
    return {"summary": summary, "rows": rows}


def _candidate_extensions_for_action(action_row: dict[str, Any]) -> set[str]:
    action_type = str(action_row.get("action_type") or "")
    source_format = str(action_row.get("format") or "").lower()
    if "pdf_or_pdf_derived_mgt" in action_type:
        return {".pdf", ".mgt"}
    if "ifc" in action_type or source_format == "ifc":
        return {".ifc"}
    if "mgt" in action_type or source_format == "mgt":
        return {".mgt"}
    if source_format == "pdf":
        return {".pdf", ".mgt"}
    return set()


def _operator_action_private_candidate_matches(
    *,
    operator_action_queue: list[dict[str, Any]],
    local_private_candidate_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for action in operator_action_queue:
        accepted_extensions = _candidate_extensions_for_action(action)
        if not accepted_extensions:
            continue
        for candidate in local_private_candidate_rows:
            if not bool(candidate.get("exists")):
                continue
            if str(candidate.get("jurisdiction") or "") != "KR":
                continue
            if str(candidate.get("file_type") or "").lower() not in accepted_extensions:
                continue
            rows.append(
                {
                    "source_id": action.get("source_id"),
                    "action_type": action.get("action_type"),
                    "accepted_candidate_extensions": sorted(accepted_extensions),
                    "candidate_project_id": candidate.get("project_id"),
                    "candidate_file_name": candidate.get("file_name"),
                    "candidate_file_type": candidate.get("file_type"),
                    "candidate_private_path": candidate.get("private_path"),
                    "candidate_role": candidate.get("role"),
                    "candidate_bytes": candidate.get("bytes"),
                    "requires_operator_source_mapping": True,
                    "requires_rights_confirmation": True,
                    "counted_in_g7": False,
                    "non_count_reason": (
                        "candidate is local/private and not yet mapped to the catalog source "
                        "with redistribution/provenance clearance"
                    ),
                    "acceptance_checks": action.get("acceptance_checks", []),
                    "promotion_blockers": candidate.get("promotion_blockers", []),
                }
            )
    source_ids = sorted({str(row.get("source_id") or "") for row in rows})
    candidate_paths = sorted({str(row.get("candidate_private_path") or "") for row in rows})
    summary = {
        "operator_action_private_candidate_match_count": int(len(rows)),
        "operator_action_private_candidate_source_count": int(len(source_ids)),
        "operator_action_private_candidate_file_count": int(len(candidate_paths)),
        "operator_action_private_candidate_requires_rights_count": sum(
            1 for row in rows if bool(row.get("requires_rights_confirmation"))
        ),
    }
    return {"summary": summary, "rows": rows}


def _repo_public_candidate_artifacts(*, benchmark_sha: str) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    roots = [
        ("curated", CURATED_ROOT),
        ("artifact_root", ARTIFACT_ROOT),
    ]
    seen_paths: set[Path] = set()
    for source_location, root in roots:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in LOCAL_CANDIDATE_EXTENSIONS:
                continue
            resolved = path.resolve()
            if resolved in seen_paths:
                continue
            seen_paths.add(resolved)
            suffix = path.suffix.lower()
            candidate_source_id = path.parent.name if source_location == "artifact_root" else path.stem
            blockers: list[str] = []
            mgt_header_ok = False
            mgt_provenance = ""
            if suffix == ".mgt":
                mgt_header_ok, blockers = _check_mgt_header(path)
                mgt_provenance = _attach_provenance(path, benchmark_sha)
                if mgt_provenance == "repo_benchmark_bridge":
                    blockers.append("repo_benchmark_bridge_mgt")
            rows.append(
                {
                    "candidate_source_id": candidate_source_id,
                    "candidate_file_name": path.name,
                    "candidate_file_type": suffix,
                    "candidate_repo_path": str(path),
                    "candidate_source_location": source_location,
                    "candidate_bytes": int(path.stat().st_size),
                    "mgt_header_ok": bool(mgt_header_ok),
                    "mgt_provenance": mgt_provenance,
                    "counted_in_g7": False,
                    "g7_non_count_reason": (
                        "repo-local candidate requires exact catalog source mapping "
                        "and must not be a benchmark bridge"
                    ),
                    "promotion_blockers": blockers,
                }
            )
    summary = {
        "repo_public_candidate_count": len(rows),
        "repo_public_candidate_mgt_count": sum(
            1 for row in rows if row["candidate_file_type"] == ".mgt"
        ),
        "repo_public_candidate_ifc_count": sum(
            1 for row in rows if row["candidate_file_type"] == ".ifc"
        ),
        "repo_public_candidate_benchmark_bridge_count": sum(
            1
            for row in rows
            if "repo_benchmark_bridge_mgt" in row["promotion_blockers"]
        ),
        "g7_counted_repo_public_candidate_count": sum(
            1 for row in rows if row["counted_in_g7"]
        ),
    }
    return {"summary": summary, "rows": rows}


def _operator_action_repo_candidate_matches(
    *,
    operator_action_queue: list[dict[str, Any]],
    repo_candidate_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for action in operator_action_queue:
        accepted_extensions = _candidate_extensions_for_action(action)
        if not accepted_extensions:
            continue
        action_source_id = str(action.get("source_id") or "")
        for candidate in repo_candidate_rows:
            if str(candidate.get("candidate_file_type") or "") not in accepted_extensions:
                continue
            candidate_source_id = str(candidate.get("candidate_source_id") or "")
            requires_source_mapping = candidate_source_id != action_source_id
            promotion_blockers = list(candidate.get("promotion_blockers") or [])
            if requires_source_mapping:
                promotion_blockers.append("catalog_source_unmatched_candidate")
            rows.append(
                {
                    "source_id": action_source_id,
                    "action_type": action.get("action_type"),
                    "accepted_candidate_extensions": sorted(accepted_extensions),
                    "candidate_source_id": candidate_source_id,
                    "candidate_file_name": candidate.get("candidate_file_name"),
                    "candidate_file_type": candidate.get("candidate_file_type"),
                    "candidate_repo_path": candidate.get("candidate_repo_path"),
                    "candidate_source_location": candidate.get("candidate_source_location"),
                    "candidate_bytes": candidate.get("candidate_bytes"),
                    "candidate_mgt_header_ok": candidate.get("mgt_header_ok"),
                    "candidate_mgt_provenance": candidate.get("mgt_provenance"),
                    "requires_operator_source_mapping": requires_source_mapping,
                    "requires_rights_confirmation": False,
                    "counted_in_g7": False,
                    "non_count_reason": (
                        "repo-local candidate is not exact counted evidence until it maps "
                        "to the action source and clears benchmark-bridge checks"
                    ),
                    "acceptance_checks": action.get("acceptance_checks", []),
                    "promotion_blockers": promotion_blockers,
                }
            )
    source_ids = sorted({str(row.get("source_id") or "") for row in rows})
    candidate_paths = sorted({str(row.get("candidate_repo_path") or "") for row in rows})
    exact_source_matches = [
        row for row in rows if not bool(row.get("requires_operator_source_mapping"))
    ]
    exact_blocker_counts: dict[str, int] = {}
    for row in exact_source_matches:
        blockers = row.get("promotion_blockers")
        blockers = blockers if isinstance(blockers, list) else []
        for blocker in blockers:
            key = str(blocker)
            if key.startswith("mgt_file_too_small:"):
                key = "mgt_file_too_small"
            exact_blocker_counts[key] = exact_blocker_counts.get(key, 0) + 1
    ifc_source_mapping_candidates = [
        row
        for row in rows
        if str(row.get("candidate_file_type") or "") == ".ifc"
        and str(row.get("action_type") or "") == "attach_operator_real_ifc"
        and bool(row.get("requires_operator_source_mapping"))
        and row.get("promotion_blockers") == ["catalog_source_unmatched_candidate"]
    ]
    summary = {
        "operator_action_repo_candidate_match_count": int(len(rows)),
        "operator_action_repo_candidate_source_count": int(len(source_ids)),
        "operator_action_repo_candidate_file_count": int(len(candidate_paths)),
        "operator_action_repo_candidate_exact_source_match_count": sum(
            1 for row in rows if not bool(row.get("requires_operator_source_mapping"))
        ),
        "operator_action_repo_candidate_exact_clean_count": sum(
            1
            for row in exact_source_matches
            if not row.get("promotion_blockers")
        ),
        "operator_action_repo_candidate_exact_blocker_counts": exact_blocker_counts,
        "operator_action_repo_candidate_requires_source_mapping_count": sum(
            1 for row in rows if bool(row.get("requires_operator_source_mapping"))
        ),
        "operator_action_repo_candidate_ifc_source_mapping_candidate_count": int(
            len(ifc_source_mapping_candidates)
        ),
        "operator_action_repo_candidate_ifc_source_mapping_candidate_source_count": int(
            len(
                {
                    str(row.get("source_id") or "")
                    for row in ifc_source_mapping_candidates
                }
            )
        ),
        "operator_action_repo_candidate_ifc_source_mapping_candidate_file_count": int(
            len(
                {
                    str(row.get("candidate_repo_path") or "")
                    for row in ifc_source_mapping_candidates
                }
            )
        ),
        "operator_action_repo_candidate_benchmark_bridge_count": sum(
            1
            for row in rows
            if "repo_benchmark_bridge_mgt" in row.get("promotion_blockers", [])
        ),
    }
    return {
        "summary": summary,
        "rows": rows,
        "ifc_source_mapping_candidates": ifc_source_mapping_candidates,
    }


def run_korean_medium_large_ingest_pipeline(
    *,
    catalog_path: Path = DEFAULT_CATALOG,
    collection_report_path: Path = DEFAULT_COLLECTION_REPORT,
    receipt_path: Path = DEFAULT_RECEIPT,
    skip_regenerate: bool = False,
    skip_collect: bool = False,
    run_roundtrip_parse: bool = False,
) -> dict[str, Any]:
    benchmark_sha = _sha256_file(BENCHMARK_MGT) if BENCHMARK_MGT.is_file() else ""
    _regenerate_catalog(skip_regenerate=skip_regenerate)
    collection_report = _run_collector(catalog_path=catalog_path, skip_collect=skip_collect)
    catalog = _load_json(catalog_path)
    rows = catalog.get("source_records")
    if not isinstance(rows, list):
        raise ValueError("catalog missing source_records")

    collection_by_id = {
        str(row.get("source_id") or ""): row
        for row in collection_report.get("records", [])
        if isinstance(row, dict) and row.get("source_id")
    }

    per_source: list[dict[str, Any]] = []
    attached_count = 0
    metadata_only_count = 0
    mgt_attached_count = 0
    mgt_header_ok_count = 0
    operator_attached_mgt_header_ok_count = 0
    repo_benchmark_bridge_mgt_header_ok_count = 0
    placeholder_mgt_count = 0
    ifc_attached_count = 0
    operator_attached_ifc_count = 0
    curated_local_ifc_attached_count = 0
    curated_local_ifc_missing_count = 0
    pdf_derived_attached_count = 0
    operator_attached_pdf_derived_count = 0
    operator_attached_real_artifact_count = 0
    metadata_only_source_ids: list[str] = []
    repo_benchmark_bridge_source_ids: list[str] = []
    operator_attach_required_source_ids: list[str] = []
    operator_action_queue: list[dict[str, Any]] = []

    for record in rows:
        if not isinstance(record, dict) or not is_medium_or_large(record):
            continue
        source_id = str(record.get("source_id") or "")
        source_format = str(record.get("format") or "").lower()
        collection_row = collection_by_id.get(source_id, {})
        collected_path = str(collection_row.get("local_path") or "").strip()
        status = str(collection_row.get("status") or "")
        artifact_mgt_path = _find_mgt_artifact(source_id) if source_format == "mgt" else None
        curated_ifc_required = bool(record.get("curated_local_ifc_required", False))
        curated_ifc_status = str(record.get("curated_local_ifc_status") or "").strip()
        curated_ifc_reference = str(record.get("curated_local_ifc_reference") or "").strip()
        curated_ifc_path = _resolve_repo_path(curated_ifc_reference)
        curated_ifc_exists = bool(curated_ifc_path is not None and curated_ifc_path.is_file())
        attached = (
            status == "collected"
            or bool(collected_path)
            or artifact_mgt_path is not None
            or (source_format == "ifc" and curated_ifc_status == "attached" and curated_ifc_exists)
        )
        if attached:
            attached_count += 1
        else:
            metadata_only_count += 1
            metadata_only_source_ids.append(source_id)

        entry: dict[str, Any] = {
            "source_id": source_id,
            "storey_band": record.get("storey_band", ""),
            "scale": building_scale_band(str(record.get("storey_band") or "")),
            "format": source_format,
            "attached": attached,
            "metadata_only": not attached,
            "mgt_header_ok": False,
            "blockers": [],
        }

        if source_format == "mgt" and attached:
            mgt_attached_count += 1
            mgt_path = Path(collected_path) if collected_path else artifact_mgt_path
            if mgt_path is None:
                entry["blockers"].append("attached_mgt_path_unresolved")
            else:
                ok, blockers = _check_mgt_header(mgt_path)
                entry["mgt_header_ok"] = ok
                entry["blockers"].extend(blockers)
                if ok:
                    mgt_header_ok_count += 1
                if any(str(blocker).startswith("mgt_file_too_small:") for blocker in blockers):
                    placeholder_mgt_count += 1
                entry["mgt_path"] = str(mgt_path)
                provenance = _attach_provenance(mgt_path, benchmark_sha)
                entry["attach_provenance"] = provenance
                if ok and provenance == "operator_attached":
                    operator_attached_mgt_header_ok_count += 1
                    operator_attached_real_artifact_count += 1
                if ok and provenance == "repo_benchmark_bridge":
                    repo_benchmark_bridge_mgt_header_ok_count += 1
                    repo_benchmark_bridge_source_ids.append(source_id)
                entry["attachment_detection"] = "collector_report" if collected_path else "artifact_root"
                if run_roundtrip_parse and ok:
                    out_dir = mgt_path.parent / "roundtrip"
                    out_dir.mkdir(parents=True, exist_ok=True)
                    json_out = out_dir / f"{source_id}.roundtrip.json"
                    npz_out = out_dir / f"{source_id}.roundtrip.npz"
                    parser_script = REPO_ROOT / "implementation/phase1/parse_midas_mgt_to_json_npz.py"
                    proc = subprocess.run(
                        [
                            sys.executable,
                            str(parser_script),
                            "--mgt",
                            str(mgt_path),
                            "--json-out",
                            str(json_out),
                            "--npz-out",
                            str(npz_out),
                        ],
                        cwd=REPO_ROOT / "implementation/phase1",
                        capture_output=True,
                        text=True,
                    )
                    entry["roundtrip_parse_exit_code"] = int(proc.returncode)
                    entry["roundtrip_json"] = str(json_out) if json_out.is_file() else ""
                    entry["roundtrip_npz"] = str(npz_out) if npz_out.is_file() else ""
                    if proc.returncode != 0:
                        entry["blockers"].append("roundtrip_parse_failed")
        elif source_format == "mgt" and not attached:
            entry["blockers"].append("awaiting_manual_mgt_attach")
        elif source_format == "ifc":
            if attached:
                ifc_attached_count += 1
            if curated_ifc_status == "attached" and curated_ifc_exists:
                curated_local_ifc_attached_count += 1
            if attached and (collected_path or curated_ifc_exists):
                operator_attached_ifc_count += 1
                operator_attached_real_artifact_count += 1
            if curated_ifc_required and not curated_ifc_exists:
                curated_local_ifc_missing_count += 1
                entry["blockers"].append("curated_local_ifc_missing")
            entry.update(
                {
                    "curated_local_ifc_required": curated_ifc_required,
                    "curated_local_ifc_status": curated_ifc_status,
                    "curated_local_ifc_reference": curated_ifc_reference,
                    "curated_local_ifc_exists": curated_ifc_exists,
                }
            )
            if collected_path:
                entry["ifc_path"] = collected_path
                entry["attachment_detection"] = "collector_report"
                entry["attach_provenance"] = "operator_attached"
            elif curated_ifc_exists and curated_ifc_path is not None:
                entry["ifc_path"] = str(curated_ifc_path)
                entry["attachment_detection"] = "curated_local_ifc_reference"
                entry["attach_provenance"] = "operator_attached"
        elif source_format in {"pdf", "zip"} and attached:
            pdf_derived_attached_count += 1
            if collected_path:
                operator_attached_pdf_derived_count += 1
                operator_attached_real_artifact_count += 1
                entry["artifact_path"] = collected_path
                entry["attachment_detection"] = "collector_report"
                entry["attach_provenance"] = "operator_attached"

        if (
            not attached
            or "awaiting_manual_mgt_attach" in entry["blockers"]
            or "curated_local_ifc_missing" in entry["blockers"]
            or any(str(blocker).startswith("mgt_file_too_small:") for blocker in entry["blockers"])
        ):
            operator_attach_required_source_ids.append(source_id)

        action_row = _operator_action_row(record=record, entry=entry)
        if action_row is not None:
            operator_action_queue.append(action_row)

        per_source.append(entry)

    operator_action_type_counts: dict[str, int] = {}
    for row in operator_action_queue:
        action_type = str(row.get("action_type") or "unknown")
        operator_action_type_counts[action_type] = operator_action_type_counts.get(action_type, 0) + 1
    local_private_candidates = _local_private_candidate_artifacts()
    local_private_candidate_summary = local_private_candidates["summary"]
    private_candidate_matches = _operator_action_private_candidate_matches(
        operator_action_queue=operator_action_queue,
        local_private_candidate_rows=local_private_candidates["rows"],
    )
    repo_public_candidates = _repo_public_candidate_artifacts(benchmark_sha=benchmark_sha)
    repo_candidate_matches = _operator_action_repo_candidate_matches(
        operator_action_queue=operator_action_queue,
        repo_candidate_rows=repo_public_candidates["rows"],
    )
    operator_attached_real_mgt_header_ok_target = 4
    operator_attached_real_mgt_header_ok_remaining = max(
        0,
        operator_attached_real_mgt_header_ok_target - int(operator_attached_mgt_header_ok_count),
    )
    operator_action_packet = _operator_action_packet(
        operator_action_queue=operator_action_queue,
        operator_action_type_counts=operator_action_type_counts,
        operator_attached_real_mgt_header_ok_target=operator_attached_real_mgt_header_ok_target,
        operator_attached_real_mgt_header_ok_remaining=operator_attached_real_mgt_header_ok_remaining,
        metadata_only_source_ids=metadata_only_source_ids,
        repo_benchmark_bridge_source_ids=repo_benchmark_bridge_source_ids,
    )

    receipt = {
        "schema_version": "korean_medium_large_ingest_receipt.v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "catalog_path": str(catalog_path),
        "collection_report_path": str(collection_report_path),
        "summary": {
            "medium_large_source_count": len(per_source),
            "attached_count": attached_count,
            "metadata_only_count": metadata_only_count,
            "mgt_attached_count": mgt_attached_count,
            "mgt_header_ok_count": mgt_header_ok_count,
            "operator_attached_mgt_header_ok_count": operator_attached_mgt_header_ok_count,
            "operator_attached_real_mgt_header_ok_count": operator_attached_mgt_header_ok_count,
            "repo_benchmark_bridge_mgt_header_ok_count": repo_benchmark_bridge_mgt_header_ok_count,
            "placeholder_mgt_count": placeholder_mgt_count,
            "ifc_attached_count": ifc_attached_count,
            "operator_attached_ifc_count": operator_attached_ifc_count,
            "curated_local_ifc_attached_count": curated_local_ifc_attached_count,
            "curated_local_ifc_missing_count": curated_local_ifc_missing_count,
            "pdf_derived_attached_count": pdf_derived_attached_count,
            "operator_attached_pdf_derived_count": operator_attached_pdf_derived_count,
            "operator_attached_real_artifact_count": operator_attached_real_artifact_count,
            "metadata_only_source_ids": metadata_only_source_ids,
            "repo_benchmark_bridge_source_ids": repo_benchmark_bridge_source_ids,
            "operator_attach_required_source_ids": operator_attach_required_source_ids,
            "operator_action_queue_count": len(operator_action_queue),
            "operator_action_queue_source_ids": [
                str(row.get("source_id") or "") for row in operator_action_queue
            ],
            "operator_action_type_counts": operator_action_type_counts,
            "operator_attached_real_mgt_header_ok_target": operator_attached_real_mgt_header_ok_target,
            "operator_attached_real_mgt_header_ok_remaining": (
                operator_attached_real_mgt_header_ok_remaining
            ),
            **local_private_candidate_summary,
            **private_candidate_matches["summary"],
            **repo_public_candidates["summary"],
            **repo_candidate_matches["summary"],
        },
        "per_source": per_source,
        "local_private_candidate_artifacts": local_private_candidates["rows"],
        "operator_action_private_candidate_matches": private_candidate_matches["rows"],
        "repo_public_candidate_artifacts": repo_public_candidates["rows"],
        "operator_action_repo_candidate_matches": repo_candidate_matches["rows"],
        "operator_action_repo_candidate_ifc_source_mapping_candidates": (
            repo_candidate_matches["ifc_source_mapping_candidates"]
        ),
        "operator_action_queue": operator_action_queue,
        "operator_action_packet": operator_action_packet,
        "summary_line": (
            "Korean medium/large ingest: "
            f"sources={len(per_source)} attached={attached_count} "
            f"metadata_only={metadata_only_count} mgt_header_ok={mgt_header_ok_count}"
        ),
    }
    _write_json(receipt_path, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--collection-report", type=Path, default=DEFAULT_COLLECTION_REPORT)
    parser.add_argument("--receipt-out", type=Path, default=DEFAULT_RECEIPT)
    parser.add_argument("--skip-regenerate", action="store_true")
    parser.add_argument("--skip-collect", action="store_true")
    parser.add_argument(
        "--run-roundtrip-parse",
        action="store_true",
        help="Run parse_midas_mgt_to_json_npz for attached MGT with valid headers",
    )
    args = parser.parse_args()

    receipt = run_korean_medium_large_ingest_pipeline(
        catalog_path=args.catalog,
        collection_report_path=args.collection_report,
        receipt_path=args.receipt_out,
        skip_regenerate=args.skip_regenerate,
        skip_collect=args.skip_collect,
        run_roundtrip_parse=args.run_roundtrip_parse,
    )
    print(receipt["summary_line"])
    print(f"Wrote receipt: {args.receipt_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
