from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_run_peer_spd_hinge_fixture_regression_passes_with_consistent_fixtures(tmp_path: Path) -> None:
    fixtures = []
    rows = []
    for idx, split in enumerate(("train", "val", "holdout"), start=1):
        fixture = tmp_path / f"seed_{idx}.hinge_fixture.json"
        _write_json(
            fixture,
            {
                "seed_id": f"seed_{idx}",
                "holdout_split": split,
                "contract_pass": True,
                "hysteresis_summary": {"point_count": 500 + idx, "peak_abs_drift_ratio": 0.03 + idx * 0.001},
                "hinge_refresh_targets": {
                    "rebar_sensitive_expected": idx == 1,
                    "confinement_sensitive_expected": idx == 2,
                },
            },
        )
        fixtures.append(fixture)
        rows.append(
            {
                "seed_id": f"seed_{idx}",
                "holdout_split": split,
                "benchmark_ready": True,
                "fixture_path": str(fixture),
                "point_count": 500 + idx,
                "peak_abs_drift_ratio": 0.03 + idx * 0.001,
                "rebar_sensitive_expected": idx == 1,
                "confinement_sensitive_expected": idx == 2,
            }
        )

    registry = tmp_path / "registry.json"
    _write_json(
        registry,
        {
            "summary": {"benchmark_ready_asset_count": 3},
            "rows": rows,
        },
    )
    out = tmp_path / "report.json"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/run_peer_spd_hinge_fixture_regression.py",
            "--asset-registry",
            str(registry),
            "--min-train-count",
            "1",
            "--min-val-count",
            "1",
            "--min-holdout-count",
            "1",
            "--min-rebar-sensitive-count",
            "1",
            "--min-confinement-sensitive-count",
            "1",
            "--min-point-count",
            "400",
            "--min-peak-drift-ratio",
            "0.02",
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["observed"]["fixture_count"] == 3
    assert payload["observed"]["min_point_count"] == 501
    assert payload["observed"]["rebar_sensitive_count"] == 1
    assert payload["observed"]["confinement_sensitive_count"] == 1


def test_run_peer_spd_hinge_fixture_regression_fails_on_missing_fixture(tmp_path: Path) -> None:
    registry = tmp_path / "registry.json"
    _write_json(
        registry,
        {
            "summary": {"benchmark_ready_asset_count": 1},
            "rows": [
                {
                    "seed_id": "seed_1",
                    "holdout_split": "train",
                    "benchmark_ready": True,
                    "fixture_path": str(tmp_path / "missing.hinge_fixture.json"),
                    "point_count": 500,
                    "peak_abs_drift_ratio": 0.03,
                    "rebar_sensitive_expected": False,
                    "confinement_sensitive_expected": False,
                }
            ],
        },
    )
    out = tmp_path / "report.json"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/run_peer_spd_hinge_fixture_regression.py",
            "--asset-registry",
            str(registry),
            "--min-train-count",
            "1",
            "--min-val-count",
            "0",
            "--min-holdout-count",
            "0",
            "--min-rebar-sensitive-count",
            "0",
            "--min-confinement-sensitive-count",
            "0",
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["reason_code"] == "ERR_FIXTURE_CONTRACT"
    assert payload["observed"]["missing_fixture_count"] == 1
