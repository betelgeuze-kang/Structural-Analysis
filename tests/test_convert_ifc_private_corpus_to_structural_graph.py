from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[1]
IFC_SCRIPT = REPO_ROOT / "implementation/phase1/convert_ifc_private_corpus_to_structural_graph.py"
QUEUE_SCRIPT = REPO_ROOT / "implementation/phase1/build_real_drawing_optimization_intake_queue.py"
IFC_SPEC = importlib.util.spec_from_file_location("convert_ifc_private_corpus_to_structural_graph", IFC_SCRIPT)
assert IFC_SPEC is not None and IFC_SPEC.loader is not None
ifc_adapter = importlib.util.module_from_spec(IFC_SPEC)
IFC_SPEC.loader.exec_module(ifc_adapter)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _manifest_payload(private_path: Path | None = None) -> dict:
    file_row = {
        "file_id": "fixture_ifc",
        "file_name": "fixture.ifc",
        "file_type": ".ifc",
        "role": "bim_ifc_model",
        "bytes": 321,
        "sha256": "abc123",
        "source_url": "https://example.invalid/fixture.ifc",
        "model_optimization_candidate": True,
        "raw_redistribution_allowed": False,
        "release_surface_allowed": False,
    }
    if private_path is not None:
        file_row["private_path"] = str(private_path)
    return {
        "schema_version": "real-drawing-private-corpus-manifest.v1",
        "projects": [
            {
                "project_id": "fixture_project",
                "project_title": "Fixture Project",
                "source_family": "fixture",
                "files": [file_row],
            }
        ],
    }


