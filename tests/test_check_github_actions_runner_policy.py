from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


SCRIPT_PATH = (
    Path(__file__).resolve().parent.parent
    / "scripts"
    / "check_github_actions_runner_policy.py"
)
SPEC = importlib.util.spec_from_file_location(
    "check_github_actions_runner_policy", SCRIPT_PATH
)
assert SPEC is not None
check_github_actions_runner_policy = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = check_github_actions_runner_policy
SPEC.loader.exec_module(check_github_actions_runner_policy)


def _workflow_dir(tmp_path: Path) -> Path:
    workflow_dir = tmp_path / ".github" / "workflows"
    workflow_dir.mkdir(parents=True)
    return workflow_dir


def test_pr_metadata_workflow_is_an_approved_deterministic_hosted_lane() -> None:
    assert (
        ".github/workflows/pr-metadata-ci.yml"
        in check_github_actions_runner_policy.DEFAULT_GITHUB_HOSTED_WORKFLOWS
    )


def test_core_quality_workflow_is_an_approved_deterministic_hosted_lane() -> None:
    assert (
        ".github/workflows/core-quality-ci.yml"
        in check_github_actions_runner_policy.DEFAULT_GITHUB_HOSTED_WORKFLOWS
    )


def test_runner_policy_blocks_unapproved_github_hosted_runner(tmp_path: Path) -> None:
    workflow_dir = _workflow_dir(tmp_path)
    (workflow_dir / "custom.yml").write_text(
        "name: Custom\njobs:\n  verify:\n    runs-on: ubuntu-latest\n",
        encoding="utf-8",
    )

    payload = check_github_actions_runner_policy.check_runner_policy(
        workflow_dir=workflow_dir,
        github_hosted_allowlist=set(),
    )

    assert payload["schema_version"] == "github-actions-runner-policy.v2"
    assert payload["contract_pass"] is False
    assert payload["status"] == "blocked"
    assert payload["blockers"] == [
        ".github/workflows/custom.yml:4:self_hosted_default_missing:ubuntu-latest",
        ".github/workflows/custom.yml:4:unapproved_github_hosted_runner:ubuntu-latest",
    ]


def test_runner_policy_accepts_allowlisted_deterministic_hosted_lane(
    tmp_path: Path,
) -> None:
    workflow_dir = _workflow_dir(tmp_path)
    (workflow_dir / "ci.yml").write_text(
        "name: CI\njobs:\n  verify:\n    runs-on: ubuntu-latest\n",
        encoding="utf-8",
    )

    payload = check_github_actions_runner_policy.check_runner_policy(
        workflow_dir=workflow_dir
    )

    assert payload["contract_pass"] is True
    assert payload["status"] == "pass"
    assert payload["deterministic_github_hosted_count"] == 1
    assert payload["hardware_or_private_self_hosted_count"] == 0
    assert payload["rows"][0]["execution_class"] == "deterministic_github_hosted"
    assert payload["blockers"] == []


def test_runner_policy_resolves_allowlisted_hosted_matrix_axis(
    tmp_path: Path,
) -> None:
    workflow_dir = _workflow_dir(tmp_path)
    (workflow_dir / "matrix.yml").write_text(
        (
            "name: Matrix\n"
            "jobs:\n"
            "  verify:\n"
            "    runs-on: ${{ matrix.os }}\n"
            "    strategy:\n"
            "      matrix:\n"
            "        os: [ubuntu-latest, windows-latest]\n"
        ),
        encoding="utf-8",
    )

    payload = check_github_actions_runner_policy.check_runner_policy(
        workflow_dir=workflow_dir,
        github_hosted_allowlist={".github/workflows/matrix.yml"},
    )

    assert payload["contract_pass"] is True
    assert payload["blockers"] == []
    assert payload["rows"][0]["runs_on"] == "${{ matrix.os }}"
    assert payload["rows"][0]["resolved_runs_on"] == ("ubuntu-latest, windows-latest")


