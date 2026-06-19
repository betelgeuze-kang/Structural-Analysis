from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


SCRIPT = Path("implementation/phase1/run_midas_interoperability_gate.py")


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_model_json(
    path: Path,
    *,
    seed_limitations: list[str] | None = None,
    pattern_limitations: list[str] | None = None,
    recovery_mode: str = "",
    loads: dict | None = None,
    bridge_exact_review_id_count: int = 12,
    bridge_heuristic_review_id_count: int = 0,
    bridge_exact_row_provenance_count: int = 1056,
    bridge_heuristic_row_provenance_count: int = 0,
) -> None:
    metadata = {
        "load_combination_editor_seed": {
            "seed_kind": "midas_load_combination_editor_seed",
            "provenance": "parser_additive_metadata",
            "limitations": list(seed_limitations or []),
            "summary": {
                "case_count": 2,
                "combination_count": 8,
                "graph_edge_count": 15,
            },
        },
        "load_pattern_library": {
            "provenance": "parser_additive_metadata",
            "limitations": list(pattern_limitations or []),
            "summary": {
                "pattern_count": 2,
                "primitive_count": 5,
            },
        },
        "kds_geometry_bridge": {
            "provenance": "kds_codecheck_bridge_metadata",
            "registry_source_label": "merged_registry",
            "summary": {
                "exact_mapped_review_id_count": bridge_exact_review_id_count,
                "heuristic_mapped_review_id_count": bridge_heuristic_review_id_count,
                "exact_mapped_row_provenance_count": bridge_exact_row_provenance_count,
                "heuristic_mapped_row_provenance_count": bridge_heuristic_row_provenance_count,
            },
        },
    }
    if recovery_mode:
        metadata["load_contract_recovery"] = {"mode": recovery_mode}
    model_payload = {"metadata": metadata}
    if loads is not None:
        model_payload["loads"] = loads
    _write_json(path, {"model": model_payload})


def _write_export_report(path: Path) -> None:
    _write_json(
        path,
        {
            "contract_pass": True,
            "summary": {
                "loadcomb_preview_exists": True,
                "loadcomb_roundtrip_pass": True,
                "loadcomb_roundtrip_report_exists": True,
                "loadcomb_combo_count": 8,
            },
        },
    )


def _write_roundtrip_report(
    path: Path,
    *,
    source_model_json: Path,
    exact_name_coverage: float = 1.0,
    exact_entry_row_coverage: float = 1.0,
    exact_header_coverage: float = 1.0,
    exact_factor_map_coverage: float = 1.0,
    exact_expression_coverage: float = 1.0,
) -> None:
    _write_json(
        path,
        {
            "pass": True,
            "exact_name_coverage": exact_name_coverage,
            "exact_entry_row_coverage": exact_entry_row_coverage,
            "exact_header_coverage": exact_header_coverage,
            "exact_factor_map_coverage": exact_factor_map_coverage,
            "exact_expression_coverage": exact_expression_coverage,
            "raw_combo_count": 8,
            "export_combo_count": 8,
            "source_model_json": str(source_model_json),
        },
    )


