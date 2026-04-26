from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from implementation.phase1.load_combination_engine import (
    generate_kds_service_combinations,
    generate_kds_strength_combinations,
)


SCRIPT = Path("implementation/phase1/run_load_combination_engine_gate.py")


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _combo_rows_from_library() -> list[dict]:
    case_alias = {
        "D": "DEAD",
        "L": "LIVE",
        "Lr": "ROOF_LIVE",
        "Wx": "WIND+X",
        "Wy": "WIND+Y",
        "Ex": "EX",
        "Ey": "EY",
    }
    rows: list[dict] = []
    for combo in [*generate_kds_strength_combinations(), *generate_kds_service_combinations()]:
        rows.append(
            {
                "name": combo.name,
                "combination_type": "GEN",
                "limit_state": combo.limit_state,
                "factor_map": {
                    str(case_alias.get(str(key), str(key))): float(value)
                    for key, value in combo.factors.items()
                },
                "expanded_factor_map": {
                    str(case_alias.get(str(key), str(key))): float(value)
                    for key, value in combo.factors.items()
                },
            }
        )
    return rows


def _combo_rows_from_library_with_nested_rc_breadth() -> list[dict]:
    rows = _combo_rows_from_library()
    rows.extend(
        [
            {
                "name": "RC_BASE",
                "combination_type": "GEN",
                "limit_state": "ULS",
                "entry_rows": [
                    {"reference_kind": "ST", "reference_name": "DEAD", "factor": 1.2},
                    {"reference_kind": "ST", "reference_name": "LIVE", "factor": 0.5},
                ],
            },
            {
                "name": "RC_WIND_ENV",
                "combination_type": "GEN",
                "limit_state": "ULS",
                "entry_rows": [
                    {"reference_kind": "CB", "reference_name": "RC_BASE", "factor": 1.0},
                    {"reference_kind": "ST", "reference_name": "WIND+X", "factor": 1.0},
                ],
            },
            {
                "name": "RC_SEISMIC_ENV",
                "combination_type": "GEN",
                "limit_state": "SERVICE",
                "entry_rows": [
                    {"reference_kind": "CB", "reference_name": "RC_WIND_ENV", "factor": 1.0},
                    {"reference_kind": "ST", "reference_name": "EX", "factor": 0.7},
                ],
            },
        ]
    )
    return rows


def _steel_combo_rows(*, mismatch_live_factor: float | None = None) -> list[dict]:
    strength_live = 1.5 if mismatch_live_factor is None else float(mismatch_live_factor)
    return [
        {
            "name": "gLCB1",
            "combination_type": "GEN",
            "limit_state": "ACTIVE",
            "factor_map": {"DEAD": 1.3, "LIVE": 1.5},
            "expanded_factor_map": {"DEAD": 1.3, "LIVE": 1.5},
        },
        {
            "name": "STL ENV_STR",
            "combination_type": "GEN",
            "limit_state": "ACTIVE",
            "factor_map": {"DEAD": 1.3, "LIVE": 1.5},
            "expanded_factor_map": {"DEAD": 1.3, "LIVE": 1.5},
        },
        {
            "name": "sLCB2",
            "combination_type": "GEN",
            "limit_state": "ACTIVE",
            "factor_map": {"DEAD": 1.0, "LIVE": strength_live},
            "expanded_factor_map": {"DEAD": 1.0, "LIVE": strength_live},
        },
        {
            "name": "STL ENV_SER",
            "combination_type": "GEN",
            "limit_state": "SERVICE",
            "factor_map": {"DEAD": 1.0, "LIVE": 1.0},
            "expanded_factor_map": {"DEAD": 1.0, "LIVE": 1.0},
        },
    ]


def _write_model_json(path: Path, *, combo_rows: list[dict], pattern_labels: list[str]) -> None:
    case_rows = [
        {
            "load_case": label,
            "semantic_status": "nodal_only_ready",
        }
        for label in pattern_labels
    ]
    pattern_rows = [
        {
            "pattern_id": f"midas:{label}",
            "label": label,
            "primitive_count": 1,
            "primitive_counts": {"point_load": 1},
            "primitives": [{"kind": "point_load"}],
        }
        for label in pattern_labels
    ]
    _write_json(
        path,
        {
            "model": {
                "loads": {
                    "load_combinations": combo_rows,
                    "semantic_load_summary": {
                        "case_force_summaries": case_rows,
                    },
                },
                "metadata": {
                    "load_pattern_library": {
                        "pattern_summary": {
                            "pattern_count": len(pattern_rows),
                            "primitive_count": len(pattern_rows),
                            "case_counts": {label: 1 for label in pattern_labels},
                            "patterns": pattern_rows,
                        }
                    }
                },
            }
        },
    )


