function safeNumber(value, fallback = 0) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function normalizeField(value) {
  return String(value || '').trim();
}

function sampleBilinearColor(c00, c10, c11, c01, u, v) {
  const top = c00.clone().lerp(c10, u);
  const bottom = c01.clone().lerp(c11, u);
  return top.lerp(bottom, v);
}

function ensureThree(THREE) {
  if (!THREE?.Vector3 || !THREE?.BufferAttribute || !THREE?.DataTexture || !THREE?.ShaderMaterial) {
    throw new TypeError('A compatible THREE namespace is required');
  }
  return THREE;
}

export function createViewerContourMaterialToolkit(THREE, config = {}) {
  const T = ensureThree(THREE);
  const contourLutSize = Math.max(2, Math.round(safeNumber(config.contourLutSize, 256)));
  const nodeContourFields = new Set(Array.from(config.nodeContourFields || ['disp_mag', 'stress_vm']).map(normalizeField));

  function isNodeContourField(field) {
    return nodeContourFields.has(normalizeField(field));
  }

  function resolveContourT(value, context) {
    if (!context || context.mx <= context.mn) return 0;
    return Math.max(0, Math.min(1, (safeNumber(value, 0) - context.mn) / (context.mx - context.mn)));
  }

  function resolveContourColor(value, context) {
    return context.cmapFn(resolveContourT(value, context));
  }

  function resolveNodeContourColor(node, context) {
    return resolveContourColor(node?.[context.field] || 0, context);
  }

  function resolveContourValue(element, field) {
    if (isNodeContourField(field)) {
      const nodes = element?.nodeData || [];
      return nodes.length
        ? nodes.reduce((sum, node) => sum + (node[field] || 0), 0) / nodes.length
        : 0;
    }
    return element?.[field] || 0;
  }

  function buildContourLutTexture(context) {
    const data = new Uint8Array(contourLutSize * 4);
    for (let index = 0; index < contourLutSize; index += 1) {
      const color = context.cmapFn(index / Math.max(contourLutSize - 1, 1));
      data[index * 4] = Math.round(color.r * 255);
      data[index * 4 + 1] = Math.round(color.g * 255);
      data[index * 4 + 2] = Math.round(color.b * 255);
      data[index * 4 + 3] = 255;
    }
    const texture = new T.DataTexture(data, contourLutSize, 1, T.RGBAFormat);
    texture.magFilter = T.LinearFilter;
    texture.minFilter = T.LinearFilter;
    texture.wrapS = T.ClampToEdgeWrapping;
    texture.wrapT = T.ClampToEdgeWrapping;
    texture.needsUpdate = true;
    return texture;
  }

  function buildConstantColorAttribute(length, color) {
    const attr = new Float32Array(length * 3);
    for (let index = 0; index < length; index += 1) {
      attr[index * 3] = color.r;
      attr[index * 3 + 1] = color.g;
      attr[index * 3 + 2] = color.b;
    }
    return attr;
  }

  function buildConstantScalarAttribute(length, value) {
    const attr = new Float32Array(length);
    for (let index = 0; index < length; index += 1) attr[index] = value;
    return attr;
  }

  function sampleBilinearScalar(s00, s10, s11, s01, u, v) {
    return s00 * (1 - u) * (1 - v) + s10 * u * (1 - v) + s11 * u * v + s01 * (1 - u) * v;
  }

  function applyLineTubeContourColors(geometry, nodeData, element, context) {
    const positionAttr = geometry?.getAttribute?.('position');
    if (!positionAttr) return;
    const vertexCount = positionAttr.count;
    const colors = new Float32Array(vertexCount * 3);
    if (isNodeContourField(context.field) && Array.isArray(nodeData) && nodeData.length >= 2) {
      const start = new T.Vector3(nodeData[0].x, nodeData[0].z, nodeData[0].y);
      const end = new T.Vector3(nodeData[1].x, nodeData[1].z, nodeData[1].y);
      const axis = end.clone().sub(start);
      const axisLengthSq = Math.max(axis.lengthSq(), 1e-12);
      const startColor = resolveNodeContourColor(nodeData[0], context);
      const endColor = resolveNodeContourColor(nodeData[1], context);
      for (let index = 0; index < vertexCount; index += 1) {
        const vertex = new T.Vector3().fromBufferAttribute(positionAttr, index);
        const t = Math.max(0, Math.min(1, vertex.clone().sub(start).dot(axis) / axisLengthSq));
        const color = startColor.clone().lerp(endColor, t);
        colors[index * 3] = color.r;
        colors[index * 3 + 1] = color.g;
        colors[index * 3 + 2] = color.b;
      }
    } else {
      const color = resolveContourColor(resolveContourValue(element, context.field), context);
      colors.set(buildConstantColorAttribute(vertexCount, color));
    }
    geometry.setAttribute('color', new T.BufferAttribute(colors, 3));
  }

  function applySurfaceContourColors(geometry, nodeData, element, context) {
    const vertexCount = geometry?.getAttribute?.('position')?.count || 0;
    if (!vertexCount) return;
    if (isNodeContourField(context.field) && Array.isArray(nodeData) && nodeData.length >= 4) {
      const colorTriples = nodeData.slice(0, 4).map(node => resolveNodeContourColor(node, context));
      const uvAttr = geometry?.getAttribute?.('uv');
      const colors = new Float32Array(vertexCount * 3);
      for (let index = 0; index < vertexCount; index += 1) {
        const u = uvAttr ? Number(uvAttr.getX(index) || 0) : 0;
        const v = uvAttr ? Number(uvAttr.getY(index) || 0) : 0;
        const color = sampleBilinearColor(
          colorTriples[0],
          colorTriples[1],
          colorTriples[2],
          colorTriples[3],
          u,
          v,
        );
        colors[index * 3] = color.r;
        colors[index * 3 + 1] = color.g;
        colors[index * 3 + 2] = color.b;
      }
      geometry.setAttribute('color', new T.BufferAttribute(colors, 3));
      return;
    }
    const color = resolveContourColor(resolveContourValue(element, context.field), context);
    geometry.setAttribute('color', new T.BufferAttribute(buildConstantColorAttribute(vertexCount, color), 3));
  }

  function applySurfaceContourScalars(geometry, nodeData, element, context) {
    const vertexCount = geometry?.getAttribute?.('position')?.count || 0;
    if (!vertexCount) return;
    if (isNodeContourField(context.field) && Array.isArray(nodeData) && nodeData.length >= 4) {
      const uvAttr = geometry?.getAttribute?.('uv');
      const scalarCorners = nodeData.slice(0, 4).map(node => resolveContourT(node?.[context.field] || 0, context));
      const scalars = new Float32Array(vertexCount);
      for (let index = 0; index < vertexCount; index += 1) {
        const u = uvAttr ? Number(uvAttr.getX(index) || 0) : 0;
        const v = uvAttr ? Number(uvAttr.getY(index) || 0) : 0;
        scalars[index] = sampleBilinearScalar(
          scalarCorners[0],
          scalarCorners[1],
          scalarCorners[2],
          scalarCorners[3],
          u,
          v,
        );
      }
      geometry.setAttribute('contourScalar', new T.BufferAttribute(scalars, 1));
      return;
    }
    geometry.setAttribute(
      'contourScalar',
      new T.BufferAttribute(
        buildConstantScalarAttribute(vertexCount, resolveContourT(resolveContourValue(element, context.field), context)),
        1,
      ),
    );
  }

  function updateDirectMeshContourGeometry(mesh, context) {
    if (!(mesh?.geometry && mesh?.material)) return;
    if (mesh.userData?.contourGeometryKind === 'line_tube') {
      applyLineTubeContourColors(mesh.geometry, mesh.userData.nodeData, mesh.userData, context);
    } else if (mesh.userData?.contourGeometryKind === 'surface') {
      applySurfaceContourScalars(mesh.geometry, mesh.userData.nodeData, mesh.userData, context);
    } else {
      const vertexCount = mesh.geometry.getAttribute?.('position')?.count || 0;
      const color = resolveContourColor(resolveContourValue(mesh.userData, context.field), context);
      mesh.geometry.setAttribute('color', new T.BufferAttribute(buildConstantColorAttribute(vertexCount, color), 3));
    }
    if (mesh.userData?.contourGeometryKind === 'surface') {
      const scalarAttr = mesh.geometry.getAttribute('contourScalar');
      if (scalarAttr) scalarAttr.needsUpdate = true;
      return;
    }
    mesh.material.vertexColors = true;
    mesh.material.color.setHex(0xffffff);
    mesh.material.needsUpdate = true;
    mesh.geometry.getAttribute('color').needsUpdate = true;
  }

  function createSurfaceContourShaderMaterial(baseOpacity) {
    return new T.ShaderMaterial({
      uniforms: {
        uOpacity: { value: baseOpacity },
        uContourLut: { value: null },
        uTint: { value: new T.Vector3(1, 1, 1) },
        uTintMix: { value: 0 },
        uLightDir: { value: new T.Vector3(0.45, 0.9, 0.35).normalize() },
      },
      vertexShader: `
        attribute float contourScalar;
        varying float vContourScalar;
        varying vec3 vNormalView;
        void main(){
          vContourScalar=contourScalar;
          vNormalView=normalize(normalMatrix*normal);
          gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0);
        }
      `,
      fragmentShader: `
        uniform float uOpacity;
        uniform sampler2D uContourLut;
        uniform vec3 uTint;
        uniform float uTintMix;
        uniform vec3 uLightDir;
        varying float vContourScalar;
        varying vec3 vNormalView;
        void main(){
          float t=clamp(vContourScalar,0.0,1.0);
          vec3 contourColor=texture2D(uContourLut,vec2(t,0.5)).rgb;
          float light=0.58+0.42*abs(dot(normalize(vNormalView),normalize(uLightDir)));
          vec3 shaded=contourColor*light;
          vec3 tinted=mix(shaded,uTint,uTintMix);
          gl_FragColor=vec4(tinted,uOpacity);
        }
      `,
      transparent: true,
      side: T.DoubleSide,
    });
  }

  function ensureSurfaceContourShaderMaterial(mesh) {
    if (mesh.userData?.surfaceContourShaderMaterial) return mesh.userData.surfaceContourShaderMaterial;
    const baseOpacity = mesh.userData.type?.toLowerCase() === 'slab' ? 0.72 : 0.92;
    const material = createSurfaceContourShaderMaterial(baseOpacity);
    mesh.userData.surfaceContourShaderMaterial = material;
    return material;
  }

  function applySurfaceContourShaderMaterial(mesh, context, { tint = null } = {}) {
    if (!(mesh?.isMesh && mesh.userData?.contourGeometryKind === 'surface')) return;
    const material = ensureSurfaceContourShaderMaterial(mesh);
    if (mesh.material !== material) mesh.material = material;
    material.uniforms.uContourLut.value = buildContourLutTexture(context);
    material.uniforms.uOpacity.value = mesh.userData.type?.toLowerCase() === 'slab' ? 0.72 : 0.92;
    const resolvedTint = tint || { color: new T.Color(1, 1, 1), mix: 0 };
    material.uniforms.uTint.value.set(
      resolvedTint.color.r,
      resolvedTint.color.g,
      resolvedTint.color.b,
    );
    material.uniforms.uTintMix.value = safeNumber(resolvedTint.mix, 0);
    material.needsUpdate = true;
  }

  return Object.freeze({
    applyLineTubeContourColors,
    applySurfaceContourColors,
    applySurfaceContourScalars,
    applySurfaceContourShaderMaterial,
    buildConstantColorAttribute,
    buildConstantScalarAttribute,
    buildContourLutTexture,
    createSurfaceContourShaderMaterial,
    ensureSurfaceContourShaderMaterial,
    isNodeContourField,
    resolveContourColor,
    resolveContourT,
    resolveContourValue,
    resolveNodeContourColor,
    sampleBilinearScalar,
    updateDirectMeshContourGeometry,
  });
}
