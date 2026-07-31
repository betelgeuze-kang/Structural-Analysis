from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_issue_supersession_inventory.py"
MANIFEST = ROOT / "artifacts" / "manifests" / "issue_supersession_inventory.json"
SPEC = importlib.util.spec_from_file_location(
    "check_issue_supersession_inventory",
    SCRIPT,
)
assert SPEC is not None and SPEC.loader is not None
inventory = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(inventory)


def _payload() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _write(tmp_path: Path, payload: dict) -> Path:
    path = tmp_path / "inventory.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_inventory_covers_open_resolved_superseded_and_orphan_classes() -> None:
    report = inventory.build_report(ROOT)

    assert report["contract_pass"] is True
    assert report["open_issue_count"] == 4
    assert report["implemented_but_open_issue_count"] == 0
    assert report["orphan_issue_count"] == 0
    assert report["resolved_issue_count"] == 5
    assert report["superseded_pull_request_count"] == 5


def test_merged_implementation_on_open_issue_must_be_in_implemented_open_list(
    tmp_path: Path,
) -> None:
    payload = deepcopy(_payload())
    payload["open_issues"][0]["merged_implementation_pull_requests"] = [999]

    report = inventory.build_report(
        ROOT,
        inventory_path=_write(tmp_path, payload),
    )

    assert report["contract_pass"] is False
    assert "implemented_but_open_issue_inventory_inconsistent" in report["blockers"]


def test_unlinked_open_issue_must_be_in_orphan_list(tmp_path: Path) -> None:
    payload = deepcopy(_payload())
    payload["open_issues"][0]["linked_pull_requests"] = []

    report = inventory.build_report(
        ROOT,
        inventory_path=_write(tmp_path, payload),
    )

    assert report["contract_pass"] is False
    assert "orphan_issue_inventory_inconsistent" in report["blockers"]


def test_superseded_pr_requires_normalization_comment(tmp_path: Path) -> None:
    payload = deepcopy(_payload())
    payload["superseded_pull_requests"][0].pop("normalization_comment_id")

    report = inventory.build_report(
        ROOT,
        inventory_path=_write(tmp_path, payload),
    )

    assert report["contract_pass"] is False
    assert "supersession_comment_missing:206" in report["blockers"]
