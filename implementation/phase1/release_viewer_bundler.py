"""Inline the Structure Viewer ESM graph for offline release artifacts.

This module owns release packaging only. Runtime ingest, state, rendering, and
report behavior stay in the corresponding Viewer JavaScript facades.
"""

from __future__ import annotations

import base64
import json
import re
from pathlib import Path


LOCAL_VIEWER_MODULE_IMPORT_RE = re.compile(
    r"from\s+([\"'])(\./viewer-[^\"']+\.js)\1\s*;?"
)


def _encode_js_module_data_url(module_source: str) -> str:
    encoded = base64.b64encode(module_source.encode("utf-8")).decode("ascii")
    return f"data:text/javascript;base64,{encoded}"


def build_inline_viewer_module_import_urls(viewer_root: Path) -> dict[str, str]:
    """Build deterministic data URLs for every local module reachable from index."""

    root = Path(viewer_root)
    index_html = (root / "index.html").read_text(encoding="utf-8")
    root_imports = sorted(
        {match.group(2) for match in LOCAL_VIEWER_MODULE_IMPORT_RE.finditer(index_html)}
    )
    cache: dict[str, str] = {}
    visiting: set[str] = set()

    def inline_module(module_path: str) -> str:
        if module_path in cache:
            return cache[module_path]
        if module_path in visiting:
            raise RuntimeError(f"Cyclic viewer module import detected: {module_path}")

        source_path = root / module_path.removeprefix("./")
        if not source_path.is_file():
            raise RuntimeError(f"Missing viewer module for single-file export: {module_path}")

        visiting.add(module_path)
        module_source = source_path.read_text(encoding="utf-8")

        def replace_import(match: re.Match[str]) -> str:
            dependency_path = match.group(2)
            return f"from '{inline_module(dependency_path)}';"

        module_source = LOCAL_VIEWER_MODULE_IMPORT_RE.sub(replace_import, module_source)
        visiting.remove(module_path)
        cache[module_path] = _encode_js_module_data_url(module_source)
        return cache[module_path]

    for module_path in root_imports:
        inline_module(module_path)
    return cache


def inline_local_viewer_module_imports(
    html_content: str,
    module_import_urls: dict[str, str],
) -> str:
    """Replace root Viewer ESM imports with their recursively bundled data URLs."""

    for module_path, module_url in module_import_urls.items():
        html_content, _replacement_count = re.subn(
            rf"from\s+['\"]{re.escape(module_path)}['\"];",
            f"from '{module_url}';",
            html_content,
            count=1,
        )
    leftover_imports = sorted(
        {
            match.group(2)
            for match in LOCAL_VIEWER_MODULE_IMPORT_RE.finditer(html_content)
        }
    )
    if leftover_imports:
        raise RuntimeError(
            f"Failed to inline viewer module imports: {', '.join(leftover_imports)}"
        )
    return html_content

def inline_viewer_worker_module_urls(
    html_content: str,
    module_import_urls: dict[str, str],
) -> str:
    """Inline leaf module URLs consumed by the normalization module worker."""

    replacements = {
        "modelNormalizer: new URL('./viewer-model-normalizer.js', import.meta.url).href,": (
            f"modelNormalizer: {json.dumps(module_import_urls['./viewer-model-normalizer.js'])},"
        ),
        "directModelNormalizer: new URL('./viewer-direct-model-normalizer.js', import.meta.url).href,": (
            "directModelNormalizer: "
            f"{json.dumps(module_import_urls['./viewer-direct-model-normalizer.js'])},"
        ),
    }
    for needle, replacement in replacements.items():
        if needle not in html_content:
            raise RuntimeError(f"Failed to inline viewer worker module URL: {needle}")
        html_content = html_content.replace(needle, replacement, 1)
    return html_content
