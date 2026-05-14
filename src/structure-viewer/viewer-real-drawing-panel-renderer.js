import {
  getRealDrawingAssetOptionLabel,
  getRealDrawingClaimQualityFlags,
  getRealDrawingInspectorRows,
  getRealDrawingLoadEvidenceLabel,
  getRealDrawingQualityBadge,
  getRealDrawingQualityFlags,
  getRealDrawingReviewAction,
  getRealDrawingSegmentLabel,
  getRealDrawingSourceQualityFlags,
  isRealDrawingReviewAsset,
  normalizeRealDrawingText,
  realDrawingAssetMatchesQualityFilter,
} from './viewer-real-drawing-quality.js';

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function safeNumber(value, fallback = 0) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function normalizeList(values) {
  return (Array.isArray(values) ? values : [])
    .map((value) => normalizeRealDrawingText(value))
    .filter(Boolean);
}

export function renderRealDrawingActiveInspector(row) {
  const assetRef = normalizeRealDrawingText(row?.asset_ref);
  if (!assetRef) return '';
  const badge = getRealDrawingQualityBadge(row);
  const notice = normalizeRealDrawingText(row?.quality_notice)
    || normalizeRealDrawingText(row?.warning_label)
    || normalizeRealDrawingText(row?.status)
    || 'ready';
  const rows = getRealDrawingInspectorRows(row);
  return `
    <section class="real-drawing-active-inspector" data-real-drawing-active-inspector="true" data-real-drawing-active-ref="${escapeHtml(assetRef)}">
      <div class="real-drawing-active-inspector__header">
        <span>Active Drawing</span>
        <strong>${escapeHtml(assetRef)}</strong>
        <span class="quality-badge quality-badge--${escapeHtml(badge.tone)}">${escapeHtml(badge.label)}</span>
      </div>
      <div class="real-drawing-active-inspector__grid">
        ${rows.map((item) => `
          <div class="real-drawing-inspector-cell real-drawing-inspector-cell--${escapeHtml(item.tone)}" data-real-drawing-inspector-row="${escapeHtml(item.label)}">
            <span>${escapeHtml(item.label)}</span>
            <strong>${escapeHtml(item.value)}</strong>
            <small>${escapeHtml(item.detail)}</small>
          </div>`).join('')}
      </div>
      <div class="real-drawing-active-inspector__notice">${escapeHtml(notice)}</div>
    </section>`;
}

function renderRealDrawingRecentRail(activeAssetRef, recentAssetRefs = []) {
  const recentRefs = normalizeList(recentAssetRefs).slice(0, 6);
  if (!recentRefs.length) return '';
  return `
      <div class="real-drawing-recent-rail" aria-label="Recent optimized drawings">
        <span>Recent</span>
        <div class="real-drawing-recent-rail__items">
          ${recentRefs.map((ref) => `
            <button type="button" class="real-drawing-recent-chip${ref === activeAssetRef ? ' is-active' : ''}" data-real-drawing-recent-asset="${escapeHtml(ref)}" title="${escapeHtml(ref)}">
              ${escapeHtml(ref)}
            </button>`).join('')}
        </div>
      </div>`;
}

