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
- `model-view`: a deterministic self-hashed ANSI-free terminal topology projection for every
  current semantically valid ModelIR v2 profile. Rust renders only the canonical C++ snapshot in
  fixed isometric/XY/XZ/YZ views, lists full node/element identities and analysis types, and keeps
  explicit analysis blockers visible. Its closed `en-US`/`ko-KR` paths translate fixed labels only
  and preserve the exact canvas, values, machine tokens and provenance; general localization and
  arbitrary-nodal-field result exploration remain open.
- `model-edit-node`: a deterministic provenance-bound edit of one existing node's finite SI
  coordinates. Rust edits only the canonical C++ snapshot, retains upstream provenance, marks the
  status of any matching exact/canonicalized round-trip row as approximated, strictly reparses and
  C++-revalidates the result, and atomically publishes a new model plus self-hashed receipt. Visual
  dragging and broader model editing remain open.
- `model-edit-nodal-load`: deterministic replacement of the six finite SI components of one
  existing nodal load inside one named load pattern. Rust edits only the canonical C++ snapshot,
  binds both identities plus previous/new components and source hashes, conservatively marks a
  matching load-pattern round-trip row approximated, then strictly reparses and C++-revalidates the
  result before create-new publication. Pattern/load creation, deletion, retargeting, combinations,
  self-weight, visual manipulation, and broader model editing remain open.
- `model-edit-constraint-value`: deterministic replacement of one finite metre/radian prescribed
  value for a DOF already restrained by one existing named constraint. Rust binds the constraint,
  DOF, unit, previous/new values and source hashes, conservatively marks a matching constraint
  round-trip row approximated, then strictly reparses and C++-revalidates before create-new
  publication. Restraint changes, constraint creation/deletion/retargeting, multi-point constraints,
  visual manipulation, and broader model editing remain open.
- `report-view`: a deterministic self-hashed UTF-8 linear alternative in `en-US` or `ko-KR` that
  re-verifies the exact ResultIR/ReportIR/Markdown/PDF/receipt chain and optional Unicode review,
  uses no ANSI/color/position/graphics semantics, and escapes directional-spoofing controls. It is
  not WCAG/PDF-UA certification; the durable fixed-font v1 PDF remains ASCII-only.
- `result-view`: a deterministic self-hashed ANSI-free table and fixed-width plot over one verified
  terminal NDTHA ResultIR. It exposes exact top-displacement, drift-ratio, base-shear or
  residual-infinity values plus per-step convergence metadata through a maximum 256-row window.
  ResultIR v1 has no `dt_s`, so the view preserves step indices and does not invent timestamps;
  `en-US` and `ko-KR` change labels only while exact values and provenance remain visible; general
  3D/deformed/modal/contour exploration remains open.
- `result-deformed-view`: a deterministic self-hashed ANSI-free original/deformed overlay for the
  exact executed fixed-guided one-story profile. It revalidates the immutable ModelIR through C++,
  applies only a selected ResultIR top displacement in global X, records the visual magnification
  and all provenance hashes, and fails closed outside the completed prefix. Its `en-US` and `ko-KR`
  paths preserve the same numeric geometry and identities. It is not a general nodal-field, stress,
  contour, modal, animation, or 3D-result surface.
