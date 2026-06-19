from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parent.parent
    / "scripts"
    / "report_release_evidence_freshness.py"
)
SPEC = importlib.util.spec_from_file_location(
    "report_release_evidence_freshness", SCRIPT_PATH
)
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
    assert payload["source_commit_sha"] == "abcdef1234567890"
    assert payload["engine_version"] == "structural-optimization-workbench@1.0.0"
    assert payload["reused_evidence"] is True
    assert payload["reuse_policy"] == "status_rebuilt_from_release_evidence_artifact_metadata"
    assert payload["input_checksums"]["evidence.json"].startswith("sha256:")
    assert payload["input_checksums"]["producer.py"].startswith("sha256:")
    assert row["ok"] is True
    assert row["source_commit_match"] is True
    assert row["engine_version_present"] is True
    assert row["input_checksum_present"] is True
    assert row["reuse_marker_present"] is True
    assert row["dependency_mtime_pass"] is True


def test_release_evidence_freshness_blocks_missing_release_metadata(
    tmp_path: Path,
) -> None:
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


def test_release_evidence_freshness_default_artifacts_include_real_project_and_customer_shadow(
    tmp_path: Path,
) -> None:
    artifacts = freshness.DEFAULT_ARTIFACTS
    labels = {label for label, _artifact, _producer in artifacts}
    assert "real_project_corpus_measured_status" in labels
    assert "customer_shadow_evidence_status" in labels
    assert "customer_shadow_evidence_intake_packet" in labels
    assert "p0_closure_status" in labels
    assert "p1_readiness_status" in labels
    assert "p1_benchmark_breadth_status" in labels
    assert "fresh_full_validation_lane_status" in labels
    assert "residual_level3_status" in labels
    assert "g1_direct_residual_terminal_gate_report" in labels
    assert "g1_shell_material_budgeted_continuation_status" in labels
    assert len(artifacts) == 10

    for label, artifact_path, producer_path in artifacts:
        assert isinstance(artifact_path, Path)
        assert isinstance(producer_path, Path)
        assert str(artifact_path).endswith(".json"), label


def test_release_evidence_freshness_audits_residual_level3_status(tmp_path: Path) -> None:
    freshness._git_head = lambda _repo_root: "abcdef1234567890"
    artifact_relpath = (
        "implementation/phase1/release_evidence/productization/residual_level3_status.json"
    )
    producer_relpath = "implementation/phase1/check_residual_level3_status.py"
    artifact_path = tmp_path / artifact_relpath
    producer_path = tmp_path / producer_relpath
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    producer_path.parent.mkdir(parents=True, exist_ok=True)
    producer_path.write_text("print('producer')\n", encoding="utf-8")
    _write_json(
        artifact_path,
        {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_commit_sha": "abcdef123456",
            "engine_version": "structural-optimization-workbench@1.0.0",
            "input_checksums": {
                "implementation/phase1/release_evidence/productization/ndtha_residual_gate_report.json": (
                    "sha256:abc"
                )
            },
            "reused_evidence": True,
            "reuse_policy": "status_rebuilt_from_existing_ndtha_residual_gate_report",
            "contract_pass": True,
        },
    )
    os.utime(
        producer_path,
        (artifact_path.stat().st_mtime - 5, artifact_path.stat().st_mtime - 5),
    )

    artifacts = freshness.DEFAULT_ARTIFACTS
    target = next(entry for entry in artifacts if entry[0] == "residual_level3_status")
    target_artifact = (tmp_path / target[1]).resolve()
    target_producer = (tmp_path / target[2]).resolve()
    target_artifact.parent.mkdir(parents=True, exist_ok=True)
    target_producer.parent.mkdir(parents=True, exist_ok=True)
    target_producer.write_text("print('producer')\n", encoding="utf-8")
    payload = _write_json(target_artifact, json.loads(artifact_path.read_text(encoding="utf-8")))
    os.utime(
        target_producer,
        (payload.stat().st_mtime - 5, payload.stat().st_mtime - 5),
    )

    payload_report = freshness.build_report(
        repo_root=tmp_path,
        artifacts=(
            (
                "residual_level3_status",
                target_artifact,
                target_producer,
            ),
        ),
        max_age_days=30,
    )
    row = payload_report["rows"][0]

    assert payload_report["contract_pass"] is True
    assert row["label"] == "residual_level3_status"
    assert row["ok"] is True
    assert row["source_commit_match"] is True
    assert row["engine_version_present"] is True
    assert row["input_checksum_present"] is True
    assert row["reuse_marker_present"] is True
    assert row["dependency_mtime_pass"] is True
    assert str(target_artifact).endswith("residual_level3_status.json")
    assert str(target_producer).endswith("check_residual_level3_status.py")


