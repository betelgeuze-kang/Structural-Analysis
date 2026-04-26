from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import numpy as np

from implementation.phase1.export_design_optimization_to_mgt import _resolve_input_path


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
3, WALL-THK
*THICKNESS
3, VALUE, 3, YES, 0.2, 0, NO, 0, 0.5
*DGN-SECT
10, DBUSER, SB1000X500, CC, 0, 0, 0, 0, 0, 0, YES, NO, SB, 2, 1.0, 0.5, 0, 0, 0, 0, 0, 0, 0, 0
*SECT-SCALE
10, 1, 1, 1, 1, 1, 1, 1, , 1
""",
        encoding="utf-8",
    )


def _write_model_json(path: Path) -> None:
    payload = {
        "model": {
            "elements": [
                {"id": 1, "type": "BEAM", "family": "beam", "node_ids": [1, 2], "section_id": 10, "material_id": 1},
                {"id": 2, "type": "PLATE", "family": "shell", "node_ids": [1, 2, 3, 4], "section_id": 3, "material_id": 2},
            ],
            "metadata": {
                "design_sections": [
                    {
                        "section_id": 10,
                        "row_tokens": [["10", "DBUSER", "SB1000X500", "CC"]],
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
                    }
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
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_dataset_npz(path: Path) -> None:
    np.savez_compressed(
        path,
        member_ids=np.asarray(["1", "2"], dtype="<U16"),
        group_ids=np.asarray(["S01:core:nogroup:beam:SB1000X500", "S01:core:nogroup:slab:default"], dtype="<U64"),
    )


def _write_changes_json(path: Path) -> None:
    payload = {
        "schema_version": "1.0",
        "changes": [
            {
                "group_id": "S01:core:nogroup:beam:SB1000X500",
                "member_type": "beam",
                "before_thickness_scale": 1.0,
                "after_thickness_scale": 0.9,
                "before_rebar_ratio": 0.02,
                "after_rebar_ratio": 0.02,
                "before_detailing_quality": 0.7,
                "after_detailing_quality": 0.7,
            },
            {
                "group_id": "S01:core:nogroup:slab:default",
                "member_type": "slab",
                "action_family": "slab_thickness",
                "before_thickness_scale": 1.0,
                "after_thickness_scale": 0.8,
                "before_rebar_ratio": 0.01,
                "after_rebar_ratio": 0.01,
                "before_detailing_quality": 1.0,
                "after_detailing_quality": 1.0,
            },
            {
                "group_id": "S01:core:nogroup:beam:SB1000X500",
                "member_type": "beam",
                "action_family": "connection_detailing",
                "before_rebar_ratio": 0.02,
                "after_rebar_ratio": 0.02,
                "before_thickness_scale": 1.0,
                "after_thickness_scale": 1.0,
                "before_detailing_quality": 0.7,
                "after_detailing_quality": 0.62,
            },
            {
                "group_id": "S01:core:nogroup:beam:SB1000X500",
                "member_type": "beam",
                "before_rebar_ratio": 0.02,
                "after_rebar_ratio": 0.018,
                "before_thickness_scale": 1.0,
                "after_thickness_scale": 1.0,
                "before_detailing_quality": 0.7,
                "after_detailing_quality": 0.7,
            },
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_export_design_optimization_to_mgt_patches_supported_rows_and_roundtrips(tmp_path: Path) -> None:
    src = tmp_path / "source.mgt"
    parsed_model = tmp_path / "model.json"
    dataset = tmp_path / "dataset.npz"
    changes = tmp_path / "changes.json"
    out_mgt = tmp_path / "optimized.mgt"
    report = tmp_path / "export_report.json"
    manifest = tmp_path / "patch_manifest.json"
    sidecar = tmp_path / "instruction_sidecar.json"
    roundtrip_json = tmp_path / "roundtrip.json"
    roundtrip_npz = tmp_path / "roundtrip.npz"
    roundtrip_edges = tmp_path / "roundtrip_edges.json"
    roundtrip_report = tmp_path / "roundtrip_report.json"

    _write_mgt(src)
    _write_model_json(parsed_model)
    _write_dataset_npz(dataset)
    _write_changes_json(changes)

    export_cmd = [
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
        "--output-mgt",
        str(out_mgt),
        "--report-out",
        str(report),
        "--patch-manifest-out",
        str(manifest),
        "--instruction-sidecar-out",
        str(sidecar),
    ]
    proc = subprocess.run(export_cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr

    export_report = json.loads(report.read_text(encoding="utf-8"))
    assert export_report["contract_pass"] is True
    assert export_report["summary"]["support_mode"] == "bounded_patch_subset"
    assert export_report["summary"]["loadcomb_preview_exists"] is True
    assert export_report["summary"]["loadcomb_roundtrip_report_exists"] is True
    assert export_report["summary"]["loadcomb_roundtrip_pass"] is True
    assert export_report["summary"]["loadcomb_roundtrip_summary_line"].startswith("MGT export LOADCOMB roundtrip: ok")
    assert export_report["summary"]["loadcomb_combo_count"] == 1
    assert export_report["summary"]["supported_change_count"] == 4
    assert export_report["summary"]["patched_supported_change_count"] == 2
    assert export_report["summary"]["direct_patch_change_count"] == 2
    assert export_report["summary"]["instruction_sidecar_change_count"] == 2
    assert export_report["summary"]["supported_change_ratio"] == 1.0
    assert export_report["summary"]["direct_patch_change_ratio"] == 0.5
    assert export_report["summary"]["instruction_sidecar_change_ratio"] == 0.5
    assert export_report["summary"]["instruction_sidecar_zero_touch_verified_change_ratio"] == 0.0
    assert export_report["summary"]["unsupported_change_ratio"] == 0.0
    assert (
        export_report["summary"]["native_authoring_summary_line"]
        == "supported=4/4 | direct_patch=2 | zero_touch_verified=0 | manual_sidecar=2 | unsupported=0"
    )
    assert (
        export_report["summary"]["native_export_verification_line"]
        == "contract=PASS | support_mode=bounded_patch_subset | output_mgt=yes | loadcomb_roundtrip=yes | direct_patch=2 | audit_pending=0 | unsupported=0"
    )
    assert (
        export_report["summary"]["mgt_output_status_line"]
        == "output_mgt=yes | loadcomb_preview=yes | loadcomb_roundtrip_report=yes | combos=1 | viewer_section_override=0"
    )
    assert export_report["summary"]["source_output_mgt_diff_available"] is True
    assert (
        export_report["summary"]["source_output_mgt_summary_line"]
        == "source_vs_output_mgt: changed=2 | added=0 | removed=0 | source_lines=20 | output_lines=20"
    )
    assert export_report["summary"]["source_output_mgt_source_meaningful_line_count"] == 20
    assert export_report["summary"]["source_output_mgt_output_meaningful_line_count"] == 20
    assert export_report["summary"]["source_output_mgt_changed_line_count"] == 2
    assert export_report["summary"]["source_output_mgt_added_line_count"] == 0
    assert export_report["summary"]["source_output_mgt_removed_line_count"] == 0
    assert export_report["summary"]["source_output_mgt_total_delta_count"] == 2
    assert export_report["summary"]["source_output_mgt_diff_sample_lines"] == [
        "~ 3, VALUE, 3, YES, 0.2, 0, NO, 0, 0.5 -> 3, VALUE, 3, YES, 0.16, 0, NO, 0, 0.5",
        "~ 10, 1, 1, 1, 1, 1, 1, 1, , 1 -> 10, 0.9, 0.9, 0.9, 0.9, 0.9, 0.9, 0.9, , 1",
    ]
    assert "value" in export_report["summary"]["source_output_mgt_diff_search_tokens"]
    assert "0.16" in export_report["summary"]["source_output_mgt_diff_search_tokens"]
    assert set(export_report["summary"]["source_output_mgt_diff_section_ids"]) == {"3", "10"}
    assert set(export_report["summary"]["source_output_mgt_diff_member_ids"]) == {"1", "2"}
    assert export_report["summary"]["source_output_mgt_diff_member_row_indices"] == {"1": [1], "2": [0]}
    assert export_report["summary"]["source_output_mgt_diff_row_ids"] == [
        "mgt-diff-row-0000",
        "mgt-diff-row-0001",
    ]
    assert export_report["summary"]["source_output_mgt_diff_json_exists"] is True
    assert export_report["summary"]["source_output_mgt_diff_preview_exists"] is True
    assert export_report["summary"]["source_output_mgt_diff_window_json_exists"] is True
    assert export_report["summary"]["source_output_mgt_diff_window_preview_exists"] is True
    assert (
        export_report["summary"]["source_output_mgt_verification_receipt_line"]
        == "source_output_mgt=yes | diff_json=yes | diff_preview=yes | window_json=yes | window_preview=yes | delta_total=2"
    )
    assert (
        export_report["summary"]["source_vs_output_diff_summary_line"]
        == "source_vs_output_mgt: changed=2 | added=0 | removed=0 | source_lines=20 | output_lines=20"
    )
    assert export_report["summary"]["source_vs_output_diff_changed_line_count"] == 2
    assert export_report["summary"]["source_vs_output_diff_added_line_count"] == 0
    assert export_report["summary"]["source_vs_output_diff_removed_line_count"] == 0
    assert export_report["summary"]["source_vs_output_diff_sample_count"] == 2
    assert isinstance(export_report["summary"]["source_vs_output_diff_sample_rows"], list)
    assert export_report["summary"]["source_vs_output_diff_sample_rows"][0]["candidate_section_ids"] == ["3"]
    assert export_report["summary"]["source_vs_output_diff_sample_rows"][0]["candidate_member_ids"] == ["2"]
    assert export_report["summary"]["source_vs_output_diff_sample_rows"][0]["geometry_bridge_member_ids"] == ["2"]
    assert export_report["summary"]["source_vs_output_diff_sample_rows"][0]["exact_member_id_match"] is True
    assert export_report["summary"]["source_vs_output_diff_sample_rows"][0]["row_index"] == 0
    assert export_report["summary"]["source_vs_output_diff_sample_rows"][0]["row_id"] == "mgt-diff-row-0000"
    assert "0.16" in export_report["summary"]["source_vs_output_diff_sample_rows"][0]["search_tokens"]
    assert export_report["summary"]["source_vs_output_diff_sample_rows"][1]["candidate_card_ids"] == ["10"]
    assert export_report["summary"]["source_vs_output_diff_sample_rows"][1]["candidate_member_ids"] == ["1"]
    assert export_report["summary"]["source_vs_output_diff_window_count"] == 2
    assert len(export_report["summary"]["source_vs_output_diff_window_rows"]) == 2
    assert export_report["summary"]["source_output_mgt_diff_window_member_row_indices"] == {"1": [1], "2": [0]}
    assert export_report["summary"]["source_output_mgt_diff_window_row_ids"] == [
        "mgt-diff-row-0000",
        "mgt-diff-row-0001",
    ]
    assert export_report["summary"]["source_vs_output_source_line_count"] == 20
    assert export_report["summary"]["source_vs_output_output_line_count"] == 20
    assert "2" in export_report["summary"]["source_output_mgt_diff_window_member_ids"]
    assert "value" in export_report["summary"]["source_output_mgt_diff_window_search_tokens"]
    assert (
        export_report["summary"]["audit_review_queue_status_line"]
        == "queue_items=0 | pending_review=0 | acknowledged=0"
    )
    assert export_report["summary"]["unsupported_change_count"] == 0
    assert export_report["summary"]["material_level_rebar_payload_row_count"] == 0
    assert export_report["summary"]["material_level_rebar_payload_available_count"] == 0
    assert export_report["summary"]["group_local_rebar_payload_row_count"] == 0
    assert export_report["summary"]["group_local_connection_detailing_payload_row_count"] == 0
    assert export_report["summary"]["group_local_detailing_payload_row_count"] == 0
    assert export_report["summary"]["connection_detailing_direct_patch_eligible_change_count"] == 0
    assert export_report["summary"]["detailing_direct_patch_eligible_change_count"] == 0
    assert export_report["summary"]["instruction_sidecar_audit_only_change_count"] == 0
    assert export_report["summary"]["instruction_sidecar_manual_input_change_count"] == 2
    assert export_report["summary"]["audit_review_manifest_change_count"] == 0
    assert (
        export_report["summary"]["mgt_export_delivery_boundary"]
        == "direct_patch=beam_section=1, slab_thickness=1 | sidecar=connection_detailing=1, rebar=1 | "
        "connection_payload=manual_sidecar_only | detailing_payload=manual_sidecar_only"
    )
    assert export_report["summary"]["rebar_payload_namespace_mode"] == "none"
    assert export_report["summary"]["rebar_payload_material_level_namespace_present"] is False
    assert export_report["summary"]["rebar_payload_group_local_namespace_present"] is False
    assert export_report["summary"]["derived_group_local_rebar_bridge_row_count"] == 1
    assert export_report["summary"]["derived_group_local_rebar_mapped_change_count"] == 1
    assert export_report["summary"]["derived_group_local_rebar_payload_available_group_count"] == 0
    assert export_report["summary"]["rebar_direct_patch_eligible_change_count"] == 0
    assert export_report["summary"]["rebar_direct_patch_ineligible_reason_counts"] == {"material_payload_missing": 1}
    assert export_report["summary"]["rebar_direct_patch_mapping_source_counts"] == {"direct_group_id": 1}
    assert export_report["summary"]["patched_section_scale_row_count"] == 1
    assert export_report["summary"]["patched_thickness_row_count"] == 1
    assert export_report["summary"]["direct_patch_action_family_counts"] == {"beam_section": 1, "slab_thickness": 1}
    assert export_report["summary"]["special_member_direct_patch_action_family_counts"] == {
        "core_beam_section": 1,
        "core_slab_thickness": 1,
    }
    assert export_report["summary"]["special_member_supported_action_family_counts"] == {
        "core_beam_connection_detailing": 1,
        "core_beam_rebar": 1,
        "core_beam_section": 1,
        "core_slab_thickness": 1,
    }
    assert export_report["summary"]["instruction_sidecar_action_family_counts"] == {"connection_detailing": 1, "rebar": 1}
    assert export_report["summary"]["special_member_instruction_sidecar_action_family_counts"] == {
        "core_beam_connection_detailing": 1,
        "core_beam_rebar": 1,
    }
    sidecar_payload = json.loads(sidecar.read_text(encoding="utf-8"))
    loadcomb_preview = Path(export_report["artifacts"]["loadcomb_preview_mgt"])
    loadcomb_roundtrip = Path(export_report["artifacts"]["loadcomb_roundtrip_report_json"])
    source_output_diff_json = Path(export_report["artifacts"]["source_output_mgt_diff_json"])
    source_output_diff_preview = Path(export_report["artifacts"]["source_output_mgt_diff_preview_txt"])
    source_output_diff_window_json = Path(export_report["artifacts"]["source_output_mgt_diff_window_json"])
    source_output_diff_window_preview = Path(export_report["artifacts"]["source_output_mgt_diff_window_preview_txt"])
    assert loadcomb_preview.exists()
    assert loadcomb_roundtrip.exists()
    assert source_output_diff_json.exists()
    assert source_output_diff_preview.exists()
    assert source_output_diff_window_json.exists()
    assert source_output_diff_window_preview.exists()
    assert "*LOADCOMB" in loadcomb_preview.read_text(encoding="utf-8")
    assert json.loads(loadcomb_roundtrip.read_text(encoding="utf-8"))["pass"] is True
    diff_json_payload = json.loads(source_output_diff_json.read_text(encoding="utf-8"))
    assert diff_json_payload["delta_counts"] == {"changed": 2, "added": 0, "removed": 0, "total": 2}
    assert "0.16" in diff_json_payload["search_tokens"]
    assert set(diff_json_payload["candidate_member_ids"]) == {"1", "2"}
    assert set(diff_json_payload["candidate_section_ids"]) == {"3", "10"}
    assert diff_json_payload["sample_lines"] == export_report["summary"]["source_output_mgt_diff_sample_lines"]
    assert diff_json_payload["member_row_indices"] == {"1": [1], "2": [0]}
    assert diff_json_payload["row_ids"] == ["mgt-diff-row-0000", "mgt-diff-row-0001"]
    assert diff_json_payload["sample_rows"][0]["candidate_section_ids"] == ["3"]
    assert diff_json_payload["sample_rows"][0]["candidate_member_ids"] == ["2"]
    diff_window_payload = json.loads(source_output_diff_window_json.read_text(encoding="utf-8"))
    assert diff_window_payload["window_count"] == 2
    assert set(diff_window_payload["candidate_member_ids"]) == {"1", "2"}
    assert diff_window_payload["member_row_indices"] == {"1": [1], "2": [0]}
    assert diff_window_payload["row_ids"] == ["mgt-diff-row-0000", "mgt-diff-row-0001"]
    assert diff_window_payload["window_rows"][1]["candidate_member_ids"] == ["1"]
    assert "MIDAS source vs output diff preview" in source_output_diff_preview.read_text(encoding="utf-8")
    assert "MIDAS source vs output diff compare window" in source_output_diff_window_preview.read_text(encoding="utf-8")
    assert sidecar_payload["summary"]["instruction_sidecar_change_count"] == 2
    assert sidecar_payload["summary"]["instruction_sidecar_audit_only_change_count"] == 0
    assert sidecar_payload["summary"]["instruction_sidecar_manual_input_change_count"] == 2
    audit_manifest = Path(export_report["artifacts"]["audit_review_manifest_json"])
    audit_payload = json.loads(audit_manifest.read_text(encoding="utf-8"))
    assert audit_payload["summary"]["audit_review_manifest_change_count"] == 0
    assert audit_payload["summary"]["instruction_sidecar_manual_input_change_count"] == 2
    packet_manifest = Path(export_report["artifacts"]["audit_review_packet_manifest_json"])
    packet_payload = json.loads(packet_manifest.read_text(encoding="utf-8"))
    assert packet_payload["summary"]["audit_review_packet_count"] == 0
    assert packet_payload["summary"]["audit_review_packet_file_count"] == 0
    queue_manifest = Path(export_report["artifacts"]["audit_review_queue_manifest_json"])
    queue_payload = json.loads(queue_manifest.read_text(encoding="utf-8"))
    assert queue_payload["summary"]["audit_review_queue_item_count"] == 0
    assert queue_payload["summary"]["audit_review_queue_pending_count"] == 0
    assert sidecar_payload["summary"]["derived_group_local_rebar_bridge_row_count"] == 1
    assert sidecar_payload["instruction_sidecar_rows"][0]["instruction_kind"] == "connection_detailing_followup"
    assert sidecar_payload["instruction_sidecar_rows"][0]["structured_payload_present"] is False
    assert sidecar_payload["instruction_sidecar_rows"][1]["instruction_kind"] == "rebar_followup"
    assert sidecar_payload["derived_group_local_rebar_bridge_rows"][0]["mapping_source"] == "direct_group_id"
    assert sidecar_payload["derived_group_local_rebar_bridge_rows"][0]["ineligibility_reason"] == "material_payload_missing"

    exported = out_mgt.read_text(encoding="utf-8")
    assert "10, 0.9, 0.9, 0.9, 0.9, 0.9, 0.9, 0.9" in exported
    assert "3, VALUE, 3, YES, 0.16, 0, NO, 0, 0.5" in exported

    roundtrip_cmd = [
        sys.executable,
        "implementation/phase1/parse_midas_mgt_to_json_npz.py",
        "--mgt",
        str(out_mgt),
        "--json-out",
        str(roundtrip_json),
        "--npz-out",
        str(roundtrip_npz),
        "--edge-list-out",
        str(roundtrip_edges),
        "--report-out",
        str(roundtrip_report),
        "--min-nodes",
        "4",
        "--min-elements",
        "2",
    ]
    proc = subprocess.run(roundtrip_cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    parsed = json.loads(roundtrip_json.read_text(encoding="utf-8"))
    section_scales = parsed["model"]["metadata"]["section_scales"]
    thickness_rows = parsed["model"]["metadata"]["thickness"]
    assert section_scales[0]["section_id"] == 10
    assert section_scales[0]["area_sf"] == 0.9
    assert thickness_rows[0]["thickness_id"] == 3
    assert thickness_rows[0]["row_tokens"][0][4] == "0.16"


def test_export_design_optimization_to_mgt_carries_connection_detailing_structured_payloads(tmp_path: Path) -> None:
    src = tmp_path / "source.mgt"
    parsed_model = tmp_path / "model.json"
    dataset = tmp_path / "dataset.npz"
    changes = tmp_path / "changes.json"
    connection_projection = tmp_path / "connection_projection.json"
    out_mgt = tmp_path / "optimized.mgt"
    report = tmp_path / "export_report.json"
    manifest = tmp_path / "patch_manifest.json"
    sidecar = tmp_path / "instruction_sidecar.json"

    _write_mgt(src)
    _write_model_json(parsed_model)
    _write_dataset_npz(dataset)
    _write_changes_json(changes)
    connection_projection.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "contract_pass": True,
                "group_local_connection_detailing_payloads": [
                    {
                        "group_id": "S01:core:nogroup:beam:SB1000X500",
                        "action_family": "connection_detailing",
                        "payload_present": True,
                        "payload_source_class": "internal_group_local_connection_detailing_projection",
                        "mapping_source": "direct_group_id",
                        "baseline_detailing_quality": 0.7,
                        "target_detailing_quality": 0.62,
                    }
                ],
                "summary": {
                    "group_local_connection_detailing_payload_row_count": 1,
                    "group_local_connection_detailing_payload_available_count": 1,
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
            "implementation/phase1/export_design_optimization_to_mgt.py",
            "--source-mgt",
            str(src),
            "--parsed-model-json",
            str(parsed_model),
            "--dataset-npz",
            str(dataset),
            "--changes-json",
            str(changes),
            "--connection-detailing-payload-projection-json",
            str(connection_projection),
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
    assert export_report["summary"]["group_local_connection_detailing_payload_row_count"] == 1
    assert export_report["summary"]["group_local_connection_detailing_payload_available_count"] == 1
    assert export_report["summary"]["connection_detailing_payload_namespace_mode"] == "group_local"
    assert export_report["summary"]["connection_detailing_payload_group_local_namespace_present"] is True
    assert export_report["summary"]["connection_detailing_structured_payload_mapped_change_count"] == 1
    assert export_report["summary"]["connection_detailing_direct_patch_eligible_change_count"] == 0
    assert export_report["summary"]["connection_detailing_delivery_mode"] == "structured_group_local_payload_plus_sidecar"
    assert (
        export_report["summary"]["mgt_export_delivery_boundary"]
        == "direct_patch=beam_section=1, slab_thickness=1 | sidecar=connection_detailing=1, rebar=1 | "
        "connection_payload=structured_group_local_payload_plus_sidecar | detailing_payload=manual_sidecar_only"
    )
    assert export_report["artifacts"]["connection_detailing_payload_projection_json"] == str(connection_projection)

    sidecar_payload = json.loads(sidecar.read_text(encoding="utf-8"))
    connection_row = next(
        row for row in sidecar_payload["instruction_sidecar_rows"] if row["action_family"] == "connection_detailing"
    )
    assert connection_row["structured_payload_present"] is True
    assert connection_row["structured_payload_mapping_source"] == "direct_group_id"
    assert connection_row["structured_payload_source_class"] == "internal_group_local_connection_detailing_projection"


def test_export_design_optimization_to_mgt_consumes_viewer_section_override_patch(tmp_path: Path) -> None:
    src = tmp_path / "source.mgt"
    parsed_model = tmp_path / "model.json"
    dataset = tmp_path / "dataset.npz"
    changes = tmp_path / "changes.json"
    section_patch = tmp_path / "section_override_patch.json"
    patched_source_json = tmp_path / "viewer_section_override_source.json"
    out_mgt = tmp_path / "optimized.mgt"
    report = tmp_path / "export_report.json"
    manifest = tmp_path / "patch_manifest.json"
    sidecar = tmp_path / "instruction_sidecar.json"

    src.write_text(
        """*NODE
