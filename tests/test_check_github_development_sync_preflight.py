from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parent.parent
    / "scripts"
    / "check_github_development_sync_preflight.py"
)
SPEC = importlib.util.spec_from_file_location("check_github_development_sync_preflight", SCRIPT_PATH)
assert SPEC is not None
sync_preflight = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(sync_preflight)


def _state(**overrides: object) -> dict[str, object]:
    state: dict[str, object] = {
        "branch": "codex/create-architecture-definition-document-for-hybrid-ai",
        "local_head_sha": "abc1234",
        "remote_feature_ref": "origin/codex/create-architecture-definition-document-for-hybrid-ai",
        "remote_feature_sha": "def5678",
        "remote_main_ref": "origin/main",
        "remote_main_sha": "012abcd",
        "remote_safety": {
            "errors": [],
            "expected_slug": "betelgeuze-kang/Structural-Analysis",
            "ok": True,
            "remotes": {
                "origin": ["https://github.com/betelgeuze-kang/Structural-Analysis.git"]
            },
        },
        "worktree_status_short": "",
        "feature_ahead_count": 2,
        "main_ahead_count": 4,
        "feature_fast_forward_possible": True,
        "main_fast_forward_possible": True,
    }
    state.update(overrides)
    return state


def test_sync_preflight_requires_r4_approval_for_ready_remote_mutation() -> None:
    payload = sync_preflight.build_report(_state())

    assert payload["status"] == "approval_required"
    assert payload["contract_pass"] is False
    assert payload["preflight_pass"] is True
    assert payload["remote_sync_needed"] is True
    assert payload["blockers"] == ["remote_mutation_approval_required"]
    assert payload["checks"]["feature_fast_forward_possible"] is True
    assert payload["checks"]["main_fast_forward_possible"] is True
    assert payload["checks"]["remote_safety_ok"] is True
    assert payload["pending_remote_updates"] == [
        {
            "target": "origin/codex/create-architecture-definition-document-for-hybrid-ai",
            "action": "push current HEAD to feature",
            "command": (
                "git push origin "
                "codex/create-architecture-definition-document-for-hybrid-ai:"
                "codex/create-architecture-definition-document-for-hybrid-ai"
            ),
            "rollback": "restore feature to previous remote SHA def5678 with an approved restore action",
        },
        {
            "target": "origin/main",
            "action": "fast-forward push current HEAD to main",
            "command": "git push origin HEAD:main",
            "rollback": "restore main to previous remote SHA 012abcd with an approved revert/restore action",
        },
    ]
    assert payload["r4_disclosure"]["target"] == [
        "origin/codex/create-architecture-definition-document-for-hybrid-ai",
        "origin/main",
    ]
    assert "git push origin HEAD:main" == payload["commands"]["main_fast_forward_push"]
    assert "read-only" in payload["claim_boundary"]


def test_sync_preflight_feature_push_command_uses_remote_feature_ref() -> None:
    payload = sync_preflight.build_report(
        _state(
            branch="codex/seed-pr-ci-source-evidence",
            remote_feature_ref="origin/codex/seed-pr-ci-source-evidence",
        )
    )

    assert payload["pending_remote_updates"][0]["target"] == (
        "origin/codex/seed-pr-ci-source-evidence"
    )
    assert payload["pending_remote_updates"][0]["command"] == (
        "git push origin "
        "codex/seed-pr-ci-source-evidence:codex/seed-pr-ci-source-evidence"
    )


def test_collect_git_state_defaults_to_current_upstream(monkeypatch) -> None:
    def fake_git_output(args, *, cwd=Path(".")):
        command = tuple(args)
        if command == ("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"):
            return "origin/codex/seed-pr-ci-source-evidence"
        if command == ("rev-parse", "--abbrev-ref", "HEAD"):
            return "codex/seed-pr-ci-source-evidence"
        if command == ("rev-parse", "HEAD"):
            return "head-sha"
        if command == ("rev-parse", "origin/codex/seed-pr-ci-source-evidence"):
            return "feature-sha"
        if command == ("rev-parse", "origin/main"):
            return "main-sha"
        if command == ("remote", "-v"):
            return "origin\thttps://github.com/betelgeuze-kang/Structural-Analysis.git (fetch)"
        if command == ("status", "--short"):
            return ""
        raise AssertionError(command)

    monkeypatch.setattr(sync_preflight, "_git_output", fake_git_output)
    monkeypatch.setattr(sync_preflight, "_ahead_count", lambda ref, *, cwd=Path("."): 0)
    monkeypatch.setattr(sync_preflight, "_git_success", lambda args, *, cwd=Path("."): True)

    state = sync_preflight.collect_git_state()

    assert state["remote_feature_ref"] == "origin/codex/seed-pr-ci-source-evidence"
    assert state["branch"] == "codex/seed-pr-ci-source-evidence"


