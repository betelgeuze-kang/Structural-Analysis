from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

from scripts import build_bounded_planar_external_vv_matrix as matrix


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/product-state-current.yml"
SOURCE_SHA = "a" * 40
REPOSITORY = "example/structural-analysis"
RUN_ID = 123
RUN_ATTEMPT = 1


def _download_step() -> str:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["build-current-state"]["steps"]
    return next(
        step["run"]
        for step in steps
        if step.get("name")
        == "Download and verify successful exact-SHA clean-runner artifact"
    )


def _inventory_script() -> str:
    shell = _download_step()
    return shell.split("artifact_id=\"$(python - <<'PY'\n", 1)[1].split('\nPY\n)"', 1)[
        0
    ]


def _artifact(artifact_id: int, name: str) -> dict:
    return {
        "id": artifact_id,
        "name": name,
        "digest": "sha256:" + "0" * 64,
        "size_in_bytes": 100,
        "expired": False,
        "archive_download_url": (
            f"https://api.github.com/repos/{REPOSITORY}/actions/artifacts/{artifact_id}/zip"
        ),
        "workflow_run": {
            "id": RUN_ID,
            "head_sha": SOURCE_SHA,
            "head_branch": "main",
        },
    }


def _fixture(tmp_path: Path, artifacts: list[dict]) -> tuple[Path, dict[str, str]]:
    input_dir = tmp_path / "clean-runner-input"
    input_dir.mkdir()
    run = {
        "id": RUN_ID,
        "run_attempt": RUN_ATTEMPT,
        "event": "push",
        "head_sha": SOURCE_SHA,
        "head_branch": "main",
        "path": ".github/workflows/opensees-calculix-current-source.yml",
        "repository": {"full_name": REPOSITORY},
        "head_repository": {"full_name": REPOSITORY},
        "conclusion": "success",
    }
    jobs = [
        {"labels": ["ubuntu-24.04"], "run_attempt": RUN_ATTEMPT},
        {"labels": ["ubuntu-22.04"], "run_attempt": RUN_ATTEMPT},
    ]
    for name, payload in (
        ("run.json", run),
        ("jobs.json", {"jobs": jobs}),
        ("artifacts.json", {"artifacts": artifacts}),
        ("lookup.json", {"source_commit_sha": SOURCE_SHA}),
    ):
        (input_dir / name).write_text(json.dumps(payload) + "\n", encoding="utf-8")
    env = {
        **os.environ,
        "CLEAN_RUNNER_INPUT_DIR": str(input_dir),
        "CLEAN_RUNNER_RUN_ID": str(RUN_ID),
        "CLEAN_RUNNER_RUN_ATTEMPT": str(RUN_ATTEMPT),
        "PRODUCT_STATE_SHA": SOURCE_SHA,
        "GITHUB_REPOSITORY": REPOSITORY,
    }
    return input_dir, env


def _run_inventory(
    tmp_path: Path, artifacts: list[dict]
) -> tuple[subprocess.CompletedProcess[str], Path]:
    input_dir, env = _fixture(tmp_path, artifacts)
    result = subprocess.run(
        [sys.executable, "-c", _inventory_script()],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    return result, input_dir


def test_missing_producer_candidate_records_zero_credit_and_no_summary(
    tmp_path: Path,
) -> None:
    final_name = f"opensees-calculix-current-source-{RUN_ID}-{RUN_ATTEMPT}"
    result, input_dir = _run_inventory(tmp_path, [_artifact(201, final_name)])

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "unavailable"
    lookup = json.loads((input_dir / "lookup.json").read_text(encoding="utf-8"))
    assert lookup["artifact_status"] == "unavailable"
    assert lookup["artifact_unavailable_reason"] == (
        "exact_sha_producer_candidate_artifact_missing"
    )
    assert lookup["producer_candidate_match_count"] == 0
    assert lookup["same_operator_execution_credit"] == 0
    assert not (input_dir / "clean_runner_receipt.json").exists()
    assert not (input_dir / "artifact.json").exists()
    assert not (input_dir / "producer-artifact.json").exists()

    binding, code_receipts, modal_receipts = matrix._validated_same_operator_execution(
        repo_root=ROOT,
        summary_path=input_dir / "clean_runner_receipt.json",
        expected_source_commit=SOURCE_SHA,
    )
    assert binding["status"] == "unavailable"
    assert binding["technical_contract_pass"] is False
    assert binding["same_operator_container_isolated_reproduction"] is False
    assert code_receipts is None and modal_receipts is None


def test_missing_producer_candidate_exits_before_artifact_download() -> None:
    shell = _download_step()
    zero_credit = shell.index('if test "$artifact_id" = "unavailable"; then')
    download = shell.index("if ! gh api -H 'Accept: application/vnd.github+json'")
    attach = shell.index('cp "${summaries[0]}" "$CLEAN_RUNNER_SUMMARY_PATH"')
    assert zero_credit < download < attach
    assert "exit 0" in shell[zero_credit:download]


@pytest.mark.parametrize(
    "failure",
    ["missing_final", "duplicate_producer", "invalid_final", "expired_producer"],
)
def test_only_missing_producer_candidate_is_nonfatal(
    tmp_path: Path, failure: str
) -> None:
    final_name = f"opensees-calculix-current-source-{RUN_ID}-{RUN_ATTEMPT}"
    producer_name = f"opensees-calculix-current-source-candidate-{RUN_ID}-{RUN_ATTEMPT}"
    final = _artifact(201, final_name)
    producer = _artifact(202, producer_name)
    artifacts = [final, producer]
    if failure == "missing_final":
        artifacts = [producer]
    elif failure == "duplicate_producer":
        artifacts.append(_artifact(203, producer_name))
    elif failure == "invalid_final":
        final["digest"] = "invalid"
        artifacts = [final]
    else:
        producer["expired"] = True

    result, input_dir = _run_inventory(tmp_path, artifacts)
    assert result.returncode != 0
    expected = (
        "clean_runner_artifact_metadata_invalid"
        if failure in {"invalid_final", "expired_producer"}
        else "clean_runner_artifact_inventory_invalid"
    )
    assert expected in result.stderr
    lookup = json.loads((input_dir / "lookup.json").read_text(encoding="utf-8"))
    assert "artifact_status" not in lookup


def test_present_producer_still_uses_verified_artifact_path(tmp_path: Path) -> None:
    final_name = f"opensees-calculix-current-source-{RUN_ID}-{RUN_ATTEMPT}"
    producer_name = f"opensees-calculix-current-source-candidate-{RUN_ID}-{RUN_ATTEMPT}"
    result, input_dir = _run_inventory(
        tmp_path, [_artifact(201, final_name), _artifact(202, producer_name)]
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "201"
    assert json.loads((input_dir / "artifact.json").read_text())["id"] == 201
    assert json.loads((input_dir / "producer-artifact.json").read_text())["id"] == 202
    assert "artifact_status" not in json.loads((input_dir / "lookup.json").read_text())
