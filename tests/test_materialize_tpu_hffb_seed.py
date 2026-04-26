from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from scipy.io import savemat


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_materialize_tpu_hffb_seed_runs_fetch_convert_prepare_chain(tmp_path: Path) -> None:
    case_html = tmp_path / "case.html"
    case_html.write_text(
        "<html><head><title>TPU Materialize Case</title></head><body></body></html>",
        encoding="utf-8",
    )
    input_mat = tmp_path / "seed.mat"
    savemat(
        input_mat,
        {
            "time": [0.0, 0.5, 1.0],
            "pressure": [[0.11, 0.12], [0.13, 0.14], [0.15, 0.16]],
        },
    )
    out_dir = tmp_path / "materialized"
    out_report = tmp_path / "materialize.report.json"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/materialize_tpu_hffb_seed.py",
            "--seed-id",
            "tpu_hffb_isolated_highrise_seed_01",
            "--case-page-html",
            str(case_html),
            "--mat-url",
            str(input_mat),
            "--dataset-key",
            "pressure",
            "--time-key",
            "time",
            "--out-dir",
            str(out_dir),
            "--out-report",
            str(out_report),
        ],
        capture_output=True,
        check=False,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    report = _load(out_report)
    manifest = _load(out_dir / "tpu_hffb_isolated_highrise_seed_01.source_manifest.json")
    assert report["contract_pass"] is True
    assert report["steps"]["fetch"]["returncode"] == 0
    assert report["steps"]["convert"]["returncode"] == 0
    assert report["steps"]["prepare"]["returncode"] == 0
    assert manifest["contract_pass"] is True
    assert manifest["benchmark_seed_id"] == "tpu_hffb_isolated_highrise_seed_01"
    assert manifest["source_name"] == "TPU Materialize Case"
    assert Path(report["artifacts"]["fetched_mat"]).exists()
    assert Path(report["artifacts"]["out_csv"]).exists()


def test_materialize_tpu_hffb_seed_reports_fetch_failure(tmp_path: Path) -> None:
    out_report = tmp_path / "materialize.report.json"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/materialize_tpu_hffb_seed.py",
            "--seed-id",
            "tpu_hffb_isolated_highrise_seed_01",
            "--case-page-html",
            str(tmp_path / "missing.html"),
            "--out-report",
            str(out_report),
        ],
        capture_output=True,
        check=False,
        text=True,
    )
    assert proc.returncode != 0
    report = _load(out_report)
    assert report["reason_code"] == "ERR_FETCH_STEP"
    assert report["steps"]["fetch"]["returncode"] != 0
