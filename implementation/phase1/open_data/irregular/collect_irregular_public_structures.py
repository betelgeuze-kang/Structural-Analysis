#!/usr/bin/env python3
"""Collect a local-first, format-agnostic irregular-structure corpus draft."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
from typing import Any
from urllib.parse import quote, unquote, urlparse
from urllib.request import urlopen
import zipfile

REPO_ROOT = Path(__file__).resolve().parents[4]

REASONS = {
    "PASS": "irregular structure source catalog processed",
    "ERR_INVALID_INPUT": "invalid irregular structure collector input",
}

CATALOG_SCHEMA_VERSION = "1.0"
REPORT_SCHEMA_VERSION = "1.0"
COLLECTOR_VERSION = "0.2.0"
GIT_LFS_POINTER_PREFIX = b"version https://git-lfs.github.com/spec/"

SUPPORTED_FORMATS = (
    "mgt",
    "inp",
    "tcl",
    "ifc",
    "dxf",
    "csv_tables",
    "step",
    "iges",
    "json_graph",
    "zip_bundle",
    "mcb",
    "meb",
    "mmbx",
    "gh",
    "rhino_3dm",
    "mat",
    "npz",
    "report_pdf",
    "metadata_json",
    "sensor_csv",
    "model_text",
)

FORMAT_SUFFIXES = {
    "mgt": {".mgt"},
    "inp": {".inp"},
    "tcl": {".tcl"},
    "ifc": {".ifc"},
    "dxf": {".dxf"},
    "csv_tables": {".csv", ".tsv"},
    "step": {".step", ".stp"},
    "iges": {".iges", ".igs"},
    "json_graph": {".json", ".jsonl"},
    "zip_bundle": {".zip"},
    "mcb": {".mcb"},
    "meb": {".meb"},
    "mmbx": {".mmbx"},
    "gh": {".gh"},
    "rhino_3dm": {".3dm"},
    "mat": {".mat"},
    "npz": {".npz"},
    "report_pdf": {".pdf"},
}

DEFAULT_CATALOG = "implementation/phase1/open_data/irregular/irregular_structure_source_catalog.json"
DEFAULT_OUT_DIR = "implementation/phase1/open_data/irregular/collected"
DEFAULT_REPORT_OUT = "implementation/phase1/open_data/irregular/irregular_structure_collection_report.json"


def _safe_name(value: str) -> str:
    name = re.sub(r"[^a-zA-Z0-9_.-]+", "_", str(value).strip())
    return name.strip("._") or "source"


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise RuntimeError(f"missing file: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"expected object json: {path}")
    return payload


def _normalize_format(value: Any) -> str:
    text = str(value or "").strip().lower()
    return text if text in SUPPORTED_FORMATS else ""


def _format_from_suffix(path: Path) -> str:
    suffix = path.suffix.lower()
    for source_format, suffixes in FORMAT_SUFFIXES.items():
        if suffix in suffixes:
            return source_format
    return ""


def _resolve_local_reference(source: dict[str, Any], catalog_path: Path) -> tuple[str, str, Path | None, str]:
    raw_ref = str(source.get("url") or source.get("path") or source.get("local_path") or "").strip()
    if not raw_ref:
        return "", "", None, ""

    parsed = urlparse(raw_ref)
    if parsed.scheme == "file":
        if parsed.netloc not in {"", "localhost"}:
            return raw_ref, "file", None, "unsupported file url host"
        resolved = Path(unquote(parsed.path))
        return raw_ref, "file", resolved, ""
    if parsed.scheme in {"http", "https"}:
        return raw_ref, parsed.scheme.lower(), None, ""
    if parsed.scheme not in {"", None}:
        return raw_ref, parsed.scheme.lower(), None, "unsupported source scheme"

    candidate = Path(raw_ref)
    if not candidate.is_absolute():
        repo_candidate = (REPO_ROOT / candidate).resolve()
        catalog_candidate = (catalog_path.parent / candidate).resolve()
        if candidate.parts and candidate.parts[0] in {"implementation", "tests", "docs"}:
            candidate = repo_candidate
        elif catalog_candidate.exists():
            candidate = catalog_candidate
        else:
            candidate = repo_candidate
    return raw_ref, "local_path", candidate, ""


def _classify_format(source: dict[str, Any], source_path: Path | None) -> tuple[str, str]:
    declared_candidates = source.get("formats") if isinstance(source.get("formats"), list) else []
    declared_candidates = [fmt for fmt in declared_candidates if _normalize_format(fmt)]
    if declared_candidates:
        return _normalize_format(declared_candidates[0]), "declared_formats_list"
    declared_format = _normalize_format(source.get("format") or source.get("source_format") or source.get("primary_format"))
    if declared_format:
        return declared_format, "declared_format"
    if source_path is not None:
        inferred_format = _format_from_suffix(source_path)
        if inferred_format:
            return inferred_format, "suffix_inference"
    return "", "unknown"


def _zip_summary(path: Path) -> dict[str, Any]:
    with zipfile.ZipFile(path, "r") as zip_file:
        members = sorted(info.filename for info in zip_file.infolist() if not info.is_dir())
    return {
        "member_count": len(members),
        "member_names_sample": members[:16],
    }


def _remote_asset_filename(remote_url: str, source_id: str, source_format: str) -> str:
    parsed = urlparse(remote_url)
    candidate = Path(unquote(parsed.path)).name.strip()
    if candidate:
        return candidate
    suffixes = next(iter(FORMAT_SUFFIXES.get(source_format, {".bin"})), ".bin")
    return f"{source_id}{suffixes}"


def _remote_url_is_direct_asset(remote_url: str, source_format: str) -> bool:
    if not source_format:
        return False
    parsed = urlparse(remote_url)
    if parsed.scheme.lower() not in {"http", "https"}:
        return False
    path = Path(unquote(parsed.path))
    suffix = path.suffix.lower()
    return suffix in FORMAT_SUFFIXES.get(source_format, set())


def _looks_like_git_lfs_pointer(data: bytes) -> bool:
    return data.lstrip().startswith(GIT_LFS_POINTER_PREFIX)


def _fetch_remote_json(remote_url: str) -> Any:
    with urlopen(remote_url, timeout=20) as response:
        data = response.read()
    try:
        payload = json.loads(data.decode("utf-8"))
    except Exception:
        return {}
    return payload


def _metadata_remote_hints(source: dict[str, Any]) -> list[str]:
    metadata = source.get("metadata") if isinstance(source.get("metadata"), dict) else {}
    ordered: list[str] = []
    for key in (
        "download_url",
        "raw_asset_url",
        "github_download_url",
        "github_api_url",
        "zenodo_download_url",
        "designsafe_download_url",
    ):
        value = str(metadata.get(key, "") or "").strip()
        if value and value not in ordered:
            ordered.append(value)
    return ordered


def _github_candidate_urls(remote_url: str, source_format: str) -> list[str]:
    parsed = urlparse(remote_url)
    host = parsed.netloc.lower()
    path = parsed.path
    candidates: list[str] = []
    if host == "raw.githubusercontent.com":
        candidates.append(remote_url)
    elif host == "github.com" and "/blob/" in path:
        prefix, suffix = path.split("/blob/", 1)
        branch, _, rest = suffix.partition("/")
        if branch and rest:
            candidates.append(f"https://raw.githubusercontent.com{prefix}/{branch}/{rest}")
    elif host == "api.github.com" and "/contents/" in path:
        payload = _fetch_remote_json(remote_url)
        if isinstance(payload, dict):
            download_url = str(payload.get("download_url", "") or "").strip()
            if download_url:
                candidates.append(download_url)
        elif isinstance(payload, list):
            for row in payload:
                if not isinstance(row, dict):
                    continue
                download_url = str(row.get("download_url", "") or "").strip()
                if download_url and _remote_url_is_direct_asset(download_url, source_format):
                    candidates.append(download_url)
    return candidates


def _zenodo_candidate_urls(remote_url: str) -> list[str]:
    parsed = urlparse(remote_url)
    if parsed.netloc.lower() != "zenodo.org":
        return []
    if "/records/" in parsed.path and "/files/" in parsed.path:
        if "download=1" in (parsed.query or ""):
            return [remote_url]
        joiner = "&" if parsed.query else "?"
        return [f"{remote_url}{joiner}download=1"]
    return []


def _designsafe_candidate_urls(remote_url: str, source_format: str) -> list[str]:
    parsed = urlparse(remote_url)
    host = parsed.netloc.lower()
    if "designsafe-ci.org" not in host:
        return []
    if _remote_url_is_direct_asset(remote_url, source_format):
        return [remote_url]
    path = parsed.path.lower()
    if ("/media/filer_public/" in path or "/media/cms_page_media/" in path) and Path(unquote(parsed.path)).suffix:
        return [remote_url]
    return []


def _designsafe_preview_paths(source: dict[str, Any]) -> list[str]:
    metadata = source.get("metadata") if isinstance(source.get("metadata"), dict) else {}
    values = metadata.get("designsafe_preview_paths")
    if not isinstance(values, list):
        return []
    paths: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in paths:
            paths.append(text)
    return paths


def _designsafe_preview_api_base(source: dict[str, Any]) -> str:
    metadata = source.get("metadata") if isinstance(source.get("metadata"), dict) else {}
    base = str(metadata.get("designsafe_preview_api_base", "") or "").strip()
    if base:
        return base.rstrip("/")
    return "https://www.designsafe-ci.org/api/datafiles/agave/public/preview/designsafe.storage.published"


def _designsafe_primary_preview_path(source: dict[str, Any], preview_paths: list[str]) -> str:
    metadata = source.get("metadata") if isinstance(source.get("metadata"), dict) else {}
    primary = str(metadata.get("designsafe_primary_preview_path", "") or "").strip()
    if primary:
        return primary
    return preview_paths[0] if preview_paths else ""


def _designsafe_listing_path(source: dict[str, Any], preview_paths: list[str]) -> str:
    metadata = source.get("metadata") if isinstance(source.get("metadata"), dict) else {}
    listing_path = str(metadata.get("designsafe_listing_path", "") or "").strip()
    if listing_path:
        return listing_path.rstrip("/")
    primary = _designsafe_primary_preview_path(source, preview_paths)
    return str(Path(primary).parent).rstrip("/") if primary else ""


def _designsafe_preview_relative_path(path: str, listing_path: str) -> str:
    normalized_path = str(path or "").strip().lstrip("/")
    normalized_root = str(listing_path or "").strip().lstrip("/")
    if normalized_root and normalized_path.startswith(normalized_root.rstrip("/") + "/"):
        relative = normalized_path[len(normalized_root.rstrip("/")) + 1 :]
        if relative:
            return relative
    return Path(normalized_path).name or _safe_name(normalized_path)


def _fetch_designsafe_preview_bundle(
    *,
    source: dict[str, Any],
    source_id: str,
    source_format: str,
    artifacts_dir: Path,
    per_source_reports_dir: Path,
    original_ref: str,
    source_urls: list[str],
) -> dict[str, Any] | None:
    preview_paths = _designsafe_preview_paths(source)
    if not preview_paths:
        return None

    api_base = _designsafe_preview_api_base(source)
    listing_path = _designsafe_listing_path(source, preview_paths)
    primary_preview_path = _designsafe_primary_preview_path(source, preview_paths)

    artifact_dir = artifacts_dir / source_id
    artifact_dir.mkdir(parents=True, exist_ok=True)
    source_report_path = per_source_reports_dir / f"{source_id}.json"
    metadata_path = artifact_dir / "source_metadata.json"

    copied_paths: list[str] = []
    primary_copied_path = ""
    total_bytes = 0
    sha_entries: list[dict[str, Any]] = []

    for preview_path in preview_paths:
        preview_url = f"{api_base}/{quote(preview_path.lstrip('/'), safe='/')}"
        with urlopen(preview_url, timeout=30) as preview_response:
            preview_payload = json.loads(preview_response.read().decode("utf-8"))
        href = str(preview_payload.get("href", "") or "").strip()
        if not href:
            raise RuntimeError(f"missing preview href for {preview_path}")
        file_type = str(preview_payload.get("fileType", "") or "").strip()
        with urlopen(href, timeout=30) as redeemed_response:
            data = redeemed_response.read()
            content_type = str(redeemed_response.headers.get("Content-Type", "") or "").strip()

        relative_path = _designsafe_preview_relative_path(preview_path, listing_path)
        copied_path = artifact_dir / relative_path
        copied_path.parent.mkdir(parents=True, exist_ok=True)
        copied_path.write_bytes(data)

        sha = _sha256_bytes(data)
        copied_paths.append(str(copied_path.resolve()))
        total_bytes += len(data)
        sha_entries.append(
            {
                "preview_path": preview_path,
                "copied_path": str(copied_path.resolve()),
                "sha256": sha,
                "bytes": len(data),
                "file_type": file_type,
                "content_type": content_type,
                "preview_href": href,
            }
        )
        if preview_path == primary_preview_path:
            primary_copied_path = str(copied_path.resolve())

    if not primary_copied_path and copied_paths:
        primary_copied_path = copied_paths[0]

    bundle_sha = hashlib.sha256(
        "\n".join(entry["sha256"] for entry in sorted(sha_entries, key=lambda row: row["preview_path"])).encode("utf-8")
    ).hexdigest()

    metadata_payload = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "collector_version": COLLECTOR_VERSION,
        "source_id": source_id,
        "source_format": source_format,
        "original_reference": original_ref,
        "source_urls": source_urls,
        "download_mode": "designsafe_preview_bundle",
        "designsafe_preview_api_base": api_base,
        "designsafe_listing_path": listing_path,
        "designsafe_primary_preview_path": primary_preview_path,
        "preview_entries": sha_entries,
        "bundle_sha256": bundle_sha,
        "bytes_copied": total_bytes,
    }
    _write_json(metadata_path, metadata_payload)

    return {
        "status": "collected",
        "source_exists": True,
        "bytes_copied": total_bytes,
        "sha256": bundle_sha,
        "remote_fetch_note": "designsafe_preview_bundle",
        "artifacts": {
            "artifact_dir": str(artifact_dir.resolve()),
            "copied_source_path": primary_copied_path,
            "source_metadata_path": str(metadata_path.resolve()),
            "source_report_path": str(source_report_path.resolve()),
        },
        "designsafe_preview_bundle": {
            "entry_count": len(sha_entries),
            "listing_path": listing_path,
            "primary_preview_path": primary_preview_path,
            "copied_paths": copied_paths,
        },
    }


def _candidate_remote_asset_urls(source: dict[str, Any], original_ref: str, source_format: str) -> list[str]:
    candidates: list[str] = []

    def _append(value: str) -> None:
        text = str(value or "").strip()
        if text and text not in candidates:
            candidates.append(text)

    raw_candidates = [original_ref]
    if isinstance(source.get("source_urls"), list):
        raw_candidates.extend(str(url).strip() for url in source.get("source_urls", []) if str(url).strip())
    raw_candidates.extend(_metadata_remote_hints(source))

    for remote_url in raw_candidates:
        if not remote_url:
            continue
        parsed = urlparse(remote_url)
        if parsed.scheme.lower() not in {"http", "https"}:
            continue
        if _remote_url_is_direct_asset(remote_url, source_format):
            _append(remote_url)
        for derived in _github_candidate_urls(remote_url, source_format):
            _append(derived)
        for derived in _zenodo_candidate_urls(remote_url):
            _append(derived)
        for derived in _designsafe_candidate_urls(remote_url, source_format):
            _append(derived)
    return candidates


def _fetch_remote_asset(remote_url: str) -> tuple[bytes, str]:
    with urlopen(remote_url, timeout=20) as response:
        data = response.read()
        content_type = str(response.headers.get("Content-Type", "") or "").strip()
    return data, content_type


def _initial_summary() -> dict[str, Any]:
    return {
        "source_count": 0,
        "collected_count": 0,
        "metadata_only_remote_candidate_count": 0,
        "rejected_count": 0,
        "local_path_count": 0,
        "file_url_count": 0,
        "remote_reference_count": 0,
        "declared_format_count": 0,
        "inferred_format_count": 0,
        "total_bytes_copied": 0,
        "status_counts": {
            "collected": 0,
            "metadata_only_remote_candidate": 0,
            "rejected": 0,
        },
        "format_counts": {source_format: 0 for source_format in SUPPORTED_FORMATS},
    }


def _source_rows(catalog: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(catalog.get("sources"), list):
        return [row for row in catalog["sources"] if isinstance(row, dict)]
    if isinstance(catalog.get("source_records"), list):
        return [row for row in catalog["source_records"] if isinstance(row, dict)]
    return []


def collect_irregular_public_structures(
    catalog_path: Path | str,
    out_dir: Path | str,
    report_out: Path | str,
) -> dict[str, Any]:
    catalog_path = Path(catalog_path)
    out_dir = Path(out_dir)
    report_out = Path(report_out)

    artifacts_dir = out_dir / "artifacts"
    per_source_reports_dir = out_dir / "reports"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    per_source_reports_dir.mkdir(parents=True, exist_ok=True)

    reason_code = "PASS"
    records: list[dict[str, Any]] = []
    summary = _initial_summary()
    catalog: dict[str, Any] = {}

    try:
        catalog = _load_json(catalog_path)
        if str(catalog.get("schema_version", "")) != CATALOG_SCHEMA_VERSION:
            reason_code = "ERR_INVALID_INPUT"
        raw_sources = _source_rows(catalog)
        if not raw_sources:
            reason_code = "ERR_INVALID_INPUT"
    except Exception:
        reason_code = "ERR_INVALID_INPUT"
        raw_sources = []

    source_ids_seen: dict[str, int] = {}
    if reason_code == "PASS":
        for index, item in enumerate(raw_sources, 1):
            raw_source_id = str(item.get("source_id") or f"source_{index}").strip()
            source_id_base = _safe_name(raw_source_id)
            source_ids_seen[source_id_base] = source_ids_seen.get(source_id_base, 0) + 1
            source_id = source_id_base if source_ids_seen[source_id_base] == 1 else f"{source_id_base}_{source_ids_seen[source_id_base]:03d}"

            original_ref, scheme, resolved_path, ref_error = _resolve_local_reference(item, catalog_path)
            source_format, format_detection_mode = _classify_format(item, resolved_path)
            declared_format = _normalize_format(item.get("format") or item.get("source_format") or item.get("primary_format"))
            source_urls = [str(url).strip() for url in item.get("source_urls", []) if str(url).strip()] if isinstance(item.get("source_urls"), list) else []

            record: dict[str, Any] = {
                "source_id": source_id,
                "source_index": index,
                "title": str(item.get("title") or item.get("source_name") or item.get("name") or "").strip(),
                "family_id": str(item.get("family_id") or item.get("source_family") or "").strip(),
                "original_reference": original_ref,
                "reference_scheme": scheme,
                "source_urls": source_urls,
                "resolved_path": str(resolved_path) if resolved_path is not None else "",
                "declared_format": declared_format,
                "source_format": source_format,
                "format_detection_mode": format_detection_mode,
                "status": "rejected",
                "reject_reason": "",
                "source_exists": False,
                "bytes_copied": 0,
                "sha256": "",
                "artifacts": {},
                "metadata": item.get("metadata") if isinstance(item.get("metadata"), dict) else {},
                "remote_candidate_urls": [],
                "remote_fetch_note": "",
            }

            summary["source_count"] += 1
            if scheme == "local_path":
                summary["local_path_count"] += 1
            elif scheme == "file":
                summary["file_url_count"] += 1
            elif scheme in {"http", "https"} or (resolved_path is None and source_urls):
                summary["remote_reference_count"] += 1

            if format_detection_mode in {"declared_format", "declared_formats_list"}:
                summary["declared_format_count"] += 1
            elif format_detection_mode == "suffix_inference":
                summary["inferred_format_count"] += 1

            if source_format:
                summary["format_counts"][source_format] = summary["format_counts"].get(source_format, 0) + 1

            if ref_error:
                record["reject_reason"] = ref_error
            elif not source_format:
                record["reject_reason"] = "unsupported or unknown source format"
            elif resolved_path is None and (scheme in {"http", "https"} or source_urls):
                if _designsafe_preview_paths(item):
                    try:
                        bundle_record = _fetch_designsafe_preview_bundle(
                            source=item,
                            source_id=source_id,
                            source_format=source_format,
                            artifacts_dir=artifacts_dir,
                            per_source_reports_dir=per_source_reports_dir,
                            original_ref=original_ref,
                            source_urls=source_urls,
                        )
                    except Exception as exc:  # pragma: no cover - network failure branch is environment-dependent
                        record["remote_fetch_note"] = f"designsafe_preview_failed:{type(exc).__name__}"
                    else:
                        if bundle_record is not None:
                            record.update(bundle_record)
                            _write_json(Path(record["artifacts"]["source_report_path"]), record)
                            summary["collected_count"] += 1
                            summary["status_counts"]["collected"] += 1
                            summary["total_bytes_copied"] += int(record["bytes_copied"] or 0)
                            records.append(record)
                            continue
                remote_candidate_urls = _candidate_remote_asset_urls(item, original_ref, source_format)
                record["remote_candidate_urls"] = remote_candidate_urls
                remote_fetch_note = ""
                fetched = False
                for candidate_url in remote_candidate_urls:
                    try:
                        data, content_type = _fetch_remote_asset(candidate_url)
                    except Exception as exc:  # pragma: no cover - network failure branch is environment-dependent
                        remote_fetch_note = f"fetch_failed:{type(exc).__name__}"
                        continue
                    if _looks_like_git_lfs_pointer(data):
                        remote_fetch_note = "git_lfs_pointer_detected"
                        continue

                    artifact_dir = artifacts_dir / source_id
                    artifact_dir.mkdir(parents=True, exist_ok=True)
                    copied_name = _remote_asset_filename(candidate_url, source_id, source_format)
                    copied_path = artifact_dir / copied_name
                    copied_path.write_bytes(data)
                    metadata_path = artifact_dir / "source_metadata.json"
                    source_report_path = per_source_reports_dir / f"{source_id}.json"
                    zip_details: dict[str, Any] = {}
                    if source_format == "zip_bundle":
                        zip_details = _zip_summary(copied_path)

                    record["status"] = "collected"
                    record["source_exists"] = True
                    record["bytes_copied"] = len(data)
                    record["sha256"] = _sha256_bytes(data)
                    record["remote_fetch_note"] = remote_fetch_note or "provider_remote_asset"
                    record["artifacts"] = {
                        "artifact_dir": str(artifact_dir.resolve()),
                        "copied_source_path": str(copied_path.resolve()),
                        "source_metadata_path": str(metadata_path.resolve()),
                        "source_report_path": str(source_report_path.resolve()),
                    }
                    if zip_details:
                        record["zip_bundle"] = zip_details

                    _write_json(
                        metadata_path,
                        {
                            "schema_version": REPORT_SCHEMA_VERSION,
                            "collector_version": COLLECTOR_VERSION,
                            "source_id": source_id,
                            "title": record["title"],
                            "family_id": record["family_id"],
                            "source_format": source_format,
                            "original_reference": original_ref,
                            "remote_candidate_url": candidate_url,
                            "source_urls": source_urls,
                            "sha256": record["sha256"],
                            "bytes_copied": len(data),
                            "download_mode": "remote_provider_asset",
                            "content_type": content_type,
                        },
                    )
                    _write_json(source_report_path, record)

                    summary["collected_count"] += 1
                    summary["status_counts"]["collected"] += 1
                    summary["total_bytes_copied"] += len(data)
                    fetched = True
                    break

                if not fetched:
                    record["status"] = "metadata_only_remote_candidate"
                    record["remote_fetch_note"] = remote_fetch_note or "no_direct_asset_candidate"
                    summary["metadata_only_remote_candidate_count"] += 1
                    summary["status_counts"]["metadata_only_remote_candidate"] += 1
                    record["artifacts"] = {
                        "artifact_dir": "",
                        "source_metadata_path": "",
                        "source_report_path": "",
                    }
            elif resolved_path is None or not resolved_path.exists() or not resolved_path.is_file():
                record["reject_reason"] = "missing local source file"
            else:
                data = resolved_path.read_bytes()
                artifact_dir = artifacts_dir / source_id
                artifact_dir.mkdir(parents=True, exist_ok=True)
                copied_name = resolved_path.name or f"{source_id}.bin"
                copied_path = artifact_dir / copied_name
                if copied_path.resolve() != resolved_path.resolve():
                    shutil.copyfile(resolved_path, copied_path)
                metadata_path = artifact_dir / "source_metadata.json"
                source_report_path = per_source_reports_dir / f"{source_id}.json"
                zip_details: dict[str, Any] = {}
                if source_format == "zip_bundle":
                    zip_details = _zip_summary(copied_path)

                record["status"] = "collected"
                record["source_exists"] = True
                record["bytes_copied"] = len(data)
                record["sha256"] = _sha256_bytes(data)
                record["artifacts"] = {
                    "artifact_dir": str(artifact_dir.resolve()),
                    "copied_source_path": str(copied_path.resolve()),
                    "source_metadata_path": str(metadata_path.resolve()),
                    "source_report_path": str(source_report_path.resolve()),
                }
                if zip_details:
                    record["zip_bundle"] = zip_details

                _write_json(
                    metadata_path,
                    {
                        "schema_version": REPORT_SCHEMA_VERSION,
                        "collector_version": COLLECTOR_VERSION,
                        "source_id": source_id,
                        "title": record["title"],
                        "family_id": record["family_id"],
                        "source_format": source_format,
                        "original_reference": original_ref,
                        "source_urls": source_urls,
                        "sha256": record["sha256"],
                        "bytes_copied": len(data),
                    },
                )
                _write_json(source_report_path, record)

                summary["collected_count"] += 1
                summary["status_counts"]["collected"] += 1
                summary["total_bytes_copied"] += len(data)

            if record["status"] == "rejected":
                summary["rejected_count"] += 1
                summary["status_counts"]["rejected"] += 1

            records.append(record)

    contract_pass = reason_code == "PASS"
    report = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "collector_version": COLLECTOR_VERSION,
        "contract_pass": contract_pass,
        "reason_code": reason_code,
        "reason": REASONS[reason_code],
        "catalog_path": str(catalog_path),
        "out_dir": str(out_dir),
        "summary": summary,
        "records": records,
    }
    _write_json(report_out, report)
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", default=DEFAULT_CATALOG)
    parser.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
    parser.add_argument("--report-out", default=DEFAULT_REPORT_OUT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = collect_irregular_public_structures(args.catalog, args.out_dir, args.report_out)
    print(f"Wrote irregular structure collection report: {args.report_out}")
    return 0 if report["contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
