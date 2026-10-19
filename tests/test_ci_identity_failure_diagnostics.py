"""Exercise rejection diagnostics with synthetic metadata and no CI/API execution."""

from __future__ import annotations

import ast
import copy
from datetime import datetime, timezone
from functools import lru_cache
import json
from pathlib import Path
import re
import sys
from typing import Any

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
SOURCE = "a" * 40
REPOSITORY = "example/analysis"
ERRORS = {
    "producer": "producer_job_result_invalid",
    "build": "github_build_job_completion_invalid",
    "run": "workflow_run_identity_invalid",
}
PREFIXES = {
    "producer": "producer_job_result_checks=",
    "build": "github_build_job_completion_checks=",
    "run": "workflow_run_identity_checks=",
}


@lru_cache
def _runner(kind: str):
    namespace = {
        "json": json,
        "sys": sys,
        "re": re,
        "datetime": datetime,
        "timezone": timezone,
        "Any": Any,
    }
    if kind == "run":
        path = ROOT / "scripts/verify_supplemental_artifact_identity.py"
        parsed = ast.parse(path.read_text(encoding="utf-8"))
        definitions = [
            node
            for node in parsed.body
            if (
                isinstance(node, (ast.FunctionDef, ast.ClassDef))
                and node.name
                in {"ArtifactIdentityError", "positive_integer", "verify_run"}
            )
            or (
                isinstance(node, ast.Assign)
                and any(
                    isinstance(target, ast.Name)
                    and target.id in {"SAFE_INTEGER", "FAMILIES"}
                    for target in node.targets
                )
            )
        ]
        exec(
            compile(ast.Module(body=definitions, type_ignores=[]), str(path), "exec"),
            namespace,
        )

        def run_metadata(record):
            return namespace["verify_run"](
                record, REPOSITORY, SOURCE, 901, 2, "scaling"
            )

        return run_metadata

    path, variable = {
        "producer": (
            ROOT / ".github/workflows/_technical-evidence-attest.yml",
            "producer_job_result_valid",
        ),
        "build": (
            ROOT / ".github/workflows/current-support-bundle.yml",
            "build_job_completion_valid",
        ),
    }[kind]
    workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
    scripts = [
        step["run"]
        for job in workflow["jobs"].values()
        for step in job.get("steps", [])
        if ERRORS[kind] in step.get("run", "")
    ]
    assert len(scripts) == 1
    marker = re.search(r"(?m)^.*<<'PY'\n", scripts[0])
    assert marker is not None
    parsed = ast.parse(scripts[0][marker.end() :].rsplit("\nPY", 1)[0])
    definitions = [
        node
        for node in parsed.body
        if isinstance(node, ast.FunctionDef)
        and node.name in {"fail", "require", "utc_timestamp"}
    ]
    exec(
        compile(ast.Module(body=definitions, type_ignores=[]), str(path), "exec"),
        namespace,
    )
    index = next(
        index
        for index, node in enumerate(parsed.body)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == variable
            for target in node.targets
        )
    )
    guard = compile(
        ast.Module(body=parsed.body[index : index + 3], type_ignores=[]),
        str(path),
        "exec",
    )

    def workflow_metadata(record):
        context = dict(namespace, run_id="901", run_attempt="2", source_sha=SOURCE)
        context.update(
            {"producer": record, "labels": record.get("labels")}
            if kind == "producer"
            else {"build_job": record}
        )
        exec(guard, context)

    return workflow_metadata


def _valid(kind: str) -> dict:
    common = {
        "run_id": 901,
        "head_sha": SOURCE,
        "status": "completed",
        "conclusion": "success",
    }
    if kind == "producer":
        return dict(common, labels=["ubuntu-24.04"])
    if kind == "build":
        return dict(common, id=701, run_attempt=2, completed_at="2026-10-19T16:40:00Z")
    return {
        "id": 901,
        "run_attempt": 2,
        "head_sha": SOURCE,
        "head_branch": "main",
        "path": ".github/workflows/bounded-planar-scaling-opensees-technical.yml",
        "event": "push",
        "status": "in_progress",
        "conclusion": None,
        "repository": {"id": 17, "full_name": REPOSITORY},
        "head_repository": {"id": 17, "full_name": REPOSITORY},
    }


