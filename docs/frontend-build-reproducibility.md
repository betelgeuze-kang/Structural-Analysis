# Frontend Build Reproducibility

The frontend shell now uses a pinned `package.json` plus a committed `package-lock.json` so clean checkouts can verify the build path deterministically.

## Commands

- `npm run verify:frontend-contract`
  - Reads only repo files and checks the expected manifest, lockfile, scripts, and build entrypoints.
  - Works even when `node_modules/` is missing.
- `npm run verify:frontend-smoke`
  - Runs the contract check, executes `npm ci`, and then runs `npm run build`.
  - This is the clean-checkout smoke path for CI or local verification.
- `npm run verify:frontend-browser-smoke`
  - Starts a local static HTTP server and runs the Playwright structure-viewer smoke against the source HTML.
  - The PR quality gate uses `-- --mode minimal`; the full gate runs desktop and mobile coverage.
- `npm run verify:viewer-manifest`
  - Checks the structure-viewer project manifest schema, registered drawing/variant counts, OPSTOOL release triples, and repo-local artifact/provenance paths.
  - Runs before viewer/browser smoke in the PR quality gate so broken drawing registrations fail early.
- `npm run verify:viewer-report-pdf`
  - Uses Playwright to export the active MIDAS33 engineer-in-loop report to PDF and checks that the PDF is non-empty with a valid `%PDF-` header.
  - Runs in the full quality gate because it is a release-output smoke rather than a fast PR contract.
- `npm run verify:viewer-performance-probe`
  - Starts the source viewer in a local browser, waits for a nonblank well-framed canvas, and samples `requestAnimationFrame`.
  - Runs in `--verify` mode in the full quality gate and writes to the OS temp directory, so the gate does not dirty tracked artifacts.
  - To persist the evidence artifact, run `node scripts/measure-structure-viewer-performance.mjs`; it writes `implementation/phase1/structure_viewer_browser_performance_probe.json`.
  - This is a local browser performance smoke. It is not a normalized customer-hardware FPS claim.
- `npm run verify:viewer-visual-regression`
  - Starts the source viewer in 11 desktop/mobile render-mode and workflow states, including plan view, review member selection, compare overlay, CSV evidence ingest, renderable JSON ingest, section edit apply, and load-combination draft, compares local canvas signatures against `implementation/phase1/structure_viewer_visual_regression_baseline.json`, and writes the verify report to the OS temp directory.
  - To refresh the tracked baseline, run `node scripts/measure-structure-viewer-visual-regression.mjs --update-baseline`.
  - This is local visual-signature regression evidence, not a pixel-perfect customer-device rendering claim.
- `python3 scripts/verify_structure_viewer_contracts.py`
  - Runs the source viewer contract suite before browser smoke.
  - Covers evidence ingest, solver receipt, commercial-tool crosswalk, lineage drilldown, drawing sheet package, report export, PDF export, and single-file inline contracts.

## Expected Contract

- `package.json` contains only the dependencies needed by the active workbench entry.
- Dependency versions are pinned exactly instead of using floating `^` or `~` ranges.
- `package-lock.json` is the source of truth for deterministic installs.
- `vite.config.ts` declares the React/Vite build entry explicitly.
- Browser smoke must load `src/structure-viewer/index.html`, verify a nonblank canvas, and exercise real-drawing selection controls.
- Source viewer reports must preserve selected-member sheet evidence through `structure-viewer-drawing-sheet-package.v1`, including SVG sheet link, revision, callout, and viewer deep-link.
- Full-gate PDF smoke must exercise the same source viewer report export path before release-facing promotion.
- Full-gate viewer performance probe must keep the local-browser claim boundary explicit with `live_performance_claim=false`.
- Full-gate visual regression must keep the local visual claim boundary explicit with `live_visual_claim=false` and record the active render mode/workflow marker for each baseline case.
