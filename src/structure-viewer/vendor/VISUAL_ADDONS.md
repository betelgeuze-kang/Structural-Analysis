# Viewer visual addons

Three.js r162 core exports `PMREMGenerator` from `three.module.js`.

CSS stack (see `docs/viewer-contract.md`):

- `design-tokens.css` — `--si-*` tokens from `DESIGN.md`
- `viewer-visual-identity.css` — glass HUD, contour legend, callout polish
- `viewer-product-shell.css` — `data-si-shell="product"` viewport-first shell; **Workspace** toggle restores cockpit chrome

Post-processing (EffectComposer / OutlinePass / SMAA) is implemented in-repo via:

- `viewer-visual-scene.js` — IBL (PMREM + room environment), infinite grid shader, selection outline meshes, ViewCube UI, technical drawing mode, quality tiers.
- `viewer-viewport-hud.js` — viewport context strip, contour legend, scale bar, compass, selection readout

External JSM postprocessing bundles are not vendored offline; selection glow uses scaled back-face outline meshes instead of GPU bloom passes for predictable performance on customer hardware.
