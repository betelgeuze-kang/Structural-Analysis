# Frontend Build Reproducibility

The frontend shell now uses a pinned `package.json` plus a committed `package-lock.json` so clean checkouts can verify the build path deterministically.

## Commands

- `npm run verify:frontend-contract`
  - Invokes the Rust-native `structural-frontend-contract` checker directly through Cargo.
  - Reads only repo files and strictly checks the expected manifest, lockfile, scripts, and build entrypoints against `native/decommission/legacy-frontend-build-contract-v1.json`.
  - Works even when `node_modules/` is missing.
  - Emits a canonical self-hashed receipt with command and network execution counts fixed at zero.
- `npm run verify:frontend-smoke`
  - Invokes the Rust-native `structural-frontend-contract smoke` process orchestrator. Rust first validates the pinned contract, directly executes the frozen `npm ci` then `npm run build` sequence with stop-on-failure semantics, rejects package/lock contract mutation across execution, and performs the built-tree delivery check before success.
  - `cargo run --quiet --locked --manifest-path native/Cargo.toml -p structural-frontend-contract -- smoke --root . --dry-run` emits a canonical self-hashed plan without spawning a process.
  - The execution receipt records only direct child-process exit codes. npm executable resolution and registry/cache access are explicitly not instrumented, and JavaScript/browser behavior remains outside this check.
  - This is the clean-checkout smoke path for CI or local verification.
- `npm run verify:workbench-viewer-delivery`
  - Invokes the Rust-native `structural-frontend-contract delivery` checker after every `npm run build` and verifies that the production output contains distinct Workbench and Static Viewer HTML entries with bounded, non-symlinked emitted assets.
  - Rejects the historical failure mode where the iframe path was absent from `dist/` and a static server silently returned the Workbench SPA fallback.
  - Also rejects legacy `App` ownership markers in the eager Workbench graph and requires exactly one separately emitted lazy legacy chunk.
  - Emits a canonical self-hashed receipt without executing JavaScript; browser behavior remains owned by the browser E2E gates.
- `npm run verify:frontend-browser-smoke`
  - Invokes the Rust-native `structural-frontend-contract browser-smoke` wrapper. Rust validates the frozen package, lock, and source inputs, owns one ephemeral IPv4 loopback server, directly launches the pinned Playwright CLI through Node, stops both sides on failure or completion, and emits a self-hashed receipt only after exit code zero. A live receipt hashes the installed Playwright launcher script.
  - The PR quality gate uses `-- --mode minimal`; the full gate runs desktop and mobile coverage.
  - `npm run verify:frontend-browser-smoke -- --mode minimal --dry-run` validates and hashes the exact command/spec plan without binding a listener or spawning Node.
  - Assumes Chromium is already available to Playwright; browser installation is an environment setup step, not part of the smoke command.
  - Node executable identity, Playwright transitive runtime bytes, Chromium, the JavaScript Viewer, and browser page requests remain outside this receipt. Sandboxes without installed packages or loopback sockets cannot produce a live receipt; hosted or clean-machine execution remains required.
- `npm run verify:workbench-prototype-dom-contract`
  - Invokes the Rust-native `structural-frontend-contract prototype` checker over the strict demo fixture, conservative six-state projection, bounded `app.js` safety/ownership markers, and prototype HTML attachment points.
  - Emits a canonical self-hashed receipt with process, network, and browser execution counts fixed at zero; it does not import or execute the JavaScript module or emulate a DOM.
  - The retained Playwright runtime continues to own rendered state, inert user-input, export, accessibility, and runtime behavior evidence.
- `npm run verify:workbench-prototype-browser-smoke`
  - Invokes the Rust-native `structural-frontend-contract prototype-browser-smoke` wrapper after the static prototype contract. Rust validates and hashes the frozen specification and owns one ephemeral IPv4 loopback server scoped to `prototype/structural-workbench/` plus one direct Node child running the pinned Playwright CLI.
  - `npm run verify:workbench-prototype-browser-smoke -- --dry-run` validates the exact command, environment, specification, static-contract receipt, and scoped server policy without binding a listener or spawning a process.
  - A live receipt is published only after Playwright exits zero and hashes the installed Playwright launcher script. Node executable identity, Playwright transitive bytes, Chromium, prototype JavaScript, rendered behavior, and browser page requests remain outside the receipt. A host with installed packages, Chromium, and loopback permission is required for live evidence.
- `npm run verify:viewer-manifest`
  - Invokes the Rust-native `structural-frontend-contract viewer-manifest` checker over the strict language-neutral JSON source and its byte-exact generated JavaScript projection.
  - Checks registered project/drawing/variant counts, OPSTOOL release triples, repo-confined artifact/provenance paths, and locally present artifact-count sources; missing gitignored release outputs remain explicit warnings.
  - Emits a canonical self-hashed receipt with command and network execution counts fixed at zero, without importing or executing the Viewer JavaScript module.
  - Runs before viewer/browser smoke in the PR quality gate so broken drawing registrations fail early.
- `npm run serve:viewer`
  - Starts the Rust-native source Viewer server on the fixed IPv4 loopback default `127.0.0.1:8765`; `STRUCTURE_VIEWER_PORT` may select another nonzero port, but non-loopback hosts are rejected.
  - Serves only bounded non-symlink files below explicit Viewer/open-data/visualization prefixes, accepts GET/HEAD only, and rejects traversal, backslashes, dotfiles, and repository-wide access.
  - `npm run serve:viewer -- --dry-run` emits the canonical self-hashed startup plan without binding a socket.
  - The server removes the Node HTTP runtime from this local launch boundary; the served Viewer application and browser remain JavaScript-owned.
  - Sandboxes that deny loopback sockets can verify routing and startup plans but cannot issue a live-listener receipt; that check remains for a hosted or clean-machine lane with loopback permission.
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
- `vite.config.ts` declares both Workbench and Static Viewer as explicit Vite build entries, preserving `dist/src/structure-viewer/index.html` for the embedded and direct-open Viewer path.
- Every production build passes `workbench_viewer_production_delivery_v1`; an iframe `src` string alone is not delivery evidence.
- The default Workbench request graph excludes the legacy `App` chunk. Browser E2E proves it is fetched only after navigating to `/#/legacy`.
- Browser smoke must load `src/structure-viewer/index.html`, verify a nonblank canvas, and exercise real-drawing selection controls.
- The offline Workbench prototype gate must pass the Rust-native static contract before the Rust-orchestrated Playwright smoke executes the retained browser behavior.
- Browser verification commands must not run `playwright install` implicitly; this keeps sandboxed quality gates from mutating the user home cache or stalling on network prompts.
- Source viewer reports must preserve selected-member sheet evidence through `structure-viewer-drawing-sheet-package.v1`, including SVG sheet link, revision, callout, and viewer deep-link.
- Full-gate PDF smoke must exercise the same source viewer report export path before release-facing promotion.
- Full-gate viewer performance probe must keep the local-browser claim boundary explicit with `live_performance_claim=false`.
- Full-gate visual regression must keep the local visual claim boundary explicit with `live_visual_claim=false` and record the active render mode/workflow marker for each baseline case.
