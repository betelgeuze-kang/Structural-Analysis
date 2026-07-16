from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_auto_source_type_resolves_authoritative_json_csv_and_ifc() -> None:
    frame_result = json.loads(
        (
            ROOT
            / "implementation/phase1/release_evidence/productization/phase1_core_api_frame_result.json"
        ).read_text(encoding="utf-8")
    )
    viewer_payload = frame_result["metrics"]["viewer_payload"]
    script = f"""
import {{
  buildEvidenceIngestPreviewFromText,
  inspectRenderableEvidencePayloadFromText,
}} from './src/structure-viewer/viewer-evidence-ingest-model.js';

const authoritative = {json.dumps(viewer_payload, sort_keys=True)};
const authoritativeInspection = inspectRenderableEvidencePayloadFromText(
  JSON.stringify(authoritative),
  {{sourceType: 'auto', sourceName: 'frame-result.json'}},
);
const authoritativePreview = buildEvidenceIngestPreviewFromText(
  JSON.stringify(authoritative),
  {{
    sourceType: 'auto',
    projectId: 'auto_authoritative',
    artifactPath: 'frame-result.json',
  }},
);
const csvPreview = buildEvidenceIngestPreviewFromText(
  'drawing_id,artifact_path,member_count,node_count,element_count\\nauto_csv,model.csv,1,2,1\\n',
  {{sourceType: 'auto', projectId: 'auto_csv', artifactPath: 'model.csv'}},
);
const ifcPreview = buildEvidenceIngestPreviewFromText(
  '#1=IFCBEAM();#2=IFCCARTESIANPOINT();',
  {{sourceType: 'auto', projectId: 'auto_ifc', artifactPath: 'model.ifc'}},
);
console.log(JSON.stringify({{
  authoritativeInspection: {{
    sourceType: authoritativeInspection.source_type,
    available: authoritativeInspection.available,
    kind: authoritativeInspection.payload_kind,
    validationStatus: authoritativeInspection.validation_status,
  }},
  authoritativePreview: {{
    sourceType: authoritativePreview.source_type,
    blockedIssueCount: authoritativePreview.blocked_issues.length,
    drawingStatus: authoritativePreview.manifest.projects[0].drawings[0].commercial_review_status,
  }},
  csv: {{
    sourceType: csvPreview.source_type,
    drawingId: csvPreview.manifest.projects[0].drawings[0].drawing_id,
    status: csvPreview.manifest.projects[0].drawings[0].commercial_review_status,
  }},
  ifc: {{
    sourceType: ifcPreview.source_type,
    sourceFamily: ifcPreview.manifest.projects[0].drawings[0].source_family,
    status: ifcPreview.manifest.projects[0].drawings[0].commercial_review_status,
  }},
}}));
"""
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)

    assert payload["authoritativeInspection"] == {
        "sourceType": "json",
        "available": True,
        "kind": "authoritative_viewer_v2",
        "validationStatus": "validated_authoritative_contract",
    }
    assert payload["authoritativePreview"] == {
        "sourceType": "json",
        "blockedIssueCount": 0,
        "drawingStatus": "needs_review",
    }
    assert payload["csv"] == {
        "sourceType": "csv",
        "drawingId": "auto_csv",
        "status": "ready",
    }
    assert payload["ifc"] == {
        "sourceType": "ifc",
        "sourceFamily": "ifc",
        "status": "needs_review",
    }
