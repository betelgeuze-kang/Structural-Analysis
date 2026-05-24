---
version: alpha
name: Structural Analysis UI Design System
description: Unified design system and viewer architecture contract for structural analysis viewers, optimization review pages, benchmark dashboards, AI optimization overlay semantics, and AI-optimized drawing review surfaces.
colors:
  primary: "#0F6A73"
  inkDark: "#08121D"
  surfaceDark: "#111C29"
  surfaceDarkSoft: "#152435"
  surfaceDarkStrong: "#0D1824"
  lineDark: "#2B3D50"
  textOnDark: "#ECF2F6"
  mutedOnDark: "#96A8BB"
  inkLight: "#1C2430"
  surfaceLight: "#FFFAF2"
  surfaceLightSoft: "#F7EFE3"
  surfaceLightStrong: "#FFFDF8"
  lineLight: "#D8CFBF"
  textOnLight: "#1C2430"
  mutedOnLight: "#5C6678"
  accentCool: "#4FB7AD"
  accentWarm: "#F4B56B"
  accentWarmLight: "#8F4A19"
  success: "#2F7D5A"
  warning: "#96580E"
  danger: "#A1492E"
typography:
  h1:
    fontFamily: "Space Grotesk, IBM Plex Sans KR, Pretendard, sans-serif"
    fontSize: 44px
    fontWeight: 700
    lineHeight: 1.02
    letterSpacing: -0.04em
  h2:
    fontFamily: "Space Grotesk, IBM Plex Sans KR, Pretendard, sans-serif"
    fontSize: 28px
    fontWeight: 700
    lineHeight: 1.08
    letterSpacing: -0.03em
  h3:
    fontFamily: "IBM Plex Sans KR, Pretendard, sans-serif"
    fontSize: 18px
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: -0.02em
  bodyMd:
    fontFamily: "IBM Plex Sans KR, Pretendard, Noto Sans KR, sans-serif"
    fontSize: 14px
    fontWeight: 400
    lineHeight: 1.6
    letterSpacing: -0.01em
  bodySm:
    fontFamily: "IBM Plex Sans KR, Pretendard, Noto Sans KR, sans-serif"
    fontSize: 12px
    fontWeight: 400
    lineHeight: 1.55
    letterSpacing: -0.01em
  labelCaps:
    fontFamily: "IBM Plex Sans KR, Pretendard, Noto Sans KR, sans-serif"
    fontSize: 11px
    fontWeight: 700
    lineHeight: 1.1
    letterSpacing: 0.12em
  metricLg:
    fontFamily: "Space Grotesk, IBM Plex Sans KR, Pretendard, sans-serif"
    fontSize: 28px
    fontWeight: 700
    lineHeight: 1.05
    letterSpacing: -0.03em
rounded:
  xs: 6px
  sm: 10px
  md: 16px
  lg: 24px
  xl: 28px
  pill: 999px
spacing:
  xs: 4px
  sm: 8px
  md: 12px
  lg: 16px
  xl: 24px
  xxl: 32px
components:
  viewerHeroDark:
    backgroundColor: "{colors.surfaceDark}"
    textColor: "{colors.textOnDark}"
    typography: "{typography.h1}"
    rounded: "{rounded.xl}"
    padding: 28px
  viewerShellDark:
    backgroundColor: "{colors.surfaceDark}"
    textColor: "{colors.textOnDark}"
    typography: "{typography.bodyMd}"
    rounded: "{rounded.lg}"
    padding: 12px
  viewerTopBarDark:
    backgroundColor: "{colors.surfaceDarkStrong}"
    textColor: "{colors.textOnDark}"
    typography: "{typography.bodySm}"
    rounded: "{rounded.md}"
    padding: 8px
    height: 44px
  viewerWorkflowTabsDark:
    backgroundColor: "{colors.surfaceDarkStrong}"
    textColor: "{colors.textOnDark}"
    typography: "{typography.bodySm}"
    rounded: "{rounded.md}"
    padding: 6px
    height: 34px
  viewerNavRailDark:
    backgroundColor: "{colors.surfaceDarkStrong}"
    textColor: "{colors.textOnDark}"
    typography: "{typography.bodySm}"
    rounded: "{rounded.lg}"
    padding: 12px
    width: 132px
  modelOverviewRailDark:
    backgroundColor: "{colors.surfaceDarkStrong}"
    textColor: "{colors.textOnDark}"
    typography: "{typography.bodySm}"
    rounded: "{rounded.sm}"
    padding: 8px
  sourceAdapterMatrixDark:
    backgroundColor: "{colors.surfaceDarkStrong}"
    textColor: "{colors.textOnDark}"
    typography: "{typography.bodySm}"
    rounded: "{rounded.sm}"
    padding: 6px
  viewerPanelDark:
    backgroundColor: "{colors.surfaceDarkSoft}"
    textColor: "{colors.textOnDark}"
    typography: "{typography.bodyMd}"
    rounded: "{rounded.lg}"
    padding: 16px
  viewerStageFrameDark:
    backgroundColor: "{colors.inkDark}"
    textColor: "{colors.textOnDark}"
    typography: "{typography.bodyMd}"
    rounded: "{rounded.lg}"
    padding: 10px
  viewerStageControlPodDark:
    backgroundColor: "{colors.surfaceDarkSoft}"
    textColor: "{colors.textOnDark}"
    typography: "{typography.bodySm}"
    rounded: "{rounded.lg}"
    padding: 12px
  deformationScaleControlDark:
    backgroundColor: "{colors.surfaceDarkStrong}"
    textColor: "{colors.textOnDark}"
    typography: "{typography.bodySm}"
    rounded: "{rounded.sm}"
    padding: 8px
  viewerStageToolRailDark:
    backgroundColor: "{colors.surfaceDarkSoft}"
    textColor: "{colors.textOnDark}"
    typography: "{typography.bodySm}"
    rounded: "{rounded.md}"
    padding: 6px
    width: 44px
  analysisStageOverlayDark:
    backgroundColor: "{colors.surfaceDarkStrong}"
    textColor: "{colors.textOnDark}"
    typography: "{typography.bodySm}"
    rounded: "{rounded.sm}"
    padding: 8px
  stageLoadSupportGlyphDark:
    backgroundColor: "{colors.surfaceDarkStrong}"
    textColor: "{colors.textOnDark}"
    typography: "{typography.bodySm}"
    rounded: "{rounded.sm}"
    padding: 4px
  analysisResultCalloutDark:
    backgroundColor: "{colors.surfaceDarkStrong}"
    textColor: "{colors.textOnDark}"
    typography: "{typography.metricLg}"
    rounded: "{rounded.sm}"
    padding: 8px
  stageCriticalHotspotDark:
    backgroundColor: "{colors.surfaceDarkStrong}"
    textColor: "{colors.textOnDark}"
    typography: "{typography.bodySm}"
    rounded: "{rounded.sm}"
    padding: 6px
  stageStoryRulerDark:
    backgroundColor: "{colors.surfaceDarkStrong}"
    textColor: "{colors.textOnDark}"
    typography: "{typography.bodySm}"
    rounded: "{rounded.sm}"
    padding: 6px
  stageDriftBandDark:
    backgroundColor: "{colors.surfaceDarkStrong}"
    textColor: "{colors.textOnDark}"
    typography: "{typography.bodySm}"
    rounded: "{rounded.sm}"
    padding: 6px
  panelZoneStageBadgeDark:
    backgroundColor: "{colors.surfaceDarkStrong}"
    textColor: "{colors.textOnDark}"
    typography: "{typography.bodySm}"
    rounded: "{rounded.sm}"
    padding: 8px
  viewerSelectionOverlayDark:
    backgroundColor: "{colors.surfaceDarkSoft}"
    textColor: "{colors.textOnDark}"
    typography: "{typography.bodySm}"
    rounded: "{rounded.lg}"
    padding: 12px
  viewerOptimizationOverlayDark:
    backgroundColor: "{colors.surfaceDarkSoft}"
    textColor: "{colors.textOnDark}"
    typography: "{typography.bodyMd}"
    rounded: "{rounded.lg}"
    padding: 14px
  viewerInsightRailDark:
    backgroundColor: "{colors.surfaceDarkSoft}"
    textColor: "{colors.textOnDark}"
    typography: "{typography.bodyMd}"
    rounded: "{rounded.lg}"
    padding: 12px
    width: 360px
  viewerInstrumentationStripDark:
    backgroundColor: "{colors.surfaceDarkStrong}"
    textColor: "{colors.textOnDark}"
    typography: "{typography.bodySm}"
    rounded: "{rounded.lg}"
    padding: 12px
    height: 48px
  viewerHandoffStripDark:
    backgroundColor: "{colors.surfaceDarkStrong}"
    textColor: "{colors.textOnDark}"
    typography: "{typography.bodySm}"
    rounded: "{rounded.lg}"
    padding: 12px
  viewerPillDark:
    backgroundColor: "{colors.surfaceDarkStrong}"
    textColor: "{colors.textOnDark}"
    typography: "{typography.bodySm}"
    rounded: "{rounded.pill}"
    padding: 8px
    height: 34px
  metricCardDark:
    backgroundColor: "{colors.surfaceDarkSoft}"
    textColor: "{colors.textOnDark}"
    typography: "{typography.metricLg}"
    rounded: "{rounded.md}"
    padding: 14px
  viewerKpiCardCompactDark:
    backgroundColor: "{colors.surfaceDark}"
    textColor: "{colors.textOnDark}"
    typography: "{typography.metricLg}"
    rounded: "{rounded.md}"
    padding: 10px
    height: 112px
  analysisCockpitKpiCardDark:
    backgroundColor: "{colors.surfaceDark}"
    textColor: "{colors.textOnDark}"
    typography: "{typography.metricLg}"
    rounded: "{rounded.md}"
    padding: 10px
    height: 88px
  analysisCockpitChartPanelDark:
    backgroundColor: "{colors.surfaceDarkStrong}"
    textColor: "{colors.textOnDark}"
    typography: "{typography.bodySm}"
    rounded: "{rounded.md}"
    padding: 12px
    height: 164px
  optimizationDeltaStripDark:
    backgroundColor: "{colors.surfaceDarkStrong}"
    textColor: "{colors.textOnDark}"
    typography: "{typography.bodySm}"
    rounded: "{rounded.sm}"
    padding: 8px
  criticalTriageDark:
    backgroundColor: "{colors.surfaceDarkStrong}"
    textColor: "{colors.textOnDark}"
    typography: "{typography.bodySm}"
    rounded: "{rounded.sm}"
    padding: 8px
  criticalMemberTableDark:
    backgroundColor: "{colors.surfaceDarkStrong}"
    textColor: "{colors.textOnDark}"
    typography: "{typography.bodySm}"
    rounded: "{rounded.sm}"
    padding: 8px
  panelZoneEvidenceDark:
    backgroundColor: "{colors.surfaceDarkStrong}"
    textColor: "{colors.textOnDark}"
    typography: "{typography.bodySm}"
    rounded: "{rounded.sm}"
    padding: 8px
  drawingHandoffPanelDark:
    backgroundColor: "{colors.surfaceDarkStrong}"
    textColor: "{colors.textOnDark}"
    typography: "{typography.bodySm}"
    rounded: "{rounded.sm}"
    padding: 8px
  analysisTimelineFooterDark:
    backgroundColor: "{colors.surfaceDarkStrong}"
    textColor: "{colors.textOnDark}"
    typography: "{typography.bodySm}"
    rounded: "{rounded.md}"
    padding: 10px
    height: 34px
  commercialCockpitPolishLayer:
    backgroundColor: "{colors.inkDark}"
    textColor: "{colors.textOnDark}"
    typography: "{typography.bodySm}"
    rounded: "{rounded.xs}"
    padding: 8px
  reviewHeroLight:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.textOnDark}"
    typography: "{typography.h1}"
    rounded: "{rounded.xl}"
    padding: 28px
  reviewPanelLight:
    backgroundColor: "{colors.surfaceLight}"
    textColor: "{colors.textOnLight}"
    typography: "{typography.bodyMd}"
    rounded: "{rounded.lg}"
    padding: 18px
  reviewPillLight:
    backgroundColor: "{colors.surfaceLightStrong}"
    textColor: "{colors.primary}"
    typography: "{typography.bodySm}"
    rounded: "{rounded.pill}"
    padding: 8px
    height: 34px
  metricCardLight:
    backgroundColor: "{colors.surfaceLightStrong}"
    textColor: "{colors.textOnLight}"
    typography: "{typography.metricLg}"
    rounded: "{rounded.md}"
    padding: 14px
  signalCard:
    backgroundColor: "{colors.surfaceLightStrong}"
    textColor: "{colors.textOnLight}"
    typography: "{typography.bodyMd}"
    rounded: "{rounded.md}"
    padding: 18px
  viewerMetaMuted:
    backgroundColor: "{colors.surfaceDarkStrong}"
    textColor: "{colors.mutedOnDark}"
    typography: "{typography.bodySm}"
    rounded: "{rounded.md}"
    padding: 10px
  reviewMetaMuted:
    backgroundColor: "{colors.surfaceLightSoft}"
    textColor: "{colors.mutedOnLight}"
    typography: "{typography.bodySm}"
    rounded: "{rounded.md}"
    padding: 10px
  viewerActionPrimary:
    backgroundColor: "{colors.accentCool}"
    textColor: "{colors.inkDark}"
    typography: "{typography.bodySm}"
    rounded: "{rounded.pill}"
    padding: 10px
    height: 36px
  viewerActionSecondary:
    backgroundColor: "{colors.accentWarm}"
    textColor: "{colors.inkDark}"
    typography: "{typography.bodySm}"
    rounded: "{rounded.pill}"
    padding: 10px
    height: 36px
  reviewAccentChip:
    backgroundColor: "{colors.surfaceLightStrong}"
    textColor: "{colors.accentWarmLight}"
    typography: "{typography.bodySm}"
    rounded: "{rounded.pill}"
    padding: 8px
    height: 34px
  reviewTableLight:
    backgroundColor: "{colors.surfaceLightSoft}"
    textColor: "{colors.inkLight}"
    typography: "{typography.bodyMd}"
    rounded: "{rounded.lg}"
    padding: 18px
  deliveryHandoffDiffLight:
    backgroundColor: "{colors.surfaceLightStrong}"
    textColor: "{colors.textOnLight}"
    typography: "{typography.bodyMd}"
    rounded: "{rounded.md}"
    padding: 16px
  ruleDividerDark:
    backgroundColor: "{colors.lineDark}"
    textColor: "{colors.textOnDark}"
    rounded: "{rounded.sm}"
    height: 1px
    width: 100%
  ruleDividerLight:
    backgroundColor: "{colors.lineLight}"
    textColor: "{colors.textOnLight}"
    rounded: "{rounded.sm}"
    height: 1px
    width: 100%
  statusSuccess:
    backgroundColor: "{colors.success}"
    textColor: "{colors.surfaceLightStrong}"
    typography: "{typography.bodySm}"
    rounded: "{rounded.pill}"
    padding: 8px
    height: 32px
  statusWarning:
    backgroundColor: "{colors.warning}"
    textColor: "{colors.surfaceLightStrong}"
    typography: "{typography.bodySm}"
    rounded: "{rounded.pill}"
    padding: 8px
    height: 32px
  statusDanger:
    backgroundColor: "{colors.danger}"
    textColor: "{colors.surfaceLightStrong}"
    typography: "{typography.bodySm}"
    rounded: "{rounded.pill}"
    padding: 8px
    height: 32px