CASES = [
    ("producer", ("run_id",), 902, "run_id_matches"),
    ("producer", ("head_sha",), "private-source", "source_matches"),
    ("producer", ("status",), "in_progress", "completed"),
    ("producer", ("conclusion",), None, "successful"),
    ("producer", ("labels",), None, "labels_list"),
    ("producer", ("labels",), "ubuntu-24.04", "labels_list"),
    ("producer", ("labels",), ["ubuntu-latest"], "hosted_label"),
    ("build", ("id",), True, "positive_job_id"),
    ("build", ("id",), None, "positive_job_id"),
    ("build", ("id",), 0, "positive_job_id"),
    ("build", ("run_id",), 902, "run_id_matches"),
    ("build", ("run_attempt",), 1, "attempt_matches"),
    ("build", ("head_sha",), "private-source", "source_matches"),
    ("build", ("status",), "in_progress", "completed"),
    ("build", ("conclusion",), None, "successful"),
    ("build", ("completed_at",), None, "completion_time_valid"),
    ("build", ("completed_at",), "invalid-date", "completion_time_valid"),
    ("run", ("repository",), None, "repository_shape"),
    ("run", ("head_repository",), [], "head_repository_shape"),
    ("run", ("repository", "full_name"), "private-repository", "repository_name"),
    (
        "run",
        ("head_repository", "full_name"),
        "private-repository",
        "head_repository_name",
    ),
    ("run", ("repository", "id"), True, "repository_id_valid"),
    ("run", ("head_repository", "id"), None, "head_repository_id_valid"),
    ("run", ("head_repository", "id"), 18, "repository_ids_match"),
    ("run", ("id",), True, "run_id_valid"),
    ("run", ("id",), 902, "run_id_matches"),
    ("run", ("run_attempt",), 0, "attempt_valid"),
    ("run", ("run_attempt",), 1, "attempt_matches"),
    ("run", ("head_sha",), "private-source", "source_matches"),
    ("run", ("head_branch",), "private-branch", "main_branch"),
    ("run", ("path",), "private-path", "workflow_path"),
    ("run", ("event",), "pull_request", "event_allowed"),
    ("run", ("status",), "queued", "status_conclusion_allowed"),
    ("run", ("conclusion",), "failure", "status_conclusion_allowed"),
]


@pytest.mark.parametrize("kind,path,value,failed_check", CASES)
def test_rejected_metadata_reports_only_bounded_boolean_checks(
    kind, path, value, failed_check, capsys
):
    record = copy.deepcopy(_valid(kind))
    marker = "SECRET_PAYLOAD_" * 5_000
    record["untrusted_extra"] = marker
    target = record
    for component in path[:-1]:
        target = target[component]
    target[path[-1]] = value
    with pytest.raises((SystemExit, ValueError)) as error:
        _runner(kind)(record)
    assert str(error.value) == ERRORS[kind]
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith(PREFIXES[kind])
    assert len(captured.err) < 1_024
    checks = json.loads(captured.err.removeprefix(PREFIXES[kind]))
    assert checks[failed_check] is False
    assert all(type(value) is bool for value in checks.values())
    assert marker not in captured.err
    assert "private-" not in captured.err


@pytest.mark.parametrize("kind", ERRORS)
def test_accepted_metadata_produces_no_rejection_diagnostic(kind, capsys):
    _runner(kind)(_valid(kind))
    captured = capsys.readouterr()
    assert captured.out == captured.err == ""


def test_completed_successful_run_is_still_accepted_without_diagnostic(capsys):
    record = _valid("run")
    record.update(status="completed", conclusion="success")
    assert _runner("run")(record) == 17
    assert capsys.readouterr().err == ""


def test_multiple_malformed_fields_preserve_the_original_rejection(capsys):
    record = _valid("run")
    record.update(repository=None, event=[])
    with pytest.raises(ValueError, match="^workflow_run_identity_invalid$"):
        _runner("run")(record)
    checks = json.loads(capsys.readouterr().err.removeprefix(PREFIXES["run"]))
    assert checks["repository_shape"] is checks["event_allowed"] is False


@pytest.mark.parametrize("kind", ERRORS)
@pytest.mark.parametrize("failure", [OSError, ValueError])
def test_unwritable_diagnostic_sink_preserves_original_error(
    kind, failure, monkeypatch
):
    class BrokenStderr:
        def write(self, value):
            raise failure("private-output-error")

    record = _valid(kind)
    record["status"] = "queued"
    with monkeypatch.context() as patch:
        patch.setattr(sys, "stderr", BrokenStderr())
        with pytest.raises((SystemExit, ValueError)) as error:
            _runner(kind)(record)
    assert str(error.value) == ERRORS[kind]
