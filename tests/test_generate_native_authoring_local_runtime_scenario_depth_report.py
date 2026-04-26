from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from implementation.phase1.generate_native_authoring_local_runtime_scenario_depth_report import (
    build_native_authoring_local_runtime_scenario_depth_report,
)


SCRIPT = Path("implementation/phase1/generate_native_authoring_local_runtime_scenario_depth_report.py")


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_build_native_authoring_local_runtime_scenario_depth_report_surfaces_deep_local_traces(
    tmp_path: Path,
) -> None:
    solver_session = tmp_path / "sample_tower" / "native_authoring_solver_session.json"
    out = tmp_path / "release" / "authoring" / "portfolio" / "native_authoring_local_runtime_scenario_depth_report.json"
    _write_json(
        solver_session,
        {
            "summary": {"combo_count": 13, "mesh_request_count": 2},
            "mesh_session": {"request_count": 2, "total_estimated_cells": 588},
            "load_combination_session": {
                "runtime_summary": {
                    "authoring_ready": True,
                    "combo_count": 13,
                    "runtime_case_breadth_count": 3,
                    "combo_family_counts": {"rc": 3, "rc+wind": 4, "rc+seismic": 6},
                },
                "editor_seed": {
                    "summary": {
                        "case_count": 4,
                        "combination_count": 13,
                        "stage_count": 2,
                        "graph_edge_count": 33,
                        "limit_state_counts": {"SLS": 5, "ULS": 8},
                    }
                },
                "selected_combination_names": [f"KDS_{index}" for index in range(13)],
                "loadcomb_preview_line_count": 37,
                "omitted_library_combinations": [],
            },
        },
    )

    payload = build_native_authoring_local_runtime_scenario_depth_report(
        portfolio_report={
            "family_rows": [
                {
                    "family_id": "sample_tower",
                    "family_label": "Sample Tower",
                    "project_id": "tower-a",
                    "artifacts": {
                        "solver_session_json": str(solver_session),
                    },
                }
            ]
        },
        runtime_submission_report={
            "family_rows": [
                {
                    "family_id": "sample_tower",
                    "project_id": "tower-a",
                    "runtime_ready": True,
                    "artifacts": {
                        "solver_session_json": str(solver_session),
                    },
                }
            ]
        },
        out=out,
        generated_at="2026-04-21T00:00:00+00:00",
    )

    assert payload["contract_pass"] is True
    assert payload["summary"]["family_count"] == 1
    assert payload["summary"]["depth_ready_family_count"] == 1
    assert payload["summary"]["scenario_ready_family_count"] == 1
    assert payload["summary"]["trace_ready_family_count"] == 1
    assert payload["summary"]["mesh_trace_ready_family_count"] == 1
    assert payload["family_rows"][0]["local_runtime_scenario_depth_status"] == "deep"
    assert "Native authoring local runtime scenario depth: PASS" in payload["summary_line"]


def test_generate_native_authoring_local_runtime_scenario_depth_report_cli(tmp_path: Path) -> None:
    solver_session = tmp_path / "solver_session.json"
    portfolio = tmp_path / "portfolio.json"
    runtime_submission = tmp_path / "runtime_submission.json"
    out = tmp_path / "native_authoring_local_runtime_scenario_depth_report.json"

    _write_json(
        solver_session,
        {
            "summary": {"combo_count": 17, "mesh_request_count": 3},
            "mesh_session": {"request_count": 3, "total_estimated_cells": 804},
            "load_combination_session": {
                "runtime_summary": {
                    "authoring_ready": True,
                    "combo_count": 17,
                    "runtime_case_breadth_count": 3,
                    "combo_family_counts": {"rc": 3, "rc+wind": 4, "rc+seismic": 10},
                },
                "editor_seed": {
                    "summary": {
                        "case_count": 5,
                        "combination_count": 17,
                        "stage_count": 2,
                        "graph_edge_count": 45,
                        "limit_state_counts": {"SLS": 5, "ULS": 12},
                    }
                },
                "selected_combination_names": [f"KDS_{index}" for index in range(17)],
                "loadcomb_preview_line_count": 49,
                "omitted_library_combinations": [],
            },
        },
    )
    _write_json(
        portfolio,
        {
            "family_rows": [
                {
                    "family_id": "rc_wall_core",
                    "project_id": "rc-core-a",
                    "artifacts": {"solver_session_json": str(solver_session)},
                }
            ]
        },
    )
    _write_json(
        runtime_submission,
        {
            "family_rows": [
                {
                    "family_id": "rc_wall_core",
                    "project_id": "rc-core-a",
                    "runtime_ready": True,
                    "artifacts": {"solver_session_json": str(solver_session)},
                }
            ]
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--portfolio-json",
            str(portfolio),
            "--runtime-submission-json",
            str(runtime_submission),
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["summary"]["depth_ready_family_count"] == 1
    assert payload["family_rows"][0]["family_id"] == "rc_wall_core"
    assert "Native authoring local runtime scenario depth: PASS" in proc.stdout
