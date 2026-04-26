from __future__ import annotations

import json
from pathlib import Path
import subprocess
import zipfile


def test_prepare_midas_binary_archive_adapter(tmp_path: Path) -> None:
    archive = tmp_path / "sample.zip"
    with zipfile.ZipFile(archive, "w") as zip_file:
        zip_file.writestr("house_model.meb", b"binary-data")
        zip_file.writestr("notes.txt", b"ignore-me")

    out_dir = tmp_path / "out"
    report = out_dir / "adapter_manifest.json"
    proc = subprocess.run(
        [
            "python3",
            "implementation/phase1/prepare_midas_binary_archive_adapter.py",
            "--source-id",
            "sample_source",
            "--archive",
            str(archive),
            "--out-dir",
            str(out_dir),
            "--report-out",
            str(report),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["reason_code"] == "PASS"
    assert payload["summary"]["recognized_member_count"] == 1
    assert payload["summary"]["recommended_adapter_family"] == "midas_binary_meb_parser"
    assert payload["summary"]["recommended_parser_script"].endswith("parse_midas_binary_meb_to_json_npz.py")
    assert payload["summary"]["recommended_primary_member"] == "house_model.meb"
    assert "primary_member_magic" in payload["summary"]
    assert "primary_member_probe_ready" in payload["summary"]
    assert payload["members"][0]["extension"] == ".meb"
