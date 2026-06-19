# Structure Viewer Product Workspace

The source viewer now has a project-workspace layer on top of the existing static 3D viewer. The goal is desktop-first engineer-in-loop review: browse registered projects, switch drawing variants, select members, inspect evidence-aware explanations, and export review reports without splitting the viewer into more standalone HTML files.

## Current Interface

- Project manifest schema: `structure-viewer-project-manifest.v1`
- Standard viewer query:

```text
src/structure-viewer/index.html?project=midas33_release&drawing=midas33_optimized&variant=optimized
```

- Backward-compatible aliases still work:

```text
src/structure-viewer/index.html?preset=midas33_optimized
src/structure-viewer/index.html?preset=real_drawing_private_3d
```

## Evidence Console First Scope

The first GUI productization surface is an Evidence Console, not a full project
dashboard or model authoring environment. The scope gate is generated with
`python3 scripts/build_evidence_console_scope_status.py`.

Evidence Console first scope:

- case list
- source/provenance inspector
- reference vs engine comparison
- residual audit
- worst member/story
- PASS/REVIEW/FAIL reviewer decision
- reproduce bundle export

Deferred full GUI surfaces:

- full project dashboard
- model editor
- accounts/permissions
- collaboration
- licensing

Launch readiness for this Evidence Console remains blocked until P0/P1,
measured real-project corpus, and validated customer completed-project shadow
evidence are all green. Missing customer shadow evidence must stay blocked; do
not close this gate with synthetic customer cases.

## Product Features

