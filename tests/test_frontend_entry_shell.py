from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_frontend_entry_shell_points_to_structural_workbench() -> None:
    main_tsx = (ROOT / "src" / "main.tsx").read_text(encoding="utf-8")
    app_tsx = (ROOT / "src" / "App.tsx").read_text(encoding="utf-8")
    index_css = (ROOT / "src" / "index.css").read_text(encoding="utf-8")
    index_html = (ROOT / "index.html").read_text(encoding="utf-8")
    resource_model = (ROOT / "src" / "workbench" / "resourceModel.ts").read_text(encoding="utf-8")
    tsconfig = json.loads((ROOT / "tsconfig.json").read_text(encoding="utf-8"))

    assert "import App from './App'" in main_tsx
    assert "import './index.css'" in main_tsx
    assert ".authoring-card--coverage-matrix" in index_css
    assert ".authoring-coverage-grid__head" in index_css
    assert ".authoring-coverage-cell__summary" in index_css
    assert ".authoring-card__topline" in index_css
    assert ".review-board-rows" in index_css
    assert ".review-board-row__header" in index_css
    assert ".review-board-row__field" in index_css
    assert ".review-board-row__footer" in index_css

    assert "Structural Signal Desk" in app_tsx
    assert "Structural Optimization Workbench" in app_tsx
    assert "./implementation/phase1/release/visualization/structural_optimization_viewer.html" in app_tsx
    assert "./implementation/phase1/release/visualization/optimized_drawing_review.html" in app_tsx
    assert "./implementation/phase1/release/visualization/benchmark_optimization_review.html" in app_tsx
    assert "./implementation/phase1/release/committee_review/committee_review_dashboard.html" in app_tsx
    assert "./implementation/phase1/release/committee_review/committee_summary.json" in app_tsx
    assert "./implementation/phase1/release/committee_review/committee_review_package_report.json" in app_tsx
    assert "./implementation/phase1/release_evidence/productization/developer_preview_readiness.json" in app_tsx
    assert "./implementation/phase1/release_evidence/productization/phase1_core_api_model_health_result.json" in app_tsx
    assert "./implementation/phase1/release_evidence/productization/phase1_core_api_model_health_report.json" in app_tsx
    assert "./implementation/phase1/release/commercial_workflow_breadth_report.json" in app_tsx
    assert "./implementation/phase1/release/release_gap_report.json" in app_tsx
    assert "./implementation/phase1/release/project_registry.json" in app_tsx
    assert "./implementation/phase1/release/project_registry_portfolio_workspace.json" in app_tsx
    assert "./implementation/phase1/release/project_registry_index.json" in app_tsx
    assert "./implementation/phase1/release/release_registry.json" in app_tsx
    assert "./implementation/phase1/release/project_package.zip" in app_tsx
    assert "./implementation/phase1/release/signing/project_registry.signature.b64" in app_tsx
    assert "./implementation/phase1/release/external_benchmark_kickoff/external_benchmark_batch_job_report.json" in app_tsx
    assert "./implementation/phase1/release/external_benchmark_kickoff/external_benchmark_execution_status_manifest.json" in app_tsx
    assert "./implementation/phase1/release/authoring/native_authoring_workspace_summary.json" in app_tsx
    assert "./implementation/phase1/release/authoring/native_authoring_solver_session.json" in app_tsx
    assert "./implementation/phase1/release/authoring/native_authoring_solver_session.loadcomb_preview.mgt" in app_tsx
    assert "./implementation/phase1/release/authoring/native_authoring_ops_bundle.json" in app_tsx
    assert "./implementation/phase1/release/authoring/native_authoring_batch_job_report.json" in app_tsx
    assert "./implementation/phase1/release/authoring/native_authoring_project_registry.json" in app_tsx
    assert "./implementation/phase1/release/authoring/portfolio/native_authoring_ops_portfolio.json" in app_tsx
    assert "./implementation/phase1/release/authoring/portfolio/native_authoring_family_tracks.json" in app_tsx
    assert "./implementation/phase1/release/authoring/portfolio/native_authoring_project_registry_workspace.json" in app_tsx
    assert "./implementation/phase1/release/authoring/portfolio/native_authoring_runtime_submission_lane.json" in app_tsx
    assert "./implementation/phase1/release/authoring/portfolio/native_authoring_runtime_writeback_depth_report.json" in app_tsx
    assert "./implementation/phase1/release/authoring/portfolio/native_authoring_multi_project_runtime_writeback_report.json" in app_tsx
    assert "./implementation/phase1/release/authoring/portfolio/native_authoring_solver_family_breadth_report.json" in app_tsx
    assert "./implementation/phase1/release/authoring/portfolio/native_authoring_local_runtime_scenario_depth_report.json" in app_tsx
    assert "./implementation/phase1/release/authoring/portfolio/native_authoring_local_variant_writeback_trace_report.json" in app_tsx
    assert "./implementation/phase1/release/authoring/portfolio/native_authoring_writeback_breadth_report.json" in app_tsx
    assert "./implementation/phase1/release/project_ops_service_snapshot.json" in app_tsx
    assert "./implementation/phase1/release/authoring/native_authoring_project_package.zip" in app_tsx
    assert "./implementation/phase1/release/signing/native_authoring_project_registry.signature.b64" in app_tsx
    assert "startTransition(() =>" in app_tsx
    assert "fetchFirstJson([" in app_tsx
    assert "Native Authoring Workspace" in app_tsx
    assert "type AuthoringFamilyOption" in app_tsx
    assert "belt_truss_mega_frame" in app_tsx
    assert "deep_transfer_basement" in app_tsx
    assert "Belt-Truss Mega Frame" in app_tsx
    assert "Deep Transfer Basement" in app_tsx
    assert "function buildAuthoringFamilyOptions" in app_tsx
    assert "function estimateAuthoringMemberCount" in app_tsx
    assert "authoringRuntimeSubmissionLane: ResourceState" in resource_model
    assert "authoringRuntimeWritebackDepth: ResourceState" in resource_model
    assert "authoringMultiProjectRuntimeWriteback: ResourceState" in resource_model
    assert "authoringSolverFamilyBreadth: ResourceState" in resource_model
    assert "authoringLocalRuntimeScenarioDepth: ResourceState" in resource_model
    assert "authoringLocalVariantWritebackTrace: ResourceState" in resource_model
    assert "authoringWritebackBreadth: ResourceState" in resource_model
    assert "developerPreview: ResourceState" in resource_model
    assert "coreApiResult: ResourceState" in resource_model
    assert "coreApiReport: ResourceState" in resource_model
    assert "function buildDeveloperPreviewSnapshot" in app_tsx
    assert "Open Benchmark Developer Preview" in app_tsx
    assert "Open Developer Preview readiness JSON" in app_tsx
    assert "getRecord(resource.data, 'gap_ledger_closure_requirement_visibility')" in app_tsx
    assert "Closure req" in app_tsx
    assert "Failed req" in app_tsx
    assert "visibility only; no G1/G6/G7 closure" in app_tsx
    assert "function buildCoreApiContractSnapshot" in app_tsx
    assert "Phase 1 Core API Contract" in app_tsx
    assert "Open Core API result JSON" in app_tsx
    assert "Open Core API validation report JSON" in app_tsx
    assert "resources.coreApiResult.source" in app_tsx
    assert "resources.coreApiReport.source" in app_tsx
    assert "external approval receipt" in app_tsx
    assert "function buildAuthoringRuntimeSubmissionLaneSnapshot" in app_tsx
    assert "function buildAuthoringRuntimeWritebackDepthSnapshot" in app_tsx
    assert "function buildAuthoringMultiProjectRuntimeWritebackSnapshot" in app_tsx
    assert "function buildAuthoringSolverFamilyBreadthSnapshot" in app_tsx
    assert "function buildAuthoringLocalRuntimeScenarioDepthSnapshot" in app_tsx
    assert "function buildAuthoringLocalVariantWritebackTraceSnapshot" in app_tsx
    assert "function buildAuthoringWritebackBreadthSnapshot" in app_tsx
    assert "function buildAuthoringFamilyCorpusSnapshot" in app_tsx
    assert "Solver-ready draft preview" in app_tsx
    assert "Commercialization breadth" in app_tsx
    assert "function buildCommercializationDepthSignal" in app_tsx
    assert "function buildCommercializationDepthSignals" in app_tsx
    assert "const advancedSsiDetail = asString(summary.advanced_ssi_summary_line)" in app_tsx
    assert "const referenceRegressionDetail = asString(summary.reference_regression_summary_line)" in app_tsx
    assert "const windDetail = asString(summary.wind_workflow_summary_line)" in app_tsx
    assert "firstBoolean(summary.material_constitutive_pass)" in app_tsx
    assert "firstBoolean(summary.reference_regression_pass)" in app_tsx
    assert "firstBoolean(summary.advanced_ssi_pass)" in app_tsx
    assert "firstBoolean(summary.wind_workflow_pass, summary.wind_tunnel_raw_mapping_ready)" in app_tsx
    assert "P0 ready" in app_tsx
    assert "P1 ready" in app_tsx
    assert "Depth lanes" in app_tsx
    assert "Portfolio scope" in app_tsx
    assert "Family corpus" in app_tsx
    assert "Open family corpus JSON" in app_tsx
    assert "summary.native_authoring_family_corpus_summary_line" in app_tsx
    assert "function buildAuthoringFamilyLocalEvidenceSnapshot" in app_tsx
    assert "Local evidence" in app_tsx
    assert "Open local evidence JSON" in app_tsx
    assert "summary.native_authoring_family_local_evidence_summary_line" in app_tsx
    assert "function buildAuthoringConsistencySnapshot" in app_tsx
    assert "Portfolio / family / runtime / service consistency" in app_tsx
    assert "type AuthoringFamilyCoverageCell" in app_tsx
    assert "type AuthoringFamilyCoverageRow" in app_tsx
    assert "function buildAuthoringFamilyCoverageRows" in app_tsx
    assert "function buildAuthoringFamilyCoverageSnapshot" in app_tsx
    assert "function buildAuthoringSolverBreadthCoverageCell" in app_tsx
    assert "function buildAuthoringLocalRuntimeDepthCoverageCell" in app_tsx
    assert "function buildAuthoringWritebackBreadthCoverageCell" in app_tsx
    assert "Family coverage matrix" in app_tsx
    assert "portfolio + solver breadth + runtime depth + writeback breadth" in app_tsx
    assert "family coverage aligned" in app_tsx
    assert "family coverage check" in app_tsx
    assert "Open runtime depth JSON" in app_tsx
    assert "Open writeback breadth JSON" in app_tsx
    assert "Scope anchor" in app_tsx
    assert "portfolio scope note is coverage, not readiness" in app_tsx
    portfolio_report = json.loads(
        (ROOT / "implementation" / "phase1" / "release" / "authoring" / "portfolio" / "native_authoring_ops_portfolio.json").read_text(
            encoding="utf-8"
        )
    )
    family_tracks_report = json.loads(
        (ROOT / "implementation" / "phase1" / "release" / "authoring" / "portfolio" / "native_authoring_family_tracks.json").read_text(
            encoding="utf-8"
        )
    )
    expected_family_ids = {
        "sample_tower",
        "steel_braced_frame",
        "rc_wall_core",
        "composite_podium",
        "outrigger_transfer_tower",
        "dual_system_hospital",
        "belt_truss_mega_frame",
        "deep_transfer_basement",
    }
    assert portfolio_report["summary"]["family_count"] == len(expected_family_ids) == 8
    assert family_tracks_report["summary"]["family_count"] == len(expected_family_ids) == 8
    assert {row["family_id"] for row in portfolio_report["family_rows"]} == expected_family_ids
    assert {row["family_id"] for row in family_tracks_report["track_rows"]} == expected_family_ids
    assert "sourceLabel(authoringPortfolioResource.source)" in app_tsx
    assert "source: {authoringConsistencySnapshot.sourceLabel}" in app_tsx
    assert "Solver session" in app_tsx
    assert "Draft authoring bundle:" in app_tsx
    assert "function classifyAuthoringSectionFamily" in app_tsx
    assert "function uniqueTokens" in app_tsx
    assert "palette breadth is still scaffold coverage입니다." in app_tsx
    assert "portfolio manifest를 우선 읽고, 없으면 shared registry portfolio index를 fallback으로 사용합니다." in app_tsx
    assert "structural-analysis-workbench/native-authoring-controls" in app_tsx
    assert "buildAuthoringDraftPayload" in app_tsx
    assert "window.localStorage.getItem(authoringDraftStorageKey)" in app_tsx
    assert "window.localStorage.setItem(" in app_tsx
    assert "Reset to baseline" in app_tsx
    assert "Export draft JSON" in app_tsx
    assert "Import draft JSON" in app_tsx
    assert "P0-P4 local review board" in app_tsx
    assert "approve / reject / needs engineer review decisions" in app_tsx
    assert "reviewStateStorageKey" in app_tsx
    assert "reviewStateDownloadName" in app_tsx
    assert "buildReviewableGapRows" in app_tsx
    assert "buildReviewStateSummary" in app_tsx
    assert "buildReviewStateStoragePayload" in app_tsx
    assert "buildReviewStateExportPayload" in app_tsx
    assert "Reset review state" in app_tsx
    assert "Export review JSON" in app_tsx
    assert "Import review JSON" in app_tsx
    assert "Issue marker" in app_tsx
    assert "Needs engineer review" in app_tsx
    assert "Comment saved locally" in app_tsx
    assert "Native family" in app_tsx
    assert "Draft switched to ${nextFamily.label}." in app_tsx
    assert "Default bay width" in app_tsx
    assert 'type="file"' in app_tsx
    assert 'accept="application/json,.json"' in app_tsx
    assert "download={authoringDraftDownloadName}" in app_tsx
    assert "Ops lane" in app_tsx
    assert "Runtime submission lane" in app_tsx
    assert "Runtime writeback depth" in app_tsx
    assert "Multi-project runtime/writeback" in app_tsx
    assert "Solver family breadth" in app_tsx
    assert "Local runtime scenario depth" in app_tsx
    assert "Local variant/writeback trace" in app_tsx
    assert "Writeback breadth" in app_tsx
    assert "runtime writeback depth ready" in app_tsx
    assert "runtime writeback depth check" in app_tsx
    assert "Open runtime writeback depth JSON" in app_tsx
    assert "multi-project runtime ready" in app_tsx
    assert "multi-project runtime check" in app_tsx
    assert "Open multi-project runtime JSON" in app_tsx
    assert "solver family breadth ready" in app_tsx
    assert "solver family breadth check" in app_tsx
    assert "Open solver family breadth JSON" in app_tsx
    assert "local runtime depth ready" in app_tsx
    assert "local runtime depth check" in app_tsx
    assert "Open local runtime depth JSON" in app_tsx
    assert "local variant/writeback trace ready" in app_tsx
    assert "local variant/writeback trace check" in app_tsx
    assert "Open local variant/writeback trace JSON" in app_tsx
    assert "writeback breadth ready" in app_tsx
    assert "writeback breadth check" in app_tsx
    assert "Open writeback breadth JSON" in app_tsx
    assert "runtime lane ready" in app_tsx
    assert "runtime lane check" in app_tsx
    assert "Open runtime lane JSON" in app_tsx
    assert "resources.authoringRuntimeSubmissionLane.source" in app_tsx
    assert "resources.authoringRuntimeWritebackDepth.source" in app_tsx
    assert "resources.authoringMultiProjectRuntimeWriteback.source" in app_tsx
    assert "resources.authoringLocalRuntimeScenarioDepth.source" in app_tsx
    assert "resources.authoringLocalVariantWritebackTrace.source" in app_tsx
    assert "const authoringRuntimeSubmissionLaneSnapshot = buildAuthoringRuntimeSubmissionLaneSnapshot(" in app_tsx
    assert "const authoringRuntimeWritebackDepthSnapshot = buildAuthoringRuntimeWritebackDepthSnapshot(" in app_tsx
    assert "const authoringMultiProjectRuntimeWritebackSnapshot = buildAuthoringMultiProjectRuntimeWritebackSnapshot(" in app_tsx
    assert "const authoringLocalRuntimeScenarioDepthSnapshot = buildAuthoringLocalRuntimeScenarioDepthSnapshot(" in app_tsx
    assert "const authoringLocalVariantWritebackTraceSnapshot = buildAuthoringLocalVariantWritebackTraceSnapshot(" in app_tsx
    assert "native authoring runtime submission lane JSON을 우선 읽고, 없으면 project ops service snapshot을 fallback으로 사용합니다." in app_tsx
    assert "Open solver session" in app_tsx
    assert "Open loadcomb preview" in app_tsx
    assert "Open ops bundle" in app_tsx
    assert "Open authoring batch" in app_tsx
    assert "Open authoring registry" in app_tsx
    assert "Open authoring package" in app_tsx
    assert "Open authoring signature" in app_tsx
    assert "Open portfolio JSON" in app_tsx
    assert "resources.authoringSolverFamilyBreadth.source" in app_tsx
    assert "Open portfolio workspace" in app_tsx
    assert "type AuthoringPortfolioFamilySnapshot" in app_tsx
    assert "function buildAuthoringPortfolioFamilySnapshots" in app_tsx
    assert "Family commercialization lanes" in app_tsx
    assert "native authoring portfolio manifest에서 family별 commercialization row를 직접 읽어," in app_tsx
    assert "family={family.familyId} | draft={family.draftLabel}" in app_tsx
    assert "lane ready" in app_tsx
    assert "lane check" in app_tsx
    assert "Workspace" in app_tsx
    assert "Solver" in app_tsx
    assert "Registry" in app_tsx
    assert "Portfolio families unavailable" in app_tsx
    assert "native authoring portfolio JSON이 아직 없어서 family commercialization rows를 표시하지 못했습니다." in app_tsx
    assert "native authoring ops portfolio를 기준으로 solver family breadth, local runtime scenario depth, writeback breadth를 family key로 조인했습니다." in app_tsx
    assert "type AdvancedHoldoutRow" in app_tsx
    assert "type CommercializationDepthSignal" in app_tsx
    assert "function buildCommercialWorkflowBreadthSnapshot" in app_tsx
    assert "function buildAdvancedHoldoutRows" in app_tsx
    assert "function buildGapSeveritySnapshot" in app_tsx
    assert "function buildCommercializationDepthSignal" in app_tsx
    assert "function buildCommercializationDepthSignals" in app_tsx
    assert "Commercialization depth snapshot" in app_tsx
    assert "release gap summary의 material/load/advanced SSI/wind signals를 compact P0/P1 readiness로 묶습니다." in app_tsx
    assert "Commercial workflow breadth" in app_tsx
    assert "`commercial_gap_analysis.md`에서 마지막까지 남던 construction-stage, rail/tunnel," in app_tsx
    assert "design redesign-loop breadth를 별도 JSON으로 묶어 보여줍니다." in app_tsx
    assert "missingSnapshot('commercial workflow breadth JSON을 아직 읽지 못했습니다.')" in app_tsx
    assert "workflow breadth ready" in app_tsx
    assert "workflow breadth check" in app_tsx
    assert "Open workflow breadth JSON" in app_tsx
    assert "resources.commercialWorkflowBreadth.source" in app_tsx
    assert "label: 'Construction'" in app_tsx
    assert "label: 'Rail'" in app_tsx
    assert "label: 'Redesign'" in app_tsx
    assert "label: 'Clauses'" in app_tsx
    assert "label: 'Actions'" in app_tsx
    assert "label: 'P0 ready'" in app_tsx
    assert "label: 'P1 ready'" in app_tsx
    assert "label: 'Depth lanes'" in app_tsx
    assert "P0 ready" in app_tsx
    assert "P1 ready" in app_tsx
    assert "Depth lanes" in app_tsx
    assert "summary.material_constitutive_summary_line" in app_tsx
    assert "summary.load_combination_editor_commercialization_summary_line" in app_tsx
    assert "summary.load_combination_engine_summary_line" in app_tsx
    assert "firstBoolean(summary.load_combination_editor_commercialization_pass, summary.load_combination_engine_pass)" in app_tsx
    assert "summary.foundation_soil_link_summary_line" in app_tsx
    assert "summary.wind_tunnel_raw_mapping_ready" in app_tsx
    assert "summary.wind_tunnel_mapping_mode" in app_tsx
    assert "summary.release_surface_status_label" in app_tsx
    assert "summary.release_surface_not_run_task_count" in app_tsx
    assert "summary.release_surface_failed_task_count" in app_tsx
    assert "Material" in app_tsx
    assert "Load" in app_tsx
    assert "Reference regression" in app_tsx
    assert "Advanced SSI" in app_tsx
    assert "Wind" in app_tsx
    assert "signal.label.toLowerCase().replace(/\\s+/g, '_')}=${signal.statusLabel}" in app_tsx
    assert "Advanced holdout commercialization" in app_tsx
    assert "release gap report의 advanced holdout rows를 compact closeout 표면으로 바로 보여줍니다." in app_tsx
    assert "Advanced holdouts unavailable" in app_tsx
    assert "release gap report에 advanced holdout rows가 아직 없어 compact commercialization table을 표시하지 못했습니다." in app_tsx
    assert "evidence unavailable" in app_tsx
    assert "Severity {row.severity}" in app_tsx
    assert "Mode {shorten(row.mode, 34)}" in app_tsx
    assert "source: {artifactSnapshots.gap.sourceLabel}" in app_tsx
    assert "Draft restored from browser storage." in app_tsx
    assert "Baseline loaded from release summary." in app_tsx
    assert "Imported draft from ${file.name}." in app_tsx
    assert "Import failed:" in app_tsx
    assert "Browser storage is unavailable; draft stays in memory." in app_tsx
    assert "Registry Portfolio Index" in app_tsx
    assert "panel panel--route" in app_tsx
    assert "Recommended route" in app_tsx
    assert "Finish gate" in app_tsx
    assert "Drawing-first review route" in app_tsx
    assert "Benchmark validation route" in app_tsx
    assert "Submission and authority route" in app_tsx
    assert "Interactive evidence route" in app_tsx
    assert "function buildWorkbenchReturnHref" in app_tsx
    assert "const selectionParamsBySurface" in app_tsx
    assert "focus_member: memberId" in app_tsx
    assert "overlay_member_id: tokenString(locatorRow.member_id)" in app_tsx
    assert "route_member_id: diffMemberId" in app_tsx
    assert "route_story_band: tokenString(viewerSelection.story_band)" in app_tsx
    assert "route_diff_index: diffIndex" in app_tsx
    assert "route_diff_row_id:" in app_tsx
    assert "route_benchmark_family" in app_tsx
    assert "route_projection" in app_tsx
    assert "route_case_id" in app_tsx
    assert "route_track" in app_tsx
    assert "route_candidate_id" in app_tsx
    assert "route_action_name" in app_tsx
    assert "combination_name: combinationName" in app_tsx
    assert "results_card: recommendedResultsCard" in app_tsx
    assert "results_companion: recommendedResultsCard ? 'interactive' : ''" in app_tsx
    assert "results_detail_block: recommendedResultsCard ? 'chart' : ''" in app_tsx
    assert "codecheck_surface: codecheckEnabled ? 'drilldown' : ''" in app_tsx
    assert "codecheck_appendix_block: codecheckEnabled ? 'subset-summary' : ''" in app_tsx
    assert "route_appendix_block: routeAppendixBlock" in app_tsx
    assert "route_combination_name: routeCombinationName" in app_tsx
    assert "route_clause_label: routeClauseLabel" in app_tsx
    assert "route_hazard_type: routeHazardType" in app_tsx
    assert "route_rule_family: routeRuleFamily" in app_tsx
    assert "const routeSurfaceFocusMap" in app_tsx
    assert "const committeeAppendixRouteMap" in app_tsx
    assert "route_focus: resolveSurfaceRouteFocus(surface.id, routeTitle)" in app_tsx
    assert "'viewer-interactive-3d'" in app_tsx
    assert "'drawing-member-review'" in app_tsx
    assert "'peer-benchmark'" in app_tsx
    assert "'committee-validation-table'" in app_tsx
    assert "selectionParamsBySurface" in app_tsx
    assert "...selectionParamsBySurface[surface.id]" in app_tsx
    assert "route_title: routeTitle" in app_tsx
    assert "target_surface: surface.id" in app_tsx
    assert "target_surface: artifact.id" in app_tsx
    assert "return_to: buildWorkbenchReturnHref(surface.href)" in app_tsx
    assert "return_to: buildWorkbenchReturnHref(artifact.href)" in app_tsx
    assert "return_label: 'Structural Optimization Workbench'" in app_tsx
    assert "viewer summary loaded" in app_tsx
    assert "release registry fallback" in app_tsx
    assert "execution status fallback" in app_tsx

    assert "<title>Structural Optimization Workbench</title>" in index_html
    assert "Monet Gallery Wedding" not in index_html
    assert "/vite.svg" not in index_html
    assert ".authoring-actions" in index_css
    assert ".authoring-import" in index_css
    assert ".authoring-status" in index_css
    assert ".authoring-card--portfolio-lanes" in index_css
    assert ".authoring-family-matrix" in index_css
    assert ".authoring-family-row" in index_css
    assert ".authoring-family-links" in index_css
    assert ".mini-metric-grid--family" in index_css
    assert ".advanced-holdout-card" in index_css
    assert ".advanced-holdout-table" in index_css
    assert ".advanced-holdout-row" in index_css
    assert ".advanced-holdout-row__fields" in index_css
    assert ".button:disabled" in index_css

    assert tsconfig["include"] == [
        "src/App.tsx",
        "src/main.tsx",
        "src/vite-env.d.ts",
        "src/workbench-v2",
    ]


