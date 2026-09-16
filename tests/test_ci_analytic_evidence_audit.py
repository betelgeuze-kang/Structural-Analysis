"""Check audit failure semantics independently of numerical acceptance rules."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
import yaml
from structural_analysis.benchmark import analytic_frame

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "ci_analytic_evidence_audit", ROOT / "scripts/check_ci_analytic_evidence.py"
)
assert spec is not None and spec.loader is not None
audit_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit_module)


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    # Mock only the strict validator in unit tests; production always replays.
    (tmp_path / "solver.py").write_text("original\n", encoding="utf-8")
    artifact = tmp_path / audit_module.DEFAULT_ARTIFACT
    artifact.parent.mkdir(parents=True)
    artifact.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(analytic_frame, "_SOURCE_PATHS", (Path("solver.py"),))
    calls = []

    def validate(payload, **kwargs):
        calls.append(kwargs)
        assert kwargs == {"repo_root": tmp_path.resolve(),
                          "require_current_sources": True, "rerun": True}

    monkeypatch.setattr(analytic_frame, "validate_analytic_frame_verification_artifact", validate)
    return tmp_path, artifact, calls


def test_valid_audit_is_read_only_and_forces_strict_replay(isolated):
    root, artifact, calls = isolated
    original = artifact.read_bytes()
    first = audit_module.audit(root)
    second = audit_module.audit(root, first)
    assert first["audit_passed"] and second["audit_passed"]
    assert not second["release_authority"]
    assert len(calls) == 2
    assert artifact.read_bytes() == original


def test_validation_error_is_not_replaced_with_regenerated_evidence(isolated, monkeypatch):
    root, artifact, _ = isolated
    original = artifact.read_bytes()

    def fail(*args, **kwargs):
        raise ValueError("analytic_frame_sources_stale")

    monkeypatch.setattr(analytic_frame, "validate_analytic_frame_verification_artifact", fail)
    report = audit_module.audit(root)
    assert not report["audit_passed"]
    assert "analytic_frame_sources_stale" in report["validation_error"]
    assert artifact.read_bytes() == original


@pytest.mark.parametrize("target", ["source", "artifact"])
def test_baseline_identifies_changed_input(isolated, target):
    root, artifact, _ = isolated
    baseline = audit_module.audit(root)
    path = root / "solver.py" if target == "source" else artifact
    path.write_text("{}\n" if target == "source" else '{"changed":true}\n', encoding="utf-8")
    report = audit_module.audit(root, baseline)
    assert not report["audit_passed"]
    assert [row["path"] for row in report["changes_since_baseline"]] == [path.relative_to(root).as_posix()]


@pytest.mark.parametrize("baseline", [{}, {"schema_version": "wrong"},
    {"schema_version": audit_module.REPORT_VERSION, "audit_passed": False, "files": {"x": "y"}},
    {"schema_version": audit_module.REPORT_VERSION, "audit_passed": True, "files": []}])
def test_invalid_baseline_fails_closed(isolated, baseline):
    report = audit_module.audit(isolated[0], baseline)
    assert not report["audit_passed"]
    assert report["baseline_error"] == "invalid_or_failed_baseline"


def test_source_mutation_during_replay_is_reported(isolated, monkeypatch):
    root, _, _ = isolated

    def mutate(*args, **kwargs):
        (root / "solver.py").write_text("changed\n", encoding="utf-8")

    monkeypatch.setattr(analytic_frame, "validate_analytic_frame_verification_artifact", mutate)
    report = audit_module.audit(root)
    assert not report["audit_passed"]
    assert report["changes_during_replay"][0]["path"] == "solver.py"


def test_snapshot_never_reads_outside_repository(tmp_path):
    assert audit_module._snapshot(tmp_path, ["../outside", "/etc/passwd"]) == {
        "../outside": "outside_repository", "/etc/passwd": "outside_repository"}


def test_cli_exit_status_and_json_report(isolated, tmp_path):
    root, artifact, _ = isolated
    out = tmp_path / "audit.json"
    assert audit_module.main(["--repo-root", str(root), "--out", str(out)]) == 0
    report = json.loads(out.read_text())
    assert report["audit_passed"]
    artifact.unlink()
    assert audit_module.main(["--repo-root", str(root), "--out", str(out)]) == 1
    assert "FileNotFoundError" in json.loads(out.read_text())["validation_error"]


def test_audit_cannot_overwrite_source_or_evidence(isolated):
    root, artifact, _ = isolated
    original = artifact.read_bytes()
    with pytest.raises(ValueError, match="audit_output_would_overwrite"):
        audit_module.main(["--repo-root", str(root), "--out", str(artifact)])
    assert artifact.read_bytes() == original


def test_ci_audits_after_preparation_and_after_full_test_execution():
    workflow = yaml.load((ROOT / ".github/workflows/python-test-collection.yml").read_text(), Loader=yaml.BaseLoader)
    steps = workflow["jobs"]["full_shards"]["steps"]
    names = [step["name"] for step in steps]
    assert names.index("Materialize exact current-source test evidence") < names.index("Audit analytic evidence before tests")
    assert names.index("Audit analytic evidence before tests") < names.index("Run materialized repository test suite shard") < names.index("Audit analytic evidence after tests")
    after = next(step for step in steps if step["name"] == "Audit analytic evidence after tests")
    assert "always()" in after["if"]
    assert "--baseline" in after["run"]
    assert after.get("continue-on-error", "false") == "false"
    test_run = next(step["run"] for step in steps if step["name"] == "Run materialized repository test suite shard")
    assert test_run.count("--deselect") == 2
    assert "--tb=long" in test_run
