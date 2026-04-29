from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


SCRIPT = Path("implementation/phase1/generate_native_authoring_draft_pipeline.py")


def test_generate_native_authoring_draft_pipeline_cli_materializes_workspace_and_solver(tmp_path: Path) -> None:
    draft_json = tmp_path / "native_authoring_workspace_draft.json"
    workspace_out = tmp_path / "native_authoring_workspace_summary.json"
    solver_out = tmp_path / "native_authoring_solver_session.json"
    loadcomb_out = tmp_path / "native_authoring_solver_session.loadcomb_preview.mgt"
    out = tmp_path / "native_authoring_draft_pipeline.json"
    draft_json.write_text(
        json.dumps(
            {
                "format": "native-authoring-workspace-draft",
                "version": 1,
                "authoring_controls": {
                    "story_count": 8,
                    "bay_count": 5,
                    "floor_height_m": 3.2,
                    "load_pattern_count": 8,
                    "section_id": "cft_box_700x700",
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--out",
            str(out),
            "--workspace-out",
            str(workspace_out),
            "--solver-out",
            str(solver_out),
            "--loadcomb-out",
            str(loadcomb_out),
            "--draft-json",
            str(draft_json),
            "--generated-at",
            "2026-04-19T09:00:00+00:00",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stderr
    pipeline_payload = json.loads(out.read_text(encoding="utf-8"))
    workspace_payload = json.loads(workspace_out.read_text(encoding="utf-8"))
    solver_payload = json.loads(solver_out.read_text(encoding="utf-8"))
    loadcomb_text = loadcomb_out.read_text(encoding="utf-8")

    assert pipeline_payload["generated_at"] == "2026-04-19T09:00:00+00:00"
    assert pipeline_payload["contract_pass"] is True
    assert pipeline_payload["authoring_controls"] == {
        "family_id": "sample_tower",
        "story_count": 8,
        "bay_count": 5,
        "floor_height_m": 3.2,
        "load_pattern_count": 8,
        "section_id": "cft_box_700x700",
    }
    assert pipeline_payload["workspace_summary"]["story_count"] == 8
    assert pipeline_payload["solver_session"]["mesh_request_count"] == 2
    assert pipeline_payload["solver_session"]["combo_count"] == 23
    assert workspace_payload["summary"]["story_count"] == 8
    assert workspace_payload["summary"]["member_count"] == 88
    assert workspace_payload["editor_controls"]["default_section_id"] == "cft_box_700x700"
    assert solver_payload["summary"]["story_count"] == 8
    assert solver_payload["summary"]["combo_count"] == 23
    assert solver_payload["authoring_controls"]["section_id"] == "cft_box_700x700"
    assert loadcomb_text.startswith("*LOADCOMB\n")
    assert "NAME=KDS_SLS_5_EY+, GEN, SLS" in loadcomb_text


def test_generate_native_authoring_draft_pipeline_cli_accepts_family_id_override(tmp_path: Path) -> None:
    workspace_out = tmp_path / "native_authoring_workspace_summary.json"
    solver_out = tmp_path / "native_authoring_solver_session.json"
    loadcomb_out = tmp_path / "native_authoring_solver_session.loadcomb_preview.mgt"
    out = tmp_path / "native_authoring_draft_pipeline.json"

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--out",
            str(out),
            "--workspace-out",
            str(workspace_out),
            "--solver-out",
            str(solver_out),
            "--loadcomb-out",
            str(loadcomb_out),
            "--family-id",
            "steel_braced_frame",
            "--story-count",
            "6",
            "--bay-count",
            "4",
            "--load-pattern-count",
            "6",
            "--generated-at",
            "2026-04-19T09:05:00+00:00",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stderr
    pipeline_payload = json.loads(out.read_text(encoding="utf-8"))
    workspace_payload = json.loads(workspace_out.read_text(encoding="utf-8"))
    solver_payload = json.loads(solver_out.read_text(encoding="utf-8"))

    assert pipeline_payload["generated_at"] == "2026-04-19T09:05:00+00:00"
    assert pipeline_payload["contract_pass"] is True
    assert pipeline_payload["authoring_controls"]["family_id"] == "steel_braced_frame"
    assert workspace_payload["authoring_controls"]["family_id"] == "steel_braced_frame"
    assert workspace_payload["summary"]["member_count"] == 126
    assert solver_payload["authoring_controls"]["family_id"] == "steel_braced_frame"
    assert solver_payload["summary"]["combo_count"] == 23
