#!/usr/bin/env python3
"""Run 5-component member-force direct compare gate with soft-accept policy.

Target components:
- axial_force_kN
- shear_force_y_kN
- shear_force_z_kN
- bending_moment_y_kNm
- bending_moment_z_kNm
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re


COMPONENT_ORDER = ["axial", "shear_y", "shear_z", "moment_y", "moment_z"]
COMPONENT_META = {
    "axial": {
        "label": "axial_force_kN",
        "default_hf_col": "axial_force_kN",
        "default_lf_col": "axial_force_kN",
        "aliases": [
            "axial_force_kN",
            "member_axial_force_kN",
            "column_axial_force_kN",
            "outrigger_col13_axial_force_kN",
            "axial_force",
        ],
    },
    "shear_y": {
        "label": "shear_force_y_kN",
        "default_hf_col": "shear_force_y_kN",
        "default_lf_col": "shear_force_y_kN",
        "aliases": ["shear_force_y_kN", "shear_y_kN", "shear_force_y", "vy_kN", "vy"],
    },
    "shear_z": {
        "label": "shear_force_z_kN",
        "default_hf_col": "shear_force_z_kN",
        "default_lf_col": "shear_force_z_kN",
        "aliases": ["shear_force_z_kN", "shear_z_kN", "shear_force_z", "vz_kN", "vz"],
    },
    "moment_y": {
        "label": "bending_moment_y_kNm",
        "default_hf_col": "bending_moment_y_kNm",
        "default_lf_col": "bending_moment_y_kNm",
        "aliases": ["bending_moment_y_kNm", "moment_y_kNm", "my_kNm", "my"],
    },
    "moment_z": {
        "label": "bending_moment_z_kNm",
        "default_hf_col": "bending_moment_z_kNm",
        "default_lf_col": "bending_moment_z_kNm",
        "aliases": ["bending_moment_z_kNm", "moment_z_kNm", "mz_kNm", "mz"],
    },
}

REASONS = {
    "PASS": "member force soft-accept gate passed",
    "ERR_INVALID_INPUT": "invalid input options",
    "ERR_FILE_MISSING": "hf/lf csv file missing",
    "ERR_COLUMNS_MISSING": "required member-force column missing",
    "ERR_CASE_MISMATCH": "hf/lf case_id alignment failed",
    "ERR_MEMBER_ID_MISMATCH": "hf/lf member_id alignment failed",
    "ERR_METRIC_INVALID": "non-numeric member-force value encountered",
    "ERR_SOFT_ACCEPT_FAIL": "member-force soft-accept policy failed",
}

STATION_AXIS = [0.0, 0.125, 0.25, 0.375, 0.5, 0.625, 0.75, 0.875, 1.0]
STATION_NUMBER_PATTERNS = [
    re.compile(r"(?:^|[^a-z0-9])station[_\-\s]*(-?\d+)p(\d+)", re.IGNORECASE),
    re.compile(r"(?:^|[^a-z0-9])station[_\-\s]*(-?\d+(?:\.\d+)?)", re.IGNORECASE),
    re.compile(r"(?:^|[^a-z0-9])st[_\-\s]*(-?\d+)p(\d+)", re.IGNORECASE),
    re.compile(r"(?:^|[^a-z0-9])st[_\-\s]*(-?\d+(?:\.\d+)?)", re.IGNORECASE),
]


def _normalize_header_token(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value).lower())


def _extract_station_value(header: str) -> float | None:
    text = str(header or "").strip()
    if not text:
        return None
    for pattern in STATION_NUMBER_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        if len(match.groups()) == 2:
            return float(f"{match.group(1)}.{match.group(2)}")
        return float(match.group(1))
    return None


def _header_matches_component(header: str, aliases: list[str]) -> bool:
    normalized_header = _normalize_header_token(header)
    alias_tokens = [_normalize_header_token(alias) for alias in aliases if str(alias).strip()]
    return any(alias_token and alias_token in normalized_header for alias_token in alias_tokens)


def _find_station_columns(headers: list[str], aliases: list[str]) -> dict[float, str]:
    station_columns: dict[float, str] = {}
    for header in headers:
        if not _header_matches_component(header, aliases):
            continue
        station = _extract_station_value(str(header))
        if station is None:
            continue
        station_columns[float(station)] = str(header)
    return dict(sorted(station_columns.items(), key=lambda item: item[0]))


def _detect_station_profiles(hf_headers: list[str], lf_headers: list[str], components: list[str]) -> dict[str, dict]:
    profiles: dict[str, dict] = {}
    for component in components:
        aliases = list(COMPONENT_META[component]["aliases"])
        hf_columns = _find_station_columns(hf_headers, aliases)
        lf_columns = _find_station_columns(lf_headers, aliases)
        shared_stations = sorted(set(hf_columns) & set(lf_columns))
        profiles[component] = {
            "hf_columns": hf_columns,
            "lf_columns": lf_columns,
            "shared_stations": shared_stations,
            "available": len(shared_stations) >= 2,
        }
    return profiles


def _build_station_source_metadata(
    *,
    hf_csv: str,
    lf_csv: str,
    hf_headers: list[str],
    lf_headers: list[str],
    component_station_profiles: dict[str, dict] | None = None,
) -> dict:
    component_station_profiles = component_station_profiles or {}
    candidate_station_headers = sorted(
        {
            str(column).strip()
            for profile in component_station_profiles.values()
            for column in [
                *(profile.get("hf_columns") or {}).values(),
                *(profile.get("lf_columns") or {}).values(),
            ]
            if str(column).strip()
        }
    )
    available_components = sorted(
        component
        for component, profile in component_station_profiles.items()
        if bool(profile.get("available"))
    )
    if available_components:
        reason = (
            "station-wise member-force columns were detected and matching hf/lf station grids are available; "
            "raw station profiles will be used when row values are finite"
        )
    elif candidate_station_headers:
        reason = (
            "station-like columns were detected in the local inputs, but no supported authoritative raw "
            "station-wise member-force source schema is currently wired for this gate"
        )
    else:
        reason = (
            "hf/lf local inputs expose only case-level 5D member-force scalars and no station-wise columns; "
            "distribution charts remain component-derived"
        )
    return {
        "authoritative_raw_station_source_available": bool(available_components),
        "authoritative_raw_station_source_used": False,
        "distribution_source_mode": (
            "authoritative_raw_station_profile" if available_components else "component_derived_station_profile"
        ),
        "inspected_inputs": [str(hf_csv), str(lf_csv)],
        "hf_header_count": int(len(hf_headers)),
        "lf_header_count": int(len(lf_headers)),
        "candidate_station_header_count": int(len(candidate_station_headers)),
        "candidate_station_headers": candidate_station_headers,
        "available_station_components": available_components,
        "component_station_profiles": {
            component: {
                "available": bool(profile.get("available")),
                "shared_station_count": int(len(profile.get("shared_stations") or [])),
                "shared_stations": [float(value) for value in (profile.get("shared_stations") or [])],
                "hf_columns": {str(k): v for k, v in (profile.get("hf_columns") or {}).items()},
                "lf_columns": {str(k): v for k, v in (profile.get("lf_columns") or {}).items()},
            }
            for component, profile in component_station_profiles.items()
        },
        "reason": reason,
    }


def _constant_profile(value: float) -> list[list[float]]:
    return [[float(station), float(value)] for station in STATION_AXIS]


def _moment_profile(value: float) -> list[list[float]]:
    profile: list[list[float]] = []
    for station in STATION_AXIS:
        taper = max(0.0, 1.0 - abs(float(station) - 0.5) * 2.0)
        profile.append([float(station), float(value) * taper])
    return profile


def _station_points_from_row(
    row: dict,
    station_columns: dict[float, str],
) -> list[list[float]]:
    points: list[list[float]] = []
    for station, column in sorted(station_columns.items(), key=lambda item: item[0]):
        value = _to_float(row[column])
        if not math.isfinite(value):
            raise ValueError(f"non-finite station value in {column}")
        points.append([float(station), float(value)])
    return points


def _filter_station_columns_to_shared(
    station_columns: dict[float, str],
    shared_stations: list[float],
) -> dict[float, str]:
    shared = {float(station) for station in shared_stations}
    return {
        float(station): column
        for station, column in station_columns.items()
        if float(station) in shared
    }


def _build_distribution_chart(
    *,
    case_id: str,
    member_id: str,
    components: dict[str, dict],
    hf_csv: str,
    lf_csv: str,
    station_source_metadata: dict,
    raw_station_profiles: dict[str, dict] | None = None,
) -> dict:
    raw_station_profiles = raw_station_profiles or {}
    used_raw = any(bool(profile.get("used")) for profile in raw_station_profiles.values())
    source_label = (
        f"authoritative raw station profile · hf={Path(hf_csv).name} · lf={Path(lf_csv).name}"
        if used_raw
        else f"component-derived station profile · hf={Path(hf_csv).name} · lf={Path(lf_csv).name}"
    )
    station_axis = sorted(
        {
            float(station)
            for profile in raw_station_profiles.values()
            for station in (profile.get("stations") or [])
        }
    ) or list(STATION_AXIS)

    def build_series(component_key: str, label: str, color: str, value_label: str, kind: str, side: str) -> dict:
        component_label = str(COMPONENT_META[component_key]["label"])
        raw_profile = raw_station_profiles.get(component_key) or {}
        points = raw_profile.get(f"{side}_points")
        used = bool(raw_profile.get("used")) and isinstance(points, list) and len(points) >= 2
        if used:
            return {
                "label": label,
                "color": color,
                "valueLabel": value_label,
                "component": component_label,
                "profile_kind": "stationwise_raw",
                "points": points,
            }
        fallback_value = float(components[component_key][side])
        fallback_points = _moment_profile(fallback_value) if kind == "moment" else _constant_profile(fallback_value)
        return {
            "label": label,
            "color": color,
            "valueLabel": value_label,
            "component": component_label,
            "profile_kind": "midspan_envelope" if kind == "moment" else "constant",
            "points": fallback_points,
        }

    return {
        "title": f"Member Force Distribution — {member_id} · {case_id}",
        "info": source_label,
        "xLabel": "Normalized Member Length",
        "case_id": case_id,
        "member_id": member_id,
        "source_mode": "authoritative_raw_station_profile" if used_raw else "component_derived_station_profile",
        "authoritative_raw_station_source_available": bool(
            station_source_metadata.get("authoritative_raw_station_source_available", False)
        ),
        "authoritative_raw_station_source_used": bool(used_raw),
        "authoritative_raw_station_source_reason": str(
            station_source_metadata.get("reason", "") or ""
        ).strip(),
        "candidate_station_headers": list(station_source_metadata.get("candidate_station_headers") or []),
        "stations": station_axis,
        "derived_from_components": list(COMPONENT_ORDER),
        "series": [
            build_series("axial", "HF axial", "#fb923c", "kN", "constant", "hf"),
            build_series("axial", "LF axial", "#fdba74", "kN", "constant", "lf"),
            build_series("shear_y", "HF shear Y", "#22d3ee", "kN", "constant", "hf"),
            build_series("shear_y", "LF shear Y", "#67e8f9", "kN", "constant", "lf"),
            build_series("shear_z", "HF shear Z", "#34d399", "kN", "constant", "hf"),
            build_series("shear_z", "LF shear Z", "#86efac", "kN", "constant", "lf"),
            build_series("moment_y", "HF moment Y", "#a78bfa", "kN·m", "moment", "hf"),
            build_series("moment_y", "LF moment Y", "#c4b5fd", "kN·m", "moment", "lf"),
            build_series("moment_z", "HF moment Z", "#38bdf8", "kN·m", "moment", "hf"),
            build_series("moment_z", "LF moment Z", "#7dd3fc", "kN·m", "moment", "lf"),
        ],
    }


def _read_csv_rows(path: Path) -> tuple[list[dict], list[str]]:
    if not path.exists():
        raise RuntimeError("ERR_FILE_MISSING")
    with path.open("r", encoding="utf-8", newline="") as f:
        rdr = csv.DictReader(f)
        rows = list(rdr)
        headers = list(rdr.fieldnames or [])
    return rows, headers


def _resolve_column(headers: list[str], preferred: str, aliases: list[str]) -> str | None:
    hs = {str(h).strip() for h in headers if str(h).strip()}
    if preferred and preferred in hs:
        return preferred
    for c in aliases:
        cc = str(c).strip()
        if cc and cc in hs:
            return cc
    return None


def _to_float(v: str) -> float:
    return float(str(v).strip())


def _err_pct(hf: float, lf: float) -> float:
    denom = max(abs(hf), 1e-9)
    return abs(lf - hf) / denom * 100.0


def _p95(xs: list[float]) -> float:
    if not xs:
        return 0.0
    arr = sorted(float(v) for v in xs)
    idx = max(0, min(len(arr) - 1, int(math.ceil(0.95 * len(arr))) - 1))
    return float(arr[idx])


def _parse_component_list(raw: str) -> list[str]:
    out: list[str] = []
    for tok in str(raw).split(","):
        k = tok.strip()
        if not k:
            continue
        if k not in COMPONENT_META:
            raise ValueError(f"unknown component: {k}")
        if k not in out:
            out.append(k)
    if not out:
        raise ValueError("component list is empty")
    return out


def _resolve_row_member_id(hf_row: dict, lf_row: dict, member_id_col: str, case_id: str) -> str:
    hf_member_id = str(hf_row.get(member_id_col, "") or "").strip()
    lf_member_id = str(lf_row.get(member_id_col, "") or "").strip()
    if hf_member_id and lf_member_id and hf_member_id != lf_member_id:
        raise RuntimeError("ERR_MEMBER_ID_MISMATCH")
    return hf_member_id or lf_member_id or case_id


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--hf-csv", default="implementation/phase1/commercial_hf_export_sample.csv")
    p.add_argument("--lf-csv", default="implementation/phase1/commercial_lf_export_sample.csv")
    p.add_argument("--case-id-col", default="case_id")
    p.add_argument("--member-id-col", default="member_id")
    p.add_argument("--components", default="axial,shear_y,shear_z,moment_y,moment_z")
    p.add_argument("--require-all-components", action=argparse.BooleanOptionalAction, default=True)
    # Backward compatibility for old callers. Equivalent to require-all-components.
    p.add_argument("--require-member-force", action=argparse.BooleanOptionalAction, default=True)

    p.add_argument("--axial-hf-col", default=COMPONENT_META["axial"]["default_hf_col"])
    p.add_argument("--axial-lf-col", default=COMPONENT_META["axial"]["default_lf_col"])
    p.add_argument("--shear-y-hf-col", default=COMPONENT_META["shear_y"]["default_hf_col"])
    p.add_argument("--shear-y-lf-col", default=COMPONENT_META["shear_y"]["default_lf_col"])
    p.add_argument("--shear-z-hf-col", default=COMPONENT_META["shear_z"]["default_hf_col"])
    p.add_argument("--shear-z-lf-col", default=COMPONENT_META["shear_z"]["default_lf_col"])
    p.add_argument("--moment-y-hf-col", default=COMPONENT_META["moment_y"]["default_hf_col"])
    p.add_argument("--moment-y-lf-col", default=COMPONENT_META["moment_y"]["default_lf_col"])
    p.add_argument("--moment-z-hf-col", default=COMPONENT_META["moment_z"]["default_hf_col"])
    p.add_argument("--moment-z-lf-col", default=COMPONENT_META["moment_z"]["default_lf_col"])

    p.add_argument("--max-hard-error-pct", type=float, default=5.0)
    p.add_argument("--max-soft-accept-error-pct", type=float, default=10.0)
    p.add_argument("--max-soft-accept-case-ratio", type=float, default=0.25)
    p.add_argument("--out", default="implementation/phase1/member_force_soft_accept_report.json")
    args = p.parse_args()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    reason_code = "PASS"
    rows_out: list[dict] = []
    component_summary: dict[str, dict] = {}

    if float(args.max_hard_error_pct) <= 0.0:
        reason_code = "ERR_INVALID_INPUT"
    if float(args.max_soft_accept_error_pct) < float(args.max_hard_error_pct):
        reason_code = "ERR_INVALID_INPUT"
    if not (0.0 <= float(args.max_soft_accept_case_ratio) <= 1.0):
        reason_code = "ERR_INVALID_INPUT"

    requested_components: list[str] = []
    if reason_code == "PASS":
        try:
            requested_components = _parse_component_list(str(args.components))
        except Exception:
            reason_code = "ERR_INVALID_INPUT"

    hf_rows: list[dict] = []
    lf_rows: list[dict] = []
    hf_headers: list[str] = []
    lf_headers: list[str] = []
    if reason_code == "PASS":
        try:
            hf_rows, hf_headers = _read_csv_rows(Path(args.hf_csv))
            lf_rows, lf_headers = _read_csv_rows(Path(args.lf_csv))
        except RuntimeError as exc:
            reason_code = str(exc) if str(exc) in REASONS else "ERR_FILE_MISSING"

    col_requests = {
        "axial": (str(args.axial_hf_col), str(args.axial_lf_col)),
        "shear_y": (str(args.shear_y_hf_col), str(args.shear_y_lf_col)),
        "shear_z": (str(args.shear_z_hf_col), str(args.shear_z_lf_col)),
        "moment_y": (str(args.moment_y_hf_col), str(args.moment_y_lf_col)),
        "moment_z": (str(args.moment_z_hf_col), str(args.moment_z_lf_col)),
    }
    resolved_columns: dict[str, dict] = {}
    component_station_profiles = _detect_station_profiles(hf_headers, lf_headers, requested_components)
    station_source_metadata = _build_station_source_metadata(
        hf_csv=str(args.hf_csv),
        lf_csv=str(args.lf_csv),
        hf_headers=hf_headers,
        lf_headers=lf_headers,
        component_station_profiles=component_station_profiles,
    )
    if reason_code == "PASS":
        for comp in requested_components:
            meta = COMPONENT_META[comp]
            hf_col = _resolve_column(hf_headers, col_requests[comp][0], list(meta["aliases"]))
            lf_col = _resolve_column(lf_headers, col_requests[comp][1], list(meta["aliases"]))
            resolved_columns[comp] = {
                "label": str(meta["label"]),
                "hf_col_requested": col_requests[comp][0],
                "lf_col_requested": col_requests[comp][1],
                "hf_col": hf_col,
                "lf_col": lf_col,
                "available": bool(hf_col is not None and lf_col is not None),
            }

    available_components = [c for c in requested_components if bool(resolved_columns.get(c, {}).get("available", False))]
    require_all_components = bool(args.require_all_components) and bool(args.require_member_force)
    if reason_code == "PASS" and require_all_components and len(available_components) != len(requested_components):
        reason_code = "ERR_COLUMNS_MISSING"

    hf_map: dict[str, dict] = {}
    lf_map: dict[str, dict] = {}
    case_ids: list[str] = []
    if reason_code == "PASS":
        case_key = str(args.case_id_col)
        try:
            hf_map = {str(r[case_key]).strip(): r for r in hf_rows if str(r.get(case_key, "")).strip()}
            lf_map = {str(r[case_key]).strip(): r for r in lf_rows if str(r.get(case_key, "")).strip()}
        except Exception:
            reason_code = "ERR_CASE_MISMATCH"
        if reason_code == "PASS":
            hf_ids = set(hf_map.keys())
            lf_ids = set(lf_map.keys())
            if not hf_ids or not lf_ids or hf_ids != lf_ids:
                reason_code = "ERR_CASE_MISMATCH"
            else:
                case_ids = sorted(hf_ids)

    component_errors: dict[str, list[float]] = {c: [] for c in available_components}
    component_bands: dict[str, dict[str, int]] = {
        c: {"hard_pass": 0, "soft_accept": 0, "fail": 0} for c in available_components
    }
    if reason_code == "PASS":
        for cid in case_ids:
            row_comp: dict[str, dict] = {}
            row_raw_station_profiles: dict[str, dict] = {}
            try:
                member_id = _resolve_row_member_id(hf_map[cid], lf_map[cid], str(args.member_id_col), cid)
            except RuntimeError as exc:
                reason_code = str(exc)
                break
            for comp in available_components:
                hf_col = str(resolved_columns[comp]["hf_col"])
                lf_col = str(resolved_columns[comp]["lf_col"])
                try:
                    hf_val = _to_float(hf_map[cid][hf_col])
                    lf_val = _to_float(lf_map[cid][lf_col])
                except Exception:
                    reason_code = "ERR_METRIC_INVALID"
                    break
                if not (math.isfinite(hf_val) and math.isfinite(lf_val)):
                    reason_code = "ERR_METRIC_INVALID"
                    break
                e = float(_err_pct(hf_val, lf_val))
                component_errors[comp].append(e)
                if e <= float(args.max_hard_error_pct):
                    band = "hard_pass"
                elif e <= float(args.max_soft_accept_error_pct):
                    band = "soft_accept"
                else:
                    band = "fail"
                component_bands[comp][band] += 1
                row_comp[comp] = {
                    "label": str(COMPONENT_META[comp]["label"]),
                    "hf": float(hf_val),
                    "lf": float(lf_val),
                    "error_pct": float(e),
                    "band": band,
                }
                station_profile = component_station_profiles.get(comp) or {}
                raw_profile = {
                    "used": False,
                    "stations": list(station_profile.get("shared_stations") or []),
                    "hf_points": [],
                    "lf_points": [],
                }
                if raw_profile["stations"]:
                    try:
                        hf_station_columns = _filter_station_columns_to_shared(
                            station_profile.get("hf_columns") or {},
                            raw_profile["stations"],
                        )
                        lf_station_columns = _filter_station_columns_to_shared(
                            station_profile.get("lf_columns") or {},
                            raw_profile["stations"],
                        )
                        raw_profile["hf_points"] = _station_points_from_row(
                            hf_map[cid],
                            hf_station_columns,
                        )
                        raw_profile["lf_points"] = _station_points_from_row(
                            lf_map[cid],
                            lf_station_columns,
                        )
                        raw_profile["used"] = (
                            len(raw_profile["hf_points"]) >= 2
                            and len(raw_profile["hf_points"]) == len(raw_profile["lf_points"])
                        )
                    except Exception:
                        raw_profile["used"] = False
                        raw_profile["hf_points"] = []
                        raw_profile["lf_points"] = []
                row_raw_station_profiles[comp] = raw_profile
            if reason_code != "PASS":
                break
            row_used_authoritative_source = any(
                bool(profile.get("used")) for profile in row_raw_station_profiles.values()
            )
            station_source_metadata["authoritative_raw_station_source_used"] = bool(
                station_source_metadata["authoritative_raw_station_source_used"] or row_used_authoritative_source
            )
            rows_out.append(
                {
                    "case_id": cid,
                    "member_id": member_id,
                    "components": row_comp,
                    "distribution_chart": _build_distribution_chart(
                        case_id=cid,
                        member_id=member_id,
                        components=row_comp,
                        hf_csv=str(args.hf_csv),
                        lf_csv=str(args.lf_csv),
                        station_source_metadata=station_source_metadata,
                        raw_station_profiles=row_raw_station_profiles,
                    ),
                }
            )

    for comp in requested_components:
        stats = {
            "label": str(COMPONENT_META[comp]["label"]),
            "available": bool(comp in available_components),
            "case_count": 0,
            "hard_pass_count": 0,
            "soft_accept_count": 0,
            "fail_count": 0,
            "soft_accept_case_ratio": 1.0,
            "error_pct_mean": math.inf,
            "error_pct_p95": math.inf,
            "error_pct_max": math.inf,
            "hard_gate_pass": False,
            "soft_accept_gate_pass": False,
        }
        if comp in available_components:
            errs = component_errors[comp]
            hard_count = int(component_bands[comp]["hard_pass"])
            soft_count = int(component_bands[comp]["soft_accept"])
            fail_count = int(component_bands[comp]["fail"])
            case_count = int(len(errs))
            soft_ratio = float(soft_count / max(1, case_count))
            max_err = float(max(errs) if errs else 0.0)
            mean_err = float(sum(errs) / len(errs) if errs else 0.0)
            p95_err = float(_p95(errs))
            hard_gate_pass = bool(max_err <= float(args.max_hard_error_pct) and fail_count == 0 and soft_count == 0)
            soft_gate_pass = bool(
                max_err <= float(args.max_soft_accept_error_pct)
                and soft_ratio <= float(args.max_soft_accept_case_ratio)
                and fail_count == 0
            )
            stats.update(
                {
                    "case_count": case_count,
                    "hard_pass_count": hard_count,
                    "soft_accept_count": soft_count,
                    "fail_count": fail_count,
                    "soft_accept_case_ratio": soft_ratio,
                    "error_pct_mean": mean_err,
                    "error_pct_p95": p95_err,
                    "error_pct_max": max_err,
                    "hard_gate_pass": hard_gate_pass,
                    "soft_accept_gate_pass": soft_gate_pass,
                }
            )
        component_summary[comp] = stats

    if bool(station_source_metadata["authoritative_raw_station_source_available"]) and not bool(
        station_source_metadata["authoritative_raw_station_source_used"]
    ):
        station_source_metadata["distribution_source_mode"] = "component_derived_station_profile"

    available_hard_pass = all(bool(component_summary[c]["hard_gate_pass"]) for c in available_components)
    available_soft_pass = all(bool(component_summary[c]["soft_accept_gate_pass"]) for c in available_components)
    five_component_pass = bool(
        len(available_components) == 5
        and set(available_components) == set(COMPONENT_ORDER)
        and available_hard_pass
    )
    global_max_err = 0.0
    global_p95_max_component = 0.0
    global_soft_ratio_max_component = 0.0
    global_fail_count = 0
    for c in available_components:
        global_max_err = max(global_max_err, float(component_summary[c]["error_pct_max"]))
        global_p95_max_component = max(global_p95_max_component, float(component_summary[c]["error_pct_p95"]))
        global_soft_ratio_max_component = max(
            global_soft_ratio_max_component, float(component_summary[c]["soft_accept_case_ratio"])
        )
        global_fail_count += int(component_summary[c]["fail_count"])

    checks = {
        "member_force_metric_present": bool(len(available_components) > 0),
        "component_coverage_pass": bool(len(available_components) == len(requested_components)),
        "member_force_components_5d_pass": bool(five_component_pass),
        "case_alignment_pass": bool(reason_code != "ERR_CASE_MISMATCH"),
        "finite_metric_pass": bool(reason_code != "ERR_METRIC_INVALID"),
        "hard_gate_pass": bool(reason_code == "PASS" and available_hard_pass),
        "soft_accept_gate_pass": bool(reason_code == "PASS" and available_soft_pass),
    }
    contract_pass = bool(
        reason_code == "PASS"
        and checks["component_coverage_pass"]
        and checks["case_alignment_pass"]
        and checks["finite_metric_pass"]
        and checks["soft_accept_gate_pass"]
    )
    if reason_code == "PASS" and not contract_pass:
        reason_code = "ERR_SOFT_ACCEPT_FAIL"

    payload = {
        "schema_version": "1.1",
        "run_id": "phase1-member-force-soft-accept-gate",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "hf_csv": str(args.hf_csv),
            "lf_csv": str(args.lf_csv),
            "case_id_col": str(args.case_id_col),
            "member_id_col": str(args.member_id_col),
            "components_requested": requested_components,
            "require_all_components": bool(require_all_components),
            "max_hard_error_pct": float(args.max_hard_error_pct),
            "max_soft_accept_error_pct": float(args.max_soft_accept_error_pct),
            "max_soft_accept_case_ratio": float(args.max_soft_accept_case_ratio),
        },
        "resolved_columns": resolved_columns,
        "summary": {
            "case_count": int(len(case_ids)),
            "member_count": int(len({str(row.get("member_id", "") or "").strip() for row in rows_out if row.get("member_id")})),
            "component_count_required": int(len(requested_components)),
            "component_count_available": int(len(available_components)),
            "error_pct_max": float(global_max_err),
            "error_pct_p95": float(global_p95_max_component),
            "soft_accept_case_ratio": float(global_soft_ratio_max_component),
            "fail_count": int(global_fail_count),
            "distribution_chart_case_count": int(len(rows_out)),
            "distribution_chart_source_mode": str(station_source_metadata["distribution_source_mode"]),
            "authoritative_raw_station_source_available": bool(
                station_source_metadata["authoritative_raw_station_source_available"]
            ),
            "authoritative_raw_station_source_used": bool(
                station_source_metadata["authoritative_raw_station_source_used"]
            ),
            "authoritative_raw_station_source_reason": station_source_metadata["reason"],
            "soft_accept_used": bool(
                any(int(component_summary[c]["soft_accept_count"]) > 0 for c in available_components)
            ),
        },
        "component_summary": component_summary,
        "station_source": station_source_metadata,
        "checks": checks,
        "rows": rows_out,
        "contract_pass": bool(contract_pass),
        "reason_code": reason_code,
        "reason": REASONS[reason_code],
    }
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote member force soft-accept gate report: {out}")
    if not contract_pass:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