def test_midas_interoperability_gate_passes_on_current_release_artifacts(tmp_path: Path) -> None:
    out_path = tmp_path / "midas_interoperability_gate_report.json"

    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--out", str(out_path)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["reason_code"] == "PASS"
    assert payload["checks"]["model_artifacts_present_pass"] is True
    assert payload["checks"]["editor_seed_present_pass"] is True
    assert payload["checks"]["load_pattern_library_present_pass"] is True
    assert payload["checks"]["export_report_pass"] is True
    assert payload["checks"]["loadcomb_preview_files_pass"] is True
    assert payload["checks"]["loadcomb_roundtrip_reports_pass"] is True
    assert payload["summary"]["loadcomb_preview_exists"] is True
    assert payload["summary"]["loadcomb_roundtrip_pass"] is True
    assert payload["summary"]["loadcomb_combo_count"] == 8
    assert payload["summary"]["preview_file_count"] == 3
    assert payload["summary"]["preview_file_present_count"] == 3
    assert payload["summary"]["roundtrip_report_count"] == 3
    assert payload["summary"]["roundtrip_report_pass_count"] == 3
    assert payload["summary"]["roundtrip_exact_entry_row_coverage_min"] == 1.0
    assert payload["summary"]["roundtrip_exact_header_coverage_min"] == 1.0
    assert payload["summary"]["roundtrip_exact_factor_map_coverage_min"] == 1.0
    assert payload["summary"]["loadcomb_exact_roundtrip_pass"] is True
    assert payload["summary"]["bounded_subset_mode"] == "full_exact_roundtrip"
    assert payload["summary"]["heuristic_raw_recovery_model_count"] == 0
    assert payload["summary"]["structured_loads_contract_present_count"] == 3
    assert payload["summary"]["kds_geometry_bridge_exact_review_id_total"] == 24
    assert payload["summary"]["kds_geometry_bridge_heuristic_review_id_total"] == 0
    assert payload["summary"]["exact_roundtrip_closure_pass"] is True
    assert payload["summary"]["exact_roundtrip_closure_status"] == "closed"
    assert payload["summary"]["exact_roundtrip_closure_blockers"] == []
    assert payload["summary"]["remaining_limits"] == []
    assert "heuristic_raw_loadcomb_recovery" not in payload["summary"]["exact_roundtrip_closure_blockers"]
    assert "primitive_load_cards_pending" not in payload["summary"]["remaining_limits"]
    assert "normalized_factor_maps_pending" not in payload["summary"]["remaining_limits"]
    assert "solver_ready_reconstruction_pending" not in payload["summary"]["remaining_limits"]
    assert "summary_grade_preview_only" not in payload["summary"]["remaining_limits"]
    assert payload["summary_line"].startswith("MIDAS interoperability/export readiness: PASS")
    assert "preview=3/3" in payload["summary_line"]
    assert "roundtrip=3/3" in payload["summary_line"]
    assert "bounded_subset=full_exact_roundtrip" in payload["summary_line"]
    assert "limits=none" in payload["summary_line"]
    assert "exact_closure=closed" in payload["summary_line"]


