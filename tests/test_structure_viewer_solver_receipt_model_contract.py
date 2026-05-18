from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_solver_receipt_model_indexes_manifest_and_local_receipts() -> None:
    script = """
import {
  STRUCTURE_VIEWER_SOLVER_RECEIPT_SCHEMA_VERSION,
  buildSolverReceiptIndex,
  buildSolverReceiptModel,
  buildSolverReceiptReportRows,
  buildSolverReceiptSummary,
  normalizeSolverReceiptRow,
} from './src/structure-viewer/viewer-solver-receipt-model.js';

const workspace = {
  projectId: 'midas33_release',
  drawingId: 'midas33_optimized',
  drawing: {
    solver_receipts: [{
      member_id: '911',
      source_tool: 'MIDAS Gen',
      load_combo: 'KDS_ULS_1',
      dcr_before: 0.91,
      dcr_after: 0.88,
      governing_constraint: 'story drift limit',
      status: 'verified',
      receipt_path: 'receipt.json',
      evidence_level: 'repo exact',
    }],
  },
};
const state = {receiptIndex: {
  'midas33_release::midas33_optimized::912': {
    project_id: 'midas33_release',
    drawing_id: 'midas33_optimized',
    member_id: '912',
    status: 'mismatch',
    source_tool: 'external csv',
  },
}};
const verified = buildSolverReceiptModel({workspace, state, memberId: '911'});
const mismatch = buildSolverReceiptModel({workspace, state, memberId: '912'});
const missing = buildSolverReceiptModel({workspace, state, memberId: '913'});
console.log(JSON.stringify({
  schema: STRUCTURE_VIEWER_SOLVER_RECEIPT_SCHEMA_VERSION,
  normalized: normalizeSolverReceiptRow({...verified, status: 'bad'}),
  indexKeys: Object.keys(buildSolverReceiptIndex({workspace, state})).sort(),
  verified,
  mismatch,
  missing,
  summary: buildSolverReceiptSummary(buildSolverReceiptIndex({workspace, state})),
  rows: buildSolverReceiptReportRows(verified),
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

    assert payload["schema"] == "structure-viewer-solver-receipt.v1"
    assert payload["normalized"]["status"] == "pending"
    assert payload["indexKeys"] == [
        "midas33_release::midas33_optimized::911",
        "midas33_release::midas33_optimized::912",
    ]
    assert payload["verified"]["status"] == "verified"
    assert payload["verified"]["label"] == "solver receipt verified"
    assert payload["verified"]["tone"] == "success"
    assert payload["mismatch"]["status"] == "mismatch"
    assert payload["mismatch"]["tone"] == "danger"
    assert payload["missing"]["missing"] is True
    assert payload["summary"]["counts"]["verified"] == 1
    assert payload["summary"]["counts"]["mismatch"] == 1
    assert payload["rows"][3]["value"] == "0.910 -> 0.880"
