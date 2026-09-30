"""Supplemental read-only audit compares proposal, guard and step bytes."""

import importlib
from pathlib import Path

import pytest


@pytest.fixture
def supplement(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    return importlib.import_module("audit_rc_material_capture_cost_supplement")


def _pair(tmp_path):
    left, right = (tmp_path / name for name in ("uncached", "cached"))
    for root in (left, right):
        folder = root / "benchmark/proposal"
        folder.mkdir(parents=True)
        for index in range(12):
            (folder / f"{index:03d}-context.json").write_bytes(b"parent")
            (folder / f"{index:03d}-guard-context.json").write_bytes(b"guard")
            (folder / f"{index:03d}-1-step.json").write_bytes(b"step")
        (folder / "preload-step.json").write_bytes(b"preload")
    return left, right


def test_exact_pair_includes_guard_context_and_preload_step(tmp_path, supplement):
    left, right = _pair(tmp_path)
    result = supplement._pair_bytes(left, right)
    assert result["exact"]
    assert result["context_file_count"] == 24
    assert result["step_file_count"] == 13
    assert result["left_observed_file_count"] == 37
    assert result["right_observed_file_count"] == 37
    assert result["left_manifest_hash"] == result["right_manifest_hash"]


def test_pair_rejects_changed_guard_or_missing_step(tmp_path, supplement):
    left, right = _pair(tmp_path)
    changed = right / "benchmark/proposal/006-guard-context.json"
    changed.write_bytes(b"different")
    result = supplement._pair_bytes(left, right)
    assert not result["exact"]
    assert result["mismatch_names"] == ["006-guard-context.json"]
    changed.write_bytes(b"guard")
    (right / "benchmark/proposal/preload-step.json").unlink()
    result = supplement._pair_bytes(left, right)
    assert not result["exact"]
    assert "preload-step.json" in result["mismatch_names"]


def test_supplement_requires_clean_audit_only_child(supplement, monkeypatch):
    responses = {
        ("status", "--porcelain"): "",
        ("rev-parse", "HEAD"): "f" * 40,
        ("rev-parse", "HEAD^"): supplement.NUMERICAL_REVISION,
        ("diff", "--name-only", "HEAD^", "HEAD"): "\n".join(
            sorted(supplement.AUDIT_ONLY_FILES)
        ),
    }
    monkeypatch.setattr(supplement, "_git", lambda *args: responses[args])
    assert supplement._audit_only_revision() == "f" * 40
    responses[("rev-parse", "HEAD^")] = "0" * 40
    with pytest.raises(ValueError, match="audit-only child commit"):
        supplement._audit_only_revision()
