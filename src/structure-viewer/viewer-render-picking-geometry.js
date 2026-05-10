function safeNumber(value, fallback = 0) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function normalizeSelectionValue(value) {
  return String(value ?? '').trim();
}

function createBoundsEntry(THREE, recordIndex, triangle) {
  const [a, b, c] = triangle;
  return {
    recordIndex,
    triangle,
    center: a.clone().add(b).add(c).multiplyScalar(1 / 3),
    boundsMin: new THREE.Vector3(
      Math.min(a.x, b.x, c.x),
      Math.min(a.y, b.y, c.y),
      Math.min(a.z, b.z, c.z),
    ),
    boundsMax: new THREE.Vector3(
      Math.max(a.x, b.x, c.x),
      Math.max(a.y, b.y, c.y),
      Math.max(a.z, b.z, c.z),
    ),
  };
}

function ensureThree(THREE) {
  if (!THREE?.Vector3 || !THREE?.BufferGeometry || !THREE?.Matrix4 || !THREE?.Ray) {
    throw new TypeError('A compatible THREE namespace is required');
  }
  return THREE;
}

export function createViewerRenderPickingGeometryToolkit(THREE, config = {}) {
  const T = ensureThree(THREE);
  const contourSurfaceTessellationMin = Math.max(1, Math.round(safeNumber(config.contourSurfaceTessellationMin, 10)));
  const contourSurfaceTessellationMax = Math.max(
    contourSurfaceTessellationMin,
    Math.round(safeNumber(config.contourSurfaceTessellationMax, 20)),
  );
  const instancedSurfaceElementThreshold = Math.max(1, Math.round(safeNumber(config.instancedSurfaceElementThreshold, 120)));
  const surfaceLodMediumElementThreshold = Math.max(1, Math.round(safeNumber(config.surfaceLodMediumElementThreshold, 480)));
  const surfaceLodCoarseElementThreshold = Math.max(
    surfaceLodMediumElementThreshold,
    Math.round(safeNumber(config.surfaceLodCoarseElementThreshold, 1200)),
  );
  const surfaceLodMediumDirectSubdivisions = Math.max(1, Math.round(safeNumber(config.surfaceLodMediumDirectSubdivisions, 12)));
  const surfaceLodCoarseDirectSubdivisions = Math.max(1, Math.round(safeNumber(config.surfaceLodCoarseDirectSubdivisions, 8)));
  const surfaceLodMediumInstancedSubdivisions = Math.max(1, Math.round(safeNumber(config.surfaceLodMediumInstancedSubdivisions, 6)));
  const surfaceLodCoarseInstancedSubdivisions = Math.max(1, Math.round(safeNumber(config.surfaceLodCoarseInstancedSubdivisions, 3)));
  const pickOverflowBvhLeafSize = Math.max(1, Math.round(safeNumber(config.pickOverflowBvhLeafSize, 12)));

  function computeLineElementMatrix(start, end) {
    const midpoint = start.clone().add(end).multiplyScalar(0.5);
    const direction = end.clone().sub(start);
    const length = Math.max(direction.length(), 1e-6);
    const quaternion = new T.Quaternion().setFromUnitVectors(
      new T.Vector3(0, 1, 0),
      direction.normalize(),
    );
    return new T.Matrix4().compose(
      midpoint,
      quaternion,
      new T.Vector3(1, length, 1),
    );
  }

  function computeSurfaceElementMatrix(points) {
    if (!Array.isArray(points) || points.length < 4) return null;
    const center = points
      .reduce((sum, point) => sum.add(point.clone()), new T.Vector3())
      .multiplyScalar(1 / points.length);
    const xAxis = points[1].clone().sub(points[0]).add(points[2].clone().sub(points[3])).multiplyScalar(0.5);
    const yAxis = points[3].clone().sub(points[0]).add(points[2].clone().sub(points[1])).multiplyScalar(0.5);
    if (xAxis.lengthSq() < 1e-10 || yAxis.lengthSq() < 1e-10) return null;
    const normal = new T.Vector3().crossVectors(xAxis, yAxis);
    if (normal.lengthSq() < 1e-10) return null;
    normal.normalize().multiplyScalar(Math.max(Math.min(xAxis.length(), yAxis.length()) * 0.001, 1e-4));
    const matrix = new T.Matrix4().makeBasis(xAxis, yAxis, normal);
    matrix.setPosition(center);
    return matrix;
  }

  function sampleBilinearPoint(points, u, v) {
    if (!Array.isArray(points) || points.length < 4) return new T.Vector3();
    const p00 = points[0].clone().multiplyScalar((1 - u) * (1 - v));
    const p10 = points[1].clone().multiplyScalar(u * (1 - v));
    const p11 = points[2].clone().multiplyScalar(u * v);
    const p01 = points[3].clone().multiplyScalar((1 - u) * v);
    return p00.add(p10).add(p11).add(p01);
  }

  function sampleBilinearColor(c00, c10, c11, c01, u, v) {
    const top = c00.clone().lerp(c10, u);
    const bottom = c01.clone().lerp(c11, u);
    return top.lerp(bottom, v);
  }

  function computeAdaptiveContourSubdivisions(points) {
    if (!Array.isArray(points) || points.length < 4) return contourSurfaceTessellationMin;
    const edges = [
      points[1].clone().sub(points[0]).length(),
      points[2].clone().sub(points[1]).length(),
      points[3].clone().sub(points[2]).length(),
      points[0].clone().sub(points[3]).length(),
    ].filter(length => Number.isFinite(length) && length > 0);
    if (!edges.length) return contourSurfaceTessellationMin;
    const longest = Math.max(...edges);
    const shortest = Math.max(Math.min(...edges), 1e-6);
    const area = new T.Triangle(points[0], points[1], points[2]).getArea()
      + new T.Triangle(points[0], points[2], points[3]).getArea();
    const aspectBoost = Math.max(1, longest / shortest);
    const densityBoost = Math.max(1, Math.sqrt(Math.max(area, 1e-6)) * 1.8);
    return Math.max(
      contourSurfaceTessellationMin,
      Math.min(contourSurfaceTessellationMax, Math.round(Math.max(aspectBoost * 4, densityBoost))),
    );
  }

  function buildContourSurfaceGeometry(points, subdivisions = contourSurfaceTessellationMin) {
    if (!Array.isArray(points) || points.length < 4) return null;
    const segments = Math.max(1, Math.round(Number(subdivisions) || 1));
    const verticesPerSide = segments + 1;
    const vertexCount = verticesPerSide * verticesPerSide;
    const positions = new Float32Array(vertexCount * 3);
    const uvs = new Float32Array(vertexCount * 2);
    const indices = [];
    let vertexIndex = 0;
    for (let row = 0; row <= segments; row += 1) {
      const v = row / segments;
      for (let column = 0; column <= segments; column += 1) {
        const u = column / segments;
        const point = sampleBilinearPoint(points, u, v);
        positions[vertexIndex * 3] = point.x;
        positions[vertexIndex * 3 + 1] = point.y;
        positions[vertexIndex * 3 + 2] = point.z;
        uvs[vertexIndex * 2] = u;
        uvs[vertexIndex * 2 + 1] = v;
        vertexIndex += 1;
      }
    }
    for (let row = 0; row < segments; row += 1) {
      for (let column = 0; column < segments; column += 1) {
        const a = row * verticesPerSide + column;
        const b = a + 1;
        const d = (row + 1) * verticesPerSide + column;
        const c = d + 1;
        indices.push(a, b, c, a, c, d);
      }
    }
    const geometry = new T.BufferGeometry();
    geometry.setAttribute('position', new T.BufferAttribute(positions, 3));
    geometry.setAttribute('uv', new T.BufferAttribute(uvs, 2));
    geometry.setIndex(indices);
    geometry.computeVertexNormals();
    return geometry;
  }

  function buildHighResolutionContourSurfaceGeometry(points) {
    return buildContourSurfaceGeometry(points, computeAdaptiveContourSubdivisions(points));
  }

  function buildSurfaceLodProfile(surfaceElementCount, instancedSurfaceCount) {
    const totalSurfaceCount = Math.max(0, safeNumber(surfaceElementCount, 0));
    const totalInstancedCount = Math.max(0, safeNumber(instancedSurfaceCount, 0));
    if (totalSurfaceCount >= surfaceLodCoarseElementThreshold) {
      return {
        label: 'coarse',
        directSurfaceMaxSubdivisions: surfaceLodCoarseDirectSubdivisions,
        instancedSurfaceMaxSubdivisions: surfaceLodCoarseInstancedSubdivisions,
        pickFromInstancedSurfaces: totalInstancedCount >= instancedSurfaceElementThreshold,
      };
    }
    if (totalSurfaceCount >= surfaceLodMediumElementThreshold) {
      return {
        label: 'medium',
        directSurfaceMaxSubdivisions: surfaceLodMediumDirectSubdivisions,
        instancedSurfaceMaxSubdivisions: surfaceLodMediumInstancedSubdivisions,
        pickFromInstancedSurfaces: totalInstancedCount >= instancedSurfaceElementThreshold,
      };
    }
    return {
      label: 'full',
      directSurfaceMaxSubdivisions: contourSurfaceTessellationMax,
      instancedSurfaceMaxSubdivisions: contourSurfaceTessellationMax,
      pickFromInstancedSurfaces: false,
    };
  }

  function computeSurfaceLodSubdivisions(points, lodProfile, { isInstancedSurface = false } = {}) {
    const adaptive = computeAdaptiveContourSubdivisions(points);
    const maxSubdivisions = Math.max(
      1,
      Math.round(
        isInstancedSurface
          ? safeNumber(lodProfile?.instancedSurfaceMaxSubdivisions, contourSurfaceTessellationMax)
          : safeNumber(lodProfile?.directSurfaceMaxSubdivisions, contourSurfaceTessellationMax),
      ),
    );
    const floorSubdivisions = isInstancedSurface && normalizeSelectionValue(lodProfile?.label) !== 'full'
      ? 1
      : Math.min(contourSurfaceTessellationMin, maxSubdivisions);
    return Math.max(floorSubdivisions, Math.min(maxSubdivisions, adaptive));
  }

  function buildLodSurfaceContourGeometry(points, lodProfile, { isInstancedSurface = false } = {}) {
    if (!lodProfile || normalizeSelectionValue(lodProfile.label) === 'full') {
      return buildHighResolutionContourSurfaceGeometry(points);
    }
    return buildContourSurfaceGeometry(
      points,
      computeSurfaceLodSubdivisions(points, lodProfile, { isInstancedSurface }),
    );
  }

  function computePickBoundingSphere(points) {
    if (!Array.isArray(points) || points.length < 2) return null;
    const center = points
      .reduce((sum, point) => sum.add(point.clone()), new T.Vector3())
      .multiplyScalar(1 / points.length);
    const radius = Math.max(
      ...points.map(point => center.distanceTo(point)),
      1e-3,
    );
    return { center, radius };
  }

  function getPickSpatialIndexKey(index, ix, iy, iz) {
    return ix + index.dimX * (iy + index.dimY * iz);
  }

  function clampPickSpatialIndexCoord(rawCoord, maxCount) {
    return Math.max(0, Math.min(maxCount - 1, Math.floor(rawCoord)));
  }

  function getPickSpatialIndexAxisCellSize(index, axis) {
    return Math.max(
      safeNumber(index?.[`cellSize${axis.toUpperCase()}`], 0),
      safeNumber(index?.cellSize, 0),
      1e-3,
    );
  }

  function getPickSpatialIndexCellCoords(index, point) {
    return {
      ix: clampPickSpatialIndexCoord((point.x - index.boundsMin.x) / getPickSpatialIndexAxisCellSize(index, 'x'), index.dimX),
      iy: clampPickSpatialIndexCoord((point.y - index.boundsMin.y) / getPickSpatialIndexAxisCellSize(index, 'y'), index.dimY),
      iz: clampPickSpatialIndexCoord((point.z - index.boundsMin.z) / getPickSpatialIndexAxisCellSize(index, 'z'), index.dimZ),
    };
  }

  function buildPickBoundsBvh(entryIndices, entries, leafSize = pickOverflowBvhLeafSize) {
    const indices = Array.isArray(entryIndices) ? entryIndices.filter(Number.isInteger) : [];
    if (!indices.length) return null;
    const boundsMin = new T.Vector3(Infinity, Infinity, Infinity);
    const boundsMax = new T.Vector3(-Infinity, -Infinity, -Infinity);
    const centerMin = new T.Vector3(Infinity, Infinity, Infinity);
    const centerMax = new T.Vector3(-Infinity, -Infinity, -Infinity);
    const validIndices = [];
    indices.forEach(entryIndex => {
      const entry = Array.isArray(entries) ? entries[entryIndex] : null;
      if (
        !(entry?.boundsMin instanceof T.Vector3)
        || !(entry?.boundsMax instanceof T.Vector3)
        || !(entry?.center instanceof T.Vector3)
      ) return;
      validIndices.push(entryIndex);
      boundsMin.min(entry.boundsMin);
      boundsMax.max(entry.boundsMax);
      centerMin.min(entry.center);
      centerMax.max(entry.center);
    });
    if (!validIndices.length) return null;
    const node = { boundsMin, boundsMax };
    if (validIndices.length <= leafSize) {
      node.entryIndices = validIndices;
      return node;
    }
    const centerExtent = centerMax.clone().sub(centerMin);
    const splitAxis = centerExtent.y > centerExtent.x && centerExtent.y >= centerExtent.z
      ? 'y'
      : centerExtent.z > centerExtent.x && centerExtent.z >= centerExtent.y
        ? 'z'
        : 'x';
    validIndices.sort((left, right) => {
      const leftCenter = entries[left]?.center;
      const rightCenter = entries[right]?.center;
      return safeNumber(leftCenter?.[splitAxis], 0) - safeNumber(rightCenter?.[splitAxis], 0);
    });
    const splitIndex = Math.floor(validIndices.length / 2);
    if (splitIndex <= 0 || splitIndex >= validIndices.length) {
      node.entryIndices = validIndices;
      return node;
    }
    const leftNode = buildPickBoundsBvh(validIndices.slice(0, splitIndex), entries, leafSize);
    const rightNode = buildPickBoundsBvh(validIndices.slice(splitIndex), entries, leafSize);
    if (!leftNode || !rightNode) {
      node.entryIndices = validIndices;
      return node;
    }
    node.left = leftNode;
    node.right = rightNode;
    return node;
  }

  function normalizePickBoundsBvhNode(node) {
    if (!node) return null;
    if (Array.isArray(node.entryIndices)) {
      node.recordIndices = node.entryIndices;
      delete node.entryIndices;
    }
    if (node.left) node.left = normalizePickBoundsBvhNode(node.left);
    if (node.right) node.right = normalizePickBoundsBvhNode(node.right);
    return node;
  }

  function buildPickSpatialIndexOverflowBvh(recordIndices, records, leafSize = pickOverflowBvhLeafSize) {
    const boundsEntries = (Array.isArray(recordIndices) ? recordIndices : []).map(recordIndex => {
      const record = Array.isArray(records) ? records[recordIndex] : null;
      const center = record?.pickCenter;
      if (!(center instanceof T.Vector3)) return null;
      const radius = Math.max(safeNumber(record?.pickRadius, 0), 1e-3);
      return {
        center,
        boundsMin: new T.Vector3(center.x - radius, center.y - radius, center.z - radius),
        boundsMax: new T.Vector3(center.x + radius, center.y + radius, center.z + radius),
      };
    });
    return normalizePickBoundsBvhNode(buildPickBoundsBvh(recordIndices, boundsEntries, leafSize));
  }

  function buildPickSurfaceFacetEntries(records) {
    const facets = [];
    (Array.isArray(records) ? records : []).forEach((record, recordIndex) => {
      if (record?.pickKind !== 'surface' || !Array.isArray(record.points) || record.points.length < 4) return;
      const points = record.points.filter(point => point instanceof T.Vector3);
      if (points.length < 4) return;
      for (let pointIndex = 1; pointIndex < points.length - 1; pointIndex += 1) {
        const a = points[0];
        const b = points[pointIndex];
        const c = points[pointIndex + 1];
        const normal = new T.Vector3().crossVectors(
          b.clone().sub(a),
          c.clone().sub(a),
        );
        if (normal.lengthSq() < 1e-12) continue;
        facets.push(createBoundsEntry(T, recordIndex, [a, b, c]));
      }
    });
    return facets;
  }

  function buildPickSurfaceFacetBvh(surfaceFacetEntries, leafSize = pickOverflowBvhLeafSize) {
    const facetIndices = (Array.isArray(surfaceFacetEntries) ? surfaceFacetEntries : []).map((_, facetIndex) => facetIndex);
    return buildPickBoundsBvh(facetIndices, surfaceFacetEntries, leafSize);
  }

  function appendPickMeshTrianglesFromGeometry(geometry, matrixWorld, recordIndex, triangleEntries) {
    if (!(geometry instanceof T.BufferGeometry) || !(matrixWorld instanceof T.Matrix4) || !Array.isArray(triangleEntries)) return;
    const positionAttr = geometry.getAttribute?.('position');
    if (!(positionAttr instanceof T.BufferAttribute) || positionAttr.itemSize < 3 || positionAttr.count < 3) return;
    const indexArray = geometry.index?.array || null;
    const triangleCount = indexArray ? Math.floor(indexArray.length / 3) : Math.floor(positionAttr.count / 3);
    for (let triangleIndex = 0; triangleIndex < triangleCount; triangleIndex += 1) {
      const aIndex = indexArray ? indexArray[triangleIndex * 3] : triangleIndex * 3;
      const bIndex = indexArray ? indexArray[triangleIndex * 3 + 1] : triangleIndex * 3 + 1;
      const cIndex = indexArray ? indexArray[triangleIndex * 3 + 2] : triangleIndex * 3 + 2;
      const a = new T.Vector3().fromBufferAttribute(positionAttr, aIndex).applyMatrix4(matrixWorld);
      const b = new T.Vector3().fromBufferAttribute(positionAttr, bIndex).applyMatrix4(matrixWorld);
      const c = new T.Vector3().fromBufferAttribute(positionAttr, cIndex).applyMatrix4(matrixWorld);
      const normal = new T.Vector3().crossVectors(
        b.clone().sub(a),
        c.clone().sub(a),
      );
      if (normal.lengthSq() < 1e-12) continue;
      triangleEntries.push(createBoundsEntry(T, recordIndex, [a, b, c]));
    }
  }

  function buildLocalGeometryTriangleEntries(geometry) {
    const triangleEntries = [];
    if (!(geometry instanceof T.BufferGeometry)) return triangleEntries;
    const positionAttr = geometry.getAttribute?.('position');
    if (!(positionAttr instanceof T.BufferAttribute) || positionAttr.itemSize < 3 || positionAttr.count < 3) return triangleEntries;
    const indexArray = geometry.index?.array || null;
    const triangleCount = indexArray ? Math.floor(indexArray.length / 3) : Math.floor(positionAttr.count / 3);
    for (let triangleIndex = 0; triangleIndex < triangleCount; triangleIndex += 1) {
      const aIndex = indexArray ? indexArray[triangleIndex * 3] : triangleIndex * 3;
      const bIndex = indexArray ? indexArray[triangleIndex * 3 + 1] : triangleIndex * 3 + 1;
      const cIndex = indexArray ? indexArray[triangleIndex * 3 + 2] : triangleIndex * 3 + 2;
      const a = new T.Vector3().fromBufferAttribute(positionAttr, aIndex);
      const b = new T.Vector3().fromBufferAttribute(positionAttr, bIndex);
      const c = new T.Vector3().fromBufferAttribute(positionAttr, cIndex);
      const normal = new T.Vector3().crossVectors(
        b.clone().sub(a),
        c.clone().sub(a),
      );
      if (normal.lengthSq() < 1e-12) continue;
      triangleEntries.push(createBoundsEntry(T, triangleEntries.length, [a, b, c]));
    }
    return triangleEntries;
  }

  function resolvePickRecordWorldMatrix(record) {
    const mesh = record?.mesh;
    if (!(mesh?.isMesh) && !(mesh?.isInstancedMesh)) return null;
    mesh.updateMatrixWorld?.(true);
    if (mesh?.isInstancedMesh && Number.isInteger(record?.instanceId)) {
      const instanceMatrix = new T.Matrix4();
      mesh.getMatrixAt(record.instanceId, instanceMatrix);
      return mesh.matrixWorld.clone().multiply(instanceMatrix);
    }
    return mesh.matrixWorld.clone();
  }

  function buildPickMeshTriangleBvh(meshTriangleEntries, leafSize = pickOverflowBvhLeafSize) {
    const triangleIndices = (Array.isArray(meshTriangleEntries) ? meshTriangleEntries : []).map((_, triangleIndex) => triangleIndex);
    return buildPickBoundsBvh(triangleIndices, meshTriangleEntries, leafSize);
  }

  function createLocalRayFromWorldRay(ray, inverseWorldMatrix) {
    if (!(ray instanceof T.Ray) || !(inverseWorldMatrix instanceof T.Matrix4)) return null;
    return new T.Ray(
      ray.origin.clone().applyMatrix4(inverseWorldMatrix),
      ray.direction.clone().transformDirection(inverseWorldMatrix).normalize(),
    );
  }

  function intersectRayBoxDistances(ray, boundsMin, boundsMax) {
    if (!(ray instanceof T.Ray) || !(boundsMin instanceof T.Vector3) || !(boundsMax instanceof T.Vector3)) {
      return null;
    }
    let entry = 0;
    let exit = Infinity;
    for (const axis of ['x', 'y', 'z']) {
      const origin = ray.origin[axis];
      const direction = ray.direction[axis];
      const minValue = boundsMin[axis];
      const maxValue = boundsMax[axis];
      if (Math.abs(direction) < 1e-9) {
        if (origin < minValue || origin > maxValue) return null;
        continue;
      }
      let t0 = (minValue - origin) / direction;
      let t1 = (maxValue - origin) / direction;
      if (t0 > t1) [t0, t1] = [t1, t0];
      entry = Math.max(entry, t0);
      exit = Math.min(exit, t1);
      if (exit < entry) return null;
    }
    return Number.isFinite(exit) ? { entry, exit } : null;
  }

  function intersectPickTriangleBvhClosest(node, entries, ray) {
    if (!node || !Array.isArray(entries) || !(ray instanceof T.Ray)) return null;
    const stack = [node];
    let bestHit = null;
    while (stack.length) {
      const current = stack.pop();
      if (!current) continue;
      const hitRange = intersectRayBoxDistances(ray, current.boundsMin, current.boundsMax);
      if (!hitRange) continue;
      if (bestHit && hitRange.entry > bestHit.distance) continue;
      const leafIndices = Array.isArray(current.entryIndices)
        ? current.entryIndices
        : Array.isArray(current.recordIndices)
          ? current.recordIndices
          : null;
      if (leafIndices) {
        leafIndices.forEach(entryIndex => {
          const entry = entries[entryIndex];
          if (!entry || !Array.isArray(entry.triangle) || entry.triangle.length !== 3) return;
          const hitPoint = ray.intersectTriangle(entry.triangle[0], entry.triangle[1], entry.triangle[2], false, new T.Vector3());
          if (!hitPoint) return;
          const distance = hitPoint.distanceTo(ray.origin);
          if (distance < 0) return;
          if (!bestHit || distance < bestHit.distance) {
            bestHit = { distance, point: hitPoint.clone(), entryIndex };
          }
        });
        continue;
      }
      if (current.left) stack.push(current.left);
      if (current.right) stack.push(current.right);
    }
    return bestHit;
  }

  function intersectLargeModelMeshLocalCatalog(ray, record, { preferDeformed = false } = {}) {
    const catalog = preferDeformed && record?.deformedPickMeshLocalCatalog
      ? record.deformedPickMeshLocalCatalog
      : record?.pickMeshLocalCatalog;
    if (!catalog?.triangleBvh || !(catalog.inverseWorldMatrix instanceof T.Matrix4) || !(catalog.worldMatrix instanceof T.Matrix4)) return null;
    const localRay = createLocalRayFromWorldRay(ray, catalog.inverseWorldMatrix);
    if (!(localRay instanceof T.Ray)) return null;
    const localHit = intersectPickTriangleBvhClosest(catalog.triangleBvh, catalog.triangleEntries, localRay);
    if (!localHit?.point) return null;
    const worldHitPoint = localHit.point.clone().applyMatrix4(catalog.worldMatrix);
    const distanceAlongRay = worldHitPoint.clone().sub(ray.origin).dot(ray.direction);
    if (distanceAlongRay < 0) return null;
    return { distance: distanceAlongRay, mesh: record?.mesh || null, data: record?.data };
  }

  function shouldIncludePickSpatialIndexOverflowRecord(record, ray, tolerance) {
    if (!record || !(ray instanceof T.Ray)) return false;
    const center = record.pickCenter instanceof T.Vector3 ? record.pickCenter : null;
    if (!center) return true;
    const radius = Math.max(safeNumber(record.pickRadius, 0), 1e-3);
    const expandedRadius = Math.max(radius + tolerance + (record.pickKind === 'surface' ? 1.2 : 0), tolerance);
    return ray.distanceSqToPoint(center) <= expandedRadius * expandedRadius;
  }

  function estimatePickRecordEntryDistance(ray, record, tolerance = 0) {
    if (!record || !(ray instanceof T.Ray)) return Infinity;
    const center = record.pickCenter instanceof T.Vector3 ? record.pickCenter : null;
    if (!center) return 0;
    const radius = Math.max(safeNumber(record.pickRadius, 0), 1e-3);
    const expandedRadius = Math.max(radius + tolerance + (record.pickKind === 'surface' ? 1.2 : 0), tolerance);
    const offset = center.clone().sub(ray.origin);
    const projected = offset.dot(ray.direction);
    const perpendicularSq = Math.max(offset.lengthSq() - projected * projected, 0);
    const radiusSq = expandedRadius * expandedRadius;
    if (perpendicularSq > radiusSq) return Infinity;
    const halfChord = Math.sqrt(Math.max(radiusSq - perpendicularSq, 0));
    return Math.max(projected - halfChord, 0);
  }

  function queryPickSpatialIndexOverflowBvh(node, ray, visitRecordIndex) {
    if (!node || !(ray instanceof T.Ray) || typeof visitRecordIndex !== 'function') return;
    const rootHit = intersectRayBoxDistances(ray, node.boundsMin, node.boundsMax);
    if (!rootHit) return;
    const stack = [{ node, entryDistance: Math.max(rootHit.entry, 0) }];
    while (stack.length) {
      const current = stack.pop();
      const currentNode = current.node;
      if (Array.isArray(currentNode?.recordIndices) && currentNode.recordIndices.length) {
        currentNode.recordIndices.forEach(recordIndex => visitRecordIndex(recordIndex, current.entryDistance));
        continue;
      }
      const leftNode = currentNode?.left || null;
      const rightNode = currentNode?.right || null;
      const leftHit = leftNode ? intersectRayBoxDistances(ray, leftNode.boundsMin, leftNode.boundsMax) : null;
      const rightHit = rightNode ? intersectRayBoxDistances(ray, rightNode.boundsMin, rightNode.boundsMax) : null;
      if (leftHit && rightHit) {
        if (leftHit.entry <= rightHit.entry) {
          stack.push({ node: rightNode, entryDistance: Math.max(rightHit.entry, 0) });
          stack.push({ node: leftNode, entryDistance: Math.max(leftHit.entry, 0) });
        } else {
          stack.push({ node: leftNode, entryDistance: Math.max(leftHit.entry, 0) });
          stack.push({ node: rightNode, entryDistance: Math.max(rightHit.entry, 0) });
        }
        continue;
      }
      if (leftHit) stack.push({ node: leftNode, entryDistance: Math.max(leftHit.entry, 0) });
      if (rightHit) stack.push({ node: rightNode, entryDistance: Math.max(rightHit.entry, 0) });
    }
  }

  function queryPickTriangleEntriesBvh(node, entries, ray, visitRecordIndex) {
    if (!node || !(ray instanceof T.Ray) || typeof visitRecordIndex !== 'function') return;
    const rootHit = intersectRayBoxDistances(ray, node.boundsMin, node.boundsMax);
    if (!rootHit) return;
    const stack = [{ node, entryDistance: Math.max(rootHit.entry, 0) }];
    while (stack.length) {
      const current = stack.pop();
      const currentNode = current.node;
      if (Array.isArray(currentNode?.entryIndices) && currentNode.entryIndices.length) {
        currentNode.entryIndices.forEach(entryIndex => {
          const facet = Array.isArray(entries) ? entries[entryIndex] : null;
          if (!facet || !Array.isArray(facet.triangle) || facet.triangle.length !== 3) return;
          const hitPoint = ray.intersectTriangle(
            facet.triangle[0],
            facet.triangle[1],
            facet.triangle[2],
            false,
            new T.Vector3(),
          );
          if (!hitPoint) return;
          const entryDistance = hitPoint.clone().sub(ray.origin).dot(ray.direction);
          if (entryDistance < 0) return;
          visitRecordIndex(facet.recordIndex, entryDistance);
        });
        continue;
      }
      const leftNode = currentNode?.left || null;
      const rightNode = currentNode?.right || null;
      const leftHit = leftNode ? intersectRayBoxDistances(ray, leftNode.boundsMin, leftNode.boundsMax) : null;
      const rightHit = rightNode ? intersectRayBoxDistances(ray, rightNode.boundsMin, rightNode.boundsMax) : null;
      if (leftHit && rightHit) {
        if (leftHit.entry <= rightHit.entry) {
          stack.push({ node: rightNode, entryDistance: Math.max(rightHit.entry, 0) });
          stack.push({ node: leftNode, entryDistance: Math.max(leftHit.entry, 0) });
        } else {
          stack.push({ node: leftNode, entryDistance: Math.max(leftHit.entry, 0) });
          stack.push({ node: rightNode, entryDistance: Math.max(rightHit.entry, 0) });
        }
        continue;
      }
      if (leftHit) stack.push({ node: leftNode, entryDistance: Math.max(leftHit.entry, 0) });
      if (rightHit) stack.push({ node: rightNode, entryDistance: Math.max(rightHit.entry, 0) });
    }
  }

  function queryPickSurfaceFacetBvh(node, entries, ray, visitRecordIndex) {
    queryPickTriangleEntriesBvh(node, entries, ray, visitRecordIndex);
  }

  function queryPickMeshTriangleBvh(node, entries, ray, visitRecordIndex) {
    queryPickTriangleEntriesBvh(node, entries, ray, visitRecordIndex);
  }

  return Object.freeze({
    appendPickMeshTrianglesFromGeometry,
    buildContourSurfaceGeometry,
    buildHighResolutionContourSurfaceGeometry,
    buildLocalGeometryTriangleEntries,
    buildLodSurfaceContourGeometry,
    buildPickBoundsBvh,
    buildPickMeshTriangleBvh,
    buildPickSpatialIndexOverflowBvh,
    buildPickSurfaceFacetBvh,
    buildPickSurfaceFacetEntries,
    buildSurfaceLodProfile,
    clampPickSpatialIndexCoord,
    computeAdaptiveContourSubdivisions,
    computeLineElementMatrix,
    computePickBoundingSphere,
    computeSurfaceElementMatrix,
    computeSurfaceLodSubdivisions,
    createLocalRayFromWorldRay,
    estimatePickRecordEntryDistance,
    getPickSpatialIndexAxisCellSize,
    getPickSpatialIndexCellCoords,
    getPickSpatialIndexKey,
    intersectLargeModelMeshLocalCatalog,
    intersectPickTriangleBvhClosest,
    intersectRayBoxDistances,
    queryPickMeshTriangleBvh,
    queryPickSpatialIndexOverflowBvh,
    queryPickSurfaceFacetBvh,
    sampleBilinearColor,
    sampleBilinearPoint,
    shouldIncludePickSpatialIndexOverflowRecord,
  });
}
