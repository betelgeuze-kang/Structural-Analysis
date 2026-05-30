function safeNumber(value, fallback = 0) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function normalizeElementType(value) {
  return String(value || 'beam').trim().toLowerCase() || 'beam';
}

function resolveTypeColor(colors, type) {
  const normalized = normalizeElementType(type);
  return safeNumber(colors?.[normalized], safeNumber(colors?.other, 0x94a3b8));
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

function nodeToViewerVector(THREE, node) {
  return new THREE.Vector3(
    safeNumber(node?.x, 0),
    safeNumber(node?.z, 0),
    safeNumber(node?.y, 0),
  );
}

function nodeToDeformedViewerVector(THREE, node, deformScale) {
  return new THREE.Vector3(
    safeNumber(node?.x, 0) + safeNumber(node?.dx, 0) * deformScale,
    safeNumber(node?.z, 0) + safeNumber(node?.dz, 0) * deformScale,
    safeNumber(node?.y, 0) + safeNumber(node?.dy, 0) * deformScale,
  );
}

function ensureThree(THREE) {
  if (!THREE?.Vector3 || !THREE?.BufferGeometry || !THREE?.Mesh || !THREE?.InstancedMesh) {
    throw new TypeError('A compatible THREE namespace is required');
  }
  return THREE;
}

export function createViewerRenderMeshBuilderToolkit(THREE, config = {}) {
  const T = ensureThree(THREE);
  const colors = config.colors || {};

  function createInstancedWireframe(records, type) {
    const items = Array.isArray(records) ? records : [];
    const positions = new Float32Array(items.length * 2 * 3);
    const colorValues = new Float32Array(items.length * 2 * 3);
    items.forEach((record, index) => {
      positions.set(record.points[0].toArray(), index * 6);
      positions.set(record.points[1].toArray(), index * 6 + 3);
      const baseColor = new T.Color(record.baseColorHex);
      colorValues.set([baseColor.r, baseColor.g, baseColor.b, baseColor.r, baseColor.g, baseColor.b], index * 6);
    });
    const basePositions = new Float32Array(positions);
    const geometry = new T.BufferGeometry();
    geometry.setAttribute('position', new T.BufferAttribute(positions, 3));
    geometry.setAttribute('color', new T.BufferAttribute(colorValues, 3));
    const material = new T.LineBasicMaterial({
      color: new T.Color(resolveTypeColor(colors, type)),
      vertexColors: true,
      transparent: true,
      opacity: 0.85,
    });
    const wireframe = new T.LineSegments(geometry, material);
    wireframe.userData = { _wireframe: true, _instancedWireframe: true, type, basePositions };
    return wireframe;
  }

  function createInstancedSurfaceWireframe(records, type) {
    const items = Array.isArray(records) ? records : [];
    const positions = new Float32Array(items.length * 8 * 3);
    const colorValues = new Float32Array(items.length * 8 * 3);
    items.forEach((record, index) => {
      const offset = index * 24;
      const corners = Array.isArray(record.points) ? record.points : [];
      const path = [
        corners[0], corners[1],
        corners[1], corners[2],
        corners[2], corners[3],
        corners[3], corners[0],
      ];
      path.forEach((point, vertexIndex) => {
        if (point?.toArray) positions.set(point.toArray(), offset + vertexIndex * 3);
      });
      const baseColor = new T.Color(record.baseColorHex);
      for (let vertexIndex = 0; vertexIndex < 8; vertexIndex += 1) {
        colorValues[offset + vertexIndex * 3] = baseColor.r;
        colorValues[offset + vertexIndex * 3 + 1] = baseColor.g;
        colorValues[offset + vertexIndex * 3 + 2] = baseColor.b;
      }
    });
    const basePositions = new Float32Array(positions);
    const geometry = new T.BufferGeometry();
    geometry.setAttribute('position', new T.BufferAttribute(positions, 3));
    geometry.setAttribute('color', new T.BufferAttribute(colorValues, 3));
    const material = new T.LineBasicMaterial({
      color: new T.Color(resolveTypeColor(colors, type)),
      vertexColors: true,
      transparent: true,
      opacity: 0.65,
    });
    const wireframe = new T.LineSegments(geometry, material);
    wireframe.userData = { _wireframe: true, _instancedWireframe: true, _surfaceWireframe: true, type, basePositions };
    return wireframe;
  }

  function createInstancedLineGroupObjects(records, type, { radius = 0.15 } = {}) {
    const items = Array.isArray(records) ? records : [];
    if (!items.length) return null;
    const visualRadius = Math.max(0.001, safeNumber(radius, 0.15));
    const geometry = new T.CylinderGeometry(visualRadius, visualRadius, 1, 8, 1, false);
    const material = new T.MeshPhongMaterial({
      color: 0xffffff,
      transparent: true,
      opacity: 0.85,
    });
    const mesh = new T.InstancedMesh(geometry, material, items.length);
    mesh.instanceMatrix.setUsage(T.DynamicDrawUsage);
    mesh.castShadow = true;
    mesh.receiveShadow = true;
    mesh.userData = { _instancedGroup: true, type, visualRadius };
    items.forEach((record, index) => {
      record.instanceId = index;
      record.groupType = type;
      record.mesh = mesh;
      record.visualRadius = safeNumber(record.visualRadius, visualRadius);
      mesh.setMatrixAt(index, record.baseMatrix);
      mesh.setColorAt(index, new T.Color(record.baseColorHex));
    });
    mesh.userData.instanceRecords = items;
    mesh.instanceMatrix.needsUpdate = true;
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
    mesh.computeBoundingBox?.();
    mesh.computeBoundingSphere?.();
    return {
      type,
      mesh,
      wireframe: createInstancedWireframe(items, type),
      records: items,
      defaultOpacity: 0.85,
      visualRadius,
    };
  }

  function createInstancedSurfaceGroupObjects(records, type) {
    const items = Array.isArray(records) ? records : [];
    if (!items.length) return null;
    const defaultOpacity = type === 'slab' ? 0.25 : 0.45;
    const geometry = new T.PlaneGeometry(1, 1, 1, 1);
    const material = new T.MeshPhongMaterial({
      color: 0xffffff,
      transparent: true,
      opacity: defaultOpacity,
      side: T.DoubleSide,
    });
    const mesh = new T.InstancedMesh(geometry, material, items.length);
    mesh.instanceMatrix.setUsage(T.DynamicDrawUsage);
    mesh.userData = { _instancedGroup: true, _instancedSurfaceGroup: true, geometryKind: 'surface', type };
    items.forEach((record, index) => {
      record.instanceId = index;
      record.groupType = type;
      record.mesh = mesh;
      mesh.setMatrixAt(index, record.baseMatrix);
      mesh.setColorAt(index, new T.Color(record.baseColorHex));
    });
    mesh.userData.instanceRecords = items;
    mesh.instanceMatrix.needsUpdate = true;
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
    mesh.computeBoundingBox?.();
    mesh.computeBoundingSphere?.();
    return {
      type,
      geometryKind: 'surface',
      mesh,
      wireframe: createInstancedSurfaceWireframe(items, type),
      records: items,
      defaultOpacity,
    };
  }

  function createLineElementRenderObjects({
    element,
    nodes,
    type,
    baseColorHex,
    radius,
    deformScale = 100,
  } = {}) {
    const nodeItems = Array.isArray(nodes) ? nodes : [];
    if (nodeItems.length !== 2) return null;
    const normalizedType = normalizeElementType(type);
    const baseColor = new T.Color(baseColorHex);
    const points = nodeItems.map(node => nodeToViewerVector(T, node));
    const lineGeometry = new T.BufferGeometry().setFromPoints(points);
    lineGeometry.setAttribute('color', new T.BufferAttribute(new Float32Array([
      baseColor.r, baseColor.g, baseColor.b,
      baseColor.r, baseColor.g, baseColor.b,
    ]), 3));
    const curve = new T.LineCurve3(points[0], points[1]);
    const tubeGeometry = new T.TubeGeometry(curve, 1, radius, 8, false);
    const material = new T.MeshPhongMaterial({
      color: baseColor.clone(),
      transparent: true,
      opacity: 0.85,
      vertexColors: false,
    });
    const mesh = new T.Mesh(tubeGeometry, material);
    const meshData = {
      ...element,
      nodeData: nodeItems,
      baseColor: baseColor.getHex(),
      contourGeometryKind: 'line_tube',
      visualRadius: Math.max(0.001, safeNumber(radius, 0.15)),
    };
    mesh.userData = meshData;
    const lineMaterial = new T.LineBasicMaterial({
      color: baseColor.clone(),
      linewidth: normalizedType === 'column' ? 2 : 1,
      vertexColors: true,
    });
    const wireframe = new T.Line(lineGeometry, lineMaterial);
    wireframe.userData = { _wireframe: true, elemId: element?.id, type: normalizedType };
    const deformedPoints = nodeItems.map(node => nodeToDeformedViewerVector(T, node, deformScale));
    const deformedCurve = new T.LineCurve3(deformedPoints[0], deformedPoints[1]);
    const deformedTubeGeometry = new T.TubeGeometry(deformedCurve, 1, radius, 8, false);
    const deformedMaterial = new T.MeshPhongMaterial({ color: 0x9fb3c8, transparent: true, opacity: 0.34 });
    const deformedMesh = new T.Mesh(deformedTubeGeometry, deformedMaterial);
    deformedMesh.userData = { ...element, _deformed: true };
    return {
      kind: 'line',
      mesh,
      meshData,
      wireframe,
      deformedMesh,
      pickPoints: points,
    };
  }

  function createSurfaceElementRenderObjects({
    element,
    nodes,
    type,
    baseColorHex,
    vertices,
    geometry,
    isInstancedSurface = false,
    surfaceLodLabel = 'full',
    surfaceContourSubdivisions = null,
  } = {}) {
    const nodeItems = Array.isArray(nodes) ? nodes : [];
    const points = Array.isArray(vertices) ? vertices : nodeItems.map(node => nodeToViewerVector(T, node));
    if (nodeItems.length < 4 || points.length < 4) return null;
    const normalizedType = normalizeElementType(type);
    const baseColor = new T.Color(baseColorHex);
    const surfaceGeometry = geometry instanceof T.BufferGeometry ? geometry : new T.BufferGeometry();
    const vertexCount = surfaceGeometry.getAttribute('position')?.count || 0;
    if (vertexCount > 0) {
      surfaceGeometry.setAttribute('color', new T.BufferAttribute(buildConstantColorAttribute(vertexCount, baseColor), 3));
    }
    const opacity = normalizedType === 'slab' ? 0.25 : 0.45;
    const material = new T.MeshPhongMaterial({
      color: baseColor.clone(),
      transparent: true,
      opacity,
      side: T.DoubleSide,
      vertexColors: false,
    });
    const mesh = new T.Mesh(surfaceGeometry, material);
    const meshData = {
      ...element,
      nodeData: nodeItems,
      baseColor: baseColor.getHex(),
      contourGeometryKind: 'surface',
      _surfaceDirectFallback: isInstancedSurface,
      surfaceLodLabel,
      surfaceContourSubdivisions,
      baseMaterial: material,
    };
    mesh.userData = meshData;
    let edgeLine = null;
    if (!isInstancedSurface) {
      const edgeGeometry = new T.BufferGeometry().setFromPoints([...points, points[0]]);
      const edgeMaterial = new T.LineBasicMaterial({ color: baseColor.clone(), opacity: 0.5, transparent: true });
      edgeLine = new T.Line(edgeGeometry, edgeMaterial);
      edgeLine.userData = { _wireframe: true, elemId: element?.id, type: normalizedType };
    }
    return {
      kind: 'surface',
      mesh,
      meshData,
      edgeLine,
      pickPoints: points,
    };
  }

  function createSolidElementRenderObjects({
    element,
    nodes,
    type,
    baseColorHex,
    size = 0.3,
    deformScale = 100,
  } = {}) {
    const nodeItems = Array.isArray(nodes) ? nodes : [];
    if (!nodeItems.length) return null;
    const normalizedType = normalizeElementType(type);
    const baseColor = new T.Color(baseColorHex);
    const points = nodeItems.map(node => nodeToViewerVector(T, node));
    const box = new T.Box3().setFromPoints(points);
    const center = box.getCenter(new T.Vector3());
    const dims = box.getSize(new T.Vector3());
    const minExtent = Math.max(0.05, safeNumber(size, 0.3) * 2);
    const sx = Math.max(dims.x, minExtent);
    const sy = Math.max(dims.y, minExtent);
    const sz = Math.max(dims.z, minExtent);
    const geometry = new T.BoxGeometry(sx, sy, sz);
    geometry.translate(center.x, center.y, center.z);
    const material = new T.MeshPhongMaterial({
      color: baseColor.clone(),
      transparent: true,
      opacity: 0.7,
      side: T.DoubleSide,
      vertexColors: false,
    });
    const mesh = new T.Mesh(geometry, material);
    const meshData = {
      ...element,
      nodeData: nodeItems,
      baseColor: baseColor.getHex(),
      contourGeometryKind: 'solid',
      baseMaterial: material,
    };
    mesh.userData = meshData;
    const wireframe = new T.LineSegments(
      new T.EdgesGeometry(geometry),
      new T.LineBasicMaterial({ color: baseColor.clone(), transparent: true, opacity: 0.6 }),
    );
    wireframe.userData = { _wireframe: true, elemId: element?.id, type: normalizedType };
    const deformedPoints = nodeItems.map(node => nodeToDeformedViewerVector(T, node, deformScale));
    const deformedBox = new T.Box3().setFromPoints(deformedPoints);
    const deformedCenter = deformedBox.getCenter(new T.Vector3());
    const deformedGeometry = new T.BoxGeometry(sx, sy, sz);
    deformedGeometry.translate(deformedCenter.x, deformedCenter.y, deformedCenter.z);
    const deformedMesh = new T.Mesh(
      deformedGeometry,
      new T.MeshPhongMaterial({ color: 0x9fb3c8, transparent: true, opacity: 0.3 }),
    );
    deformedMesh.userData = { ...element, _deformed: true };
    return {
      kind: 'solid',
      mesh,
      meshData,
      wireframe,
      deformedMesh,
      pickPoints: points,
    };
  }

  const VISUAL_RADIUS_BY_TYPE = {
    column: 0.35, beam: 0.20, brace: 0.18, truss: 0.12, cable: 0.06, rebar: 0.015,
    girder: 0.28, purlin: 0.08, joist: 0.09, tie: 0.07, strut: 0.14,
    wall: 0.20, slab: 0.15, shell: 0.16, roof: 0.14, diaphragm: 0.14,
    footing: 0.45, pile: 0.18, mat: 0.40, panel_zone: 0.30, joint: 0.20,
    isolator: 0.16, damper: 0.12, shear_wall: 0.22, core_wall: 0.22,
  };

  function getVisualRadius(type) {
    const normalized = normalizeElementType(type);
    return safeNumber(VISUAL_RADIUS_BY_TYPE[normalized], 0.15);
  }

  function getMaterialProperties(type) {
    const normalized = normalizeElementType(type);
    if (normalized === 'cable' || normalized === 'rebar' || normalized === 'prestressing_tendon') {
      return { roughness: 0.35, metalness: 0.85, opacity: 0.95 };
    }
    if (normalized === 'slab' || normalized === 'wall' || normalized === 'shell' || normalized === 'roof') {
      return { roughness: 0.9, metalness: 0.05, opacity: normalized === 'slab' ? 0.25 : 0.45 };
    }
    if (normalized === 'footing' || normalized === 'pile' || normalized === 'mat') {
      return { roughness: 0.95, metalness: 0.0, opacity: 0.7 };
    }
    return { roughness: 0.55, metalness: 0.45, opacity: 0.85 };
  }

  function createCableElementRenderObjects({
    element,
    nodes,
    baseColorHex,
    radius = 0.06,
    sagRatio = 0.05,
  } = {}) {
    const nodeItems = Array.isArray(nodes) ? nodes : [];
    if (nodeItems.length < 2) return null;
    const baseColor = new T.Color(baseColorHex);
    const start = nodeToViewerVector(T, nodeItems[0]);
    const end = nodeToViewerVector(T, nodeItems[nodeItems.length - 1]);
    const span = start.distanceTo(end);
    const mid = start.clone().add(end).multiplyScalar(0.5);
    mid.y -= span * Math.max(0, safeNumber(sagRatio, 0.05));
    const curve = new T.CatmullRomCurve3([start, mid, end]);
    const tubeGeometry = new T.TubeGeometry(curve, 16, Math.max(0.01, safeNumber(radius, 0.06)), 6, false);
    const props = getMaterialProperties('cable');
    const material = new T.MeshPhongMaterial({ color: baseColor.clone(), transparent: true, opacity: props.opacity });
    const mesh = new T.Mesh(tubeGeometry, material);
    const meshData = {
      ...element,
      nodeData: nodeItems,
      baseColor: baseColor.getHex(),
      contourGeometryKind: 'cable',
      visualRadius: Math.max(0.01, safeNumber(radius, 0.06)),
    };
    mesh.userData = meshData;
    const pickPoints = curve.getPoints(16);
    const wireframe = new T.Line(
      new T.BufferGeometry().setFromPoints(pickPoints),
      new T.LineBasicMaterial({ color: baseColor.clone(), transparent: true, opacity: 0.6 }),
    );
    wireframe.userData = { _wireframe: true, elemId: element?.id, type: 'cable' };
    return { kind: 'cable', mesh, meshData, wireframe, pickPoints: [start, end] };
  }

  function createRebarElementRenderObjects({
    element,
    nodes,
    baseColorHex,
    radius = 0.012,
    deformScale = 100,
  } = {}) {
    const nodeItems = Array.isArray(nodes) ? nodes : [];
    if (nodeItems.length < 2) return null;
    const baseColor = new T.Color(baseColorHex);
    const points = nodeItems.map(node => nodeToViewerVector(T, node));
    const r = Math.max(0.004, safeNumber(radius, 0.012));
    const curve = new T.CatmullRomCurve3(points);
    const tubeGeometry = new T.TubeGeometry(curve, Math.max(2, points.length * 4), r, 6, false);
    const props = getMaterialProperties('rebar');
    const material = new T.MeshPhongMaterial({ color: baseColor.clone(), transparent: true, opacity: props.opacity });
    const mesh = new T.Mesh(tubeGeometry, material);
    const meshData = {
      ...element,
      nodeData: nodeItems,
      baseColor: baseColor.getHex(),
      contourGeometryKind: 'rebar',
      visualRadius: r,
    };
    mesh.userData = meshData;
    const deformedPoints = nodeItems.map(node => nodeToDeformedViewerVector(T, node, deformScale));
    const deformedCurve = new T.CatmullRomCurve3(deformedPoints);
    const deformedGeometry = new T.TubeGeometry(deformedCurve, Math.max(2, points.length * 4), r, 6, false);
    const deformedMesh = new T.Mesh(
      deformedGeometry,
      new T.MeshPhongMaterial({ color: 0x9fb3c8, transparent: true, opacity: 0.3 }),
    );
    deformedMesh.userData = { ...element, _deformed: true };
    return { kind: 'rebar', mesh, meshData, deformedMesh, pickPoints: points };
  }

  function createTerrainMesh({
    element,
    nodes,
    baseColorHex,
  } = {}) {
    const nodeItems = Array.isArray(nodes) ? nodes : [];
    if (nodeItems.length < 3) return null;
    const baseColor = new T.Color(baseColorHex);
    const points = nodeItems.map(node => nodeToViewerVector(T, node));
    const geometry = new T.BufferGeometry();
    const positions = [];
    points.forEach(point => positions.push(point.x, point.y, point.z));
    geometry.setAttribute('position', new T.BufferAttribute(new Float32Array(positions), 3));
    const material = new T.MeshStandardMaterial({
      color: baseColor.clone(),
      transparent: true,
      opacity: 0.85,
      roughness: 0.95,
      metalness: 0.0,
      side: T.DoubleSide,
    });
    const mesh = new T.Mesh(geometry, material);
    const meshData = { ...element, nodeData: nodeItems, contourGeometryKind: 'terrain' };
    mesh.userData = meshData;
    return { kind: 'terrain', mesh, meshData, pickPoints: points };
  }

  return Object.freeze({
    createInstancedLineGroupObjects,
    createInstancedSurfaceGroupObjects,
    createInstancedSurfaceWireframe,
    createInstancedWireframe,
    createLineElementRenderObjects,
    createSurfaceElementRenderObjects,
    createSolidElementRenderObjects,
    createCableElementRenderObjects,
    createRebarElementRenderObjects,
    createTerrainMesh,
    getMaterialProperties,
    getVisualRadius,
  });
}
