from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def test_probe_tpu_hffb_case_pool_aggregates_fetch_reports(tmp_path: Path) -> None:
    probe_dir = tmp_path / "probes"
    out_report = tmp_path / "probe.json"
    fixture_dir = tmp_path / "fetch_reports"
    pass_report = _write(
        fixture_dir / "case_917.report.json",
        {
            "contract_pass": True,
            "reason_code": "PASS",
            "summary": {
                "case_title": "TPU fixture case 917",
                "mat_link_count": 1,
                "resolved_mat_url": "https://minio.wind.arch.t-kougei.ac.jp/web/media/case/917/time_series_1_0.mat",
                "size_bytes": 128,
            },
        },
    )
    empty_report = _write(
        fixture_dir / "case_1202.report.json",
        {
            "contract_pass": False,
            "reason_code": "ERR_MAT_EMPTY",
            "summary": {
                "case_title": "TPU fixture case 1202",
                "mat_link_count": 1,
                "resolved_mat_url": "https://minio.wind.arch.t-kougei.ac.jp/web/media/case/1202/time_series_1_0.mat",
                "size_bytes": 0,
            },
        },
    )
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/probe_tpu_hffb_case_pool.py",
            "--case-id",
            "917",
            "--case-id",
            "1202",
            "--fetch-report-fixture",
            f"917={pass_report}",
            "--fetch-report-fixture",
            f"1202={empty_report}",
            "--probe-dir",
            str(probe_dir),
            "--out-report",
            str(out_report),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    report = _load(out_report)
    assert report["summary"]["probed_case_count"] == 2
    assert "917" in report["summary"]["usable_case_ids"]
    assert "1202" in report["summary"]["empty_case_ids"]
    by_case = {row["case_id"]: row for row in report["rows"]}
    assert by_case["917"]["contract_pass"] is True
    assert by_case["917"]["fetch_mode"] == "fixture_report"
    assert by_case["1202"]["reason_code"] == "ERR_MAT_EMPTY"
    assert by_case["1202"]["fetch_mode"] == "fixture_report"
    assert report["contract_pass"] is True
    assert report["blockers"] == []


def test_probe_tpu_hffb_case_pool_blocks_when_fetch_fixture_failed(tmp_path: Path) -> None:
    probe_dir = tmp_path / "probes"
    out_report = tmp_path / "probe.json"
    failed_report = _write(
        tmp_path / "fetch_reports" / "case_917.report.json",
        {
            "contract_pass": False,
            "reason_code": "ERR_CASE_PAGE_FETCH",
            "summary": {
                "case_title": "",
                "mat_link_count": 0,
                "resolved_mat_url": "",
                "size_bytes": 0,
            },
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/probe_tpu_hffb_case_pool.py",
            "--case-id",
            "917",
            "--fetch-report-fixture",
            f"917={failed_report}",
            "--probe-dir",
            str(probe_dir),
            "--out-report",
            str(out_report),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    report = _load(out_report)
    assert report["contract_pass"] is False
    assert report["summary"]["pass_count"] == 0
    assert report["summary"]["fetch_error_count"] == 1
    assert report["blockers"] == ["case_917:ERR_CASE_PAGE_FETCH"]
