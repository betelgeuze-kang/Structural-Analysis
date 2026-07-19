from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from implementation.phase1.release_viewer_bundler import (
    build_inline_viewer_module_import_urls,
)


ROOT = Path(__file__).resolve().parents[1]
VIEWER_ROOT = ROOT / "src" / "structure-viewer"
RUNTIME_FACADES = {
    "./viewer-ingest.js",
    "./viewer-renderer.js",
    "./viewer-report.js",
    "./viewer-shell.js",
    "./viewer-state.js",
    "./viewer-storage.js",
}
ALL_MODULES = {
    "viewer-contracts",
    "viewer-ingest",
    "viewer-renderer",
    "viewer-report",
    "viewer-shell",
    "viewer-state",
    "viewer-storage",
}


def test_index_composes_only_runtime_facades() -> None:
    index = (VIEWER_ROOT / "index.html").read_text(encoding="utf-8")
    entry_imports = set(
        re.findall(r"from\s+['\"](\./viewer-[^'\"]+\.js)['\"]\s*;", index)
    )

    assert entry_imports == RUNTIME_FACADES
    assert "createBrowserRuntimeIngestPayloadStorage(window)" in index
    assert "storageGet:key=>window.sessionStorage.getItem(key)" not in index
    assert "storageSet:(key,text)=>window.sessionStorage.setItem(key,text)" not in index


def test_facades_are_explicit_and_documented() -> None:
    docs = (ROOT / "docs" / "structure-viewer-module-boundaries.md").read_text(
        encoding="utf-8"
    )

    for module_name in ALL_MODULES:
        source = VIEWER_ROOT / f"{module_name}.js"
        assert source.is_file(), module_name
        assert f"`{module_name}`" in docs
    assert "`release-viewer-bundler`" in docs
    assert "Workbench v2 is the application product shell" in docs


def test_release_bundler_reaches_facades_and_leaf_modules_deterministically() -> None:
    first = build_inline_viewer_module_import_urls(VIEWER_ROOT)
    second = build_inline_viewer_module_import_urls(VIEWER_ROOT)

    assert first == second
    assert RUNTIME_FACADES.issubset(first)
    assert "./viewer-contracts.js" in first
    assert "./viewer-model-normalizer.js" in first
    assert "./viewer-runtime-ingest-payload-storage.js" in first
    assert all(value.startswith("data:text/javascript;base64,") for value in first.values())


def test_browser_storage_facade_preserves_fail_closed_security_receipt() -> None:
    script = r"""
import {
  createBrowserRuntimeIngestPayloadStorage,
  runtimeIngestStorageReceiptMetadata,
} from './src/structure-viewer/viewer-storage.js';

const browserWindow = {};
Object.defineProperty(browserWindow, 'sessionStorage', {
  get() {
    const error = new Error('sensitive browser detail');
    error.name = 'SecurityError';
    throw error;
  },
});
const adapter = createBrowserRuntimeIngestPayloadStorage(browserWindow);
const result = adapter.read();
console.log(JSON.stringify(runtimeIngestStorageReceiptMetadata(result.receipt)));
"""
    completed = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    receipt = json.loads(completed.stdout)

    assert receipt["display_status"] == "Storage unavailable"
    assert receipt["persistence"] == "none"
    assert receipt["error_code"] == "runtime_ingest_storage_access_denied"
    assert "sensitive browser detail" not in completed.stdout
