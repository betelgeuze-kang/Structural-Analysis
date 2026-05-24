# Betelgeuze Harness State

- Status: active
- Mode: Deep
- Risk: R3, local artifact/productization work
- Goal: keep recursively improving the workstation-based structural delivery service until locally closable gaps are eliminated.
- Current boundary: EB/RH strict independent-product evidence remains external and is not claimed as locally closable.

## Completed In This Track

- Added workstation hardware profile, service budget, delivery package, client input validation, and workstation delivery readiness gates.
- Generated local workstation artifacts and package zip.
- Verified workstation delivery readiness passes locally.
- Kept independent commercial product readiness blocked by EB/RH only.

## Current Recursive Gap

Resolved local productization gaps:

- `build_workstation_delivery_package.py` now writes `implementation/phase1/workstation_jobs/<job_id>/`.
- The job folder contains `input_manifest.json`, `run_log.jsonl`, `output_manifest.json`, and `checksums.sha256`.
- `check_workstation_delivery_readiness.py` now includes `Job reproducibility contract`.
- Delivery package builder now verifies `manifest.json` output rows against the zip's actual bytes/SHA-256 rows.
- Restore smoke now verifies the restored `viewer.html` has a viewer shell marker.
- Delivery package now includes `DELIVERY_INDEX.md`, `REVISION_HISTORY.md`, and `data/revision_policy.json`.
- Restore smoke now verifies the delivery index marker and revision policy.
- Added `workstation-job-retention-policy.v1` with explicit-confirmation cleanup policy.
- `check_workstation_delivery_readiness.py` now includes `Job retention and cleanup policy`.
- Added a read-only `cleanup_preview` that lists stale job folders without deleting.
- Restore smoke now checks PDF header, manifest report/viewer references, and manifest claim boundary.
- Added `ACCEPTANCE_PACKET.md` with customer acceptance/rejection and engineer-review acknowledgement markers.
- Added `data/redelivery_comparison_manifest.json` to link current package/job to previous delivery history.
- Restore smoke now verifies acceptance packet markers, manifest acceptance references, and redelivery comparison policy.
- Added `DELIVERY_QA_SUMMARY.md` with customer-visible QA, included-check, and hidden/internal marker checks.
- Added `data/report_metadata.json` with report SHA-256/bytes, fallback source, manifest/revision/QA summary links, and current job id.
- Restore smoke and readiness now verify QA summary markers and report metadata cross-reference.
- Added `data/signing_manifest.json` as an unsigned offline-signing skeleton with no embedded key material/private key.
- Restore smoke and readiness now verify signing manifest schema, `unsigned_placeholder` status, signable payload, and no-key-material guarantees.
- Added `HANDOFF_DIFF_SUMMARY.md` and `data/handoff_diff_summary.json` for customer-facing redelivery package-member deltas.
- Restore smoke and readiness now verify handoff diff markers, schema, current job id, and added/removed/changed/unchanged counts.
- `DESIGN.md` now includes `deliveryHandoffDiffLight` for customer-facing redelivery diff summaries.
- Added `workstation-delivery-viewer-smoke.v1` as a restored-package customer-open browser smoke.
- `scripts/verify-workstation-delivery-viewer-smoke.mjs` extracts `project_package.zip`, serves restored `viewer.html`, verifies package checksums, opens the viewer in Chromium, and records canvas screenshot metrics.
- Current workstation delivery readiness is `PASS | gates=8/8`.
- Support bundle includes 22/22 required artifacts, including workstation delivery viewer smoke.
- Full Python test suite passes: `1465 passed`.
- Structural Insight Viewer cockpit polish advanced toward the target reference image:
  - Added `src/structure-viewer/commercial-cockpit-polish.css` as the final flagship dark cockpit layer.
  - Default MIDAS33 review now enters contour-first with engineering-unit legend values and no automatic Compare geometry pass.
  - Display-only node contour scalar context supplies mm/MPa values when raw node fields lack usable range, without mutating analysis/KPI inputs.
  - MIDAS33 review/frame camera presets now use target offsets and distance scaling for a larger stage-focused view.
  - Deformed/Compare geometry now uses muted neutral ghost styling when explicitly enabled.
  - Critical member table deduplicates repeated member rows, and the utilization heatmap renders an inactive core void.
  - Contour mode now keeps instanced frame/surface meshes visible with subdued wire overlays, improving section/body readability while staying above local FPS budget.
  - Direct and instanced line members now use type/section/utilization-informed visual radius buckets, so heavier columns/beams/braces read as structural members while preserving instancing.
  - KPI provenance labels now use customer-facing `Model estimate`, `Model quantity estimate`, `Model volume estimate`, and `Model cost estimate` wording instead of internal `proxy` labels.
  - Drawing handoff is now a first-class rail panel with revision, active callout, SVG sheet links, primary sheet, and viewer deep-link copy, while preserving the KPI -> optimization -> critical-members first-viewport flow.
  - Footer instrumentation now includes a commercial analysis timeline strip with load case, active step, previous/play/next controls, scrubber, scale, solver, convergence, and runtime.
  - Drawing handoff now includes a compact sheet preview thumbnail with active sheet name, callout tag, revision, selected member, and package status, so the rail reads like a deliverable sheet handoff instead of a plain link list.
  - The viewport now includes compact stage-native result callouts for max displacement, max drift, base shear, and the leading critical member, all derived from the same analysis cockpit model as the KPI rail and critical-member table.
  - Stage critical-member callout, critical-member table row, and viewport focus now share the same member selection. The browser smoke verifies the critical callout click selects member `11744` and mirrors `is-selected`, `aria-selected`, and `aria-pressed`.
  - The active critical member now receives a 3D viewport focus halo, leader, and projected HUD badge using the same selection identity, with `nodeData` / `p0` / `p1` fallback so normalized overlay segments can still be located.
  - Drawing handoff sheet preview is now interactive: hovering or focusing a sheet updates the active thumbnail, selected `aria-current` sheet state, disabled state, and `Open Active Sheet` link while preserving the selected member/callout identity.
  - Added `scripts/verify-structure-viewer-drawing-handoff-preview.mjs` to browser-smoke the handoff rail against the live viewer.
  - Ctrl/Cmd selection from critical-member rows and search results now preserves `member_set`, keeps all selected critical rows marked, distinguishes the primary row, and publishes the selected set through the shared selection/deep-link state.
  - The viewport selection HUD now shows selected-count, edge-pinned state, and secondary selected-member markers instead of only a single active-member badge.
  - Added `scripts/verify-structure-viewer-multi-selection-hud.mjs` to browser-smoke member-set selection, row state, badge count, edge metadata, local storage, and deep-link `member_set`.
  - Stage result callouts now use collision-aware docking across right, left, bottom-right, and bottom-left positions when the active selection HUD would overlap the result callout stack.
  - Added `scripts/verify-structure-viewer-callout-docking.mjs` to browser-smoke forced HUD/callout overlap and verify the callout stack re-docks clear.
  - Updated `DESIGN.md` to document contour-first defaults and explicit Compare/deformed ghosting.
  - Updated `implementation/phase1/structure_viewer_visual_regression_baseline.json` after intentional visual change.
  - Synced generated single-file delivery viewer packaging with the current commercial cockpit source by recursively inlining local `viewer-*.js` modules plus `design-theme.css` and `commercial-cockpit-polish.css`.
  - Regenerated `implementation/phase1/release/visualization/structural_viewer_midas33_pr_singlefile.html`, `project_package.zip`, job record, retention policy, support bundle, and readiness artifacts.
  - Customer-open package viewer smoke now reports `current_cockpit_delivery` with all 7/7 required cockpit markers and a visible nonblank restored canvas.
  - Added dense cockpit short-viewport compression for 1600x900 desktop use: compact top chrome/rails/stage controls/KPIs/charts/footer so the 3D viewport, KPI rail, critical members, four lower charts, and solver timeline remain readable in one screen.
  - Added browser coverage for dense desktop layout: topbar budget, viewport/right-rail minimums, eight KPI cards, four chart panels, critical-member rows, stage callouts, zero chart/footer overlap, and zero callout/HUD overlap.
  - The material quantity chart now reads as grouped before/after result evidence with original and optimized vertical bars, unit labels, and percent deltas for steel, concrete, and rebar.
  - The story drift over height chart now reads as original/optimized comparison evidence with muted original and teal optimized curves, grid lines, drift limit marker, peak dot, and comparison legend.
  - Lower cockpit line charts now carry compact engineering axis/tick/unit labels: story drift labels drift/height and peak optimized drift, and displacement-vs-load-step uses one shared y-scale for original/optimized curves with load-step/displacement labels.
  - KPI rail cards now read as compact commercial evidence cards with label, engineering value, trend/margin badge, reference limit or before/baseline value, provenance label, filled mini-trend, and latest-point marker; dense 1600x900 browser smoke verifies KPI overflow remains zero.
  - Critical Members rows now read as commercial engineering review rows with normalized severity, D/C ratio bar, limit marker, margin label, drift-contribution microbar, status chip, and recommended-change chip while preserving stage/table focus behavior.
  - Optimization Summary cards now read as before/after evidence receipts with source/provenance, before and after values, after-vs-before bars, signed deltas, saved amount labels, metric labels, and a details link into the lower analysis strip; dense 1600x900 browser smoke verifies Optimization Summary overflow remains zero.
  - The left stage overlay now includes a compact Stage Result Receipt beside the contour legend with render mode, scalar field, engineering range, source/provenance label, load case, step, colormap, and Compare/deformation state; dense 1600x900 browser smoke verifies receipt overflow remains zero.
  - Customer-open package smoke now requires `stage_result_receipt` as part of `current_cockpit_delivery`, raising the marker contract to 8/8.
  - Load Cases in the left stage overlay now render as compact evidence rows with case kind, selected/governing/available state, source label, and step progress bars instead of plain links; dense 1600x900 browser smoke verifies at least two rows, one active row, and zero row overflow.
  - Customer-open package smoke now requires `load_case_evidence_rows` in addition to `stage_result_receipt`, raising the `current_cockpit_delivery` marker contract to 9/9.
  - The viewport tool rail now reads like a grouped commercial 3D tool strip: render/result/camera groups, icon tools, tooltip labels, active `aria-pressed` state, and synchronized render/compare/animate/view preset state.
  - The viewport now includes a compact 3D Overlay Receipt for lateral load vectors and base support markers, with load-vector count/direction, support-marker count, active load case, source label, DOM data attributes, and `window.__STRUCTURE_VIEWER_ANALYSIS_OVERLAY_STATE__` smoke state.
  - Customer-open package smoke now requires `viewport_tool_rail` and `analysis_overlay_receipt`, raising the `current_cockpit_delivery` marker contract to 11/11.
  - The left stage overlay now starts with a compact View Controls pod: view mode, camera preset, optimized model visibility, Compare Ghost state, active result field, load/step, and deformation scale. It stays synchronized with toolbar and viewport rail state.
  - Customer-open package smoke now requires `stage_review_controls`, raising the `current_cockpit_delivery` marker contract to 12/12.
  - The Utilization Heatmap panel now reads as plan-level engineering evidence with active level chip, D/C color scale, core void, hot-zone outlines, max/average D/C, hot-cell count, critical-zone share, and governing member/story receipt.
  - Customer-open package smoke now requires `utilization_heatmap_evidence`, raising the `current_cockpit_delivery` marker contract to 13/13.
  - The Contour Scale now reads as a vertical engineering result scale with five high-to-low tick labels, explicit unit/source labels, min/max summary, and dense overflow coverage.
  - Customer-open package smoke now requires `contour_scale_evidence`, raising the `current_cockpit_delivery` marker contract to 14/14.
  - The top app bar now includes a compact commercial run-control strip with load case, step, solver/runtime receipt, Compare, Export, Report, Share, New Run, Light, and Shortcuts actions. `New Run` resets local review state, Compare/deformed overlay, timeline playback/override, isolation/selection, and review camera without implying cloud solve submission.
  - Customer-open package smoke now requires `top_run_control`, raising the `current_cockpit_delivery` marker contract to 15/15.
  - The top app bar Project area is now a real manifest-backed project/drawing selector tied to the same workspace URL contract as the left Project Browser. It exposes project, drawing, variant, and review-status data attributes, stays overflow-free in the dense 1600x900 smoke, and preserves the legacy hidden `shell-project-pill` marker for shell compatibility.
  - Customer-open package smoke now requires `top_project_selector`, raising the `current_cockpit_delivery` marker contract to 16/16.
  - The 3D Overlay Receipt now includes an in-stage visual-evidence legend with yellow vector and green support swatches, visible evidence counts, browser state, dense overflow coverage, and stronger load-arrow/support-marker visual prominence so lateral-load/support evidence reads in the viewport instead of only as text.
  - Customer-open package smoke now requires `analysis_overlay_visual_evidence`, raising the `current_cockpit_delivery` marker contract to 17/17.
  - Added compact Result Evidence receipt under the KPI cards with source-backed metric count, estimate metric count, total metric count, sample base, load-step receipt, heatmap cell count, and critical-member evidence count. This makes mixed source/estimate status visible without turning model estimates into solver-source claims.
  - Customer-open package smoke now requires `analysis_result_evidence`, raising the `current_cockpit_delivery` marker contract to 18/18.
  - Regenerated the single-file delivery viewer and `project_package.zip`; workstation delivery smoke/readiness/support all remain PASS with latest job `20260524T130037-f8616d87d2ed53b4`.
  - Sequential artifact refresh confirmed retention and job reproducibility both point to latest job `20260524T130037-f8616d87d2ed53b4`.
  - Latest workstation service budget evidence is `ready=4745ms`, `fps=26.6`; visual regression remains `PASS | cases=11/11 | mode=baseline_update`.
  - Added Materials & Members catalog coverage to the flagship viewer:
    - Direct normalizer now promotes source material grades, inferred material families, usage counts, E/Poisson/density, material colors, thickness rows, and rebar code snippets into `material_catalog_summary`, `thickness_catalog_summary`, and `rebar_material_code_summary`.
    - MIDAS33 inline release routes now hydrate missing material/member catalog metadata from the direct roundtrip artifact without replacing the existing release compare payload.
    - Right rail now exposes a compact Materials & Members panel with 6 source materials, 183 sections, 34 thickness rows, steel/concrete grade visibility, material row focus/isolate actions, and explicit missing/inferred status labelling.
    - Selection properties now show material label, ID, family, E, Poisson ratio, density, and non-source material status when available.
    - Customer-open package smoke now requires `material_member_catalog`, raising `current_cockpit_delivery` marker coverage to 20/20.
    - Regenerated the single-file delivery viewer and `project_package.zip`; workstation delivery smoke/readiness/support remain PASS with latest job `20260524T133322-f8616d87d2ed53b4`.
  - Added Material Schedule coverage to close missing material/member visibility:
    - Direct normalizer now adds `section_usage_summary` per material row and `material_section_schedule_count` to meta, linking each material grade to section ids, section labels, inferred family/shape, usage counts, member samples, and element samples.
    - The Materials & Members rail now includes a compact `Material schedule` block with material-section rows, usage counts, family mix labels, and click-to-isolate `material_section` filtering.
    - Browser smoke now verifies material schedule count, row count, steel/concrete schedule visibility, and zero schedule overflow in the dense 1600x900 cockpit.
    - Customer-open package smoke now requires `material_section_schedule`, raising `current_cockpit_delivery` marker coverage to 21/21.
    - Regenerated the single-file delivery viewer and `project_package.zip`; workstation delivery smoke/readiness/support remain PASS with latest job `20260524T134607-f8616d87d2ed53b4`.
  - Added Section Schedule coverage for reverse section-to-material/member review:
    - Direct normalizer now adds `material_usage_summary` to `section_catalog_summary` and `section_material_schedule_count` to meta, linking each section id/label/family/shape to material usage, family mix, sample member ids, and sample element ids.
    - The Materials & Members rail now includes a compact `Section schedule` block with section-material rows and click-to-isolate `section_id` filtering.
    - Browser smoke now verifies section schedule count, row count, section/material visibility, and zero section schedule overflow in the dense 1600x900 cockpit.
    - Customer-open package smoke now requires `section_member_schedule`, raising `current_cockpit_delivery` marker coverage to 22/22.
    - Regenerated the single-file delivery viewer and `project_package.zip`; workstation delivery smoke/readiness/support remain PASS with latest job `20260524T135523-f8616d87d2ed53b4`.
  - Added expanded Material/Member ontology coverage:
    - Direct normalizer now classifies concrete, structural steel, rebar, prestressing, cable, bolt/anchor, weld, FRP, timber, masonry, aluminum, stainless steel, cold-formed steel, metal deck, composite, elastomeric bearing, glass, soil/geotechnical, and rigid-link material families from source names/grades/raw tokens.
    - Section fallback inference now classifies wall, slab, column, beam, brace, cable, steel H/box/pipe/tube/angle/channel, concrete rectangular, composite, and foundation section descriptors when source `section_library` rows are sparse.
    - The Materials & Members rail now includes `Material coverage` family chips with known/unclassified counts and keeps source-status warnings visible instead of silently collapsing sparse material definitions.
    - Browser smoke now verifies material-family chip count and zero material-family overflow in the dense 1600x900 cockpit.
    - Customer-open package smoke now requires `material_family_coverage`, raising `current_cockpit_delivery` marker coverage to 23/23.
    - Regenerated the single-file delivery viewer and `project_package.zip`; workstation delivery smoke/readiness/support remain PASS with latest job `20260524T141336-f8616d87d2ed53b4`.
  - Added Material/Member ontology breadth follow-up for previously missing delivery materials:
    - Direct normalizer and viewer fallback inference now classify rail steel, rail fasteners, grout/backfill, asphalt, seismic isolators, resilient pads, dampers, spring/nonlinear links, mass/inertia, ballast, and geosynthetic/membrane families instead of sending them to `unclassified`.
    - Section fallback inference now covers retaining/diaphragm walls, pile/mat/footing foundations, wall-boundary columns, coupling beams, transfer girders, dampers, isolators, spring links, rail sections, and tunnel segment lining.
    - The Materials & Members rail now exposes `data-material-family-ontology-count` and shows supported ontology breadth separately from used material-family chips.
    - Browser smoke verifies ontology breadth >=30, and customer-open package smoke now requires `material_ontology_breadth`, raising `current_cockpit_delivery` marker coverage to 24/24.
    - Regenerated the single-file delivery viewer and `project_package.zip`; workstation delivery smoke/readiness/support remain PASS with latest job `20260524T142950-f8616d87d2ed53b4`.
  - Added Result Step Schedule coverage:
    - The KPI rail now includes `structure-viewer-result-step-schedule.v1` with active load case, step x/y, convergence, runtime, and five nearby load-step rows.
    - Clicking a schedule row updates the shared analysis timeline override and re-renders the footer timeline, top run-control, schedule active row, and load-step chart cursor from the same resolved step state.
    - Browser smoke verifies one active schedule row, at least five rows, nonempty load case/solver/convergence, chart label sync after a row click, and zero schedule overflow in the dense 1600x900 cockpit.
    - Customer-open package smoke now requires `result_step_schedule`, raising `current_cockpit_delivery` marker coverage to 25/25.
    - Regenerated the single-file delivery viewer and `project_package.zip`; workstation delivery smoke/readiness/support remain PASS with latest job `20260524T144145-f8616d87d2ed53b4`.
  - Added a second Material/Member ontology breadth expansion after missing-material review:
    - Direct normalizer and viewer fallback inference now expose 47 supported material families, adding ground improvement, waterproofing/waterstop, roofing, insulation, fireproofing, coatings, sealants/joint fillers, gypsum/board, stone/tile, facade/cladding panels, rail sleepers/ties, pot/spherical bearings, expansion joints, adhesive/resin, formwork/shoring, screed/topping, and sleeve/embedded inserts.
    - Section fallback inference now covers retaining/diaphragm/parapet walls, piers/grade beams, stairs/ramps/balconies/roof slabs, mega columns, spandrel/lintel/joist/purlin/rafter/edge beams, BRBs, trusses, outriggers, diaphragm/collector/drag-strut members, tiebacks/ground anchors, and base/gusset/splice/embed plates.
    - Browser smoke now verifies ontology breadth >=45, and customer-open package smoke still passes the 25/25 current cockpit delivery marker set.
    - Regenerated the single-file delivery viewer and `project_package.zip`; workstation delivery smoke/readiness/support remain PASS with latest job `20260524T145752-f8616d87d2ed53b4`.
  - Added Result Envelope coverage:
    - The KPI rail now includes `structure-viewer-result-envelope.v1` between Result Step Schedule and Delivery Review Receipt.
    - Envelope rows expose governing displacement, drift, base shear, utilization, and heatmap hot-zone evidence with load case, active step, source/estimate coverage, and member-scoped focus actions.
    - Browser smoke verifies the envelope is ready, contains at least four governing rows, includes member-linked rows, and remains overflow-free at dense 1600x900.
    - Customer-open package smoke now requires `result_envelope`, raising `current_cockpit_delivery` marker coverage to 26/26.
    - Regenerated the single-file delivery viewer and `project_package.zip`; workstation delivery smoke/readiness/support remain PASS with latest job `20260524T152125-f8616d87d2ed53b4`.
  - Added compact Model Overview and source adapter matrix coverage:
    - The left rail now exposes `structure-viewer-model-overview.v1` and `structure-viewer-source-adapter-matrix.v1` for model/name/nodes/elements/stories/height/units/analysis type/last run plus MIDAS/OpenSees/Abaqus source slots.
    - Dense 1600x900 browser smoke verifies the overview is ready, MIDAS is the active source for MIDAS33, all three adapter slots render, and the overview has zero overflow.
    - Renderable JSON evidence ingest reload now persists the direct model payload through local/session storage and fixes the short-model height label fallback that previously caused demo fallback after reload.
    - Customer-open package smoke now requires `model_overview`, raising `current_cockpit_delivery` marker coverage to 27/27.
    - Regenerated the delivery package artifacts; workstation delivery smoke/readiness/support remain PASS with latest job `20260524T161723-f8616d87d2ed53b4`.

## Next Recursive Candidates

1. Add detached signature verification flow after explicit key/signature material exists.
2. Add customer-facing delivery index cross-links to QA, diff, signing, and report metadata files.
3. Continue viewer fidelity toward the reference image with deeper model/result evidence richness and high-density edge-case refinements beyond the now-covered top project selector, top run-control strip, stage review controls, result evidence receipt, Result Step Schedule, Result Envelope, contour scale evidence, load-case evidence rows, utilization heatmap evidence, viewport tool rail, 3D overlay receipt with visual-evidence legend, stage result receipt, KPI evidence cards, Optimization Summary evidence receipts, Critical Members review rows, Materials & Members catalog, Material Schedule links, Section Schedule links, Material Family Coverage chips, 47-family Material Ontology Breadth receipt, lower-chart axis labeling, and 1600x900 cockpit layout.
4. Reduce remaining operator-prompt friction by keeping verification/build paths non-interactive and using saved approval prefixes for repeated browser/sandbox gates.