---

## Overview

Structural Analysis UI Design System is the house style for every HTML viewer and release-facing review surface in this repository.

Treat this file as the source of truth for the viewer architecture contract, shared selection state v1, AI optimization overlay semantics, evidence payloads, and nullable or missing-data fallback, not just visual tokens.

The system must make the product look like a premium structural engineering platform rather than a generic analytics dashboard. The visual outcome should communicate:

- structural analysis credibility
- AI-assisted optimization with traceable evidence
- committee-review readiness
- bilingual durability for Korean and English labels
- enterprise delivery quality suitable for client handoff

This design system covers two linked surface families:

- Dark review surfaces for geometry-heavy tools such as 3D model viewers, clash viewers, and analysis charts
- Light review surfaces for drawing review, benchmark dashboards, committee packages, and export-oriented evidence pages

Every surface should feel like part of one product line even when the operating mode changes from immersive review to printable evidence.

Within the dark viewer family, the flagship variant is the reference command-center shell for geometry-heavy expert workflows such as structural analysis, nonlinear review, optimization comparison, and AI-optimized drawing inspection. It should feel like a high-trust structural-analysis cockpit where direct manipulation is predictable across mouse, pen, and touch: a compact app bar for search, project, status, and actions; a shallow workflow tab row; a slim navigation rail; a dominant 3D stage; an in-stage control pod; a vertical tool rail; and a dense KPI insight rail. Dark review pages such as charts, optimization history, and panel zone should inherit the same shell nouns, selection behavior, and evidence order, only with reduced chrome.

The flagship top bar should include a compact run-control group rather than loose utility buttons. Project selection must be a manifest-backed selector tied to the same workspace URL contract as the left project browser, not a static status chip. Project, run status, governing load case, step, solver/runtime receipt, Compare, Export, Report, Share, and New Run must read as one operational strip. `New Run` resets the local review state, camera preset, compare overlay, and timeline controls; it must not imply cloud solve submission or independent solver approval.

The flagship viewer's default review state should prioritize a fast contour-first result read: enter through the MIDAS33 review camera with the model filling the stage, scalar legends in engineering units, support/load/axis cues visible, and Compare/deformed overlays available as an explicit user action rather than an automatic second geometry pass. Line members should render with type- and section-aware visual radius buckets so columns, beams, braces, and heavier sections read as engineered members without claiming fabrication-accurate solid geometry. When deformed or compare geometry is enabled, it should render as a muted neutral ghost behind the active contour result so performance and result legibility stay ahead of visual drama.

Treat `index`, `charts`, `optimization_history`, and `panel_zone` as one Structural Insight Viewer suite. Use the body shell classes `command-center-shell`, `charts-command-shell`, `history-command-shell`, and `panel-inspection-shell` as the shared suite identity. The shell grammar should stay consistent across those pages: a compact suite identity in the top bar, shallow workflow tabs or nav rails, compact action/status chips next to provenance, selection feedback that stays visible in both the stage and the evidence rail, a dominant stage with a dense but subordinate insight rail, and mobile overflow that collapses to one column around `1080px` and finishes stacking controls by `720px`.

