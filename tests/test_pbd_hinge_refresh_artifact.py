from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import numpy as np


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_pbd_hinge_refresh_artifact_reports_missing_source_as_proxy_only(tmp_path: Path) -> None:
    dataset = tmp_path / "design_opt_dataset.json"
    _write_json(
        dataset,
        {
            "contract_pass": True,
            "summary": {"member_count": 2},
            "rows_head": [{"member_id": "B101"}, {"member_id": "C101"}],
        },
    )
    out = tmp_path / "pbd_hinge_refresh_artifact.json"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_pbd_hinge_refresh_artifact.py",
            "--design-optimization-dataset",
            str(dataset),
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
    assert payload["summary"]["hinge_state_mode"] == "proxy_only_hinge_visualization"
    assert payload["summary"]["source_mode"] == "proxy_only_dataset_heuristic"


def test_pbd_hinge_refresh_artifact_requires_member_overlap(tmp_path: Path) -> None:
    dataset = tmp_path / "design_opt_dataset.json"
    _write_json(
        dataset,
        {
            "contract_pass": True,
            "summary": {"member_count": 2},
            "rows_head": [{"member_id": "B101"}, {"member_id": "C101"}],
        },
    )
    source = tmp_path / "hinge_refresh_source.json"
    _write_json(
        source,
        {
            "hinge_refresh_rows": [
                {
                    "member_id": "W999",
                    "yield_rotation": 0.01,
                    "ultimate_rotation": 0.08,
                    "rebar_sensitive": True,
                }
            ]
        },
    )
    out = tmp_path / "pbd_hinge_refresh_artifact.json"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_pbd_hinge_refresh_artifact.py",
            "--design-optimization-dataset",
            str(dataset),
            "--source-input",
            str(source),
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
    assert payload["reason_code"] == "ERR_SOURCE_MEMBER_OVERLAP_MISSING"
    assert payload["summary"]["overlap_member_count"] == 0


def test_pbd_hinge_refresh_artifact_passes_with_rebar_sensitive_overlap_rows(tmp_path: Path) -> None:
    dataset = tmp_path / "design_opt_dataset.json"
    _write_json(
        dataset,
        {
            "contract_pass": True,
            "summary": {"member_count": 2},
            "rows_head": [{"member_id": "B101"}, {"member_id": "C101"}],
        },
    )
    source = tmp_path / "hinge_refresh_source.json"
    _write_json(
        source,
        {
            "solver_export": {
                "hinge_refresh": {
                    "hinge_refresh_rows": [
                        {
                            "member_id": "B101",
                            "yield_rotation": 0.01,
                            "ultimate_rotation": 0.08,
                            "updated_after_optimization": True,
                        }
                    ]
                }
            }
        },
    )
    out = tmp_path / "pbd_hinge_refresh_artifact.json"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_pbd_hinge_refresh_artifact.py",
            "--design-optimization-dataset",
            str(dataset),
            "--source-input",
            str(source),
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
    assert payload["summary"]["source_mode"] == "rebar_sensitive_member_local_refresh"
    assert payload["summary"]["overlap_member_count"] == 1
    assert payload["summary"]["rebar_sensitive_member_count"] == 1


def test_pbd_hinge_refresh_artifact_uses_optimized_member_scope_from_npz_when_rows_head_is_truncated(tmp_path: Path) -> None:
    dataset = tmp_path / "design_opt_dataset.json"
    dataset_npz = tmp_path / "design_opt_dataset.npz"
    changes = tmp_path / "design_optimization_cost_reduction_changes.json"
    _write_json(
        dataset,
        {
            "contract_pass": True,
            "summary": {"member_count": 3},
            "rows_head": [{"member_id": "B101"}, {"member_id": "C101"}],
        },
    )
    np.savez(
        dataset_npz,
        member_ids=np.asarray(["B101", "C101", "W901"], dtype=object),
        group_ids=np.asarray(["G1", "G2", "OPT_WALL"], dtype=object),
    )
    _write_json(changes, {"changes": [{"group_id": "OPT_WALL", "member_type": "wall"}]})
    source = tmp_path / "hinge_refresh_source.json"
    _write_json(
        source,
        {
            "hinge_refresh_rows": [
                {
                    "member_id": "W901",
                    "yield_rotation": 0.01,
                    "ultimate_rotation": 0.08,
                    "recomputed_from_rebar": True,
                }
            ]
        },
    )
    out = tmp_path / "pbd_hinge_refresh_artifact.json"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_pbd_hinge_refresh_artifact.py",
            "--design-optimization-dataset",
            str(dataset),
            "--design-optimization-npz",
            str(dataset_npz),
            "--cost-reduction-changes",
            str(changes),
            "--source-input",
            str(source),
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
    assert payload["summary"]["candidate_scope_mode"] == "optimized_groups_from_npz"
    assert payload["summary"]["optimized_group_count"] == 1
    assert payload["summary"]["optimized_target_member_count"] == 1
    assert payload["summary"]["dataset_rows_head_member_count"] == 2
    assert payload["summary"]["dataset_npz_member_count"] == 3
    assert payload["summary"]["overlap_member_count"] == 1
    assert payload["source_provenance"]["candidate_member_ids_head"] == ["W901"]
