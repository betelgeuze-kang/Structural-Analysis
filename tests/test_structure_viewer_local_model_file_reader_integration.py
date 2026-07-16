from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "src/structure-viewer/index.html"
TEMP_WORKFLOW = (
    ROOT / ".github/workflows/codex-temp-local-model-file-handler-patch.yml"
)


def _file_select_handler() -> str:
    text = INDEX.read_text(encoding="utf-8")
    match = re.search(
        r"async function handleFileSelect\(event\)\s*\{.*?"
        r"\n\}\n\nfunction showLoadingIndicator",
        text,
        re.DOTALL,
    )
    assert match is not None
    return match.group(0)


def _drop_handler() -> str:
    text = INDEX.read_text(encoding="utf-8")
    match = re.search(
        r"dropZone\.addEventListener\('drop', async \(e\) => \{.*?"
        r"\n  \}\);",
        text,
        re.DOTALL,
    )
    assert match is not None
    return match.group(0)


def test_file_select_and_drop_share_the_bounded_model_reader() -> None:
    text = INDEX.read_text(encoding="utf-8")
    select_handler = _file_select_handler()
    drop_handler = _drop_handler()

    assert "from './viewer-local-model-file-reader.js';" in text
    assert "readViewerLocalModelFile," in text
    assert "viewerLocalModelFileFailure," in text

    for handler, action in (
        (select_handler, "selected"),
        (drop_handler, "dropped"),
    ):
        assert handler.count("readViewerLocalModelFile(file)") == 1
        assert "viewerLocalModelFileFailure(error" in handler
        assert "failure.error_code" in handler
        assert "failure.error_path" in handler
        assert f"Could not load the {action} JSON model" in handler
        assert "await window.buildModel?.(fileRead.payload" in handler
        assert "mode: 'local_file'" in handler
        assert "label: fileRead.name || file.name" in handler
        assert "resolvedPath: fileRead.name || file.name" in handler
        assert "showLoadingIndicator(" in handler
        assert "hideLoadingIndicator();" in handler
        assert "file.text()" not in handler
        assert "JSON.parse(" not in handler
        assert "window.loadStructureData(" not in handler
        assert "console.error(" not in handler
        assert "String(error" not in handler
        assert ".message" not in handler

    assert "input.value = '';" in select_handler
    assert "e.preventDefault();" in drop_handler
    assert "dropZone.classList.remove('drag-over');" in drop_handler


def test_temporary_local_model_patch_workflow_is_absent() -> None:
    assert not TEMP_WORKFLOW.exists()