1, 0.0, 0.0, 0.0
2, 0.0, 0.0, 3.0
*ELEMENT
1, BEAM, 1, 10, 1, 2, 0, 0
*MATERIAL
1, STEEL
*SECTION
10, B-SEC
11, B-ALT
*SECT-SCALE
10, 1, 1, 1, 1, 1, 1, 1, , 1
11, 1, 1, 1, 1, 1, 1, 1, , 1
""",
        encoding="utf-8",
    )
    _write_json(
        parsed_model,
        {
            "model": {
                "elements": [
                    {"id": 1, "member_id": "1", "type": "BEAM", "family": "beam", "node_ids": [1, 2], "section_id": 10, "material_id": 1},
                ],
                "sections": [
                    {"id": 10, "name": "B-SEC"},
                    {"id": 11, "name": "B-ALT"},
                ],
                "metadata": {
                    "design_sections": [
                        {"section_id": 10, "row_tokens": [["10", "DBUSER", "B-SEC"]], "raw_row_count": 1},
                        {"section_id": 11, "row_tokens": [["11", "DBUSER", "B-ALT"]], "raw_row_count": 1},
                    ]
                },
            }
        },
    )
    _write_dataset_npz(dataset)
    changes.write_text(json.dumps({"schema_version": "1.0", "changes": []}, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_json(
        section_patch,
        {
            "patch_mode": "working_section_override_patch",
            "patch_member_count": 1,
            "patch_entries": [
                {
                    "member_id": "1",
                    "representative_element_id": "1",
                    "element_ids": ["1"],
                    "target_section": "B-ALT",
                    "target_section_id": 11,
                    "target_section_resolution_mode": "resolved_to_section_id",
                }
            ],
        },
    )

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
            str(section_patch),
            "--section-override-applied-source-json-out",
            str(patched_source_json),
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
    assert export_report["summary"]["viewer_section_override_patch_present"] is True
    assert export_report["summary"]["viewer_section_override_patch_member_count"] == 1
    assert export_report["summary"]["viewer_section_override_patch_resolved_entry_count"] == 1
    assert export_report["summary"]["viewer_section_override_retarget_row_count"] == 1
    assert export_report["summary"]["viewer_section_override_applied_source_json_exists"] is True
    assert export_report["artifacts"]["section_override_patch_json"] == str(section_patch)
    assert export_report["artifacts"]["section_override_applied_source_json"] == str(patched_source_json)

    assert "1, BEAM, 1, 11, 1, 2, 0, 0" in out_mgt.read_text(encoding="utf-8")
    patched_source_payload = json.loads(patched_source_json.read_text(encoding="utf-8"))
    assert patched_source_payload["model"]["elements"][0]["section_id"] == 11
    assert patched_source_payload["viewer_section_override_patch"]["resolved_entry_count"] == 1


def test_export_design_optimization_to_mgt_consumes_viewer_loadcomb_override_patch(tmp_path: Path) -> None:
    src = tmp_path / "source.mgt"
    parsed_model = tmp_path / "model.json"
    dataset = tmp_path / "dataset.npz"
    changes = tmp_path / "changes.json"
    loadcomb_patch = tmp_path / "loadcomb_override_patch.json"
    patched_source_json = tmp_path / "viewer_loadcomb_override_source.json"
    out_mgt = tmp_path / "optimized.mgt"
    report = tmp_path / "export_report.json"
    manifest = tmp_path / "patch_manifest.json"
    sidecar = tmp_path / "instruction_sidecar.json"

    src.write_text(
        """*NODE