def _write_roundtrip_report(
    path: Path,
    *,
    source_model_json: Path,
    combo_count: int,
    exact_name_coverage: float = 1.0,
    exact_entry_row_coverage: float = 1.0,
    exact_header_coverage: float = 1.0,
    exact_factor_map_coverage: float = 1.0,
    exact_expression_coverage: float = 1.0,
    pass_flag: bool = True,
    supported: bool = True,
) -> None:
    _write_json(
        path,
        {
            "contract_version": "0.1.0",
            "supported": supported,
            "source_model_json": str(source_model_json),
            "recovery_mode": "",
            "raw_combo_count": combo_count,
            "export_combo_count": combo_count,
            "pass": pass_flag,
            "exact_name_coverage": exact_name_coverage,
            "exact_entry_row_coverage": exact_entry_row_coverage,
            "exact_header_coverage": exact_header_coverage,
            "exact_factor_map_coverage": exact_factor_map_coverage,
            "exact_expression_coverage": exact_expression_coverage,
        },
    )


def _run_gate(*, model_jsons: list[Path], roundtrip_reports: list[Path], out: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--model-jsons",
            ",".join(str(path) for path in model_jsons),
            "--loadcomb-roundtrip-reports",
            ",".join(str(path) for path in roundtrip_reports),
            "--out",
            str(out),
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )


def test_run_load_combination_engine_gate_passes_for_exact_kds_aligned_runtime_library(tmp_path: Path) -> None:
    model_path = tmp_path / "model.json"
    report_path = tmp_path / "roundtrip_report.json"
    out_path = tmp_path / "load_combination_engine_gate_report.json"

    combo_rows = _combo_rows_from_library()
    pattern_labels = ["DEAD", "LIVE", "WIND+X", "WIND+Y", "EX", "EY", "ROOF_LIVE"]
    _write_model_json(model_path, combo_rows=combo_rows, pattern_labels=pattern_labels)
    _write_roundtrip_report(report_path, source_model_json=model_path, combo_count=len(combo_rows))

    proc = _run_gate(model_jsons=[model_path], roundtrip_reports=[report_path], out=out_path)

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["reason_code"] == "PASS"
    assert payload["checks"]["exact_roundtrip_fidelity_pass"] is True
    assert payload["checks"]["required_load_pattern_coverage_pass"] is True
    assert payload["checks"]["kds_strength_alignment_pass"] is True
    assert payload["checks"]["kds_service_alignment_pass"] is True
    assert payload["summary"]["selected_kds_family"] == "KDS-2022-generic"
    assert payload["summary"]["recommended_kds_family"] == "KDS-2022-generic"
    assert payload["summary"]["selected_kds_family_counts"] == {"KDS-2022-generic": 1}
    assert payload["summary"]["runtime_combo_count_total"] == len(combo_rows)
    assert payload["summary"]["required_load_pattern_coverage_ratio_min"] == 1.0
    assert payload["summary"]["artifact_gap_counts"] == {}
    assert payload["summary"]["artifact_rows"][0]["gap_labels"] == []
    assert payload["summary"]["artifact_rows"][0]["selected_kds_family"] == "KDS-2022-generic"
    assert "Load-combination engine gate: PASS" in payload["summary_line"]
    assert "family=KDS-2022-generic" in payload["summary_line"]


def test_run_load_combination_engine_gate_selects_steel_family_for_canonical_style_runtime_set(
    tmp_path: Path,
) -> None:
    model_path = tmp_path / "model.json"
    report_path = tmp_path / "roundtrip_report.json"
    out_path = tmp_path / "load_combination_engine_gate_report.json"

    combo_rows = _steel_combo_rows()
    _write_model_json(model_path, combo_rows=combo_rows, pattern_labels=["DEAD", "LIVE"])
    _write_roundtrip_report(report_path, source_model_json=model_path, combo_count=len(combo_rows))

    proc = _run_gate(model_jsons=[model_path], roundtrip_reports=[report_path], out=out_path)

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    artifact_row = payload["summary"]["artifact_rows"][0]
    assert payload["contract_pass"] is True
    assert payload["reason_code"] == "PASS"
    assert payload["checks"]["kds_strength_alignment_pass"] is True
    assert payload["checks"]["kds_service_alignment_pass"] is True
    assert payload["summary"]["selected_kds_family"] == "KDS-2022-steel-gravity"
    assert payload["summary"]["recommended_kds_family"] == "KDS-2022-steel-gravity"
    assert payload["summary"]["selected_kds_family_counts"] == {"KDS-2022-steel-gravity": 1}
    assert artifact_row["selected_kds_family"] == "KDS-2022-steel-gravity"
    assert artifact_row["recommended_kds_family"] == "KDS-2022-steel-gravity"
    assert artifact_row["kds_family_selection_reason"] == "steel_named_gravity_signature_match"
    assert artifact_row["kds_family_selection_signals"]["steel_family_clear_signal"] is True
    assert artifact_row["kds_family_selection_signals"]["steel_name_token_hits"] == ["ENV_SER", "ENV_STR", "SLCB", "STL"]
    assert artifact_row["kds_family_selection_signals"]["steel_signature_match_count"] == 3
    assert artifact_row["kds_strength_target_count"] == 2
    assert artifact_row["kds_service_target_count"] == 1
    assert artifact_row["kds_strength_match"]["avg_match_score"] == 1.0
    assert artifact_row["kds_service_match"]["avg_match_score"] == 1.0
    assert "family=KDS-2022-steel-gravity" in payload["summary_line"]


