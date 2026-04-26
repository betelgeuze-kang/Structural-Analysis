#!/usr/bin/env python3
"""Generate readiness report for raw wind-tunnel HFFB mapping."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any


RUN_ID = "phase3-wind-tunnel-raw-mapping-readiness"
SCHEMA_VERSION = "1.0"

REASONS = {
    "PASS": "Raw wind-tunnel HFFB mapping is ready for traceable MIDAS binding.",
    "ERR_RAW_WIND_MISSING": "Raw wind data is missing or unreadable.",
    "ERR_RAW_MANIFEST_INVALID": "Raw wind manifest is missing or failed verification.",
    "ERR_MAPPING_MISSING": "Wind raw mapping artifact is missing.",
    "ERR_MAPPING_EMPTY": "Wind raw mapping artifact exists but contains no mapping rows.",
    "ERR_MIDAS_TRACEABILITY": "MIDAS conversion traceability is missing or not green enough.",
    "ERR_UNHANDLED": "Unhandled error while building wind raw mapping readiness report.",
}


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        try:
            return int(float(value))
        except Exception:
            return int(default)


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


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _status(pass_flag: bool, exists: bool = True) -> str:
    if pass_flag:
        return "pass"
    return "fail" if exists else "open"


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
    if raw_wind.exists():
        actual_sha = _sha256_file(raw_wind)
        if sha != actual_sha:
            return False, "manifest sha256 mismatch"
    return True, ""


def _read_csv_row_count(path: Path) -> tuple[int, int]:
    if not path.exists():
        return 0, 0
    try:
        with path.open("r", encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        if not rows:
            return 0, 0
        cols = [str(c) for c in (rows[0].keys() if isinstance(rows[0], dict) else [])]
        pressure_cols = [
            c for c in cols
            if any(token in c.lower() for token in ("pressure", "cp", "force", "load"))
            and c.lower() not in {"time", "time_s"}
        ]
        if not pressure_cols:
            return len(rows), len(rows)
        pressure_rows = 0
        for row in rows:
            has_pressure = False
            for c in pressure_cols:
                v = str(row.get(c, "")).strip()
                if v:
                    has_pressure = True
                    break
            if has_pressure:
                pressure_rows += 1
        return len(rows), int(pressure_rows)
    except Exception:
        return 0, 0


def _parse_raw_wind(path: Path) -> tuple[int, int]:
    if not path.exists():
        return 0, 0
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return _read_csv_row_count(path)
    if suffix == ".json":
        payload = _load_json(path)
        if not isinstance(payload, dict):
            return 0, 0
        rows = payload.get("rows")
        if isinstance(rows, list):
            n = len(rows)
            return n, n
        samples = payload.get("samples")
        if isinstance(samples, list):
            n = len(samples)
            return n, n
    return 0, 0


def _pick_first_int(obj: dict[str, Any], keys: list[str], default: int = 0) -> int:
    for k in keys:
        if k in obj:
            return _safe_int(obj.get(k), default=default)
    return int(default)


def _parse_mapping(path: Path) -> dict[str, Any]:
    out = {
        "mapping_exists": bool(path.exists()),
        "mapping_mode": "missing" if not path.exists() else "unknown",
        "mapping_row_count": 0,
        "mapped_node_row_count": 0,
        "mapped_floor_row_count": 0,
        "mapping_contract_pass": False,
        "mapping_reason": "",
    }
    if not path.exists():
        return out

    suffix = path.suffix.lower()
    if suffix == ".csv":
        try:
            with path.open("r", encoding="utf-8", newline="") as f:
                rows = list(csv.DictReader(f))
            node_cols = {"node_id", "target_node_id", "midas_node_id"}
            floor_cols = {"floor_id", "story_id", "level_id", "target_floor_id"}
            mapped_node = 0
            mapped_floor = 0
            for row in rows:
                if any(str(row.get(c, "")).strip() for c in node_cols):
                    mapped_node += 1
                if any(str(row.get(c, "")).strip() for c in floor_cols):
                    mapped_floor += 1
            out["mapping_mode"] = "csv_mapping_rows"
            out["mapping_row_count"] = int(len(rows))
            out["mapped_node_row_count"] = int(mapped_node)
            out["mapped_floor_row_count"] = int(mapped_floor)
            out["mapping_contract_pass"] = bool(len(rows) > 0)
            out["mapping_reason"] = "csv mapping rows parsed"
            return out
        except Exception:
            out["mapping_reason"] = "csv mapping parse failed"
            return out

    payload = _load_json(path)
    if not isinstance(payload, dict):
        out["mapping_reason"] = "json mapping parse failed"
        return out

    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}

    out["mapping_mode"] = str(
        summary.get("mapping_mode")
        or metrics.get("mapping_mode")
        or payload.get("mapping_mode")
        or "raw_hffb_node_pressure_mapping"
    )
    out["mapping_row_count"] = _pick_first_int(
        summary,
        ["mapping_row_count", "mapped_row_count", "row_count"],
        default=_pick_first_int(metrics, ["mapping_row_count", "mapped_row_count", "row_count"], default=0),
    )
    out["mapped_node_row_count"] = _pick_first_int(
        summary,
        ["mapped_node_row_count", "node_row_count", "bound_node_row_count"],
        default=_pick_first_int(metrics, ["mapped_node_row_count", "node_row_count", "bound_node_row_count"], default=0),
    )
    out["mapped_floor_row_count"] = _pick_first_int(
        summary,
        ["mapped_floor_row_count", "floor_row_count", "bound_floor_row_count"],
        default=_pick_first_int(metrics, ["mapped_floor_row_count", "floor_row_count", "bound_floor_row_count"], default=0),
    )
    out["mapping_contract_pass"] = bool(
        _safe_bool(payload.get("contract_pass"), default=False)
        or _safe_bool(summary.get("mapping_pass"), default=False)
        or out["mapping_row_count"] > 0
    )
    out["mapping_reason"] = str(payload.get("reason") or summary.get("reason") or "")
    return out


def _parse_midas(path: Path) -> dict[str, Any]:
    out = {
        "midas_exists": bool(path.exists()),
        "midas_contract_pass": False,
        "midas_traceability_pass": False,
        "midas_bound_pressure_row_count": 0,
        "midas_unbound_pressure_row_count": 0,
        "midas_reason": "",
    }
    if not path.exists():
        out["midas_reason"] = "midas conversion report missing"
        return out

    payload = _load_json(path)
    if not isinstance(payload, dict):
        out["midas_reason"] = "midas conversion report invalid json"
        return out

    metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
    out["midas_contract_pass"] = _safe_bool(payload.get("contract_pass"), default=False)
    out["midas_bound_pressure_row_count"] = _safe_int(metrics.get("bound_pressure_row_count"), default=0)
    out["midas_unbound_pressure_row_count"] = _safe_int(metrics.get("unbound_pressure_row_count"), default=0)
    semantic_load_case_count = _safe_int(metrics.get("semantic_load_case_count"), default=0)
    use_stld_block_count = _safe_int(metrics.get("use_stld_block_count"), default=0)
    out["midas_traceability_pass"] = bool(
        out["midas_contract_pass"]
        and semantic_load_case_count > 0
        and use_stld_block_count > 0
        and out["midas_bound_pressure_row_count"] > 0
        and out["midas_unbound_pressure_row_count"] == 0
    )
    out["midas_reason"] = str(payload.get("reason") or "")
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-wind", default="implementation/phase1/open_data/wind/across_wind_10h_dt1s.csv")
    parser.add_argument("--raw-wind-manifest", default="implementation/phase1/open_data/wind/across_wind_10h_dt1s.manifest.json")
    parser.add_argument("--wind-raw-mapping", default="implementation/phase1/wind_tunnel_raw_mapping.json")
    parser.add_argument("--midas-conversion", default="implementation/phase1/midas_mgt_conversion_report.json")
    parser.add_argument("--out", default="implementation/phase1/wind_tunnel_raw_mapping_report.json")
    args = parser.parse_args()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    inputs = {
        "raw_wind": str(args.raw_wind),
        "raw_wind_manifest": str(args.raw_wind_manifest),
        "wind_raw_mapping": str(args.wind_raw_mapping),
        "midas_conversion": str(args.midas_conversion),
        "out": str(args.out),
    }

    try:
        raw_wind_path = Path(args.raw_wind)
        manifest_path = Path(args.raw_wind_manifest)
        mapping_path = Path(args.wind_raw_mapping)
        midas_path = Path(args.midas_conversion)

        raw_row_count, raw_pressure_row_count = _parse_raw_wind(raw_wind_path)
        raw_exists = bool(raw_wind_path.exists() and raw_row_count > 0)

        manifest_payload = _load_json(manifest_path) if manifest_path.exists() else None
        manifest_verified, manifest_error = _verify_manifest(manifest_payload, raw_wind_path)

        mapping = _parse_mapping(mapping_path)
        mapping_has_rows = bool(mapping["mapping_exists"] and int(mapping["mapping_row_count"]) > 0)

        midas = _parse_midas(midas_path)

        checks = {
            "raw_wind_data_exists": {
                "status": _status(raw_exists, exists=raw_wind_path.exists()),
                "pass": bool(raw_exists),
                "path": str(raw_wind_path),
            },
            "raw_wind_manifest_verified": {
                "status": _status(manifest_verified, exists=manifest_path.exists()),
                "pass": bool(manifest_verified),
                "path": str(manifest_path),
                "error": str(manifest_error),
            },
            "wind_raw_mapping_available": {
                "status": _status(mapping_has_rows, exists=bool(mapping["mapping_exists"])),
                "pass": bool(mapping_has_rows),
                "path": str(mapping_path),
                "mapping_mode": str(mapping["mapping_mode"]),
            },
            "midas_traceability_ready": {
                "status": _status(bool(midas["midas_traceability_pass"]), exists=bool(midas["midas_exists"])),
                "pass": bool(midas["midas_traceability_pass"]),
                "path": str(midas_path),
            },
        }

        contract_pass = bool(
            checks["raw_wind_data_exists"]["pass"]
            and checks["raw_wind_manifest_verified"]["pass"]
            and checks["wind_raw_mapping_available"]["pass"]
            and checks["midas_traceability_ready"]["pass"]
        )

        if contract_pass:
            reason_code = "PASS"
        elif not checks["raw_wind_data_exists"]["pass"]:
            reason_code = "ERR_RAW_WIND_MISSING"
        elif not checks["raw_wind_manifest_verified"]["pass"]:
            reason_code = "ERR_RAW_MANIFEST_INVALID"
        elif not bool(mapping["mapping_exists"]):
            reason_code = "ERR_MAPPING_MISSING"
        elif not mapping_has_rows:
            reason_code = "ERR_MAPPING_EMPTY"
        else:
            reason_code = "ERR_MIDAS_TRACEABILITY"
        reason = REASONS.get(reason_code, REASONS["ERR_UNHANDLED"])

        summary = {
            "mapping_mode": str(mapping["mapping_mode"]),
            "raw_row_count": int(raw_row_count),
            "raw_pressure_row_count": int(raw_pressure_row_count),
            "mapping_row_count": int(mapping["mapping_row_count"]),
            "mapped_node_row_count": int(mapping["mapped_node_row_count"]),
            "mapped_floor_row_count": int(mapping["mapped_floor_row_count"]),
            "midas_bound_pressure_row_count": int(midas["midas_bound_pressure_row_count"]),
            "midas_unbound_pressure_row_count": int(midas["midas_unbound_pressure_row_count"]),
            "manifest_verified": bool(manifest_verified),
            "reason": str(reason),
        }

        artifacts = {
            "raw_wind_path": str(raw_wind_path),
            "raw_wind_manifest_path": str(manifest_path),
            "wind_raw_mapping_path": str(mapping_path),
            "midas_conversion_path": str(midas_path),
        }

        payload = {
            "schema_version": SCHEMA_VERSION,
            "run_id": RUN_ID,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": inputs,
            "checks": checks,
            "summary": summary,
            "artifacts": artifacts,
            "contract_pass": bool(contract_pass),
            "reason_code": str(reason_code),
            "reason": str(reason),
        }
    except Exception as exc:  # noqa: BLE001
        reason_code = "ERR_UNHANDLED"
        reason = f"{REASONS['ERR_UNHANDLED']}: {exc}"
        payload = {
            "schema_version": SCHEMA_VERSION,
            "run_id": RUN_ID,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": inputs,
            "checks": {
                "raw_wind_data_exists": {"status": "open", "pass": False},
                "raw_wind_manifest_verified": {"status": "open", "pass": False},
                "wind_raw_mapping_available": {"status": "open", "pass": False},
                "midas_traceability_ready": {"status": "open", "pass": False},
            },
            "summary": {
                "mapping_mode": "unavailable",
                "raw_row_count": 0,
                "raw_pressure_row_count": 0,
                "mapping_row_count": 0,
                "mapped_node_row_count": 0,
                "mapped_floor_row_count": 0,
                "midas_bound_pressure_row_count": 0,
                "midas_unbound_pressure_row_count": 0,
                "manifest_verified": False,
                "reason": reason,
            },
            "artifacts": {
                "raw_wind_path": str(args.raw_wind),
                "raw_wind_manifest_path": str(args.raw_wind_manifest),
                "wind_raw_mapping_path": str(args.wind_raw_mapping),
                "midas_conversion_path": str(args.midas_conversion),
            },
            "contract_pass": False,
            "reason_code": reason_code,
            "reason": reason,
        }

    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote wind-tunnel raw mapping readiness report: {out_path}")


if __name__ == "__main__":
    main()
