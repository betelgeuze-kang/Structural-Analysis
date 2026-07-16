from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_local_ops_persistence_deduplicates_payloads_and_preserves_safe_state() -> None:
    script = """
import {
  VIEWER_LOCAL_OPS_PERSISTENCE_POLICY,
  prepareViewerLocalOpsStateForStorage,
  viewerLocalOpsPersistenceLimits,
} from './src/structure-viewer/viewer-local-ops-persistence-policy.js';
import {
  VIEWER_PROJECT_BUNDLE_MAX_RECEIPTS,
  VIEWER_PROJECT_BUNDLE_MAX_SERIALIZED_BYTES,
  inspectViewerProjectBundleLocalState,
} from './src/structure-viewer/viewer-project-bundle-state-policy.js';
import {
  buildViewerProjectBundleExport,
  mergeViewerEvidenceIngestPreview,
  readViewerLocalOpsState,
  writeViewerLocalOpsState,
} from './src/structure-viewer/viewer-local-ops-state.js';

function receiptRows(count, prefix = 'receipt') {
  return Object.fromEntries(
    Array.from({length: count}, (_, index) => [
      `${prefix}-${index}`,
      {
        project_id: 'project',
        drawing_id: 'drawing',
        member_id: `${prefix}-${index}`,
        receipt_path: `receipts/${prefix}-${index}.json`,
      },
    ]),
  );
}

function previewWithPayload(payload, overrides = {}) {
  return {
    schema_version: 'structure-viewer-evidence-ingest-preview.v1',
    source_type: 'json',
    generated_at: '2026-07-16T00:00:00Z',
    resource_policy: 'structure_viewer_evidence_ingest_budget_v1',
    resource_limits: {max_text_bytes: 67108864},
    ingest_text_byte_count: 100,
    row_count: 1,
    drawing_count: 1,
    normalized_rows: [{raw_marker: 'NORMALIZED_ROW_COPY'}],
    commercial_tool_profiles: {generic: 1},
    crosswalk_candidate_count: 0,
    blocked_issues: [],
    manifest: {
      schema_version: 'structure-viewer-project-manifest.v1',
      generated_at: '2026-07-16T00:00:00Z',
      projects: [{
        project_id: 'project',
        drawings: [{
          drawing_id: 'drawing',
          solver_receipts: [],
        }],
      }],
    },
    renderable_payload_available: true,
    renderable_payload_kind: 'direct_model',
    renderable_payload_validation_status: 'basic_shape_only',
    renderable_payload_error_code: '',
    renderable_payload_error_path: '',
    renderable_payload_model_identity: null,
    renderable_node_count: 2,
    renderable_element_count: 1,
    renderable_segment_count: 0,
    ingest_file_read: {
      contract: 'structure_viewer_evidence_file_read_v1',
      resource_policy: 'structure_viewer_evidence_ingest_budget_v1',
      file_name: 'model.json',
      file_size: 100,
      text_byte_length: 100,
    },
    renderable_payload: payload,
    ...overrides,
  };
}

const rawPayload = {
  schema_version: 'structure-viewer-renderable-ingest-payload.v1',
  payload_kind: 'direct_model',
  marker: 'RAW_RENDERABLE_MARKER',
  payload: {
    model: {
      nodes: [{id: 1}, {id: 2}],
      elements: [{id: 'E1'}],
    },
  },
};
const smallState = {
  recentSelections: [{id: 'selection'}],
  auditEventsJsonl: '{"event":"one"}',
  exportHistory: [{filename: 'one.html'}],
  reviewNotes: {one: 'note'},
  reviewTasks: {one: {status: 'needs_check'}},
  annotations: {one: {text: 'annotation'}},
  receiptIndex: {one: {receipt_path: 'receipts/one.json'}},
  lastIngestPreview: previewWithPayload(rawPayload),
  lastIngestRenderablePayload: rawPayload,
};
const smallPrepared = prepareViewerLocalOpsStateForStorage(smallState);
const smallSerialized = JSON.stringify(smallPrepared.state);
const markerCount = smallSerialized.split('RAW_RENDERABLE_MARKER').length - 1;
const bundle = buildViewerProjectBundleExport({
  state: smallPrepared.state,
  projectId: 'project',
  drawingId: 'drawing',
});

let stored = '';
const written = writeViewerLocalOpsState(smallState, {
  storageGet: () => null,
  storageSet: (_key, value) => { stored = value; },
});
const restored = readViewerLocalOpsState({storageGet: () => stored});

const largeRawMarker = 'SECRET_LARGE_RAW_PAYLOAD';
const largeRaw = {
  marker: largeRawMarker,
  payload: 'x'.repeat(VIEWER_PROJECT_BUNDLE_MAX_SERIALIZED_BYTES + 1),
};
const rawDegraded = prepareViewerLocalOpsStateForStorage({
  lastIngestPreview: previewWithPayload(largeRaw),
  lastIngestRenderablePayload: largeRaw,
});

const largeManifestMarker = 'SECRET_LARGE_MANIFEST';
const manifestDegraded = prepareViewerLocalOpsStateForStorage({
  lastIngestPreview: previewWithPayload(null, {
    renderable_payload_available: false,
    renderable_payload: null,
    manifest: {
      projects: [{marker: largeManifestMarker, payload: 'y'.repeat(VIEWER_PROJECT_BUNDLE_MAX_SERIALIZED_BYTES + 1)}],
    },
  }),
  lastIngestRenderablePayload: null,
});

const importMarker = 'SECRET_IMPORT_PAYLOAD';
const importDegraded = prepareViewerLocalOpsStateForStorage({
  lastImportPreview: {
    schema_version: 'structure-viewer-project-bundle-import-preview.v1',
    source_schema_version: 'structure-viewer-project-bundle.v1',
    project_id: 'project',
    drawing_id: 'drawing',
    variant: 'compare',
    blocked: false,
    issues: [],
    incoming_counts: {},
    state_policy: 'structure_viewer_project_bundle_state_budget_v1',
    state_limits: {},
    local_state_serialized_bytes: VIEWER_PROJECT_BUNDLE_MAX_SERIALIZED_BYTES + 1,
    manifest: {projects: [{marker: importMarker}]},
    local_state: {reviewNotes: {large: 'z'.repeat(VIEWER_PROJECT_BUNDLE_MAX_SERIALIZED_BYTES + 1)}},
  },
});

const impossibleExisting = JSON.stringify({reviewNotes: {safe: 'preserve'}});
let invalidWriteCount = 0;
const invalidWriteResult = writeViewerLocalOpsState({
  reviewNotes: {huge: 'q'.repeat(VIEWER_PROJECT_BUNDLE_MAX_SERIALIZED_BYTES + 1)},
}, {
  storageGet: () => impossibleExisting,
  storageSet: () => { invalidWriteCount += 1; },
});

const existingReceipts = receiptRows(VIEWER_PROJECT_BUNDLE_MAX_RECEIPTS - 1, 'existing');
const overflowReceiptPreview = previewWithPayload(null, {
  renderable_payload_available: false,
  renderable_payload: null,
  manifest: {
    projects: [{
      project_id: 'project',
      drawings: [{
        drawing_id: 'drawing',
        solver_receipts: [
          {project_id: 'project', drawing_id: 'drawing', member_id: 'new-1'},
          {project_id: 'project', drawing_id: 'drawing', member_id: 'new-2'},
        ],
      }],
    }],
  },
});
const receiptCurrent = {receiptIndex: existingReceipts};
const receiptOverflowResult = mergeViewerEvidenceIngestPreview(
  receiptCurrent,
  overflowReceiptPreview,
);

const overwriteKey = 'project::drawing::existing-0';
const allowedReceiptPreview = previewWithPayload(rawPayload, {
  manifest: {
    projects: [{
      project_id: 'project',
      drawings: [{
        drawing_id: 'drawing',
        solver_receipts: [
          {project_id: 'project', drawing_id: 'drawing', member_id: 'existing-0', receipt_path: 'updated.json'},
          {project_id: 'project', drawing_id: 'drawing', member_id: 'new-1', receipt_path: 'new.json'},
        ],
      }],
    }],
  },
});
const allowedReceiptResult = mergeViewerEvidenceIngestPreview(
  receiptCurrent,
  allowedReceiptPreview,
);
const allowedInspection = inspectViewerProjectBundleLocalState(allowedReceiptResult);

console.log(JSON.stringify({
  limits: viewerLocalOpsPersistenceLimits(),
  policy: VIEWER_LOCAL_OPS_PERSISTENCE_POLICY,
  small: {
    valid: smallPrepared.valid,
    degraded: smallPrepared.degraded_fields,
    markerCount,
    hasNestedPayload: Object.prototype.hasOwnProperty.call(smallPrepared.state.lastIngestPreview, 'renderable_payload'),
    hasNormalizedRows: Object.prototype.hasOwnProperty.call(smallPrepared.state.lastIngestPreview, 'normalized_rows'),
    manifestPreserved: Boolean(smallPrepared.state.lastIngestPreview.manifest),
    rawPreserved: smallPrepared.state.lastIngestRenderablePayload?.marker || '',
    persistedFlag: smallPrepared.state.lastIngestPreview.renderable_payload_persisted,
    written,
    restored,
    bundleMarkerCount: bundle.json.split('RAW_RENDERABLE_MARKER').length - 1,
  },
  rawDegraded: {
    valid: rawDegraded.valid,
    degraded: rawDegraded.degraded_fields,
    raw: rawDegraded.state.lastIngestRenderablePayload,
    persistedFlag: rawDegraded.state.lastIngestPreview.renderable_payload_persisted,
    manifestPreserved: Boolean(rawDegraded.state.lastIngestPreview.manifest),
    serialized: JSON.stringify(rawDegraded.state),
  },
  manifestDegraded: {
    valid: manifestDegraded.valid,
    degraded: manifestDegraded.degraded_fields,
    manifest: manifestDegraded.state.lastIngestPreview.manifest,
    persistence: manifestDegraded.state.lastIngestPreview.preview_persistence,
    serialized: JSON.stringify(manifestDegraded.state),
  },
  importDegraded: {
    valid: importDegraded.valid,
    degraded: importDegraded.degraded_fields,
    preview: importDegraded.state.lastImportPreview,
    serialized: JSON.stringify(importDegraded.state),
  },
  invalidWrite: {
    writeCount: invalidWriteCount,
    result: invalidWriteResult,
  },
  receiptOverflow: {
    sameObject: receiptOverflowResult === receiptCurrent,
    count: Object.keys(receiptOverflowResult.receiptIndex).length,
  },
  receiptAllowed: {
    sameObject: allowedReceiptResult === receiptCurrent,
    valid: allowedInspection.valid,
    count: Object.keys(allowedReceiptResult.receiptIndex).length,
    overwrite: allowedReceiptResult.receiptIndex[overwriteKey],
    hasNestedPayload: Object.prototype.hasOwnProperty.call(allowedReceiptResult.lastIngestPreview, 'renderable_payload'),
    markerCount: JSON.stringify(allowedReceiptResult).split('RAW_RENDERABLE_MARKER').length - 1,
  },
}));
"""
    completed = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )
    payload = json.loads(completed.stdout)

    assert payload["policy"] == "structure_viewer_local_ops_persistence_v1"
    assert payload["limits"]["state_policy"] == (
        "structure_viewer_project_bundle_state_budget_v1"
    )
    assert payload["limits"]["state_limits"]["max_serialized_bytes"] == (
        4 * 1024 * 1024
    )

    small = payload["small"]
    assert small["valid"] is True
    assert small["degraded"] == []
    assert small["markerCount"] == 1
    assert small["hasNestedPayload"] is False
    assert small["hasNormalizedRows"] is False
    assert small["manifestPreserved"] is True
    assert small["rawPreserved"] == "RAW_RENDERABLE_MARKER"
    assert small["persistedFlag"] is True
    assert small["bundleMarkerCount"] == 1
    assert small["written"] == small["restored"]
    assert small["restored"]["lastIngestPreview"][
        "renderable_payload_persisted"
    ] is True

    raw_degraded = payload["rawDegraded"]
    assert raw_degraded["valid"] is True
    assert raw_degraded["degraded"] == ["lastIngestRenderablePayload"]
    assert raw_degraded["raw"] is None
    assert raw_degraded["persistedFlag"] is False
    assert raw_degraded["manifestPreserved"] is True
    assert largeRawMarker not in raw_degraded["serialized"]

    manifest_degraded = payload["manifestDegraded"]
    assert manifest_degraded["valid"] is True
    assert manifest_degraded["degraded"] == ["lastIngestPreview.manifest"]
    assert manifest_degraded["manifest"] is None
    assert manifest_degraded["persistence"] == "summary_only_state_budget"
    assert largeManifestMarker not in manifest_degraded["serialized"]

    import_degraded = payload["importDegraded"]
    assert import_degraded["valid"] is True
    assert import_degraded["degraded"] == [
        "lastImportPreview.local_state",
        "lastImportPreview.manifest",
    ]
    assert import_degraded["preview"]["blocked"] is True
    assert import_degraded["preview"]["local_state"] == {}
    assert import_degraded["preview"]["manifest"] is None
    assert import_degraded["preview"]["preview_persistence"] == (
        "summary_only_state_budget"
    )
    assert importMarker not in import_degraded["serialized"]

    invalid_write = payload["invalidWrite"]
    assert invalid_write["writeCount"] == 0
    assert invalid_write["result"]["reviewNotes"] == {"safe": "preserve"}

    overflow = payload["receiptOverflow"]
    assert overflow["sameObject"] is True
    assert overflow["count"] == 499

    allowed = payload["receiptAllowed"]
    assert allowed["sameObject"] is False
    assert allowed["valid"] is True
    assert allowed["count"] == 500
    assert allowed["overwrite"]["receipt_path"] == "updated.json"
    assert allowed["hasNestedPayload"] is False
    assert allowed["markerCount"] == 1
