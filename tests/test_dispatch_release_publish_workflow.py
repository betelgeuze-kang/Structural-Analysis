from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
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
    assert plan["token"]["gh_auth_fallback_allowed"] is False
    assert plan["required_publication_evidence"]["post_publish_roundtrip_json"] == (
        "structural-post-publish-roundtrip.json"
    )
    assert any(
        "--post-publish-roundtrip-json" in command
        for command in plan["required_publication_evidence"]["validation_commands"]
    )


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
    assert plan["token"]["env"] == "GITHUB_TOKEN"
    assert plan["token"]["resolved_env"] == "GITHUB_TOKEN"
    assert plan["token"]["available"] is True
    assert plan["token"]["gh_auth_fallback_allowed"] is False
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
    assert "--allow-gh-auth-token" in payload["error"]


def test_dispatch_plan_can_use_authenticated_gh_cli_without_serializing_token(monkeypatch) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.setattr(dispatch_release_publish_workflow, "_token_from_gh_auth", lambda: ("gh-secret", "gh-auth-token"))

    plan = dispatch_release_publish_workflow.build_dispatch_plan(
        ref="release-branch",
        replace_existing=True,
        promote_manifest=True,
        allow_gh_auth_token=True,
        dry_run=True,
    )
    serialized = json.dumps(plan, sort_keys=True)

    assert "gh-secret" not in serialized
    assert plan["token"] == {
        "env": "GITHUB_TOKEN",
        "resolved_env": "gh-auth-token",
        "available": True,
        "gh_auth_fallback_allowed": True,
    }
    assert plan["request"]["payload"] == {
        "ref": "release-branch",
        "inputs": {
            "replace_existing": "true",
            "promote_manifest": "true",
        },
    }


def test_gh_auth_token_fallback_supports_older_status_show_token(monkeypatch) -> None:
    calls = []

    def fake_run(command, check, capture_output, text, timeout):
        calls.append(command)
        if command == ["gh", "auth", "token"]:
            return subprocess.CompletedProcess(command, 1, stdout="", stderr='unknown command "token"')
        return subprocess.CompletedProcess(
            command,
            0,
            stdout="",
            stderr="github.com\n  ✓ Token: ghp_status_secret\n",
        )

    monkeypatch.setattr(dispatch_release_publish_workflow.subprocess, "run", fake_run)

    token, source = dispatch_release_publish_workflow._token_from_gh_auth()

    assert token == "ghp_status_secret"
    assert source == "gh-auth-status"
    assert calls == [
        ["gh", "auth", "token"],
        ["gh", "auth", "status", "--hostname", "github.com", "--show-token"],
    ]


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


def test_dispatch_success_can_use_gh_cli_token_fallback(monkeypatch) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.setattr(dispatch_release_publish_workflow, "_token_from_gh_auth", lambda: ("gh-secret", "gh-auth-token"))
    requests = []

    def fake_urlopen(request, timeout):
        requests.append(request)
        return _Response(status=204)

    result = dispatch_release_publish_workflow.dispatch_workflow(
        repo="acme/widgets",
        workflow="ship.yml",
        ref="release",
        replace_existing=True,
        promote_manifest=True,
        allow_gh_auth_token=True,
        urlopen=fake_urlopen,
    )

    assert result["ok"] is True
    assert result["token"]["resolved_env"] == "gh-auth-token"
    assert dict(requests[0].header_items())["Authorization"] == "Bearer gh-secret"


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