def test_frontend_entry_shell_adds_authoring_server_ops_and_family_track_surfaces() -> None:
    app_tsx = (ROOT / "src" / "App.tsx").read_text(encoding="utf-8")
    resource_model = (ROOT / "src" / "workbench" / "resourceModel.ts").read_text(encoding="utf-8")

    assert "authoringServerOps: ResourceState" in resource_model
    assert "authoringFamilyTrack: ResourceState" in resource_model
    assert "./implementation/phase1/release/project_ops_service_snapshot.json" in app_tsx
    assert "./implementation/phase1/release/authoring/native_authoring_job_manifest.json" in app_tsx
    assert "./implementation/phase1/release/authoring/portfolio/native_authoring_ops_portfolio_batch.json" in app_tsx
    assert "./implementation/phase1/release/authoring/portfolio/native_authoring_family_tracks.json" in app_tsx
    assert "./implementation/phase1/release/authoring/portfolio/native_authoring_project_registry_index.json" in app_tsx
    assert "function buildAuthoringServerOpsSnapshot" in app_tsx
    assert "function buildAuthoringFamilyTrackSnapshot" in app_tsx
    assert "const authoringServerOpsSnapshot = buildAuthoringServerOpsSnapshot(resources.authoringServerOps)" in app_tsx
    assert "const authoringFamilyTrackSnapshot = buildAuthoringFamilyTrackSnapshot(resources.authoringFamilyTrack)" in app_tsx
    assert "Server ops summary" in app_tsx
    assert "Family-track commercialization breadth" in app_tsx
    assert "Open server ops JSON" in app_tsx
    assert "Open family track JSON" in app_tsx
    assert "resources.authoringServerOps.source" in app_tsx
    assert "resources.authoringFamilyTrack.source" in app_tsx
    assert "function buildAuthoringConsistencySnapshot" in app_tsx
    assert "consistency aligned" in app_tsx
    assert "statusLabel: contractPass === true ? 'server ops ready' : 'server ops check'" in app_tsx
    assert "statusLabel: contractPass === true ? 'family track ready' : 'family track check'" in app_tsx
    assert "missingSnapshot('native authoring server ops summary를 아직 읽지 못했습니다.')" in app_tsx
    assert "missingSnapshot('native authoring family track JSON을 아직 읽지 못했습니다.')" in app_tsx


