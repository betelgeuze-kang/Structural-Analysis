from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "build_core_family_p95_report.py"
SPEC = importlib.util.spec_from_file_location("build_core_family_p95_report", SCRIPT_PATH)
assert SPEC is not None
build_core_family_p95_report = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(build_core_family_p95_report)


def _write(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _comparison(path: Path, drift_preds: list[float]) -> Path:
    rows = []
    for idx, pred in enumerate(drift_preds, start=1):
        rows.append(
            {
                "case_id": f"case-{idx}",
                "metrics": {
                    "drift_ratio_pct": {"hf": 2.0, "topk_pred": pred},
                    "base_shear_kN": {"hf": 1000.0, "topk_pred": 1005.0},
                    "buckling_factor": {"hf": 2.5, "topk_pred": 2.48},
                },
            }
        )
    return _write(path, {"rows": rows})


def test_core_family_p95_report_uses_comparison_rows_and_passes_threshold(tmp_path: Path) -> None:
    comparison = _comparison(tmp_path / "cmp.json", [2.01, 2.02, 2.03, 2.04])
    commercial = _write(
        tmp_path / "commercial.json",
        {
            "contract_pass": True,
            "model_rows": [
                {
                    "model_id": "family_a",
                    "source_provenance": {"source_families": ["family_a"]},
                    "reports": {"comparison": str(comparison)},
                    "metrics": {"high_noise_drift_error_pct_p95": 12.0},
                }
            ],
        },
    )

    payload = build_core_family_p95_report.build_report(
        commercial_readiness_path=commercial,
        max_p95_error_pct=5.0,
    )

    assert payload["contract_pass"] is True
    assert payload["checks"]["noise_robustness_metrics_excluded"] is True
    assert payload["summary"]["family_count"] == 1
    assert payload["summary"]["max_family_p95_error_pct"] <= 2.000001


def test_core_family_p95_report_blocks_family_above_threshold(tmp_path: Path) -> None:
    comparison = _comparison(tmp_path / "cmp.json", [2.0, 2.4, 2.5, 2.6])
    commercial = _write(
        tmp_path / "commercial.json",
        {
            "contract_pass": True,
            "model_rows": [
                {
                    "model_id": "family_a",
                    "reports": {"comparison": str(comparison)},
                }
            ],
        },
    )

    payload = build_core_family_p95_report.build_report(
        commercial_readiness_path=commercial,
        max_p95_error_pct=5.0,
    )

    assert payload["contract_pass"] is False
    assert "family_p95_error_limited_pass" in payload["blockers"]
