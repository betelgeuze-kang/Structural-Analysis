from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_commercial_tool_crosswalk_profiles_matches_and_mismatches_rows() -> None:
    script = """
import {
  buildCommercialToolCrosswalkModel,
  buildCommercialToolCsvMapperModel,
  inferCommercialToolProfile,
  listCommercialToolCsvMapperPresets,
} from './src/structure-viewer/viewer-commercial-tool-crosswalk-model.js';

const data = {
  elements: [
    {id: '911', member_id: '911', section: 'W14X90', dcr: 0.88},
    {id: '912', member_id: '912', section: 'W14X82', dcr: 0.72},
    {id: '913', member_id: '913', section: 'W14X68', dcr: 0.55},
  ],
};
const ingestPreview = {
  normalized_rows: [
    {source_tool: 'ETABS 22', source_tool_profile: 'etabs', member_id: '911', section: 'W14X90', dcr_after: 0.89, story: 'L10'},
    {source_tool: 'RFEM', source_tool_profile: 'rfem', member_id: '912', section: 'W14X76', dcr_after: 0.72},
    {source_tool: 'Revit', source_tool_profile: 'revit', member_id: 'MISSING-1', section: 'HSS8X8', dcr_after: 0.44},
    {source_tool: 'SAP2000', source_tool_profile: 'sap2000', member_id: '913', section: 'W14X68', dcr_after: 0.75, receipt_path: 'sap/913.json'},
  ],
};
const model = buildCommercialToolCrosswalkModel({data, ingestPreview, memberId: '911', dcrTolerance: 0.03});
const autoMapper = buildCommercialToolCsvMapperModel({profile: 'auto', ingestPreview});
const revitMapper = buildCommercialToolCsvMapperModel({profile: 'revit', ingestPreview});
const pending = buildCommercialToolCrosswalkModel({data, ingestPreview: null});
console.log(JSON.stringify({
  profiles: {
    etabs: inferCommercialToolProfile('ETABS v22'),
    sap: inferCommercialToolProfile('SAP2000'),
    rfem: inferCommercialToolProfile('Dlubal RFEM'),
    tekla: inferCommercialToolProfile('Tekla Structures'),
    revit: inferCommercialToolProfile('Autodesk Revit'),
  },
  model,
  mapperPresets: listCommercialToolCsvMapperPresets(),
  autoMapper,
  revitMapper,
  selected: model.selectedRows[0],
  sectionMismatch: model.rows.find((row) => row.status === 'section_mismatch'),
  dcrMismatch: model.rows.find((row) => row.status === 'dcr_mismatch'),
  missing: model.rows.find((row) => row.status === 'missing_viewer_member'),
  pending,
}));
"""
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)

    assert payload["profiles"] == {
        "etabs": "etabs",
        "sap": "sap2000",
        "rfem": "rfem",
        "tekla": "tekla",
        "revit": "revit",
    }
    assert payload["model"]["schema_version"] == "structure-viewer-commercial-tool-crosswalk.v1"
    assert payload["model"]["status"] == "needs_review"
    assert payload["model"]["counts"]["total"] == 4
    assert payload["model"]["counts"]["matched"] == 1
    assert payload["model"]["counts"]["section_mismatch"] == 1
    assert payload["model"]["counts"]["dcr_mismatch"] == 1
    assert payload["model"]["counts"]["missing_viewer_member"] == 1
    assert "ETABS/SAP2000 1" in payload["model"]["summary"]
    assert payload["selected"]["externalMemberId"] == "911"
    assert payload["selected"]["viewerMemberId"] == "911"
    assert payload["selected"]["status"] == "matched"
    assert any(row["profile"] == "etabs" for row in payload["mapperPresets"])
    assert any(row["profile"] == "revit" for row in payload["mapperPresets"])
    assert payload["autoMapper"]["schema_version"] == "structure-viewer-commercial-tool-csv-mapper.v1"
    assert payload["autoMapper"]["requestedProfile"] == "auto"
    assert payload["autoMapper"]["profile"] == "etabs"
    assert payload["autoMapper"]["detectedProfile"] == "etabs"
    assert any(row["field"] == "member_id" and "frame" in row["candidates"] for row in payload["autoMapper"]["rows"])
    assert payload["revitMapper"]["profile"] == "revit"
    assert any(row["field"] == "member_id" and "unique_id" in row["candidates"] for row in payload["revitMapper"]["rows"])
    assert payload["sectionMismatch"]["externalMemberId"] == "912"
    assert payload["dcrMismatch"]["externalMemberId"] == "913"
    assert payload["missing"]["externalMemberId"] == "MISSING-1"
    assert payload["pending"]["status"] == "missing"
