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
    assert payload["summary"]["opensees_parser_ready_case_count"] == 3
    assert "Measured benchmark breadth: PASS" in payload["summary_line"]


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
