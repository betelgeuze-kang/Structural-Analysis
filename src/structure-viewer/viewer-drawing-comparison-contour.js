function safeNumber(value, fallback = NaN) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

export function isNodeContourField(field = '') {
  return field === 'disp_mag' || field === 'stress_vm';
}

export function hasUsableContourRange(values = []) {
  const finite = (Array.isArray(values) ? values : [])
    .map((value) => safeNumber(value, NaN))
    .filter(Number.isFinite);
  if (finite.length < 2) return false;
  return Math.max(...finite) - Math.min(...finite) > 1e-9;
}

export function mergeContourRanges(...ranges) {
  let mn = Infinity;
  let mx = -Infinity;
  for (const range of ranges) {
    if (!range || typeof range !== 'object') continue;
    const rangeMin = safeNumber(range.mn, NaN);
    const rangeMax = safeNumber(range.mx, NaN);
    if (Number.isFinite(rangeMin)) mn = Math.min(mn, rangeMin);
    if (Number.isFinite(rangeMax)) mx = Math.max(mx, rangeMax);
  }
  if (!Number.isFinite(mn) || !Number.isFinite(mx)) {
    return { mn: 0, mx: 1 };
  }
  if (Math.abs(mx - mn) < 1e-9) {
    return { mn: mn - 0.5, mx: mx + 0.5 };
  }
  return { mn, mx };
}

export function buildContourContextDescriptor({
  field = 'dcr',
  mn = 0,
  mx = 1,
  cmapFn = null,
  nodeScalarById = null,
  nodeScalarScale = 1,
  nodeScalarSource = 'direct',
  role = '',
  linked = false,
} = {}) {
  return {
    field,
    mn,
    mx,
    cmapFn,
    nodeScalarById,
    nodeScalarScale,
    nodeScalarSource,
    role,
    linked,
  };
}

export function summarizeContourContexts(baselineContext = null, optimizedContext = null) {
  const field = baselineContext?.field || optimizedContext?.field || 'dcr';
  const linkedRange = mergeContourRanges(
    baselineContext ? { mn: baselineContext.mn, mx: baselineContext.mx } : null,
    optimizedContext ? { mn: optimizedContext.mn, mx: optimizedContext.mx } : null,
  );
  return {
    field,
    linkedRange,
    baselineSource: baselineContext?.nodeScalarSource || 'direct',
    optimizedSource: optimizedContext?.nodeScalarSource || 'direct',
  };
}
