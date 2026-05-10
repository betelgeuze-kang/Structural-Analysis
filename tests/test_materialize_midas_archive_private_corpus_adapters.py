from __future__ import annotations

import json
from pathlib import Path
import struct
import subprocess
import sys
import zipfile


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "implementation/phase1/materialize_midas_archive_private_corpus_adapters.py"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _raw_xyz_meb_bytes() -> bytes:
    data = bytearray(b"\x00" * 262144)
    prefix = b"MBDG\x00\x00__DBMS_DATA__\x00GUID\x00UNIT\x00MATL\x00SECT\x00STOR\x00PONT\x00MEMB"
    data[: len(prefix)] = prefix
    values = [
        (0.0, 200.0, 250.0),
        (200.0, 250.0, 300.0),
        (250.0, 300.0, 200.0),
        (50.0, 150.0, 275.0),
        (75.0, 120.0, 225.0),
        (120.0, 80.0, 210.0),
    ]
    offset = 210432
    for xyz in values:
        data[offset : offset + 24] = struct.pack("<ddd", *xyz)
        offset += 56
    return bytes(data)


def test_materialize_midas_archive_private_corpus_adapters_builds_preview_bridge(tmp_path: Path) -> None:
    archive = tmp_path / "archive.zip"
    with zipfile.ZipFile(archive, "w") as zip_file:
        zip_file.writestr("model.meb", _raw_xyz_meb_bytes())
        zip_file.writestr("notes.txt", "ignored\n")
    private_manifest = tmp_path / "private_manifest.json"
    _write_json(
        private_manifest,
        {
            "schema_version": "real-drawing-private-corpus-manifest.v1",
            "projects": [
                {
                    "project_id": "project_a",
                    "project_title": "Project A",
                    "source_family": "fixture_archive",
                    "files": [
                        {
                            "file_id": "archive_a",
                            "file_name": "archive.zip",
                            "file_type": ".zip",
                            "role": "midas_model_archive",
                            "private_path": str(archive),
                            "bytes": archive.stat().st_size,
                            "sha256": "fixture",
                            "source_url": "https://example.invalid/archive.zip",
                            "model_optimization_candidate": True,
                            "zip_model_member_count": 1,
                        }
                    ],
                }
            ],
        },
    )
    out_root = tmp_path / "out"
    out_report = tmp_path / "adapter_report.json"

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--private-manifest",
            str(private_manifest),
            "--out-root",
            str(out_root),
            "--out-report",
            str(out_report),
            "--json",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out_report.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["summary"]["archive_candidate_count"] == 1
    assert payload["summary"]["decoded_preview_bridge_ready_count"] == 1
    assert payload["summary"]["archive_hard_tier_ready_count"] == 0
    assert payload["summary"]["archive_hard_tier_blocked_count"] == 1
    assert payload["summary"]["archive_hard_tier_blocked_reason_counts"] == {
        "ERR_ARCHIVE_PREVIEW_NOT_SOLVER_EXACT": 1
    }
    assert payload["summary"]["viewer_ready_count"] == 1
    assert payload["summary"]["ready_node_count_total"] > 0
    assert payload["summary"]["ready_element_count_total"] > 0
    archive_row = payload["archives"][0]
    assert archive_row["status"] == "decoded_preview_bridge_ready"
    assert archive_row["raw_redistribution_allowed"] is False
    assert archive_row["release_surface_allowed"] is False
    assert archive_row["exact_topology_promoted"] is False
    assert archive_row["archive_hard_tier_ready"] is False
    assert archive_row["archive_hard_tier_reason_code"] == "ERR_ARCHIVE_PREVIEW_NOT_SOLVER_EXACT"
    assert archive_row["preview_exactness_tier"]
    assert "source_private_manifest" not in payload
    assert "private_path" not in json.dumps(payload)
    assert Path(archive_row["model_json"]).exists()
