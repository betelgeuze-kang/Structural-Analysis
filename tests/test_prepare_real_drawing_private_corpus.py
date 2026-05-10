from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "implementation/phase1/prepare_real_drawing_private_corpus.py"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_private_corpus_download_writes_redacted_manifest_without_raw_paths(tmp_path: Path) -> None:
    source_pdf = tmp_path / "source.pdf"
    source_pdf.write_bytes(b"%PDF-1.6\nprivate drawing fixture\n")
    source_mgt = tmp_path / "source.mgt"
    source_mgt.write_text("*NODE\n1,0,0,0\n", encoding="utf-8")
    source_zip = tmp_path / "source.zip"
    with zipfile.ZipFile(source_zip, "w") as zip_file:
        zip_file.writestr("models/a.mgt", "*NODE\n1,0,0,0\n")
        zip_file.writestr("models/b.ifc", "ISO-10303-21;\nEND-ISO-10303-21;\n")
        zip_file.writestr("notes/readme.txt", "fixture archive\n")
    catalog = tmp_path / "catalog.json"
    _write_json(
        catalog,
        {
            "schema_version": "real-drawing-private-corpus-catalog.v1",
            "generated_at": "2026-05-06T00:00:00Z",
            "policy": {
                "raw_redistribution_allowed": False,
                "release_surface_allowed": False,
                "storage_boundary": "private_corpus_only",
                "license_basis": "test fixture private only",
            },
            "projects": [
                {
                    "project_id": "fixture_project",
                    "project_title": "Fixture project",
                    "source_family": "public_institution_bid_drawing_docs",
                    "jurisdiction": "KR",
                    "notice_id": "fixture-notice",
                    "source_page_url": "https://example.invalid/notice",
                    "files": [
                        {
                            "file_id": "drawing_pdf",
                            "file_name": "drawing.pdf",
                            "file_type": ".pdf",
                            "role": "architectural_drawing_pdf",
                            "source_url": source_pdf.as_uri(),
                        },
                        {
                            "file_id": "native_model_mgt",
                            "file_name": "native_model.mgt",
                            "file_type": ".mgt",
                            "role": "midas_mgt_model",
                            "source_url": source_mgt.as_uri(),
                            "expected_sha256": hashlib.sha256(source_mgt.read_bytes()).hexdigest(),
                        },
                        {
                            "file_id": "model_archive_zip",
                            "file_name": "model_archive.zip",
                            "file_type": ".zip",
                            "role": "midas_model_archive",
                            "source_url": source_zip.as_uri(),
                            "expected_md5": hashlib.md5(source_zip.read_bytes()).hexdigest(),
                        }
                    ],
                }
            ],
        },
    )
    private_root = tmp_path / "private_corpus" / "real_drawings"
    private_manifest = private_root / "manifest.json"
    redacted_manifest = tmp_path / "redacted.json"
    summary = tmp_path / "summary.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--catalog",
            str(catalog),
            "--private-root",
            str(private_root),
            "--out-manifest",
            str(private_manifest),
            "--out-redacted",
            str(redacted_manifest),
            "--out-summary",
            str(summary),
            "--download",
            "--json",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    private_payload = json.loads(private_manifest.read_text(encoding="utf-8"))
    redacted_payload = json.loads(redacted_manifest.read_text(encoding="utf-8"))

    private_file = private_payload["projects"][0]["files"][0]
    redacted_file = redacted_payload["projects"][0]["files"][0]
    assert private_file["retrieval_status"] == "downloaded"
    assert Path(private_file["private_path"]).exists()
    assert private_file["sha256"]
    assert private_file["bytes"] > 0
    assert "source_private_manifest" not in redacted_payload
    assert "private_path" not in redacted_file
    assert "fetch" not in redacted_file
    assert "zip_model_member_names_sample" not in redacted_file
    assert redacted_file["raw_redistribution_allowed"] is False
    assert redacted_file["release_surface_allowed"] is False
    assert redacted_payload["summary"]["drawing_review_candidate_count"] == 2
    assert redacted_payload["summary"]["downloaded_drawing_review_candidate_count"] == 2
    assert redacted_payload["summary"]["model_optimization_candidate_count"] == 2
    assert redacted_payload["summary"]["downloaded_model_optimization_candidate_count"] == 2
    assert redacted_payload["summary"]["model_optimization_asset_count"] == 3
    assert redacted_payload["summary"]["model_optimization_candidate_file_type_counts"] == {".mgt": 1, ".zip": 1}
    archive_file = next(row for row in private_payload["projects"][0]["files"] if row["file_id"] == "model_archive_zip")
    assert archive_file["zip_member_count"] == 3
    assert archive_file["zip_model_member_count"] == 2
