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

## Expected Contract

- `package.json` contains only the dependencies needed by the active workbench entry.
- Dependency versions are pinned exactly instead of using floating `^` or `~` ranges.
- `package-lock.json` is the source of truth for deterministic installs.
- `vite.config.ts` declares the React/Vite build entry explicitly.
- Browser smoke must load `src/structure-viewer/index.html`, verify a nonblank canvas, and exercise real-drawing selection controls.
- Full-gate PDF smoke must exercise the same source viewer report export path before release-facing promotion.
