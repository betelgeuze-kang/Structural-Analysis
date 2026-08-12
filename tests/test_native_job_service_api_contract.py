from __future__ import annotations

import importlib.util
from pathlib import Path
import shutil
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_native_job_service_api.py"
SPEC = importlib.util.spec_from_file_location("check_native_job_service_api", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
job_service_api = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = job_service_api
SPEC.loader.exec_module(job_service_api)


def _copy_contract(tmp_path: Path) -> None:
    for relative in ("native/capabilities.json", *job_service_api.REQUIRED_TOKENS):
        source = ROOT / relative
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)


def test_repository_job_service_api_contract_is_evidence_backed() -> None:
    report = job_service_api.check_job_service_api_contract(ROOT)

    assert report["contract_pass"] is True
    assert report["cutover_gate"] == "C5"
    assert report["blockers"] == []


def test_contract_fails_closed_when_process_kill_evidence_disappears(
    tmp_path: Path,
) -> None:
    _copy_contract(tmp_path)
    path = tmp_path / "native/crates/structural-cli/tests/job_service_api_cli.rs"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "first.kill()",
            "first.wait()",
        ),
        encoding="utf-8",
    )

    report = job_service_api.check_job_service_api_contract(tmp_path)

    assert report["contract_pass"] is False
    assert any(
        blocker.endswith(":first.kill()") for blocker in report["blockers"]
    )
