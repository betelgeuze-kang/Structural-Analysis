from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import numpy as np


def _write_projection_fixture_mgt(path: Path) -> None:
    path.write_text(
        """*NODE
1, 0.0, 0.0, 0.0
2, 0.0, 0.0, 3.0
3, 3.0, 0.0, 3.0
4, 3.0, 0.0, 0.0
*ELEMENT
2, PLATE, 2, 3, 1, 2, 3, 4, 0, 0
*MATERIAL
2, CONC
*SECTION
3, WALL-THK
*DGN-MATL
2, CONC, C40, 2, 0, NO, 1, NO, 0, , , , 0, 0, 0, NO, 0, 0
""",
        encoding="utf-8",
    )


def _write_projection_fixture_model(path: Path) -> None:
    payload = {
        "model": {
            "elements": [
                {"id": 2, "type": "PLATE", "family": "shell", "node_ids": [1, 2, 3, 4], "section_id": 3, "material_id": 2}
            ],
            "materials": [
                {"id": 2, "name": "CONC", "raw_tokens": ["C40", "0", "0", "C"]},
            ],
            "metadata": {
                "rebar_material_codes": [
                    {"tokens": ["GB10(RC)", "HRB400", "GB10(RC)", "HRB400"], "raw": "GB10(RC), HRB400, GB10(RC), HRB400"}
                ],
                "design_material_rebar_payloads": [
                    {
                        "material_id": 2,
                        "material_type": "CONC",
                        "material_name": "C40",
                        "payload_basis": "concrete_r_data",
                        "payload_present": False,
                        "rbcode": "",
                        "rbmain": "",
                        "rbsub": "",
                        "fy_r": None,
                        "fys": None,
                    }
                ],
                "group_local_rebar_payloads": [],
                "design_sections": [
                    {
                        "section_id": 3,
                        "row_tokens": [["3", "DBUSER", "SB1000X500", "CC", "0", "0", "0", "0", "0", "0", "YES", "NO", "SB", "2", "1.0", "0.5", "0", "0", "0", "0", "0", "0", "0", "0"]],
                        "raw_row_count": 1,
                    }
                ],
                "thickness": [
                    {
                        "thickness_id": 3,
                        "row_tokens": [["3", "VALUE", "3", "YES", "0.2", "0", "NO", "0", "0.5"]],
                        "raw_row_count": 1,
                    }
                ],
            },
        }
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_projection_fixture_dataset(path: Path) -> None:
    np.savez_compressed(
        path,
        member_ids=np.asarray(["2"], dtype="<U16"),
        group_ids=np.asarray(["S01:core:nogroup:wall:SB1000X500"], dtype="<U64"),
    )


def _write_projection_fixture_changes(path: Path) -> None:
    payload = {
        "schema_version": "1.0",
        "changes": [
            {
                "group_id": "S01:core:nogroup:wall:SB1000X500",
                "member_type": "wall",
                "action_family": "rebar",
                "before_rebar_ratio": 0.010,
                "after_rebar_ratio": 0.004,
                "before_thickness_scale": 1.0,
                "after_thickness_scale": 1.0,
                "before_detailing_quality": 0.9,
                "after_detailing_quality": 0.9,
            }
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_generate_group_local_rebar_payloads_projects_payload_rows(tmp_path: Path) -> None:
    model = tmp_path / "model.json"
    dataset = tmp_path / "dataset.npz"
    changes = tmp_path / "changes.json"
    projection = tmp_path / "projection.json"

    _write_projection_fixture_model(model)
    _write_projection_fixture_dataset(dataset)
    _write_projection_fixture_changes(changes)

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_group_local_rebar_payloads.py",
            "--parsed-model-json",
            str(model),
            "--dataset-npz",
            str(dataset),
            "--changes-json",
            str(changes),
            "--projection-json-out",
            str(projection),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(projection.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["summary"]["design_material_rebar_payload_available_count"] == 1
    assert payload["summary"]["group_local_rebar_payload_available_count"] == 1
    row = payload["group_local_rebar_payloads"][0]
    assert row["group_id"] == "S01:core:nogroup:wall:SB1000X500"
    assert row["payload_present"] is True
    assert row["rbcode"] == "GB10(RC)"
    assert row["rbmain"] == "D16"
    assert row["rbsub"] == "D13"
    assert row["fy_r"] == 400.0
    assert row["material_types"] == ["CONC"]


def test_generate_group_local_rebar_payloads_projects_src_perimeter_frame_rows(tmp_path: Path) -> None:
    model = tmp_path / "model_src.json"
    dataset = tmp_path / "dataset_src.npz"
    changes = tmp_path / "changes_src.json"
    projection = tmp_path / "projection_src.json"

    model.write_text(
        json.dumps(
            {
                "model": {
                    "elements": [
                        {"id": 11, "type": "BEAM", "family": "beam", "node_ids": [1, 2], "section_id": 31, "material_id": 3}
                    ],
                    "materials": [
                        {"id": 3, "name": "SRC", "raw_tokens": ["C40+Q235", "0", "0", "C"]},
                    ],
                    "metadata": {
                        "rebar_material_codes": [
                            {"tokens": ["GB10(RC)", "HRB400", "GB10(RC)", "HRB400"], "raw": "GB10(RC), HRB400, GB10(RC), HRB400"}
                        ],
                        "design_material_rebar_payloads": [
                            {
                                "material_id": 3,
                                "material_type": "SRC",
                                "material_name": "C40+Q235",
                                "payload_basis": "unsupported_material_type",
                                "payload_present": False,
                                "rbcode": "",
                                "rbmain": "",
                                "rbsub": "",
                                "fy_r": None,
                                "fys": None,
                            }
                        ],
                        "group_local_rebar_payloads": [],
                        "design_sections": [
                            {
                                "section_id": 31,
                                "row_tokens": [["31", "DBUSER", "P 50x4", "CC", "0", "0", "0", "0", "0", "0", "YES", "NO", "SB", "2", "0.5", "0.5", "0", "0", "0", "0", "0", "0", "0", "0"]],
                                "raw_row_count": 1,
                            }
                        ],
                    },
                }
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    np.savez_compressed(
        dataset,
        member_ids=np.asarray(["11"], dtype="<U16"),
        group_ids=np.asarray(["S05:perimeter:2:column:P 50x4"], dtype="<U64"),
    )
    changes.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "changes": [
                    {
                        "group_id": "S05:perimeter:2:column:P 50x4",
                        "member_type": "column",
                        "action_family": "perimeter_frame",
                        "before_rebar_ratio": 0.074,
                        "after_rebar_ratio": 0.064,
                        "before_thickness_scale": 1.02,
                        "after_thickness_scale": 1.02,
                        "before_detailing_quality": 0.55,
                        "after_detailing_quality": 0.55,
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_group_local_rebar_payloads.py",
            "--parsed-model-json",
            str(model),
            "--dataset-npz",
            str(dataset),
            "--changes-json",
            str(changes),
            "--projection-json-out",
            str(projection),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(projection.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["summary"]["group_local_rebar_payload_available_count"] == 1
    assert payload["summary"]["blocked_group_local_payload_row_count"] == 0
    assert payload["blocked_group_local_payload_rows"] == []
    row = payload["group_local_rebar_payloads"][0]
    assert row["group_id"] == "S05:perimeter:2:column:P 50x4"
    assert row["action_family"] == "perimeter_frame"
    assert row["payload_present"] is True
    assert row["material_types"] == ["SRC"]
    assert row["rbmain"] == "D25"
    assert row["rbsub"] == "D22"


def test_export_design_optimization_to_mgt_consumes_projected_rebar_payloads(tmp_path: Path) -> None:
    src = tmp_path / "source.mgt"
    model = tmp_path / "model.json"
    dataset = tmp_path / "dataset.npz"
    changes = tmp_path / "changes.json"
    projection = tmp_path / "projection.json"
    out_mgt = tmp_path / "optimized.mgt"
    report = tmp_path / "export_report.json"
    manifest = tmp_path / "patch_manifest.json"
    sidecar = tmp_path / "instruction_sidecar.json"

    _write_projection_fixture_mgt(src)
    _write_projection_fixture_model(model)
    _write_projection_fixture_dataset(dataset)
    _write_projection_fixture_changes(changes)

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_group_local_rebar_payloads.py",
            "--parsed-model-json",
            str(model),
            "--dataset-npz",
            str(dataset),
            "--changes-json",
            str(changes),
            "--projection-json-out",
            str(projection),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/export_design_optimization_to_mgt.py",
            "--source-mgt",
            str(src),
            "--parsed-model-json",
            str(model),
            "--dataset-npz",
            str(dataset),
            "--changes-json",
            str(changes),
            "--rebar-payload-projection-json",
            str(projection),
            "--output-mgt",
            str(out_mgt),
            "--report-out",
            str(report),
            "--patch-manifest-out",
            str(manifest),
            "--instruction-sidecar-out",
            str(sidecar),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    export_report = json.loads(report.read_text(encoding="utf-8"))
    assert export_report["contract_pass"] is True
    assert export_report["summary"]["group_local_rebar_payload_row_count"] == 1
    assert export_report["summary"]["group_local_rebar_payload_available_count"] == 1
    assert export_report["summary"]["rebar_direct_patch_eligible_change_count"] == 1
    assert export_report["summary"]["patched_material_row_count"] == 1
    assert export_report["summary"]["cloned_material_count"] == 1
    assert export_report["summary"]["retargeted_element_row_count"] == 1
    assert export_report["summary"]["instruction_sidecar_change_count"] == 0

    exported = out_mgt.read_text(encoding="utf-8")
    assert "D16" in exported
    assert "D13" in exported
