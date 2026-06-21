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
PM_BLOCKER_REGISTER = (
    REPO_ROOT
    / "implementation"
    / "phase1"
    / "release_evidence"
    / "productization"
    / "pm_release_blocker_action_register.json"
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


def test_docs_pm_release_area_and_handoff_counts_match_register() -> None:
    payload = json.loads(PM_BLOCKER_REGISTER.read_text(encoding="utf-8"))
    summary = payload["summary"]
    green = int(summary["release_area_green_count"])
    total = int(summary["release_area_total_count"])
    open_count = int(summary["open_blocker_count"])
    release_area_count = int(summary["release_area_blocker_count"])
    fresh_count = int(summary["local_remediation_ready_count"])
    external_customer_count = open_count - release_area_count - fresh_count
    expected_fragments = [
        f"{green}/{total}",
        f"`{open_count}`",
        f"`{release_area_count}`",
        f"`{external_customer_count}`",
        f"`{fresh_count}`",
    ]

    for path in DOCS:
        text = path.read_text(encoding="utf-8")
        for fragment in expected_fragments:
            assert fragment in text, (path, fragment)


def test_docs_describe_release_mode_as_non_mutating_checks() -> None:
    required_fragments = [
        "check_github_actions_self_hosted_runner_status.py",
        "--check --fail-blocked",
        "build_product_readiness_snapshot.py",
        "without rewriting tracked evidence",
    ]
    runner_query_failure_fragments = [
        "query failure remains a blocker",
        "query failure는 blocker로 남기며",
    ]
    forbidden_fragments = [
        "Release mode refreshes that self-hosted runner status",
        "refreshes self-hosted runner status, rebuilds the canonical product readiness snapshot",
        "self-hosted runner 상태를 다시 수집",
    ]

    for path in DOCS:
        text = path.read_text(encoding="utf-8")
        for fragment in required_fragments[:3]:
            assert fragment in text, (path, fragment)
        assert (
            required_fragments[3] in text
            or "재작성하지 않고 `--check`로 검증" in text
        ), path
        assert any(fragment in text for fragment in runner_query_failure_fragments), path
        for fragment in forbidden_fragments:
            assert fragment not in text, (path, fragment)
