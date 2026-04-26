from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import numpy as np


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_prepare_opstool_606m_outrigger_synthetic_bridge(tmp_path: Path) -> None:
    ndtha_report = tmp_path / "nonlinear_ndtha_stress_report.pbd7.json"
    out_dir = tmp_path / "out"
    _write_json(
        ndtha_report,
        {
            "rows": [
                {
                    "case_id": "opstool_606m_megatall_model-00001",
                    "split": "train",
                    "topology_type": "outrigger",
                    "hazard_type": "seismic",
                    "summary": {
                        "story_count": 8,
                        "residual_drift_ratio_pct": 1.22,
                        "section_family_counts": {
                            "mega_column": 2,
                            "outrigger_beam": 3,
                            "core_column": 3,
                        },
                        "section_profile": {
                            "stiffness_scale_mean": 1.01,
                            "yield_scale_mean": 0.98,
                        },
                        "material_indices": {
                            "stiffness_scale_mean": 0.88,
                        },
                    },
                    "response": {
                        "story_drift_envelope_pct": [8.5, 7.9, 6.8, 5.7, 4.6, 3.5, 2.4, 1.2],
                        "final_story_drift_pct": [1.8, 1.65, 1.44, 1.2, 0.96, 0.72, 0.48, 0.22],
                    },
                    "section_probe_head": [
                        {
                            "story": 1,
                            "family_name": "mega_column",
                            "stiffness_scale": 1.03,
                            "yield_scale": 0.99,
                            "beam_tangent_scale": 0.95,
                            "beam_yielded_end_count": 0,
                            "section_moment_kNm": 144.0,
                        },
                        {
                            "story": 3,
                            "family_name": "outrigger_beam",
                            "stiffness_scale": 1.01,
                            "yield_scale": 0.97,
                            "beam_tangent_scale": 0.9,
                            "beam_yielded_end_count": 2,
                            "section_moment_kNm": 84.0,
                        },
                    ],
                }
            ]
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/prepare_opstool_606m_outrigger_synthetic_bridge.py",
            "--ndtha-report",
            str(ndtha_report),
            "--case-id",
            "opstool_606m_megatall_model-00001",
            "--out-dir",
            str(out_dir),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    report = json.loads((out_dir / "bridge_report.json").read_text(encoding="utf-8"))
    model = json.loads((out_dir / "model.json").read_text(encoding="utf-8"))
    changes = json.loads((out_dir / "synthetic_changes.json").read_text(encoding="utf-8"))
    change_summary = json.loads((out_dir / "synthetic_change_summary.json").read_text(encoding="utf-8"))
    release_gap = json.loads((out_dir / "synthetic_release_gap_report.json").read_text(encoding="utf-8"))
    export_report = json.loads((out_dir / "synthetic_export_report.json").read_text(encoding="utf-8"))
    dataset = np.load(out_dir / "dataset.npz", allow_pickle=True)

    assert report["contract_pass"] is True
    assert report["reason_code"] == "PASS"
    assert report["summary"]["viewer_ready"] is True
    assert report["summary"]["ai_overlay_ready"] is True
    assert report["summary"]["story_count"] == 8
    assert report["summary"]["drift_hotspot_story"] == 1
    assert report["summary"]["drift_hotspot_story_label"] == "S01"
    assert report["summary"]["drift_hotspot_family"] == "mega_column"

    assert model["model_kind"] == "synthetic_606m_outrigger_megatall"
    assert model["topology_metrics"]["story_count"] == 8
    assert len(model["model"]["nodes"]) > 0
    assert len(model["model"]["elements"]) > 0

    assert len(changes["changes"]) == 8
    assert len(change_summary["change_summary_rows"]) == 8
    assert release_gap["summary"]["commercial_grade"] == "Synthetic Benchmark"
    assert export_report["summary"]["direct_patch_change_count"] == 8

    assert "member_ids" in dataset.files
    assert "group_index_per_member" in dataset.files
    assert "story_band_index" in dataset.files
    assert dataset["member_ids"].shape[0] == len(model["model"]["elements"])
    assert dataset["group_index_per_member"].shape[0] == len(model["model"]["elements"])


def test_prepare_opstool_606m_outrigger_synthetic_bridge_suite(tmp_path: Path) -> None:
    ndtha_report = tmp_path / "nonlinear_ndtha_stress_report.pbd7.json"
    out_dir = tmp_path / "suite"
    _write_json(
        ndtha_report,
        {
            "rows": [
                {
                    "case_id": "opstool_606m_megatall_model-00001",
                    "topology_type": "outrigger",
                    "summary": {
                        "story_count": 6,
                        "residual_drift_ratio_pct": 1.0,
                        "section_family_counts": {"mega_column": 2, "outrigger_beam": 2, "core_column": 2},
                        "section_profile": {"stiffness_scale_mean": 1.0, "yield_scale_mean": 1.0},
                        "material_indices": {"stiffness_scale_mean": 0.9},
                    },
                    "response": {
                        "story_drift_envelope_pct": [8.0, 7.0, 6.0, 5.0, 4.0, 3.0],
                        "final_story_drift_pct": [1.8, 1.5, 1.2, 0.9, 0.6, 0.3],
                    },
                    "section_probe_head": [],
                },
                {
                    "case_id": "opstool_606m_megatall_model-00002",
                    "topology_type": "truss",
                    "summary": {"story_count": 6},
                    "response": {},
                    "section_probe_head": [],
                },
                {
                    "case_id": "opstool_606m_megatall_model-00005",
                    "topology_type": "outrigger",
                    "summary": {
                        "story_count": 6,
                        "residual_drift_ratio_pct": 1.1,
                        "section_family_counts": {"mega_column": 1, "outrigger_beam": 3, "core_column": 2},
                        "section_profile": {"stiffness_scale_mean": 1.01, "yield_scale_mean": 0.99},
                        "material_indices": {"stiffness_scale_mean": 0.88},
                    },
                    "response": {
                        "story_drift_envelope_pct": [8.4, 7.2, 6.4, 5.3, 4.1, 3.1],
                        "final_story_drift_pct": [1.9, 1.55, 1.25, 0.95, 0.62, 0.31],
                    },
                    "section_probe_head": [],
                },
            ]
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/prepare_opstool_606m_outrigger_synthetic_bridge.py",
            "--ndtha-report",
            str(ndtha_report),
            "--out-dir",
            str(out_dir),
            "--all-outrigger-cases",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    suite_report = json.loads((out_dir / "bridge_report.json").read_text(encoding="utf-8"))
    assert suite_report["contract_pass"] is True
    assert suite_report["reason_code"] == "PASS_SUITE"
    assert suite_report["summary"]["case_count"] == 2
    assert suite_report["summary"]["viewer_ready_count"] == 2
    assert (out_dir / "opstool_606m_megatall_model-00001" / "model.json").exists()
    assert (out_dir / "opstool_606m_megatall_model-00005" / "synthetic_changes.json").exists()