def test_sync_preflight_passes_when_already_synced_without_remote_mutation() -> None:
    payload = sync_preflight.build_report(
        _state(
            remote_feature_sha="abc1234",
            remote_main_sha="abc1234",
            feature_ahead_count=0,
            main_ahead_count=0,
        )
    )

    assert payload["status"] == "synced"
    assert payload["contract_pass"] is True
    assert payload["source_commit_sha"] == "abc1234"
    assert payload["remote_sync_needed"] is False
    assert payload["blockers"] == []
    assert payload["pending_remote_updates"] == []
    assert payload["receipt_commit_boundary"] == {
        "source_commit_sha": "abc1234",
        "post_receipt_commit_delta_policy": "productization_or_surface_receipts_only",
        "claim_boundary": (
            "This receipt records GitHub sync state at source_commit_sha. A later commit "
            "that only refreshes productization/surface evidence can remain fresh in the "
            "PM gate as an evidence-only delta; any source-code or non-evidence delta must "
            "regenerate this preflight before claiming GitHub sync release credit."
        ),
    }
    assert payload["r4_disclosure"]["action"] == "no remote mutation required"
    assert payload["r4_disclosure"]["risk"] == "No remote mutation remains."


def test_sync_preflight_reports_only_main_update_after_feature_is_synced() -> None:
    payload = sync_preflight.build_report(
        _state(
            remote_feature_sha="abc1234",
            feature_ahead_count=0,
            main_ahead_count=4,
        )
    )

    assert payload["status"] == "approval_required"
    assert payload["checks"]["feature_synced_to_head"] is True
    assert payload["checks"]["main_synced_to_head"] is False
    assert payload["pending_remote_updates"] == [
        {
            "target": "origin/main",
            "action": "fast-forward push current HEAD to main",
            "command": "git push origin HEAD:main",
            "rollback": "restore main to previous remote SHA 012abcd with an approved revert/restore action",
        }
    ]
    assert payload["r4_disclosure"]["target"] == ["origin/main"]
    assert payload["r4_disclosure"]["action"] == "fast-forward push current HEAD to main"
    assert "Main CI" in payload["r4_disclosure"]["risk"]


def test_sync_preflight_allows_ready_push_only_with_explicit_approval() -> None:
    payload = sync_preflight.build_report(_state(), remote_mutation_approved=True)

    assert payload["status"] == "ready_to_push"
    assert payload["contract_pass"] is True
    assert payload["checks"]["explicit_remote_mutation_approval"] is True
    assert payload["blockers"] == []


def test_sync_preflight_records_successful_remote_fetch() -> None:
    payload = sync_preflight.build_report(
        _state(),
        remote_mutation_approved=True,
        remote_fetch_attempted=True,
        remote_fetch_ok=True,
    )

    assert payload["contract_pass"] is True
    assert payload["remote_fetch_attempted"] is True
    assert payload["remote_fetch_ok"] is True
    assert payload["checks"]["remote_fetch_ok"] is True
    assert "remote_fetch_failed" not in payload["blockers"]


def test_sync_preflight_blocks_failed_remote_fetch() -> None:
    payload = sync_preflight.build_report(
        _state(),
        remote_mutation_approved=True,
        remote_fetch_attempted=True,
        remote_fetch_ok=False,
    )

    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is False
    assert payload["preflight_pass"] is False
    assert payload["checks"]["remote_fetch_ok"] is False
    assert "remote_fetch_failed" in payload["blockers"]


def test_sync_preflight_blocks_dirty_or_non_fast_forward_state() -> None:
    payload = sync_preflight.build_report(
        _state(
            worktree_status_short=" M README.md",
            main_fast_forward_possible=False,
        ),
        remote_mutation_approved=True,
    )

    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is False
    assert "worktree_not_clean" in payload["blockers"]
    assert "main_remote_not_ancestor_of_head" in payload["blockers"]


def test_sync_preflight_ignores_release_evidence_dirty_for_sync_gate() -> None:
    payload = sync_preflight.build_report(
        _state(
            remote_feature_sha="abc1234",
            feature_ahead_count=0,
            worktree_status_short=(
                "M implementation/phase1/release_evidence/productization/"
                "developer_preview_rc_status.json\n"
                " M implementation/phase1/release_evidence/productization/"
                "pm_release_gate_report.json\n"
                " M implementation/phase1/release_evidence/productization/"
                "structural_product_development_roadmap.json\n"
                " M implementation/phase1/release_evidence/surface/"
                "product_capabilities_surface.json\n"
                " M implementation/phase1/support_bundle_manifest.json"
            ),
        )
    )

    assert payload["status"] == "approval_required"
    assert payload["preflight_pass"] is True
    assert "worktree_not_clean" not in payload["blockers"]
    assert payload["checks"]["worktree_clean"] is True
    assert payload["checks"]["worktree_only_ignored_evidence_dirty"] is True
    assert payload["state"]["effective_worktree_status_short"] == ""
    assert "developer_preview_rc_status.json" in payload["state"]["ignored_worktree_status_short"]
    assert "pm_release_gate_report.json" in payload["state"]["ignored_worktree_status_short"]
    assert "product_capabilities_surface.json" in payload["state"]["ignored_worktree_status_short"]
    assert "support_bundle_manifest.json" in payload["state"]["ignored_worktree_status_short"]


def test_sync_preflight_blocks_wrong_remote_even_with_approval() -> None:
    payload = sync_preflight.build_report(
        _state(
            remote_safety={
                "errors": [
                    "protected remote `origin` must point to betelgeuze-kang/Structural-Analysis"
                ],
                "expected_slug": "betelgeuze-kang/Structural-Analysis",
                "ok": False,
                "remotes": {
                    "origin": ["https://github.com/betelgeuze-kang/Monet-wedding.git"]
                },
            }
        ),
        remote_mutation_approved=True,
    )

    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is False
    assert payload["checks"]["remote_safety_ok"] is False
    assert "remote_safety_failed" in payload["blockers"]
