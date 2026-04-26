from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_pbd_hinge_refresh_report_stays_proxy_only_without_artifact(tmp_path: Path) -> None:
    dataset = tmp_path / "design_opt_dataset.json"
    pbd = tmp_path / "pbd.json"
    midas = tmp_path / "midas.json"
    ndtha = tmp_path / "ndtha.json"
    out = tmp_path / "pbd_hinge_refresh_report.json"
    _write_json(
        dataset,
        {
            "contract_pass": True,
            "summary": {"member_count": 2},
            "rows_head": [
                {"member_id": "B101", "member_hinge_state_source": "proxy", "member_family": "beam"},
                {"member_id": "C101", "member_hinge_state_source": "proxy", "member_family": "column"},
            ],
        },
    )
    _write_json(pbd, {"contract_pass": True, "metrics": {"drift_split_counts": {"test": 3}}})
    _write_json(midas, {"contract_pass": True})
    _write_json(ndtha, {"contract_pass": True})
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_pbd_hinge_refresh_report.py",
            "--design-optimization-dataset",
            str(dataset),
            "--pbd-review-package",
            str(pbd),
            "--midas-conversion",
            str(midas),
            "--ndtha-stress-report",
            str(ndtha),
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is False
    assert payload["reason_code"] == "ERR_HINGE_PROXY_ONLY"
    assert payload["summary"]["hinge_state_mode"] == "proxy_only_hinge_visualization"
    assert payload["summary"]["hinge_refresh_artifact_present"] is False


def test_pbd_hinge_refresh_report_uses_attached_artifact_provenance(tmp_path: Path) -> None:
    dataset = tmp_path / "design_opt_dataset.json"
    pbd = tmp_path / "pbd.json"
    midas = tmp_path / "midas.json"
    ndtha = tmp_path / "ndtha.json"
    artifact = tmp_path / "pbd_hinge_refresh_artifact.json"
    out = tmp_path / "pbd_hinge_refresh_report.json"
    _write_json(
        dataset,
        {
            "contract_pass": True,
            "summary": {"member_count": 2},
            "rows_head": [{"member_id": "B101", "member_family": "beam"}, {"member_id": "C101", "member_family": "column"}],
        },
    )
    _write_json(pbd, {"contract_pass": True, "metrics": {"drift_split_counts": {"test": 3}}})
    _write_json(midas, {"contract_pass": True})
    _write_json(ndtha, {"contract_pass": True})
    _write_json(
        artifact,
        {
            "contract_pass": True,
            "reason_code": "PASS",
            "reason": "rebar-sensitive dynamic hinge-refresh rows are attached for optimized members",
            "summary": {
                "hinge_state_mode": "computed_member_local_hinge_refresh",
                "source_artifact_kind": "hinge_refresh_source_json",
                "source_mode": "rebar_sensitive_member_local_refresh",
                "overlap_member_count": 1,
                "rebar_sensitive_member_count": 1,
            },
        },
    )
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_pbd_hinge_refresh_report.py",
            "--design-optimization-dataset",
            str(dataset),
            "--pbd-review-package",
            str(pbd),
            "--midas-conversion",
            str(midas),
            "--ndtha-stress-report",
            str(ndtha),
            "--hinge-refresh-artifact",
            str(artifact),
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
    assert payload["summary"]["hinge_state_mode"] == "computed_member_local_hinge_refresh"
    assert payload["summary"]["hinge_refresh_artifact_present"] is True
    assert payload["summary"]["hinge_refresh_artifact_kind"] == "hinge_refresh_source_json"
    assert payload["summary"]["hinge_refresh_source_mode"] == "rebar_sensitive_member_local_refresh"
    assert payload["summary"]["hinge_refresh_candidate_scope_mode"] == ""
    assert payload["summary"]["hinge_refresh_overlap_member_count"] == 1
    assert payload["summary"]["hinge_refresh_rebar_sensitive_member_count"] == 1


