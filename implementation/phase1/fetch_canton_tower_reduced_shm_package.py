#!/usr/bin/env python3
"""Download the public Canton Tower reduced SHM benchmark package."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import ssl
from typing import Any
from urllib.parse import unquote, urlsplit
import urllib.request


DEFAULT_PROBE = Path("implementation/phase1/open_data/megastructure/canton_tower_reduced_shm.download_probe.json")
DEFAULT_OUT_DIR = Path("implementation/phase1/open_data/megastructure/canton_tower_reduced_shm")
DEFAULT_REPORT = Path("implementation/phase1/open_data/megastructure/canton_tower_reduced_shm_fetch_report.json")

MINIMUM_NAME_MAP = {
    "phase_i_measurement description.pdf": "Phase_I_measurement_description.pdf",
    "phase i_measurement description.pdf": "Phase_I_measurement_description.pdf",
    "phase i data_all.zip": "Phase_I_data_all.zip",
    "phase_i_data_all.zip": "Phase_I_data_all.zip",
    "phase_i_fe_model_description.pdf": "Phase_I_FE_model_description.pdf",
    "system_matrices.mat": "system_matrices.mat",
}


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize_target_name(url: str) -> str:
    name = unquote(Path(urlsplit(url).path).name)
    key = name.lower()
    if key in MINIMUM_NAME_MAP:
        return MINIMUM_NAME_MAP[key]
    return name.replace(" ", "_")


def _download(url: str, target: Path, *, insecure_ssl: bool) -> dict[str, Any]:
    context = ssl._create_unverified_context() if insecure_ssl else None
    req = urllib.request.Request(url, headers={"User-Agent": "phase1-canton-fetch/1.0"})
    with urllib.request.urlopen(req, timeout=180, context=context) as response:  # nosec B310
        data = response.read()
        headers = dict(response.headers.items())
        status = getattr(response, "status", None)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return {
        "url": url,
        "target": str(target),
        "status": status,
        "bytes": int(len(data)),
        "content_type": headers.get("Content-Type"),
        "content_length_header": headers.get("Content-Length"),
        "downloaded": True,
    }


def _selected_urls(probe_payload: dict[str, Any], *, include_hourly: bool, include_aux: bool) -> list[str]:
    rec = probe_payload.get("recommended_downloads") or {}
    out: list[str] = []
    for url in rec.get("minimum_viable_package", []) or []:
        if isinstance(url, str) and url not in out:
            out.append(url)
    if include_hourly:
        for url in rec.get("hourly_acceleration_archives", []) or []:
            if isinstance(url, str) and url not in out:
                out.append(url)
    if include_aux:
        for url in rec.get("auxiliary_environmental_channels", []) or []:
            if isinstance(url, str) and url not in out:
                out.append(url)
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe-json", default=str(DEFAULT_PROBE))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--report-out", default=str(DEFAULT_REPORT))
    parser.add_argument("--include-hourly", action="store_true")
    parser.add_argument("--include-aux", action="store_true")
    parser.add_argument("--default-ssl", action="store_true", help="Use default SSL verification instead of the unverified fallback.")
    args = parser.parse_args()

    probe_payload = _load_json(Path(args.probe_json))
    urls = _selected_urls(
        probe_payload,
        include_hourly=bool(args.include_hourly),
        include_aux=bool(args.include_aux),
    )
    out_dir = Path(args.out_dir)
    rows: list[dict[str, Any]] = []
    for url in urls:
        target = out_dir / _normalize_target_name(url)
        if target.exists():
            rows.append(
                {
                    "url": url,
                    "target": str(target),
                    "downloaded": False,
                    "bytes": int(target.stat().st_size),
                    "status": "existing",
                }
            )
            continue
        rows.append(_download(url, target, insecure_ssl=not bool(args.default_ssl)))

    payload = {
        "schema_version": "1.0",
        "run_id": "phase1-fetch-canton-tower-reduced-shm-package",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "probe_json": str(args.probe_json),
        "out_dir": str(out_dir),
        "include_hourly": bool(args.include_hourly),
        "include_aux": bool(args.include_aux),
        "download_rows": rows,
        "summary": {
            "requested_url_count": len(urls),
            "downloaded_count": sum(1 for row in rows if row.get("downloaded")),
            "existing_count": sum(1 for row in rows if row.get("status") == "existing"),
        },
        "contract_pass": bool(rows),
    }
    report_out = Path(args.report_out)
    report_out.parent.mkdir(parents=True, exist_ok=True)
    report_out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote Canton Tower package fetch report: {report_out}")


if __name__ == "__main__":
    main()
