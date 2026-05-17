from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "report_source_boundary_footprint.py"
SPEC = importlib.util.spec_from_file_location("report_source_boundary_footprint", SCRIPT_PATH)
assert SPEC is not None
report_source_boundary_footprint = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(report_source_boundary_footprint)


def test_source_boundary_footprint_report_keeps_non_destructive_contract(tmp_path: Path) -> None:
    tracked = tmp_path / "tracked.txt"
    tracked.write_text("src/example.py\n", encoding="utf-8")
    allowlist = tmp_path / "allowlist.json"
    allowlist.write_text(
        json.dumps({"schema_version": "source-boundary-allowlist.v1", "records": []}),
        encoding="utf-8",
    )
    runbook = tmp_path / "runbook.md"
    runbook.write_text("restore", encoding="utf-8")

    payload = report_source_boundary_footprint.build_footprint_report(
        files=["src/example.py"],
        allowlist_manifest=allowlist,
        restore_runbook=runbook,
        large_file_threshold_mib=10,
    )

    assert payload["schema_version"] == "source-boundary-footprint-report.v1"
    assert payload["contract_pass"] is True
    assert payload["non_destructive_policy"] is True
    assert payload["cleanup_policy"] == "report_only_no_git_rm_cached_no_history_rewrite"
    assert payload["candidate_files"] == 0
    assert payload["restore_runbook_present"] is True


def test_source_boundary_footprint_report_blocks_missing_runbook(tmp_path: Path) -> None:
    allowlist = tmp_path / "allowlist.json"
    allowlist.write_text(
        json.dumps({"schema_version": "source-boundary-allowlist.v1", "records": []}),
        encoding="utf-8",
    )
    payload = report_source_boundary_footprint.build_footprint_report(
        files=["src/example.py"],
        allowlist_manifest=allowlist,
        restore_runbook=tmp_path / "missing.md",
        large_file_threshold_mib=10,
    )

    assert payload["contract_pass"] is False
    assert payload["reason_code"] == "ERR_SOURCE_BOUNDARY_FOOTPRINT_CONTRACT"
