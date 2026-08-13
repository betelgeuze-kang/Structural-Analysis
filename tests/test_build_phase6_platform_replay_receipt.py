from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_phase6_platform_replay_receipt.py"
for candidate in (REPO_ROOT / "scripts", REPO_ROOT / "src"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

spec = importlib.util.spec_from_file_location("build_phase6_platform_replay_receipt", SCRIPT_PATH)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def _passing_commands() -> list[dict]:
    return [
        {
            "command": "python scripts/build_phase3_benchmark_factory_artifacts.py --check",
            "argv": ["python", "scripts/build_phase3_benchmark_factory_artifacts.py", "--check"],
            "return_code": 0,
        },
        {
            "command": "python -m structural_analysis.benchmark.cli --fail-blocked",
            "argv": ["python", "-m", "structural_analysis.benchmark.cli", "--fail-blocked"],
            "return_code": 0,
        },
    ]


@pytest.fixture(autouse=True)
def _phase3_repro_bundle(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "source_commit_sha": "a" * 40,
        "expected_scorecard": {"case_count": 30},
        "stable_artifact_checksums": {
            "manifest": "sha256:" + "1" * 64,
            "scorecard": "sha256:" + "2" * 64,
            "summary": "sha256:" + "3" * 64,
        },
    }
    monkeypatch.setattr(module, "_load_json", lambda *_args, **_kwargs: payload)


def test_windows_platform_replay_receipt_can_pass_with_matching_clean_platform() -> None:
    receipt = module.build_phase6_platform_replay_receipt(
        repo_root=REPO_ROOT,
        platform_name="windows",
        actual_platform="windows",
        dirty_paths=[],
        command_results=_passing_commands(),
        generated_output_checksums={
            "manifest": "sha256:generated-manifest",
            "scorecard": "sha256:generated-scorecard",
            "summary": "sha256:generated-summary",
        },
        replay_environment="unit_test_windows_replay",
    )

    assert receipt["schema_version"] == "phase6-linux-windows-platform-replay-receipt.v1"
    assert receipt["platform"] == "windows"
    assert receipt["actual_platform"] == "windows"
    assert receipt["contract_pass"] is True
    assert receipt["blockers"] == []
    assert receipt["working_tree_clean"] is True
    assert receipt["local_dirty_inputs"] == []
    assert receipt["platform_identity"]["platform"] == "windows"
    assert receipt["platform_identity"]["commands_return_code_zero"] is True
    assert receipt["platform_identity"]["replay_environment"] == "unit_test_windows_replay"
    assert receipt["node_version"] == module.NODE_RUNTIME_DISPOSITION
    assert receipt["source_commit_sha"]
    assert receipt["receipt_builder_source_commit_sha"]
    assert receipt["expected_scorecard"]["case_count"] == 30
    assert receipt["stable_artifact_checksums"]["manifest"].startswith("sha256:")
    assert receipt["generated_output_checksums"]["manifest"] == "sha256:generated-manifest"
    assert receipt["developer_preview_release_candidate_claim"] is False
    assert "cannot be copied across platforms" in receipt["claim_boundary"]
    assert "Node is neither invoked nor required" in receipt["claim_boundary"]


def test_platform_replay_source_has_no_node_process_probe() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")

    assert "def _node_version" not in source
    assert '["node", "--version"]' not in source
    assert "NODE_RUNTIME_DISPOSITION" in source


def test_platform_replay_receipt_blocks_on_platform_mismatch() -> None:
    receipt = module.build_phase6_platform_replay_receipt(
        repo_root=REPO_ROOT,
        platform_name="windows",
        actual_platform="linux",
        dirty_paths=[],
        command_results=_passing_commands(),
    )

    assert receipt["contract_pass"] is False
    assert receipt["blockers"] == ["actual_platform_mismatch:linux!=windows"]
    assert receipt["platform_identity"]["commands_return_code_zero"] is True


def test_platform_replay_receipt_blocks_on_dirty_worktree_or_failed_command() -> None:
    commands = _passing_commands()
    commands[1]["return_code"] = 1

    receipt = module.build_phase6_platform_replay_receipt(
        repo_root=REPO_ROOT,
        platform_name="linux",
        actual_platform="linux",
        dirty_paths=[" M scripts/build_phase6_platform_replay_receipt.py"],
        command_results=commands,
    )

    assert receipt["contract_pass"] is False
    assert "replay_command_return_code_nonzero" in receipt["blockers"]
    assert "replay_worktree_dirty_path_count=1" in receipt["blockers"]
    assert receipt["working_tree_clean"] is False
    assert receipt["platform_identity"]["commands_return_code_zero"] is False


def test_cli_refuses_to_write_windows_receipt_on_non_windows(tmp_path: Path) -> None:
    if module._actual_platform() == "windows":
        return
    out = tmp_path / "windows.json"

    exit_code = module.main(["--platform", "windows", "--out", str(out)])

    assert exit_code == 2
    assert not out.exists()
