from __future__ import annotations

import json
import subprocess
from pathlib import Path


def test_viewer_direct_model_normalizer_preserves_midas_metadata_contract() -> None:
    script = """
import {
  buildMaterialCatalogSummary,
  buildSectionCatalogSummary,
  buildThicknessCatalogSummary,
  sanitizeModelPayload,
  sanitizeModelPayloadAsync,
} from './src/structure-viewer/viewer-direct-model-normalizer.js';

const artifact = {
  run_id: 'fixture-run',
  generated_at: '2026-05-08T00:00:00Z',
  source: {path: 'fixture.json', sha256: 'abc123', format: 'midas-json', source_family: 'midas'},
  meta: {
    real_drawing_asset_count: 2,
    real_drawing_renderable_asset_count: 2,
    real_drawing_solver_exact_asset_count: 1,
    real_drawing_proxy_or_preview_asset_count: 1,
    real_drawing_registry_summary: {
      asset_count: 2,
      renderable_asset_count: 2,
      solver_exact_asset_count: 1,
      proxy_or_preview_asset_count: 1,
      route_counts: {midas_mgt_direct_parser: 1, ifc_to_structural_graph_adapter: 1},
      status_counts: {solver_graph_ready: 1, ifc_proxy_graph_ready: 1},
      quality_flag_counts: {not_solver_exact: 1}
    },
    real_drawing_solver_exact_promotion_queue: {
      schema_version: 'fixture-promotion.v1',
      contract_pass: true,
      reason_code: 'PASS_PROMOTION_QUEUE_OPEN',
      summary: {
        current_solver_exact_asset_count: 1,
        target_solver_exact_asset_count: 2,
        required_solver_exact_delta: 1,
        planned_unlock_batch_count: 1,
        planned_unlock_batch_expected_delta: 1,
        planned_solver_exact_asset_count_after_unlock_batch: 2,
        promotion_candidate_count: 1,
        promotion_delta_available: 1,
        sufficient_unlock_batch_for_target: true,
        family_counts: {ifc_coordinate_geometry_reconstruction: 1},
        effort_counts: {high: 1}
      },
      planned_unlock_batch: [{
        promotion_id: 'RP-001',
        asset_ref: 'RD-002',
        promotion_family: 'ifc_coordinate_geometry_reconstruction',
        effort_label: 'high',
        quality_tier: 'proxy_preview_review',
        expected_solver_exact_delta: 1,
        quality_flags: ['not_solver_exact'],
        closure_evidence_required: ['proxy_layout_flag_removed'],
        recommended_action: 'replace proxy layout with recovered structural geometry'
      }],
      open_promotion_items: [{
        promotion_id: 'RP-001',
        asset_ref: 'RD-002',
        promotion_family: 'ifc_coordinate_geometry_reconstruction',
        effort_label: 'high',
        blocker_reason_code: 'ERR_IFC_PROXY_LAYOUT_NOT_TRUE_GEOMETRY',
        commercial_claim_blocked: true,
        edge_coverage_ratio: 1,
        closure_evidence_required: ['ifc_local_placement_coordinate_extraction_receipt']
      }]
    },
    real_drawing_asset_registry: [
      {
        asset_ref: 'RD-001',
        file_type: '.mgt',
        route: 'midas_mgt_direct_parser',
        status: 'solver_graph_ready',
        solver_exact: true,
        geometry_mode: 'solver_topology_xyz',
        geometry_available: true,
        segment_count: 2,
        quality_flags: [],
        lod_evidence_status: 'PASS_FULL_DETAIL_LOD_EVIDENCE_ATTACHED',
        full_detail_segment_count: 7,
        viewer_sample_segment_count: 2,
        lod_sample_ratio: 0.285714
      },
      {
        asset_ref: 'RD-002',
        file_type: '.ifc',
        route: 'ifc_to_structural_graph_adapter',
        status: 'ifc_proxy_graph_ready',
        solver_exact: false,
        geometry_mode: 'ifc_proxy_topology_3d_layout',
        graph_source_kind: 'ifc_solver_graph_draft',
        geometry_available: true,
        geometry_exact_ready: true,
        ifc_geometry_exact_ready: true,
        geometry_claim_status: 'ifc_geometry_exact_ready',
        load_model_status: 'source_ifc_load_model_missing',
        load_model_ready: false,
        analysis_claim_ready: false,
        load_evidence_status: 'ERR_IFC_LOAD_CASES_MISSING_ENGINEER_ZERO_LOAD_SIGNATURE_REQUIRED',
        load_evidence_contract_pass: false,
        load_case_group_count: 0,
        structural_load_count: 0,
        zero_load_signature_required: true,
        engineer_zero_load_signature_attached: false,
        segment_count: 1,
        quality_flags: ['not_solver_exact'],
        source_quality_flags: ['ifc_source_shape_missing_partial'],
        claim_quality_flags: ['ifc_load_model_missing']
      }
    ]
  },
  model: {
    nodes: [
      {id: 10, x: '1', y: '2', z: '0'},
      {id: 11, x: '1', y: '2', z: '3'}
    ],
    elements: [
      {id: 'E1', type: 'beam', node_ids: [10, 11], section_id: 'S1', material_id: 'M-STEEL', dcr: '0.92'}
    ],
    materials: [
      {id: 'M-STEEL', name: 'STEEL', raw_tokens: ['SM355', '0', '0', 'C', 'NO', '0.02', '2', '2.0500e+08', '0.30', '1.2000e-05', '78', '0']}
    ],
    sections: [
      {id: 'S1', section_name: 'H-400x200', raw_tokens: ['H-400x200', 'SM355']}
    ],
    metadata: {
      material_colors: [{material_id: 'M-STEEL', fill_rgb: [8, 144, 180]}],
      thickness: [{thickness_id: 7, row_tokens: [['7', 'VALUE', 'M-STEEL', 'YES', '0.225', '0', 'NO', '0', '0.5']], raw_row_count: 1}],
      rebar_material_codes: [{tokens: ['KSD3504', 'SD400'], raw: 'KSD3504, SD400'}],
      section_colors: [{section_id: 'S1', fill_rgb: [1, 2, 3]}],
      members: [{id: 'M1', element_ids: ['E1']}],
      groups: [{name: 'Core A', element_ids: ['E1'], element_count: 1, node_count: 2, physical_line_span: 3, element_ids_head: ['E1']}],
      section_library: {
        summary: {section_row_count: 1, used_section_count: 1},
        usage_summary: [{section_id: 'S1', inferred_family: 'steel', inferred_shape: 'H', usage_count: 1, name: 'H-400x200'}]
      },
      kds_geometry_bridge: {
        axis_refs: {z: [{label: '1F'}, {label: '2F'}]},
        summary: {review_id_count: 1, mapped_review_id_count: 1, full_member_crosswalk_count: 1},
        bridge_rows: [{
          review_case_id: 'R1',
          baseline_focus_member_id: 'M1',
          row_provenance_top_row_label: 'row-1',
          row_provenance_summary_label: 'summary-1',
          full_crosswalk_load_combination_names: ['LC1'],
          full_crosswalk_member_groups: ['Core A'],
          full_crosswalk_target_element_id: 'E1'
        }]
      },
      load_pattern_library: {
        summary: {pattern_count: 1, primitive_count: 2},
        case_semantic_rows: [{label: 'DEAD'}]
      },
      load_combination_editor_seed: {
        combination_nodes: [{
          name: 'COMBO1',
          combination_type: 'STR',
          limit_state: 'ULS',
          entry_rows: [{reference_kind: 'LC', reference_name: 'DEAD', factor: '1.2'}]
        }]
      },
      structure_type: [{raw: 'Steel'}],
      length_units: [{raw: 'm'}]
    }
  }
};

const direct = sanitizeModelPayload(artifact, {mode: 'fixture', label: 'Fixture artifact'});
const chunkCalls = [];
const chunked = await sanitizeModelPayloadAsync(artifact, {mode: 'fixture'}, {
  processInChunks: async (rows, handler, options) => {
    chunkCalls.push({length: rows.length, label: options.progressLabel});
    rows.forEach((row, index) => handler(row, index, index));
  },
});
const catalog = buildSectionCatalogSummary(
  artifact.model.sections,
  artifact.model.metadata.section_library.usage_summary,
  artifact.model.elements,
  artifact.model.materials,
  artifact.model.metadata
);
const materialCatalog = buildMaterialCatalogSummary(
  artifact.model.materials,
  artifact.model.elements,
  artifact.model.metadata
);
const thicknessCatalog = buildThicknessCatalogSummary(artifact.model.metadata.thickness);

console.log(JSON.stringify({
  directMode: direct.meta.normalization_mode,
  chunkedMode: chunked.meta.normalization_mode,
  chunkCalls,
  element: direct.elements[0],
  meta: direct.meta,
  catalog,
  materialCatalog,
  thicknessCatalog,
}));
"""
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=Path(__file__).resolve().parents[1],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    element = payload["element"]
    meta = payload["meta"]

    assert payload["directMode"] == "direct"
    assert payload["chunkedMode"] == "chunked"
    assert payload["chunkCalls"] == [
        {"length": 2, "label": "Normalizing nodes"},
        {"length": 1, "label": "Normalizing elements"},
    ]
    assert element["member_id"] == "M1"
    assert element["material_id"] == "M-STEEL"
    assert element["material_name"] == "STEEL"
    assert element["material_grade"] == "SM355"
    assert element["material_label"] == "STEEL SM355"
    assert element["material_family"] == "steel"
    assert element["material_elastic_modulus"] == 205000000
    assert element["material_poisson_ratio"] == 0.3
    assert element["material_density"] == 78
    assert element["material_usage_count"] == 1
    assert element["material_source_status"] == "source_material"
    assert element["material_color"] == "#0890b4"
    assert element["section"] == "H-400x200"
    assert element["section_family"] == "steel"
    assert element["section_shape"] == "H"
    assert element["group_label"] == "Core A"
    assert element["review_case_id"] == "R1"
    assert element["review_row_label"] == "row-1"
    assert element["review_summary_label"] == "summary-1"
    assert element["review_combination_label"] == "LC1"
    assert element["color"] == "#010203"
    assert meta["name"] == "fixture-run"
    assert meta["stories"] == 2
    assert meta["source_label"] == "Fixture artifact"
    assert meta["source_artifact_sha256"] == "abc123"
    assert meta["source_artifact_format"] == "midas-json"
    assert meta["material_count"] == 1
    assert meta["used_material_count"] == 1
    assert meta["thickness_count"] == 1
    assert meta["material_catalog_summary"][0]["material_label"] == "STEEL SM355"
    assert meta["material_catalog_summary"][0]["element_family_mix_label"] == "beam:1"
    assert meta["material_catalog_summary"][0]["source_status"] == "source_material"
    assert meta["material_catalog_summary"][0]["section_usage_summary"][0]["section_id"] == "S1"
    assert meta["material_catalog_summary"][0]["section_usage_summary"][0]["section_label"] == "H-400x200"
    assert meta["material_catalog_summary"][0]["section_usage_summary"][0]["usage_count"] == 1
    assert meta["material_section_schedule_count"] == 1
    assert meta["thickness_catalog_summary"][0]["thickness_value"] == 0.225
    assert meta["rebar_material_code_summary"][0]["material_code_label"] == "KSD3504 / SD400"
    assert meta["load_case_inventory"] == ["DEAD"]
    assert meta["load_combination_inventory"][0]["name"] == "COMBO1"
    assert meta["section_catalog_summary"][0]["display_label"] == "H-400x200"
    assert meta["section_catalog_summary"][0]["usage_count"] == 1
    assert meta["section_catalog_summary"][0]["material_usage_summary"][0]["material_label"] == "STEEL SM355"
    assert meta["section_material_schedule_count"] == 1
    assert meta["section_family_summary"][0]["family"] == "steel"
    assert meta["group_summary"][0]["group_name"] == "Core A"
    assert meta["review_row_summary"][0]["isolation_token"] == "R1::row-1::M1::E1"
    assert meta["real_drawing_asset_count"] == 2
    assert meta["real_drawing_solver_exact_asset_count"] == 1
    assert meta["real_drawing_proxy_or_preview_asset_count"] == 1
    assert meta["real_drawing_registry_summary"]["quality_flag_counts"]["not_solver_exact"] == 1
    assert meta["real_drawing_asset_registry"][0]["lod_evidence_status"] == "PASS_FULL_DETAIL_LOD_EVIDENCE_ATTACHED"
    assert meta["real_drawing_asset_registry"][0]["full_detail_segment_count"] == 7
    assert meta["real_drawing_asset_registry"][1]["asset_ref"] == "RD-002"
    assert meta["real_drawing_asset_registry"][1]["quality_flags"] == ["not_solver_exact"]
    assert meta["real_drawing_asset_registry"][1]["graph_source_kind"] == "ifc_solver_graph_draft"
    assert meta["real_drawing_asset_registry"][1]["geometry_claim_status"] == "ifc_geometry_exact_ready"
    assert meta["real_drawing_asset_registry"][1]["load_model_status"] == "source_ifc_load_model_missing"
    assert (
        meta["real_drawing_asset_registry"][1]["load_evidence_status"]
        == "ERR_IFC_LOAD_CASES_MISSING_ENGINEER_ZERO_LOAD_SIGNATURE_REQUIRED"
    )
    assert meta["real_drawing_asset_registry"][1]["zero_load_signature_required"] is True
    assert meta["real_drawing_asset_registry"][1]["source_quality_flags"] == [
        "ifc_source_shape_missing_partial"
    ]
    assert meta["real_drawing_asset_registry"][1]["claim_quality_flags"] == ["ifc_load_model_missing"]
    assert meta["real_drawing_solver_exact_promotion_queue"]["summary"]["target_solver_exact_asset_count"] == 2
    assert meta["real_drawing_solver_exact_promotion_queue"]["planned_unlock_batch"][0]["asset_ref"] == "RD-002"
    assert meta["real_drawing_solver_exact_promotion_queue"]["planned_unlock_batch"][0][
        "closure_evidence_required"
    ] == ["proxy_layout_flag_removed"]
    assert meta["real_drawing_solver_exact_promotion_queue"]["open_promotion_items"][0][
        "blocker_reason_code"
    ] == "ERR_IFC_PROXY_LAYOUT_NOT_TRUE_GEOMETRY"
    assert meta["real_drawing_solver_exact_promotion_queue"]["open_promotion_items"][0][
        "commercial_claim_blocked"
    ] is True
    assert payload["catalog"][0]["raw_tokens_head"] == ["H-400x200", "SM355"]
    assert payload["catalog"][0]["material_usage_summary"][0]["material_id"] == "M-STEEL"
    assert payload["materialCatalog"][0]["material_family"] == "steel"
    assert payload["materialCatalog"][0]["color"] == "#0890b4"
    assert payload["thicknessCatalog"][0]["material_id"] == "M-STEEL"


