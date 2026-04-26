"""Shared I/O and registry helpers for bounded design-optimization refactor."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from .entrypoints import ENTRYPOINTS, entrypoint_rows


def load_json(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    return json.loads(target.read_text(encoding="utf-8")) if target.exists() else {}


def load_npz(path: str | Path) -> dict[str, np.ndarray]:
    data = np.load(Path(path))
    return {str(key): data[key] for key in data.files}


def write_json(path: str | Path, payload: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_state_npz(path: str | Path, state: dict[str, np.ndarray]) -> None:
    target = Path(path)
    payload = {str(k): np.asarray(v) for k, v in state.items()}
    target.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(target, **payload)


def load_design_opt_reports() -> dict[str, dict[str, Any]]:
    reports: dict[str, dict[str, Any]] = {}
    for name, meta in ENTRYPOINTS.items():
        report = load_json(meta.primary_report)
        if report:
            reports[name] = report
    return reports


def entrypoint_status_rows(reports: dict[str, dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    loaded = reports if reports is not None else load_design_opt_reports()
    rows: list[dict[str, Any]] = []
    for row in entrypoint_rows():
        report = loaded.get(str(row["name"]), {})
        summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
        rows.append(
            {
                **row,
                "report_exists": bool(report),
                "contract_pass": bool(report.get("contract_pass", report.get("all_pass", report.get("pass", False)))),
                "reason_code": str(report.get("reason_code", "")),
                "generated_at": str(report.get("generated_at", "")),
                "summary_keys": sorted(summary.keys())[:8],
            }
        )
    return rows


def entrypoint_group_rows(rows: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    source = rows if rows is not None else entrypoint_status_rows()
    grouped: dict[str, dict[str, Any]] = {}
    for row in source:
        group = str(row.get("group", "")).strip() or "ungrouped"
        bucket = grouped.setdefault(
            group,
            {
                "group": group,
                "group_label": str(row.get("group_label", group)).strip() or group,
                "entrypoint_count": 0,
                "report_count": 0,
                "pass_count": 0,
                "entrypoint_names": [],
            },
        )
        bucket["entrypoint_count"] = int(bucket["entrypoint_count"]) + 1
        bucket["report_count"] = int(bucket["report_count"]) + int(bool(row.get("report_exists", False)))
        bucket["pass_count"] = int(bucket["pass_count"]) + int(bool(row.get("contract_pass", False)))
        bucket["entrypoint_names"].append(str(row.get("name", "")))
    rows_out: list[dict[str, Any]] = []
    for group in sorted(grouped):
        bucket = grouped[group]
        entrypoint_count = int(bucket["entrypoint_count"])
        report_count = int(bucket["report_count"])
        pass_count = int(bucket["pass_count"])
        rows_out.append(
            {
                **bucket,
                "entrypoint_names": sorted(bucket["entrypoint_names"]),
                "all_present": bool(entrypoint_count > 0 and report_count == entrypoint_count),
                "all_pass": bool(entrypoint_count > 0 and pass_count == entrypoint_count),
            }
        )
    return rows_out


__all__ = [
    "entrypoint_rows",
    "entrypoint_group_rows",
    "entrypoint_status_rows",
    "load_design_opt_reports",
    "load_json",
    "load_npz",
    "write_json",
    "write_state_npz",
]
