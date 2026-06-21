from __future__ import annotations

import json
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PRODUCTIZATION = REPO_ROOT / "implementation" / "phase1" / "release_evidence" / "productization"
PM_REPORT = PRODUCTIZATION / "pm_release_gate_report.json"
SUPPORT_BUNDLE = REPO_ROOT / "implementation" / "phase1" / "support_bundle_manifest.json"


PM_JSON_ARTIFACTS = [
    PRODUCTIZATION / "pm_release_gate_report.json",
    PRODUCTIZATION / "pm_release_gate_completion_audit.json",
    PRODUCTIZATION / "pm_release_blocker_action_register.json",
    PRODUCTIZATION / "pm_release_blocker_closure_board.json",
    PRODUCTIZATION / "pm_release_gate_reviewer_handoff.json",
    PRODUCTIZATION / "pm_owner_evidence_request_packet.json",
    PRODUCTIZATION / "pm_release_reproduction_command_audit.json",
    SUPPORT_BUNDLE,
]

PM_TEXT_ARTIFACTS = [
    PRODUCTIZATION / "pm_release_gate_report.md",
    PRODUCTIZATION / "pm_release_gate_completion_audit.md",
    PRODUCTIZATION / "pm_release_blocker_action_register.md",
    PRODUCTIZATION / "pm_release_blocker_closure_board.md",
    PRODUCTIZATION / "pm_release_gate_reviewer_handoff.md",
    PRODUCTIZATION / "pm_owner_evidence_request_packet.md",
    PRODUCTIZATION / "pm_release_reproduction_command_audit.md",
    REPO_ROOT / "docs" / "pm-release-gate-milestones.md",
    REPO_ROOT / "docs" / "github-documentation-status.md",
    REPO_ROOT / "docs" / "commercialization-gap-current-state.md",
    REPO_ROOT / "docs" / "commercialization-improvement-priority-assessment.md",
]


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _summary_green_total(summary_line: str) -> tuple[int, int] | None:
    match = re.search(r"release_areas_green=(\d+)/(\d+)", summary_line)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def _canonical_release_area_evidence(payload: dict) -> dict:
    if isinstance(payload.get("canonical_release_area_evidence"), dict):
        return payload["canonical_release_area_evidence"]
    coverage = payload.get("pm_failure_bundle_coverage")
    if isinstance(coverage, dict) and isinstance(coverage.get("canonical_release_area_evidence"), dict):
        return coverage["canonical_release_area_evidence"]
    return {}


def test_pm_release_area_counts_and_blockers_are_canonical() -> None:
    report = _load_json(PM_REPORT)
    release_area_rows = [
        row for row in report["release_area_matrix"] if isinstance(row, dict)
    ]
    expected_green_total = (
        sum(1 for row in release_area_rows if row.get("ok") is True),
        len(release_area_rows),
    )
    expected_blockers = sorted(str(item) for item in report["release_area_blockers"])

    assert expected_green_total == (12, 16)
    assert len(expected_blockers) == 9
    assert _summary_green_total(report["summary_line"]) == expected_green_total

    audit = _load_json(PRODUCTIZATION / "pm_release_gate_completion_audit.json")
    audit_release_area_blockers = sorted(
        {
            str(blocker)
            for row in audit["rows"]
            if str(row.get("requirement_id", "")).startswith("release_area.")
            for blocker in row.get("blockers", [])
        }
    )
    assert audit_release_area_blockers == expected_blockers

    for path in PM_JSON_ARTIFACTS:
        payload = _load_json(path)
        for key in ("summary_line", "pm_summary_line"):
            if key in payload and "release_areas_green=" in str(payload[key]):
                assert _summary_green_total(str(payload[key])) == expected_green_total

        canonical = _canonical_release_area_evidence(payload)
        if canonical:
            assert (
                canonical["release_area_green_count"],
                canonical["release_area_total_count"],
            ) == expected_green_total
            assert canonical["release_area_summary"] == "12/16"
            assert sorted(canonical["release_area_blocker_ids"]) == expected_blockers
            assert canonical["release_area_blocker_count"] == len(expected_blockers)

    support = _load_json(SUPPORT_BUNDLE)
    coverage = support["pm_failure_bundle_coverage"]
    assert coverage["summary"]["open_blocker_count"] == 21
    assert coverage["summary"]["release_tier_blocker_count"] == 21
    assert coverage["summary"]["release_area_blocker_count"] == len(expected_blockers)
    assert sorted(coverage["release_area_blocker_ids"]) == expected_blockers


def test_pm_user_facing_artifacts_have_no_stale_13_of_16_claims() -> None:
    for path in [*PM_JSON_ARTIFACTS, *PM_TEXT_ARTIFACTS]:
        text = path.read_text(encoding="utf-8")
        assert "13/16" not in text, path
        assert "release_areas_green=13/16" not in text, path
