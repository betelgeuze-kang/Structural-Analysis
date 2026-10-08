from __future__ import annotations

import base64
import copy
import hashlib
import json
import math
from pathlib import Path
import shlex
import subprocess
import sys
import textwrap

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("native_code", [0, 7])
def test_runtime_browser_retains_native_report_before_http_overwrites_results(
    tmp_path: Path, native_code: int
) -> None:
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/runtime-input-viewer-ci.yml").read_text()
    )
    steps = workflow["jobs"]["frontend-contracts"]["steps"]
    names = [step["name"] for step in steps]
    runner = steps[names.index("Workbench v2 guarded E2E")]
    retention = steps[names.index("Preserve native Workbench diagnostic retention")]
    assert names.index(retention["name"]) < names.index(
        "Workbench actual HTTP integration"
    )
    assert retention["if"] == (
        "always() && (steps.workbench_e2e.outcome == 'success' || "
        "steps.workbench_e2e.outcome == 'failure')"
    )
    assert retention["with"]["if-no-files-found"] == "error"
    assert "${{ github.run_attempt }}" in retention["with"]["name"]
    assert {Path(line).name for line in retention["with"]["path"].splitlines()} == {
        "run-linkage.json",
        "retention.json",
        "native-playwright.json",
    }
    command = runner["run"]
    for key, value in {"sha": "a" * 40, "run_id": "123", "run_attempt": "2"}.items():
        command = command.replace("${{ github." + key + " }}", value)
    result = subprocess.run(
        [
            "bash",
            "-c",
            'npm() { [ "$TMPDIR" = "$RUNNER_TEMP" ] || return 97; '
            'printf "%s\\n" "$@" > arguments.txt; return '
            + str(native_code)
            + "; };\n"
            + command,
        ],
        cwd=tmp_path,
        env={
            "PATH": "/usr/bin:/bin",
            "RUNNER_TEMP": str(tmp_path),
            "TMPDIR": str(tmp_path / "inherited-other-temp"),
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == native_code
    arguments = (tmp_path / "arguments.txt").read_text().splitlines()
    assert "--trace=retain-on-failure" in arguments
    assert (
        f"--diagnostics-dir={tmp_path}/workbench-browser-diagnostics-123-2" in arguments
    )
    assert "--diagnostics-sha=" + "a" * 40 in arguments
    assert "--diagnostics-run-id=123" in arguments
    assert "--diagnostics-run-attempt=2" in arguments


PHASE2_REFRESH_COMMANDS = (
    "python scripts/build_phase2_state_updated_steel_material_artifacts.py",
    "python scripts/build_phase2_state_updated_bilinear_link_artifacts.py",
    "python scripts/build_phase2_state_updated_composite_section_artifacts.py",
    "python scripts/build_phase2_state_updated_concrete_damage_artifacts.py",
    "python scripts/build_phase2_adaptive_newton_continuation_artifacts.py",
)
ANALYTIC_FRAME_REFRESH_COMMANDS = (
    "python scripts/build_analytic_frame_verification_artifact.py",
    "python scripts/build_analytic_frame_verification_artifact.py --check",
    "python scripts/build_verification_hierarchy_status.py",
    "python scripts/build_verification_hierarchy_status.py --check",
)


def _canonical_artifact_cli_bindings(run: str, mode: str) -> dict[str, str]:
    expanded = run.replace("\\\n", " ")
    marker = f"python scripts/verify_canonical_actions_artifact.py {mode} "
    assert expanded.count(marker) == 1
    line = next(line.lstrip() for line in expanded.splitlines() if marker in line)
    prefix = 'if canonical_artifact_id="$(' if mode == "select" else ""
    assert line.startswith(prefix + marker)
    command = line.removeprefix(prefix + marker)
    if mode == "select":
        assert command.endswith(')"; then')
        command = command.removesuffix(')"; then')
    arguments = shlex.split(command)
    assert len(arguments) % 2 == 0
    assert all(flag.startswith("--") for flag in arguments[::2])
    bindings = dict(zip(arguments[::2], arguments[1::2]))
    assert len(bindings) == len(arguments) // 2
    return bindings


@pytest.mark.parametrize(
    ("workflow_name", "job_name", "consumer_steps"),
    [
        (
            "ci.yml",
            "verify",
            ("Build current-HEAD readiness snapshot", "PR quality gate"),
        ),
        (
            "nightly-full-quality.yml",
            "python_full_shards",
            ("Run materialized repository test suite shard",),
        ),
        (
            "nightly-full-quality.yml",
            "deterministic_quality",
            ("Deterministic repository quality gate",),
        ),
        (
            "nightly-heavy-solver.yml",
            "heavy-full-quality",
            (
                "Run materialized repository Python suite",
                "Full workstation/release quality gate",
            ),
        ),
    ],
)
def test_phase2_source_receipts_materialize_before_consumers(
    workflow_name: str, job_name: str, consumer_steps: tuple[str, ...]
) -> None:
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows" / workflow_name).read_text(encoding="utf-8")
    )
    steps = workflow["jobs"][job_name]["steps"]
    names = [step["name"] for step in steps]
    materialize_index = names.index("Materialize exact current-source test evidence")
    run_lines = [line.strip() for line in steps[materialize_index]["run"].splitlines()]
    refresh_indices = [run_lines.index(command) for command in PHASE2_REFRESH_COMMANDS]

    assert refresh_indices == sorted(refresh_indices)
    assert all(run_lines.count(command) == 1 for command in PHASE2_REFRESH_COMMANDS)
    assert refresh_indices[-1] < next(
        index
        for index, line in enumerate(run_lines)
        if line.startswith(
            "python scripts/run_external_code_to_code_technical_receipt.py"
        )
    )
    assert all(materialize_index < names.index(name) for name in consumer_steps)
    if "Validate pristine commercial gap ledger" in names:
        assert (
            names.index("Validate pristine commercial gap ledger") < materialize_index
        )


CI_MODAL_REFRESH_COMMANDS = (
    "env OPENBLAS_CORETYPE=Haswell OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 "
    "python scripts/build_phase2_whole_model_modal_artifacts.py",
    "env OPENBLAS_CORETYPE=Haswell OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 "
    "python scripts/build_phase2_whole_model_modal_artifacts.py --check",
)
CI_MODAL_SUMMARY_PATH = (
    "implementation/phase1/release_evidence/productization/"
    "phase2_whole_model_modal_summary.json"
)


def _modal_materialization_script(
    workflow: dict, job_name: str, consumers: tuple[str, ...]
) -> str:
    job = workflow["jobs"][job_name]
    assert job.get("continue-on-error", False) is False
    assert job.get("if") is None
    for owner in (workflow, job):
        defaults = owner.get("defaults", {}).get("run", {})
        assert defaults.get("shell") in (None, "bash")
        assert defaults.get("working-directory") is None
    steps = job["steps"]
    names = [step["name"] for step in steps]
    assert names.count("Materialize exact current-source test evidence") == 1
    materialize_index = names.index("Materialize exact current-source test evidence")
    step = steps[materialize_index]
    assert step["shell"] == "bash"
    assert step.get("continue-on-error", False) is False
    assert step.get("if") is None
    assert step.get("working-directory") is None
    lines = [line.strip() for line in step["run"].splitlines()]
    assert step["run"].count("scripts/build_phase2_whole_model_modal_artifacts.py") == 2
    assert all(lines.count(command) == 1 for command in CI_MODAL_REFRESH_COMMANDS)
    producer, check = [lines.index(command) for command in CI_MODAL_REFRESH_COMMANDS]
    assert max(lines.index(command) for command in PHASE2_REFRESH_COMMANDS) < producer
    assert lines.count("python - <<'MODAL_SUMMARY'") == 1
    assert lines.count("MODAL_SUMMARY") == 1
    guard = lines.index("python - <<'MODAL_SUMMARY'")
    end = lines.index("MODAL_SUMMARY")
    external = next(
        index
        for index, line in enumerate(lines)
        if line.startswith(
            "python scripts/run_external_code_to_code_technical_receipt.py"
        )
    )
    assert producer < check < guard < end < external
    assert lines[producer : guard + 1] == [
        *CI_MODAL_REFRESH_COMMANDS,
        "python - <<'MODAL_SUMMARY'",
    ]
    # The existing materialization prefix is straight-line Python commands.
    # A copied block inside a branch or after a successful early exit is not admission.
    assert all(
        not line or line.startswith(("#", "python ")) for line in lines[:producer]
    )
    for consumer in consumers:
        assert names.count(consumer) == 1
        assert materialize_index < names.index(consumer)
        assert steps[names.index(consumer)].get("if") is None
        assert steps[names.index(consumer)].get("continue-on-error", False) is False
    prefix = "python - <<'MODAL_SUMMARY'\n"
    assert step["run"].count(prefix) == 1
    code, suffix = step["run"].split(prefix, 1)[1].split("\nMODAL_SUMMARY\n", 1)
    assert suffix
    compile(code, "ci-modal-summary", "exec")
    return code


def _ci_modal_materialization_script(workflow: dict) -> str:
    return _modal_materialization_script(
        workflow, "verify", ("Build current-HEAD readiness snapshot", "PR quality gate")
    )


def test_ci_modal_materialization_is_scoped_before_consumers() -> None:
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    code = _ci_modal_materialization_script(workflow)
    assert "scripts/" not in code
    assert "structural_analysis" not in code
    assert CI_MODAL_SUMMARY_PATH in code
    assert "--check" not in PHASE2_REFRESH_COMMANDS
    assert all(
        "whole_model_modal" not in command for command in PHASE2_REFRESH_COMMANDS
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_producer",
        "missing_check",
        "duplicate_producer",
        "duplicate_check",
        "unscoped_extra_producer",
        "wrong_core",
        "wrong_thread_count",
        "check_before_producer",
        "guard_before_check",
        "missing_guard",
        "outside_materialization_decoy",
        "consumer_before_materialization",
        "continue_on_error",
    ],
)
def test_ci_modal_materialization_rejects_scoped_workflow_drift(mutation: str) -> None:
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    steps = workflow["jobs"]["verify"]["steps"]
    index = next(
        i
        for i, step in enumerate(steps)
        if step["name"] == "Materialize exact current-source test evidence"
    )
    step = steps[index]
    producer, check = CI_MODAL_REFRESH_COMMANDS
    run = step["run"]
    if mutation == "missing_producer":
        step["run"] = run.replace(producer + "\n", "", 1)
    elif mutation == "missing_check":
        step["run"] = run.replace(check + "\n", "", 1)
    elif mutation == "duplicate_producer":
        step["run"] = run.replace(producer + "\n", (producer + "\n") * 2, 1)
    elif mutation == "duplicate_check":
        step["run"] = run.replace(check + "\n", (check + "\n") * 2, 1)
    elif mutation == "unscoped_extra_producer":
        step["run"] = (
            run + "python scripts/build_phase2_whole_model_modal_artifacts.py\n"
        )
    elif mutation == "wrong_core":
        step["run"] = run.replace(
            "OPENBLAS_CORETYPE=Haswell", "OPENBLAS_CORETYPE=Skylake", 1
        )
    elif mutation == "wrong_thread_count":
        step["run"] = run.replace("OPENBLAS_NUM_THREADS=1", "OPENBLAS_NUM_THREADS=2", 1)
    elif mutation == "check_before_producer":
        step["run"] = run.replace(producer + "\n" + check, check + "\n" + producer, 1)
    elif mutation == "guard_before_check":
        step["run"] = run.replace(check + "\n", "", 1).replace(
            "MODAL_SUMMARY\n", "MODAL_SUMMARY\n" + check + "\n", 1
        )
    elif mutation == "missing_guard":
        start = run.index("python - <<'MODAL_SUMMARY'\n")
        end = run.index("\nMODAL_SUMMARY\n", start) + len("\nMODAL_SUMMARY\n")
        step["run"] = run[:start] + run[end:]
    elif mutation == "outside_materialization_decoy":
        step["run"] = run.replace(producer + "\n", "", 1)
        steps.append({"name": "Unrelated modal producer decoy", "run": producer})
    elif mutation == "consumer_before_materialization":
        consumer = next(
            i
            for i, item in enumerate(steps)
            if item["name"] == "Build current-HEAD readiness snapshot"
        )
        steps.insert(index, steps.pop(consumer))
    elif mutation == "continue_on_error":
        step["continue-on-error"] = True
    with pytest.raises((AssertionError, ValueError)):
        _ci_modal_materialization_script(workflow)


