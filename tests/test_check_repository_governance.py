from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_repository_governance.py"
SPEC = importlib.util.spec_from_file_location("check_repository_governance", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
governance = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(governance)


def test_repository_governance_contract_passes_without_claiming_legal_approval() -> None:
    report = governance.build_report(ROOT)

    assert report["contract_pass"] is True
    assert report["license_posture"] == "all_rights_reserved_no_license_granted"
    assert report["product_license_approval_claimed"] is False
    assert "does not prove legal approval" in report["claim_boundary"]
    assert report["blockers"] == []


def test_repository_governance_fails_closed_for_an_empty_repository(
    tmp_path: Path,
) -> None:
    report = governance.build_report(tmp_path)

    assert report["contract_pass"] is False
    assert report["status"] == "blocked"
    for relative in governance.REQUIRED_FILES:
        assert f"missing_required_file:{relative.as_posix()}" in report["blockers"]


def test_repository_governance_cli_emits_machine_readable_report() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--json"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)

    assert result.returncode == 0
    assert payload["status"] == "pass"
    assert payload["contract_pass"] is True
