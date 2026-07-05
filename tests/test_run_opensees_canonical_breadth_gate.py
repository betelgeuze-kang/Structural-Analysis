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
    assert payload["summary"]["canonical_case_count"] >= 8
    assert payload["summary"]["canonical_family_count"] >= 6
    assert payload["summary"]["standalone_parser_ready_case_count"] >= 5
    assert "OpenSees canonical breadth: PASS" in payload["summary_line"]
    rows = {row["case_id"]: row for row in payload["rows"]}
    assert rows["luxinzheng_megatall_model1"]["parser_contract_ready"] is True
    assert rows["luxinzheng_megatall_model2"]["parser_contract_ready"] is True
    assert rows["nheri_soft_story_podium"]["parser_contract_ready"] is True
    assert rows["nheri_soft_story_podium"]["parser_contract"]["parse_counters"]["source_include"] >= 2
