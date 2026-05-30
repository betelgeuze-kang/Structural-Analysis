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
    governing_load_case: 'LCB-001',
    active_step: 18,
    total_steps: 20,
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
const enhancedLayerItems = buildLayerToggleItems({
  beam: [{id: 'E1'}, {id: 'E2'}],
  shell: [{id: 'E3'}],
}, {
  materialRows: [
    {material_family: 'concrete', material_family_label: 'Concrete', usage_count: 12},
    {material_family: 'steel', material_family_label: 'Structural steel', usage_count: 4},
  ],
  materialModelRows: [
    {material_model: 'Concrete damage-plasticity', usage_count: 12},
    {material_model: 'Steel bilinear', usage_count: 4},
  ],
});

console.log(JSON.stringify({
  explicit,
  storyFallback,
  empty,
  layerItems,
  enhancedLayerItems,
}));
"""
    )

    assert payload["explicit"] == {
        "activeLoadCase": "LCB-999",
        "items": [
            {
                "label": "LCB-999",
                "selected": True,
                "kind": "Combo",
                "statusLabel": "Pinned selection",
                "stepLabel": "Step 18/20",
                "sourceLabel": "Shared selection",
                "progressPct": 90,
                "ordinal": 1,
            },
            {
                "label": "LCB-001",
                "selected": False,
                "kind": "Combo",
                "statusLabel": "Governing",
                "stepLabel": "Step 18/20",
                "sourceLabel": "Load inventory",
                "progressPct": 90,
                "ordinal": 2,
            },
            {
                "label": "LCB-002",
                "selected": False,
                "kind": "Combo",
                "statusLabel": "Available",
                "stepLabel": "Ready",
                "sourceLabel": "Load inventory",
                "progressPct": 100,
                "ordinal": 3,
            },
        ],
        "emptyText": "real drawing | comparison ready",
    }
    assert payload["storyFallback"] == {
        "activeLoadCase": "S2",
        "items": [
            {
                "label": "S1",
                "selected": False,
                "kind": "Story",
                "statusLabel": "Available",
                "stepLabel": "Ready",
                "sourceLabel": "Story slice fallback",
                "progressPct": 100,
                "ordinal": 1,
            },
            {
                "label": "S2",
                "selected": True,
                "kind": "Story",
                "statusLabel": "Selected",
                "stepLabel": "Step 1/1",
                "sourceLabel": "Story slice fallback",
                "progressPct": 100,
                "ordinal": 2,
            },
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
    assert payload["enhancedLayerItems"] == [
        {
            "type": "beam",
            "key": "beam",
            "label": "beam",
            "group": "Structure",
            "count": 2,
            "checked": True,
        },
        {
            "type": "shell",
            "key": "shell",
            "label": "shell",
            "group": "Structure",
            "count": 1,
            "checked": True,
        },
        {
            "type": "material_family:concrete",
            "key": "material_family:concrete",
            "label": "Concrete",
            "group": "Material families",
            "count": 12,
            "checked": True,
        },
        {
            "type": "material_family:steel",
            "key": "material_family:steel",
            "label": "Structural steel",
            "group": "Material families",
            "count": 4,
            "checked": True,
        },
        {
            "type": "material_model:Concrete damage-plasticity",
            "key": "material_model:concrete_damage-plasticity",
            "label": "Concrete damage-plasticity",
            "group": "Material laws",
            "count": 12,
            "checked": True,
        },
        {
            "type": "material_model:Steel bilinear",
            "key": "material_model:steel_bilinear",
            "label": "Steel bilinear",
            "group": "Material laws",
            "count": 4,
            "checked": True,
        },
    ]
