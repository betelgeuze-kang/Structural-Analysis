from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "check_github_actions_runner_policy.py"
SPEC = importlib.util.spec_from_file_location("check_github_actions_runner_policy", SCRIPT_PATH)
assert SPEC is not None
check_github_actions_runner_policy = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = check_github_actions_runner_policy
SPEC.loader.exec_module(check_github_actions_runner_policy)


def test_runner_policy_blocks_github_hosted_runner(tmp_path: Path) -> None:
    workflow_dir = tmp_path / ".github" / "workflows"
    workflow_dir.mkdir(parents=True)
    (workflow_dir / "ci.yml").write_text(
        "name: CI\njobs:\n  verify:\n    runs-on: ubuntu-latest\n",
        encoding="utf-8",
    )

    payload = check_github_actions_runner_policy.check_runner_policy(
        workflow_dir=workflow_dir
    )

    assert payload["contract_pass"] is False
    assert payload["status"] == "blocked"
    assert payload["blockers"] == [
        ".github/workflows/ci.yml:4:github_hosted_runner_label:ubuntu-latest"
    ]


def test_runner_policy_accepts_self_hosted_expression(tmp_path: Path) -> None:
    workflow_dir = tmp_path / ".github" / "workflows"
    workflow_dir.mkdir(parents=True)
    (workflow_dir / "ci.yml").write_text(
        (
            "name: CI\n"
            "jobs:\n"
            "  verify:\n"
            "    runs-on: ${{ fromJSON(vars.STRUCTURAL_ACTIONS_RUNNER_LABELS || "
            "'[\"self-hosted\",\"linux\",\"x64\"]') }}\n"
        ),
        encoding="utf-8",
    )

    payload = check_github_actions_runner_policy.check_runner_policy(
        workflow_dir=workflow_dir
    )

    assert payload["contract_pass"] is True
    assert payload["status"] == "pass"
    assert payload["blockers"] == []
