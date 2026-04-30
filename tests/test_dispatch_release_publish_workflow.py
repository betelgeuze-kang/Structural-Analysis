from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from urllib.error import HTTPError

import pytest


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "dispatch_release_publish_workflow.py"
SPEC = importlib.util.spec_from_file_location("dispatch_release_publish_workflow", SCRIPT_PATH)
assert SPEC is not None
dispatch_release_publish_workflow = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(dispatch_release_publish_workflow)


class _Response:
    def __init__(self, status: int = 204, payload: bytes = b"") -> None:
        self.status = status
        self._payload = payload

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def read(self) -> bytes:
        return self._payload


class _ErrorBody:
    def read(self) -> bytes:
        return b'{"message":"workflow not found"}'

    def close(self) -> None:
        return None


def test_dry_run_writes_dispatch_plan_without_token(tmp_path: Path, monkeypatch, capsys) -> None:
    out_path = tmp_path / "dispatch-plan.json"
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)

    exit_code = dispatch_release_publish_workflow.main(
        [
            "--dry-run",
            "--json",
            "--out",
            str(out_path),
            "--replace-existing",
            "--no-promote-manifest",
        ]
    )

    assert exit_code == 0
    plan = json.loads(out_path.read_text(encoding="utf-8"))
    assert json.loads(capsys.readouterr().out) == plan
    assert plan["ok"] is True
    assert plan["dry_run"] is True
    assert plan["request"]["method"] == "POST"
    assert plan["request"]["url"].endswith(
        "/repos/betelgeuze-kang/Structural-Analysis/actions/workflows/release-publish.yml/dispatches"
    )
    assert plan["request"]["payload"] == {
        "ref": "main",
        "inputs": {
            "replace_existing": "true",
            "promote_manifest": "false",
        },
    }
    assert plan["token"]["available"] is False
    assert plan["token"]["env"] == "GITHUB_TOKEN"


def test_dispatch_plan_encodes_urls_and_never_serializes_token(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "super-secret-token")

    plan = dispatch_release_publish_workflow.build_dispatch_plan(
        repo="acme/widgets",
        workflow="release publish.yml",
        ref="release/2026 q2",
        replace_existing=False,
        promote_manifest=True,
        dry_run=True,
    )
    serialized = json.dumps(plan, sort_keys=True)

    assert "super-secret-token" not in serialized
    assert plan["token"] == {
        "env": "GITHUB_TOKEN",
        "resolved_env": "GITHUB_TOKEN",
        "available": True,
    }
    assert plan["request"]["url"].endswith("/actions/workflows/release%20publish.yml/dispatches")
    assert plan["status_check"]["url"].endswith(
        "/actions/workflows/release%20publish.yml/runs?branch=release%2F2026%20q2&per_page=5"
    )
    assert plan["request"]["payload"]["inputs"]["promote_manifest"] == "true"


def test_missing_token_returns_exit_code_2_before_network(monkeypatch, capsys) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)

    exit_code = dispatch_release_publish_workflow.main(["--json"])

    assert exit_code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert "Missing GitHub token" in payload["error"]
    assert "GITHUB_TOKEN" in payload["error"]
    assert "GH_TOKEN" in payload["error"]


def test_dispatch_success_204_sends_boolean_inputs_as_strings(monkeypatch) -> None:
    monkeypatch.setenv("CUSTOM_TOKEN", "secret")
    requests = []

    def fake_urlopen(request, timeout):
        requests.append(request)
        assert timeout == dispatch_release_publish_workflow.DEFAULT_TIMEOUT_SECONDS
        return _Response(status=204)

    result = dispatch_release_publish_workflow.dispatch_workflow(
        repo="acme/widgets",
        workflow="ship.yml",
        ref="release",
        replace_existing=True,
        promote_manifest=False,
        token_env="CUSTOM_TOKEN",
        urlopen=fake_urlopen,
    )

    assert result["ok"] is True
    assert result["status"] == 204
    assert len(requests) == 1
    request = requests[0]
    assert request.get_method() == "POST"
    assert request.full_url.endswith("/repos/acme/widgets/actions/workflows/ship.yml/dispatches")
    assert dict(request.header_items())["Authorization"] == "Bearer secret"
    assert json.loads(request.data.decode("utf-8")) == {
        "ref": "release",
        "inputs": {
            "replace_existing": "true",
            "promote_manifest": "false",
        },
    }


def test_dispatch_failure_includes_status_and_body(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "secret")

    def fake_urlopen(request, timeout):
        raise HTTPError(
            request.full_url,
            404,
            "Not Found",
            hdrs=None,
            fp=_ErrorBody(),
        )

    with pytest.raises(
        dispatch_release_publish_workflow.WorkflowDispatchError,
        match=r"HTTP 404.*workflow not found",
    ):
        dispatch_release_publish_workflow.dispatch_workflow(
            repo="acme/widgets",
            workflow="missing.yml",
            ref="main",
            urlopen=fake_urlopen,
        )


def test_status_check_reads_recent_workflow_runs(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "secret")
    requests = []

    def fake_urlopen(request, timeout):
        requests.append(request)
        assert timeout == dispatch_release_publish_workflow.DEFAULT_TIMEOUT_SECONDS
        return _Response(
            status=200,
            payload=json.dumps(
                {
                    "workflow_runs": [
                        {
                            "id": 123,
                            "status": "completed",
                            "conclusion": "success",
                            "html_url": "https://github.com/acme/widgets/actions/runs/123",
                        }
                    ]
                }
            ).encode("utf-8"),
        )

    result = dispatch_release_publish_workflow.check_workflow_status(
        repo="acme/widgets",
        workflow="ship.yml",
        ref="main",
        urlopen=fake_urlopen,
    )

    assert result["ok"] is True
    assert result["status"] == 200
    assert result["workflow_runs"] == [
        {
            "id": 123,
            "status": "completed",
            "conclusion": "success",
            "html_url": "https://github.com/acme/widgets/actions/runs/123",
        }
    ]
    assert requests[0].get_method() == "GET"
    assert requests[0].full_url.endswith("/actions/workflows/ship.yml/runs?branch=main&per_page=5")


def test_status_check_failure_includes_status_and_body(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "secret")

    def fake_urlopen(request, timeout):
        raise HTTPError(
            request.full_url,
            403,
            "Forbidden",
            hdrs=None,
            fp=_ErrorBody(),
        )

    with pytest.raises(
        dispatch_release_publish_workflow.WorkflowDispatchError,
        match=r"HTTP 403.*workflow not found",
    ):
        dispatch_release_publish_workflow.check_workflow_status(
            repo="acme/widgets",
            workflow="ship.yml",
            ref="main",
            urlopen=fake_urlopen,
        )
