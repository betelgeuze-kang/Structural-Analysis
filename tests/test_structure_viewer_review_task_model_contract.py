from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_review_task_model_builds_fixed_statuses_summary_and_report_rows() -> None:
    script = """
import {
  buildReviewTaskKey,
  buildReviewTaskModel,
  buildReviewTaskReportRows,
  buildReviewTaskSummary,
  normalizeReviewTaskStatus,
} from './src/structure-viewer/viewer-review-task-model.js';

const workspace = {projectId: 'midas33_release', drawingId: 'midas33_optimized'};
const key = buildReviewTaskKey({...workspace, memberId: '911'});
const state = {reviewTasks: {
  [key]: {
    status: 'approved',
    note: 'checked receipt and section delta',
    updatedAt: '2026-05-17T00:00:00Z',
    auditTrail: [{at: '2026-05-17T00:00:00Z', status: 'approved'}],
  },
  'midas33_release::midas33_optimized::912': {status: 'rerun_required'},
}};
const task = buildReviewTaskModel({state, workspace, memberId: '911'});
const fallback = buildReviewTaskModel({state: {}, workspace, memberId: '913'});
console.log(JSON.stringify({
  key,
  task,
  fallback,
  summary: buildReviewTaskSummary(state.reviewTasks, workspace),
  rows: buildReviewTaskReportRows(task),
  invalid: normalizeReviewTaskStatus('bad status'),
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

    assert payload["key"] == "midas33_release::midas33_optimized::911"
    assert payload["task"]["status"] == "approved"
    assert payload["task"]["label"] == "승인"
    assert payload["task"]["tone"] == "success"
    assert payload["task"]["note"] == "checked receipt and section delta"
    assert payload["task"]["hasTask"] is True
    assert payload["fallback"]["status"] == "needs_check"
    assert payload["fallback"]["label"] == "확인 필요"
    assert payload["summary"]["total"] == 2
    assert payload["summary"]["counts"]["approved"] == 1
    assert payload["summary"]["counts"]["rerun_required"] == 1
    assert payload["rows"][0]["value"] == "승인"
    assert payload["invalid"] == "needs_check"
