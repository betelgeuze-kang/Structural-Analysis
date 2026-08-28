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
    comparison = _job(source, "compare-platforms", "packaged-browser-replay")

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
    assert "manage_native_frame_alpha_portable_install.py install" in replay
    assert "manage_native_frame_alpha_portable_install.py update" in replay
    assert "manage_native_frame_alpha_portable_install.py rollback" in replay
    assert "manage_native_frame_alpha_portable_install.py verify" in replay
    assert "--expected-source-tree" in replay
    assert "--expected-archive-sha256" in replay
    assert "portable-install-${PLATFORM_TAG}.json" in replay
    assert "portable-update-${PLATFORM_TAG}.json" in replay
    assert "portable-rollback-${PLATFORM_TAG}.json" in replay
    assert "portable-transition-${PLATFORM_TAG}.json" in replay
    assert "build_native_frame_alpha_portable_transition_evidence.py" in replay
    assert "verify-receipt" in replay
    assert 'cp "$install_root/current.json"' in replay
    assert "--package-version 0.1.0" in build
    assert "--package-version 0.1.1" in build
    assert "ephemeral update generation" in build
    assert "transition-trust-${PLATFORM_TAG}.json" in build
    assert "needs: clean-install-replay" in comparison
    assert "compare_native_frame_alpha_clean_install_replays.py" in comparison


def test_clean_install_workflow_watches_complete_frontend_build_inputs() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    for path in (
        '"src/**"',
        '"public/**"',
        '"index.html"',
        '"vite.config.ts"',
        '"tsconfig*.json"',
        '"package.json"',
        '"package-lock.json"',
        '"scripts/verify-workbench-viewer-delivery.mjs"',
        '"scripts/native_frame_alpha_clean_install_contract.py"',
    ):
        assert source.count(path) == 2, path
    assert '"src/workbench-v2/**"' not in source


def test_clean_install_workflow_attests_only_exact_current_main() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    handoff = _job(source, "build-sealed-handoff", "attest-current-main")
    attest = _job(source, "attest-current-main", None)

    assert "github.event_name != 'pull_request'" in attest
    assert "github.ref == 'refs/heads/main'" in attest
    assert 'test "$WORKFLOW_SHA" = "$GITHUB_SHA"' in handoff
    assert "name: produce-unprivileged" in handoff
    assert 'GH_TOKEN: ""' in handoff
    assert "id-token: write" not in handoff
    assert "attestations: write" not in handoff
    assert "artifact-id: ${{ steps.handoff.outputs.artifact-id }}" in handoff
    assert "artifact-digest: ${{ steps.handoff.outputs.artifact-digest }}" in handoff
    assert "pattern:" not in handoff
    assert "uses: ./.github/workflows/_technical-evidence-attest.yml" in attest
    assert "receipt-path: native-clean-install-summary.json" in attest


def test_packaged_browser_job_reverifies_downloaded_archive_before_chromium() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    browser = _job(source, "packaged-browser-replay", "build-sealed-handoff")

    assert "needs: [build-packages, clean-install-replay]" in browser
    assert "runs-on: ubuntu-24.04" in browser
    assert "run_native_frame_alpha_clean_install_replay.py" in browser
    assert "frame-alpha-workstation-linux-x86_64-gnu-baseline.zip" in browser
    assert "frame-alpha-workstation-linux-x86_64-gnu.zip" not in browser
    assert 'expected["archive"] == actual["archive"]' in browser
    assert "_extract_verified_archive" in browser
    assert "npx playwright install --with-deps chromium" in browser
    assert "verify-native-frame-packaged-browser.mjs" in browser


def test_clean_install_workflow_triggers_for_every_packaged_browser_input() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    for path in (
        "scripts/verify-native-frame-packaged-browser.mjs",
        "scripts/verify-workbench-viewer-delivery.mjs",
        "src/**",
        "index.html",
        "package.json",
        "package-lock.json",
        "tsconfig.json",
        "vite.config.ts",
    ):
        assert source.count(f'- "{path}"') == 2, path


def test_clean_install_workflow_uses_immutable_artifact_actions() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    assert source.count('python-version: "3.12.10"') == 4
    assert 'python-version: "3.12.11"' not in source
    assert "actions/upload-artifact@v" not in source
    assert "actions/download-artifact@v" not in source
    assert (
        source.count("actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a")
        == 5
    )
    assert source.count("include-hidden-files: true") == 3
    assert (
        source.count(
            "actions/download-artifact@37930b1c2abaa49bbe596cd826c3c89aef350131"
        )
        == 10
    )


def test_clean_install_privileged_verifier_is_fresh_and_exact() -> None:
    verifier = (ROOT / ".github/workflows/_technical-evidence-attest.yml").read_text(
        encoding="utf-8"
    )
    job = verifier.split("jobs:", 1)[1]

    assert "runs-on: ubuntu-24.04" in job
    assert "class NoRedirect(HTTPRedirectHandler)" in job
    assert 'producer_job_identity_invalid' in job
    assert 'artifact_archive_digest_mismatch' in job
    assert 'native_handoff_file_set_invalid' in job
    assert 'native_package_duplicate_path' in job
    assert 'native_package_nonregular_entry' in job
    assert 'native_package_file_hash_invalid' in job
    assert 'native_schema_identity_invalid' in job
    assert "subject-path: ${{ runner.temp }}/verified-technical-handoff/${{ inputs.receipt-path }}" in job
    assert "subject-path: |" not in job
    assert "actions/checkout" not in job
    assert "actions/setup-python" not in job
    assert "actions/setup-node" not in job
    assert "pip install" not in job
    assert "npm " not in job


def test_clean_install_workflow_is_an_approved_hosted_lane() -> None:
    payload = runner_policy.check_runner_policy()
    assert payload["contract_pass"] is True, payload["blockers"]
