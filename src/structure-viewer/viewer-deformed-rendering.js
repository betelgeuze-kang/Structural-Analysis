function safeNumber(value, fallback = 0) {
  if (value === null || value === undefined || value === '') return fallback;
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function normalizeSelectionValue(value) {
  return String(value ?? '').trim();
}

function normalizeElementType(value) {
  return String(value || 'beam').trim().toLowerCase() || 'beam';
}

function nodeToDeformedViewerVector(THREE, node, factor) {
  return new THREE.Vector3(
    safeNumber(node?.x, 0) + safeNumber(node?.dx, 0) * factor,
    safeNumber(node?.z, 0) + safeNumber(node?.dz, 0) * factor,
    safeNumber(node?.y, 0) + safeNumber(node?.dy, 0) * factor,
  );
}

function indexFromMap(primaryMap, primaryKey, fallbackMap, fallbackKey) {
  if (primaryMap instanceof Map && primaryKey && primaryMap.has(primaryKey)) return primaryMap.get(primaryKey);
  if (fallbackMap instanceof Map && fallbackKey && fallbackMap.has(fallbackKey)) return fallbackMap.get(fallbackKey);
  return null;
}

function ensureThree(THREE) {
  if (!THREE?.Vector3 || !THREE?.BufferGeometry || !THREE?.Mesh || !THREE?.Line) {
    throw new TypeError('A compatible THREE namespace is required');
  }
  return THREE;
}

export function createViewerDeformedRenderingToolkit(THREE, config = {}) {
  const T = ensureThree(THREE);
  const meshTriangleBvhThreshold = Math.max(1, Math.round(safeNumber(config.meshTriangleBvhThreshold, 2048)));
  const deformedGhostColor = safeNumber(config.deformedGhostColor, 0x9fb3c8);
  const deformedGhostOpacity = Math.max(0, Math.min(1, safeNumber(config.deformedGhostOpacity, 0.32)));
  const deformedWireOpacity = Math.max(0, Math.min(1, safeNumber(config.deformedWireOpacity, 0.46)));

  function getDeformedLineRadius(type) {
    const normalizedType = normalizeElementType(type);
    return normalizedType === 'column'
      ? 0.3
      : (normalizedType === 'wall' || normalizedType === 'slab' ? 0.12 : 0.15);
  }

  function createDeformedLineRenderObjects(element, nodes, { factor = 100, radius = null } = {}) {
    const nodeItems = Array.isArray(nodes) ? nodes : [];
    if (nodeItems.length !== 2) return null;
    const type = normalizeElementType(element?.type);
    const points = nodeItems.map(node => nodeToDeformedViewerVector(T, node, factor));
    const curve = new T.LineCurve3(points[0], points[1]);
    const geometry = new T.TubeGeometry(curve, 1, safeNumber(radius, getDeformedLineRadius(type)), 6, false);
    const material = new T.MeshPhongMaterial({
      color: deformedGhostColor,
      transparent: true,
      opacity: deformedGhostOpacity,
      wireframe: false,
    });
    const mesh = new T.Mesh(geometry, material);
    mesh.userData = { ...element, _deformed: true };
    const lineGeometry = new T.BufferGeometry().setFromPoints(points);
    const line = new T.Line(
      lineGeometry,
      new T.LineBasicMaterial({ color: deformedGhostColor, opacity: deformedWireOpacity, transparent: true }),
    );
    line.userData = { _wireframe: true, _deformedWireframe: true, elemId: element?.id, type };
    return { mesh, line, points };
  }

  function buildDeformedPickAcceleration(
    deformedMeshes,
    pickSpatialIndex,
    {
      appendPickMeshTrianglesFromGeometry,
      buildLocalGeometryTriangleEntries,
      buildPickMeshTriangleBvh,
    } = {},
  ) {
    const triangleEntries = [];
    const localCatalogs = [];
    const localCatalogByRecordIndex = new Map();
    const records = Array.isArray(pickSpatialIndex?.records) ? pickSpatialIndex.records : [];
    (Array.isArray(deformedMeshes) ? deformedMeshes : []).forEach(mesh => {
      if (!(mesh?.isMesh) && !mesh?.isInstancedMesh) return;
      const elementId = normalizeSelectionValue(mesh?.userData?.id || mesh?.userData?.elementId);
      const memberId = normalizeSelectionValue(mesh?.userData?.member_id || mesh?.userData?.memberId);
      const recordIndex = indexFromMap(
        pickSpatialIndex?.recordIndexByElementId,
        elementId,
        pickSpatialIndex?.recordIndexByMemberId,
        memberId,
      );
      if (!Number.isInteger(recordIndex)) return;
      mesh.updateMatrixWorld?.(true);
      appendPickMeshTrianglesFromGeometry?.(mesh.geometry, mesh.matrixWorld.clone(), recordIndex, triangleEntries);
      if (mesh.geometry instanceof T.BufferGeometry) {
        const localEntries = typeof buildLocalGeometryTriangleEntries === 'function'
          ? buildLocalGeometryTriangleEntries(mesh.geometry)
          : [];
        if (localEntries.length) {
          const worldMatrix = mesh.matrixWorld.clone();
          const catalog = {
            key: `deformed::${normalizeSelectionValue(elementId || memberId || recordIndex)}`,
            recordIndex,
            triangleEntries: localEntries,
            triangleBvh: localEntries.length >= meshTriangleBvhThreshold && typeof buildPickMeshTriangleBvh === 'function'
              ? buildPickMeshTriangleBvh(localEntries)
              : null,
            worldMatrix,
            inverseWorldMatrix: worldMatrix.clone().invert(),
            meshUuid: String(mesh.uuid || ''),
            instanceId: null,
          };
          localCatalogs.push(catalog);
          localCatalogByRecordIndex.set(recordIndex, catalog);
        }
      }
    });
    return {
      triangleEntries,
      localCatalogs,
      localCatalogByRecordIndex,
      triangleBvh: triangleEntries.length >= meshTriangleBvhThreshold && typeof buildPickMeshTriangleBvh === 'function'
        ? buildPickMeshTriangleBvh(triangleEntries)
        : null,
      records,
    };
  }

  function applyDeformedPickAcceleration(pickSpatialIndex, largeModelBuildProfile, acceleration) {
    if (!pickSpatialIndex || !acceleration) return;
    const triangleEntries = Array.isArray(acceleration.triangleEntries) ? acceleration.triangleEntries : [];
    const localCatalogs = Array.isArray(acceleration.localCatalogs) ? acceleration.localCatalogs : [];
    const localCatalogByRecordIndex = acceleration.localCatalogByRecordIndex instanceof Map
      ? acceleration.localCatalogByRecordIndex
      : new Map();
    pickSpatialIndex.deformedMeshTriangleEntries = triangleEntries;
    pickSpatialIndex.deformedMeshLocalTriangleCatalogs = localCatalogs;
    pickSpatialIndex.deformedMeshTriangleBvh = acceleration.triangleBvh || null;
    const records = Array.isArray(pickSpatialIndex.records) ? pickSpatialIndex.records : [];
    records.forEach((record, recordIndex) => {
      if (record && typeof record === 'object') {
        record.deformedPickMeshLocalCatalog = localCatalogByRecordIndex.get(recordIndex) || null;
      }
    });
    if (largeModelBuildProfile) {
      largeModelBuildProfile.pickSpatialDeformedMeshTriangleCount = triangleEntries.length;
      largeModelBuildProfile.pickSpatialDeformedMeshTriangleBvhEnabled = Boolean(pickSpatialIndex.deformedMeshTriangleBvh);
      largeModelBuildProfile.pickSpatialDeformedMeshLocalCatalogCount = localCatalogs.length;
    }
  }

  function clearDeformedPickAcceleration(pickSpatialIndex, largeModelBuildProfile) {
    if (!pickSpatialIndex) return;
    pickSpatialIndex.deformedMeshTriangleEntries = [];
    pickSpatialIndex.deformedMeshLocalTriangleCatalogs = [];
    pickSpatialIndex.deformedMeshTriangleBvh = null;
    if (Array.isArray(pickSpatialIndex.records)) {
      pickSpatialIndex.records.forEach(record => {
        if (record && typeof record === 'object') record.deformedPickMeshLocalCatalog = null;
      });
    }
    if (largeModelBuildProfile) {
      largeModelBuildProfile.pickSpatialDeformedMeshTriangleCount = 0;
      largeModelBuildProfile.pickSpatialDeformedMeshTriangleBvhEnabled = false;
      largeModelBuildProfile.pickSpatialDeformedMeshLocalCatalogCount = 0;
    }
  }

  return Object.freeze({
    applyDeformedPickAcceleration,
    buildDeformedPickAcceleration,
    clearDeformedPickAcceleration,
    createDeformedLineRenderObjects,
    getDeformedLineRadius,
  });
}