def test_frontend_entry_shell_wraps_content_in_product_app_shell() -> None:
    app_tsx = (ROOT / "src" / "App.tsx").read_text(encoding="utf-8")
    index_css = (ROOT / "src" / "index.css").read_text(encoding="utf-8")

    # App-shell chrome: top app bar + left review-desk nav + status bar.
    assert 'className="app-shell"' in app_tsx
    assert 'className="app-bar"' in app_tsx
    assert "Local evidence workspace" in app_tsx
    assert 'className="app-nav"' in app_tsx
    assert 'aria-label="Review surfaces"' in app_tsx
    assert "Review desks" in app_tsx
    assert "app-nav__item" in app_tsx
    assert "onClick={() => setActiveSurfaceId(surface.id)}" in app_tsx
    assert 'aria-current={surface.id === activeSurfaceId ? \'page\' : undefined}' in app_tsx
    assert 'className="shell app-shell__main"' in app_tsx
    assert 'className="app-statusbar" aria-label="Workspace status"' in app_tsx

    # Shell layout styles must be present.
    assert ".app-shell {" in index_css
    assert ".app-bar {" in index_css
    assert ".app-nav__item {" in index_css
    assert ".app-nav__item.is-active {" in index_css
    assert ".app-statusbar {" in index_css
    assert "grid-template-areas:" in index_css
