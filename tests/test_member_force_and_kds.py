from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from implementation.phase1.code_check_engine import evaluate_code_compliance
from implementation.phase1.generate_kds_compliance_report import _build_frontend_payload


def test_member_force_soft_accept_gate_pass(tmp_path: Path) -> None:
    out = tmp_path / "member_force_gate.json"
    cmd = [
        sys.executable,
        "implementation/phase1/run_member_force_soft_accept_gate.py",
        "--hf-csv",
        "implementation/phase1/commercial_hf_export_sample.csv",
        "--lf-csv",
        "implementation/phase1/commercial_lf_export_sample.csv",
        "--out",
        str(out),
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["contract_pass"] is True
    assert report["checks"]["member_force_metric_present"] is True
    assert report["checks"]["member_force_components_5d_pass"] is True
    assert report["checks"]["hard_gate_pass"] is True
    assert report["checks"]["soft_accept_gate_pass"] is True
    assert int(report["summary"]["component_count_available"]) == 5
    assert int(report["summary"]["case_count"]) >= 3
    assert int(report["summary"]["member_count"]) >= 3
    assert int(report["summary"]["distribution_chart_case_count"]) >= 3
    assert report["summary"]["authoritative_raw_station_source_available"] is True
    assert report["summary"]["authoritative_raw_station_source_used"] is True
    assert "raw station profiles will be used" in report["summary"]["authoritative_raw_station_source_reason"]
    station_source = report["station_source"]
    assert station_source["authoritative_raw_station_source_available"] is True
    assert station_source["candidate_station_header_count"] > 0
    row = report["rows"][0]
    assert row["member_id"].startswith("MF-")
    distribution = row["distribution_chart"]
    assert distribution["source_mode"] == "authoritative_raw_station_profile"
    assert distribution["authoritative_raw_station_source_available"] is True
    assert distribution["authoritative_raw_station_source_used"] is True
    assert distribution["member_id"] == row["member_id"]
    assert distribution["case_id"] == row["case_id"]
    assert distribution["xLabel"] == "Normalized Member Length"
    assert len(distribution["stations"]) >= 5
    assert len(distribution["series"]) == 10
    assert distribution["series"][0]["component"] == "axial_force_kN"
    assert len(distribution["series"][0]["points"]) == len(distribution["stations"])


def test_member_force_soft_accept_gate_uses_authoritative_station_profiles_when_available(tmp_path: Path) -> None:
    out = tmp_path / "member_force_gate_station.json"
    headers = [
        "case_id",
        "axial_force_kN",
        "shear_force_y_kN",
        "shear_force_z_kN",
        "bending_moment_y_kNm",
        "bending_moment_z_kNm",
    ]
    station_headers = [
        "axial_force_kN_station_0.0",
        "axial_force_kN_station_0.5",
        "axial_force_kN_station_1.0",
        "bending_moment_y_kNm_station_0.0",
        "bending_moment_y_kNm_station_0.5",
        "bending_moment_y_kNm_station_1.0",
    ]
    row_hf = [
        "CASE-RAW-001",
        "1000",
        "120",
        "90",
        "220",
        "180",
        "950",
        "1000",
        "980",
        "0",
        "220",
        "0",
    ]
    row_lf = [
        "CASE-RAW-001",
        "1010",
        "118",
        "92",
        "225",
        "176",
        "960",
        "1015",
        "995",
        "0",
        "228",
        "0",
    ]
    hf_csv = tmp_path / "hf_station.csv"
    lf_csv = tmp_path / "lf_station.csv"
    hf_csv.write_text(",".join(headers + station_headers) + "\n" + ",".join(row_hf) + "\n", encoding="utf-8")
    lf_csv.write_text(",".join(headers + station_headers) + "\n" + ",".join(row_lf) + "\n", encoding="utf-8")

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/run_member_force_soft_accept_gate.py",
            "--hf-csv",
            str(hf_csv),
            "--lf-csv",
            str(lf_csv),
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["station_source"]["authoritative_raw_station_source_available"] is True
    assert report["station_source"]["authoritative_raw_station_source_used"] is True
    assert "raw station profiles will be used" in report["station_source"]["reason"]
    assert "axial" in report["station_source"]["available_station_components"]
    distribution = report["rows"][0]["distribution_chart"]
    assert distribution["source_mode"] == "authoritative_raw_station_profile"
    assert distribution["authoritative_raw_station_source_available"] is True
    assert distribution["authoritative_raw_station_source_used"] is True
    axial_hf = next(series for series in distribution["series"] if series["label"] == "HF axial")
    moment_y_hf = next(series for series in distribution["series"] if series["label"] == "HF moment Y")
    assert axial_hf["profile_kind"] == "stationwise_raw"
    assert axial_hf["points"] == [[0.0, 950.0], [0.5, 1000.0], [1.0, 980.0]]
    assert moment_y_hf["profile_kind"] == "stationwise_raw"
    assert moment_y_hf["points"] == [[0.0, 0.0], [0.5, 220.0], [1.0, 0.0]]


def test_member_force_soft_accept_gate_supports_station_token_variants_and_shared_subset(tmp_path: Path) -> None:
    out = tmp_path / "member_force_gate_station_variants.json"
    headers = [
        "case_id",
        "axial_force_kN",
        "shear_force_y_kN",
        "shear_force_z_kN",
        "bending_moment_y_kNm",
        "bending_moment_z_kNm",
        "axial_force_kN_station_0.0",
        "axial_force_kN_st_0p5",
        "axial_force_kN_station_1.0",
        "axial_force_kN_station_0.25",
    ]
    hf_row = ["CASE-RAW-002", "900", "100", "80", "210", "175", "880", "900", "860", "890"]
    lf_headers = [
        "case_id",
        "axial_force_kN",
        "shear_force_y_kN",
        "shear_force_z_kN",
        "bending_moment_y_kNm",
        "bending_moment_z_kNm",
        "axial_force_kN_station_0.0",
        "axial_force_kN_st_0p5",
        "axial_force_kN_station_1.0",
    ]
    lf_row = ["CASE-RAW-002", "905", "101", "79", "208", "173", "882", "904", "864"]
    hf_csv = tmp_path / "hf_station_variants.csv"
    lf_csv = tmp_path / "lf_station_variants.csv"
    hf_csv.write_text(",".join(headers) + "\n" + ",".join(hf_row) + "\n", encoding="utf-8")
    lf_csv.write_text(",".join(lf_headers) + "\n" + ",".join(lf_row) + "\n", encoding="utf-8")

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/run_member_force_soft_accept_gate.py",
            "--hf-csv",
            str(hf_csv),
            "--lf-csv",
            str(lf_csv),
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    report = json.loads(out.read_text(encoding="utf-8"))
    axial_profile = report["station_source"]["component_station_profiles"]["axial"]
    assert axial_profile["available"] is True
    assert axial_profile["shared_stations"] == [0.0, 0.5, 1.0]
    distribution = report["rows"][0]["distribution_chart"]
    axial_hf = next(series for series in distribution["series"] if series["label"] == "HF axial")
    assert axial_hf["profile_kind"] == "stationwise_raw"
    assert axial_hf["points"] == [[0.0, 880.0], [0.5, 900.0], [1.0, 860.0]]


def test_generate_kds_compliance_report(tmp_path: Path) -> None:
    pbd = tmp_path / "pbd.json"
    commercial = tmp_path / "commercial.json"
    member_force = tmp_path / "member_force.json"
    out_dir = tmp_path / "kds_out"

    pbd.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "run_id": "phase3-pbd-review-package",
                "generated_at": "2026-03-05T00:00:00+00:00",
                "reason_code": "PASS",
                "contract_pass": True,
                "metrics": {
                    "drift_envelope_max_pct": 1.2,
                    "all_cases_converged": True,
                    "converged_step_ratio_min": 1.0,
                    "energy_balance_relative_error_ref": 1.0e-4,
                },
            }
        ),
        encoding="utf-8",
    )
    commercial.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "run_id": "phase1-commercial-csv-gate",
                "generated_at": "2026-03-05T00:00:00+00:00",
                "reason_code": "PASS",
                "contract_pass": True,
                "checks": {
                    "drift_within_5pct": True,
                    "base_shear_within_5pct": True,
                    "buckling_within_5pct": True,
                    "mac_above_095": True,
                },
                "metrics": {
                    "drift_error_pct": 1.0,
                    "base_shear_error_pct": 1.2,
                    "buckling_factor_error_pct": 1.4,
                    "mode_shape_mac": 0.98,
                },
            }
        ),
        encoding="utf-8",
    )
    member_force.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "run_id": "phase1-member-force-soft-accept-gate",
                "generated_at": "2026-03-05T00:00:00+00:00",
                "reason_code": "PASS",
                "contract_pass": True,
                "checks": {
                    "member_force_metric_present": True,
                    "member_force_components_5d_pass": True,
                    "hard_gate_pass": True,
                    "soft_accept_gate_pass": True,
                },
                "summary": {
                    "error_pct_p95": 3.2,
                    "soft_accept_case_ratio": 0.1,
                },
            }
        ),
        encoding="utf-8",
    )

    cmd = [
        sys.executable,
        "implementation/phase1/generate_kds_compliance_report.py",
        "--pbd-review-package",
        str(pbd),
        "--commercial-csv-gate",
        str(commercial),
        "--member-force-gate",
        str(member_force),
        "--out-dir",
        str(out_dir),
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr

    report = json.loads((out_dir / "kds_compliance_summary.json").read_text(encoding="utf-8"))
    assert report["contract_pass"] is True
    assert report["reason_code"] == "PASS"
    assert Path(report["artifacts"]["kds_compliance_csv"]).exists()
    assert Path(report["artifacts"]["kds_compliance_markdown"]).exists()
    assert Path(report["artifacts"]["kds_compliance_pdf"]).exists()
    assert Path(report["artifacts"]["kds_frontend_payload_json"]).exists()
    frontend = report.get("frontend_payload")
    assert isinstance(frontend, dict)
    assert isinstance(frontend.get("summary_cards"), list)
    assert len(frontend.get("summary_cards", [])) >= 8
    assert isinstance(frontend.get("compliance_rows"), list)
    assert len(frontend.get("compliance_rows", [])) >= 500
    assert isinstance(frontend.get("governing_member_checks_top500"), list)
    assert len(frontend.get("governing_member_checks_top500", [])) == 500
    assert isinstance(frontend.get("governing_rc_checks_top100"), list)
    assert isinstance(frontend.get("ng_members_by_combination"), list)
    assert isinstance(frontend.get("member_family_dcr_envelope"), list)
    summary = report.get("summary")
    assert isinstance(summary, dict)
    assert int(summary.get("summary_card_count", 0)) >= 8
    assert int(summary.get("compliance_row_count", 0)) >= 500
    assert int(summary.get("member_check_row_count", 0)) >= 500
    assert int(summary.get("clause_count", 0)) >= 8
    assert int(summary.get("member_type_count", 0)) >= 4
    assert int(summary.get("rc_rule_row_count", 0)) >= 4
    assert int(summary.get("steel_rule_row_count", 0)) == 0
    assert isinstance(frontend.get("governing_steel_checks_top100"), list)
    assert any(str(card.get("label")) == "Steel Detail" for card in frontend.get("summary_cards", []))


def test_code_check_engine_uses_kds_combo_library_and_rc_rows(tmp_path: Path) -> None:
    hf_csv = tmp_path / "hf.csv"
    hf_csv.write_text(
        "\n".join(
            [
                "case_id,topology_type,hazard_type,drift_ratio_pct,buckling_factor,axial_force_kN,shear_force_y_kN,shear_force_z_kN,bending_moment_y_kNm,bending_moment_z_kNm,member_type",
                "W-001,wall-frame,seismic,1.35,2.8,950,210,180,860,740,wall",
                "C-001,outrigger,seismic,1.10,3.2,1200,150,140,920,810,column",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    load_comb_model = {
        "model": {
            "loads": {
                "load_combinations": [
                    {"name": "gLCB1", "expanded_factor_map": {"DEAD": 1.2, "LIVE": 1.6}},
                    {"name": "gLCB2", "expanded_factor_map": {"DEAD": 1.2, "EX": 1.0}},
                    {"name": "gLCB3", "expanded_factor_map": {"DEAD": 1.2, "EY": 1.0}},
                ]
            }
        }
    }
    report = evaluate_code_compliance(
        hf_csv=hf_csv,
        capacity={
            "axial_capacity_kN": 2200.0,
            "shear_capacity_kN": 380.0,
            "moment_capacity_kNm": 2600.0,
        },
        combination_scales=[],
        max_dcr=1.25,
        combination_family="KDS-2022",
        combination_limit_state="ULS",
        load_combination_model=load_comb_model,
    )
    assert report["inputs"]["combination_family"] == "KDS-2022"
    assert report["inputs"]["combination_limit_state"] == "ULS"
    assert report["inputs"]["load_combination_model_present"] is True
    assert int(report["summary"]["combination_count"]) >= 10
    assert int(report["summary"]["combination_provenance_count"]) >= 10
    assert int(report["summary"]["rc_rule_row_count"]) >= 4
    assert report["checks"]["rc_rule_rows_min_pass"] is True
    assert report["checks"]["combination_provenance_pass"] is True
    assert isinstance(report.get("combination_provenance_rows"), list)


def test_code_check_engine_infers_steel_combo_family_from_model_when_not_requested(tmp_path: Path) -> None:
    hf_csv = tmp_path / "hf_steel.csv"
    hf_csv.write_text(
        "\n".join(
            [
                "case_id,topology_type,hazard_type,drift_ratio_pct,buckling_factor,axial_force_kN,shear_force_y_kN,shear_force_z_kN,bending_moment_y_kNm,bending_moment_z_kNm,member_type",
                "B-001,rahmen,wind,0.45,3.4,180,40,35,120,95,beam",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    steel_load_comb_model = {
        "model": {
            "loads": {
                "load_combinations": [
                    {"name": "SLCB1", "combination_type": "STEEL", "limit_state": "ULS", "expanded_factor_map": {"DEAD": 1.3, "LIVE": 1.5}},
                    {"name": "SLCB2", "combination_type": "STEEL", "limit_state": "ULS", "expanded_factor_map": {"DEAD": 1.0, "LIVE": 1.5}},
                    {"name": "SLCB3", "combination_type": "STEEL", "limit_state": "SLS", "expanded_factor_map": {"DEAD": 1.0, "LIVE": 1.0}},
                ]
            }
        }
    }

    report = evaluate_code_compliance(
        hf_csv=hf_csv,
        capacity={
            "axial_capacity_kN": 2200.0,
            "shear_capacity_kN": 380.0,
            "moment_capacity_kNm": 2600.0,
        },
        combination_scales=[],
        max_dcr=1.25,
        combination_limit_state="ULS",
        load_combination_model=steel_load_comb_model,
    )

    assert report["inputs"]["combination_family"] == "KDS-2022-STEEL-BASIC"
    assert report["inputs"]["requested_combination_family"] == ""
    assert report["inputs"]["combination_family_source"] == "load_combination_model"
    assert report["summary"]["combination_count"] == 2
    assert report["summary"]["combination_provenance_count"] == 2
    assert int(report["summary"]["steel_rule_row_count"]) >= 3
    assert [row["kds_name"] for row in report["combination_provenance_rows"]] == [
        "KDS_STEEL_ULS_1",
        "KDS_STEEL_ULS_2",
    ]
    assert all(row["reference_family"] == "KDS-2022-STEEL-BASIC" for row in report["combination_provenance_rows"])
    assert report["checks"]["steel_rule_rows_min_pass"] is True
    assert any(row["rule_family"] == "steel_detail" for row in report["member_check_rows"])
    assert any(str(row["clause"]).startswith("KDS-STEEL-") for row in report["member_check_rows"])


def test_code_check_engine_keeps_explicit_combo_family_over_model_inference(tmp_path: Path) -> None:
    hf_csv = tmp_path / "hf_concrete_override.csv"
    hf_csv.write_text(
        "\n".join(
            [
                "case_id,topology_type,hazard_type,drift_ratio_pct,buckling_factor,axial_force_kN,shear_force_y_kN,shear_force_z_kN,bending_moment_y_kNm,bending_moment_z_kNm,member_type",
                "C-010,outrigger,seismic,0.55,3.1,240,55,50,160,140,column",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    steel_load_comb_model = {
        "model": {
            "loads": {
                "load_combinations": [
                    {"name": "SLCB1", "combination_type": "STEEL", "limit_state": "ULS", "expanded_factor_map": {"DEAD": 1.3, "LIVE": 1.5}},
                    {"name": "SLCB2", "combination_type": "STEEL", "limit_state": "ULS", "expanded_factor_map": {"DEAD": 1.0, "LIVE": 1.5}},
                    {"name": "SLCB3", "combination_type": "STEEL", "limit_state": "SLS", "expanded_factor_map": {"DEAD": 1.0, "LIVE": 1.0}},
                ]
            }
        }
    }

    report = evaluate_code_compliance(
        hf_csv=hf_csv,
        capacity={
            "axial_capacity_kN": 2200.0,
            "shear_capacity_kN": 380.0,
            "moment_capacity_kNm": 2600.0,
        },
        combination_scales=[],
        max_dcr=1.25,
        combination_family="KDS-2022",
        combination_limit_state="ULS",
        load_combination_model=steel_load_comb_model,
    )

    assert report["inputs"]["combination_family"] == "KDS-2022"
    assert report["inputs"]["requested_combination_family"] == "KDS-2022"
    assert report["inputs"]["combination_family_source"] == "user_input"
    assert report["summary"]["combination_count"] >= 10
    assert report["summary"]["combination_provenance_count"] >= 10
    assert report["combination_provenance_rows"][0]["kds_name"] == "KDS_ULS_1"
    assert report["combination_provenance_rows"][0]["reference_family"] == "KDS-2022"
    assert int(report["summary"]["steel_rule_row_count"]) == 0
    assert report["checks"]["steel_rule_rows_min_pass"] is True


def test_kds_frontend_payload_surfaces_steel_detail_rows(tmp_path: Path) -> None:
    hf_csv = tmp_path / "hf_steel_payload.csv"
    hf_csv.write_text(
        "\n".join(
            [
                "case_id,topology_type,hazard_type,drift_ratio_pct,buckling_factor,axial_force_kN,shear_force_y_kN,shear_force_z_kN,bending_moment_y_kNm,bending_moment_z_kNm,member_type",
                "B-201,rahmen,wind,0.48,3.6,190,44,38,130,102,beam",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    steel_load_comb_model = {
        "model": {
            "loads": {
                "load_combinations": [
                    {
                        "name": "SLCB1",
                        "combination_type": "STEEL",
                        "limit_state": "ULS",
                        "expanded_factor_map": {"DEAD": 1.3, "LIVE": 1.5},
                    },
                    {
                        "name": "SLCB2",
                        "combination_type": "STEEL",
                        "limit_state": "ULS",
                        "expanded_factor_map": {"DEAD": 1.0, "LIVE": 1.5},
                    },
                    {
                        "name": "SLCB3",
                        "combination_type": "STEEL",
                        "limit_state": "SLS",
                        "expanded_factor_map": {"DEAD": 1.0, "LIVE": 1.0},
                    },
                ]
            }
        }
    }

    code_check_report = evaluate_code_compliance(
        hf_csv=hf_csv,
        capacity={
            "axial_capacity_kN": 2200.0,
            "shear_capacity_kN": 380.0,
            "moment_capacity_kNm": 2600.0,
        },
        combination_scales=[],
        max_dcr=1.25,
        combination_limit_state="ULS",
        load_combination_model=steel_load_comb_model,
    )
    frontend = _build_frontend_payload(
        rows=[
            {
                "item": "Code Check D/C",
                "criterion": "max D/C <= 1.250",
                "value": f"{float(code_check_report['summary']['max_dcr']):.4f}",
                "status": "PASS" if bool(code_check_report.get("contract_pass", False)) else "FAIL",
                "evidence": "unit-test steel payload",
            }
        ],
        code_check_report=code_check_report,
    )

    assert int(frontend["summary"]["steel_rule_row_count"]) >= 3
    assert isinstance(frontend.get("governing_steel_checks_top100"), list)
    assert len(frontend["governing_steel_checks_top100"]) >= 3
    assert all(
        str(row.get("clause", "")).startswith("KDS-STEEL-")
        for row in frontend["governing_steel_checks_top100"][:3]
    )
    assert any(str(card.get("label")) == "Steel Detail" for card in frontend.get("summary_cards", []))
