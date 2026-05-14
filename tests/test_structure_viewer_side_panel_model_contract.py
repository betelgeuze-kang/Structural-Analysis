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


def test_side_panel_model_builds_layer_toggles_and_load_case_inventory() -> None:
    payload = _run_node_contract_script(
        """
import {
  buildLayerToggleItems,
  buildLoadCaseListModel,
} from './src/structure-viewer/viewer-side-panel-model.js';

const explicit = buildLoadCaseListModel({
  meta: {
    load_case_inventory: ['LCB-001', 'LCB-002'],
    story_slices: ['S1', 'S2'],
    source_label: 'real drawing',
    comparison_availability: 'comparison ready',
  },
}, {
  activeLoadCase: 'LCB-999',
});
const storyFallback = buildLoadCaseListModel({
  meta: {
    story_slices: ['S1', 'S2', 'S3'],
  },
}, {
  activeLoadCase: 'S2',
  maxItems: 2,
});
const empty = buildLoadCaseListModel({
  meta: {
    source_label: 'artifact source',
    comparison_availability: 'no comparison',
  },
});
const layerItems = buildLayerToggleItems({
  beam: [{id: 'E1'}],
  wall: [{id: 'E2'}],
});

console.log(JSON.stringify({
  explicit,
  storyFallback,
  empty,
  layerItems,
}));
"""
    )

    assert payload["explicit"] == {
        "activeLoadCase": "LCB-999",
        "items": [
            {"label": "LCB-999", "selected": True},
            {"label": "LCB-001", "selected": False},
            {"label": "LCB-002", "selected": False},
        ],
        "emptyText": "real drawing | comparison ready",
    }
    assert payload["storyFallback"] == {
        "activeLoadCase": "S2",
        "items": [
            {"label": "S1", "selected": False},
            {"label": "S2", "selected": True},
        ],
        "emptyText": "Artifact-driven view",
    }
    assert payload["empty"] == {
        "activeLoadCase": "",
        "items": [],
        "emptyText": "artifact source | no comparison",
    }
    assert payload["layerItems"] == [
        {"type": "beam", "label": "beam", "checked": True},
        {"type": "wall", "label": "wall", "checked": True},
    ]