Selection state must also be portable: member, story, grid, and empty selections should travel as copyable deep links from one canonical `{kind, id, label, provenance}` state so a review can be handed off with the same identity, provenance, and context. Outbound/copy/share URLs must serialize only canonical selection params; legacy `member`, `story`, and `grid` params are inbound compatibility only. Canonical restore should win first, then remove stale or conflicting legacy/hash params so the resolved URL stays canonical. If member-story context is needed, keep it in the canonical context param only and do not mix it with legacy `story`. URL, copied deep link, restore, viewport highlight, selection inspector, selected table row, overlay, diff/export handoff, export handoff, and archive handoff must all resolve to that same canonical state. Generated summary/export metadata must preserve the active selection contract version and diff-focus contract version so downstream handoffs remain traceable. Member selections may focus linked raw/source-output diff rows, but story, grid, and empty selections must clear stale member-level diff focus in an audit-visible way so the evidence rail never implies that a non-member aggregate still owns a previous member's diff. `p0` and `p1` are the identity-bearing endpoints for every 3D segment, and they must remain the geometry provenance for viewport extent, axis references, selection focus, story aggregates, and export handoff. A literal `[0,0,0]` point must stay distinct from a fallback-generated `[0,0,0]`; provenance must distinguish the real origin from a safe fallback, and fallback coordinates may remain only for payload shape compatibility, not as canonical geometry. Generated payloads, summary/export metadata, and archive handoff must carry endpoint-specific `coordinate_valid`, `coordinate_status`, `coordinate_fallback_provenance`, and `coordinate_fallback_diagnostics` so invalid, missing, `NaN`, or `inf` coordinates can render safely without losing explicit state in the inspector, export bundle, or review handoff, and invalid row preview/details stay traceable in reviewer handoff. When no valid coordinate row exists, the payload must surface an explicit `no_valid_geometry` state rather than turning fallback `[0,0,0]` into phantom origin extent, axis refs, or story refs. The Selection Inspector is not a plain property table; it is the evidence panel that compresses the selected entity's AI-optimized judgment, D/C ratio, cost delta, constructability, selection gate, diff/export handoff, and explicit empty-data labels into the same shareable review state, while keeping the selection and diff-focus contract versions visible in generated summary/export metadata. The AI Optimization Overlay Mode and the Selection Inspector are paired views of that same state: the overlay annotates the stage, while the inspector explains the evidence on the rail. Copy success, copy failure, and empty-selection feedback should read as enterprise workflow status, not transient UI noise.

The AI Optimization Overlay Mode is a semantic analysis layer, not a color theme. It must keep the same meaning across legend, selected state, inspector evidence, and review handoff so the viewport, inspector, and export notes all describe the same member, story, or grid in the same terms. `Member type` is identity metadata, `D/C ratio` and `Cost delta` are quantitative comparison signals, and `Constructability` is a feasibility verdict; those meanings should stay stable across the shared review state.

## Colors

Use dark surfaces as an instrument room, not as a gaming interface. The dark family should feel controlled, technical, calm, and premium enterprise. Teal is the primary signal color, and warm mineral brass is the secondary highlight.

Use light surfaces as a formal review desk. They should feel deliberate, not washed out, and should read like premium technical documentation rather than consumer SaaS.

Color rules:

- Teal communicates active review state, linked navigation, and the currently controlled overlay mode
- In command-center shells, teal should mark the active route, selected stage tools, and ready-to-run states, while warm brass should stay reserved for thresholds, ratios, deltas, and bounded cautions
- In command-center shells, the tone should read like a structural-analysis operations desk rather than a consumer dashboard
- Warm brass communicates secondary emphasis, thresholds, quantitative deltas, and bounded warnings
- Success communicates feasible, passed, or ready-for-handoff states
- Warning communicates bounded risk, incomplete evidence, or attention-required states
- Danger communicates constraint violations, failed validation, or unsafe conditions
- AI Optimization Overlay Mode must reuse teal and brass for meaning in the legend, selected state, inspector, and review handoff; do not introduce a second palette for the same semantics
- Danger, warning, and success colors must remain readable but should never take over the full page chrome
- Purple should not be used as a default brand accent in new viewer work
- Light-mode pages should look intentionally designed, not like a fallback after dark mode

## Typography

Typography should signal technical authority with editorial restraint.

- `Space Grotesk` is reserved for page titles, hero statements, and high-value numeric callouts
- `IBM Plex Sans KR` is the default UI typeface for controls, metadata, tables, and dense review copy
- `Pretendard` and `Noto Sans KR` remain Korean-safe fallbacks

Type usage rules:

- Titles should be compact and decisive, not soft or decorative
- In command-center shells, `Space Grotesk` belongs in the app title, stage headings, and KPI numerics, while app bar controls, workflow tabs, rails, properties, and tables stay in `IBM Plex Sans KR`
- Metadata labels should behave like engineering annotations
- Long provenance or artifact strings should wrap cleanly without collapsing hierarchy
- HUD labels, bottom-sheet titles, and selection microcopy should stay compact, label-first, and abbreviation-safe; keep explanations in nearby evidence copy rather than inside the viewport chrome
- Numbers should be visually prominent in metric cards and summary strips
- Do not introduce serif or default browser typography on new or refreshed product surfaces

## Layout

Layout must support review flow before visual novelty.

Preferred page rhythm:

1. Entry block or hero with page intent
2. Current status or provenance strip
3. Quick workflow controls or navigation pills
4. Core evidence panels, charts, tables, or 3D viewport
5. Follow-up review links and export actions

For the dark viewer command-center shell, the preferred desktop structure is:

1. A compact global app bar for suite identity, project and search context, status, and primary actions
2. A shallow workflow tab row for model, analysis, optimization, materials, results, and drawing contexts
3. A slim left navigation rail for mode switching, imported-source context, and fast workflow movement
4. A dominant central 3D stage for the model, with an in-stage control pod and a vertical tool rail
5. A dense right insight rail for compact KPIs, optimization summaries, the selection inspector evidence card, properties, recommendations, and review cards
6. A lower evidence band or footer instrumentation strip for solver state, step controls, trend charts, units, and comparison context

Layout rules:

