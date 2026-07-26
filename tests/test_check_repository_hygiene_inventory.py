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
    assert report["open_pull_request_count"] == 2
    assert report["stale_remote_branch_count"] == 0
    assert report["external_actions_performed"] == []
    assert "open_pr_215_conflicts_with_default_branch" in report["closure_blockers"]
    assert "external_pr_or_branch_mutation_not_authorized" in report["closure_blockers"]


def test_hygiene_inventory_rejects_incomplete_open_pull_request_enumeration(
    tmp_path,
) -> None:
    import json

    source = ROOT / "artifacts/manifests/repository_hygiene_inventory.json"
    payload = json.loads(source.read_text(encoding="utf-8"))
    payload["observed_open_pull_request_count"] = len(payload["open_pull_requests"]) + 1
    target = tmp_path / "inventory.json"
    target.write_text(json.dumps(payload), encoding="utf-8")

    report = inventory.build_report(ROOT, inventory_path=target)

    assert report["contract_pass"] is False
    assert "open_pull_request_inventory_incomplete" in report["blockers"]


def test_hygiene_inventory_rejects_inferred_disposition_authority(tmp_path) -> None:
    import json

    source = ROOT / "artifacts/manifests/repository_hygiene_inventory.json"
    payload = json.loads(source.read_text(encoding="utf-8"))
    payload["open_pull_requests"][0]["disposition_authorized"] = True
    target = tmp_path / "inventory.json"
    target.write_text(json.dumps(payload), encoding="utf-8")

    report = inventory.build_report(ROOT, inventory_path=target)

    assert report["contract_pass"] is False
    assert any(
        blocker.startswith("disposition_authority_must_not_be_inferred")
        for blocker in report["blockers"]
    )