def test_pbd_hinge_refresh_report_uses_member_type_as_family_fallback_and_carries_scope_metadata(tmp_path: Path) -> None:
    dataset = tmp_path / "design_opt_dataset.json"
    pbd = tmp_path / "pbd.json"
    midas = tmp_path / "midas.json"
    ndtha = tmp_path / "ndtha.json"
    artifact = tmp_path / "pbd_hinge_refresh_artifact.json"
    out = tmp_path / "pbd_hinge_refresh_report.json"
    _write_json(
        dataset,
        {
            "contract_pass": True,
            "summary": {"member_count": 3},
            "rows_head": [
                {"member_id": "B101", "member_type": "beam"},
                {"member_id": "W901", "member_type": "wall"},
            ],
        },
    )
    _write_json(pbd, {"contract_pass": True, "metrics": {"drift_split_counts": {"test": 3}}})
    _write_json(midas, {"contract_pass": True})
    _write_json(ndtha, {"contract_pass": True})
    _write_json(
        artifact,
        {
            "contract_pass": False,
            "reason_code": "ERR_SOURCE_MISSING",
            "reason": "no hinge-refresh source rows are attached for optimized member scope (12 members across 4 changed groups)",
            "summary": {
                "hinge_state_mode": "proxy_only_hinge_visualization",
                "source_artifact_kind": "hinge_refresh_source_json",
                "source_mode": "proxy_only_dataset_heuristic",
                "candidate_scope_mode": "optimized_groups_from_npz",
                "optimized_group_count": 4,
                "optimized_target_member_count": 12,
                "dataset_npz_member_count": 12728,
                "overlap_member_count": 0,
                "rebar_sensitive_member_count": 0,
            },
        },
    )
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_pbd_hinge_refresh_report.py",
            "--design-optimization-dataset",
            str(dataset),
            "--pbd-review-package",
            str(pbd),
            "--midas-conversion",
            str(midas),
            "--ndtha-stress-report",
            str(ndtha),
            "--hinge-refresh-artifact",
            str(artifact),
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is False
    assert payload["reason_code"] == "ERR_SOURCE_MISSING"
    assert payload["summary"]["pbd_family_type_count"] == 2
    assert payload["artifact_samples"]["member_family_counts_head"] == {"beam": 1, "wall": 1}
    assert payload["summary"]["hinge_refresh_candidate_scope_mode"] == "optimized_groups_from_npz"
    assert payload["summary"]["hinge_refresh_optimized_group_count"] == 4
    assert payload["summary"]["hinge_refresh_optimized_target_member_count"] == 12
    assert payload["summary"]["hinge_refresh_dataset_npz_member_count"] == 12728


