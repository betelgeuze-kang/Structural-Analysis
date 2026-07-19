from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "src/structure-viewer/index.html"
TEMP_WORKFLOW = (
    ROOT / ".github/workflows/codex-temp-viewer-ingest-handler-inspect.yml"
)


def _evidence_ingest_handler() -> str:
    text = INDEX.read_text(encoding="utf-8")
    match = re.search(
        r"async function previewEvidenceIngestFromInput\(event\)\{\n.*?\n\}"
        r"\nfunction attachEvidenceIngestPreview\(\)\{",
        text,
        re.DOTALL,
    )
    assert match is not None
    return match.group(0)


def test_runtime_uses_pre_read_validation_and_persists_metadata_only() -> None:
    text = INDEX.read_text(encoding="utf-8")
    ingest_facade = (INDEX.parent / "viewer-ingest.js").read_text(encoding="utf-8")
    handler = _evidence_ingest_handler()

    assert "from './viewer-ingest.js';" in text
    assert "export * from './viewer-evidence-ingest-file-reader.js';" in ingest_facade
    assert "buildEvidenceIngestFileReadFailurePreview," in text
    assert "evidenceIngestFileReadMetadata," in text
    assert "readEvidenceIngestFileText," in text

    assert handler.count("readEvidenceIngestFileText(file)") == 1
    assert "const text=fileRead.text;" in handler
    assert "preview.ingest_file_read=evidenceIngestFileReadMetadata(fileRead);" in handler
    assert "buildEvidenceIngestFileReadFailurePreview(err" in handler
    assert "renderable_payload_error_code" in handler
    assert "renderable_payload_error_path" in handler
    assert "file.text()" not in handler
    assert "String(err?.message||err)" not in handler

    metadata_index = handler.index(
        "preview.ingest_file_read=evidenceIngestFileReadMetadata(fileRead);"
    )
    persist_index = handler.index("writeLocalOpsState({")
    assert metadata_index < persist_index


def test_temporary_handler_inspection_workflow_is_not_part_of_the_pr() -> None:
    assert not TEMP_WORKFLOW.exists()
