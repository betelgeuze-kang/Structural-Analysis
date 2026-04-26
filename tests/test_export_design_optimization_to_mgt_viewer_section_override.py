from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import numpy as np

from implementation.phase1.export_design_optimization_to_mgt import (
    _collect_viewer_section_override_element_retargets,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_mgt(path: Path) -> None:
    path.write_text(
        """*NODE
1, 0.0, 0.0, 0.0
2, 0.0, 0.0, 3.0
3, 3.0, 0.0, 3.0
4, 3.0, 0.0, 0.0
*ELEMENT
1, BEAM, 1, 10, 1, 2, 0, 0
2, PLATE, 2, 3, 1, 2, 3, 4, 0, 0
*MATERIAL
1, STEEL
2, CONC
*SECTION
10, B-SEC
11, B-SEC-ALT
3, WALL-THK
*THICKNESS
3, VALUE, 3, YES, 0.2, 0, NO, 0, 0.5
*DGN-SECT
10, DBUSER, SB1000X500, CC, 0, 0, 0, 0, 0, 0, YES, NO, SB, 2, 1.0, 0.5, 0, 0, 0, 0, 0, 0, 0, 0
11, DBUSER, SB1000X600, CC, 0, 0, 0, 0, 0, 0, YES, NO, SB, 2, 1.0, 0.6, 0, 0, 0, 0, 0, 0, 0, 0
*SECT-SCALE
10, 1, 1, 1, 1, 1, 1, 1, , 1
11, 1, 1, 1, 1, 1, 1, 1, , 1
""",
        encoding="utf-8",
    )


def _write_model_json(path: Path) -> None:
    payload = {
        "model": {
            "elements": [
                {
                    "id": 1,
                    "type": "BEAM",
                    "family": "beam",
                    "node_ids": [1, 2],
                    "section_id": 10,
                    "material_id": 1,
                },
                {
                    "id": 2,
                    "type": "PLATE",
                    "family": "shell",
                    "node_ids": [1, 2, 3, 4],
                    "section_id": 3,
                    "material_id": 2,
                },
            ],
            "sections": [
                {"id": 10, "name": "B-SEC"},
                {"id": 11, "name": "B-SEC-ALT"},
                {"id": 3, "name": "WALL-THK"},
            ],
            "metadata": {
                "design_sections": [
                    {
                        "section_id": 10,
                        "row_tokens": [["10", "DBUSER", "SB1000X500", "CC"]],
                        "raw_row_count": 1,
                    },
                    {
                        "section_id": 11,
                        "row_tokens": [["11", "DBUSER", "SB1000X600", "CC"]],
                        "raw_row_count": 1,
                    },
                ],
                "thickness": [
                    {
                        "thickness_id": 3,
                        "row_tokens": [["3", "VALUE", "3", "YES", "0.2", "0", "NO", "0", "0.5"]],
                        "raw_row_count": 1,
                    }
                ],
                "section_scales": [
                    {
                        "section_id": 10,
                        "area_sf": 1.0,
                        "asy_sf": 1.0,
                        "asz_sf": 1.0,
                        "ixx_sf": 1.0,
                        "iyy_sf": 1.0,
                        "izz_sf": 1.0,
                        "weight_sf": 1.0,
                        "group": "",
                        "part_id": 1,
                    },
                    {
                        "section_id": 11,
                        "area_sf": 1.0,
                        "asy_sf": 1.0,
                        "asz_sf": 1.0,
                        "ixx_sf": 1.0,
                        "iyy_sf": 1.0,
                        "izz_sf": 1.0,
                        "weight_sf": 1.0,
                        "group": "",
                        "part_id": 1,
                    },
                ],
                "load_combination_editor_seed": {
                    "contract_version": "0.1.0",
                    "combination_nodes": [
                        {
                            "name": "ULS1",
                            "combination_type": "GEN",
                            "limit_state": "STRENGTH",
                            "editor_stage": 1,
                            "entry_rows": [
                                {"reference_kind": "ST", "reference_name": "DEAD", "factor": 1.2},
                                {"reference_kind": "ST", "reference_name": "LIVE", "factor": 1.6},
                            ],
                        }
                    ],
                },
            },
            "load_combinations_raw": [
                "NAME=ULS1, GEN, STRENGTH, 0, 0, 1.2(D) + 1.6(L), 0, 0, 0",
                "ST, DEAD, 1.2, ST, LIVE, 1.6",
            ],
        }
    }
    _write_json(path, payload)


def _write_patch_json(path: Path) -> None:
    _write_json(
        path,
        {
            "patch_mode": "working_section_override_patch",
            "patch_member_count": 1,
            "patch_entries": [
                {
                    "member_id": "1",
                    "representative_element_id": "1",
                    "element_ids": ["1"],
                    "target_section": "B-SEC-ALT",
                    "draft_note": "upgrade section",
                }
            ],
        },
    )


def _write_dataset_npz(path: Path) -> None:
    np.savez_compressed(
        path,
        member_ids=np.asarray(["1", "2"], dtype="<U16"),
        group_ids=np.asarray(["viewer:beam", "viewer:shell"], dtype="<U32"),
    )


def _write_empty_changes_json(path: Path) -> None:
    _write_json(
        path,
        {
            "schema_version": "1.0",
            "changes": [],
        },
    )


def test_collect_viewer_section_override_element_retargets_uses_resolved_rows_only() -> None:
    payload = {
        "model": {
            "elements": [
                {
                    "id": 1,
                    "section_id": 11,
                    "viewer_section_override_resolution": "resolved_to_section_id",
                    "viewer_section_override_previous_section_id": 10,
                    "viewer_section_override_resolved_section_id": 11,
                    "viewer_section_override_target_section": "B-SEC-ALT",
                    "viewer_section_override_resolved_section_name": "B-SEC-ALT",
                },
                {
                    "id": 2,
                    "section_id": 3,
                    "viewer_section_override_resolution": "unresolved_target_section",
                    "viewer_section_override_previous_section_id": 3,
                },
                {
                    "id": 3,
                    "section_id": 7,
                    "viewer_section_override_resolution": "resolved_to_section_id",
                    "viewer_section_override_previous_section_id": 7,
                    "viewer_section_override_resolved_section_id": 7,
                },
            ]
        },
        "viewer_section_override_patch": {
            "rows": [{"member_id": "1", "target_section": "B-SEC-ALT"}],
        },
    }

    retarget_map, rows = _collect_viewer_section_override_element_retargets(payload)

    assert retarget_map == {1: 11}
    assert rows == [
        {
            "element_id": 1,
            "member_id": "1",
            "previous_section_id": 10,
            "resolved_section_id": 11,
            "current_section_id": 11,
            "target_section": "B-SEC-ALT",
            "resolved_section_name": "B-SEC-ALT",
            "draft_note": "",
            "applied_at": "",
            "source": "viewer_section_override_patch",
        }
    ]


def test_export_design_optimization_to_mgt_writes_viewer_section_override_retarget(tmp_path: Path) -> None:
    src = tmp_path / "source.mgt"
    parsed_model = tmp_path / "model.json"
    patch_json = tmp_path / "section_override_patch.json"
    applied_source = tmp_path / "model.section_override_applied.json"
    dataset = tmp_path / "dataset.npz"
    changes = tmp_path / "changes.json"
    out_mgt = tmp_path / "optimized.mgt"
    report = tmp_path / "export_report.json"
    manifest = tmp_path / "patch_manifest.json"
    sidecar = tmp_path / "instruction_sidecar.json"

    _write_mgt(src)
    _write_model_json(parsed_model)
    _write_patch_json(patch_json)
    _write_dataset_npz(dataset)
    _write_empty_changes_json(changes)

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/export_design_optimization_to_mgt.py",
            "--source-mgt",
            str(src),
            "--parsed-model-json",
            str(parsed_model),
            "--dataset-npz",
            str(dataset),
            "--changes-json",
            str(changes),
            "--section-override-patch-json",
            str(patch_json),
            "--section-override-applied-source-json-out",
            str(applied_source),
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

    applied_payload = json.loads(applied_source.read_text(encoding="utf-8"))
    assert applied_payload["model"]["elements"][0]["section_id"] == 11
    assert applied_payload["model"]["elements"][0]["viewer_section_override_previous_section_id"] == 10
    assert applied_payload["model"]["elements"][0]["viewer_section_override_resolved_section_id"] == 11
    assert applied_payload["viewer_section_override_patch"]["patch_mode"] == "working_section_override_patch"
    assert applied_payload["viewer_section_override_patch"]["patch_member_count"] == 1
    applied_element_at = applied_payload["model"]["elements"][0]["viewer_section_override_applied_at"]

    output_text = out_mgt.read_text(encoding="utf-8")
    assert "1, BEAM, 1, 11, 1, 2, 0, 0" in output_text
    assert "1, BEAM, 1, 10, 1, 2, 0, 0" not in output_text

    export_report = json.loads(report.read_text(encoding="utf-8"))
    assert export_report["contract_pass"] is True
    assert export_report["summary"]["patched_section_scale_row_count"] == 0
    assert export_report["summary"]["patched_thickness_row_count"] == 0
    assert export_report["summary"]["patched_material_row_count"] == 0
    assert export_report["summary"]["retargeted_element_row_count"] == 1
    assert export_report["summary"]["viewer_section_override_patch_present"] is True
    assert export_report["summary"]["viewer_section_override_patch_member_count"] == 1
    assert export_report["summary"]["viewer_section_override_patch_matched_element_count"] == 1
    assert export_report["summary"]["viewer_section_override_patch_resolved_entry_count"] == 1
    assert export_report["summary"]["viewer_section_override_patch_unresolved_entry_count"] == 0
    assert export_report["summary"]["viewer_section_override_retarget_row_count"] == 1
    assert export_report["artifacts"]["section_override_patch_json"] == str(patch_json)
    assert export_report["artifacts"]["section_override_applied_source_json"] == str(applied_source)

    patch_manifest = json.loads(manifest.read_text(encoding="utf-8"))
    assert patch_manifest["viewer_section_override_retarget_rows"] == [
        {
            "element_id": 1,
            "member_id": "1",
            "previous_section_id": 10,
            "resolved_section_id": 11,
            "current_section_id": 11,
            "target_section": "B-SEC-ALT",
            "resolved_section_name": "B-SEC-ALT",
            "draft_note": "upgrade section",
            "applied_at": applied_element_at,
            "source": "viewer_section_override_patch",
        }
    ]
    assert patch_manifest["retargeted_element_rows"] == [
        {
            "element_id": 1,
            "old_property_id": 10,
            "new_property_id": 11,
            "retarget_source": "viewer_section_override_patch",
            "member_id": "1",
            "target_section": "B-SEC-ALT",
            "previous_section_id": 10,
            "resolved_section_id": 11,
            "resolved_section_name": "B-SEC-ALT",
            "draft_note": "upgrade section",
            "viewer_patch_applied_at": applied_element_at,
        }
    ]
