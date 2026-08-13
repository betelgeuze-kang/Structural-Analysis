# Native Workbench UI transition v1

This contract keeps the React/TypeScript/JavaScript surface visible while product authority moves
to `structural-workbench`. It is a C5 transition inventory, not a C6 removal receipt.

## Native authority now present

The bounded fixed-guided ModelIR or normalized-MGT NDTHA profile runs
`Import -> Validate -> Run -> Resume -> Compare -> Report` without Python, Node, a browser, a CLI
subprocess, or an external renderer. The same Rust binary now also provides:

- `inspect`: a deterministic self-hashed operator view over verified stage, ResultIR, backend,
  comparison, and PDF receipts;
- `review`: one immutable explicit human disposition bound to the exact session, ResultIR,
  comparison IR, and PDF. Solver completion or comparison success never infers this decision;
- `export`: a deterministic self-hashed handoff manifest containing relative artifact names,
  lengths, and hashes.
- `catalog` / `catalog-show`: strict, self-hashed browsing of the 26-case language-neutral native
  benchmark catalog, including lifecycle, truth, size, first-target and text filters. Geometry-only
  cases remain excluded from accuracy and no runner/acquisition string is executed.
- `evidence` / `evidence-show`: bounded read-only browsing of an operator-supplied copied evidence
  bundle. The native reader rejects unsafe paths, symlinks, duplicate IDs/paths, checksum drift and
  malformed JSON, exposes commit mismatch, and never promotes blocked or signal-free sources.
- `structural-evidence check/build`: a Rust-native evidence-bundle builder driven by the fixed
  language-neutral source map under `native/evidence`. It rejects mixed commits, duplicate JSON
  keys, symlinks, oversized input and sensitive-data signals, copies exact source bytes, requires an
  explicit timestamp, and atomically publishes only to a new output directory.
- `structural-catalog check/build`: a Rust-native benchmark-catalog builder driven by the
  language-neutral source map under `native/catalog`. It strictly checks all 21 open-data reports
  and five PEER snapshots, reproduces the prior 26 cases, rejects drift and unsafe metadata, and
  never fetches or executes a catalog string.
- `structural-frontend-contract check/smoke/delivery/frontend-build/frontend-dev/frontend-preview/playwright-install/prototype/prototype-browser-smoke/workbench-v2-browser-smoke/browser-smoke/viewer-js-syntax/viewer-sample-workflow/viewer-performance-probe/viewer-visual-regression/viewer-readme-capture/viewer-report-pdf-export/viewer-report-pdf-smoke/serve/viewer-manifest`: a Rust-native frontend
  contract checker and clean-build process orchestrator driven by the language-neutral transition
  map under `native/decommission`. It replaces the prior Node package, built-tree, and Viewer
  manifest checkers, the former Node smoke wrapper, and the offline prototype DOM shim with strict
  duplicate-key JSON parsing, a conservative typed demo-status projection, an
  exact neutral-JSON-to-JavaScript projection, repo-confined non-symlink path and emitted-asset
  inventories, eager/lazy chunk separation, a fixed stop-on-failure `npm ci` / `npm run build`
  process sequence, and canonical self-hashed receipts. npm/Vite/TypeScript still perform the
  actual legacy install and build; the native prototype check is static. Rust now owns the source
  Viewer, Workbench prototype, and Workbench v2 browser-smoke wrappers, scoped loopback/SPA
  servers, and direct child-process lifetimes. For Workbench v2, Rust also owns the fixed
  `VITE_BASE_PATH=/` npm-build boundary, post-build delivery check, JSON-loader/spec hashes, and
  exact replacement of inherited `NODE_OPTIONS` for the direct Node child and its workers. Retained npm, Vite, TypeScript,
  Node, Playwright, Chromium, React/TypeScript application code, Viewer JavaScript, and prototype
  JavaScript still own build or rendered behavior and browser-page request authority. Playwright
  still owns inert-input, export, accessibility, and rendered-behavior evidence.
  Frontend TypeScript/Vite build orchestration is Rust-native: the package build command freezes a
  bounded inventory of the configured source roots, hashes the installed TypeScript and Vite CLI
  entrypoints, removes inherited `NODE_OPTIONS`, owns two direct Node children, rejects mutation,
  and validates the emitted delivery tree. Node, TypeScript, Vite, plugins, transitive npm bytes,
  and build-time environment/network behavior remain retained and explicitly outside that receipt.
  Frontend development-server orchestration is Rust-native: the package development command hashes
  the installed Vite CLI, removes inherited `NODE_OPTIONS`, fixes loopback/strict-port arguments,
  and owns one direct Node child. Vite retains the listener, HMR and source-mutation semantics;
  listener readiness, plugins, environment loading and rendered behavior remain uninstrumented.
  Frontend production-delivery preview serving is Rust-native: the package preview command validates
  the frontend and built-delivery receipts, binds only fixed IPv4 loopback, serves `dist/` through
  the confined SPA router, and spawns no Node, Vite, browser, Python, or child process. A valid built
  tree is required, and rendered browser behavior plus clean-machine publication remain open.
  Playwright browser-install orchestration is Rust-native: hosted workflows enter one command that
  hashes the installed Playwright CLI, removes inherited `NODE_OPTIONS`, and owns the exact Chromium
  plus OS-dependency installation child. Playwright retains downloads, caches, elevation and host
  package mutation; downloaded bytes and rollback remain uninstrumented.
  Viewer JavaScript syntax gate orchestration is Rust-native: the runtime-input CI enters through
  one Rust command that freezes the exact ten source identities, owns each `node --check` child,
  rejects source mutation, and emits a canonical receipt. The retained Node parser and executable
  identity still own JavaScript parsing; the gate starts no listener and requires no browser.
  The Viewer report PDF verification wrapper is Rust-native: it owns the retained exporter child,
  temporary and explicit-output cleanup, bounded PDF/HTML reads, hashes, PDF header/size checks,
  required report markers, and optional `pdftotext` verification. The retained Node exporter still
  owns its internal loopback server, Playwright, Chromium, Viewer rendering, and PDF generation.
  The Viewer performance verifier is Rust-native as well: it owns the retained probe child and
  artifact lifecycle, strict JSON decoding, frozen source identities, and independent ready-time,
  RAF, browser-error, and canvas checks. The retained Node probe still owns its internal loopback
  server, Playwright/Chromium, Viewer rendering, canvas inspection, and RAF sampling.
  The Viewer sample-workflow verifier is Rust-native: it owns the retained probe child and artifact
  cleanup, strictly parses bounded duplicate-key-free JSON, and independently rechecks the exact
  four ordered MIDAS33/real-drawing steps, completion-time budget, browser error/warning aggregates,
  and nonblank significant-pixel canvas evidence. The retained Node probe still owns its internal
  loopback server, Playwright/Chromium, Viewer navigation/input/rendering, canvas inspection, and raw
  artifact construction. This automated rehearsal is not human new-user observation or approval.
  The Viewer visual-regression verifier is Rust-native: it freezes the baseline plus four source
  identities, owns the retained probe child and output cleanup, strictly parses duplicate-key-free
  bounded JSON, and independently checks all 11 ordered workflow cases, loopback URLs, canvas
  geometry/signatures, source rows, baseline deltas, and tolerances. The retained Node probe still
  owns its internal loopback server, Playwright/Chromium, Viewer state manipulation, screenshots,
  canvas sampling, and raw report construction; explicit baseline refresh remains a direct Node
  operator action.
  The local source-Viewer server is also Rust-native and fixed to an allowlisted IPv4 loopback
  surface, but the JavaScript Viewer it serves is still legacy runtime authority.

