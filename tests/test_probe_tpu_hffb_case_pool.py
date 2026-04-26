from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_probe_tpu_hffb_case_pool_aggregates_fetch_reports(tmp_path: Path) -> None:
    probe_dir = tmp_path / "probes"
    out_report = tmp_path / "probe.json"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/probe_tpu_hffb_case_pool.py",
            "--case-id",
            "917",
            "--case-id",
            "1202",
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
    assert by_case["1202"]["reason_code"] == "ERR_MAT_EMPTY"