function renderRealDrawingBrowserBlock({
  assets = [],
  browserAssets = [],
  activeAssetRef = '',
  activeQuery = '',
  activeSort = 'priority',
  recentAssetRefs = [],
  sortOptions = [],
} = {}) {
  const nextReviewRef = normalizeRealDrawingText((browserAssets.find(isRealDrawingReviewAsset) || browserAssets[0] || {}).asset_ref);
  const renderedSortOptions = sortOptions.map((option) => (
    `<option value="${escapeHtml(option.key)}"${option.key === activeSort ? ' selected' : ''}>${escapeHtml(option.label)}</option>`
  )).join('');
  const recentRail = renderRealDrawingRecentRail(activeAssetRef, recentAssetRefs);
  const visibleAssets = browserAssets.slice(0, 32);
  const overflowCount = Math.max(browserAssets.length - visibleAssets.length, 0);
  const list = visibleAssets.length
    ? visibleAssets.map((row) => {
      const assetRef = normalizeRealDrawingText(row.asset_ref);
      const badge = getRealDrawingQualityBadge(row);
      const route = normalizeRealDrawingText(row.file_type)
        || normalizeRealDrawingText(row.route)
        || normalizeRealDrawingText(row.status)
        || '--';
      const flags = [
        ...getRealDrawingQualityFlags(row),
        ...getRealDrawingSourceQualityFlags(row).map((flag) => `source:${flag}`),
        ...getRealDrawingClaimQualityFlags(row).map((flag) => `claim:${flag}`),
      ].filter(Boolean);
      const loadEvidence = getRealDrawingLoadEvidenceLabel(row);
      const detail = loadEvidence
        || flags.slice(0, 3).join(', ')
        || normalizeRealDrawingText(row.quality_notice)
        || normalizeRealDrawingText(row.status)
        || 'ready';
      return `
        <button type="button" class="real-drawing-browser-item${assetRef === activeAssetRef ? ' is-active' : ''}" data-real-drawing-browser-asset="${escapeHtml(assetRef)}">
          <span class="quality-badge quality-badge--${escapeHtml(badge.tone)}">${escapeHtml(badge.label)}</span>
          <span class="real-drawing-browser-item__body">
            <strong>${escapeHtml(assetRef)}</strong>
            <small>${escapeHtml(route)}</small>
          </span>
          <span class="real-drawing-browser-item__meta">
            <span>${escapeHtml(getRealDrawingSegmentLabel(row))}</span>
            <small>${escapeHtml(detail)}</small>
          </span>
        </button>`;
    }).join('')
    : '<div class="panel-placeholder">No drawings match the active browser filters.</div>';
  return `
    <section class="real-drawing-browser" data-real-drawing-browser="true">
      <div class="real-drawing-browser__header">
        <span>Drawing Browser</span>
        <strong>${escapeHtml(String(browserAssets.length))}/${escapeHtml(String(assets.length))}</strong>
      </div>
      <div class="real-drawing-browser__search">
        <input type="search" id="real-drawing-browser-query" data-real-drawing-browser-query="true" value="${escapeHtml(activeQuery)}" placeholder="RD-001 / ifc / load" aria-label="Search optimized drawings">
        <button type="button" data-real-drawing-browser-clear="true" aria-label="Clear drawing search"${activeQuery ? '' : ' disabled'}>&times;</button>
      </div>
      <div class="real-drawing-browser__toolbar">
        <label class="real-drawing-browser__sort" for="real-drawing-browser-sort">
          <select id="real-drawing-browser-sort" data-real-drawing-browser-sort="true" aria-label="Sort optimized drawings">${renderedSortOptions}</select>
        </label>
        <button type="button" data-real-drawing-next-review="${escapeHtml(nextReviewRef)}"${nextReviewRef ? '' : ' disabled'}>Next Review</button>
      </div>
      ${recentRail}
      <div class="real-drawing-browser__list" data-real-drawing-browser-count="${escapeHtml(String(browserAssets.length))}">
        ${list}
      </div>
      ${overflowCount ? `<div class="real-drawing-browser__overflow">+${escapeHtml(String(overflowCount))} more</div>` : ''}
    </section>`;
}

