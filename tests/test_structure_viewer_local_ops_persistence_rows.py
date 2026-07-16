from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_normalized_rows_are_whitelisted_capped_and_dropped_before_manifest() -> None:
    script = """
import {
  VIEWER_LOCAL_OPS_MAX_NORMALIZED_ROWS,
  prepareViewerLocalOpsStateForStorage,
} from './src/structure-viewer/viewer-local-ops-persistence-policy.js';

const rows = Array.from(
  {length: VIEWER_LOCAL_OPS_MAX_NORMALIZED_ROWS + 2},
  (_, index) => ({
    frame: `F-${index}`,
    frame_section: 'W14X90',
    dcr_after: 0.75,
    story: 'L10',
    mode: 'M1',
    source_tool: 'ETABS 22',
    source_tool_profile: 'etabs',
    artifact_path: 'etabs.csv',
    raw_marker: `SECRET_ROW_${index}`,
    nested: {marker: `SECRET_NESTED_${index}`},
  }),
);
const bounded = prepareViewerLocalOpsStateForStorage({
  lastIngestPreview: {
    schema_version: 'structure-viewer-evidence-ingest-preview.v1',
    source_type: 'csv',
    generated_at: '2026-07-16T00:00:00Z',
    normalized_rows: rows,
    commercial_tool_profiles: {etabs: rows.length},
    manifest: {projects: [{project_id: 'project'}]},
    blocked_issues: [],
  },
});

const hugeRows = Array.from(
  {length: VIEWER_LOCAL_OPS_MAX_NORMALIZED_ROWS},
  (_, index) => ({
    frame: `F-${index}`,
    label: `safe-${index}-${'x'.repeat(5000)}`,
    source_tool_profile: 'etabs',
  }),
);
const degraded = prepareViewerLocalOpsStateForStorage({
  lastIngestPreview: {
    schema_version: 'structure-viewer-evidence-ingest-preview.v1',
    source_type: 'csv',
    generated_at: '2026-07-16T00:00:01Z',
    normalized_rows: hugeRows,
    commercial_tool_profiles: {etabs: hugeRows.length},
    manifest: {projects: [{project_id: 'project', marker: 'KEEP_MANIFEST'}]},
    blocked_issues: [],
  },
});

console.log(JSON.stringify({
  maxRows: VIEWER_LOCAL_OPS_MAX_NORMALIZED_ROWS,
  bounded: {
    valid: bounded.valid,
    degraded: bounded.degraded_fields,
    count: bounded.state.lastIngestPreview.normalized_rows.length,
    first: bounded.state.lastIngestPreview.normalized_rows[0],
    last: bounded.state.lastIngestPreview.normalized_rows.at(-1),
    persisted: bounded.state.lastIngestPreview.normalized_rows_persisted,
    serialized: JSON.stringify(bounded.state),
  },
  degraded: {
    valid: degraded.valid,
    degraded: degraded.degraded_fields,
    hasRows: Object.prototype.hasOwnProperty.call(
      degraded.state.lastIngestPreview,
      'normalized_rows',
    ),
    persisted: degraded.state.lastIngestPreview.normalized_rows_persisted,
    manifest: degraded.state.lastIngestPreview.manifest,
    serialized: JSON.stringify(degraded.state),
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

    assert payload["maxRows"] == 1000
    bounded = payload["bounded"]
    assert bounded["valid"] is True
    assert bounded["degraded"] == []
    assert bounded["count"] == 1000
    assert bounded["persisted"] is True
    expected_fields = {
        "frame",
        "frame_section",
        "dcr_after",
        "story",
        "mode",
        "source_tool",
        "source_tool_profile",
        "artifact_path",
    }
    assert set(bounded["first"]) == expected_fields
    assert bounded["first"]["frame"] == "F-0"
    assert bounded["last"]["frame"] == "F-999"
    assert "SECRET_ROW_" not in bounded["serialized"]
    assert "SECRET_NESTED_" not in bounded["serialized"]

    degraded = payload["degraded"]
    assert degraded["valid"] is True
    assert degraded["degraded"] == ["lastIngestPreview.normalized_rows"]
    assert degraded["hasRows"] is False
    assert degraded["persisted"] is False
    assert degraded["manifest"]["projects"][0]["marker"] == "KEEP_MANIFEST"
    assert "safe-0-" not in degraded["serialized"]
