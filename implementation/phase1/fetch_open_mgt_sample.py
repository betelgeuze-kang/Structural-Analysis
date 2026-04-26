#!/usr/bin/env python3
"""Download a public MIDAS .mgt sample with provenance manifest."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import urllib.request


DEFAULT_URL = (
    "https://raw.githubusercontent.com/chen39137112/MidasMgtGenerator/"
    "f704e6300795f35d7d7d2c05bce2b9b6a15ccbb1/33.mgt"
)
DEFAULT_SHA256 = "269419de4b0ae9aacbfd2aeed05766d2c8bb065f7b64e81fee8c295129bbf2cc"


def _sha256_bytes(data: bytes) -> str:
    h = hashlib.sha256()
    h.update(data)
    return h.hexdigest()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--url", default=DEFAULT_URL)
    p.add_argument("--out", default="implementation/phase1/open_data/midas/midas_generator_33.mgt")
    p.add_argument("--manifest-out", default="implementation/phase1/open_data/midas/midas_generator_33.source_manifest.json")
    p.add_argument("--expected-sha256", default=DEFAULT_SHA256)
    args = p.parse_args()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(str(args.url), headers={"User-Agent": "phase1-mgt-fetcher/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = resp.read()
        status = int(getattr(resp, "status", 200))

    digest = _sha256_bytes(data)
    if str(args.expected_sha256).strip() and digest.lower() != str(args.expected_sha256).strip().lower():
        raise SystemExit(f"sha256 mismatch: expected={args.expected_sha256} got={digest}")

    out.write_bytes(data)
    manifest = {
        "schema_version": "1.0",
        "run_id": "phase1-fetch-open-mgt-sample",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "url": str(args.url),
        "http_status": status,
        "out": str(out),
        "size_bytes": int(len(data)),
        "sha256": digest,
        "contract_pass": True,
        "reason_code": "PASS",
    }
    manifest_out = Path(args.manifest_out)
    manifest_out.parent.mkdir(parents=True, exist_ok=True)
    manifest_out.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Downloaded MGT sample: {out}")
    print(f"Wrote source manifest: {manifest_out}")


if __name__ == "__main__":
    main()
