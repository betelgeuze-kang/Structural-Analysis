"""Tests for MGT roundtrip provenance sync."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))

from sync_mgt_roundtrip_provenance import (  # noqa: E402
    refresh_optimized_roundtrip_from_mgt,
    sync_roundtrip_source_from_mgt,
)


def test_sync_roundtrip_source_updates_sha256(tmp_path: Path) -> None:
    mgt = tmp_path / "sample.mgt"
    mgt.write_text("*UNIT\n", encoding="utf-8")
    roundtrip = tmp_path / "sample.roundtrip.json"
    roundtrip.write_text(
        json.dumps({"source": {"sha256": "deadbeef", "path": "x.mgt"}}),
        encoding="utf-8",
    )

    result = sync_roundtrip_source_from_mgt(roundtrip_json=roundtrip, mgt_path=mgt)
    assert result["status"] == "synced"
    assert result["sha256_changed"] is True

    payload = json.loads(roundtrip.read_text(encoding="utf-8"))
    assert payload["source"]["sha256"] == result["sha256"]
    assert payload["source"]["size_bytes"] == mgt.stat().st_size


def test_refresh_provenance_only_without_parse(tmp_path: Path) -> None:
    mgt = tmp_path / "opt.mgt"
    mgt.write_text("*VERSION\n", encoding="utf-8")
    roundtrip = tmp_path / "opt.roundtrip.json"
    roundtrip.write_text(json.dumps({"source": {"sha256": "00"}}), encoding="utf-8")

    payload = refresh_optimized_roundtrip_from_mgt(
        mgt_path=mgt,
        roundtrip_json=roundtrip,
        parse_refresh=False,
        sync_provenance_only=True,
    )
    assert payload["status"] == "ready"
    assert payload["integrity_status"] == "verified"
    assert payload.get("parse") is None


def test_sync_cli_parse_on_repo_optimized_mgt() -> None:
    out = REPO_ROOT / "implementation/phase1/release_evidence/productization/mgt_roundtrip_parse_cli_test.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/sync_optimized_mgt_roundtrip.py"),
            "--parse",
            "--output-json",
            str(out),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload.get("status") == "ready"
    assert (payload.get("parse") or {}).get("contract_pass") is True


def test_sync_cli_on_repo_optimized_mgt() -> None:
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/sync_optimized_mgt_roundtrip.py"),
            "--sync-only",
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
