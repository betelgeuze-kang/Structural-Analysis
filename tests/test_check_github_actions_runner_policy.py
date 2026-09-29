from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest


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


def test_pages_deploy_job_has_exact_fresh_hosted_runner_allowlist() -> None:
    assert check_github_actions_runner_policy.DEFAULT_GITHUB_HOSTED_JOB_ALLOWLIST[
        (".github/workflows/deploy-pages.yml", "deploy")
    ] == frozenset({"ubuntu-24.04"})


def test_sealed_attestor_has_exact_fresh_hosted_runner_allowlist() -> None:
    assert check_github_actions_runner_policy.DEFAULT_GITHUB_HOSTED_JOB_ALLOWLIST[
        (
            ".github/workflows/bounded-planar-sealed-technical-attestor.yml",
            "attest",
        )
    ] == frozenset({"ubuntu-24.04"})


@pytest.mark.parametrize(
    ("filename", "job"),
    [
        ("rc-pin-roller-budget-evidence.yml", "budget-packet"),
        ("rc-pin-roller-replication-evidence.yml", "replication-packet"),
    ],
)
def test_rc_synthetic_evidence_allows_only_declared_job_and_runner(
    tmp_path: Path, filename: str, job: str
) -> None:
    workflow_dir = _workflow_dir(tmp_path)
    path = workflow_dir / filename
    template = "name: RC synthetic evidence\njobs:\n  {job}:\n    runs-on: {runner}\n"

    def check(job_name: str, runner: str, extra_job: str = "") -> dict:
        path.write_text(
            template.format(job=job_name, runner=runner) + extra_job,
            encoding="utf-8",
        )
        return check_github_actions_runner_policy.check_runner_policy(
            workflow_dir=workflow_dir
        )

    assert check(job, "ubuntu-24.04")["contract_pass"] is True
    for runner in ("ubuntu-latest", "ubuntu-22.04", "[self-hosted, linux, x64]"):
        payload = check(job, runner)
        assert payload["contract_pass"] is False
        assert any("hosted_job_runner_not_exact" in b for b in payload["blockers"])

    for payload in (
        check("other-job", "ubuntu-24.04"),
        check(job, "ubuntu-24.04", "  other-job:\n    runs-on: ubuntu-24.04\n"),
    ):
        assert payload["contract_pass"] is False
        assert any("unapproved_github_hosted_runner" in b for b in payload["blockers"])

    payload = check(
        job, "ubuntu-24.04", "  hardware-job:\n    runs-on: [self-hosted, linux, x64]\n"
    )
    assert payload["contract_pass"] is True
    assert payload["rows"][-1]["execution_class"] == "hardware_or_private_self_hosted"


def test_pages_mixed_runner_policy_accepts_only_exact_deploy_runner(
    tmp_path: Path,
) -> None:
    workflow_dir = _workflow_dir(tmp_path)
    template = (
        "name: Pages\n"
        "jobs:\n"
        "  build:\n"
        "    runs-on: [self-hosted, linux, x64]\n"
        "  deploy:\n"
        "    runs-on: {runner}\n"
    )
    path = workflow_dir / "deploy-pages.yml"
    path.write_text(template.format(runner="ubuntu-24.04"), encoding="utf-8")
    assert (
        check_github_actions_runner_policy.check_runner_policy(
            workflow_dir=workflow_dir
        )["contract_pass"]
        is True
    )

    for runner in ("ubuntu-latest", "ubuntu-25.04"):
        path.write_text(template.format(runner=runner), encoding="utf-8")
        payload = check_github_actions_runner_policy.check_runner_policy(
            workflow_dir=workflow_dir
        )
        assert payload["contract_pass"] is False
        assert payload["blockers"] == [
            f".github/workflows/deploy-pages.yml:6:hosted_job_runner_not_exact:{runner}"
        ]


def test_product_truth_and_external_technical_workflows_are_approved_hosted_lanes() -> (
    None
):
    expected = {
        ".github/workflows/bounded-planar-negative-opensees-technical.yml",
        ".github/workflows/bounded-planar-modal-buckling-technical.yml",
        ".github/workflows/bounded-planar-nonlinear-material-recovery-technical.yml",
        ".github/workflows/bounded-planar-opensees-technical.yml",
        ".github/workflows/bounded-planar-scaling-opensees-technical.yml",
        ".github/workflows/bounded-planar-sealed-technical-attestor.yml",
        ".github/workflows/current-support-bundle.yml",
        ".github/workflows/git-lfs-integrity.yml",
        ".github/workflows/mgt-import-health-current-source.yml",
        ".github/workflows/mgt-import-health-tenth-source.yml",
        ".github/workflows/ifc-import-health-current-source.yml",
        ".github/workflows/issue-state-current.yml",
        ".github/workflows/medium-scale-current-source.yml",
        ".github/workflows/native-nightly-quality.yml",
        ".github/workflows/native-pr-fast.yml",
        ".github/workflows/opensees-calculix-clean-runner-attestor.yml",
        ".github/workflows/p0-canonical-contract.yml",
        ".github/workflows/product-state-current.yml",
        ".github/workflows/python-test-collection.yml",
        ".github/workflows/repository-hygiene-freshness.yml",
    }

    assert expected <= (
        check_github_actions_runner_policy.DEFAULT_GITHUB_HOSTED_WORKFLOWS
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


def test_runner_policy_resolves_allowlisted_hosted_matrix_include_axis(
    tmp_path: Path,
) -> None:
    workflow_dir = _workflow_dir(tmp_path)
    (workflow_dir / "matrix.yml").write_text(
        (
            "name: Matrix\n"
            "jobs:\n"
            "  verify:\n"
            "    runs-on: ${{ matrix.runner }}\n"
            "    strategy:\n"
            "      matrix:\n"
            "        include:\n"
            "          - runner: ubuntu-24.04\n"
            "            platform: linux-x86_64-gnu\n"
            "          - runner: windows-2025\n"
            "            platform: windows-x86_64-msvc\n"
        ),
        encoding="utf-8",
    )

    payload = check_github_actions_runner_policy.check_runner_policy(
        workflow_dir=workflow_dir,
        github_hosted_allowlist={".github/workflows/matrix.yml"},
    )

    assert payload["contract_pass"] is True
    assert payload["blockers"] == []
    assert payload["rows"][0]["resolved_runs_on"] == ("ubuntu-24.04, windows-2025")


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
