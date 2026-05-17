export const VIEWER_RENDER_MODES = ['wireframe', 'solid', 'contour'];
export const DEFAULT_VIEWER_RENDER_MODE = 'wireframe';

export function normalizeViewerRenderMode(value, fallback = DEFAULT_VIEWER_RENDER_MODE) {
  const normalized = String(value || '').trim().toLowerCase();
  if (VIEWER_RENDER_MODES.includes(normalized)) return normalized;
  const fallbackMode = String(fallback || '').trim().toLowerCase();
  return VIEWER_RENDER_MODES.includes(fallbackMode) ? fallbackMode : DEFAULT_VIEWER_RENDER_MODE;
}

export function buildViewerRenderModeButtonStates(activeMode = DEFAULT_VIEWER_RENDER_MODE) {
  const normalized = normalizeViewerRenderMode(activeMode);
  return VIEWER_RENDER_MODES.map(mode => ({
    mode,
    buttonId: `btn-${mode}`,
    active: mode === normalized,
  }));
}

export function getViewerLegendDisplayForRenderMode(mode = DEFAULT_VIEWER_RENDER_MODE) {
  return normalizeViewerRenderMode(mode) === 'contour' ? 'block' : 'none';
}
