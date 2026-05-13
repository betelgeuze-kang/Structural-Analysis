from __future__ import annotations

import json
from pathlib import Path
import subprocess

from implementation.phase1.parse_midas_binary_meb_to_json_npz import decode_meb_inventory


def test_parse_midas_binary_meb_to_json_npz_scaffold(tmp_path: Path) -> None:
    meb = tmp_path / "sample.meb"
    meb.write_bytes(b"MBDG\x00\x00__DBMS_DATA__\x00GUID\x00xUNIT\x00xMATL\x00xSECT\x00xSTOR\x00xMEMB")
    report = tmp_path / "probe.json"
    proc = subprocess.run(
        [
            "python3",
            "implementation/phase1/parse_midas_binary_meb_to_json_npz.py",
            "--meb",
            str(meb),
            "--report-out",
            str(report),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["reason_code"] in {
        "PASS_TABLE_DIRECTORY_ONLY",
        "PASS_HEURISTIC_GEOMETRY_PREVIEW_READY",
    }
    assert payload["contract_pass"] is True
    assert payload["probe"]["layout_family"] == "MBDG_DB_CONTAINER"
    assert payload["probe"]["scaffold_ready"] is True


def test_parse_midas_binary_meb_to_json_npz_plain_table_tokens(tmp_path: Path) -> None:
    meb = tmp_path / "plain_tokens.meb"
    meb.write_bytes(b"MBDG\x00\x00__DBMS_DATA__\x00GUID\x00UNIT\x00MATL\x00SECT\x00STOR\x00PONT\x00MEMB")
    report = tmp_path / "plain_probe.json"
    proc = subprocess.run(
        [
            "python3",
            "implementation/phase1/parse_midas_binary_meb_to_json_npz.py",
            "--meb",
            str(meb),
            "--report-out",
            str(report),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["reason_code"] == "PASS_TABLE_DIRECTORY_ONLY"
    assert payload["probe"]["layout_family"] == "MBDG_DB_CONTAINER"
    assert payload["probe"]["scaffold_ready"] is True
    assert payload["summary"]["table_entry_count"] >= 4


def test_parse_midas_binary_meb_to_json_npz_mcvl_directory(tmp_path: Path) -> None:
    mcb = tmp_path / "sample.mcb"
    data = bytearray(b"\x00" * 256)
    data[:4] = b"MCVL"
    data[4:8] = (1).to_bytes(4, "little")
    data[8:12] = (0x3F800000).to_bytes(4, "little")
    data[12:16] = (20).to_bytes(4, "little")
    rows = [
        (b"NODE", (0, 100, 200, 7)),
        (b"ELEM", (0, 201, 260, 35)),
        (b"MATL", (0, 261, 300, 104)),
    ]
    offset = 20
    for token, values in rows:
        data[offset : offset + 4] = token
        data[offset + 4 : offset + 20] = b"".join(int(value).to_bytes(4, "little") for value in values)
        offset += 20
    mcb.write_bytes(bytes(data))
    report = tmp_path / "mcvl_probe.json"
    proc = subprocess.run(
        [
            "python3",
            "implementation/phase1/parse_midas_binary_meb_to_json_npz.py",
            "--meb",
            str(mcb),
            "--report-out",
            str(report),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["reason_code"] == "PASS_TABLE_DIRECTORY_ONLY"
    assert payload["probe"]["layout_family"] == "MCVL_TABLE_CONTAINER"
    assert payload["probe"]["scaffold_ready"] is True
    assert payload["summary"]["table_entry_count"] == 3
    assert payload["summary"]["in_file_payload_table_count"] == 0
    assert payload["summary"]["layout_family"] == "MCVL_TABLE_CONTAINER"
    assert payload["summary"]["reason_code"] == "PASS_TABLE_DIRECTORY_ONLY"
    assert payload["summary"]["source_member_name"] == "sample.mcb"
    assert payload["summary"]["table_names"][:3] == ["NODE", "ELEM", "MATL"]
    assert payload["summary"]["mcvl_node_elem_probe"]["node"]["range_start"] == 100
    assert payload["summary"]["mcvl_node_elem_probe"]["node"]["range_end"] == 200
    assert payload["summary"]["mcvl_node_elem_probe"]["elem"]["range_start"] == 201
    assert payload["summary"]["mcvl_node_elem_probe"]["elem"]["range_end"] == 260
    assert payload["summary"]["mcvl_node_elem_probe"]["likely_stride_bytes"] == 32


def test_parse_midas_binary_meb_to_json_npz_mcvl_node_hint_probe_points(tmp_path: Path) -> None:
    mcb = tmp_path / "hint_preview.mcb"
    data = bytearray(b"\x00" * 262144)
    data[:4] = b"MCVL"
    data[4:8] = (1).to_bytes(4, "little")
    data[8:12] = (0x3F800000).to_bytes(4, "little")
    data[12:16] = (20).to_bytes(4, "little")
    rows = [
        (b"NODE", (0, 100, 112, 7)),
        (b"ELEM", (0, 220, 260, 35)),
    ]
    offset = 20
    for token, values in rows:
        data[offset : offset + 4] = token
        data[offset + 4 : offset + 20] = b"".join(int(value).to_bytes(4, "little") for value in values)
        offset += 20

    scalar_rows = [
        (100, 1, 212.0),
        (101, 0, 212.9),
        (102, 2, -23.0),
        (103, 3, 217.1),
        (104, 1, -43.0),
        (105, 2, 217.1),
        (106, 0, -19.0),
        (107, 1, 173.0),
        (108, 0, 155.0),
        (109, 3, 263.0),
        (110, 2, 73.0),
        (111, 1, 37.0),
    ]
    for record_index, value_index, value in scalar_rows:
        row_offset = record_index * 32
        doubles = [0.0, 0.0, 0.0, 0.0]
        doubles[value_index] = float(value)
        data[row_offset : row_offset + 32] = __import__("struct").pack("<dddd", *doubles)

    mcb.write_bytes(bytes(data))
    report = tmp_path / "mcvl_hint_preview.json"
    proc = subprocess.run(
        [
            "python3",
            "implementation/phase1/parse_midas_binary_meb_to_json_npz.py",
            "--meb",
            str(mcb),
            "--report-out",
            str(report),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["summary"]["layout_family"] == "MCVL_TABLE_CONTAINER"
    assert payload["summary"]["geometry_preview_ready"] is False
    assert payload["summary"]["geometry_preview_point_count"] >= 4
    assert payload["summary"]["geometry_preview_source_table"] == "NODE/ELEM hinted ranges"
    assert payload["summary"]["geometry_preview_mode"] == "mcvl_node_hint_preview"
    assert payload["geometry_preview"]["mode"] == "mcvl_node_hint_preview"
    assert payload["geometry_preview"]["hint_stride_bytes"] == 32
    assert payload["summary"]["mcvl_hint_preview_probe"]["candidate_point_count"] >= 4
    assert payload["summary"]["geometry_preview_segment_count"] >= 3
    assert payload["summary"]["mcvl_hint_preview_probe"]["candidate_segment_count"] >= 3
    assert payload["summary"]["mcvl_hint_preview_probe"]["topology_grounding_label"] == "record_order_polyline"
    assert payload["geometry_preview"]["topology_grounding_label"] == "record_order_polyline"
    assert "hint preview" in payload["geometry_preview"]["note"]


def test_parse_midas_binary_meb_to_json_npz_raw_xyz_fallback(tmp_path: Path) -> None:
    meb = tmp_path / "raw_xyz.meb"
    data = bytearray(b"\x00" * 262144)
    prefix = b"MBDG\x00\x00__DBMS_DATA__\x00GUID\x00UNIT\x00MATL\x00SECT\x00STOR\x00PONT\x00MEMB"
    data[: len(prefix)] = prefix
    values = [
        (0.0, 200.0, 250.0),
        (200.0, 250.0, 300.0),
        (250.0, 300.0, 200.0),
        (50.0, 150.0, 275.0),
        (75.0, 120.0, 225.0),
        (120.0, 80.0, 210.0),
    ]
    offset = 210432
    for xyz in values:
        data[offset : offset + 24] = __import__("struct").pack("<ddd", *xyz)
        offset += 56
    meb.write_bytes(bytes(data))
    report = tmp_path / "raw_xyz_probe.json"
    proc = subprocess.run(
        [
            "python3",
            "implementation/phase1/parse_midas_binary_meb_to_json_npz.py",
            "--meb",
            str(meb),
            "--report-out",
            str(report),
            "--sample-bytes",
            "32768",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["reason_code"] == "PASS_TABLE_DIRECTORY_ONLY"
    assert payload["summary"]["geometry_preview_ready"] is False
    assert payload["summary"]["geometry_preview_point_count"] >= 6
    assert payload["summary"]["geometry_preview_source_table"] == "raw_f64_xyz_scan"
    assert payload["summary"]["layout_family"] == "MBDG_DB_CONTAINER"
    assert payload["summary"]["geometry_preview_mode"] == "heuristic_xyz_point_scan"
    assert "unverified preview" in payload["geometry_preview"]["note"]


def test_parse_midas_binary_meb_to_json_npz_mcvl_raw_xyz_preview(tmp_path: Path) -> None:
    mcb = tmp_path / "raw_xyz.mcb"
    data = bytearray(b"\x00" * 262144)
    data[:4] = b"MCVL"
    data[4:8] = (1).to_bytes(4, "little")
    data[8:12] = (0x3F800000).to_bytes(4, "little")
    data[12:16] = (20).to_bytes(4, "little")
    rows = [
        (b"NODE", (0, 100, 200, 7)),
        (b"ELEM", (0, 201, 260, 35)),
    ]
    offset = 20
    for token, values in rows:
        data[offset : offset + 4] = token
        data[offset + 4 : offset + 20] = b"".join(int(value).to_bytes(4, "little") for value in values)
        offset += 20
    xyz_offset = 8192
    values = [
        (0.0, 100.0, 50.0),
        (120.0, 140.0, 80.0),
        (160.0, 110.0, 95.0),
        (210.0, 180.0, 130.0),
        (260.0, 190.0, 140.0),
        (320.0, 220.0, 160.0),
        (360.0, 260.0, 180.0),
        (410.0, 280.0, 210.0),
        (470.0, 320.0, 230.0),
        (490.0, 340.0, 250.0),
        (430.0, 210.0, 170.0),
        (390.0, 180.0, 140.0),
    ]
    for xyz in values:
        data[xyz_offset : xyz_offset + 24] = __import__("struct").pack("<ddd", *xyz)
        xyz_offset += 56
    mcb.write_bytes(bytes(data))
    report = tmp_path / "mcvl_raw_xyz_probe.json"
    proc = subprocess.run(
        [
            "python3",
            "implementation/phase1/parse_midas_binary_meb_to_json_npz.py",
            "--meb",
            str(mcb),
            "--report-out",
            str(report),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["reason_code"] == "PASS_TABLE_DIRECTORY_ONLY"
    assert payload["summary"]["geometry_preview_ready"] is False
    assert payload["summary"]["geometry_preview_point_count"] >= 12
    assert payload["summary"]["geometry_preview_source_table"] == "raw_f64_xyz_scan"
    assert payload["summary"]["layout_family"] == "MCVL_TABLE_CONTAINER"
    assert payload["summary"]["geometry_preview_mode"] == "heuristic_xyz_point_scan"
    assert payload["geometry_preview"]["mode"] == "heuristic_xyz_point_scan"
    assert "unverified preview" in payload["geometry_preview"]["note"]


def test_parse_midas_binary_meb_to_json_npz_mcvl_node_hint_preview(tmp_path: Path) -> None:
    mcb = tmp_path / "hinted_node_preview.mcb"
    data = bytearray(b"\x00" * 16384)
    data[:4] = b"MCVL"
    data[4:8] = (1).to_bytes(4, "little")
    data[8:12] = (0x3F800000).to_bytes(4, "little")
    data[12:16] = (20).to_bytes(4, "little")
    rows = [
        (b"NODE", (0, 100, 115, 7)),
        (b"ELEM", (0, 224, 379, 35)),
    ]
    offset = 20
    for token, values in rows:
        data[offset : offset + 4] = token
        data[offset + 4 : offset + 20] = b"".join(int(value).to_bytes(4, "little") for value in values)
        offset += 20

    scalar_values = [
        212.0,
        212.9,
        -23.0,
        217.1,
        -43.0,
        217.1,
        -19.0,
        173.0,
        155.0,
        263.0,
        73.0,
        37.0,
        284.0,
        106.0,
        124.0,
    ]
    value_slots = [1, 0, 2, 3, 1, 2, 0, 1, 0, 3, 2, 1, 0, 3, 2]
    for record_index, (value, slot) in enumerate(zip(scalar_values, value_slots), start=100):
        row_offset = record_index * 32
        doubles = [0.0, 0.0, 0.0, 0.0]
        doubles[slot] = value
        data[row_offset : row_offset + 32] = __import__("struct").pack("<dddd", *doubles)

    mcb.write_bytes(bytes(data))
    report = tmp_path / "mcvl_hint_probe.json"
    proc = subprocess.run(
        [
            "python3",
            "implementation/phase1/parse_midas_binary_meb_to_json_npz.py",
            "--meb",
            str(mcb),
            "--report-out",
            str(report),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["reason_code"] == "PASS_TABLE_DIRECTORY_ONLY"
    assert payload["summary"]["layout_family"] == "MCVL_TABLE_CONTAINER"
    assert payload["summary"]["geometry_preview_ready"] is False
    assert payload["summary"]["geometry_preview_mode"] == "mcvl_node_hint_preview"
    assert payload["summary"]["geometry_preview_source_table"] == "NODE/ELEM hinted ranges"
    assert payload["summary"]["geometry_preview_point_count"] == 5
    assert payload["summary"]["geometry_preview_segment_count"] == 4
    assert payload["summary"]["mcvl_hint_preview_probe"]["candidate_scalar_count"] == 15
    assert payload["summary"]["mcvl_hint_preview_probe"]["candidate_point_count"] == 5
    assert payload["summary"]["mcvl_hint_preview_probe"]["candidate_segment_count"] == 4
    assert payload["summary"]["mcvl_hint_preview_probe"]["topology_grounding_label"] == "record_order_polyline"
    assert payload["summary"]["mcvl_hint_preview_probe"]["phase_scoreboard"][0]["phase"] == 0
    assert payload["summary"]["mcvl_hint_preview_probe"]["selected_phase_record_windows"][0] == [100, 101, 102]
    assert payload["summary"]["mcvl_hint_preview_probe"]["selected_phase_lane_sequences"][0] == [1, 0, 2]
    slot_recovery_probe = payload["summary"]["mcvl_node_xyz_slot_recovery_probe"]
    assert slot_recovery_probe["assembler_label"] == "phase_triplet_plus_lane_anchor_probe"
    assert slot_recovery_probe["candidate_xyz_tuple_count"] == 5
    assert slot_recovery_probe["strong_xyz_tuple_count"] == 4
    assert slot_recovery_probe["partial_xyz_tuple_count"] == 1
    assert slot_recovery_probe["three_lane_tuple_count"] == 4
    assert slot_recovery_probe["recovery_evidence_label"] == "partial_repeatable_slot_recovery"
    assert slot_recovery_probe["exact_xyz_recovery_ready"] is False
    assert slot_recovery_probe["tuple_samples"][0]["quality_label"] == "strong_candidate"
    assert payload["summary"]["mcvl_node_record_probe"]["records_with_1_value"] >= 1
    assert payload["summary"]["mcvl_node_record_probe"]["records_with_3plus_values"] == 0
    assert payload["summary"]["mcvl_node_reassembly_probe"]["best_phase"] == 0
    assert payload["summary"]["mcvl_node_reassembly_probe"]["candidate_triplet_count"] == 5
    assert payload["summary"]["mcvl_node_reassembly_probe"]["cross_record_triplet_count"] == 5
    assert payload["summary"]["mcvl_node_reassembly_probe"]["best_lane_sequence"] == [1, 0, 2]
    assert payload["summary"]["mcvl_node_reassembly_probe"]["supports_cross_record_xyz_hypothesis"] is True
    assert payload["summary"]["mcvl_node_scalar_lane_probe"]["records_scanned"] == 15
    assert payload["summary"]["mcvl_node_scalar_lane_probe"]["active_scalar_record_count"] == 15
    assert payload["summary"]["mcvl_node_scalar_lane_probe"]["single_scalar_record_count"] == 15
    assert payload["summary"]["mcvl_node_scalar_lane_probe"]["multi_scalar_record_count"] == 0
    assert payload["summary"]["mcvl_node_scalar_lane_probe"]["scalar_lane_counts"] == [4, 4, 4, 3]
    assert payload["summary"]["mcvl_node_scalar_lane_probe"]["likely_scalar_lane_indices"] == [0, 1, 2, 3]
    assert payload["summary"]["mcvl_node_scalar_lane_probe"]["dominant_scalar_lane_patterns"][0]["record_count"] == 4
    assert len(payload["summary"]["mcvl_node_scalar_lane_probe"]["companion_small_uint_slot_hits"]) == 4
    assert isinstance(payload["summary"]["mcvl_node_scalar_lane_probe"]["likely_scalar_anchor_slots"], list)
    assert payload["summary"]["mcvl_node_uint_layout_probe"]["records_scanned"] == 15
    assert payload["summary"]["mcvl_node_uint_layout_probe"]["record_range"] == [100, 115]
    assert max(payload["summary"]["mcvl_node_uint_layout_probe"]["nonzero_slot_counts"]) >= 1
    assert payload["summary"]["mcvl_node_uint_layout_probe"]["layout_state_label"] in {"mixed_sparse_uint_fields", "sparse_identifier_candidate", "constant_fill_dominant"}
    assert isinstance(payload["summary"]["mcvl_node_uint_layout_probe"]["small_uint_slot_minmax"], list)
    assert isinstance(payload["summary"]["mcvl_node_uint_layout_probe"]["slot_pattern_probe"], list)
    assert isinstance(payload["summary"]["mcvl_node_uint_layout_probe"]["slot_progression_probe"], list)
    assert len(payload["summary"]["mcvl_node_uint_layout_probe"]["slot_progression_probe"]) == 8
    assert isinstance(payload["summary"]["mcvl_node_uint_layout_probe"]["likely_counter_slots"], list)
    assert isinstance(payload["summary"]["mcvl_node_uint_layout_probe"]["adjacent_slot_pair_probe"], list)
    assert len(payload["summary"]["mcvl_node_uint_layout_probe"]["adjacent_slot_pair_probe"]) == 7
    assert isinstance(payload["summary"]["mcvl_node_uint_layout_probe"]["likely_packed_identifier_pairs"], list)
    assert "node_range" in payload["summary"]["mcvl_node_uint_layout_probe"]["reference_slot_hits"]
    assert payload["summary"]["mcvl_elem_uint_layout_probe"]["records_scanned"] == 155
    assert payload["summary"]["mcvl_elem_uint_layout_probe"]["record_range"] == [224, 379]
    assert payload["summary"]["mcvl_elem_uint_layout_probe"]["dominant_record_ratio"] == 1.0
    assert payload["summary"]["mcvl_elem_uint_layout_probe"]["layout_state_label"] == "constant_fill_dominant"
    assert len(payload["summary"]["mcvl_elem_uint_layout_probe"]["slot_progression_probe"]) == 8
    assert len(payload["summary"]["mcvl_elem_uint_layout_probe"]["adjacent_slot_pair_probe"]) == 7
    assert payload["geometry_preview"]["mode"] == "mcvl_node_hint_preview"
    assert payload["geometry_preview"]["source_table"] == "NODE/ELEM hinted ranges"
    assert payload["geometry_preview"]["hint_grouping_phase"] == 0
    assert payload["geometry_preview"]["candidate_segment_count"] == 4
    assert payload["geometry_preview"]["topology_grounding_label"] == "record_order_polyline"
    assert payload["geometry_preview"]["node_xyz_recovery_label"] == "partial_repeatable_slot_recovery"
    assert payload["geometry_preview"]["node_xyz_recovery_ready"] is False
    assert payload["geometry_preview"]["node_xyz_strong_tuple_count"] == 4
    assert payload["geometry_preview"]["node_xyz_tuple_count"] == 5
    assert "hint preview" in payload["geometry_preview"]["note"]


def test_parse_midas_binary_meb_to_json_npz_mcvl_elem_fill_probe(tmp_path: Path) -> None:
    mcb = tmp_path / "elem_fill_probe.mcb"
    data = bytearray(b"\x00" * 16384)
    data[:4] = b"MCVL"
    data[4:8] = (1).to_bytes(4, "little")
    data[8:12] = (0x3F800000).to_bytes(4, "little")
    data[12:16] = (20).to_bytes(4, "little")
    rows = [
        (b"NODE", (0, 100, 102, 7)),
        (b"ELEM", (0, 200, 206, 35)),
    ]
    offset = 20
    for token, values in rows:
        data[offset : offset + 4] = token
        data[offset + 4 : offset + 20] = b"".join(int(value).to_bytes(4, "little") for value in values)
        offset += 20

    data[100 * 32 : 100 * 32 + 32] = __import__("struct").pack("<dddd", 10.0, 0.0, 0.0, 0.0)
    data[101 * 32 : 101 * 32 + 32] = __import__("struct").pack("<dddd", 0.0, 20.0, 0.0, 0.0)

    for record_index in (200, 201, 202):
        data[record_index * 32 : record_index * 32 + 32] = b" " * 32
    data[205 * 32 : 205 * 32 + 32] = (b" " * 16) + (1).to_bytes(4, "little") + (b"\x00" * 12)

    mcb.write_bytes(bytes(data))
    _, payload = decode_meb_inventory(mcb)

    elem_probe = payload["summary"]["mcvl_elem_uint_layout_probe"]
    assert elem_probe["records_scanned"] == 6
    assert elem_probe["zero_record_count"] == 2
    assert elem_probe["constant_fill_record_count"] == 5
    assert elem_probe["nonzero_constant_fill_record_count"] == 3
    assert elem_probe["space_fill_record_count"] == 3
    assert elem_probe["nonfill_nonzero_record_count"] == 1
    assert elem_probe["dominant_fill_byte_hex"] == "0x20"
    assert elem_probe["dominant_fill_byte_ascii"] == " "
    assert elem_probe["dominant_nonzero_fill_byte_hex"] == "0x20"
    assert elem_probe["dominant_nonzero_fill_byte_ascii"] == " "
    assert "0x20-filled" in elem_probe["note"]


def test_parse_midas_binary_meb_to_json_npz_mcvl_record_topology_preview(tmp_path: Path) -> None:
    mcb = tmp_path / "record_topology.mcb"
    data = bytearray(b"\x00" * 16384)
    data[:4] = b"MCVL"
    data[4:8] = (1).to_bytes(4, "little")
    data[8:12] = (0x3F800000).to_bytes(4, "little")
    data[12:16] = (20).to_bytes(4, "little")
    rows = [
        (b"NODE", (0, 100, 104, 7)),
        (b"ELEM", (0, 200, 203, 35)),
    ]
    offset = 20
    for token, values in rows:
        data[offset : offset + 4] = token
        data[offset + 4 : offset + 20] = b"".join(int(value).to_bytes(4, "little") for value in values)
        offset += 20

    node_rows = {
        100: (0.0, 0.0, 0.0, 0.0),
        101: (10.0, 0.0, 0.0, 0.0),
        102: (10.0, 5.0, 0.0, 0.0),
        103: (15.0, 5.0, 2.0, 0.0),
    }
    for record_index, xyz in node_rows.items():
        row_offset = record_index * 32
        data[row_offset : row_offset + 32] = __import__("struct").pack("<dddd", *xyz)

    elem_rows = {
        200: (100, 101, 0, 0, 0, 0, 0, 0),
        201: (101, 102, 0, 0, 0, 0, 0, 0),
        202: (102, 103, 0, 0, 0, 0, 0, 0),
    }
    for record_index, refs in elem_rows.items():
        row_offset = record_index * 32
        data[row_offset : row_offset + 32] = __import__("struct").pack("<IIIIIIII", *refs)

    mcb.write_bytes(bytes(data))
    report = tmp_path / "mcvl_record_topology.json"
    proc = subprocess.run(
        [
            "python3",
            "implementation/phase1/parse_midas_binary_meb_to_json_npz.py",
            "--meb",
            str(mcb),
            "--report-out",
            str(report),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["reason_code"] == "PASS_TABLE_DIRECTORY_ONLY"
    assert payload["summary"]["geometry_preview_mode"] == "mcvl_record_topology_preview"
    assert payload["summary"]["geometry_preview_source_table"] == "NODE/ELEM decoded records"
    assert payload["summary"]["geometry_preview_point_count"] == 4
    assert payload["summary"]["geometry_preview_segment_count"] == 3
    assert payload["summary"]["mcvl_exact_topology_probe"]["candidate_point_count"] == 4
    assert payload["summary"]["mcvl_exact_topology_probe"]["candidate_segment_count"] == 3
    assert payload["summary"]["mcvl_exact_topology_probe"]["topology_grounding_label"] == "record_local_node_elem_paths"
    assert payload["geometry_preview"]["mode"] == "mcvl_record_topology_preview"
    assert payload["geometry_preview"]["topology_preview_ready"] is True
    assert payload["geometry_preview"]["topology_readiness_label"] == "record-grounded NODE/ELEM topology preview"
    assert payload["geometry_preview"]["resolved_member_reference_rate"] == 1.0
    assert payload["geometry_preview"]["candidate_elem_reference_slots"][0]["slot"] == 0


def test_parse_midas_binary_meb_to_json_npz_beam_archive_mcvl_evidence_regression() -> None:
    beam_path = Path(
        "implementation/phase1/open_data/midas/quality_corpus/extracted/midas_support_beam_archive/FCM Bridge.mcb"
    )
    assert beam_path.exists()

    _, payload = decode_meb_inventory(beam_path)
    summary = payload["summary"]

    assert summary["layout_family"] == "MCVL_TABLE_CONTAINER"
    assert summary["geometry_preview_mode"] == "mcvl_node_hint_preview"
    assert summary["geometry_preview_point_count"] == 5

    node_scalar_probe = summary["mcvl_node_scalar_lane_probe"]
    assert node_scalar_probe["records_scanned"] == 160
    assert node_scalar_probe["active_scalar_record_count"] == 14
    assert node_scalar_probe["single_scalar_record_count"] == 13
    assert node_scalar_probe["multi_scalar_record_count"] == 1
    assert node_scalar_probe["scalar_lane_counts"] == [4, 4, 4, 3]
    assert node_scalar_probe["dominant_scalar_lane_patterns"][:3] == [
        {"lanes": [1], "record_count": 4},
        {"lanes": [0], "record_count": 3},
        {"lanes": [2], "record_count": 3},
    ]
    assert node_scalar_probe["likely_scalar_anchor_slots"][:4] == [
        {"lane": 0, "total_hits": 4, "dominant_slots": [{"slot": 6, "hit_count": 3}, {"slot": 2, "hit_count": 1}], "dominant_slot_confidence": 0.75},
        {"lane": 1, "total_hits": 5, "dominant_slots": [{"slot": 1, "hit_count": 3}, {"slot": 4, "hit_count": 1}, {"slot": 5, "hit_count": 1}], "dominant_slot_confidence": 0.6},
        {"lane": 2, "total_hits": 4, "dominant_slots": [{"slot": 3, "hit_count": 3}, {"slot": 6, "hit_count": 1}], "dominant_slot_confidence": 0.75},
        {"lane": 3, "total_hits": 3, "dominant_slots": [{"slot": 5, "hit_count": 3}], "dominant_slot_confidence": 1.0},
    ]

    hint_probe = summary["mcvl_hint_preview_probe"]
    assert hint_probe["phase_scoreboard"] == [
        {"phase": 0, "point_count": 5, "segment_count": 4, "projection_label": "XY", "score": 387688.5},
        {"phase": 1, "point_count": 4, "segment_count": 3, "projection_label": "XZ", "score": 310150.8},
        {"phase": 2, "point_count": 4, "segment_count": 3, "projection_label": "XY", "score": 291001.2},
    ]
    assert hint_probe["selected_phase_record_windows"][:3] == [
        [951, 953, 953],
        [954, 955, 956],
        [957, 958, 960],
    ]
    assert hint_probe["selected_phase_lane_sequences"][:3] == [
        [1, 0, 2],
        [3, 1, 2],
        [0, 1, 0],
    ]
    reassembly_probe = summary["mcvl_node_reassembly_probe"]
    assert reassembly_probe["best_phase"] == 0
    assert reassembly_probe["candidate_triplet_count"] == 5
    assert reassembly_probe["cross_record_triplet_count"] == 5
    assert reassembly_probe["cross_record_triplet_ratio"] == 1.0
    assert reassembly_probe["best_lane_sequence"] == [1, 0, 2]
    assert reassembly_probe["best_record_window"] == [951, 953, 953]
    assert reassembly_probe["supports_cross_record_xyz_hypothesis"] is True
    slot_recovery_probe = summary["mcvl_node_xyz_slot_recovery_probe"]
    assert slot_recovery_probe["assembler_label"] == "phase_triplet_plus_lane_anchor_probe"
    assert slot_recovery_probe["candidate_xyz_tuple_count"] == 5
    assert slot_recovery_probe["strong_xyz_tuple_count"] == 4
    assert slot_recovery_probe["partial_xyz_tuple_count"] == 1
    assert slot_recovery_probe["three_lane_tuple_count"] == 4
    assert slot_recovery_probe["repeated_lane_tuple_count"] == 1
    assert slot_recovery_probe["tight_window_tuple_count"] == 4
    assert slot_recovery_probe["stable_anchor_lane_count"] == 3
    assert slot_recovery_probe["recovery_evidence_label"] == "partial_repeatable_slot_recovery"
    assert slot_recovery_probe["exact_xyz_recovery_ready"] is False
    assert slot_recovery_probe["tuple_samples"][1]["record_window"] == [954, 955, 956]
    assert slot_recovery_probe["tuple_samples"][2]["quality_label"] == "partial_candidate"

    elem_probe = summary["mcvl_elem_uint_layout_probe"]
    assert elem_probe["records_scanned"] == 155
    assert elem_probe["zero_record_count"] == 108
    assert elem_probe["constant_fill_record_count"] == 154
    assert elem_probe["nonzero_constant_fill_record_count"] == 46
    assert elem_probe["space_fill_record_count"] == 46
    assert elem_probe["nonfill_nonzero_record_count"] == 1
    assert elem_probe["dominant_fill_byte_hex"] == "0x00"
    assert elem_probe["dominant_nonzero_fill_byte_hex"] == "0x20"
    assert elem_probe["dominant_nonzero_fill_byte_ascii"] == " "
    assert payload["geometry_preview"]["node_xyz_recovery_label"] == "partial_repeatable_slot_recovery"
    assert payload["geometry_preview"]["node_xyz_recovery_ready"] is False
    assert payload["geometry_preview"]["node_xyz_strong_tuple_count"] == 4
    assert payload["geometry_preview"]["node_xyz_tuple_count"] == 5


def test_parse_midas_binary_meb_to_json_npz_sparse_local_xyz_preview(tmp_path: Path) -> None:
    meb = tmp_path / "sparse_local.mmbx"
    data = bytearray(b"\x00" * 262144)
    prefix = b"MBDG\x00\x00__DBMS_DATA__\x00GUID\x00UNIT\x00MATL\x00SECT\x00STOR\x00MEMB\x00"
    data[: len(prefix)] = prefix
    # No xVPNT payload; only a sparse local xyz cluster in a later window.
    window_offset = 172032
    values = [
        (0.03, 0.03, 0.0),
        (0.3, 0.3, 0.03),
        (0.3, 0.03, 0.02),
        (0.03, 0.02, 0.0),
    ]
    for xyz in values:
        data[window_offset : window_offset + 24] = __import__("struct").pack("<ddd", *xyz)
        window_offset += 96
    meb.write_bytes(bytes(data))
    report = tmp_path / "sparse_local_probe.json"
    proc = subprocess.run(
        [
            "python3",
            "implementation/phase1/parse_midas_binary_meb_to_json_npz.py",
            "--meb",
            str(meb),
            "--report-out",
            str(report),
            "--sample-bytes",
            "32768",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["reason_code"] == "PASS_TABLE_DIRECTORY_ONLY"
    assert payload["summary"]["geometry_preview_ready"] is False
    assert payload["summary"]["geometry_preview_mode"] == "sparse_local_xyz_point_scan"
    assert payload["summary"]["geometry_preview_source_table"] == "windowed_f64_xyz_scan"
    assert payload["summary"]["geometry_preview_point_count"] >= 4
    assert payload["geometry_preview"]["projection_label"] in {"XY", "XZ", "YZ"}
    assert payload["geometry_preview"]["window_start_byte"] >= 65536
    assert "sparse preview" in payload["geometry_preview"]["note"]


def test_parse_midas_binary_meb_to_json_npz_table_local_ascii_block_stops_at_next_section(tmp_path: Path) -> None:
    meb = tmp_path / "ascii_block_boundary.mmbx"
    prefix = b"MBDG\x00\x00__DBMS_DATA__\x00GUID\x00UNIT\x00MATL\x00SECT\x00STOR\x00MEMB\x00"
    ascii_payload = (
        "*POINT\n"
        "  1, 5, 0, 0, 3.5, 2\n"
        "  2, 3, 0, -7.2, 3.5, 2\n"
        "  3, 1, 0, -13.2, 3.5, 2\n"
        "  4, 9, 4.5, -13.2, 4, 2\n"
        "*LOAD\n"
        "  1, 1, 28, 99, 100, 101\n"
        "  2, 2, 29, 99, 100, 101\n"
    ).encode("latin-1")
    meb.write_bytes(prefix + (b"\x00" * 128) + ascii_payload)
    report = tmp_path / "ascii_block_boundary.json"
    proc = subprocess.run(
        [
            "python3",
            "implementation/phase1/parse_midas_binary_meb_to_json_npz.py",
            "--meb",
            str(meb),
            "--report-out",
            str(report),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["summary"]["geometry_preview_mode"] == "table_local_ascii_preview"
    assert payload["summary"]["geometry_preview_source_table"] == "ASCII:PONT/CURV/MEMB:*POINT/*MEMBER_ADD"
    preview_points = payload["geometry_preview"]["candidate_points_xyz"]
    assert preview_points[:4] == [
        [0.0, 0.0, 3.5],
        [0.0, -7.2, 3.5],
        [0.0, -13.2, 3.5],
        [4.5, -13.2, 4.0],
    ]


def test_parse_midas_binary_meb_to_json_npz_table_local_ascii_preview(tmp_path: Path) -> None:
    mmbx = tmp_path / "table_local_ascii.mmbx"
    data = bytearray(b"\x00" * 65536)
    prefix = b"MBDG\x00\x00__DBMS_DATA__\x00GUID\x00UNIT\x00MATL\x00SECT\x00STOR\x00PONT\x00CURV\x00MEMB\x00"
    data[: len(prefix)] = prefix
    ascii_block = (
        "*POINT\n"
        "  1, 5, 0, 0, 3.5, 2\n"
        "  2, 3, 0, -7.2, 3.5, 2\n"
        "  3, 1, 0, -13.2, 3.5, 2\n"
        "  4, 9, 4.5, -13.2, 4, 2\n"
        "  5, 14, 4.5, -7.2, 4, 2\n"
        "  6, 19, 4.5, 0, 4, 2\n"
        "*MEMBER_ADD\n"
        "  1, 2\n"
        "  1, 2\n"
        "  2, 4\n"
        "  2, 3, 4, 5\n"
        "  3, 2\n"
        "  5, 6\n"
        "*LOAD\n"
        "  999, 1, 5000, 5000, 5000\n"
        "  1000, 1, -6000, 6000, 7000\n"
    ).encode("ascii")
    data[24000 : 24000 + len(ascii_block)] = ascii_block
    mmbx.write_bytes(bytes(data))
    report = tmp_path / "table_local_ascii_probe.json"
    proc = subprocess.run(
        [
            "python3",
            "implementation/phase1/parse_midas_binary_meb_to_json_npz.py",
            "--meb",
            str(mmbx),
            "--report-out",
            str(report),
            "--sample-bytes",
            "32768",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["reason_code"] == "PASS_TABLE_DIRECTORY_ONLY"
    assert payload["summary"]["geometry_preview_ready"] is False
    assert payload["summary"]["geometry_preview_mode"] == "table_local_ascii_preview"
    assert payload["summary"]["geometry_preview_source_table"] == "ASCII:PONT/CURV/MEMB:*POINT/*MEMBER_ADD"
    assert payload["summary"]["geometry_preview_point_count"] == 6
    assert payload["summary"]["geometry_preview_segment_count"] >= 4
    assert payload["summary"]["table_local_preview_probe"]["candidate_point_count"] >= 6
    assert payload["summary"]["table_local_preview_probe"]["candidate_segment_count"] >= 4
    assert payload["summary"]["table_local_preview_probe"]["anchor_table_names"] == ["PONT", "CURV", "MEMB", "*POINT", "*MEMBER_ADD"]
    assert payload["summary"]["table_local_preview_probe"]["member_path_count"] == 3
    assert payload["summary"]["table_local_preview_probe"]["resolved_member_path_count"] == 3
    assert payload["summary"]["table_local_preview_probe"]["missing_member_path_count"] == 0
    assert payload["summary"]["table_local_preview_probe"]["member_path_resolution_rate"] == 1.0
    assert payload["summary"]["table_local_preview_probe"]["member_reference_count"] == 8
    assert payload["summary"]["table_local_preview_probe"]["resolved_member_reference_count"] == 8
    assert payload["summary"]["table_local_preview_probe"]["missing_member_reference_count"] == 0
    assert payload["summary"]["table_local_preview_probe"]["member_reference_resolution_rate"] == 1.0
    assert payload["summary"]["table_local_preview_probe"]["payload_exact_topology_ready"] is True
    assert payload["summary"]["table_local_preview_probe"]["payload_exactness_label"] == "payload-exact member-add topology preview"
    assert payload["summary"]["table_local_preview_probe"]["topology_grounding_label"] == "explicit_member_add_paths"
    assert payload["summary"]["table_local_preview_probe"]["topology_preview_ready"] is True
    assert payload["summary"]["table_local_preview_probe"]["topology_readiness_label"] == "payload-exact member-add topology preview"
    assert payload["summary"]["table_local_preview_probe"]["topology_node_count"] == 6
    assert payload["summary"]["table_local_preview_probe"]["topology_edge_count"] == 5
    assert payload["summary"]["table_local_preview_probe"]["topology_component_count"] == 1
    assert payload["summary"]["table_local_preview_probe"]["dangling_point_count"] == 2
    assert payload["summary"]["table_local_preview_probe"]["junction_point_count"] == 0
    assert payload["summary"]["table_local_preview_probe"]["isolated_preview_point_count"] == 0
    assert payload["summary"]["topology_preview_ready"] is True
    assert payload["summary"]["table_local_preview_probe"]["resolved_member_path_samples"][0] == [1, 2]
    assert payload["geometry_preview"]["mode"] == "table_local_ascii_preview"
    assert payload["geometry_preview"]["member_path_count"] == 3
    assert payload["geometry_preview"]["resolved_member_path_count"] == 3
    assert payload["geometry_preview"]["payload_exact_topology_ready"] is True
    assert payload["geometry_preview"]["payload_exactness_label"] == "payload-exact member-add topology preview"
    assert payload["geometry_preview"]["topology_preview_ready"] is True
    assert payload["geometry_preview"]["topology_readiness_label"] == "payload-exact member-add topology preview"
    assert payload["geometry_preview"]["topology_edge_count"] == 5
    assert payload["geometry_preview"]["projection_label"] in {"XY", "XZ", "YZ"}
    assert "table-local" in payload["geometry_preview"]["note"]


def test_parse_midas_binary_meb_to_json_npz_table_local_ascii_preview_prefers_directory_window(tmp_path: Path) -> None:
    meb = tmp_path / "ramp_like_ascii_local.meb"
    data = bytearray(b"\x00" * 300000)
    prefix = b"MBDG\x00\x00__DBMS_DATA__\x00GUID\x00UNIT\x00MATL\x00SECT\x00STOR\x00PONT\x00CURV\x00MEMB\x00"
    data[: len(prefix)] = prefix

    # Directory entries point nowhere useful, but do establish local anchor positions.
    table_rows = [
        (b"PONT\x00\x00\x00\x00", 14092638, 0, 0),
        (b"CURV\x00\x00\x00\x00", 14092546, 0, 0),
        (b"MEMB\x00\x00\x00\x00", 14092597, 0, 0),
    ]
    directory_offset = 156737
    for token, word1, word2, word3 in table_rows:
        data[directory_offset : directory_offset + 8] = token
        data[directory_offset + 8 : directory_offset + 20] = (
            int(word1).to_bytes(4, "little")
            + int(word2).to_bytes(4, "little")
            + int(word3).to_bytes(4, "little")
        )
        directory_offset += 20

    # Earlier global *POINT marker is intentionally incomplete, so whole-file first-hit search alone is insufficient.
    broken_ascii = (
        "*POINT\n"
        "  1, 5, 0\n"
        "  2, 3, 0\n"
        "*LOAD\n"
    ).encode("ascii")
    data[32000 : 32000 + len(broken_ascii)] = broken_ascii

    local_ascii = (
        "*MEMBER_ADD\n"
        "  1, 2\n"
        "  1, 2\n"
        "  2, 2\n"
        "  2, 3\n"
        "*POINT\n"
        "  1, 5, 0, 0, 3.5, 2\n"
        "  2, 3, 0, -7.2, 3.5, 2\n"
        "  3, 1, 0, -13.2, 3.5, 2\n"
        "  4, 9, 4.5, -13.2, 4, 2\n"
        "*LOAD\n"
    ).encode("ascii")
    data[271500 : 271500 + len(local_ascii)] = local_ascii
    meb.write_bytes(bytes(data))

    report = tmp_path / "ramp_like_ascii_local.json"
    proc = subprocess.run(
        [
            "python3",
            "implementation/phase1/parse_midas_binary_meb_to_json_npz.py",
            "--meb",
            str(meb),
            "--report-out",
            str(report),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["summary"]["geometry_preview_ready"] is False
    assert payload["summary"]["geometry_preview_mode"] == "table_local_ascii_preview"
    assert payload["summary"]["geometry_preview_source_table"] == "ASCII:PONT/CURV/MEMB:*POINT/*MEMBER_ADD"
    assert payload["summary"]["geometry_preview_point_count"] == 4
    assert payload["summary"]["table_local_preview_probe"]["anchor_table_names"] == ["PONT", "CURV", "MEMB", "*POINT", "*MEMBER_ADD"]
    assert payload["summary"]["table_local_preview_probe"]["anchor_directory_position"] == 156737
    assert payload["summary"]["table_local_preview_probe"]["window_start_byte"] >= 271500
    assert payload["summary"]["table_local_preview_probe"]["payload_exact_topology_ready"] is True
    assert payload["summary"]["table_local_preview_probe"]["payload_exactness_label"] == "payload-exact member-add topology preview"
    assert payload["summary"]["table_local_preview_probe"]["topology_grounding_label"] == "explicit_member_add_paths"
    assert payload["summary"]["table_local_preview_probe"]["topology_preview_ready"] is False
    assert payload["summary"]["table_local_preview_probe"]["topology_readiness_label"] == "table-local preview"
    assert payload["summary"]["table_local_preview_probe"]["topology_node_count"] == 3
    assert payload["summary"]["table_local_preview_probe"]["topology_edge_count"] == 2
    assert payload["summary"]["table_local_preview_probe"]["isolated_preview_point_count"] == 1
    assert payload["summary"]["topology_preview_ready"] is False
    assert payload["geometry_preview"]["mode"] == "table_local_ascii_preview"
    assert payload["geometry_preview"]["source_table"] == "ASCII:PONT/CURV/MEMB:*POINT/*MEMBER_ADD"
    assert payload["geometry_preview"]["payload_exact_topology_ready"] is True
    assert payload["geometry_preview"]["payload_exactness_label"] == "payload-exact member-add topology preview"
    assert "directory_position" in payload["geometry_preview"]["note"]
