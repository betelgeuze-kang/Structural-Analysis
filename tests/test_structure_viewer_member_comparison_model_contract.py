from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _run_node(script: str) -> dict:
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def test_member_comparison_model_filters_exact_proxy_and_missing_evidence() -> None:
    payload = _run_node(
        """
import {buildMemberComparisonModel} from './src/structure-viewer/viewer-member-comparison-model.js';

const workspace = {
  drawing: {
    optimization_summary: {
      baseline_member_count: 10,
      optimized_member_count: 8,
      evidence_level: 'manifest derived proxy',
    },
  },
};
const data = {
  elements: [
    {
      member_id: 'A-1',
      before_section: 'H-400',
      after_section: 'H-350',
      weight_delta_pct: -12.5,
      max_dcr_before: 0.72,
      max_dcr_after: 0.82,
    },
    {
      member_id: 'B-1',
      before_section: 'H-300',
      after_section: 'H-300',
      max_dcr_before: 0.61,
      max_dcr_after: 0.58,
    },
    {
      member_id: 'C-1',
      before_section: 'H-250',
      after_section: 'H-250',
      max_dcr_before: 0.92,
      max_dcr_after: 1.03,
    },
    {member_id: 'D-1'},
  ],
};
const changed = buildMemberComparisonModel({data, workspace, filter: 'changed'});
const reduced = buildMemberComparisonModel({data, workspace, filter: 'reduced'});
const retained = buildMemberComparisonModel({data, workspace, filter: 'retained'});
const risk = buildMemberComparisonModel({data, workspace, filter: 'risk_up'});
const missing = buildMemberComparisonModel({data, workspace, filter: 'missing_evidence'});

console.log(JSON.stringify({
  filterCounts: changed.filterOptions.reduce((acc, option) => ({...acc, [option.key]: option.count}), {}),
  changedFirst: changed.items[0],
  reducedLabels: reduced.items.map((item) => item.label),
  reducedProxy: reduced.items.find((item) => item.id === 'manifest_member_delta'),
  reducedHighlightIds: reduced.highlightMemberIds,
  reducedHighlightTone: reduced.highlightToneByMemberId['A-1'],
  retainedIds: retained.items.map((item) => item.id),
  riskIds: risk.items.map((item) => item.id),
  riskHighlightIds: risk.highlightMemberIds,
  riskTones: risk.items.map((item) => item.tone),
  missingFirst: missing.items[0],
  missingHighlightIds: missing.highlightMemberIds,
  summary: changed.summaryRows,
}));
"""
    )

    assert payload["filterCounts"]["changed"] == 1
    assert payload["filterCounts"]["reduced"] == 2
    assert payload["filterCounts"]["retained"] == 2
    assert payload["filterCounts"]["risk_up"] == 2
    assert payload["filterCounts"]["missing_evidence"] == 1
    assert payload["changedFirst"]["id"] == "A-1"
    assert payload["changedFirst"]["delta"] == "H-400 -> H-350"
    assert payload["changedFirst"]["evidence"] == "exact source"
    assert "Manifest member count delta" in payload["reducedLabels"]
    assert payload["reducedProxy"]["evidence"] == "manifest derived proxy"
    assert payload["reducedHighlightIds"] == ["A-1"]
    assert payload["reducedHighlightTone"] == "danger"
    assert payload["retainedIds"] == ["B-1", "C-1"]
    assert payload["riskIds"] == ["A-1", "C-1"]
    assert payload["riskHighlightIds"] == ["A-1", "C-1"]
    assert payload["riskTones"] == ["danger", "danger"]
    assert payload["missingFirst"]["id"] == "D-1"
    assert payload["missingFirst"]["evidence"] == "missing evidence"
    assert payload["missingHighlightIds"] == ["D-1"]
    assert payload["summary"][1]["label"] == "Member reduction"
    assert payload["summary"][2]["label"] == "Risk-up candidates"
