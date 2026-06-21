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
