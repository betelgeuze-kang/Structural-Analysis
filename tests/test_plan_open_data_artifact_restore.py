from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "plan_open_data_artifact_restore.py"
SPEC = importlib.util.spec_from_file_location("plan_open_data_artifact_restore", SCRIPT_PATH)
assert SPEC is not None
plan_restore = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(plan_restore)


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _manifest(tmp_path: Path, payload: bytes = b"abc") -> Path:
    manifest = {
        "schema_version": 1,
        "artifacts": [
            {
                "path": "implementation/phase1/open_data/sample.bin",
                "bytes": len(payload),
                "sha256": _sha256(payload),
                "source_family": "fixture_family",
                "disposition": "externalize",
            }
        ],
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def test_restore_plan_reports_blocked_without_cache_or_target(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    manifest = _manifest(tmp_path)

    plan = plan_restore.build_restore_plan(manifest_path=manifest)

    assert plan["ok"] is False
    assert plan["summary"]["blocked"] == 1
    assert plan["artifacts"][0]["status"] == "blocked"
    assert plan["artifacts"][0]["target"]["reason"] == "missing"


def test_restore_plan_accepts_already_restored_target(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    payload = b"abc"
    manifest = _manifest(tmp_path, payload)
    target = tmp_path / "implementation" / "phase1" / "open_data" / "sample.bin"
    target.parent.mkdir(parents=True)
    target.write_bytes(payload)

    plan = plan_restore.build_restore_plan(manifest_path=manifest)

    assert plan["ok"] is True
    assert plan["summary"]["already_restored"] == 1
    assert plan["artifacts"][0]["status"] == "already_restored"


def test_restore_plan_checks_source_family_sha_cache_layout(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    payload = b"abc"
    digest = _sha256(payload)
    manifest = _manifest(tmp_path, payload)
    cache_root = tmp_path / "cache"
    cache_file = cache_root / "fixture_family" / digest / "sample.bin"
    cache_file.parent.mkdir(parents=True)
    cache_file.write_bytes(payload)

    plan = plan_restore.build_restore_plan(manifest_path=manifest, cache_root=cache_root)

    assert plan["ok"] is True
    assert plan["summary"]["cache_ready"] == 1
    row = plan["artifacts"][0]
    assert row["status"] == "cache_ready"
    assert row["cache"]["path"] == str(cache_file)
    assert "cp " in row["restore_command"]


def test_cli_writes_json_and_can_fail_unready(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    manifest = _manifest(tmp_path)
    out = tmp_path / "plan.json"

    exit_code = plan_restore.main(["--manifest", str(manifest), "--json", "--out", str(out), "--fail-unready"])

    assert exit_code == 1
    stdout = capsys.readouterr().out
    assert json.loads(stdout)["summary"]["blocked"] == 1
    assert json.loads(out.read_text(encoding="utf-8"))["summary"]["blocked"] == 1
