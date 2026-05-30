from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
STRUCTURE_VIEWER_STYLE_SHEETS = (
    ("design-tokens.css", REPO_ROOT / "src" / "structure-viewer" / "design-tokens.css"),
    ("design-theme.css", REPO_ROOT / "src" / "structure-viewer" / "design-theme.css"),
    ("viewer-visual-identity.css", REPO_ROOT / "src" / "structure-viewer" / "viewer-visual-identity.css"),
    ("commercial-cockpit-polish.css", REPO_ROOT / "src" / "structure-viewer" / "commercial-cockpit-polish.css"),
)
STYLESHEET_LINK_RE = re.compile(
    r'<link\s+rel=["\']stylesheet["\']\s+href=["\']\./(?P<name>[^"\']+\.css)["\']\s*/?>',
    re.IGNORECASE,
)
REMOTE_CSS_IMPORT_RE = re.compile(
    r"^\s*@import\s+url\(\s*['\"]?https?://[^)]+?\)\s*;\s*$",
    re.IGNORECASE | re.MULTILINE,
)
LOCAL_CSS_IMPORT_RE = re.compile(
    r"^\s*@import\s+url\(\s*['\"]?\./[^)]+?\)\s*;\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def _strip_remote_css_imports(css: str) -> str:
    css = REMOTE_CSS_IMPORT_RE.sub("", css)
    css = LOCAL_CSS_IMPORT_RE.sub("", css)
    return css.lstrip()


def _inline_stylesheet_link(html: str, filename: str, css_path: Path) -> str:
    css = _strip_remote_css_imports(css_path.read_text(encoding="utf-8")).strip()
    inline_style = f"<style>\n/* inlined from src/structure-viewer/{filename} */\n{css}\n</style>"
    pattern = re.compile(
        rf'<link\s+rel=["\']stylesheet["\']\s+href=["\']\./{re.escape(filename)}["\']\s*/?>',
        re.IGNORECASE,
    )
    inlined_html, replacements = pattern.subn(inline_style, html, count=1)
    if replacements != 1:
        raise RuntimeError(f"Failed to inline {filename} into single-file viewer HTML")
    return inlined_html


def inline_structure_viewer_stylesheets(html: str) -> str:
    for filename, css_path in STRUCTURE_VIEWER_STYLE_SHEETS:
        html = _inline_stylesheet_link(html, filename, css_path)
    return html
