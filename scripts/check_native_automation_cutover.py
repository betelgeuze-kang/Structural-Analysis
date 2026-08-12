#!/usr/bin/env python3
"""Fail closed on active remote mutation after the native deployment cutover."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = Path("native/decommission/production-automation-v1.json")
ARCHIVE_ROOT = Path("deployment/legacy-python-release-publication")
ARCHIVED_EVIDENCE_WORKFLOW = ARCHIVE_ROOT / "authoritative-core-evidence-resync.yml"
ARCHIVED_RELEASE_WORKFLOW = ARCHIVE_ROOT / "release-publish.yml"
ARCHIVED_DISPATCHER = ARCHIVE_ROOT / "scripts/dispatch_release_publish_workflow.py"
ARCHIVED_PUBLISHER = ARCHIVE_ROOT / "scripts/publish_github_release_assets.py"
ARCHIVED_README = ARCHIVE_ROOT / "README.md"

REQUIRED_FILES = (
    MANIFEST,
    ARCHIVED_EVIDENCE_WORKFLOW,
    ARCHIVED_RELEASE_WORKFLOW,
    ARCHIVED_DISPATCHER,
    ARCHIVED_PUBLISHER,
    ARCHIVED_README,
    Path("native/capabilities.json"),
)

RETIRED_ACTIVE_PATHS = (
    Path(".github/workflows/authoritative-core-evidence-resync.yml"),
    Path(".github/workflows/release-publish.yml"),
    Path("scripts/dispatch_release_publish_workflow.py"),
    Path("scripts/publish_github_release_assets.py"),
)

FORBIDDEN_ACTIVE_WORKFLOW_TOKENS = (
    "contents: write",
    "pages: write",
    "packages: write",
    "deployments: write",
    "git push",
    "publish_github_release_assets.py",
    "dispatch_release_publish_workflow.py",
)


def _text(root: Path, relative: Path, blockers: list[str]) -> str:
    try:
        return (root / relative).read_text(encoding="utf-8")
    except OSError as exc:
        blockers.append(f"automation_cutover_file_unreadable:{relative.as_posix()}:{exc}")
        return ""


def _json_object(root: Path, relative: Path, blockers: list[str]) -> dict[str, Any]:
    text = _text(root, relative, blockers)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        blockers.append(f"automation_cutover_json_invalid:{relative.as_posix()}:{exc}")
        return {}
    if not isinstance(payload, dict):
        blockers.append(f"automation_cutover_json_not_object:{relative.as_posix()}")
        return {}
    return payload


def _require_tokens(
    relative: Path,
    text: str,
    tokens: tuple[str, ...],
    blockers: list[str],
) -> None:
    for token in tokens:
        if token not in text:
            blockers.append(
                f"automation_cutover_token_missing:{relative.as_posix()}:{token}"
            )


def check_native_automation_cutover(repo_root: Path = ROOT) -> dict[str, object]:
    root = repo_root.resolve()
    blockers: list[str] = []
    for relative in REQUIRED_FILES:
        if not (root / relative).is_file():
            blockers.append(f"automation_cutover_file_missing:{relative.as_posix()}")
    for relative in RETIRED_ACTIVE_PATHS:
        if (root / relative).exists():
            blockers.append(f"retired_mutation_entrypoint_reactivated:{relative.as_posix()}")

    workflow_dir = root / ".github/workflows"
    workflows = sorted(
        [*workflow_dir.glob("*.yml"), *workflow_dir.glob("*.yaml")]
    ) if workflow_dir.is_dir() else []
    active_contents_write: list[str] = []
    active_branch_push: list[str] = []
    for path in workflows:
        relative = path.relative_to(root).as_posix()
        lowered = path.read_text(encoding="utf-8", errors="replace").lower()
        for token in FORBIDDEN_ACTIVE_WORKFLOW_TOKENS:
            if token in lowered:
                blockers.append(f"active_remote_mutation_authority:{relative}:{token}")
                if token == "contents: write":
                    active_contents_write.append(relative)
                if token == "git push":
                    active_branch_push.append(relative)

    evidence_workflow = _text(root, ARCHIVED_EVIDENCE_WORKFLOW, blockers)
    _require_tokens(
        ARCHIVED_EVIDENCE_WORKFLOW,
        evidence_workflow,
        (
            "ARCHIVED - Authoritative Core Evidence Resync",
            "contents: write",
            "actions/setup-python@",
            "git push origin",
        ),
        blockers,
    )
    release_workflow = _text(root, ARCHIVED_RELEASE_WORKFLOW, blockers)
    _require_tokens(
        ARCHIVED_RELEASE_WORKFLOW,
        release_workflow,
        (
            "ARCHIVED - Publish Release Assets",
            "contents: write",
            "actions/setup-python@",
            "actions/setup-node@",
            "scripts/publish_github_release_assets.py",
            "git push origin",
        ),
        blockers,
    )
    dispatcher = _text(root, ARCHIVED_DISPATCHER, blockers)
    _require_tokens(
        ARCHIVED_DISPATCHER,
        dispatcher,
        ("Archived rollback-only dispatcher", 'method="POST"'),
        blockers,
    )
    publisher = _text(root, ARCHIVED_PUBLISHER, blockers)
    _require_tokens(
        ARCHIVED_PUBLISHER,
        publisher,
        ("Archived rollback-only publisher", 'method="DELETE"', 'method="POST"'),
        blockers,
    )
    readme = _text(root, ARCHIVED_README, blockers)
    _require_tokens(
        ARCHIVED_README,
        readme,
        (
            "rollback-only archive",
            "GitHub cannot dispatch",
            "explicit human review",
            "Removal remains disallowed",
        ),
        blockers,
    )

    manifest = _json_object(root, MANIFEST, blockers)
    expected_fields: dict[str, object] = {
        "schema_version": "native-production-automation-cutover.v1",
        "status": "implemented",
        "cutover_gate": "C5",
        "owner": "structural-distribution",
        "active_contents_write_workflows": [],
        "active_branch_push_workflows": [],
        "active_python_release_mutators": [],
        "technical_receipt_workflows_retained": True,
        "c6_complete": False,
    }
    for field, expected in expected_fields.items():
        if manifest.get(field) != expected:
            blockers.append(f"automation_cutover_manifest_field_invalid:{field}")
    retired = manifest.get("retired_entrypoints")
    retired_index = {
        str(row.get("path", "")): row
        for row in retired
        if isinstance(row, dict)
    } if isinstance(retired, list) else {}
    for relative in (
        ARCHIVED_EVIDENCE_WORKFLOW,
        ARCHIVED_RELEASE_WORKFLOW,
        ARCHIVED_DISPATCHER,
        ARCHIVED_PUBLISHER,
    ):
        row = retired_index.get(relative.as_posix())
        if (
            row is None
            or row.get("rollback_only") is not True
            or row.get("removal_allowed") is not False
        ):
            blockers.append(
                f"automation_cutover_retired_entry_invalid:{relative.as_posix()}"
            )
    remaining = manifest.get("remaining_c6_blockers")
    if not isinstance(remaining, list) or len(remaining) < 4:
        blockers.append("automation_cutover_c6_blockers_not_preserved")

    capabilities = _json_object(root, Path("native/capabilities.json"), blockers)
    mapping = capabilities.get("capabilities")
    capability = mapping.get("native_automation_cutover") if isinstance(
        mapping, dict
    ) else None
    if not isinstance(capability, dict):
        blockers.append("native_automation_cutover_capability_missing")
    else:
        for field, expected in (
            ("status", "implemented"),
            ("cutover_gate", "C5"),
            ("owner", "structural-distribution"),
        ):
            if capability.get(field) != expected:
                blockers.append(f"native_automation_cutover_capability_invalid:{field}")
        claim = str(capability.get("claim", ""))
        for token in (
            "contents:write and branch-push authority 0",
            "rollback-only",
            "final C6 remain open",
        ):
            if token not in claim:
                blockers.append(
                    f"native_automation_cutover_capability_claim_missing:{token}"
                )

    blockers = sorted(set(blockers))
    return {
        "schema_version": "native-automation-cutover-check.v1",
        "status": "pass" if not blockers else "blocked",
        "contract_pass": not blockers,
        "active_workflow_count": len(workflows),
        "active_contents_write_workflows": sorted(set(active_contents_write)),
        "active_branch_push_workflows": sorted(set(active_branch_push)),
        "active_python_release_mutators": [
            relative.as_posix()
            for relative in RETIRED_ACTIVE_PATHS[2:]
            if (root / relative).exists()
        ],
        "technical_receipt_workflows_retained": manifest.get(
            "technical_receipt_workflows_retained"
        ),
        "c6_complete": False,
        "blockers": blockers,
        "claim_boundary": (
            "This proves only the C5 removal of active repository/release mutation authority "
            "from Python/Node workflows and helpers. Read-only oracle/technical workflows, "
            "source deletion, external signing/import, protected HIP C2 and final C6 remain open."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    args = parser.parse_args()
    report = check_native_automation_cutover(args.repo_root)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"Native automation cutover: {report['status']}")
        for blocker in report["blockers"]:
            print(f"- {blocker}")
    return 1 if args.fail_blocked and not report["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
