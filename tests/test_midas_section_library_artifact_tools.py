from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_backfill_midas_section_library_metadata_writes_embedded_payload(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    module = _load_module(
        repo_root / "implementation/phase1/backfill_midas_section_library_metadata.py",
        "backfill_midas_section_library_metadata_test",
    )
    artifact = tmp_path / "model.json"
    _write_json(
        artifact,
        {
            "model": {
                "sections": [
                    {"id": 11, "name": "WALL300X5000", "raw_tokens": ["WALL300X5000", "0.3", "5.0"]},
                    {"id": 12, "name": "SB800X3002.00", "raw_tokens": ["SB800X3002.00", "SB", "2", "0.8", "0.3"]},
                ],
                "elements": [
                    {"id": 101, "family": "wall", "section_id": 11, "node_ids": [1, 2, 3, 4]},
                    {"id": 202, "family": "beam", "section_id": 12, "node_ids": [5, 6]},
                ],
                "metadata": {
                    "design_sections": [{"section_id": 11}],
                    "section_colors": [{"section_id": 12}],
                    "section_scales": [{"section_id": 12}],
                },
            }
        },
    )

    summary = module.backfill_artifact(artifact, write=True)
    updated = json.loads(artifact.read_text(encoding="utf-8"))
    embedded = (((updated.get("model") or {}).get("metadata") or {}).get("section_library"))

    assert summary["written"] is True
    assert summary["section_rows"] == 2
    assert summary["used"] == 2
    assert summary["templates"] == 2
    assert isinstance(embedded, dict)
    assert embedded["summary"]["section_row_count"] == 2


def test_validate_midas_section_library_artifacts_reports_missing_and_ok(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    backfill_module = _load_module(
        repo_root / "implementation/phase1/backfill_midas_section_library_metadata.py",
        "backfill_midas_section_library_metadata_test_validate",
    )
    validator_path = repo_root / "implementation/phase1/validate_midas_section_library_artifacts.py"
    artifact = tmp_path / "model.json"
    _write_json(
        artifact,
        {
            "model": {
                "sections": [{"id": 12, "name": "SB800X3002.00", "raw_tokens": ["SB800X3002.00", "SB", "2", "0.8", "0.3"]}],
                "elements": [{"id": 202, "family": "beam", "section_id": 12, "node_ids": [5, 6]}],
                "metadata": {},
            }
        },
    )

    missing = subprocess.run(
        [sys.executable, str(validator_path), "--path", str(artifact), "--require"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert missing.returncode == 1
    assert "missing" in missing.stdout
    assert artifact.name in missing.stdout

    backfill_module.backfill_artifact(artifact, write=True)
    ok = subprocess.run(
        [sys.executable, str(validator_path), "--path", str(artifact), "--require"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert ok.returncode == 0
    assert "ok" in ok.stdout
    assert artifact.name in ok.stdout


def test_validate_midas_section_library_artifacts_smoke_on_canonical_payload() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    validator_path = repo_root / "implementation/phase1/validate_midas_section_library_artifacts.py"
    canonical = repo_root / "implementation/phase1/open_data/midas/midas_generator_33.json"

    result = subprocess.run(
        [sys.executable, str(validator_path), "--path", str(canonical), "--require"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "ok" in result.stdout
    assert "embedded metadata" in result.stdout or "midas_parser_derived" in result.stdout
    assert canonical.name in result.stdout
