import {
  getRealDrawingAssetRegistry,
  getRealDrawingClaimQualityFlags,
  getRealDrawingLoadEvidenceLabel,
  getRealDrawingQualityBadge,
  getRealDrawingSegmentLabel,
  getRealDrawingSourceQualityFlags,
  normalizeRealDrawingText,
  realDrawingAssetMatchesQualityFilter,
} from './viewer-real-drawing-quality.js';

function clampItemLimit(maxItems, fallback) {
  const value = Number(maxItems);
  return Number.isFinite(value) && value > 0 ? Math.floor(value) : fallback;
}

export function buildRealDrawingTreeModel(data = {}, {
  activeFilter = 'all',
  maxItems = 32,
} = {}) {
  const assets = getRealDrawingAssetRegistry(data);
  const filteredAssets = assets.filter((row) => realDrawingAssetMatchesQualityFilter(row, activeFilter));
  const limit = clampItemLimit(maxItems, 32);
  return {
    assets,
    filteredAssets,
    totalCount: assets.length,
    filteredCount: filteredAssets.length,
    heading: `Real Drawing Assets · ${filteredAssets.length}/${assets.length}`,
    emptyText: 'No assets match the active drawing quality filter.',
    items: filteredAssets.slice(0, limit).map((row) => {
      const assetRef = normalizeRealDrawingText(row?.asset_ref);
      const status = normalizeRealDrawingText(row?.status) || 'ready';
      const badgeInfo = getRealDrawingQualityBadge(row);
      const flags = Array.isArray(row?.quality_flags) ? row.quality_flags.map(normalizeRealDrawingText).filter(Boolean) : [];
      const claimFlags = getRealDrawingClaimQualityFlags(row).map((flag) => `claim:${flag}`);
      const sourceFlags = getRealDrawingSourceQualityFlags(row).map((flag) => `source:${flag}`);
      const loadEvidence = getRealDrawingLoadEvidenceLabel(row);
      const warning = normalizeRealDrawingText(row?.warning_label);
      const detail = warning || normalizeRealDrawingText(row?.geometry_mode) || status;
      const tooltipFlags = [...flags, ...claimFlags, ...sourceFlags, loadEvidence].filter(Boolean);
      const label = `${assetRef} · ${detail}`;
      return {
        assetRef,
        label,
        badgeText: `${badgeInfo.label} · ${getRealDrawingSegmentLabel(row)}`,
        badgeTone: badgeInfo.tone,
        badgeTitle: `${status}${tooltipFlags.length ? ` | ${tooltipFlags.join(', ')}` : ''}`,
        isolateKind: 'member',
        isolateValue: assetRef,
        isolateLabel: label,
      };
    }),
  };
}
