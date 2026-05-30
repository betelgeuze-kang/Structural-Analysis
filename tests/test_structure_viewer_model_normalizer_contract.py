from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _run_node_contract_script(script: str) -> dict:
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def test_viewer_model_normalizer_exports_and_helpers() -> None:
    payload = _run_node_contract_script(
        """
import * as normalizer from './src/structure-viewer/viewer-model-normalizer.js';

const directModel = {nodes:[{id:1,x:0,y:0,z:0}], elements:[{id:2}]};
const nestedModel = {model:{nodes:[{id:1,x:0,y:0,z:0}], elements:[{id:2}]}, meta:{kind:'nested'}};
const nestedInteractive = {
  interactive_3d: {
    baseline_segments:[{p0:[0,0,0], p1:[1,0,0]}],
    after_segments:[{p0:[0,0,0], p1:[0,1,0]}],
    comparison_availability:'compare',
  },
};
const dedupNodes=[];
const dedupIndexByKey=new Map();
const firstId = normalizer.registerSegmentNode([1,2,3], dedupIndexByKey, dedupNodes);
const secondId = normalizer.registerSegmentNode([1,2,3], dedupIndexByKey, dedupNodes);
const directExtract = normalizer.extractModelPayload(directModel);
const nestedExtract = normalizer.extractModelPayload(nestedModel);
const interactiveExtract = normalizer.extractInteractivePayload(nestedInteractive);

console.log(JSON.stringify({
  exports: Object.keys(normalizer).sort(),
  hasDefault: Object.prototype.hasOwnProperty.call(normalizer, 'default'),
  safeNumber: [normalizer.safeNumber('3.5', 0), normalizer.safeNumber('bad', 7)],
  normalizedType: [normalizer.normalizeElementType('  BRACE '), normalizer.normalizeElementType('')],
  modelPayload: {
    directIsModel: normalizer.isModelPayload(directModel),
    directRootSame: directExtract?.model === directModel,
    nestedIsModel: normalizer.isModelPayload(nestedModel),
    nestedRootKind: nestedExtract?.root?.meta?.kind || null,
  },
  interactivePayload: {
    isInteractive: Boolean(interactiveExtract),
    comparisonAvailability: interactiveExtract?.comparison_availability || null,
  },
  normalizedPoint: normalizer.normalizePoint([1, '2', 'bad']),
  invalidPoint: normalizer.normalizePoint([1, 2]),
  dedup: {
    firstId,
    secondId,
    nodeCount: dedupNodes.length,
    node: dedupNodes[0],
  },
  hex: normalizer.rgbArrayToHex([255, 128, 0]),
  storyCount: normalizer.estimateStoryCount([{z:0},{z:4},{z:8},{z:12}], {z:['L1','L2']}),
}));
        """
    )

    assert payload["exports"] == [
        "ELEMENT_TYPE_REGISTRY",
        "buildModelFromInteractivePayload",
        "buildModelFromInteractivePayloadAsync",
        "buildModelFromNativePayload",
        "buildModelFromNativePayloadAsync",
        "estimateStoryCount",
        "extractInteractivePayload",
        "extractModelPayload",
        "extractNativeModelPayload",
        "getElementGeometryKind",
        "isModelPayload",
        "normalizeElementType",
        "normalizePoint",
        "registerSegmentNode",
        "resolveMaterialType",
        "rgbArrayToHex",
        "safeNumber",
    ]
    assert payload["hasDefault"] is False
    assert payload["safeNumber"] == [3.5, 7]
    assert payload["normalizedType"] == ["brace", "beam"]
    assert payload["modelPayload"] == {
        "directIsModel": True,
        "directRootSame": True,
        "nestedIsModel": True,
        "nestedRootKind": "nested",
    }
    assert payload["interactivePayload"] == {
        "isInteractive": True,
        "comparisonAvailability": "compare",
    }
    assert payload["normalizedPoint"] == [1, 2, 0]
    assert payload["invalidPoint"] is None
    assert payload["dedup"]["firstId"] == 0
    assert payload["dedup"]["secondId"] == 0
    assert payload["dedup"]["nodeCount"] == 1
    assert payload["dedup"]["node"] == {
        "id": 0,
        "x": 1,
        "y": 3,
        "z": 2,
        "dx": 0,
        "dy": 0,
        "dz": 0,
        "disp_mag": 0,
        "stress_vm": 0,
        "dcr": 0,
        "axial": 0,
        "moment": 0,
        "shear": 0,
    }
    assert payload["hex"] == "#ff8000"
    assert payload["storyCount"] == 3


