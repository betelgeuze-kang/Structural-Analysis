#!/usr/bin/env python3
"""JSON stdin/stdout wrapper for Rust 3-Bead SoA hook binary.

Supported actions (forwarded to Rust binary):
- step1_case
- step5_profile
- dlpack_bridge_probe
- av_operator
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from rust_track_lf_bridge import run_inplace_probe


ROOT = Path(__file__).resolve().parent
CRATE_DIR = ROOT / "rust_hip_md3bead_hook"
BIN_PATH = CRATE_DIR / "target" / "release" / "rust_hip_md3bead_hook"


def _latest_source_mtime() -> float:
    latest = 0.0
    for p in (CRATE_DIR / "src").rglob("*.rs"):
        latest = max(latest, p.stat().st_mtime)
    latest = max(latest, (CRATE_DIR / "Cargo.toml").stat().st_mtime)
    latest = max(latest, (CRATE_DIR / "Cargo.lock").stat().st_mtime)
    return latest


def _build_if_needed() -> None:
    if BIN_PATH.exists():
        if BIN_PATH.stat().st_mtime >= _latest_source_mtime():
            return
    subprocess.run(["cargo", "build", "--release"], cwd=CRATE_DIR, check=True)


def main() -> None:
    payload_text = sys.stdin.read()
    payload = json.loads(payload_text or "{}")
    action = str(payload.get("action", "")).strip()

    if action == "dlpack_bridge_probe":
        probe_length = int(payload.get("probe_length", 8192))
        probe_alpha = float(payload.get("probe_alpha", 1.125))
        probe_seed = int(payload.get("probe_seed", 23))
        out = run_inplace_probe(length=probe_length, alpha=probe_alpha, seed=probe_seed)
        challenge = payload.get("challenge")
        if challenge is not None:
            out["challenge_echo"] = challenge
        print(json.dumps(out))
        return

    _build_if_needed()
    proc = subprocess.run(
        [str(BIN_PATH)],
        input=payload_text,
        text=True,
        capture_output=True,
        check=True,
    )
    out = json.loads(proc.stdout)
    print(json.dumps(out))


if __name__ == "__main__":
    main()