def test_viewer_direct_model_normalizer_expands_material_and_section_ontology() -> None:
    script = """
import {
  buildMaterialCatalogSummary,
  buildMaterialFamilyCoverageSummary,
  buildSectionCatalogSummary,
} from './src/structure-viewer/viewer-direct-model-normalizer.js';

const materials = [
  {id: 'M-CONC', name: 'CONC', raw_tokens: ['C40']},
  {id: 'M-REBAR', name: 'REBAR', raw_tokens: ['SD500']},
  {id: 'M-TENDON', name: 'PC STRAND', raw_tokens: ['SWPC7B']},
  {id: 'M-RAIL', name: 'UIC60 RAIL STEEL', raw_tokens: ['rail_steel_UIC60']},
  {id: 'M-FASTENER', name: 'RAIL FASTENER', raw_tokens: ['PANDROL CLIP']},
  {id: 'M-GROUT', name: 'NON-SHRINK GROUT', raw_tokens: ['grout_backfill']},
  {id: 'M-DAMPER', name: 'VISCOUS DAMPER', raw_tokens: ['damper_validation']},
  {id: 'M-ISOLATOR', name: 'LEAD RUBBER BEARING', raw_tokens: ['LRB isolator']},
  {id: 'M-SPRING', name: 'P-Y SPRING', raw_tokens: ['p-y q-z nonlinear link']},
  {id: 'M-MASS', name: 'LUMPED MASS', raw_tokens: ['inertia mass']},
  {id: 'M-BALLAST', name: 'BALLAST GRANITE', raw_tokens: ['ballast_granite']},
  {id: 'M-PAD', name: 'RESILIENT PAD EVA', raw_tokens: ['resilient_pad_eva']},
  {id: 'M-GEO', name: 'HDPE GEOMEMBRANE', raw_tokens: ['geotextile geogrid']},
  {id: 'M-ASPHALT', name: 'ASPHALT PAVEMENT', raw_tokens: ['bituminous']},
  {id: 'M-TIMBER', name: 'GLULAM', raw_tokens: ['GL24H']},
  {id: 'M-MASONRY', name: 'CMU MASONRY', raw_tokens: ['BLOCK']},
  {id: 'M-AL', name: 'ALUMINUM', raw_tokens: ['6061-T6']},
  {id: 'M-FRP', name: 'CFRP retrofit', raw_tokens: ['CFRP']},
  {id: 'M-BOLT', name: 'HIGH STRENGTH BOLT', raw_tokens: ['F10T']},
  {id: 'M-BEARING', name: 'ELASTOMERIC BEARING', raw_tokens: ['RUBBER']},
  {id: 'M-SOIL', name: 'SOIL CLAY', raw_tokens: ['CLAY']},
  {id: 'M-GROUND', name: 'JET GROUT COLUMN', raw_tokens: ['ground improvement dcm']},
  {id: 'M-WATER', name: 'PVC WATERSTOP', raw_tokens: ['waterproofing sheet membrane']},
  {id: 'M-INSUL', name: 'XPS INSULATION', raw_tokens: ['EPS board']},
  {id: 'M-FIRE', name: 'INTUMESCENT FIREPROOFING', raw_tokens: ['SFRM']},
  {id: 'M-COAT', name: 'ZINC RICH PRIMER', raw_tokens: ['galvanized coating']},
  {id: 'M-SEAL', name: 'JOINT SEALANT', raw_tokens: ['backer rod']},
  {id: 'M-GYPSUM', name: 'GYPSUM BOARD', raw_tokens: ['GWB']},
  {id: 'M-STONE', name: 'GRANITE TILE', raw_tokens: ['stone cladding']},
  {id: 'M-FACADE', name: 'CURTAIN WALL PANEL', raw_tokens: ['ACM facade']},
  {id: 'M-SLEEPER', name: 'CONCRETE SLEEPER', raw_tokens: ['rail tie']},
  {id: 'M-POT', name: 'POT BEARING', raw_tokens: ['spherical bearing']},
  {id: 'M-JOINT', name: 'EXPANSION JOINT', raw_tokens: ['modular joint']},
  {id: 'M-ADHESIVE', name: 'EPOXY RESIN', raw_tokens: ['bonding agent']},
  {id: 'M-FORM', name: 'FORMWORK SHORING', raw_tokens: ['falsework temporary support']},
  {id: 'M-SCREED', name: 'FLOOR SCREED', raw_tokens: ['self leveling topping']},
  {id: 'M-ROOF', name: 'ROOFING MEMBRANE', raw_tokens: ['roof tile shingle']},
  {id: 'M-SLEEVE', name: 'PIPE SLEEVE', raw_tokens: ['cast-in insert']},
];
const sections = [
  {id: 'S-H', section_name: 'H-400x200', raw_tokens: ['H-400x200']},
  {id: 'S-WALL', section_name: 'Core Wall', raw_tokens: ['WALL-200']},
  {id: 'S-RETAIN', section_name: 'Retaining Wall', raw_tokens: ['RETAINING WALL']},
  {id: 'S-DWALL', section_name: 'Diaphragm Wall', raw_tokens: ['D-WALL']},
  {id: 'S-PARAPET', section_name: 'Parapet', raw_tokens: ['PARAPET']},
  {id: 'S-SLAB', section_name: 'Flat Slab', raw_tokens: ['SLAB-180']},
  {id: 'S-STAIR', section_name: 'Stair Landing', raw_tokens: ['STAIR']},
  {id: 'S-RAMP', section_name: 'Ramp Slab', raw_tokens: ['RAMP']},
  {id: 'S-BALCONY', section_name: 'Balcony Slab', raw_tokens: ['BALCONY']},
  {id: 'S-MEGA', section_name: 'Mega Column', raw_tokens: ['MEGA COLUMN']},
  {id: 'S-SPANDREL', section_name: 'Spandrel Beam', raw_tokens: ['SPANDREL']},
  {id: 'S-LINTEL', section_name: 'Lintel Beam', raw_tokens: ['LINTEL']},
  {id: 'S-JOIST', section_name: 'Steel Joist', raw_tokens: ['JOIST']},
  {id: 'S-PURLIN', section_name: 'Roof Purlin', raw_tokens: ['PURLIN']},
  {id: 'S-RAFTER', section_name: 'Rafter', raw_tokens: ['RAFTER']},
  {id: 'S-BRB', section_name: 'BRB Brace', raw_tokens: ['BUCKLING RESTRAINED']},
  {id: 'S-TRUSS', section_name: 'Space Truss', raw_tokens: ['TRUSS']},
  {id: 'S-OUTRIGGER', section_name: 'Outrigger Truss', raw_tokens: ['OUTRIGGER']},
  {id: 'S-COLLECTOR', section_name: 'Collector Drag Strut', raw_tokens: ['COLLECTOR']},
  {id: 'S-TIEBACK', section_name: 'Tieback Anchor', raw_tokens: ['TIEBACK']},
  {id: 'S-BASEPLATE', section_name: 'Base Plate', raw_tokens: ['BASE PLATE']},
  {id: 'S-GUSSET', section_name: 'Gusset Plate', raw_tokens: ['GUSSET']},
  {id: 'S-CABLE', section_name: 'Cable 40', raw_tokens: ['CABLE-40']},
  {id: 'S-DAMPER', section_name: 'Viscous Damper', raw_tokens: ['DAMPER-LINK']},
  {id: 'S-ISOLATOR', section_name: 'LRB Isolator', raw_tokens: ['LEAD RUBBER BEARING']},
  {id: 'S-RAIL', section_name: 'UIC60 Rail', raw_tokens: ['UIC60']},
  {id: 'S-SEGMENT', section_name: 'Tunnel Segment Lining', raw_tokens: ['SEGMENT-LINING']},
  {id: 'S-FOOTING', section_name: 'Pile Footing', raw_tokens: ['PILE-FOOTING']},
  {id: 'S-MAT', section_name: 'Mat Foundation', raw_tokens: ['MAT FOUNDATION']},
];
const elements = [
  {id: 'E1', type: 'beam', section_id: 'S-H', material_id: 'M-CONC'},
  {id: 'E2', type: 'beam', section_id: 'S-H', material_id: 'M-REBAR'},
  {id: 'E3', type: 'truss', section_id: 'S-CABLE', material_id: 'M-TENDON'},
  {id: 'E4', type: 'beam', section_id: 'S-RAIL', material_id: 'M-RAIL'},
  {id: 'E5', type: 'spring', section_id: 'S-H', material_id: 'M-FASTENER'},
  {id: 'E6', type: 'solid', section_id: 'S-SEGMENT', material_id: 'M-GROUT'},
  {id: 'E7', type: 'spring', section_id: 'S-DAMPER', material_id: 'M-DAMPER'},
  {id: 'E8', type: 'spring', section_id: 'S-ISOLATOR', material_id: 'M-ISOLATOR'},
  {id: 'E9', type: 'spring', section_id: 'S-FOOTING', material_id: 'M-SPRING'},
  {id: 'E10', type: 'mass', section_id: 'S-H', material_id: 'M-MASS'},
  {id: 'E11', type: 'solid', section_id: 'S-FOOTING', material_id: 'M-BALLAST'},
  {id: 'E12', type: 'spring', section_id: 'S-RAIL', material_id: 'M-PAD'},
  {id: 'E13', type: 'plate', section_id: 'S-SLAB', material_id: 'M-GEO'},
  {id: 'E14', type: 'plate', section_id: 'S-SLAB', material_id: 'M-ASPHALT'},
  {id: 'E15', type: 'beam', section_id: 'S-H', material_id: 'M-TIMBER'},
  {id: 'E16', type: 'wall', section_id: 'S-WALL', material_id: 'M-MASONRY'},
  {id: 'E17', type: 'beam', section_id: 'S-H', material_id: 'M-AL'},
  {id: 'E18', type: 'plate', section_id: 'S-SLAB', material_id: 'M-FRP'},
  {id: 'E19', type: 'beam', section_id: 'S-H', material_id: 'M-BOLT'},
  {id: 'E20', type: 'spring', section_id: 'S-FOOTING', material_id: 'M-BEARING'},
  {id: 'E21', type: 'solid', section_id: 'S-MAT', material_id: 'M-SOIL'},
  {id: 'E22', type: 'solid', section_id: 'S-FOOTING', material_id: 'M-GROUND'},
  {id: 'E23', type: 'plate', section_id: 'S-WALL', material_id: 'M-WATER'},
  {id: 'E24', type: 'plate', section_id: 'S-SLAB', material_id: 'M-INSUL'},
  {id: 'E25', type: 'beam', section_id: 'S-H', material_id: 'M-FIRE'},
  {id: 'E26', type: 'beam', section_id: 'S-H', material_id: 'M-COAT'},
  {id: 'E27', type: 'joint', section_id: 'S-SLAB', material_id: 'M-SEAL'},
  {id: 'E28', type: 'plate', section_id: 'S-WALL', material_id: 'M-GYPSUM'},
  {id: 'E29', type: 'plate', section_id: 'S-SLAB', material_id: 'M-STONE'},
  {id: 'E30', type: 'plate', section_id: 'S-WALL', material_id: 'M-FACADE'},
  {id: 'E31', type: 'beam', section_id: 'S-RAIL', material_id: 'M-SLEEPER'},
  {id: 'E32', type: 'spring', section_id: 'S-FOOTING', material_id: 'M-POT'},
  {id: 'E33', type: 'joint', section_id: 'S-SLAB', material_id: 'M-JOINT'},
  {id: 'E34', type: 'plate', section_id: 'S-SLAB', material_id: 'M-ADHESIVE'},
  {id: 'E35', type: 'temporary', section_id: 'S-H', material_id: 'M-FORM'},
  {id: 'E36', type: 'plate', section_id: 'S-SLAB', material_id: 'M-SCREED'},
  {id: 'E37', type: 'plate', section_id: 'S-SLAB', material_id: 'M-ROOF'},
  {id: 'E38', type: 'insert', section_id: 'S-WALL', material_id: 'M-SLEEVE'},
];
const materialCatalog = buildMaterialCatalogSummary(materials, elements, {section_rows: sections});
const coverage = buildMaterialFamilyCoverageSummary(materialCatalog);
const sectionCatalog = buildSectionCatalogSummary(sections, [], elements, materials, {});
console.log(JSON.stringify({
  families: materialCatalog.map(row => row.material_family).sort(),
  coverage,
  sections: Object.fromEntries(sectionCatalog.map(row => [row.section_id, {
    family: row.inferred_family,
    shape: row.inferred_shape,
    source: row.section_descriptor_source,
  }])),
}));
"""
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=Path(__file__).resolve().parents[1],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)

    assert set(payload["families"]) >= {
        "aluminum",
        "asphalt",
        "ballast",
        "bolt_anchor",
        "concrete",
        "damper",
        "elastomeric_bearing",
        "frp",
        "geosynthetic",
        "grout",
        "ground_improvement",
        "waterproofing",
        "roofing",
        "insulation",
        "fireproofing",
        "coating",
        "sealant_joint",
        "gypsum_board",
        "stone_tile",
        "formwork_shoring",
        "screed_topping",
        "facade_panel",
        "sleeve_embed",
        "rail_sleeper",
        "pot_spherical_bearing",
        "expansion_joint",
        "adhesive_resin",
        "masonry",
        "mass",
        "prestressing",
        "rail_fastener",
        "rail_steel",
        "rebar",
        "resilient_pad",
        "seismic_isolator",
        "soil",
        "spring_link",
        "timber",
    }
    assert payload["coverage"]["status"] == "ready"
    assert payload["coverage"]["known_family_count"] >= 38
    assert payload["coverage"]["ontology_family_count"] >= 45
    assert payload["coverage"]["unclassified_material_count"] == 0
    assert payload["sections"]["S-H"]["family"] == "steel"
    assert payload["sections"]["S-H"]["shape"] == "h_beam"
    assert payload["sections"]["S-WALL"]["family"] == "wall"
    assert payload["sections"]["S-RETAIN"]["shape"] == "retaining_wall"
    assert payload["sections"]["S-DWALL"]["shape"] == "diaphragm_wall"
    assert payload["sections"]["S-PARAPET"]["shape"] == "parapet"
    assert payload["sections"]["S-SLAB"]["family"] == "slab"
    assert payload["sections"]["S-STAIR"]["shape"] == "stair"
    assert payload["sections"]["S-RAMP"]["shape"] == "ramp"
    assert payload["sections"]["S-BALCONY"]["shape"] == "balcony"
    assert payload["sections"]["S-MEGA"]["shape"] == "mega_column"
    assert payload["sections"]["S-SPANDREL"]["shape"] == "spandrel_beam"
    assert payload["sections"]["S-LINTEL"]["shape"] == "lintel"
    assert payload["sections"]["S-JOIST"]["shape"] == "joist"
    assert payload["sections"]["S-PURLIN"]["shape"] == "purlin_girt"
    assert payload["sections"]["S-RAFTER"]["shape"] == "rafter"
    assert payload["sections"]["S-BRB"]["shape"] == "buckling_restrained_brace"
    assert payload["sections"]["S-TRUSS"]["family"] == "truss"
    assert payload["sections"]["S-OUTRIGGER"]["family"] == "outrigger"
    assert payload["sections"]["S-COLLECTOR"]["family"] == "diaphragm"
    assert payload["sections"]["S-TIEBACK"]["family"] == "strut_tie"
    assert payload["sections"]["S-BASEPLATE"]["shape"] == "base_plate"
    assert payload["sections"]["S-GUSSET"]["shape"] == "gusset_plate"
    assert payload["sections"]["S-CABLE"]["family"] == "cable"
    assert payload["sections"]["S-FOOTING"]["family"] == "foundation"
    assert payload["sections"]["S-MAT"]["shape"] == "mat_foundation"
    assert payload["sections"]["S-DAMPER"]["family"] == "link_device"
    assert payload["sections"]["S-ISOLATOR"]["shape"] == "isolator"
    assert payload["sections"]["S-RAIL"]["family"] == "rail"
    assert payload["sections"]["S-SEGMENT"]["shape"] == "segment_lining"