- Project browser: registered MIDAS33, real drawing, and release visualization entries are normalized into project/drawing rows with status badges. The bundled release project currently covers the OPSTOOL 606m outrigger plus seven megatall optimized/compare triples (`baseline`, `after_only`, `ai_compare`) so the viewer can browse the release optimization set from one manifest.
- Drawing search: the project browser supports `drawing_query` filtering across drawing title, id, source family, references, and quality flags without leaving the current viewer.
- Variant navigation: `baseline`, `optimized`, and `compare` buttons keep URL state explicit and reload through the existing preset/artifact loader.
- Drawing evidence drilldown: the selected drawing now shows review status, count verification/source, baseline/optimized refs, artifact path, quality flags, and registered variants directly in the project browser.
- Drawing review card: quality flags are normalized into `critical`, `warning`, and `info` issues. The selected drawing shows `상용 검토 가능`, `제한적 검토`, or `검토 불가`, issue counts, recommended action, and severity rows. Drawing list badges use the same issue-count model, so a blocked or limited drawing is visible before opening it.
- Before/optimized work surface: registered drawings can expose member-count, weight/cost proxy, risk-movement, and member-level comparison rows. The viewer now provides fixed comparison filters for `changed`, `reduced`, `retained`, `risk_up`, and `missing_evidence`; manifest-level deltas are shown as derived proxy evidence when exact member rows are not available. When exact member rows exist, the active comparison filter is also promoted into 3D highlight state and shown as an exact-member highlight count in the comparison panel/report.
- Analysis cockpit: the main viewer now derives eight command-center KPI cards, before/after optimization summary cards, top critical member rows with drift contribution, story-drift/load-step/material/heatmap chart panels, and a footer solver timeline from the loaded artifact. Empty result fields fall back to explicit artifact-derived product proxies instead of rendering zero-filled demo panels. Critical member rows are clickable and reuse the existing member focus path, so the cockpit is scan-first but still connected to model selection.
- Stage-native analysis overlays: the desktop command-center shell keeps top chrome compact, folds low-priority provenance/chip rows out of the first viewport, tightens the default camera fit, and renders lateral-load arrows plus base support markers directly in the 3D stage so the geometry reads as an analysis result rather than a neutral wireframe.
- Evidence Hub v1: the workspace now carries review tasks (`needs_check`, `approved`, `hold`, `rerun_required`), local annotations, solver receipt slots, CSV/JSON/IFC evidence ingest previews, renderable JSON ingest payloads, bundle import/export preview, and manifest lineage in the same local ops state/report flow. The URL also accepts `task`, `overlay`, and `receipt` parameters alongside the existing `project`, `drawing`, `variant`, `member`, and `comparison_filter` state.
- Commercial-tool crosswalk: CSV/JSON ingest rows now preserve normalized result rows and infer source profiles for MIDAS, ETABS/SAP2000, RFEM, Tekla, Revit, IFC, and generic exports. The viewer compares external member IDs, sections, and DCR values against the loaded viewer model, then reports matched rows, section/DCR mismatches, missing viewer members, and selected-member crosswalk evidence in the inspector and report. Crosswalk rows in the report panel are actionable: selectable rows focus the viewer member, and the mismatch isolation command applies the existing member isolate path for fast review.
- CSV mapper preview: the report panel exposes mapper presets for `auto`, MIDAS, ETABS/SAP2000, RFEM, Tekla, Revit, IFC, and generic CSV/JSON. Each preset shows accepted source columns for canonical fields such as `member_id`, `section`, `dcr_after`, `story`, `load_combo`, `material`, and `receipt_path`, so an engineer can see why an ingest row was normalized the way it was.
- Runtime ingest workspace: once an evidence ingest preview exists, the project browser adds an `Evidence Ingest Preview` project without mutating the checked-in manifest. Uploaded CSV/JSON/IFC rows can be opened as temporary project/drawing entries, while rendering falls back to the current viewer preset so evidence review does not break the 3D stage when the uploaded file is not a renderable model artifact.
- Overlay controls: comparison filters are exposed as desktop overlay actions. `changed`, `reduced`, and `risk_up` layers update the 3D highlight state; isolate buttons focus the first exact member in the active layer when exact rows exist, with manifest-level proxy rows falling back gracefully.
- Solver receipt model: `structure-viewer-solver-receipt.v1` links a member to source tool, load combo, before/after DCR, governing constraint, status (`verified`, `pending`, `mismatch`), receipt path, and evidence level. The inspector and report show `solver receipt verified`, `solver receipt pending`, or `solver receipt mismatch` instead of hiding missing evidence.
- Artifact count verification: `npm run verify:viewer-manifest` reads each `artifact_count_source` JSON and verifies the manifest member counts against `interactive_3d.baseline_segment_count` and `interactive_3d.after_segment_count`. The project browser, viewer report panel, and exported HTML report surface the same count-verification status/source, so demo/review output does not rely on a separate terminal log.
- Drawing quality: each drawing carries `commercial_review_status=ready|needs_review|blocked` plus quality flags such as `load_model_missing`, `empty_geometry`, `missing_members`, `scale_outlier`, `axis_flipped_review`, and `provenance_missing`.
- Input normalization: `viewer-project-workspace.js` exposes `normalizeProjectManifestRow()`, `buildProjectManifestFromRows()`, and `buildRuntimeProjectManifest()` so MIDAS, IFC, JSON, and CSV rows can be converted into the same workspace manifest contract before the viewer accepts them as reviewable drawings. `viewer-evidence-ingest-model.js` adds CSV/JSON/IFC ingest previews; CSV/JSON can carry member/result/receipt rows, while IFC v1 records metadata, geometry summary, and quality issues. Browser UI can now ingest evidence files, preview blocked drawing issues, attach parsed solver receipt rows into the local receipt index, and open the temporary ingest workspace from the project selector.
- Explainability panel: selected members show grouped section/material/load, D/C usage, review status, optimization delta, weight/cost proxy, optimization rationale, risk focus, review task state, solver receipt state, and whether each value is `exact source`, `derived proxy`, `local annotation`, or `missing evidence`. The checklist includes load, DCR, section change, missing evidence, review task, and solver receipt checks.
- Renderable ingest: JSON payloads with `model.nodes`/`model.elements` or `interactive_3d` segments are stored in local ops state as `structure-viewer-renderable-ingest-payload.v1`. When the viewer is opened with `project=evidence_ingest_preview`, that payload is normalized before preset fallback, so the temporary ingest project can render the uploaded evidence model directly.
- Lineage drilldown: the selection inspector and HTML/PDF report now show a source model → analysis result → optimization delta → optimized model → solver receipt → review task → report package chain. Each row is tagged as `exact source`, `derived proxy`, `local ingest payload`, or `missing evidence`, keeping engineer-in-loop claim boundaries visible in the exported review package.
- Report export: the viewer exports an HTML engineer-in-loop review report and a local audit JSONL file for the active project/drawing. The report includes the drawing review card, issue list, before/after member comparison, selected member checklist, local review note, review task table, solver receipt summary, commercial-tool crosswalk table, CSV mapper candidates, overlay state, renderable ingest status, lineage drilldown, import/ingest summary, and a viewer screenshot marker. PDF export is available through Playwright:
- Drawing sheet package: selected members now carry an explicit `structure-viewer-drawing-sheet-package.v1` bridge into the report/panel. It preserves SVG sheet links, drawing revision, callout id/label, and the viewer deep-link, so a review package can move from 3D selection to plan/elevation/isometric SVG evidence without relying on a live browser state.
- Static performance budget: `scripts/build_structure_viewer_performance_budget_manifest.py` records the wall/slab instancing, surface LOD, BVH picking, deformed pick refresh, Playwright canvas smoke, and pick-candidate cap contract in `implementation/phase1/structure_viewer_performance_budget_manifest.json`. This is a regression contract only; measured FPS/latency remains separate follow-up evidence.
- Browser performance probe: `scripts/measure-structure-viewer-performance.mjs` starts the source viewer under Playwright, waits for a nonblank well-framed canvas, samples `requestAnimationFrame`, and writes `implementation/phase1/structure_viewer_browser_performance_probe.json`. The npm verifier runs in `--verify` mode and writes to the OS temp directory so full quality gates do not dirty the repo. This remains local-browser smoke evidence, not a normalized customer-hardware FPS claim.
- Visual regression baseline: `scripts/measure-structure-viewer-visual-regression.mjs --update-baseline` captures 11 desktop/mobile render-mode and workflow signatures, including plan view, review member selection, compare overlay, CSV evidence ingest, renderable JSON ingest, section edit apply, and load-combination draft markers in `implementation/phase1/structure_viewer_visual_regression_baseline.json`. The npm verifier compares against that baseline in `--verify` mode and writes only to the OS temp directory. This is local visual-signature regression evidence, not a pixel-perfect customer-device rendering claim.