- The flagship shell should read as a premium enterprise structural-analysis console, with compact chrome and dense evidence rails
- The workflow tab row should stay compact and shallow so it reads as workflow context, not primary navigation
- The 3D viewport is the hero on geometry-heavy pages, and side panels should frame it rather than compete with it
- The top app bar should stay compact and global so the 3D stage keeps most of the vertical attention
- Desktop provenance cards, suite-route context, and low-priority chips should fold out of the first viewport when they compete with the model stage; the workflow tabs and project/status controls are the visible chrome budget
- Command-center shell pages should omit `viewerHeroDark` by default and use `viewerShellDark` with `viewerTopBarDark` and `viewerWorkflowTabsDark` as the entry unless a separate overview block is essential
- The left side should feel like a slim navigation rail first, with stronger route hierarchy than a generic control column
- The left rail's imported-source and model-info block should behave like a compact commercial model overview: expose `structure-viewer-source-adapter-matrix.v1`, show current source adapter state for MIDAS/OpenSees/Abaqus without overclaiming unsupported evidence, and surface model name, nodes, elements, stories, height, units, analysis type, last run, review IDs, and source in a dense overflow-free grid
- The in-stage control pod and vertical tool rail should stay inside or immediately adjacent to the stage frame, not expand into equal-weight sidebars
- The right side should separate fast KPI scanning at the top from optimization summaries, drawing handoff, critical member rankings, deeper properties, selection evidence cards, and insight cards below
- Toolbars around the stage should have clear action hierarchy: one teal primary action, warm brass only for bounded comparison or caution emphasis, and dark pills for quiet utilities
- Mouse, pen, and touch should share the same direct-manipulation grammar: tap or click to select, drag to orbit or pan, pinch to zoom, and explicit buttons for reset, fit, isolate, and compare when a gesture would be ambiguous
- The viewport chrome should stay thin and overlap-free, with the axis compass, selection badges, and interaction ribbon anchored inside the stage frame rather than floating as page-level decoration
- Default analysis-stage overlays should make result state visible on the geometry itself: lateral-load arrows, support markers, projected load/support glyphs, active contour cues, stage result callouts with `structure-viewer-stage-result-callouts.v2` evidence, projected critical-member hotspots, solver-verified panel-zone/joint badges, section-aware member thickness, optional neutral deformed ghosting, primary and secondary selection halos, edge-safe selection HUD badges, and collision-aware callout docking belong in the viewport and should never be presented only as sidebar text
- The 1600x900 command-center shell must maintain a dense stage-primary dominance budget: the central 3D canvas should be at least roughly three quarters of the stage-frame width after the in-stage control pod and tool rail are accounted for, so the structure remains the visual protagonist rather than a small preview between sidebars.
- Stage overlays must obey a dense model-protagonist occlusion budget in the 1600x900 command-center viewport: result callouts, drift bands, critical hotspots, panel-zone badges, story rulers, receipts, and selection HUDs may remain visible, but their combined central-viewport footprint should stay bounded so orbit/pan and visual inspection still read the structure first.
- Lateral-load arrows and support markers need a compact viewport-native 3D Overlay Receipt that reports load-vector count/direction, support-marker count, active load case, and overlay source/provenance. It should include an in-stage visual-evidence legend with yellow vector and green support swatches, sit near the axis compass without covering the model, publish the same counts to browser state for smoke checks, and never replace the actual 3D arrows or base markers. Projected load/support glyphs may amplify those same 3D objects for dense review captures, but they must be explicitly tied to the same overlay counts and source state.
- The viewport tool rail should behave like a compact commercial 3D tool strip: group render modes, result overlays, and camera presets into icon buttons with stable dimensions, accessible labels, hover/focus tooltips, active `aria-pressed` state, and no text overflow. It should mirror the top stage controls rather than becoming a separate command system.
- The left stage overlay should start with a compact View Controls pod when the page is geometry-heavy: view mode, camera preset, optimized-model visibility, Compare ghost state, active result field, load/step, and deformation scale should be visible beside the model and synchronized with the top toolbar and viewport tool rail. Deformation scale should use commercial display units such as `1.0x` while preserving the internal render multiplier as machine-readable evidence.
- The left stage overlay should carry a compact Result Receipt beside the contour legend: active render mode, scalar field, engineering range, source/provenance label, load case, active step, colormap, and Compare/deformation state must be readable without opening sidebars or reports
- Contour legends in the left stage overlay should read like engineering result scales: use a vertical color bar with at least five high-to-low tick labels, explicit unit/source labels, min/max summary, and no overflow in the dense 1600x900 cockpit. The result/legend section has first-stage-viewport priority: it appears immediately after View Controls and before Load Cases so the active scalar scale is visible beside the model without scrolling.
- Load cases in the left stage overlay should read as compact evidence rows rather than plain links: each row should show the case label, inferred case kind, selected/governing/available state, source label, and step progress bar so the stage, receipt, and footer timeline all explain the same active analysis context
- Short desktop viewports around 900px tall should use a dense cockpit compression mode: keep the top chrome, rails, stage controls, chart strip, and timeline compact enough that the 3D viewport, KPI rail, critical member table, four lower charts, and footer timeline are all readable in one screen without horizontal overflow or chart/footer overlap
- Story drift over height charts should show original versus optimized response curves plus the drift limit in the same compact panel, with muted/dashed original lines and teal optimized lines so the chart reads as comparative engineering evidence rather than a decorative sparkline
- Lower cockpit line charts should use shared engineering scales for comparison series and carry compact axis/tick labels such as drift percent, height, load step, displacement units, peak tags, and active-step markers; never normalize comparison lines independently when the purpose is before/after engineering comparison
- Material quantity comparison charts in the cockpit should read as grouped before/after result evidence: original and optimized vertical bars, visible unit values, and explicit percent deltas for steel, concrete, and rebar rather than abstract progress bars
- Materials & Members rail catalog should expose source material grades, inferred material families, material-family ontology breadth, element usage counts, elastic modulus, Poisson ratio, density, material-section usage schedule rows, section-material usage schedule rows, section-family coverage, slab/wall thickness rows, and rebar code snippets. Concrete, structural steel, rail steel, rebar, prestressing, cable, bolt/anchor, weld, FRP, formwork/shoring, timber, screed/topping, masonry, ground improvement, grout/backfill, waterproofing/waterstop, roofing, asphalt, insulation, fireproofing, coating/corrosion protection, sealant/joint filler, gypsum/board, stone/tile, aluminum, stainless steel, cold-formed steel, metal deck, composite, facade/cladding panels, sleeve/embedded inserts, rail fasteners, rail sleepers/ties, bearing, pot/spherical bearing, expansion joints, resilient pads, seismic isolators, dampers, spring/nonlinear links, lumped mass, glass, ballast, soil/geotechnical, geosynthetics/membranes, adhesive/resin, and rigid-link families should resolve to explicit families when source labels carry enough evidence. Section/member descriptors should also recognize retaining/diaphragm/parapet walls, pile/mat/grade-beam/pier foundations, stairs/ramps/balconies/roof slabs, mega columns, spandrel/lintel/joist/purlin/rafter/edge beams, BRB braces, trusses, outriggers, diaphragm/collector/drag-strut members, strut/tie/tieback anchors, and base/gusset/splice/embed plates. Missing material definitions must be labelled as `missing_material_definition` or `element_inferred`; they must not silently collapse into `0`, blank material, or only section names.
- Utilization heatmap panels should read as plan-level engineering evidence rather than decorative colored grids: include the active level chip, D/C color scale, hot-zone outlines, max/average D/C, hot-cell count, critical-zone share, governing member/story, and source/load-case receipt without overflowing the 1600x900 cockpit
- KPI cards in the insight rail should be compact evidence cards, not headline tiles: each card should compress full metric label, full engineering value, separate unit token, trend or margin badge, reference limit/baseline, provenance label, and a filled mini-trend with latest-point marker without causing overflow in the 1600x900 cockpit. Metric labels must remain readable as one or two compact lines rather than degrading to `MAX DISP...`, `INTERST...`, or `ESTIMATE...`. The core value must never render as a visual ellipsis such as `13...`, `1...`, or `24...`; if space is tight, the evidence/trend badges yield before the label or value does.
- KPI cards should be followed by a compact result-evidence receipt that reports source-backed metric count, model-estimate count, node/element sample base, active load step, and heatmap/critical evidence counts. This receipt must make mixed source/estimate status visible without turning engineering estimates into solver-source claims.
- Optimization Summary cards should read as before/after evidence receipts: each card must expose the metric label, source/provenance chip, before and after engineering values, after-vs-before bar, signed delta, saved amount, and a details link into the lower analysis strip while staying overflow-free in the 1600x900 cockpit
- Critical member ranking rows should read like engineering review rows: ID/story/type, D/C ratio with limit marker, drift-contribution microbar, severity status chip, and recommended-change chip must stay scan-safe in the dense 1600x900 cockpit while preserving the same focus behavior as stage callouts
- Selection feedback should be persistent and mirrored: the shared selection state API should be the single source of truth for member, member-set, grid, story, and empty selection, and the active entity should keep the same identity in the viewport, selection inspector, provenance row, selected table rows, URL/share state, diff/export handoff, archive handoff, and deep-link target; outbound copy/share URLs should emit canonical selection params only, legacy `member`, `story`, and `grid` remain inbound compatibility only, and generated summary/export metadata should retain the active selection contract version and diff-focus contract version alongside that canonical state
- Share/copy URL generation should serialize only canonical selection params, keep legacy `member`, `story`, and `grid` for inbound compatibility only, and let canonical restore win before stale or conflicting legacy/hash params are removed deterministically; if member-story context is needed, keep it in the canonical context param only rather than mixing it with legacy `story`
- Drawing handoff should be a first-class rail card, not only a report-export detail: expose `structure-viewer-drawing-handoff-panel.v2`, show revision, active callout, member identity, active sheet receipt, copy-ready viewer deep-link state, an active sheet preview thumbnail, SVG sheet links, primary sheet, `Open Active Sheet`, and viewer deep-link copy in one compact component tied to the same selection state as the viewport and report. Hover or keyboard focus on any sheet link should update the active preview, selected sheet state, handoff receipt, and open action together.
- The selection inspector should behave as a review evidence card, not a plain property table; it should compress AI-optimized reasoning, D/C ratio, cost delta, constructability, selection gate, diff/export handoff, and share-link status into a compact stack
- Shared selection is accepted only when canonical deep links can be copied and restored after reload without losing object identity, label, or provenance, and when stale or conflicting legacy member/story/grid or hash parameters do not survive the restore path
- The AI Optimization Overlay Mode must ride on the same copy review link and shareable review state contract as the selection system; it may summarize the selected member's optimization status, but it must not create a second share URL or restore path
- The optimization legend and inspector must keep one meaning system across `Member type`, `D/C ratio`, `Cost delta`, and `Constructability`: member type is identity, D/C ratio and cost delta are brass-toned quantitative comparisons, and constructability is a feasibility verdict that may resolve to success, warning, or danger
- Missing optimization or linkage data must fall back to explicit muted labels such as `No data`, `N/A`, `Unknown`, or `not linked`, and those fallbacks should remain readable, subordinate, and accessible instead of masquerading as a result or a zero. Derived quantities that are usable but not source-authored should use customer-facing provenance labels such as `Model estimate`, `Model quantity estimate`, `Model volume estimate`, or `Model cost estimate` rather than internal `proxy` wording.
- Copy success, copy failure, and no-selection states must be announced through an `aria-live` region or equivalent live channel, with the visible handoff strip mirroring the same state
- Engineering evidence should stay dense but structured, with IDs, units, member names, load cases, deltas, critical-member ratios, chart snapshots, and solver state compacted into rows, chips, and cards instead of long prose
- Result Step Schedule should sit near the KPI evidence in the commercial cockpit and show active load case, step x/y, convergence, runtime, and five nearby load-step rows. Row selection must sync with the footer timeline and load-step chart so the right rail, bottom controls, and chart cursor all describe the same active step.
- Result Envelope should sit between the step schedule and delivery receipt so KPI values are not orphaned numbers: each row should name the metric, engineering value, governing step/story/member/case, source/provenance label, and review detail, with member-scoped rows focusing the same critical member identity as the table and viewport.
- Optimization Delta Strip should sit in the first KPI rail viewport, before Critical Triage, so before/after steel, concrete, material cost, and CO2 deltas are visible without scrolling. It should expose `structure-viewer-optimization-delta-strip.v1`, four compact rows/tiles, before/after labels, reduction count, saved value, source label, and mini before/after bars while reusing the same `optimizationRows` as the full Optimization Summary section.
- Critical Triage should keep top governing members visible in the first KPI rail viewport instead of burying them below secondary evidence panels: it should expose `structure-viewer-critical-triage.v1`, top four D/C-governed rows, severity count, D/C limit marker, drift contribution, status, recommended action, and the same click-to-focus/Ctrl-click member-set behavior as the full Critical Members table.
- Panel Zone / Joint Evidence should sit next to the result-envelope/delivery receipt band in the commercial cockpit when solver-verified handoff evidence exists. It must show joint-geometry, rebar-anchorage, 3D clash, exact/fallback validation counts, candidate member rows, source path, validation boundary, and member-focus actions without turning constructability candidates into autonomous approval.
- The primary panel-zone candidate should also project into the 3D stage as a compact `panelZoneStageBadgeDark` badge with a leader, member id, source count, clash count, fallback count, and solver-verified boundary. It should focus the same member as the rail row, edge-pin instead of disappearing when the anchor projects outside the viewport, and publish machine-readable `structure-viewer-panel-zone-stage-badge.v1` state for smoke checks.
- Accessibility should be built into the shell: keyboard parity for every important action, visible focus states, sufficient touch targets, concise label text, selected table rows that reflect state with `aria-selected`, no reliance on color alone for selection or status, and accessible names for legend rows, selection inspector fields, and optimization overlay chips
- Light review pages should privilege reading order, comparison, and decision support
- Dense engineering pages should feel information-rich but never noisy
- Repeated strips such as provenance rows, status pills, quick stats, and route context banners must use shared primitives rather than page-local redesigns
- Footer and lower-band status areas may remain dense, but they should use `viewerInstrumentationStripDark` so they read as instrumentation strips rather than a second header
- Mobile collapse should preserve the same review order rather than becoming a different product experience
- For `optimized_drawing_review.html`, the mobile layout must be viewport-first: the 3D workspace leads the reading order, selected-member details collapse into a bottom sheet or compact overlay, supporting tables and cards restack into narrow evidence blocks, HUD labels stay short and explicit, gesture affordances must remain obvious enough for first-time touch use, and the page must not create horizontal overflow

