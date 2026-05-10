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


def test_deformed_rendering_toolkit_exports_and_line_render_objects() -> None:
    payload = _run_node_contract_script(
        """
import * as THREE from './src/structure-viewer/vendor/three.module.js';
import {createViewerDeformedRenderingToolkit} from './src/structure-viewer/viewer-deformed-rendering.js';

const toolkit = createViewerDeformedRenderingToolkit(THREE, {meshTriangleBvhThreshold: 1});
const lineObjects = toolkit.createDeformedLineRenderObjects(
  {id: 'E-1', type: 'column'},
  [
    {id: 1, x: 0, y: 0, z: 0, dx: 0.1, dy: 0.2, dz: 0.3},
    {id: 2, x: 2, y: 1, z: 0, dx: 0, dy: 0, dz: 0},
  ],
  {factor: 10},
);

console.log(JSON.stringify({
  toolkitKeys: Object.keys(toolkit).sort(),
  radiusByType: {
    beam: toolkit.getDeformedLineRadius('beam'),
    column: toolkit.getDeformedLineRadius('column'),
    wall: toolkit.getDeformedLineRadius('wall'),
  },
  lineObjects: {
    mesh: lineObjects.mesh.isMesh,
    line: lineObjects.line.isLine,
    points: lineObjects.points.map(point => point.toArray()),
    meshUserData: lineObjects.mesh.userData,
    lineUserData: lineObjects.line.userData,
    linePointCount: lineObjects.line.geometry.getAttribute('position').count,
  },
}));
        """
    )

    assert payload["toolkitKeys"] == [
        "applyDeformedPickAcceleration",
        "buildDeformedPickAcceleration",
        "clearDeformedPickAcceleration",
        "createDeformedLineRenderObjects",
        "getDeformedLineRadius",
    ]
    assert payload["radiusByType"] == {
        "beam": 0.15,
        "column": 0.3,
        "wall": 0.12,
    }
    assert payload["lineObjects"] == {
        "mesh": True,
        "line": True,
        "points": [[1, 3, 2], [2, 0, 1]],
        "meshUserData": {
            "id": "E-1",
            "type": "column",
            "_deformed": True,
        },
        "lineUserData": {
            "_wireframe": True,
            "_deformedWireframe": True,
            "elemId": "E-1",
            "type": "column",
        },
        "linePointCount": 2,
    }