```bash
npm run export:viewer-report-pdf -- --query "project=midas33_release&drawing=midas33_optimized&variant=optimized" --out /tmp/structure_viewer_report.pdf
npm run verify:viewer-report-pdf
```

- Local ops state: recent project selections, active member/filter, review notes, review tasks, annotations, solver receipt index, last bundle import preview, last evidence ingest preview, export history, and audit events are stored in browser local storage as a reference control-plane surface. Recent chips restore project, drawing, variant, member, and comparison filter through URL state (`member` and `comparison_filter`), while audit JSONL and project-bundle JSON export/import preview give demos/reviews a portable activity trail without turning the static viewer into a SaaS tenant store.

## Verification

Run the focused checks:

```bash
python3 -m pytest -q tests/test_structure_viewer_project_workspace_contract.py \
  tests/test_structure_viewer_member_comparison_model_contract.py \
  tests/test_structure_viewer_review_task_model_contract.py \
  tests/test_structure_viewer_solver_receipt_model_contract.py \
  tests/test_structure_viewer_evidence_ingest_model_contract.py \
  tests/test_structure_viewer_drawing_sheet_package_contract.py \
  tests/test_structure_viewer_explainability_report_contract.py \
  tests/test_structure_viewer_local_ops_state_contract.py
npm run verify:viewer-manifest
npm run verify:frontend-browser-smoke -- --mode minimal
python3 scripts/build_structure_viewer_performance_budget_manifest.py --json
npm run verify:viewer-performance-probe
npm run verify:viewer-visual-regression
```

Full viewer verification:

```bash
python3 -m pytest -q tests/test_structure_viewer_*
npm run verify:viewer-manifest
npm run verify:frontend-browser-smoke
npm run verify:viewer-report-pdf
npm run verify:viewer-performance-probe
npm run verify:viewer-visual-regression
python3 scripts/build_structure_viewer_performance_budget_manifest.py --json --fail-blocked
python3 scripts/verify_quality_gate.py --mode pr
```

Commercial claim remains bounded to `engineer-in-loop commercial assist only` until strict EB/RH external evidence is attached.
