from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "build_workstation_job_retention_policy.py"
SPEC = importlib.util.spec_from_file_location("build_workstation_job_retention_policy", SCRIPT_PATH)
assert SPEC is not None
build_workstation_job_retention_policy = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(build_workstation_job_retention_policy)


def test_job_retention_policy_passes_with_latest_job(tmp_path: Path) -> None:
    job_root = tmp_path / "jobs"
    job_dir = job_root / "J1"
    job_dir.mkdir(parents=True)
    (job_dir / "checksums.sha256").write_text("abc  input_manifest.json\n", encoding="utf-8")
    (job_root / "latest_job_id.txt").write_text("J1\n", encoding="utf-8")

    payload = build_workstation_job_retention_policy.build_workstation_job_retention_policy(job_root=job_root)

    assert payload["schema_version"] == "workstation-job-retention-policy.v1"
    assert payload["contract_pass"] is True
    assert payload["policy"]["delete_requires_explicit_confirmation"] is True
    assert payload["cleanup_policy"]["automatic_delete_enabled"] is False
    assert payload["cleanup_preview"]["mode"] == "dry_run_only"
    assert payload["cleanup_preview"]["delete_operation_executed"] is False


def test_job_retention_policy_blocks_missing_latest(tmp_path: Path) -> None:
    job_root = tmp_path / "jobs"
    job_root.mkdir()

    payload = build_workstation_job_retention_policy.build_workstation_job_retention_policy(job_root=job_root)

    assert payload["contract_pass"] is False
    assert "latest_job_id_missing" in payload["blockers"]


def test_job_retention_policy_lists_stale_jobs_without_deleting(tmp_path: Path) -> None:
    job_root = tmp_path / "jobs"
    old_job = job_root / "20000101T000000-old"
    latest_job = job_root / "20990101T000000-new"
    old_job.mkdir(parents=True)
    latest_job.mkdir(parents=True)
    (old_job / "checksums.sha256").write_text("abc  input_manifest.json\n", encoding="utf-8")
    (latest_job / "checksums.sha256").write_text("def  input_manifest.json\n", encoding="utf-8")
    (job_root / "latest_job_id.txt").write_text("20990101T000000-new\n", encoding="utf-8")

    payload = build_workstation_job_retention_policy.build_workstation_job_retention_policy(
        job_root=job_root,
        retention_days=30,
        max_completed_jobs=1,
    )

    preview = payload["cleanup_preview"]
    assert payload["contract_pass"] is True
    assert preview["delete_operation_executed"] is False
    assert preview["candidate_count"] == 1
    assert preview["candidate_rows"][0]["job_id"] == "20000101T000000-old"
    assert "older_than_retention_days" in preview["candidate_rows"][0]["reasons"]
