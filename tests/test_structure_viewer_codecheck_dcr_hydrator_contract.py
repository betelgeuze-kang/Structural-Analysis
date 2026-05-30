"""Contract tests for viewer-codecheck-dcr-hydrator.js."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
HYDRATOR = REPO_ROOT / "src/structure-viewer/viewer-codecheck-dcr-hydrator.js"
BASELINE_JSON = REPO_ROOT / "implementation/phase1/open_data/midas/midas_generator_33.json"


def _run(script: str) -> dict:
    completed = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout.strip())


def test_geometry_bridge_hydrates_crosswalk_handles() -> None:
    payload = _run(
        f"""
import {{ readFileSync }} from 'fs';
import {{
  buildElementDcrMapFromGeometryBridge,
  hydrateModelElementsWithCodecheckDcr,
}} from {json.dumps(str(HYDRATOR))};

const root = JSON.parse(readFileSync({json.dumps(str(BASELINE_JSON))}, 'utf8'));
const bridge = root.model.metadata.kds_geometry_bridge;
const map = buildElementDcrMapFromGeometryBridge(bridge, {{ combination: 'KDS_ULS_1' }});
const model = {{
  elements: [...map.keys()].slice(0, 5).map((id) => ({{ id, type: 'BEAM', node_ids: [1, 2] }})),
  meta: {{}},
}};
const summary = hydrateModelElementsWithCodecheckDcr(model, map, {{ combination: 'KDS_ULS_1' }});
console.log(JSON.stringify({{
  mapSize: map.size,
  hydrated: summary.hydrated_count,
  firstDcr: model.elements[0]?.dcr ?? 0,
}}));
"""
    )
    assert payload["mapSize"] >= 200
    assert payload["hydrated"] == 5
    assert payload["firstDcr"] > 0


def test_all_combinations_map_covers_more_than_single_combo() -> None:
    payload = _run(
        f"""
import {{ readFileSync }} from 'fs';
import {{
  buildElementDcrMapFromModelMeta,
  buildElementDcrMapAllCombinations,
}} from {json.dumps(str(HYDRATOR))};

const root = JSON.parse(readFileSync({json.dumps(str(BASELINE_JSON))}, 'utf8'));
const meta = root.model.metadata;
const single = buildElementDcrMapFromModelMeta(meta, root, {{ combination: 'KDS_ULS_1' }});
const all = buildElementDcrMapAllCombinations(meta, root);
console.log(JSON.stringify({{ single: single.size, all: all.size }}));
"""
    )
    assert payload["all"] >= payload["single"]


def test_merge_prefers_higher_dcr() -> None:
    payload = _run(
        f"""
import {{ mergeElementDcrMaps }} from {json.dumps(str(HYDRATOR))};
const a = new Map([['12', {{ dcr: 0.8, source: 'a' }}]]);
const b = new Map([['12', {{ dcr: 1.1, source: 'b' }}]]);
const merged = mergeElementDcrMaps(a, b);
console.log(JSON.stringify({{ dcr: merged.get('12')?.dcr, source: merged.get('12')?.source }}));
"""
    )
    assert payload["dcr"] == 1.1
    assert payload["source"] == "b"
