function safeNumber(value, fallback = 0) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function ensureThree(THREE) {
  if (!THREE?.Vector3 || !THREE?.Ray) {
    throw new TypeError('A compatible THREE namespace is required');
  }
  return THREE;
}

function asFunction(value, fallback) {
  return typeof value === 'function' ? value : fallback;
}

export function createViewerLargeModelPickingToolkit(THREE, config = {}) {
  const T = ensureThree(THREE);
  const lineScreenTolerancePx = Math.max(0, safeNumber(config.lineScreenTolerancePx, 10));
  const getBoundingDiagonal = asFunction(config.getBoundingDiagonal, () => 0);
  const getShowDeformed = asFunction(config.getShowDeformed, () => false);
  const worldUnitsPerPixelAtPoint = asFunction(config.worldUnitsPerPixelAtPoint, () => Infinity);
  const isLargeModelPickAccelerationEnabled = asFunction(
    config.isLargeModelPickAccelerationEnabled,
    () => false,
  );
  const isElementVisible = asFunction(config.isElementVisible, () => true);
  const getPickAnalyticSpatialIndex = asFunction(config.getPickAnalyticSpatialIndex, () => null);
  const getPickAnalyticRecords = asFunction(config.getPickAnalyticRecords, () => []);

  const {
    intersectRayBoxDistances,
    shouldIncludePickSpatialIndexOverflowRecord,
    estimatePickRecordEntryDistance,
    queryPickMeshTriangleBvh,
    queryPickSurfaceFacetBvh,
    queryPickSpatialIndexOverflowBvh,
    getPickSpatialIndexCellCoords,
    getPickSpatialIndexKey,
    getPickSpatialIndexAxisCellSize,
    intersectLargeModelMeshLocalCatalog,
    computePickBoundingSphere,
  } = config;

  function getPickTolerance() {
    return Math.max(
      0.5,
      safeNumber(getBoundingDiagonal(), 0) * 0.0025,
      lineScreenTolerancePx * 0.05,
    );
  }

  function queryPickSpatialIndexCandidates(index, ray) {
    if (!index || !(ray instanceof T.Ray)) return [];
    const hitRange = intersectRayBoxDistances(ray, index.boundsMin, index.boundsMax);
    const tolerance = getPickTolerance();
    const seenRecordIndices = new Set();
    const candidateEntries = [];
    const pushCandidateEntry = (recordIndex, cellEntryDistance = 0) => {
      if (seenRecordIndices.has(recordIndex)) return;
      const record = index.records[recordIndex];
      if (!record) return;
      if (
        cellEntryDistance === 0
        && !shouldIncludePickSpatialIndexOverflowRecord(record, ray, tolerance)
      ) return;
      const entryDistance = Math.max(
        safeNumber(cellEntryDistance, 0),
        estimatePickRecordEntryDistance(ray, record, tolerance),
      );
      if (!Number.isFinite(entryDistance)) return;
      seenRecordIndices.add(recordIndex);
      candidateEntries.push({ record, entryDistance });
    };
    if (getShowDeformed() && index.deformedMeshTriangleBvh) {
      queryPickMeshTriangleBvh(
        index.deformedMeshTriangleBvh,
        index.deformedMeshTriangleEntries,
        ray,
        pushCandidateEntry,
      );
    }
    if (index.meshTriangleBvh) {
      queryPickMeshTriangleBvh(index.meshTriangleBvh, index.meshTriangleEntries, ray, pushCandidateEntry);
    }
    if (index.surfaceFacetBvh) {
      queryPickSurfaceFacetBvh(index.surfaceFacetBvh, index.surfaceFacetEntries, ray, pushCandidateEntry);
    }
    if (index.nonSurfaceRecordBvh) {
      queryPickSpatialIndexOverflowBvh(index.nonSurfaceRecordBvh, ray, pushCandidateEntry);
    }
    if (index.fullRecordBvh && !index.meshTriangleBvh && !index.surfaceFacetBvh && !index.nonSurfaceRecordBvh) {
      queryPickSpatialIndexOverflowBvh(index.fullRecordBvh, ray, pushCandidateEntry);
      if (candidateEntries.length) {
        return candidateEntries.sort((left, right) => left.entryDistance - right.entryDistance);
      }
    }
    if (index.overflowBvh) {
      queryPickSpatialIndexOverflowBvh(index.overflowBvh, ray, pushCandidateEntry);
    } else {
      index.overflowIndices.forEach(recordIndex => pushCandidateEntry(recordIndex, 0));
    }
    if (index.denseBucketBvh) {
      queryPickSpatialIndexOverflowBvh(index.denseBucketBvh, ray, pushCandidateEntry);
    } else if (Array.isArray(index.denseBucketRecordIndices) && index.denseBucketRecordIndices.length) {
      index.denseBucketRecordIndices.forEach(recordIndex => pushCandidateEntry(recordIndex, 0));
    }
    if (!hitRange) return candidateEntries.sort((left, right) => left.entryDistance - right.entryDistance);
    const entryDistance = Math.max(hitRange.entry, 0);
    const exitDistance = Math.max(hitRange.exit, entryDistance);
    const startPoint = ray.at(entryDistance + 1e-6, new T.Vector3()).clamp(index.boundsMin, index.boundsMax);
    let { ix, iy, iz } = getPickSpatialIndexCellCoords(index, startPoint);
    const pushBucketRecords = (cellX, cellY, cellZ, cellEntryDistance) => {
      const bucket = index.buckets.get(getPickSpatialIndexKey(index, cellX, cellY, cellZ));
      if (!Array.isArray(bucket) || !bucket.length) return;
      bucket.forEach(recordIndex => pushCandidateEntry(recordIndex, cellEntryDistance));
    };
    pushBucketRecords(ix, iy, iz, entryDistance);
    const cellSizeX = getPickSpatialIndexAxisCellSize(index, 'x');
    const cellSizeY = getPickSpatialIndexAxisCellSize(index, 'y');
    const cellSizeZ = getPickSpatialIndexAxisCellSize(index, 'z');
    const stepX = ray.direction.x > 0 ? 1 : (ray.direction.x < 0 ? -1 : 0);
    const stepY = ray.direction.y > 0 ? 1 : (ray.direction.y < 0 ? -1 : 0);
    const stepZ = ray.direction.z > 0 ? 1 : (ray.direction.z < 0 ? -1 : 0);
    const cellBoundaryX = stepX > 0
      ? index.boundsMin.x + (ix + 1) * cellSizeX
      : index.boundsMin.x + ix * cellSizeX;
    const cellBoundaryY = stepY > 0
      ? index.boundsMin.y + (iy + 1) * cellSizeY
      : index.boundsMin.y + iy * cellSizeY;
    const cellBoundaryZ = stepZ > 0
      ? index.boundsMin.z + (iz + 1) * cellSizeZ
      : index.boundsMin.z + iz * cellSizeZ;
    let tMaxX = stepX !== 0 ? entryDistance + ((cellBoundaryX - startPoint.x) / ray.direction.x) : Infinity;
    let tMaxY = stepY !== 0 ? entryDistance + ((cellBoundaryY - startPoint.y) / ray.direction.y) : Infinity;
    let tMaxZ = stepZ !== 0 ? entryDistance + ((cellBoundaryZ - startPoint.z) / ray.direction.z) : Infinity;
    const tDeltaX = stepX !== 0 ? Math.abs(cellSizeX / ray.direction.x) : Infinity;
    const tDeltaY = stepY !== 0 ? Math.abs(cellSizeY / ray.direction.y) : Infinity;
    const tDeltaZ = stepZ !== 0 ? Math.abs(cellSizeZ / ray.direction.z) : Infinity;
    let traveled = entryDistance;
    let visitedCells = 1;
    while (
      visitedCells < index.visitedCellCap
      && traveled <= exitDistance
      && ix >= 0 && ix < index.dimX
      && iy >= 0 && iy < index.dimY
      && iz >= 0 && iz < index.dimZ
    ) {
      const nextTravel = Math.min(tMaxX, tMaxY, tMaxZ);
      if (!Number.isFinite(nextTravel)) break;
      traveled = nextTravel;
      const epsilon = 1e-8;
      if (tMaxX <= nextTravel + epsilon) {
        ix += stepX;
        tMaxX += tDeltaX;
      }
      if (tMaxY <= nextTravel + epsilon) {
        iy += stepY;
        tMaxY += tDeltaY;
      }
      if (tMaxZ <= nextTravel + epsilon) {
        iz += stepZ;
        tMaxZ += tDeltaZ;
      }
      if (ix < 0 || ix >= index.dimX || iy < 0 || iy >= index.dimY || iz < 0 || iz >= index.dimZ) break;
      pushBucketRecords(ix, iy, iz, traveled);
      visitedCells += 1;
    }
    return candidateEntries.sort((left, right) => left.entryDistance - right.entryDistance);
  }

  function intersectLargeModelLineRecord(ray, record) {
    if (!Array.isArray(record?.points) || record.points.length < 2 || !(ray instanceof T.Ray)) return null;
    const center = record.pickCenter instanceof T.Vector3
      ? record.pickCenter
      : record.points[0].clone().add(record.points[1]).multiplyScalar(0.5);
    const lineTolerance = worldUnitsPerPixelAtPoint(center) * lineScreenTolerancePx;
    const coarseRadius = Math.max(safeNumber(record.pickRadius, 0) + lineTolerance, lineTolerance);
    if (ray.distanceSqToPoint(center) > (coarseRadius * coarseRadius)) return null;
    const localCatalogHit = intersectLargeModelMeshLocalCatalog(ray, record, { preferDeformed: getShowDeformed() });
    if (localCatalogHit) return localCatalogHit;
    const pointOnRay = new T.Vector3();
    const pointOnSegment = new T.Vector3();
    const distanceSq = ray.distanceSqToSegment(record.points[0], record.points[1], pointOnRay, pointOnSegment);
    if (!Number.isFinite(distanceSq) || distanceSq > (lineTolerance * lineTolerance)) return null;
    const distanceAlongRay = pointOnRay.sub(ray.origin).dot(ray.direction);
    if (distanceAlongRay < 0) return null;
    return { distance: distanceAlongRay, mesh: record.mesh || null, data: record.data };
  }

  function intersectLargeModelSurfaceRecord(ray, record) {
    if (!Array.isArray(record?.points) || record.points.length < 4 || !(ray instanceof T.Ray)) return null;
    const center = record.pickCenter instanceof T.Vector3
      ? record.pickCenter
      : computePickBoundingSphere(record.points)?.center;
    const coarsePadding = Math.max(worldUnitsPerPixelAtPoint(center), 1e-3);
    const coarseRadius = Math.max(safeNumber(record.pickRadius, 0) + coarsePadding, coarsePadding);
    if (center && ray.distanceSqToPoint(center) > (coarseRadius * coarseRadius)) return null;
    const localCatalogHit = intersectLargeModelMeshLocalCatalog(ray, record, { preferDeformed: getShowDeformed() });
    if (localCatalogHit) return localCatalogHit;
    const firstHit = new T.Vector3();
    const secondHit = new T.Vector3();
    const hitA = ray.intersectTriangle(record.points[0], record.points[1], record.points[2], false, firstHit);
    const hitB = ray.intersectTriangle(record.points[0], record.points[2], record.points[3], false, secondHit);
    const hitPoint = hitA || hitB;
    if (!hitPoint) return null;
    const distanceAlongRay = hitPoint.distanceTo(ray.origin);
    if (distanceAlongRay < 0) return null;
    return { distance: distanceAlongRay, mesh: record.mesh || null, data: record.data };
  }

  function pickLargeModelRecord(ray) {
    const pickAnalyticSpatialIndex = getPickAnalyticSpatialIndex();
    const pickAnalyticRecords = getPickAnalyticRecords();
    if (
      !isLargeModelPickAccelerationEnabled()
      || !pickAnalyticSpatialIndex
      || !Array.isArray(pickAnalyticRecords)
      || !pickAnalyticRecords.length
    ) return null;
    const candidateEntries = queryPickSpatialIndexCandidates(pickAnalyticSpatialIndex, ray);
    if (!candidateEntries.length) return null;
    let bestHit = null;
    for (const candidate of candidateEntries) {
      if (bestHit && candidate.entryDistance > bestHit.distance) break;
      const record = candidate.record;
      if (!isElementVisible(record?.data)) continue;
      const nextHit = record.pickKind === 'surface'
        ? intersectLargeModelSurfaceRecord(ray, record)
        : intersectLargeModelLineRecord(ray, record);
      if (!nextHit) continue;
      if (!bestHit || nextHit.distance < bestHit.distance) bestHit = nextHit;
    }
    return bestHit;
  }

  return {
    queryPickSpatialIndexCandidates,
    intersectLargeModelLineRecord,
    intersectLargeModelSurfaceRecord,
    pickLargeModelRecord,
  };
}
