from __future__ import annotations

import csv
import json
from pathlib import Path
import subprocess
import sys

from scipy.io import savemat


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_convert_tpu_mat_to_csv_writes_time_series_csv(tmp_path: Path) -> None:
    input_mat = tmp_path / "sample.mat"
    savemat(
        input_mat,
        {
            "time": [0.0, 0.5, 1.0],
            "pressure": [[0.11, 0.12], [0.13, 0.14], [0.15, 0.16]],
        },
    )
    out_csv = tmp_path / "sample.csv"
    out_report = tmp_path / "sample.report.json"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/convert_tpu_mat_to_csv.py",
            "--input-mat",
            str(input_mat),
            "--dataset-key",
            "pressure",
            "--time-key",
            "time",
            "--out-csv",
            str(out_csv),
            "--out-report",
            str(out_report),
        ],
        capture_output=True,
        check=False,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    with out_csv.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))
    report = _load(out_report)
    assert rows[0] == ["time_s", "signal_01", "signal_02"]
    assert rows[1] == ["0.0", "0.11", "0.12"]
    assert rows[3] == ["1.0", "0.15", "0.16"]
    assert report["contract_pass"] is True
    assert report["summary"]["dataset_name"] == "pressure"
    assert report["summary"]["row_count"] == 3
    assert report["summary"]["has_time_column"] is True
    assert report["summary"]["dt_s"] == 0.5


def test_convert_tpu_mat_to_csv_fails_for_missing_dataset_key(tmp_path: Path) -> None:
    input_mat = tmp_path / "sample.mat"
    savemat(input_mat, {"pressure": [[0.11], [0.13]]})
    out_report = tmp_path / "sample.report.json"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/convert_tpu_mat_to_csv.py",
            "--input-mat",
            str(input_mat),
            "--dataset-key",
            "missing",
            "--out-report",
            str(out_report),
        ],
        capture_output=True,
        check=False,
        text=True,
    )
    assert proc.returncode != 0
    report = _load(out_report)
    assert report["reason_code"] == "ERR_DATASET_NOT_FOUND"


def test_convert_tpu_mat_to_csv_infers_time_from_sample_frequency(tmp_path: Path) -> None:
    input_mat = tmp_path / "sample.mat"
    savemat(
        input_mat,
        {
            "Pressure_coefficients": [[0.11, 0.12], [0.13, 0.14], [0.15, 0.16]],
            "Sample_frequency": 4,
        },
    )
    out_csv = tmp_path / "sample.csv"
    out_report = tmp_path / "sample.report.json"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/convert_tpu_mat_to_csv.py",
            "--input-mat",
            str(input_mat),
            "--out-csv",
            str(out_csv),
            "--out-report",
            str(out_report),
        ],
        capture_output=True,
        check=False,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    with out_csv.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))
    report = _load(out_report)
    assert rows[0] == ["time_s", "signal_01", "signal_02"]
    assert rows[1] == ["0.0", "0.11", "0.12"]
    assert rows[2] == ["0.25", "0.13", "0.14"]
    assert report["summary"]["has_time_column"] is True
    assert report["summary"]["dt_s"] == 0.25
    assert report["summary"]["time_source_mode"] == "scalar_sample_frequency"