## Elevation & Depth

Depth should support hierarchy, not decoration.

- Dark surfaces may use layered gradients, soft glow accents, and restrained glass-like framing
- In the command-center shell, the stage frame should be the deepest surface, the insight rail should sit one tonal step lighter, and KPI cards should separate as compact evidence cards through contrast and crisp grouping rather than theatrical glow
- Light surfaces may use paper-like tonal layering with thin borders and modest shadows
- Strong shadows are allowed only where they improve grouping of important review units
- Decorative blur or glow should never reduce chart readability, table clarity, or fine engineering labels

## Shapes

Shapes should feel machined and deliberate.

- Panels and cards use rounded rectangles with controlled radii
- Top bars, nav rails, stage frames, and insight cards should share the same deliberate radius family so the shell feels machined end to end
- Buttons and pills should feel precise and premium, not playful
- Metric cards should look compact and authoritative
- Table shells, chart frames, and embedded sheet viewers should share the same family of corner radii and panel framing

Avoid mixing sharp industrial corners with overly soft consumer cards on the same page.

## Components

The following components define the cross-product vocabulary and the viewer architecture contract. Shell-specific dark tokens are semantic layout primitives built from the shared `viewerPanelDark` and `metricCardDark` language; use them when a persistent shell role needs stable mapping for the app bar, workflow tabs, rails, stage controls, or AI optimization overlays rather than as generic replacements for every dark card. Precision viewport chrome should also resolve through this semantic token set so stage frames, legend chips, tool docks, selection inspector evidence cards, selected-state overlays, and interaction ribbons stay tokenized instead of ad hoc. Segment geometry should keep `p0` / `p1` as the canonical identity; coordinate validity, status, `coordinate_fallback_provenance`, and `coordinate_fallback_diagnostics` must travel with each endpoint, fallback coordinates may exist only for payload shape compatibility, and a real `[0,0,0]` must remain distinct from a fallback-generated `[0,0,0]`.

Shared selection identity must stay stable across URL, copied deep links, restore, viewport highlight, selection inspector, selected table row, overlay, diff/export handoff, export handoff, and archive handoff, all driven by the same canonical `{kind, id, label, provenance}` selection record. Outbound share links should be canonical-only, legacy `member`, `story`, and `grid` should remain inbound compatibility only, and restore should prefer canonical params before scrubbing stale legacy/hash params. Generated summary/export metadata must serialize the selection contract version and diff-focus contract version next to that record so the handoff trail can be audited after export. Diff focus is member-scoped: selecting a member can focus related raw/source-output diff rows, while selecting a story, grid bubble, or empty stage must clear previous member diff classes and visible query state in an audit-visible way.

- `viewerShellDark` for the overall dark application shell that carries permanent chrome around a geometry-heavy stage
- `viewerTopBarDark` for compact global app bars carrying suite identity, project and model context, search, export or compare actions, and status badges
- `viewerWorkflowTabsDark` for the shallow workflow tab row that switches between model, analysis, optimization, materials, results, and drawing contexts
- `viewerNavRailDark` for slim left-side navigation and operations rails with persistent workflow hierarchy
- `viewerHeroDark` and `reviewHeroLight` for page entry blocks
- `viewerStageFrameDark` for the dominant central stage zone inside `viewerShellDark`, including primary 3D viewport framing, stage-adjacent legends, direct-manipulation tool docks, selection halos, support markers, lateral-load arrows, overlay receipts, and touch-safe interaction ribbons
- `analysisStageOverlayDark`, `stageLoadSupportGlyphDark`, `analysisResultCalloutDark`, `stageStoryRulerDark`, `stageDriftBandDark`, `stageCriticalHotspotDark`, and `panelZoneStageBadgeDark` for compact stage-native result overlays such as load arrows, base supports, projected load/support glyphs, contour hints, projected story/height rulers, story drift limit bands, max displacement, drift, base shear, critical-member tags, projected critical-member hotspots, solver-verified panel-zone/joint badges, 3D Overlay Receipt, primary selected-member focus halos, secondary member-set markers, edge-pinned projected HUD badges, collision-aware result-callout docking, and deformed-shape affordances that make the 3D model read as an analysis result, not a neutral wireframe; focusable callouts may target members or story clips, but they must stay small enough to avoid stealing normal orbit and pan interaction from the model. Stage result callouts must expose full label, full value, source type, active load case, active step, and member-focus attributes so a customer-open package can audit the same evidence shown in the KPI rail.
- `viewerSelectionOverlayDark` for the compact selected-member, story, or grid overlay that renders the canonical selection record, shows active identity, mirrors shareable review state and copy-link feedback without obscuring the geometry, and keeps story evidence counts split into renderable, total, and invalid-excluded segments so the overlay reads like audit-visible engineering status rather than a warning chip
- `viewerSelectionInspectorDark` for the compact right-rail evidence card that reads the same canonical selection record and explains the selected member, story, or grid with AI-optimized judgment, D/C ratio, cost delta, constructability, selection gate, diff/export handoff, explicit empty-data labels such as `null`, `No data`, `N/A`, or `not linked`, and coordinate diagnostics for `p0` / `p1`, including `coordinate_valid`, `coordinate_status`, `coordinate_fallback_provenance`, and `coordinate_fallback_diagnostics` when the renderer had to use a safe fallback; its selection handoff copy should stay canonical and explicit, and `no_valid_geometry` should read as an audit-visible engineering state rather than an error banner
- `viewerOptimizationOverlayDark` for the semantic AI Optimization Overlay Mode that layers legend, selected-state emphasis, inspector cues, and review handoff over the stage while keeping the same shareable review state, identity key, and evidence payload contract
- `viewerStageControlPodDark` for the compact in-stage control pod that holds render-mode, compare, animation, camera, fit, and reset actions
- `viewerStageToolRailDark` for the vertical tool rail or secondary tool dock that carries selection, isolate, clip, measure, and review-handoff utility actions without competing with the stage
- `viewerPanelDark` and `reviewPanelLight` for shared primary evidence containers outside persistent shell roles
- `viewerInsightRailDark` for the persistent right-side shell rail, one tonal step lighter than the stage and reserved for KPI, summary, properties, selection inspector evidence cards, recommendation stacks, AI optimization inspector cards, and compact evidence density
- `viewerInstrumentationStripDark` for lower evidence bands and footer instrumentation strips carrying solver state, units, step controls, and run context
- `viewerHandoffStripDark` for enterprise review handoff copy, shared deep links, recipient context, optimization-state summaries, generated summary/export/archive metadata, package freshness and membership receipt for `project_package.zip` / `project_registry.json`, artifact href validation, sha256/bytes, selection contract version markers, diff-focus contract version markers, and copy success, copy failure, or empty-selection messaging; it should mirror the same selected identity as URL, restore, inspector, overlay, diff state, and archive handoff, keep canonical selection handoff wording explicit, and when representative-member fields such as `ai_reason`, `review_handoff_summary`, `source_output_diff_focus`, or `linked_diff_row_count` are empty, present an evidence completeness receipt with audit-visible labels like `No data`, `not linked`, `missing_evidence_fields`, or `partial evidence` instead of blank cells, hidden rows, or zeros; any copied link it emits should stay canonical-only even when it is normalizing legacy inbound links
- `viewerPillDark` and `reviewPillLight` for state summaries, route tokens, legend chips, compact utilities, deep-link chips, and low-emphasis toolbar actions
- `metricCardDark` and `metricCardLight` for headline KPIs and bounded numeric evidence
- `viewerKpiCardCompactDark` for compact insight-rail KPI cards with short trend context; treat it as a denser semantic subvariant of `metricCardDark` that sits on the rail as separated evidence cards rather than shell slabs
- `modelOverviewRailDark`, `sourceAdapterMatrixDark`, `deformationScaleControlDark`, `analysisCockpitKpiCardDark`, `analysisCockpitChartPanelDark`, `optimizationDeltaStripDark`, `resultStepScheduleDark`, `resultEnvelopeDark`, `criticalTriageDark`, `panelZoneEvidenceDark`, `panelZoneStageBadgeDark`, `stageStoryRulerDark`, `stageDriftBandDark`, `stageCriticalHotspotDark`, `criticalMemberTableDark`, `materialMemberCatalogDark`, `drawingHandoffPanelDark`, and `analysisTimelineFooterDark` for the flagship viewer's cockpit layer: imported-source adapter state, dense model info, stage-local deformation scale, eight result/quantity KPI cards, first-viewport before/after optimization delta strip, before/after optimization summary cards, source material/section/thickness catalog rows, material-family coverage chips, material ontology breadth receipt, material-section and section-material schedule rows with focus/isolate affordance, compact result-step schedule rows with active-step receipt, governing result-envelope rows for displacement, drift, base shear, utilization, plan hot zones, a first-viewport critical-triage snapshot, story/height levels projected into the 3D stage, governing story drift bands with limit markers projected into the 3D stage, top critical members projected into the stage, and solver-verified panel-zone/joint evidence mirrored into the stage, drawing revision/callout/deep-link handoff with a compact active sheet preview thumbnail, focus-linked sheet actions, top utilization member rows, compact trend/heatmap panels, and footer solver timeline context that must remain linked to the current model artifact rather than marketing copy. The footer timeline should expose `structure-viewer-analysis-timeline-footer.v1`, load case, step count, previous/play/next controls, a scrubber, nearby step ticks, scale, solver, convergence, and runtime in one compact row. Estimate-derived KPI values must be labeled as model estimates without exposing internal proxy language.
- `signalCard` for small review summaries that must read clearly in either light-oriented surfaces or export workflows
- `deliveryHandoffDiffLight` for customer-facing redelivery comparison summaries that show added, removed, changed, and unchanged package members with clear review guidance, no hidden internal paths, and explicit initial-delivery/no-previous-delivery states
- `viewerMetaMuted` and `reviewMetaMuted` for provenance strips, secondary labels, route context details, review handoff copy, compact accessible helper text, and explicit empty-data fallback such as `null`, `No data`, `N/A`, or `not linked`
- `viewerActionPrimary`, `viewerActionSecondary`, and `reviewAccentChip` for bounded emphasis without inventing new accent logic, especially brass-toned optimization deltas and caution markers
- `reviewTableLight`, `ruleDividerDark`, and `ruleDividerLight` for tables, section separators, and export-friendly evidence framing
- `statusSuccess`, `statusWarning`, and `statusDanger` for top-bar readiness badges, solver state, and explicit pass, caution, and failure states