def test_run_load_combination_engine_gate_flags_required_pattern_gap_before_alignment(tmp_path: Path) -> None:
    model_path = tmp_path / "model.json"
    report_path = tmp_path / "roundtrip_report.json"
    out_path = tmp_path / "load_combination_engine_gate_report.json"

    combo_rows = [
        {
            "name": "ULS_PROJECT",
            "combination_type": "GEN",
            "limit_state": "ULS",
            "factor_map": {"DEAD": 1.2, "LIVE": 1.6, "WIND+X": 1.0},
            "expanded_factor_map": {"DEAD": 1.2, "LIVE": 1.6, "WIND+X": 1.0},
        }
    ]
    _write_model_json(model_path, combo_rows=combo_rows, pattern_labels=["DEAD", "LIVE"])
    _write_roundtrip_report(report_path, source_model_json=model_path, combo_count=len(combo_rows))

    proc = _run_gate(model_jsons=[model_path], roundtrip_reports=[report_path], out=out_path)

    assert proc.returncode == 1
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is False
    assert payload["reason_code"] == "ERR_LOAD_PATTERN_COVERAGE_GAP"
    assert payload["checks"]["exact_roundtrip_fidelity_pass"] is True
    assert payload["checks"]["required_load_pattern_coverage_pass"] is False
    artifact_row = payload["summary"]["artifact_rows"][0]
    assert artifact_row["missing_required_load_pattern_cases"] == ["Wx"]
    assert "load_pattern_coverage_gap" in artifact_row["gap_labels"]


def test_run_load_combination_engine_gate_reports_kds_alignment_gap_for_project_specific_runtime_set(tmp_path: Path) -> None:
    model_path = tmp_path / "model.json"
    report_path = tmp_path / "roundtrip_report.json"
    out_path = tmp_path / "load_combination_engine_gate_report.json"

    combo_rows = [
        {
            "name": "gLCB1",
            "combination_type": "GEN",
            "limit_state": "ACTIVE",
            "factor_map": {"DEAD": 1.3, "LIVE": 1.5},
            "expanded_factor_map": {"DEAD": 1.3, "LIVE": 1.5},
        },
        {
            "name": "gLCB2",
            "combination_type": "GEN",
            "limit_state": "ACTIVE",
            "factor_map": {"DEAD": 1.0},
            "expanded_factor_map": {"DEAD": 1.0},
        },
        {
            "name": "gLCB3",
            "combination_type": "GEN",
            "limit_state": "SERVICE",
            "factor_map": {"DEAD": 1.0, "LIVE": 1.0},
            "expanded_factor_map": {"DEAD": 1.0, "LIVE": 1.0},
        },
    ]
    _write_model_json(model_path, combo_rows=combo_rows, pattern_labels=["DEAD", "LIVE"])
    _write_roundtrip_report(report_path, source_model_json=model_path, combo_count=len(combo_rows))

    proc = _run_gate(model_jsons=[model_path], roundtrip_reports=[report_path], out=out_path)

    assert proc.returncode == 1
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is False
    assert payload["reason_code"] == "ERR_KDS_RUNTIME_ALIGNMENT_GAP"
    assert payload["checks"]["exact_roundtrip_fidelity_pass"] is True
    assert payload["checks"]["required_load_pattern_coverage_pass"] is True
    assert payload["checks"]["kds_strength_alignment_pass"] is False
    assert payload["checks"]["kds_service_alignment_pass"] is False
    artifact_row = payload["summary"]["artifact_rows"][0]
    assert "kds_strength_alignment_gap" in artifact_row["gap_labels"]
    assert "kds_service_alignment_gap" in artifact_row["gap_labels"]
    assert artifact_row["kds_strength_match"]["avg_match_score"] < payload["summary"]["kds_strength_avg_match_threshold"]
    assert artifact_row["selected_kds_family"] == "KDS-2022-generic"


