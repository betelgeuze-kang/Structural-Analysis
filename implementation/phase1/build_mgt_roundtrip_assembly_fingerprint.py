#!/usr/bin/env python3
"""Stable assembly fingerprint from parsed MGT roundtrip (for future global FEA hook)."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from design_optimization.io import load_json


SCHEMA_VERSION = "mgt-roundtrip-assembly-fingerprint.v1"


def _section_count(roundtrip: dict[str, Any], key: str) -> int:
    parser = roundtrip.get("parser") if isinstance(roundtrip.get("parser"), dict) else {}
    counts = parser.get("section_counts") if isinstance(parser.get("section_counts"), dict) else {}
    try:
        return int(counts.get(key) or 0)
    except (TypeError, ValueError):
        return 0


def build_mgt_roundtrip_assembly_fingerprint(
    *,
    roundtrip_json: Path,
    roundtrip_npz: Path | None = None,
) -> dict[str, Any]:
    roundtrip_npz = roundtrip_npz or roundtrip_json.with_suffix(".npz")
    if not roundtrip_json.is_file():
        return {
            "schema_version": SCHEMA_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": "missing_roundtrip",
            "fingerprint_sha256": "",
            "blockers": ["roundtrip_json_missing"],
        }

    roundtrip = load_json(roundtrip_json)
    source = roundtrip.get("source") if isinstance(roundtrip.get("source"), dict) else {}
    metrics = {
        "element_count": _section_count(roundtrip, "ELEMENT"),
        "node_count": _section_count(roundtrip, "NODE"),
        "section_count": _section_count(roundtrip, "SECTION"),
        "source_sha256": str(source.get("sha256") or ""),
        "npz_bytes": int(roundtrip_npz.stat().st_size) if roundtrip_npz.is_file() else 0,
    }
    canonical = json.dumps(metrics, sort_keys=True, separators=(",", ":"))
    fingerprint = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    blockers: list[str] = []
    if metrics["element_count"] < 1:
        blockers.append("no_elements")
    if not metrics["source_sha256"]:
        blockers.append("missing_source_sha256")

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready" if not blockers else "blocked",
        "fingerprint_sha256": fingerprint,
        "metrics": metrics,
        "roundtrip_json": str(roundtrip_json),
        "roundtrip_npz": str(roundtrip_npz),
        "solver_hook_status": "not_wired",
        "blockers": blockers,
        "note": "Fingerprint stabilizes MGT assembly identity for a future global FEA import path.",
    }
