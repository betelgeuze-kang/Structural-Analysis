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


def test_render_mesh_builder_toolkit_exports_and_creates_mesh_objects() -> None:
    payload = _run_node_contract_script(
        """
import * as THREE from './src/structure-viewer/vendor/three.module.js';
import {createViewerRenderMeshBuilderToolkit} from './src/structure-viewer/viewer-render-mesh-builders.js';

const toolkit = createViewerRenderMeshBuilderToolkit(THREE, {
  colors: {beam: 0x38bdf8, column: 0xf87171, wall: 0x34d399, slab: 0xfbbf24, other: 0x94a3b8},
});
const nodes = [
  {id: 1, x: 0, y: 0, z: 0, dx: 0.01, dy: 0, dz: 0},
  {id: 2, x: 2, y: 0, z: 0, dx: 0.02, dy: 0, dz: 0},
];
const surfaceNodes = [
  {id: 1, x: 0, y: 0, z: 0},
  {id: 2, x: 2, y: 0, z: 0},
  {id: 3, x: 2, y: 2, z: 0},
  {id: 4, x: 0, y: 2, z: 0},
];
const lineObjects = toolkit.createLineElementRenderObjects({
  element: {id: 'B1', type: 'beam', dcr: 0.9},
  nodes,
  type: 'beam',
  baseColorHex: 0x38bdf8,
  radius: 0.15,
  deformScale: 10,
});
const surfaceGeometry = new THREE.BufferGeometry();
surfaceGeometry.setAttribute('position', new THREE.BufferAttribute(new Float32Array([
  0, 0, 0,
  2, 0, 0,
  2, 0, 2,
  0, 0, 0,
  2, 0, 2,
  0, 0, 2,
]), 3));
const surfaceObjects = toolkit.createSurfaceElementRenderObjects({
  element: {id: 'S1', type: 'slab'},
  nodes: surfaceNodes,
  type: 'slab',
  baseColorHex: 0xfbbf24,
  vertices: surfaceNodes.map(node => new THREE.Vector3(node.x, node.z, node.y)),
  geometry: surfaceGeometry,
  isInstancedSurface: false,
  surfaceLodLabel: 'medium',
  surfaceContourSubdivisions: 4,
});
const instancedRecords = [
  {
    elementId: 'B1',
    memberId: 'M1',
    type: 'beam',
    baseColorHex: 0x38bdf8,
    data: {id: 'B1'},
    points: [new THREE.Vector3(0, 0, 0), new THREE.Vector3(2, 0, 0)],
    baseMatrix: new THREE.Matrix4(),
  },
];
const instancedLineGroup = toolkit.createInstancedLineGroupObjects(instancedRecords, 'beam', {radius: 0.15});
const instancedSurfaceGroup = toolkit.createInstancedSurfaceGroupObjects([
  {
    elementId: 'S1',
    memberId: 'M2',
    type: 'slab',
    baseColorHex: 0xfbbf24,
    data: {id: 'S1'},
    points: surfaceNodes.map(node => new THREE.Vector3(node.x, node.z, node.y)),
    baseMatrix: new THREE.Matrix4(),
  },
], 'slab');

console.log(JSON.stringify({
  toolkitKeys: Object.keys(toolkit).sort(),
  line: {
    mesh: lineObjects.mesh.isMesh,
    wireframe: lineObjects.wireframe.isLine,
    deformed: lineObjects.deformedMesh.isMesh,
    contourKind: lineObjects.meshData.contourGeometryKind,
    visualRadius: lineObjects.meshData.visualRadius,
    pickPointCount: lineObjects.pickPoints.length,
  },
  surface: {
    mesh: surfaceObjects.mesh.isMesh,
    edge: surfaceObjects.edgeLine.isLine,
    colorCount: surfaceObjects.mesh.geometry.getAttribute('color').count,
    contourKind: surfaceObjects.meshData.contourGeometryKind,
    lod: surfaceObjects.meshData.surfaceLodLabel,
    subdivisions: surfaceObjects.meshData.surfaceContourSubdivisions,
  },
  instancedLine: {
    mesh: instancedLineGroup.mesh.isInstancedMesh,
    wireframe: instancedLineGroup.wireframe.isLineSegments,
    recordMeshLinked: instancedRecords[0].mesh === instancedLineGroup.mesh,
    visualRadius: instancedLineGroup.visualRadius,
    meshVisualRadius: instancedLineGroup.mesh.userData.visualRadius,
    recordVisualRadius: instancedRecords[0].visualRadius,
    defaultOpacity: instancedLineGroup.defaultOpacity,
  },
  instancedSurface: {
    mesh: instancedSurfaceGroup.mesh.isInstancedMesh,
    wireframe: instancedSurfaceGroup.wireframe.isLineSegments,
    geometryKind: instancedSurfaceGroup.geometryKind,
    defaultOpacity: instancedSurfaceGroup.defaultOpacity,
  },
}));
        """
    )

    assert payload["toolkitKeys"] == [
        "createCableElementRenderObjects",
        "createInstancedLineGroupObjects",
        "createInstancedSurfaceGroupObjects",
        "createInstancedSurfaceWireframe",
        "createInstancedWireframe",
        "createLineElementRenderObjects",
        "createRebarElementRenderObjects",
        "createSolidElementRenderObjects",
        "createSurfaceElementRenderObjects",
        "createTerrainMesh",
        "getMaterialProperties",
        "getVisualRadius",
    ]
    assert payload["line"] == {
        "mesh": True,
        "wireframe": True,
        "deformed": True,
        "contourKind": "line_tube",
        "visualRadius": 0.15,
        "pickPointCount": 2,
    }
    assert payload["surface"] == {
        "mesh": True,
        "edge": True,
        "colorCount": 6,
        "contourKind": "surface",
        "lod": "medium",
        "subdivisions": 4,
    }
    assert payload["instancedLine"] == {
        "mesh": True,
        "wireframe": True,
        "recordMeshLinked": True,
        "visualRadius": 0.15,
        "meshVisualRadius": 0.15,
        "recordVisualRadius": 0.15,
        "defaultOpacity": 0.85,
    }
    assert payload["instancedSurface"] == {
        "mesh": True,
        "wireframe": True,
        "geometryKind": "surface",
        "defaultOpacity": 0.25,
    }
