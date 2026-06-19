from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "report_release_evidence_freshness.py"
SPEC = importlib.util.spec_from_file_location("report_release_evidence_freshness", SCRIPT_PATH)
assert SPEC is not None
freshness = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(freshness)


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def test_release_evidence_freshness_passes_complete_metadata(tmp_path: Path) -> None:
    freshness._git_head = lambda _repo_root: "abcdef1234567890"
    producer = tmp_path / "producer.py"
    producer.write_text("print('producer')\n", encoding="utf-8")
    artifact = _write_json(
        tmp_path / "evidence.json",
        {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_commit_sha": "abcdef123456",
            "engine_version": "engine-v1",
            "input_checksums": {"fixture": "sha256:123"},
            "reused_evidence": False,
        },
    )
    os.utime(producer, (artifact.stat().st_mtime - 5, artifact.stat().st_mtime - 5))

    payload = freshness.build_report(
        repo_root=tmp_path,
        artifacts=(("evidence", artifact, producer),),
        max_age_days=30,
    )
    row = payload["rows"][0]

    assert payload["contract_pass"] is True
    assert row["ok"] is True
    assert row["source_commit_match"] is True
    assert row["engine_version_present"] is True
    assert row["input_checksum_present"] is True
    assert row["reuse_marker_present"] is True
    assert row["dependency_mtime_pass"] is True


def test_release_evidence_freshness_blocks_missing_release_metadata(tmp_path: Path) -> None:
    freshness._git_head = lambda _repo_root: "abcdef1234567890"
    producer = tmp_path / "producer.py"
    producer.write_text("print('producer')\n", encoding="utf-8")
    artifact = _write_json(tmp_path / "evidence.json", {"contract_pass": True})

    payload = freshness.build_report(
        repo_root=tmp_path,
        artifacts=(("evidence", artifact, producer),),
        max_age_days=30,
    )

    assert payload["contract_pass"] is False
    assert "evidence::generated_at_missing_or_invalid" in payload["blockers"]
    assert "evidence::source_commit_missing" in payload["blockers"]
    assert "evidence::engine_version_missing" in payload["blockers"]
    assert "evidence::input_checksum_missing" in payload["blockers"]
    assert "evidence::reuse_marker_missing" in payload["blockers"]


def test_release_evidence_freshness_blocks_newer_producer(tmp_path: Path) -> None:
    freshness._git_head = lambda _repo_root: "abcdef1234567890"
    producer = tmp_path / "producer.py"
    producer.write_text("print('producer')\n", encoding="utf-8")
    artifact = _write_json(
        tmp_path / "evidence.json",
        {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_commit_sha": "abcdef123456",
            "engine_version": "engine-v1",
            "input_checksum": "sha256:abc",
            "reuse_existing_if_present": True,
        },
    )
    future = artifact.stat().st_mtime + 30
    os.utime(producer, (future, future))

    payload = freshness.build_report(
        repo_root=tmp_path,
        artifacts=(("evidence", artifact, producer),),
        max_age_days=30,
    )

    assert payload["contract_pass"] is False
    assert "evidence::producer_newer_than_artifact" in payload["blockers"]
