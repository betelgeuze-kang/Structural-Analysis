from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DESIGN_THEME_PATH = REPO_ROOT / "src" / "structure-viewer" / "design-theme.css"
COMMERCIAL_COCKPIT_PATH = REPO_ROOT / "src" / "structure-viewer" / "commercial-cockpit-polish.css"
DESIGN_THEME_LINK_RE = re.compile(
    r'<link\s+rel=["\']stylesheet["\']\s+href=["\']\./design-theme\.css["\']\s*/?>',
    re.IGNORECASE,
)
COMMERCIAL_COCKPIT_LINK_RE = re.compile(
    r'<link\s+rel=["\']stylesheet["\']\s+href=["\']\./commercial-cockpit-polish\.css["\']\s*/?>',
    re.IGNORECASE,
)
REMOTE_CSS_IMPORT_RE = re.compile(
    r"^\s*@import\s+url\(\s*['\"]?https?://[^)]+?\)\s*;\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def _strip_remote_css_imports(css: str) -> str:
    return REMOTE_CSS_IMPORT_RE.sub("", css).lstrip()


def inline_design_theme_stylesheet(html: str) -> str:
    design_theme_css = _strip_remote_css_imports(DESIGN_THEME_PATH.read_text(encoding="utf-8")).strip()
    inline_style = "<style>\n/* inlined from src/structure-viewer/design-theme.css */\n"
    inline_style += f"{design_theme_css}\n</style>"
    inlined_html, replacements = DESIGN_THEME_LINK_RE.subn(inline_style, html, count=1)
    if replacements != 1:
        raise RuntimeError("Failed to inline design-theme.css into single-file viewer HTML")
    return inlined_html


def inline_commercial_cockpit_stylesheet(html: str) -> str:
    cockpit_css = _strip_remote_css_imports(COMMERCIAL_COCKPIT_PATH.read_text(encoding="utf-8")).strip()
    inline_style = "<style>\n/* inlined from src/structure-viewer/commercial-cockpit-polish.css */\n"
    inline_style += f"{cockpit_css}\n</style>"
    inlined_html, replacements = COMMERCIAL_COCKPIT_LINK_RE.subn(inline_style, html, count=1)
    if replacements != 1:
        raise RuntimeError("Failed to inline commercial-cockpit-polish.css into single-file viewer HTML")
    return inlined_html


def inline_structure_viewer_stylesheets(html: str) -> str:
    html = inline_design_theme_stylesheet(html)
    return inline_commercial_cockpit_stylesheet(html)
