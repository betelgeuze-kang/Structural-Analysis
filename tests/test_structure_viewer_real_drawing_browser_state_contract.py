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


def test_real_drawing_browser_state_module_normalizes_storage_and_query_params() -> None:
    payload = _run_node_contract_script(
        """
import {
  REAL_DRAWING_BROWSER_STATE_KEY,
  applyRealDrawingBrowserQueryParams,
  buildRealDrawingBrowserStateSnapshot,
  normalizeRealDrawingBrowserSort,
  normalizeRealDrawingQualityFilter,
  persistRealDrawingBrowserState,
  readInitialRealDrawingBrowserState,
} from './src/structure-viewer/viewer-real-drawing-browser-state.js';

const storage = new Map();
storage.set(REAL_DRAWING_BROWSER_STATE_KEY, JSON.stringify({
  filter: 'review',
  query: 'RD',
  sort: 'segments',
  recentAssets: ['RD-001', '', 'RD-001', 'RD-002'],
}));

let persisted = null;
const initial = readInitialRealDrawingBrowserState({
  search: '?drawing_filter=proxy&drawing_query=ifc&drawing_sort=status',
  storageGet: (key) => storage.get(key) || null,
});
const fallback = readInitialRealDrawingBrowserState({
  search: '?drawing_filter=invalid&drawing_sort=invalid',
  storageGet: (key) => storage.get(key) || null,
});
persistRealDrawingBrowserState({
  filter: 'solver_exact',
  query: ' KDS ',
  sort: 'asset',
  recentAssetRefs: ['RD-004', 'RD-005', 'RD-004', '', 'RD-006'],
  updatedAt: '2026-05-13T00:00:00.000Z',
}, {
  storageSet: (key, value) => {
    persisted = {key, value: JSON.parse(value)};
  },
});

const url = new URL('https://viewer.test/index.html?drawing_asset=old&drawing_filter=review&drawing_query=x&drawing_sort=status');
applyRealDrawingBrowserQueryParams(url, {filter: 'geometry_ready', query: ' load ', sort: 'segments'}, {assetRef: 'RD-009'});
const cleanUrl = new URL('https://viewer.test/index.html?drawing_asset=old&drawing_filter=review&drawing_query=x&drawing_sort=status');
applyRealDrawingBrowserQueryParams(cleanUrl, {filter: 'all', query: '', sort: 'priority'});

console.log(JSON.stringify({
  initial,
  fallback,
  persisted,
  url: url.toString(),
  cleanUrl: cleanUrl.toString(),
  badFilter: normalizeRealDrawingQualityFilter('unknown'),
  badSort: normalizeRealDrawingBrowserSort('unknown'),
  snapshot: buildRealDrawingBrowserStateSnapshot({
    filter: 'review',
    query: ' q ',
    sort: 'status',
    recentAssetRefs: ['A', 'B', 'A'],
    updatedAt: 'fixed',
  }),
}));
"""
    )

    assert payload["initial"] == {
        "filter": "proxy",
        "query": "ifc",
        "sort": "status",
        "recentAssetRefs": ["RD-001", "RD-002"],
    }
    assert payload["fallback"]["filter"] == "all"
    assert payload["fallback"]["sort"] == "priority"
    assert payload["fallback"]["query"] == "RD"
    assert payload["persisted"]["key"] == "structural-viewer-real-drawing-browser-v1"
    assert payload["persisted"]["value"]["recentAssetRefs"] == ["RD-004", "RD-005", "RD-006"]
    assert "drawing_asset=RD-009" in payload["url"]
    assert "drawing_filter=geometry_ready" in payload["url"]
    assert "drawing_query=load" in payload["url"]
    assert "drawing_sort=segments" in payload["url"]
    assert payload["cleanUrl"] == "https://viewer.test/index.html"
    assert payload["badFilter"] == "all"
    assert payload["badSort"] == "priority"
    assert payload["snapshot"]["query"] == "q"
    assert payload["snapshot"]["recentAssetRefs"] == ["A", "B"]