1, 0.0, 0.0, 0.0
2, 0.0, 0.0, 3.0
*ELEMENT
1, BEAM, 1, 10, 1, 2, 0, 0
*MATERIAL
1, STEEL
*SECTION
10, B-SEC
*SECT-SCALE
10, 1, 1, 1, 1, 1, 1, 1, , 1
""",
        encoding="utf-8",
    )
    _write_json(
        parsed_model,
        {
            "model": {
                "elements": [
                    {"id": 1, "member_id": "1", "type": "BEAM", "family": "beam", "node_ids": [1, 2], "section_id": 10, "material_id": 1},
                ],
                "sections": [
                    {"id": 10, "name": "B-SEC"},
                ],
                "loads": {
                    "load_combinations": [
                        {
                            "name": "gLCB1",
                            "combination_type": "GEN",
                            "limit_state": "ACTIVE",
                            "expression": "1.3(DEAD) + 1.5(LIVE)",
                            "entry_rows": [
                                {"reference_kind": "ST", "reference_name": "DEAD", "factor": 1.3},
                                {"reference_kind": "ST", "reference_name": "LIVE", "factor": 1.5},
                            ],
                            "entries": [
                                {"reference_kind": "ST", "reference_name": "DEAD", "factor": 1.3},
                                {"reference_kind": "ST", "reference_name": "LIVE", "factor": 1.5},
                            ],
                            "factor_map": {"DEAD": 1.3, "LIVE": 1.5},
                            "expanded_factor_map": {"DEAD": 1.3, "LIVE": 1.5},
                            "referenced_cases": ["DEAD", "LIVE"],
                            "referenced_combinations": [],
                            "referenced_leaf_cases": ["DEAD", "LIVE"],
                            "entry_count": 2,
                            "expansion_mode": "linear_combination",
                            "expansion_depth": 1,
                        }
                    ]
                },
                "metadata": {
                    "load_combination_editor_seed": {
                        "contract_version": "0.1.0",
                        "provenance": "test-fixture",
                        "seed_kind": "midas_load_combination_editor_seed",
                        "summary": {"combination_count": 1, "case_count": 2},
                        "case_nodes": [
                            {"id": "CASE:DEAD", "name": "DEAD", "kind": "case"},
                            {"id": "CASE:LIVE", "name": "LIVE", "kind": "case"},
                        ],
                        "combination_nodes": [
                            {
                                "id": "COMBO:gLCB1",
                                "name": "gLCB1",
                                "kind": "combo",
                                "editor_stage": 1,
                                "limit_state": "ACTIVE",
                                "combination_type": "GEN",
                                "expression": "1.3(DEAD) + 1.5(LIVE)",
                                "entry_count": 2,
                                "expansion_mode": "linear_combination",
                                "expansion_depth": 1,
                                "referenced_combinations": [],
                                "referenced_leaf_cases": ["DEAD", "LIVE"],
                                "factor_map": {"DEAD": 1.3, "LIVE": 1.5},
                                "entry_rows": [
                                    {"reference_kind": "ST", "reference_name": "DEAD", "factor": 1.3},
                                    {"reference_kind": "ST", "reference_name": "LIVE", "factor": 1.5},
                                ],
                                "node_role": "combo",
                            }
                        ],
                        "graph_edges": [],
                    }
                },
            }
        },
    )
    _write_dataset_npz(dataset)
    changes.write_text(json.dumps({"schema_version": "1.0", "changes": []}, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_json(
        loadcomb_patch,
        {
            "patch_mode": "working_loadcomb_override_patch",
            "patch_entries": [
                {
                    "base_combination_name": "gLCB1",
                    "target_combination_name": "gLCB1_SERVICE_085",
                    "scale_factor": 0.85,
                    "draft_note": "serviceability what-if",
                }
            ],
        },
    )

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
            "--loadcomb-override-patch-json",
            str(loadcomb_patch),
            "--loadcomb-override-applied-source-json-out",
            str(patched_source_json),
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
    assert export_report["summary"]["viewer_loadcomb_override_patch_present"] is True
    assert export_report["summary"]["viewer_loadcomb_override_patch_entry_count"] == 1
    assert export_report["summary"]["viewer_loadcomb_override_patch_resolved_entry_count"] == 1
    assert export_report["summary"]["viewer_loadcomb_override_patch_appended_combo_count"] == 1
    assert export_report["summary"]["viewer_loadcomb_override_applied_source_json_exists"] is True
    assert export_report["summary"]["loadcomb_preview_exists"] is True
    assert export_report["summary"]["loadcomb_roundtrip_pass"] is True
    assert export_report["summary"]["loadcomb_combo_count"] == 2
    assert export_report["artifacts"]["loadcomb_override_patch_json"] == str(loadcomb_patch)
    assert export_report["artifacts"]["loadcomb_override_applied_source_json"] == str(patched_source_json)

    preview_path = Path(export_report["artifacts"]["loadcomb_preview_mgt"])
    assert preview_path.exists()
    preview_text = preview_path.read_text(encoding="utf-8")
    assert "NAME=gLCB1_SERVICE_085" in preview_text
    assert "DEAD" in preview_text and "LIVE" in preview_text

    patched_source_payload = json.loads(patched_source_json.read_text(encoding="utf-8"))
    assert patched_source_payload["viewer_loadcomb_override_patch"]["resolved_entry_count"] == 1
    combo_names = [row["name"] for row in patched_source_payload["model"]["loads"]["load_combinations"]]
    assert "gLCB1_SERVICE_085" in combo_names
    seed_combo_names = [
        row["name"]
        for row in patched_source_payload["model"]["metadata"]["load_combination_editor_seed"]["combination_nodes"]
    ]
    assert "gLCB1_SERVICE_085" in seed_combo_names


def test_export_design_optimization_to_mgt_carries_detailing_structured_payloads(tmp_path: Path) -> None:
    src = tmp_path / "source.mgt"
    parsed_model = tmp_path / "model.json"
    dataset = tmp_path / "dataset.npz"
    changes = tmp_path / "changes.json"
    detailing_projection = tmp_path / "detailing_projection.json"
    out_mgt = tmp_path / "optimized.mgt"
    report = tmp_path / "export_report.json"
    manifest = tmp_path / "patch_manifest.json"
    sidecar = tmp_path / "instruction_sidecar.json"

    _write_mgt(src)
    _write_model_json(parsed_model)
    _write_dataset_npz(dataset)
    changes.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "changes": [
                    {
                        "group_id": "S01:core:nogroup:beam:SB1000X500",
                        "member_type": "beam",
                        "action_family": "detailing",
                        "action_name": "detailing_down",
                        "before_rebar_ratio": 0.02,
                        "after_rebar_ratio": 0.02,
                        "before_thickness_scale": 1.0,
                        "after_thickness_scale": 1.0,
                        "before_detailing_quality": 0.70,
                        "after_detailing_quality": 0.62,
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    detailing_projection.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "contract_pass": True,
                "group_local_detailing_payloads": [
                    {
                        "group_id": "S01:core:nogroup:beam:SB1000X500",
                        "action_family": "detailing",
                        "payload_present": True,
                        "payload_source_class": "internal_group_local_detailing_projection",
                        "mapping_source": "direct_group_id",
                        "baseline_detailing_quality": 0.7,
                        "target_detailing_quality": 0.62,
                    }
                ],
                "summary": {
                    "group_local_detailing_payload_row_count": 1,
                    "group_local_detailing_payload_available_count": 1,
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
            "implementation/phase1/export_design_optimization_to_mgt.py",
            "--source-mgt",
            str(src),
            "--parsed-model-json",
            str(parsed_model),
            "--dataset-npz",
            str(dataset),
            "--changes-json",
            str(changes),
            "--detailing-payload-projection-json",
            str(detailing_projection),
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
    assert export_report["summary"]["group_local_detailing_payload_row_count"] == 1
    assert export_report["summary"]["group_local_detailing_payload_available_count"] == 1
    assert export_report["summary"]["detailing_payload_namespace_mode"] == "group_local"
    assert export_report["summary"]["detailing_payload_group_local_namespace_present"] is True
    assert export_report["summary"]["detailing_structured_payload_mapped_change_count"] == 1
    assert export_report["summary"]["detailing_direct_patch_eligible_change_count"] == 0
    assert export_report["summary"]["detailing_delivery_mode"] == "structured_group_local_payload_plus_sidecar"
    assert (
        export_report["summary"]["mgt_export_delivery_boundary"]
        == "direct_patch=none | sidecar=detailing=1 | "
        "connection_payload=manual_sidecar_only | detailing_payload=structured_group_local_payload_plus_sidecar"
    )
    assert export_report["artifacts"]["detailing_payload_projection_json"] == str(detailing_projection)

    sidecar_payload = json.loads(sidecar.read_text(encoding="utf-8"))
    detailing_row = next(row for row in sidecar_payload["instruction_sidecar_rows"] if row["action_family"] == "detailing")
    assert detailing_row["structured_payload_present"] is True
    assert detailing_row["structured_payload_mapping_source"] == "direct_group_id"
    assert detailing_row["structured_payload_source_class"] == "internal_group_local_detailing_projection"
    assert detailing_row["structured_payload_section_ids"] == []
    assert detailing_row["structured_payload_material_ids"] == []


def test_export_design_optimization_to_mgt_direct_patches_connection_detailing_material_metadata(tmp_path: Path) -> None:
    src = tmp_path / "source_connection_detailing.mgt"
    parsed_model = tmp_path / "model_connection_detailing.json"
    dataset = tmp_path / "dataset_connection_detailing.npz"
    changes = tmp_path / "changes_connection_detailing.json"
    connection_projection = tmp_path / "connection_projection.json"
    out_mgt = tmp_path / "optimized_connection_detailing.mgt"
    report = tmp_path / "export_report_connection_detailing.json"
    manifest = tmp_path / "patch_manifest_connection_detailing.json"
    sidecar = tmp_path / "instruction_sidecar_connection_detailing.json"

    src.write_text(
        """*NODE