def test_release_evidence_freshness_audits_g1_residual_receipts(tmp_path: Path) -> None:
    freshness._git_head = lambda _repo_root: "abcdef1234567890"
    now_iso = datetime.now(timezone.utc).isoformat()
    artifacts: list[tuple[str, Path, Path]] = []
    for label, artifact_relpath, producer_relpath, source_relpath in (
        (
            "g1_direct_residual_terminal_gate_report",
            "implementation/phase1/release_evidence/productization/"
            "mgt_g1_direct_residual_terminal_gate_report.json",
            "scripts/build_mgt_g1_direct_residual_terminal_gate_report.py",
            "implementation/phase1/release_evidence/productization/"
            "mgt_direct_residual_attached_policy_followup365_gate_replay_probe.json",
        ),
        (
            "g1_shell_material_budgeted_continuation_status",
            "implementation/phase1/release_evidence/productization/"
            "mgt_g1_followup387_shell_material_budgeted_continuation_status.json",
            "scripts/build_mgt_g1_shell_material_budgeted_continuation_status.py",
            "implementation/phase1/release_evidence/productization/"
            "mgt_shell_material_rowcorr_budget_controller_followup398_after_global_krylov_target4_support4.json",
        ),
    ):
        artifact_path = tmp_path / artifact_relpath
        producer_path = tmp_path / producer_relpath
        source_path = tmp_path / source_relpath
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        producer_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.parent.mkdir(parents=True, exist_ok=True)
        producer_path.write_text("print('producer')\n", encoding="utf-8")
        source_path.write_text('{"receipt": true}\n', encoding="utf-8")
        _write_json(
            artifact_path,
            {
                "generated_at": now_iso,
                "source_commit_sha": "abcdef123456",
                "engine_version": "structural-optimization-workbench@1.0.0",
                "input_checksums": {source_relpath: "sha256:abc"},
                "reused_evidence": True,
                "reuse_policy": "status_rebuilt_from_existing_g1_receipts",
                "contract_pass": label == "g1_direct_residual_terminal_gate_report",
            },
        )
        artifact_mtime = artifact_path.stat().st_mtime
        os.utime(producer_path, (artifact_mtime - 5, artifact_mtime - 5))
        os.utime(source_path, (artifact_mtime - 5, artifact_mtime - 5))
        artifacts.append((label, artifact_path, producer_path))

    payload = freshness.build_report(
        repo_root=tmp_path,
        artifacts=tuple(artifacts),
        max_age_days=30,
    )

    assert payload["contract_pass"] is True
    assert payload["summary"]["artifact_count"] == 2
    rows_by_label = {row["label"]: row for row in payload["rows"]}
    assert rows_by_label["g1_direct_residual_terminal_gate_report"]["ok"] is True
    assert rows_by_label["g1_shell_material_budgeted_continuation_status"]["ok"] is True
    assert rows_by_label["g1_shell_material_budgeted_continuation_status"][
        "input_dependency_paths"
    ][0].endswith(
        "mgt_shell_material_rowcorr_budget_controller_followup398_after_global_krylov_target4_support4.json"
    )


