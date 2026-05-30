"""Contract tests for viewer-optimization-timeline-model.js."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TIMELINE = REPO_ROOT / "src/structure-viewer/viewer-optimization-timeline-model.js"
CHANGES = (
    REPO_ROOT
    / "implementation/phase1/release_evidence/productization/design_optimization_cost_reduction_changes.json"
)


def _run(script: str) -> dict:
    completed = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout.strip())


def test_build_optimization_timeline_from_release_changes() -> None:
    payload = _run(
        f"""
import {{ buildOptimizationTimelineModel, resolveOptimizationTimelineStep }} from {json.dumps(str(TIMELINE))};
import fs from 'node:fs';
const changesPayload = JSON.parse(fs.readFileSync({json.dumps(str(CHANGES))}, 'utf8'));
const model = buildOptimizationTimelineModel(changesPayload);
const finalStep = resolveOptimizationTimelineStep(model, model.changeCount - 1);
console.log(JSON.stringify({{
  status: model.status,
  changeCount: model.changeCount,
  stepCount: model.steps.length,
  finalIndex: finalStep?.index,
  finalCumulative: finalStep?.cumulativeCostDelta,
  stageKeys: model.stageSummary.map((row) => row.key),
}}));
"""
    )
    assert payload["status"] == "ready"
    assert payload["changeCount"] > 0
    assert payload["stepCount"] == payload["changeCount"] + 1
    assert payload["finalIndex"] == payload["changeCount"] - 1
    assert payload["finalCumulative"] < 0
    assert set(payload["stageKeys"]) == {"stage_a", "stage_b", "stage_c"}


def test_parse_optimization_group_id_story_band() -> None:
    payload = _run(
        f"""
import {{ parseOptimizationGroupId }} from {json.dumps(str(TIMELINE))};
const parsed = parseOptimizationGroupId('S04:intermediate:nogroup:slab:SB1500X800');
console.log(JSON.stringify(parsed));
"""
    )
    assert payload["storyBand"] == 4
    assert payload["zoneLabel"] == "intermediate"
    assert payload["memberType"] == "slab"


def test_build_timeline_highlights_matches_story_band_z() -> None:
    payload = _run(
        f"""
import {{ buildTimelineStepHighlights }} from {json.dumps(str(TIMELINE))};
const highlight = buildTimelineStepHighlights({{
  stepIndex: 0,
  changesPayload: {{
    changes: [{{
      group_id: 'S01:perimeter:nogroup:beam:SB1200',
      action_name: 'rebar_down',
    }}],
  }},
  elements: [
    {{ id: '1', type: 'beam', node_ids: [1] }},
    {{ id: '2', type: 'beam', node_ids: [2] }},
  ],
  nodes: [
    {{ id: 1, z: 3.0 }},
    {{ id: 2, z: 12.0 }},
  ],
  storyBands: [
    {{ label: 'Story 1', zMin: 0, zMax: 6 }},
    {{ label: 'Story 2', zMin: 6, zMax: 15 }},
  ],
}});
console.log(JSON.stringify({{
  memberIds: highlight.memberIds,
  storyClipLabel: highlight.storyClipLabel,
}}));
"""
    )
    assert payload["memberIds"] == ["1"]
    assert payload["storyClipLabel"] == "Story 1"


def test_resolve_timeline_step_for_member_in_story_band() -> None:
    payload = _run(
        f"""
import {{ resolveTimelineStepIndexForMember }} from {json.dumps(str(TIMELINE))};
const idx = resolveTimelineStepIndexForMember('beam-1', {{
  changesPayload: {{
    changes: [{{
      group_id: 'S01:perimeter:nogroup:beam:SB1200',
      action_name: 'rebar_down',
    }}],
  }},
  elements: [{{ id: 'beam-1', type: 'beam', node_ids: [1] }}],
  nodes: [{{ id: 1, z: 3.0 }}],
  storyBands: [{{ label: 'Story 1', zMin: 0, zMax: 6 }}],
}});
console.log(JSON.stringify({{ idx }}));
"""
    )
    assert payload["idx"] == 0


def test_resolve_timeline_step_for_steel_delta_key() -> None:
    payload = _run(
        f"""
import {{
  resolveTimelineStepIndexForDeltaKey,
}} from {json.dumps(str(TIMELINE))};
const idx = resolveTimelineStepIndexForDeltaKey('steel', {{
  changes: [
    {{ action_family: 'slab', action_name: 'slab_thickness_down', cost_proxy_delta: -10 }},
    {{ action_family: 'rebar', action_name: 'rebar_down', cost_proxy_delta: -50 }},
  ],
}});
console.log(JSON.stringify({{ idx }}));
"""
    )
    assert payload["idx"] == 1


def test_build_timeline_delivery_rows() -> None:
    payload = _run(
        f"""
import {{
  buildOptimizationTimelineModel,
  buildOptimizationTimelineDeliveryRows,
  resolveOptimizationTimelineStep,
}} from {json.dumps(str(TIMELINE))};
import fs from 'node:fs';
const changesPayload = JSON.parse(fs.readFileSync({json.dumps(str(CHANGES))}, 'utf8'));
const model = buildOptimizationTimelineModel(changesPayload);
const step = resolveOptimizationTimelineStep(model, model.changeCount - 1);
const rows = buildOptimizationTimelineDeliveryRows(model, step);
console.log(JSON.stringify({{
  rowCount: rows.length,
  labels: rows.map((row) => row.label),
}}));
"""
    )
    assert payload["rowCount"] >= 5
    assert "Timeline snapshot label" in payload["labels"]


def test_classify_rebar_down_as_stage_b() -> None:
    payload = _run(
        f"""
import {{ classifyOptimizationChangeStage }} from {json.dumps(str(TIMELINE))};
const stage = classifyOptimizationChangeStage({{
  action_name: 'rebar_down',
  action_family: 'rebar',
}});
console.log(JSON.stringify({{ stage }}));
"""
    )
    assert payload["stage"] == "stage_b"
