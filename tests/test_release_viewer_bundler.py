from __future__ import annotations

from pathlib import Path

import pytest

from implementation.phase1.release_viewer_bundler import (
    build_inline_viewer_module_import_urls,
    inline_local_viewer_module_imports,
)


ROOT = Path(__file__).resolve().parents[1]


def test_release_bundler_rejects_a_missing_reachable_module(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text(
        "<script type='module'>import {x} from './viewer-shell.js';</script>",
        encoding="utf-8",
    )
    (tmp_path / "viewer-shell.js").write_text(
        "export {missing} from './viewer-missing.js';",
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="Missing viewer module"):
        build_inline_viewer_module_import_urls(tmp_path)


def test_release_bundler_rejects_a_cycle(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text(
        "<script type='module'>import {a} from './viewer-a.js';</script>",
        encoding="utf-8",
    )
    (tmp_path / "viewer-a.js").write_text(
        "export {b} from './viewer-b.js'; export const a = 1;",
        encoding="utf-8",
    )
    (tmp_path / "viewer-b.js").write_text(
        "export {a} from './viewer-a.js'; export const b = 2;",
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="Cyclic viewer module import"):
        build_inline_viewer_module_import_urls(tmp_path)


def test_release_bundler_fails_if_a_root_import_was_not_replaced() -> None:
    html = "<script type='module'>import {x} from './viewer-shell.js';</script>"

    with pytest.raises(RuntimeError, match="Failed to inline viewer module imports"):
        inline_local_viewer_module_imports(html, {})


def test_release_bundler_inlines_the_neutral_viewer_manifest_projection() -> None:
    urls = build_inline_viewer_module_import_urls(ROOT / "src/structure-viewer")

    assert "./viewer-project-manifest-data.js" in urls
    assert urls["./viewer-project-manifest-data.js"].startswith(
        "data:text/javascript;base64,"
    )
