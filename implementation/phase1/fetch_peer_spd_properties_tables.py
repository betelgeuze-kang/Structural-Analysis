#!/usr/bin/env python3
"""Fetch official PEER SPD RC column property tables."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
from urllib.request import Request, urlopen


RUN_ID = "phase1-fetch-peer-spd-properties-tables"
SCHEMA_VERSION = "1.0"

TABLES = {
    "rectangular": "https://nisee.berkeley.edu/spd/rectangular_properties.txt",
    "spiral": "https://nisee.berkeley.edu/spd/spiral_properties.txt",
}

REASONS = {
    "PASS": "Official PEER SPD property tables fetched.",
    "ERR_FETCH_FAILED": "One or more official PEER SPD property tables could not be fetched.",
}


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _candidate_urls(url: str) -> list[str]:
    out = [url]
    if url.startswith("https://"):
        out.append("http://" + url[len("https://"):])
    return out


def _fetch(url: str) -> tuple[bytes | None, str, str]:
    last_error = ""
    for candidate in _candidate_urls(url):
        for _attempt in range(3):
            try:
                request = Request(candidate, headers={"User-Agent": "Mozilla/5.0 Codex/PEER-SPD-Fetch"})
                with urlopen(request, timeout=10) as response:
                    return response.read(), candidate, ""
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                time.sleep(0.5)
    return None, "", last_error


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", default="implementation/phase1/open_data/pbd_hinge/peer_spd")
    parser.add_argument("--rectangular-url", default=TABLES["rectangular"])
    parser.add_argument("--spiral-url", default=TABLES["spiral"])
    parser.add_argument("--out-report", default="implementation/phase1/open_data/pbd_hinge/peer_spd_fetch_report.json")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    failures = 0
    for table_kind, url in {
        "rectangular": str(args.rectangular_url),
        "spiral": str(args.spiral_url),
    }.items():
        out_path = out_dir / f"{table_kind}_properties.txt"
        payload, fetched_url, error = _fetch(url)
        line_count = 0
        sha256 = ""
        cache_reused = False
        if payload is not None:
            out_path.write_bytes(payload)
            text = payload.decode("utf-8", "ignore")
            line_count = len(text.splitlines())
            sha256 = _sha256_bytes(payload)
        elif out_path.exists():
            payload = out_path.read_bytes()
            text = payload.decode("utf-8", "ignore")
            line_count = len(text.splitlines())
            sha256 = _sha256_bytes(payload)
            cache_reused = True
        else:
            failures += 1
        rows.append(
            {
                "table_kind": table_kind,
                "source_url": url,
                "fetched_url": fetched_url,
                "path": str(out_path),
                "line_count": int(line_count),
                "sha256": sha256,
                "contract_pass": bool(payload is not None),
                "fresh_fetch": bool(payload is not None and not cache_reused and bool(fetched_url)),
                "cache_reused": cache_reused,
                "error": error,
            }
        )

    reason_code = "PASS" if failures == 0 else "ERR_FETCH_FAILED"
    reason = REASONS[reason_code]

    report = {
        "schema_version": SCHEMA_VERSION,
        "run_id": RUN_ID,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contract_pass": bool(failures == 0),
        "reason_code": reason_code,
        "reason": reason,
        "inputs": {
            "out_dir": str(out_dir),
            "rectangular_url": str(args.rectangular_url),
            "spiral_url": str(args.spiral_url),
        },
        "summary": {
            "table_count": int(len(rows)),
            "table_pass_count": int(sum(1 for row in rows if bool(row.get("contract_pass", False)))),
            "table_fail_count": int(failures),
            "fresh_fetch_count": int(sum(1 for row in rows if bool(row.get("fresh_fetch", False)))),
            "cache_reuse_count": int(sum(1 for row in rows if bool(row.get("cache_reused", False)))),
            "line_count_total": int(sum(int(row["line_count"]) for row in rows)),
        },
        "rows": rows,
    }
    out_report = Path(args.out_report)
    out_report.parent.mkdir(parents=True, exist_ok=True)
    out_report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote PEER SPD fetch report: {args.out_report}")


if __name__ == "__main__":
    main()
