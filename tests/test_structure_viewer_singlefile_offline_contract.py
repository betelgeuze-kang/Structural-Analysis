from __future__ import annotations

from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
RELEASE_VIEWERS = [
    ROOT / "implementation" / "phase1" / "release" / "visualization" / "structural_viewer_singlefile.html",
    ROOT / "implementation" / "phase1" / "release" / "visualization" / "charts_viewer_singlefile.html",
    ROOT / "implementation" / "phase1" / "release" / "visualization" / "optimization_history_viewer_singlefile.html",
    ROOT / "implementation" / "phase1" / "release" / "visualization" / "panel_zone_viewer_singlefile.html",
]


def test_release_singlefile_viewers_do_not_depend_on_remote_or_sidecar_assets() -> None:
    forbidden_fragments = [
        "@import url(",
        "fonts.googleapis",
        "https://fonts",
        "./design-theme.css",
        "./charts.data.js",
        "./optimization_history.data.js",
        "./panel_zone.data.js",
        "./index.data.js",
        "./viewer-data-loader.js",
        "./viewer-model-normalizer.js",
        "./viewer-direct-model-normalizer.js",
        "./viewer-render-picking-geometry.js",
        "./viewer-large-model-picking.js",
        "./viewer-pick-broadphase.js",
        "./viewer-render-mesh-builders.js",
        "./viewer-deformed-rendering.js",
        "./viewer-contour-materials.js",
        "./viewer-real-drawing-browser-state.js",
        "./viewer-real-drawing-quality.js",
        "./viewer-real-drawing-panel-events.js",
        "./viewer-real-drawing-panel-model.js",
        "./viewer-real-drawing-panel-renderer.js",
        "./viewer-real-drawing-selection.js",
        "./viewer-real-drawing-tree-model.js",
        "./viewer-search-results-model.js",
        "./viewer-selection-summary-model.js",
        "./viewer-shared-selection-state.js",
        "./viewer-side-panel-model.js",
        "./viewer-stats-summary.js",
        "./vendor/three.module.js",
        "./vendor/OrbitControls.js",
        "cdn.jsdelivr.net",
        "unpkg.com",
    ]

    # The single-file viewers are generated release artifacts under
    # implementation/phase1/release/ (gitignored) and are absent on clean
    # checkouts (CI). Validate every viewer that is present; skip only when none
    # have been generated locally.
    present_viewers = [path for path in RELEASE_VIEWERS if path.exists()]
    if not present_viewers:
        pytest.skip("generated single-file release viewers are absent (clean checkout)")

    for viewer_path in present_viewers:
        text = viewer_path.read_text(encoding="utf-8")
        assert "window.__STRUCTURAL_SINGLEFILE__=true;" in text, viewer_path.name
        assert "inlined from src/structure-viewer/design-theme.css" in text, viewer_path.name
        for fragment in forbidden_fragments:
            assert fragment not in text, f"{viewer_path.name} keeps forbidden fragment {fragment!r}"
