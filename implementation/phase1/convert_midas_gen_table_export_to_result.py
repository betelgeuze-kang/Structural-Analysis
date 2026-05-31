#!/usr/bin/env python3
"""Convert one-row MIDAS Gen summary CSV into midas-gen-same-mesh-result.v1 JSON."""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from design_optimization.io import load_json
from ingest_midas_gen_same_mesh_result import SCHEMA_VERSION


METRIC_ALIASES = {
    "drift_ratio_pct": ("drift_ratio_pct", "max_drift_ratio_pct", "story_drift_pct", "drift_pct"),
    "base_shear_kN": ("base_shear_kN", "base_shear_kn", "base_shear"),
    "top_displacement_m": ("top_displacement_m", "top_disp_m", "displacement_top_m"),
}


def _read_metrics_row(csv_path: Path) -> dict[str, float]:
    with csv_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
    if not rows:
        raise ValueError("csv_empty")
    row = rows[0]
    normalized = {str(k).strip(): v for k, v in row.items() if k}
    metrics: dict[str, float] = {}
    for canonical, aliases in METRIC_ALIASES.items():
        for alias in aliases:
            if alias in normalized and str(normalized[alias]).strip():
                metrics[canonical] = float(normalized[alias])
                break
        if canonical not in metrics:
            raise ValueError(f"missing_column_for_{canonical}")
    return metrics


def convert_midas_gen_table_export_to_result(
    *,
    csv_path: Path,
    roundtrip_json: Path,
    output_json: Path,
    kind: str = "midas_gen_live_export",
    load_case: str = "",
    run_id: str = "",
    midas_model_name: str = "",
    note: str = "",
) -> dict[str, Any]:
    if kind not in {"midas_gen_live_export", "midas_gen_export_proxy"}:
        raise ValueError("invalid_kind")
    roundtrip = load_json(roundtrip_json)
    source = roundtrip.get("source") if isinstance(roundtrip.get("source"), dict) else {}
    metrics = _read_metrics_row(csv_path)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "kind": kind,
            "mgt_sha256": str(source.get("sha256") or ""),
            "roundtrip_json": str(roundtrip_json),
            "load_case": load_case,
            "run_id": run_id,
            "midas_model_name": midas_model_name or roundtrip_json.stem,
            "note": note or f"Converted from CSV {csv_path.name}",
            "source_csv": str(csv_path),
        },
        "metrics": metrics,
        "blockers": [],
    }
    output_json.parent.mkdir(parents=True, exist_ok=True)
    import json

    output_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload
