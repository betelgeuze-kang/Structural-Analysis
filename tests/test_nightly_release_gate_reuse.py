from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from implementation.phase1 import run_nightly_release_gate as nightly


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_report_matches_command_inputs_reuses_fresh_report(tmp_path: Path) -> None:
    report_path = tmp_path / "nightly_report.json"
    producer_script = tmp_path / "producer.py"
    producer_script.write_text("print('ok')\n", encoding="utf-8")

    cmd = [
        sys.executable,
        str(producer_script),
        "--foo",
        "bar",
        "--flag",
        "--no-baz",
        "--out",
        str(report_path),
    ]
    _write_json(
        report_path,
        {
            "contract_pass": True,
            "inputs": {
                "foo": "bar",
                "flag": True,
                "baz": False,
                "out": str(report_path),
            },
        },
    )

    report_mtime = report_path.stat().st_mtime
    producer_mtime = producer_script.stat().st_mtime
    if producer_mtime > report_mtime:
        report_path.touch()

    assert nightly._report_matches_command_inputs(report_path, cmd) is True

    producer_script.write_text("print('changed')\n", encoding="utf-8")
    future = max(report_path.stat().st_mtime, producer_script.stat().st_mtime) + 5.0
    os.utime(producer_script, (future, future))
    assert nightly._report_matches_command_inputs(report_path, cmd) is False


def test_report_matches_command_inputs_rejects_contract_fail(tmp_path: Path) -> None:
    report_path = tmp_path / "nightly_report.json"
    producer_script = tmp_path / "producer.py"
    producer_script.write_text("print('ok')\n", encoding="utf-8")
    _write_json(
        report_path,
        {
            "contract_pass": False,
            "inputs": {"foo": "bar"},
        },
    )

    cmd = [sys.executable, str(producer_script), "--foo", "bar", "--out", str(report_path)]
    assert nightly._report_matches_command_inputs(report_path, cmd) is False
