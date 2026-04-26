from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from implementation.phase1.generate_pbd_review_package import _resolve_ndtha_bundle


def _make_rows() -> list[dict]:
    rows: list[dict] = []
    for idx in range(7):
        case_id = f"demo-model-{idx+1:05d}"
        rows.append(
            {
                "case_id": case_id,
                "checks": {"converged_all_steps": True},
                "summary": {"story_count": 3},
                "response": {"story_drift_envelope_pct": [0.2, 0.3, 0.4]},
            }
        )
    return rows


def test_resolve_ndtha_bundle_falls_back_to_latest_valid_response(tmp_path: Path) -> None:
    requested = tmp_path / "nonlinear_ndtha_stress_report.pbd7.json"
    requested_rows = _make_rows()
    requested.write_text(
        json.dumps({"contract_pass": True, "rows": requested_rows}, indent=2),
        encoding="utf-8",
    )
    np.savez_compressed(requested.with_suffix(".response.npz"))

    experiments_root = tmp_path / "experiments" / "by_test" / "nonlinear_ndtha_stress" / "20260322T000000Z" / "artifacts"
    experiments_root.mkdir(parents=True, exist_ok=True)
    fallback_report = experiments_root / requested.name
    fallback_rows = _make_rows()
    fallback_report.write_text(
        json.dumps({"contract_pass": True, "rows": fallback_rows}, indent=2),
        encoding="utf-8",
    )

    payload: dict[str, np.ndarray] = {}
    for idx, row in enumerate(fallback_rows):
        case_id = str(row["case_id"]).replace("-", "_")
        payload[f"{case_id}__top_displacement_m"] = np.linspace(0.0, 0.01 + idx * 0.001, 8, dtype=np.float64)
        payload[f"{case_id}__base_shear_kN"] = np.linspace(0.0, 1200.0 + idx * 10.0, 8, dtype=np.float64)
        payload[f"{case_id}__time_s"] = np.linspace(0.0, 7.0, 8, dtype=np.float64)
    np.savez_compressed(fallback_report.with_suffix(".response.npz"), **payload)

    bundle = _resolve_ndtha_bundle(
        requested,
        earthquake_count=7,
        search_roots=[tmp_path / "experiments" / "by_test" / "nonlinear_ndtha_stress"],
    )

    assert bundle["fallback_used"] is True
    assert Path(str(bundle["resolved_path"])) == fallback_report
    assert Path(str(bundle["resolved_response_npz_path"])) == fallback_report.with_suffix(".response.npz")
    assert bundle["response_coverage_count"] == 7
    assert len(bundle["selected_rows"]) == 7