function renderRealDrawingPromotionBlock({
  plannedUnlockBatch = [],
  openPromotionItems = [],
  nextQueueTitle = 'Next Quality Closure',
  promotionTarget = 0,
  promotionAfterBatch = 0,
  promotionCurrent = 0,
  promotionRequiredDelta = 0,
} = {}) {
  if (plannedUnlockBatch.length) {
    return `
    <section class="real-drawing-promotion-panel" data-real-drawing-promotion-target="${escapeHtml(String(promotionTarget))}">
      <div class="real-drawing-promotion-header">
        <span>Next Unlock Batch</span>
        <strong>${escapeHtml(String(promotionCurrent))} -&gt; ${escapeHtml(String(promotionAfterBatch || promotionCurrent))}/${escapeHtml(String(promotionTarget || '--'))}</strong>
      </div>
      <div class="real-drawing-review-list real-drawing-unlock-list" data-real-drawing-promotion-count="${escapeHtml(String(plannedUnlockBatch.length))}">
        ${plannedUnlockBatch.map((row) => {
          const assetRef = normalizeRealDrawingText(row.asset_ref);
          const family = normalizeRealDrawingText(row.promotion_family) || 'solver-exact promotion';
          const action = normalizeRealDrawingText(row.recommended_action) || family;
          const delta = safeNumber(row.expected_solver_exact_delta, 1);
          const flags = normalizeList(row.quality_flags);
          const claimFlags = normalizeList(row.claim_quality_flags).map((flag) => `claim:${flag}`);
          const loadEvidence = getRealDrawingLoadEvidenceLabel(row);
          return `
            <button type="button" class="real-drawing-review-item real-drawing-promotion-item" data-real-drawing-promotion-asset="${escapeHtml(assetRef)}">
              <span class="quality-badge quality-badge--review">${escapeHtml(normalizeRealDrawingText(row.promotion_id) || 'unlock')}</span>
              <span class="real-drawing-review-item__body">
                <strong>${escapeHtml(assetRef)} · ${escapeHtml(family)}</strong>
                <span>${escapeHtml(action)}</span>
                <small>${escapeHtml([...flags, ...claimFlags, loadEvidence].filter(Boolean).join(', ') || normalizeRealDrawingText(row.status) || 'pending')}</small>
              </span>
              <span class="real-drawing-review-item__segments">+${escapeHtml(String(delta))}</span>
            </button>`;
        }).join('')}
      </div>
    </section>`;
  }
  if (!(promotionTarget && promotionRequiredDelta === 0)) return '';
  const nextQueueList = openPromotionItems.length
    ? `<div class="real-drawing-review-list real-drawing-unlock-list" data-real-drawing-open-promotion-count="${escapeHtml(String(openPromotionItems.length))}">
        ${openPromotionItems.map((row) => {
          const assetRef = normalizeRealDrawingText(row.asset_ref);
          const family = normalizeRealDrawingText(row.promotion_family) || 'quality closure';
          const action = normalizeRealDrawingText(row.recommended_action) || family;
          const blocker = normalizeRealDrawingText(row.blocker_reason_code);
          const effort = normalizeRealDrawingText(row.effort_label) || 'review';
          const flags = normalizeList(row.quality_flags);
          const claimFlags = normalizeList(row.claim_quality_flags).map((flag) => `claim:${flag}`);
          const loadEvidence = getRealDrawingLoadEvidenceLabel(row);
          return `
            <button type="button" class="real-drawing-review-item real-drawing-promotion-item" data-real-drawing-promotion-asset="${escapeHtml(assetRef)}">
              <span class="quality-badge quality-badge--review">${escapeHtml(normalizeRealDrawingText(row.promotion_id) || 'open')}</span>
              <span class="real-drawing-review-item__body">
                <strong>${escapeHtml(assetRef)} · ${escapeHtml(family)}</strong>
                <span>${escapeHtml(action)}</span>
                <small>${escapeHtml(loadEvidence || blocker || [...flags, ...claimFlags].filter(Boolean).join(', ') || normalizeRealDrawingText(row.status) || 'pending')}</small>
              </span>
              <span class="real-drawing-review-item__segments">${escapeHtml(effort)}</span>
            </button>`;
        }).join('')}
      </div>`
    : '<div class="panel-placeholder">Archive native write-back promotions are closed for this target.</div>';
  return `
    <section class="real-drawing-promotion-panel" data-real-drawing-promotion-state="target-reached" data-real-drawing-promotion-target="${escapeHtml(String(promotionTarget))}">
      <div class="real-drawing-promotion-header">
        <span>Solver-Exact Target Reached</span>
        <strong>${escapeHtml(String(promotionCurrent))}/${escapeHtml(String(promotionTarget))}</strong>
      </div>
      <div class="real-drawing-promotion-header real-drawing-promotion-header--subtle">
        <span>${escapeHtml(nextQueueTitle)}</span>
        <strong>${escapeHtml(String(openPromotionItems.length))}</strong>
      </div>
      ${nextQueueList}
    </section>`;
}

