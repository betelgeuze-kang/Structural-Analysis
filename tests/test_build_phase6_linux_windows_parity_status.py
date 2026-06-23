from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts/build_phase6_linux_windows_parity_status.py"
for candidate in (REPO_ROOT / "scripts", REPO_ROOT / "src"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

spec = importlib.util.spec_from_file_location("build_phase6_linux_windows_parity_status", SCRIPT_PATH)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def test_phase6_linux_platform_replay_receipt_uses_local_clean_checkout_only() -> None:
    receipt = module.build_phase6_linux_platform_replay_receipt(repo_root=REPO_ROOT)

    assert receipt["schema_version"] == "phase6-linux-windows-platform-replay-receipt.v1"
    assert receipt["platform"] == "linux"
    assert receipt["contract_pass"] is True
    assert receipt["developer_preview_release_candidate_claim"] is False
    assert receipt["working_tree_clean"] is True
    assert receipt["working_tree_clean_scope"] == "isolated_minimal_worktree_copy"
    assert receipt["local_dirty_inputs"] == []
    assert receipt["source_clean_checkout_status"] == "pass"
    assert receipt["source_clean_checkout_contract_pass"] is True
    assert receipt["source_clean_checkout_execution_mode"] == "isolated_minimal_worktree_copy"
    assert receipt["source_git_clean_clone_receipt"].endswith(
        "phase3_benchmark_factory_seed_git_clean_clone_reproduction.json"
    )
    assert receipt["stable_artifact_checksums"]
    assert receipt["expected_scorecard"]["case_count"] == 30
    assert receipt["blockers"] == []
    assert "not a Windows receipt" in receipt["claim_boundary"]
    assert "not a git-clean-clone pass" in receipt["claim_boundary"]


def test_phase6_linux_windows_parity_status_blocks_with_linux_only_receipt() -> None:
    payload = module.build_phase6_linux_windows_parity_status(repo_root=REPO_ROOT)

    assert payload["schema_version"] == "phase6-linux-windows-parity-status.v1"
    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is False
    assert payload["developer_preview_release_candidate_claim"] is False
    assert payload["required_platforms"] == ["linux", "windows"]
    assert payload["platform_receipt_schema"] == "phase6-linux-windows-platform-replay-receipt.v1"
    assert payload["current_platform_receipts"] == ["linux"]
    assert payload["missing_platform_receipts"] == ["windows"]
    assert payload["platform_receipt_paths"] == {
        "linux": (
            "implementation/phase1/release_evidence/productization/"
            "phase6_linux_platform_replay_receipt.json"
        ),
        "windows": (
            "implementation/phase1/release_evidence/productization/"
            "phase6_windows_platform_replay_receipt.json"
        ),
    }
    rows = {row["platform"]: row for row in payload["platform_rows"]}
    assert rows["linux"]["status"] == "ready"
    assert rows["windows"]["status"] == "missing"
    assert rows["linux"]["contract_pass"] is True
    assert rows["windows"]["contract_pass"] is False
    assert rows["linux"]["blockers"] == []
    assert "platform_replay_receipt_missing:windows" in rows["windows"]["blockers"]
    assert "linux_windows_parity_receipts_missing" in payload["blocked_by"]
    assert "git_clean_clone_reproduction_not_passed" in payload["blocked_by"]
    assert "platform_replay_receipt_missing:linux" not in payload["blocked_by"]
    grouping = payload["blocker_grouping_metadata"]
    assert grouping["schema_version"] == "phase6-linux-windows-parity-blocker-groups.v1"
    assert grouping["blocker_count"] == len(payload["blocked_by"])
    assert grouping["unassigned_blockers"] == []
    assert "linux_windows_parity_receipts_missing" in grouping["groups"][
        "platform_receipt_presence"
    ]["blockers"]
    assert "platform_replay_receipt_missing:windows" in grouping["groups"][
        "platform_receipt_presence"
    ]["blockers"]
    assert "git_clean_clone_reproduction_not_passed" in grouping["groups"][
        "git_clean_clone_spillover"
    ]["blockers"]
    template = payload["platform_receipt_template"]
    assert template["schema_version"] == "phase6-linux-windows-platform-replay-receipt.v1"
    assert template["platform"] == "linux|windows"
    assert template["working_tree_clean"] is True
    assert template["local_dirty_inputs"] == []
    assert template["contract_pass"] is False
    assert template["stable_artifact_checksums"] == payload["expected_stable_artifact_checksums"]
    assert template["expected_scorecard"] == payload["expected_scorecard"]
    comparison = payload["parity_comparison_contract"]
    assert comparison["required_platform_receipt_count"] == 2
    assert comparison["current_platform_receipt_count"] == 1
    assert comparison["missing_platforms"] == ["windows"]
    assert comparison["local_dirty_inputs_allowed"] is False
    assert comparison["contract_pass"] is False
    assert "manifest" in comparison["checksum_keys"]
    assert "scorecard" in comparison["checksum_keys"]
    assert "case_count" in comparison["scorecard_identity_fields"]
    linux_source = payload["linux_local_replay_receipt_source"]
    assert linux_source["status"] == "pass"
    assert linux_source["contract_pass"] is True
    assert linux_source["execution_mode"] == "isolated_minimal_worktree_copy"
    assert "does not satisfy Windows parity" in linux_source["claim_boundary"]
    assert any(
        "build_phase6_linux_windows_parity_status.py --check" in command
        for command in payload["required_commands"]
    )
    assert "does not prove parity" in payload["claim_boundary"]


def test_phase6_linux_windows_parity_status_check_detects_missing_output(tmp_path: Path) -> None:
    ok, message = module.check_phase6_linux_windows_parity_status(
        repo_root=REPO_ROOT,
        out_path=tmp_path / "missing.json",
    )

    assert ok is False
    assert message.startswith("phase6_linux_windows_parity_status_missing:")


def test_phase6_linux_windows_parity_status_check_detects_drift(tmp_path: Path) -> None:
    out = tmp_path / "parity.json"
    module.write_phase6_linux_windows_parity_status(repo_root=REPO_ROOT, out_path=out)
    payload = json.loads(out.read_text(encoding="utf-8"))
    payload["contract_pass"] = True
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    ok, message = module.check_phase6_linux_windows_parity_status(
        repo_root=REPO_ROOT,
        out_path=out,
    )

    assert ok is False
    assert message == "phase6_linux_windows_parity_status_mismatch"