1, 0.0, 0.0, 0.0
2, 0.0, 0.0, 3.0
*ELEMENT
1, BEAM, 1, 10, 1, 2, 0, 0
*MATERIAL
1, CONC
*SECTION
10, B-SEC
*DGN-SECT
10, DBUSER, SB1000X500, CC, 0, 0, 0, 0, 0, 0, YES, NO, SB, 2, 1.0, 0.5, 0, 0, 0, 0, 0, 0, 0, 0
*SECT-SCALE
10, 1, 1, 1, 1, 1, 1, 1, , 1
*DGN-MATL
    1, CONC, C40, 2, 0, NO, 1, NO, 0, 0, 0, 0, 0, 0
""",
        encoding="utf-8",
    )
    parsed_model.write_text(
        json.dumps(
            {
                "model": {
                    "elements": [
                        {"id": 1, "type": "BEAM", "family": "beam", "node_ids": [1, 2], "section_id": 10, "material_id": 1},
                    ],
                    "materials": [
                        {"id": 1, "name": "CONC", "raw_tokens": ["C40"]},
                    ],
                    "metadata": {
                        "design_sections": [
                            {
                                "section_id": 10,
                                "row_tokens": [["10", "DBUSER", "SB1000X500", "CC"]],
                                "raw_row_count": 1,
                            }
                        ],
                        "thickness": [],
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
                            }
                        ],
                        "design_material_rebar_payloads": [
                            {
                                "material_id": 1,
                                "material_type": "CONC",
                                "material_name": "C40",
                                "payload_basis": "concrete_r_data",
                                "payload_present": False,
                                "rbcode": "0",
                                "rbmain": "0",
                                "rbsub": "0",
                                "fy_r": None,
                                "fys": 0.0,
                            }
                        ],
                        "rebar_material_codes": [
                            {"tokens": ["GB10(RC)", "HRB400", "GB10(RC)", "HRB400"], "raw": "GB10(RC), HRB400, GB10(RC), HRB400"}
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
        member_ids=np.asarray(["1"], dtype="<U16"),
        group_ids=np.asarray(["S99:unmapped:nogroup:beam:OTHER"], dtype="<U64"),
    )
    changes.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "changes": [
                    {
                        "group_id": "S01:core:nogroup:beam:SB1000X500",
                        "member_type": "beam",
                        "action_family": "connection_detailing",
                        "action_name": "connection_detailing_down",
                        "before_rebar_ratio": 0.02,
                        "after_rebar_ratio": 0.02,
                        "before_thickness_scale": 1.0,
                        "after_thickness_scale": 1.0,
                        "before_detailing_quality": 0.70,
                        "after_detailing_quality": 0.62,
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    connection_projection.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "contract_pass": True,
                "group_local_connection_detailing_payloads": [
                    {
                        "group_id": "S01:core:nogroup:beam:SB1000X500",
                        "member_type": "beam",
                        "action_family": "connection_detailing",
                        "payload_present": True,
                        "payload_source_class": "internal_group_local_connection_detailing_projection",
                        "mapping_source": "direct_group_id",
                        "element_id_count": 1,
                        "element_ids_head": [1],
                        "section_ids": [10],
                        "material_ids": [1],
                        "baseline_detailing_quality": 0.7,
                        "target_detailing_quality": 0.62,
                    }
                ],
                "summary": {
                    "group_local_connection_detailing_payload_row_count": 1,
                    "group_local_connection_detailing_payload_available_count": 1,
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
            "implementation/phase1/export_design_optimization_to_mgt.py",
            "--source-mgt",
            str(src),
            "--parsed-model-json",
            str(parsed_model),
            "--dataset-npz",
            str(dataset),
            "--changes-json",
            str(changes),
            "--connection-detailing-payload-projection-json",
            str(connection_projection),
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
    assert export_report["summary"]["supported_change_count"] == 2
    assert export_report["summary"]["direct_patch_change_count"] == 1
    assert export_report["summary"]["instruction_sidecar_change_count"] == 0
    assert export_report["summary"]["direct_patch_action_family_counts"] == {"connection_detailing": 1}
    assert export_report["summary"]["instruction_sidecar_action_family_counts"] == {}
    assert export_report["summary"]["connection_detailing_structured_payload_mapped_change_count"] == 1
    assert export_report["summary"]["connection_detailing_direct_patch_eligible_change_count"] == 1
    assert export_report["summary"]["support_mode"] == "native_authoring_supported_changeset"
    assert export_report["summary"]["instruction_sidecar_audit_only_change_count"] == 0
    assert export_report["summary"]["instruction_sidecar_zero_touch_verified_change_count"] == 1
    assert export_report["summary"]["instruction_sidecar_manual_input_change_count"] == 0
    assert export_report["summary"]["audit_review_manifest_change_count"] == 0
    assert export_report["summary"]["connection_detailing_delivery_mode"] == "direct_patch_native_authoring_zero_touch_verified"
    assert export_report["summary"]["evidence_model"] == "direct_patch_plus_zero_touch_verification_manifest"
    assert export_report["summary"]["patched_material_row_count"] == 1
    assert export_report["summary"]["cloned_material_count"] == 1
    assert export_report["summary"]["retargeted_element_row_count"] == 1
    assert export_report["summary"]["supported_change_ratio"] == 1.0
    assert export_report["summary"]["direct_patch_change_ratio"] == 0.5
    assert export_report["summary"]["instruction_sidecar_change_ratio"] == 0.0
    assert export_report["summary"]["instruction_sidecar_zero_touch_verified_change_ratio"] == 0.5
    assert export_report["summary"]["unsupported_change_ratio"] == 0.0
    assert (
        export_report["summary"]["native_authoring_summary_line"]
        == "supported=2/2 | direct_patch=1 | zero_touch_verified=1 | manual_sidecar=0 | unsupported=0"
    )
    assert export_report["summary"]["source_vs_output_diff_summary_line"].startswith(
        "source_vs_output_mgt: changed="
    )
    assert export_report["summary"]["source_vs_output_diff_changed_line_count"] >= 1
    assert export_report["summary"]["source_vs_output_diff_sample_count"] >= 1
    assert export_report["summary"]["source_output_mgt_diff_json_exists"] is True
    assert export_report["summary"]["source_output_mgt_diff_preview_exists"] is True
    assert export_report["summary"]["source_output_mgt_diff_window_json_exists"] is True
    assert export_report["summary"]["source_output_mgt_diff_window_preview_exists"] is True
    assert (
        export_report["summary"]["mgt_export_delivery_boundary"]
        == "direct_patch=connection_detailing=1 | sidecar=none | "
        "connection_payload=direct_patch_native_authoring_zero_touch_verified | detailing_payload=manual_sidecar_only"
    )

    manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert manifest_payload["support_mode"] == "native_authoring_supported_changeset"
    assert manifest_payload["applied_material_rows"][0]["payload_source_class"] == "group_local_rebar_payload"
    assert manifest_payload["applied_material_rows"][0]["rbmain"] == "HRB400"
    assert manifest_payload["supported_changes"][0]["direct_patch_kind"] == "connection_detailing_material_metadata"
    assert len(manifest_payload["zero_touch_verified_rows"]) == 1

    sidecar_payload = json.loads(sidecar.read_text(encoding="utf-8"))
    assert sidecar_payload["summary"]["connection_detailing_direct_patch_eligible_change_count"] == 1
    assert sidecar_payload["summary"]["instruction_sidecar_audit_only_change_count"] == 0
    assert sidecar_payload["summary"]["instruction_sidecar_zero_touch_verified_change_count"] == 1
    assert sidecar_payload["summary"]["instruction_sidecar_manual_input_change_count"] == 0
    assert sidecar_payload["summary"]["instruction_sidecar_change_count"] == 0
    assert sidecar_payload["instruction_sidecar_rows"] == []
    assert sidecar_payload["audit_review_reference_rows"] == []
    assert len(sidecar_payload["zero_touch_verified_reference_rows"]) == 1
    audit_payload = json.loads(Path(export_report["artifacts"]["audit_review_manifest_json"]).read_text(encoding="utf-8"))
    assert audit_payload["summary"]["audit_review_manifest_change_count"] == 0
    assert audit_payload["summary"]["audit_review_manifest_action_family_counts"] == {}
    assert audit_payload["summary"]["zero_touch_verified_change_count"] == 1
    assert audit_payload["summary"]["zero_touch_verified_action_family_counts"] == {"connection_detailing": 1}
    packet_payload = json.loads(Path(export_report["artifacts"]["audit_review_packet_manifest_json"]).read_text(encoding="utf-8"))
    assert packet_payload["summary"]["audit_review_packet_count"] == 0
    assert packet_payload["summary"]["audit_review_packet_action_family_counts"] == {}
    assert packet_payload["summary"]["audit_review_packet_file_count"] == 0
    assert packet_payload["summary"]["audit_review_packet_file_action_family_counts"] == {}
    assert packet_payload["audit_review_packet_files"] == []
    queue_payload = json.loads(Path(export_report["artifacts"]["audit_review_queue_manifest_json"]).read_text(encoding="utf-8"))
    assert queue_payload["summary"]["audit_review_queue_item_count"] == 0
    assert queue_payload["summary"]["audit_review_queue_pending_count"] == 0
    assert queue_payload["summary"]["audit_review_queue_acknowledged_count"] == 0
    assert queue_payload["summary"]["audit_review_queue_status_counts"] == {}
    assert queue_payload["summary"]["audit_review_queue_action_family_counts"] == {}
    assert queue_payload["audit_review_queue_items"] == []
    followup_payload = json.loads(
        Path(export_report["artifacts"]["audit_review_followup_manifest_json"]).read_text(encoding="utf-8")
    )
    assert followup_payload["summary"]["audit_review_followup_item_count"] == 0
    assert followup_payload["summary"]["audit_review_followup_open_item_count"] == 0
    assert followup_payload["summary"]["audit_review_followup_closed_item_count"] == 0
    assert followup_payload["summary"]["audit_review_followup_action_counts"] == {}
    assert followup_payload["summary"]["audit_review_followup_owner_counts"] == {}
    assert followup_payload["summary"]["audit_review_followup_status_counts"] == {}
    assert export_report["summary"]["audit_review_followup_action_counts"] == {}
    row = sidecar_payload["zero_touch_verified_reference_rows"][0]
    assert row["direct_patch_applied"] is True
    assert row["direct_patch_kind"] == "connection_detailing_material_metadata"
    assert row["followup_type"] == "connection_detailing_zero_touch_verified"
    assert row["zero_touch_verified"] is True
    assert row["structured_payload_present"] is True

    exported = out_mgt.read_text(encoding="utf-8")
    assert "1, BEAM, 2, 10," in exported
    assert "2, CONC, C40" in exported
    assert "GB10(RC)" in exported
    assert "HRB400" in exported


def test_export_design_optimization_to_mgt_direct_patches_detailing_material_metadata(tmp_path: Path) -> None:
    src = tmp_path / "source_detailing.mgt"
    parsed_model = tmp_path / "model_detailing.json"
    dataset = tmp_path / "dataset_detailing.npz"
    changes = tmp_path / "changes_detailing.json"
    detailing_projection = tmp_path / "detailing_projection.json"
    out_mgt = tmp_path / "optimized_detailing.mgt"
    report = tmp_path / "export_report_detailing.json"
    manifest = tmp_path / "patch_manifest_detailing.json"
    sidecar = tmp_path / "instruction_sidecar_detailing.json"

    src.write_text(
        """*NODE
