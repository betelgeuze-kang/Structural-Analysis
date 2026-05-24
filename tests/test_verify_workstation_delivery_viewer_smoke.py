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
          <body>
            <link rel="stylesheet" href="commercial-cockpit-polish.css">
            <main id="viewport" data-stage-overlay-occlusion-budget="dense-model-protagonist" data-stage-dominance-budget="dense-stage-primary"><canvas></canvas></main>
            <nav class="workflow-tab">Model Optimization</nav>
            <select data-shell-project-select onchange="setTopbarWorkspaceSelection(this.value)"><option value="demo::drawing">Demo Drawing</option></select>
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
            <section data-delivery-review-receipt><span class="delivery-review-receipt__row">Delivery receipt</span></section>
            <section data-material-member-catalog>
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
            <button id="btn-contour" onclick="setRenderMode('contour')">Contour</button>
            <section data-stage-callout-focus-member="C-21">Critical Members</section>
            <section data-stage-critical-hotspots data-stage-critical-hotspots-schema="structure-viewer-stage-critical-hotspots.v1">
              <button data-stage-critical-hotspot data-stage-critical-hotspot-member="C-21">Critical Hotspot C-21</button>
            </section>
            <section data-stage-story-ruler data-stage-story-ruler-schema="structure-viewer-stage-story-ruler.v1">
              <button data-stage-story-ruler-row data-stage-story-label="Story 21">Story Level S21</button>
            </section>
            <section data-stage-drift-bands data-stage-drift-bands-schema="structure-viewer-stage-drift-bands.v1">
              <button data-stage-drift-band data-stage-drift-band-label="Story 21">Drift Band Limit</button>
            </section>
            <section data-stage-result-receipt>Result Receipt</section>
            <section data-result-step-schedule>
              <button data-result-step-row data-result-step="18" data-result-step-active="true">Step 18 structure-viewer-result-step-schedule.v1</button>
            </section>
            <section data-result-envelope>
              <button data-result-envelope-row data-result-envelope-member-id="C-21">Result Envelope structure-viewer-result-envelope.v1</button>
            </section>
            <section data-critical-triage data-critical-triage-schema="structure-viewer-critical-triage.v1">
              <button data-critical-triage-row data-critical-triage-member-id="C-21">Critical Triage D/C</button>
            </section>
            <section data-panel-zone-evidence data-panel-zone-schema="structure-viewer-panel-zone-evidence.v1">
              <button data-panel-zone-member-row data-panel-zone-member-id="26705">Panel Zone / Joint Evidence</button>
            </section>
            <button data-panel-zone-stage-badge data-panel-zone-stage-schema="structure-viewer-panel-zone-stage-badge.v1" data-panel-zone-stage-member="26705">Panel Zone Stage Badge</button>
            <section data-drawing-handoff-panel>Optimization Summary</section>
            <style>.stage-critical-hotspot small{display:none}.panel-zone-stage-badge__leader{flex-basis:18px}.stage-frame{grid-template-columns:minmax(154px,164px) minmax(0,1fr) 32px}</style>
            <script>const THREE = {}; const MATERIAL_FAMILY_ONTOLOGY=[{family:'rail_steel'},{family:'seismic_isolator'},{family:'spring_link'},{family:'fireproofing'},{family:'waterproofing'},{family:'insulation'},{family:'expansion_joint'}]; const material_family_ontology_count=45; window.__STRUCTURE_VIEWER_ANALYSIS_OVERLAY_STATE__ = {}; window.__STRUCTURE_VIEWER_STAGE_LOAD_SUPPORT_GLYPHS_STATE__ = {}; window.__STRUCTURE_VIEWER_CRITICAL_TRIAGE_STATE__ = {}; window.__STRUCTURE_VIEWER_OPTIMIZATION_DELTA_STRIP_STATE__ = {}; function setRenderMode() { return true; } function startNewReviewRun() { return true; } function setTopbarWorkspaceSelection() { return true; } function renderTopbarProjectSelector() { return true; } function renderSourceAdapterMatrix() { return true; } function updateDeformDisplayScale() { return true; } function formatDeformDisplayScale() { return '1.0x'; } function renderKpiReadout() { return true; } function compactKpiChipLabel() { return 'Model est.'; } function renderKpiChip() { return true; } function renderAnalysisResultEvidence() { return true; } function renderOptimizationDeltaStrip() { return true; } function renderStageLoadSupportGlyphs() { return true; } function positionStageLoadSupportGlyphs() { return true; } function renderStageCriticalHotspots() { return true; } function positionStageCriticalHotspots() { return true; } function renderStageStoryRuler() { return true; } function positionStageStoryRuler() { return true; } function renderStageDriftBands() { return true; } function positionStageDriftBands() { return true; } function renderResultStepSchedule() { return true; } function renderResultEnvelope() { return true; } function renderCriticalTriagePanel() { return true; } function renderPanelZoneEvidencePanel() { return true; } function renderPanelZoneStageBadge() { return true; } function positionPanelZoneStageBadge() { return true; } function renderDeliveryReviewReceipt() { return true; } function renderMaterialMemberCatalogPanel() { return true; } const SOURCE_ADAPTER_SCHEMA='structure-viewer-source-adapter-matrix.v1'; const STAGE_LOAD_SUPPORT_GLYPHS_SCHEMA='structure-viewer-stage-load-support-glyphs.v1'; const STAGE_CRITICAL_HOTSPOTS_SCHEMA='structure-viewer-stage-critical-hotspots.v1'; const STAGE_STORY_RULER_SCHEMA='structure-viewer-stage-story-ruler.v1'; const STAGE_DRIFT_BANDS_SCHEMA='structure-viewer-stage-drift-bands.v1'; const CRITICAL_TRIAGE_SCHEMA='structure-viewer-critical-triage.v1'; const OPTIMIZATION_DELTA_STRIP_SCHEMA='structure-viewer-optimization-delta-strip.v1'; const DELIVERY_RECEIPT_SCHEMA='structure-viewer-delivery-review-receipt.v1'; const RESULT_STEP_SCHEDULE_SCHEMA='structure-viewer-result-step-schedule.v1'; const RESULT_ENVELOPE_SCHEMA='structure-viewer-result-envelope.v1'; const PANEL_ZONE_SCHEMA='structure-viewer-panel-zone-evidence.v1'; const PANEL_ZONE_STAGE_SCHEMA='structure-viewer-panel-zone-stage-badge.v1'; const MATERIAL_CATALOG_SCHEMA='structure-viewer-material-member-catalog.v1';</script>
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
