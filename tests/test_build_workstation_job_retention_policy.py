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


def test_job_retention_policy_blocks_missing_latest(tmp_path: Path) -> None:
    job_root = tmp_path / "jobs"
    job_root.mkdir()

    payload = build_workstation_job_retention_policy.build_workstation_job_retention_policy(job_root=job_root)

    assert payload["contract_pass"] is False
    assert "latest_job_id_missing" in payload["blockers"]
