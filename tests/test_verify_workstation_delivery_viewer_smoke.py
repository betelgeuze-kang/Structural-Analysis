from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import zipfile


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "verify-workstation-delivery-viewer-smoke.mjs"


def _write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _checksum_rows(root: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        rel = path.relative_to(root).as_posix()
        if rel == "checksums.sha256":
            continue
        rows.append({"path": rel, "bytes": path.stat().st_size, "sha256": _sha256(path)})
    return rows


def _write_zip(root: Path, package: Path) -> None:
    package.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(package, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(item for item in root.rglob("*") if item.is_file()):
            archive.write(path, path.relative_to(root).as_posix())


def test_workstation_delivery_viewer_smoke_static_contract(tmp_path: Path) -> None:
    root = tmp_path / "package-root"
    _write_text(
        root / "viewer.html",
        """
        <!doctype html>
        <html>
          <head><title>Structural Insight Viewer</title></head>
          <body data-viewer-workflow="model">
            <link rel="stylesheet" href="commercial-cockpit-polish.css">
            <main id="viewport" data-stage-overlay-occlusion-budget="dense-model-protagonist" data-stage-dominance-budget="dense-stage-primary"><canvas></canvas></main>
            <nav class="workflow-tab">Model Optimization</nav>
            <a class="viewer-tab" data-viewer-workflow-tab="drawings" href="#drawing-handoff-section">Drawings</a>
            <section id="layer-toggles">
              <div class="layer-toggle-group">Material families</div>
              <label class="panel-toggle-row" data-layer-toggle-row="true"><input type="checkbox" checked>Concrete</label>
              <div class="layer-toggle-group">Material laws</div>
              <label class="panel-toggle-row" data-layer-toggle-row="true"><input type="checkbox" checked>Concrete damage-plasticity</label>
            </section>
            <select data-shell-project-select onchange="setTopbarWorkspaceSelection(this.value)"><option value="demo::drawing">Demo Drawing</option></select>
            <section data-integrated-review-navigator data-integrated-review-schema="structure-viewer-integrated-review-navigator.v1">
              <button data-integrated-review-open onclick="openIntegratedReviewNavigator()">Map</button>
              <button data-integrated-review-drawing data-integrated-review-drawing-id="demo">setIntegratedReviewNavigatorDrawing</button>
              <button data-integrated-review-section data-integrated-review-target="stage-panel">Review Section</button>
              <div data-integrated-review-preview data-integrated-review-preview-schema="structure-viewer-integrated-review-preview.v1">
                <span data-integrated-review-preview-row>Selected Combination</span>
              </div>
            </section>
            <section data-top-run-control><button data-top-run-action="new-run" onclick="startNewReviewRun()">New Run</button></section>
            <section data-model-overview-panel>
              <div data-source-adapter-matrix>
                <span data-source-adapter-row data-source-adapter-status="current">MIDAS structure-viewer-source-adapter-matrix.v1</span>
              </div>
            </section>
            <section data-stage-review-controls>
              <div data-stage-model-stack data-stage-model-stack-schema="structure-viewer-stage-model-stack.v1">
                <span data-stage-model-layer="optimized"><i class="stage-model-stack__swatch--optimized"></i>Optimized Model</span>
                <span data-stage-model-layer="original"><i class="stage-model-stack__swatch--original"></i>Original Ghost</span>
                <span data-stage-model-layer="deformed"><i class="stage-model-stack__swatch--deformed"></i>Deformed Shape</span>
              </div>
              <div data-stage-deformation-control data-deformation-control-schema="structure-viewer-deformation-control.v1">
                <input data-stage-deformation-scale-slider value="1.0">
              </div>
            </section>
            <section data-analysis-result-evidence><span class="analysis-result-evidence-row">Result evidence</span></section>
            <section id="kpi-summary-panel">
              <article class="kpi-card">
                <span class="kpi-card__label" data-kpi-full-label="Max Displacement">Max Displacement</span>
                <strong class="kpi-card__value" data-kpi-full-value="118.6 mm">
                  <span class="kpi-card__value-number">118.6</span>
                  <span class="kpi-card__value-unit">mm</span>
                </strong>
                <span class="kpi-card__evidence" data-kpi-chip="evidence" data-kpi-chip-full-label="Model estimate" data-kpi-chip-short-label="Model est.">Model est.</span>
              </article>
              <article class="kpi-card">
                <span class="kpi-card__label" data-kpi-full-label="Estimated Material Cost">Estimated Material Cost</span>
              </article>
            </section>
            <section data-optimization-delta-strip data-optimization-delta-strip-schema="structure-viewer-optimization-delta-strip.v1">
              <article data-optimization-delta-row data-optimization-delta-key="steel">Optimization Summary After -6.8%</article>
            </section>
            <section id="analysis-cockpit-chart-strip">
              <article class="analysis-chart-panel" data-lower-chart-evidence-schema="structure-viewer-lower-chart-evidence.v1" data-lower-chart-evidence-status="ready">
                <div class="analysis-chart-axis-receipt" data-lower-chart-axis-receipt data-lower-chart-schema="structure-viewer-lower-chart-evidence.v1" data-lower-chart-kind="story-drift" data-lower-chart-scale-mode="shared-original-optimized">Drift axis evidence</div>
              </article>
            </section>
            <section data-delivery-review-receipt><span class="delivery-review-receipt__row">Delivery receipt</span></section>
            <section data-material-member-catalog>
              <div data-material-model-parity data-material-model-parity-schema="structure-viewer-material-model-parity.v1">
                <span data-material-model-parity-row data-material-model-parity-row-key="library">Material Model Lock buildMaterialModelParityModel renderMaterialModelParityPanel structure-viewer-material-model-parity.v1 __STRUCTURE_VIEWER_MATERIAL_MODEL_PARITY_STATE__</span>
              </div>
              <div data-material-model-signature-ledger data-material-model-signature-ledger-schema="structure-viewer-material-model-signature-ledger.v1">
                <button data-material-model-signature-row data-material-model-signature-token-count="12">
                  All Material Models buildMaterialModelSignatureLedgerModel renderMaterialModelSignatureLedgerPanel structure-viewer-material-model-signature-ledger.v1 __STRUCTURE_VIEWER_MATERIAL_MODEL_SIGNATURE_LEDGER_STATE__
                </button>
              </div>
              <div data-material-model-demand-atlas data-material-model-demand-atlas-schema="structure-viewer-material-model-demand-atlas.v1">
                <button data-material-model-demand-row data-material-model-force-row-count="4">
                  Material Model Demand Atlas buildMaterialModelDemandAtlasModel renderMaterialModelDemandAtlasPanel structure-viewer-material-model-demand-atlas.v1 __STRUCTURE_VIEWER_MATERIAL_MODEL_DEMAND_ATLAS_STATE__
                </button>
              </div>
              <div data-material-model-force-envelope data-material-model-force-envelope-schema="structure-viewer-material-model-force-envelope.v1">
                <button data-material-model-force-envelope-row data-material-model-force-envelope-row-material-id="M1">
                  <svg data-material-model-force-envelope-svg viewBox="0 0 100 56">
                    <path d="M8 46 L92 12"></path>
                    <circle data-material-model-force-envelope-point data-material-model-force-envelope-point-combination="ULS1" cx="8" cy="46" r="2"></circle>
                  </svg>
                  Material Model Force Envelope buildMaterialModelForceEnvelopeModel renderMaterialModelForceEnvelopePanel structure-viewer-material-model-force-envelope.v1 __STRUCTURE_VIEWER_MATERIAL_MODEL_FORCE_ENVELOPE_STATE__
                </button>
              </div>
              <div data-material-model-capacity-envelope data-material-model-capacity-envelope-schema="structure-viewer-material-model-capacity-envelope.v1">
                <button data-material-model-capacity-envelope-row data-material-model-capacity-envelope-row-source-capacity="1200" data-material-model-capacity-envelope-row-estimated-capacity="1180">
                  <svg data-material-model-capacity-envelope-svg viewBox="0 0 100 56">
                    <path d="M8 46 L92 12"></path>
                    <circle data-material-model-capacity-envelope-point data-material-model-capacity-envelope-point-combination="ULS1" cx="8" cy="46" r="2"></circle>
                  </svg>
                  Material Model Capacity Envelope buildMaterialModelCapacityEnvelopeModel renderMaterialModelCapacityEnvelopePanel structure-viewer-material-model-capacity-envelope.v1 __STRUCTURE_VIEWER_MATERIAL_MODEL_CAPACITY_ENVELOPE_STATE__
                </button>
              </div>
              <div data-material-force-interaction data-material-force-interaction-schema="structure-viewer-material-force-interaction.v1">
                <button data-material-force-row data-material-force-member-sample="C-21">Material-Force Interaction buildMaterialForceInteractionModel renderMaterialForceInteractionPanel structure-viewer-material-force-interaction.v1 __STRUCTURE_VIEWER_MATERIAL_FORCE_INTERACTION_STATE__</button>
              </div>
              <div data-material-coverage-readiness data-material-coverage-schema="structure-viewer-material-coverage-readiness.v1">
                <span data-material-coverage-check data-material-coverage-check-status="pass">Material definitions</span>
              </div>
              <div data-material-constitutive-lens data-material-constitutive-schema="structure-viewer-material-constitutive-lens.v1">
                <button data-material-constitutive-row data-material-id="M1">Steel bilinear Concrete damage-plasticity</button>
              </div>
              <div data-material-stress-strain-curves data-material-stress-strain-curves-schema="structure-viewer-material-stress-strain-curves.v1">
                <button data-material-stress-strain-curve-row data-material-id="M1">Stress-Strain Curves buildMaterialStressStrainCurvesModel</button>
              </div>
              <button data-material-catalog-row="M1"><span class="material-catalog-row__props">E 2.05e8</span></button>
              <div data-material-family-coverage data-material-family-count="2" data-known-material-family-count="2" data-material-family-ontology-count="45">
                <span data-material-family-chip data-material-family="steel">Structural steel</span>
                <span data-material-family-chip data-material-family="concrete">Concrete</span>
              </div>
              <div data-material-section-schedule data-material-section-schedule-count="1">
                <button data-material-section-row data-material-id="M1" data-section-id="S1">STEEL SM355 H-400x200 material_section_schedule_count</button>
              </div>
              <div data-section-schedule data-section-material-schedule-count="1">
                <button data-section-schedule-row data-section-id="S1">H-400x200 STEEL SM355 section_material_schedule_count</button>
              </div>
            </section>
            <section id="contour-section" data-stage-results-priority="first-stage-viewport" data-contour-scale-evidence><div data-contour-scale-ticks>Contour ticks</div></section>
            <section id="loadcases-section" data-stage-loadcases-priority="after-results" class="load-case-evidence-row" data-load-case-status="Governing">Load evidence</section>
            <section data-utilization-heatmap-evidence><div class="analysis-heatmap-receipt">Heatmap evidence</div></section>
            <section data-viewport-tool-rail><button data-viewport-tool-render-mode="contour">Contour</button></section>
            <section data-stage-overlay-receipt>
              <div data-stage-overlay-visual-evidence>
                <span data-stage-overlay-load-key><i class="stage-overlay-legend-swatch--load"></i>Vectors</span>
                <span data-stage-overlay-support-key><i class="stage-overlay-legend-swatch--support"></i>Supports</span>
              </div>
              3D Overlay Receipt
            </section>
            <section data-stage-load-support-glyphs data-stage-load-support-glyphs-schema="structure-viewer-stage-load-support-glyphs.v1">
              <span data-stage-load-glyph data-stage-load-glyph-projection="projected">+X</span>
              <span data-stage-support-glyph data-stage-support-glyph-projection="projected">Support</span>
            </section>
            <section data-stage-load-combination-force-glyphs data-stage-load-combination-force-glyphs-schema="structure-viewer-stage-load-combination-force-glyphs.v1">
              <button data-stage-load-combination-force-glyph data-stage-load-combination-force-glyph-member="C-21" data-stage-load-combination-force-glyph-projection="projected">Load Combination Force Glyph renderStageLoadCombinationForceGlyphs positionStageLoadCombinationForceGlyphs structure-viewer-stage-load-combination-force-glyphs.v1</button>
            </section>
            <section data-stage-force-demand-contour data-stage-force-demand-contour-schema="structure-viewer-stage-force-demand-contour.v1">
              <button data-stage-force-demand-contour-marker data-stage-force-demand-member="C-21" data-stage-force-demand-projection="projected">
                Stage Force Demand Contour renderStageForceDemandContour positionStageForceDemandContour structure-viewer-stage-force-demand-contour.v1 __STRUCTURE_VIEWER_STAGE_FORCE_DEMAND_CONTOUR_STATE__
              </button>
            </section>
            <section data-stage-material-model-demand-badges data-stage-material-model-demand-badges-schema="structure-viewer-stage-material-model-demand-badges.v1">
              <button data-stage-material-model-demand-badge data-stage-material-model-demand-member="C-21" data-stage-material-model-demand-force-backed="true" data-stage-material-model-demand-projection="projected">
                Stage Material Model Demand Badges buildStageMaterialModelDemandBadgesModel renderStageMaterialModelDemandBadges positionStageMaterialModelDemandBadges structure-viewer-stage-material-model-demand-badges.v1 __STRUCTURE_VIEWER_STAGE_MATERIAL_MODEL_DEMAND_BADGES_STATE__
              </button>
            </section>
            <section data-stage-material-force-ribbons data-stage-material-force-ribbons-schema="structure-viewer-stage-material-force-ribbons.v1">
              <button data-stage-material-force-ribbon data-stage-material-force-member="C-21" data-stage-material-force-axial="1" data-stage-material-force-projection="projected">
                Stage Material Force Ribbons buildStageMaterialForceRibbonsModel renderStageMaterialForceRibbons positionStageMaterialForceRibbons structure-viewer-stage-material-force-ribbons.v1 __STRUCTURE_VIEWER_STAGE_MATERIAL_FORCE_RIBBONS_STATE__
              </button>
            </section>
            <section data-stage-material-force-envelope data-stage-material-force-envelope-schema="structure-viewer-stage-material-force-envelope.v1">
              <button data-stage-material-force-envelope-card data-stage-material-force-envelope-member="C-21" data-stage-material-force-envelope-projection="projected">
                <svg data-stage-material-force-envelope-svg viewBox="0 0 100 32">
                  <path d="M8 25 L92 5"></path>
                  <circle data-stage-material-force-envelope-point data-stage-material-force-envelope-point-combination="ULS1" cx="8" cy="25" r="2"></circle>
                </svg>
                Stage Material Force Envelope buildStageMaterialForceEnvelopeModel renderStageMaterialForceEnvelope positionStageMaterialForceEnvelope structure-viewer-stage-material-force-envelope.v1 __STRUCTURE_VIEWER_STAGE_MATERIAL_FORCE_ENVELOPE_STATE__
              </button>
            </section>
            <section data-stage-material-capacity-envelope data-stage-material-capacity-envelope-schema="structure-viewer-stage-material-capacity-envelope.v1">
              <button data-stage-material-capacity-envelope-card data-stage-material-capacity-envelope-member="C-21" data-stage-material-capacity-envelope-source-capacity-count="1" data-stage-material-capacity-envelope-estimated-capacity-count="1" data-stage-material-capacity-envelope-projection="projected">
                <svg data-stage-material-capacity-envelope-svg viewBox="0 0 100 32">
                  <path d="M8 25 L92 5"></path>
                  <circle data-stage-material-capacity-envelope-point data-stage-material-capacity-envelope-point-combination="ULS1" cx="8" cy="25" r="2"></circle>
                </svg>
                Stage Material Capacity Envelope buildStageMaterialCapacityEnvelopeModel renderStageMaterialCapacityEnvelope positionStageMaterialCapacityEnvelope structure-viewer-stage-material-capacity-envelope.v1 __STRUCTURE_VIEWER_STAGE_MATERIAL_CAPACITY_ENVELOPE_STATE__
              </button>
            </section>
            <button id="btn-contour" onclick="setRenderMode('contour')">Contour</button>
            <section data-stage-result-callout-anchors data-stage-result-callout-anchor-schema="structure-viewer-stage-result-callouts.v3" data-stage-result-callout-anchor-status="ready" data-stage-result-callout-anchor-count="4">
              <span data-stage-result-callout-anchor data-stage-result-callout-anchor-key="critical-member" data-stage-result-callout-anchor-kind="critical-member" data-stage-result-callout-anchor-projection="projected">Critical</span>
            </section>
            <section data-stage-result-callouts data-stage-result-callouts-schema="structure-viewer-stage-result-callouts.v3" data-stage-result-callouts-status="ready" data-stage-result-callout-count="4">
              <button data-stage-result-callout data-stage-result-callout-key="critical-member" data-stage-callout-focus-member="C-21" data-stage-result-callout-full-label="Critical Member" data-stage-result-callout-source="Critical member table" data-stage-result-callout-source-type="source" data-stage-result-callout-load-case="Pushover X+" data-stage-result-callout-step="18/20" data-stage-result-callout-anchor-kind="critical-member" data-stage-result-callout-anchor-label="Critical member focus" data-stage-result-callout-projection="projected">
                <strong data-stage-result-callout-full-value="C-21">C-21</strong>
              </button>
            </section>
            <section data-stage-critical-hotspots data-stage-critical-hotspots-schema="structure-viewer-stage-critical-hotspots.v1">
              <button data-stage-critical-hotspot data-stage-critical-hotspot-member="C-21">Critical Hotspot C-21</button>
            </section>
            <section data-stage-story-ruler data-stage-story-ruler-schema="structure-viewer-stage-story-ruler.v1">
              <button data-stage-story-ruler-row data-stage-story-label="Story 21">Story Level S21</button>
            </section>
            <section data-stage-drift-bands data-stage-drift-bands-schema="structure-viewer-stage-drift-bands.v1">
              <button data-stage-drift-band data-stage-drift-band-label="Story 21">Drift Band Limit</button>
            </section>
            <section data-stage-story-force-flow-bands data-stage-story-force-flow-bands-schema="structure-viewer-stage-story-force-flow-bands.v1">
              <button data-stage-story-force-flow-band data-stage-story-force-flow-story="Story 21" data-stage-story-force-flow-projection="projected">
                Story Force Bands renderStageStoryForceFlowBands positionStageStoryForceFlowBands structure-viewer-stage-story-force-flow-bands.v1 __STRUCTURE_VIEWER_STAGE_STORY_FORCE_FLOW_BANDS_STATE__
              </button>
            </section>
            <section data-stage-result-receipt>Result Receipt</section>
            <section data-analysis-timeline-footer data-analysis-timeline-schema="structure-viewer-analysis-timeline-footer.v1">
              <button data-analysis-timeline-step-tick data-analysis-timeline-tick-status="active">Step 18</button>
            </section>
            <section data-result-step-schedule>
              <button data-result-step-row data-result-step="18" data-result-step-active="true">Step 18 structure-viewer-result-step-schedule.v1</button>
            </section>
            <section data-result-envelope>
              <button data-result-envelope-row data-result-envelope-member-id="C-21">Result Envelope structure-viewer-result-envelope.v1</button>
            </section>
            <section data-force-flow-lens data-force-flow-schema="structure-viewer-force-flow-lens.v1">
              <button data-force-flow-row data-force-flow-member-id="C-21">Applied Load Path renderForceFlowLensPanel structure-viewer-force-flow-lens.v1</button>
            </section>
            <section data-story-force-flow-ledger data-story-force-flow-schema="structure-viewer-story-force-flow-ledger.v1">
              <button data-story-force-flow-row data-story-force-flow-axial-total="1200" data-story-force-flow-shear-total="650" data-story-force-flow-moment-total="330">
                Story Force Ledger buildStoryForceFlowLedgerModel renderStoryForceFlowLedgerPanel structure-viewer-story-force-flow-ledger.v1 __STRUCTURE_VIEWER_STORY_FORCE_FLOW_LEDGER_STATE__
              </button>
            </section>
            <section data-load-combination-force-matrix data-load-combination-force-schema="structure-viewer-load-combination-force-matrix.v1" data-load-combination-force-stepper-schema="structure-viewer-load-combination-force-stepper.v1">
              <button data-load-combination-force-stepper data-load-combination-force-step-combination="ULS1">setLoadCombinationForceSelection structure-viewer-load-combination-force-stepper.v1</button>
              <button data-load-combination-force-row data-load-combination-force-member-id="C-21">Load Combination Matrix buildLoadCombinationForceMatrixModel structure-viewer-load-combination-force-matrix.v1</button>
            </section>
            <section data-member-force-diagram data-member-force-diagram-schema="structure-viewer-member-force-diagram.v1">
              <button data-member-force-diagram-row data-member-force-diagram-member="C-21">
                <svg data-member-force-diagram-svg viewBox="0 0 100 56"><path d="M8 28 H92"></path></svg>
                Member Force Diagram buildMemberForceDiagramModel renderMemberForceDiagramPanel structure-viewer-member-force-diagram.v1
              </button>
            </section>
            <section data-member-force-envelope data-member-force-envelope-schema="structure-viewer-member-force-envelope.v1">
              <button data-member-force-envelope-row data-member-force-envelope-member="C-21">
                <svg data-member-force-envelope-svg viewBox="0 0 100 56"><path d="M8 44 L92 14"></path></svg>
                Member Force Envelope buildMemberForceEnvelopeModel renderMemberForceEnvelopePanel structure-viewer-member-force-envelope.v1
              </button>
            </section>
            <section data-member-force-history data-member-force-history-schema="structure-viewer-member-force-history.v1">
              <button data-member-force-history-row data-member-force-history-member="C-21">
                <svg data-member-force-history-svg viewBox="0 0 100 56"><path d="M8 46 L92 14"></path><circle data-member-force-history-point cx="8" cy="46" r="2"></circle></svg>
                Member Force History buildMemberForceHistoryModel renderMemberForceHistoryPanel structure-viewer-member-force-history.v1 __STRUCTURE_VIEWER_MEMBER_FORCE_HISTORY_STATE__
              </button>
            </section>
            <section data-member-material-nonlinear-state data-member-material-nonlinear-schema="structure-viewer-member-material-nonlinear-state.v1">
              <button data-member-material-nonlinear-row data-member-material-nonlinear-material-id="M1">
                <svg data-member-material-nonlinear-svg viewBox="0 0 100 56">
                  <path d="M8 48 L92 14"></path>
                  <circle data-member-material-nonlinear-yield-marker cx="46" cy="28" r="2"></circle>
                  <circle data-member-material-nonlinear-demand-marker cx="70" cy="18" r="3"></circle>
                </svg>
                Member Material State buildMemberMaterialNonlinearStateModel renderMemberMaterialNonlinearStatePanel structure-viewer-member-material-nonlinear-state.v1 __STRUCTURE_VIEWER_MEMBER_MATERIAL_NONLINEAR_STATE__
              </button>
              <button data-member-material-nonlinear-force-row data-member-material-nonlinear-force-combination="ULS1">source force row</button>
            </section>
            <section data-member-section-capacity data-member-section-capacity-schema="structure-viewer-member-section-capacity.v1">
              <button data-member-section-capacity-row data-member-section-capacity-source-capacity="1200" data-member-section-capacity-estimated-capacity="1180">
                Section Capacity Check buildMemberSectionCapacityModel renderMemberSectionCapacityPanel structure-viewer-member-section-capacity.v1 __STRUCTURE_VIEWER_MEMBER_SECTION_CAPACITY_STATE__
              </button>
            </section>
            <section data-member-force-playback data-member-force-playback-schema="structure-viewer-member-force-playback.v1">
              <button data-member-force-playback-action="play">Play</button>
              <button data-member-force-playback-frame data-member-force-playback-combination="ULS1">Member Force Playback buildMemberForcePlaybackModel renderMemberForcePlaybackPanel structure-viewer-member-force-playback.v1 __STRUCTURE_VIEWER_MEMBER_FORCE_PLAYBACK_STATE__</button>
            </section>
            <section data-stage-member-force-playback-trail data-stage-member-force-playback-trail-schema="structure-viewer-stage-member-force-playback-trail.v1">
              <button data-stage-member-force-playback-trail-frame data-stage-member-force-playback-trail-combination="ULS1">Stage Member Force Playback Trail buildStageMemberForcePlaybackTrailModel renderStageMemberForcePlaybackTrail positionStageMemberForcePlaybackTrail structure-viewer-stage-member-force-playback-trail.v1 __STRUCTURE_VIEWER_STAGE_MEMBER_FORCE_PLAYBACK_TRAIL_STATE__</button>
            </section>
            <section data-stage-member-force-vector-field data-stage-member-force-vector-field-schema="structure-viewer-stage-member-force-vector-field.v1">
              <button data-stage-member-force-vector data-stage-member-force-vector-kind="axial" data-stage-member-force-vector-combination="ULS1">Stage Member Force Vector Field buildStageMemberForceVectorFieldModel renderStageMemberForceVectorField positionStageMemberForceVectorField structure-viewer-stage-member-force-vector-field.v1 __STRUCTURE_VIEWER_STAGE_MEMBER_FORCE_VECTOR_FIELD_STATE__</button>
            </section>
            <section data-stage-member-material-state-badge data-stage-member-material-state-badge-schema="structure-viewer-stage-member-material-state-badge.v1">
              <button data-stage-member-material-state-card data-stage-member-material-state-member="C-21" data-stage-member-material-state-material-id="M1" data-stage-member-material-state-projection="projected">
                Stage Member Material State Badge buildStageMemberMaterialStateBadgeModel renderStageMemberMaterialStateBadge positionStageMemberMaterialStateBadge structure-viewer-stage-member-material-state-badge.v1 __STRUCTURE_VIEWER_STAGE_MEMBER_MATERIAL_STATE_BADGE_STATE__
              </button>
            </section>
            <section data-critical-triage data-critical-triage-schema="structure-viewer-critical-triage.v1" data-critical-members-compact-table-schema="structure-viewer-critical-members-compact-table.v1">
              <div data-critical-members-compact-head data-critical-members-compact-table data-critical-members-compact-table-schema="structure-viewer-critical-members-compact-table.v1"><span>ID</span><span>D/C</span><span>Drift</span><span>Status</span><span>Recommended Change</span></div>
              <button data-critical-triage-row data-critical-members-compact-row data-critical-triage-member-id="C-21">Critical Members Critical Triage D/C</button>
            </section>
            <section data-panel-zone-evidence data-panel-zone-schema="structure-viewer-panel-zone-evidence.v1">
              <button data-panel-zone-member-row data-panel-zone-member-id="26705">Panel Zone / Joint Evidence</button>
            </section>
            <button data-panel-zone-stage-badge data-panel-zone-stage-schema="structure-viewer-panel-zone-stage-badge.v1" data-panel-zone-stage-member="26705">Panel Zone Stage Badge</button>
            <section data-drawing-handoff-panel data-drawing-handoff-schema="structure-viewer-drawing-handoff-panel.v2" data-drawing-handoff-deep-link-ready="true">
              <span data-drawing-handoff-receipt>
                <span data-drawing-handoff-receipt-row="active-sheet">Optimization Summary</span>
              </span>
              <span data-drawing-material-parity-ledger data-drawing-material-parity-schema="structure-viewer-drawing-material-parity-ledger.v1">
                <span data-drawing-material-parity-row data-drawing-material-parity-row-key="material-library">
                  Drawing Material Parity buildDrawingMaterialParityLedgerModel structure-viewer-drawing-material-parity-ledger.v1 __STRUCTURE_VIEWER_DRAWING_MATERIAL_PARITY_LEDGER_STATE__
                </span>
              </span>
              <span data-drawing-source-detail-ledger data-drawing-source-detail-schema="structure-viewer-drawing-source-detail-ledger.v1">
                <span data-drawing-source-detail-row data-drawing-source-detail-row-key="original-detail">
                  Original Drawing Detail buildDrawingSourceDetailLedgerModel structure-viewer-drawing-source-detail-ledger.v1 __STRUCTURE_VIEWER_DRAWING_SOURCE_DETAIL_LEDGER_STATE__
                </span>
              </span>
              <span data-drawing-sheet-detail-matrix data-drawing-sheet-detail-schema="structure-viewer-drawing-sheet-detail-matrix.v1">
                <span data-drawing-sheet-detail-row data-drawing-sheet-detail-row-sheet="S-001">
                  Drawing Sheet Details buildDrawingSheetDetailMatrixModel structure-viewer-drawing-sheet-detail-matrix.v1 __STRUCTURE_VIEWER_DRAWING_SHEET_DETAIL_MATRIX_STATE__
                </span>
              </span>
              <span data-drawing-material-model-matrix data-drawing-material-model-matrix-schema="structure-viewer-drawing-material-model-matrix.v1">
                <span data-drawing-material-model-row data-drawing-material-model-row-material-id="M1">
                  Drawing Material Models buildDrawingMaterialModelMatrixModel structure-viewer-drawing-material-model-matrix.v1 __STRUCTURE_VIEWER_DRAWING_MATERIAL_MODEL_MATRIX_STATE__
                </span>
              </span>
              <span data-drawing-material-constitutive-register data-drawing-material-constitutive-register-schema="structure-viewer-drawing-material-constitutive-register.v1">
                <span data-drawing-material-constitutive-row data-drawing-material-constitutive-row-material-id="M1">
                  Drawing Material Constitutive Register buildDrawingMaterialConstitutiveRegisterModel structure-viewer-drawing-material-constitutive-register.v1 __STRUCTURE_VIEWER_DRAWING_MATERIAL_CONSTITUTIVE_REGISTER_STATE__
                </span>
              </span>
              <span data-drawing-material-curve-evidence data-drawing-material-curve-evidence-schema="structure-viewer-drawing-material-curve-evidence.v1">
                <span data-drawing-material-curve-row data-drawing-material-curve-row-material-id="M1">
                  <svg data-drawing-material-curve-svg></svg>
                  Drawing Material Curve Evidence buildDrawingMaterialCurveEvidenceModel structure-viewer-drawing-material-curve-evidence.v1 __STRUCTURE_VIEWER_DRAWING_MATERIAL_CURVE_EVIDENCE_STATE__
                </span>
              </span>
              <span data-drawing-force-handoff-ledger data-drawing-force-handoff-schema="structure-viewer-drawing-force-handoff-ledger.v1">
                <span data-drawing-force-handoff-row data-drawing-force-handoff-row-key="axial">
                  Drawing Force Handoff buildDrawingForceHandoffLedgerModel structure-viewer-drawing-force-handoff-ledger.v1 __STRUCTURE_VIEWER_DRAWING_FORCE_HANDOFF_LEDGER_STATE__
                </span>
              </span>
              <span data-drawing-force-vector-evidence data-drawing-force-vector-schema="structure-viewer-drawing-force-vector-evidence.v1">
                <span data-drawing-force-vector-row data-drawing-force-vector-row-key="axial">
                  <svg data-drawing-force-vector-svg></svg>
                  Drawing Force Vector Evidence buildDrawingForceVectorEvidenceModel structure-viewer-drawing-force-vector-evidence.v1 __STRUCTURE_VIEWER_DRAWING_FORCE_VECTOR_EVIDENCE_STATE__
                </span>
              </span>
              <span data-drawing-sheet-force-overlay data-drawing-sheet-force-overlay-schema="structure-viewer-drawing-sheet-force-overlay.v1">
                <span data-drawing-sheet-force-overlay-row data-drawing-sheet-force-overlay-row-kind="axial">
                  <svg data-drawing-sheet-force-overlay-svg><g data-drawing-sheet-force-overlay-vector></g></svg>
                  Drawing Sheet Force Overlay buildDrawingSheetForceOverlayModel structure-viewer-drawing-sheet-force-overlay.v1 __STRUCTURE_VIEWER_DRAWING_SHEET_FORCE_OVERLAY_STATE__
                </span>
              </span>
              <span data-drawing-capacity-handoff-ledger data-drawing-capacity-handoff-schema="structure-viewer-drawing-capacity-handoff-ledger.v1">
                <span data-drawing-capacity-handoff-row data-drawing-capacity-handoff-row-material-id="M1">
                  Drawing Capacity Handoff buildDrawingCapacityHandoffLedgerModel structure-viewer-drawing-capacity-handoff-ledger.v1 __STRUCTURE_VIEWER_DRAWING_CAPACITY_HANDOFF_LEDGER_STATE__
                </span>
              </span>
              <span data-drawing-sheet-force-matrix data-drawing-sheet-force-matrix-schema="structure-viewer-drawing-sheet-force-matrix.v1">
                <span data-drawing-sheet-force-row data-drawing-sheet-force-row-sheet="S-001">
                  Drawing Sheet Force Matrix buildDrawingSheetForceMatrixModel structure-viewer-drawing-sheet-force-matrix.v1 __STRUCTURE_VIEWER_DRAWING_SHEET_FORCE_MATRIX_STATE__
                </span>
              </span>
            </section>
            <style>.stage-critical-hotspot small{display:none}.panel-zone-stage-badge__leader{flex-basis:18px}.stage-frame{grid-template-columns:minmax(154px,164px) minmax(0,1fr) 32px}[data-viewer-workflow="model"] [data-viewer-workflow-tab="drawings"]{color:inherit}.panel-toggle-row[data-layer-toggle-row]{} .layer-toggle-group{}</style>
            <script>const THREE = {}; const MATERIAL_FAMILY_ONTOLOGY=[{family:'rail_steel'},{family:'seismic_isolator'},{family:'spring_link'},{family:'fireproofing'},{family:'waterproofing'},{family:'insulation'},{family:'expansion_joint'}]; const material_family_ontology_count=45; const materialLayerMetaById = new Map(); function normalizeLayerVisibilityKey(){ return 'material_family:concrete'; } const drawing_clean='drawing-clean'; window.__STRUCTURE_VIEWER_ANALYSIS_OVERLAY_STATE__ = {}; window.__STRUCTURE_VIEWER_STAGE_LOAD_SUPPORT_GLYPHS_STATE__ = {}; window.__STRUCTURE_VIEWER_STAGE_LOAD_COMBINATION_FORCE_GLYPHS_STATE__ = {}; window.__STRUCTURE_VIEWER_INTEGRATED_REVIEW_NAVIGATOR_STATE__ = {}; window.__STRUCTURE_VIEWER_STAGE_RESULT_CALLOUTS_STATE__ = {}; window.__STRUCTURE_VIEWER_CRITICAL_TRIAGE_STATE__ = {}; window.__STRUCTURE_VIEWER_OPTIMIZATION_DELTA_STRIP_STATE__ = {}; window.__STRUCTURE_VIEWER_FORCE_FLOW_LENS_STATE__ = {}; window.__STRUCTURE_VIEWER_LOAD_COMBINATION_FORCE_MATRIX_STATE__ = {}; window.__STRUCTURE_VIEWER_MEMBER_FORCE_DIAGRAM_STATE__ = {}; window.__STRUCTURE_VIEWER_MEMBER_FORCE_ENVELOPE_STATE__ = {}; window.__STRUCTURE_VIEWER_MEMBER_FORCE_HISTORY_STATE__ = {}; window.__STRUCTURE_VIEWER_MEMBER_MATERIAL_NONLINEAR_STATE__ = {}; window.__STRUCTURE_VIEWER_STAGE_MEMBER_MATERIAL_STATE_BADGE_STATE__ = {}; window.__STRUCTURE_VIEWER_DRAWING_MATERIAL_PARITY_LEDGER_STATE__ = {}; window.__STRUCTURE_VIEWER_DRAWING_SOURCE_DETAIL_LEDGER_STATE__ = {}; window.__STRUCTURE_VIEWER_DRAWING_SHEET_DETAIL_MATRIX_STATE__ = {}; window.__STRUCTURE_VIEWER_DRAWING_MATERIAL_MODEL_MATRIX_STATE__ = {}; window.__STRUCTURE_VIEWER_DRAWING_FORCE_HANDOFF_LEDGER_STATE__ = {}; window.__STRUCTURE_VIEWER_DRAWING_FORCE_VECTOR_EVIDENCE_STATE__ = {}; window.__STRUCTURE_VIEWER_DRAWING_SHEET_FORCE_OVERLAY_STATE__ = {}; window.__STRUCTURE_VIEWER_DRAWING_SHEET_FORCE_MATRIX_STATE__ = {}; window.__STRUCTURE_VIEWER_MATERIAL_STRESS_STRAIN_CURVES_STATE__ = {}; function setRenderMode() { return true; } function startNewReviewRun() { return true; } function setTopbarWorkspaceSelection() { return true; } function renderTopbarProjectSelector() { return true; } function openIntegratedReviewNavigator() { return true; } function renderIntegratedReviewNavigator() { return true; } function setIntegratedReviewNavigatorDrawing() { return true; } function setIntegratedReviewNavigatorPreview() { return true; } function openIntegratedReviewActiveSection() { return true; } function renderSourceAdapterMatrix() { return true; } function updateDeformDisplayScale() { return true; } function formatDeformDisplayScale() { return '1.0x'; } function renderKpiReadout() { return true; } function compactKpiChipLabel() { return 'Model est.'; } function renderKpiChip() { return true; } function renderAnalysisResultEvidence() { return true; } function renderOptimizationDeltaStrip() { return true; } function renderStageLoadSupportGlyphs() { return true; } function positionStageLoadSupportGlyphs() { return true; } function renderStageLoadCombinationForceGlyphs() { return true; } function positionStageLoadCombinationForceGlyphs() { return true; } function renderStageCriticalHotspots() { return true; } function positionStageCriticalHotspots() { return true; } function renderStageStoryRuler() { return true; } function positionStageStoryRuler() { return true; } function renderStageDriftBands() { return true; } function positionStageDriftBands() { return true; } function buildAnalysisTimelineFooterModel() { return true; } function renderResultStepSchedule() { return true; } function renderResultEnvelope() { return true; } function renderForceFlowLensPanel() { return true; } function buildForceFlowLensModel() { return true; } function setLoadCombinationForceSelection() { return true; } function renderLoadCombinationForceMatrixPanel() { return true; } function buildLoadCombinationForceMatrixModel() { return true; } function buildMemberForceDiagramModel() { return true; } function renderMemberForceDiagramPanel() { return true; } function buildMemberForceEnvelopeModel() { return true; } function renderMemberForceEnvelopePanel() { return true; } function buildMemberForceHistoryModel() { return true; } function renderMemberForceHistoryPanel() { return true; } function buildMemberMaterialNonlinearStateModel() { return true; } function renderMemberMaterialNonlinearStatePanel() { return true; } function buildStageMemberMaterialStateBadgeModel() { return true; } function renderStageMemberMaterialStateBadge() { return true; } function positionStageMemberMaterialStateBadge() { return true; } function buildDrawingMaterialParityLedgerModel() { return true; } function buildDrawingSourceDetailLedgerModel() { return true; } function buildDrawingSheetDetailMatrixModel() { return true; } function buildDrawingMaterialModelMatrixModel() { return true; } function buildDrawingForceHandoffLedgerModel() { return true; } function buildDrawingForceVectorEvidenceModel() { return true; } function buildDrawingSheetForceOverlayModel() { return true; } function buildDrawingSheetForceMatrixModel() { return true; } function renderCriticalTriagePanel() { return true; } function renderPanelZoneEvidencePanel() { return true; } function renderPanelZoneStageBadge() { return true; } function positionPanelZoneStageBadge() { return true; } function renderDeliveryReviewReceipt() { return true; } function renderMaterialMemberCatalogPanel() { return true; } function buildMaterialCoverageReadinessModel() { return true; } function buildMaterialConstitutiveLensModel() { return true; } function buildMaterialStressStrainCurvesModel() { return true; } const SOURCE_ADAPTER_SCHEMA='structure-viewer-source-adapter-matrix.v1'; const INTEGRATED_REVIEW_NAVIGATOR_SCHEMA='structure-viewer-integrated-review-navigator.v1'; const INTEGRATED_REVIEW_PREVIEW_SCHEMA='structure-viewer-integrated-review-preview.v1'; const STAGE_RESULT_CALLOUTS_SCHEMA='structure-viewer-stage-result-callouts.v3'; const STAGE_LOAD_SUPPORT_GLYPHS_SCHEMA='structure-viewer-stage-load-support-glyphs.v1'; const STAGE_LOAD_COMBINATION_FORCE_GLYPHS_SCHEMA='structure-viewer-stage-load-combination-force-glyphs.v1'; const STAGE_CRITICAL_HOTSPOTS_SCHEMA='structure-viewer-stage-critical-hotspots.v1'; const STAGE_STORY_RULER_SCHEMA='structure-viewer-stage-story-ruler.v1'; const STAGE_DRIFT_BANDS_SCHEMA='structure-viewer-stage-drift-bands.v1'; const CRITICAL_TRIAGE_SCHEMA='structure-viewer-critical-triage.v1'; const CRITICAL_MEMBERS_COMPACT_TABLE_SCHEMA='structure-viewer-critical-members-compact-table.v1'; const OPTIMIZATION_DELTA_STRIP_SCHEMA='structure-viewer-optimization-delta-strip.v1'; const DELIVERY_RECEIPT_SCHEMA='structure-viewer-delivery-review-receipt.v1'; const ANALYSIS_TIMELINE_FOOTER_SCHEMA='structure-viewer-analysis-timeline-footer.v1'; const RESULT_STEP_SCHEDULE_SCHEMA='structure-viewer-result-step-schedule.v1'; const RESULT_ENVELOPE_SCHEMA='structure-viewer-result-envelope.v1'; const FORCE_FLOW_LENS_SCHEMA='structure-viewer-force-flow-lens.v1'; const LOAD_COMBINATION_FORCE_MATRIX_SCHEMA='structure-viewer-load-combination-force-matrix.v1'; const LOAD_COMBINATION_FORCE_STEPPER_SCHEMA='structure-viewer-load-combination-force-stepper.v1'; const MEMBER_FORCE_DIAGRAM_SCHEMA='structure-viewer-member-force-diagram.v1'; const MEMBER_FORCE_ENVELOPE_SCHEMA='structure-viewer-member-force-envelope.v1'; const MEMBER_FORCE_HISTORY_SCHEMA='structure-viewer-member-force-history.v1'; const MEMBER_MATERIAL_NONLINEAR_STATE_SCHEMA='structure-viewer-member-material-nonlinear-state.v1'; const STAGE_MEMBER_MATERIAL_STATE_BADGE_SCHEMA='structure-viewer-stage-member-material-state-badge.v1'; const DRAWING_MATERIAL_PARITY_LEDGER_SCHEMA='structure-viewer-drawing-material-parity-ledger.v1'; const DRAWING_SOURCE_DETAIL_LEDGER_SCHEMA='structure-viewer-drawing-source-detail-ledger.v1'; const DRAWING_SHEET_DETAIL_MATRIX_SCHEMA='structure-viewer-drawing-sheet-detail-matrix.v1'; const DRAWING_MATERIAL_MODEL_MATRIX_SCHEMA='structure-viewer-drawing-material-model-matrix.v1'; const DRAWING_FORCE_HANDOFF_LEDGER_SCHEMA='structure-viewer-drawing-force-handoff-ledger.v1'; const DRAWING_FORCE_VECTOR_EVIDENCE_SCHEMA='structure-viewer-drawing-force-vector-evidence.v1'; const DRAWING_SHEET_FORCE_OVERLAY_SCHEMA='structure-viewer-drawing-sheet-force-overlay.v1'; const DRAWING_SHEET_FORCE_MATRIX_SCHEMA='structure-viewer-drawing-sheet-force-matrix.v1'; const PANEL_ZONE_SCHEMA='structure-viewer-panel-zone-evidence.v1'; const PANEL_ZONE_STAGE_SCHEMA='structure-viewer-panel-zone-stage-badge.v1'; const MATERIAL_CATALOG_SCHEMA='structure-viewer-material-member-catalog.v1'; const MATERIAL_COVERAGE_READINESS_SCHEMA='structure-viewer-material-coverage-readiness.v1'; const MATERIAL_CONSTITUTIVE_LENS_SCHEMA='structure-viewer-material-constitutive-lens.v1'; const MATERIAL_STRESS_STRAIN_CURVES_SCHEMA='structure-viewer-material-stress-strain-curves.v1';</script>
          </body>
        </html>
        """,
    )
    _write_text(root / "report.pdf", "%PDF-1.4\n%%EOF\n")
    rows = _checksum_rows(root)
    _write_text(
        root / "manifest.json",
        json.dumps(
            {
                "package_claim_boundary": "requires structural engineer review",
                "output_rows": rows,
            },
            indent=2,
        ),
    )
    checksum_rows = _checksum_rows(root)
    _write_text(
        root / "checksums.sha256",
        "".join(f"{row['sha256']}  {row['path']}\n" for row in checksum_rows),
    )
    package = tmp_path / "project_package.zip"
    _write_zip(root, package)
    out = tmp_path / "viewer-smoke.json"

    result = subprocess.run(
        ["node", str(SCRIPT), "--package", str(package), "--out", str(out), "--static-only", "--json"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["browser_skipped"] is True
    assert payload["static_checks"]["pass"] is True
    assert payload["static_checks"]["commercial_cockpit_alignment"]["status"] == "current_cockpit_delivery"
    assert "Workstation delivery viewer smoke: PASS" in result.stdout
