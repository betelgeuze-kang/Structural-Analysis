from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/check_repository_hygiene_inventory.py"
SPEC = importlib.util.spec_from_file_location(
    "check_repository_hygiene_inventory", SCRIPT
)
assert SPEC is not None and SPEC.loader is not None
inventory = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(inventory)


def test_hygiene_inventory_is_valid_but_does_not_claim_external_closure() -> None:
    report = inventory.build_report(ROOT)

    assert report["contract_pass"] is True
    assert report["closure_pass"] is False
    assert report["open_pull_request_count"] == 1
    assert report["stale_remote_branch_count"] == 0
    assert report["external_actions_performed"] == []
    assert "open_pr_137_metadata_inconsistent" in report["closure_blockers"]
