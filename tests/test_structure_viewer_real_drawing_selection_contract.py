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


def test_real_drawing_selection_module_resolves_recents_filters_and_navigation() -> None:
    payload = _run_node_contract_script(
        """
import {
  filterRecentRealDrawingAssetRefs,
  getActiveRealDrawingAssetRef,
  getRealDrawingBrowserVisibleAssets,
  rememberRealDrawingAssetRef,
  resolveRealDrawingAssetRefForSelection,
  stepRealDrawingAssetRef,
} from './src/structure-viewer/viewer-real-drawing-selection.js';

const data = {
  meta: {
    real_drawing_asset_registry: [
      {
        asset_ref: 'RD-001',
        geometry_available: true,
        segment_count: 10,
        solver_exact: true,
        status: 'solver_graph_ready',
      },
      {
        asset_ref: 'RD-002',
        geometry_available: true,
        segment_count: 3,
        solver_exact: false,
        status: 'ifc_proxy_graph_ready',
        geometry_mode: 'ifc_proxy_topology_3d_layout',
        quality_flags: ['proxy_layout_not_true_geometry', 'not_solver_exact'],
        warning_label: 'proxy layout',
        zero_load_signature_required: true,
      },
      {
        asset_ref: 'RD-010',
        geometry_available: true,
        segment_count: 18,
        solver_exact: true,
        status: 'solver_graph_ready',
      },
    ],
  },
};

const assets = data.meta.real_drawing_asset_registry;
const resolveDirect = resolveRealDrawingAssetRefForSelection({
  assets,
  selection: {memberId: 'RD-002', memberIds: ['RD-010']},
  selectedMemberId: 'RD-001',
  activeIsolation: {kind: 'member', value: 'RD-010'},
  queryAssetRef: 'RD-001',
});
const resolveMemberSet = resolveRealDrawingAssetRefForSelection({
  assets,
  selection: {memberId: 'MISSING', memberIds: ['RD-010']},
});
const resolveSelected = resolveRealDrawingAssetRefForSelection({
  assets,
  selectedMemberId: 'RD-001',
});
const resolveIsolation = resolveRealDrawingAssetRefForSelection({
  assets,
  activeIsolation: {kind: 'member', value: 'RD-002'},
});
const resolveQuery = resolveRealDrawingAssetRefForSelection({
  assets,
  activeIsolation: {kind: 'story', value: 'S1'},
  queryAssetRef: 'RD-010',
});
const resolveMissing = resolveRealDrawingAssetRefForSelection({
  assets,
  selection: {memberId: 'BAD'},
  queryAssetRef: 'NOPE',
});

const remembered = rememberRealDrawingAssetRef('RD-002', {
  assets,
  recentAssetRefs: ['RD-001', 'RD-404', 'RD-001'],
  maxRecent: 4,
});
const rememberedInvalid = rememberRealDrawingAssetRef('RD-404', {
  assets,
  recentAssetRefs: ['RD-001', 'RD-404', 'RD-002'],
  maxRecent: 4,
});
const recentFiltered = filterRecentRealDrawingAssetRefs({
  assets,
  recentAssetRefs: ['RD-010', 'RD-404', 'RD-002', 'RD-001'],
  maxRecent: 2,
});

const visibleProxy = getRealDrawingBrowserVisibleAssets(data, {
  activeFilter: 'proxy',
  activeQuery: 'zero-load proxy',
  activeSort: 'asset',
}).map((row) => row.asset_ref);
const visibleFallback = getRealDrawingBrowserVisibleAssets(data, {
  activeFilter: 'proxy',
  activeQuery: 'no-match-token',
  activeSort: 'asset',
}).map((row) => row.asset_ref);
const visibleNoFallback = getRealDrawingBrowserVisibleAssets(data, {
  activeFilter: 'proxy',
  activeQuery: 'no-match-token',
  activeSort: 'asset',
  fallbackToRegistry: false,
}).map((row) => row.asset_ref);

console.log(JSON.stringify({
  resolved: {
    direct: resolveDirect,
    memberSet: resolveMemberSet,
    selected: resolveSelected,
    isolation: resolveIsolation,
    query: resolveQuery,
    missing: resolveMissing,
  },
  active: {
    selected: getActiveRealDrawingAssetRef({
      assets,
      selectedMemberId: 'RD-010',
      sharedMemberId: 'RD-002',
      activeIsolation: {kind: 'member', value: 'RD-001'},
    }),
    shared: getActiveRealDrawingAssetRef({
      assets,
      selectedMemberId: 'BAD',
      sharedMemberId: 'RD-002',
      activeIsolation: {kind: 'member', value: 'RD-001'},
    }),
    isolated: getActiveRealDrawingAssetRef({
      assets,
      selectedMemberId: 'BAD',
      sharedMemberId: 'MISS',
      activeIsolation: {kind: 'member', value: 'RD-001'},
    }),
    fallback: getActiveRealDrawingAssetRef({assets}),
  },
  recents: {
    remembered,
    rememberedInvalid,
    recentFiltered,
  },
  visible: {
    proxy: visibleProxy,
    fallback: visibleFallback,
    noFallback: visibleNoFallback,
  },
  step: {
    next: stepRealDrawingAssetRef({assets, activeAssetRef: 'RD-001', direction: 1}),
    previous: stepRealDrawingAssetRef({assets, activeAssetRef: 'RD-001', direction: -1}),
    missingForward: stepRealDrawingAssetRef({assets, activeAssetRef: 'NOPE', direction: 1}),
    missingBackward: stepRealDrawingAssetRef({assets, activeAssetRef: 'NOPE', direction: -1}),
    empty: stepRealDrawingAssetRef({assets: [], activeAssetRef: 'RD-001', direction: 1}),
  },
}));
"""
    )

    assert payload["resolved"] == {
        "direct": "RD-002",
        "memberSet": "RD-010",
        "selected": "RD-001",
        "isolation": "RD-002",
        "query": "RD-010",
        "missing": "",
    }
    assert payload["active"] == {
        "selected": "RD-010",
        "shared": "RD-002",
        "isolated": "RD-001",
        "fallback": "RD-001",
    }
    assert payload["recents"] == {
        "remembered": ["RD-002", "RD-001"],
        "rememberedInvalid": ["RD-001", "RD-002"],
        "recentFiltered": ["RD-010", "RD-002"],
    }
    assert payload["visible"] == {
        "proxy": ["RD-002"],
        "fallback": ["RD-001", "RD-002", "RD-010"],
        "noFallback": [],
    }
    assert payload["step"] == {
        "next": "RD-002",
        "previous": "RD-010",
        "missingForward": "RD-001",
        "missingBackward": "RD-010",
        "empty": "",
    }
