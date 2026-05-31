#!/usr/bin/env python3
"""Validate midas-gen-same-mesh-result.v1 and emit structured checklist."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from design_optimization.io import load_json
from ingest_midas_gen_same_mesh_result import SCHEMA_VERSION, ingest_midas_gen_same_mesh_result


def validate_midas_gen_same_mesh_result(
    *,
    result_json: Path,
    roundtrip_json: Path | None = None,
) -> dict[str, Any]:
    ingest = ingest_midas_gen_same_mesh_result(result_json=result_json, roundtrip_json=roundtrip_json)
    payload = load_json(result_json) if result_json.is_file() else {}
    source = payload.get("source") if isinstance(payload.get("source"), dict) else {}
    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"check": name, "ok": ok, "detail": detail})

    add("schema_version", str(payload.get("schema_version") or "") == SCHEMA_VERSION)
    add("ingest_ready", ingest.get("status") == "ready", str(ingest.get("blockers") or []))
    add("mgt_sha256_match", bool((ingest.get("integrity") or {}).get("sha256_match")))
    kind = str(source.get("kind") or "")
    add(
        "kind_declared",
        kind in {"midas_gen_live_export", "midas_gen_export_proxy", "model_derived_estimate"},
        kind,
    )
    add("live_export_kind", kind == "midas_gen_live_export", "required for live MIDAS claim")
    metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
    for key in ("drift_ratio_pct", "base_shear_kN", "top_displacement_m"):
        try:
            value = float(metrics.get(key))
            add(f"metric_{key}_finite", value == value and value >= 0.0, str(value))
        except (TypeError, ValueError):
            add(f"metric_{key}_finite", False, "missing")

    failed = [row for row in checks if not row.get("ok")]
    required_failed = [row for row in failed if row["check"] not in {"live_export_kind"}]
    status = "pass" if not required_failed else "fail"
    return {
        "schema_version": "validate-midas-gen-same-mesh-result.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "result_json": str(result_json),
        "roundtrip_json": str(roundtrip_json) if roundtrip_json else "",
        "ingest": ingest,
        "checks": checks,
        "failed_checks": [row["check"] for row in failed],
        "live_export_ready": kind == "midas_gen_live_export" and status == "pass",
    }
