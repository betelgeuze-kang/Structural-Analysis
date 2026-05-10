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


def test_large_model_picking_toolkit_exports_and_queries_candidates() -> None:
    payload = _run_node_contract_script(
        """
import * as THREE from './src/structure-viewer/vendor/three.module.js';
import {createViewerLargeModelPickingToolkit} from './src/structure-viewer/viewer-large-model-picking.js';

const records = [
  {label: 'mesh-near', data: {id: 'mesh-near'}, pickKind: 'line'},
  {label: 'mesh-far', data: {id: 'mesh-far'}, pickKind: 'line'},
  {label: 'surface', data: {id: 'surface'}, pickKind: 'surface'},
  {label: 'overflow', data: {id: 'overflow'}, pickKind: 'line'},
];
const helperCalls = [];
const toolkit = createViewerLargeModelPickingToolkit(THREE, {
  lineScreenTolerancePx: 10,
  getBoundingDiagonal: () => 100,
  intersectRayBoxDistances: () => null,
  shouldIncludePickSpatialIndexOverflowRecord: () => true,
  estimatePickRecordEntryDistance: () => 0,
  queryPickMeshTriangleBvh(_node, _entries, _ray, visit) {
    helperCalls.push('mesh');
    visit(1, 8);
    visit(0, 4);
  },
  queryPickSurfaceFacetBvh(_node, _entries, _ray, visit) {
    helperCalls.push('surface');
    visit(2, 6);
  },
  queryPickSpatialIndexOverflowBvh(_node, _ray, visit) {
    helperCalls.push('overflow');
    visit(3, 2);
  },
});
const ray = new THREE.Ray(new THREE.Vector3(0, 0, 0), new THREE.Vector3(0, 0, 1));
const index = {
  records,
  meshTriangleBvh: {},
  meshTriangleEntries: [],
  surfaceFacetBvh: {},
  surfaceFacetEntries: [],
  nonSurfaceRecordBvh: {},
  fullRecordBvh: null,
  overflowBvh: null,
  overflowIndices: [],
  denseBucketBvh: null,
  denseBucketRecordIndices: [],
  boundsMin: new THREE.Vector3(-1, -1, -1),
  boundsMax: new THREE.Vector3(1, 1, 10),
  buckets: new Map(),
  visitedCellCap: 1,
};
const candidates = toolkit.queryPickSpatialIndexCandidates(index, ray);

console.log(JSON.stringify({
  toolkitKeys: Object.keys(toolkit).sort(),
  helperCalls,
  candidates: candidates.map(candidate => ({
    label: candidate.record.label,
    entryDistance: candidate.entryDistance,
  })),
}));
        """
    )

    assert payload["toolkitKeys"] == [
        "intersectLargeModelLineRecord",
        "intersectLargeModelSurfaceRecord",
        "pickLargeModelRecord",
        "queryPickSpatialIndexCandidates",
    ]
    assert payload["helperCalls"] == ["mesh", "surface", "overflow"]
    assert payload["candidates"] == [
        {"label": "overflow", "entryDistance": 2},
        {"label": "mesh-near", "entryDistance": 4},
        {"label": "surface", "entryDistance": 6},
        {"label": "mesh-far", "entryDistance": 8},
    ]