### Implementation Mapping

- `DESIGN.md` is the source of truth for tokens, shared selection state, AI optimization overlay semantics, evidence payload shape, coordinate fallback provenance/diagnostics, and nullable or missing-data fallback
- `src/structure-viewer/design-theme.css` is the shared token bridge for `body.structural-surface`
- `src/structure-viewer/commercial-cockpit-polish.css` is the final flagship cockpit layer loaded after `design-theme.css`; use it only for commercial-tool fidelity refinements such as flatter chrome, denser rail telemetry, stage-dominant viewport framing, contour-first review defaults, section-aware member thickness support, explicit Compare/deformed ghosting, and target-image-specific cockpit compression
- `implementation/phase1/ui_design_tokens.py` is the shared token bridge for `body.signal-desk-dark` and `body.signal-desk-light`
- Generated HTML under `implementation/phase1/release/visualization` must change through the generator, its contract test, and the regeneration path; do not patch release artifacts directly
- `scripts/verify-workstation-delivery-viewer-smoke.mjs` is the customer-open package viewer smoke for `project_package.zip`; it verifies that restored `viewer.html` opens with a visible nonblank canvas, and it must require `commercial_cockpit_alignment.status=current_cockpit_delivery` so a legacy single-file delivery viewer cannot be mistaken for the current source cockpit
- Future refactors should split in this order: data adapter -> normalized viewer model -> shared state contract -> tokenized shell/view components -> singlefile/release packaging -> browser QA
- New HTML generators should map to one of these families instead of inventing a new palette, font stack, or card language

### Surface Mapping

- `src/structure-viewer/index.html` is the flagship dark Structural Insight Viewer shell and should read as a compact enterprise FE-analysis application shell rather than a loose collection of panels: compact app bar, workflow tab row, slim navigation rail, dominant 3D stage, in-stage control pod, vertical tool rail, dense analysis cockpit KPI insight rail, optimization summary, critical member table, lower chart strip, and lower instrumentation strip; it must preserve the same member, story, grid, and empty-state identity across URL, share, restore, inspector, overlay, diff/export handoff, export handoff, and archive handoff, with outbound copy/share URLs using canonical params only, legacy `member`, `story`, and `grid` remaining inbound compatibility only, and member-story context staying in the canonical context param instead of being mixed with legacy `story`; it must keep `p0` / `p1` as the canonical geometry identity so viewport extent, axis refs, selection focus, story aggregates, and export/archive handoff all resolve from the same segment record; generated summary/export metadata must retain the active selection contract version and diff-focus contract version
- `src/structure-viewer/index.html` should expose AI Optimization Overlay Mode as a stage-anchored semantic layer whose legend, selected state, selection inspector evidence card, and handoff stay synchronized with the same shareable review state and never fork into a separate copy-link flow
- The selection inspector on `src/structure-viewer/index.html` should explain the same selected member, story, or grid state that the overlay marks, and missing metrics or linkage data should appear as explicit `null`, `No data`, `N/A`, or `not linked` rather than zero or blank placeholders; invalid, missing, `NaN`, or `inf` coordinates should still surface `coordinate_valid`, `coordinate_status`, `coordinate_fallback_provenance`, and `coordinate_fallback_diagnostics` even when the stage uses a safe render fallback, and invalid row preview/details must stay traceable in reviewer handoff
- `implementation/phase1/release/visualization` is a generated artifact surface and should only change after the generator and contract test pass and the HTML is regenerated from source
- `src/structure-viewer/charts.html`, `src/structure-viewer/optimization_history.html`, and `src/structure-viewer/panel_zone.html` belong to the dark review family first and should reuse the same shell vocabulary, provenance labels, and action grammar with reduced chrome rather than inventing page-local roles
- `optimization_history.html` should treat the summary-bar companion-insight as a live history marker rail, with the latest iteration updating the card values and note text instead of freezing into static KPI copy
- `panel_zone.html` should keep the WebGL canvas inside an explicit stage, viewport, tool rail, and insight rail structure, so it reads as the same inspection application family as the flagship viewer
- `panel_zone.html` should treat picked objects as first-class review state: hover and click feedback must stay restrained, selected-object state should drive provenance and deep-link handoff, and the same `panel_zone_object_id` / `panel_zone_object_kind` must survive stage highlight, shared selection, deep links, and reload restoration without drifting from the selected 3D object
- `generate_optimized_drawing_review_ui.py`, `generate_structural_optimization_visualization_viewer.py`, `generate_pbd_review_package.py`, and committee or external validation outputs belong to the light review family first
- `optimized_drawing_review.html` may embed a dark precision viewport inside the light review page, but that viewport must still feel like the same product line: direct-manipulation controls for orbit, pan, zoom, fit, and reset; in-stage HUD chips; an axis compass; a bottom interaction ribbon; pinned member overlays; and dark glass tooltip language should frame the 3D drawing canvas without competing with the surrounding review evidence. The status badges and evidence card should read renderable, total, and invalid-excluded counts explicitly, and `no_valid_geometry` should surface as an audit-visible geometry state rather than an error. On mobile and tablet, keep the viewport first, keep gesture affordances obvious, compress HUD labels, preserve accessible focus and label order, keep tap-safe in-stage controls, preserve a clear stage-chrome hierarchy that prevents overlap, collapse selected-member state into a bottom sheet or compact overlay, and restack hero, provenance, table, and card evidence into mobile-safe blocks that never create page-level horizontal overflow
- Benchmark compare dashboards may mix dark visual focus with light documentation framing, but the entry hierarchy and control styling must still come from this system

### Acceptance

