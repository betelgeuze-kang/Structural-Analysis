from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "implementation/phase1/check_residual_level3_status.py"
SPEC = importlib.util.spec_from_file_location("check_residual_level3_status", SCRIPT_PATH)
assert SPEC is not None
residual_status = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(residual_status)


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _normalized() -> dict[str, float]:
    return {
        "hard_top_ratio": 0.1,
        "hard_drift_ratio": 0.2,
        "hard_max_ratio": 0.2,
        "recommended_top_ratio": 0.5,
        "recommended_drift_ratio": 0.8,
        "recommended_max_ratio": 0.8,
    }


def _row(case_id: str, *, recommended: bool = True, normalized: bool = True) -> dict[str, object]:
    row = {
        "case_id": case_id,
        "collapsed": False,
        "residual_metric_source": "solver_raw",
        "residual_metric_fallback_used": False,
        "corrected_state_recompute": {
            "present": True,
            "pass": True,
            "source": "solver_corrected_state_recompute",
            "residual_top_displacement_m": 1e-6,
            "residual_drift_ratio_pct": 1e-5,
        },
        "checks": {
            "finite_pass": True,
            "hard_pass": True,
            "recommended_residual_pass": recommended,
            "corrected_state_recompute_present": True,
            "corrected_state_recompute_pass": True,
        },
    }
    if normalized:
        row["normalized_residual"] = _normalized()
    return row


def _gate(rows: list[dict[str, object]], *, fallback_rate: float = 0.0, solver_raw_ratio: float = 1.0) -> dict[str, object]:
    return {
        "contract_pass": True,
        "checks": {
            "ndtha_no_collapse_pass": True,
            "solver_control_event_sequence_pass": True,
            "strict_recommended_residual_hard_fail_enabled": True,
            "strict_recommended_residual_pass": True,
        },
        "summary": {
            "case_count": len(rows),
            "fallback_rate": fallback_rate,
            "solver_raw_ratio": solver_raw_ratio,
            "strict_recommended_residual_hard_fail": True,
            "corrected_state_recompute_required": True,
            "solver_control_nonconverged_step_total": 0,
        },
        "rows": rows,
    }


def test_residual_level3_status_passes_complete_gate(tmp_path: Path) -> None:
    gate = _write_json(
        tmp_path / "ndtha.json",
        _gate([_row("C1"), _row("C2"), _row("C3")]),
    )

    payload = residual_status.build_status(ndtha_residual_gate_path=gate)

    assert payload["contract_pass"] is True
    assert payload["reason_code"] == "PASS"
    assert payload["summary"]["hard_pass_rate"] == 1.0
    assert payload["summary"]["recommended_pass_rate"] == 1.0
    assert payload["checks"]["fallback_rate_limited_pass"] is True
    assert payload["checks"]["solver_raw_ratio_pass"] is True
    assert payload["summary"]["row_derived_fallback_rate"] == 0.0
    assert payload["summary"]["row_derived_solver_raw_ratio"] == 1.0
    assert payload["checks"]["corrected_state_recompute_all_rows_pass"] is True
    assert payload["blockers"] == []


def test_residual_level3_status_blocks_weak_release_evidence(tmp_path: Path) -> None:
    rows = [_row("C1"), _row("C2", recommended=False, normalized=False), _row("C3")]
    rows[2]["checks"]["corrected_state_recompute_pass"] = False
    rows[2]["corrected_state_recompute"]["pass"] = False
    rows[2]["collapsed"] = True
    gate = _write_json(
        tmp_path / "ndtha.json",
        _gate(rows, fallback_rate=0.20, solver_raw_ratio=0.50),
    )

    payload = residual_status.build_status(ndtha_residual_gate_path=gate)

    assert payload["contract_pass"] is False
    assert payload["summary"]["recommended_pass_rate"] == 2 / 3
    assert "recommended_residual_pass_rate_below_target" in payload["blockers"]
    assert "fallback_rate_gt_5pct" in payload["blockers"]
    assert "solver_raw_ratio_below_95pct" in payload["blockers"]
    assert "silent_failure_or_collapse_false_pass_present" in payload["blockers"]
    assert "normalized_residual_missing" in payload["blockers"]
    assert "corrected_state_recompute_missing_or_failed" in payload["blockers"]


def test_residual_level3_status_recomputes_row_source_and_fallback_rates(
    tmp_path: Path,
) -> None:
    rows = [_row("C1"), _row("C2"), _row("C3")]
    rows[1]["residual_metric_source"] = "fallback_corrected"
    rows[1]["residual_metric_fallback_used"] = True
    gate = _write_json(
        tmp_path / "ndtha.json",
        _gate(rows, fallback_rate=0.0, solver_raw_ratio=1.0),
    )

    payload = residual_status.build_status(ndtha_residual_gate_path=gate)

    assert payload["contract_pass"] is False
    assert payload["summary"]["row_derived_fallback_rate"] == 1 / 3
    assert payload["summary"]["row_derived_solver_raw_ratio"] == 2 / 3
    assert payload["summary"]["fallback_case_ids"] == ["C2"]
    assert payload["summary"]["solver_raw_case_ids"] == ["C1", "C3"]
    assert "fallback_rate_gt_5pct" in payload["blockers"]
    assert "solver_raw_ratio_below_95pct" in payload["blockers"]


def test_residual_level3_status_requires_corrected_recompute_payload(
    tmp_path: Path,
) -> None:
    rows = [_row("C1"), _row("C2"), _row("C3")]
    rows[0]["corrected_state_recompute"] = {
        "present": True,
        "pass": True,
        "source": "",
    }
    gate = _write_json(
        tmp_path / "ndtha.json",
        _gate(rows),
    )

    payload = residual_status.build_status(ndtha_residual_gate_path=gate)

    assert payload["contract_pass"] is False
    assert payload["summary"]["corrected_state_recompute_missing_case_ids"] == ["C1"]
    assert "corrected_state_recompute_missing_or_failed" in payload["blockers"]


def test_residual_level3_status_blocks_missing_gate(tmp_path: Path) -> None:
    payload = residual_status.build_status(ndtha_residual_gate_path=tmp_path / "missing.json")

    assert payload["contract_pass"] is False
    assert "ndtha_residual_gate_report_missing" in payload["blockers"]
    assert "residual_case_count_missing_or_mismatched" in payload["blockers"]
