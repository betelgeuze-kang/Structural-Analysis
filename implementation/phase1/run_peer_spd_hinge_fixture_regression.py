#!/usr/bin/env python3
"""Validate generated PEER SPD hinge fixtures as usable regression assets."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


RUN_ID = "phase1-run-peer-spd-hinge-fixture-regression"
SCHEMA_VERSION = "1.0"

REASONS = {
    "PASS": "PEER SPD hinge fixtures are present, internally consistent, and satisfy the regression gate.",
    "ERR_REGISTRY_INVALID": "PBD hinge benchmark asset registry is missing or invalid.",
    "ERR_FIXTURE_CONTRACT": "One or more hinge fixtures are missing or do not satisfy the regression contract.",
}


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _safe_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        raw = value.strip().lower()
        if raw in {"1", "true", "yes", "y", "on"}:
            return True
        if raw in {"0", "false", "no", "n", "off"}:
            return False
    try:
        return bool(value)
    except Exception:
        return bool(default)


def _approx_equal(a: float, b: float, tol: float = 1e-9) -> bool:
    return abs(float(a) - float(b)) <= float(tol)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--asset-registry",
        default="implementation/phase1/open_data/pbd_hinge/pbd_hinge_benchmark_asset_registry.json",
    )
    parser.add_argument(
        "--out",
        default="implementation/phase1/open_data/pbd_hinge/peer_spd_hinge_fixture_regression_report.json",
    )
    parser.add_argument("--min-train-count", type=int, default=2)
    parser.add_argument("--min-val-count", type=int, default=2)
    parser.add_argument("--min-holdout-count", type=int, default=1)
    parser.add_argument("--min-rebar-sensitive-count", type=int, default=1)
    parser.add_argument("--min-confinement-sensitive-count", type=int, default=1)
    parser.add_argument("--min-point-count", type=int, default=400)
    parser.add_argument("--min-peak-drift-ratio", type=float, default=0.02)
    args = parser.parse_args()

    registry = _load_json(Path(args.asset_registry))
    summary = registry.get("summary") if isinstance(registry.get("summary"), dict) else {}
    rows = [row for row in (registry.get("rows") or []) if isinstance(row, dict)]
    benchmark_rows = [row for row in rows if _safe_bool(row.get("benchmark_ready"), False)]

    contract = {
        "min_train_count": int(args.min_train_count),
        "min_val_count": int(args.min_val_count),
        "min_holdout_count": int(args.min_holdout_count),
        "min_rebar_sensitive_count": int(args.min_rebar_sensitive_count),
        "min_confinement_sensitive_count": int(args.min_confinement_sensitive_count),
        "min_point_count": int(args.min_point_count),
        "min_peak_drift_ratio": float(args.min_peak_drift_ratio),
    }

    if not summary or not benchmark_rows:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "run_id": RUN_ID,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "contract_pass": False,
            "reason_code": "ERR_REGISTRY_INVALID",
            "reason": REASONS["ERR_REGISTRY_INVALID"],
            "inputs": {"asset_registry": str(args.asset_registry), "out": str(args.out)},
            "contract": contract,
            "observed": {
                "fixture_count": 0,
                "fixture_contract_pass_count": 0,
                "missing_fixture_count": 0,
                "min_point_count": 0,
                "min_peak_drift_ratio": 0.0,
            },
            "rows_head": [],
        }
        _write_json(Path(args.out), payload)
        print(f"Wrote PEER SPD hinge fixture regression report: {args.out}")
        raise SystemExit(1)

    train_count = 0
    val_count = 0
    holdout_count = 0
    rebar_sensitive_count = 0
    confinement_sensitive_count = 0
    fixture_contract_pass_count = 0
    missing_fixture_count = 0
    min_point_count = None
    min_peak_drift_ratio = None
    row_reports: list[dict[str, Any]] = []

    for row in benchmark_rows:
        fixture_path = Path(str(row.get("fixture_path", "")).strip())
        fixture = _load_json(fixture_path) if fixture_path.exists() else {}
        fixture_exists = fixture_path.exists()
        fixture_contract_pass = _safe_bool(fixture.get("contract_pass"), False)
        if not fixture_exists:
            missing_fixture_count += 1
        if fixture_contract_pass:
            fixture_contract_pass_count += 1

        fixture_summary = fixture.get("hysteresis_summary") if isinstance(fixture.get("hysteresis_summary"), dict) else {}
        target_summary = fixture.get("hinge_refresh_targets") if isinstance(fixture.get("hinge_refresh_targets"), dict) else {}
        fixture_seed_id = str(fixture.get("seed_id", "") or "")
        fixture_holdout_split = str(fixture.get("holdout_split", "") or "")
        fixture_point_count = _safe_int(fixture_summary.get("point_count"), 0)
        fixture_peak_drift_ratio = _safe_float(fixture_summary.get("peak_abs_drift_ratio"), 0.0)
        row_point_count = _safe_int(row.get("point_count"), 0)
        row_peak_drift_ratio = _safe_float(row.get("peak_abs_drift_ratio"), 0.0)

        split = str(row.get("holdout_split", "") or "")
        if split == "train":
            train_count += 1
        elif split == "val":
            val_count += 1
        elif split == "holdout":
            holdout_count += 1

        if _safe_bool(row.get("rebar_sensitive_expected"), False):
            rebar_sensitive_count += 1
        if _safe_bool(row.get("confinement_sensitive_expected"), False):
            confinement_sensitive_count += 1

        if min_point_count is None or fixture_point_count < min_point_count:
            min_point_count = fixture_point_count
        if min_peak_drift_ratio is None or fixture_peak_drift_ratio < min_peak_drift_ratio:
            min_peak_drift_ratio = fixture_peak_drift_ratio

        row_pass = bool(
            fixture_exists
            and fixture_contract_pass
            and fixture_seed_id == str(row.get("seed_id", "") or "")
            and fixture_holdout_split == split
            and fixture_point_count >= int(args.min_point_count)
            and fixture_peak_drift_ratio >= float(args.min_peak_drift_ratio)
            and fixture_point_count == row_point_count
            and _approx_equal(fixture_peak_drift_ratio, row_peak_drift_ratio)
            and _safe_bool(target_summary.get("rebar_sensitive_expected"), False)
            == _safe_bool(row.get("rebar_sensitive_expected"), False)
            and _safe_bool(target_summary.get("confinement_sensitive_expected"), False)
            == _safe_bool(row.get("confinement_sensitive_expected"), False)
        )
        row_reports.append(
            {
                "seed_id": str(row.get("seed_id", "") or ""),
                "fixture_path": str(fixture_path),
                "fixture_exists": fixture_exists,
                "fixture_contract_pass": fixture_contract_pass,
                "row_contract_pass": row_pass,
                "holdout_split": split,
                "fixture_holdout_split": fixture_holdout_split,
                "row_point_count": row_point_count,
                "fixture_point_count": fixture_point_count,
                "row_peak_drift_ratio": row_peak_drift_ratio,
                "fixture_peak_drift_ratio": fixture_peak_drift_ratio,
                "rebar_sensitive_expected": _safe_bool(row.get("rebar_sensitive_expected"), False),
                "fixture_rebar_sensitive_expected": _safe_bool(
                    target_summary.get("rebar_sensitive_expected"), False
                ),
                "confinement_sensitive_expected": _safe_bool(row.get("confinement_sensitive_expected"), False),
                "fixture_confinement_sensitive_expected": _safe_bool(
                    target_summary.get("confinement_sensitive_expected"), False
                ),
            }
        )

    observed = {
        "fixture_count": int(len(benchmark_rows)),
        "fixture_contract_pass_count": int(fixture_contract_pass_count),
        "missing_fixture_count": int(missing_fixture_count),
        "min_point_count": int(min_point_count or 0),
        "min_peak_drift_ratio": float(min_peak_drift_ratio or 0.0),
        "train_count": int(train_count),
        "val_count": int(val_count),
        "holdout_count": int(holdout_count),
        "rebar_sensitive_count": int(rebar_sensitive_count),
        "confinement_sensitive_count": int(confinement_sensitive_count),
        "registry_benchmark_ready_asset_count": int(summary.get("benchmark_ready_asset_count", 0) or 0),
    }

    contract_pass = bool(
        all(_safe_bool(row.get("row_contract_pass"), False) for row in row_reports)
        and observed["fixture_count"] >= int(summary.get("benchmark_ready_asset_count", 0) or 0)
        and observed["train_count"] >= contract["min_train_count"]
        and observed["val_count"] >= contract["min_val_count"]
        and observed["holdout_count"] >= contract["min_holdout_count"]
        and observed["rebar_sensitive_count"] >= contract["min_rebar_sensitive_count"]
        and observed["confinement_sensitive_count"] >= contract["min_confinement_sensitive_count"]
        and observed["min_point_count"] >= contract["min_point_count"]
        and observed["min_peak_drift_ratio"] >= contract["min_peak_drift_ratio"]
    )
    reason_code = "PASS" if contract_pass else "ERR_FIXTURE_CONTRACT"

    payload = {
        "schema_version": SCHEMA_VERSION,
        "run_id": RUN_ID,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contract_pass": contract_pass,
        "reason_code": reason_code,
        "reason": REASONS[reason_code],
        "inputs": {
            "asset_registry": str(args.asset_registry),
            "out": str(args.out),
        },
        "contract": contract,
        "observed": observed,
        "rows_head": row_reports[:5],
    }
    _write_json(Path(args.out), payload)
    print(f"Wrote PEER SPD hinge fixture regression report: {args.out}")
    if not contract_pass:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