1, 0.0, 0.0, 0.0
2, 0.0, 0.0, 3.0
*ELEMENT
1, BEAM, 1, 10, 1, 2, 0, 0
*MATERIAL
1, CONC
*SECTION
10, B-SEC
*DGN-SECT
10, DBUSER, SB1000X500, CC, 0, 0, 0, 0, 0, 0, YES, NO, SB, 2, 1.0, 0.5, 0, 0, 0, 0, 0, 0, 0, 0
*SECT-SCALE
10, 1, 1, 1, 1, 1, 1, 1, , 1
*DGN-MATL
    1, CONC, C40, 2, 0, NO, 1, NO, 0, 0, 0, 0, 0, 0
""",
        encoding="utf-8",
    )
    parsed_model.write_text(
        json.dumps(
            {
                "model": {
                    "elements": [
                        {"id": 1, "type": "BEAM", "family": "beam", "node_ids": [1, 2], "section_id": 10, "material_id": 1},
                    ],
                    "materials": [
                        {"id": 1, "name": "CONC", "raw_tokens": ["C40"]},
                    ],
                    "metadata": {
                        "design_sections": [
                            {
                                "section_id": 10,
                                "row_tokens": [["10", "DBUSER", "SB1000X500", "CC"]],
                                "raw_row_count": 1,
                            }
                        ],
                        "thickness": [],
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
                            }
                        ],
                        "design_material_rebar_payloads": [
                            {
                                "material_id": 1,
                                "material_type": "CONC",
                                "material_name": "C40",
                                "payload_basis": "concrete_r_data",
                                "payload_present": False,
                                "rbcode": "0",
                                "rbmain": "0",
                                "rbsub": "0",
                                "fy_r": None,
                                "fys": 0.0,
                            }
                        ],
                        "rebar_material_codes": [
                            {"tokens": ["GB10(RC)", "HRB400", "GB10(RC)", "HRB400"], "raw": "GB10(RC), HRB400, GB10(RC), HRB400"}
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
        member_ids=np.asarray(["1"], dtype="<U16"),
        group_ids=np.asarray(["S99:unmapped:nogroup:beam:OTHER"], dtype="<U64"),
    )
    changes.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "changes": [
                    {
                        "group_id": "S01:core:nogroup:beam:SB1000X500",
                        "member_type": "beam",
                        "action_family": "detailing",
                        "action_name": "detailing_down",
                        "before_rebar_ratio": 0.02,
                        "after_rebar_ratio": 0.02,
                        "before_thickness_scale": 1.0,
                        "after_thickness_scale": 1.0,
                        "before_detailing_quality": 0.70,
                        "after_detailing_quality": 0.62,
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    detailing_projection.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "contract_pass": True,
                "group_local_detailing_payloads": [
                    {
                        "group_id": "S01:core:nogroup:beam:SB1000X500",
                        "member_type": "beam",
                        "action_family": "detailing",
                        "payload_present": True,
                        "payload_source_class": "internal_group_local_detailing_projection",
                        "mapping_source": "direct_group_id",
                        "element_id_count": 1,
                        "element_ids_head": [1],
                        "section_ids": [10],
                        "material_ids": [1],
                        "baseline_detailing_quality": 0.7,
                        "target_detailing_quality": 0.62,
                    }
                ],
                "summary": {
                    "group_local_detailing_payload_row_count": 1,
                    "group_local_detailing_payload_available_count": 1,
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
            "implementation/phase1/export_design_optimization_to_mgt.py",
            "--source-mgt",
            str(src),
            "--parsed-model-json",
            str(parsed_model),
            "--dataset-npz",
            str(dataset),
            "--changes-json",
            str(changes),
            "--detailing-payload-projection-json",
            str(detailing_projection),
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
    assert export_report["summary"]["supported_change_count"] == 2
    assert export_report["summary"]["direct_patch_change_count"] == 1
    assert export_report["summary"]["instruction_sidecar_change_count"] == 0
    assert export_report["summary"]["direct_patch_action_family_counts"] == {"detailing": 1}
    assert export_report["summary"]["instruction_sidecar_action_family_counts"] == {}
    assert export_report["summary"]["detailing_structured_payload_mapped_change_count"] == 1
    assert export_report["summary"]["detailing_direct_patch_eligible_change_count"] == 1
    assert export_report["summary"]["support_mode"] == "native_authoring_supported_changeset"
    assert export_report["summary"]["instruction_sidecar_audit_only_change_count"] == 0
    assert export_report["summary"]["instruction_sidecar_zero_touch_verified_change_count"] == 1
    assert export_report["summary"]["instruction_sidecar_manual_input_change_count"] == 0
    assert export_report["summary"]["audit_review_manifest_change_count"] == 0
    assert export_report["summary"]["detailing_delivery_mode"] == "direct_patch_native_authoring_zero_touch_verified"
    assert export_report["summary"]["evidence_model"] == "direct_patch_plus_zero_touch_verification_manifest"
    assert export_report["summary"]["patched_material_row_count"] == 1
    assert export_report["summary"]["cloned_material_count"] == 1
    assert export_report["summary"]["retargeted_element_row_count"] == 1
    assert (
        export_report["summary"]["mgt_export_delivery_boundary"]
        == "direct_patch=detailing=1 | sidecar=none | "
        "connection_payload=manual_sidecar_only | detailing_payload=direct_patch_native_authoring_zero_touch_verified"
    )

    manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert manifest_payload["support_mode"] == "native_authoring_supported_changeset"
    assert manifest_payload["applied_material_rows"][0]["payload_source_class"] == "group_local_rebar_payload"
    assert manifest_payload["applied_material_rows"][0]["rbmain"] == "HRB400"
    assert manifest_payload["supported_changes"][0]["direct_patch_kind"] == "detailing_material_metadata"
    assert len(manifest_payload["zero_touch_verified_rows"]) == 1

    sidecar_payload = json.loads(sidecar.read_text(encoding="utf-8"))
    assert sidecar_payload["summary"]["detailing_direct_patch_eligible_change_count"] == 1
    assert sidecar_payload["summary"]["instruction_sidecar_audit_only_change_count"] == 0
    assert sidecar_payload["summary"]["instruction_sidecar_zero_touch_verified_change_count"] == 1
    assert sidecar_payload["summary"]["instruction_sidecar_manual_input_change_count"] == 0
    assert sidecar_payload["summary"]["instruction_sidecar_change_count"] == 0
    assert sidecar_payload["instruction_sidecar_rows"] == []
    assert sidecar_payload["audit_review_reference_rows"] == []
    assert len(sidecar_payload["zero_touch_verified_reference_rows"]) == 1
    audit_payload = json.loads(Path(export_report["artifacts"]["audit_review_manifest_json"]).read_text(encoding="utf-8"))
    assert audit_payload["summary"]["audit_review_manifest_change_count"] == 0
    assert audit_payload["summary"]["audit_review_manifest_action_family_counts"] == {}
    assert audit_payload["summary"]["zero_touch_verified_change_count"] == 1
    assert audit_payload["summary"]["zero_touch_verified_action_family_counts"] == {"detailing": 1}
    packet_payload = json.loads(Path(export_report["artifacts"]["audit_review_packet_manifest_json"]).read_text(encoding="utf-8"))
    assert packet_payload["summary"]["audit_review_packet_count"] == 0
    assert packet_payload["summary"]["audit_review_packet_action_family_counts"] == {}
    assert packet_payload["summary"]["audit_review_packet_file_count"] == 0
    assert packet_payload["summary"]["audit_review_packet_file_action_family_counts"] == {}
    assert packet_payload["audit_review_packet_files"] == []
    queue_payload = json.loads(Path(export_report["artifacts"]["audit_review_queue_manifest_json"]).read_text(encoding="utf-8"))
    assert queue_payload["summary"]["audit_review_queue_item_count"] == 0
    assert queue_payload["summary"]["audit_review_queue_status_counts"] == {}
    assert queue_payload["summary"]["audit_review_queue_action_family_counts"] == {}
    assert queue_payload["audit_review_queue_items"] == []
    row = sidecar_payload["zero_touch_verified_reference_rows"][0]
    assert row["direct_patch_applied"] is True
    assert row["direct_patch_kind"] == "detailing_material_metadata"
    assert row["followup_type"] == "detailing_zero_touch_verified"
    assert row["zero_touch_verified"] is True
    assert row["structured_payload_present"] is True
    assert row["element_ids"] == [1]
    assert row["structured_payload_section_ids"] == [10]
    assert row["structured_payload_material_ids"] == [1]

    exported = out_mgt.read_text(encoding="utf-8")
    assert "1, BEAM, 2, 10," in exported
    assert "2, CONC, C40" in exported
    assert "GB10(RC)" in exported
    assert "HRB400" in exported


def test_export_design_optimization_to_mgt_direct_patches_multi_material_detailing_metadata(tmp_path: Path) -> None:
    src = tmp_path / "source_multi_detailing.mgt"
    parsed_model = tmp_path / "model_multi_detailing.json"
    dataset = tmp_path / "dataset_multi_detailing.npz"
    changes = tmp_path / "changes_multi_detailing.json"
    detailing_projection = tmp_path / "detailing_multi_projection.json"
    out_mgt = tmp_path / "optimized_multi_detailing.mgt"
    report = tmp_path / "export_report_multi_detailing.json"
    manifest = tmp_path / "patch_manifest_multi_detailing.json"
    sidecar = tmp_path / "instruction_sidecar_multi_detailing.json"

    src.write_text(
        """*NODE
