from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "dp-windows-parity.yml"


def test_dp_windows_parity_workflow_uses_self_hosted_windows_runner() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "name: DP Windows Parity Receipt" in text
    assert "workflow_dispatch:" in text
    assert "STRUCTURAL_WINDOWS_RUNNER_LABELS" in text
    assert '["self-hosted","windows","x64"]' in text
    assert "windows-latest" not in text
    assert "ubuntu-latest" not in text
    assert "fetch-depth: 0" in text
    assert "actions/setup-python@v6" in text
    assert "python -m pip install -e .[dev]" in text
    assert "scripts/build_phase6_platform_replay_receipt.py" in text
    assert "--platform windows" in text
    assert "phase6_windows_platform_replay_receipt.json" in text
    assert "scripts/build_phase6_linux_windows_parity_status.py --check" in text
    assert "actions/upload-artifact@v7" in text
