from pathlib import Path


def test_primary_webgl_viewers_use_repo_local_three_vendor_assets() -> None:
    for path in [
        Path("src/structure-viewer/index.html"),
        Path("src/structure-viewer/panel_zone.html"),
        Path("src/structure-viewer/demo_viewer.html"),
    ]:
        text = path.read_text(encoding="utf-8")
        assert "./vendor/three.module.js" in text
        assert "./vendor/OrbitControls.js" in text
        assert 'type="importmap"' not in text
        assert "three/addons" not in text
        assert "cdn.jsdelivr.net/npm/three" not in text


def test_vendor_assets_exist() -> None:
    assert Path("src/structure-viewer/vendor/three.module.js").is_file()
    assert Path("src/structure-viewer/vendor/OrbitControls.js").is_file()
