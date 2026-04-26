#!/usr/bin/env python3
"""Fetch directly accessible public E-Defense / PEER blind-prediction files."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.parse import unquote, urlsplit
import urllib.request


DEFAULT_PROBE = Path("implementation/phase1/open_data/pbd_hinge/edefense_peer_blind_prediction_seed_01.download_probe.json")
DEFAULT_OUT_DIR = Path("implementation/phase1/open_data/pbd_hinge/edefense_peer_blind_prediction_seed_01")
DEFAULT_REPORT = Path("implementation/phase1/open_data/pbd_hinge/edefense_peer_blind_prediction_seed_01.fetch_report.json")


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _target_name(url: str) -> str:
    name = unquote(Path(urlsplit(url).path).name)
    return (name or "downloaded_asset").replace(" ", "_")


def _slug(value: str) -> str:
    token = "".join(ch.lower() if ch.isalnum() else "_" for ch in str(value or "").strip())
    return token.strip("_") or "asset"


def _probe_rows(probe: dict) -> list[dict]:
    rows: list[dict] = []
    seen_urls: set[str] = set()

    direct_rows = probe.get("direct_download_rows")
    if isinstance(direct_rows, list):
        for row in direct_rows:
            if not isinstance(row, dict):
                continue
            url = str(row.get("url", "") or "").strip()
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            rows.append(
                {
                    "url": url,
                    "artifact_class": str(row.get("artifact_class", "") or ""),
                    "anchor_text": str(row.get("anchor_text", "") or ""),
                    "page_sources": [
                        str(item)
                        for item in (row.get("page_sources") or [])
                        if str(item or "").strip()
                    ],
                    "probe_reachable": bool(row.get("reachable", False)),
                    "probe_content_type": str(row.get("content_type", "") or ""),
                    "probe_content_length": int(row.get("content_length", 0) or 0),
                    "probe_last_modified": str(row.get("last_modified", "") or ""),
                }
            )

    for url in (probe.get("direct_downloads") or []):
        if not isinstance(url, str):
            continue
        token = url.strip()
        if not token or token in seen_urls:
            continue
        seen_urls.add(token)
        rows.append(
            {
                "url": token,
                "artifact_class": "",
                "anchor_text": "",
                "page_sources": [],
                "probe_reachable": False,
                "probe_content_type": "",
                "probe_content_length": 0,
                "probe_last_modified": "",
            }
        )
    return rows


def _assign_target_names(rows: list[dict]) -> tuple[list[dict], int]:
    used: dict[str, str] = {}
    collision_count = 0
    planned: list[dict] = []
    for row in rows:
        url = str(row.get("url", "") or "")
        base_name = _target_name(url)
        candidate = base_name
        if candidate in used and used[candidate] != url:
            collision_count += 1
            stem = Path(base_name).stem or "downloaded_asset"
            suffix = Path(base_name).suffix
            artifact_class = _slug(str(row.get("artifact_class", "") or "dup"))
            digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:8]
            candidate = f"{stem}.{artifact_class}.{digest}{suffix}"
        used[candidate] = url
        planned.append({**row, "target_name": candidate})
    return planned, collision_count


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe-json", default=str(DEFAULT_PROBE))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--report-out", default=str(DEFAULT_REPORT))
    args = parser.parse_args()

    probe = _load_json(Path(args.probe_json))
    probe_rows, collision_count = _assign_target_names(_probe_rows(probe))
    out_dir = Path(args.out_dir)
    rows = []
    for probe_row in probe_rows:
        url = str(probe_row.get("url", "") or "")
        target_name = str(probe_row.get("target_name", "") or _target_name(url))
        target = out_dir / target_name
        if target.exists():
            rows.append(
                {
                    **probe_row,
                    "target": str(target),
                    "target_name": target_name,
                    "fetch_state": "existing",
                    "status": "existing",
                    "bytes": int(target.stat().st_size),
                    "content_type": str(probe_row.get("probe_content_type", "") or ""),
                    "downloaded": False,
                }
            )
            continue
        req = urllib.request.Request(url, headers={"User-Agent": "phase1-edefense-fetch/1.0"})
        with urllib.request.urlopen(req, timeout=60) as response:  # nosec B310
            data = response.read()
            headers = dict(response.headers.items())
            status = getattr(response, "status", None)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        rows.append(
            {
                **probe_row,
                "url": url,
                "target": str(target),
                "target_name": target_name,
                "fetch_state": "downloaded",
                "status": status,
                "bytes": int(len(data)),
                "content_type": headers.get("Content-Type"),
                "downloaded": True,
            }
        )

    payload = {
        "schema_version": "1.0",
        "run_id": "phase1-fetch-edefense-peer-blind-prediction-seed-package",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "probe_json": str(args.probe_json),
        "out_dir": str(out_dir),
        "download_rows": rows,
        "summary": {
            "requested_url_count": len(probe_rows),
            "downloaded_count": sum(1 for row in rows if row.get("downloaded")),
            "existing_count": sum(1 for row in rows if row.get("status") == "existing"),
            "artifact_class_counts": {
                artifact_class: sum(1 for row in rows if str(row.get("artifact_class", "") or "") == artifact_class)
                for artifact_class in sorted(
                    {
                        str(row.get("artifact_class", "") or "")
                        for row in rows
                        if str(row.get("artifact_class", "") or "")
                    }
                )
            },
            "measured_response_dataset_count": sum(
                1 for row in rows if str(row.get("artifact_class", "") or "") == "measured_response_dataset"
            ),
            "measured_response_support_doc_count": sum(
                1 for row in rows if str(row.get("artifact_class", "") or "") == "measured_response_support_doc"
            ),
            "stable_target_collision_count": int(collision_count),
        },
        "contract_pass": bool(rows),
    }
    report_out = Path(args.report_out)
    report_out.parent.mkdir(parents=True, exist_ok=True)
    report_out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote E-Defense / PEER fetch report: {report_out}")


if __name__ == "__main__":
    main()
