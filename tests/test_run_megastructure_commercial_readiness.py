from __future__ import annotations

import json
import subprocess
import sys
import hashlib
from pathlib import Path


SCRIPT = Path("implementation/phase1/run_megastructure_commercial_readiness.py")


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _case_rows(*, source_family: str, metric_source: str, prefix: str) -> list[dict]:
    rows: list[dict] = []
    topologies = ["rahmen", "truss", "wall-frame", "outrigger"]
    hazards = ["wind", "seismic", "combined", "seismic"]
    mixes = ["beam_only", "beam_only", "shell_beam_mix", "shell_beam_mix"]
    for idx in range(4):
        rows.append(
            {
                "case_id": f"{prefix}-{idx+1:03d}",
                "split": ["train", "train", "val", "test"][idx],
                "ood_tag": "in_distribution" if idx < 3 else "ood_hazard",
                "topology_type": topologies[idx],
                "hazard_type": hazards[idx],
                "source_family": source_family,
                "element_mix": mixes[idx],
                "load_scale": 1.0 + 0.05 * idx,
                "residual_norm": 0.02 + 0.01 * idx,
                "metrics": {
                    "drift_ratio_pct": {"hf": 0.8 + 0.1 * idx, "lf": 0.84 + 0.1 * idx},
                    "base_shear_kN": {"hf": 1200.0 + 50.0 * idx, "lf": 1180.0 + 50.0 * idx},
                    "mode_shape_mac": {"hf": 0.99, "lf": 0.97},
                    "buckling_factor": {"hf": 2.8, "lf": 2.7},
                    "equilibrium_residual": {"hf": 0.02, "lf": 0.03},
                },
                "metric_source": metric_source,
                "hf_source": (
                    {
                        "provider": "open_data_measurement",
                        "dataset": f"zenodo:{prefix.lower()}",
                        "hf_metric_extraction": "direct_from_measured_timeseries",
                    }
                    if metric_source == "open_data_measurement"
                    else {"provider": "commercial_solver_export"}
                ),
            }
        )
    return rows


