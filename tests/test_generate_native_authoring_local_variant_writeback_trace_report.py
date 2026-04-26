from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from implementation.phase1.generate_native_authoring_local_variant_writeback_trace_report import (
    build_native_authoring_local_variant_writeback_trace_report,
)


SCRIPT = Path("implementation/phase1/generate_native_authoring_local_variant_writeback_trace_report.py")


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def _workspace_payload(family_id: str) -> dict:
    return {
        "contract_pass": True,
        "summary": {
            "native_authoring_ready": True,
            "load_pattern_count": 6,
            "section_usage_counts": {
                "deck_beam_500x250": 12,
                "rc_column_700x700": 18,
                "steel_h_600x200": 24,
            },
            "member_type_counts": {
                "beam": 12,
                "column": 18,
                "slab": 12,
            },
        },
        "selected_family": {
            "family_id": family_id,
            "label": family_id.replace("_", " ").title(),
        },
        "authoring_controls": {
            "family_id": family_id,
            "section_palette": [
                "steel_h_600x200",
                "steel_box_400x400x16",
                "rc_column_700x700",
                "deck_beam_500x250",
            ],
        },
        "editor_controls": {
            "family_palette": [
                {"family_id": "sample_tower"},
                {"family_id": "steel_braced_frame"},
                {"family_id": "rc_wall_core"},
                {"family_id": "composite_podium"},
            ],
            "section_palette": [
                "steel_h_600x200",
                "steel_box_400x400x16",
                "rc_column_700x700",
                "deck_beam_500x250",
            ],
        },
    }


def _solver_payload(*, combo_count: int, omitted_count: int = 0) -> dict:
    return {
        "contract_pass": True,
        "summary": {
            "session_ready": True,
            "combo_count": combo_count,
            "load_case_count": 6,
            "mesh_request_count": 3,
        },
        "mesh_session": {
            "request_count": 3,
            "total_estimated_cells": 804,
        },
        "load_combination_session": {
            "runtime_summary": {
                "authoring_ready": True,
                "combo_count": combo_count,
                "runtime_case_count": 6,
                "combo_family_counts": {
                    "gravity": 4,
                    "wind": 7,
                    "seismic": 6,
                },
            },
            "editor_seed": {
                "summary": {
                    "limit_state_counts": {
                        "SLS": 7,
                        "ULS": 10,
                    }
                }
            },
            "selected_combination_names": [f"KDS_{index}" for index in range(combo_count)],
            "omitted_library_combinations": [
                {"name": f"optional_{index}"} for index in range(omitted_count)
            ],
        },
    }


def _family_row(
    tmp_path: Path,
    *,
    family_id: str,
    project_id: str,
    project_name: str,
    combo_count: int,
    omitted_count: int = 0,
) -> dict:
    family_dir = tmp_path / family_id
    workspace_summary = family_dir / "native_authoring_workspace_summary.json"
    solver_session = family_dir / "native_authoring_solver_session.json"
    project_registry = family_dir / "native_authoring_project_registry.json"
    project_package = family_dir / "native_authoring_project_package.zip"
    project_signature = family_dir / "native_authoring_project_registry.signature.b64"

    _write_json(workspace_summary, _workspace_payload(family_id))
    _write_json(solver_session, _solver_payload(combo_count=combo_count, omitted_count=omitted_count))
    _write_json(project_registry, {"summary": {"approval_count": 2}})
    _write_bytes(project_package, b"pk")
    _write_text(project_signature, "sig\n")

    return {
        "family_id": family_id,
        "family_label": family_id.replace("_", " ").title(),
        "project_id": project_id,
        "project_name": project_name,
        "registry_ready": True,
        "signature_verified": True,
        "approval_count": 2,
        "snapshot_count": 3,
        "package_bytes": 4096,
        "artifacts": {
            "workspace_summary_json": str(workspace_summary),
            "solver_session_json": str(solver_session),
            "project_registry_json": str(project_registry),
            "project_package_zip": str(project_package),
            "project_registry_signature": str(project_signature),
        },
    }


def test_build_native_authoring_local_variant_writeback_trace_report_is_deterministic(
    tmp_path: Path,
) -> None:
    out = tmp_path / "release" / "authoring" / "portfolio" / "native_authoring_local_variant_writeback_trace_report.json"
    family_rows = [
        _family_row(
            tmp_path,
            family_id="steel_braced_frame",
            project_id="frame-b",
            project_name="Frame B",
            combo_count=23,
        ),
        _family_row(
            tmp_path,
            family_id="sample_tower",
            project_id="tower-a",
            project_name="Tower A",
            combo_count=17,
            omitted_count=1,
        ),
    ]

    payload_a = build_native_authoring_local_variant_writeback_trace_report(
        family_rows=family_rows,
        out=out,
        generated_at="2026-04-21T01:00:00+00:00",
    )
    payload_b = build_native_authoring_local_variant_writeback_trace_report(
        family_rows=family_rows,
        out=out,
        generated_at="2026-04-21T01:00:00+00:00",
    )

    assert payload_a == payload_b
    assert payload_a["contract_pass"] is True
    assert payload_a["summary"]["family_count"] == 2
    assert payload_a["summary"]["deep_ready_family_count"] == 2
    assert payload_a["summary"]["workspace_variant_ready_family_count"] == 2
    assert payload_a["summary"]["solver_variant_ready_family_count"] == 2
    assert payload_a["summary"]["writeback_trace_ready_family_count"] == 2
    assert payload_a["summary"]["signed_writeback_family_count"] == 2
    assert payload_a["summary"]["omitted_library_family_count"] == 1
    assert payload_a["family_rows"][0]["family_id"] == "sample_tower"
    assert payload_a["family_rows"][0]["local_variant_writeback_trace_status"] == "deep"
    assert payload_a["family_rows"][0]["workspace_active_family_count"] == 3
    assert payload_a["family_rows"][0]["solver_combo_family_count"] == 3
    assert "Native authoring local variant/writeback trace: PASS" in payload_a["summary_line"]


def test_generate_native_authoring_local_variant_writeback_trace_report_cli(tmp_path: Path) -> None:
    portfolio = tmp_path / "native_authoring_ops_portfolio.json"
    out = tmp_path / "native_authoring_local_variant_writeback_trace_report.json"
    family_row = _family_row(
        tmp_path,
        family_id="composite_podium",
        project_id="podium-c",
        project_name="Podium C",
        combo_count=18,
    )
    _write_json(portfolio, {"family_rows": [family_row]})

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--portfolio-json",
            str(portfolio),
            "--generated-at",
            "2026-04-21T01:30:00+00:00",
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["generated_at"] == "2026-04-21T01:30:00+00:00"
    assert payload["contract_pass"] is True
    assert payload["summary"]["deep_ready_family_count"] == 1
    assert payload["summary"]["writeback_trace_ready_family_count"] == 1
    assert payload["family_rows"][0]["family_id"] == "composite_podium"
    assert "Native authoring local variant/writeback trace: PASS" in proc.stdout
