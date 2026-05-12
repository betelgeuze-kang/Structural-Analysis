from __future__ import annotations

import json
import subprocess
from pathlib import Path


def test_viewer_direct_model_normalizer_preserves_midas_metadata_contract() -> None:
    script = """
import {
  buildSectionCatalogSummary,
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
      {id: 'E1', type: 'beam', node_ids: [10, 11], section_id: 'S1', dcr: '0.92'}
    ],
    sections: [
      {id: 'S1', section_name: 'H-400x200', raw_tokens: ['H-400x200', 'SM355']}
    ],
    metadata: {
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
  artifact.model.metadata.section_library.usage_summary
);

console.log(JSON.stringify({
  directMode: direct.meta.normalization_mode,
  chunkedMode: chunked.meta.normalization_mode,
  chunkCalls,
  element: direct.elements[0],
  meta: direct.meta,
  catalog,
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
    assert meta["load_case_inventory"] == ["DEAD"]
    assert meta["load_combination_inventory"][0]["name"] == "COMBO1"
    assert meta["section_catalog_summary"][0]["display_label"] == "H-400x200"
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
