#!/usr/bin/env python3
"""Fetch PEER SPD hysteresis text resources and build raw specimen JSON bundles."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import time
from typing import Any
from urllib.request import Request, urlopen


RUN_ID = "phase1-fetch-peer-spd-hysteresis-resources"
SCHEMA_VERSION = "1.0"

REASONS = {
    "PASS": "Selected PEER SPD hysteresis text resources were fetched and converted into raw specimen JSON bundles.",
    "ERR_SPECIMEN_PAGES_INVALID": "Specimen page report is missing or does not contain selected specimen rows.",
    "ERR_FETCH_FAILED": "One or more hysteresis text resources could not be fetched.",
    "ERR_PARSE_FAILED": "One or more fetched hysteresis text resources could not be parsed into displacement-force rows.",
}

_FLOAT_RE = re.compile(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _fetch_text(url: str) -> tuple[str | None, str]:
    last_error = ""
    for _attempt in range(3):
        try:
            req = Request(url, headers={"User-Agent": "Mozilla/5.0 Codex/PEER-SPD-Resource-Fetch"})
            with urlopen(req, timeout=20) as response:
                return response.read().decode("utf-8", "ignore"), ""
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            time.sleep(0.5)
    return None, last_error


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _selected_seed_ids(page_report: dict[str, Any], allowed_seed_ids: set[str]) -> list[str]:
    rows = page_report.get("rows")
    if not isinstance(rows, list):
        return []
    out: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        seed_id = str(row.get("seed_id", "")).strip()
        if not seed_id:
            continue
        if allowed_seed_ids and seed_id not in allowed_seed_ids:
            continue
        if seed_id not in out:
            out.append(seed_id)
    return out


def _find_seed(seed_manifest: dict[str, Any], seed_id: str) -> dict[str, Any]:
    rows = seed_manifest.get("seed_cases")
    if not isinstance(rows, list):
        return {}
    for row in rows:
        if isinstance(row, dict) and str(row.get("seed_id", "")).strip() == seed_id:
            return row
    return {}


def _find_candidate(candidate_report: dict[str, Any], seed_id: str) -> dict[str, Any]:
    rows = candidate_report.get("rows")
    if not isinstance(rows, list):
        return {}
    for row in rows:
        if isinstance(row, dict) and str(row.get("seed_id", "")).strip() == seed_id:
            return row.get("selected_candidate") if isinstance(row.get("selected_candidate"), dict) else {}
    return {}


def _find_page_row(page_report: dict[str, Any], seed_id: str) -> dict[str, Any]:
    rows = page_report.get("rows")
    if not isinstance(rows, list):
        return {}
    for row in rows:
        if isinstance(row, dict) and str(row.get("seed_id", "")).strip() == seed_id:
            return row
    return {}


def _pick_text_resource_link(page_payload: dict[str, Any]) -> dict[str, str]:
    candidates: list[dict[str, str]] = []
    for key in ("hysteresis_link_candidates", "resource_links", "all_links"):
        rows = page_payload.get(key)
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, dict):
                    href = str(row.get("href", "")).strip()
                    if href:
                        candidates.append({
                            "href": href,
                            "text": str(row.get("text", "")),
                            "section": str(row.get("section", "")),
                            "row_key": str(row.get("row_key", "")),
                        })
    for row in candidates:
        href = row.get("href", "").lower()
        if href.endswith(".txt"):
            return row
    return {}


def _first_number(text: Any) -> float:
    raw = str(text or "")
    match = _FLOAT_RE.search(raw.replace(",", ""))
    if not match:
        return 0.0
    try:
        return float(match.group(0))
    except Exception:
        return 0.0


def _extract_measured_length_mm(page_payload: dict[str, Any]) -> float:
    sections = page_payload.get("sections") if isinstance(page_payload.get("sections"), dict) else {}
    geometry = sections.get("Geometry") if isinstance(sections.get("Geometry"), dict) else {}
    raw = str(geometry.get("Length", "") or "")
    match = re.search(r"L-Measured:\s*([0-9,]+(?:\.\d+)?)", raw)
    if match:
        try:
            return float(match.group(1).replace(",", ""))
        except Exception:
            return 0.0
    return 0.0


def _parse_resource_text(text: str) -> tuple[str, int, list[tuple[float, float]]]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 3:
        return "", 0, []
    title = lines[0].strip().strip('"')
    declared_count = 0
    count_match = re.search(r"\d+", lines[1].replace(",", ""))
    if count_match:
        declared_count = int(count_match.group(0))
    rows: list[tuple[float, float]] = []
    for line in lines[2:]:
        parts = _FLOAT_RE.findall(line.replace(",", ""))
        if len(parts) < 2:
            continue
        rows.append((float(parts[0]), float(parts[1])))
    return title, declared_count, rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed-manifest", default="implementation/phase1/open_data/pbd_hinge/peer_spd_column_seed_manifest.json")
    parser.add_argument("--candidates", default="implementation/phase1/open_data/pbd_hinge/peer_spd_column_seed_candidates.json")
    parser.add_argument("--specimen-pages-report", default="implementation/phase1/open_data/pbd_hinge/peer_spd_specimen_pages_report.json")
    parser.add_argument("--seed-id", action="append", default=[])
    parser.add_argument("--out-dir", default="implementation/phase1/open_data/pbd_hinge/peer_spd_resources")
    parser.add_argument("--out-report", default="implementation/phase1/open_data/pbd_hinge/peer_spd_hysteresis_resources_report.json")
    parser.add_argument("--prefer-cache", action=argparse.BooleanOptionalAction, default=False)
    args = parser.parse_args()

    seed_manifest = _load_json(Path(args.seed_manifest))
    candidate_report = _load_json(Path(args.candidates))
    page_report = _load_json(Path(args.specimen_pages_report))
    allowed_seed_ids = {str(seed_id).strip() for seed_id in args.seed_id if str(seed_id).strip()}
    selected_seed_ids = _selected_seed_ids(page_report, allowed_seed_ids)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not selected_seed_ids:
        reason_code = "ERR_SPECIMEN_PAGES_INVALID"
        payload = {
            "schema_version": SCHEMA_VERSION,
            "run_id": RUN_ID,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "contract_pass": False,
            "reason_code": reason_code,
            "reason": REASONS[reason_code],
            "inputs": {
                "seed_manifest": str(args.seed_manifest),
                "candidates": str(args.candidates),
                "specimen_pages_report": str(args.specimen_pages_report),
                "seed_ids": sorted(allowed_seed_ids),
                "out_dir": str(out_dir),
            },
            "summary": {
                "selected_seed_count": 0,
                "fetch_pass_count": 0,
                "parse_pass_count": 0,
            },
            "rows": [],
        }
        _write_json(Path(args.out_report), payload)
        print(f"Wrote PEER SPD hysteresis resource report: {args.out_report}")
        raise SystemExit(1)

    rows_out: list[dict[str, Any]] = []
    fetch_failures = 0
    parse_failures = 0
    for seed_id in selected_seed_ids:
        seed = _find_seed(seed_manifest, seed_id)
        candidate = _find_candidate(candidate_report, seed_id)
        page_row = _find_page_row(page_report, seed_id)
        page_json_path = Path(str(page_row.get("raw_json_path", "") or ""))
        page_payload = _load_json(page_json_path)
        resource_row = _pick_text_resource_link(page_payload)
        resource_url = str(resource_row.get("href", "") or "").strip()

        expected_targets = seed.get("expected_local_targets", {}) if isinstance(seed.get("expected_local_targets"), dict) else {}
        raw_json_path = Path(str(expected_targets.get("raw_json", "")) or (out_dir / f"{seed_id}.raw.json"))
        text_snapshot_path = out_dir / f"{seed_id}.hysteresis.txt"

        text_payload: str | None = None
        error = ""
        cache_reused = False
        if bool(args.prefer_cache) and text_snapshot_path.exists():
            text_payload = text_snapshot_path.read_text(encoding="utf-8", errors="ignore")
            cache_reused = True
        elif resource_url:
            text_payload, error = _fetch_text(resource_url)
        if text_payload is None and text_snapshot_path.exists():
            text_payload = text_snapshot_path.read_text(encoding="utf-8", errors="ignore")
            cache_reused = True

        fetch_pass = text_payload is not None and bool(resource_url or text_snapshot_path.exists())
        parse_pass = False
        title = ""
        declared_count = 0
        point_rows: list[tuple[float, float]] = []
        if fetch_pass and text_payload is not None:
            text_snapshot_path.write_text(text_payload, encoding="utf-8")
            title, declared_count, point_rows = _parse_resource_text(text_payload)
            parse_pass = bool(point_rows)

        if not fetch_pass:
            fetch_failures += 1
        elif not parse_pass:
            parse_failures += 1

        measured_length_mm = _extract_measured_length_mm(page_payload)
        point_payload = [
            {
                "step_index": int(idx),
                "displacement_mm": float(displacement_mm),
                "drift_ratio": float(displacement_mm / measured_length_mm) if measured_length_mm else 0.0,
                "lateral_force_kN": float(force_kN),
            }
            for idx, (displacement_mm, force_kN) in enumerate(point_rows)
        ]

        raw_payload = {
            "schema_version": SCHEMA_VERSION,
            "run_id": RUN_ID,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "seed_id": seed_id,
            "holdout_split": str(seed.get("holdout_split", "") or str(page_payload.get("holdout_split", "") or "")),
            "source_name": str(page_payload.get("page_title", "") or "PEER Structural Performance Database"),
            "source_url": str(page_payload.get("specimen_display_url", "") or str(candidate.get("source_url", "") or "")),
            "source_origin_class": "official_external_benchmark",
            "selection_mode": "properties_based_preselection_plus_specimen_page_snapshot_plus_text_resource",
            "specimen_display_url": str(page_payload.get("specimen_display_url", "") or ""),
            "resource_text_url": resource_url,
            "resource_text_snapshot_path": str(text_snapshot_path) if text_snapshot_path.exists() else "",
            "resource_text_sha256": _sha256_file(text_snapshot_path) if text_snapshot_path.exists() else "",
            "specimen": {
                "specimen_id": str(candidate.get("specimen_id", page_payload.get("specimen_id", "")) or ""),
                "specimen_name": str(candidate.get("specimen_name", "") or page_payload.get("page_title", "")),
                "family_name": str(candidate.get("family_name", "") or ""),
                "column_shape": str(candidate.get("column_shape", "") or ""),
                "confinement_type": str(candidate.get("confinement_type", "") or ""),
                "confinement_detail": str(candidate.get("confinement_detail", "") or ""),
                "axial_load_kn": float(candidate.get("axial_load_kn", 0.0) or 0.0),
                "axial_load_ratio": float(candidate.get("axial_load_ratio", 0.0) or 0.0),
                "longitudinal_rebar_ratio": float(candidate.get("longitudinal_rebar_ratio", 0.0) or 0.0),
                "transverse_reinforcement_ratio": float(candidate.get("transverse_reinforcement_ratio", 0.0) or 0.0),
                "fc_mpa": float(candidate.get("fc_mpa", 0.0) or 0.0),
                "height_mm": float(measured_length_mm),
                "section_width_mm": float(candidate.get("section_width_mm", 0.0) or 0.0),
                "section_depth_mm": float(candidate.get("section_depth_mm", 0.0) or 0.0),
            },
            "hysteresis": {
                "title": title,
                "point_count_declared": int(declared_count),
                "point_count_parsed": int(len(point_payload)),
                "point_count_mismatch": bool(declared_count not in (0, len(point_payload))),
                "displacement_unit_assumed": "mm",
                "lateral_force_unit_assumed": "kN",
                "rows": point_payload,
                "drift_ratio": [float(row["drift_ratio"]) for row in point_payload],
                "lateral_force_kN": [float(row["lateral_force_kN"]) for row in point_payload],
            },
            "contract_pass": bool(fetch_pass and parse_pass),
            "reason_code": "PASS" if fetch_pass and parse_pass else ("ERR_FETCH_FAILED" if not fetch_pass else "ERR_PARSE_FAILED"),
        }
        if fetch_pass and parse_pass:
            _write_json(raw_json_path, raw_payload)

        peak_abs_drift_ratio = max((abs(float(row["drift_ratio"])) for row in point_payload), default=0.0)
        peak_abs_force_kN = max((abs(float(row["lateral_force_kN"])) for row in point_payload), default=0.0)
        rows_out.append(
            {
                "seed_id": seed_id,
                "holdout_split": str(seed.get("holdout_split", "") or ""),
                "specimen_id": str(candidate.get("specimen_id", page_payload.get("specimen_id", "")) or ""),
                "raw_json_path": str(raw_json_path),
                "page_json_path": str(page_json_path),
                "resource_text_url": resource_url,
                "resource_text_snapshot_path": str(text_snapshot_path),
                "fetch_pass": bool(fetch_pass),
                "parse_pass": bool(parse_pass),
                "cache_reused": bool(cache_reused),
                "point_count_declared": int(declared_count),
                "point_count_parsed": int(len(point_payload)),
                "measured_length_mm": float(measured_length_mm),
                "peak_abs_drift_ratio": float(peak_abs_drift_ratio),
                "peak_abs_lateral_force_kN": float(peak_abs_force_kN),
                "error": error,
            }
        )

    reason_code = "PASS"
    if fetch_failures > 0:
        reason_code = "ERR_FETCH_FAILED"
    elif parse_failures > 0:
        reason_code = "ERR_PARSE_FAILED"

    payload = {
        "schema_version": SCHEMA_VERSION,
        "run_id": RUN_ID,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contract_pass": bool(reason_code == "PASS"),
        "reason_code": reason_code,
        "reason": REASONS[reason_code],
        "inputs": {
            "seed_manifest": str(args.seed_manifest),
            "candidates": str(args.candidates),
            "specimen_pages_report": str(args.specimen_pages_report),
            "seed_ids": selected_seed_ids,
            "out_dir": str(out_dir),
            "out_report": str(args.out_report),
        },
        "summary": {
            "selected_seed_count": int(len(rows_out)),
            "fetch_pass_count": int(sum(1 for row in rows_out if bool(row.get("fetch_pass", False)))),
            "parse_pass_count": int(sum(1 for row in rows_out if bool(row.get("parse_pass", False)))),
            "cache_reuse_count": int(sum(1 for row in rows_out if bool(row.get("cache_reused", False)))),
            "raw_json_written_count": int(sum(1 for row in rows_out if Path(str(row.get("raw_json_path", ""))).exists())),
        },
        "rows": rows_out,
    }
    _write_json(Path(args.out_report), payload)
    print(f"Wrote PEER SPD hysteresis resource report: {args.out_report}")
    if reason_code != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
