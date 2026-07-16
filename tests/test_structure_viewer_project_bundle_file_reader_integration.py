from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "src/structure-viewer/index.html"
TEMP_WORKFLOW = (
    ROOT / ".github/workflows/codex-temp-project-bundle-file-handler-patch.yml"
)


def _project_bundle_handler() -> str:
    text = INDEX.read_text(encoding="utf-8")
    match = re.search(
        r"async function previewProjectBundleImportFromInput\(event\)\{\n.*?\n\}"
        r"\nfunction mergeProjectBundleImportPreview\(\)\{",
        text,
        re.DOTALL,
    )
    assert match is not None
    return match.group(0)


def test_runtime_preflights_project_bundle_and_persists_metadata_only() -> None:
    text = INDEX.read_text(encoding="utf-8")
    handler = _project_bundle_handler()

    assert "from './viewer-project-bundle-file-reader.js';" in text
    assert "buildViewerProjectBundleFileFailurePreview," in text
    assert "readViewerProjectBundleFile," in text
    assert "viewerProjectBundleFileMetadata," in text

    assert handler.count("readViewerProjectBundleFile(file)") == 1
    assert "buildViewerProjectBundleImportPreview(bundleRead.payload" in handler
    assert "preview.file_read=viewerProjectBundleFileMetadata(bundleRead);" in handler
    assert "buildViewerProjectBundleFileFailurePreview(err" in handler
    assert "file.text()" not in handler
    assert "JSON.parse(" not in handler
    assert "String(err?.message||err)" not in handler

    metadata_index = handler.index(
        "preview.file_read=viewerProjectBundleFileMetadata(bundleRead);"
    )
    persist_index = handler.index("writeLocalOpsState({")
    assert metadata_index < persist_index


def test_temporary_project_bundle_patch_workflow_is_absent() -> None:
    assert not TEMP_WORKFLOW.exists()
