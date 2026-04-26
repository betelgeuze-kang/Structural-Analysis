from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _execution_manifest_payload(source_manifest_path: Path) -> dict:
    return {
        "schema_version": "1.0",
        "generated_at": "2026-03-22T00:00:00+00:00",
        "contract_pass": True,
        "reason_code": "PASS_EXECUTION_MANIFEST_READY",
        "summary": {
            "execution_mode": "limited",
            "ready_task_count": 1,
            "blocked_task_count": 0,
            "review_boundary_pending_count": 0,
        },
        "ready_tasks": [
            {
                "task_id": "wind::seed_a",
                "phase": "component_wind",
                "benchmark_family": "tpu_raw_hffb_mapping",
                "submission_scope": "limited_external_benchmark",
                "execution_status": "ready",
                "input_path": str(source_manifest_path),
                "source_origin_class": "official_external_benchmark",
                "holdout_split": "val",
            }
        ],
        "blocked_tasks": [],
    }


def _midas_model_payload() -> dict:
    return {
        "model": {
            "nodes": [
                {"id": 1, "z": 0.0},
                {"id": 2, "z": 0.0},
                {"id": 3, "z": 10.0},
                {"id": 4, "z": 10.0},
            ],
            "elements": [
                {"id": 101, "node_ids": [1, 2, 3, 4]},
            ],
            "loads": {
                "pressure_loads": [
                    {"element_ids": [101], "load_case": "LIVE", "element_type": "PLATE", "load_type": "PRESSURE"},
                ]
            },
        }
    }


def test_execute_external_benchmark_task_component_wind(tmp_path: Path) -> None:
    raw_wind = tmp_path / "seed.csv"
    raw_wind.write_text("time_s,pressure_01,pressure_02\n0.0,1.0,2.0\n0.1,1.1,2.1\n", encoding="utf-8")
    source_manifest = tmp_path / "seed.source_manifest.json"
    _write_json(
        source_manifest,
        {
            "schema_version": "1.0",
            "real_source": True,
            "data_path": str(raw_wind),
            "source_url": "https://example.test/tpu/seed",
            "source_name": "TPU Seed",
            "source_origin_class": "official_external_benchmark",
            "sha256": _sha256(raw_wind),
        },
    )
    execution_manifest = tmp_path / "external_benchmark_execution_manifest.json"
    updates_json = tmp_path / "external_benchmark_execution_updates.json"
    status_manifest_out = tmp_path / "external_benchmark_execution_status_manifest.json"
    runs_dir = tmp_path / "runs"
    midas_json = tmp_path / "midas_model.json"
    midas_conversion = tmp_path / "midas_conversion_report.json"
    _write_json(execution_manifest, _execution_manifest_payload(source_manifest))
    _write_json(midas_json, _midas_model_payload())
    _write_json(midas_conversion, {"metrics": {"bound_pressure_row_count": 1}})

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/execute_external_benchmark_task.py",
            "--execution-manifest",
            str(execution_manifest),
            "--updates-json",
            str(updates_json),
            "--status-manifest-out",
            str(status_manifest_out),
            "--runs-dir",
            str(runs_dir),
            "--task-id",
            "wind::seed_a",
            "--midas-json",
            str(midas_json),
            "--midas-conversion",
            str(midas_conversion),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    report = json.loads(proc.stdout)
    assert report["contract_pass"] is True
    assert report["lifecycle_status_set"] == "completed"
    artifact_path = Path(report["artifact_path"])
    assert artifact_path.exists()
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert artifact["contract_pass"] is True
    updates = json.loads(updates_json.read_text(encoding="utf-8"))
    assert updates["updates"][0]["task_id"] == "wind::seed_a"
    assert updates["updates"][0]["lifecycle_status"] == "completed"
    status_manifest = json.loads(status_manifest_out.read_text(encoding="utf-8"))
    assert status_manifest["summary"]["completed_task_count"] == 1
    assert status_manifest["summary"]["status_mode"] == "execution_complete_no_fail"