def test_ifc_adapter_builds_proxy_graph_and_omits_private_path(tmp_path: Path) -> None:
    ifc_path = tmp_path / "private" / "fixture.ifc"
    ifc_path.parent.mkdir(parents=True)
    ifc_path.write_text(
        """ISO-10303-21;
HEADER;
FILE_SCHEMA(('IFC2X3'));
ENDSEC;
DATA;
#10= IFCBUILDINGSTOREY('storey-guid',$,'Level 1',$,$,$,$,$,$);
#11= IFCCARTESIANPOINT((0.,0.,0.));
#12= IFCAXIS2PLACEMENT3D(#11,$,$);
#13= IFCLOCALPLACEMENT($,#12);
#14= IFCCARTESIANPOINT((4.,0.,0.));
#15= IFCAXIS2PLACEMENT3D(#14,$,$);
#16= IFCLOCALPLACEMENT($,#15);
#17= IFCCARTESIANPOINT((0.,4.,0.));
#18= IFCAXIS2PLACEMENT3D(#17,$,$);
#19= IFCLOCALPLACEMENT($,#18);
#20= IFCCOLUMN('column-guid',$,'C1',$,$,#13,#40,$);
#21= IFCBEAM('beam-guid',$,'B1',$,$,#16,#43,$);
#22= IFCSLAB('slab-guid',$,'S1',$,$,#19,#46,$);
#30= IFCRELCONTAINEDINSPATIALSTRUCTURE('rel-guid',$,$,$,(#20,#21,#22),#10);
#40= IFCPRODUCTDEFINITIONSHAPE($,$,(#41));
#41= IFCSHAPEREPRESENTATION($,'Body','SweptSolid',(#42));
#42= IFCEXTRUDEDAREASOLID(#50,$,$,3.);
#43= IFCPRODUCTDEFINITIONSHAPE($,$,(#44));
#44= IFCSHAPEREPRESENTATION($,'Body','SweptSolid',(#45));
#45= IFCEXTRUDEDAREASOLID(#50,$,$,4.);
#46= IFCPRODUCTDEFINITIONSHAPE($,$,(#47));
#47= IFCSHAPEREPRESENTATION($,'Body','SweptSolid',(#48));
#48= IFCEXTRUDEDAREASOLID(#50,$,$,0.25);
#50= IFCRECTANGLEPROFILEDEF(.AREA.,$,$,1.,2.);
#51= IFCMATERIAL('Concrete');
#52= IFCMATERIALLAYER(#51,250.,$);
#53= IFCMATERIALLAYERSET((#52),'LayerSet');
#54= IFCMATERIALLAYERSETUSAGE(#53,.AXIS2.,.POSITIVE.,0.);
#55= IFCRELASSOCIATESMATERIAL('mat-guid',$,$,$,(#20,#21,#22),#54);
ENDSEC;
END-ISO-10303-21;
""",
        encoding="utf-8",
    )
    private_manifest = tmp_path / "private_manifest.json"
    redacted_manifest = tmp_path / "redacted_manifest.json"
    out_dir = tmp_path / "ifc_adapter"
    _write_json(private_manifest, _manifest_payload(private_path=ifc_path))
    _write_json(redacted_manifest, _manifest_payload(private_path=None))

    proc = subprocess.run(
        [
            sys.executable,
            str(IFC_SCRIPT),
            "--private-manifest",
            str(private_manifest),
            "--redacted-manifest",
            str(redacted_manifest),
            "--out-dir",
            str(out_dir),
            "--json",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    manifest = json.loads(proc.stdout)
    assert manifest["summary"]["solver_graph_json_npz_receipt_count"] == 1
    assert manifest["summary"]["solver_graph_element_count_total"] == 3
    report_text = (out_dir / "fixture_ifc.report.json").read_text(encoding="utf-8")
    graph = json.loads((out_dir / "fixture_ifc.graph.json").read_text(encoding="utf-8"))
    report = json.loads(report_text)
    assert "private_path" not in report_text
    assert str(ifc_path) not in report_text
    assert report["adapter_mode"] == "entity_proxy_graph"
    assert report["contract_pass"] is True
    assert report["solver_exact"] is False
    assert "material/section binding" in report["readiness_note"]
    assert report["solver_graph_json"] == str(out_dir / "fixture_ifc.solver_graph.json")
    assert report["solver_graph_npz"] == str(out_dir / "fixture_ifc.solver_graph.npz")
    assert report["metrics"]["structural_entity_count"] == 3
    assert report["entity_counts"]["IFCBUILDINGSTOREY"] == 1
    assert report["entity_counts"]["IFCCOLUMN"] == 1
    assert graph["metrics"]["proxy_node_count"] == 4
    assert graph["metrics"]["proxy_edge_count"] == 3
    solver_receipt = report["evidence_receipts"]["solver_graph_json_npz_receipt"]
    assert solver_receipt["contract_pass"] is True
    assert solver_receipt["solver_exact"] is False
    assert solver_receipt["reason_code"] == "PASS_IFC_SOLVER_GRAPH_JSON_NPZ_DRAFT_EMITTED"
    assert solver_receipt["geometry_scope"] == "ifc_axis_or_body_member_extents"
    assert solver_receipt["element_count"] == 3
    assert solver_receipt["body_extrusion_element_count"] == 3
    assert solver_receipt["placement_marker_fallback_count"] == 0
    assert solver_receipt["member_extent_coverage_ratio"] == 1.0
    assert "ifc_load_case_extraction_or_engineer_signed_zero_load_receipt" in solver_receipt["open_dependencies"]
    solver_payload = json.loads((out_dir / "fixture_ifc.solver_graph.json").read_text(encoding="utf-8"))
    assert solver_payload["solver_exact"] is False
    assert solver_payload["model"]["geometry_scope"] == "ifc_axis_or_body_member_extents"
    assert len(solver_payload["model"]["nodes"]) == 6
    assert len(solver_payload["model"]["elements"]) == 3
    with np.load(out_dir / "fixture_ifc.solver_graph.npz") as dataset:
        assert dataset["node_xyz"].shape == (6, 3)
        assert dataset["element_node_indices"].shape == (3, 2)
    load_receipt = graph["evidence_receipts"]["ifc_load_case_extraction_or_engineer_signed_zero_load_receipt"]
    assert load_receipt["contract_pass"] is False
    assert load_receipt["reason_code"] == "ERR_IFC_LOAD_CASES_MISSING_ENGINEER_ZERO_LOAD_SIGNATURE_REQUIRED"
    assert load_receipt["zero_load_substitution_requires_engineer_signature"] is True


def test_ifc_adapter_marks_source_shape_missing_fallback_reason(tmp_path: Path) -> None:
    ifc_path = tmp_path / "private" / "shape_missing.ifc"
    ifc_path.parent.mkdir(parents=True)
    ifc_path.write_text(
        """ISO-10303-21;
HEADER;
FILE_SCHEMA(('IFC2X3'));
ENDSEC;
DATA;
#1= IFCCARTESIANPOINT((0.,0.,0.));
#2= IFCCARTESIANPOINT((5.,0.,0.));
#3= IFCAXIS2PLACEMENT3D(#1,$,$);
#4= IFCAXIS2PLACEMENT3D(#2,$,$);
#5= IFCLOCALPLACEMENT($,#3);
#6= IFCLOCALPLACEMENT($,#4);
#7= IFCRECTANGLEPROFILEDEF(.AREA.,$,$,1.,2.);
#8= IFCEXTRUDEDAREASOLID(#7,$,$,3.);
#9= IFCSHAPEREPRESENTATION($,'Body','SweptSolid',(#8));
#10= IFCPRODUCTDEFINITIONSHAPE($,$,(#9));
#11= IFCCOLUMN('column-guid',$,'C1',$,$,#5,#10,$);
#12= IFCSLAB('slab-guid',$,'S1',$,$,#6,$,$);
ENDSEC;
END-ISO-10303-21;
""",
        encoding="utf-8",
    )

    graph = ifc_adapter.parse_ifc_proxy_graph(ifc_path)
    missing_node = next(node for node in graph["nodes"] if node.get("id") == "#12")
    assert missing_node["member_extent_missing_reason"] == "source_ifc_product_shape_missing"
    json_path = tmp_path / "solver" / "shape_missing.solver_graph.json"
    npz_path = tmp_path / "solver" / "shape_missing.solver_graph.npz"

    receipt = ifc_adapter._write_solver_graph_artifacts(graph=graph, json_path=json_path, npz_path=npz_path)
    payload = json.loads(json_path.read_text(encoding="utf-8"))

    assert receipt["placement_marker_fallback_count"] == 1
    assert receipt["placement_marker_fallback_source_shape_missing_count"] == 1
    assert receipt["placement_marker_fallback_unresolved_count"] == 0
    assert payload["metrics"]["placement_marker_fallback_reason_counts"] == {
        "source_ifc_product_shape_missing": 1
    }
    fallback_element = next(
        element
        for element in payload["model"]["elements"]
        if element["geometry_scope"] == "placement_origin_axis_marker_not_member_extents"
    )
    assert fallback_element["geometry_fallback_reason"] == "source_ifc_product_shape_missing"


def test_ifc_adapter_uses_release_safe_aggregate_group_edges(tmp_path: Path) -> None:
    ifc_path = tmp_path / "private" / "aggregate_only.ifc"
    ifc_path.parent.mkdir(parents=True)
    ifc_path.write_text(
        """ISO-10303-21;
HEADER;
FILE_SCHEMA(('IFC2X3'));
ENDSEC;
DATA;
#5= IFCBUILDING('building-guid',$,'Building',$,$,$,$,$,$,$,$,$);
#6= IFCCARTESIANPOINT((10.,20.,0.));
#7= IFCAXIS2PLACEMENT3D(#6,$,$);
#8= IFCLOCALPLACEMENT($,#7);
#9= IFCCARTESIANPOINT((14.,22.,0.));
#10= IFCAXIS2PLACEMENT3D(#9,$,$);
#11= IFCLOCALPLACEMENT($,#10);
#12= IFCPRODUCTDEFINITIONSHAPE($,$,(#13,#15));
#13= IFCSHAPEREPRESENTATION($,'Body','SweptSolid',(#14));
#14= IFCEXTRUDEDAREASOLID(#22,$,$,3.);
#15= IFCSHAPEREPRESENTATION($,'Axis','Curve2D',(#16));
#16= IFCPOLYLINE((#6,#9));
#17= IFCPRODUCTDEFINITIONSHAPE($,$,(#18));
#18= IFCSHAPEREPRESENTATION($,'Body','SweptSolid',(#19));
#19= IFCEXTRUDEDAREASOLID(#23,$,$,4.);
#20= IFCCOLUMN('column-guid',$,'C1',$,$,#8,#12,$);
#21= IFCBEAM('beam-guid',$,'B1',$,$,#11,#17,$);
#22= IFCRECTANGLEPROFILEDEF(.AREA.,$,$,1.,2.);
#23= IFCRECTANGLEPROFILEDEF(.AREA.,$,$,1.,3.);
#24= IFCMATERIAL('Concrete');
#25= IFCMATERIALLAYER(#24,250.,$);
#26= IFCMATERIALLAYERSET((#25),'LayerSet');
#27= IFCMATERIALLAYERSETUSAGE(#26,.AXIS2.,.POSITIVE.,0.);
#28= IFCMATERIAL('Steel');
#29= IFCRELASSOCIATESMATERIAL('mat-column',$,$,$,(#20),#27);
#30= IFCRELASSOCIATESMATERIAL('mat-beam',$,$,$,(#21),#28);
#40= IFCRELAGGREGATES('rel-guid',$,$,$,#5,(#20,#21));
#50= IFCSTRUCTURALLOADGROUP('load-case-guid',$,'DL',$,$,.LOAD_CASE.,.ACTION.,$);
#51= IFCSTRUCTURALLOADLINEARFORCE('dead-line',0.,0.,-10.,0.,0.,0.);
#52= IFCSTRUCTURALCURVEACTION('action-guid',$,'Dead line',$,$,$,$,.CONST.,.GLOBAL_COORDS.,#51);
#53= IFCRELCONNECTSSTRUCTURALACTIVITY('activity-guid',$,$,$,#20,#52);
#54= IFCRELASSIGNSTOGROUP('assign-guid',$,$,$,(#52),$,#50);
ENDSEC;
END-ISO-10303-21;
""",
        encoding="utf-8",
    )

    payload = ifc_adapter.parse_ifc_proxy_graph(ifc_path)

    assert payload["metrics"]["structural_entity_count"] == 2
    assert payload["metrics"]["direct_relationship_edge_count"] == 0
    assert payload["metrics"]["relationship_group_node_count"] == 1
    assert payload["metrics"]["proxy_node_count"] == 3
    assert payload["metrics"]["proxy_edge_count"] == 2
    assert payload["metrics"]["placement_coordinate_structural_count"] == 2
    assert payload["metrics"]["placement_coordinate_node_count"] == 3
    assert payload["metrics"]["shape_product_structural_count"] == 2
    assert payload["metrics"]["body_representation_structural_count"] == 2
    assert payload["metrics"]["axis_representation_structural_count"] == 1
    assert payload["metrics"]["member_extent_structural_count"] == 2
    assert payload["metrics"]["axis_polyline_extent_structural_count"] == 1
    assert payload["metrics"]["body_extrusion_extent_structural_count"] == 1
    assert payload["metrics"]["member_extent_coverage_ratio"] == 1.0
    assert payload["metrics"]["material_bound_structural_count"] == 2
    assert payload["metrics"]["section_source_structural_count"] == 2
    assert payload["metrics"]["load_related_record_count"] == 5
    assert payload["metrics"]["load_case_group_count"] == 1
    assert payload["metrics"]["structural_load_count"] == 1
    assert payload["metrics"]["structural_action_count"] == 1
    assert payload["evidence_receipts"]["ifc_local_placement_coordinate_extraction_receipt"]["contract_pass"] is True
    representation_receipt = payload["evidence_receipts"]["ifc_representation_shape_axis_receipt"]
    assert representation_receipt["contract_pass"] is True
    assert representation_receipt["representation_identifier_counts"] == {"Axis": 1, "Body": 2}
    assert representation_receipt["geometry_item_type_counts"] == {
        "IFCEXTRUDEDAREASOLID": 2,
        "IFCPOLYLINE": 1,
    }
    material_receipt = payload["evidence_receipts"]["ifc_material_section_binding_receipt"]
    assert material_receipt["contract_pass"] is True
    assert material_receipt["material_bound_structural_count"] == 2
    assert material_receipt["section_source_structural_count"] == 2
    assert material_receipt["material_root_type_counts"] == {
        "IFCMATERIAL": 1,
        "IFCMATERIALLAYERSETUSAGE": 1,
    }
    assert material_receipt["section_source_type_counts"] == {
        "IFCMATERIALLAYER": 1,
        "IFCMATERIALLAYERSET": 1,
        "IFCMATERIALLAYERSETUSAGE": 1,
        "IFCRECTANGLEPROFILEDEF": 2,
    }
    load_receipt = payload["evidence_receipts"]["ifc_load_case_extraction_or_engineer_signed_zero_load_receipt"]
    assert load_receipt["contract_pass"] is True
    assert load_receipt["reason_code"] == "PASS_IFC_LOAD_CASES_EXTRACTED"
    assert load_receipt["load_case_group_count"] == 1
    assert load_receipt["structural_load_count"] == 1
    assert load_receipt["structural_action_count"] == 1
    assert load_receipt["connected_structural_action_count"] == 1
    assert load_receipt["load_group_assignment_count"] == 1
    assert load_receipt["zero_load_substitution_requires_engineer_signature"] is False
    assert payload["proxy_relationship_counts"] == {"aggregates_decomposition": 2}
    assert "release_safe_aggregate_group_edges" in payload["relationship_extraction_modes"]
    assert next(node for node in payload["nodes"] if node["id"] == "#20")["x"] == 10.0
    assert next(node for node in payload["nodes"] if node["id"] == "#21")["y"] == 22.0
    axis_node = next(node for node in payload["nodes"] if node["id"] == "#20")
    assert axis_node["member_extent_source"] == "ifc_axis_polyline_world"
    assert len(axis_node["member_axis_world_points"]) == 2
    group_node = next(node for node in payload["nodes"] if node["id"] == "relationship:IFCRELAGGREGATES:#40")
    assert group_node["x"] == 12.0
    assert group_node["y"] == 21.0
    assert all(edge["target"] == "relationship:IFCRELAGGREGATES:#40" for edge in payload["edges"])


def test_ifc_adapter_recovers_mapped_and_boolean_body_extents(tmp_path: Path) -> None:
    ifc_path = tmp_path / "private" / "mapped_boolean.ifc"
    ifc_path.parent.mkdir(parents=True)
    ifc_path.write_text(
        """ISO-10303-21;
HEADER;
FILE_SCHEMA(('IFC2X3'));
ENDSEC;
DATA;
#1= IFCCARTESIANPOINT((0.,0.,0.));
#2= IFCCARTESIANPOINT((4.,0.,0.));
#3= IFCAXIS2PLACEMENT3D(#1,$,$);
#4= IFCAXIS2PLACEMENT3D(#2,$,$);
#5= IFCLOCALPLACEMENT($,#3);
#6= IFCLOCALPLACEMENT($,#4);
#7= IFCDIRECTION((0.,0.,1.));
#8= IFCRECTANGLEPROFILEDEF(.AREA.,$,$,1.,2.);
#9= IFCEXTRUDEDAREASOLID(#8,#3,#7,5.);
#10= IFCSHAPEREPRESENTATION($,'Body','SweptSolid',(#9));
#11= IFCREPRESENTATIONMAP(#3,#10);
#12= IFCCARTESIANTRANSFORMATIONOPERATOR3D($,$,#1,1.,$);
#13= IFCMAPPEDITEM(#11,#12);
#14= IFCSHAPEREPRESENTATION($,'Body','MappedRepresentation',(#13));
#15= IFCPRODUCTDEFINITIONSHAPE($,$,(#14));
#16= IFCBOOLEANCLIPPINGRESULT(.DIFFERENCE.,#9,#99);
#17= IFCSHAPEREPRESENTATION($,'Body','Clipping',(#16));
#18= IFCPRODUCTDEFINITIONSHAPE($,$,(#17));
#19= IFCCOLUMN('mapped-guid',$,'Mapped column',$,$,#5,#15,$);
#20= IFCBEAM('boolean-guid',$,'Boolean beam',$,$,#6,#18,$);
ENDSEC;
END-ISO-10303-21;
""",
        encoding="utf-8",
    )

    payload = ifc_adapter.parse_ifc_proxy_graph(ifc_path)

    assert payload["metrics"]["structural_entity_count"] == 2
    assert payload["metrics"]["member_extent_structural_count"] == 2
    assert payload["metrics"]["body_extrusion_extent_structural_count"] == 2
    assert payload["metrics"]["member_extent_coverage_ratio"] == 1.0
    extent_sources = {
        node["id"]: node.get("member_extent_source")
        for node in payload["nodes"]
        if node.get("proxy_node_kind") == "structural_element"
    }
    assert extent_sources["#19"] == "ifc_mapped_body_extrusion_depth_world"
    assert extent_sources["#20"] == "ifc_body_boolean_operand_extent_world"


def test_ifc_adapter_recovers_brep_body_bounds_as_member_extents(tmp_path: Path) -> None:
    ifc_path = tmp_path / "private" / "brep.ifc"
    ifc_path.parent.mkdir(parents=True)
    ifc_path.write_text(
        """ISO-10303-21;
HEADER;
FILE_SCHEMA(('IFC2X3'));
ENDSEC;
DATA;
#1= IFCCARTESIANPOINT((0.,0.,0.));
#2= IFCAXIS2PLACEMENT3D(#1,$,$);
#3= IFCLOCALPLACEMENT($,#2);
#4= IFCCARTESIANPOINT((0.,0.,0.));
#5= IFCCARTESIANPOINT((2.,0.,0.));
#6= IFCCARTESIANPOINT((2.,1.,12.));
#7= IFCCARTESIANPOINT((0.,1.,12.));
#8= IFCPOLYLOOP((#4,#5,#6,#7));
#9= IFCFACEOUTERBOUND(#8,.T.);
#10= IFCFACE((#9));
#11= IFCCLOSEDSHELL((#10));
#12= IFCFACETEDBREP(#11);
#13= IFCADVANCEDBREP(#11);
#14= IFCSHAPEREPRESENTATION($,'Body','Brep',(#12));
#15= IFCSHAPEREPRESENTATION($,'Body','AdvancedBrep',(#13));
#16= IFCPRODUCTDEFINITIONSHAPE($,$,(#14));
#17= IFCPRODUCTDEFINITIONSHAPE($,$,(#15));
#18= IFCSLAB('brep-guid',$,'Brep slab',$,$,#3,#16,$);
#19= IFCWALL('advanced-guid',$,'Advanced wall',$,$,#3,#17,$);
ENDSEC;
END-ISO-10303-21;
""",
        encoding="utf-8",
    )

    payload = ifc_adapter.parse_ifc_proxy_graph(ifc_path)

    assert payload["metrics"]["structural_entity_count"] == 2
    assert payload["metrics"]["member_extent_structural_count"] == 2
    assert payload["metrics"]["body_extrusion_extent_structural_count"] == 2
    assert payload["metrics"]["member_extent_coverage_ratio"] == 1.0
    extent_sources = {
        node["id"]: node.get("member_extent_source")
        for node in payload["nodes"]
        if node.get("proxy_node_kind") == "structural_element"
    }
    assert extent_sources["#18"] == "ifc_body_brep_bounds_world"
    assert extent_sources["#19"] == "ifc_body_advanced_brep_bounds_world"


def test_queue_promotes_ifc_adapter_report_to_proxy_ready(tmp_path: Path) -> None:
    manifest = tmp_path / "redacted_manifest.json"
    mgt_parse_dir = tmp_path / "mgt_parse"
    ifc_adapter_dir = tmp_path / "ifc_adapter"
    out = tmp_path / "queue.json"
    _write_json(
        manifest,
        {
            "schema_version": "real-drawing-redacted-corpus-manifest.v1",
            "projects": [
                {
                    "project_id": "fixture_project",
                    "project_title": "Fixture Project",
                    "source_family": "fixture",
                    "files": [
                        {
                            "file_id": "fixture_ifc",
                            "file_name": "fixture.ifc",
                            "file_type": ".ifc",
                            "role": "bim_ifc_model",
                            "bytes": 321,
                            "sha256": "abc123",
                            "source_url": "https://example.invalid/fixture.ifc",
                            "model_optimization_candidate": True,
                            "raw_redistribution_allowed": False,
                            "release_surface_allowed": False,
                        }
                    ],
                }
            ],
        },
    )
    _write_json(
        ifc_adapter_dir / "fixture_ifc.report.json",
        {
            "contract_pass": True,
            "reason_code": "PASS",
            "adapter_mode": "entity_proxy_graph",
            "solver_exact": False,
            "graph_json": str(ifc_adapter_dir / "fixture_ifc.graph.json"),
            "solver_graph_json": str(ifc_adapter_dir / "fixture_ifc.solver_graph.json"),
            "solver_graph_npz": str(ifc_adapter_dir / "fixture_ifc.solver_graph.npz"),
            "metrics": {
                "proxy_node_count": 4,
                "proxy_edge_count": 3,
                "structural_entity_count": 3,
                "storey_count": 1,
            },
            "evidence_receipts": {
                "solver_graph_json_npz_receipt": {
                    "contract_pass": True,
                    "reason_code": "PASS_IFC_SOLVER_GRAPH_JSON_NPZ_DRAFT_EMITTED",
                    "json_path": str(ifc_adapter_dir / "fixture_ifc.solver_graph.json"),
                    "npz_path": str(ifc_adapter_dir / "fixture_ifc.solver_graph.npz"),
                }
            },
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(QUEUE_SCRIPT),
            "--redacted-manifest",
            str(manifest),
            "--mgt-parse-report-dir",
            str(mgt_parse_dir),
            "--ifc-adapter-report-dir",
            str(ifc_adapter_dir),
            "--out",
            str(out),
            "--json",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["summary"]["optimized_drawing_generation_ready_count"] == 1
    assert payload["summary"]["ifc_proxy_graph_ready_count"] == 1
    assert payload["summary"]["ifc_adapter_required_count"] == 0
    assert payload["summary"]["ready_ifc_proxy_node_count_total"] == 4
    row = payload["queue"][0]
    assert row["optimization_status"] == "ifc_proxy_graph_ready"
    assert row["ready_for_optimized_drawing_generation"] is True
    assert row["solver_exact"] is False
    assert row["solver_graph_model_json"] == str(ifc_adapter_dir / "fixture_ifc.solver_graph.json")
    assert row["solver_graph_dataset_npz"] == str(ifc_adapter_dir / "fixture_ifc.solver_graph.npz")
    assert "not solver-exact" in row["readiness_note"]
    assert "load/zero-load attestation" in row["readiness_note"]
