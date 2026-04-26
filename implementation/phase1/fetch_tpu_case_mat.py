#!/usr/bin/env python3
"""Fetch a TPU wind-tunnel case MAT file with provenance/reporting."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any

import requests


RUN_ID = "phase1-fetch-tpu-case-mat"
SCHEMA_VERSION = "1.0"
USER_AGENT = "phase1-tpu-fetcher/1.0"

REASONS = {
    "PASS": "TPU case page resolved and MAT file fetched successfully.",
    "ERR_INPUT_MODE": "provide one of --case-id, --case-page-url, or --case-page-html.",
    "ERR_CASE_PAGE_FETCH": "failed to fetch or parse the TPU case page.",
    "ERR_MAT_LINK_MISSING": "no MAT link could be resolved from the TPU case page.",
    "ERR_MAT_FETCH": "failed to fetch the TPU MAT file.",
    "ERR_MAT_EMPTY": "resolved TPU MAT file is empty.",
}


def _load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _sha256_bytes(raw: bytes) -> str:
    h = hashlib.sha256()
    h.update(raw)
    return h.hexdigest()


def _fetch_text(url: str) -> str:
    response = requests.get(url, timeout=60, headers={"User-Agent": USER_AGENT})
    response.raise_for_status()
    return response.text


def _fetch_bytes(source: str) -> tuple[bytes, str]:
    local_path = Path(source)
    if local_path.exists():
        return local_path.read_bytes(), str(local_path.resolve())
    response = requests.get(source, timeout=120, headers={"User-Agent": USER_AGENT})
    response.raise_for_status()
    return response.content, str(response.url)


def _resolve_case_page_url(*, case_id: str, case_page_url: str) -> str:
    if str(case_page_url).strip():
        return str(case_page_url).strip()
    return f"https://db.wind.arch.t-kougei.ac.jp/aerodynamic/case-redirect/?case={case_id}"


def _extract_title(html: str) -> str:
    match = re.search(r"<title>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    return re.sub(r"\s+", " ", match.group(1)).strip()


def _extract_mat_links(html: str) -> list[str]:
    return list(
        dict.fromkeys(
            re.findall(
                r"https://minio\.wind\.arch\.t-kougei\.ac\.jp/web/media/case/[^\s\"'<>]+?\.mat",
                html,
                flags=re.IGNORECASE,
            )
        )
    )


def _default_paths(case_label: str) -> tuple[Path, Path, Path]:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", case_label).strip("_") or "tpu_case"
    out_dir = Path("implementation/phase1/open_data/wind/tpu")
    mat = out_dir / f"{safe}.mat"
    manifest = out_dir / f"{safe}.source_manifest.json"
    report = out_dir / f"{safe}.fetch_report.json"
    return mat, manifest, report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-id", default="")
    parser.add_argument("--case-page-url", default="")
    parser.add_argument("--case-page-html", default="")
    parser.add_argument("--mat-url", default="")
    parser.add_argument("--mat-index", type=int, default=0)
    parser.add_argument("--out-mat", default="")
    parser.add_argument("--source-manifest-out", default="")
    parser.add_argument("--out-report", default="")
    args = parser.parse_args()

    case_id = str(args.case_id).strip()
    case_page_url = str(args.case_page_url).strip()
    case_page_html = str(args.case_page_html).strip()
    explicit_mat_url = str(args.mat_url).strip()

    reason_code = "PASS"
    reason = REASONS[reason_code]
    html = ""
    resolved_case_page = ""
    title = ""
    mat_links: list[str] = []
    resolved_mat_url = ""
    mat_bytes = b""
    resolved_mat_source = ""

    if not any([case_id, case_page_url, case_page_html]):
        reason_code = "ERR_INPUT_MODE"
        reason = REASONS[reason_code]
    else:
        try:
            if case_page_html:
                html = _load_text(Path(case_page_html))
                resolved_case_page = str(Path(case_page_html).resolve())
            else:
                resolved_case_page = _resolve_case_page_url(case_id=case_id, case_page_url=case_page_url)
                html = _fetch_text(resolved_case_page)
            title = _extract_title(html)
            mat_links = _extract_mat_links(html)
        except Exception:
            reason_code = "ERR_CASE_PAGE_FETCH"
            reason = REASONS[reason_code]

    if reason_code == "PASS":
        if explicit_mat_url:
            resolved_mat_url = explicit_mat_url
        elif mat_links and int(args.mat_index) < len(mat_links):
            resolved_mat_url = mat_links[int(args.mat_index)]
        else:
            reason_code = "ERR_MAT_LINK_MISSING"
            reason = REASONS[reason_code]

    if reason_code == "PASS":
        try:
            mat_bytes, resolved_mat_source = _fetch_bytes(resolved_mat_url)
        except Exception:
            reason_code = "ERR_MAT_FETCH"
            reason = REASONS[reason_code]
        else:
            if len(mat_bytes) <= 0:
                reason_code = "ERR_MAT_EMPTY"
                reason = REASONS[reason_code]

    case_label = case_id or title or Path(case_page_html).stem or "tpu_case"
    default_mat, default_manifest, default_report = _default_paths(case_label)
    out_mat = Path(str(args.out_mat).strip()) if str(args.out_mat).strip() else default_mat
    source_manifest_out = (
        Path(str(args.source_manifest_out).strip()) if str(args.source_manifest_out).strip() else default_manifest
    )
    out_report = Path(str(args.out_report).strip()) if str(args.out_report).strip() else default_report

    if reason_code == "PASS":
        out_mat.parent.mkdir(parents=True, exist_ok=True)
        out_mat.write_bytes(mat_bytes)

    manifest_payload = {
        "schema_version": SCHEMA_VERSION,
        "run_id": RUN_ID,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_name": title or case_label,
        "source_url": resolved_case_page,
        "case_id": case_id,
        "mat_url": resolved_mat_url,
        "mat_source_resolved": resolved_mat_source,
        "real_source": True,
        "source_origin_class": "official_external_benchmark",
        "data_path": str(out_mat),
        "sha256": _sha256_bytes(mat_bytes) if mat_bytes else "",
        "size_bytes": int(len(mat_bytes)),
        "contract_pass": bool(reason_code == "PASS"),
        "reason_code": reason_code,
        "reason": reason,
    }
    report_payload = {
        "schema_version": SCHEMA_VERSION,
        "run_id": RUN_ID,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contract_pass": bool(reason_code == "PASS"),
        "reason_code": reason_code,
        "reason": reason,
        "inputs": {
            "case_id": case_id,
            "case_page_url": case_page_url,
            "case_page_html": case_page_html,
            "mat_url": explicit_mat_url,
            "mat_index": int(args.mat_index),
        },
        "summary": {
            "case_title": title,
            "resolved_case_page": resolved_case_page,
            "mat_link_count": int(len(mat_links)),
            "candidate_mat_urls_head": mat_links[: min(len(mat_links), 5)],
            "resolved_mat_url": resolved_mat_url,
            "size_bytes": int(len(mat_bytes)),
        },
        "artifacts": {
            "out_mat": str(out_mat) if out_mat.exists() else "",
            "source_manifest_out": str(source_manifest_out),
        },
    }
    _write_json(source_manifest_out, manifest_payload)
    _write_json(out_report, report_payload)
    print(f"Wrote TPU fetch manifest: {source_manifest_out}")
    print(f"Wrote TPU fetch report: {out_report}")
    if reason_code != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