def test_midas_interoperability_gate_flags_missing_preview_as_failure(tmp_path: Path) -> None:
    out_path = tmp_path / "midas_interoperability_gate_report.json"
    missing_preview = tmp_path / "missing_preview.mgt"

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--loadcomb-preview-files",
            str(missing_preview),
            "--out",
            str(out_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0

    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is False
    assert payload["reason_code"] == "ERR_INTEROPERABILITY_FAIL"
    assert payload["checks"]["loadcomb_preview_files_pass"] is False
    assert payload["summary"]["preview_file_present_count"] == 0
    assert payload["summary_line"].startswith("MIDAS interoperability/export readiness: CHECK")


def test_midas_interoperability_gate_marks_full_exact_roundtrip_when_no_blockers(tmp_path: Path) -> None:
    out_path = tmp_path / "midas_interoperability_gate_report.json"
    model_path = tmp_path / "model.json"
    export_report_path = tmp_path / "export_report.json"
    roundtrip_report_path = tmp_path / "roundtrip_report.json"
    preview_path = tmp_path / "preview.mgt"

    _write_model_json(model_path)
    _write_export_report(export_report_path)
    _write_roundtrip_report(roundtrip_report_path, source_model_json=model_path)
    preview_path.write_text("*LOADCOMB\n", encoding="utf-8")

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--model-jsons",
            str(model_path),
            "--export-report",
            str(export_report_path),
            "--loadcomb-roundtrip-reports",
            str(roundtrip_report_path),
            "--loadcomb-preview-files",
            str(preview_path),
            "--out",
            str(out_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["summary"]["bounded_subset_mode"] == "full_exact_roundtrip"
    assert payload["summary"]["loadcomb_exact_roundtrip_pass"] is True
    assert payload["summary"]["exact_roundtrip_closure_pass"] is True
    assert payload["summary"]["exact_roundtrip_closure_status"] == "closed"
    assert payload["summary"]["exact_roundtrip_closure_blockers"] == []
    assert "exact_closure=closed" in payload["summary_line"]


def test_midas_interoperability_gate_surfaces_heuristic_geometry_bridge_mode(tmp_path: Path) -> None:
    out_path = tmp_path / "midas_interoperability_gate_report.json"
    model_path = tmp_path / "model.json"
    export_report_path = tmp_path / "export_report.json"
    roundtrip_report_path = tmp_path / "roundtrip_report.json"
    preview_path = tmp_path / "preview.mgt"

    _write_model_json(
        model_path,
        bridge_exact_review_id_count=0,
        bridge_heuristic_review_id_count=12,
        bridge_exact_row_provenance_count=0,
        bridge_heuristic_row_provenance_count=1056,
    )
    _write_export_report(export_report_path)
    _write_roundtrip_report(roundtrip_report_path, source_model_json=model_path)
    preview_path.write_text("*LOADCOMB\n", encoding="utf-8")

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--model-jsons",
            str(model_path),
            "--export-report",
            str(export_report_path),
            "--loadcomb-roundtrip-reports",
            str(roundtrip_report_path),
            "--loadcomb-preview-files",
            str(preview_path),
            "--out",
            str(out_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["summary"]["bounded_subset_mode"] == "editor_seed+heuristic_geometry_bridge+preview_roundtrip"
    assert payload["summary"]["heuristic_kds_geometry_bridge_model_count"] == 1
    assert payload["summary"]["kds_geometry_bridge_heuristic_review_id_total"] == 12
    assert payload["summary"]["exact_roundtrip_closure_pass"] is False
    assert payload["summary"]["exact_roundtrip_closure_status"] == "bounded_subset_pending"
    assert "heuristic_kds_geometry_bridge" in payload["summary"]["exact_roundtrip_closure_blockers"]


def test_midas_interoperability_gate_suppresses_static_disclaimer_limits_when_roundtrip_is_exact(tmp_path: Path) -> None:
    out_path = tmp_path / "midas_interoperability_gate_report.json"
    model_path = tmp_path / "model.json"
    export_report_path = tmp_path / "export_report.json"
    roundtrip_report_path = tmp_path / "roundtrip_report.json"
    preview_path = tmp_path / "preview.mgt"

    _write_model_json(
        model_path,
        seed_limitations=[
            "Editor seed rows are deterministic authoring contracts, not final solver-ready code-check assemblies.",
            "Expanded factor maps should be treated as normalized references until round-trip export is fully wired.",
        ],
        pattern_limitations=[
            "Combination expansion is summary-grade and should not replace final code-check load assembly."
        ],
    )
    _write_export_report(export_report_path)
    _write_roundtrip_report(roundtrip_report_path, source_model_json=model_path)
    preview_path.write_text("*LOADCOMB\n", encoding="utf-8")

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--model-jsons",
            str(model_path),
            "--export-report",
            str(export_report_path),
            "--loadcomb-roundtrip-reports",
            str(roundtrip_report_path),
            "--loadcomb-preview-files",
            str(preview_path),
            "--out",
            str(out_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["summary"]["remaining_limits"] == []
    assert payload["summary"]["exact_roundtrip_closure_pass"] is True
    assert payload["summary"]["exact_roundtrip_closure_status"] == "closed"
    assert payload["summary"]["exact_roundtrip_closure_blockers"] == []
    assert "limits=none" in payload["summary_line"]


def test_midas_interoperability_gate_keeps_limit_when_roundtrip_evidence_has_real_gap(tmp_path: Path) -> None:
    out_path = tmp_path / "midas_interoperability_gate_report.json"
    model_path = tmp_path / "model.json"
    export_report_path = tmp_path / "export_report.json"
    roundtrip_report_path = tmp_path / "roundtrip_report.json"
    preview_path = tmp_path / "preview.mgt"

    _write_model_json(
        model_path,
        seed_limitations=[
            "Editor seed rows are deterministic authoring contracts, not final solver-ready code-check assemblies.",
            "Expanded factor maps should be treated as normalized references until round-trip export is fully wired.",
        ],
        pattern_limitations=[
            "Combination expansion is summary-grade and should not replace final code-check load assembly."
        ],
    )
    _write_export_report(export_report_path)
    _write_roundtrip_report(
        roundtrip_report_path,
        source_model_json=model_path,
        exact_factor_map_coverage=0.5,
        exact_expression_coverage=0.5,
    )
    preview_path.write_text("*LOADCOMB\n", encoding="utf-8")

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--model-jsons",
            str(model_path),
            "--export-report",
            str(export_report_path),
            "--loadcomb-roundtrip-reports",
            str(roundtrip_report_path),
            "--loadcomb-preview-files",
            str(preview_path),
            "--out",
            str(out_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0

    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is False
    assert payload["summary"]["remaining_limits"] == [
        "solver_ready_reconstruction_pending",
        "normalized_factor_maps_pending",
        "summary_grade_preview_only",
    ]
    assert payload["summary"]["exact_roundtrip_closure_pass"] is False
    assert payload["summary"]["exact_roundtrip_closure_status"] == "fidelity_gap"


def test_midas_interoperability_gate_clears_raw_recovery_when_structured_loads_exist(tmp_path: Path) -> None:
    out_path = tmp_path / "midas_interoperability_gate_report.json"
    model_path = tmp_path / "model.json"
    export_report_path = tmp_path / "export_report.json"
    roundtrip_report_path = tmp_path / "roundtrip_report.json"
    preview_path = tmp_path / "preview.mgt"

    _write_model_json(
        model_path,
        recovery_mode="combination_only_raw_recovery",
        loads={
            "load_cases": [{"name": "DEAD", "type": "static"}],
            "load_combinations": [{"name": "ULS_1", "factor_map": {"D": 1.4}}],
            "semantic_load_summary": {"case_count": 1, "combination_count": 1},
        },
        seed_limitations=[
            "Recovered from raw LOADCOMB rows because a structured loads block was unavailable.",
            "Editor seed rows are deterministic authoring contracts, not final solver-ready code-check assemblies.",
        ],
        pattern_limitations=[
            "Load primitives are unavailable in this recovery path and are represented as zero-primitive authoring seeds."
        ],
    )
    _write_export_report(export_report_path)
    _write_roundtrip_report(roundtrip_report_path, source_model_json=model_path)
    preview_path.write_text("*LOADCOMB\n", encoding="utf-8")

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--model-jsons",
            str(model_path),
            "--export-report",
            str(export_report_path),
            "--loadcomb-roundtrip-reports",
            str(roundtrip_report_path),
            "--loadcomb-preview-files",
            str(preview_path),
            "--out",
            str(out_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["summary"]["structured_loads_contract_present_count"] == 1
    assert payload["summary"]["heuristic_raw_recovery_model_count"] == 0
    assert payload["summary"]["remaining_limits"] == []
    assert payload["summary"]["bounded_subset_mode"] == "full_exact_roundtrip"
    assert payload["summary"]["exact_roundtrip_closure_pass"] is True
    assert "heuristic_raw_loadcomb_recovery" not in payload["summary"]["exact_roundtrip_closure_blockers"]
    assert "primitive_load_cards_pending" not in payload["summary"]["remaining_limits"]


def test_midas_interoperability_gate_keeps_raw_recovery_when_structured_loads_are_not_exact(tmp_path: Path) -> None:
    out_path = tmp_path / "midas_interoperability_gate_report.json"
    model_path = tmp_path / "model.json"
    export_report_path = tmp_path / "export_report.json"
    roundtrip_report_path = tmp_path / "roundtrip_report.json"
    preview_path = tmp_path / "preview.mgt"

    _write_model_json(
        model_path,
        recovery_mode="combination_only_raw_recovery",
        loads={
            "load_cases": [{"name": "DEAD", "type": "static"}],
            "load_combinations": [{"name": "ULS_1", "factor_map": {"D": 1.4}}],
        },
        pattern_limitations=[
            "Load primitives are unavailable in this recovery path and are represented as zero-primitive authoring seeds."
        ],
    )
    _write_export_report(export_report_path)
    _write_roundtrip_report(
        roundtrip_report_path,
        source_model_json=model_path,
        exact_factor_map_coverage=0.5,
    )
    preview_path.write_text("*LOADCOMB\n", encoding="utf-8")

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--model-jsons",
            str(model_path),
            "--export-report",
            str(export_report_path),
            "--loadcomb-roundtrip-reports",
            str(roundtrip_report_path),
            "--loadcomb-preview-files",
            str(preview_path),
            "--out",
            str(out_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0

    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["summary"]["structured_loads_contract_present_count"] == 1
    assert payload["summary"]["heuristic_raw_recovery_model_count"] == 1
    assert "primitive_load_cards_pending" in payload["summary"]["remaining_limits"]
    assert "heuristic_raw_loadcomb_recovery" in payload["summary"]["exact_roundtrip_closure_blockers"]
