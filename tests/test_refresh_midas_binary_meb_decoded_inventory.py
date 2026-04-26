from __future__ import annotations

import json
from pathlib import Path
import struct

import implementation.phase1.refresh_midas_binary_meb_decoded_inventory as refresh_mod
from implementation.phase1.refresh_midas_binary_meb_decoded_inventory import refresh_source


def _write_fake_meb(path: Path, *, with_preview: bool) -> None:
    data = bytearray(b"\x00" * 4096)
    prefix = b"MBDG\0__DBMS_DATA__\0GUID\0xUNIT\0xMATL\0xSECT\0xSTOR\0"
    data[: len(prefix)] = prefix

    directory_pos = 256
    payload_pos = 1024
    table_name = b"xVPNT\x00\x00\x00"
    data[directory_pos : directory_pos + 8] = table_name
    data[directory_pos + 8 : directory_pos + 20] = struct.pack("<III", payload_pos, 0, 0)

    if with_preview:
        payload_values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0]
    else:
        payload_values = [0.0, 0.0, 0.0, 0.0]
    payload = struct.pack("<" + "d" * len(payload_values), *payload_values)
    data[payload_pos : payload_pos + len(payload)] = payload
    path.write_bytes(bytes(data))


def _write_fake_mcb(path: Path, *, table_count: int) -> None:
    data = bytearray(b"\x00" * 512)
    data[:4] = b"MCVL"
    data[4:8] = struct.pack("<I", 1)
    data[8:12] = struct.pack("<I", 0x3F800000)
    data[12:16] = struct.pack("<I", 20)
    offset = 20
    tokens = [b"NODE", b"ELEM", b"MATL", b"SECT", b"GRUP", b"ELNK"]
    for index in range(table_count):
        token = tokens[index % len(tokens)]
        data[offset : offset + 4] = token
        data[offset + 4 : offset + 20] = struct.pack("<IIII", 0, 100 + index, 200 + index, 7 + index)
        offset += 20
    path.write_bytes(bytes(data))


