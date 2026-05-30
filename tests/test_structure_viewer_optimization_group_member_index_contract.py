"""Contract tests for viewer-optimization-group-member-index.js."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE = REPO_ROOT / "src/structure-viewer/viewer-optimization-group-member-index.js"
INDEX_JSON = (
    REPO_ROOT
    / "implementation/phase1/release_evidence/productization/design_optimization_group_member_index.json"
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


def test_group_member_index_artifact_is_ready() -> None:
    payload = _run(
        f"""
import {{ readFileSync }} from 'fs';
import {{ buildGroupMemberIndexModel }} from {json.dumps(str(MODULE))};
const root = JSON.parse(readFileSync({json.dumps(str(INDEX_JSON))}, 'utf8'));
const model = buildGroupMemberIndexModel(root);
console.log(JSON.stringify({{
  status: model.status,
  groupCount: model.groupCount,
  memberCount: model.memberCount,
}}));
"""
    )
    assert payload["status"] == "ready"
    assert payload["groupCount"] > 100
    assert payload["memberCount"] > 100


def test_resolve_member_ids_by_group_index() -> None:
    payload = _run(
        f"""
import {{ readFileSync }} from 'fs';
import {{
  buildGroupMemberIndexModel,
  resolveMemberIdsForOptimizationChange,
}} from {json.dumps(str(MODULE))};
const root = JSON.parse(readFileSync({json.dumps(str(INDEX_JSON))}, 'utf8'));
const index = buildGroupMemberIndexModel(root);
const firstKey = Object.keys(index.byGroupIndex)[0];
const members = resolveMemberIdsForOptimizationChange({{ group_index: Number(firstKey) }}, index);
console.log(JSON.stringify({{ key: firstKey, count: members.length }}));
"""
    )
    assert payload["count"] > 0


def test_timeline_highlights_merge_group_members() -> None:
    payload = _run(
        f"""
import {{ readFileSync }} from 'fs';
import {{
  buildGroupMemberIndexModel,
  buildTimelineHighlightsWithGroupIndex,
}} from {json.dumps(str(MODULE))};
const root = JSON.parse(readFileSync({json.dumps(str(INDEX_JSON))}, 'utf8'));
const index = buildGroupMemberIndexModel(root);
const changesPayload = {{
  changes: [
    {{ group_index: 0, after_rebar_ratio: 1.05, after_thickness_scale: 0.95 }},
  ],
}};
const highlight = buildTimelineHighlightsWithGroupIndex({{
  stepIndex: 0,
  changesPayload,
  groupMemberIndex: index,
  elements: [],
  nodes: [],
  storyBands: [],
  sectionChangedIds: [],
}});
console.log(JSON.stringify({{
  memberCount: highlight.memberIds.length,
  morphKeys: Object.keys(highlight.morphByElementId || {{}}).length,
}}));
"""
    )
    assert payload["memberCount"] > 0
    assert payload["morphKeys"] > 0
