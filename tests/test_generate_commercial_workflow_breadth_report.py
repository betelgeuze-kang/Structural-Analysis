from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from implementation.phase1.generate_commercial_workflow_breadth_report import (
    build_commercial_workflow_breadth_report,
)


ROOT = Path(__file__).resolve().parents[1]


def test_build_commercial_workflow_breadth_report_surfaces_stage_rail_and_redesign(tmp_path: Path) -> None:
    payload = build_commercial_workflow_breadth_report(
        construction_sequence_gate_report={
            "summary": {
                "max_differential_shortening_mm": 38.33072269918383,
                "stage_count": 24,
            }
        },
        component_dir=tmp_path / "commercialization",
    )

    assert payload["contract_pass"] is True
    assert payload["checks"]["pass"] is True
    assert payload["summary"]["construction_stage_ready"] is True
    assert payload["summary"]["construction_stage_history_snapshot_count"] == 3
    assert payload["summary"]["construction_stage_max_differential_shortening_mm"] == 38.33072269918383
    assert payload["summary"]["rail_tunnel_ready"] is True
    assert payload["summary"]["rail_tunnel_serviceability_status"] == "PASS"
    assert payload["summary"]["rail_tunnel_maintenance_priority"] == "inspect_soon"
    assert payload["summary"]["rail_tunnel_recommended_action_count"] == 4
    assert payload["summary"]["design_redesign_loop_ready"] is True
    assert payload["summary"]["design_report_traceability_ratio"] == 1.0
    assert payload["summary"]["design_report_ng_member_count"] == 4
    assert payload["summary"]["section_optimizer_suggestion_count"] == 5
    assert payload["summary"]["section_optimizer_strengthen_count"] == 4
    assert payload["summary"]["section_optimizer_reduce_count"] == 1
    assert payload["summary"]["governing_clause_count"] == 5
    assert payload["summary_line"].startswith("Commercial workflow breadth: PASS")
    assert Path(payload["artifacts"]["construction_stage_breadth_report_json"]).exists()
    assert Path(payload["artifacts"]["rail_tunnel_breadth_report_json"]).exists()
    assert Path(payload["artifacts"]["design_report_book_json"]).exists()
    assert Path(payload["artifacts"]["section_optimizer_report_json"]).exists()


def test_generate_commercial_workflow_breadth_report_cli_writes_release_artifact(tmp_path: Path) -> None:
    construction_sequence = tmp_path / "construction_sequence_gate_report.json"
    out_path = tmp_path / "commercial_workflow_breadth_report.json"
    component_dir = tmp_path / "commercialization"
    construction_sequence.write_text(
        json.dumps(
            {
                "summary": {
                    "max_differential_shortening_mm": 38.33072269918383,
                    "stage_count": 24,
                }
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_commercial_workflow_breadth_report.py",
            "--construction-sequence-gate-report",
            str(construction_sequence),
            "--component-dir",
            str(component_dir),
            "--out",
            str(out_path),
        ],
        cwd=str(ROOT),
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stderr
    assert "Commercial workflow breadth: PASS" in proc.stdout
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["checks"]["pass"] is True
    assert payload["summary"]["rail_tunnel_maintenance_priority"] == "inspect_soon"
    assert payload["summary"]["section_optimizer_suggestion_count"] == 5