def test_release_evidence_freshness_audits_real_project_and_customer_shadow_artifacts(
    tmp_path: Path,
) -> None:
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
        os.utime(
            producer_path,
            (artifact_path.stat().st_mtime - 5, artifact_path.stat().st_mtime - 5),
        )
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
    assert (
        rows_by_label["customer_shadow_evidence_status"]["engine_version_present"]
        is True
    )
    assert (
        rows_by_label["customer_shadow_evidence_status"]["input_checksum_present"]
        is True
    )
    assert (
        rows_by_label["customer_shadow_evidence_status"]["reuse_marker_present"] is True
    )


def test_release_evidence_freshness_accepts_receipt_only_commit_when_inputs_unchanged(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    subprocess = freshness.subprocess
    subprocess.check_call(["git", "init"], cwd=tmp_path, stdout=subprocess.DEVNULL)
    subprocess.check_call(
        ["git", "config", "user.email", "test@example.com"], cwd=tmp_path
    )
    subprocess.check_call(["git", "config", "user.name", "Test"], cwd=tmp_path)
    producer = tmp_path / "producer.py"
    source = tmp_path / "input.json"
    producer.write_text("print('producer')\n", encoding="utf-8")
    source.write_text('{"ok": true}\n', encoding="utf-8")
    subprocess.check_call(["git", "add", "producer.py", "input.json"], cwd=tmp_path)
    subprocess.check_call(
        ["git", "commit", "-m", "source"], cwd=tmp_path, stdout=subprocess.DEVNULL
    )
    source_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, text=True
    ).strip()
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
    subprocess.check_call(
        ["git", "commit", "-m", "receipt"], cwd=tmp_path, stdout=subprocess.DEVNULL
    )
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


def test_release_evidence_freshness_blocks_newer_input_dependency(
    tmp_path: Path,
) -> None:
    freshness._git_head = lambda _repo_root: "abcdef1234567890"
    producer = tmp_path / "producer.py"
    producer.write_text("print('producer')\n", encoding="utf-8")
    input_dep = tmp_path / "input.json"
    input_dep.write_text('{"ok": true}\n', encoding="utf-8")
    artifact = _write_json(
        tmp_path / "evidence.json",
        {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_commit_sha": "abcdef123456",
            "engine_version": "engine-v1",
            "input_checksums": {"input.json": "sha256:abc"},
            "reused_evidence": True,
        },
    )
    os.utime(producer, (artifact.stat().st_mtime - 5, artifact.stat().st_mtime - 5))
    future = artifact.stat().st_mtime + 30
    os.utime(input_dep, (future, future))

    payload = freshness.build_report(
        repo_root=tmp_path,
        artifacts=(("evidence", artifact, producer),),
        max_age_days=30,
    )
    row = payload["rows"][0]

    assert payload["contract_pass"] is False
    assert "evidence::input_dependency_newer_than_artifact" in payload["blockers"]
    assert row["dependency_mtime_pass"] is False
    newer = [
        detail
        for detail in row["dependency_mtime_details"]
        if detail["newer_than_artifact"]
    ]
    assert len(newer) == 1
    assert newer[0]["dependency_kind"] == "input_checksum"
    assert newer[0]["dependency_path"] == str(input_dep)
    assert any(path == str(input_dep) for path in row["input_dependency_paths"])