This closes bounded results inspection, review/export, and catalog and copied-evidence browsing for
the current native product. The canonical benchmark JSON and its Rust-native benchmark-catalog
builder now live under `native/catalog`; the legacy React browser consumes that native-owned file.
Both catalog and evidence-bundle generators and their contract tests are Rust-native; the legacy
npm commands are wrappers only. The legacy frontend clean-build orchestration, static contract,
and built-tree delivery are Rust-native. Loopback Viewer serving and default Viewer
project-manifest checks and Viewer, prototype, and Workbench v2 browser-smoke orchestration are Rust-native as
well. Viewer report PDF verification plus Viewer sample-workflow, performance, and visual-regression
process/artifact verification are also Rust-native; npm package installation, Vite/TypeScript
execution, the Node PDF exporter and measurement probes, Playwright/Chromium execution, browser
checks, prototype JavaScript, and viewer runtime remain Node/browser-owned. It does not provide a
general visual model editor or 3D result explorer. Broader fixture/oracle migration is still needed
before language-neutral golden ownership is complete.

## Legacy authority still active

`native/decommission/workbench-ui-transition-v1.json` freezes the current source and CI inventory.
The product deployment, benchmark-catalog generation, and evidence-bundle generation authorities
have left React/Node, and the frontend smoke orchestration, static/delivery, prototype-static,
Viewer-server, Viewer manifest, Viewer/prototype/Workbench v2 browser-smoke, Viewer PDF verification
wrapper, Viewer sample-workflow/process artifact verifier, Viewer performance process/artifact
verifier, and Viewer visual-regression verifier
authorities have
left Node, but seven active workflows still use Node for frontend, viewer, AI-contract, or broader quality
verification. React/Vite source, TypeScript tests, static JavaScript viewer modules, remaining Node
scripts, and their package manifest remain active verification or parity material. They are not a
deletion target yet.

The checker fails if source counts or active Node workflow inventory drift without an explicit
ledger update. It also fails if the manifest claims C6 without deriving it from every prerequisite.
Run it with:

```text
python3 scripts/check_native_workbench_ui_transition.py --json --fail-blocked
```

`--require-c6` intentionally exits nonzero while the transition remains open.

## Removal gates

React/TypeScript/JavaScript removal remains forbidden until all of these are simultaneously true:

1. general native feature parity is complete for the accepted product scope;
2. active Node verification authority is zero and Rust/Cargo/CTest/HIP E2E owns the tests;
3. Python and Node fixture ownership has moved to language-neutral golden data;
4. the approved-device HIP C2 receipts are complete;
5. the deprecation window and rollback package are complete;
6. a Python/Node-free clean-machine product package E2E is authoritative;
7. native result, error, and checksum parity is complete.

Until then `removal_allowed` and `c6_complete` stay false. A contract pass means the inventory is
honest; it does not mean the transition is finished.
