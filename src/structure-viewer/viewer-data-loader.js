export const DEFAULT_ARTIFACT_CANDIDATES = [
  '../../implementation/phase1/release/visualization/optimized_drawing_review_summary.json',
  '../../implementation/phase1/release/visualization/structural_optimization_viewer.json',
];

export const ARTIFACT_PRESET_CANDIDATES = {
  midas33: ['../../implementation/phase1/open_data/midas/midas_generator_33.json'],
  midas33_pr: ['../../implementation/phase1/open_data/midas/midas_generator_33.pr_recheck.json'],
  midas33_optimized: ['../../implementation/phase1/open_data/midas/midas_generator_33.optimized.roundtrip.json'],
};

export const PRESET_SIDECAR_FILES = {
  midas33: './index.midas33.data.js',
  midas33_pr: './index.midas33.data.js',
  midas33_optimized: './index.midas33.data.js',
  real_drawing_private_3d: './index.real_drawing_private.data.js',
};

export const EMBEDDED_DATA_IDS = [
  'embedded-model-data',
  'structure-model-data',
  'model-data',
  'interactive-3d-data',
];

export const GLOBAL_EMBEDDED_KEYS = [
  '__STRUCTURE_VIEWER_PAYLOAD__',
  '__STRUCTURE_MODEL__',
  '__EMBEDDED_MODEL__',
  '__STRUCTURE_VIEWER_DATA__',
];

export const GLOBAL_PRESET_PAYLOAD_KEYS = ['__STRUCTURE_VIEWER_PRESET_PAYLOADS__'];

export function normalizePresetToken(value) {
  const raw = String(value || '').trim().toLowerCase();
  if (!raw) return '';
  const normalized = raw.replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '');
  const aliasMap = {
    midas_33: 'midas33',
    midas33: 'midas33',
    midas33_pr: 'midas33_pr',
    midas33_precheck: 'midas33_pr',
    midas33_pr_recheck: 'midas33_pr',
    midas33_optimized: 'midas33_optimized',
    midas33_optimized_roundtrip: 'midas33_optimized',
    real_drawing_private_3d: 'real_drawing_private_3d',
    real_drawing_3d: 'real_drawing_private_3d',
    real_drawings: 'real_drawing_private_3d',
    real_drawing_private: 'real_drawing_private_3d',
  };
  return aliasMap[normalized] || normalized;
}

export function getRequestedPreset(search = globalThis.window?.location?.search || '') {
  const params = new URLSearchParams(search);
  const explicitPreset = normalizePresetToken(params.get('preset') || params.get('model_preset') || '');
  if (explicitPreset) return explicitPreset;
  return normalizePresetToken(globalThis.window?.__STRUCTURE_VIEWER_WORKSPACE_RESOLVED_PRESET__ || '');
}

export function buildArtifactCandidates(search = globalThis.window?.location?.search || '') {
  const params = new URLSearchParams(search);
  const hasExplicitPreset = Boolean(normalizePresetToken(params.get('preset') || params.get('model_preset') || ''));
  const preset = getRequestedPreset(search);
  const presetCandidates = Array.isArray(ARTIFACT_PRESET_CANDIDATES[preset])
    ? ARTIFACT_PRESET_CANDIDATES[preset]
    : [];
  const custom = [...params.getAll('artifact'), ...params.getAll('data')]
    .map(value => String(value || '').trim())
    .filter(Boolean);
  const workspaceArtifact = custom.length || hasExplicitPreset
    ? ''
    : String(globalThis.window?.__STRUCTURE_VIEWER_WORKSPACE_RESOLVED_ARTIFACT__ || '').trim();
  return [...new Set([...custom, workspaceArtifact, ...presetCandidates, ...DEFAULT_ARTIFACT_CANDIDATES].filter(Boolean))];
}

export function getPresetSidecarPath(preset) {
  const normalized = normalizePresetToken(preset);
  return normalized ? PRESET_SIDECAR_FILES[normalized] || '' : '';
}

export function readEmbeddedPresetPayload(preset, root = globalThis.window) {
  const normalized = normalizePresetToken(preset);
  if (!normalized || !root || typeof root !== 'object') return null;
  for (const key of GLOBAL_PRESET_PAYLOAD_KEYS) {
    const registry = root[key];
    if (!registry || typeof registry !== 'object') continue;
    const entry = registry[normalized];
    if (entry && typeof entry === 'object' && entry.payload && typeof entry.payload === 'object') {
      return {
        payload: entry.payload,
        label: String(entry.label || `preset ${normalized}`),
        reportName: String(entry.report_name || entry.label || normalized),
        sourcePath: String(entry.path || ''),
      };
    }
  }
  return null;
}

function defaultParseJsonText(text, label = 'embedded JSON') {
  try {
    return JSON.parse(text);
  } catch (err) {
    console.warn(`[Viewer] Failed to parse ${label}:`, err);
    return null;
  }
}

export function readEmbeddedPayload({
  root = globalThis.window,
  documentRef = globalThis.document,
  parseJson = defaultParseJsonText,
} = {}) {
  if (root && typeof root === 'object') {
    for (const key of GLOBAL_EMBEDDED_KEYS) {
      const payload = root[key];
      if (payload && typeof payload === 'object') {
        return { payload, label: `window.${key}` };
      }
    }
  }
  if (!documentRef || typeof documentRef.getElementById !== 'function') return null;
  for (const id of EMBEDDED_DATA_IDS) {
    const el = documentRef.getElementById(id);
    if (!el) continue;
    const payload = parseJson(el.textContent || '', `#${id}`);
    if (payload) return { payload, label: `#${id}` };
  }
  return null;
}

export async function loadPresetSidecarIfNeeded(preset, {
  root = globalThis.window,
  documentRef = globalThis.document,
} = {}) {
  const normalized = normalizePresetToken(preset);
  if (!normalized) return null;
  const embedded = readEmbeddedPresetPayload(normalized, root);
  if (embedded) return embedded;
  if (root?.__STRUCTURAL_SINGLEFILE__) return null;
  const sidecarPath = getPresetSidecarPath(normalized);
  if (!sidecarPath || !documentRef) return null;
  const existing = documentRef.querySelector?.(`script[data-viewer-preset="${normalized}"]`);
  if (!existing) {
    await new Promise((resolve, reject) => {
      const script = documentRef.createElement('script');
      script.src = sidecarPath;
      script.dataset.viewerPreset = normalized;
      script.onload = () => resolve();
      script.onerror = () => reject(new Error(`failed to load preset sidecar ${sidecarPath}`));
      documentRef.head.appendChild(script);
    });
  }
  return readEmbeddedPresetPayload(normalized, root);
}