def test_deformed_rendering_toolkit_build_apply_and_clear_pick_acceleration() -> None:
    payload = _run_node_contract_script(
        """
import * as THREE from './src/structure-viewer/vendor/three.module.js';
import {createViewerDeformedRenderingToolkit} from './src/structure-viewer/viewer-deformed-rendering.js';

const toolkit = createViewerDeformedRenderingToolkit(THREE, {meshTriangleBvhThreshold: 1});

const geometry = new THREE.BufferGeometry();
geometry.setAttribute('position', new THREE.Float32BufferAttribute([
  0, 0, 0,
  1, 0, 0,
  0, 1, 0,
], 3));

const matchedMesh = new THREE.Mesh(geometry, new THREE.MeshBasicMaterial());
matchedMesh.userData = {id: 'E-2', member_id: 'M-2'};
matchedMesh.position.set(4, 5, 6);

const ignoredMesh = new THREE.Mesh(geometry.clone(), new THREE.MeshBasicMaterial());
ignoredMesh.userData = {id: 'E-missing', member_id: 'M-missing'};

const pickSpatialIndex = {
  records: [
    {label: 'record-0'},
    {label: 'record-1'},
  ],
  recordIndexByElementId: new Map([['E-2', 1]]),
  recordIndexByMemberId: new Map([['M-2', 1]]),
  deformedMeshTriangleEntries: ['stale'],
  deformedMeshLocalTriangleCatalogs: ['stale'],
  deformedMeshTriangleBvh: {kind: 'stale'},
};

const largeModelBuildProfile = {
  pickSpatialDeformedMeshTriangleCount: 99,
  pickSpatialDeformedMeshTriangleBvhEnabled: true,
  pickSpatialDeformedMeshLocalCatalogCount: 99,
};

const helperCalls = {
  append: [],
  local: [],
  bvh: [],
};

const acceleration = toolkit.buildDeformedPickAcceleration([matchedMesh, ignoredMesh], pickSpatialIndex, {
  appendPickMeshTrianglesFromGeometry(geometry, matrixWorld, recordIndex, triangleEntries) {
    helperCalls.append.push({
      recordIndex,
      geometryKind: geometry.type,
      translation: [matrixWorld.elements[12], matrixWorld.elements[13], matrixWorld.elements[14]],
    });
    triangleEntries.push({recordIndex, kind: 'triangle'});
  },
  buildLocalGeometryTriangleEntries(geometry) {
    helperCalls.local.push({geometryKind: geometry.type});
    return [{kind: 'local', geometryKind: geometry.type}];
  },
  buildPickMeshTriangleBvh(entries) {
    helperCalls.bvh.push({size: entries.length});
    return {kind: 'triangle-bvh', size: entries.length};
  },
});

toolkit.applyDeformedPickAcceleration(pickSpatialIndex, largeModelBuildProfile, acceleration);

const applied = {
  triangleEntries: pickSpatialIndex.deformedMeshTriangleEntries,
  localCatalogs: pickSpatialIndex.deformedMeshLocalTriangleCatalogs.map(catalog => ({
    key: catalog.key,
    recordIndex: catalog.recordIndex,
    triangleEntriesLength: catalog.triangleEntries.length,
    triangleBvh: catalog.triangleBvh,
    meshUuid: catalog.meshUuid,
    instanceId: catalog.instanceId,
  })),
  triangleBvh: pickSpatialIndex.deformedMeshTriangleBvh,
  recordCatalogRefs: pickSpatialIndex.records.map(record => record.deformedPickMeshLocalCatalog?.key || null),
  profile: {
    pickSpatialDeformedMeshTriangleCount: largeModelBuildProfile.pickSpatialDeformedMeshTriangleCount,
    pickSpatialDeformedMeshTriangleBvhEnabled: largeModelBuildProfile.pickSpatialDeformedMeshTriangleBvhEnabled,
    pickSpatialDeformedMeshLocalCatalogCount: largeModelBuildProfile.pickSpatialDeformedMeshLocalCatalogCount,
  },
};

toolkit.clearDeformedPickAcceleration(pickSpatialIndex, largeModelBuildProfile);

const cleared = {
  triangleEntries: pickSpatialIndex.deformedMeshTriangleEntries,
  localCatalogs: pickSpatialIndex.deformedMeshLocalTriangleCatalogs,
  triangleBvh: pickSpatialIndex.deformedMeshTriangleBvh,
  recordCatalogRefs: pickSpatialIndex.records.map(record => record.deformedPickMeshLocalCatalog ?? null),
  profile: {
    pickSpatialDeformedMeshTriangleCount: largeModelBuildProfile.pickSpatialDeformedMeshTriangleCount,
    pickSpatialDeformedMeshTriangleBvhEnabled: largeModelBuildProfile.pickSpatialDeformedMeshTriangleBvhEnabled,
    pickSpatialDeformedMeshLocalCatalogCount: largeModelBuildProfile.pickSpatialDeformedMeshLocalCatalogCount,
  },
};

console.log(JSON.stringify({
  helperCalls,
  build: {
    triangleEntries: acceleration.triangleEntries,
    localCatalogs: acceleration.localCatalogs.map(catalog => ({
      key: catalog.key,
      recordIndex: catalog.recordIndex,
      triangleEntriesLength: catalog.triangleEntries.length,
      triangleBvh: catalog.triangleBvh,
      meshUuid: catalog.meshUuid,
      instanceId: catalog.instanceId,
    })),
    triangleBvh: acceleration.triangleBvh,
    localCatalogByRecordIndexKeys: Array.from(acceleration.localCatalogByRecordIndex.keys()),
    recordsLength: acceleration.records.length,
  },
  applied,
  cleared,
}));
        """
    )

    mesh_uuid = payload["build"]["localCatalogs"][0]["meshUuid"]
    assert isinstance(mesh_uuid, str) and mesh_uuid

    assert payload["helperCalls"] == {
        "append": [
            {
                "recordIndex": 1,
                "geometryKind": "BufferGeometry",
                "translation": [4, 5, 6],
            },
        ],
        "local": [
            {
                "geometryKind": "BufferGeometry",
            },
        ],
        "bvh": [
            {"size": 1},
            {"size": 1},
        ],
    }
    assert payload["build"] == {
        "triangleEntries": [
            {"recordIndex": 1, "kind": "triangle"},
        ],
        "localCatalogs": [
            {
                "key": "deformed::E-2",
                "recordIndex": 1,
                "triangleEntriesLength": 1,
                "triangleBvh": {"kind": "triangle-bvh", "size": 1},
                "meshUuid": mesh_uuid,
                "instanceId": None,
            },
        ],
        "triangleBvh": {"kind": "triangle-bvh", "size": 1},
        "localCatalogByRecordIndexKeys": [1],
        "recordsLength": 2,
    }
    assert payload["applied"] == {
        "triangleEntries": [
            {"recordIndex": 1, "kind": "triangle"},
        ],
        "localCatalogs": [
            {
                "key": "deformed::E-2",
                "recordIndex": 1,
                "triangleEntriesLength": 1,
                "triangleBvh": {"kind": "triangle-bvh", "size": 1},
                "meshUuid": mesh_uuid,
                "instanceId": None,
            },
        ],
        "triangleBvh": {"kind": "triangle-bvh", "size": 1},
        "recordCatalogRefs": [None, "deformed::E-2"],
        "profile": {
            "pickSpatialDeformedMeshTriangleCount": 1,
            "pickSpatialDeformedMeshTriangleBvhEnabled": True,
            "pickSpatialDeformedMeshLocalCatalogCount": 1,
        },
    }
    assert payload["cleared"] == {
        "triangleEntries": [],
        "localCatalogs": [],
        "triangleBvh": None,
        "recordCatalogRefs": [None, None],
        "profile": {
            "pickSpatialDeformedMeshTriangleCount": 0,
            "pickSpatialDeformedMeshTriangleBvhEnabled": False,
            "pickSpatialDeformedMeshLocalCatalogCount": 0,
        },
    }
