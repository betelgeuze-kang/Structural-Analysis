from __future__ import annotations

import json
import subprocess
from pathlib import Path


def test_viewer_data_loader_resolves_preset_aliases_and_candidate_order() -> None:
    script = """
import {
  buildArtifactCandidates,
  getPresetSidecarPath,
  getRequestedPreset,
  readEmbeddedPayload,
  normalizePresetToken,
  readEmbeddedPresetPayload,
} from './src/structure-viewer/viewer-data-loader.js';

const root = {
  __STRUCTURE_VIEWER_PAYLOAD__: {inline: true},
  __STRUCTURE_VIEWER_PRESET_PAYLOADS__: {
    real_drawing_private_3d: {
      label: 'fixture real drawings',
      report_name: 'fixture-report',
      path: 'fixture-sidecar',
      payload: {model: {nodes: [], elements: []}},
    },
  },
};
console.log(JSON.stringify({
  alias: normalizePresetToken('real drawings'),
  query: getRequestedPreset('?model_preset=real_drawing_3d'),
  sidecar: getPresetSidecarPath('real_drawings'),
  candidates: buildArtifactCandidates('?preset=midas33_pr&artifact=custom.json').slice(0, 3),
  inlineLabel: readEmbeddedPayload({root})?.label || '',
  embedded: readEmbeddedPresetPayload('real_drawings', root)?.reportName || '',
}));
"""
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=Path(__file__).resolve().parents[1],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)

    assert payload["alias"] == "real_drawing_private_3d"
    assert payload["query"] == "real_drawing_private_3d"
    assert payload["sidecar"] == "./index.real_drawing_private.data.js"
    assert payload["candidates"][0] == "custom.json"
    assert payload["candidates"][1].endswith("midas_generator_33.pr_recheck.json")
    assert payload["inlineLabel"] == "window.__STRUCTURE_VIEWER_PAYLOAD__"
    assert payload["embedded"] == "fixture-report"
