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


def test_pick_broadphase_toolkit_filters_targets_and_builds_acceleration_records() -> None:
    payload = _run_node_contract_script(
        """
import * as THREE from './src/structure-viewer/vendor/three.module.js';
import {createViewerPickBroadphaseToolkit} from './src/structure-viewer/viewer-pick-broadphase.js';

function makeMesh(id, x, userData = {}, visible = true) {
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.Float32BufferAttribute([
    -0.5, 0, 0,
    0.5, 0, 0,
    0, 0.5, 0,
  ], 3));
  const mesh = new THREE.Mesh(geometry, new THREE.MeshBasicMaterial());
  mesh.position.set(x, 0, 0);
  mesh.userData = {id, ...userData};
  mesh.visible = visible;
  return mesh;
}

const direct = makeMesh('direct', 0);
const surfaceFallback = makeMesh('surface-fallback', 1, {_surfaceDirectFallback: true});
const wireframe = makeMesh('wireframe', 2, {_wireframe: true});
const hidden = makeMesh('hidden', 3, {}, false);
const hiddenInstancedSurface = makeMesh('hidden-instanced-surface', 4, {
  _instancedGroup: true,
  _instancedSurfaceGroup: true,
  instanceRecords: [{data: {visible: false}}],
});
const visibleInstancedSurface = makeMesh('visible-instanced-surface', 0.25, {
  _instancedGroup: true,
  _instancedSurfaceGroup: true,
  instanceRecords: [{data: {visible: true}}],
});
const visibleInstancedLine = makeMesh('visible-instanced-line', 0.5, {
  _instancedGroup: true,
  instanceRecords: [{data: {visible: true}}],
});

const toolkit = createViewerPickBroadphaseToolkit(THREE, {
  accelerationThreshold: 1,
  lineScreenTolerancePx: 10,
  getBoundingDiagonal: () => 100,
  getSurfaceRenderLodProfile: () => ({pickFromInstancedSurfaces: true}),
  isElementVisible: data => data?.visible !== false,
});

const cache = toolkit.buildPickTargetMeshCache({
  children: [
    direct,
    surfaceFallback,
    wireframe,
    hidden,
    hiddenInstancedSurface,
    visibleInstancedSurface,
    visibleInstancedLine,
  ],
});

console.log(JSON.stringify({
  toolkitKeys: Object.keys(toolkit).sort(),
  preferInstancedSurfacePicking: toolkit.shouldPreferInstancedSurfacePicking(),
  hiddenInstancedVisible: toolkit.hasVisibleInstancedRecords(hiddenInstancedSurface),
  visibleInstancedVisible: toolkit.hasVisibleInstancedRecords(visibleInstancedSurface),
  targetIds: cache.pickTargetMeshes.map(mesh => mesh.userData.id),
  accelerationRecords: cache.pickAccelerationRecords.map(record => ({
    id: record.mesh.userData.id,
    center: record.center.toArray(),
    radiusPositive: record.radius > 0,
    isInstanced: record.isInstanced,
    isSurface: record.isSurface,
  })),
}));
        """
    )

    assert payload["toolkitKeys"] == [
        "buildPickAccelerationRecord",
        "buildPickTargetMeshCache",
        "getPickableMeshesFromCache",
        "hasVisibleInstancedRecords",
        "shouldPreferInstancedSurfacePicking",
    ]
    assert payload["preferInstancedSurfacePicking"] is True
    assert payload["hiddenInstancedVisible"] is False
    assert payload["visibleInstancedVisible"] is True
    assert payload["targetIds"] == ["direct", "visible-instanced-surface", "visible-instanced-line"]
    assert payload["accelerationRecords"] == [
        {
            "id": "direct",
            "center": [0, 0.25, 0],
            "radiusPositive": True,
            "isInstanced": False,
            "isSurface": False,
        },
        {
            "id": "visible-instanced-surface",
            "center": [0.25, 0.25, 0],
            "radiusPositive": True,
            "isInstanced": True,
            "isSurface": True,
        },
        {
            "id": "visible-instanced-line",
            "center": [0.5, 0.25, 0],
            "radiusPositive": True,
            "isInstanced": True,
            "isSurface": False,
        },
    ]


def test_pick_broadphase_toolkit_returns_near_ray_candidates_or_cache_fallback() -> None:
    payload = _run_node_contract_script(
        """
import * as THREE from './src/structure-viewer/vendor/three.module.js';
import {createViewerPickBroadphaseToolkit} from './src/structure-viewer/viewer-pick-broadphase.js';

function makeRecord(id, x, isSurface = false) {
  const mesh = {visible: true, userData: {id}};
  return {
    mesh,
    center: new THREE.Vector3(x, 0, 0),
    radius: 0.25,
    isSurface,
  };
}

const near = makeRecord('near', 0.1);
const surfaceNear = makeRecord('surface-near', 0.9, true);
const far = makeRecord('far', 10);
const cache = {
  pickTargetMeshes: [near.mesh, surfaceNear.mesh, far.mesh],
  pickAccelerationRecords: [far, surfaceNear, near],
};
const toolkit = createViewerPickBroadphaseToolkit(THREE, {
  accelerationThreshold: 2,
  lineScreenTolerancePx: 10,
  getBoundingDiagonal: () => 0,
});
const ray = new THREE.Ray(new THREE.Vector3(0, 0, 5), new THREE.Vector3(0, 0, -1));
const lowRecordToolkit = createViewerPickBroadphaseToolkit(THREE, {
  accelerationThreshold: 4,
});

console.log(JSON.stringify({
  rayCandidates: toolkit.getPickableMeshesFromCache(ray, cache).map(mesh => mesh.userData.id),
  noRayFallback: toolkit.getPickableMeshesFromCache(null, cache).map(mesh => mesh.userData.id),
  thresholdFallback: lowRecordToolkit.getPickableMeshesFromCache(ray, cache).map(mesh => mesh.userData.id),
}));
        """
    )

    assert payload["rayCandidates"] == ["near", "surface-near"]
    assert payload["noRayFallback"] == ["near", "surface-near", "far"]
    assert payload["thresholdFallback"] == ["near", "surface-near", "far"]
