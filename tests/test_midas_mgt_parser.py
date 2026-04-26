from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import numpy as np


def _foundation_fixture_path(name: str) -> Path:
    return Path(__file__).resolve().parent / "fixtures" / "foundation_realish" / name


def _write_demo_mgt(path: Path) -> None:
    path.write_text(
        """*UNIT
N, m, C
*NODE
1, 0.0, 0.0, 0.0
2, 0.0, 0.0, 3.0
3, 4.0, 0.0, 3.0
4, 4.0, 0.0, 0.0
5, 2.0, 2.0, 0.0
6, 2.0, 2.0, 3.0
100, 0.0, 0.0, 0.0
*ELEMENT
1, BEAM, 20, 10, 1, 2, 0, 0
2, BEAM, 20, 10, 2, 3, 0, 0
3, PLATE, 21, 11, 3, 4, 5, 6, 0, 0
*ELASTICLINK
1, 100, 1, RIGID, 0, NO, 0.5, 0.5
*MATERIAL
20, STEEL, 2.05E+11, 0.3, 7850
21, CONC, 2.70E+10, 0.2, 2500
*SECTION
10, H-400x200
11, SLAB-200
*STLDCASE
DEAD, D,
*SELFWEIGHT
0, 0, -1,
*CONLOAD
1 2, 0, 0, -10, 0, 0, 0, G1, DEAD
*NODALMASS
3 4, 1.0, 1.0, 0.0, 0.0, 0.0, 0.0
*OFFSET
1, GLOBAL, 0.1, 0.0, 0.0, 0.1, 0.0, 0.0, G1
*PRESSURE
3, PRES, PLATE, FACE, GZ, 0, 0, 0, NO, -5, 0, 0, 0, 0, G1, 0
*MEMBER
1, 1, NO, 1, 2
*GROUP
G1, 1 2 3 4, 1 2 3, FLOOR
*THICKNESS
11, SLAB_T, VALUE, YES, 0.2, 0.2, NO, NONE, 0
*DGN-SECT
10, DB, H-400x200, C, NO, NO, H
AREA, 0.1, 0.2, 0.3, 0.4, 0.5
*SECT-COLOR
10, 128, 0, 128, 255, 0, 0, 0, 255, 0, NO, 0.5
*SECT-SCALE
10, 1, 1, 1, 1, 1, 1, 1, G1, 1
*STRUCTYPE
0, 1, 1, NO, YES, 9.81, 0, YES, YES, NO
*VERSION
9.3.0
*LOADCASE
LC1, DEAD
*LOADCOMB
ULS1, ULS, STRENGTH, LC1, 1.4, DEAD, 1.0
""",
        encoding="utf-8",
    )


