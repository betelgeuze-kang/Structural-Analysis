from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/native-frame-alpha-clean-install.yml"
RUNNER_POLICY = ROOT / "scripts/check_github_actions_runner_policy.py"
SPEC = importlib.util.spec_from_file_location(
    "check_github_actions_runner_policy_clean_install_test", RUNNER_POLICY
)
assert SPEC is not None and SPEC.loader is not None
runner_policy = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = runner_policy
SPEC.loader.exec_module(runner_policy)


def _job(source: str, name: str, next_name: str | None) -> str:
    block = source.split(f"  {name}:\n", 1)[1]
    if next_name is not None:
        block = block.split(f"\n  {next_name}:\n", 1)[0]
    return block


def test_clean_install_workflow_separates_build_from_ephemeral_replay() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    build = _job(source, "build-packages", "clean-install-replay")
    replay = _job(source, "clean-install-replay", "compare-platforms")
    comparison = _job(source, "compare-platforms", "attest-current-main")

    for runner, platform in (
        ("ubuntu-24.04", "linux-x86_64-gnu"),
        ("windows-2025", "windows-x86_64-msvc"),
    ):
        assert f"runner: {runner}" in build
        assert f"platform_tag: {platform}" in build
        assert f"runner: {runner}" in replay
        assert f"platform_tag: {platform}" in replay
    assert "cargo build" in build
    assert "npm ci" in build
    assert "build-workstation" in build
    assert "needs: build-packages" in replay
    assert "cargo build" not in replay
    assert "npm ci" not in replay
    assert "test ! -e native/target" in replay
    assert "test ! -e dist" in replay
    assert "--runner-profile github_hosted_ephemeral" in replay
    assert "needs: clean-install-replay" in comparison
    assert "compare_native_frame_alpha_clean_install_replays.py" in comparison


def test_clean_install_workflow_attests_only_exact_current_main() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    attest = _job(source, "attest-current-main", None)

    assert "github.event_name != 'pull_request'" in attest
    assert "github.ref == 'refs/heads/main'" in attest
    assert 'test "$WORKFLOW_SHA" = "$GITHUB_SHA"' in attest
    assert "git/ref/heads/main" in attest
    assert "actions/attest@508db95dd578ae2727ebd6217d5ba78e4fbda05d" in attest
    assert "gh attestation verify" in attest
    assert '--signer-digest "$WORKFLOW_SHA"' in attest
    assert '--source-digest "$GITHUB_SHA"' in attest
    assert ".ci/frame-alpha-clean-install/packages/*.zip" in attest
    assert ".ci/frame-alpha-clean-install/receipts/*.json" in attest


def test_clean_install_workflow_uses_immutable_artifact_actions() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    assert source.count('python-version: "3.12.10"') == 3
    assert 'python-version: "3.12.11"' not in source
    assert "actions/upload-artifact@v" not in source
    assert "actions/download-artifact@v" not in source
    assert (
        source.count("actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a")
        == 4
    )
    assert (
        source.count(
            "actions/download-artifact@37930b1c2abaa49bbe596cd826c3c89aef350131"
        )
        == 5
    )


def test_clean_install_workflow_is_an_approved_hosted_lane() -> None:
    payload = runner_policy.check_runner_policy()
    assert payload["contract_pass"] is True, payload["blockers"]