1, 0.0, 0.0, 0.0
2, 4.0, 0.0, 0.0
3, 4.0, 4.0, 0.0
4, 0.0, 4.0, 0.0
5, 8.0, 0.0, 0.0
6, 8.0, 4.0, 0.0
*ELEMENT
1, PLATE, 1, 3, 1, 2, 3, 4, 0, 0
2, PLATE, 4, 3, 2, 5, 6, 3, 0, 0
*MATERIAL
1, CONC
4, CONC
*THICKNESS
3, VALUE, 3, YES, 0.2, 0, NO, 0, 0.5
*DGN-MATL
    1, CONC, C40, 2, 0, NO, 1, NO, 0, 0, 0, 0, 0, 0
    4, CONC, C40WBR, 2, 0, NO, 1, NO, 0, 0, 0, 0, 0, 0
""",
        encoding="utf-8",
    )
    parsed_model.write_text(
        json.dumps(
            {
                "model": {
                    "elements": [
                        {"id": 1, "type": "PLATE", "family": "shell", "node_ids": [1, 2, 3, 4], "section_id": 3, "material_id": 1},
                        {"id": 2, "type": "PLATE", "family": "shell", "node_ids": [2, 5, 6, 3], "section_id": 3, "material_id": 4},
                    ],
                    "materials": [
                        {"id": 1, "name": "CONC", "raw_tokens": ["C40"]},
                        {"id": 4, "name": "CONC", "raw_tokens": ["C40WBR"]},
                    ],
                    "metadata": {
                        "design_sections": [],
                        "thickness": [
                            {
                                "thickness_id": 3,
                                "row_tokens": [["3", "VALUE", "3", "YES", "0.2", "0", "NO", "0", "0.5"]],
                                "raw_row_count": 1,
                            }
                        ],
                        "section_scales": [],
                        "design_material_rebar_payloads": [
                            {
                                "material_id": 1,
                                "material_type": "CONC",
                                "material_name": "C40",
                                "payload_basis": "concrete_r_data",
                                "payload_present": False,
                                "rbcode": "0",
                                "rbmain": "0",
                                "rbsub": "0",
                                "fy_r": None,
                                "fys": 0.0,
                            },
                            {
                                "material_id": 4,
                                "material_type": "CONC",
                                "material_name": "C40WBR",
                                "payload_basis": "concrete_r_data",
                                "payload_present": False,
                                "rbcode": "0",
                                "rbmain": "0",
                                "rbsub": "0",
                                "fy_r": None,
                                "fys": 0.0,
                            },
                        ],
                        "rebar_material_codes": [
                            {"tokens": ["GB10(RC)", "HRB400", "GB10(RC)", "HRB400"], "raw": "GB10(RC), HRB400, GB10(RC), HRB400"}
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
        member_ids=np.asarray(["1", "2"], dtype="<U16"),
        group_ids=np.asarray(["S01:perimeter:nogroup:slab:default", "S01:perimeter:nogroup:slab:default"], dtype="<U64"),
    )
    changes.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "changes": [
                    {
                        "group_id": "S01:perimeter:nogroup:slab:default",
                        "member_type": "wall",
                        "action_family": "detailing",
                        "action_name": "detailing_down",
                        "before_rebar_ratio": 0.01,
                        "after_rebar_ratio": 0.01,
                        "before_thickness_scale": 1.0,
                        "after_thickness_scale": 1.0,
                        "before_detailing_quality": 1.10,
                        "after_detailing_quality": 1.06,
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    detailing_projection.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "contract_pass": True,
                "group_local_detailing_payloads": [
                    {
                        "group_id": "S01:perimeter:nogroup:slab:default",
                        "member_type": "wall",
                        "action_family": "detailing",
                        "payload_present": True,
                        "payload_source_class": "internal_group_local_detailing_projection",
                        "mapping_source": "direct_group_id",
                        "element_id_count": 2,
                        "element_ids_head": [1, 2],
                        "section_ids": [3],
                        "material_ids": [1, 4],
                        "baseline_detailing_quality": 1.10,
                        "target_detailing_quality": 1.06,
                    }
                ],
                "summary": {
                    "group_local_detailing_payload_row_count": 1,
                    "group_local_detailing_payload_available_count": 1,
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
            "implementation/phase1/export_design_optimization_to_mgt.py",
            "--source-mgt",
            str(src),
            "--parsed-model-json",
            str(parsed_model),
            "--dataset-npz",
            str(dataset),
            "--changes-json",
            str(changes),
            "--detailing-payload-projection-json",
            str(detailing_projection),
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
    assert export_report["summary"]["supported_change_count"] == 2
    assert export_report["summary"]["direct_patch_change_count"] == 1
    assert export_report["summary"]["instruction_sidecar_change_count"] == 0
    assert export_report["summary"]["direct_patch_action_family_counts"] == {"detailing": 1}
    assert export_report["summary"]["instruction_sidecar_action_family_counts"] == {}
    assert export_report["summary"]["detailing_structured_payload_mapped_change_count"] == 1
    assert export_report["summary"]["detailing_direct_patch_eligible_change_count"] == 1
    assert export_report["summary"]["support_mode"] == "native_authoring_supported_changeset"
    assert export_report["summary"]["instruction_sidecar_audit_only_change_count"] == 0
    assert export_report["summary"]["instruction_sidecar_zero_touch_verified_change_count"] == 1
    assert export_report["summary"]["instruction_sidecar_manual_input_change_count"] == 0
    assert export_report["summary"]["detailing_delivery_mode"] == "direct_patch_native_authoring_zero_touch_verified"
    assert export_report["summary"]["evidence_model"] == "direct_patch_plus_zero_touch_verification_manifest"
    assert export_report["summary"]["patched_material_row_count"] == 2
    assert export_report["summary"]["cloned_material_count"] == 2
    assert export_report["summary"]["retargeted_element_row_count"] == 2

    manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert len(manifest_payload["applied_material_rows"]) == 2
    assert manifest_payload["supported_changes"][0]["direct_patch_kind"] == "detailing_material_metadata"
    assert len(manifest_payload["zero_touch_verified_rows"]) == 1

    sidecar_payload = json.loads(sidecar.read_text(encoding="utf-8"))
    assert sidecar_payload["summary"]["instruction_sidecar_audit_only_change_count"] == 0
    assert sidecar_payload["summary"]["instruction_sidecar_zero_touch_verified_change_count"] == 1
    assert sidecar_payload["summary"]["instruction_sidecar_manual_input_change_count"] == 0
    assert sidecar_payload["summary"]["instruction_sidecar_change_count"] == 0
    assert sidecar_payload["instruction_sidecar_rows"] == []
    assert sidecar_payload["audit_review_reference_rows"] == []
    assert len(sidecar_payload["zero_touch_verified_reference_rows"]) == 1
    packet_payload = json.loads(Path(export_report["artifacts"]["audit_review_packet_manifest_json"]).read_text(encoding="utf-8"))
    assert packet_payload["summary"]["audit_review_packet_count"] == 0
    assert packet_payload["summary"]["audit_review_packet_action_family_counts"] == {}
    assert packet_payload["summary"]["audit_review_packet_file_count"] == 0
    assert packet_payload["summary"]["audit_review_packet_file_action_family_counts"] == {}
    assert packet_payload["audit_review_packet_files"] == []
    queue_payload = json.loads(Path(export_report["artifacts"]["audit_review_queue_manifest_json"]).read_text(encoding="utf-8"))
    assert queue_payload["summary"]["audit_review_queue_item_count"] == 0
    assert queue_payload["summary"]["audit_review_queue_status_counts"] == {}
    assert queue_payload["summary"]["audit_review_queue_action_family_counts"] == {}
    assert queue_payload["audit_review_queue_items"] == []
    row = sidecar_payload["zero_touch_verified_reference_rows"][0]
    assert row["direct_patch_applied"] is True
    assert row["direct_patch_kind"] == "detailing_material_metadata"
    assert row["followup_type"] == "detailing_zero_touch_verified"
    assert row["structured_payload_material_ids"] == [1, 4]

    exported = out_mgt.read_text(encoding="utf-8")
    assert "1, PLATE, 5, 3," in exported
    assert "2, PLATE, 6, 3," in exported
    assert "5, CONC, C40" in exported
    assert "6, CONC, C40WBR" in exported


def test_export_design_optimization_to_mgt_supports_perimeter_frame_via_sidecar(tmp_path: Path) -> None:
    src = tmp_path / "source_pf.mgt"
    parsed_model = tmp_path / "model_pf.json"
    dataset = tmp_path / "dataset_pf.npz"
    changes = tmp_path / "changes_pf.json"
    out_mgt = tmp_path / "optimized_pf.mgt"
    report = tmp_path / "export_report_pf.json"
    manifest = tmp_path / "patch_manifest_pf.json"
    sidecar = tmp_path / "instruction_sidecar_pf.json"

    _write_mgt(src)
    _write_model_json(parsed_model)
    np.savez_compressed(
        dataset,
        member_ids=np.asarray(["1"], dtype="<U16"),
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
                        "action_name": "perimeter_frame_down",
                        "before_rebar_ratio": 0.074,
                        "after_rebar_ratio": 0.064,
                        "before_thickness_scale": 1.02,
                        "after_thickness_scale": 1.02,
                        "before_detailing_quality": 0.55,
                        "after_detailing_quality": 0.55,
                        "zone_label": "perimeter",
                        "story_band": 5,
                        "semantic_group": "2",
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    export_cmd = [
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
        "--output-mgt",
        str(out_mgt),
        "--report-out",
        str(report),
        "--patch-manifest-out",
        str(manifest),
        "--instruction-sidecar-out",
        str(sidecar),
    ]
    proc = subprocess.run(export_cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr

    export_report = json.loads(report.read_text(encoding="utf-8"))
    assert export_report["contract_pass"] is True
    assert export_report["summary"]["supported_change_count"] == 1
    assert export_report["summary"]["direct_patch_change_count"] == 0
    assert export_report["summary"]["instruction_sidecar_change_count"] == 1
    assert export_report["summary"]["unsupported_change_count"] == 0
    assert export_report["summary"]["rebar_payload_namespace_mode"] == "none"
    assert export_report["summary"]["rebar_direct_patch_eligible_change_count"] == 0
    assert export_report["summary"]["direct_patch_action_family_counts"] == {}
    assert export_report["summary"]["instruction_sidecar_action_family_counts"] == {"perimeter_frame": 1}
    assert export_report["summary"]["instruction_sidecar_followup_type_counts"] == {"perimeter_frame_manual_update": 1}

    sidecar_payload = json.loads(sidecar.read_text(encoding="utf-8"))
    row = sidecar_payload["instruction_sidecar_rows"][0]
    assert row["instruction_kind"] == "perimeter_frame_followup"
    assert row["review_priority"] == "high"
    assert row["before_rebar_ratio"] == 0.074
    assert row["after_rebar_ratio"] == 0.064


def test_export_design_optimization_to_mgt_clones_shared_thickness_and_retargets_elements(tmp_path: Path) -> None:
    src = tmp_path / "source_conflict.mgt"
    parsed_model = tmp_path / "model_conflict.json"
    dataset = tmp_path / "dataset_conflict.npz"
    changes = tmp_path / "changes_conflict.json"
    out_mgt = tmp_path / "optimized_conflict.mgt"
    report = tmp_path / "export_report_conflict.json"
    manifest = tmp_path / "patch_manifest_conflict.json"
    roundtrip_json = tmp_path / "roundtrip_conflict.json"
    roundtrip_npz = tmp_path / "roundtrip_conflict.npz"
    roundtrip_edges = tmp_path / "roundtrip_conflict_edges.json"
    roundtrip_report = tmp_path / "roundtrip_conflict_report.json"

    src.write_text(
        """*NODE
