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


def test_search_results_model_builds_unique_selected_and_isolated_member_rows() -> None:
    payload = _run_node_contract_script(
        """
import {
  buildViewerSearchResultsModel,
  resolveViewerSearchMatches,
  viewerElementMatchesSearchQuery,
} from './src/structure-viewer/viewer-search-results-model.js';

const elements = [
  {
    id: 'E-001',
    member_id: 'M-001',
    section: 'W18',
    section_family: 'beam family',
    group_names: ['core'],
    story_band_label: 'S1',
  },
  {
    id: 'E-002',
    member_id: 'M-001',
    section: 'W18 duplicate',
    section_family: 'beam family',
    story_band_label: 'S1',
  },
  {
    id: 'E-003',
    member_id: 'M-002',
    section: 'C40',
    section_family: 'column family',
    section_shape: 'box',
    zone_label: 'perimeter',
  },
  {
    id: 'E-004',
    case_id: 'CASE-004',
    type: 'wall',
    review_case_id: 'RC-01',
    review_row_label: 'shear check',
  },
];
const appliedSections = new Map([['M-002', 'C40X']]);
const resolveMemberId = (row) => String(row.member_id || row.case_id || row.id || '').trim();
const resolveEffectiveSectionValue = (row) => appliedSections.get(resolveMemberId(row)) || row.section || '--';
const hasAppliedSectionOverride = (row) => appliedSections.has(resolveMemberId(row));
const model = buildViewerSearchResultsModel({elements}, {
  query: 'perimeter c40x',
  limit: 10,
  selectedMemberId: 'M-002',
  activeIsolation: {kind: 'member', value: 'M-002'},
  resolveMemberId,
  resolveEffectiveSectionValue,
  hasAppliedSectionOverride,
});
const ready = buildViewerSearchResultsModel({elements}, {query: '', resolveMemberId});
const unavailable = buildViewerSearchResultsModel({}, {query: 'x'});
const noMatches = buildViewerSearchResultsModel({elements}, {
  query: 'nope',
  resolveMemberId,
  resolveEffectiveSectionValue,
});

console.log(JSON.stringify({
  matchAppliedSection: viewerElementMatchesSearchQuery(elements[2], 'c40x perimeter', {resolveEffectiveSectionValue}),
  uniqueMatches: resolveViewerSearchMatches(elements, 'beam', {resolveMemberId, resolveEffectiveSectionValue}).map(resolveMemberId),
  model,
  ready,
  unavailable,
  noMatches,
}));
"""
    )

    assert payload["matchAppliedSection"] is True
    assert payload["uniqueMatches"] == ["M-001"]
    assert payload["model"]["statusText"] == '"perimeter c40x" | matches 1'
    assert payload["model"]["items"] == [
        {
            "memberId": "M-002",
            "memberLabel": "C40X",
            "selected": True,
            "isolateActive": True,
        }
    ]
    assert payload["model"]["emptyHtml"] == '<div class="search-status">No matches</div>'
    assert payload["ready"] == {
        "statusText": "Search ready | members 3",
        "items": [],
        "emptyHtml": "",
        "ready": True,
    }
    assert payload["unavailable"] == {
        "statusText": "Search unavailable",
        "items": [],
        "emptyHtml": "",
        "unavailable": True,
    }
    assert payload["noMatches"]["statusText"] == '"nope" | matches 0'
    assert payload["noMatches"]["items"] == []