def test_runner_policy_blocks_self_hosted_runner_in_allowlisted_deterministic_lane(
    tmp_path: Path,
) -> None:
    workflow_dir = _workflow_dir(tmp_path)
    value = '${{ fromJSON(vars.STRUCTURAL_ACTIONS_RUNNER_LABELS || \'["self-hosted","linux","x64"]\') }}'
    (workflow_dir / "ci.yml").write_text(
        f"name: CI\njobs:\n  verify:\n    runs-on: {value}\n",
        encoding="utf-8",
    )

    payload = check_github_actions_runner_policy.check_runner_policy(
        workflow_dir=workflow_dir
    )

    assert payload["contract_pass"] is False
    assert payload["status"] == "blocked"
    assert len(payload["blockers"]) == 2
    assert any("github_hosted_runner_required" in item for item in payload["blockers"])
    assert any(
        "deterministic_lane_uses_self_hosted" in item for item in payload["blockers"]
    )


def test_runner_policy_accepts_self_hosted_expression_for_hardware_lane(
    tmp_path: Path,
) -> None:
    workflow_dir = _workflow_dir(tmp_path)
    (workflow_dir / "heavy.yml").write_text(
        (
            "name: Heavy\n"
            "jobs:\n"
            "  verify:\n"
            "    runs-on: ${{ fromJSON(vars.STRUCTURAL_ACTIONS_RUNNER_LABELS || "
            '\'["self-hosted","linux","x64"]\') }}\n'
        ),
        encoding="utf-8",
    )

    payload = check_github_actions_runner_policy.check_runner_policy(
        workflow_dir=workflow_dir,
        github_hosted_allowlist=set(),
    )

    assert payload["contract_pass"] is True
    assert payload["status"] == "pass"
    assert payload["hardware_or_private_self_hosted_count"] == 1
    assert payload["blockers"] == []


def test_runner_policy_accepts_multiline_self_hosted_labels(tmp_path: Path) -> None:
    workflow_dir = _workflow_dir(tmp_path)
    (workflow_dir / "heavy.yml").write_text(
        (
            "name: Heavy\n"
            "jobs:\n"
            "  verify:\n"
            "    runs-on:\n"
            "      - self-hosted\n"
            "      - linux\n"
            "      - x64\n"
        ),
        encoding="utf-8",
    )

    payload = check_github_actions_runner_policy.check_runner_policy(
        workflow_dir=workflow_dir,
        github_hosted_allowlist=set(),
    )

    assert payload["contract_pass"] is True
    assert payload["rows"][0]["runs_on"] == "self-hosted, linux, x64"
    assert payload["blockers"] == []


def test_runner_policy_blocks_multiline_unapproved_github_hosted_labels(
    tmp_path: Path,
) -> None:
    workflow_dir = _workflow_dir(tmp_path)
    (workflow_dir / "custom.yml").write_text(
        ("name: Custom\njobs:\n  verify:\n    runs-on:\n      - ubuntu-latest\n"),
        encoding="utf-8",
    )

    payload = check_github_actions_runner_policy.check_runner_policy(
        workflow_dir=workflow_dir,
        github_hosted_allowlist=set(),
    )

    assert payload["contract_pass"] is False
    assert payload["blockers"] == [
        ".github/workflows/custom.yml:4:self_hosted_default_missing:ubuntu-latest",
        ".github/workflows/custom.yml:4:unapproved_github_hosted_runner:ubuntu-latest",
    ]


def test_runner_policy_accepts_runner_group_label_object(tmp_path: Path) -> None:
    workflow_dir = _workflow_dir(tmp_path)
    (workflow_dir / "heavy.yml").write_text(
        (
            "name: Heavy\n"
            "jobs:\n"
            "  verify:\n"
            "    runs-on:\n"
            "      group: structural-self-hosted\n"
            "      labels:\n"
            "        - self-hosted\n"
            "        - linux\n"
            "        - x64\n"
        ),
        encoding="utf-8",
    )

    payload = check_github_actions_runner_policy.check_runner_policy(
        workflow_dir=workflow_dir,
        github_hosted_allowlist=set(),
    )

    assert payload["contract_pass"] is True
    assert payload["rows"][0]["runs_on"] == "self-hosted, linux, x64"
    assert payload["blockers"] == []