def test_pbd_hinge_refresh_report_carries_peer_benchmark_provenance(tmp_path: Path) -> None:
    dataset = tmp_path / "design_opt_dataset.json"
    pbd = tmp_path / "pbd.json"
    midas = tmp_path / "midas.json"
    ndtha = tmp_path / "ndtha.json"
    artifact = tmp_path / "pbd_hinge_refresh_artifact.json"
    benchmark_registry = tmp_path / "pbd_hinge_benchmark_asset_registry.json"
    benchmark_gate = tmp_path / "peer_spd_hinge_benchmark_gate_report.json"
    benchmark_fixture_regression = tmp_path / "peer_spd_hinge_fixture_regression_report.json"
    benchmark_alignment = tmp_path / "peer_spd_hinge_refresh_alignment_report.json"
    out = tmp_path / "pbd_hinge_refresh_report.json"
    _write_json(
        dataset,
        {
            "contract_pass": True,
            "summary": {"member_count": 2},
            "rows_head": [{"member_id": "B101", "member_family": "beam"}, {"member_id": "C101", "member_family": "column"}],
        },
    )
    _write_json(pbd, {"contract_pass": True, "metrics": {"drift_split_counts": {"test": 3}}})
    _write_json(midas, {"contract_pass": True})
    _write_json(ndtha, {"contract_pass": True})
    _write_json(
        artifact,
        {
            "contract_pass": True,
            "reason_code": "PASS",
            "reason": "rebar-sensitive dynamic hinge-refresh rows are attached for optimized members",
            "summary": {
                "hinge_state_mode": "computed_member_local_hinge_refresh",
                "source_artifact_kind": "hinge_refresh_source_json",
                "source_mode": "rebar_sensitive_member_local_refresh",
                "overlap_member_count": 2,
                "rebar_sensitive_member_count": 1,
            },
        },
    )
    _write_json(
        benchmark_registry,
        {
            "contract_pass": True,
            "summary": {
                "benchmark_ready_asset_count": 5,
                "train_count": 2,
                "val_count": 2,
                "holdout_count": 1,
                "rebar_sensitive_count": 1,
                "confinement_sensitive_count": 1,
            },
        },
    )
    _write_json(
        benchmark_gate,
        {
            "contract_pass": True,
            "reason": "PEER SPD hinge benchmark pool satisfies the current diversification contract.",
            "observed": {
                "train_count": 2,
                "val_count": 2,
                "holdout_count": 1,
                "rebar_sensitive_count": 1,
                "confinement_sensitive_count": 1,
                "benchmark_ready_asset_count": 5,
            },
        },
    )
    _write_json(
        benchmark_fixture_regression,
        {
            "contract_pass": True,
            "reason": "PEER SPD hinge fixtures are present and consistent.",
            "observed": {
                "fixture_count": 5,
                "min_point_count": 449,
                "min_peak_drift_ratio": 0.0366,
            },
        },
    )
    _write_json(
        benchmark_alignment,
        {
            "contract_pass": True,
            "reason": "Current hinge-refresh source covers column and rebar-sensitive benchmark scope within the PEER SPD rebar envelope.",
            "observed": {
                "refresh_column_row_count": 5,
                "refresh_rebar_sensitive_column_count": 5,
                "benchmark_longitudinal_rebar_ratio_min": 0.0127,
                "benchmark_longitudinal_rebar_ratio_max": 0.0603,
                "refresh_combined_rebar_ratio_min": 0.064,
                "refresh_combined_rebar_ratio_max": 0.074,
            },
        },
    )
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_pbd_hinge_refresh_report.py",
            "--design-optimization-dataset",
            str(dataset),
            "--pbd-review-package",
            str(pbd),
            "--midas-conversion",
            str(midas),
            "--ndtha-stress-report",
            str(ndtha),
            "--benchmark-asset-registry",
            str(benchmark_registry),
            "--benchmark-gate-report",
            str(benchmark_gate),
            "--benchmark-fixture-regression-report",
            str(benchmark_fixture_regression),
            "--benchmark-alignment-report",
            str(benchmark_alignment),
            "--hinge-refresh-artifact",
            str(artifact),
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["summary"]["hinge_benchmark_gate_pass"] is True
    assert payload["summary"]["hinge_benchmark_asset_count"] == 5
    assert payload["summary"]["hinge_benchmark_train_count"] == 2
    assert payload["summary"]["hinge_benchmark_val_count"] == 2
    assert payload["summary"]["hinge_benchmark_holdout_count"] == 1
    assert payload["summary"]["hinge_benchmark_rebar_sensitive_count"] == 1
    assert payload["summary"]["hinge_benchmark_confinement_sensitive_count"] == 1
    assert payload["summary"]["hinge_benchmark_fixture_regression_pass"] is True
    assert payload["summary"]["hinge_benchmark_fixture_count"] == 5
    assert payload["summary"]["hinge_benchmark_fixture_min_point_count"] == 449
    assert payload["summary"]["hinge_benchmark_alignment_pass"] is True
    assert payload["summary"]["hinge_benchmark_alignment_refresh_column_row_count"] == 5
    assert payload["summary"]["hinge_benchmark_alignment_rebar_sensitive_column_count"] == 5
    assert payload["summary"]["hinge_benchmark_alignment_benchmark_rebar_ratio_min"] == 0.0127
    assert payload["summary"]["hinge_benchmark_alignment_benchmark_rebar_ratio_max"] == 0.0603
    assert payload["summary"]["hinge_benchmark_alignment_refresh_rebar_ratio_min"] == 0.064
    assert payload["summary"]["hinge_benchmark_alignment_refresh_rebar_ratio_max"] == 0.074
    assert payload["checks"]["hinge_benchmark_gate_pass"] is True
    assert payload["checks"]["hinge_benchmark_fixture_regression_pass"] is True
    assert payload["checks"]["hinge_benchmark_alignment_pass"] is True