def test_refresh_source_selects_best_meb(tmp_path: Path) -> None:
    source_dir = tmp_path / "midas_support_fake_archive"
    source_dir.mkdir(parents=True)
    adapter_manifest = {
        "source_id": "midas_support_fake_archive",
        "summary": {
            "recommended_primary_member": "weak.meb",
            "recommended_adapter_family": "midas_binary_meb_parser",
        },
    }
    (source_dir / "adapter_manifest.json").write_text(json.dumps(adapter_manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    _write_fake_meb(source_dir / "weak.meb", with_preview=False)
    _write_fake_meb(source_dir / "strong_preview.meb", with_preview=True)

    payload = refresh_source(source_dir)

    assert payload["selected_member_name"] == "strong_preview.meb"
    assert payload["selected_reason_code"] == "PASS_HEURISTIC_GEOMETRY_PREVIEW_READY"
    assert (source_dir / "meb_decoded_inventory.json").exists()
    assert (source_dir / "meb_decoded_inventory.npz").exists()
    assert (source_dir / "meb_decoded_inventory_report.json").exists()
    assert (source_dir / "meb_inventory_refresh_report.json").exists()

    report_payload = json.loads((source_dir / "meb_decoded_inventory_report.json").read_text(encoding="utf-8"))
    assert report_payload["summary"]["geometry_preview_ready"] is True
    assert report_payload["summary"]["geometry_preview_source_table"] == "xVPNT"
    assert len(payload["evaluations"]) == 2
    assert payload["selected_preview_quality"]["label"] == "verified preview"
    assert payload["selected_selection_basis"].startswith("verified preview |")


def test_refresh_source_supports_mmbx_candidates(tmp_path: Path) -> None:
    source_dir = tmp_path / "midas_support_fake_mmbx_archive"
    source_dir.mkdir(parents=True)
    adapter_manifest = {
        "source_id": "midas_support_fake_mmbx_archive",
        "summary": {
            "recommended_primary_member": "candidate_a.mmbx",
            "recommended_adapter_family": "midas_binary_mmbx_parser",
        },
    }
    (source_dir / "adapter_manifest.json").write_text(json.dumps(adapter_manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    _write_fake_meb(source_dir / "candidate_a.mmbx", with_preview=False)
    _write_fake_meb(source_dir / "candidate_b.mmbx", with_preview=True)

    payload = refresh_source(source_dir)

    assert payload["selected_member_name"] == "candidate_b.mmbx"
    assert payload["selected_reason_code"] == "PASS_HEURISTIC_GEOMETRY_PREVIEW_READY"
    assert len(payload["evaluations"]) == 2


def test_refresh_source_supports_mcb_candidates(tmp_path: Path) -> None:
    source_dir = tmp_path / "midas_support_fake_mcb_archive"
    source_dir.mkdir(parents=True)
    adapter_manifest = {
        "source_id": "midas_support_fake_mcb_archive",
        "summary": {
            "recommended_primary_member": "candidate_a.mcb",
            "recommended_adapter_family": "midas_binary_mcb_parser",
        },
    }
    (source_dir / "adapter_manifest.json").write_text(json.dumps(adapter_manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    _write_fake_mcb(source_dir / "candidate_a.mcb", table_count=2)
    _write_fake_mcb(source_dir / "candidate_b.mcb", table_count=5)

    payload = refresh_source(source_dir)

    assert payload["selected_member_name"] == "candidate_b.mcb"
    assert payload["selected_reason_code"] == "PASS_TABLE_DIRECTORY_ONLY"
    assert len(payload["evaluations"]) == 2
    selected_row = next(row for row in payload["evaluations"] if row["member_name"] == "candidate_b.mcb")
    assert selected_row["mcvl_node_layout_state_label"] in {
        "",
        "mixed_sparse_uint_fields",
        "sparse_identifier_candidate",
        "constant_fill_dominant",
    }
    assert isinstance(selected_row["mcvl_node_likely_identifier_slots"], list)
    assert isinstance(selected_row["mcvl_node_likely_counter_slots"], list)
    assert isinstance(selected_row["mcvl_node_likely_packed_identifier_pairs"], list)
    report_payload = json.loads((source_dir / "meb_decoded_inventory_report.json").read_text(encoding="utf-8"))
    assert report_payload["probe"]["layout_family"] == "MCVL_TABLE_CONTAINER"
    assert report_payload["summary"]["table_entry_count"] == 5


def test_refresh_source_prefers_candidate_with_unverified_preview_points(tmp_path: Path) -> None:
    source_dir = tmp_path / "midas_support_fake_sparse_preview_archive"
    source_dir.mkdir(parents=True)
    adapter_manifest = {
        "source_id": "midas_support_fake_sparse_preview_archive",
        "summary": {
            "recommended_primary_member": "inventory_only.mmbx",
            "recommended_adapter_family": "midas_binary_mmbx_parser",
        },
    }
    (source_dir / "adapter_manifest.json").write_text(json.dumps(adapter_manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    _write_fake_meb(source_dir / "inventory_only.mmbx", with_preview=False)

    sparse_preview = bytearray(b"\x00" * 262144)
    prefix = b"MBDG\x00\x00__DBMS_DATA__\x00GUID\x00UNIT\x00MATL\x00SECT\x00STOR\x00MEMB\x00"
    sparse_preview[: len(prefix)] = prefix
    offset = 172032
    for xyz in [(0.03, 0.03, 0.0), (0.3, 0.3, 0.03), (0.3, 0.03, 0.02), (0.03, 0.02, 0.0)]:
        sparse_preview[offset : offset + 24] = struct.pack("<ddd", *xyz)
        offset += 96
    (source_dir / "sparse_preview.mmbx").write_bytes(bytes(sparse_preview))

    payload = refresh_source(source_dir)

    assert payload["selected_member_name"] == "sparse_preview.mmbx"
    assert payload["selected_preview_quality"]["label"] == "table-local preview"
    assert payload["selected_selection_basis"].startswith("table-local preview |")
    assert len(payload["evaluations"]) == 2
    picked = next(row for row in payload["evaluations"] if row["member_name"] == "sparse_preview.mmbx")
    assert picked["geometry_preview_point_count"] >= 4
    assert picked["geometry_preview_mode"] == "sparse_local_xyz_point_scan"
    assert picked["preview_quality_label"] == "table-local preview"
    assert picked["selection_basis"].startswith("table-local preview |")


def test_refresh_source_selection_priority_prefers_table_local_over_hint_and_raw(tmp_path: Path, monkeypatch) -> None:
    source_dir = tmp_path / "midas_support_priority_archive"
    source_dir.mkdir(parents=True)
    adapter_manifest = {
        "source_id": "midas_support_priority_archive",
        "summary": {
            "recommended_primary_member": "inventory_only.mmbx",
            "recommended_adapter_family": "midas_binary_mmbx_parser",
        },
    }
    (source_dir / "adapter_manifest.json").write_text(json.dumps(adapter_manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    member_names = [
        "inventory_only.mmbx",
        "raw_preview.mmbx",
        "hint_preview.mcb",
        "table_local_preview.mmbx",
    ]
    for member_name in member_names:
        (source_dir / member_name).write_bytes(b"placeholder")

    responses = {
        "inventory_only.mmbx": (
            {"summary": {}, "geometry_preview": {}},
            {
                "contract_pass": True,
                "reason_code": "PASS_TABLE_DIRECTORY_ONLY",
                "summary": {
                    "geometry_preview_ready": False,
                    "topology_preview_ready": False,
                    "geometry_preview_mode": "",
                    "geometry_preview_point_count": 0,
                    "geometry_preview_segment_count": 0,
                    "table_entry_count": 3,
                    "in_file_payload_table_count": 0,
                },
            },
        ),
        "raw_preview.mmbx": (
            {"summary": {}, "geometry_preview": {}},
            {
                "contract_pass": True,
                "reason_code": "PASS_TABLE_DIRECTORY_ONLY",
                "summary": {
                    "geometry_preview_ready": False,
                    "topology_preview_ready": False,
                    "geometry_preview_mode": "heuristic_xyz_point_scan",
                    "geometry_preview_point_count": 8,
                    "geometry_preview_segment_count": 0,
                    "table_entry_count": 3,
                    "in_file_payload_table_count": 0,
                },
            },
        ),
        "hint_preview.mcb": (
            {"summary": {}, "geometry_preview": {}},
            {
                "contract_pass": True,
                "reason_code": "PASS_TABLE_DIRECTORY_ONLY",
                "summary": {
                    "geometry_preview_ready": False,
                    "topology_preview_ready": False,
                    "geometry_preview_mode": "mcvl_node_hint_preview",
                    "geometry_preview_point_count": 5,
                    "geometry_preview_segment_count": 0,
                    "table_entry_count": 6,
                    "in_file_payload_table_count": 0,
                },
            },
        ),
        "table_local_preview.mmbx": (
            {"summary": {}, "geometry_preview": {}},
            {
                "contract_pass": True,
                "reason_code": "PASS_TABLE_DIRECTORY_ONLY",
                "summary": {
                    "geometry_preview_ready": False,
                    "topology_preview_ready": True,
                    "geometry_preview_mode": "table_local_ascii_preview",
                    "geometry_preview_point_count": 4,
                    "geometry_preview_segment_count": 4,
                    "table_local_preview_probe": {
                        "topology_grounding_label": "explicit_member_add_paths",
                        "topology_edge_count": 4,
                        "topology_component_count": 1,
                        "topology_preview_ready": True,
                        "topology_readiness_label": "topology-grounded member-add preview",
                    },
                    "table_entry_count": 2,
                    "in_file_payload_table_count": 1,
                },
            },
        ),
    }

    def _fake_decode(member_path: Path):
        return responses[member_path.name]

    monkeypatch.setattr(refresh_mod, "decode_meb_inventory", _fake_decode)

    payload = refresh_source(source_dir)

    assert payload["selected_member_name"] == "table_local_preview.mmbx"
    assert payload["selected_preview_quality"]["label"] == "topology-grounded preview"
    assert payload["selected_selection_basis"].startswith("topology-grounded preview |")
    labels = {row["member_name"]: row["preview_quality_label"] for row in payload["evaluations"]}
    selected_row = next(row for row in payload["evaluations"] if row["member_name"] == "table_local_preview.mmbx")
    assert selected_row["topology_preview_ready"] is True
    assert selected_row["table_local_topology_grounding_label"] == "explicit_member_add_paths"
    assert selected_row["table_local_topology_edge_count"] == 4
    assert selected_row["table_local_topology_component_count"] == 1
    assert selected_row["table_local_topology_preview_ready"] is True
    assert selected_row["table_local_topology_readiness_label"] == "topology-grounded member-add preview"
    assert labels == {
        "hint_preview.mcb": "hint preview",
        "inventory_only.mmbx": "inventory only",
        "raw_preview.mmbx": "raw preview",
        "table_local_preview.mmbx": "topology-grounded preview",
    }
