export const MIDAS33_PRESET_TOKENS = new Set([
  'midas33',
  'midas33_pr',
  'midas33_optimized',
]);

export const DEFAULT_MIDAS33_VIEW_PRESET = 'review';

export const MIDAS33_VIEW_PRESETS = {
  review: {
    label: 'Review',
    mode: 'solid',
    factors: { x: -0.55, y: 0.85, z: 0.35 },
    up: { x: 0, y: 0, z: 1 },
  },
  frame: {
    label: 'Frame',
    mode: 'solid',
    factors: { x: 0.72, y: 0.56, z: 0.48 },
    up: { x: 0, y: 0, z: 1 },
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
  const radius = Math.max(safeNumber(bounds.radius, 1), 1);
  const config = getMidas33ViewPresetConfig(preset);
  const factors = config.factors || {};
  return {
    target,
    position: {
      x: target.x + radius * safeNumber(factors.x, 0),
      y: target.y + radius * safeNumber(factors.y, 0),
      z: target.z + radius * safeNumber(factors.z, 0),
    },
    up: config.up || { x: 0, y: 0, z: 1 },
  };
}