- `report-export-pdf`: a deterministic bounded embedded-font PDF export in `en-US` or `ko-KR`.
  It re-verifies the stored v1 report chain, embeds a renamed OFL-1.1 Type0/ToUnicode subset,
  publishes to a new directory, and leaves the Workbench unchanged. Fixed labels and printable
  ASCII dynamic values are supported; arbitrary Unicode, tagged PDF, and PDF/UA remain open.
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
- `structural-frontend-contract check/smoke/delivery/frontend-audit/frontend-audit-report/frontend-build/frontend-dev/frontend-install/frontend-preview/phase5-task-browser-smoke/playwright-install/prototype/prototype-browser-smoke/workbench-v2-browser-smoke/browser-smoke/viewer-js-syntax/viewer-sample-workflow/viewer-performance-probe/viewer-visual-regression/viewer-readme-capture/viewer-report-pdf-export/viewer-report-pdf-smoke/serve/viewer-manifest`: a Rust-native frontend
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
  Frontend dependency-install orchestration is Rust-native: hosted workflows enter one direct Rust
  command that validates package/lock/source-map identity, removes inherited `NODE_OPTIONS`, owns
  the exact `npm ci` child, and rejects contract mutation. npm registry/cache access, lifecycle
  scripts, configuration/environment, transitive processes, extracted bytes, `node_modules`
  contents and rollback remain retained and uninstrumented.
  Frontend dependency-audit orchestration is Rust-native: frontend-web CI enters one direct Rust
  command that freezes the frontend contract, removes inherited `NODE_OPTIONS`, owns the exact
  `npm audit --audit-level high` child, rejects repository-contract mutation, and records every
  numeric exit. Numeric nonzero remains deliberately non-blocking and is only
  `advisory_or_tool_failure`; npm findings, registry/network/configuration/tool-failure
  classification, dependency/license clearance, and external cache mutation remain outside the
  receipt.
  Frontend dependency-audit evidence projection and publication are Rust-native:
  `scripts/build_frontend_dependency_audit_report.py` now launches one direct Cargo
  `frontend-audit-report` command and no longer launches or interprets npm itself. Rust owns the
  exact `npm audit --json` child, bounded concurrent stdout/stderr capture, duplicate-key and
  non-finite rejection, metadata/finding-count cross-checking, vulnerability aggregation,
  compatibility report construction, frontend-contract and destination mutation checks, and
  verified staging/backup/rename publication with rollback. The
  Python wrapper strictly checks the canonical self-hashed receipt and published report identity,
  then retains only CLI/output compatibility. npm remains the advisory oracle; registry/cache
  behavior, independent advisory validation, dependency/license clearance, clean-machine evidence,
  C5, and C6 remain open.
  Quality-gate frontend entrypoints are Rust-native: `scripts/verify_quality_gate.py` still owns
  Python sequencing of the broader repository checks, but its frontend install, strict audit,
  contract, build, manifest and browser verifiers call direct Cargo commands with npm package-script
  entrypoints zero. Strict audit publishes the canonical unclassified receipt before returning
  failure on numeric nonzero, preserving the prior gate behavior; all retained inner runtimes and
  Python sequencing remain visible.
  Hosted frontend/browser workflow product entrypoints are Rust-native: frontend web, nightly full,
  runtime-input Viewer, and Viewer-browser jobs call the Cargo commands directly, with no `npm run`,
  `npx`, direct Node, or direct `npm audit` entrypoint. The two native catalog/evidence Bash wrappers remain because they
  own repository-root and source-commit timestamp projection; package scripts remain local
  conveniences and Node/npm still execute retained frontend internals.
  Frontend development-server orchestration is Rust-native: the package development command hashes
  the installed Vite CLI, removes inherited `NODE_OPTIONS`, fixes loopback/strict-port arguments,
  and owns one direct Node child. Vite retains the listener, HMR and source-mutation semantics;
  listener readiness, plugins, environment loading and rendered behavior remain uninstrumented.
  Frontend production-delivery preview serving is Rust-native: the package preview command validates
  the frontend and built-delivery receipts, binds only fixed IPv4 loopback, serves `dist/` through
  the confined SPA router, and spawns no Node, Vite, browser, Python, or child process. A valid built
  tree is required, and rendered browser behavior plus clean-machine publication remain open.
  Playwright browser-install orchestration is Rust-native: hosted workflows enter one direct Rust command that
  hashes the installed Playwright CLI, removes inherited `NODE_OPTIONS`, and owns the exact Chromium
  plus OS-dependency installation child. Playwright retains downloads, caches, elevation and host
  package mutation; downloaded bytes and rollback remain uninstrumented.
  Phase 5 task-based browser-smoke orchestration is Rust-native: the legacy Python receipt script
  launches one direct Cargo command instead of directly owning npm build, npm preview, socket
  readiness, or npx Playwright processes. Rust freezes the exact developer-preview specification
  and five-step vocabulary, owns the frontend build, fixed `127.0.0.1:4173` SPA listener and direct
  Playwright child, and emits a canonical receipt only after unchanged inputs/delivery, all zero
  exits, and no request error. Python still owns compatibility release-receipt assembly; retained
  Node, TypeScript, Vite, Playwright, Chromium, React behavior and human usability evidence remain
  open, and this sandbox cannot provide the live loopback receipt.
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
checks, prototype JavaScript, and viewer runtime remain Node/browser-owned. It provides only one
bounded command-level node-coordinate edit, one bounded existing-nodal-load component edit, one
bounded existing-constraint prescribed-value edit, one
bounded response-history table, and one exact-profile selected-step deformed-shape overlay, not a
general visual model editor or arbitrary-nodal-field 3D result explorer.
Broader fixture/oracle migration is still needed before language-neutral golden ownership is
complete.

The bounded terminal UTF-8 linear report view is C5-implemented for English and Korean.
The bounded embedded-font PDF export is C5-implemented
for English and Korean fixed labels. General graphical
accessibility, full application localization, assistive-technology validation, tagged PDF and
arbitrary-Unicode PDF input remain an explicit removal blocker; the composite parity row stays
open.

The bounded general-ModelIR terminal topology view is C5-implemented for the eight current positive
profiles and all four fixed projections. It closes native semantic-snapshot geometry inspection,
not solver selection/execution, perspective interaction, or deformed/modal/contour result
exploration. The separate C++-revalidated node-coordinate, existing-nodal-load component and
existing-restrained-DOF prescribed-value commands close only three provenance-bound edit
operations; visual dragging, entity creation/deletion/retargeting, restraint-mask changes, and
general property/material/section/load-combination/constraint-topology editing remain open, so the
composite visual parity row stays open.

The bounded NDTHA response-history view is C5-implemented for four closed response channels and
arbitrary completed-prefix windows of at most 256 rows. It closes exact terminal response-table
inspection for the current profile, not time reconstruction or 3D/deformed/modal/contour result
exploration, so the composite visual parity row remains open.

The fixed-guided deformed-shape view is C5-implemented for the exact executed one-story adapter
profile, four fixed projections, and a bounded visual magnification. It closes selected-step
original/deformed inspection only; general nodal displacement fields, element curvature, stress,
contour, modal, animation, and interactive 3D exploration remain open.

The localized NDTHA result views are C5-implemented for the closed `en-US` and `ko-KR` locale set.
The locale changes only labels and operator guidance: exact response values, coordinates and all
provenance identities remain visible, output stays ANSI-free, and each localized byte stream is
self-hashed. This linear-text slice does not claim WCAG conformance, assistive-technology testing,
general application localization, or general 3D result parity, so the composite accessibility and
visual-parity rows remain open.

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
