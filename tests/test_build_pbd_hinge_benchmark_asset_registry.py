from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_build_pbd_hinge_benchmark_asset_registry(tmp_path: Path) -> None:
    fixture = tmp_path / "fixture.json"
    fixture.write_text(
        json.dumps(
            {
                "contract_pass": True,
                "holdout_split": "val",
                "source_origin_class": "official_external_benchmark",
                "specimen_summary": {"specimen_id": "SPD-1"},
                "hysteresis_summary": {"point_count": 4, "peak_abs_drift_ratio": 0.03, "peak_abs_lateral_force_kN": 120.0},
                "hinge_refresh_targets": {"rebar_sensitive_expected": True, "axial_load_sensitive_expected": False, "confinement_sensitive_expected": True},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    source_manifest = tmp_path / "source_manifest.json"
    source_manifest.write_text(json.dumps({"source_origin_class": "official_external_benchmark"}), encoding="utf-8")
    seed_manifest = tmp_path / "seed_manifest.json"
    seed_manifest.write_text(
        json.dumps(
            {
                "seed_cases": [
                    {
                        "seed_id": "seed_01",
                        "holdout_split": "val",
                        "expected_local_targets": {
                            "raw_json": str(tmp_path / "raw.json"),
                            "hinge_fixture": str(fixture),
                            "source_manifest": str(source_manifest),
                        },
                    }
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    materialize_report = tmp_path / "materialize_report.json"
    materialize_report.write_text(json.dumps({"steps": {"normalize": [{"returncode": 0}]}}), encoding="utf-8")
    out = tmp_path / "registry.json"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/build_pbd_hinge_benchmark_asset_registry.py",
            "--seed-manifest",
            str(seed_manifest),
            "--materialize-report",
            str(materialize_report),
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    registry = _load(out)
    assert registry["summary"]["benchmark_ready_asset_count"] == 1
    assert registry["summary"]["rebar_sensitive_count"] == 1
    assert registry["summary"]["confinement_sensitive_count"] == 1
