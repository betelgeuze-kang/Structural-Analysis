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


def test_render_picking_geometry_toolkit_exports_and_core_contracts() -> None:
    payload = _run_node_contract_script(
        """
import * as THREE from './src/structure-viewer/vendor/three.module.js';
import {createViewerRenderPickingGeometryToolkit} from './src/structure-viewer/viewer-render-picking-geometry.js';

const toolkit = createViewerRenderPickingGeometryToolkit(THREE, {
  contourSurfaceTessellationMin: 2,
  contourSurfaceTessellationMax: 6,
  surfaceLodMediumElementThreshold: 10,
  surfaceLodCoarseElementThreshold: 20,
  surfaceLodMediumDirectSubdivisions: 4,
  surfaceLodCoarseDirectSubdivisions: 3,
  surfaceLodMediumInstancedSubdivisions: 2,
  surfaceLodCoarseInstancedSubdivisions: 1,
  instancedSurfaceElementThreshold: 3,
  pickOverflowBvhLeafSize: 2,
});

const square = [
  new THREE.Vector3(0, 0, 0),
  new THREE.Vector3(1, 0, 0),
  new THREE.Vector3(1, 1, 0),
  new THREE.Vector3(0, 1, 0),
];
const geometry = toolkit.buildContourSurfaceGeometry(square, 2);
const lod = toolkit.buildSurfaceLodProfile(25, 4);
const instancedSubdivisions = toolkit.computeSurfaceLodSubdivisions(square, lod, {isInstancedSurface: true});
const sphere = toolkit.computePickBoundingSphere([new THREE.Vector3(0, 0, 0), new THREE.Vector3(2, 0, 0)]);
const facets = toolkit.buildPickSurfaceFacetEntries([{pickKind: 'surface', points: square}]);
const triangleBvh = toolkit.buildPickMeshTriangleBvh(facets, 1);
const ray = new THREE.Ray(new THREE.Vector3(0.75, 0.25, -1), new THREE.Vector3(0, 0, 1));
const closestTriangleHit = toolkit.intersectPickTriangleBvhClosest(triangleBvh, facets, ray);
const visitedFacetRecords = [];
toolkit.queryPickSurfaceFacetBvh(triangleBvh, facets, ray, (recordIndex, distance) => {
  visitedFacetRecords.push({recordIndex, distance});
});
const rayBox = toolkit.intersectRayBoxDistances(
  new THREE.Ray(new THREE.Vector3(0.5, 0.5, -2), new THREE.Vector3(0, 0, 1)),
  new THREE.Vector3(0, 0, 0),
  new THREE.Vector3(1, 1, 1),
);

console.log(JSON.stringify({
  toolkitKeys: Object.keys(toolkit).sort(),
  geometry: {
    positionCount: geometry.getAttribute('position').count,
    uvCount: geometry.getAttribute('uv').count,
    indexCount: geometry.index.count,
  },
  lod,
  instancedSubdivisions,
  sphere: {
    center: sphere.center.toArray(),
    radius: sphere.radius,
  },
  facets: {
    count: facets.length,
    recordIndices: facets.map(facet => facet.recordIndex),
  },
  closestTriangleHit: {
    distance: closestTriangleHit?.distance ?? null,
    entryIndex: closestTriangleHit?.entryIndex ?? null,
  },
  visitedFacetRecords,
  rayBox,
}));
        """
    )

    assert payload["toolkitKeys"] == [
        "appendPickMeshTrianglesFromGeometry",
        "buildContourSurfaceGeometry",
        "buildHighResolutionContourSurfaceGeometry",
        "buildLocalGeometryTriangleEntries",
        "buildLodSurfaceContourGeometry",
        "buildPickBoundsBvh",
        "buildPickMeshTriangleBvh",
        "buildPickSpatialIndexOverflowBvh",
        "buildPickSurfaceFacetBvh",
        "buildPickSurfaceFacetEntries",
        "buildSurfaceLodProfile",
        "clampPickSpatialIndexCoord",
        "computeAdaptiveContourSubdivisions",
        "computeLineElementMatrix",
        "computePickBoundingSphere",
        "computeSurfaceElementMatrix",
        "computeSurfaceLodSubdivisions",
        "createLocalRayFromWorldRay",
        "estimatePickRecordEntryDistance",
        "getPickSpatialIndexAxisCellSize",
        "getPickSpatialIndexCellCoords",
        "getPickSpatialIndexKey",
        "intersectLargeModelMeshLocalCatalog",
        "intersectPickTriangleBvhClosest",
        "intersectRayBoxDistances",
        "queryPickMeshTriangleBvh",
        "queryPickSpatialIndexOverflowBvh",
        "queryPickSurfaceFacetBvh",
        "sampleBilinearColor",
        "sampleBilinearPoint",
        "shouldIncludePickSpatialIndexOverflowRecord",
    ]
    assert payload["geometry"] == {
        "positionCount": 9,
        "uvCount": 9,
        "indexCount": 24,
    }
    assert payload["lod"] == {
        "label": "coarse",
        "directSurfaceMaxSubdivisions": 3,
        "instancedSurfaceMaxSubdivisions": 1,
        "pickFromInstancedSurfaces": True,
    }
    assert payload["instancedSubdivisions"] == 1
    assert payload["sphere"] == {"center": [1, 0, 0], "radius": 1}
    assert payload["facets"] == {"count": 2, "recordIndices": [0, 0]}
    assert payload["closestTriangleHit"] == {"distance": 1, "entryIndex": 0}
    assert payload["visitedFacetRecords"] == [{"recordIndex": 0, "distance": 1}]
    assert payload["rayBox"] == {"entry": 2, "exit": 3}
