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
    assert "git push origin HEAD:main" == payload["commands"]["main_fast_forward_push"]
    assert "read-only" in payload["claim_boundary"]


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
    assert payload["remote_sync_needed"] is False
    assert payload["blockers"] == []


def test_sync_preflight_allows_ready_push_only_with_explicit_approval() -> None:
    payload = sync_preflight.build_report(_state(), remote_mutation_approved=True)

    assert payload["status"] == "ready_to_push"
    assert payload["contract_pass"] is True
    assert payload["checks"]["explicit_remote_mutation_approval"] is True
    assert payload["blockers"] == []


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
