# Structural Insight — product shell (v2)

> Status: **closed** for source `index.html` (2026-05-30)

## Goal

Present the 3D viewer as a **standalone Structural Insight product** (MIDAS/Tekla/RFEM-class dark engineering UI), not an internal “optimization cockpit” page.

## Delivered

| Item | Implementation |
|------|----------------|
| Design tokens | `src/structure-viewer/design-tokens.css` (`--si-*` from `DESIGN.md`) |
| Visual layer | `viewer-visual-identity.css` — glass HUD, contour legend, info overlay, KPI/chart polish |
| Product shell | `viewer-product-shell.css` + `data-si-shell="product"` default |
| Branding | Top bar: **Structural Insight** / **Precision Engineering** |
| Viewport-first layout | Collapsed left/right rails by default; stage header hidden; 3D stage dominant |
| Stage clutter | Product mode hides DOM stage overlays (callouts, rulers, glyphs, receipt) |
| Viewport HUD | `viewer-viewport-hud.js` — case/mode, contour ramp, scale, compass, coords |
| Viewport graphics | `viewer-visual-scene.js` — PMREM/IBL, infinite grid, ViewCube, quality tiers |
| Workspace escape hatch | Top bar **Workspace** → `data-si-shell="workspace"` restores cockpit chrome |
| Persistence | `structure-viewer-si-shell`, panel collapse keys in `sessionStorage` |
| Contract | `docs/viewer-contract.md` CSS stack + shell modes |

## CSS load order

`design-tokens.css` → `design-theme.css` (layout baseline) → `viewer-visual-identity.css` → `viewer-product-shell.css` → `commercial-cockpit-polish.css`

## Model recentering

Large artifact coordinates (e.g. MIDAS global X/Y/Z) are recentered after build:

- `applyViewerModelRecenter(nodes)` sets `modelGroup` / `deformedGroup` / overlay group position to negative structural-viewer centroid `(x, z, y)`.
- Infinite grid stays at world origin; the structure sits on the grid center after `fitAll()`.
- Product shell hides `analysisOverlayGroup` (3D load arrows / support markers); workspace mode shows them again.
- `window.getViewerModelRecenterOffset()` returns the applied offset for tooling/tests.

## Not in scope (intentional)

- Removing `design-theme.css` (437KB layout grid still required)
- Renaming every “cockpit” string in JS panel IDs (internal only)
- Single-file export reskin (generator path unchanged)

## Verification

1. Open `src/structure-viewer/index.html?project=midas33_release&drawing=midas33_optimized&variant=optimized`
2. Confirm product shell: compact top bar, large viewport, HUD visible, rails collapsed
3. Click **Workspace** — tabs, stage header, chart strip, left result controls return
4. Toggle back — viewport-first layout restores
