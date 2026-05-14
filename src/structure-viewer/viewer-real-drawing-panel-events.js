import {
  normalizeRealDrawingText,
} from './viewer-real-drawing-quality.js';

function toNumber(value, fallback = 0) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function getAttributeValue(node, name) {
  return normalizeRealDrawingText(typeof node?.getAttribute === 'function' ? node.getAttribute(name) : '');
}

function getNodeValue(node) {
  return normalizeRealDrawingText(node?.value);
}

function getAll(panel, selector) {
  return Array.from(typeof panel?.querySelectorAll === 'function' ? panel.querySelectorAll(selector) : []);
}

function getFirst(panel, selector) {
  return typeof panel?.querySelector === 'function' ? panel.querySelector(selector) : null;
}

function bindClickAll(panel, selector, handler) {
  const nodes = getAll(panel, selector);
  nodes.forEach((node) => {
    if (typeof node?.addEventListener === 'function') node.addEventListener('click', () => handler(node));
  });
  return nodes.length;
}

function bindEvent(node, eventName, handler) {
  if (typeof node?.addEventListener !== 'function') return false;
  node.addEventListener(eventName, handler);
  return true;
}

export function bindRealDrawingQualityPanelEvents(panel, {
  focusQuery = false,
  getActiveAssetRef = () => '',
  focusAsset = () => false,
  stepAsset = () => false,
  copyDeepLink = () => false,
  setQualityFilter = () => false,
  setAssetQuery = () => false,
  setBrowserSort = () => false,
} = {}) {
  const bindings = {
    assetSelect: false,
    stepButtons: 0,
    focusButtons: 0,
    isolateButtons: 0,
    copyButtons: 0,
    qualityFilterButtons: 0,
    browserQuery: false,
    browserClear: false,
    browserSort: false,
    nextReview: false,
    browserAssetButtons: 0,
    recentAssetButtons: 0,
    reviewAssetButtons: 0,
    promotionAssetButtons: 0,
  };

  const assetSelect = getFirst(panel, '[data-real-drawing-asset-select]');
  bindings.assetSelect = bindEvent(assetSelect, 'change', () => {
    focusAsset(getNodeValue(assetSelect));
  });

  bindings.stepButtons = bindClickAll(panel, '[data-real-drawing-step]', (button) => {
    stepAsset(toNumber(getAttributeValue(button, 'data-real-drawing-step'), 1));
  });
  bindings.focusButtons = bindClickAll(panel, '[data-real-drawing-focus]', () => {
    focusAsset(normalizeRealDrawingText(getActiveAssetRef()));
  });
  bindings.isolateButtons = bindClickAll(panel, '[data-real-drawing-isolate]', () => {
    focusAsset(normalizeRealDrawingText(getActiveAssetRef()), { isolate: true });
  });
  bindings.copyButtons = bindClickAll(panel, '[data-real-drawing-copy-link]', (button) => {
    const assetRef = getAttributeValue(button, 'data-real-drawing-copy-link') || normalizeRealDrawingText(getActiveAssetRef());
    copyDeepLink(assetRef, button);
  });
  bindings.qualityFilterButtons = bindClickAll(panel, '[data-real-drawing-quality-filter]', (button) => {
    setQualityFilter(getAttributeValue(button, 'data-real-drawing-quality-filter'));
  });

  const browserQuery = getFirst(panel, '[data-real-drawing-browser-query]');
  bindings.browserQuery = bindEvent(browserQuery, 'input', () => {
    setAssetQuery(getNodeValue(browserQuery), { preserveFocus: true });
  });
  if (bindings.browserQuery) {
    bindEvent(browserQuery, 'keydown', (event) => {
      if (event?.key !== 'Enter') return;
      const firstAsset = getFirst(panel, '[data-real-drawing-browser-asset]');
      const assetRef = getAttributeValue(firstAsset, 'data-real-drawing-browser-asset');
      if (assetRef) focusAsset(assetRef);
    });
    if (focusQuery) {
      if (typeof browserQuery.focus === 'function') browserQuery.focus({ preventScroll: true });
      const cursor = String(browserQuery.value ?? '').length;
      if (typeof browserQuery.setSelectionRange === 'function') browserQuery.setSelectionRange(cursor, cursor);
    }
  }

  const browserClear = getFirst(panel, '[data-real-drawing-browser-clear]');
  bindings.browserClear = bindEvent(browserClear, 'click', () => {
    setAssetQuery('', { preserveFocus: true });
  });

  const browserSort = getFirst(panel, '[data-real-drawing-browser-sort]');
  bindings.browserSort = bindEvent(browserSort, 'change', () => {
    setBrowserSort(getNodeValue(browserSort));
  });

  const nextReviewButton = getFirst(panel, '[data-real-drawing-next-review]');
  bindings.nextReview = bindEvent(nextReviewButton, 'click', () => {
    const assetRef = getAttributeValue(nextReviewButton, 'data-real-drawing-next-review');
    if (assetRef) focusAsset(assetRef);
  });

  bindings.browserAssetButtons = bindClickAll(panel, '[data-real-drawing-browser-asset]', (button) => {
    focusAsset(getAttributeValue(button, 'data-real-drawing-browser-asset'));
  });
  bindings.recentAssetButtons = bindClickAll(panel, '[data-real-drawing-recent-asset]', (button) => {
    focusAsset(getAttributeValue(button, 'data-real-drawing-recent-asset'));
  });
  bindings.reviewAssetButtons = bindClickAll(panel, '[data-real-drawing-review-asset]', (button) => {
    focusAsset(getAttributeValue(button, 'data-real-drawing-review-asset'));
  });
  bindings.promotionAssetButtons = bindClickAll(panel, '[data-real-drawing-promotion-asset]', (button) => {
    focusAsset(getAttributeValue(button, 'data-real-drawing-promotion-asset'));
  });

  return bindings;
}