def test_parse_midas_mgt_to_json_npz(tmp_path: Path) -> None:
    mgt = tmp_path / "real_building_model.mgt"
    _write_demo_mgt(mgt)
    json_out = tmp_path / "model.json"
    npz_out = tmp_path / "graph.npz"
    edge_out = tmp_path / "edges.json"
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
        "--edge-list-out",
        str(edge_out),
        "--report-out",
        str(rpt_out),
        "--require-shell-beam-mix",
        "--min-nodes",
        "3",
        "--min-elements",
        "3",
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr

    report = json.loads(rpt_out.read_text(encoding="utf-8"))
    assert report["contract_pass"] is True
    assert report["reason_code"] == "PASS"
    assert int(report["metrics"]["node_count"]) == 6
    assert int(report["metrics"]["element_count"]) == 3
    assert int(report["metrics"]["beam_element_count"]) >= 1
    assert int(report["metrics"]["shell_element_count"]) >= 1
    assert int(report["metrics"]["dummy_node_removed_count"]) >= 1
    assert int(report["metrics"]["typed_section_count"]) >= 5
    assert int(report["metrics"]["unknown_section_count"]) == 0
    assert str(report["artifacts"]["edge_list_out"]) == str(edge_out)
    assert int((report["artifacts"]["edge_list_summary"] or {}).get("node_count", 0)) == 6

    model = json.loads(json_out.read_text(encoding="utf-8"))
    assert len(model["model"]["nodes"]) == 6
    assert len(model["model"]["elements"]) == 3
    assert len(model["model"]["loads"]["static_load_cases"]) == 1
    assert len(model["model"]["loads"]["load_cases"]) == 1
    assert len(model["model"]["loads"]["load_combinations"]) == 1
    assert model["model"]["loads"]["load_combinations"][0]["entry_count"] >= 1
    assert model["model"]["loads"]["load_combinations"][0]["expression_component_count"] >= 0
    assert isinstance(model["model"]["loads"]["load_combinations"][0]["referenced_cases"], list)
    assert "load_combination_graph" in model["model"]["loads"]
    assert len(model["model"]["loads"]["selfweight"]) == 1
    assert len(model["model"]["loads"]["nodal_loads"]) == 1
    assert len(model["model"]["loads"]["nodal_masses"]) == 1
    assert len(model["model"]["loads"]["beam_offsets"]) == 1
    assert len(model["model"]["loads"]["pressure_loads"]) == 1
    assert len(model["model"]["metadata"]["members"]) == 1
    assert len(model["model"]["metadata"]["groups"]) == 1
    assert model["model"]["metadata"]["groups"][0]["name"] == "G1"
    assert len(model["model"]["metadata"]["thickness"]) == 1
    assert len(model["model"]["metadata"]["design_sections"]) == 1
    assert len(model["model"]["metadata"]["section_colors"]) == 1
    assert len(model["model"]["metadata"]["section_scales"]) == 1
    assert len(model["model"]["metadata"]["design_materials"]) == 0
    assert len(model["model"]["metadata"]["design_material_rebar_payloads"]) == 0
    assert len(model["model"]["metadata"]["group_local_rebar_payloads"]) == 0
    assert len(model["model"]["metadata"]["structure_type"]) == 1
    assert len(model["model"]["metadata"]["version"]) == 1
    assert len(model["model"]["load_cases_raw"]) == 1
    assert len(model["model"]["load_combinations_raw"]) == 1

    npz = np.load(npz_out)
    assert int(npz["node_id"].shape[0]) == 6
    assert int(npz["node_xyz"].shape[1]) == 3
    assert int(npz["edge_index"].shape[0]) == 2
    assert int(npz["elem_id"].shape[0]) == 3

    edge_payload = json.loads(edge_out.read_text(encoding="utf-8"))
    assert int(edge_payload["node_count"]) == 6
    assert isinstance(edge_payload["edges"], list) and len(edge_payload["edges"]) >= 3


