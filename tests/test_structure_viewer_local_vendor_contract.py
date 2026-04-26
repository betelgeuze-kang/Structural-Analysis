from pathlib import Path


def test_structure_viewer_vendor_assets_exist() -> None:
    assert Path("src/structure-viewer/vendor/three.module.js").is_file()
    assert Path("src/structure-viewer/vendor/OrbitControls.js").is_file()


def test_index_html_uses_repo_local_vendor_modules() -> None:
    text = Path("src/structure-viewer/index.html").read_text(encoding="utf-8")

    assert "./vendor/three.module.js" in text
    assert "./vendor/OrbitControls.js" in text
    assert "cdn.jsdelivr.net" not in text
