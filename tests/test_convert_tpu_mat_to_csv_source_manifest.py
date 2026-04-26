from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from scipy.io import savemat


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_convert_tpu_mat_to_csv_reads_mat_path_from_source_manifest(tmp_path: Path) -> None:
    input_mat = tmp_path / "sample.mat"
    savemat(
        input_mat,
        {
            "time": [0.0, 0.5, 1.0],
            "pressure": [[0.11, 0.12], [0.13, 0.14], [0.15, 0.16]],
        },
    )
    source_manifest = tmp_path / "sample.source_manifest.json"
    source_manifest.write_text(
        json.dumps(
            {
                "source_name": "TPU Source Manifest Case",
                "source_origin_class": "official_external_benchmark",
                "data_path": str(input_mat),
            }
        ),
        encoding="utf-8",
    )
    out_csv = tmp_path / "sample.csv"
    out_report = tmp_path / "sample.report.json"

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/convert_tpu_mat_to_csv.py",
            "--source-manifest",
            str(source_manifest),
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

    report = _load(out_report)
    assert out_csv.exists()
    assert report["contract_pass"] is True
    assert report["summary"]["source_name"] == "TPU Source Manifest Case"
    assert report["summary"]["source_origin_class"] == "official_external_benchmark"


def test_convert_tpu_mat_to_csv_fails_for_invalid_source_manifest(tmp_path: Path) -> None:
    source_manifest = tmp_path / "sample.source_manifest.json"
    source_manifest.write_text(json.dumps({"data_path": str(tmp_path / "missing.mat")}), encoding="utf-8")
    out_report = tmp_path / "sample.report.json"

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/convert_tpu_mat_to_csv.py",
            "--source-manifest",
            str(source_manifest),
            "--out-report",
            str(out_report),
        ],
        capture_output=True,
        check=False,
        text=True,
    )
    assert proc.returncode != 0
    report = _load(out_report)
    assert report["reason_code"] == "ERR_SOURCE_MANIFEST_INVALID"
