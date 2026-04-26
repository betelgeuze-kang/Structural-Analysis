#!/usr/bin/env python3
"""Normalize a PEER SPD RC column specimen into a hinge benchmark fixture."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any


RUN_ID = "phase1-normalize-peer-spd-column-seed"
SCHEMA_VERSION = "1.0"

REASONS = {
    "PASS": "PEER SPD column specimen normalized into a hinge benchmark fixture.",
    "ERR_SEED_NOT_FOUND": "seed_id is not defined in the PEER SPD seed manifest.",
    "ERR_RAW_SPECIMEN_MISSING": "raw specimen json is missing or unreadable.",
    "ERR_RAW_SPECIMEN_INVALID": "raw specimen json does not contain usable specimen metadata and hysteresis rows.",
}


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _find_seed(seed_manifest: dict[str, Any], seed_id: str) -> dict[str, Any]:
    rows = seed_manifest.get("seed_cases", [])
    if not isinstance(rows, list):
        return {}
    for row in rows:
        if isinstance(row, dict) and str(row.get("seed_id", "")).strip() == seed_id:
            return row
    return {}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _specimen_block(payload: dict[str, Any]) -> dict[str, Any]:
    nested = payload.get("specimen")
    if isinstance(nested, dict):
        return nested
    return payload


def _extract_hysteresis_rows(payload: dict[str, Any]) -> list[dict[str, float]]:
    candidates: list[dict[str, Any]] = []
    hysteresis = payload.get("hysteresis")
    if isinstance(hysteresis, dict):
        if isinstance(hysteresis.get("rows"), list):
            candidates = [row for row in hysteresis.get("rows", []) if isinstance(row, dict)]
        elif isinstance(hysteresis.get("points"), list):
            candidates = [row for row in hysteresis.get("points", []) if isinstance(row, dict)]
        else:
            drift = hysteresis.get("drift_ratio")
            force = hysteresis.get("lateral_force_kN")
            if isinstance(drift, list) and isinstance(force, list):
                limit = min(len(drift), len(force))
                candidates = [
                    {"drift_ratio": drift[idx], "lateral_force_kN": force[idx]}
                    for idx in range(limit)
                ]
    elif isinstance(payload.get("rows"), list):
        candidates = [row for row in payload.get("rows", []) if isinstance(row, dict)]

    out: list[dict[str, float]] = []
    for row in candidates:
        drift = _safe_float(
            row.get("drift_ratio", row.get("drift", row.get("story_drift_ratio", 0.0))),
            0.0,
        )
        force = _safe_float(
            row.get("lateral_force_kN", row.get("force_kN", row.get("lateral_force", 0.0))),
            0.0,
        )
        out.append(
            {
                "drift_ratio": float(drift),
                "lateral_force_kN": float(force),
            }
        )
    return out


def _max_abs(values: list[float]) -> float:
    if not values:
        return 0.0
    return max(abs(float(value)) for value in values)


def _selection_flag(seed: dict[str, Any], key: str, contains: str = "") -> bool:
    selection = seed.get("selection_filters", {})
    if not isinstance(selection, dict):
        return False
    raw = str(selection.get(key, "") or "").strip().lower()
    if contains:
        return contains in raw
    return bool(raw)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--seed-manifest",
        default="implementation/phase1/open_data/pbd_hinge/peer_spd_column_seed_manifest.json",
    )
    parser.add_argument("--seed-id", required=True)
    parser.add_argument("--raw-specimen-json", required=True)
    parser.add_argument("--out-fixture", default="")
    parser.add_argument("--source-manifest-out", default="")
    parser.add_argument("--out-report", default="")
    args = parser.parse_args()

    seed_manifest_path = Path(args.seed_manifest)
    seed_manifest = _load_json(seed_manifest_path)
    seed = _find_seed(seed_manifest, str(args.seed_id).strip())
    raw_specimen_path = Path(args.raw_specimen_json)

    reason_code = "PASS"
    reason = REASONS[reason_code]
    raw_payload: dict[str, Any] = {}
    specimen: dict[str, Any] = {}
    hysteresis_rows: list[dict[str, float]] = []

    if not seed:
        reason_code = "ERR_SEED_NOT_FOUND"
        reason = REASONS[reason_code]
    elif not raw_specimen_path.exists():
        reason_code = "ERR_RAW_SPECIMEN_MISSING"
        reason = REASONS[reason_code]
    else:
        raw_payload = _load_json(raw_specimen_path)
        specimen = _specimen_block(raw_payload)
        hysteresis_rows = _extract_hysteresis_rows(raw_payload)
        specimen_id = str(specimen.get("specimen_id", specimen.get("id", "")) or "").strip()
        if not specimen_id or not hysteresis_rows:
            reason_code = "ERR_RAW_SPECIMEN_INVALID"
            reason = REASONS[reason_code]

    expected_targets = seed.get("expected_local_targets", {}) if isinstance(seed.get("expected_local_targets"), dict) else {}
    if str(args.out_fixture).strip():
        out_fixture = Path(str(args.out_fixture).strip())
    else:
        out_fixture = Path(str(expected_targets.get("hinge_fixture", "")) or raw_specimen_path.with_suffix(".hinge_fixture.json"))
    if str(args.source_manifest_out).strip():
        source_manifest_out = Path(str(args.source_manifest_out).strip())
    else:
        source_manifest_out = Path(str(expected_targets.get("source_manifest", "")) or raw_specimen_path.with_suffix(".source_manifest.json"))
    if str(args.out_report).strip():
        out_report = Path(str(args.out_report).strip())
    else:
        out_report = out_fixture.with_suffix(".normalize_report.json")

    specimen_id = str(specimen.get("specimen_id", specimen.get("id", "")) or "").strip()
    source_url = str(raw_payload.get("source_url", "") or "").strip()
    if not source_url:
        urls = seed_manifest.get("source_urls", [])
        if isinstance(urls, list) and urls:
            source_url = str(urls[0]).strip()
    source_name = str(raw_payload.get("source_name", "") or "").strip() or str(seed_manifest.get("source_name", "") or "")

    drift_values = [float(row["drift_ratio"]) for row in hysteresis_rows]
    force_values = [float(row["lateral_force_kN"]) for row in hysteresis_rows]

    rebar_sensitive_expected = "rebar_sensitive" in str(args.seed_id).strip().lower() or _selection_flag(seed, "rebar_ratio_band", "higher")
    axial_load_sensitive_expected = _selection_flag(seed, "axial_load_ratio_band", "high")
    confinement_sensitive_expected = _selection_flag(seed, "confinement_type", "spiral") or _selection_flag(seed, "column_shape", "circular")

    fixture_payload = {
        "schema_version": SCHEMA_VERSION,
        "run_id": RUN_ID,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "seed_id": str(args.seed_id).strip(),
        "holdout_split": str(seed.get("holdout_split", "") or ""),
        "source_name": source_name,
        "source_url": source_url,
        "source_origin_class": "official_external_benchmark",
        "source_file_path": str(raw_specimen_path),
        "source_sha256": _sha256_file(raw_specimen_path) if raw_specimen_path.exists() else "",
        "specimen_summary": {
            "specimen_id": specimen_id,
            "column_shape": str(specimen.get("column_shape", specimen.get("shape", "")) or ""),
            "confinement_type": str(specimen.get("confinement_type", "") or ""),
            "axial_load_ratio": _safe_float(specimen.get("axial_load_ratio"), 0.0),
            "longitudinal_rebar_ratio": _safe_float(specimen.get("longitudinal_rebar_ratio", specimen.get("rebar_ratio")), 0.0),
            "transverse_reinforcement_ratio": _safe_float(specimen.get("transverse_reinforcement_ratio"), 0.0),
            "height_mm": _safe_float(specimen.get("height_mm"), 0.0),
            "section_width_mm": _safe_float(specimen.get("section_width_mm", specimen.get("width_mm")), 0.0),
            "section_depth_mm": _safe_float(specimen.get("section_depth_mm", specimen.get("depth_mm")), 0.0),
        },
        "hysteresis_summary": {
            "point_count": int(len(hysteresis_rows)),
            "peak_abs_drift_ratio": float(_max_abs(drift_values)),
            "peak_abs_lateral_force_kN": float(_max_abs(force_values)),
        },
        "hinge_refresh_targets": {
            "rebar_sensitive_expected": bool(rebar_sensitive_expected),
            "axial_load_sensitive_expected": bool(axial_load_sensitive_expected),
            "confinement_sensitive_expected": bool(confinement_sensitive_expected),
        },
        "normalized_hysteresis": {
            "rows_head": hysteresis_rows[:32],
            "full_point_count": int(len(hysteresis_rows)),
        },
        "contract_pass": bool(reason_code == "PASS"),
        "reason_code": reason_code,
        "reason": reason,
    }

    source_manifest_payload = {
        "schema_version": SCHEMA_VERSION,
        "source_family": "peer_spd_column",
        "seed_id": str(args.seed_id).strip(),
        "holdout_split": str(seed.get("holdout_split", "") or ""),
        "specimen_id": specimen_id,
        "source_url": source_url,
        "source_file_path": str(raw_specimen_path),
        "source_sha256": _sha256_file(raw_specimen_path) if raw_specimen_path.exists() else "",
        "source_origin_class": "official_external_benchmark",
    }

    report_payload = {
        "schema_version": SCHEMA_VERSION,
        "run_id": RUN_ID,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contract_pass": bool(reason_code == "PASS"),
        "reason_code": reason_code,
        "reason": reason,
        "inputs": {
            "seed_manifest": str(seed_manifest_path),
            "seed_id": str(args.seed_id).strip(),
            "raw_specimen_json": str(raw_specimen_path),
        },
        "summary": {
            "holdout_split": str(seed.get("holdout_split", "") or ""),
            "specimen_id": specimen_id,
            "point_count": int(len(hysteresis_rows)),
            "rebar_sensitive_expected": bool(rebar_sensitive_expected),
            "axial_load_sensitive_expected": bool(axial_load_sensitive_expected),
            "confinement_sensitive_expected": bool(confinement_sensitive_expected),
        },
        "artifacts": {
            "out_fixture": str(out_fixture),
            "source_manifest_out": str(source_manifest_out),
        },
    }

    _write_json(out_fixture, fixture_payload)
    _write_json(source_manifest_out, source_manifest_payload)
    _write_json(out_report, report_payload)
    print(f"Wrote PEER SPD hinge fixture: {out_fixture}")
    print(f"Wrote PEER SPD source manifest: {source_manifest_out}")
    print(f"Wrote PEER SPD normalization report: {out_report}")

    if reason_code != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