def test_run_load_combination_engine_gate_keeps_check_when_steel_family_parity_does_not_close(
    tmp_path: Path,
) -> None:
    model_path = tmp_path / "model.json"
    report_path = tmp_path / "roundtrip_report.json"
    out_path = tmp_path / "load_combination_engine_gate_report.json"

    combo_rows = _steel_combo_rows(mismatch_live_factor=1.1)
    _write_model_json(model_path, combo_rows=combo_rows, pattern_labels=["DEAD", "LIVE"])
    _write_roundtrip_report(report_path, source_model_json=model_path, combo_count=len(combo_rows))

    proc = _run_gate(model_jsons=[model_path], roundtrip_reports=[report_path], out=out_path)

    assert proc.returncode == 1
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    artifact_row = payload["summary"]["artifact_rows"][0]
    assert payload["contract_pass"] is False
    assert payload["reason_code"] == "ERR_KDS_RUNTIME_ALIGNMENT_GAP"
    assert artifact_row["selected_kds_family"] == "KDS-2022-steel-gravity"
    assert artifact_row["recommended_kds_family"] == "KDS-2022-steel-gravity"
    assert artifact_row["kds_family_selection_signals"]["steel_family_clear_signal"] is True
    assert payload["checks"]["kds_strength_alignment_pass"] is False
    assert payload["checks"]["kds_service_alignment_pass"] is True
    assert "kds_strength_alignment_gap" in artifact_row["gap_labels"]
    assert artifact_row["kds_strength_match"]["avg_match_score"] < payload["summary"]["kds_strength_avg_match_threshold"]


def test_run_load_combination_engine_gate_surfaces_nested_depth_and_case_breadth_metrics(
    tmp_path: Path,
) -> None:
    model_path = tmp_path / "model.json"
    report_path = tmp_path / "roundtrip_report.json"
    out_path = tmp_path / "load_combination_engine_gate_report.json"

    combo_rows = _combo_rows_from_library_with_nested_rc_breadth()
    _write_model_json(
        model_path,
        combo_rows=combo_rows,
        pattern_labels=["DEAD", "LIVE", "WIND+X", "WIND+Y", "EX", "EY", "ROOF_LIVE"],
    )
    _write_roundtrip_report(report_path, source_model_json=model_path, combo_count=len(combo_rows))

    proc = _run_gate(model_jsons=[model_path], roundtrip_reports=[report_path], out=out_path)

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    artifact_row = payload["summary"]["artifact_rows"][0]

    assert payload["contract_pass"] is True
    assert payload["checks"]["runtime_nested_depth_surface_pass"] is True
    assert payload["checks"]["runtime_case_breadth_surface_pass"] is True
    assert payload["summary"]["supported_kds_family_labels"] == [
        "KDS-2022-generic",
        "KDS-2022-rc-nested",
        "KDS-2022-rc-seismic",
        "KDS-2022-rc-wind",
        "KDS-2022-steel-gravity",
    ]
    assert payload["summary"]["runtime_linear_combo_count_total"] == len(combo_rows) - 2
    assert payload["summary"]["runtime_nested_combo_count_total"] == 2
    assert payload["summary"]["runtime_max_nested_depth_global"] == 3
    assert payload["summary"]["runtime_case_breadth_count_min"] == 3
    assert payload["summary"]["runtime_case_breadth_count_max"] == 3
    assert payload["summary"]["runtime_case_breadth_label"] == "rc, wind, seismic"
    assert payload["summary"]["runtime_case_family_counts_total"] == {"rc": 2, "seismic": 2, "wind": 2}
    assert payload["summary"]["runtime_combo_family_counts_total"]["rc+wind+nested"] == 1
    assert payload["summary"]["runtime_combo_family_counts_total"]["rc+wind+seismic+nested"] == 1
    assert payload["summary"]["runtime_rc_combo_count_total"] == len(combo_rows)
    assert payload["summary"]["runtime_wind_combo_count_total"] == 10
    assert payload["summary"]["runtime_seismic_combo_count_total"] == 13
    assert payload["summary"]["runtime_rc_max_nested_depth_global"] == 3
    assert payload["summary"]["runtime_wind_max_nested_depth_global"] == 3
    assert payload["summary"]["runtime_seismic_max_nested_depth_global"] == 3
    assert artifact_row["runtime_nested_combo_count"] == 2
    assert artifact_row["runtime_max_nested_depth"] == 3
    assert artifact_row["runtime_case_breadth_label"] == "rc, wind, seismic"
    assert artifact_row["runtime_case_family_counts"] == {"rc": 2, "seismic": 2, "wind": 2}
    assert artifact_row["runtime_limit_state_counts"]["ULS"] >= 1
    assert artifact_row["runtime_combo_depth_rows"][-1]["name"] == "RC_WIND_ENV"
    assert "nested=2 max_depth=3" in payload["summary_line"]
    assert "breadth=rc, wind, seismic" in payload["summary_line"]