1, 0.0, 0.0, 0.0
2, 0.0, 0.0, 3.0
3, 3.0, 0.0, 3.0
4, 3.0, 0.0, 0.0
5, 6.0, 0.0, 0.0
6, 6.0, 0.0, 3.0
7, 9.0, 0.0, 3.0
8, 9.0, 0.0, 0.0
*ELEMENT
1, PLATE, 2, 3, 1, 2, 3, 4, 0, 0
2, PLATE, 2, 3, 5, 6, 7, 8, 0, 0
*MATERIAL
2, CONC
*SECTION
3, WALL-THK
*THICKNESS
3, VALUE, 3, YES, 0.2, 0, NO, 0, 0.5
""",
        encoding="utf-8",
    )
    parsed_model.write_text(
        json.dumps(
            {
                "model": {
                    "elements": [
                        {"id": 1, "type": "PLATE", "family": "shell", "node_ids": [1, 2, 3, 4], "section_id": 3, "material_id": 2},
                        {"id": 2, "type": "PLATE", "family": "shell", "node_ids": [5, 6, 7, 8], "section_id": 3, "material_id": 2},
                    ],
                    "metadata": {
                        "design_sections": [],
                        "thickness": [
                            {
                                "thickness_id": 3,
                                "row_tokens": [["3", "VALUE", "3", "YES", "0.2", "0", "NO", "0", "0.5"]],
                                "raw_row_count": 1,
                            }
                        ],
                        "section_scales": [],
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
        member_ids=np.asarray(["1", "2"], dtype="<U16"),
        group_ids=np.asarray(
            ["S01:perimeter:nogroup:wall:default", "S02:perimeter:nogroup:wall:default"],
            dtype="<U64",
        ),
    )
    changes.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "changes": [
                    {
                        "group_id": "S01:perimeter:nogroup:wall:default",
                        "member_type": "wall",
                        "action_family": "wall_thickness",
                        "before_thickness_scale": 1.0,
                        "after_thickness_scale": 0.8,
                    },
                    {
                        "group_id": "S02:perimeter:nogroup:wall:default",
                        "member_type": "wall",
                        "action_family": "wall_thickness",
                        "before_thickness_scale": 1.0,
                        "after_thickness_scale": 0.9,
                    },
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    export_cmd = [
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
        "--output-mgt",
        str(out_mgt),
        "--report-out",
        str(report),
        "--patch-manifest-out",
        str(manifest),
    ]
    proc = subprocess.run(export_cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr

    export_report = json.loads(report.read_text(encoding="utf-8"))
    assert export_report["contract_pass"] is True
    assert export_report["summary"]["supported_change_count"] == 2
    assert export_report["summary"]["unsupported_change_count"] == 0
    assert export_report["summary"]["cloned_thickness_count"] == 2
    assert export_report["summary"]["retargeted_element_row_count"] == 2

    exported = out_mgt.read_text(encoding="utf-8")
    assert "1, PLATE, 2, 4," in exported
    assert "2, PLATE, 2, 5," in exported
    assert "4, VALUE, 3, YES, 0.16, 0, NO, 0, 0.5" in exported
    assert "5, VALUE, 3, YES, 0.18, 0, NO, 0, 0.5" in exported

    roundtrip_cmd = [
        sys.executable,
        "implementation/phase1/parse_midas_mgt_to_json_npz.py",
        "--mgt",
        str(out_mgt),
        "--json-out",
        str(roundtrip_json),
        "--npz-out",
        str(roundtrip_npz),
        "--edge-list-out",
        str(roundtrip_edges),
        "--report-out",
        str(roundtrip_report),
        "--min-nodes",
        "8",
        "--min-elements",
        "2",
    ]
    proc = subprocess.run(roundtrip_cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    parsed = json.loads(roundtrip_json.read_text(encoding="utf-8"))
    thickness_rows = parsed["model"]["metadata"]["thickness"]
    thickness_ids = {int(row["thickness_id"]) for row in thickness_rows}
    assert thickness_ids == {3, 4, 5}
    element_props = {int(row["id"]): int(row["section_id"]) for row in parsed["model"]["elements"]}
    assert element_props[1] == 4
    assert element_props[2] == 5


def test_export_design_optimization_to_mgt_reports_alt_slab_wall_rebar_bridge(tmp_path: Path) -> None:
    src = tmp_path / "source_rebar_bridge.mgt"
    parsed_model = tmp_path / "model_rebar_bridge.json"
    dataset = tmp_path / "dataset_rebar_bridge.npz"
    changes = tmp_path / "changes_rebar_bridge.json"
    out_mgt = tmp_path / "optimized_rebar_bridge.mgt"
    report = tmp_path / "export_report_rebar_bridge.json"
    manifest = tmp_path / "patch_manifest_rebar_bridge.json"
    sidecar = tmp_path / "instruction_sidecar_rebar_bridge.json"

    _write_mgt(src)
    _write_model_json(parsed_model)
    parsed_payload = json.loads(parsed_model.read_text(encoding="utf-8"))
    parsed_payload["model"]["metadata"]["design_material_rebar_payloads"] = [
        {
            "material_id": 2,
            "material_type": "CONC",
            "material_name": "C40",
            "payload_basis": "concrete_r_data",
            "payload_present": False,
            "rbcode": "0",
            "rbmain": "0",
            "rbsub": "0",
            "fy_r": None,
            "fys": 0.0,
        }
    ]
    parsed_payload["model"]["metadata"]["group_local_rebar_payloads"] = []
    parsed_model.write_text(json.dumps(parsed_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    np.savez_compressed(
        dataset,
        member_ids=np.asarray(["2"], dtype="<U16"),
        group_ids=np.asarray(["S04:intermediate:nogroup:wall:SB800X4002.00"], dtype="<U64"),
    )
    changes.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "changes": [
                    {
                        "group_id": "S04:intermediate:nogroup:slab:SB800X4002.00",
                        "member_type": "wall",
                        "action_family": "rebar",
                        "before_rebar_ratio": 0.01,
                        "after_rebar_ratio": 0.004,
                        "before_thickness_scale": 1.0,
                        "after_thickness_scale": 1.0,
                        "before_detailing_quality": 0.7,
                        "after_detailing_quality": 0.7,
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    export_cmd = [
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
        "--output-mgt",
        str(out_mgt),
        "--report-out",
        str(report),
        "--patch-manifest-out",
        str(manifest),
        "--instruction-sidecar-out",
        str(sidecar),
    ]
    proc = subprocess.run(export_cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr

    export_report = json.loads(report.read_text(encoding="utf-8"))
    assert export_report["summary"]["supported_change_count"] == 1
    assert export_report["summary"]["instruction_sidecar_change_count"] == 1
    assert export_report["summary"]["rebar_payload_namespace_mode"] == "material_level_only"
    assert export_report["summary"]["rebar_payload_material_level_namespace_present"] is True
    assert export_report["summary"]["rebar_payload_group_local_namespace_present"] is False
    assert export_report["summary"]["derived_group_local_rebar_bridge_row_count"] == 1
    assert export_report["summary"]["derived_group_local_rebar_mapped_change_count"] == 1
    assert export_report["summary"]["rebar_direct_patch_eligible_change_count"] == 0
    assert export_report["summary"]["rebar_direct_patch_ineligible_reason_counts"] == {"material_payload_missing": 1}
    assert export_report["summary"]["rebar_direct_patch_mapping_source_counts"] == {"alt_slab_wall_group_id": 1}

    manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert manifest_payload["derived_group_local_rebar_bridge_rows"][0]["mapping_source"] == "alt_slab_wall_group_id"
    assert manifest_payload["derived_group_local_rebar_bridge_rows"][0]["material_ids"] == [2]
    assert manifest_payload["derived_group_local_rebar_bridge_rows"][0]["direct_patch_eligible"] is False


def test_export_design_optimization_to_mgt_direct_patches_group_local_rebar_payloads(tmp_path: Path) -> None:
    src = tmp_path / "source_group_local_rebar.mgt"
    parsed_model = tmp_path / "model_group_local_rebar.json"
    dataset = tmp_path / "dataset_group_local_rebar.npz"
    changes = tmp_path / "changes_group_local_rebar.json"
    out_mgt = tmp_path / "optimized_group_local_rebar.mgt"
    report = tmp_path / "export_report_group_local_rebar.json"
    manifest = tmp_path / "patch_manifest_group_local_rebar.json"
    sidecar = tmp_path / "instruction_sidecar_group_local_rebar.json"
    roundtrip_json = tmp_path / "roundtrip_group_local_rebar.json"
    roundtrip_npz = tmp_path / "roundtrip_group_local_rebar.npz"
    roundtrip_edges = tmp_path / "roundtrip_group_local_rebar_edges.json"
    roundtrip_report = tmp_path / "roundtrip_group_local_rebar_report.json"

    src.write_text(
        """*NODE