def _ci_modal_summary() -> dict:
    return {
        "schema_version": "phase2-whole-model-modal-artifacts.v1",
        "status": "partial",
        "contract_pass": True,
        "case_count": 4,
        "passing_case_count": 4,
        "source_commit_sha": "a" * 40,
        "source_set_hash": "sha256:" + "b" * 64,
        "result_artifact_hash": "sha256:" + "c" * 64,
        "claims": {
            "independent_code_to_code_or_verification_level_2": False,
            "release_readiness": False,
        },
    }


def _run_ci_modal_summary(
    tmp_path: Path,
    summary: dict,
    source_sha: str = "a" * 40,
) -> subprocess.CompletedProcess:
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    code = _ci_modal_materialization_script(workflow)
    output = tmp_path / CI_MODAL_SUMMARY_PATH
    output.parent.mkdir(parents=True)
    output.write_text(json.dumps(summary))
    return subprocess.run(
        [sys.executable, "-I", "-c", code],
        cwd=tmp_path,
        env={"GITHUB_SHA": source_sha},
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )


def test_ci_modal_materialization_summary_accepts_only_bounded_current_identity(
    tmp_path: Path,
) -> None:
    summary = _ci_modal_summary()
    process = _run_ci_modal_summary(tmp_path, summary)
    assert process.returncode == 0, process.stderr
    receipt = json.loads(process.stdout)
    assert receipt == {
        "schema": "ci-whole-model-modal-materialization.v1",
        **{
            field: summary[field]
            for field in (
                "status",
                "contract_pass",
                "case_count",
                "passing_case_count",
                "source_commit_sha",
                "source_set_hash",
                "result_artifact_hash",
            )
        },
        "verification_level_2": False,
        "release_readiness": False,
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", "other-schema.v1"),
        ("status", "blocked"),
        ("contract_pass", False),
        ("contract_pass", 1),
        ("case_count", 3),
        ("case_count", 4.0),
        ("passing_case_count", 3),
        ("passing_case_count", 4.0),
        ("source_commit_sha", "d" * 40),
        ("source_set_hash", "not-a-hash"),
        ("result_artifact_hash", "not-a-hash"),
        ("claims.independent_code_to_code_or_verification_level_2", True),
        ("claims.independent_code_to_code_or_verification_level_2", None),
        ("claims.release_readiness", True),
        ("claims.release_readiness", None),
    ],
)
def test_ci_modal_materialization_summary_rejects_unqualified_receipts(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    summary = _ci_modal_summary()
    if field.startswith("claims."):
        summary["claims"][field.removeprefix("claims.")] = value
    else:
        summary[field] = value
    process = _run_ci_modal_summary(tmp_path, summary)
    assert process.returncode != 0
    assert "modal materialization" in process.stderr
    assert not process.stdout


@pytest.mark.parametrize("source_sha", ["", "not-a-commit"])
def test_ci_modal_materialization_summary_rejects_invalid_checkout_identity(
    tmp_path: Path,
    source_sha: str,
) -> None:
    summary = _ci_modal_summary()
    summary["source_commit_sha"] = source_sha
    process = _run_ci_modal_summary(tmp_path, summary, source_sha)
    assert process.returncode != 0
    assert "modal materialization is not bound to GITHUB_SHA" in process.stderr
    assert not process.stdout


EXPANDED_MODAL_CONTEXTS = (
    (
        "python-test-collection.yml",
        "full_shards",
        (
            (
                "Run materialized repository test suite shard",
                "python scripts/run_pytest_shard.py --shard-index ",
            ),
        ),
    ),
    (
        "nightly-full-quality.yml",
        "python_full_shards",
        (
            (
                "Run materialized repository test suite shard",
                "python scripts/run_pytest_shard.py --shard-index ",
            ),
        ),
    ),
    (
        "nightly-full-quality.yml",
        "deterministic_quality",
        (
            (
                "Deterministic repository quality gate",
                "python scripts/verify_quality_gate.py --mode full --python-suite-delegated-to-workflow-shards",
            ),
        ),
    ),
    (
        "nightly-heavy-solver.yml",
        "heavy-full-quality",
        (
            ("Run materialized repository Python suite", "python -m pytest -q "),
            (
                "Full workstation/release quality gate",
                "python scripts/verify_quality_gate.py --mode full --python-suite-verified-in-prior-step",
            ),
        ),
    ),
)
EXPANDED_MODAL_CONTEXT_IDS = (
    "python-full-shards",
    "nightly-full-shards",
    "nightly-deterministic-quality",
    "heavy-full-quality",
)


def _expanded_modal_materialization_script(
    workflow: dict,
    job_name: str,
    consumers: tuple[tuple[str, str], ...],
) -> str:
    code = _modal_materialization_script(
        workflow, job_name, tuple(name for name, _ in consumers)
    )
    original = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    assert code == _ci_modal_materialization_script(original)
    steps = workflow["jobs"][job_name]["steps"]
    for name, command_prefix in consumers:
        consumer = next(step for step in steps if step["name"] == name)
        run = consumer["run"]
        assert len(run.splitlines()) == 1
        assert run.startswith(command_prefix)
        lexer = shlex.shlex(run, posix=True, punctuation_chars=";&|<>")
        lexer.whitespace_split = True
        arguments = list(lexer)
        assert not any(
            token and all(character in ";&|<>" for character in token)
            for token in arguments
        )
        assert consumer.get("shell") in (None, "bash")
        assert consumer.get("working-directory") is None
        if "run_pytest_shard.py" in run:
            index = arguments.index("--shard-count")
            assert arguments[index : index + 3] == ["--shard-count", "4", "--"]
    return code


@pytest.mark.parametrize(
    ("workflow_name", "job_name", "consumers"),
    EXPANDED_MODAL_CONTEXTS,
    ids=EXPANDED_MODAL_CONTEXT_IDS,
)
def test_all_modal_consumers_admit_exact_ci_summary_before_execution(
    workflow_name: str,
    job_name: str,
    consumers: tuple[tuple[str, str], ...],
) -> None:
    workflow = yaml.safe_load((ROOT / ".github/workflows" / workflow_name).read_text())
    code = _expanded_modal_materialization_script(workflow, job_name, consumers)
    assert CI_MODAL_SUMMARY_PATH in code
    assert all(
        "whole_model_modal" not in command for command in PHASE2_REFRESH_COMMANDS
    )


@pytest.mark.parametrize(
    ("workflow_name", "job_name", "consumers"),
    EXPANDED_MODAL_CONTEXTS,
    ids=EXPANDED_MODAL_CONTEXT_IDS,
)
@pytest.mark.parametrize(
    "mutation",
    (
        "missing_producer",
        "missing_check",
        "duplicate_producer",
        "duplicate_check",
        "wrong_core",
        "wrong_thread_count",
        "check_before_producer",
        "guard_before_check",
        "guard_code_changed",
        "outside_materialization_decoy",
        "consumer_before_materialization",
        "consumer_command_decoy",
        "materialization_continue_on_error",
        "job_continue_on_error",
        "conditional_materialization",
        "conditional_consumer",
        "early_successful_exit",
        "disable_errexit",
        "consumer_error_rescue",
        "consumer_successful_suffix",
    ),
)
def test_all_modal_consumers_reject_context_local_materialization_drift(
    workflow_name: str,
    job_name: str,
    consumers: tuple[tuple[str, str], ...],
    mutation: str,
) -> None:
    workflow = yaml.safe_load((ROOT / ".github/workflows" / workflow_name).read_text())
    before = copy.deepcopy(workflow)
    job = workflow["jobs"][job_name]
    steps = job["steps"]
    index = next(
        i
        for i, step in enumerate(steps)
        if step["name"] == "Materialize exact current-source test evidence"
    )
    step = steps[index]
    producer, check = CI_MODAL_REFRESH_COMMANDS
    run = step["run"]
    consumer_name = consumers[0][0]
    consumer = next(item for item in steps if item["name"] == consumer_name)
    if mutation == "missing_producer":
        step["run"] = run.replace(producer + "\n", "", 1)
    elif mutation == "missing_check":
        step["run"] = run.replace(check + "\n", "", 1)
    elif mutation == "duplicate_producer":
        step["run"] = run.replace(producer + "\n", (producer + "\n") * 2, 1)
    elif mutation == "duplicate_check":
        step["run"] = run.replace(check + "\n", (check + "\n") * 2, 1)
    elif mutation == "wrong_core":
        step["run"] = run.replace(
            "OPENBLAS_CORETYPE=Haswell", "OPENBLAS_CORETYPE=Skylake", 1
        )
    elif mutation == "wrong_thread_count":
        step["run"] = run.replace("OPENBLAS_NUM_THREADS=1", "OPENBLAS_NUM_THREADS=2", 1)
    elif mutation == "check_before_producer":
        step["run"] = run.replace(producer + "\n" + check, check + "\n" + producer, 1)
    elif mutation == "guard_before_check":
        step["run"] = run.replace(check + "\n", "", 1).replace(
            "MODAL_SUMMARY\n", "MODAL_SUMMARY\n" + check + "\n", 1
        )
    elif mutation == "guard_code_changed":
        step["run"] = run.replace(
            'payload.get("contract_pass") is not True',
            'payload.get("contract_pass") is True',
            1,
        )
    elif mutation == "outside_materialization_decoy":
        step["run"] = run.replace(producer + "\n", "", 1)
        steps.insert(index, {"name": "Unrelated modal producer decoy", "run": producer})
    elif mutation == "consumer_before_materialization":
        steps.remove(consumer)
        steps.insert(index, consumer)
    elif mutation == "consumer_command_decoy":
        consumer["run"] = "true"
    elif mutation == "materialization_continue_on_error":
        step["continue-on-error"] = True
    elif mutation == "job_continue_on_error":
        job["continue-on-error"] = True
    elif mutation == "conditional_materialization":
        step["if"] = "${{ false }}"
    elif mutation == "conditional_consumer":
        consumer["if"] = "${{ false }}"
    elif mutation == "early_successful_exit":
        step["run"] = run.replace(producer + "\n", "exit 0\n" + producer + "\n", 1)
    elif mutation == "disable_errexit":
        step["run"] = "set +e\n" + run
    elif mutation == "consumer_error_rescue":
        consumer["run"] += "||true"
    elif mutation == "consumer_successful_suffix":
        consumer["run"] += ";true"
    assert workflow != before
    with pytest.raises(AssertionError):
        _expanded_modal_materialization_script(workflow, job_name, consumers)


@pytest.mark.parametrize(
    ("workflow_name", "job_name", "preparer_name", "consumer_steps"),
    [
        (
            "ci.yml",
            "verify",
            "Materialize exact current-source test evidence",
            ("Build current-HEAD readiness snapshot", "PR quality gate"),
        ),
        (
            "python-test-collection.yml",
            "full_shards",
            "Materialize exact current-source test evidence",
            ("Run materialized repository test suite shard",),
        ),
        (
            "nightly-full-quality.yml",
            "python_full_shards",
            "Materialize exact current-source test evidence",
            ("Run materialized repository test suite shard",),
        ),
        (
            "nightly-full-quality.yml",
            "deterministic_quality",
            "Materialize exact current-source test evidence",
            ("Deterministic repository quality gate",),
        ),
        (
            "nightly-heavy-solver.yml",
            "heavy-full-quality",
            "Materialize exact current-source test evidence",
            (
                "Run materialized repository Python suite",
                "Full workstation/release quality gate",
            ),
        ),
        (
            "release-publish-current.yml",
            "publish",
            "Regenerate release viewer artifacts",
            ("Build fresh publication candidate", "Strict release quality gate"),
        ),
    ],
    ids=(
        "ci-verify",
        "python-full-shards",
        "nightly-full-shards",
        "nightly-deterministic-quality",
        "heavy-full-quality",
        "release-publish",
    ),
)
def test_analytic_frame_and_hierarchy_replay_before_consumers(
    workflow_name: str,
    job_name: str,
    preparer_name: str,
    consumer_steps: tuple[str, ...],
) -> None:
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows" / workflow_name).read_text(encoding="utf-8")
    )
    steps = workflow["jobs"][job_name]["steps"]
    names = [step["name"] for step in steps]
    preparer_index = names.index(preparer_name)
    preparer = steps[preparer_index]
    run_lines = [line.strip() for line in preparer["run"].splitlines()]
    indices = [run_lines.index(command) for command in ANALYTIC_FRAME_REFRESH_COMMANDS]

    assert indices == sorted(indices)
    assert all(
        run_lines.count(command) == 1 for command in ANALYTIC_FRAME_REFRESH_COMMANDS
    )
    assert all(preparer_index < names.index(name) for name in consumer_steps)
    assert "continue-on-error" not in preparer
    if "Validate pristine commercial gap ledger" in names:
        assert names.index("Validate pristine commercial gap ledger") < preparer_index
    if workflow_name == "release-publish-current.yml":
        assert names.index("Verify cryptographic legal and release authority") < (
            preparer_index
        )
        assert indices[-1] < run_lines.index("set +e")


