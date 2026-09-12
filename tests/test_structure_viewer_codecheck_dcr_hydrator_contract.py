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


def test_companion_hydration_preserves_model_root_and_combination_scope() -> None:
    payload = _run(
        f"""
import fs from 'node:fs';
import * as hydrator from {json.dumps(str(HYDRATOR))};
const html = fs.readFileSync('src/structure-viewer/index.html', 'utf8');
const start = html.indexOf('async function hydrateModelDataFromCodecheckCompanion(');
const end = html.indexOf('function buildContourCompareSafetyReceipt(', start);
if (start < 0 || end < start) throw Error('hydration functions missing');
const root = (a, b) => ({{case_context: {{load_combination_codecheck_table_by_name: {{
  A: {{table_rows: [{{member_id: 'same-id', dcr: a}}]}},
  B: {{table_rows: [{{member_id: 'same-id', dcr: b}}]}},
}}}}}});
const results = [];
for (const [allCombinations, companionB, missingRoot, unavailable] of [
  [false, 1.2, false, false], [true, 1.2, false, false],
  [true, 1.8, false, false], [true, 1.2, true, false],
  [true, 1.2, false, true],
]) {{
  const sourceRoot = missingRoot ? null : root(0.3, 1.4);
  const optimizedRoot = root(9, 10);
  const companionRoot = root(0.5, companionB);
  const globals = {{
    ...hydrator,
    normalizeSelectionValue: x => String(x ?? '').trim(),
    getActiveCodecheckCombinationName: () => 'A',
    tryFetchArtifact: async () => {{
      if (unavailable) throw Error('companion unavailable');
      return {{payload: companionRoot}};
    }},
    lastNormalizedRootPayload: optimizedRoot,
    workspaceState: {{}}, window: {{}}, console,
  }};
  const run = new Function(...Object.keys(globals), html.slice(start, end) + ';return applyFullCodecheckHydration;')(...Object.values(globals));
  const model = {{elements: [{{id: 'same-id'}}], meta: {{}}}};
  await run(model, {{rootPayload: sourceRoot, companionRole: 'baseline', allCombinations}});
  results.push({{dcr: model.elements[0].dcr, combination: model.elements[0].codecheck_combination}});
}}
console.log(JSON.stringify(results));
"""
    )
    assert payload == [
        {"dcr": 0.5, "combination": "A"},
        {"dcr": 1.4, "combination": "B"},
        {"dcr": 1.8, "combination": "B"},
        {"dcr": 1.2, "combination": "B"},
        {"dcr": 1.4, "combination": "B"},
    ]


def test_companion_hydration_reads_canonical_metadata_without_root_case_context() -> None:
    payload = _run(
        f"""
import fs from 'node:fs';
import * as hydrator from {json.dumps(str(HYDRATOR))};
const html = fs.readFileSync('src/structure-viewer/index.html', 'utf8');
const start = html.indexOf('async function hydrateModelDataFromCodecheckCompanion(');
const end = html.indexOf('async function applyFullCodecheckHydration(', start);
if (start < 0 || end < start) throw Error('companion function missing');
const original = JSON.parse(fs.readFileSync({json.dumps(str(BASELINE_JSON))}, 'utf8'));
if (original.case_context) throw Error('expected canonical metadata-only original');
const results = [];
for (const allCombinations of [false, true]) {{
  const expected = allCombinations
    ? hydrator.buildElementDcrMapAllCombinations(original.model.metadata, original)
    : hydrator.buildElementDcrMapFromModelMeta(original.model.metadata, original, {{combination: 'KDS_ULS_1'}});
  const globals = {{...hydrator, normalizeSelectionValue: x => String(x ?? '').trim(),
    getActiveCodecheckCombinationName: () => 'KDS_ULS_1',
    tryFetchArtifact: async () => ({{payload: original}}), console}};
  const run = new Function(...Object.keys(globals), html.slice(start, end) + ';return hydrateModelDataFromCodecheckCompanion;')(...Object.values(globals));
  const model = {{elements: [...expected.keys()].map(id => ({{id}})), meta: {{}}}};
  const summary = await run(model, 'canonical-original.json', 'KDS_ULS_1', {{rootPayload: null, allCombinations}});
  results.push({{expected: expected.size, hydrated: summary.hydrated_count,
    exact: model.elements.every(e => e.dcr === expected.get(e.id).dcr && e.codecheck_combination === expected.get(e.id).combination)}});
}}
console.log(JSON.stringify(results));
"""
    )
    for row in payload:
        assert row["expected"] >= 200
        assert row["hydrated"] == row["expected"]
        assert row["exact"]
