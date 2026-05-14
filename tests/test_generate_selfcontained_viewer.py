from pathlib import Path

from implementation.phase1.generate_selfcontained_viewer import (
    ARTIFACT_PRESET_INPUTS,
    build_inline_vendor_import_urls,
    ensure_local_vendor_bundle,
    extract_viewer_model_payload,
    generate_demo_model,
    generate_selfcontained_html,
    load_model_data,
    resolve_generation_source,
)


def test_generate_selfcontained_html_uses_full_index_template() -> None:
    html = generate_selfcontained_html(generate_demo_model())

    assert '<div id="app">' in html
    assert 'id="embedded-model-data"' in html
    assert "window.__STRUCTURAL_SINGLEFILE__=true;" in html
    assert 'loadInitialModelData' in html
    assert 'id="loading-message"' in html
    assert html.index('id="embedded-model-data"') < html.rindex("</body>")
    assert "<script type=\"application/json\" id=\"embedded-model-data\">" in html
    assert "./index.data.js" not in html
    assert "./viewer-data-loader.js" not in html
    assert "./viewer-model-normalizer.js" not in html
    assert "./viewer-direct-model-normalizer.js" not in html
    assert "./viewer-render-picking-geometry.js" not in html
    assert "./viewer-large-model-picking.js" not in html
    assert "./viewer-pick-broadphase.js" not in html
    assert "./viewer-render-mesh-builders.js" not in html
    assert "./viewer-deformed-rendering.js" not in html
    assert "./viewer-contour-materials.js" not in html
    assert "./viewer-real-drawing-browser-state.js" not in html
    assert "./viewer-real-drawing-quality.js" not in html
    assert "./viewer-real-drawing-panel-events.js" not in html
    assert "./viewer-real-drawing-panel-model.js" not in html
    assert "./viewer-real-drawing-panel-renderer.js" not in html
    assert "./viewer-real-drawing-selection.js" not in html
    assert "./viewer-real-drawing-tree-model.js" not in html
    assert "./viewer-search-results-model.js" not in html
    assert "./viewer-shared-selection-state.js" not in html
    assert "./viewer-side-panel-model.js" not in html
    assert "./viewer-stats-summary.js" not in html
    assert "./viewer-optimization-worker.js" not in html
    assert "new URL('./viewer-model-normalizer.js'" not in html
    assert "new URL('./viewer-direct-model-normalizer.js'" not in html
    assert "new URL('./viewer-render-picking-geometry.js'" not in html
    assert "new URL('./viewer-large-model-picking.js'" not in html
    assert "new URL('./viewer-pick-broadphase.js'" not in html
    assert "new URL('./viewer-render-mesh-builders.js'" not in html
    assert "new URL('./viewer-deformed-rendering.js'" not in html
    assert "new URL('./viewer-contour-materials.js'" not in html
    assert "./design-theme.css" not in html
    assert "inlined from src/structure-viewer/design-theme.css" in html
    assert "cdn.jsdelivr.net" not in html
    assert "unpkg.com" not in html
    assert "https://" not in html
    assert "http://" not in html


def test_generate_selfcontained_html_no_longer_depends_on_window_patch() -> None:
    html = generate_selfcontained_html(generate_demo_model())

    assert 'window.__EMBEDDED_MODEL__ = data' not in html
    assert 'window.__EMBEDDED_MODEL__||generateDemoModel()' not in html
    assert "Failed to parse embedded model data" not in html
    assert "Override: load from embedded data if available" not in html


def test_generate_selfcontained_html_uses_only_inline_module_bootstrap() -> None:
    html = generate_selfcontained_html(generate_demo_model())

    assert "data:text/javascript;base64," in html
    assert html.count("data:text/javascript;base64,") >= 5
    assert "./vendor/three.module.js" not in html
    assert "./vendor/OrbitControls.js" not in html
    assert 'type="importmap"' not in html


def test_build_inline_vendor_import_urls_returns_data_urls() -> None:
    three_url, orbit_url = build_inline_vendor_import_urls()

    assert three_url.startswith("data:text/javascript;base64,")
    assert orbit_url.startswith("data:text/javascript;base64,")
    assert "./vendor/three.module.js" not in orbit_url
    assert "./vendor/OrbitControls.js" not in orbit_url


def test_ensure_local_vendor_bundle_tracks_generated_html_bootstrap(tmp_path: Path) -> None:
    output = tmp_path / "viewer.html"
    html = generate_selfcontained_html(generate_demo_model())
    output.write_text(html, encoding="utf-8")

    copied = ensure_local_vendor_bundle(output)
    copied_names = {path.name for path in copied}
    uses_local_vendor_sidecars = "./vendor/three.module.js" in html or "./vendor/OrbitControls.js" in html

    if uses_local_vendor_sidecars:
        assert copied_names == {"three.module.js", "OrbitControls.js"}
        assert (tmp_path / "vendor" / "three.module.js").is_file()
        assert (tmp_path / "vendor" / "OrbitControls.js").is_file()
    else:
        assert copied_names in (set(), {"three.module.js", "OrbitControls.js"})
        for copied_path in copied:
            assert copied_path.parent == tmp_path / "vendor"
            assert copied_path.is_file()


def test_ensure_local_vendor_bundle_keeps_any_sidecars_under_output_dir(tmp_path: Path) -> None:
    output = tmp_path / "nested" / "viewer.html"
    copied = ensure_local_vendor_bundle(output)

    for copied_path in copied:
        assert copied_path.parent == output.parent / "vendor"
        assert copied_path.is_file()


def test_load_model_data_supports_actual_artifact_preset() -> None:
    model_data, source_label = load_model_data(input_path=None, preset="midas33", demo=False)
    payload = extract_viewer_model_payload(model_data)

    assert source_label == str(ARTIFACT_PRESET_INPUTS["midas33"].relative_to(Path.cwd()))
    assert len(payload.get("nodes", [])) > 1000
    assert len(payload.get("elements", [])) > 1000


def test_generate_selfcontained_html_preserves_nested_artifact_payload() -> None:
    model_data, _ = load_model_data(input_path=None, preset="midas33_pr", demo=False)
    html = generate_selfcontained_html(model_data)

    assert '"model"' in html
    assert '"schema_version"' in html
    assert 'id="embedded-model-data"' in html


def test_resolve_generation_source_defaults_release_artifact_to_midas33() -> None:
    input_path, preset, demo = resolve_generation_source(
        input_path=None,
        preset=None,
        demo=False,
        release_artifact=True,
    )

    assert input_path is None
    assert preset == "midas33"
    assert demo is False
