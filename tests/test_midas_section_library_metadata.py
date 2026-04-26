from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


def test_parse_midas_mgt_emits_section_library_metadata(tmp_path: Path) -> None:
    mgt = tmp_path / "section_library_demo.mgt"
    mgt.write_text(
        """*NODE
1, 0.0, 0.0, 0.0
2, 0.0, 0.0, 3.0
3, 4.0, 0.0, 3.0
4, 4.0, 0.0, 0.0
*ELEMENT
1, BEAM, 1, 10, 1, 2, 0, 0
2, PLATE, 2, 11, 1, 2, 3, 4, 0, 0
*MATERIAL
1, STEEL
2, CONC
*SECTION
10, H-400x200
11, SLAB-200
*DGN-SECT
10, DB, H-400x200, C, NO, NO, H
AREA, 0.1, 0.2, 0.3, 0.4, 0.5
*SECT-COLOR
10, 128, 0, 128, 255, 0, 0, 0, 255, 0, NO, 0.5
*SECT-SCALE
10, 1, 1, 1, 1, 1, 1, 1, G1, 1
""",
        encoding="utf-8",
    )
    json_out = tmp_path / "model.json"
    npz_out = tmp_path / "graph.npz"
    rpt_out = tmp_path / "report.json"

    cmd = [
        sys.executable,
        "implementation/phase1/parse_midas_mgt_to_json_npz.py",
        "--mgt",
        str(mgt),
        "--json-out",
        str(json_out),
        "--npz-out",
        str(npz_out),
        "--report-out",
        str(rpt_out),
        "--min-nodes",
        "4",
        "--min-elements",
        "2",
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr

    model = json.loads(json_out.read_text(encoding="utf-8"))
    section_library = model["model"]["metadata"]["section_library"]
    assert section_library["contract_version"] == "0.1.0"
    assert section_library["provenance"] == "parser_additive_metadata"
    assert len(section_library["usage_summary"]) == 2
    assert section_library["summary"]["section_row_count"] == 2
    assert section_library["summary"]["used_section_count"] == 2
    assert section_library["summary"]["derived_template_count"] >= 2

    usage_by_id = {int(row["section_id"]): row for row in section_library["usage_summary"]}
    assert usage_by_id[10]["inferred_family"] == "steel"
    assert usage_by_id[10]["inferred_shape"] == "h_beam"
    assert usage_by_id[10]["has_design_section_row"] is True
    assert usage_by_id[10]["has_section_color_row"] is True
    assert usage_by_id[10]["has_section_scale_row"] is True
    assert usage_by_id[11]["inferred_family"] == "rc"
    assert usage_by_id[11]["inferred_shape"] == "slab_strip"
    assert usage_by_id[11]["usage_count"] == 1

    derived_catalog = section_library["derived_catalog"]
    assert derived_catalog["source_label"] == "midas_parser_derived"
    assert derived_catalog["template_count"] >= 2
    template_ids = {row["section_id"] for row in derived_catalog["templates"]}
    assert "midas:10" in template_ids
    assert "midas:11" in template_ids

    report = json.loads(rpt_out.read_text(encoding="utf-8"))
    assert int(report["metrics"]["section_usage_summary_count"]) == 2
    assert int(report["metrics"]["used_section_count"]) == 2
    assert int(report["metrics"]["derived_section_template_count"]) >= 2
    assert report["section_productization"]["section_row_count"] == 2


def test_parse_midas_mgt_emits_load_pattern_library_metadata(tmp_path: Path) -> None:
    mgt = tmp_path / "load_pattern_demo.mgt"
    mgt.write_text(
        """*NODE
1, 0.0, 0.0, 0.0
2, 0.0, 0.0, 3.0
3, 4.0, 0.0, 3.0
4, 4.0, 0.0, 0.0
*ELEMENT
1, BEAM, 1, 10, 1, 2, 0, 0
2, PLATE, 2, 11, 1, 2, 3, 4, 0, 0
*MATERIAL
1, STEEL
2, CONC
*SECTION
10, H-400x200
11, SLAB-200
*STLDCASE
DEAD, D,
LIVE, L,
WINDX, WIND,
*USE-STLD, DEAD
*SELFWEIGHT
0, 0, -1,
*USE-STLD, LIVE
*CONLOAD
1 2, 0, 0, -12, 0, 0, 0, G1
*USE-STLD, WINDX
*PRESSURE
2, PRES, PLATE, FACE, GX, 0, 0, 0, NO, -5, 0, 0, 0, 0, G2, 0
*LOADCOMB
ULS1, GEN, STRENGTH, 1.2(D) + 1.6(L) + 0.7(WINDX)
ST, DEAD, 1.2, ST, LIVE, 1.6, ST, WINDX, 0.7
*LC-COLOR
DEAD, 255, 0, 0
""",
        encoding="utf-8",
    )
    json_out = tmp_path / "model.json"
    npz_out = tmp_path / "graph.npz"
    rpt_out = tmp_path / "report.json"

    cmd = [
        sys.executable,
        "implementation/phase1/parse_midas_mgt_to_json_npz.py",
        "--mgt",
        str(mgt),
        "--json-out",
        str(json_out),
        "--npz-out",
        str(npz_out),
        "--report-out",
        str(rpt_out),
        "--min-nodes",
        "4",
        "--min-elements",
        "2",
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr

    model = json.loads(json_out.read_text(encoding="utf-8"))
    load_pattern_library = model["model"]["metadata"]["load_pattern_library"]
    assert load_pattern_library["contract_version"] == "0.1.0"
    assert load_pattern_library["provenance"] == "parser_additive_metadata"
    assert len(load_pattern_library["pattern_summary"]["patterns"]) == 3
    assert load_pattern_library["summary"]["pattern_count"] == 3
    assert load_pattern_library["summary"]["primitive_count"] == 3
    assert load_pattern_library["summary"]["design_situation_counts"] == {
        "lateral_wind": 1,
        "permanent_gravity": 1,
        "variable_imposed": 1,
    }
    assert load_pattern_library["summary"]["semantic_status_counts"] == {
        "nodal_only_ready": 1,
        "nodal_plus_body_pending": 1,
        "nodal_plus_surface_pending": 1,
    }
    assert load_pattern_library["summary"]["load_color_row_count"] == 1
    assert load_pattern_library["combination_summary"]["combination_count"] == 1
    assert load_pattern_library["combination_summary"]["expansion_mode_counts"] == {
        "linear_combination": 1,
    }
    assert load_pattern_library["combination_summary"]["max_expansion_depth"] == 1
    assert load_pattern_library["combination_summary"]["nested_combination_count"] == 0
    assert load_pattern_library["combination_summary"]["referenced_case_union"] == ["DEAD", "LIVE", "WINDX"]
    assert load_pattern_library["combination_summary"]["referenced_leaf_case_union"] == ["DEAD", "LIVE", "WINDX"]
    assert load_pattern_library["pattern_summary"]["primitive_kind_counts"] == {
        "point_load": 1,
        "self_weight": 1,
        "surface_pressure": 1,
    }

    patterns = {row["label"]: row for row in load_pattern_library["pattern_summary"]["patterns"]}
    assert patterns["DEAD"]["design_situation"] == "permanent_gravity"
    assert patterns["DEAD"]["primitives"][0]["kind"] == "self_weight"
    assert patterns["DEAD"]["primitives"][0]["direction"] == "global_z"
    assert patterns["LIVE"]["design_situation"] == "variable_imposed"
    assert patterns["LIVE"]["primitives"][0]["kind"] == "point_load"
    assert patterns["LIVE"]["primitives"][0]["target_scope"] == "nodes=2 | rows=1"
    assert patterns["WINDX"]["design_situation"] == "lateral_wind"
    assert patterns["WINDX"]["primitives"][0]["kind"] == "surface_pressure"
    assert patterns["WINDX"]["primitives"][0]["direction"] == "global_x"
    editor_seed = model["model"]["metadata"]["load_combination_editor_seed"]
    assert editor_seed["contract_version"] == "0.1.0"
    assert editor_seed["provenance"] == "parser_additive_metadata"
    assert editor_seed["seed_kind"] == "midas_load_combination_editor_seed"
    assert editor_seed["summary"]["combination_count"] == 1
    assert editor_seed["summary"]["case_count"] == 3
    assert editor_seed["summary"]["graph_edge_count"] == 3
    assert editor_seed["summary"]["stage_count"] == 2
    assert editor_seed["summary"]["max_expansion_depth"] == 1
    assert editor_seed["summary"]["limit_state_counts"] == {"STRENGTH": 1}
    assert editor_seed["summary"]["expansion_mode_counts"] == {"linear_combination": 1}
    assert editor_seed["case_nodes"][0]["kind"] == "case"
    assert editor_seed["combination_nodes"][0]["name"] == "ULS1"
    assert editor_seed["combination_nodes"][0]["factor_map"] == {"DEAD": 1.2, "LIVE": 1.6, "WINDX": 0.7}
    assert editor_seed["combination_nodes"][0]["entry_rows"][0]["reference_kind"] == "ST"
    assert editor_seed["combination_nodes"][0]["entry_rows"][0]["reference_name"] == "DEAD"
    assert editor_seed["graph_edges"][0]["src_kind"] == "combo"
    assert editor_seed["graph_edges"][0]["dst_kind"] == "case"

    report = json.loads(rpt_out.read_text(encoding="utf-8"))
    assert int(report["metrics"]["load_pattern_count"]) == 3
    assert int(report["metrics"]["load_pattern_primitive_count"]) == 3
    assert int(report["metrics"]["load_pattern_combination_count"]) == 1
    assert int(report["metrics"]["load_combination_editor_combo_count"]) == 1
    assert int(report["metrics"]["load_combination_editor_case_count"]) == 3
    assert int(report["metrics"]["load_combination_editor_edge_count"]) == 3
    assert int(report["metrics"]["derived_load_pattern_count"]) == 3
    assert int(report["metrics"]["derived_load_pattern_primitive_count"]) == 3
    assert report["load_pattern_productization"]["pattern_count"] == 3
    assert report["load_pattern_productization"]["primitive_kind_counts"] == {
        "point_load": 1,
        "self_weight": 1,
        "surface_pressure": 1,
    }
    assert report["load_combination_editor_seed"]["combination_count"] == 1
    assert report["load_combination_editor_seed"]["case_count"] == 3
    assert report["load_combination_editor_seed"]["graph_edge_count"] == 3
