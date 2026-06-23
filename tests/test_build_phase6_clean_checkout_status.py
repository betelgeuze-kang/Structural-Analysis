from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts/build_phase6_clean_checkout_status.py"
for candidate in (REPO_ROOT / "scripts", REPO_ROOT / "src"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

spec = importlib.util.spec_from_file_location("build_phase6_clean_checkout_status", SCRIPT_PATH)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def test_phase6_clean_checkout_status_blocks_on_git_clean_clone_cleanup() -> None:
    payload = module.build_phase6_clean_checkout_status(repo_root=REPO_ROOT)

    assert payload["schema_version"] == "phase6-clean-checkout-status.v1"
    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is False
    assert payload["developer_preview_release_candidate_claim"] is False
    assert payload["local_clean_checkout_gate"]["status"] == "ready"
    assert payload["local_clean_checkout_gate"]["contract_pass"] is True
    assert payload["local_clean_checkout_gate"]["clean_checkout_executed"] is True
    assert payload["git_clean_clone_gate"]["status"] == "blocked"
    assert payload["git_clean_clone_gate"]["contract_pass"] is False
    assert payload["git_clean_clone_gate"]["git_clean_clone_executed"] is False
    assert payload["git_clean_clone_gate"]["blocker_count"] > 0
    assert payload["git_clean_clone_gate"]["blocker_counts"]["required_path_has_uncommitted_changes"] > 0
    assert payload["release_control_cleanup_gate"]["status"] == "blocked"
    assert payload["release_control_cleanup_gate"]["human_git_action_required"] is True
    assert payload["release_control_cleanup_gate"]["codex_commit_or_push_performed"] is False
    assert payload["release_control_cleanup_gate"]["candidate_release_control_commit_set_count"] > 0
    assert "git_clean_clone_reproduction_not_passed" in payload["blockers"]
    assert "human_git_action_required_for_release_control_inputs" in payload["blockers"]
    assert any(blocker.startswith("release_control_commit_set_pending:") for blocker in payload["blockers"])
    grouping = payload["blocker_grouping_metadata"]
    assert grouping["schema_version"] == "phase6-clean-checkout-blocker-groups.v1"
    assert grouping["blocker_count"] == len(payload["blockers"])
    assert grouping["unassigned_blockers"] == []
    assert "git_clean_clone_reproduction_not_passed" in grouping["groups"][
        "git_clean_clone_root"
    ]["blockers"]
    assert grouping["groups"]["dirty_tracked_required_inputs"]["blocker_count"] > 0
    assert grouping["groups"]["untracked_required_inputs"]["blocker_count"] > 0
    assert "human_git_action_required_for_release_control_inputs" in grouping["groups"][
        "release_control_human_handoff"
    ]["blockers"]
    assert any(
        blocker.startswith("release_control_commit_set_pending:")
        for blocker in grouping["groups"]["release_control_commit_set"]["blockers"]
    )
    assert "does not run git add, commit, push" in payload["claim_boundary"]
    assert "does not prove Linux/Windows parity" in payload["claim_boundary"]


def test_phase6_clean_checkout_status_check_detects_missing_output(tmp_path: Path) -> None:
    ok, message = module.check_phase6_clean_checkout_status(
        repo_root=REPO_ROOT,
        out_path=tmp_path / "missing.json",
    )

    assert ok is False
    assert message.startswith("phase6_clean_checkout_status_missing:")


def test_phase6_clean_checkout_status_check_detects_drift(tmp_path: Path) -> None:
    out = tmp_path / "clean.json"
    module.write_phase6_clean_checkout_status(repo_root=REPO_ROOT, out_path=out)
    payload = json.loads(out.read_text(encoding="utf-8"))
    payload["contract_pass"] = True
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    ok, message = module.check_phase6_clean_checkout_status(repo_root=REPO_ROOT, out_path=out)

    assert ok is False
    assert message == "phase6_clean_checkout_status_mismatch"
