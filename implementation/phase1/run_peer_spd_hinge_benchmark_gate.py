#!/usr/bin/env python3
"""Validate that the local PEER SPD hinge fixture pool is benchmark-ready."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


RUN_ID = "phase1-run-peer-spd-hinge-benchmark-gate"
SCHEMA_VERSION = "1.0"

REASONS = {
    "PASS": "PEER SPD hinge benchmark pool satisfies the current diversification contract.",
    "ERR_REGISTRY_INVALID": "PBD hinge benchmark asset registry is missing or invalid.",
    "ERR_CONTRACT_UNSATISFIED": "PBD hinge benchmark asset registry does not satisfy the current diversification contract.",
}


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--asset-registry", default="implementation/phase1/open_data/pbd_hinge/pbd_hinge_benchmark_asset_registry.json")
    parser.add_argument("--out", default="implementation/phase1/open_data/pbd_hinge/peer_spd_hinge_benchmark_gate_report.json")
    args = parser.parse_args()

    registry = _load_json(Path(args.asset_registry))
    summary = registry.get("summary") if isinstance(registry.get("summary"), dict) else {}
    rows = registry.get("rows") if isinstance(registry.get("rows"), list) else []
    valid = bool(rows) and bool(summary)

    reason_code = "PASS"
    contract = {
        "min_train_count": 2,
        "min_val_count": 2,
        "min_holdout_count": 1,
        "min_rebar_sensitive_count": 1,
        "min_confinement_sensitive_count": 1,
    }
    observed = {
        "train_count": int(summary.get("train_count", 0) or 0),
        "val_count": int(summary.get("val_count", 0) or 0),
        "holdout_count": int(summary.get("holdout_count", 0) or 0),
        "rebar_sensitive_count": int(summary.get("rebar_sensitive_count", 0) or 0),
        "confinement_sensitive_count": int(summary.get("confinement_sensitive_count", 0) or 0),
        "benchmark_ready_asset_count": int(summary.get("benchmark_ready_asset_count", 0) or 0),
    }
    if not valid:
        reason_code = "ERR_REGISTRY_INVALID"
    elif (
        observed["train_count"] < contract["min_train_count"]
        or observed["val_count"] < contract["min_val_count"]
        or observed["holdout_count"] < contract["min_holdout_count"]
        or observed["rebar_sensitive_count"] < contract["min_rebar_sensitive_count"]
        or observed["confinement_sensitive_count"] < contract["min_confinement_sensitive_count"]
    ):
        reason_code = "ERR_CONTRACT_UNSATISFIED"

    payload = {
        "schema_version": SCHEMA_VERSION,
        "run_id": RUN_ID,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contract_pass": bool(reason_code == "PASS"),
        "reason_code": reason_code,
        "reason": REASONS[reason_code],
        "inputs": {
            "asset_registry": str(args.asset_registry),
            "out": str(args.out),
        },
        "contract": contract,
        "observed": observed,
        "rows_head": rows[:5],
    }
    _write_json(Path(args.out), payload)
    print(f"Wrote PEER SPD hinge benchmark gate report: {args.out}")
    if reason_code != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
