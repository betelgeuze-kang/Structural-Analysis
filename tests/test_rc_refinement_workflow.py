"""Keep RC integration in a reviewed read-only CPU lane without weakening gates."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import re
import shlex

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/python-test-collection.yml"
TESTS = {
    "tests/test_neutral_strict_input.py",
    "tests/test_rc_control_refinement.py",
    "tests/test_rc_control_local_research.py",
    "tests/test_rc_control_persistence.py",
    "tests/test_rc_local_resources.py",
    "tests/test_rc_refinement_workflow.py",
}


def workflow():
    return yaml.load(WORKFLOW.read_text(), Loader=yaml.BaseLoader)


def test_refinement_uses_existing_read_only_cpu_lane():
    data = workflow()
    job = data["jobs"]["refinement_contracts"]
    assert data["permissions"] == {"contents": "read"}
    assert job["name"] == "rc-refinement-integration"
    assert job["runs-on"] == "ubuntu-latest"
    assert "needs" not in job and "if" not in job
    assert "permissions" not in job and "continue-on-error" not in job
    assert all("continue-on-error" not in step for step in job["steps"])
    assert not (ROOT / ".github/workflows/rc-refinement-integration.yml").exists()


def test_refinement_is_collected_without_filtering_or_hiding_failures():
    job = workflow()["jobs"]["refinement_contracts"]
    runs = [step for step in job["steps"] if "run" in step]
    assert len(runs) == 4
    args = shlex.split(runs[1]["run"])
    assert args[:4] == ["python", "-m", "pytest", "-q"]
    assert {arg for arg in args if arg.startswith("tests/")} == TESTS
    assert all((ROOT / path).is_file() for path in TESTS)
    assert "--junitxml=rc-refinement-tests.xml" in args
    assert not {"--deselect", "--ignore", "-k"}.intersection(args)
    assert "if" not in runs[1]
    assert runs[2]["if"] == runs[3]["if"] == "${{ !cancelled() }}"
    assert "ruff format --check --diff" in runs[2]["run"]
    assert "ruff check --output-format=json" in runs[3]["run"]


def test_refinement_sources_trigger_pr_push_and_merge_group():
    events = workflow()["on"]
    assert "merge_group" in events and "workflow_dispatch" in events
    for event in ("pull_request", "push"):
        trigger = events[event]
        if trigger is not None and isinstance(trigger, dict):
            assert "paths" not in trigger and "paths-ignore" not in trigger
    assert "main" in events["push"]["branches"]


def test_original_diagnostics_are_retained_with_immutable_actions():
    steps = workflow()["jobs"]["refinement_contracts"]["steps"]
    assert steps[0]["with"] == {
        "fetch-depth": "0",
        "persist-credentials": "false",
    }
    for step in steps:
        if "uses" in step:
            assert re.fullmatch(r"actions/[a-z-]+@[0-9a-f]{40}", step["uses"])
    upload = steps[-1]
    assert upload["if"] == "${{ always() }}"
    assert set(upload["with"]["path"].splitlines()) == {
        "rc-refinement-tests.xml",
        "rc-refinement-format.diff",
        "rc-refinement-lint.json",
    }
    assert "rc-integration-source" not in WORKFLOW.read_text()


def test_integration_does_not_replace_required_full_shards():
    data = yaml.load(
        (ROOT / ".github/workflows/python-test-collection.yml").read_text(),
        Loader=yaml.BaseLoader,
    )
    full = data["jobs"]["full"]
    assert full["needs"] == "full_shards"
    assert full["if"] == "${{ always() }}"
    assert full["steps"][0]["run"] == 'test "$FULL_SHARDS_RESULT" = "success"'
    assert data["jobs"]["full_shards"]["strategy"]["matrix"]["shard"] == [
        "0",
        "1",
        "2",
        "3",
    ]
    assert "continue-on-error" not in data["jobs"]["full_shards"]


def test_runner_policy_still_accepts_existing_lane_and_rejects_unknown(tmp_path):
    path = ROOT / "scripts/check_github_actions_runner_policy.py"
    spec = importlib.util.spec_from_file_location("rc_runner_policy", path)
    assert spec is not None and spec.loader is not None
    policy = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(policy)
    assert ".github/workflows/python-test-collection.yml" in (
        policy.DEFAULT_GITHUB_HOSTED_WORKFLOWS
    )
    assert ".github/workflows/unknown-hardware.yml" not in (
        policy.DEFAULT_GITHUB_HOSTED_WORKFLOWS
    )
    # The integration must not introduce a wildcard approval for hosted hardware.
    assert all("*" not in name for name in policy.DEFAULT_GITHUB_HOSTED_WORKFLOWS)
