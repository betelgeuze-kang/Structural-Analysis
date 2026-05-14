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


def test_viewer_provenance_model_builds_source_selection_and_chip_labels() -> None:
    payload = _run_node_contract_script(
        """
import {
  basenameProvenanceLabel,
  buildViewerProvenanceModel,
  formatProvenanceTimestamp,
  normalizeProvenanceValue,
} from './src/structure-viewer/viewer-provenance-model.js';

const model = buildViewerProvenanceModel({
  meta: {
    source_label: 'Release Candidate',
    source_path: '/tmp/release/optimized-viewer.html',
    generated_at: '2026-05-14T01:02:03Z',
  },
  modelSourceMeta: {
    label: 'Fallback Source',
    resolvedPath: '/tmp/fallback.json',
  },
  selection: {
    memberId: 'B-12',
    loadCase: 'LC-7',
  },
  selectedCount: 3,
  isolation: {
    kind: 'member',
    value: 'B-12',
    label: 'Beam B-12',
  },
  clipLabel: 'Z+',
  drawingAssetLabel: 'RD-001',
  reviewHref: 'review/RD-001.json',
});

const fallback = buildViewerProvenanceModel({
  meta: {},
  selection: {},
  selectedCount: Number.NaN,
});

console.log(JSON.stringify({
  normalized: normalizeProvenanceValue('  abc  '),
  basename: basenameProvenanceLabel('C:\\\\tmp\\\\drawing.ifc'),
  timestampFallback: formatProvenanceTimestamp('not-a-date'),
  sourceLabel: model.sourceLabel,
  reportName: model.reportName,
  selectionText: model.selectionText,
  reviewLink: model.reviewLink,
  stageLoadCase: model.stageLoadCase,
  stageSelection: model.stageSelection,
  footerSelectionText: model.footerSelectionText,
  fallback: {
    sourceLabel: fallback.sourceLabel,
    reportName: fallback.reportName,
    timestampLabel: fallback.timestampLabel,
    selectionText: fallback.selectionText,
    reviewLink: fallback.reviewLink,
    footerSelectionText: fallback.footerSelectionText,
  },
}));
"""
    )

    assert payload["normalized"] == "abc"
    assert payload["basename"] == "drawing.ifc"
    assert payload["timestampFallback"] == "not-a-date"
    assert payload["sourceLabel"] == "Release Candidate"
    assert payload["reportName"] == "optimized-viewer.html"
    assert payload["selectionText"] == (
        "member=B-12 | drawing=RD-001 | load_case=LC-7 | selected=3 | "
        "isolate=member=Beam B-12 | clip=Z+"
    )
    assert payload["reviewLink"] == {
        "href": "review/RD-001.json",
        "disabled": False,
        "text": "Row provenance",
    }
    assert payload["stageLoadCase"] == {"text": "Load case LC-7", "accent": True}
    assert payload["stageSelection"] == {"text": "Selection 3 | B-12", "warn": True}
    assert payload["footerSelectionText"] == "3 selected | load LC-7 | isolate member=Beam B-12 | clip Z+"
    assert payload["fallback"] == {
        "sourceLabel": "--",
        "reportName": "--",
        "timestampLabel": "--",
        "selectionText": "member=-- | drawing=-- | load_case=-- | selected=0 | isolate=-- | clip=--",
        "reviewLink": {
            "href": "",
            "disabled": True,
            "text": "Row provenance unavailable",
        },
        "footerSelectionText": "0 selected | load -- | isolate -- | clip --",
    }