1, 0.0, 0.0, 0.0
2, 0.0, 0.0, 3.0
3, 3.0, 0.0, 3.0
4, 3.0, 0.0, 0.0
*ELEMENT
1, PLATE, 1, 3, 1, 2, 3, 4, 0, 0
*MATERIAL
1, CONC
*SECTION
3, WALL-THK
*THICKNESS
3, VALUE, 3, YES, 0.2, 0, NO, 0, 0.5
*DGN-MATL
    1, CONC , C40, 2, 0, NO, 1, NO, 0, 0, 0, 0, 0, 0
""",
        encoding="utf-8",
    )
    parsed_model.write_text(
        json.dumps(
            {
                "model": {
                    "elements": [
                        {"id": 1, "type": "PLATE", "family": "shell", "node_ids": [1, 2, 3, 4], "section_id": 3, "material_id": 1},
                    ],
                    "metadata": {
                        "design_sections": [],
                        "thickness": [
                            {
                                "thickness_id": 3,
                                "row_tokens": [["3", "VALUE", "3", "YES", "0.2", "0", "NO", "0", "0.5"]],
                                "raw_row_count": 1,
                            }
                        ],
                        "section_scales": [],
                        "design_material_rebar_payloads": [
                            {
                                "material_id": 1,
                                "material_type": "CONC",
                                "material_name": "C40",
                                "payload_basis": "concrete_r_data",
                                "payload_present": False,
                                "rbcode": "0",
                                "rbmain": "0",
                                "rbsub": "0",
                                "fy_r": 0.0,
                                "fys": 0.0,
                            }
                        ],
                        "group_local_rebar_payloads": [
                            {
                                "group_id": "S02:core:nogroup:wall:default",
                                "payload_present": True,
                                "rbcode": "SD400",
                                "rbmain": "D16",
                                "rbsub": "D10",
                                "fy_r": 400.0,
                                "fys": 400.0,
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
        member_ids=np.asarray(["1"], dtype="<U16"),
        group_ids=np.asarray(["S02:core:nogroup:wall:default"], dtype="<U64"),
    )
    changes.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "changes": [
                    {
                        "group_id": "S02:core:nogroup:wall:default",
                        "member_type": "wall",
                        "action_family": "rebar",
                        "before_rebar_ratio": 0.01,
                        "after_rebar_ratio": 0.004,
                        "before_thickness_scale": 1.0,
                        "after_thickness_scale": 1.0,
                        "before_detailing_quality": 0.7,
                        "after_detailing_quality": 0.7,
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    export_cmd = [
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
        "--output-mgt",
        str(out_mgt),
        "--report-out",
        str(report),
        "--patch-manifest-out",
        str(manifest),
        "--instruction-sidecar-out",
        str(sidecar),
    ]
    proc = subprocess.run(export_cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr

    export_report = json.loads(report.read_text(encoding="utf-8"))
    assert export_report["contract_pass"] is True
    assert export_report["summary"]["supported_change_count"] == 1
    assert export_report["summary"]["direct_patch_change_count"] == 1
    assert export_report["summary"]["instruction_sidecar_change_count"] == 0
    assert export_report["summary"]["group_local_rebar_payload_row_count"] == 1
    assert export_report["summary"]["group_local_rebar_payload_available_count"] == 1
    assert export_report["summary"]["rebar_payload_namespace_mode"] == "group_local"
    assert export_report["summary"]["rebar_direct_patch_eligible_change_count"] == 1
    assert export_report["summary"]["direct_patch_action_family_counts"] == {"rebar": 1}
    assert export_report["summary"]["patched_material_row_count"] == 1
    assert export_report["summary"]["cloned_material_count"] == 1
    assert export_report["summary"]["retargeted_element_row_count"] == 1
    assert export_report["summary"]["rebar_delivery_mode"] == "direct_patch_eligible"

    manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert manifest_payload["applied_material_rows"][0]["payload_source_class"] == "group_local_rebar_payload"
    assert manifest_payload["derived_group_local_rebar_bridge_rows"][0]["direct_patch_eligible"] is True
    assert manifest_payload["derived_group_local_rebar_bridge_rows"][0]["group_local_payload_present"] is True

    sidecar_payload = json.loads(sidecar.read_text(encoding="utf-8"))
    assert sidecar_payload["summary"]["instruction_sidecar_change_count"] == 0
    assert sidecar_payload["summary"]["rebar_direct_patch_eligible_change_count"] == 1

    exported = out_mgt.read_text(encoding="utf-8")
    assert "1, PLATE, 2, 3," in exported
    assert "2, CONC, C40" in exported
    assert "D16" in exported
    assert "D10" in exported

    roundtrip_cmd = [
        sys.executable,
        "implementation/phase1/parse_midas_mgt_to_json_npz.py",
        "--mgt",
        str(out_mgt),
        "--json-out",
        str(roundtrip_json),
        "--npz-out",
        str(roundtrip_npz),
        "--edge-list-out",
        str(roundtrip_edges),
        "--report-out",
        str(roundtrip_report),
        "--min-nodes",
        "4",
        "--min-elements",
        "1",
    ]
    proc = subprocess.run(roundtrip_cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr

    parsed = json.loads(roundtrip_json.read_text(encoding="utf-8"))
    assert parsed["model"]["elements"][0]["material_id"] == 2
    payload_rows = parsed["model"]["metadata"]["design_material_rebar_payloads"]
    payload_by_material = {int(row["material_id"]): row for row in payload_rows}
    assert payload_by_material[2]["payload_present"] is True
    assert payload_by_material[2]["rbmain"] == "D16"
    assert payload_by_material[2]["rbsub"] == "D10"


def test_export_design_optimization_to_mgt_direct_patches_src_perimeter_frame_payloads(tmp_path: Path) -> None:
    src = tmp_path / "source_src_pf.mgt"
    parsed_model = tmp_path / "model_src_pf.json"
    dataset = tmp_path / "dataset_src_pf.npz"
    changes = tmp_path / "changes_src_pf.json"
    out_mgt = tmp_path / "optimized_src_pf.mgt"
    report = tmp_path / "export_report_src_pf.json"
    manifest = tmp_path / "patch_manifest_src_pf.json"
    sidecar = tmp_path / "instruction_sidecar_src_pf.json"

    src.write_text(
        """*NODE
1, 0.0, 0.0, 0.0
2, 0.0, 0.0, 3.0
*ELEMENT
1, BEAM, 1, 31, 1, 2, 0, 0
*MATERIAL
1, SRC
*SECTION
31, B-SEC
*DGN-MATL
    1, SRC  , C40+Q235          , 2,  2.0600e+08, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 2, 0, , , , 0, 0,NO, 0.0000e+00,     0,, 0, 0,0, 0, 0,0, 0, 0,0, 0, 0,0, 0, 0, 0.0000e+00,     0,, 0, 0,0, 0, 0,0, 0, 0,0, 0, 0,0, 0, 0, 0.0000e+00,     0,, 0, 0,0, 0, 0,0, 0, 0,0, 0, 0,0, 0, 0,
""",
        encoding="utf-8",
    )
    parsed_model.write_text(
        json.dumps(
            {
                "model": {
                    "elements": [
                        {"id": 1, "type": "BEAM", "family": "beam", "node_ids": [1, 2], "section_id": 31, "material_id": 1},
                    ],
                    "materials": [
                        {"id": 1, "name": "SRC", "raw_tokens": ["C40+Q235", "0", "0", "C"]},
                    ],
                    "metadata": {
                        "design_sections": [
                            {
                                "section_id": 31,
                                "row_tokens": [["31", "DBUSER", "P 50x4", "CC"]],
                                "raw_row_count": 1,
                            }
                        ],
                        "thickness": [],
                        "section_scales": [],
                        "design_material_rebar_payloads": [
                            {
                                "material_id": 1,
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
                        "group_local_rebar_payloads": [
                            {
                                "group_id": "S05:perimeter:2:column:P 50x4",
                                "payload_present": True,
                                "rbcode": "GB10(RC)",
                                "rbmain": "D29",
                                "rbsub": "D25",
                                "fy_r": 400.0,
                                "fys": 400.0,
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
        member_ids=np.asarray(["1"], dtype="<U16"),
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

    export_cmd = [
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
        "--output-mgt",
        str(out_mgt),
        "--report-out",
        str(report),
        "--patch-manifest-out",
        str(manifest),
        "--instruction-sidecar-out",
        str(sidecar),
    ]
    proc = subprocess.run(export_cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr

    export_report = json.loads(report.read_text(encoding="utf-8"))
    assert export_report["contract_pass"] is True
    assert export_report["summary"]["supported_change_count"] == 1
    assert export_report["summary"]["direct_patch_change_count"] == 1
    assert export_report["summary"]["instruction_sidecar_change_count"] == 0
    assert export_report["summary"]["group_local_rebar_payload_row_count"] == 1
    assert export_report["summary"]["group_local_rebar_payload_available_count"] == 1
    assert export_report["summary"]["rebar_direct_patch_eligible_change_count"] == 1
    assert export_report["summary"]["direct_patch_action_family_counts"] == {"perimeter_frame": 1}
    assert export_report["summary"]["patched_material_row_count"] == 1
    assert export_report["summary"]["cloned_material_count"] == 1
    assert export_report["summary"]["retargeted_element_row_count"] == 1
    assert export_report["summary"]["rebar_delivery_mode"] == "direct_patch_eligible"

    manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert manifest_payload["applied_material_rows"][0]["payload_source_class"] == "group_local_rebar_payload"
    assert manifest_payload["applied_material_rows"][0]["source_material_type"] == "SRC"
    assert manifest_payload["derived_group_local_rebar_bridge_rows"][0]["direct_patch_eligible"] is True
    assert manifest_payload["derived_group_local_rebar_bridge_rows"][0]["group_local_payload_present"] is True

    sidecar_payload = json.loads(sidecar.read_text(encoding="utf-8"))
    assert sidecar_payload["summary"]["instruction_sidecar_change_count"] == 0
    assert sidecar_payload["summary"]["rebar_direct_patch_eligible_change_count"] == 1

    exported = out_mgt.read_text(encoding="utf-8")
    assert "1, BEAM, 2, 31," in exported
    assert "2, SRC" in exported
    assert "D29" in exported
    assert "D25" in exported


def test_resolve_input_path_falls_back_to_repo_root_for_default_projection_path(tmp_path: Path) -> None:
    repo_relative = Path("implementation/phase1/open_data/midas/midas_generator_33.rebar_payload_projection.json")
    expected = (Path(__file__).resolve().parents[1] / repo_relative).resolve()
    nested = tmp_path / "nested" / "cwd"
    nested.mkdir(parents=True)
    before = Path.cwd()
    try:
        os.chdir(nested)
        resolved = _resolve_input_path(repo_relative)
    finally:
        os.chdir(before)
    assert resolved == expected
