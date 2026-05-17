from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_midas33_view_preset_sidecar_keeps_pure_camera_contract() -> None:
    result = subprocess.run(
        [
            "node",
            "--input-type=module",
            "-e",
            """
import {
  buildMidas33CameraPoseFromBounds,
  buildMidas33ViewButtonStates,
  getMidas33ViewPresetConfig,
  isMidas33PresetToken,
  normalizeMidas33ViewPreset,
} from './src/structure-viewer/viewer-midas33-view-presets.js';

const bounds = {
  center: {x: 10, y: 20, z: 30},
  radius: 100,
};
console.log(JSON.stringify({
  midas: isMidas33PresetToken('midas33_optimized'),
  realDrawing: isMidas33PresetToken('real_drawing_private_3d'),
  badPreset: normalizeMidas33ViewPreset('bad'),
  fitPreset: normalizeMidas33ViewPreset('fit'),
  planMode: getMidas33ViewPresetConfig('plan').mode,
  reviewPose: buildMidas33CameraPoseFromBounds(bounds, 'review'),
  activeStates: buildMidas33ViewButtonStates('frame'),
}));
""",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)

    assert payload["midas"] is True
    assert payload["realDrawing"] is False
    assert payload["badPreset"] == "review"
    assert payload["fitPreset"] == "fit"
    assert payload["planMode"] == "wireframe"
    assert payload["reviewPose"]["target"] == {"x": 10, "y": 20, "z": 30}
    assert round(payload["reviewPose"]["position"]["x"], 6) == -45
    assert round(payload["reviewPose"]["position"]["y"], 6) == 105
    assert round(payload["reviewPose"]["position"]["z"], 6) == 65
    assert payload["activeStates"] == [
        {"key": "review", "active": False},
        {"key": "frame", "active": True},
        {"key": "plan", "active": False},
        {"key": "fit", "active": False},
    ]
