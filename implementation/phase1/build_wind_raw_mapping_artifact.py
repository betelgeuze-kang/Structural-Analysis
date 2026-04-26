#!/usr/bin/env python3
"""Build a traceable raw wind-tunnel to MIDAS pressure mapping artifact."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any


RUN_ID = "phase3-wind-raw-mapping-artifact"
SCHEMA_VERSION = "1.0"

REASONS = {
    "PASS": "Raw wind series is traceably bridged to MIDAS pressure-loaded elements, nodes, and floor proxies.",
    "ERR_RAW_WIND_MISSING": "Raw wind data is missing or unreadable.",
    "ERR_RAW_MANIFEST_INVALID": "Raw wind manifest is missing or failed verification.",
    "ERR_MIDAS_JSON_INVALID": "MIDAS roundtrip JSON is missing or invalid.",
    "ERR_PRESSURE_ROWS_MISSING": "MIDAS roundtrip JSON does not expose pressure-loaded elements.",
    "ERR_MAPPING_INCOMPLETE": "Pressure rows exist but node/floor backreference could not be completed.",
}


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _safe_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        token = value.strip().lower()
        if token in {"1", "true", "yes", "y", "on", "pass"}:
            return True
        if token in {"0", "false", "no", "n", "off", "fail"}:
            return False
    return bool(default)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        try:
            return int(float(value))
        except Exception:
            return int(default)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _verify_manifest(manifest: dict[str, Any] | None, raw_wind: Path) -> tuple[bool, str]:
    if manifest is None:
        return False, "manifest file is missing or invalid json"
    if not _safe_bool(manifest.get("real_source"), default=False):
        return False, "manifest.real_source must be true"
    data_path = Path(str(manifest.get("data_path", "")).strip())
    if not data_path.exists():
        return False, "manifest data_path missing"
    if raw_wind.exists() and data_path.resolve() != raw_wind.resolve():
        return False, "manifest data_path does not match --raw-wind"
    if not str(manifest.get("source_url", "")).strip():
        return False, "manifest source_url missing"
    sha = str(manifest.get("sha256", "")).strip().lower()
    if len(sha) != 64:
        return False, "manifest sha256 invalid"
    if raw_wind.exists() and _sha256_file(raw_wind) != sha:
        return False, "manifest sha256 mismatch"
    return True, ""


def _parse_raw_wind(path: Path) -> tuple[int, int]:
    if not path.exists():
        return 0, 0
    try:
        with path.open("r", encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
    except Exception:
        return 0, 0
    if not rows:
        return 0, 0
    cols = [str(col) for col in rows[0].keys()]
    signal_cols = [
        col
        for col in cols
        if any(token in col.lower() for token in ("pressure", "cp", "force", "load"))
        and col.lower() not in {"time", "time_s"}
    ]
    if not signal_cols:
        return len(rows), len(rows)
    pressure_rows = 0
    for row in rows:
        if any(str(row.get(col, "")).strip() for col in signal_cols):
            pressure_rows += 1
    return len(rows), int(pressure_rows)


def _resolve_midas_json_path(path_str: str) -> Path:
    requested = Path(path_str)
    if requested.exists():
        return requested
    fallbacks = [
        Path("implementation/phase1/open_data/midas/midas_model.json"),
        Path("implementation/phase1/midas_model.json"),
    ]
    for candidate in fallbacks:
        if candidate.exists():
            return candidate
    return requested


def _pressure_mapping(roundtrip_json: dict[str, Any]) -> dict[str, Any]:
    model = roundtrip_json.get("model") if isinstance(roundtrip_json.get("model"), dict) else {}
    loads = model.get("loads") if isinstance(model.get("loads"), dict) else {}
    pressure_rows = loads.get("pressure_loads") if isinstance(loads.get("pressure_loads"), list) else []
    elements_raw = model.get("elements") if isinstance(model.get("elements"), list) else []
    nodes_raw = model.get("nodes") if isinstance(model.get("nodes"), list) else []

    elements: dict[int, list[int]] = {}
    for row in elements_raw:
        if not isinstance(row, dict):
            continue
        element_id = _safe_int(row.get("id"), default=0)
        node_ids = row.get("node_ids")
        if element_id <= 0 or not isinstance(node_ids, list):
            continue
        elements[element_id] = [_safe_int(node_id, default=0) for node_id in node_ids if _safe_int(node_id, default=0) > 0]

    node_z: dict[int, float] = {}
    for row in nodes_raw:
        if not isinstance(row, dict):
            continue
        node_id = _safe_int(row.get("id"), default=0)
        if node_id <= 0:
            continue
        node_z[node_id] = _safe_float(row.get("z"), default=0.0)

    average_z_by_pressure_row: list[float] = []
    node_ids_by_pressure_row: list[list[int]] = []
    pressure_case_counts: dict[str, int] = {}
    pressure_loaded_elements: set[int] = set()
    pressure_loaded_nodes: set[int] = set()
    floor_keys: set[float] = set()

    for row in pressure_rows:
        if not isinstance(row, dict):
            continue
        element_ids = row.get("element_ids") if isinstance(row.get("element_ids"), list) else []
        resolved_nodes: list[int] = []
        for raw_element_id in element_ids:
            element_id = _safe_int(raw_element_id, default=0)
            if element_id <= 0:
                continue
            pressure_loaded_elements.add(element_id)
            resolved_nodes.extend(elements.get(element_id, []))
        unique_nodes = sorted({node_id for node_id in resolved_nodes if node_id in node_z})
        node_ids_by_pressure_row.append(unique_nodes)
        pressure_loaded_nodes.update(unique_nodes)
        if unique_nodes:
            avg_z = round(sum(node_z[node_id] for node_id in unique_nodes) / float(len(unique_nodes)), 6)
            floor_keys.add(avg_z)
        else:
            avg_z = 0.0
        average_z_by_pressure_row.append(avg_z)
        load_case = str(row.get("load_case", "")).strip() or "UNKNOWN"
        pressure_case_counts[load_case] = int(pressure_case_counts.get(load_case, 0)) + 1

    floor_lookup = {z_value: index + 1 for index, z_value in enumerate(sorted(floor_keys))}
    mapping_rows_head: list[dict[str, Any]] = []
    for index, row in enumerate(pressure_rows[:64]):
        if not isinstance(row, dict):
            continue
        nodes = node_ids_by_pressure_row[index]
        avg_z = average_z_by_pressure_row[index]
        element_ids = row.get("element_ids") if isinstance(row.get("element_ids"), list) else []
        mapping_rows_head.append(
            {
                "pressure_row_index": int(index),
                "load_case": str(row.get("load_case", "")).strip(),
                "element_id": _safe_int(element_ids[0], default=0) if element_ids else 0,
                "target_node_id": int(nodes[0]) if nodes else 0,
                "floor_id": int(floor_lookup.get(avg_z, 0)),
                "average_z": float(avg_z),
                "element_type": str(row.get("element_type", "")).strip(),
                "load_type": str(row.get("load_type", "")).strip(),
            }
        )

    return {
        "mapping_row_count": int(len(pressure_rows)),
        "mapped_node_row_count": int(len(pressure_loaded_nodes)),
        "mapped_floor_row_count": int(len(floor_lookup)),
        "pressure_loaded_element_count": int(len(pressure_loaded_elements)),
        "pressure_case_counts": {str(key): int(value) for key, value in sorted(pressure_case_counts.items())},
        "mapping_rows_head": mapping_rows_head,
        "element_to_node_backreference_present": bool(len(pressure_loaded_nodes) > 0),
        "floor_proxy_present": bool(len(floor_lookup) > 0),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-wind", default="implementation/phase1/open_data/wind/across_wind_10h_dt1s.csv")
    parser.add_argument("--raw-wind-manifest", default="implementation/phase1/open_data/wind/across_wind_10h_dt1s.manifest.json")
    parser.add_argument("--midas-json", default="implementation/phase1/midas_model.json")
    parser.add_argument("--midas-conversion", default="implementation/phase1/midas_mgt_conversion_report.json")
    parser.add_argument("--wind-gate-report", default="")
    parser.add_argument("--out", default="implementation/phase1/wind_tunnel_raw_mapping.json")
    args = parser.parse_args()

    raw_wind_path = Path(args.raw_wind)
    manifest_path = Path(args.raw_wind_manifest)
    midas_json_path = _resolve_midas_json_path(str(args.midas_json))
    midas_conversion_path = Path(args.midas_conversion)
    wind_gate_path = Path(args.wind_gate_report) if str(args.wind_gate_report).strip() else None

    raw_row_count, raw_pressure_row_count = _parse_raw_wind(raw_wind_path)
    manifest = _load_json(manifest_path)
    manifest_ok, manifest_reason = _verify_manifest(manifest, raw_wind_path)
    midas_json = _load_json(midas_json_path)
    midas_conversion = _load_json(midas_conversion_path)
    wind_gate = _load_json(wind_gate_path) if wind_gate_path is not None and wind_gate_path.exists() else None

    mapping = _pressure_mapping(midas_json or {}) if isinstance(midas_json, dict) else {
        "mapping_row_count": 0,
        "mapped_node_row_count": 0,
        "mapped_floor_row_count": 0,
        "pressure_loaded_element_count": 0,
        "pressure_case_counts": {},
        "mapping_rows_head": [],
        "element_to_node_backreference_present": False,
        "floor_proxy_present": False,
    }

    conversion_metrics = midas_conversion.get("metrics", {}) if isinstance(midas_conversion, dict) and isinstance(midas_conversion.get("metrics"), dict) else {}
    bound_pressure_row_count = _safe_int(conversion_metrics.get("bound_pressure_row_count"), default=0)
    conversion_pressure_match = bool(bound_pressure_row_count <= 0 or bound_pressure_row_count == mapping["mapping_row_count"])

    if raw_row_count <= 0:
        contract_pass = False
        reason_code = "ERR_RAW_WIND_MISSING"
    elif not manifest_ok:
        contract_pass = False
        reason_code = "ERR_RAW_MANIFEST_INVALID"
    elif not isinstance(midas_json, dict):
        contract_pass = False
        reason_code = "ERR_MIDAS_JSON_INVALID"
    elif mapping["mapping_row_count"] <= 0:
        contract_pass = False
        reason_code = "ERR_PRESSURE_ROWS_MISSING"
    elif not (mapping["element_to_node_backreference_present"] and mapping["floor_proxy_present"] and conversion_pressure_match):
        contract_pass = False
        reason_code = "ERR_MAPPING_INCOMPLETE"
    else:
        contract_pass = True
        reason_code = "PASS"

    reason = REASONS[reason_code]
    if reason_code == "ERR_RAW_MANIFEST_INVALID" and manifest_reason:
        reason = f"{REASONS[reason_code]} ({manifest_reason})"
    elif reason_code == "ERR_MAPPING_INCOMPLETE" and not conversion_pressure_match:
        reason = f"{REASONS[reason_code]} (pressure row mismatch vs conversion report: {bound_pressure_row_count} != {mapping['mapping_row_count']})"

    payload = {
        "schema_version": SCHEMA_VERSION,
        "run_id": RUN_ID,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "raw_wind": str(raw_wind_path),
            "raw_wind_manifest": str(manifest_path),
            "wind_gate_report": str(wind_gate_path) if wind_gate_path is not None else "",
            "midas_roundtrip_json": str(midas_json_path),
            "midas_conversion_report": str(midas_conversion_path),
        },
        "summary": {
            "mapping_mode": "raw_hffb_node_pressure_mapping",
            "mapping_row_count": int(mapping["mapping_row_count"]),
            "mapped_node_row_count": int(mapping["mapped_node_row_count"]),
            "mapped_floor_row_count": int(mapping["mapped_floor_row_count"]),
            "pressure_loaded_element_count": int(mapping["pressure_loaded_element_count"]),
            "raw_row_count": int(raw_row_count),
            "raw_pressure_row_count": int(raw_pressure_row_count),
            "pressure_case_counts": dict(mapping["pressure_case_counts"]),
            "wind_gate_contract_pass": bool(_safe_bool((wind_gate or {}).get("contract_pass"), default=False)),
            "conversion_pressure_row_count": int(bound_pressure_row_count),
        },
        "checks": {
            "raw_manifest_verified": bool(manifest_ok),
            "pressure_rows_present": bool(mapping["mapping_row_count"] > 0),
            "element_to_node_backreference_present": bool(mapping["element_to_node_backreference_present"]),
            "floor_proxy_present": bool(mapping["floor_proxy_present"]),
            "pressure_count_matches_conversion_report": bool(conversion_pressure_match),
        },
        "artifacts": {
            "mapping_rows_head": list(mapping["mapping_rows_head"]),
        },
        "contract_pass": bool(contract_pass),
        "reason_code": reason_code,
        "reason": reason,
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote wind raw mapping artifact: {out}")


if __name__ == "__main__":
    main()
