from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_project_bundle_state_limits_block_oversized_preview_and_merge_bypasses() -> None:
    script = """
import {
  VIEWER_PROJECT_BUNDLE_MAX_ANNOTATIONS,
  VIEWER_PROJECT_BUNDLE_MAX_AUDIT_LINES,
  VIEWER_PROJECT_BUNDLE_MAX_EXPORT_HISTORY,
  VIEWER_PROJECT_BUNDLE_MAX_RECEIPTS,
  VIEWER_PROJECT_BUNDLE_MAX_RECENT_SELECTIONS,
  VIEWER_PROJECT_BUNDLE_MAX_REVIEW_NOTES,
  VIEWER_PROJECT_BUNDLE_MAX_REVIEW_TASKS,
  VIEWER_PROJECT_BUNDLE_MAX_SERIALIZED_BYTES,
  VIEWER_PROJECT_BUNDLE_STATE_POLICY,
  inspectViewerProjectBundleLocalState,
  mergeViewerProjectBundleLocalState,
  viewerProjectBundleStateLimits,
} from './src/structure-viewer/viewer-project-bundle-state-policy.js';
import {
  buildViewerProjectBundleImportPreview,
  mergeViewerProjectBundleImport,
} from './src/structure-viewer/viewer-local-ops-state.js';

function objectRows(prefix, count, valueFactory = (index) => ({index})) {
  return Object.fromEntries(
    Array.from({length: count}, (_, index) => [`${prefix}-${index}`, valueFactory(index)]),
  );
}

function lines(prefix, count) {
  return Array.from({length: count}, (_, index) => `${prefix}-${index}`).join('\\n');
}

const limits = viewerProjectBundleStateLimits();
const exactState = {
  recentSelections: Array.from({length: VIEWER_PROJECT_BUNDLE_MAX_RECENT_SELECTIONS}, (_, index) => ({index})),
  auditEventsJsonl: lines('audit', VIEWER_PROJECT_BUNDLE_MAX_AUDIT_LINES),
  exportHistory: Array.from({length: VIEWER_PROJECT_BUNDLE_MAX_EXPORT_HISTORY}, (_, index) => ({index})),
  reviewNotes: objectRows('note', VIEWER_PROJECT_BUNDLE_MAX_REVIEW_NOTES, (index) => `note-${index}`),
  reviewTasks: objectRows('task', VIEWER_PROJECT_BUNDLE_MAX_REVIEW_TASKS),
  annotations: objectRows('annotation', VIEWER_PROJECT_BUNDLE_MAX_ANNOTATIONS),
  receiptIndex: objectRows('receipt', VIEWER_PROJECT_BUNDLE_MAX_RECEIPTS, (index) => ({
    member_id: `M-${index}`,
    receipt_path: `receipts/${index}.json`,
  })),
};
const exactInspection = inspectViewerProjectBundleLocalState(exactState);

const overflowCases = {
  recent: inspectViewerProjectBundleLocalState({
    recentSelections: new Array(VIEWER_PROJECT_BUNDLE_MAX_RECENT_SELECTIONS + 1).fill({}),
  }),
  audit: inspectViewerProjectBundleLocalState({
    auditEventsJsonl: lines('audit', VIEWER_PROJECT_BUNDLE_MAX_AUDIT_LINES + 1),
  }),
  exportHistory: inspectViewerProjectBundleLocalState({
    exportHistory: new Array(VIEWER_PROJECT_BUNDLE_MAX_EXPORT_HISTORY + 1).fill({}),
  }),
  reviewNotes: inspectViewerProjectBundleLocalState({
    reviewNotes: objectRows('note', VIEWER_PROJECT_BUNDLE_MAX_REVIEW_NOTES + 1),
  }),
  reviewTasks: inspectViewerProjectBundleLocalState({
    reviewTasks: objectRows('task', VIEWER_PROJECT_BUNDLE_MAX_REVIEW_TASKS + 1),
  }),
  annotations: inspectViewerProjectBundleLocalState({
    annotations: objectRows('annotation', VIEWER_PROJECT_BUNDLE_MAX_ANNOTATIONS + 1),
  }),
  receipts: inspectViewerProjectBundleLocalState({
    receiptIndex: objectRows('receipt', VIEWER_PROJECT_BUNDLE_MAX_RECEIPTS + 1),
  }),
  bytes: inspectViewerProjectBundleLocalState({
    lastIngestPreview: {payload: 'x'.repeat(VIEWER_PROJECT_BUNDLE_MAX_SERIALIZED_BYTES + 1)},
  }),
  auditType: inspectViewerProjectBundleLocalState({auditEventsJsonl: {not: 'text'}}),
  circular: (() => {
    const state = {};
    state.self = state;
    return inspectViewerProjectBundleLocalState(state);
  })(),
};

const secretTasks = objectRows(
  'task',
  VIEWER_PROJECT_BUNDLE_MAX_REVIEW_TASKS + 1,
  (index) => ({note: index === 0 ? 'SECRET_IMPORT_STATE_MARKER' : `task-${index}`}),
);
const blockedPreview = buildViewerProjectBundleImportPreview({
  schema_version: 'structure-viewer-project-bundle.v1',
  project_id: 'project',
  drawing_id: 'drawing',
  local_state: {reviewTasks: secretTasks},
});

const validPreview = buildViewerProjectBundleImportPreview({
  schema_version: 'structure-viewer-project-bundle.v1',
  project_id: 'project',
  drawing_id: 'drawing',
  local_state: {
    recentSelections: [{projectId: 'project', drawingId: 'drawing'}],
    auditEventsJsonl: '{"type":"one"}',
    reviewNotes: {'project::drawing::M1': 'review'},
    reviewTasks: {'project::drawing::M1': {status: 'needs_check'}},
    annotations: {'project::drawing::M1': {text: 'annotation'}},
    receiptIndex: {'project::drawing::M1': {member_id: 'M1', receipt_path: 'receipts/M1.json'}},
  },
});

const current = {
  recentSelections: Array.from({length: 8}, (_, index) => ({id: `current-${index}`})),
  auditEventsJsonl: lines('current-audit', 60),
  exportHistory: Array.from({length: 15}, (_, index) => ({id: `current-export-${index}`})),
  reviewNotes: objectRows('current-note', 70, (index) => `current-${index}`),
  reviewTasks: objectRows('current-task', 180),
  annotations: objectRows('current-annotation', 480),
  receiptIndex: objectRows('current-receipt', 480),
};
const incoming = {
  recentSelections: Array.from({length: 8}, (_, index) => ({id: `incoming-${index}`})),
  auditEventsJsonl: lines('incoming-audit', 40),
  exportHistory: Array.from({length: 10}, (_, index) => ({id: `incoming-export-${index}`})),
  reviewNotes: {
    ...objectRows('incoming-note', 20, (index) => `incoming-${index}`),
    'current-note-69': 'incoming-override',
  },
  reviewTasks: objectRows('incoming-task', 30),
  annotations: objectRows('incoming-annotation', 30),
  receiptIndex: objectRows('incoming-receipt', 30),
};
const validMergePreview = {
  schema_version: 'structure-viewer-project-bundle-import-preview.v1',
  source_schema_version: 'structure-viewer-project-bundle.v1',
  project_id: 'project',
  drawing_id: 'drawing',
  variant: 'optimized',
  blocked: false,
  issues: [],
  incoming_counts: {},
  state_policy: VIEWER_PROJECT_BUNDLE_STATE_POLICY,
  state_limits: limits,
  local_state_serialized_bytes: JSON.stringify(incoming).length,
  manifest: {projects: [{project_id: 'SECRET_MANIFEST_SHOULD_NOT_PERSIST'}]},
  local_state: incoming,
};
const merged = mergeViewerProjectBundleImport(current, validMergePreview);
const mergedInspection = inspectViewerProjectBundleLocalState(merged);

const craftedInvalidPreview = {
  blocked: false,
  local_state: {
    receiptIndex: objectRows(
      'receipt',
      VIEWER_PROJECT_BUNDLE_MAX_RECEIPTS + 1,
      (index) => ({marker: index === 0 ? 'SECRET_CRAFTED_MARKER' : index}),
    ),
  },
};
const craftedCurrent = {reviewNotes: {safe: 'preserve'}};
const craftedResult = mergeViewerProjectBundleImport(craftedCurrent, craftedInvalidPreview);

const invalidCurrent = {
  reviewNotes: objectRows('note', VIEWER_PROJECT_BUNDLE_MAX_REVIEW_NOTES + 1),
};
const invalidCurrentResult = mergeViewerProjectBundleLocalState(
  invalidCurrent,
  {reviewNotes: {incoming: 'value'}},
);

console.log(JSON.stringify({
  limits,
  exactInspection,
  overflowCases,
  blockedPreview: {
    blocked: blockedPreview.blocked,
    issues: blockedPreview.issues,
    incomingCounts: blockedPreview.incoming_counts,
    localState: blockedPreview.local_state,
    serialized: JSON.stringify(blockedPreview),
  },
  validPreview: {
    blocked: validPreview.blocked,
    incomingCounts: validPreview.incoming_counts,
    statePolicy: validPreview.state_policy,
    stateLimits: validPreview.state_limits,
    localState: validPreview.local_state,
  },
  merged: {
    sameObject: merged === current,
    counts: mergedInspection.counts,
    valid: mergedInspection.valid,
    override: merged.reviewNotes['current-note-69'],
    hasIncomingNewest: Object.prototype.hasOwnProperty.call(merged.reviewNotes, 'incoming-note-19'),
    lastImportPreview: merged.lastImportPreview,
    serialized: JSON.stringify(merged),
  },
  crafted: {
    sameObject: craftedResult === craftedCurrent,
    state: craftedResult,
    serialized: JSON.stringify(craftedResult),
  },
  invalidCurrent: {
    valid: invalidCurrentResult.valid,
    sameObject: invalidCurrentResult.state === invalidCurrent,
    source: invalidCurrentResult.source,
    issueCodes: invalidCurrentResult.inspection.issues.map((row) => row.code),
  },
}));
"""
    completed = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=90,
    )
    payload = json.loads(completed.stdout)

    assert payload["limits"] == {
        "policy": "structure_viewer_project_bundle_state_budget_v1",
        "max_serialized_bytes": 4 * 1024 * 1024,
        "max_recent_selections": 12,
        "max_audit_lines": 80,
        "max_export_history": 20,
        "max_review_notes": 80,
        "max_review_tasks": 200,
        "max_annotations": 500,
        "max_receipts": 500,
    }
    assert payload["exactInspection"]["valid"] is True
    assert payload["exactInspection"]["counts"] == {
        "recentSelections": 12,
        "auditEvents": 80,
        "exportHistory": 20,
        "reviewNotes": 80,
        "reviewTasks": 200,
        "annotations": 500,
        "receiptIndex": 500,
    }

    expected_codes = {
        "recent": "project_bundle_recent_selection_limit_exceeded",
        "audit": "project_bundle_audit_line_limit_exceeded",
        "exportHistory": "project_bundle_export_history_limit_exceeded",
        "reviewNotes": "project_bundle_review_note_limit_exceeded",
        "reviewTasks": "project_bundle_review_task_limit_exceeded",
        "annotations": "project_bundle_annotation_limit_exceeded",
        "receipts": "project_bundle_receipt_limit_exceeded",
        "bytes": "project_bundle_local_state_byte_limit_exceeded",
        "auditType": "project_bundle_local_state_type_invalid",
        "circular": "project_bundle_local_state_serialization_failed",
    }
    for name, code in expected_codes.items():
        inspection = payload["overflowCases"][name]
        assert inspection["valid"] is False
        assert code in [row["code"] for row in inspection["issues"]]

    blocked = payload["blockedPreview"]
    assert blocked["blocked"] is True
    assert blocked["incomingCounts"]["reviewTasks"] == 201
    assert blocked["localState"] == {}
    assert any(
        row["code"] == "project_bundle_review_task_limit_exceeded"
        and row["path"] == "/local_state/reviewTasks"
        for row in blocked["issues"]
    )
    assert "SECRET_IMPORT_STATE_MARKER" not in blocked["serialized"]

    valid_preview = payload["validPreview"]
    assert valid_preview["blocked"] is False
    assert valid_preview["statePolicy"] == payload["limits"]["policy"]
    assert valid_preview["stateLimits"] == payload["limits"]
    assert valid_preview["incomingCounts"] == {
        "recentSelections": 1,
        "auditEvents": 1,
        "exportHistory": 0,
        "reviewNotes": 1,
        "reviewTasks": 1,
        "annotations": 1,
        "receiptIndex": 1,
    }
    assert valid_preview["localState"]["reviewNotes"] == {
        "project::drawing::M1": "review"
    }

    merged = payload["merged"]
    assert merged["sameObject"] is False
    assert merged["valid"] is True
    assert merged["counts"] == {
        "recentSelections": 12,
        "auditEvents": 80,
        "exportHistory": 20,
        "reviewNotes": 80,
        "reviewTasks": 200,
        "annotations": 500,
        "receiptIndex": 500,
    }
    assert merged["override"] == "incoming-override"
    assert merged["hasIncomingNewest"] is True
    assert "local_state" not in merged["lastImportPreview"]
    assert "manifest" not in merged["lastImportPreview"]
    assert "SECRET_MANIFEST_SHOULD_NOT_PERSIST" not in merged["serialized"]

    crafted = payload["crafted"]
    assert crafted["sameObject"] is True
    assert crafted["state"] == {"reviewNotes": {"safe": "preserve"}}
    assert "SECRET_CRAFTED_MARKER" not in crafted["serialized"]

    invalid_current = payload["invalidCurrent"]
    assert invalid_current["valid"] is False
    assert invalid_current["sameObject"] is True
    assert invalid_current["source"] == "current_state"
    assert "project_bundle_review_note_limit_exceeded" in invalid_current[
        "issueCodes"
    ]
