from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import build_canonical_verification_receipt as module


ROOT = Path(__file__).resolve().parents[1]


def test_checked_in_environment_is_digest_and_hash_pinned() -> None:
    config = module.load_config(repo_root=ROOT)
    locked = module.load_lock(ROOT / config["dependency_lock"]["path"])

    assert (
        config["container"]["image"] == "docker.io/library/python:3.12.11-slim-bookworm"
    )
    assert config["container"]["digest"].startswith("sha256:")
    assert len(config["container"]["digest"]) == 71
    assert config["python"] == {
        "implementation": "CPython",
        "version": "3.12.11",
        "abi": "cp312",
    }
    assert locked["numpy"]["version"] == "2.2.6"
    assert locked["scipy"]["version"] == "1.15.3"
    assert locked["pip"]["version"] == config["build"]["frontend_version"]
    assert all(len(row["wheel_sha256"]) == 64 for row in locked.values())


def test_lock_rejects_unhashed_or_ranged_dependency(tmp_path: Path) -> None:
    lock = tmp_path / "requirements.lock"
    lock.write_text("numpy>=2\n", encoding="utf-8")

    with pytest.raises(module.CanonicalEnvironmentError, match="not exactly hashed"):
        module.load_lock(lock)


def test_receipt_contains_runtime_identity_and_detects_environment_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = module.load_config(repo_root=ROOT)
    locked = module.load_lock(ROOT / config["dependency_lock"]["path"])
    monkeypatch.setattr(
        module.metadata,
        "version",
        lambda name: locked[name.lower().replace("_", "-")]["version"],
    )
    monkeypatch.setattr(module.platform, "python_version", lambda: "3.12.11")
    env = dict(config["determinism"])
    env["OMP_NUM_THREADS"] = "8"

    receipt = module.build_receipt(
        config,
        repo_root=ROOT,
        environ=env,
        source_sha="a" * 40,
    )

    runtime = receipt["runtime"]
    assert receipt["source_commit_sha"] == "a" * 40
    assert set(("python", "packages", "os", "libc", "blas", "lapack")) <= set(runtime)
    assert (
        runtime["packages"]["numpy"]["wheel_sha256"] == locked["numpy"]["wheel_sha256"]
    )
    assert runtime["thread_limits"]["OMP_NUM_THREADS"] == "8"
    assert runtime["timezone"] == "UTC"
    assert runtime["python_hash_seed"] == "0"
    assert receipt["contract_pass"] is False
    assert "environment_mismatch:OMP_NUM_THREADS:8" in receipt["violations"]


def test_check_mode_does_not_replace_stored_receipt(tmp_path: Path) -> None:
    stored = tmp_path / "receipt.json"
    stored.write_text(json.dumps({"stale": True}), encoding="utf-8")
    before = stored.read_bytes()

    exit_code = module.main(
        [
            "--repo-root",
            str(ROOT),
            "--source-sha",
            "b" * 40,
            "--check",
            str(stored),
        ]
    )

    assert exit_code == 1
    assert stored.read_bytes() == before
