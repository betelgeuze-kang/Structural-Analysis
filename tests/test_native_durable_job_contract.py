from __future__ import annotations

import importlib.util
from pathlib import Path
import shutil
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_native_durable_jobs.py"
SPEC = importlib.util.spec_from_file_location("check_native_durable_jobs", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
durable = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = durable
SPEC.loader.exec_module(durable)


def _copy_contract(tmp_path: Path) -> None:
    for relative in ("native/capabilities.json", *durable.REQUIRED_TOKENS):
        source = ROOT / relative
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)


def test_repository_durable_job_contract_is_evidence_backed() -> None:
    report = durable.check_durable_job_contract(ROOT)

    assert report["contract_pass"] is True
    assert report["cutover_gate"] == "C5"
    assert report["blockers"] == []


def test_contract_fails_closed_when_expired_lease_evidence_disappears(
    tmp_path: Path,
) -> None:
    _copy_contract(tmp_path)
    path = tmp_path / "native/crates/structural-runtime/tests/durable_job.rs"
    text = path.read_text(encoding="utf-8").replace(
        "expired_lease_recovers_after_reopen_and_stale_worker_is_rejected",
        "lease_recovery_evidence_removed",
    )
    path.write_text(text, encoding="utf-8")

    report = durable.check_durable_job_contract(tmp_path)

    assert report["contract_pass"] is False
    assert (
        "durable_job_evidence_token_missing:"
        "native/crates/structural-runtime/tests/durable_job.rs:"
        "expired_lease_recovers_after_reopen_and_stale_worker_is_rejected"
        in report["blockers"]
    )
