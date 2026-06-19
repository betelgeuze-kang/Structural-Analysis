#!/usr/bin/env python3
"""Check Level 3 residual exit criteria from the NDTHA residual gate."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from release_evidence_metadata import release_evidence_metadata  # noqa: E402


SCHEMA_VERSION = "residual-level3-status.v1"
DEFAULT_NDTHA_RESIDUAL_GATE = Path(
    "implementation/phase1/release_evidence/productization/ndtha_residual_gate_report.json"
)
DEFAULT_OUT = Path("implementation/phase1/release_evidence/productization/residual_level3_status.json")
NORMALIZED_RESIDUAL_KEYS = {
    "hard_top_ratio",
    "hard_drift_ratio",
    "hard_max_ratio",
    "recommended_top_ratio",
    "recommended_drift_ratio",
    "recommended_max_ratio",
}


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_float(value: Any, default: float = math.nan) -> float:
    try:
        parsed = float(value)
    except Exception:
        return default
    return parsed if math.isfinite(parsed) else default


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _row_check(row: dict[str, Any], key: str) -> bool:
    return bool(_as_dict(row.get("checks")).get(key, False))


def _normalized_row_pass(row: dict[str, Any]) -> bool:
    normalized = _as_dict(row.get("normalized_residual"))
    return bool(NORMALIZED_RESIDUAL_KEYS <= set(normalized))


def _corrected_state_recompute_row_pass(row: dict[str, Any]) -> bool:
    corrected = _as_dict(row.get("corrected_state_recompute"))
    return bool(
        _row_check(row, "corrected_state_recompute_present")
        and _row_check(row, "corrected_state_recompute_pass")
        and corrected.get("present") is True
        and corrected.get("pass") is True
        and str(corrected.get("source", "") or "").strip()
        and math.isfinite(_as_float(corrected.get("residual_top_displacement_m")))
        and math.isfinite(_as_float(corrected.get("residual_drift_ratio_pct")))
    )


def build_status(
    *,
    ndtha_residual_gate_path: Path = DEFAULT_NDTHA_RESIDUAL_GATE,
    min_recommended_pass_rate: float = 0.95,
    max_fallback_rate: float = 0.05,
    ga_max_fallback_rate: float = 0.01,
    min_solver_raw_ratio: float = 0.95,
) -> dict[str, Any]:
    payload = _load_json(ndtha_residual_gate_path)
    summary = _as_dict(payload.get("summary"))
    checks = _as_dict(payload.get("checks"))
    rows = [row for row in _as_list(payload.get("rows")) if isinstance(row, dict)]
    case_count = _as_int(summary.get("case_count"), len(rows))
    denominator = max(1, case_count)

    hard_pass_count = sum(1 for row in rows if _row_check(row, "hard_pass"))
    recommended_pass_count = sum(1 for row in rows if _row_check(row, "recommended_residual_pass"))
    non_finite_case_ids = [
        str(row.get("case_id", "") or "")
        for row in rows
        if not _row_check(row, "finite_pass")
    ]
    normalized_missing_case_ids = [
        str(row.get("case_id", "") or "")
        for row in rows
        if not _normalized_row_pass(row)
    ]
    fallback_case_ids = [
        str(row.get("case_id", "") or "")
        for row in rows
        if bool(row.get("residual_metric_fallback_used", False))
    ]
    solver_raw_case_ids = [
        str(row.get("case_id", "") or "")
        for row in rows
        if str(row.get("residual_metric_source", "") or "") == "solver_raw"
        and not bool(row.get("residual_metric_fallback_used", False))
    ]
    corrected_missing_case_ids = [
        str(row.get("case_id", "") or "")
        for row in rows
        if not _corrected_state_recompute_row_pass(row)
    ]
    collapse_false_pass_case_ids = [
        str(row.get("case_id", "") or "")
        for row in rows
        if bool(row.get("collapsed", False)) and _row_check(row, "hard_pass")
    ]

    fallback_rate = _as_float(summary.get("fallback_rate"), 1.0)
    solver_raw_ratio = _as_float(summary.get("solver_raw_ratio"), 0.0)
    hard_pass_rate = float(hard_pass_count / denominator)
    recommended_pass_rate = float(recommended_pass_count / denominator)
    row_fallback_rate = float(len(fallback_case_ids) / denominator)
    row_solver_raw_ratio = float(len(solver_raw_case_ids) / denominator)
    solver_control_nonconverged_step_total = _as_int(summary.get("solver_control_nonconverged_step_total"), 0)
    corrected_required = bool(summary.get("corrected_state_recompute_required", False))

    gate_checks = {
        "ndtha_residual_gate_report_present": ndtha_residual_gate_path.exists(),
        "ndtha_residual_gate_contract_pass": bool(payload.get("contract_pass", False)),
        "case_count_present_pass": case_count > 0 and len(rows) == case_count,
        "hard_pass_rate_100pct_pass": hard_pass_rate >= 1.0,
        "recommended_pass_rate_pass": recommended_pass_rate >= min_recommended_pass_rate,
        "strict_recommended_residual_hard_fail_enabled": bool(
            checks.get("strict_recommended_residual_hard_fail_enabled")
            or summary.get("strict_recommended_residual_hard_fail")
        ),
        "strict_recommended_residual_pass": bool(checks.get("strict_recommended_residual_pass", False)),
        "fallback_rate_limited_pass": fallback_rate <= max_fallback_rate
        and row_fallback_rate <= max_fallback_rate,
        "fallback_rate_ga_pass": fallback_rate <= ga_max_fallback_rate
        and row_fallback_rate <= ga_max_fallback_rate,
        "solver_raw_ratio_pass": solver_raw_ratio >= min_solver_raw_ratio
        and row_solver_raw_ratio >= min_solver_raw_ratio,
        "non_finite_residual_zero_pass": not non_finite_case_ids,
        "silent_failure_zero_pass": bool(
            checks.get("ndtha_no_collapse_pass", False)
            and checks.get("solver_control_event_sequence_pass", False)
            and not collapse_false_pass_case_ids
            and solver_control_nonconverged_step_total == 0
        ),
        "normalized_residual_all_rows_pass": not normalized_missing_case_ids and case_count > 0,
        "corrected_state_recompute_required": corrected_required,
        "corrected_state_recompute_all_rows_pass": bool(
            corrected_required and not corrected_missing_case_ids and case_count > 0
        ),
    }
    blockers = [
        *(["ndtha_residual_gate_report_missing"] if not gate_checks["ndtha_residual_gate_report_present"] else []),
        *(["ndtha_residual_gate_not_green"] if not gate_checks["ndtha_residual_gate_contract_pass"] else []),
        *(["residual_case_count_missing_or_mismatched"] if not gate_checks["case_count_present_pass"] else []),
        *(["hard_residual_pass_rate_below_100pct"] if not gate_checks["hard_pass_rate_100pct_pass"] else []),
        *(["recommended_residual_pass_rate_below_target"] if not gate_checks["recommended_pass_rate_pass"] else []),
        *(["strict_recommended_residual_not_hard_fail"] if not gate_checks["strict_recommended_residual_hard_fail_enabled"] else []),
        *(["strict_recommended_residual_failed"] if not gate_checks["strict_recommended_residual_pass"] else []),
        *(["fallback_rate_gt_5pct"] if not gate_checks["fallback_rate_limited_pass"] else []),
        *(["solver_raw_ratio_below_95pct"] if not gate_checks["solver_raw_ratio_pass"] else []),
        *(["non_finite_residual_present"] if not gate_checks["non_finite_residual_zero_pass"] else []),
        *(["silent_failure_or_collapse_false_pass_present"] if not gate_checks["silent_failure_zero_pass"] else []),
        *(["normalized_residual_missing"] if not gate_checks["normalized_residual_all_rows_pass"] else []),
        *(["corrected_state_recompute_missing_or_failed"] if not gate_checks["corrected_state_recompute_all_rows_pass"] else []),
    ]
    status = "ready" if not blockers else "blocked"
    return {
        "schema_version": SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=[ndtha_residual_gate_path],
            reused_evidence=True,
            reuse_policy="status_rebuilt_from_existing_ndtha_residual_gate_report",
        ),
        "status": status,
        "contract_pass": not blockers,
        "reason_code": "PASS" if not blockers else "ERR_RESIDUAL_LEVEL3_INCOMPLETE",
        "ndtha_residual_gate_report": str(ndtha_residual_gate_path),
        "targets": {
            "hard_pass_rate": 1.0,
            "min_recommended_pass_rate": float(min_recommended_pass_rate),
            "max_fallback_rate": float(max_fallback_rate),
            "ga_max_fallback_rate": float(ga_max_fallback_rate),
            "min_solver_raw_ratio": float(min_solver_raw_ratio),
            "non_finite_residual_count": 0,
            "silent_failure_count": 0,
            "normalized_residual_required": True,
            "corrected_state_recompute_required": True,
        },
        "summary": {
            "case_count": case_count,
            "hard_pass_count": hard_pass_count,
            "hard_pass_rate": hard_pass_rate,
            "recommended_pass_count": recommended_pass_count,
            "recommended_pass_rate": recommended_pass_rate,
            "fallback_rate": fallback_rate,
            "row_derived_fallback_rate": row_fallback_rate,
            "fallback_case_count": len(fallback_case_ids),
            "fallback_case_ids": fallback_case_ids,
            "solver_raw_ratio": solver_raw_ratio,
            "row_derived_solver_raw_ratio": row_solver_raw_ratio,
            "solver_raw_case_count": len(solver_raw_case_ids),
            "solver_raw_case_ids": solver_raw_case_ids,
            "non_finite_residual_case_count": len(non_finite_case_ids),
            "non_finite_residual_case_ids": non_finite_case_ids,
            "collapse_false_pass_case_count": len(collapse_false_pass_case_ids),
            "collapse_false_pass_case_ids": collapse_false_pass_case_ids,
            "solver_control_nonconverged_step_total": solver_control_nonconverged_step_total,
            "normalized_residual_missing_case_count": len(normalized_missing_case_ids),
            "normalized_residual_missing_case_ids": normalized_missing_case_ids,
            "corrected_state_recompute_missing_case_count": len(corrected_missing_case_ids),
            "corrected_state_recompute_missing_case_ids": corrected_missing_case_ids,
        },
        "checks": gate_checks,
        "blockers": blockers,
        "claim_boundary": (
            "This Level 3 residual status audits the attached NDTHA residual gate rows only. PASS means "
            "the tracked core NDTHA residual slice satisfies hard, recommended, fallback, solver_raw, "
            "normalized residual, silent-failure, and corrected-state recompute targets. It does not by "
            "itself close independent V&V, benchmark breadth, family validation, GA signoff, or external "
            "customer shadow evidence."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ndtha-residual-gate", type=Path, default=DEFAULT_NDTHA_RESIDUAL_GATE)
    parser.add_argument("--min-recommended-pass-rate", type=float, default=0.95)
    parser.add_argument("--max-fallback-rate", type=float, default=0.05)
    parser.add_argument("--ga-max-fallback-rate", type=float, default=0.01)
    parser.add_argument("--min-solver-raw-ratio", type=float, default=0.95)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    args = parser.parse_args(argv)

    payload = build_status(
        ndtha_residual_gate_path=args.ndtha_residual_gate,
        min_recommended_pass_rate=args.min_recommended_pass_rate,
        max_fallback_rate=args.max_fallback_rate,
        ga_max_fallback_rate=args.ga_max_fallback_rate,
        min_solver_raw_ratio=args.min_solver_raw_ratio,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        summary = payload["summary"]
        print(
            "residual-level3-status: "
            f"{'PASS' if payload['contract_pass'] else 'BLOCKED'} | "
            f"hard={summary['hard_pass_count']}/{summary['case_count']} | "
            f"recommended_rate={summary['recommended_pass_rate']:.3f} | "
            f"fallback_rate={summary['fallback_rate']:.3f} | "
            f"solver_raw_ratio={summary['solver_raw_ratio']:.3f}"
        )
    return 1 if args.fail_blocked and not payload["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