- Dark viewer pages are accepted when the stage, viewport, tool rail, and insight rail remain distinct semantic regions, the 3D viewport stays dominant, side rails remain subordinate to the stage, and every primary action exposes keyboard parity, visible focus, and an accessible name
- Shared selection is accepted when the single selection state API restores member, grid, story, and empty selection across reloads, deep links, and copied share URLs from the canonical `{kind, id, label, provenance}` record, keeps member/story/grid/empty identity stable across URL, copied deep links, restore, viewport highlight, selection inspector, selected table row, overlay, diff/export handoff, export handoff, and archive handoff, preserves object identity, label, provenance, and contract-version metadata, emits copied share URLs from canonical params only, with legacy `member`, `story`, and `grid` reserved for inbound compatibility only, clears stale member-level raw diff focus when the active state becomes story, grid, or empty in an audit-visible way, and announces selection changes through an `aria-live` or equivalent live channel instead of hover-only state
- Shared selection restore is accepted when canonical selection wins over conflicting legacy `member`, `story`, or `grid` params, stale legacy/hash params are removed after restore, and member-story context stays in the canonical context param rather than being mixed with legacy `story`
- AI Optimization Overlay Mode is accepted when the same legend, selection inspector evidence card, and handoff text describe `Member type`, `D/C ratio`, `Cost delta`, and `Constructability` in the viewport, inspector, and review handoff; the overlay stays anchored to the same copy review link / shareable review state, and missing data falls back to explicit `null`, `No data`, `N/A`, or `not linked` labels rather than fabricated, blank, or zero-valued results
- Stage result callouts are accepted when the viewport exposes `structure-viewer-stage-result-callouts.v2`, max displacement, max drift, base shear, and a critical member as compact model-adjacent tags derived from the same cockpit model as the KPI rail and critical-member table, includes per-callout full label, full value, source/source-type, active load case, active step, and evidence rows, lets the critical-member tag focus the same member selection as the table, mirrors `is-selected` / `aria-selected` / `aria-pressed` state between table and callout, projects the active critical member into a visible 3D halo plus compact HUD badge using the same selection identity, preserves Ctrl/Cmd member-set selection in `member_set`, shows secondary selected members as subordinate viewport markers, edge-pins the HUD badge instead of dropping it when the anchor is near or beyond the viewport edge, re-docks the stage result callout stack to a clear viewport corner when it would collide with the active selection HUD, and package smoke requires the v2 callout marker rather than a generic focus button.
- Stage story ruler is accepted when the viewport exposes `structure-viewer-stage-story-ruler.v1`, renders at least six projected story/height rows from the same story clip bands used by the Story Clip control, includes model height and story count receipt, surfaces drift context when available, lets story rows activate or clear the same story clip state, remains visible through projected/edge/docked placement, and reports zero overflow in the dense 1600x900 cockpit.
- Stage drift bands are accepted when the viewport exposes `structure-viewer-stage-drift-bands.v1`, projects the governing story drift rows from the same Story Drift chart model into the 3D stage, shows optimized drift, original drift, delta, and limit-marker bars, lets band clicks activate or clear the same story clip state, remains visible through projected/edge/docked placement, and reports zero overflow in the dense 1600x900 cockpit.
- Projected load/support glyphs are accepted when the viewport exposes `structure-viewer-stage-load-support-glyphs.v1`, mirrors the same lateral-load arrow count and sampled base-support marker count as the WebGL analysis overlay, shows high-contrast yellow load arrows and green support markers in the 3D stage, publishes projected/edge-pinned state to browser smoke evidence, remains pointer-transparent for orbit/pan, and reports zero overflow in the dense 1600x900 cockpit.
- Stage model stack evidence is accepted when the 1600x900 source viewer exposes `structure-viewer-stage-model-stack.v1`, keeps compact optimized/original/deformed layer rows visible in the dense stage control pod, uses distinct contour, neutral ghost, and deformed-shape swatches, synchronizes Compare/deformed `aria-pressed` state with the viewport tool rail and top run control, and does not hide the model stack merely to make room for other controls.
- Critical member hotspots are accepted when the top three critical members from the same cockpit model project into the viewport as `structure-viewer-stage-critical-hotspots.v1`, expose member id, rank, D/C ratio, story, drift contribution, selection state, and click-to-focus behavior, and remain visible through projected or edge/docked placement without text overflow or selected-member HUD collision.
- Panel-zone stage evidence is accepted when solver-verified rail evidence also appears in the viewport as `structure-viewer-panel-zone-stage-badge.v1`, exposes the same primary member, source counts, 3D clash count, fallback count, validation boundary, visible leader, and focus behavior as the rail candidate row, and remains visible through projected, edge-pinned, or docked placement without text overflow or selected-member HUD collision.
- Viewport tool rail is accepted when the 1600x900 source viewer shows three grouped tool sections, at least ten icon tools, tooltip labels, active contour/review states, correct `aria-pressed` state, and zero tool-button overflow while preserving the same render and camera actions as the top stage controls.
- Deformation scale control is accepted when the 1600x900 source viewer exposes `structure-viewer-deformation-control.v1`, renders a stage-local range control with a visible `1.0x` display scale and internal multiplier evidence, synchronizes the legacy deformation slider and stage review receipt, keeps Compare/Animate state on the same control, and reports zero overflow.
- Stage Result Receipt is accepted when the 1600x900 source viewer shows at least six compact rows for field, range, source, load case, step, and map/Compare state next to the contour legend, with no receipt overflow and with source labels using customer-facing terms such as `Source values` or `Model estimate`.
- Load-case evidence rows are accepted when the 1600x900 source viewer shows at least two compact load-case rows with case kind, status, source, and progress-bar evidence, marks one active row even when the source artifact only provides story-slice fallback labels, and keeps every row overflow-free.
- Dense desktop cockpit layout is accepted when the 1600x900 source viewer keeps top chrome under the compact-header budget, preserves a usable 3D viewport, shows all eight KPI cards, all four chart panels, at least four critical-member rows, and at least four stage result callouts, and proves the lower chart strip has zero overlap with the footer timeline while the stage callout stack has zero overlap with the selected-member HUD.
- KPI cards are accepted when all eight source-viewer KPI cards expose `data-kpi-full-label` and `data-kpi-full-value`, show labels such as `Max Displacement` and `Estimated Material Cost` without label ellipsis, split the visible value readout into `.kpi-card__value-number` plus `.kpi-card__value-unit` when units exist, keep the value readout free of `text-overflow: ellipsis`, render evidence/reference/trend chips with full labels preserved in `data-kpi-chip-full-label` plus dense short labels in `data-kpi-chip-short-label`, report zero label/value/chip overflow in the dense 1600x900 smoke, and customer-open package smoke requires the `kpi_full_label_readout`, `kpi_full_value_readout`, and `kpi_chip_readout` markers.
- Result-evidence receipt is accepted when the 1600x900 source viewer shows source-backed metric count, estimate metric count, total metric count, source coverage, sample base, load-step receipt, and heatmap/critical evidence rows directly under the KPI cards with zero overflow, and package smoke requires the same marker so a delivery viewer cannot drop provenance coverage.
- Materials & Members catalog is accepted when the source viewer exposes the normalized `structure-viewer-material-member-catalog.v1` contract, `structure-viewer-material-family-coverage.v1` coverage semantics, and a `structure-viewer-material-coverage-readiness.v1` readiness strip that scores material definitions, family classification, section catalog breadth, material-section links, thickness rows, and used material rows before the detailed list; it must show at least six material rows for the MIDAS33 optimized artifact, at least two known material-family chips, ontology breadth of at least 45 supported material families, at least six material-section schedule links, at least six section-material schedule links, section count at or above 180, thickness count at or above 30, visible steel and concrete grade labels, source-status labelling for every missing or inferred row, material-section rows that can focus/isolate the matching members when the direct model contains matching material and section ids, section rows that can isolate the matching section id, an explicit material review queue whenever missing or unclassified material evidence remains, and zero overflow in the 1600x900 cockpit.
- Result Step Schedule is accepted when the source viewer exposes `structure-viewer-result-step-schedule.v1`, renders at least five step rows around the active MIDAS33 load step, marks exactly one row as current, surfaces load case, solver, convergence, and runtime, row clicks sync the shared timeline step, the load-step chart cursor follows that same step, customer-open package smoke requires the schedule marker, and dense 1600x900 smoke reports zero schedule overflow.
- Analysis Timeline Footer is accepted when the source viewer exposes `structure-viewer-analysis-timeline-footer.v1`, renders the current load case, active step, total step count, previous/play/next controls, scrubber, at least five nearby step ticks with exactly one active tick, scale, solver, convergence, and runtime, keeps the footer state synchronized with Result Step Schedule and the load-step chart cursor, customer-open package smoke requires the timeline marker, and dense 1600x900 smoke reports zero footer/tick overflow.
- Result Envelope is accepted when the source viewer exposes `structure-viewer-result-envelope.v1`, renders at least four governing rows for displacement, drift, base shear, and utilization, surfaces load case, active step, source-metric coverage, and the governing critical member, lets member-scoped rows focus the same selected member as the Critical Members table, customer-open package smoke requires the envelope marker, and dense 1600x900 smoke reports zero envelope overflow.
- Optimization Delta Strip is accepted when the source viewer exposes `structure-viewer-optimization-delta-strip.v1`, renders four first-viewport before/after delta tiles from the same optimization rows as the full summary, includes reduction count, saved values, before/after bars, source labels, customer-open package smoke requires the marker, and dense 1600x900 smoke reports zero strip overflow.
- Critical Triage is accepted when the source viewer exposes `structure-viewer-critical-triage.v1` plus `structure-viewer-critical-members-compact-table.v1`, renders at least four top critical rows in the first right-rail viewport as a compact Critical Members table with ID, D/C, drift, status, and recommended-change columns, reports source row count, high-severity count, max D/C ratio, D/C limit markers, drift contribution, status and recommended action chips, mirrors full-table selection state, customer-open package smoke requires both markers, and dense 1600x900 smoke reports zero triage/table overflow.
- Model Overview is accepted when the source viewer exposes `structure-viewer-source-adapter-matrix.v1`, renders three imported-source adapter rows with exactly one current adapter for the active artifact, surfaces nonempty height, units, analysis type, and last-run fields in the left Model Info grid, customer-open package smoke requires the model-overview marker, and dense 1600x900 smoke reports zero source-adapter/model-info overflow.
- 3D segment geometry is accepted when `p0` / `p1` remain the canonical endpoints, provenance keeps a real `[0,0,0]` distinct from a fallback-generated `[0,0,0]`, invalid, missing, `NaN`, or `inf` coordinates preserve `coordinate_valid`, `coordinate_status`, `coordinate_fallback_provenance`, and `coordinate_fallback_diagnostics` through inspector review, export handoff, and archive handoff; when no valid coordinate row exists, the payload must surface `no_valid_geometry` as an audit-visible engineering state, stage badges and evidence cards must expose renderable, total, and invalid-excluded counts, and fallback coordinates kept only for legacy payload shape compatibility are excluded from viewport extent, derived axis/story refs, camera fit, hit testing, and rendered geometry
- Generated HTML is accepted when the selection state contract, generator, and contract test all pass before regeneration, the regenerated release artifact matches the source contract, and `implementation/phase1/release/visualization` is not patched by hand
- Package handoff is accepted when `project_package.zip` and `project_registry.json` agree, artifact hrefs validate, sha256/bytes match, the package membership receipt keeps `package_ready`, `packaged`, `missing_package_member`, `stale package`, and `hash mismatch` states explicit instead of flattening ZIP membership and registry/signature freshness into `0`, `pass`, or blank success, `HANDOFF_DIFF_SUMMARY.md` plus `data/handoff_diff_summary.json` explain redelivery added/removed/changed member counts without implying independent solver approval, and the customer-open viewer smoke proves the restored package's `viewer.html` opens with a visible nonblank canvas while reporting `commercial_cockpit_alignment.status=current_cockpit_delivery` for the current source cockpit markers. Legacy or stale single-file delivery surfaces must be explicit non-current handoff states, not quiet pass states.
- Drawing handoff is accepted when the rail card exposes `structure-viewer-drawing-handoff-panel.v2`, revision, active callout, selected member, primary SVG sheet, copyable viewer deep-link, handoff receipt rows for active sheet/callout/deep-link/selection sync, sheet-list actions, `Open Active Sheet`, and a compact preview thumbnail whose sheet name and callout match the same selection state as the viewport and report. Sheet hover and keyboard focus must update the active sheet preview, selected `aria-current` state, receipt data, and open action without losing the selected member identity; customer-open package smoke must require the drawing handoff receipt marker and dense 1600x900 smoke must report zero receipt overflow.
- Selection inspector evidence cards are accepted when keyboard focus lands on the active card, the same selected-state identity is readable in the viewport and rail, and missing facts stay explicit instead of collapsing to `0` or blank
- Overlay accessibility is accepted when legend rows, selection inspector fields, selected-state chips, and fallback labels have accessible names, visible focus, keyboard reachability, and enough contrast to be read without relying on hue alone
- Tables are accepted when selected rows mirror the same shared selection state with `aria-selected` and keyboard focus lands on the same row identity, and grid selection clears member rows rather than leaving stale member rows selected
- Viewport chrome is accepted when stage HUDs, axis cues, and interaction ribbons stay inside a touch-safe inset from the stage edge, avoid occluding picked geometry or bottom-sheet triggers, and do not promise mobile gestures the implementation cannot actually perform; any gesture advertised in chrome must work on touch or have an explicit fallback control
- Tokenized stage chrome is accepted when the stage frame, control pod, tool rail, interaction ribbon, and instrumentation strip resolve through the shared dark semantic tokens, so dark precision viewport chrome keeps its surface, text, border, and elevation mapping consistent, stays visually distinct, and avoids ad hoc color, border, or shadow treatments
- `optimization_history.html` is accepted when the history insight rail carries live markers derived from `last.event_label`, `last.event_note`, `last.selected_count`, and `summary.modified_total`
- `panel_zone.html` is accepted when `panel-stage`, `panel-viewport`, `panel-tool-rail`, and `panel-insight-rail` remain visible in the markup, the stage owns the WebGL canvas, selected-object shared-selection handoff stays aligned with provenance and deep links, and the same selected object can be restored after reload without drifting from the shared-selection contract
- `optimized_drawing_review.html` is accepted when the 3D drawing workspace keeps viewport-first mobile and tablet order, exposes explicit direct-manipulation affordances for orbit, pan, zoom, fit, and reset, keeps selection feedback visible in the viewport and detail sheet, keeps grid/member/story URL-share-restore state stable with stale-param cleanup, uses compact HUD labels with accessible focus order and tap-safe controls, collapses selected-member details into a bottom sheet or compact overlay, preserves a non-overlapping stage-chrome hierarchy, restacks hero, provenance, table, and card evidence for mobile, and avoids any page-level horizontal overflow
- Singlefile release exports are accepted only when `window.__STRUCTURAL_SINGLEFILE__=true;` is preserved and `IS_SINGLEFILE_VIEWER` continues to disable repo-payload fetches in exported HTML