def test_execute_external_benchmark_task_unknown_family_fails(tmp_path: Path) -> None:
    execution_manifest = tmp_path / "external_benchmark_execution_manifest.json"
    _write_json(
        execution_manifest,
        {
            "ready_tasks": [
                {
                    "task_id": "weird::task",
                    "phase": "component_unknown",
                    "benchmark_family": "unknown_family",
                    "execution_status": "ready",
                    "input_path": "unknown",
                }
            ],
            "blocked_tasks": [],
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/execute_external_benchmark_task.py",
            "--execution-manifest",
            str(execution_manifest),
            "--task-id",
            "weird::task",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0
    report = json.loads(proc.stdout)
    assert report["reason_code"] == "ERR_UNSUPPORTED_BENCHMARK_FAMILY"


def test_execute_external_benchmark_task_component_hinge(tmp_path: Path) -> None:
    fixture = tmp_path / "seed.hinge_fixture.json"
    _write_json(
        fixture,
        {
            "seed_id": "peer_spd_rc_column_rectangular_seed_01",
            "holdout_split": "train",
            "specimen_summary": {"specimen_id": "121"},
            "hysteresis_summary": {"point_count": 1169, "peak_abs_drift_ratio": 0.042},
            "hinge_refresh_targets": {
                "rebar_sensitive_expected": True,
                "confinement_sensitive_expected": False,
                "axial_load_sensitive_expected": False,
            },
            "contract_pass": True,
        },
    )
    execution_manifest = tmp_path / "external_benchmark_execution_manifest.json"
    updates_json = tmp_path / "external_benchmark_execution_updates.json"
    status_manifest_out = tmp_path / "external_benchmark_execution_status_manifest.json"
    runs_dir = tmp_path / "runs"
    _write_json(
        execution_manifest,
        {
            "summary": {"execution_mode": "limited", "ready_task_count": 1, "blocked_task_count": 0, "review_boundary_pending_count": 0},
            "ready_tasks": [
                {
                    "task_id": "hinge::peer_spd_rc_column_rectangular_seed_01",
                    "phase": "component_hinge",
                    "benchmark_family": "peer_spd_column_hinge",
                    "execution_status": "ready",
                    "input_path": str(fixture),
                }
            ],
            "blocked_tasks": [],
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/execute_external_benchmark_task.py",
            "--execution-manifest",
            str(execution_manifest),
            "--updates-json",
            str(updates_json),
            "--status-manifest-out",
            str(status_manifest_out),
            "--runs-dir",
            str(runs_dir),
            "--task-id",
            "hinge::peer_spd_rc_column_rectangular_seed_01",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    report = json.loads(proc.stdout)
    assert report["contract_pass"] is True
    assert report["lifecycle_status_set"] == "completed"
    artifact = json.loads(Path(report["artifact_path"]).read_text(encoding="utf-8"))
    assert artifact["contract_pass"] is True
    assert artifact["summary"]["specimen_id"] == "121"
    status_manifest = json.loads(status_manifest_out.read_text(encoding="utf-8"))
    assert status_manifest["summary"]["completed_task_count"] == 1


def test_execute_external_benchmark_task_system_anchor(tmp_path: Path) -> None:
    report_path = tmp_path / "nonlinear_frame_engine_report.json"
    _write_json(
        report_path,
        {
            "contract_pass": True,
            "reason_code": "PASS",
            "summary": {
                "case_count": 12,
                "drift_error_pct_p95": 3.2,
            },
        },
    )
    execution_manifest = tmp_path / "external_benchmark_execution_manifest.json"
    updates_json = tmp_path / "external_benchmark_execution_updates.json"
    status_manifest_out = tmp_path / "external_benchmark_execution_status_manifest.json"
    runs_dir = tmp_path / "runs"
    _write_json(
        execution_manifest,
        {
            "summary": {"execution_mode": "limited", "ready_task_count": 1, "blocked_task_count": 0, "review_boundary_pending_count": 0},
            "ready_tasks": [
                {
                    "task_id": "system::nonlinear_frame",
                    "phase": "system_anchor",
                    "benchmark_family": "nonlinear_frame",
                    "execution_status": "ready_reference_anchor",
                    "input_path": str(report_path),
                }
            ],
            "blocked_tasks": [],
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/execute_external_benchmark_task.py",
            "--execution-manifest",
            str(execution_manifest),
            "--updates-json",
            str(updates_json),
            "--status-manifest-out",
            str(status_manifest_out),
            "--runs-dir",
            str(runs_dir),
            "--task-id",
            "system::nonlinear_frame",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    report = json.loads(proc.stdout)
    assert report["contract_pass"] is True
    assert report["lifecycle_status_set"] == "completed"
    artifact = json.loads(Path(report["artifact_path"]).read_text(encoding="utf-8"))
    assert artifact["contract_pass"] is True
    assert artifact["summary"]["case_count"] == 12
    status_manifest = json.loads(status_manifest_out.read_text(encoding="utf-8"))
    assert status_manifest["summary"]["completed_task_count"] == 1


def test_execute_external_benchmark_task_hardest_case_builds_receipt_and_bundle(tmp_path: Path) -> None:
    execution_manifest = tmp_path / "external_benchmark_execution_manifest.json"
    updates_json = tmp_path / "external_benchmark_execution_updates.json"
    status_manifest_out = tmp_path / "external_benchmark_execution_status_manifest.json"
    runs_dir = tmp_path / "runs"
    _write_json(
        execution_manifest,
        {
            "summary": {"execution_mode": "limited", "ready_task_count": 1, "blocked_task_count": 0, "review_boundary_pending_count": 0},
            "ready_tasks": [
                {
                    "task_id": "hardest::peer_tbi_tall_building_ndtha",
                    "case_id": "peer_tbi_tall_building_ndtha",
                    "case_label": "PEER TBI Tall Building NDTHA",
                    "phase": "hardest_case",
                    "benchmark_family": "highrise_ndtha",
                    "execution_status": "ready",
                    "input_path": "implementation/phase1/nonlinear_ndtha_stress_report.json",
                }
            ],
            "blocked_tasks": [],
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/execute_external_benchmark_task.py",
            "--execution-manifest",
            str(execution_manifest),
            "--updates-json",
            str(updates_json),
            "--status-manifest-out",
            str(status_manifest_out),
            "--runs-dir",
            str(runs_dir),
            "--task-id",
            "hardest::peer_tbi_tall_building_ndtha",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    report = json.loads(proc.stdout)
    assert report["contract_pass"] is True
    assert Path(report["kpi_receipt_path"]).exists()
    assert Path(report["case_bundle_zip_path"]).exists()
    receipt_text = Path(report["kpi_receipt_path"]).with_suffix(".md").read_text(encoding="utf-8")
    assert "Appendix: MIDAS Native Roundtrip / Write-Back" in receipt_text
    bundle_dir = Path(report["case_bundle_dir"])
    assert (bundle_dir / "unsupported_lossy_card_family_appendix.md").exists()
    assert (bundle_dir / "unsupported_lossy_card_family_appendix.json").exists()
    status_manifest = json.loads(status_manifest_out.read_text(encoding="utf-8"))
    assert status_manifest["summary"]["kpi_receipt_task_count"] == 1
    assert status_manifest["summary"]["case_bundle_zip_task_count"] == 1