def test_viewer_model_normalizer_builds_interactive_models_directly_and_with_chunking() -> None:
    payload = _run_node_contract_script(
        """
import * as normalizer from './src/structure-viewer/viewer-model-normalizer.js';

const interactivePayload = {
  interactive_3d: {
    baseline_segments: [
      {
        member_id: 'B1',
        member_type: 'Beam',
        p0: [0, 0, 0],
        p1: [1, 0, 0],
        section_name: 'BEAM-BEFORE',
        color: ' #112233 ',
        dcr: '1.25',
        axial: '2',
        moment: '3',
        shear: '4',
        story_band_label: 'Basement',
        zone_label: 'Z1',
        action_name: 'baseline',
        optimization_meaning_label: 'keep',
        before_after_snapshot_note: 'before',
      },
      {
        member_id: 'B2',
        member_type: 'Column',
        p0: [1, 0, 0],
        p1: [1, 1, 0],
        section_name: 'COLUMN-BEFORE',
        max_dcr_before: '1.5',
      },
    ],
    after_segments: [
      {
        member_id: 'A1',
        member_type: 'Brace',
        p0: [0, 0, 0],
        p1: [0, 1, 0],
        after_section: 'BRACE-AFTER',
        max_dcr_after: '0.75',
        axial: '5',
        moment: '6',
        shear: '7',
      },
    ],
    story_slice_options: [{label: 'L1'}, {value: 'L2'}],
    axis_refs: {z: [0, 1, 2, 3]},
    comparison_availability: 'baseline_vs_opt',
  },
  case_context: {
    case_id: 'CASE-17',
    case_label: 'Case 17',
    load_combination_count_label: '8',
    load_combination_source_label: 'release-context',
    load_combination_contract_label: '0.3.0',
    load_combination_graph_combo_count_label: '8',
    load_combination_geometry_bridge_summary_label: 'rows exact=1056',
    midas_kds_geometry_bridge_summary_line: 'rows=1056 | exact_rows=1056/1056',
    load_combination_highlights: ['gLCB1'],
    load_combination_graph_node_rows: [
      {
        id: 'COMBO:gLCB1',
        name: 'gLCB1',
        kind: 'combo',
        focus_representative_member_id: '1003',
      },
    ],
    load_combination_codecheck_table_by_name: {
      gLCB1: {
        row_count_label: '1',
        governing_member_label: 'MF-012',
        governing_component_label: 'bending_moment_y_kNm',
        governing_dcr_label: '1.216',
        table_rows: [
          {
            member_id: 'MF-012',
            baseline_focus_member_id: '27441',
            component: 'bending_moment_y_kNm',
            dcr_label: '1.216',
          },
        ],
      },
    },
  },
  generated_at: '2026-05-08T01:23:45+09:00',
};
const sourceMeta = {
  mode: 'fixture-mode',
  label: 'fixture label',
  resolvedPath: '/tmp/interactive.json',
  loadedAt: '2026-05-08T00:00:00+09:00',
};

const direct = normalizer.buildModelFromInteractivePayload(interactivePayload, sourceMeta);
const chunkCalls = [];
const chunked = await normalizer.buildModelFromInteractivePayloadAsync(interactivePayload, sourceMeta, {
  chunkSize: 1,
  processInChunks: async (rows, handler, options) => {
    chunkCalls.push({
      rowCount: rows.length,
      progressLabel: options.progressLabel,
      totalCount: options.totalCount,
      startOffset: options.startOffset ?? 0,
      forceChunking: options.forceChunking,
    });
    rows.forEach((row, index) => handler(row, index));
  },
});

console.log(JSON.stringify({
  direct: {
    nodeCount: direct.nodes.length,
    elementCount: direct.elements.length,
    firstNode: direct.nodes[0],
    firstElement: {
      id: direct.elements[0].id,
      type: direct.elements[0].type,
      color: direct.elements[0].color,
      section: direct.elements[0].section,
      nodeIds: direct.elements[0].node_ids,
      overlayScope: direct.elements[0].overlay_scope,
      dcr: direct.elements[0].dcr,
      axial: direct.elements[0].axial,
      moment: direct.elements[0].moment,
      shear: direct.elements[0].shear,
    },
    meta: {
      name: direct.meta.name,
      sourceMode: direct.meta.source_mode,
      sourceLabel: direct.meta.source_label,
      sourcePath: direct.meta.source_path,
      loadedAt: direct.meta.loaded_at,
      generatedAt: direct.meta.generated_at,
      normalizationMode: direct.meta.normalization_mode,
      comparisonAvailability: direct.meta.comparison_availability,
      storySlices: direct.meta.story_slices,
      baselineSegmentCount: direct.meta.baseline_segment_count,
      optimizedSegmentCount: direct.meta.optimized_segment_count,
      stories: direct.meta.stories,
      loadCombinationCount: direct.meta.load_combination_count_label,
      loadCombinationSource: direct.meta.load_combination_source_label,
      loadCombinationContract: direct.meta.load_combination_contract_label,
      loadCombinationGraphComboCount: direct.meta.load_combination_graph_combo_count_label,
      loadCombinationBridgeSummary: direct.meta.load_combination_geometry_bridge_summary_label,
      midasKdsBridgeSummary: direct.meta.midas_kds_geometry_bridge_summary_line,
      loadCombinationHighlightCount: direct.meta.load_combination_highlights.length,
      loadCombinationGraphNodeCount: direct.meta.load_combination_graph_node_rows.length,
      loadCombinationGraphFocus: direct.meta.load_combination_graph_node_rows[0].focus_representative_member_id,
      loadCombinationCodecheckKeys: Object.keys(direct.meta.load_combination_codecheck_table_by_name),
      loadCombinationCodecheckRows: direct.meta.load_combination_codecheck_table_by_name.gLCB1.table_rows.length,
      loadCombinationCodecheckFocus: direct.meta.load_combination_codecheck_table_by_name.gLCB1.table_rows[0].baseline_focus_member_id,
    },
  },
  chunked: {
    nodeCount: chunked.nodes.length,
    elementCount: chunked.elements.length,
    meta: {
      name: chunked.meta.name,
      sourceMode: chunked.meta.source_mode,
      sourceLabel: chunked.meta.source_label,
      sourcePath: chunked.meta.source_path,
      loadedAt: chunked.meta.loaded_at,
      generatedAt: chunked.meta.generated_at,
      normalizationMode: chunked.meta.normalization_mode,
      comparisonAvailability: chunked.meta.comparison_availability,
      storySlices: chunked.meta.story_slices,
      baselineSegmentCount: chunked.meta.baseline_segment_count,
      optimizedSegmentCount: chunked.meta.optimized_segment_count,
      stories: chunked.meta.stories,
      loadCombinationCount: chunked.meta.load_combination_count_label,
      loadCombinationGraphNodeCount: chunked.meta.load_combination_graph_node_rows.length,
      loadCombinationCodecheckRows: chunked.meta.load_combination_codecheck_table_by_name.gLCB1.table_rows.length,
    },
  },
  chunkCalls,
}));
        """
    )

    assert payload["direct"]["nodeCount"] == 4
    assert payload["direct"]["elementCount"] == 3
    assert payload["direct"]["firstNode"] == {
        "id": 0,
        "x": 0,
        "y": 0,
        "z": 0,
        "dx": 0,
        "dy": 0,
        "dz": 0,
        "disp_mag": 0,
        "stress_vm": 0,
        "dcr": 0,
        "axial": 0,
        "moment": 0,
        "shear": 0,
    }
    assert payload["direct"]["firstElement"] == {
        "id": "baseline:B1:0",
        "type": "beam",
        "color": "#112233",
        "section": "BEAM-BEFORE",
        "nodeIds": [0, 1],
        "overlayScope": "baseline",
        "dcr": 1.25,
        "axial": 2,
        "moment": 3,
        "shear": 4,
    }
    assert payload["direct"]["meta"] == {
        "name": "CASE-17",
        "sourceMode": "fixture-mode",
        "sourceLabel": "fixture label",
        "sourcePath": "/tmp/interactive.json",
        "loadedAt": "2026-05-08T00:00:00+09:00",
        "generatedAt": "2026-05-08T01:23:45+09:00",
        "normalizationMode": "direct",
        "comparisonAvailability": "baseline_vs_opt",
        "storySlices": ["L1", "L2"],
        "baselineSegmentCount": 2,
        "optimizedSegmentCount": 1,
        "stories": 4,
        "loadCombinationCount": "8",
        "loadCombinationSource": "release-context",
        "loadCombinationContract": "0.3.0",
        "loadCombinationGraphComboCount": "8",
        "loadCombinationBridgeSummary": "rows exact=1056",
        "midasKdsBridgeSummary": "rows=1056 | exact_rows=1056/1056",
        "loadCombinationHighlightCount": 1,
        "loadCombinationGraphNodeCount": 1,
        "loadCombinationGraphFocus": "1003",
        "loadCombinationCodecheckKeys": ["gLCB1"],
        "loadCombinationCodecheckRows": 1,
        "loadCombinationCodecheckFocus": "27441",
    }
    assert payload["chunked"]["nodeCount"] == 4
    assert payload["chunked"]["elementCount"] == 3
    assert payload["chunked"]["meta"] == {
        "name": "CASE-17",
        "sourceMode": "fixture-mode",
        "sourceLabel": "fixture label",
        "sourcePath": "/tmp/interactive.json",
        "loadedAt": "2026-05-08T00:00:00+09:00",
        "generatedAt": "2026-05-08T01:23:45+09:00",
        "normalizationMode": "chunked",
        "comparisonAvailability": "baseline_vs_opt",
        "storySlices": ["L1", "L2"],
        "baselineSegmentCount": 2,
        "optimizedSegmentCount": 1,
        "stories": 4,
        "loadCombinationCount": "8",
        "loadCombinationGraphNodeCount": 1,
        "loadCombinationCodecheckRows": 1,
    }
    assert payload["chunkCalls"] == [
        {
            "rowCount": 2,
            "progressLabel": "Normalizing interactive_3d segments",
            "totalCount": 3,
            "startOffset": 0,
            "forceChunking": True,
        },
        {
            "rowCount": 1,
            "progressLabel": "Normalizing interactive_3d segments",
            "totalCount": 3,
            "startOffset": 2,
            "forceChunking": True,
        },
    ]
