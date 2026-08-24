from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_workbench_v2_is_the_default_product_surface() -> None:
    main = _read("src/main.tsx")

    assert "export function resolveProductSurface" in main
    assert "path.endsWith('/legacy') || hash === '#/legacy'" in main
    assert "return legacyRoute ? 'legacy-app' : 'workbench-v2'" in main
    assert "export function resolveSameOriginJobUrl" in main
    assert "resolved.origin === origin ? resolved.toString() : undefined" in main
    assert "import.meta.env.VITE_JOB_STATUS_URL" in main
    assert "return surface === 'legacy-app' ? (" in main
    assert "<LegacyAppSurface />" in main
    assert "<WorkbenchPage" in main
    assert "jobStatusUrl={jobStatusUrl}" in main
    assert "nativeFrameResultUrl={nativeFrameResultUrl}" in main
    assert "nativeFrameReportUrl={nativeFrameReportUrl}" in main
    assert "window.addEventListener('hashchange', updateSurface)" in main
    assert "window.addEventListener('popstate', updateSurface)" in main
    assert "isWorkbenchV2Route() ? <WorkbenchPage /> : <App />" not in main


def test_legacy_surface_is_explicit_and_has_a_return_path() -> None:
    main = _read("src/main.tsx")
    shell = _read("src/workbench-v2/components/WorkbenchShell.tsx")

    assert "data-legacy-surface" in main
    assert 'href="#/workbench-v2"' in main
    assert "const LegacyApp = lazy(() => import('./App'))" in main
    assert "<LegacyApp />" in main
    assert "<Suspense" in main
    assert "data-legacy-loading" in main
    assert "import App from './App'" not in main
    assert 'href="#/legacy"' in shell
    assert "data-wb2-legacy-link" in shell


def test_static_viewer_remains_an_embedded_workbench_subsystem() -> None:
    viewport = _read("src/workbench-v2/components/ModelViewport.tsx")
    docs = _read("docs/workbench-v2.md")
    viewer_shell_docs = _read("docs/structural-insight-product-shell.md")
    viewer_workspace_docs = _read("docs/structure-viewer-product-workspace.md")

    assert "<iframe" in viewport
    assert "src/structure-viewer/index.html" in viewport
    assert "createViewerBridge" in viewport
    assert "default product shell" in docs
    assert "Static Viewer is embedded as the specialized" in docs
    assert "viewer-local `index.html` surface" in viewer_shell_docs
    assert "Workbench v2 is the default application product shell" in viewer_shell_docs
    assert "Workbench v2 is the default application product shell" in viewer_workspace_docs
    assert "matching provenance" in viewer_workspace_docs


def test_production_build_emits_both_product_entries_and_verifies_delivery() -> None:
    vite = _read("vite.config.ts")
    package = _read("package.json")
    verifier = _read("scripts/verify-workbench-viewer-delivery.mjs")
    e2e = _read("tests/frontend/workbench-v2-e2e.spec.ts")

    assert "const rootHtml" in vite
    assert "const viewerHtml" in vite
    assert "workbench: rootHtml" in vite
    assert "structureViewer: viewerHtml" in vite
    assert "verify-workbench-viewer-delivery.mjs" in package
    assert "distDir, 'src', 'structure-viewer', 'index.html'" in verifier
    assert 'data-si-shell="product"' in verifier
    assert "Viewer entry resolved to the Workbench SPA fallback" in verifier
    assert "Legacy App code leaked into the eager Workbench graph" in verifier
    assert "exactly one lazy legacy App chunk" in verifier
    assert "legacy_marker_count" in verifier
    assert 'body[data-si-shell="product"]' in e2e