export function buildRealDrawingQualityPanelHtml({
  data = {},
  quality = {},
  filteredAssets = [],
  browserAssets = [],
  reviewRows = [],
  activeAssetRef = '',
  activeAsset = {},
  activeIsolation = {},
  activeFilter = 'all',
  activeSort = 'priority',
  activeQuery = '',
  recentAssetRefs = [],
  qualityFilters = [],
  sortOptions = [],
  plannedUnlockBatch = [],
  openPromotionItems = [],
  nextQueueTitle = 'Next Quality Closure',
  promotionTarget = 0,
  promotionAfterBatch = 0,
  promotionCurrent = 0,
  promotionRequiredDelta = 0,
} = {}) {
  const activeBadge = getRealDrawingQualityBadge(activeAsset);
  const activeLoadEvidence = getRealDrawingLoadEvidenceLabel(activeAsset);
  const activeInspectorBlock = renderRealDrawingActiveInspector(activeAsset);
  const browserBlock = renderRealDrawingBrowserBlock({
    assets: filteredAssets,
    browserAssets,
    activeAssetRef,
    activeQuery,
    activeSort,
    recentAssetRefs,
    sortOptions,
  });
  const switcherOptions = (quality.assets || []).map((row) => {
    const assetRef = normalizeRealDrawingText(row.asset_ref);
    return `<option value="${escapeHtml(assetRef)}"${assetRef === activeAssetRef ? ' selected' : ''}>${escapeHtml(getRealDrawingAssetOptionLabel(row))}</option>`;
  }).join('');
  const isolateActive = activeIsolation.kind === 'member' && activeIsolation.value === activeAssetRef;
  const switcherBlock = `
    <section class="real-drawing-switcher" aria-label="Optimized drawing selector">
      <div class="real-drawing-switcher__top">
        <span class="quality-badge quality-badge--${escapeHtml(activeBadge.tone)}">${escapeHtml(activeBadge.label)}</span>
        <strong>${escapeHtml(activeAssetRef || '--')}</strong>
        <span>${escapeHtml(`${(quality.assets || []).length} drawings`)}</span>
      </div>
      <div class="real-drawing-switcher__row">
        <label class="real-drawing-switcher__select" for="real-drawing-asset-select">
          <select id="real-drawing-asset-select" data-real-drawing-asset-select="true">${switcherOptions}</select>
        </label>
        <div class="real-drawing-switcher__controls" aria-label="Drawing navigation">
          <button type="button" class="real-drawing-switcher__button" data-real-drawing-step="-1" title="Previous drawing" aria-label="Previous drawing">&lsaquo;</button>
          <button type="button" class="real-drawing-switcher__button" data-real-drawing-step="1" title="Next drawing" aria-label="Next drawing">&rsaquo;</button>
          <button type="button" class="real-drawing-switcher__button" data-real-drawing-focus="true" title="Focus drawing" aria-label="Focus drawing">&#8982;</button>
          <button type="button" class="real-drawing-switcher__button${isolateActive ? ' is-active' : ''}" data-real-drawing-isolate="true" title="Isolate drawing" aria-label="Isolate drawing">&#8857;</button>
        </div>
      </div>
      <div class="real-drawing-switcher__meta">
        <span>${escapeHtml(getRealDrawingReviewAction(activeAsset))}</span>
        <small>${escapeHtml(activeLoadEvidence || normalizeRealDrawingText(activeAsset.quality_notice) || normalizeRealDrawingText(activeAsset.status) || 'ready')}</small>
      </div>
      <div class="real-drawing-action-row">
        <button type="button" data-real-drawing-copy-link="${escapeHtml(activeAssetRef)}">Copy Link</button>
        <span data-real-drawing-browser-state="true">${escapeHtml(`${activeFilter} | ${activeSort}${activeQuery ? ` | ${activeQuery}` : ''}`)}</span>
      </div>
    </section>`;
  const filterButtons = qualityFilters.map((filter) => {
    const count = (quality.assets || []).filter((row) => realDrawingAssetMatchesQualityFilter(row, filter.key)).length;
    const selected = filter.key === activeFilter;
    return `<button type="button" class="quality-filter-button${selected ? ' is-active' : ''}" data-real-drawing-quality-filter="${escapeHtml(filter.key)}">${escapeHtml(filter.label)} <span>${count}</span></button>`;
  }).join('');
  const emptyReviewText = activeQuery
    ? 'No review queue assets match the drawing browser filters.'
    : 'No review queue assets in the active quality filter.';
  const reviewList = reviewRows.length
    ? reviewRows.map((row) => {
      const badge = getRealDrawingQualityBadge(row);
      const assetRef = normalizeRealDrawingText(row.asset_ref);
      const flags = getRealDrawingQualityFlags(row);
      const claimFlags = getRealDrawingClaimQualityFlags(row).map((flag) => `claim:${flag}`);
      const sourceFlags = getRealDrawingSourceQualityFlags(row).map((flag) => `source:${flag}`);
      const loadEvidence = getRealDrawingLoadEvidenceLabel(row);
      const notice = normalizeRealDrawingText(row.quality_notice)
        || normalizeRealDrawingText(row.geometry_mode)
        || normalizeRealDrawingText(row.status);
      return `
        <button type="button" class="real-drawing-review-item" data-real-drawing-review-asset="${escapeHtml(assetRef)}">
          <span class="quality-badge quality-badge--${escapeHtml(badge.tone)}">${escapeHtml(badge.label)}</span>
          <span class="real-drawing-review-item__body">
            <strong>${escapeHtml(assetRef)}</strong>
            <span>${escapeHtml(getRealDrawingReviewAction(row))}</span>
            <small>${escapeHtml([...flags, ...claimFlags, ...sourceFlags, loadEvidence].filter(Boolean).join(', ') || notice || 'solver-exact')}</small>
          </span>
          <span class="real-drawing-review-item__segments">${escapeHtml(getRealDrawingSegmentLabel(row))}</span>
        </button>`;
    }).join('')
    : `<div class="panel-placeholder">${escapeHtml(emptyReviewText)}</div>`;
  const promotionBlock = renderRealDrawingPromotionBlock({
    plannedUnlockBatch,
    openPromotionItems,
    nextQueueTitle,
    promotionTarget,
    promotionAfterBatch,
    promotionCurrent,
    promotionRequiredDelta,
  });
  return `
    ${switcherBlock}
    ${activeInspectorBlock}
    <div class="real-drawing-quality-summary" data-real-drawing-quality-gate="${escapeHtml(quality.gateLabel)}">
      <div><span>Gate</span><strong>${escapeHtml(quality.gateLabel)}</strong></div>
      <div><span>Renderable</span><strong>${escapeHtml(String(safeNumber(data?.meta?.real_drawing_renderable_asset_count, quality.assetCount)))}/${escapeHtml(String(quality.assetCount))}</strong></div>
      <div><span>Solver Exact</span><strong>${escapeHtml(String(quality.exactCount))}</strong></div>
      <div><span>Review Queue</span><strong>${escapeHtml(String(quality.reviewQueueCount))}</strong></div>
      <div><span>Full Exact</span><strong>${quality.fullSolverExactReady ? 'true' : 'false'}</strong></div>
    </div>
    ${promotionBlock}
    <div class="quality-filter-bar" aria-label="Real drawing quality filters">${filterButtons}</div>
    ${browserBlock}
    <div class="real-drawing-review-list" data-real-drawing-review-count="${escapeHtml(String(quality.reviewQueueCount))}">
      ${reviewList}
    </div>`;
}

