from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/check_large_git_blobs.py"
SPEC = importlib.util.spec_from_file_location("check_large_git_blobs", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


def test_current_head_has_no_unapproved_blob_above_25_mib() -> None:
    report = audit.build_report(ROOT, scope="current")

    assert report["threshold_bytes"] == 25 * 1024 * 1024
    assert report["contract_pass"] is True
    assert report["oversized_blob_count"] == 0
    assert report["unapproved_oversized_blob_count"] == 0
    assert report["history_rewrite_authorized"] is False
    assert report["p0_required_scope"] == "all_history"
