#!/usr/bin/env python3
"""Materialize private real-drawing corpus files and redacted release-safe metadata."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen
import zipfile


CATALOG_SCHEMA_VERSION = "real-drawing-private-corpus-catalog.v1"
MANIFEST_SCHEMA_VERSION = "real-drawing-private-corpus-manifest.v1"
REDACTED_SCHEMA_VERSION = "real-drawing-redacted-corpus-manifest.v1"
DEFAULT_CATALOG = Path("implementation/phase1/real_drawing_private_corpus_seed_catalog.json")
DEFAULT_PRIVATE_ROOT = Path("private_corpus/real_drawings")
DEFAULT_OUT_MANIFEST = DEFAULT_PRIVATE_ROOT / "private_real_drawing_corpus_manifest.json"
DEFAULT_OUT_REDACTED = Path("tmp/real_drawing_private_corpus/redacted_manifest.json")
DEFAULT_OUT_SUMMARY = Path("tmp/real_drawing_private_corpus/summary.json")
MODEL_FILE_TYPES = {".mgt", ".ifc", ".dxf"}
MODEL_ARCHIVE_FILE_TYPES = {".zip"}
MODEL_ARCHIVE_MEMBER_SUFFIXES = {".mgt", ".ifc", ".dxf", ".mcb", ".meb", ".mgb", ".mmb", ".mmbx"}
REDACTED_FILE_OMIT_KEYS = {"private_path", "fetch", "zip_model_member_names_sample"}


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256_bytes(data: bytes) -> str:
    h = hashlib.sha256()
    h.update(data)
    return h.hexdigest()


def _md5_bytes(data: bytes) -> str:
    h = hashlib.md5()
    h.update(data)
    return h.hexdigest()


def _safe_slug(value: Any) -> str:
    text = str(value or "").strip().lower()
    chars = [ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in text]
    slug = "".join(chars).strip("._")
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug or "item"


def _is_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https", "file"} and bool(parsed.netloc or parsed.scheme == "file")


def _fetch_bytes(source_url: str, *, timeout_sec: int) -> tuple[bytes, dict[str, Any]]:
    parsed = urlparse(source_url)
    if parsed.scheme == "file":
        source_path = Path(parsed.path)
        data = source_path.read_bytes()
        return data, {"source_kind": "file", "status": 200, "content_type": "application/octet-stream"}
    request = Request(source_url, headers={"User-Agent": "real-drawing-private-corpus/1.0"})
    with urlopen(request, timeout=timeout_sec) as response:
        data = response.read()
        return data, {
            "source_kind": "http",
            "status": int(getattr(response, "status", 200)),
            "content_type": str(response.headers.get("Content-Type", "") or ""),
        }


def _role_is_drawing(role: str, file_type: str) -> bool:
    role_text = role.lower()
    return "drawing" in role_text or file_type.lower() in {".mgt", ".ifc", ".dwg", ".dxf", ".pdf"}


def _role_is_model_candidate(role: str, file_type: str) -> bool:
    role_text = role.lower()
    return file_type.lower() in MODEL_FILE_TYPES or "model" in role_text


def _pdf_page_count(path: Path) -> int:
    if path.suffix.lower() != ".pdf":
        return 0
    pdfinfo = shutil.which("pdfinfo")
    if not pdfinfo:
        return 0
    proc = subprocess.run([pdfinfo, str(path)], capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        return 0
    for line in proc.stdout.splitlines():
        if line.lower().startswith("pages:"):
            try:
                return int(line.split(":", 1)[1].strip())
            except Exception:
                return 0
    return 0


def _zip_model_member_summary(path: Path) -> dict[str, Any]:
    if path.suffix.lower() not in MODEL_ARCHIVE_FILE_TYPES:
        return {}
    try:
        with zipfile.ZipFile(path, "r") as zip_file:
            members = sorted(info.filename for info in zip_file.infolist() if not info.is_dir())
    except zipfile.BadZipFile:
        return {"zip_member_count": 0, "zip_model_member_count": 0, "zip_error": "bad zip file"}
    model_members = [
        member
        for member in members
        if Path(member).suffix.lower() in MODEL_ARCHIVE_MEMBER_SUFFIXES
    ]
    return {
        "zip_member_count": len(members),
        "zip_model_member_count": len(model_members),
        "zip_model_member_names_sample": model_members[:16],
    }


def _model_asset_count(row: dict[str, Any]) -> int:
    if not row.get("model_optimization_candidate"):
        return 0
    file_type = str(row.get("file_type", "") or "").lower()
    if file_type in MODEL_FILE_TYPES:
        return 1
    if file_type in MODEL_ARCHIVE_FILE_TYPES:
        return int(row.get("zip_model_member_count", 0) or 0)
    return 1


def _catalog_policy(catalog: dict[str, Any]) -> dict[str, Any]:
    policy = catalog.get("policy")
    if not isinstance(policy, dict):
        policy = {}
    return {
        "raw_redistribution_allowed": bool(policy.get("raw_redistribution_allowed", False)),
        "release_surface_allowed": bool(policy.get("release_surface_allowed", False)),
        "storage_boundary": str(policy.get("storage_boundary", "private_corpus_only") or "private_corpus_only"),
        "license_basis": str(
            policy.get(
                "license_basis",
                "Raw files are private corpus inputs until document-level redistribution review is complete.",
            )
            or ""
        ),
    }


def build_manifest(
    *,
    catalog_path: Path,
    private_root: Path,
    download: bool,
    timeout_sec: int,
    max_bytes: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    catalog = _load_json(catalog_path)
    if catalog.get("schema_version") != CATALOG_SCHEMA_VERSION:
        raise ValueError(f"unsupported catalog schema: {catalog_path}")
    policy = _catalog_policy(catalog)
    generated_at = datetime.now(timezone.utc).isoformat()
    projects: list[dict[str, Any]] = []
    redacted_projects: list[dict[str, Any]] = []
    errors: list[str] = []
    downloaded_count = 0
    reused_count = 0
    total_bytes = 0
    drawing_candidate_count = 0
    downloaded_drawing_candidate_count = 0
    drawing_sheet_candidate_count = 0
    model_candidate_count = 0
    downloaded_model_candidate_count = 0
    model_asset_count = 0
    file_type_counts: dict[str, int] = {}
    downloaded_file_type_counts: dict[str, int] = {}
    model_candidate_file_type_counts: dict[str, int] = {}

    for project in catalog.get("projects", []):
        if not isinstance(project, dict):
            continue
        project_id = _safe_slug(project.get("project_id", "project"))
        project_dir = private_root / project_id
        raw_dir = project_dir / "raw"
        files: list[dict[str, Any]] = []
        redacted_files: list[dict[str, Any]] = []
        for file_row in project.get("files", []):
            if not isinstance(file_row, dict):
                continue
            file_id = _safe_slug(file_row.get("file_id", "file"))
            file_name = _safe_slug(file_row.get("file_name", file_id))
            source_url = str(file_row.get("source_url", "") or "").strip()
            file_type = str(file_row.get("file_type", Path(file_name).suffix) or "").lower()
            role = str(file_row.get("role", "") or "")
            expected_sha256 = str(file_row.get("expected_sha256", "") or "").strip().lower()
            expected_md5 = str(file_row.get("expected_md5", "") or "").strip().lower()
            row: dict[str, Any] = {
                "file_id": file_id,
                "file_name": file_name,
                "file_type": file_type,
                "role": role,
                "source_url": source_url,
                "retrieval_status": "candidate",
                "sha256": "",
                "bytes": 0,
                "private_path": "",
                "raw_redistribution_allowed": False,
                "release_surface_allowed": False,
                "drawing_review_candidate": _role_is_drawing(role, file_type),
                "model_optimization_candidate": _role_is_model_candidate(role, file_type),
            }
            if expected_sha256:
                row["expected_sha256"] = expected_sha256
            if expected_md5:
                row["expected_md5"] = expected_md5
            file_type_counts[file_type or "unknown"] = file_type_counts.get(file_type or "unknown", 0) + 1
            if row["drawing_review_candidate"]:
                drawing_candidate_count += 1
            if row["model_optimization_candidate"]:
                model_candidate_count += 1
                model_candidate_file_type_counts[file_type or "unknown"] = (
                    model_candidate_file_type_counts.get(file_type or "unknown", 0) + 1
                )
            if not _is_url(source_url):
                row["retrieval_status"] = "blocked"
                row["error"] = "invalid source_url"
                errors.append(f"{project_id}/{file_id}: invalid source_url")
            elif download:
                try:
                    raw_dir.mkdir(parents=True, exist_ok=True)
                    private_path = raw_dir / file_name
                    if private_path.exists():
                        data = private_path.read_bytes()
                        fetch_meta = {"source_kind": "existing_private", "status": "reused"}
                        reused_count += 1
                    else:
                        data, fetch_meta = _fetch_bytes(source_url, timeout_sec=timeout_sec)
                    if len(data) > max_bytes:
                        raise ValueError(f"download exceeds max bytes: {len(data)} > {max_bytes}")
                    actual_sha256 = _sha256_bytes(data)
                    actual_md5 = _md5_bytes(data)
                    if expected_sha256 and actual_sha256 != expected_sha256:
                        raise ValueError(f"sha256 mismatch: expected {expected_sha256}, got {actual_sha256}")
                    if expected_md5 and actual_md5 != expected_md5:
                        raise ValueError(f"md5 mismatch: expected {expected_md5}, got {actual_md5}")
                    private_path.write_bytes(data)
                    zip_summary = _zip_model_member_summary(private_path)
                    row.update(
                        {
                            "retrieval_status": "downloaded",
                            "sha256": actual_sha256,
                            "md5": actual_md5,
                            "bytes": int(len(data)),
                            "private_path": str(private_path),
                            "pdf_page_count": _pdf_page_count(private_path),
                            "fetch": fetch_meta,
                            **zip_summary,
                        }
                    )
                    if row["drawing_review_candidate"]:
                        downloaded_drawing_candidate_count += 1
                        drawing_sheet_candidate_count += int(row.get("pdf_page_count", 0) or 0)
                    if row["model_optimization_candidate"]:
                        downloaded_model_candidate_count += 1
                        model_asset_count += _model_asset_count(row)
                    downloaded_file_type_counts[file_type or "unknown"] = (
                        downloaded_file_type_counts.get(file_type or "unknown", 0) + 1
                    )
                    downloaded_count += 1
                    total_bytes += len(data)
                except Exception as exc:
                    row["retrieval_status"] = "blocked"
                    row["error"] = str(exc)
                    errors.append(f"{project_id}/{file_id}: {exc}")
            files.append(row)
            redacted_files.append({key: value for key, value in row.items() if key not in REDACTED_FILE_OMIT_KEYS})

        project_record = {
            "project_id": project_id,
            "project_title": str(project.get("project_title", "") or ""),
            "source_family": str(project.get("source_family", "") or ""),
            "jurisdiction": str(project.get("jurisdiction", "") or ""),
            "notice_id": str(project.get("notice_id", "") or ""),
            "source_page_url": str(project.get("source_page_url", "") or ""),
            "source_page_title": str(project.get("source_page_title", "") or ""),
            "retrieval_note": str(project.get("retrieval_note", "") or ""),
            "access_policy": policy,
            "files": files,
        }
        projects.append(project_record)
        redacted_projects.append({**project_record, "files": redacted_files})

    summary = {
        "project_count": len(projects),
        "file_count": sum(len(project["files"]) for project in projects),
        "downloaded_count": downloaded_count,
        "reused_private_file_count": reused_count,
        "blocked_count": len(errors),
        "total_bytes": total_bytes,
        "drawing_review_candidate_count": drawing_candidate_count,
        "downloaded_drawing_review_candidate_count": downloaded_drawing_candidate_count,
        "drawing_sheet_candidate_count": drawing_sheet_candidate_count,
        "model_optimization_candidate_count": model_candidate_count,
        "downloaded_model_optimization_candidate_count": downloaded_model_candidate_count,
        "model_optimization_asset_count": model_asset_count,
        "file_type_counts": dict(sorted(file_type_counts.items())),
        "downloaded_file_type_counts": dict(sorted(downloaded_file_type_counts.items())),
        "model_optimization_candidate_file_type_counts": dict(sorted(model_candidate_file_type_counts.items())),
        "raw_redistribution_allowed_count": 0,
        "release_surface_allowed_count": 0,
        "private_only": True,
    }
    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "generated_at": generated_at,
        "catalog": str(catalog_path),
        "private_root": str(private_root),
        "contract_pass": not errors,
        "reason_code": "PASS" if not errors else "ERR_PRIVATE_CORPUS_MATERIALIZATION_BLOCKED",
        "policy": policy,
        "summary": summary,
        "projects": projects,
        "errors": errors,
    }
    redacted = {
        "schema_version": REDACTED_SCHEMA_VERSION,
        "generated_at": generated_at,
        "contract_pass": not errors,
        "reason_code": manifest["reason_code"],
        "policy": policy,
        "summary": summary,
        "projects": redacted_projects,
    }
    return manifest, redacted


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--private-root", type=Path, default=DEFAULT_PRIVATE_ROOT)
    parser.add_argument("--out-manifest", type=Path, default=DEFAULT_OUT_MANIFEST)
    parser.add_argument("--out-redacted", type=Path, default=DEFAULT_OUT_REDACTED)
    parser.add_argument("--out-summary", type=Path, default=DEFAULT_OUT_SUMMARY)
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--timeout-sec", type=int, default=60)
    parser.add_argument("--max-bytes", type=int, default=64 * 1024 * 1024)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    manifest, redacted = build_manifest(
        catalog_path=args.catalog,
        private_root=args.private_root,
        download=bool(args.download),
        timeout_sec=int(args.timeout_sec),
        max_bytes=int(args.max_bytes),
    )
    _write_json(args.out_manifest, manifest)
    _write_json(args.out_redacted, redacted)
    _write_json(args.out_summary, {"summary": manifest["summary"], "artifacts": {
        "private_manifest": str(args.out_manifest),
        "redacted_manifest": str(args.out_redacted),
        "private_root": str(args.private_root),
    }})
    if args.json:
        print(json.dumps(redacted, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        summary = manifest["summary"]
        print(
            "Real drawing private corpus: "
            f"{manifest['reason_code']} | projects={summary['project_count']} | "
            f"files={summary['file_count']} | downloaded={summary['downloaded_count']} | "
            f"drawing_candidates={summary['drawing_review_candidate_count']} | "
            f"model_candidates={summary['model_optimization_candidate_count']}"
        )
    return 0 if manifest["contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
