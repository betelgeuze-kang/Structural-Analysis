#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PRODUCTIZATION = REPO_ROOT / "implementation/phase1/release_evidence/productization"


def test_finalize_rh_closure_roundtrip() -> None:
    bundle_path = PRODUCTIZATION / "delivery_evidence_bundle.json"
    if not bundle_path.is_file():
        return
    rh_path = PRODUCTIZATION / "residual_holdout_closure_updates.json"
    packet_dir = PRODUCTIZATION / "rh_signed_closure_packets_test"
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/finalize_rh_signed_closure.py"),
            "--bundle-json",
            str(bundle_path),
            "--rh-json",
            str(rh_path),
            "--packet-dir",
            str(packet_dir),
            "--output-json",
            str(packet_dir / "rh_updates_test.json"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    payload = json.loads((packet_dir / "rh_updates_test.json").read_text(encoding="utf-8"))
    assert payload.get("rh_closure_status") == "closed"