def test_large_model_picking_toolkit_intersects_line_surface_and_best_visible_record() -> None:
    payload = _run_node_contract_script(
        """
import * as THREE from './src/structure-viewer/vendor/three.module.js';
import {createViewerLargeModelPickingToolkit} from './src/structure-viewer/viewer-large-model-picking.js';

const ray = new THREE.Ray(new THREE.Vector3(0.25, 0.25, 0), new THREE.Vector3(0, 0, 1));
const hiddenLine = {
  pickKind: 'line',
  data: {id: 'hidden'},
  pickCenter: new THREE.Vector3(0.25, 0.25, 2),
  pickRadius: 2,
  points: [new THREE.Vector3(-0.5, 0.25, 2), new THREE.Vector3(0.5, 0.25, 2)],
};
const fallbackLine = {
  pickKind: 'line',
  data: {id: 'fallback-line'},
  pickCenter: new THREE.Vector3(0.25, 0.25, 6),
  pickRadius: 2,
  points: [new THREE.Vector3(-0.5, 0.25, 6), new THREE.Vector3(0.5, 0.25, 6)],
};
const localLine = {
  pickKind: 'line',
  data: {id: 'local-line'},
  pickCenter: new THREE.Vector3(0.25, 0.25, 5),
  pickRadius: 2,
  points: [new THREE.Vector3(-0.5, 0.25, 5), new THREE.Vector3(0.5, 0.25, 5)],
};
const surface = {
  pickKind: 'surface',
  data: {id: 'surface'},
  pickCenter: new THREE.Vector3(0.5, 0.5, 4),
  pickRadius: 2,
  points: [
    new THREE.Vector3(0, 0, 4),
    new THREE.Vector3(1, 0, 4),
    new THREE.Vector3(1, 1, 4),
    new THREE.Vector3(0, 1, 4),
  ],
};
const records = [hiddenLine, fallbackLine, surface];
const spatialIndex = {
  records,
  meshTriangleBvh: {},
  meshTriangleEntries: [],
  surfaceFacetBvh: null,
  surfaceFacetEntries: [],
  nonSurfaceRecordBvh: null,
  fullRecordBvh: null,
  overflowBvh: null,
  overflowIndices: [],
  denseBucketBvh: null,
  denseBucketRecordIndices: [],
  boundsMin: new THREE.Vector3(-1, -1, -1),
  boundsMax: new THREE.Vector3(2, 2, 8),
  buckets: new Map(),
  visitedCellCap: 1,
};
const toolkit = createViewerLargeModelPickingToolkit(THREE, {
  lineScreenTolerancePx: 10,
  worldUnitsPerPixelAtPoint: () => 0.1,
  getShowDeformed: () => true,
  getPickAnalyticSpatialIndex: () => spatialIndex,
  getPickAnalyticRecords: () => records,
  isLargeModelPickAccelerationEnabled: () => true,
  isElementVisible: data => data?.id !== 'hidden',
  intersectRayBoxDistances: () => null,
  shouldIncludePickSpatialIndexOverflowRecord: () => true,
  estimatePickRecordEntryDistance: () => 0,
  queryPickMeshTriangleBvh(_node, _entries, _ray, visit) {
    visit(0, 1);
    visit(1, 2);
    visit(2, 3);
  },
  queryPickSurfaceFacetBvh() {},
  queryPickSpatialIndexOverflowBvh() {},
  intersectLargeModelMeshLocalCatalog(_ray, record, options) {
    if (record?.data?.id === 'local-line') {
      return {distance: 2, mesh: 'local-mesh', data: {id: 'local-hit', preferDeformed: options.preferDeformed}};
    }
    return null;
  },
  computePickBoundingSphere(points) {
    const center = points.reduce((acc, point) => acc.add(point), new THREE.Vector3()).multiplyScalar(1 / points.length);
    return {center};
  },
});

console.log(JSON.stringify({
  localLineHit: toolkit.intersectLargeModelLineRecord(ray, localLine),
  fallbackLineHit: toolkit.intersectLargeModelLineRecord(ray, fallbackLine),
  surfaceHit: toolkit.intersectLargeModelSurfaceRecord(ray, surface),
  bestHit: toolkit.pickLargeModelRecord(ray),
}));
        """
    )

    assert payload["localLineHit"] == {
        "distance": 2,
        "mesh": "local-mesh",
        "data": {"id": "local-hit", "preferDeformed": True},
    }
    assert payload["fallbackLineHit"] == {
        "distance": 6,
        "mesh": None,
        "data": {"id": "fallback-line"},
    }
    assert payload["surfaceHit"] == {
        "distance": 4,
        "mesh": None,
        "data": {"id": "surface"},
    }
    assert payload["bestHit"] == {
        "distance": 4,
        "mesh": None,
        "data": {"id": "surface"},
    }
