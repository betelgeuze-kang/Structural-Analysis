"""Contract tests for viewer-drawing-comparison-engine.js."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ENGINE = REPO_ROOT / "src/structure-viewer/viewer-drawing-comparison-engine.js"


def _run(script: str) -> dict:
    completed = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout.strip())


def test_diff_element_sections_detects_section_change() -> None:
    payload = _run(
        f"""
import {{
  diffElementSections,
  inferSectionVisualScale,
}} from {json.dumps(str(ENGINE))};

const diff = diffElementSections(
  [{{ id: 1, section_id: 10, section: 'H400x200' }}],
  [{{ id: 1, section_id: 11, section: 'H350x175' }}],
);
const scale = inferSectionVisualScale('H400x200', 'H350x175');
console.log(JSON.stringify({{
  changed: diff.changed,
  tone: [...diff.toneByElementId.entries()][0]?.[1],
  scale: diff.visualByElementId.get('1')?.scale,
  inferred: scale,
}}));
"""
    )
    assert payload["changed"] == ["1"]
    assert payload["tone"] == "section_reduced"
    assert payload["scale"] < 1
    assert payload["inferred"] < 1


def test_resolve_baseline_artifact_from_workspace_variant() -> None:
    payload = _run(
        f"""
import {{ resolveBaselineArtifactPath }} from {json.dumps(str(ENGINE))};
const path = resolveBaselineArtifactPath({{
  drawing: {{
    baseline_ref: 'midas33',
    variants: [
      {{ variant: 'baseline', artifact_path: 'baseline.json' }},
      {{ variant: 'optimized', artifact_path: 'optimized.json' }},
    ],
  }},
}});
console.log(JSON.stringify({{ path }}));
"""
    )
    assert payload["path"] == "baseline.json"


def test_removed_summary_counts_baseline_only_ids() -> None:
    payload = _run(
        f"""
import {{ buildDrawingComparisonRemovedSummary }} from {json.dumps(str(ENGINE))};
const summary = buildDrawingComparisonRemovedSummary({{
  removed: ['101', '102'],
  added: ['999'],
}});
console.log(JSON.stringify(summary));
"""
    )
    assert payload["removedCount"] == 2
    assert payload["addedCount"] == 1
    assert payload["removedMemberIds"] == ["101", "102"]


def test_removed_summary_merges_member_alignment_contract() -> None:
    payload = _run(
        f"""
import {{ buildDrawingComparisonRemovedSummary }} from {json.dumps(str(ENGINE))};
const summary = buildDrawingComparisonRemovedSummary(
  {{ removed: ['101'] }},
  {{ member_alignment: {{ removed_member_ids: ['202'], added_member_ids: ['303'], group_merge_count: 2 }} }},
);
console.log(JSON.stringify(summary));
"""
    )
    assert payload["removedCount"] == 2
    assert payload["addedCount"] == 1
    assert payload["groupMergeCount"] == 2


def test_merge_contour_ranges_links_before_after() -> None:
    contour = REPO_ROOT / "src/structure-viewer/viewer-drawing-comparison-contour.js"
    payload = _run(
        f"""
import {{ mergeContourRanges }} from {json.dumps(str(contour))};
const linked = mergeContourRanges({{ mn: 0.2, mx: 0.8 }}, {{ mn: 0.5, mx: 1.1 }});
console.log(JSON.stringify(linked));
"""
    )
    assert payload["mn"] == 0.2
    assert payload["mx"] == 1.1
