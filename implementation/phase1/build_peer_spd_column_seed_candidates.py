#!/usr/bin/env python3
"""Build properties-based PEER SPD RC column seed candidates."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from typing import Any


RUN_ID = "phase1-build-peer-spd-column-seed-candidates"
SCHEMA_VERSION = "1.0"

RECTANGULAR_URL = "https://nisee.berkeley.edu/spd/rectangular_properties.txt"
SPIRAL_URL = "https://nisee.berkeley.edu/spd/spiral_properties.txt"

REASONS = {
    "PASS": "Properties-based PEER SPD seed candidates were identified for hinge benchmark intake.",
    "ERR_TABLES_MISSING": "Required PEER SPD property tables are missing.",
    "ERR_SEEDS_UNMATCHED": "One or more PEER SPD seed filters could not be matched to any official property-table candidate.",
}


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _canonical_key(value: str) -> str:
    return "".join(ch for ch in str(value).lower() if ch.isalnum())


def _to_float(value: Any) -> float | None:
    token = str(value).replace(",", "").strip()
    if not token or token == "-":
        return None
    try:
        out = float(token)
    except Exception:
        return None
    if math.isfinite(out):
        return out
    return None


def _read_table(path: Path, table_kind: str) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    raw = path.read_text(encoding="utf-8", errors="ignore")
    try:
        reader = csv.DictReader(raw.splitlines(), delimiter="\t")
        rows = list(reader)
    except Exception:
        rows = []
    if rows and len(rows[0].keys()) > 1:
        return [_normalize_row(row, table_kind) for row in rows if isinstance(row, dict)]
    return []


def _value(row: dict[str, Any], *names: str) -> str:
    for name in names:
        key = _canonical_key(name)
        for row_key, row_value in row.items():
            if _canonical_key(str(row_key)) == key:
                return str(row_value)
    return ""


def _normalize_row(row: dict[str, Any], table_kind: str) -> dict[str, Any]:
    specimen_id = str(_value(row, "No.", "No")).strip()
    specimen_name = str(_value(row, "Specimen Name")).strip()
    comments = str(_value(row, "Comments")).strip()
    fc_mpa = _to_float(_value(row, "f'c (MPa)", "fc (MPa)", "f'c", "fc")) or 0.0
    axial_load_kn = _to_float(_value(row, "Axial Load (kN)", "P")) or 0.0
    reinf_ratio = _to_float(_value(row, "Reinf Ratio", "rho Long")) or 0.0
    transverse_ratio = _to_float(_value(row, "Vol Trans Reinf Ratio", "rho Spiral")) or 0.0
    confinement_text = str(_value(row, "Type of confinement", "Configuration")).strip()
    if table_kind == "rectangular":
        width_mm = _to_float(_value(row, "B (mm)")) or 0.0
        depth_mm = _to_float(_value(row, "H (mm)")) or 0.0
        gross_area_mm2 = width_mm * depth_mm
        column_shape = "rectangular"
        confinement_type = "tied"
        source_url = RECTANGULAR_URL
    else:
        diameter_mm = _to_float(_value(row, "Diameter")) or 0.0
        gross_area_mm2 = math.pi * (diameter_mm ** 2) / 4.0 if diameter_mm > 0.0 else 0.0
        width_mm = diameter_mm
        depth_mm = diameter_mm
        column_shape = "circular_or_spiral"
        confinement_type = "spiral"
        source_url = SPIRAL_URL
    axial_load_ratio = 0.0
    if gross_area_mm2 > 0.0 and fc_mpa > 0.0:
        axial_load_ratio = axial_load_kn / ((gross_area_mm2 * fc_mpa) / 1000.0)
    family_name = specimen_name.split(",")[0].strip() if specimen_name else ""
    return {
        "table_kind": table_kind,
        "specimen_id": specimen_id,
        "specimen_name": specimen_name,
        "family_name": family_name,
        "comments": comments,
        "column_shape": column_shape,
        "confinement_type": confinement_type,
        "confinement_detail": confinement_text,
        "axial_load_kn": float(axial_load_kn),
        "axial_load_ratio": float(axial_load_ratio),
        "longitudinal_rebar_ratio": float(reinf_ratio),
        "transverse_reinforcement_ratio": float(transverse_ratio),
        "fc_mpa": float(fc_mpa),
        "section_width_mm": float(width_mm),
        "section_depth_mm": float(depth_mm),
        "specimen_display_url": f"https://nisee.berkeley.edu/spd/servlet/display?format=html&id={specimen_id}",
        "source_url": source_url,
    }


def _band(axial_load_ratio: float) -> str:
    if axial_load_ratio >= 0.30:
        return "high"
    if axial_load_ratio >= 0.10:
        return "moderate"
    return "low"


def _seed_cases(seed_manifest: dict[str, Any]) -> list[dict[str, Any]]:
    rows = seed_manifest.get("seed_cases")
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _match_seed(rows: list[dict[str, Any]], seed: dict[str, Any], used_families: set[str], reinf_high_threshold: float) -> list[dict[str, Any]]:
    filters = seed.get("selection_filters", {}) if isinstance(seed.get("selection_filters"), dict) else {}
    matched = rows
    shape = str(filters.get("column_shape", "")).strip()
    if shape == "rectangular":
        matched = [row for row in matched if row.get("column_shape") == "rectangular"]
    elif shape == "circular_or_spiral":
        matched = [row for row in matched if row.get("column_shape") == "circular_or_spiral"]
    conf = str(filters.get("confinement_type", "")).strip().lower()
    if "tied" in conf:
        matched = [row for row in matched if row.get("confinement_type") == "tied"]
    elif "spiral" in conf:
        matched = [row for row in matched if row.get("confinement_type") == "spiral"]
    axial_band = str(filters.get("axial_load_ratio_band", "")).strip().lower()
    if axial_band:
        matched = [row for row in matched if _band(float(row.get("axial_load_ratio", 0.0))) == axial_band]
    rebar_band = str(filters.get("rebar_ratio_band", "")).strip().lower()
    if rebar_band == "higher":
        matched = [row for row in matched if float(row.get("longitudinal_rebar_ratio", 0.0)) >= reinf_high_threshold]
    if bool(filters.get("transverse_reinforcement_variation_required", False)):
        matched = [row for row in matched if float(row.get("transverse_reinforcement_ratio", 0.0)) > 0.0]
    family_distance = str(filters.get("specimen_family_distance", "")).strip().lower()
    if "out_of_family" in family_distance:
        out_of_family = [row for row in matched if str(row.get("family_name", "")) not in used_families]
        if out_of_family:
            matched = out_of_family
    prefer_high_rebar = rebar_band == "higher"
    return sorted(
        matched,
        key=lambda row: (
            -float(row.get("longitudinal_rebar_ratio", 0.0)) if prefer_high_rebar else 0.0,
            str(row.get("family_name", "")) in used_families,
            abs(float(row.get("axial_load_ratio", 0.0)) - (0.20 if axial_band == "moderate" else 0.35 if axial_band == "high" else 0.05)),
            -float(row.get("longitudinal_rebar_ratio", 0.0)),
            str(row.get("specimen_id", "")),
        ),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed-manifest", default="implementation/phase1/open_data/pbd_hinge/peer_spd_column_seed_manifest.json")
    parser.add_argument("--rectangular-table", default="implementation/phase1/open_data/pbd_hinge/peer_spd/rectangular_properties.txt")
    parser.add_argument("--spiral-table", default="implementation/phase1/open_data/pbd_hinge/peer_spd/spiral_properties.txt")
    parser.add_argument("--out", default="implementation/phase1/open_data/pbd_hinge/peer_spd_column_seed_candidates.json")
    args = parser.parse_args()

    seed_manifest = _load_json(Path(args.seed_manifest))
    rectangular_rows = _read_table(Path(args.rectangular_table), "rectangular")
    spiral_rows = _read_table(Path(args.spiral_table), "spiral")
    all_rows = [row for row in (rectangular_rows + spiral_rows) if str(row.get("specimen_id", "")).strip()]

    if not rectangular_rows or not spiral_rows:
        reason_code = "ERR_TABLES_MISSING"
    else:
        reason_code = "PASS"

    reinf_values = sorted(float(row.get("longitudinal_rebar_ratio", 0.0)) for row in all_rows if float(row.get("longitudinal_rebar_ratio", 0.0)) > 0.0)
    reinf_high_threshold = reinf_values[max(0, int(len(reinf_values) * 0.75) - 1)] if reinf_values else 0.0

    used_families: set[str] = set()
    seed_rows = []
    unmatched_seed_count = 0
    for seed in _seed_cases(seed_manifest):
        matches = _match_seed(all_rows, seed, used_families, reinf_high_threshold)
        selected = matches[0] if matches else None
        if selected is None:
            unmatched_seed_count += 1
        else:
            used_families.add(str(selected.get("family_name", "")))
        seed_rows.append(
            {
                "seed_id": str(seed.get("seed_id", "")),
                "holdout_split": str(seed.get("holdout_split", "")),
                "candidate_count": int(len(matches)),
                "selected_candidate": selected or {},
                "candidate_head": matches[:5],
                "selection_filters": seed.get("selection_filters", {}),
                "selection_mode": "properties_based_preselection_only",
                "hysteresis_complete_verified": False,
            }
        )

    if reason_code == "PASS" and unmatched_seed_count > 0:
        reason_code = "ERR_SEEDS_UNMATCHED"

    payload = {
        "schema_version": SCHEMA_VERSION,
        "run_id": RUN_ID,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contract_pass": bool(reason_code == "PASS"),
        "reason_code": reason_code,
        "reason": REASONS[reason_code],
        "inputs": {
            "seed_manifest": str(args.seed_manifest),
            "rectangular_table": str(args.rectangular_table),
            "spiral_table": str(args.spiral_table),
            "out": str(args.out),
        },
        "summary": {
            "rectangular_row_count": int(len(rectangular_rows)),
            "spiral_row_count": int(len(spiral_rows)),
            "total_candidate_row_count": int(len(all_rows)),
            "seed_case_count": int(len(seed_rows)),
            "matched_seed_count": int(sum(1 for row in seed_rows if int(row.get("candidate_count", 0) or 0) > 0)),
            "unmatched_seed_count": int(unmatched_seed_count),
            "properties_only_preselection": True,
            "rebar_high_threshold": float(reinf_high_threshold),
        },
        "rows": seed_rows,
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote PEER SPD seed candidate report: {args.out}")


if __name__ == "__main__":
    main()