def test_release_evidence_freshness_ignores_non_path_input_checksum_keys(
    tmp_path: Path,
) -> None:
    freshness._git_head = lambda _repo_root: "abcdef1234567890"
    producer = tmp_path / "producer.py"
    producer.write_text("print('producer')\n", encoding="utf-8")
    artifact = _write_json(
        tmp_path / "evidence.json",
        {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_commit_sha": "abcdef123456",
            "engine_version": "engine-v1",
            "input_checksums": {"fixture": "sha256:123", "dataset": "sha256:456"},
            "reused_evidence": True,
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
    assert row["dependency_mtime_pass"] is True
    assert row["input_dependency_paths"] == []
    assert all(
        detail["dependency_kind"] == "producer"
        for detail in row["dependency_mtime_details"]
    )


def test_release_evidence_freshness_ignores_missing_optional_input_file(
    tmp_path: Path,
) -> None:
    freshness._git_head = lambda _repo_root: "abcdef1234567890"
    producer = tmp_path / "producer.py"
    producer.write_text("print('producer')\n", encoding="utf-8")
    artifact = _write_json(
        tmp_path / "evidence.json",
        {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_commit_sha": "abcdef123456",
            "engine_version": "engine-v1",
            "input_checksums": {
                "present.json": "sha256:abc",
                "absent.json": "sha256:def",
            },
            "reused_evidence": True,
        },
    )
    present = tmp_path / "present.json"
    present.write_text('{"ok": true}\n', encoding="utf-8")
    os.utime(producer, (artifact.stat().st_mtime - 5, artifact.stat().st_mtime - 5))
    os.utime(present, (artifact.stat().st_mtime - 5, artifact.stat().st_mtime - 5))

    payload = freshness.build_report(
        repo_root=tmp_path,
        artifacts=(("evidence", artifact, producer),),
        max_age_days=30,
    )
    row = payload["rows"][0]

    assert payload["contract_pass"] is True
    assert row["dependency_mtime_pass"] is True
    assert row["input_dependency_paths"] == [str(present)]
    kinds = {detail["dependency_kind"] for detail in row["dependency_mtime_details"]}
    assert kinds == {"producer", "input_checksum"}


def test_release_evidence_freshness_checks_directory_input_dependency(
    tmp_path: Path,
) -> None:
    freshness._git_head = lambda _repo_root: "abcdef1234567890"
    producer = tmp_path / "producer.py"
    producer.write_text("print('producer')\n", encoding="utf-8")
    input_dir = tmp_path / "inputs"
    input_dir.mkdir()
    (input_dir / "case.json").write_text('{"ok": true}\n', encoding="utf-8")
    artifact = _write_json(
        tmp_path / "evidence.json",
        {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_commit_sha": "abcdef123456",
            "engine_version": "engine-v1",
            "input_checksums": {"inputs": "dir-sha256:abc"},
            "reused_evidence": True,
        },
    )
    os.utime(producer, (artifact.stat().st_mtime - 5, artifact.stat().st_mtime - 5))
    future = artifact.stat().st_mtime + 30
    os.utime(input_dir, (future, future))

    payload = freshness.build_report(
        repo_root=tmp_path,
        artifacts=(("evidence", artifact, producer),),
        max_age_days=30,
    )
    row = payload["rows"][0]

    assert payload["contract_pass"] is False
    assert "evidence::input_dependency_newer_than_artifact" in payload["blockers"]
    assert row["input_dependency_paths"] == [str(input_dir)]
    newer_paths = {
        detail["dependency_path"]
        for detail in row["dependency_mtime_details"]
        if detail["newer_than_artifact"]
    }
    assert newer_paths == {str(input_dir)}


def test_release_evidence_freshness_dependency_mtime_details_for_clean_producer(
    tmp_path: Path,
) -> None:
    freshness._git_head = lambda _repo_root: "abcdef1234567890"
    producer = tmp_path / "producer.py"
    producer.write_text("print('producer')\n", encoding="utf-8")
    input_dep = tmp_path / "input.json"
    input_dep.write_text('{"ok": true}\n', encoding="utf-8")
    artifact = _write_json(
        tmp_path / "evidence.json",
        {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_commit_sha": "abcdef123456",
            "engine_version": "engine-v1",
            "input_checksums": {"input.json": "sha256:123"},
            "reused_evidence": True,
        },
    )
    os.utime(producer, (artifact.stat().st_mtime - 5, artifact.stat().st_mtime - 5))
    os.utime(input_dep, (artifact.stat().st_mtime - 5, artifact.stat().st_mtime - 5))

    payload = freshness.build_report(
        repo_root=tmp_path,
        artifacts=(("evidence", artifact, producer),),
        max_age_days=30,
    )
    row = payload["rows"][0]

    assert row["dependency_mtime_pass"] is True
    assert all(
        detail["newer_than_artifact"] is False
        for detail in row["dependency_mtime_details"]
    )
    paths = {detail["dependency_path"] for detail in row["dependency_mtime_details"]}
    assert paths == {"<producer>", str(input_dep)}
