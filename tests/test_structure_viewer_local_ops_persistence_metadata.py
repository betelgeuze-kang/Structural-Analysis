from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_persistence_whitelists_nested_preview_metadata() -> None:
    script = """
import {
  VIEWER_LOCAL_OPS_MAX_ISSUE_FLAGS,
  prepareViewerLocalOpsStateForStorage,
} from './src/structure-viewer/viewer-local-ops-persistence-policy.js';

const flags = Array.from({length: VIEWER_LOCAL_OPS_MAX_ISSUE_FLAGS + 5}, (_, index) => `flag-${index}`);
const state = {
  lastIngestPreview: {
    schema_version: 'structure-viewer-evidence-ingest-preview.v1',
    source_type: 'json',
    generated_at: '2026-07-16T00:00:00Z',
    resource_policy: 'structure_viewer_evidence_ingest_budget_v1',
    resource_limits: {
      policy: 'structure_viewer_evidence_ingest_budget_v1',
      max_text_bytes: 100,
      injected: 'SECRET_RESOURCE_LIMIT',
      nested: {marker: 'SECRET_RESOURCE_NESTED'},
    },
    commercial_tool_profiles: {
      generic: 1,
      invalid: 'SECRET_PROFILE_VALUE',
    },
    blocked_issues: [{
      severity: 'critical',
      issue: 'blocked input',
      value: 'code@path',
      code: 'blocked_code',
      path: '/payload',
      drawing_id: 'drawing-1',
      quality_flags: flags,
      text: 'SECRET_ISSUE_TEXT',
      nested: {marker: 'SECRET_ISSUE_NESTED'},
    }],
    renderable_payload_model_identity: {
      identity_policy: 'source_bytes_and_detached_canonical_model_v1',
      source_input_checksum: `sha256:${'a'.repeat(64)}`,
      canonical_model_checksum: `sha256:${'b'.repeat(64)}`,
      analysis_input_snapshot: 'detached_canonical_model_v1',
      text: 'SECRET_IDENTITY_TEXT',
      nested: {marker: 'SECRET_IDENTITY_NESTED'},
    },
    ingest_file_read: {
      contract: 'structure_viewer_evidence_file_read_v1',
      resource_policy: 'structure_viewer_evidence_ingest_budget_v1',
      file_name: 'model.json',
      file_size: 100,
      file_type: 'application/json',
      last_modified: 123,
      text_byte_length: 100,
      status: 'ready',
      error_code: '',
      error_path: '',
      text: 'SECRET_FILE_TEXT',
      payload: {marker: 'SECRET_FILE_PAYLOAD'},
      nested: {marker: 'SECRET_FILE_NESTED'},
    },
  },
  lastImportPreview: {
    schema_version: 'structure-viewer-project-bundle-import-preview.v1',
    source_schema_version: 'structure-viewer-project-bundle.v1',
    project_id: 'project',
    drawing_id: 'drawing',
    variant: 'compare',
    blocked: true,
    issues: [{
      severity: 'critical',
      issue: 'import blocked',
      code: 'import_code',
      path: '/local_state',
      raw: 'SECRET_IMPORT_ISSUE',
    }],
    incoming_counts: {
      reviewTasks: 2,
      receiptIndex: 3,
      injected: 'SECRET_INCOMING_COUNT',
      nested: {marker: 'SECRET_INCOMING_NESTED'},
    },
    state_policy: 'structure_viewer_project_bundle_state_budget_v1',
    state_limits: {
      policy: 'structure_viewer_project_bundle_state_budget_v1',
      max_review_tasks: 200,
      injected: 'SECRET_STATE_LIMIT',
    },
    local_state_serialized_bytes: 20,
    manifest: null,
    local_state: {},
    file_read: {
      contract: 'structure_viewer_project_bundle_file_read_v1',
      resource_policy: 'structure_viewer_project_bundle_budget_v1',
      file_name: 'bundle.json',
      file_size: 20,
      text_byte_length: 20,
      text: 'SECRET_IMPORT_FILE_TEXT',
      payload: {marker: 'SECRET_IMPORT_FILE_PAYLOAD'},
    },
  },
};
const prepared = prepareViewerLocalOpsStateForStorage(state);
const serialized = JSON.stringify(prepared.state);
const ingest = prepared.state.lastIngestPreview;
const imported = prepared.state.lastImportPreview;
console.log(JSON.stringify({
  valid: prepared.valid,
  serialized,
  ingest: {
    resourceLimits: ingest.resource_limits,
    toolProfiles: ingest.commercial_tool_profiles,
    issue: ingest.blocked_issues[0],
    identity: ingest.renderable_payload_model_identity,
    fileRead: ingest.ingest_file_read,
  },
  imported: {
    issue: imported.issues[0],
    incomingCounts: imported.incoming_counts,
    stateLimits: imported.state_limits,
    fileRead: imported.file_read,
  },
}));
"""
    completed = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    payload = json.loads(completed.stdout)

    assert payload["valid"] is True
    for marker in (
        "SECRET_RESOURCE_LIMIT",
        "SECRET_RESOURCE_NESTED",
        "SECRET_PROFILE_VALUE",
        "SECRET_ISSUE_TEXT",
        "SECRET_ISSUE_NESTED",
        "SECRET_IDENTITY_TEXT",
        "SECRET_IDENTITY_NESTED",
        "SECRET_FILE_TEXT",
        "SECRET_FILE_PAYLOAD",
        "SECRET_FILE_NESTED",
        "SECRET_IMPORT_ISSUE",
        "SECRET_INCOMING_COUNT",
        "SECRET_INCOMING_NESTED",
        "SECRET_STATE_LIMIT",
        "SECRET_IMPORT_FILE_TEXT",
        "SECRET_IMPORT_FILE_PAYLOAD",
    ):
        assert marker not in payload["serialized"]

    assert payload["ingest"]["resourceLimits"] == {
        "policy": "structure_viewer_evidence_ingest_budget_v1",
        "max_text_bytes": 100,
    }
    assert payload["ingest"]["toolProfiles"] == {"generic": 1}
    issue = payload["ingest"]["issue"]
    assert issue["severity"] == "critical"
    assert issue["issue"] == "blocked input"
    assert issue["value"] == "code@path"
    assert issue["code"] == "blocked_code"
    assert issue["path"] == "/payload"
    assert issue["drawing_id"] == "drawing-1"
    assert issue["quality_flags"] == [f"flag-{index}" for index in range(20)]
    assert set(issue) == {
        "severity",
        "issue",
        "value",
        "code",
        "path",
        "drawing_id",
        "quality_flags",
    }
    assert payload["ingest"]["identity"] == {
        "identity_policy": "source_bytes_and_detached_canonical_model_v1",
        "source_input_checksum": "sha256:" + "a" * 64,
        "canonical_model_checksum": "sha256:" + "b" * 64,
        "analysis_input_snapshot": "detached_canonical_model_v1",
    }
    assert payload["ingest"]["fileRead"] == {
        "contract": "structure_viewer_evidence_file_read_v1",
        "resource_policy": "structure_viewer_evidence_ingest_budget_v1",
        "file_name": "model.json",
        "file_type": "application/json",
        "status": "ready",
        "file_size": 100,
        "last_modified": 123,
        "text_byte_length": 100,
    }

    assert payload["imported"]["issue"] == {
        "severity": "critical",
        "issue": "import blocked",
        "code": "import_code",
        "path": "/local_state",
    }
    assert payload["imported"]["incomingCounts"] == {
        "reviewTasks": 2,
        "receiptIndex": 3,
    }
    assert payload["imported"]["stateLimits"] == {
        "policy": "structure_viewer_project_bundle_state_budget_v1",
        "max_review_tasks": 200,
    }
    assert payload["imported"]["fileRead"] == {
        "contract": "structure_viewer_project_bundle_file_read_v1",
        "resource_policy": "structure_viewer_project_bundle_budget_v1",
        "file_name": "bundle.json",
        "file_size": 20,
        "text_byte_length": 20,
    }
