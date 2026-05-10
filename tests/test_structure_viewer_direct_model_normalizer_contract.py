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
    assert payload["catalog"][0]["raw_tokens_head"] == ["H-400x200", "SM355"]
