from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_fetch_peer_spd_properties_tables_from_file_urls(tmp_path: Path) -> None:
    rectangular_src = tmp_path / "rectangular.txt"
    rectangular_src.write_text("No.\tSpecimen Name\n1\tRect A\n", encoding="utf-8")
    spiral_src = tmp_path / "spiral.txt"
    spiral_src.write_text("No.\tSpecimen Name\n10\tSpiral A\n", encoding="utf-8")
    out_dir = tmp_path / "peer_spd"
    out_report = tmp_path / "fetch_report.json"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/fetch_peer_spd_properties_tables.py",
            "--out-dir",
            str(out_dir),
            "--rectangular-url",
            rectangular_src.resolve().as_uri(),
            "--spiral-url",
            spiral_src.resolve().as_uri(),
            "--out-report",
            str(out_report),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    report = _load(out_report)
    assert report["contract_pass"] is True
    assert report["summary"]["table_count"] == 2
    assert (out_dir / "rectangular_properties.txt").exists()
    assert (out_dir / "spiral_properties.txt").exists()

