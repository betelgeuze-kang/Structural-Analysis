function safeNumber(value, fallback = 0) {
  if (value === null || value === undefined || value === '') return fallback;
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function ensureThree(THREE) {
  if (!THREE?.BufferGeometry || !THREE?.Sphere || !THREE?.Vector3 || !THREE?.Quaternion || !THREE?.Ray) {
    throw new TypeError('A compatible THREE namespace is required');
  }
  return THREE;
}

function asFunction(value, fallback) {
  return typeof value === 'function' ? value : fallback;
}

export function createViewerPickBroadphaseToolkit(THREE, config = {}) {
  const T = ensureThree(THREE);
  const accelerationThreshold = Math.max(1, Math.round(safeNumber(config.accelerationThreshold, 900)));
  const lineScreenTolerancePx = Math.max(0, safeNumber(config.lineScreenTolerancePx, 10));
  const getBoundingDiagonal = asFunction(config.getBoundingDiagonal, () => 0);
  const getSurfaceRenderLodProfile = asFunction(config.getSurfaceRenderLodProfile, () => null);
  const isElementVisible = asFunction(config.isElementVisible, () => true);

  function shouldPreferInstancedSurfacePicking() {
    return Boolean(getSurfaceRenderLodProfile()?.pickFromInstancedSurfaces);
  }

  function hasVisibleInstancedRecords(mesh) {
    if (!(mesh?.userData?._instancedGroup)) return false;
    if (typeof mesh.userData.hasVisibleInstances === 'boolean') return mesh.userData.hasVisibleInstances;
    const records = Array.isArray(mesh.userData.instanceRecords) ? mesh.userData.instanceRecords : [];
    return records.some(record => isElementVisible(record?.data));
  }

  function shouldIncludePickTargetMesh(child, preferInstancedSurfacePicking = shouldPreferInstancedSurfacePicking()) {
    if (!(child?.isMesh) || child.userData?._wireframe) return false;
    if (child.userData?._instancedSurfaceGroup) {
      return preferInstancedSurfacePicking ? hasVisibleInstancedRecords(child) : child.visible !== false;
    }
    if (child.userData?._instancedGroup) return child.visible !== false;
    if (child.visible === false) return false;
    if (preferInstancedSurfacePicking && child.userData?._surfaceDirectFallback) return false;
    return true;
  }

  function buildPickAccelerationRecord(mesh) {
    const geometry = mesh?.geometry;
    if (!(geometry instanceof T.BufferGeometry)) return null;
    if (!geometry.boundingSphere) geometry.computeBoundingSphere();
    const sphere = geometry.boundingSphere;
    if (!(sphere instanceof T.Sphere)) return null;
    const center = sphere.center.clone();
    mesh.updateMatrixWorld?.(true);
    center.applyMatrix4(mesh.matrixWorld);
    const scaleVector = new T.Vector3();
    mesh.matrixWorld.decompose(new T.Vector3(), new T.Quaternion(), scaleVector);
    const maxScale = Math.max(
      Math.abs(scaleVector.x) || 1,
      Math.abs(scaleVector.y) || 1,
      Math.abs(scaleVector.z) || 1,
      1,
    );
    return {
      mesh,
      center,
      radius: Math.max(safeNumber(sphere.radius, 1) * maxScale, 0.25),
      isInstanced: Boolean(mesh.userData?._instancedGroup || mesh.userData?._instancedSurfaceGroup),
      isSurface: Boolean(mesh.userData?._surfaceDirectFallback || mesh.userData?._instancedSurfaceGroup),
    };
  }

  function buildPickTargetMeshCache(modelGroup) {
    const children = Array.isArray(modelGroup?.children) ? modelGroup.children : [];
    if (!children.length) return { pickTargetMeshes: [], pickAccelerationRecords: [] };
    const preferInstancedSurfacePicking = shouldPreferInstancedSurfacePicking();
    const pickTargetMeshes = children.filter(child => (
      shouldIncludePickTargetMesh(child, preferInstancedSurfacePicking)
    ));
    const pickAccelerationRecords = pickTargetMeshes
      .map(mesh => buildPickAccelerationRecord(mesh))
      .filter(Boolean);
    return { pickTargetMeshes, pickAccelerationRecords };
  }

  function getPickableMeshesFromCache(ray = null, cache = {}) {
    const pickTargetMeshes = Array.isArray(cache.pickTargetMeshes) ? cache.pickTargetMeshes : [];
    const pickAccelerationRecords = Array.isArray(cache.pickAccelerationRecords) ? cache.pickAccelerationRecords : [];
    if (!(ray instanceof T.Ray) || pickAccelerationRecords.length < accelerationThreshold) return pickTargetMeshes;
    const tolerance = Math.max(
      0.5,
      safeNumber(getBoundingDiagonal(), 0) * 0.0025,
      lineScreenTolerancePx * 0.05,
    );
    const candidates = pickAccelerationRecords
      .filter(record => {
        if (record.mesh?.visible === false) return false;
        const expandedRadius = record.radius + tolerance + (record.isSurface ? 1.2 : 0);
        return ray.distanceSqToPoint(record.center) <= expandedRadius * expandedRadius;
      })
      .sort((left, right) => {
        const leftDistance = ray.distanceSqToPoint(left.center);
        const rightDistance = ray.distanceSqToPoint(right.center);
        return leftDistance - rightDistance;
      })
      .slice(0, 1600)
      .map(record => record.mesh);
    return candidates.length ? candidates : pickTargetMeshes;
  }

  return Object.freeze({
    buildPickAccelerationRecord,
    buildPickTargetMeshCache,
    getPickableMeshesFromCache,
    hasVisibleInstancedRecords,
    shouldPreferInstancedSurfacePicking,
  });
}