## Do's and Don'ts

- Do make every viewer feel like it belongs to the same enterprise-grade structural review suite
- Do make the flagship dark viewer feel like a premium enterprise structural-analysis cockpit with compact chrome and dense evidence rails
- Do keep `charts.html`, `optimization_history.html`, and `panel_zone.html` speaking the same command-center vocabulary as the flagship shell for provenance, controls, and review actions
- Do keep provenance, selection context, and evidence links visible near the top of the page
- Do treat `DESIGN.md` as the source of truth for tokens, shared selection state, AI optimization overlay semantics, evidence payloads, and nullable or missing-data fallback
- Do keep member, story, grid, and empty identity stable across URL, copied deep links, restore, viewport highlight, inspector, selected table row, overlay, diff/export handoff, export handoff, and archive handoff
- Do treat member, story, grid, and empty selection as one canonical `{kind, id, label, provenance}` record, write shared URLs from canonical params only, keep legacy `member`, `story`, and `grid` reserved for inbound compatibility only, and carry selection contract version plus diff-focus contract version through generated summary/export metadata
- Do keep `p0` and `p1` as the canonical geometry identity for each 3D segment, and carry `coordinate_valid`, `coordinate_status`, `coordinate_fallback_provenance`, and `coordinate_fallback_diagnostics` through inspector, export, and archive handoff flows while keeping fallback coordinates shape-compatible only
- Do surface package freshness, archive membership, and hash receipt explicitly, with `package_ready`, `packaged`, `missing_package_member`, `stale package`, and `hash mismatch` labels instead of `0`, `pass`, or hidden success states
- Do make member diff focus and non-member stale diff clearing audit-visible so story, grid, and empty states never masquerade as a previous member's diff
- Do keep missing metrics and representative-member handoff fields explicit with `null`, `No data`, `N/A`, `not linked`, `missing_evidence_fields`, or `partial evidence` instead of hiding them, blanking them, or coercing them to `0`
- Do surface the representative-member evidence completeness receipt in both expert HTML and print-to-PDF review sheets before the callout table, so complete, partial, missing, `No data`, `not linked`, and `missing_evidence_fields` remain visible to external reviewers
- Do keep selection overlays, copy-state feedback, optimization overlay legend, and review handoff copy in the same enterprise tone as provenance and solver state
- Do treat the Selection Inspector as a review evidence card that explains AI judgment, selection gates, and diff/export handoff for the same selected state as the overlay
- Do keep `Member type`, `D/C ratio`, `Cost delta`, and `Constructability` aligned across legend, selected state, inspector, and review handoff
- Do bias toward teal and warm mineral accents instead of purple SaaS defaults, and keep teal/brass meaning distinct from success/warning/danger verdicts
- Do preserve high information density while improving grouping, spacing, and scan order
- Do keep the 3D stage visually dominant even when KPI cards, trend charts, critical member rows, properties, and optimization summaries become dense
- Do keep Korean and English labels equally robust in headers, controls, and metadata rows
- Do make direct manipulation feel precise across mouse, pen, and touch, with selection feedback that survives deep links and reloads
- Do keep engineering evidence dense but readable, with IDs, units, deltas, and provenance close to the viewport
- Do keep controls accessible with visible focus, tap-safe targets, label text that works in Korean and English, and explicit empty-data fallbacks that do not depend on color alone
- Do update generator sources, contract tests, and the regeneration path when changing selection state contracts or release artifacts
- Do regenerate generated HTML from source instead of hand-editing release artifacts
- Don't use `Inter`, `Segoe UI`, `Georgia`, or other local fallback stacks as the primary surface personality on refreshed pages
- Don't let light pages drift into plain document styling or dark pages drift into gaming visuals
- Don't create page-local accent palettes that break the product family
- Don't let the workflow tab row, left rail, or right rail collapse into oversized consumer navigation blocks or form dumps
- Don't make the global top bar tall enough to compete with the model stage
- Don't make export pages look like a downgraded version of the interactive viewer
- Don't hide important state behind hover alone or color alone
- Don't collapse a real `[0,0,0]` coordinate into a fallback-generated `[0,0,0]`, or strip invalid, missing, `NaN`, or `inf` coordinate state, provenance, or diagnostics just because the renderer needed a safe fallback
- Don't rely on toast-only feedback or consumer share language for copy success, copy failure, empty selection, or missing optimization data
- Don't use `0` as a stand-in for missing optimization, provenance, or linkage data; use explicit muted fallbacks like `null`, `No data`, `N/A`, or `not linked`
- Don't hand-edit generated HTML or release artifacts
- Don't let copy review link or shareable review state fork when optimization overlays or selection inspector evidence cards are present, and don't leave stale legacy or hash selection params behind after canonical restore
- Don't rename the same shell roles across dark review pages or introduce page-local chrome for a shared function
