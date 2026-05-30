/**
 * Separates overlapping stage result callout anchor positions.
 */

function rectsOverlap(a, b, padding = 10) {
  return !(
    a.right + padding < b.left
    || a.left - padding > b.right
    || a.bottom + padding < b.top
    || a.top - padding > b.bottom
  );
}

function estimateCalloutRect(row, width = 168, height = 72) {
  return {
    left: row.left - width * 0.5,
    top: row.top - height,
    right: row.left + width * 0.5,
    bottom: row.top + 12,
  };
}

export function separateCalloutAnchorRows(rows = [], viewportRect = null, options = {}) {
  const minGap = Number(options.minGap) || 14;
  const maxIterations = Number(options.maxIterations) || 24;
  const width = Number(options.cardWidth) || 168;
  const height = Number(options.cardHeight) || 72;
  const items = rows.map((row) => ({ ...row }));
  if (!items.length) return items;

  const bounds = viewportRect || { width: 800, height: 600 };
  const min = 18;
  const maxLeft = Math.max(bounds.width - min, min);
  const maxTop = Math.max(bounds.height - min, min);

  for (let pass = 0; pass < maxIterations; pass += 1) {
    let moved = false;
    for (let i = 0; i < items.length; i += 1) {
      for (let j = i + 1; j < items.length; j += 1) {
        const rectA = estimateCalloutRect(items[i], width, height);
        const rectB = estimateCalloutRect(items[j], width, height);
        if (!rectsOverlap(rectA, rectB, minGap)) continue;
        const dy = (rectA.top + rectA.bottom) / 2 - (rectB.top + rectB.bottom) / 2;
        const push = dy >= 0 ? minGap : -minGap;
        items[j].top += push;
        items[j].left += minGap * 0.35 * (j % 2 === 0 ? 1 : -1);
        moved = true;
      }
    }
    items.forEach((row) => {
      row.left = Math.min(Math.max(row.left, min), maxLeft);
      row.top = Math.min(Math.max(row.top, min + height * 0.5), maxTop);
    });
    if (!moved) break;
  }
  return items;
}
