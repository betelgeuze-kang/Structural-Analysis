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


def test_release_evidence_freshness_default_artifacts_include_real_project_and_customer_shadow(tmp_path: Path) -> None:
    artifacts = freshness.DEFAULT_ARTIFACTS
    labels = {label for label, _artifact, _producer in artifacts}
    assert "real_project_corpus_measured_status" in labels
    assert "customer_shadow_evidence_status" in labels
    assert "p0_closure_status" in labels
    assert "p1_readiness_status" in labels
    assert "p1_benchmark_breadth_status" in labels
    assert "fresh_full_validation_lane_status" in labels
    assert len(artifacts) == 6

    for label, artifact_path, producer_path in artifacts:
        assert isinstance(artifact_path, Path)
        assert isinstance(producer_path, Path)
        assert str(artifact_path).endswith(".json"), label


def test_release_evidence_freshness_audits_real_project_and_customer_shadow_artifacts(tmp_path: Path) -> None:
    freshness._git_head = lambda _repo_root: "abcdef1234567890"
    now_iso = datetime.now(timezone.utc).isoformat()
    repo_root_artifacts: list[tuple[str, Path, Path]] = []
    for label, artifact_relpath, producer_relpath in (
        (
            "real_project_corpus_measured_status",
            "implementation/phase1/real_project_corpus_measured_status.json",
            "implementation/phase1/check_real_project_corpus_measured_status.py",
        ),
        (
            "customer_shadow_evidence_status",
            "implementation/phase1/customer_shadow_evidence_status.json",
            "implementation/phase1/check_customer_shadow_evidence_status.py",
        ),
    ):
        artifact_path = tmp_path / artifact_relpath
        producer_path = tmp_path / producer_relpath
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        producer_path.parent.mkdir(parents=True, exist_ok=True)
        producer_path.write_text("print('producer')\n", encoding="utf-8")
        _write_json(
            artifact_path,
            {
                "generated_at": now_iso,
                "source_commit_sha": "abcdef123456",
                "engine_version": "structural-analysis-workbench@unversioned",
                "input_checksums": {artifact_relpath: "sha256:abc"},
                "reused_evidence": True,
                "reuse_policy": "status_rebuilt_from_existing_metadata",
                "contract_pass": label == "real_project_corpus_measured_status",
            },
        )
        os.utime(producer_path, (artifact_path.stat().st_mtime - 5, artifact_path.stat().st_mtime - 5))
        repo_root_artifacts.append((label, artifact_path, producer_path))

    payload = freshness.build_report(
        repo_root=tmp_path,
        artifacts=tuple(repo_root_artifacts),
        max_age_days=30,
    )

    assert payload["contract_pass"] is True
    assert payload["summary"]["artifact_count"] == 2
    rows_by_label = {row["label"]: row for row in payload["rows"]}
    assert rows_by_label["real_project_corpus_measured_status"]["ok"] is True
    assert rows_by_label["customer_shadow_evidence_status"]["ok"] is True
    assert rows_by_label["customer_shadow_evidence_status"]["engine_version_present"] is True
    assert rows_by_label["customer_shadow_evidence_status"]["input_checksum_present"] is True
    assert rows_by_label["customer_shadow_evidence_status"]["reuse_marker_present"] is True


def test_release_evidence_freshness_accepts_receipt_only_commit_when_inputs_unchanged(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    subprocess = freshness.subprocess
    subprocess.check_call(["git", "init"], cwd=tmp_path, stdout=subprocess.DEVNULL)
    subprocess.check_call(["git", "config", "user.email", "test@example.com"], cwd=tmp_path)
    subprocess.check_call(["git", "config", "user.name", "Test"], cwd=tmp_path)
    producer = tmp_path / "producer.py"
    source = tmp_path / "input.json"
    producer.write_text("print('producer')\n", encoding="utf-8")
    source.write_text('{"ok": true}\n', encoding="utf-8")
    subprocess.check_call(["git", "add", "producer.py", "input.json"], cwd=tmp_path)
    subprocess.check_call(["git", "commit", "-m", "source"], cwd=tmp_path, stdout=subprocess.DEVNULL)
    source_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=tmp_path, text=True).strip()
    artifact = _write_json(
        tmp_path / "evidence.json",
        {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_commit_sha": source_commit,
            "engine_version": "engine-v1",
            "input_checksums": {"input.json": "sha256:123"},
            "reused_evidence": True,
        },
    )
    subprocess.check_call(["git", "add", "evidence.json"], cwd=tmp_path)
    subprocess.check_call(["git", "commit", "-m", "receipt"], cwd=tmp_path, stdout=subprocess.DEVNULL)
    freshness._git_head = lambda _repo_root: subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=tmp_path,
        text=True,
    ).strip()

    payload = freshness.build_report(
        repo_root=tmp_path,
        artifacts=(("evidence", artifact, producer),),
        max_age_days=30,
    )
    row = payload["rows"][0]

    assert payload["contract_pass"] is True
    assert row["source_commit_match"] is True
    assert row["source_commit_exact_match"] is False
    assert row["changed_paths_since_source_commit"] == []
