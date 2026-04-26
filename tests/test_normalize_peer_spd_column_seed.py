from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_normalize_peer_spd_column_seed_builds_hinge_fixture(tmp_path: Path) -> None:
    raw_json = tmp_path / "peer_spd_seed.raw.json"
    raw_json.write_text(
        json.dumps(
            {
                "source_name": "PEER SPD",
                "source_url": "https://peer.berkeley.edu/node/123",
                "specimen": {
                    "specimen_id": "SPD_COL_001",
                    "column_shape": "rectangular",
                    "confinement_type": "tied",
                    "axial_load_ratio": 0.24,
                    "longitudinal_rebar_ratio": 0.021,
                    "transverse_reinforcement_ratio": 0.006,
                    "height_mm": 1800,
                    "section_width_mm": 400,
                    "section_depth_mm": 400,
                },
                "hysteresis": {
                    "drift_ratio": [0.0, 0.005, -0.005, 0.010],
                    "lateral_force_kN": [0.0, 125.0, -120.0, 160.0],
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    out_fixture = tmp_path / "peer_spd_seed.hinge_fixture.json"
    out_manifest = tmp_path / "peer_spd_seed.source_manifest.json"
    out_report = tmp_path / "peer_spd_seed.normalize_report.json"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/normalize_peer_spd_column_seed.py",
            "--seed-id",
            "peer_spd_rc_column_rebar_sensitive_seed_01",
            "--raw-specimen-json",
            str(raw_json),
            "--out-fixture",
            str(out_fixture),
            "--source-manifest-out",
            str(out_manifest),
            "--out-report",
            str(out_report),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    fixture = _load(out_fixture)
    source_manifest = _load(out_manifest)
    report = _load(out_report)
    assert fixture["contract_pass"] is True
    assert fixture["seed_id"] == "peer_spd_rc_column_rebar_sensitive_seed_01"
    assert fixture["holdout_split"] == "val"
    assert fixture["specimen_summary"]["specimen_id"] == "SPD_COL_001"
    assert fixture["hysteresis_summary"]["point_count"] == 4
    assert fixture["hinge_refresh_targets"]["rebar_sensitive_expected"] is True
    assert fixture["source_origin_class"] == "official_external_benchmark"
    assert source_manifest["source_family"] == "peer_spd_column"
    assert source_manifest["holdout_split"] == "val"
    assert report["contract_pass"] is True
    assert report["summary"]["rebar_sensitive_expected"] is True


def test_normalize_peer_spd_column_seed_fails_without_hysteresis(tmp_path: Path) -> None:
    raw_json = tmp_path / "peer_spd_seed.raw.json"
    raw_json.write_text(
        json.dumps(
            {
                "specimen": {
                    "specimen_id": "SPD_COL_002",
                    "column_shape": "rectangular",
                }
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    out_fixture = tmp_path / "peer_spd_seed.hinge_fixture.json"
    out_manifest = tmp_path / "peer_spd_seed.source_manifest.json"
    out_report = tmp_path / "peer_spd_seed.normalize_report.json"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/normalize_peer_spd_column_seed.py",
            "--seed-id",
            "peer_spd_rc_column_rectangular_seed_01",
            "--raw-specimen-json",
            str(raw_json),
            "--out-fixture",
            str(out_fixture),
            "--source-manifest-out",
            str(out_manifest),
            "--out-report",
            str(out_report),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0
    report = _load(out_report)
    assert report["reason_code"] == "ERR_RAW_SPECIMEN_INVALID"