@pytest.mark.parametrize(
    ("workflow_name", "job_name"),
    [("python-test-collection.yml", "full_shards"), ("ci.yml", "verify")],
)
def test_failed_materialization_upload_preserves_failure_and_limits_files(
    workflow_name: str,
    job_name: str,
) -> None:
    workflow = yaml.safe_load((ROOT / ".github/workflows" / workflow_name).read_text())
    job = workflow["jobs"][job_name]
    steps = {step["name"]: step for step in job["steps"]}
    materialize = steps["Materialize exact current-source test evidence"]
    assert materialize["id"] == "materialize"
    if job_name == "full_shards":
        assert "--fail-blocked" not in materialize["run"]
        assert (
            "python scripts/build_internal_license_due_diligence.py"
            in materialize["run"]
        )
    else:
        assert "--fail-blocked" in materialize["run"]
    assert not job.get("continue-on-error", False)
    assert all(not step.get("continue-on-error", False) for step in job["steps"])
    gate = (
        "Run materialized repository test suite shard"
        if job_name == "full_shards"
        else "Build current-HEAD readiness snapshot"
    )
    assert "if" not in steps[gate]
    condition = "${{ failure() && steps.materialize.outcome == 'failure' }}"
    assert steps["Describe failed materialization diagnostics"]["if"] == condition
    upload = steps["Upload failed materialization diagnostics"]
    assert upload["if"] == condition
    assert upload["with"]["name"] == (
        "materialization-failure-shard-${{ matrix.shard }}-${{ github.sha }}"
        if job_name == "full_shards"
        else "materialization-failure-verify-${{ github.sha }}"
    )
    assert upload["with"]["path"].splitlines() == [
        "materialization-failure-context.json",
        "implementation/phase1/release_evidence/productization/"
        "external_code_to_code_technical_execution_receipt.json",
        "implementation/phase1/release_evidence/productization/"
        "external_modal_buckling_technical_execution_receipt.json",
        "artifacts/manifests/internal_license_due_diligence.current.v1.json",
    ]
    assert upload["with"]["retention-days"] == 7


def test_full_shard_reports_pytest_before_enforcing_external_license_gate() -> None:
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/python-test-collection.yml").read_text()
    )
    jobs = workflow["jobs"]
    shard_steps = jobs["full_shards"]["steps"]
    names = [step["name"] for step in shard_steps]
    materialize = shard_steps[
        names.index("Materialize exact current-source test evidence")
    ]
    test_step = shard_steps[names.index("Run materialized repository test suite shard")]
    upload = shard_steps[
        names.index(
            "Retain diagnostic shard test result independently of license status"
        )
    ]
    license_gate = shard_steps[
        names.index("Require exact current-source external license contract")
    ]

    assert (
        names.index("Materialize exact current-source test evidence")
        < names.index("Run materialized repository test suite shard")
        < names.index(
            "Retain diagnostic shard test result independently of license status"
        )
        < names.index("Require exact current-source external license contract")
    )
    assert "if" not in test_step
    assert "--junitxml=pytest-full-shard-${{ matrix.shard }}.xml" in test_step["run"]
    assert (
        "python scripts/build_internal_license_due_diligence.py" in materialize["run"]
    )
    assert "--fail-blocked" not in materialize["run"]
    assert upload["if"] == "${{ always() }}"
    assert upload["with"] == {
        "name": "pytest-full-shard-diagnostic-${{ matrix.shard }}-${{ github.sha }}",
        "path": "pytest-full-shard-${{ matrix.shard }}.xml",
        "if-no-files-found": "warn",
        "retention-days": 14,
    }
    assert license_gate["if"] == (
        "${{ always() && steps.materialize.outcome == 'success' }}"
    )
    assert license_gate["run"] == (
        "python scripts/build_internal_license_due_diligence.py "
        '--out "$RUNNER_TEMP/internal-license-gate.json" --fail-blocked'
    )
    assert all(not step.get("continue-on-error", False) for step in shard_steps)
    assert jobs["full"]["needs"] == "full_shards"
    assert jobs["full"]["if"] == "${{ always() }}"


