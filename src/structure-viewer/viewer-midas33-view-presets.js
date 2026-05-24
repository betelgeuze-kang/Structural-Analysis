export const MIDAS33_PRESET_TOKENS = new Set([
  'midas33',
  'midas33_pr',
  'midas33_optimized',
]);

export const DEFAULT_MIDAS33_VIEW_PRESET = 'review';

export const MIDAS33_VIEW_PRESETS = {
  review: {
    label: 'Review',
    mode: 'contour',
    factors: { x: -0.70, y: 0.46, z: 0.82 },
    distanceScale: 0.92,
    targetOffset: { x: 0.02, y: 0.12, z: -0.04 },
    up: { x: 0, y: 1, z: 0 },
  },
  frame: {
    label: 'Frame',
    mode: 'contour',
    factors: { x: 0.78, y: 0.58, z: 0.54 },
    distanceScale: 1.08,
    targetOffset: { x: -0.02, y: 0.06, z: 0.02 },
    up: { x: 0, y: 1, z: 0 },
  },
  plan: {
    label: 'Plan',
    mode: 'wireframe',
    factors: { x: 0.08, y: 1.25, z: 0.18 },
    up: { x: 0, y: 0, z: 1 },
  },
};

export function normalizeMidas33ViewPreset(value) {
  const normalized = String(value || '').trim().toLowerCase();
  if (normalized === 'fit') return 'fit';
  return MIDAS33_VIEW_PRESETS[normalized] ? normalized : DEFAULT_MIDAS33_VIEW_PRESET;
}

export function isMidas33PresetToken(value) {
  return MIDAS33_PRESET_TOKENS.has(String(value || '').trim().toLowerCase());
}

export function getMidas33ViewPresetConfig(value) {
  return MIDAS33_VIEW_PRESETS[normalizeMidas33ViewPreset(value)] || MIDAS33_VIEW_PRESETS[DEFAULT_MIDAS33_VIEW_PRESET];
}

export function buildMidas33ViewButtonStates(activePreset = '') {
  const active = normalizeMidas33ViewPreset(activePreset);
  return ['review', 'frame', 'plan', 'fit'].map(key => ({
    key,
    active: Boolean(activePreset) && key === active,
  }));
}

function safeNumber(value, fallback = 0) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function safePoint(value) {
  if (!value || typeof value !== 'object') return null;
  const x = safeNumber(value.x, NaN);
  const y = safeNumber(value.y, NaN);
  const z = safeNumber(value.z, NaN);
  if (!Number.isFinite(x) || !Number.isFinite(y) || !Number.isFinite(z)) return null;
  return { x, y, z };
}

export function buildMidas33CameraPoseFromBounds(bounds, preset = DEFAULT_MIDAS33_VIEW_PRESET) {
  if (!bounds || typeof bounds !== 'object') return null;
  const target = safePoint(bounds.center);
  if (!target) return null;
  const size = safePoint(bounds.size) || { x: 0, y: 0, z: 0 };
  const radius = Math.max(safeNumber(bounds.radius, 1), 1);
  const config = getMidas33ViewPresetConfig(preset);
  const factors = config.factors || {};
  const targetOffset = config.targetOffset || {};
  const resolvedTarget = {
    x: target.x + size.x * safeNumber(targetOffset.x, 0),
    y: target.y + size.y * safeNumber(targetOffset.y, 0),
    z: target.z + size.z * safeNumber(targetOffset.z, 0),
  };
  const distanceScale = Math.max(safeNumber(config.distanceScale, 1), 0.1);
  return {
    target: resolvedTarget,
    position: {
      x: resolvedTarget.x + radius * distanceScale * safeNumber(factors.x, 0),
      y: resolvedTarget.y + radius * distanceScale * safeNumber(factors.y, 0),
      z: resolvedTarget.z + radius * distanceScale * safeNumber(factors.z, 0),
    },
    up: config.up || { x: 0, y: 0, z: 1 },
  };
}