def test_parse_midas_mgt_semantic_loadcomb_expression(tmp_path: Path) -> None:
    mgt = tmp_path / "loadcomb_expr.mgt"
    mgt.write_text(
        """*NODE
1, 0.0, 0.0, 0.0
2, 0.0, 0.0, 3.0
*ELEMENT
1, BEAM, 1, 10, 1, 2, 0, 0
*MATERIAL
1, STEEL
*SECTION
10, SEC-A
*LOADCOMB
NAME=ULS-A, GEN, ACTIVE, 0, 0, 1.2(D) + 1.6(L), 0, 0, 0
ST, DEAD, 1.2, ST, LIVE, 1.6
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
        "2",
        "--min-elements",
        "1",
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    model = json.loads(json_out.read_text(encoding="utf-8"))
    combo = model["model"]["loads"]["load_combinations"][0]
    assert combo["name"] == "ULS-A"
    assert combo["expression"] == "1.2(D) + 1.6(L)"
    assert combo["expression_component_count"] == 2
    assert combo["expression_components"][0]["name"] == "DEAD"
    assert combo["expression_components"][1]["name"] == "LIVE"
    assert combo["referenced_cases"] == ["DEAD", "LIVE"]
    assert combo["factor_map"] == {"DEAD": 1.2, "LIVE": 1.6}
    graph = model["model"]["loads"]["load_combination_graph"]
    assert graph["node_count"] >= 3
    assert len(graph["nodes"]) == graph["node_count"]


def test_parse_midas_mgt_extracts_material_level_rebar_payloads(tmp_path: Path) -> None:
    mgt = tmp_path / "rebar_payload.mgt"
    mgt.write_text(
        """*NODE
1, 0.0, 0.0, 0.0
2, 0.0, 0.0, 3.0
*ELEMENT
1, BEAM, 1, 10, 1, 2, 0, 0
*MATERIAL
1, CONC
*SECTION
10, SEC-A
*DGN-MATL
1, CONC, C40, 2, 0, NO, 1, NO, 0, GB10(RC), HRB400, HRB400, 400, 400, 0, NO, 1, 0
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
        "2",
        "--min-elements",
        "1",
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    report = json.loads(rpt_out.read_text(encoding="utf-8"))
    assert int(report["metrics"]["design_material_rebar_payload_row_count"]) == 1
    assert int(report["metrics"]["design_material_rebar_payload_available_count"]) == 1
    assert int(report["metrics"]["group_local_rebar_payload_row_count"]) == 0
    model = json.loads(json_out.read_text(encoding="utf-8"))
    payload = model["model"]["metadata"]["design_material_rebar_payloads"][0]
    assert payload["material_id"] == 1
    assert payload["payload_present"] is True
    assert payload["rbcode"] == "GB10(RC)"
    assert payload["rbmain"] == "HRB400"


def test_parse_midas_mgt_binds_use_stld_load_blocks(tmp_path: Path) -> None:
    mgt = tmp_path / "semantic_use_stld.mgt"
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
10, B-SEC
11, W-SEC
*STLDCASE
DEAD, D,
LIVE, L,
*USE-STLD, DEAD
*SELFWEIGHT
0, 0, -1,
*CONLOAD
1 2, 0, 0, -10, 0, 0, 0, G1
*USE-STLD, LIVE
*CONLOAD
3 4, 5, 0, 0, 0, 0, 0, G2
*PRESSURE
2, PRES, PLATE, FACE, GZ, 0, 0, 0, NO, -5, 0, 0, 0, 0, G2, 0
*LOADCOMB
ULS1, GEN, STRENGTH, 1.2(D) + 1.6(L)
ST, DEAD, 1.2, ST, LIVE, 1.6
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

    report = json.loads(rpt_out.read_text(encoding="utf-8"))
    assert int(report["metrics"]["use_stld_block_count"]) == 2
    assert int(report["metrics"]["semantic_load_case_count"]) == 2
    assert int(report["metrics"]["bound_nodal_load_row_count"]) == 2
    assert int(report["metrics"]["bound_selfweight_row_count"]) == 1
    assert int(report["metrics"]["bound_pressure_row_count"]) == 1
    assert int(report["metrics"]["unbound_nodal_load_row_count"]) == 0
    assert int(report["metrics"]["unbound_selfweight_row_count"]) == 0
    assert int(report["metrics"]["unbound_pressure_row_count"]) == 0

    model = json.loads(json_out.read_text(encoding="utf-8"))
    loads = model["model"]["loads"]
    assert loads["active_static_case_sequence"] == ["DEAD", "LIVE"]
    assert loads["nodal_loads"][0]["load_case"] == "DEAD"
    assert loads["nodal_loads"][0]["load_case_source"] == "use_stld"
    assert loads["selfweight"][0]["load_case"] == "DEAD"
    assert loads["pressure_loads"][0]["load_case"] == "LIVE"
    semantic = loads["semantic_load_summary"]
    case_rows = {row["load_case"]: row for row in semantic["case_force_summaries"]}
    assert set(case_rows) == {"DEAD", "LIVE"}
    assert case_rows["DEAD"]["selfweight_row_count"] == 1
    assert case_rows["LIVE"]["pressure_row_count"] == 1
    assert case_rows["LIVE"]["surface_load_assembly_pending"] is True
    combo = semantic["combination_force_summaries"][0]
    assert combo["name"] == "ULS1"
    assert combo["referenced_cases"] == ["DEAD", "LIVE"]
    assert combo["body_load_assembly_pending"] is True
    assert combo["surface_load_assembly_pending"] is True


def test_parse_midas_mgt_parses_foundation_realish_fixture(tmp_path: Path) -> None:
    mgt = _foundation_fixture_path("foundation_small.mgt")
    json_out = tmp_path / "foundation_small_model.json"
    npz_out = tmp_path / "foundation_small_graph.npz"
    rpt_out = tmp_path / "foundation_small_report.json"

    proc = subprocess.run(
        [
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
            "3",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    report = json.loads(rpt_out.read_text(encoding="utf-8"))
    assert report["contract_pass"] is True
    assert report["reason_code"] == "PASS"
    assert report["source_provenance"]["source_family"] == "midas_mgt"
    assert report["source_provenance"]["path"].endswith("tests/fixtures/foundation_realish/foundation_small.mgt")
    assert int(report["metrics"]["node_count"]) == 8
    assert int(report["metrics"]["element_count"]) == 3
    assert int(report["metrics"]["edge_count_undirected"]) == 6
    assert int(report["metrics"]["beam_element_count"]) == 2
    assert int(report["metrics"]["shell_element_count"]) == 1
    assert int(report["metrics"]["element_rows_total"]) == 3
    assert int(report["metrics"]["element_rows_skipped"]) == 0
    assert float(report["metrics"]["element_skip_ratio"]) == 0.0
    assert int(report["metrics"]["group_row_count"]) == 2
    assert int(report["metrics"]["dummy_node_removed_count"]) == 0
    assert int(report["metrics"]["typed_section_count"]) >= 2
    row_parse = report["parser_diagnostics"]["row_parse"]
    assert row_parse["node_rows"] == 8
    assert row_parse["node_rows_parsed"] == 8
    assert row_parse["element_rows"] == 3
    assert row_parse["element_rows_parsed"] == 3
    assert row_parse["section_rows"] == 3
    assert row_parse["section_rows_parsed"] == 3
    assert row_parse["material_rows"] == 2
    assert row_parse["material_rows_parsed"] == 2
    assert report["parser_diagnostics"]["element_skip_reason_count"] == {}
    assert report["coarsening"]["dummy_node_removed_count"] == 0
    assert report["coarsening"]["node_count_post"] == 8
    assert report["coarsening"]["element_count_post"] == 3
    assert report["artifacts"]["npz_summary"]["node_count"] == 8
    assert report["artifacts"]["npz_summary"]["element_count"] == 3
    assert report["artifacts"]["npz_summary"]["elem_conn_index_count"] == 8

    model = json.loads(json_out.read_text(encoding="utf-8"))
    assert model["source"]["path"].endswith("tests/fixtures/foundation_realish/foundation_small.mgt")
    assert model["source"]["source_family"] == "midas_mgt"
    assert model["source"]["format"] == "midas_mgt"
    assert model["parser"]["strict_element_slot_parse"] is True
    assert model["parser"]["section_counts"]["NODE"] == 8
    assert model["parser"]["section_counts"]["MATERIAL"] == 2
    assert model["parser"]["section_counts"]["SECTION"] == 3
    assert model["parser"]["section_counts"]["ELEMENT"] == 3
    assert model["parser"]["section_counts"]["GROUP"] == 2
    assert len(model["model"]["elements"]) == 3
    assert len(model["model"]["materials"]) == 2
    assert [str(row["name"]) for row in model["model"]["materials"]] == ["STEEL", "CONC"]
    assert [str(row["name"]) for row in model["model"]["sections"]] == ["RAFT-1200", "PILE-CAP-700", "B-SEC-450"]
    elements = {int(row["id"]): row for row in model["model"]["elements"]}
    assert elements[101]["family"] == "shell"
    assert elements[101]["section_id"] == 21
    assert elements[101]["material_id"] == 21
    assert elements[101]["node_ids"] == [1, 2, 3, 4]
    assert elements[102]["family"] == "beam"
    assert elements[102]["section_id"] == 22
    assert elements[102]["material_id"] == 21
    assert elements[102]["node_ids"] == [5, 6]
    assert elements[103]["family"] == "beam"
    assert elements[103]["section_id"] == 23
    assert elements[103]["material_id"] == 20
    assert elements[103]["node_ids"] == [7, 8]
    groups = {str(row["name"]): row for row in model["model"]["metadata"]["groups"]}
    assert set(groups) == {"FOUNDATION_ZONE", "PERIM_FRAME"}
    assert groups["FOUNDATION_ZONE"]["plane_type"] == "FOUNDATION"
    assert groups["FOUNDATION_ZONE"]["node_expr"] == "1 2 3 4 5 6"
    assert groups["FOUNDATION_ZONE"]["element_expr"] == "101 102"
    assert groups["FOUNDATION_ZONE"]["node_ids"] == [1, 2, 3, 4, 5, 6]
    assert groups["FOUNDATION_ZONE"]["element_ids"] == [101, 102]
    assert groups["PERIM_FRAME"]["plane_type"] == "FRAME"
    assert groups["PERIM_FRAME"]["node_expr"] == "7 8"
    assert groups["PERIM_FRAME"]["element_expr"] == "103"
    assert groups["PERIM_FRAME"]["element_ids"] == [103]
    assert model["topology_metrics"]["node_count"] == 8
    assert model["topology_metrics"]["element_count"] == 3
    assert model["topology_metrics"]["edge_count_undirected"] == 6

    npz = np.load(npz_out)
    assert int(npz["node_id"].shape[0]) == 8
    assert int(npz["elem_id"].shape[0]) == 3
    assert int(npz["edge_index"].shape[1]) == 12
    assert npz["elem_section_id"].tolist() == [21, 22, 23]


def test_parse_midas_mgt_parses_foundation_generic_section_fixture(tmp_path: Path) -> None:
    mgt = _foundation_fixture_path("foundation_generic_sections.mgt")
    json_out = tmp_path / "foundation_generic_sections_model.json"
    npz_out = tmp_path / "foundation_generic_sections_graph.npz"
    rpt_out = tmp_path / "foundation_generic_sections_report.json"

    proc = subprocess.run(
        [
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
            "3",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    report = json.loads(rpt_out.read_text(encoding="utf-8"))
    assert report["contract_pass"] is True
    assert report["reason_code"] == "PASS"
    assert report["source_provenance"]["path"].endswith("tests/fixtures/foundation_realish/foundation_generic_sections.mgt")
    assert int(report["metrics"]["node_count"]) == 8
    assert int(report["metrics"]["element_count"]) == 3
    assert int(report["metrics"]["group_row_count"]) == 2

    model = json.loads(json_out.read_text(encoding="utf-8"))
    assert [str(row["name"]) for row in model["model"]["sections"]] == ["DBUSER", "DBUSER", "B-SEC-450"]
    groups = {str(row["name"]): row for row in model["model"]["metadata"]["groups"]}
    assert set(groups) == {"PILE_FOUNDATION_ZONE", "PERIM_FRAME"}
    assert groups["PILE_FOUNDATION_ZONE"]["element_ids"] == [101, 102]
    assert groups["PILE_FOUNDATION_ZONE"]["plane_type"] == "SUBSTRUCTURE"

    npz = np.load(npz_out)
    assert int(npz["node_id"].shape[0]) == 8
    assert int(npz["elem_id"].shape[0]) == 3
    assert npz["elem_section_id"].tolist() == [21, 22, 23]
    assert npz["elem_material_id"].tolist() == [21, 21, 20]


def test_parse_midas_mgt_parses_foundation_deep_fixture(tmp_path: Path) -> None:
    mgt = _foundation_fixture_path("foundation_deep_small.mgt")
    json_out = tmp_path / "foundation_deep_small_model.json"
    npz_out = tmp_path / "foundation_deep_small_graph.npz"
    rpt_out = tmp_path / "foundation_deep_small_report.json"

    proc = subprocess.run(
        [
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
            "3",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    report = json.loads(rpt_out.read_text(encoding="utf-8"))
    assert report["contract_pass"] is True
    assert report["reason_code"] == "PASS"
    assert report["source_provenance"]["path"].endswith("tests/fixtures/foundation_realish/foundation_deep_small.mgt")
    assert int(report["metrics"]["node_count"]) == 10
    assert int(report["metrics"]["element_count"]) == 4
    assert int(report["metrics"]["group_row_count"]) == 2

    model = json.loads(json_out.read_text(encoding="utf-8"))
    assert [str(row["name"]) for row in model["model"]["sections"]] == ["MAT-1500", "CAISSON-900", "PILE-600", "G-SEC-500"]
    groups = {str(row["name"]): row for row in model["model"]["metadata"]["groups"]}
    assert set(groups) == {"DEEP_FOUNDATION_ZONE", "UPPER_FRAME"}
    assert groups["DEEP_FOUNDATION_ZONE"]["element_ids"] == [201, 202, 203]
    assert groups["DEEP_FOUNDATION_ZONE"]["plane_type"] == "FOUNDATION"

    npz = np.load(npz_out)
    assert int(npz["node_id"].shape[0]) == 10
    assert int(npz["elem_id"].shape[0]) == 4
    assert npz["elem_section_id"].tolist() == [31, 32, 33, 34]
    assert npz["elem_material_id"].tolist() == [31, 31, 31, 30]


def test_parse_midas_mgt_preserves_foundation_plane_type_with_generic_section_names(tmp_path: Path) -> None:
    mgt = _foundation_fixture_path("foundation_parser_drop_small.mgt")
    json_out = tmp_path / "foundation_parser_drop_small_model.json"
    npz_out = tmp_path / "foundation_parser_drop_small_graph.npz"
    rpt_out = tmp_path / "foundation_parser_drop_small_report.json"

    proc = subprocess.run(
        [
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
            "3",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    report = json.loads(rpt_out.read_text(encoding="utf-8"))
    assert report["contract_pass"] is True
    assert report["reason_code"] == "PASS"
    assert report["source_provenance"]["path"].endswith("tests/fixtures/foundation_realish/foundation_parser_drop_small.mgt")
    assert int(report["metrics"]["node_count"]) == 8
    assert int(report["metrics"]["element_count"]) == 3
    assert int(report["metrics"]["group_row_count"]) == 2

    model = json.loads(json_out.read_text(encoding="utf-8"))
    assert [str(row["name"]) for row in model["model"]["sections"]] == ["DBUSER", "DBUSER", "B-SEC-450"]
    groups = {str(row["name"]): row for row in model["model"]["metadata"]["groups"]}
    assert set(groups) == {"SUBSTRUCT_ZONE", "PERIM_FRAME"}
    assert groups["SUBSTRUCT_ZONE"]["element_ids"] == [101, 102]
    assert groups["SUBSTRUCT_ZONE"]["plane_type"] == "FOUNDATION"

    npz = np.load(npz_out)
    assert int(npz["node_id"].shape[0]) == 8
    assert int(npz["elem_id"].shape[0]) == 3
    assert npz["elem_section_id"].tolist() == [21, 22, 23]
    assert npz["elem_material_id"].tolist() == [21, 21, 20]


def test_parse_midas_mgt_ignores_non_node_int_slots(tmp_path: Path) -> None:
    mgt = tmp_path / "real_building_model_slots.mgt"
    mgt.write_text(
        """*NODE
1, 0.0, 0.0, 0.0
2, 0.0, 0.0, 3.0
3, 4.0, 0.0, 3.0
4, 4.0, 0.0, 0.0
*ELEMENT
1, BEAM, 1, 9999, 1, 2, 0, 0
2, BEAM, 1, 7777, 2, 3, 0, 0
*MATERIAL
1, STEEL
*SECTION
9999, SEC-A
7777, SEC-B
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
        "3",
        "--min-elements",
        "2",
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr

    npz = np.load(npz_out)
    edge_index = npz["edge_index"]
    pairs = {(int(edge_index[0, i]), int(edge_index[1, i])) for i in range(edge_index.shape[1])}
    # wrong section ids 9999/7777 must never appear as node indices
    assert all(u < 4 and v < 4 for u, v in pairs)


def test_parse_midas_mgt_parses_comptr_and_tri_plate_zero_slot(tmp_path: Path) -> None:
    mgt = tmp_path / "real_building_comptr_tri.mgt"
    mgt.write_text(
        """*NODE
1, 0.0, 0.0, 0.0
2, 0.0, 0.0, 3.0
3, 4.0, 0.0, 3.0
4, 4.0, 0.0, 0.0
*ELEMENT
1, COMPTR, 1, 10, 1, 2, 0, 1, 0, 0, NO
2, PLATE, 1, 11, 1, 2, 3, 0, 3, 0
*MATERIAL
1, STEEL
*SECTION
10, SEC-A
11, SEC-B
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
        "3",
        "--min-elements",
        "2",
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    report = json.loads(rpt_out.read_text(encoding="utf-8"))
    assert report["contract_pass"] is True
    assert int(report["metrics"]["element_rows_skipped"]) == 0
    assert float(report["metrics"]["element_skip_ratio"]) == 0.0
    assert int(report["metrics"]["beam_element_count"]) == 1
    assert int(report["metrics"]["shell_element_count"]) == 1


def test_parse_midas_mgt_fails_on_unresolved_element_skip_by_default(tmp_path: Path) -> None:
    mgt = tmp_path / "real_building_unresolved_element.mgt"
    mgt.write_text(
        """*NODE
1, 0.0, 0.0, 0.0
2, 0.0, 0.0, 3.0
3, 4.0, 0.0, 3.0
4, 4.0, 0.0, 0.0
*ELEMENT
1, BEAM, 1, 10, 1, 2, 0, 0
2, UNKNOWN_SPECIAL, 1, 10, 2, 3, 0, 0
*MATERIAL
1, STEEL
*SECTION
10, SEC-A
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
        "2",
        "--min-elements",
        "1",
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode != 0
    report = json.loads(rpt_out.read_text(encoding="utf-8"))
    assert report["reason_code"] == "ERR_ELEMENT_SKIP_BUDGET"


def test_parse_midas_mgt_blocks_synthetic_source(tmp_path: Path) -> None:
    mgt = tmp_path / "toy_atwood_sample.mgt"
    _write_demo_mgt(mgt)
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
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode != 0
    report = json.loads(rpt_out.read_text(encoding="utf-8"))
    assert report["reason_code"] == "ERR_SYNTHETIC_SOURCE"


def test_parse_midas_mgt_unknown_section_lenient_vs_strict(tmp_path: Path) -> None:
    mgt = tmp_path / "real_building_unknown_section.mgt"
    mgt.write_text(
        """*NODE
1, 0.0, 0.0, 0.0
2, 0.0, 0.0, 3.0
3, 4.0, 0.0, 3.0
4, 4.0, 0.0, 0.0
*ELEMENT
1, BEAM, 1, 10, 1, 2, 0, 0
2, BEAM, 1, 10, 2, 3, 0, 0
*MATERIAL
1, STEEL
*SECTION
10, SEC-A
*FOO_BAR_UNKNOWN
THIS,SECTION,SHOULD,NOT,CRASH
""",
        encoding="utf-8",
    )
    json_out = tmp_path / "model.json"
    npz_out = tmp_path / "graph.npz"
    rpt_out = tmp_path / "report_lenient.json"
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
        "3",
        "--min-elements",
        "2",
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    report = json.loads(rpt_out.read_text(encoding="utf-8"))
    assert report["contract_pass"] is True
    assert int(report["parser_diagnostics"]["unknown_section_count"]) == 1
    assert "FOO_BAR_UNKNOWN" in report["parser_diagnostics"]["unknown_sections"]

    strict_report = tmp_path / "report_strict.json"
    strict_cmd = cmd + ["--strict-unknown-sections", "--report-out", str(strict_report)]
    proc2 = subprocess.run(strict_cmd, check=False, capture_output=True, text=True)
    assert proc2.returncode != 0
    report2 = json.loads(strict_report.read_text(encoding="utf-8"))
    assert report2["reason_code"] == "ERR_UNKNOWN_SECTION"
