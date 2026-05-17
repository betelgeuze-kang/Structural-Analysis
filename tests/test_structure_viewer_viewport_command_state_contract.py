from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_viewport_command_state_sidecar_keeps_render_mode_contract() -> None:
    result = subprocess.run(
        [
            "node",
            "--input-type=module",
            "-e",
            """
import {
  buildViewerRenderModeButtonStates,
  getViewerLegendDisplayForRenderMode,
  normalizeViewerRenderMode,
} from './src/structure-viewer/viewer-viewport-command-state.js';

console.log(JSON.stringify({
  invalidFallback: normalizeViewerRenderMode('bad', 'solid'),
  invalidDefault: normalizeViewerRenderMode('bad', 'also-bad'),
  contourLegend: getViewerLegendDisplayForRenderMode('contour'),
  solidLegend: getViewerLegendDisplayForRenderMode('solid'),
  buttonStates: buildViewerRenderModeButtonStates('contour'),
}));
""",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)

    assert payload["invalidFallback"] == "solid"
    assert payload["invalidDefault"] == "wireframe"
    assert payload["contourLegend"] == "block"
    assert payload["solidLegend"] == "none"
    assert payload["buttonStates"] == [
        {"mode": "wireframe", "buttonId": "btn-wireframe", "active": False},
        {"mode": "solid", "buttonId": "btn-solid", "active": False},
        {"mode": "contour", "buttonId": "btn-contour", "active": True},
    ]
