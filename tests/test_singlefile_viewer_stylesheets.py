from __future__ import annotations

from implementation.phase1.singlefile_viewer_support import inline_structure_viewer_stylesheets


def test_inline_structure_viewer_stylesheets_inlines_all_layers() -> None:
    html = (
        '<link rel="stylesheet" href="./design-tokens.css"/>'
        '<link rel="stylesheet" href="./design-theme.css"/>'
        '<link rel="stylesheet" href="./viewer-visual-identity.css"/>'
        '<link rel="stylesheet" href="./commercial-cockpit-polish.css"/>'
    )
    inlined = inline_structure_viewer_stylesheets(html)
    assert "./design-tokens.css" not in inlined
    assert "./viewer-visual-identity.css" not in inlined
    assert "--si-accent-500" in inlined
    assert "inlined from src/structure-viewer/design-theme.css" in inlined
    assert "inlined from src/structure-viewer/viewer-visual-identity.css" in inlined
