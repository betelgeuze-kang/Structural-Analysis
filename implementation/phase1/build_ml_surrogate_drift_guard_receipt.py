#!/usr/bin/env python3
"""Compute ML surrogate drift and gate production activation.

This thin bridge:
  - reads the validated ML surrogate checkpoint manifest
    (validation_receipt, ood_gate, solver_fallback_receipt, checkpoint)
  - reads the live production activation status from
    :func:`probe_ml_surrogate_production_gate`
  - computes a per-component drift metric (max_dcr, drift contribution,
    group cost proxy) and compares it against the validation thresholds
  - emits a deterministic receipt declaring:
      * production_ml_wired  (shadow_with_solver_fallback)
      * drift_per_component  (current vs validation max_dcr p95)
      * drift_guard_decision  (armed / disarm_recommended / forced_disabled)
      * env_recommendation    (set PHASE1_ML_SURROGATE_DISABLE=1 if guard fires)

The receipt is the audit-friendly record of why the production ML surrogate
is or is not wired at a given moment. The CI gate ``check_ml_surrogate_drift_guard``
re-runs the same logic and fails closed when the guard fires.

Output JSON:
  implementation/phase1/release_evidence/productization/ml_surrogate_drift_guard_receipt.json
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
PHASE1 = REPO_ROOT / "implementation" / "phase1"
PRODUCTIZATION = PHASE1 / "release_evidence" / "productization"

sys.path.insert(0, str(PHASE1))
try:
    from ml_surrogate_production_gate import probe_ml_surrogate_production_gate  # type: ignore
except ImportError:  # pragma: no cover
    from implementation.phase1.ml_surrogate_production_gate import (  # type: ignore
        probe_ml_surrogate_production_gate,
    )

SCHEMA_VERSION = "ml-surrogate-drift-guard-receipt.v1"
DEFAULT_OUT = PRODUCTIZATION / "ml_surrogate_drift_guard_receipt.json"

DEFAULT_DRIFT_MULTIPLIER = 1.5
DRIFT_COMPONENTS = ("max_dcr", "member_story_drift_contribution_pct", "log1p_group_cost_proxy")


def _load(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return dict(json.loads(path.read_text(encoding="utf-8")))
    except json.JSONDecodeError:
        return {}


def _per_component_drift(
    validation_receipt: dict[str, Any],
    live_shadow_metrics: dict[str, float] | None,
    drift_multiplier: float,
) -> list[dict[str, Any]]:
    """Return per-component drift assessment.

    ``live_shadow_metrics`` is a dict with optional keys matching
    ``DRIFT_COMPONENTS``. When absent (e.g. no live shadow inference has
    been run in this CI window), the receipt records
    ``live_value=None, drift_breach=False`` so the guard does not fire on
    missing data alone.
    """
    if not isinstance(validation_receipt, dict):
        return []
    thresholds = validation_receipt.get("thresholds") or {}
    test_p95 = (validation_receipt.get("split_metrics") or {}).get("test") or {}
    test_p95_block = test_p95.get("p95_abs_error") if isinstance(test_p95, dict) else {}
    rows: list[dict[str, Any]] = []
    for component in DRIFT_COMPONENTS:
        threshold_key = f"test_{component}_p95_abs_error"
        threshold = float(thresholds.get(threshold_key) or 0.0)
        baseline = float((test_p95_block or {}).get(component) or 0.0)
        live = None
        if isinstance(live_shadow_metrics, dict) and component in live_shadow_metrics:
            try:
                live = float(live_shadow_metrics[component])
            except (TypeError, ValueError):
                live = None
        breach_threshold = baseline * float(drift_multiplier) if baseline > 0.0 else threshold * float(drift_multiplier)
        drift_breach = bool(
            live is not None and baseline > 0.0 and live > breach_threshold
        )
        rows.append(
            {
                "component": component,
                "threshold": float(threshold),
                "baseline_test_p95": float(baseline),
                "drift_breach_threshold": float(breach_threshold),
                "drift_multiplier": float(drift_multiplier),
                "live_value": live,
                "drift_breach": drift_breach,
            }
        )
    return rows


def build_ml_surrogate_drift_guard_receipt(
    *,
    live_shadow_metrics: dict[str, float] | None = None,
    drift_multiplier: float = DEFAULT_DRIFT_MULTIPLIER,
    output_json: Path | None = None,
) -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc).isoformat()
    gate = probe_ml_surrogate_production_gate()
    validation_receipt_path = (
        gate.get("validation_receipt_path")
        or str(PHASE1 / "release/ml_surrogate/validation_receipt.json")
    )
    ood_gate_path = (
        gate.get("ood_gate_path")
        or str(PHASE1 / "release/ml_surrogate/ood_gate.json")
    )
    solver_fallback_path = (
        gate.get("solver_fallback_receipt_path")
        or str(PHASE1 / "release/ml_surrogate/solver_fallback_receipt.json")
    )
    checkpoint_path = (
        gate.get("checkpoint_path")
        or str(PHASE1 / "release/ml_surrogate/checkpoint.pt")
    )
    validation_receipt = _load(Path(str(validation_receipt_path)))
    ood_gate = _load(Path(str(ood_gate_path)))
    solver_fallback = _load(Path(str(solver_fallback_path)))
    drift_rows = _per_component_drift(validation_receipt, live_shadow_metrics, drift_multiplier)
    breach_count = sum(1 for row in drift_rows if bool(row.get("drift_breach")))
    forced_disabled = bool(gate.get("forced_disabled"))
    production_wired = bool(gate.get("production_ml_wired"))
    if forced_disabled:
        decision = "forced_disabled"
    elif breach_count > 0:
        decision = "disarm_recommended"
    elif not production_wired:
        decision = "not_wired"
    else:
        decision = "armed"
    env_recommendation = {
        "set_disable_env": bool(decision == "disarm_recommended"),
        "env_var": "PHASE1_ML_SURROGATE_DISABLE",
        "env_value": "1",
        "rationale": (
            "One or more drift components exceeded the configured threshold; "
            "set PHASE1_ML_SURROGATE_DISABLE=1 to force disable shadow inference "
            "in the next CI run."
        ),
    }
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "status": "ready" if decision in {"armed", "not_wired"} else "guard_fired",
        "drift_guard_decision": decision,
        "production_ml_wired": production_wired,
        "forced_disabled": forced_disabled,
        "drift_multiplier": float(drift_multiplier),
        "source": {
            "checkpoint_path": str(checkpoint_path),
            "validation_receipt_path": str(validation_receipt_path),
            "ood_gate_path": str(ood_gate_path),
            "solver_fallback_receipt_path": str(solver_fallback_path),
            "live_shadow_metrics_provided": bool(isinstance(live_shadow_metrics, dict)),
        },
        "gate": gate,
        "drift_per_component": drift_rows,
        "drift_breach_count": int(breach_count),
        "env_recommendation": env_recommendation,
        "ood_gate_summary": {
            "ood_pass": bool(ood_gate.get("ood_pass")),
            "status": str(ood_gate.get("status") or ""),
        },
        "solver_fallback_summary": {
            "solver_fallback_verified": bool(solver_fallback.get("solver_fallback_verified")),
            "status": str(solver_fallback.get("status") or ""),
        },
        "claim_boundary": (
            "Drift guard is an honest read-only evaluator of the current production "
            "ML surrogate activation state. It compares the live shadow inference "
            "metric (if provided) against the validated baseline p95, and recommends "
            "disabling via PHASE1_ML_SURROGATE_DISABLE when any component exceeds "
            "the configured threshold. It does not retroactively change any "
            "previously emitted decision; it only emits a receipt describing the "
            "current state and the recommended next action."
        ),
        "blockers": []
        if decision in {"armed", "not_wired"}
        else [f"drift_guard_{decision}"] if decision == "disarm_recommended"
        else ["forced_disabled"],
    }
    if output_json is not None:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live-max-dcr",
        type=float,
        default=None,
        help="Live shadow inference max_dcr value (optional).",
    )
    parser.add_argument(
        "--live-drift-contribution",
        type=float,
        default=None,
        help="Live shadow inference member_story_drift_contribution_pct value (optional).",
    )
    parser.add_argument(
        "--live-group-cost",
        type=float,
        default=None,
        help="Live shadow inference log1p_group_cost_proxy value (optional).",
    )
    parser.add_argument(
        "--drift-multiplier",
        type=float,
        default=DEFAULT_DRIFT_MULTIPLIER,
        help="Drift breach multiplier applied to baseline p95 (default 1.5).",
    )
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    live_metrics: dict[str, float] = {}
    if args.live_max_dcr is not None:
        live_metrics["max_dcr"] = float(args.live_max_dcr)
    if args.live_drift_contribution is not None:
        live_metrics["member_story_drift_contribution_pct"] = float(args.live_drift_contribution)
    if args.live_group_cost is not None:
        live_metrics["log1p_group_cost_proxy"] = float(args.live_group_cost)
    payload = build_ml_surrogate_drift_guard_receipt(
        live_shadow_metrics=live_metrics or None,
        drift_multiplier=float(args.drift_multiplier),
        output_json=args.output_json,
    )
    decision = payload["drift_guard_decision"]
    breach_count = payload["drift_breach_count"]
    print(
        "ml-surrogate-drift-guard: "
        f"{payload['status']} decision={decision} breaches={breach_count} "
        f"wired={payload['production_ml_wired']} "
        f"-> {args.output_json}"
    )
    return 0 if payload.get("status") in {"ready", "guard_fired"} else 3


if __name__ == "__main__":
    raise SystemExit(main())
