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


def test_contour_material_toolkit_exports_and_applies_attributes() -> None:
    payload = _run_node_contract_script(
        """
import * as THREE from './src/structure-viewer/vendor/three.module.js';
import {createViewerContourMaterialToolkit} from './src/structure-viewer/viewer-contour-materials.js';

const toolkit = createViewerContourMaterialToolkit(THREE, {
  contourLutSize: 4,
  nodeContourFields: new Set(['disp_mag', 'stress_vm']),
});
const context = {
  field: 'disp_mag',
  mn: 0,
  mx: 10,
  cmapFn: t => new THREE.Color(t, 0, 1 - t),
};
const overrideContext = {
  ...context,
  nodeScalarById: {
    overrideA: 2,
    overrideB: 8,
  },
};
const lineGeometry = new THREE.BufferGeometry().setFromPoints([
  new THREE.Vector3(0, 0, 0),
  new THREE.Vector3(10, 0, 0),
]);
const lineNodes = [
  {x: 0, y: 0, z: 0, disp_mag: 0},
  {x: 10, y: 0, z: 0, disp_mag: 10},
];
toolkit.applyLineTubeContourColors(lineGeometry, lineNodes, {nodeData: lineNodes}, context);

const surfaceGeometry = new THREE.BufferGeometry();
surfaceGeometry.setAttribute('position', new THREE.BufferAttribute(new Float32Array([
  0, 0, 0,
  1, 0, 0,
  1, 1, 0,
  0, 1, 0,
]), 3));
surfaceGeometry.setAttribute('uv', new THREE.BufferAttribute(new Float32Array([
  0, 0,
  1, 0,
  1, 1,
  0, 1,
]), 2));
const surfaceNodes = [
  {disp_mag: 0},
  {disp_mag: 10},
  {disp_mag: 10},
  {disp_mag: 0},
];
toolkit.applySurfaceContourScalars(surfaceGeometry, surfaceNodes, {nodeData: surfaceNodes}, context);
const mesh = new THREE.Mesh(surfaceGeometry, new THREE.MeshPhongMaterial());
mesh.userData = {type: 'slab', contourGeometryKind: 'surface'};
toolkit.applySurfaceContourShaderMaterial(mesh, context, {tint: {color: new THREE.Color(0.25, 0.5, 0.75), mix: 0.4}});

console.log(JSON.stringify({
  toolkitKeys: Object.keys(toolkit).sort(),
  lineColors: Array.from(lineGeometry.getAttribute('color').array).map(value => Number(value.toFixed(3))),
  surfaceScalars: Array.from(surfaceGeometry.getAttribute('contourScalar').array).map(value => Number(value.toFixed(3))),
  fieldChecks: [
    toolkit.isNodeContourField('disp_mag'),
    toolkit.isNodeContourField('not_a_node_field'),
  ],
  contour: {
    t: toolkit.resolveContourT(5, context),
    color: toolkit.resolveContourColor(10, context).toArray(),
    nodeColor: toolkit.resolveNodeContourColor({disp_mag: 0}, context).toArray(),
    value: toolkit.resolveContourValue({nodeData: surfaceNodes}, 'disp_mag'),
    overrideNodeColor: toolkit.resolveNodeContourColor({id: 'overrideA', disp_mag: 0}, overrideContext).toArray(),
    overrideValue: toolkit.resolveContourValue({
      nodeData: [
        {id: 'overrideA', disp_mag: 0},
        {id: 'overrideB', disp_mag: 0},
      ],
    }, 'disp_mag', overrideContext),
  },
  material: {
    isShader: mesh.material.isShaderMaterial,
    opacity: mesh.material.uniforms.uOpacity.value,
    tint: mesh.material.uniforms.uTint.value.toArray().map(value => Number(value.toFixed(3))),
    tintMix: mesh.material.uniforms.uTintMix.value,
    lutWidth: mesh.material.uniforms.uContourLut.value.image.width,
  },
}));
        """
    )

    assert payload["toolkitKeys"] == [
        "applyLineTubeContourColors",
        "applySurfaceContourColors",
        "applySurfaceContourScalars",
        "applySurfaceContourShaderMaterial",
        "buildConstantColorAttribute",
        "buildConstantScalarAttribute",
        "buildContourLutTexture",
        "createSurfaceContourShaderMaterial",
        "ensureSurfaceContourShaderMaterial",
        "isNodeContourField",
        "resolveContourColor",
        "resolveContourT",
        "resolveContourValue",
        "resolveNodeContourColor",
        "sampleBilinearScalar",
        "updateDirectMeshContourGeometry",
    ]
    assert payload["lineColors"] == [0, 0, 1, 1, 0, 0]
    assert payload["surfaceScalars"] == [0, 1, 1, 0]
    assert payload["fieldChecks"] == [True, False]
    assert payload["contour"] == {
        "t": 0.5,
        "color": [1, 0, 0],
        "nodeColor": [0, 0, 1],
        "value": 5,
        "overrideNodeColor": [0.2, 0, 0.8],
        "overrideValue": 5,
    }
    assert payload["material"] == {
        "isShader": True,
        "opacity": 0.72,
        "tint": [0.25, 0.5, 0.75],
        "tintMix": 0.4,
        "lutWidth": 4,
    }