def test_commercial_readiness_enforces_measured_benchmark_breadth(tmp_path: Path) -> None:
    work_dir = tmp_path / "work"
    out_path = tmp_path / "commercial_readiness_report.json"

    cases_a = tmp_path / "rwth.json"
    cases_b = tmp_path / "atwood.json"
    cases_c = tmp_path / "commercial.json"
    _write_json(
        cases_a,
        {
            "cases": _case_rows(source_family="rwth_zenodo", metric_source="open_data_measurement", prefix="RWTH"),
            "public_benchmark_cases": [{"case_id": f"RWTH-{i:03d}"} for i in range(1, 4)],
        },
    )
    _write_json(
        cases_b,
        {
            "cases": _case_rows(
                source_family="zenodo_atwood_highrise_shm_2025",
                metric_source="open_data_measurement",
                prefix="ATWOOD",
            ),
            "public_benchmark_cases": [{"case_id": f"ATWOOD-{i:03d}"} for i in range(1, 4)],
        },
    )
    _write_json(
        cases_c,
        {
            "cases": _case_rows(source_family="commercial_export", metric_source="commercial_solver_export", prefix="COMM"),
            "public_benchmark_cases": [{"case_id": f"COMM-{i:03d}"} for i in range(1, 4)],
        },
    )

    for stem in ("rwth", "atwood", "commercial"):
        model_dir = work_dir / "models" / stem
        _write_json(
            model_dir / "hf_benchmark.json",
            {
                "contract_pass": True,
                "metrics": {
                    "drift_error_pct": 1.0,
                    "base_shear_error_pct": 1.0,
                    "mode_shape_mac": 0.99,
                    "buckling_factor_error_pct": 1.0,
                },
            },
        )
        _write_json(
            model_dir / "noise_sensitivity.json",
            {
                "contract_pass": True,
                "summary": {
                    "high_noise_drift_error_pct_p95": 5.0,
                    "high_noise_base_shear_error_pct_p95": 5.0,
                },
            },
        )
        _write_json(model_dir / "noise_convergence.json", {"contract_pass": True, "summary": {"fail_count": 0}})

    _write_json(
        work_dir / "phase_correction_assimilation_report.json",
        {
            "contract_pass": True,
            "metrics": {"post_phase_error_deg": 2.0, "post_time_lag_ms": 1.0},
            "trajectory_head": [
                {"u_ref": 0.0, "u_post": 0.0},
                {"u_ref": 1.0, "u_post": 1.0},
                {"u_ref": 2.0, "u_post": 2.0},
                {"u_ref": 3.0, "u_post": 3.0},
            ],
        },
    )
    _write_json(
        work_dir / "heterogeneous_soil_ood_report.json",
        {"contract_pass": True, "metrics": {"recall": 0.95, "false_negative_ratio": 0.02}},
    )
    _write_json(work_dir / "multiscale_l3_streaming_report.json", {"contract_pass": True})
    _write_json(
        work_dir / "partitioned_scaleout_report.json",
        {
            "contract_pass": True,
            "checks": {"nightly_scale_pass": True, "real_graph_used": True, "gpu_strict_pass": True},
            "complexity_regression": {"memory_loglog_slope": 1.1, "latency_loglog_slope": 1.2},
        },
    )
    _write_json(
        work_dir / "scaleout_io_profile_report.json",
        {
            "contract_pass": True,
            "checks": {
                "probe_pass": True,
                "has_1m_plus": True,
                "scaleout_1m_microbatch_pass": True,
                "gpu_strict_pass": True,
            },
        },
    )

    cmd = [
        sys.executable,
        str(SCRIPT),
        "--model-cases",
        f"{cases_a},{cases_b},{cases_c}",
        "--target-split",
        "all",
        "--ci-mode",
        "nightly",
        "--work-dir",
        str(work_dir),
        "--out",
        str(out_path),
        "--reuse-existing-if-present",
        "--min-source-families",
        "3",
        "--require-measured-dynamic-targets",
        "--min-measured-source-families",
        "2",
        "--min-measured-case-count",
        "6",
        "--require-shell-beam-mix-cases",
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["checks"]["benchmark_breadth_pass"] is True
    assert payload["checks"]["measured_dynamic_targets_pass"] is True
    assert payload["checks"]["measured_source_family_pass"] is True
    assert payload["checks"]["measured_case_count_pass"] is True
    assert payload["global_metrics"]["source_family_count"] == 3
    assert payload["global_metrics"]["measured_source_family_count"] == 2
    assert payload["global_metrics"]["measured_case_count"] == 8
    assert payload["global_metrics"]["measured_shell_beam_mix_case_count"] >= 2
    work_items = {row["work_item_id"]: row for row in payload["residual_holdout_work_items"]}
    assert set(work_items) == {"RH-001", "RH-002", "RH-003"}
    assert work_items["RH-001"]["queue_name"] == "licensed_engineer_review_queue"
    assert work_items["RH-002"]["owner"] == "기존툴+기술사"
    assert work_items["RH-003"]["status"] == "open"
    assert all(row["full_commercial_replacement_blocker"] is True for row in work_items.values())


def test_commercial_readiness_reruns_stale_benchmark_report_when_cases_hash_changes(tmp_path: Path) -> None:
    work_dir = tmp_path / "work"
    out_path = tmp_path / "commercial_readiness_report.json"
    cases_path = tmp_path / "cases.json"
    _write_json(
        cases_path,
        {
            "cases": _case_rows(source_family="rwth_zenodo", metric_source="open_data_measurement", prefix="RWTH"),
            "public_benchmark_cases": [{"case_id": f"RWTH-{i:03d}"} for i in range(1, 4)],
        },
    )

    model_dir = work_dir / "models" / "cases"
    _write_json(
        model_dir / "hf_benchmark.json",
        {
            "contract_pass": True,
            "metrics": {
                "drift_error_pct": 99.0,
                "base_shear_error_pct": 99.0,
                "mode_shape_mac": 0.1,
                "buckling_factor_error_pct": 99.0,
            },
        },
    )
    _write_json(
        model_dir / "noise_sensitivity.json",
        {
            "contract_pass": True,
            "summary": {
                "high_noise_drift_error_pct_p95": 5.0,
                "high_noise_base_shear_error_pct_p95": 5.0,
            },
        },
    )
    _write_json(model_dir / "noise_convergence.json", {"contract_pass": True, "summary": {"fail_count": 0}})

    _write_json(
        work_dir / "phase_correction_assimilation_report.json",
        {
            "contract_pass": True,
            "metrics": {"post_phase_error_deg": 2.0, "post_time_lag_ms": 1.0},
            "trajectory_head": [
                {"u_ref": 0.0, "u_post": 0.0},
                {"u_ref": 1.0, "u_post": 1.0},
                {"u_ref": 2.0, "u_post": 2.0},
                {"u_ref": 3.0, "u_post": 3.0},
            ],
        },
    )
    _write_json(
        work_dir / "heterogeneous_soil_ood_report.json",
        {"contract_pass": True, "metrics": {"recall": 0.95, "false_negative_ratio": 0.02}},
    )
    _write_json(work_dir / "multiscale_l3_streaming_report.json", {"contract_pass": True})
    _write_json(
        work_dir / "partitioned_scaleout_report.json",
        {
            "contract_pass": True,
            "checks": {"nightly_scale_pass": True, "real_graph_used": True, "gpu_strict_pass": True},
            "complexity_regression": {"memory_loglog_slope": 1.1, "latency_loglog_slope": 1.2},
        },
    )
    _write_json(
        work_dir / "scaleout_io_profile_report.json",
        {
            "contract_pass": True,
            "checks": {
                "probe_pass": True,
                "has_1m_plus": True,
                "scaleout_1m_microbatch_pass": True,
                "gpu_strict_pass": True,
            },
        },
    )

    cmd = [
        sys.executable,
        str(SCRIPT),
        "--model-cases",
        str(cases_path),
        "--target-split",
        "all",
        "--ci-mode",
        "nightly",
        "--work-dir",
        str(work_dir),
        "--out",
        str(out_path),
        "--reuse-existing-if-present",
        "--benchmark-epochs",
        "20",
        "--benchmark-branches",
        "4",
        "--benchmark-top-k",
        "2",
        "--min-source-families",
        "1",
        "--min-total-case-count",
        "4",
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["model_rows"][0]["checks"]["accuracy_pass"] is True
    assert payload["model_rows"][0]["metrics"]["mode_shape_mac"] >= 0.95

    benchmark_report = json.loads((model_dir / "hf_benchmark.json").read_text(encoding="utf-8"))
    expected_sha = hashlib.sha256(cases_path.read_bytes()).hexdigest()
    assert benchmark_report["source_cases_sha256"] == expected_sha
