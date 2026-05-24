# Work Queue

## Completed

- Promote workstation job reproducibility from flat JSON only to folderized job contract and readiness gate.
- Add delivery package manifest self-consistency checks that verify manifest rows against zip file rows.
- Add restored viewer shell marker check.
- Add customer-facing `DELIVERY_INDEX.md` and `REVISION_HISTORY.md` to the delivery package.
- Add `data/revision_policy.json` and restore/readiness checks for it.
- Add `workstation-job-retention-policy.v1` and include it in readiness/support bundle.
- Keep full Python suite green after viewer preset contract update.
- Add read-only stale job cleanup preview for `workstation_jobs/`.
- Add package restore checks for PDF magic/header and report/package manifest cross-reference.
- Add customer-facing `ACCEPTANCE_PACKET.md` for acceptance/rejection and engineer-review acknowledgement.
- Add `data/redelivery_comparison_manifest.json` linking current package/job to previous delivery history.
- Add report metadata/manifest revision cross-reference checks.
- Add a customer-facing delivery QA summary page that mirrors readiness PASS/BLOCKED.
- Add optional unsigned signing manifest skeleton for offline handoff.
- Add package-level customer handoff diff summary for redeliveries.
- Add flagship Structural Insight Viewer cockpit polish: final CSS layer, contour-first default, display-only contour scalar fallback, stage-focused MIDAS33 presets, muted Compare/deformed ghost styling, critical-member dedupe, core-void heatmap, and refreshed visual baseline.
- Improve contour-stage body readability by rendering instanced frame/surface meshes in contour mode with subdued wire overlays while keeping local browser performance green.
- Add section-aware member thickness for direct and instanced line elements while preserving instancing and visual regression coverage.
- Replace internal `proxy` KPI copy with customer-facing model estimate provenance labels.
- Add commercial drawing handoff rail panel for revision, active callout, SVG sheet links, and viewer deep-link copy.
- Upgrade footer instrumentation into a commercial analysis timeline strip with step playback controls.
- Add compact drawing sheet preview thumbnail affordance to the handoff rail.
- Add compact stage-native result callouts for max displacement, max drift, base shear, and the leading critical member.
- Link the stage critical-member callout, critical-member table row, and viewport focus selection.
- Add active critical-member viewport focus halo, leader, and projected HUD badge.
- Add active sheet-preview interaction polish to the drawing handoff rail, including hover/focus sync, `aria-current`, disabled state, and `Open Active Sheet` updates.
- Add multi-selection and edge-safe viewport HUD behavior, including Ctrl/Cmd row/search selection, `member_set` preservation, selected-count badge state, primary-vs-secondary row state, and secondary viewport markers.
- Add collision-aware stage result callout docking to keep KPI/result callouts clear of the active selection HUD.
- Add customer-open smoke log for restored `viewer.html` inside `project_package.zip`, including package checksum verification, browser open, nonblank canvas screenshot metrics, and explicit commercial-cockpit alignment warning.
- Sync generated single-file delivery viewer packaging with the latest commercial cockpit source, including recursive local viewer-module inlining, cockpit polish CSS inlining, regenerated package artifacts, and `current_cockpit_delivery` smoke alignment.
- Add dense cockpit short-viewport compression so 1600x900 desktop captures keep the top chrome compact, the 3D viewport usable, KPI rail/critical members readable, all four lower charts visible, and footer timeline non-overlapping.
- Upgrade material quantity comparison into grouped before/after result evidence with original/optimized vertical bars, unit labels, and percent deltas for steel, concrete, and rebar.
- Upgrade story drift over height into original/optimized comparison evidence with drift limit marker, peak dot, grid lines, and compact comparison legend.
- Add compact engineering axis/tick/unit labels to lower line charts and make displacement-vs-load-step compare original/optimized curves on one shared y-scale.
- Upgrade KPI rail cards into compact commercial evidence cards with trend/margin badges, reference limit/baseline labels, provenance chips, filled mini-trends, latest-point markers, and dense-layout overflow coverage.
- Upgrade Critical Members rows into commercial engineering review rows with D/C limit markers, margin labels, drift microbars, severity chips, recommended-change chips, and dense-layout coverage.
- Upgrade Optimization Summary into before/after evidence receipts with source chips, after-vs-before bars, signed deltas, saved amount labels, details link, and dense-layout overflow coverage.
- Add compact Stage Result Receipt beside the contour legend with render mode, scalar, engineering range, source/provenance, load case, step, colormap, Compare/deformation state, and delivery smoke marker coverage.
- Upgrade Load Cases into compact stage evidence rows with inferred case kind, status, source label, step progress bar, default active row fallback, dense-layout overflow coverage, and delivery smoke marker coverage.
- Upgrade the viewport tool rail into grouped render/result/camera icon tools with tooltip labels, active `aria-pressed` sync, dense overflow coverage, and delivery smoke marker coverage.
- Add a compact 3D Overlay Receipt for lateral-load arrows and base support markers, including count/direction/source/load-case state, browser smoke state, dense overflow coverage, and delivery smoke marker coverage.
- Add compact left-stage View Controls with render mode, camera preset, optimized/compare model stack, result/load-step/scale receipt, toolbar/viewport-rail sync, dense overflow coverage, and delivery smoke marker coverage.
- Upgrade the Utilization Heatmap into plan-level evidence with active level chip, D/C scale, core void, hot-zone outlines, max/average D/C, hot-cell count, critical-zone share, governing member/story receipt, dense overflow coverage, and delivery smoke marker coverage.
- Upgrade the Contour Scale into a vertical engineering result scale with five high-to-low tick labels, unit/source labels, min/max summary, dense overflow coverage, and delivery smoke marker coverage.
- Upgrade the top app bar into a compact commercial run-control strip with load/step receipt, synchronized Compare state, export/report/share actions, local New Run reset behavior, dense overflow coverage, and delivery smoke marker coverage.
- Upgrade the top app bar Project area into a manifest-backed project/drawing selector synchronized with the Project Browser workspace URL contract, with dense overflow coverage and delivery smoke marker coverage.
- Add viewport-native 3D Overlay visual evidence with yellow load-vector and green support swatches, visible count state, dense overflow coverage, and delivery smoke marker coverage.
- Add compact KPI-adjacent Result Evidence receipt with source/estimate metric coverage, node/element sample base, active load step, heatmap cells, critical-member evidence, dense overflow coverage, and delivery smoke marker coverage.
- Add Materials & Members rail catalog with source material grades, material families, usage counts, E/Poisson/density, material colors, section count, thickness rows, rebar code snippets, MIDAS33 direct-artifact hydration, dense overflow coverage, and delivery smoke marker coverage.
- Add Material Schedule links with per-material section usage, usage counts, family/shape labels, sample member/element ids, click-to-isolate `material_section` filtering, dense overflow coverage, and delivery smoke marker coverage.
- Add Section Schedule links with per-section material usage, usage counts, primary material labels, section isolate filtering, dense overflow coverage, and delivery smoke marker coverage.
- Add expanded Material Family Coverage ontology and section fallback inference for sparse material/member inputs, including visible family chips, known/unclassified counts, dense overflow coverage, and delivery smoke marker coverage.
- Add Material Ontology Breadth follow-up for commonly missed delivery materials and members, including rail steel/fasteners, grout/backfill, asphalt, isolators, pads, dampers, nonlinear links, mass, ballast, geosynthetics, retaining/diaphragm walls, mat/pile/footing foundations, coupling/transfer members, rail, and tunnel segment lining.
- Add compact Result Step Schedule evidence rows for active load step/convergence, with row-click sync to footer timeline, top run-control, and load-step chart cursor.
- Add second Material/Member ontology breadth expansion for missing delivery materials and descriptors, raising supported families to 47 and covering waterproofing, roofing, insulation, fireproofing, coatings, sealants, gypsum/board, stone/tile, facade panels, rail sleepers, pot/spherical bearings, expansion joints, adhesive/resin, formwork/shoring, screed/topping, sleeve/embed inserts, parapet/diaphragm/retaining walls, stairs/ramps/balconies, mega columns, joists/purlins/rafters, BRBs, trusses, outriggers, collectors, tiebacks, and connection plates.
- Add compact Result Envelope evidence rows for governing displacement, drift, base shear, utilization, and heatmap hot-zone status, including load case, active step, source coverage, member-scoped focus, dense overflow coverage, and delivery smoke marker coverage.
- Add compact Model Overview and source adapter matrix coverage in the left rail, including MIDAS/OpenSees/Abaqus source slots, model height/units/analysis type/last run fields, dense overflow coverage, delivery smoke marker coverage, and renderable JSON evidence reload persistence.
- Add commercial Deformation Scale control in stage View Controls with `1.0x` display scale, internal multiplier evidence, legacy slider sync, receipt sync, dense overflow coverage, and delivery smoke marker coverage.
- Add solver-verified Panel Zone / Joint Evidence in the right rail with joint geometry, rebar anchorage, 3D clash, exact/fallback validation counts, candidate member focus rows, package evidence files, dense overflow coverage, and delivery smoke marker coverage.
- Add viewport-native Panel Zone / Joint stage badge with leader, primary candidate member id, solver-verified source/clash/fallback counts, projection/docked state, click-to-focus behavior, dense overflow/collision coverage, and delivery smoke marker coverage.
- Add projected Critical Member stage hotspots with leading member D/C/status/change labels, click-to-focus selection sync, edge/collision metadata, dense overflow/collision coverage, and delivery smoke marker coverage.
- Add projected Story Level Ruler with story/height rows from the same Story Clip bands, model height/story count receipt, drift context, click-to-clip/clear behavior, dense overflow coverage, and delivery smoke marker coverage.
- Add Stage Drift Limit Bands with original/optimized drift rows, limit utilization tones, story-clip synchronization, dense overflow coverage, and delivery smoke marker coverage.

## Next

- Add detached signature verification flow after explicit key/signature material exists.
- Add customer-facing delivery index cross-links to QA, diff, signing, and report metadata files.
- Add deeper model/result evidence richness and dense model/callout edge-case refinements beyond the now-upgraded top project selector, top run-control strip, stage review controls, commercial deformation scale control, Model Overview/source adapter matrix, projected Story Level Ruler, Stage Drift Limit Bands, result evidence receipt, Result Step Schedule, Result Envelope, Panel Zone / Joint Evidence rail plus stage badge, projected Critical Member stage hotspots, contour scale evidence, load-case evidence rows, utilization heatmap evidence, viewport tool rail, 3D overlay receipt with visual-evidence legend, stage result receipt, KPI, Optimization Summary, Critical Members, Materials & Members rail, Material Schedule links, Section Schedule links, Material Family Coverage chips, and 47-family Material Ontology Breadth receipt.
- Reduce remaining operator-prompt friction by preferring non-interactive script flags and saved approval prefixes where sandbox policy allows.

## External / Not Locally Closable

- EB receipt `4/4`.
- RH closure `3/3`.
