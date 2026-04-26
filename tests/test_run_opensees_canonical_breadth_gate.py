import json
import subprocess
import sys
from pathlib import Path


def test_run_opensees_canonical_breadth_gate_generates_expected_summary(tmp_path: Path) -> None:
    out = tmp_path / "opensees_canonical_breadth_report.json"
    cmd = [
        sys.executable,
        "implementation/phase1/run_opensees_canonical_breadth_gate.py",
        "--out",
        str(out),
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["reason_code"] == "PASS"
    assert payload["summary"]["canonical_case_count"] >= 7
    assert payload["summary"]["canonical_family_count"] >= 6
    assert payload["summary"]["standalone_parser_ready_case_count"] >= 3
    assert "OpenSees canonical breadth: PASS" in payload["summary_line"]
    assert any(row["case_id"] == "luxinzheng_megatall_model1" for row in payload["rows"])
    assert any(row["case_id"] == "nheri_soft_story_podium" for row in payload["rows"])
