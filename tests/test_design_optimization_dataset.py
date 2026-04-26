from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import numpy as np

from implementation.phase1.design_optimization_env import aggregate_group_state
from implementation.phase1.generate_design_optimization_dataset import _member_type_from_element


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _foundation_fixture_path(name: str) -> Path:
    return Path(__file__).resolve().parent / "fixtures" / "foundation_realish" / name


def test_generate_design_optimization_dataset(tmp_path: Path) -> None:
    model = {
        "model": {
            "nodes": [
                {"id": 1, "x": 0.0, "y": 0.0, "z": 0.0},
                {"id": 2, "x": 1.0, "y": 0.0, "z": 0.0},
                {"id": 3, "x": 1.0, "y": 0.0, "z": 1.0},
                {"id": 4, "x": 1.0, "y": 1.0, "z": 1.0},
                {"id": 5, "x": 1.0, "y": 1.0, "z": 0.0},
                {"id": 6, "x": 2.0, "y": 0.0, "z": 0.0},
            ],
            "elements": [
                {"id": 1, "type": "BEAM", "section": 10, "nodes": [1, 2]},
                {"id": 2, "type": "PLATE", "section": 11, "nodes": [2, 3, 4, 5]},
                {"id": 3, "type": "ELASTICLINK", "section": 12, "nodes": [5, 6]},
            ],
            "sections": [
                {"id": 10, "name": "B-SEC"},
                {"id": 11, "name": "DBUSER"},
                {"id": 12, "name": "JOINT-SEC"},
            ],
        }
    }
    code_check = {
        "rows": [
            {"member_id": "1", "max_dcr": 0.91, "governing_component": "moment"},
            {"member_id": "2", "max_dcr": 0.84, "governing_component": "shear"},
            {"member_id": "3", "max_dcr": 0.66, "governing_component": "connection_slip"},
        ],
        "member_check_rows": [
            {"member_id": "1", "member_type": "beam", "rule_family": "strength", "clause": "KDS-MOMENT-Y-001", "dcr": 0.91},
            {"member_id": "2", "member_type": "wall", "rule_family": "rc_detail", "clause": "KDS-RC-WALL-SHEAR-001", "dcr": 0.84},
            {"member_id": "3", "member_type": "connection", "rule_family": "rc_detail", "clause": "KDS-RC-CONN-SLIP-001", "dcr": 0.66},
        ],
    }
    pbd = {"metrics": {"drift_envelope_max_pct": 1.25}}
    ndtha = {"summary": {"residual_drift_ratio_pct_max_abs": 0.42}}
    model_path = tmp_path / "model.json"
    code_path = tmp_path / "code.json"
    pbd_path = tmp_path / "pbd.json"
    ndtha_path = tmp_path / "ndtha.json"
    npz_out = tmp_path / "dataset.npz"
    report_out = tmp_path / "dataset_report.json"
    model_path.write_text(json.dumps(model), encoding="utf-8")
    code_path.write_text(json.dumps(code_check), encoding="utf-8")
    pbd_path.write_text(json.dumps(pbd), encoding="utf-8")
    ndtha_path.write_text(json.dumps(ndtha), encoding="utf-8")

    cmd = [
        sys.executable,
        "implementation/phase1/generate_design_optimization_dataset.py",
        "--midas-model",
        str(model_path),
        "--code-check",
        str(code_path),
        "--pbd-review",
        str(pbd_path),
        "--ndtha-residual",
        str(ndtha_path),
        "--dataset-npz-out",
        str(npz_out),
        "--summary-out",
        str(report_out),
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr

    report = json.loads(report_out.read_text(encoding="utf-8"))
    assert report["contract_pass"] is True
    assert int(report["summary"]["member_count"]) == 3
    assert int(report["summary"]["group_count"]) >= 2
    assert int(report["summary"]["zone_count"]) >= 1
    assert int(report["summary"]["story_band_count"]) >= 1
    data = np.load(npz_out)
    assert int(data["member_ids"].shape[0]) == 3
    assert int(data["action_mask"].shape[1]) == 2
    assert int(data["action_mask_extended"].shape[1]) == 6
    assert data["action_names"].tolist() == [
        "rebar_down",
        "rebar_up",
        "thickness_down",
        "thickness_up",
        "detailing_down",
        "detailing_up",
    ]
    assert "section_signatures" in data
    assert "exact_family_keys" in data
    assert "member_cluster_id" in data
    assert "semantic_groups" in data
    assert "member_type_per_group" in data
    assert "zone_label_per_group" in data
    assert "semantic_group_per_group" in data
    assert "story_band_index" in data
    assert "lap_splice_ratio" in data
    assert "combination_match_score" in data
    assert "combination_risk_scale" in data
    assert "detailing_active_clause_count" in data
    assert "case_state_ids" in data
    assert "case_state_index_per_member" in data
    assert "case_state_drift_envelope_max_pct" in data
    assert "case_state_residual_drift_pct_max_abs" in data
    assert "thickness_scale" in data
    assert "detailing_quality" in data
    assert "robustness_margin" in data
    assert "multi_hazard_margin" in data
    assert float(data["project_total_cost"][0]) > 0.0
    assert int(data["case_state_ids"].shape[0]) >= 1
    assert np.all(np.asarray(data["case_state_index_per_member"], dtype=np.int32) >= 0)
    assert bool(report["summary"]["global_state_split"]) is True
    assert int(report["summary"]["action_space_count"]) >= 18
    legacy_counts = report["summary"]["action_mask_legal_counts_legacy"]
    assert set(legacy_counts.keys()) == {
        "rebar_down",
        "rebar_up",
        "thickness_down",
        "thickness_up",
        "detailing_down",
        "detailing_up",
    }
    assert int(legacy_counts["rebar_up"]) >= 1
    legal_counts = report["summary"]["action_mask_legal_counts"]
    assert "beam_section_down" in legal_counts
    assert "connection_detailing_up" in legal_counts
    assert int(report["summary"]["semantic_group_mapped_count"]) >= 0
    member_types = [str(v) for v in data["member_types"].tolist()]
    assert "wall" in member_types
    dataset = {key: data[key] for key in data.files}
    overridden = dict(dataset)
    overridden["member_type_per_group"] = np.asarray(["wall"] * int(data["unique_group_ids"].shape[0]), dtype="<U32")
    state = aggregate_group_state(overridden)
    assert set(str(v) for v in state["member_type"].tolist()) == {"wall"}


def test_member_type_from_element_recognizes_pile_raft_and_caisson_as_foundation() -> None:
    sections = {
        10: {"id": 10, "name": "PILE-CAP-600"},
        11: {"id": 11, "name": "RAFT-1200"},
        12: {"id": 12, "name": "GENERIC"},
        13: {"id": 13, "name": "DBUSER", "raw_tokens": ["MAT-1500"]},
    }
    nodes = {
        1: {"id": 1, "x": 0.0, "y": 0.0, "z": 0.0},
        2: {"id": 2, "x": 1.0, "y": 0.0, "z": 0.0},
        3: {"id": 3, "x": 1.0, "y": 1.0, "z": 0.0},
        4: {"id": 4, "x": 0.0, "y": 1.0, "z": 0.0},
    }

    assert _member_type_from_element({"type": "BEAM", "section": 10, "nodes": [1, 2]}, sections, nodes) == "foundation"
    assert _member_type_from_element({"type": "PLATE", "section": 11, "nodes": [1, 2, 3, 4]}, sections, nodes) == "foundation"
    assert (
        _member_type_from_element(
            {"type": "BEAM", "section": 12, "nodes": [1, 2], "name": "C-01"},
            sections,
            nodes,
            semantic_group="caisson_support",
        )
        == "foundation"
    )
    assert _member_type_from_element({"type": "PLATE", "section": 13, "nodes": [1, 2, 3, 4]}, sections, nodes) == "foundation"


def test_generate_design_optimization_dataset_promotes_foundation_scope_from_source_tokens(tmp_path: Path) -> None:
    model = {
        "model": {
            "nodes": [
                {"id": 1, "x": 0.0, "y": 0.0, "z": 0.0},
                {"id": 2, "x": 4.0, "y": 0.0, "z": 0.0},
                {"id": 3, "x": 4.0, "y": 4.0, "z": 0.0},
                {"id": 4, "x": 0.0, "y": 4.0, "z": 0.0},
                {"id": 5, "x": 0.0, "y": 0.0, "z": -2.0},
                {"id": 6, "x": 4.0, "y": 0.0, "z": -2.0},
            ],
            "elements": [
                {"id": 101, "type": "PLATE", "section": 21, "nodes": [1, 2, 3, 4], "name": "MAT-A"},
                {"id": 102, "type": "BEAM", "section": 22, "nodes": [5, 6], "name": "PILECAP-B1"},
            ],
            "sections": [
                {"id": 21, "name": "RAFT-1200"},
                {"id": 22, "name": "PILE-CAP-700"},
            ],
            "metadata": {
                "groups": [
                    {"name": "FOUNDATION_ZONE", "element_ids": [101, 102]},
                ]
            },
        }
    }
    code_check = {
        "rows": [
            {"member_id": "101", "max_dcr": 0.74, "governing_component": "punching"},
            {"member_id": "102", "max_dcr": 0.81, "governing_component": "shear"},
        ],
        "member_check_rows": [
            {
                "member_id": "101",
                "member_type": "foundation",
                "rule_family": "strength",
                "clause": "KDS-RC-FOUND-PUNCH-001",
                "dcr": 0.74,
            },
            {
                "member_id": "102",
                "member_type": "foundation",
                "rule_family": "strength",
                "clause": "KDS-RC-FOUND-SHEAR-001",
                "dcr": 0.81,
            },
        ],
    }
    pbd = {"metrics": {"drift_envelope_max_pct": 0.92}}
    ndtha = {"summary": {"residual_drift_ratio_pct_max_abs": 0.18}}
    model_path = tmp_path / "midas_model.json"
    code_path = tmp_path / "code_check.json"
    pbd_path = tmp_path / "pbd.json"
    ndtha_path = tmp_path / "ndtha.json"
    npz_out = tmp_path / "design_optimization_dataset.npz"
    report_out = tmp_path / "design_optimization_dataset_report.json"
    _write_json(model_path, model)
    _write_json(code_path, code_check)
    _write_json(pbd_path, pbd)
    _write_json(ndtha_path, ndtha)

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_design_optimization_dataset.py",
            "--midas-model",
            str(model_path),
            "--code-check",
            str(code_path),
            "--pbd-review",
            str(pbd_path),
            "--ndtha-residual",
            str(ndtha_path),
            "--dataset-npz-out",
            str(npz_out),
            "--summary-out",
            str(report_out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    report = json.loads(report_out.read_text(encoding="utf-8"))
    assert report["contract_pass"] is True
    assert report["summary"]["member_type_counts"]["foundation"] == 2
    rows = [row for row in report["rows_head"] if str(row.get("member_type")) == "foundation"]
    assert len(rows) == 2
    assert {str(row["semantic_group"]) for row in rows} == {"FOUNDATION_ZONE"}
    assert {str(row["section_name"]) for row in rows} == {"RAFT-1200", "PILE-CAP-700"}

    data = np.load(npz_out)
    assert set(str(v) for v in data["member_types"].tolist()) == {"foundation"}
    assert set(str(v) for v in data["member_type_per_group"].tolist()) == {"foundation"}
    assert set(str(v) for v in data["semantic_groups"].tolist()) == {"FOUNDATION_ZONE"}


def test_generate_design_optimization_dataset_promotes_foundation_scope_from_generic_section_signatures(tmp_path: Path) -> None:
    model = {
        "model": {
            "nodes": [
                {"id": 1, "x": 0.0, "y": 0.0, "z": -3.0},
                {"id": 2, "x": 4.0, "y": 0.0, "z": -3.0},
                {"id": 3, "x": 4.0, "y": 4.0, "z": -3.0},
                {"id": 4, "x": 0.0, "y": 4.0, "z": -3.0},
            ],
            "elements": [
                {"id": 201, "type": "PLATE", "section": 31, "nodes": [1, 2, 3, 4], "name": "GEN-FOUND"},
            ],
            "sections": [
                {"id": 31, "name": "DBUSER", "raw_tokens": ["MAT-1500", "CC"]},
            ],
            "metadata": {"groups": [{"name": "GENERAL_ZONE", "element_ids": [201]}]},
        }
    }
    code_check = {"rows": [], "member_check_rows": []}
    pbd = {"metrics": {"drift_envelope_max_pct": 0.0}}
    ndtha = {"summary": {"residual_drift_ratio_pct_max_abs": 0.0}}
    model_path = tmp_path / "midas_model.json"
    code_path = tmp_path / "code_check.json"
    pbd_path = tmp_path / "pbd.json"
    ndtha_path = tmp_path / "ndtha.json"
    npz_out = tmp_path / "design_optimization_dataset.npz"
    report_out = tmp_path / "design_optimization_dataset_report.json"
    _write_json(model_path, model)
    _write_json(code_path, code_check)
    _write_json(pbd_path, pbd)
    _write_json(ndtha_path, ndtha)

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_design_optimization_dataset.py",
            "--midas-model",
            str(model_path),
            "--code-check",
            str(code_path),
            "--pbd-review",
            str(pbd_path),
            "--ndtha-residual",
            str(ndtha_path),
            "--dataset-npz-out",
            str(npz_out),
            "--summary-out",
            str(report_out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    report = json.loads(report_out.read_text(encoding="utf-8"))
    assert report["contract_pass"] is True
    assert report["summary"]["member_type_counts"]["foundation"] == 1
    foundation_rows = [row for row in report["rows_head"] if str(row.get("member_type")) == "foundation"]
    assert len(foundation_rows) == 1
    assert foundation_rows[0]["section_name"] == "DBUSER"
    assert foundation_rows[0]["section_signature"] == "MAT-1500"

    data = np.load(npz_out)
    assert set(str(v) for v in data["member_types"].tolist()) == {"foundation"}
    assert set(str(v) for v in data["member_type_per_group"].tolist()) == {"foundation"}


def test_generate_design_optimization_dataset_promotes_foundation_scope_from_realish_fixture(tmp_path: Path) -> None:
    model_path = _foundation_fixture_path("foundation_small_model.json")
    code_path = _foundation_fixture_path("foundation_small_code_check.json")
    pbd_path = _foundation_fixture_path("foundation_small_pbd.json")
    ndtha_path = _foundation_fixture_path("foundation_small_ndtha.json")
    npz_out = tmp_path / "design_optimization_dataset.npz"
    report_out = tmp_path / "design_optimization_dataset_report.json"

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_design_optimization_dataset.py",
            "--midas-model",
            str(model_path),
            "--code-check",
            str(code_path),
            "--pbd-review",
            str(pbd_path),
            "--ndtha-residual",
            str(ndtha_path),
            "--dataset-npz-out",
            str(npz_out),
            "--summary-out",
            str(report_out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    report = json.loads(report_out.read_text(encoding="utf-8"))
    assert report["contract_pass"] is True
    assert report["inputs"]["midas_model"].endswith("tests/fixtures/foundation_realish/foundation_small_model.json")
    assert report["summary"]["member_type_counts"]["foundation"] == 2
    assert report["summary"]["member_type_counts"]["beam"] == 1
    rows = report["rows_head"]
    foundation_rows = [row for row in rows if str(row.get("member_type")) == "foundation"]
    beam_rows = [row for row in rows if str(row.get("member_type")) == "beam"]
    assert len(foundation_rows) == 2
    assert len(beam_rows) == 1
    assert {str(row["semantic_group"]) for row in foundation_rows} == {"FOUNDATION_ZONE"}
    assert {str(row["section_name"]) for row in foundation_rows} == {"RAFT-1200", "PILE-CAP-700"}
    assert str(beam_rows[0]["semantic_group"]) == "PERIM_FRAME"

    data = np.load(npz_out)
    assert set(str(v) for v in data["member_types"].tolist()) == {"foundation", "beam"}
    assert set(str(v) for v in data["member_type_per_group"].tolist()) == {"foundation", "beam"}
    assert set(str(v) for v in data["semantic_groups"].tolist()) == {"FOUNDATION_ZONE", "PERIM_FRAME"}
