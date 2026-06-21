from __future__ import annotations

import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = (
    REPO_ROOT
    / "implementation"
    / "phase1"
    / "release_evidence"
    / "productization"
    / "product_readiness_snapshot.json"
)
INDEPENDENT_PRODUCT = (
    REPO_ROOT / "implementation" / "phase1" / "release" / "independent_product_readiness.json"
)
DOCS = [
    REPO_ROOT / "README.md",
    REPO_ROOT / "docs" / "commercialization-gap-current-state.md",
]


def test_readiness_snapshot_summary_is_doc_synced() -> None:
    payload = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    expected = (
        "Canonical product readiness snapshot: "
        f"status `{payload['status']}`, "
        f"blocker_count `{payload['blocker_count']}`, "
        f"paid_pilot_ready=`{str(payload['paid_pilot_ready']).lower()}`, "
        f"release_ready=`{str(payload['release_ready']).lower()}`"
    )

    for path in DOCS:
        assert expected in path.read_text(encoding="utf-8"), path


def test_docs_do_not_claim_github_sync_complete_while_snapshot_blocks() -> None:
    payload = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    github_sync_blocked = any(
        str(blocker).startswith("pm_release::github_sync::")
        for blocker in payload["blockers"]
    )
    if not github_sync_blocked:
        return

    forbidden = "GitHub development sync is complete"
    for path in DOCS:
        text = path.read_text(encoding="utf-8")
        assert forbidden not in text, path


def test_readme_independent_product_score_matches_receipt() -> None:
    payload = json.loads(INDEPENDENT_PRODUCT.read_text(encoding="utf-8"))
    expected = (
        "Independent commercial product status:"
        " `python3 scripts/check_independent_product_readiness.py --json`"
    )
    expected_score = (
        f"Current status is {payload['status']} at "
        f"`{payload['readiness_score']}/100`"
    )
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

    assert expected in readme
    assert expected_score in readme