@pytest.mark.parametrize(
    ("workflow_name", "job_name"),
    [("python-test-collection.yml", "full_shards"), ("ci.yml", "verify")],
)
def test_failure_context_is_valid_json_without_generation_or_qualification_credit(
    tmp_path: Path,
    workflow_name: str,
    job_name: str,
) -> None:
    workflow = yaml.safe_load((ROOT / ".github/workflows" / workflow_name).read_text())
    step = next(
        step
        for step in workflow["jobs"][job_name]["steps"]
        if step["name"] == "Describe failed materialization diagnostics"
    )
    lines = step["run"].splitlines()
    assert lines[0] == "python - <<'PYTHON'" and lines[-1] == "PYTHON"
    subprocess.run(
        [sys.executable, "-c", "\n".join(lines[1:-1])],
        cwd=tmp_path,
        env={
            "GITHUB_SHA": "a" * 40,
            "GITHUB_RUN_ID": "123",
            "GITHUB_RUN_ATTEMPT": "2",
            "GITHUB_JOB": job_name,
        },
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(
        (tmp_path / "materialization-failure-context.json").read_bytes()
    )
    assert payload["job"] == job_name
    assert payload["workflow_sha"] == "a" * 40
    assert payload["run_id"] == "123" and payload["run_attempt"] == "2"
    assert payload["diagnostic_only"] is True
    assert payload["receipt_generation_attested"] is False
    assert payload["may_include_tracked_or_partially_rewritten_receipts"] is True
    assert payload["qualification_inferred"] is False


def test_every_pull_request_collects_the_complete_pytest_suite() -> None:
    workflow = (
        ROOT / ".github" / "workflows" / "python-test-collection.yml"
    ).read_text(encoding="utf-8")

    assert "pull_request:" in workflow
    assert "paths:" not in workflow
    assert "python -m pytest --collect-only -q" in workflow
    assert "collect:\n    if:" not in workflow
    assert workflow.count("python -m pip install numpy==1.26.4 scipy==1.12.0") == 4
    assert "OPENBLAS_CORETYPE: Haswell" in workflow
    assert 'OPENBLAS_NUM_THREADS: "1"' in workflow
    assert 'OMP_NUM_THREADS: "1"' in workflow


def test_all_supported_events_run_the_complete_pytest_suite() -> None:
    workflow = (
        ROOT / ".github" / "workflows" / "python-test-collection.yml"
    ).read_text(encoding="utf-8")

    assert "Protected Option B is active" in workflow
    assert "  pull_request:\n" in workflow
    assert "  merge_group:\n" in workflow
    assert "  push:\n" in workflow
    assert "  workflow_dispatch:\n" in workflow
    push_trigger = workflow.split("  push:\n", 1)[1].split("  workflow_dispatch:\n", 1)[
        0
    ]
    assert 'branches: ["main"]' in push_trigger
    assert "python scripts/run_pytest_shard.py" in workflow
    shard_job = workflow.split("  full_shards:", 1)[1].split("  full:", 1)[0]
    assert "\n    if:" not in shard_job
    assert "name: pytest-full-shard-${{ matrix.shard }}" in shard_job
    assert "fail-fast: false" in shard_job
    assert "shard: [0, 1, 2, 3]" in shard_job
    assert '--shard-index "${{ matrix.shard }}"' in shard_job
    assert "--shard-count 4" in shard_job
    assert "timeout-minutes: 360" in shard_job
    full_checkout = shard_job.split(
        "      - name: Set up Python",
        1,
    )[0]
    assert "fetch-depth: 0" in full_checkout
    aggregate_job = workflow.split("  full:", 1)[1]
    assert "name: pytest-full" in aggregate_job
    assert "if: ${{ always() }}" in aggregate_job
    assert "needs: full_shards" in aggregate_job
    assert 'test "$FULL_SHARDS_RESULT" = "success"' in aggregate_job
    pristine_ledger = workflow.index("- name: Validate pristine commercial gap ledger")
    hosted_hip_source = workflow.index(
        "- name: Validate hosted HIP receipt source binding"
    )
    materialize = workflow.index(
        "- name: Materialize exact current-source test evidence"
    )
    full_suite = workflow.index("- name: Run materialized repository test suite shard")
    ledger_nodeid = (
        "tests/test_commercial_gap_ledger_status.py::"
        "test_commercial_gap_ledger_status_is_honest_about_current_blockers"
    )
    assert workflow.count(ledger_nodeid) == 2
    hip_reproduction_nodeid = (
        "tests/test_build_g1_mgt_hip_current_tangent_host_parser_receipt.py::"
        "test_committed_receipt_is_reproducible"
    )
    assert workflow.count(hip_reproduction_nodeid) == 1
    assert "--check-source-only" in workflow[hosted_hip_source:pristine_ledger]
    assert hosted_hip_source < pristine_ledger < materialize < full_suite
    assert "--deselect" in workflow[full_suite:]
    for command in (
        *PHASE2_REFRESH_COMMANDS,
        "python scripts/build_stateful_nonlinear_no_solve_reaction_only_artifact.py",
        "python scripts/build_fracture_energy_concrete_benchmark.py",
        "python scripts/build_g1_mgt_state_updated_frame_axial_matrix_free_fgmres_smoke.py",
        "python scripts/build_g1_mgt_state_updated_frame_axial_matrix_free_newton_continuation_receipt.py",
    ):
        assert command in workflow
        assert materialize < workflow.index(command) < full_suite


def test_nightly_full_quality_is_full_in_name_and_execution() -> None:
    workflow = (ROOT / ".github" / "workflows" / "nightly-full-quality.yml").read_text(
        encoding="utf-8"
    )

    assert "python scripts/verify_quality_gate.py" in workflow
    assert "--mode full" in workflow
    assert "--python-suite-delegated-to-workflow-shards" in workflow
    assert "python scripts/verify_quality_gate.py --mode pr" not in workflow
    assert "OPENBLAS_CORETYPE: Haswell" in workflow
    assert 'OPENBLAS_NUM_THREADS: "1"' in workflow
    assert 'OMP_NUM_THREADS: "1"' in workflow
    for checkout in workflow.split(
        "uses: actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803"
    )[1:]:
        checkout_options = checkout.split("\n\n", 1)[0]
        assert checkout_options.count("with:") == 1
        assert "fetch-depth: 0" in checkout_options
        assert "persist-credentials: false" in checkout_options
    assert "- name: Deterministic Python regression suite" not in workflow
    assert "python_full_shards:" in workflow
    assert "matrix:\n        shard: [0, 1, 2, 3]" in workflow
    assert "python scripts/run_pytest_shard.py" in workflow
    assert workflow.count("--deselect") == 2
    assert "full_quality:" in workflow
    assert "if: ${{ always() }}" in workflow
    assert "needs: [python_full_shards, deterministic_quality]" in workflow
    assert 'test "$PYTHON_FULL_SHARDS_RESULT" = "success"' in workflow
    assert 'test "$DETERMINISTIC_QUALITY_RESULT" = "success"' in workflow
    assert (
        "tests/test_commercial_gap_ledger_status.py::"
        "test_commercial_gap_ledger_status_is_honest_about_current_blockers" in workflow
    )
    assert (
        "tests/test_build_g1_mgt_hip_current_tangent_host_parser_receipt.py::"
        "test_committed_receipt_is_reproducible" in workflow
    )
    materialize = workflow.index(
        "- name: Materialize exact current-source test evidence"
    )
    quality_gate = workflow.index("- name: Deterministic repository quality gate")
    propagation = workflow.index("for pass in 1 2 3; do")
    assert materialize < propagation < quality_gate
    phase1 = workflow.index(
        "python scripts/build_phase1_core_api_contract_artifacts.py",
        materialize,
    )
    assert materialize < phase1 < propagation
    for command in (
        "python scripts/build_developer_preview_readiness.py",
        "python scripts/build_developer_preview_rc_status.py",
        "python scripts/report_release_evidence_freshness.py",
        "python scripts/report_pm_release_gate.py",
        "python scripts/build_pm_release_blocker_action_register.py",
        "python scripts/build_product_readiness_snapshot.py",
        "python scripts/build_structural_product_development_roadmap.py",
    ):
        assert propagation < workflow.index(command, propagation) < quality_gate
    assert "scripts/build_product_state.py" not in workflow

    gate = (ROOT / "scripts" / "verify_quality_gate.py").read_text(encoding="utf-8")
    assert '[_python(), "-m", "pytest", "-q"]' in gate
    assert "python_suite_delegated_to_workflow_shards" in gate


def test_heavy_quality_separates_python_and_readiness_evidence_epochs() -> None:
    workflow = (ROOT / ".github" / "workflows" / "nightly-heavy-solver.yml").read_text(
        encoding="utf-8"
    )

    materialize = workflow.index(
        "- name: Materialize exact current-source test evidence"
    )
    python_suite = workflow.index("- name: Run materialized repository Python suite")
    readiness = workflow.index("- name: Materialize current-source readiness graph")
    quality_gate = workflow.index("- name: Full workstation/release quality gate")
    assert materialize < python_suite < readiness < quality_gate
    assert "timeout-minutes: 420" in workflow
    assert "--python-suite-verified-in-prior-step" in workflow[quality_gate:]
    assert "--materialized-python-suite" not in workflow
    assert "python -m pytest -q" in workflow[python_suite:readiness]
    assert workflow[python_suite:readiness].count("--deselect") == 2
    assert (
        "python scripts/build_phase1_core_api_contract_artifacts.py"
        in workflow[readiness:quality_gate]
    )
    assert "for pass in 1 2 3; do" in workflow[readiness:quality_gate]
    checkout = workflow.split(
        "uses: actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803",
        1,
    )[1].split("\n\n", 1)[0]
    assert checkout.count("with:") == 1
    assert "fetch-depth: 0" in checkout
    assert "persist-credentials: false" in checkout


def test_current_product_state_records_every_completed_main_nightly_outcome() -> None:
    workflow = (ROOT / ".github" / "workflows" / "product-state-current.yml").read_text(
        encoding="utf-8"
    )

    assert "timeout-minutes: 90" in workflow
    assert "workflow_run:" in workflow
    assert 'workflows: ["Nightly Full Quality"]' in workflow
    assert "github.event.workflow_run.conclusion == 'success'" not in workflow
    assert "github.event.workflow_run.head_branch == 'main'" in workflow
    assert "github.event.workflow_run.event == 'schedule'" in workflow
    assert "github.event.workflow_run.event == 'workflow_dispatch'" in workflow
    assert "PRODUCT_STATE_SHA: ${{ github.event.workflow_run.head_sha }}" in workflow
    assert (
        "PRODUCT_STATE_CONCLUSION: ${{ github.event.workflow_run.conclusion }}"
        in workflow
    )
    assert "PRODUCT_STATE_WORKFLOW_SHA: ${{ github.workflow_sha }}" in workflow
    assert "PRODUCT_STATE_WORKFLOW_REF: ${{ github.workflow_ref }}" in workflow
    assert "PRODUCT_STATE_WORKFLOW_NAME: ${{ github.workflow }}" in workflow
    assert "PRODUCT_STATE_WORKFLOW_EVENT: ${{ github.event_name }}" in workflow
    assert "PRODUCT_STATE_WORKFLOW_RUN_ID: ${{ github.run_id }}" in workflow
    assert "PRODUCT_STATE_WORKFLOW_RUN_NUMBER: ${{ github.run_number }}" in workflow
    assert "PRODUCT_STATE_WORKFLOW_RUN_ATTEMPT: ${{ github.run_attempt }}" in workflow
    assert "ref: ${{ env.PRODUCT_STATE_SHA }}" in workflow
    assert 'test "$PRODUCT_STATE_WORKFLOW_SHA" = "$PRODUCT_STATE_SHA"' in workflow
    assert 'test "$PRODUCT_STATE_WORKFLOW_EVENT" = "workflow_run"' in workflow
    assert (
        "$GITHUB_REPOSITORY/.github/workflows/"
        "product-state-current.yml@refs/heads/main" in workflow
    )
    assert "Verify product-state workflow execution identity" in workflow
    identity_step = workflow.index("Verify product-state workflow execution identity")
    evidence_step = workflow.index("Verify generated capability surfaces")
    assert identity_step < evidence_step
    assert 'python-version: "3.12.11"' in workflow
    assert "canonical/requirements-cp312-manylinux2014-x86_64.lock" in workflow
    assert "--require-hashes" in workflow
    assert "--no-deps" in workflow
    assert "OPENBLAS_CORETYPE: Haswell" in workflow
    assert 'PYTHONHASHSEED: "0"' in workflow
    assert "scripts/build_product_state.py" in workflow
    assert "scripts/generate_capability_surfaces.py" in workflow
    assert "opensees-calculix-current-source.yml/runs?branch=main" in workflow
    assert 'row.get("head_sha") == os.environ["PRODUCT_STATE_SHA"]' in workflow
    assert "CLEAN_RUNNER_RUN_CONCLUSION" in workflow
    assert "if: ${{ env.CLEAN_RUNNER_RUN_CONCLUSION == 'success' }}" in workflow
    assert (
        "opensees-calculix-current-source-{os.environ['CLEAN_RUNNER_RUN_ID']}"
        in workflow
    )
    assert (
        "CLEAN_RUNNER_EVIDENCE_ROOT: "
        ".ci/product-state-inputs/opensees-calculix-clean-runner" in workflow
    )
    assert "CLEAN_RUNNER_RECEIPT_DIR" not in workflow
    assert "actions/runs/$CLEAN_RUNNER_RUN_ID/jobs?per_page=100" in workflow
    assert "actions/runs/$CLEAN_RUNNER_RUN_ID/artifacts?per_page=100" in workflow
    assert "actions/artifacts/$artifact_id/zip" in workflow
    assert 'candidate.get("archive_download_url") == expected_url' in workflow
    assert 'workflow_run.get("id") == run["id"]' in workflow
    assert "expected_producer_name" in workflow
    assert "producer-artifact.json" in workflow
    assert 'artifact["id"] == producer_artifact["id"]' in workflow
    assert '"id": producer_artifact["id"]' in workflow
    assert '"digest": producer_artifact["digest"].removeprefix("sha256:")' in workflow
    clean_runner_verification = workflow[
        workflow.index(
            'summary = json.loads(Path(os.environ["CLEAN_RUNNER_SUMMARY_PATH"])'
        ) : workflow.index(
            'verification = json.loads((root / "attestation-verification.json")',
            workflow.index(
                'summary = json.loads(Path(os.environ["CLEAN_RUNNER_SUMMARY_PATH"])'
            ),
        )
    ]
    producer_loader = clean_runner_verification.index("producer_artifact = json.loads(")
    producer_first_use = clean_runner_verification.index(
        '"id": producer_artifact["id"]'
    )
    assert producer_loader < producer_first_use
    assert '(root / "producer-artifact.json").read_text()' in clean_runner_verification
    assert "clean_runner_artifact_archive_invalid" in workflow
    assert "clean_runner_artifact_file_set_invalid" in workflow
    assert (
        '"artifact_status": "unavailable"' in workflow
        and "exact_sha_artifact_download_failed_after_bounded_retry" in workflow
    )
    unavailable_branch = workflow.index(
        "if ! gh api -H 'Accept: application/vnd.github+json'"
    )
    unavailable_exit = workflow.index("exit 0", unavailable_branch)
    materialized_copy = workflow.index(
        'materialized_receipt_dir="$CLEAN_RUNNER_EVIDENCE_ROOT/'
        'artifacts/vv/opensees_calculix_clean_runner"'
    )
    assert unavailable_branch < unavailable_exit < materialized_copy
    assert 'cp -R "$artifact_root"/. "$materialized_receipt_dir"/' in workflow
    assert 'materialized_host="$CLEAN_RUNNER_EVIDENCE_ROOT/$host_receipt"' in workflow
    assert (
        "git status --porcelain=v1 --untracked-files=all -- \\\n"
        "              artifacts/vv/opensees_calculix_clean_runner" in workflow
    )
    assert (
        'cp -R "$artifact_root"/. '
        '"artifacts/vv/opensees_calculix_clean_runner"/' not in workflow
    )
    product_state_upload = workflow.index(
        "- name: Upload verified current and historical Product State artifact"
    )
    assert ".ci/product-state-inputs" in workflow
    assert "${{ runner.temp }}/signed-product-state" in workflow[product_state_upload:]
    assert (
        '--signer-workflow "$GITHUB_REPOSITORY/.github/workflows/opensees-calculix-clean-runner-attestor.yml"'
        in workflow
    )
    assert 'certificate["runInvocationURI"] == invocation' in workflow
    assert (
        'statement["predicate"]["runDetails"]["metadata"]["invocationId"]' in workflow
    )
    assert 'statement["subject"] == [{' in workflow
    assert '--signer-digest "$PRODUCT_STATE_SHA"' in workflow
    assert '--clean-runner-summary "$CLEAN_RUNNER_SUMMARY_PATH"' in workflow
    assert (
        "--same-operator-supplemental-receipt "
        '"$SAME_OPERATOR_SUPPLEMENTAL_RECEIPT_PATH"' in workflow
    )
    assert '--external-vv-clean-runner-summary "$CLEAN_RUNNER_SUMMARY_PATH"' in workflow
    assert "p0-canonical-contract.yml" in workflow
    assert "head_sha=$PRODUCT_STATE_SHA" in workflow
    assert "for attempt in {1..30}" in workflow
    assert "sleep 10" in workflow
    assert "canonical workflow lookup failed after bounded retry" in workflow
    assert 'row.get("head_sha") == os.environ["PRODUCT_STATE_SHA"]' in workflow
    parsed = yaml.safe_load(workflow)
    build_steps = parsed["jobs"]["build-current-state"]["steps"]
    canonical_step = next(
        step
        for step in build_steps
        if step["name"] == "Materialize exact-SHA canonical verification receipt"
    )
    canonical_run = canonical_step["run"]
    assert "gh run download" not in canonical_run
    selection_bindings = {
        "--run": ".ci/product-state-inputs/canonical-verification-workflow-run.json",
        "--inventory": ".ci/product-state-inputs/canonical-verification-artifacts.json",
        "--repository": "$GITHUB_REPOSITORY",
        "--source-sha": "$PRODUCT_STATE_SHA",
        "--run-id": "$canonical_run_id",
    }
    assert _canonical_artifact_cli_bindings(canonical_run, "select") == (
        selection_bindings
    )
    sealed_bindings = selection_bindings | {
        "--artifact": ".ci/product-state-inputs/canonical-verification-artifact-api.json",
        "--api-url": "$GITHUB_API_URL",
        "--materialize-root": ".",
        "--identity-out": ".ci/product-state-inputs/canonical-actions-artifact-identity.json",
    }
    assert _canonical_artifact_cli_bindings(canonical_run, "admit") == (
        sealed_bindings
        | {"--archive": ".ci/canonical-receipt-download/canonical-artifact.zip"}
    )
    run_lookup = '"repos/$GITHUB_REPOSITORY/actions/runs/$canonical_run_id"'
    artifact_lookup = (
        '"repos/$GITHUB_REPOSITORY/actions/artifacts/$canonical_artifact_id"'
    )
    archive_lookup = (
        '"repos/$GITHUB_REPOSITORY/actions/artifacts/$canonical_artifact_id/zip"'
    )
    assert artifact_lookup in canonical_run
    assert archive_lookup in canonical_run
    assert canonical_run.count(run_lookup) == 2
    assert (
        canonical_run.index(run_lookup)
        < canonical_run.index("verify_canonical_actions_artifact.py select")
        < canonical_run.index(artifact_lookup)
        < canonical_run.index(archive_lookup)
        < canonical_run.rindex(run_lookup)
        < canonical_run.index("verify_canonical_actions_artifact.py admit")
    )
    source_inputs = next(
        step
        for step in build_steps
        if step["name"] == "Materialize exact current-source product-state inputs"
    )["run"]
    assert " ".join(source_inputs.replace("\\\n", " ").split()).startswith(
        "python scripts/verify_tracked_source_tree.py --repo-root . "
        '--source-sha "$PRODUCT_STATE_SHA" --profile consumer'
    )
    candidate = next(
        step
        for step in build_steps
        if step["name"] == "Assemble allowlisted source-bound Product State candidate"
    )["run"]
    required = candidate.split("required = {", 1)[1].split("}", 1)[0]
    for key in ("--run", "--inventory", "--artifact", "--identity-out"):
        assert f'"{sealed_bindings[key]}"' in required
    replay = next(
        step
        for step in parsed["jobs"]["verify-current-state"]["steps"]
        if step["name"] == "Replay exact-source overlay, full DAG, and provenance"
    )["run"]
    assert _canonical_artifact_cli_bindings(replay, "replay") == sealed_bindings
    assert (
        replay.index("build_post_main_evidence_overlay.py materialize")
        < replay.index("verify_canonical_actions_artifact.py replay")
        < replay.index("check_generated_artifact_dag.py")
        < replay.index("build_product_state_provenance_bundle.py")
    )
    assert "for attempt in {1..12}" in workflow
    assert "sleep 5" in workflow
    assert "exact-attempt canonical artifact unavailable after bounded retry" in (
        canonical_run
    )
    assert (
        "artifacts/manifests/canonical_verification_environment.current.v1.json"
        in workflow
    )
    assert (
        "CANONICAL_WHEEL_CONTRACT_PATH: .ci/canonical-project-wheel-contract.json"
        in workflow
    )
    assert (
        "CANONICAL_WHEEL_PATH: .ci/canonical-wheel/"
        "structural_analysis-0.3.0-py3-none-any.whl" in workflow
    )
    assert (
        "NIGHTLY_WORKFLOW_RUN_EVENT_PATH: "
        ".ci/product-state-inputs/nightly-workflow-run-event.json" in workflow
    )
    assert (
        'receipt["contract_profile"] == "p0-canonical-installed-wheel.v1"' in workflow
    )
    assert 'receipt["source_commit_sha"] == os.environ["PRODUCT_STATE_SHA"]' in workflow
    assert 'receipt["project_wheel"] == wheel_contract' in workflow
    assert "hashlib.sha256(wheel_path.read_bytes()).hexdigest()" in workflow
    assert 'receipt["contract_pass"] is True' in workflow
    assert 'cp "$GITHUB_EVENT_PATH" "$NIGHTLY_WORKFLOW_RUN_EVENT_PATH"' in workflow
    assert (
        workflow.count(
            "gh api \"repos/$GITHUB_REPOSITORY/git/ref/heads/main\" --jq '.object.sha'"
        )
        == 2
    )
    assert '--observed-main-sha "${{ steps.observe_main.outputs.sha }}"' in workflow
    assert "github_api_refs_heads_main_pre_build" in workflow
    assert (
        workflow.count(
            '--nightly-workflow-run-event "$NIGHTLY_WORKFLOW_RUN_EVENT_PATH"'
        )
        == 3
    )
    assert '--product-state-workflow-sha "$PRODUCT_STATE_WORKFLOW_SHA"' in workflow
    assert '--product-state-workflow-ref "$PRODUCT_STATE_WORKFLOW_REF"' in workflow
    assert '--product-state-workflow-name "$PRODUCT_STATE_WORKFLOW_NAME"' in workflow
    assert '--product-state-workflow-event "$PRODUCT_STATE_WORKFLOW_EVENT"' in workflow
    assert (
        '--product-state-workflow-run-id "$PRODUCT_STATE_WORKFLOW_RUN_ID"' in workflow
    )
    assert (
        '--product-state-workflow-run-number "$PRODUCT_STATE_WORKFLOW_RUN_NUMBER"'
        in workflow
    )
    assert (
        "--product-state-workflow-run-attempt "
        '"$PRODUCT_STATE_WORKFLOW_RUN_ATTEMPT"' in workflow
    )
    assert "--verify-legacy-git-objects" in workflow
    assert 'payload["source_commit_sha"] == source_sha' in workflow
    assert 'payload["observed_github_main_sha"] == observed_main_sha' in workflow
    assert "if source_sha != observed_main_sha:" in workflow
    assert 'payload["quality_evidence"]["status"] == "invalid"' in workflow
    assert 'payload["quality_evidence"]["status"] == "available"' in workflow
    assert '"source_commit_does_not_match_observed_github_main"' in workflow
    assert '"nightly_full_quality_evidence_invalid:head_sha"' in workflow
    assert 'payload["quality_evidence"]["conclusion"] == conclusion' in workflow
    assert 'elif conclusion == "success":' in workflow
    assert 'payload["contract_pass"] is True' in workflow
    assert 'payload["contract_pass"] is False' in workflow
    assert 'f"nightly_full_quality_not_success:{conclusion}"' in workflow
    assert "continue-on-error: true" in workflow
    assert '--write-state "$DAG_STATE_PATH"' in workflow
    assert '--report "$DAG_REPORT_PATH"' in workflow
    assert 'cat "$DAG_REPORT_PATH"' in workflow
    assert (
        '--product-state-nightly-event "$NIGHTLY_WORKFLOW_RUN_EVENT_PATH"' in workflow
    )
    assert "--allow-missing" not in workflow
    assert "canonical/generated-artifact-dag-state.v2.schema.json" in workflow
    assert "canonical/generated-artifact-dag-report.v2.schema.json" in workflow
    assert 'report["contract_pass"] is True' in workflow
    assert 'report["stale_nodes"] == []' in workflow
    assert 'row["current_binding"]["status"] == "current"' in workflow
    assert 'payload["release_authority"] is False' in workflow
    assert 'git_object_verification"] == "passed"' in workflow
    assert "actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803" in workflow
    assert "actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1" in workflow
    assert "actions/attest@508db95dd578ae2727ebd6217d5ba78e4fbda05d" in workflow
    assert (
        "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a" in workflow
    )
    assert "actions/checkout@v" not in workflow
    assert "actions/setup-python@v" not in workflow
    assert "actions/attest@v" not in workflow
    assert "actions/upload-artifact@v" not in workflow
    assert "product-state.current.sigstore.json" in workflow
    assert "scripts/build_product_state_provenance_bundle.py" in workflow
    assert '--source-sha "$PRODUCT_STATE_SHA"' in workflow
    assert '--product-state "$PRODUCT_STATE_PATH"' in workflow
    assert '--canonical-receipt "$CANONICAL_RECEIPT_PATH"' in workflow
    assert '--canonical-wheel-contract "$CANONICAL_WHEEL_CONTRACT_PATH"' in workflow
    assert '--canonical-wheel "$CANONICAL_WHEEL_PATH"' in workflow
    assert '--dag-state "$DAG_STATE_PATH"' in workflow
    assert '--dag-report "$DAG_REPORT_PATH"' in workflow
    assert "canonical-verification-workflow-run.json" in workflow
    assert "product-state.provenance-bundle.v1.json" in workflow
    assert (
        workflow.count("actions/attest@508db95dd578ae2727ebd6217d5ba78e4fbda05d") == 3
    )
    assert "steps.attest_provenance.outputs.bundle-path" in workflow
    assert "steps.attest_state.outputs.bundle-path" in workflow
    assert (
        workflow.index("id: attest_state")
        < workflow.index("id: attest_provenance")
        < workflow.index("id: attest_candidate_seal")
    )
    assert "product-state.provenance-bundle.sigstore.json" in workflow
    assert "product-state.provenance-bundle.attestation-verification.json" in workflow
    assert workflow.count(".github/workflows/product-state-current.yml") >= 5
    assert workflow.count("gh attestation verify") >= 5
    assert workflow.count('--signer-digest "$PRODUCT_STATE_SHA"') >= 3
    assert workflow.count('--source-digest "$PRODUCT_STATE_SHA"') >= 5
    assert workflow.count("--source-ref refs/heads/main") >= 5
    assert "canonical/product-state.current.v1.schema.json" in workflow
    assert "jsonschema.Draft202012Validator.check_schema(schema)" in workflow
    assert 'test "$current_main_sha" = "$PRODUCT_STATE_SHA"' in workflow
    assert workflow.index("Validate current product-state schema") < workflow.index(
        "Verify current-main binding, outcome, and bounded authority"
    )
    assert workflow.index(
        "Confirm main observation is stable before candidate handoff"
    ) < (workflow.index("  attest-current-state:"))
    assert workflow.count("include-hidden-files: true") == 3
    assert "retention-days: 90" in workflow


@pytest.mark.parametrize(
    ("original", "replacement"),
    [
        (
            "python scripts/verify_canonical_actions_artifact.py select",
            "python scripts/unverified_artifact_download.py select",
        ),
        (
            'actions/artifacts/$canonical_artifact_id"',
            'actions/artifacts/$unbound_artifact_id"',
        ),
        (
            "actions/artifacts/$canonical_artifact_id/zip",
            "actions/artifacts/$unbound_artifact_id/zip",
        ),
        (
            "--archive .ci/canonical-receipt-download/canonical-artifact.zip",
            "--archive .ci/canonical-receipt-download/unverified-artifact.zip",
        ),
        (
            '--api-url "$GITHUB_API_URL"',
            '--api-url "$UNBOUND_API_URL"',
        ),
        (
            "python scripts/verify_canonical_actions_artifact.py admit",
            "python scripts/unverified_artifact_download.py admit",
        ),
        (
            "python scripts/verify_tracked_source_tree.py \\\n"
            '            --repo-root . --source-sha "$PRODUCT_STATE_SHA" --profile consumer',
            "true",
        ),
        (
            '              ".ci/product-state-inputs/canonical-actions-artifact-identity.json",',
            "",
        ),
        (
            "python scripts/verify_canonical_actions_artifact.py replay",
            "python scripts/unverified_artifact_download.py replay",
        ),
    ],
    ids=[
        "selection-bypass",
        "metadata-id-drift",
        "archive-id-drift",
        "archive-path-drift",
        "api-authority-drift",
        "admission-bypass",
        "source-admission-bypass",
        "sealed-identity-omitted",
        "replay-bypass",
    ],
)
def test_product_state_rejects_unbound_canonical_artifact_wiring(
    original: str,
    replacement: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = Path(".github/workflows/product-state-current.yml")
    workflow = (ROOT / path).read_text(encoding="utf-8")
    assert original in workflow
    mutated = workflow.replace(original, replacement, 1)
    # A copy outside the actual step must not satisfy the scoped wiring checks.
    decoy = "\n".join(f"# {line}" for line in original.splitlines())
    target = tmp_path / path
    target.parent.mkdir(parents=True)
    target.write_text(mutated + "\n" + decoy + "\n", encoding="utf-8")
    monkeypatch.setattr(sys.modules[__name__], "ROOT", tmp_path)
    with pytest.raises(AssertionError):
        test_current_product_state_records_every_completed_main_nightly_outcome()


def test_product_state_privileged_authority_binding_rejects_byte_transplants() -> None:
    workflow = (ROOT / ".github" / "workflows" / "product-state-current.yml").read_text(
        encoding="utf-8"
    )
    policy_path = "canonical/product-authority-profiles.v1.json"
    schema_path = "canonical/product-authority-profiles.v1.schema.json"

    assert (
        f"repos/$GITHUB_REPOSITORY/contents/{policy_path}?ref=$PRODUCT_STATE_SHA"
        in workflow
    )
    assert (
        f"repos/$GITHUB_REPOSITORY/contents/{schema_path}?ref=$PRODUCT_STATE_SHA"
        in workflow
    )
    assert (
        'source_file(load((temp / "product-authority-policy-content.json").read_bytes(), '
        '"product_authority_policy_api"), product_authority_policy_path, '
        "files[product_authority_policy_path])" in workflow
    )
    assert (
        "source_schema_raw[schema_path] = source_file(load((temp / "
        "api_name).read_bytes(), api_name), schema_path, files[schema_path])"
        in workflow
    )
    assert (
        '("product-authority-schema-content.json", '
        '"canonical/product-authority-profiles.v1.schema.json")' in workflow
    )
    assert 'product_authority_binding.get("sha256") != digest(' in workflow
    assert 'product_authority_binding.get("schema_sha256") != digest(' in workflow
    assert "load_product_authority_policy(product_authority_policy_raw)" in workflow

    helper_start = workflow.index("          def fail(reason):")
    helper_end = workflow.index(
        "          def load_authority_policy(raw):", helper_start
    )
    policy_start = workflow.index(
        "          def load_product_authority_schema(raw):", helper_end
    )
    policy_end = workflow.index("          def canonical_authority_key", policy_start)
    privileged_source = textwrap.dedent(
        workflow[helper_start:helper_end] + workflow[policy_start:policy_end]
    )
    namespace = {
        "base64": base64,
        "hashlib": hashlib,
        "json": json,
        "math": math,
    }
    exec(privileged_source, namespace)

    raw = (ROOT / policy_path).read_bytes()
    blob_sha = hashlib.sha1(
        b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw
    ).hexdigest()
    api_payload = {
        "type": "file",
        "path": policy_path,
        "encoding": "base64",
        "content": base64.b64encode(raw).decode("ascii"),
        "size": len(raw),
        "sha": blob_sha,
    }
    source_file = namespace["source_file"]
    load_schema = namespace["load_product_authority_schema"]
    load_policy = namespace["load_product_authority_policy"]
    assert source_file(api_payload, policy_path, raw) == raw
    assert load_policy(raw)["policy_id"] == (
        "frame-alpha-product-authority-separation.v1"
    )

    with pytest.raises(SystemExit, match="source_file_bytes_invalid"):
        source_file(api_payload, policy_path, raw + b"\n")

    schema_raw = (ROOT / schema_path).read_bytes()
    schema_blob_sha = hashlib.sha1(
        b"blob " + str(len(schema_raw)).encode("ascii") + b"\0" + schema_raw
    ).hexdigest()
    schema_api_payload = {
        "type": "file",
        "path": schema_path,
        "encoding": "base64",
        "content": base64.b64encode(schema_raw).decode("ascii"),
        "size": len(schema_raw),
        "sha": schema_blob_sha,
    }
    assert source_file(schema_api_payload, schema_path, schema_raw) == schema_raw
    assert load_schema(schema_raw)["$schema"] == (
        "https://json-schema.org/draft/2020-12/schema"
    )
    with pytest.raises(SystemExit, match="source_file_bytes_invalid"):
        source_file(schema_api_payload, schema_path, schema_raw + b"\n")

    weakened_schema = json.loads(schema_raw)
    weakened_schema["$defs"]["g1Track"]["allOf"][1]["properties"]["status"] = {
        "type": "string"
    }
    with pytest.raises(
        SystemExit,
        match="product_authority_schema_exact_contract_invalid",
    ):
        load_schema(json.dumps(weakened_schema).encode("utf-8"))

    promoted = json.loads(raw)
    promoted["non_authoritative_tracks"][0]["status"] = "closed"
    with pytest.raises(
        SystemExit,
        match="product_authority_policy_exact_contract_invalid",
    ):
        load_policy(json.dumps(promoted).encode("utf-8"))

    duplicate = raw.replace(
        b'"schema_version": "product-authority-profiles.v1",',
        b'"schema_version": "ignored", '
        b'"schema_version": "product-authority-profiles.v1",',
        1,
    )
    with pytest.raises(SystemExit, match="duplicate_json_key:schema_version"):
        load_policy(duplicate)


def test_profile_scoped_state_uses_the_bounded_authority_loader_dependency() -> None:
    workflow = (
        ROOT / ".github" / "workflows" / "profile-scoped-product-state.yml"
    ).read_text(encoding="utf-8")

    for path in (
        "scripts/build_profile_scoped_product_states.py",
        "scripts/product_authority_policy.py",
        "scripts/strict_json.py",
        "canonical/product-authority-profiles.v1.json",
        "canonical/product-authority-profiles.v1.schema.json",
    ):
        assert workflow.count(f'- "{path}"') == 2
    assert "scripts/build_product_state.py" not in workflow
    assert "pytest==8.4.2 jsonschema==4.26.0" in workflow
    assert "python scripts/build_profile_scoped_product_states.py" in workflow


def test_product_state_reverifies_all_exact_sha_supplemental_attestations() -> None:
    workflow = (ROOT / ".github" / "workflows" / "product-state-current.yml").read_text(
        encoding="utf-8"
    )
    step = workflow.split(
        "- name: Download and reverify exact-SHA supplemental technical attestations",
        1,
    )[1].split(
        "- name: Retain bounded supplemental consumer diagnostics",
        1,
    )[0]

    for path in (
        ".github/workflows/bounded-planar-opensees-technical.yml",
        ".github/workflows/bounded-planar-negative-opensees-technical.yml",
        ".github/workflows/bounded-planar-scaling-opensees-technical.yml",
        ".github/workflows/bounded-planar-modal-buckling-technical.yml",
        ".github/workflows/bounded-planar-nonlinear-material-recovery-technical.yml",
    ):
        assert step.count(path) == 1
    assert "status=success&head_sha=$PRODUCT_STATE_SHA" in step
    assert 'row.get("head_sha") == os.environ["PRODUCT_STATE_SHA"]' in step
    assert 'row.get("head_branch") == "main"' in step
    assert 'row.get("conclusion") == "success"' in step
    assert "type(run_id) is not int" in step
    assert "type(run_attempt) is not int" in step
    assert "for lookup_attempt in {1..30}" in step
    assert "gh run download" not in step
    assert "python scripts/consume_supplemental_artifact.py" in step
    for argument in (
        '--repository "$GITHUB_REPOSITORY"',
        '--source-sha "$PRODUCT_STATE_SHA"',
        '--run-id "$run_id"',
        '--run-attempt "$run_attempt"',
        '--family "$family"',
        '--run-json "$family_root/workflow-run.json"',
        '--inventory-json "$family_root/artifacts.json"',
        '--target "$artifact_root"',
        '--diagnostic "$transport_diagnostic_dir/$family.json"',
    ):
        assert argument in step
    assert 'mkdir -p "$family_root"' in step
    assert 'mkdir -p "$artifact_root"' not in step
    assert 'mktemp -d "$RUNNER_TEMP/supplemental-consumer.XXXXXX"' in step
    assert '>> "$GITHUB_OUTPUT"' in step
    assert "mark_supplemental_unavailable" in step
    assert "workflow_run_lookup_failed_after_bounded_retry" in step
    assert "successful_exact_sha_workflow_run_missing" in step
    assert "actions/runs/$run_id/artifacts?per_page=100" in step
    assert "exact_sha_artifact_missing" in step
    assert "exact_sha_artifact_expired" in step
    assert "exact-SHA supplemental artifact consumer failed" in step
    assert 'if test "$artifact_status" != "available"; then' in step
    unavailable_branch = step.index('if test "$supplemental_available" != "true"; then')
    assert step.index("exit 0", unavailable_branch) < step.index(
        "scripts/build_bounded_planar_current_source_supplemental_attestation.py"
    )
    assert "gh attestation verify" in step
    assert (
        '--signer-workflow "$GITHUB_REPOSITORY/.github/workflows/'
        'bounded-planar-sealed-technical-attestor.yml"' in step
    )
    assert '--signer-digest "$PRODUCT_STATE_SHA"' in step
    assert '--source-digest "$PRODUCT_STATE_SHA"' in step
    assert "--source-ref refs/heads/main" in step
    assert "--deny-self-hosted-runners" in step
    assert "product-state-attestation-verification.json" in step
    assert (
        "scripts/build_bounded_planar_current_source_supplemental_attestation.py"
        in step
    )
    assert '--out "$SAME_OPERATOR_SUPPLEMENTAL_RECEIPT_PATH"' in step

    diagnostic_upload = workflow.split(
        "- name: Retain bounded supplemental consumer diagnostics", 1
    )[1].split(
        "- name: Materialize attested exact-SHA clean-runner evidence when available", 1
    )[0]
    assert (
        "always() && steps.consume_supplemental.outputs.diagnostic_dir != ''"
        in diagnostic_upload
    )
    assert (
        "path: ${{ steps.consume_supplemental.outputs.diagnostic_dir }}/*.json"
        in diagnostic_upload
    )
    assert "retention-days: 7" in diagnostic_upload
    assert "if-no-files-found: warn" in diagnostic_upload
    assert "SUPPLEMENTAL_ATTESTATION_INPUT_DIR" not in diagnostic_upload
    assert (
        "bounded-planar-supplemental-consumer-${{ github.run_id }}-${{ github.run_attempt }}"
        in diagnostic_upload
    )


def test_supplemental_workflows_upload_hidden_attestation_inputs() -> None:
    workflow_paths = (
        ".github/workflows/bounded-planar-opensees-technical.yml",
        ".github/workflows/bounded-planar-negative-opensees-technical.yml",
        ".github/workflows/bounded-planar-scaling-opensees-technical.yml",
        ".github/workflows/bounded-planar-modal-buckling-technical.yml",
        ".github/workflows/bounded-planar-nonlinear-material-recovery-technical.yml",
    )

    for relative_path in workflow_paths:
        workflow = (ROOT / relative_path).read_text(encoding="utf-8")
        assert (
            "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a"
            in workflow
        )
        assert ".ci/bounded-planar-" in workflow
        assert workflow.count("include-hidden-files: true") == 1
        assert "if-no-files-found: error" in workflow


def test_canonical_workflow_binds_receipt_to_the_checked_out_sha() -> None:
    workflow = (ROOT / ".github" / "workflows" / "p0-canonical-contract.yml").read_text(
        encoding="utf-8"
    )
    config = json.loads(
        (ROOT / "canonical/verification-environment.v1.json").read_text(
            encoding="utf-8"
        )
    )

    assert "timeout-minutes: 30" in workflow
    assert "merge_group:" in workflow
    assert "runs-on: ubuntu-latest" in workflow
    assert config["container"]["platform"] == "linux/amd64"
    assert config["python"]["abi"] == "cp312"
    assert config["dependency_lock"]["path"].endswith(
        "requirements-cp312-manylinux2014-x86_64.lock"
    )
    assert (
        f"image: {config['container']['image']}@{config['container']['digest']}"
        in workflow
    )
    source_control_probe = workflow.index("- name: Verify source-control toolchain")
    checkout = workflow.index("- name: Checkout exact source")
    assert source_control_probe < checkout
    assert "command -v git" in workflow
    assert "git --version" in workflow
    push = workflow.split("  push:", 1)[1].split("  workflow_dispatch:", 1)[0]
    assert "paths:" not in push
    assert '--source-sha "${{ github.sha }}"' in workflow
    assert "ref: ${{ github.sha }}" in workflow
    checkout_options = workflow.split(
        "uses: actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803",
        1,
    )[1].split("\n\n", 1)[0]
    assert checkout_options.count("with:") == 1
    assert "fetch-depth: 0" in checkout_options
    assert "persist-credentials: false" in checkout_options
    assert "--require-hashes" in workflow
    assert "--no-deps" in workflow
    assert "python -m pip download" in workflow
    assert "--no-index" in workflow
    assert "--force-reinstall" in workflow
    assert "--no-cache-dir" in workflow
    assert '--find-links "$CANONICAL_WHEELHOUSE"' in workflow
    assert 'git -c safe.directory="$GITHUB_WORKSPACE" rev-parse HEAD' in workflow
    assert 'git -c safe.directory="$GITHUB_WORKSPACE" show -s --format=%ct' in workflow
    assert 'test "$checkout_sha" = "$source_sha"' in workflow
    assert "''|*[!0-9]*)" in workflow
    assert 'echo "SOURCE_DATE_EPOCH=$source_date_epoch"' in workflow
    assert "git config --global" not in workflow
    assert 'echo "SOURCE_DATE_EPOCH=$(git show' not in workflow
    assert 'echo "GIT_CONFIG_COUNT=1" >> "$GITHUB_ENV"' in workflow
    assert 'echo "GIT_CONFIG_KEY_0=safe.directory" >> "$GITHUB_ENV"' in workflow
    assert 'echo "GIT_CONFIG_VALUE_0=$GITHUB_WORKSPACE" >> "$GITHUB_ENV"' in workflow
    assert "GIT_CONFIG_VALUE_0: ${{ github.workspace }}" not in workflow
    assert "scripts/build_canonical_project_wheel.py" in workflow
    assert '--source-date-epoch "$SOURCE_DATE_EPOCH"' in workflow
    assert '--wheelhouse "$CANONICAL_WHEELHOUSE"' in workflow
    assert '--project-wheel-contract "$CANONICAL_WHEEL_CONTRACT"' in workflow
    assert '--dependency-wheelhouse "$CANONICAL_WHEELHOUSE"' in workflow
    assert "canonical-project-wheel-contract.v1.schema.json" in workflow
    assert (
        'receipt["contract_profile"] == "p0-canonical-installed-wheel.v1"' in workflow
    )
    assert 'receipt["contract_pass"] is True' in workflow
    assert "--no-build-isolation -e ." not in workflow
    assert "actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803" in workflow
    assert (
        "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a" in workflow
    )
    assert "actions/checkout@v" not in workflow
    assert "actions/upload-artifact@v" not in workflow
    assert "retention-days: 90" in workflow
    assert "scripts/generate_capability_surfaces.py" in workflow
    assert (
        "artifacts/manifests/canonical_verification_environment.current.v1.json"
        in workflow
    )
    assert '--write-candidate-state "$DAG_CANDIDATE_STATE_PATH"' in workflow
    assert '--report "$DAG_CANDIDATE_REPORT_PATH"' in workflow
    assert 'report["scope_pass"] is True' in workflow
    assert 'report["contract_pass"] is False' in workflow
    assert 'report["stale_nodes"] == ["product-state"]' in workflow
    assert '["current_binding"]["status"] == "out_of_scope"' in workflow
    assert "generated-artifact-dag-candidate-${{ github.sha }}" in workflow
    assert workflow.count("include-hidden-files: true") == 2


def test_required_workflow_contexts_are_unique_and_unconditional_on_prs() -> None:
    workflows = {
        "canonical-contract": "p0-canonical-contract.yml",
        "workflow-contract": "workflow-contract-ci.yml",
        "git-lfs-integrity": "git-lfs-integrity.yml",
        "pytest-collection": "python-test-collection.yml",
        "pytest-full": "python-test-collection.yml",
    }

    for context, filename in workflows.items():
        workflow = (ROOT / ".github" / "workflows" / filename).read_text(
            encoding="utf-8"
        )
        pull_request = workflow.split("  pull_request:", 1)[1].split("  push:", 1)[0]
        assert "paths:" not in pull_request
        assert "paths-ignore:" not in pull_request
        assert "merge_group:" in workflow
        assert f"name: {context}" in workflow


def test_workflow_contract_self_validates_strict_yaml_and_full_history() -> None:
    workflow = (ROOT / ".github" / "workflows" / "workflow-contract-ci.yml").read_text(
        encoding="utf-8"
    )
    checkout = workflow.split(
        "uses: actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803",
        1,
    )[1].split("\n\n", 1)[0]
    assert checkout.count("with:") == 1
    assert "fetch-depth: 0" in checkout
    assert "persist-credentials: false" in checkout

    merge_trigger = workflow.split("  merge_group:", 1)[1].split("  pull_request:", 1)[
        0
    ]
    pull_trigger = workflow.split("  pull_request:", 1)[1].split("  push:", 1)[0]
    push_trigger = workflow.split("  push:", 1)[1].split("  workflow_dispatch:", 1)[0]
    for trigger in (merge_trigger, pull_trigger, push_trigger):
        assert "paths:" not in trigger
        assert "paths-ignore:" not in trigger
    assert "types: [checks_requested]" in merge_trigger

    ancestry = workflow.split(
        "- name: Verify local direct and nested merge-parent ancestry", 1
    )[1].split("- name: Set up Python", 1)[0]
    assert "git fetch" not in ancestry
    assert " origin " not in ancestry
    assert "github.token" not in ancestry
    assert "GITHUB_TOKEN" not in ancestry
    assert "git cat-file -p HEAD" in ancestry
    assert 'git cat-file -e "${parent}^{commit}"' in ancestry
    assert 'git cat-file -p "$parent"' in ancestry
    assert 'git cat-file -e "${nested_parent}^{commit}"' in ancestry

    assert "yaml.safe_load" not in workflow
    assert "class StrictWorkflowLoader(yaml.SafeLoader)" in workflow
    assert "path.lstat()" in workflow
    assert "path.is_symlink()" in workflow
    assert "workflow_root.rglob('*.yml')" in workflow
    assert "workflow_root.rglob('*.yaml')" in workflow
    assert "found duplicate key" in workflow
    assert workflow.count("tests/test_repository_python_workflow_contract.py") == 1
    assert workflow.count("tests/test_workflow_yaml_strict.py") == 1


def test_pytest_full_aggregate_is_unique_and_covers_every_shard() -> None:
    workflow = (
        ROOT / ".github" / "workflows" / "python-test-collection.yml"
    ).read_text(encoding="utf-8")

    assert workflow.count("    name: pytest-full\n") == 1
    assert workflow.count("  full_shards:\n") == 1
    assert workflow.count("  full:\n") == 1
    assert "needs: full_shards" in workflow.split("  full:\n", 1)[1]
    assert "FULL_SHARDS_RESULT: ${{ needs.full_shards.result }}" in workflow


def test_development_contracts_remain_independent_without_replacing_full_gate():
    import shlex
    import yaml

    workflow = yaml.load(
        (ROOT / ".github/workflows/python-test-collection.yml").read_text(),
        Loader=yaml.BaseLoader,
    )
    jobs = workflow["jobs"]
    diagnostic = jobs["development_contracts"]
    assert diagnostic["name"] == "pytest-development-contracts"
    assert diagnostic["timeout-minutes"] == "45"
    assert "needs" not in diagnostic and "if" not in diagnostic
    assert "continue-on-error" not in diagnostic
    assert workflow["permissions"] == {"contents": "read"}
    assert all("continue-on-error" not in step for step in diagnostic["steps"])
    commands = [step["run"] for step in diagnostic["steps"] if "run" in step]
    assert len(commands) == 2
    tests = shlex.split(commands[1])
    assert tests[:3] == ["python", "-m", "pytest"]
    assert "--junitxml=development-contracts.xml" in tests
    assert not any(x in tests for x in ("-k", "--deselect", "--ignore"))
    selected_paths = [x for x in tests if x.startswith("tests/")]
    selected = set(selected_paths)
    assert len(selected_paths) == len(selected), (
        "duplicate development module selection"
    )
    assert len(selected) == 84
    assert all((ROOT / path).is_file() for path in selected)
    assert {
        "tests/test_stateful_fiber_section.py",
        "tests/test_public_rc_fiber_frame_api.py",
        "tests/test_fiber_frame_design.py",
        "tests/test_fiber_frame_physical_identity.py",
        "tests/test_fiber_frame_candidate_learning.py",
        "tests/test_bounded_planar_model_ir_adapter.py",
        "tests/test_model_ir_v2_contract.py",
        "tests/test_fiber_frame_candidate_search.py",
        "tests/test_fiber_frame_candidate_cost.py",
        "tests/test_fiber_frame_candidate_search_suite.py",
        "tests/test_bounded_rc_fiber_direct_control_api.py",
        "tests/test_nonlinear_failure_diagnostic.py",
        "tests/test_durable_failure_diagnostics.py",
        "tests/test_durable_job_service.py",
        "tests/test_rc_control_runtime_selection.py",
        "tests/test_rc_runtime_cost_diagnostic.py",
        "tests/test_rc_control_initial_residual.py",
        "tests/test_rc_control_trust_region.py",
        "tests/test_rc_recovery_configuration.py",
        "tests/test_rc_replay_streaming.py",
        "tests/test_rc_branch_diagnostic.py",
        "tests/test_rc_recovery_followup.py",
        "tests/test_rc_adaptive_continuation_campaign.py",
        "tests/test_rc_adaptive_campaign_audit.py",
        "tests/test_rc_internal_portal_20mm_comparison.py",
        "tests/test_audit_rc_internal_portal_20mm_comparison.py",
        "tests/test_rc_offline_cost_tree.py",
        "tests/test_rc_scalar_runtime_equivalence.py",
        "tests/test_rc_same_parent_probe_records.py",
        "tests/test_planar_steel_refinement_witness_audit.py",
        "tests/test_planar_concrete_localization_audit.py",
        "tests/test_planar_1024_witness_probe.py",
        "tests/test_planar_2048_witness_probe.py",
        "tests/test_planar_4096_refinement_driver.py",
        "tests/test_extract_planar_2048_features.py",
        "tests/test_audit_planar_4096_refinement.py",
        "tests/test_planar_path_artifact_writer.py",
        "tests/test_planar_path_artifact_reader.py",
        "tests/test_planar_material_activity.py",
        "tests/test_rc_control_step_work.py",
        "tests/test_rc_control_iteration_cost.py",
        "tests/test_newton_assembly_work.py",
        "tests/test_rc_control_assembly_work.py",
        "tests/test_rc_control_assembly_phases.py",
        "tests/test_rc_quadratic_seed.py",
        "tests/test_rc_native_assembly_reuse.py",
        "tests/test_rc_line_search_reuse_experiment.py",
        "tests/test_rc_reuse_campaign.py",
        "tests/test_rc_control_search_accounting.py",
        "tests/test_rc_control_strategy_costs.py",
        "tests/test_rc_control_process_costs.py",
        "tests/test_rc_control_layout_features.py",
        "tests/test_rc_control_layout_dataset.py",
        "tests/test_rc_control_layout_labels.py",
        "tests/test_rc_control_layout_learning.py",
        "tests/test_rc_control_layout_search.py",
        "tests/test_rc_layout_search_http.py",
        "tests/test_rc_layout_staged_http.py",
        "tests/test_rc_strategy_cohort.py",
        "tests/test_repository_python_workflow_contract.py",
        "tests/test_rc_constant_load_durable.py",
        "tests/test_rc_control_parent_step.py",
        "tests/test_rc_control_cost_pruned_design.py",
        "tests/test_rc_control_reinforcement_learning.py",
        "tests/test_rc_control_candidate_search.py",
        "tests/test_rc_control_candidate_cost.py",
        "tests/test_rc_control_cost_dominance.py",
        "tests/test_measured_response_split.py",
        "tests/test_aci_column_archive.py",
        "tests/test_pinned_opensees_runtime.py",
        "tests/test_external_reference_output_capture.py",
        "tests/test_external_product_replay_identity.py",
        "tests/test_local_source_reference_comparison.py",
    } <= selected
    assert all(
        "materializ" not in cmd and "--refresh-product-replay" not in cmd
        for cmd in commands
    )
    upload = diagnostic["steps"][-1]
    assert upload["if"] == "${{ always() }}"
    assert upload["with"]["path"] == "development-contracts.xml"
    # A successful diagnostic cannot mask failed, cancelled or skipped shards.
    full = jobs["full"]
    assert full["needs"] == "full_shards"
    assert full["if"] == "${{ always() }}"
    assert full["steps"][0]["run"] == 'test "$FULL_SHARDS_RESULT" = "success"'
    assert (
        full["steps"][0]["env"]["FULL_SHARDS_RESULT"]
        == "${{ needs.full_shards.result }}"
    )
    assert "continue-on-error" not in jobs["full_shards"]
