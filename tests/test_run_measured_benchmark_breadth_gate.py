import json
import subprocess
import sys
from pathlib import Path


def test_run_measured_benchmark_breadth_gate_generates_expected_summary(tmp_path: Path) -> None:
    commercial = tmp_path / "commercial_readiness_report.json"
    opensees = tmp_path / "opensees_canonical_breadth_report.json"
    authority = tmp_path / "global_authority_gate_report.json"
    external = tmp_path / "external_benchmark_execution_status_manifest.json"
    canton_conversion = tmp_path / "missing_canton_conversion_report.json"
    canton_compare = tmp_path / "missing_canton_compare_report.json"
    out = tmp_path / "measured_benchmark_breadth_report.json"

    commercial.write_text(
        json.dumps(
            {
                "model_rows": [
                    {
                        "model_id": "baseline_rc_001",
                        "source_provenance": {
                            "measured_source_families": ["sac", "nheri"],
                            "measured_case_count": 51,
                        },
                    }
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    opensees.write_text(
        json.dumps(
            {
                "summary": {
                    "canonical_family_count": 6,
                    "canonical_case_count": 7,
                    "standalone_parser_ready_case_count": 3,
                },
                "rows": [
                    {"family_id": "designsafe_soft_story", "case_id": "designsafe_soft_story_case"},
                    {"family_id": "peer_transfer", "case_id": "peer_transfer_case"},
                    {"family_id": "luxinzheng_tall", "case_id": "luxinzheng_tall_case"},
                    {"family_id": "github_shell_wall", "case_id": "github_shell_wall_case"},
                    {"family_id": "public_lab_shell", "case_id": "public_lab_shell_case"},
                    {"family_id": "public_lab_bridge", "case_id": "public_lab_bridge_case"},
                    {"family_id": "public_lab_bridge", "case_id": "github_tunnel_case"},
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    authority.write_text(
        json.dumps(
            {
                "summary": {
                    "sac_case_count": 3,
                    "nheri_case_count": 3,
                    "opensees_case_count": 3,
                }
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    external.write_text(
        json.dumps(
            {
                "tasks": [
                    {
                        "case_id": f"external_case_{idx}",
                        "benchmark_family": family,
                        "execution_status": "ready",
                        "source_origin_class": "official_external_benchmark_fullcase",
                    }
                    for idx, family in enumerate(
                        [
                            "highrise_ndtha",
                            "soil_structure_interaction",
                            "wind_time_history",
                            "seismic_isolation_damping",
                            "moving_load_track_bridge",
                            "construction_stage_time_dependent",
                            "progressive_collapse",
                            "buckling_snapthrough",
                            "excavation_tunnel_ground_interaction",
                            "offshore_multiphysics_ssi",
                        ],
                        start=1,
                    )
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/run_measured_benchmark_breadth_gate.py",
            "--commercial-readiness",
            str(commercial),
            "--opensees-canonical-breadth",
            str(opensees),
            "--authority-report",
            str(authority),
            "--external-benchmark-status",
            str(external),
            "--canton-conversion-report",
            str(canton_conversion),
            "--canton-reduced-order-compare",
            str(canton_compare),
            "--peer-blind-prediction-cases",
            str(tmp_path / "missing_peer_cases.json"),
            "--peer-blind-prediction-compare",
            str(tmp_path / "missing_peer_compare.json"),
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
    assert payload["reason_code"] == "PASS"
    assert payload["summary"]["baseline_measured_family_count"] == 2
    assert payload["summary"]["baseline_measured_case_count"] == 51
    assert payload["summary"]["opensees_incremental_family_count"] == 6
    assert payload["summary"]["opensees_incremental_case_count"] == 7
    assert payload["summary"]["authority_incremental_family_count"] == 2
    assert payload["summary"]["authority_incremental_case_count"] == 6
    assert payload["summary"]["external_incremental_family_count"] == 10
    assert payload["summary"]["external_incremental_case_count"] == 10
    assert payload["summary"]["measured_family_count"] == 20
    assert payload["summary"]["measured_case_count"] == 74
    assert payload["summary"]["family_coverage_row_count"] == 20
    assert payload["summary"]["holdout_family_count"] == 20
    assert payload["summary"]["holdout_case_count"] == 20
    assert payload["summary"]["opensees_parser_ready_case_count"] == 3
    assert len(payload["family_coverage_rows"]) == 20
    assert len(payload["holdout_rows"]) == 20
    assert "Measured benchmark breadth: PASS" in payload["summary_line"]
    assert "holdout_families=20" in payload["summary_line"]

    worst_case = json.loads((tmp_path / "worst_case_report.json").read_text(encoding="utf-8"))
    assert worst_case["contract_pass"] is True
    assert worst_case["metric_basis"] == "coverage_risk_no_accuracy_claim"
    assert worst_case["accuracy_claimed"] is False
    assert worst_case["summary"]["worst_case_family_count"] == 20
    assert worst_case["summary"]["holdout_family_count"] == 20
    assert worst_case["rows"][0]["reason_codes"]


def test_run_measured_benchmark_breadth_gate_surfaces_canton_delta(tmp_path: Path) -> None:
    commercial = tmp_path / "commercial_readiness_report.json"
    opensees = tmp_path / "opensees_canonical_breadth_report.json"
    authority = tmp_path / "global_authority_gate_report.json"
    external = tmp_path / "external_benchmark_execution_status_manifest.json"
    canton_conversion = tmp_path / "canton_tower_conversion_report.json"
    canton_compare = tmp_path / "canton_tower_reduced_order_compare_report.json"
    out = tmp_path / "measured_benchmark_breadth_report.json"

    commercial.write_text(json.dumps({"model_rows": []}, ensure_ascii=False, indent=2), encoding="utf-8")
    opensees.write_text(json.dumps({"summary": {}, "rows": []}, ensure_ascii=False, indent=2), encoding="utf-8")
    authority.write_text(json.dumps({"summary": {}}, ensure_ascii=False, indent=2), encoding="utf-8")
    external.write_text(json.dumps({"tasks": []}, ensure_ascii=False, indent=2), encoding="utf-8")
    canton_conversion.write_text(
        json.dumps({"outputs": {"benchmark_case_count": 64, "dynamic_case_count": 64}}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    canton_compare.write_text(
        json.dumps(
            {
                "contract_pass": True,
                "summary_line": "Canton Tower reduced-order compare: PASS",
                "summary": {
                    "benchmark_case_count": 64,
                    "observed_channel_count": 20,
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
            "implementation/phase1/run_measured_benchmark_breadth_gate.py",
            "--commercial-readiness",
            str(commercial),
            "--opensees-canonical-breadth",
            str(opensees),
            "--authority-report",
            str(authority),
            "--external-benchmark-status",
            str(external),
            "--canton-conversion-report",
            str(canton_conversion),
            "--canton-reduced-order-compare",
            str(canton_compare),
            "--peer-blind-prediction-cases",
            str(tmp_path / "missing_peer_cases.json"),
            "--peer-blind-prediction-compare",
            str(tmp_path / "missing_peer_compare.json"),
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["summary"]["canton_incremental_family_count"] == 1
    assert payload["summary"]["canton_incremental_case_count"] == 64
    assert payload["summary"]["canton_observed_channel_count"] == 20
    assert "canton_delta=1/64" in payload["summary_line"]


def test_run_measured_benchmark_breadth_gate_surfaces_peer_blind_prediction_delta(tmp_path: Path) -> None:
    commercial = tmp_path / "commercial_readiness_report.json"
    opensees = tmp_path / "opensees_canonical_breadth_report.json"
    authority = tmp_path / "global_authority_gate_report.json"
    external = tmp_path / "external_benchmark_execution_status_manifest.json"
    canton_conversion = tmp_path / "missing_canton_conversion_report.json"
    canton_compare = tmp_path / "missing_canton_compare_report.json"
    peer_cases = tmp_path / "commercial_benchmark_cases.peer_blind_prediction_open.json"
    peer_compare = tmp_path / "peer_blind_prediction_compare_report.json"
    out = tmp_path / "measured_benchmark_breadth_report.json"

    commercial.write_text(
        json.dumps(
            {
                "model_rows": [
                    {
                        "model_id": "baseline",
                        "source_provenance": {
                            "measured_source_families": ["baseline_a", "baseline_b"],
                            "measured_case_count": 60,
                        },
                    }
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    opensees.write_text(
        json.dumps(
            {
                "summary": {"standalone_parser_ready_case_count": 3},
                "rows": [
                    {"family_id": "frame", "case_id": "frame_1", "parser_contract_ready": True},
                    {"family_id": "wall", "case_id": "wall_1", "parser_contract_ready": True},
                    {"family_id": "bridge", "case_id": "bridge_1", "parser_contract_ready": True},
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    authority.write_text(
        json.dumps({"summary": {"sac_case_count": 3, "nheri_case_count": 3}}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    external.write_text(
        json.dumps(
            {
                "tasks": [
                    {
                        "case_id": "external_case_1",
                        "benchmark_family": "ssi",
                        "execution_status": "completed",
                        "source_origin_class": "official_external_benchmark_fullcase",
                    },
                    {
                        "case_id": "external_case_2",
                        "benchmark_family": "wind",
                        "execution_status": "completed",
                        "source_origin_class": "official_external_benchmark_fullcase",
                    },
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    peer_cases.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "case_id": f"edefense_peer_blind_prediction_seed_01::gm{idx}",
                        "source_family": "edefense_peer_blind_prediction",
                        "source_member": "peer_blind_prediction_public_input_bundle_report.json",
                        "benchmark_case_status": "ready",
                        "compare_ready": True,
                        "blind_prediction_targets": {"measured_response_present": True},
                        "blind_prediction_metrics": {
                            "measured_channel_count": 11,
                            "drift_channel_count": 11,
                        },
                    }
                    for idx in range(1, 11)
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    peer_compare.write_text(
        json.dumps(
            {
                "contract_pass": True,
                "summary": {
                    "case_count": 10,
                    "measured_response_ready": True,
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
            "implementation/phase1/run_measured_benchmark_breadth_gate.py",
            "--commercial-readiness",
            str(commercial),
            "--opensees-canonical-breadth",
            str(opensees),
            "--authority-report",
            str(authority),
            "--external-benchmark-status",
            str(external),
            "--canton-conversion-report",
            str(canton_conversion),
            "--canton-reduced-order-compare",
            str(canton_compare),
            "--peer-blind-prediction-cases",
            str(peer_cases),
            "--peer-blind-prediction-compare",
            str(peer_compare),
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["summary"]["peer_blind_prediction_incremental_family_count"] == 1
    assert payload["summary"]["peer_blind_prediction_incremental_case_count"] == 10
    assert payload["summary"]["peer_blind_prediction_ready_case_count"] == 10
    assert payload["summary"]["peer_blind_prediction_compare_ready"] is True
    assert payload["summary"]["measured_case_count"] == 81
    assert "peer_blind_delta=1/10" in payload["summary_line"]
    family_ids = {row["family_id"] for row in payload["family_coverage_rows"]}
    assert "peer_blind_prediction:edefense_peer_blind_prediction" in family_ids


def test_run_measured_benchmark_breadth_gate_writes_coverage_worst_case_report(tmp_path: Path) -> None:
    commercial = tmp_path / "commercial_readiness_report.json"
    opensees = tmp_path / "opensees_canonical_breadth_report.json"
    authority = tmp_path / "global_authority_gate_report.json"
    external = tmp_path / "external_benchmark_execution_status_manifest.json"
    canton_conversion = tmp_path / "missing_canton_conversion_report.json"
    canton_compare = tmp_path / "missing_canton_compare_report.json"
    out = tmp_path / "measured_benchmark_breadth_report.json"
    worst_case_out = tmp_path / "custom_worst_case_report.json"

    commercial.write_text(
        json.dumps(
            {
                "model_rows": [
                    {
                        "model_id": "baseline",
                        "source_provenance": {
                            "measured_source_families": ["baseline_a", "baseline_b"],
                            "measured_case_count": 60,
                        },
                    }
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    opensees.write_text(
        json.dumps(
            {
                "summary": {"standalone_parser_ready_case_count": 3},
                "rows": [
                    {"family_id": "frame", "case_id": "frame_1", "parser_contract_ready": True},
                    {"family_id": "frame", "case_id": "frame_2", "parser_contract_ready": True},
                    {"family_id": "wall", "case_id": "wall_1", "parser_contract_ready": True},
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    authority.write_text(
        json.dumps({"summary": {"sac_case_count": 3, "nheri_case_count": 3}}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    external.write_text(
        json.dumps(
            {
                "tasks": [
                    {
                        "case_id": f"external_case_{idx}",
                        "benchmark_family": family,
                        "execution_status": "completed",
                        "source_origin_class": "official_external_benchmark_fullcase",
                    }
                    for idx, family in enumerate(["ssi", "ndtha", "buckling", "wind"], start=1)
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/run_measured_benchmark_breadth_gate.py",
            "--commercial-readiness",
            str(commercial),
            "--opensees-canonical-breadth",
            str(opensees),
            "--authority-report",
            str(authority),
            "--external-benchmark-status",
            str(external),
            "--canton-conversion-report",
            str(canton_conversion),
            "--canton-reduced-order-compare",
            str(canton_compare),
            "--peer-blind-prediction-cases",
            str(tmp_path / "missing_peer_cases.json"),
            "--peer-blind-prediction-compare",
            str(tmp_path / "missing_peer_compare.json"),
            "--out",
            str(out),
            "--worst-case-out",
            str(worst_case_out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    worst_case = json.loads(worst_case_out.read_text(encoding="utf-8"))
    assert worst_case["contract_pass"] is True
    assert worst_case["checks"]["no_accuracy_claim"] is True
    assert worst_case["metric_basis"] == "coverage_risk_no_accuracy_claim"
    assert worst_case["rows"][0]["measured_case_count"] == 1
    assert "LOW_CASE_COUNT_SINGLETON" in worst_case["rows"][0]["reason_codes"]
    assert worst_case["accuracy_claimed"] is False
