from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_prepare_tpu_hffb_seed_materializes_manifest_from_raw_csv(tmp_path: Path) -> None:
    raw_csv = tmp_path / "tpu_seed.csv"
    raw_csv.write_text(
        "time_s,pressure_cp_01,pressure_cp_02\n"
        "0.0,0.10,0.12\n"
        "0.5,0.15,0.11\n"
        "1.0,0.09,0.10\n",
        encoding="utf-8",
    )
    out_manifest = tmp_path / "tpu_seed.manifest.json"
    out_report = tmp_path / "tpu_seed.report.json"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/prepare_tpu_hffb_seed.py",
            "--seed-id",
            "tpu_hffb_isolated_highrise_seed_01",
            "--raw-wind",
            str(raw_csv),
            "--out-manifest",
            str(out_manifest),
            "--out-report",
            str(out_report),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    manifest = _load(out_manifest)
    report = _load(out_report)
    assert manifest["contract_pass"] is True
    assert manifest["benchmark_seed_id"] == "tpu_hffb_isolated_highrise_seed_01"
    assert manifest["holdout_split"] == "val"
    assert manifest["case_role"] == "baseline_isolated_highrise"
    assert manifest["source_origin_class"] == "official_external_benchmark"
    assert manifest["data_path"] == str(raw_csv)
    assert manifest["dt_s"] == 0.5
    assert manifest["duration_hours"] is not None
    assert len(manifest["sha256"]) == 64
    assert report["contract_pass"] is True
    assert report["summary"]["row_count"] == 3
    assert report["summary"]["signal_column_count"] == 2


def test_prepare_tpu_hffb_seed_fails_for_unknown_seed(tmp_path: Path) -> None:
    raw_csv = tmp_path / "tpu_seed.csv"
    raw_csv.write_text("time_s,pressure_cp_01\n0.0,0.10\n", encoding="utf-8")
    out_manifest = tmp_path / "tpu_seed.manifest.json"
    out_report = tmp_path / "tpu_seed.report.json"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/prepare_tpu_hffb_seed.py",
            "--seed-id",
            "missing_seed",
            "--raw-wind",
            str(raw_csv),
            "--out-manifest",
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
    assert report["reason_code"] == "ERR_SEED_NOT_FOUND"


def test_prepare_tpu_hffb_seed_counts_signal_prefixed_columns(tmp_path: Path) -> None:
    raw_csv = tmp_path / "tpu_seed.csv"
    raw_csv.write_text(
        "signal_01,signal_02,signal_03\n"
        "0.10,0.12,0.14\n"
        "0.15,0.11,0.13\n",
        encoding="utf-8",
    )
    out_manifest = tmp_path / "tpu_seed.manifest.json"
    out_report = tmp_path / "tpu_seed.report.json"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/prepare_tpu_hffb_seed.py",
            "--seed-id",
            "tpu_hffb_interference_highrise_seed_01",
            "--raw-wind",
            str(raw_csv),
            "--out-manifest",
            str(out_manifest),
            "--out-report",
            str(out_report),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    report = _load(out_report)
    assert report["summary"]["signal_column_count"] == 3
