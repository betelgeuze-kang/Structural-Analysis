#!/usr/bin/env python3
"""Ingest MIDAS Gen (or export-proxy) same-mesh structural result for comparison receipts."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from design_optimization.io import load_json


SCHEMA_VERSION = "midas-gen-same-mesh-result.v1"
REQUIRED_METRICS = ("drift_ratio_pct", "base_shear_kN", "top_displacement_m")


def ingest_midas_gen_same_mesh_result(
    *,
    result_json: Path,
    roundtrip_json: Path | None = None,
) -> dict[str, Any]:
    blockers: list[str] = []
    if not result_json.is_file():
        return {
            "schema_version": SCHEMA_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": "blocked",
            "blockers": ["result_json_missing"],
        }

    payload = load_json(result_json)
    if str(payload.get("schema_version") or "") != SCHEMA_VERSION:
        blockers.append("schema_version_mismatch")

    source = payload.get("source") if isinstance(payload.get("source"), dict) else {}
    metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
    for key in REQUIRED_METRICS:
        try:
            float(metrics.get(key))
        except (TypeError, ValueError):
            blockers.append(f"missing_metric_{key}")

    expected_sha = str(source.get("mgt_sha256") or "").strip().lower()
    roundtrip_sha = ""
    if roundtrip_json and roundtrip_json.is_file():
        roundtrip = load_json(roundtrip_json)
        roundtrip_source = roundtrip.get("source") if isinstance(roundtrip.get("source"), dict) else {}
        roundtrip_sha = str(roundtrip_source.get("sha256") or "").strip().lower()

    sha_match = bool(expected_sha and roundtrip_sha and expected_sha == roundtrip_sha)
    if roundtrip_json and roundtrip_json.is_file() and expected_sha and not sha_match:
        blockers.append("mgt_sha256_mismatch")

    kind = str(source.get("kind") or "unknown")
    live_midas = kind == "midas_gen_live_export"
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready" if not blockers else "blocked",
        "claim": (
            "Licensed-solver same-mesh metrics for delivery comparison."
            if live_midas
            else "Export-proxy same-mesh metrics (HF benchmark alignment); not live MIDAS Gen API on full mesh."
        ),
        "source": {
            **source,
            "kind": kind,
            "live_midas_gen_export": live_midas,
            "result_json": str(result_json),
            "roundtrip_json": str(roundtrip_json) if roundtrip_json else "",
        },
        "metrics": {key: float(metrics.get(key) or 0.0) for key in REQUIRED_METRICS},
        "integrity": {
            "mgt_sha256_expected": expected_sha,
            "mgt_sha256_roundtrip": roundtrip_sha,
            "sha256_match": sha_match,
        },
        "blockers": blockers,
    }
