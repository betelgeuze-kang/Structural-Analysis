#!/usr/bin/env python3
"""Dispatch the GitHub release publication workflow safely.

The command is intentionally dry-run friendly so operators can keep an
automation-evidence JSON plan even on machines without a GitHub token.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen as urllib_urlopen


GITHUB_API = "https://api.github.com"
DEFAULT_REPO = "betelgeuze-kang/Structural-Analysis"
DEFAULT_WORKFLOW = "release-publish.yml"
DEFAULT_REF = "main"
DEFAULT_TIMEOUT_SECONDS = 60


class WorkflowDispatchError(RuntimeError):
    """Raised when workflow dispatch cannot proceed."""


class MissingTokenError(WorkflowDispatchError):
    """Raised when a live dispatch was requested without a GitHub token."""


def _repo_parts(repo: str) -> tuple[str, str]:
    parts = [part.strip() for part in repo.split("/")]
    if len(parts) != 2 or not all(parts):
        raise WorkflowDispatchError("--repo must be in owner/name format")
    return parts[0], parts[1]


def _dispatch_url(repo: str, workflow: str) -> str:
    owner, name = _repo_parts(repo)
    return (
        f"{GITHUB_API}/repos/{quote(owner, safe='')}/{quote(name, safe='')}"
        f"/actions/workflows/{quote(workflow, safe='')}/dispatches"
    )


def _runs_url(repo: str, workflow: str, ref: str) -> str:
    owner, name = _repo_parts(repo)
    workflow_part = quote(workflow, safe="")
    ref_part = quote(ref, safe="")
    return (
        f"{GITHUB_API}/repos/{quote(owner, safe='')}/{quote(name, safe='')}"
        f"/actions/workflows/{workflow_part}/runs?branch={ref_part}&per_page=5"
    )


def _bool_string(value: bool) -> str:
    return "true" if value else "false"


def _payload(ref: str, *, replace_existing: bool, promote_manifest: bool) -> dict[str, Any]:
    return {
        "ref": ref,
        "inputs": {
            "replace_existing": _bool_string(replace_existing),
            "promote_manifest": _bool_string(promote_manifest),
        },
    }


def _token_from_env(token_env: str) -> tuple[str | None, str | None]:
    token = os.environ.get(token_env)
    if token:
        return token, token_env
    if token_env == "GITHUB_TOKEN":
        fallback = os.environ.get("GH_TOKEN")
        if fallback:
            return fallback, "GH_TOKEN"
    return None, None


def _missing_token_message(token_env: str) -> str:
    if token_env == "GITHUB_TOKEN":
        return (
            "Missing GitHub token. Set GITHUB_TOKEN or GH_TOKEN, or rerun with "
            "--dry-run to write a dispatch plan without network access."
        )
    return (
        f"Missing GitHub token. Set {token_env}, or rerun with --dry-run to "
        "write a dispatch plan without network access."
    )


def build_dispatch_plan(
    *,
    repo: str = DEFAULT_REPO,
    workflow: str = DEFAULT_WORKFLOW,
    ref: str = DEFAULT_REF,
    replace_existing: bool = False,
    promote_manifest: bool = False,
    token_env: str = "GITHUB_TOKEN",
    dry_run: bool = False,
) -> dict[str, Any]:
    """Return a JSON-serializable dispatch plan without exposing token values."""

    token, resolved_env = _token_from_env(token_env)
    return {
        "ok": True,
        "dry_run": dry_run,
        "repo": repo,
        "workflow": workflow,
        "ref": ref,
        "request": {
            "method": "POST",
            "url": _dispatch_url(repo, workflow),
            "payload": _payload(
                ref,
                replace_existing=replace_existing,
                promote_manifest=promote_manifest,
            ),
        },
        "status_check": {
            "method": "GET",
            "url": _runs_url(repo, workflow, ref),
            "note": "Use after dispatch to inspect recent workflow runs for this ref.",
        },
        "token": {
            "env": token_env,
            "resolved_env": resolved_env,
            "available": token is not None,
        },
    }


def _headers(token: str) -> dict[str, str]:
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/vnd.github+json",
        "User-Agent": "arch-struct-analysis-release-workflow-dispatcher",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _read_error_body(exc: HTTPError) -> str:
    try:
        body = exc.read().decode("utf-8", errors="replace")
    except OSError:
        return ""
    return body.strip()


def _read_json_response(response: Any) -> Any:
    return json.loads(response.read().decode("utf-8"))


def dispatch_workflow(
    *,
    repo: str = DEFAULT_REPO,
    workflow: str = DEFAULT_WORKFLOW,
    ref: str = DEFAULT_REF,
    replace_existing: bool = False,
    promote_manifest: bool = False,
    token_env: str = "GITHUB_TOKEN",
    dry_run: bool = False,
    urlopen: Callable[..., Any] = urllib_urlopen,
) -> dict[str, Any]:
    """Dispatch a GitHub Actions workflow or return a dry-run plan."""

    plan = build_dispatch_plan(
        repo=repo,
        workflow=workflow,
        ref=ref,
        replace_existing=replace_existing,
        promote_manifest=promote_manifest,
        token_env=token_env,
        dry_run=dry_run,
    )
    if dry_run:
        return plan

    token, resolved_env = _token_from_env(token_env)
    if token is None:
        raise MissingTokenError(_missing_token_message(token_env))

    request = Request(
        plan["request"]["url"],
        data=json.dumps(plan["request"]["payload"]).encode("utf-8"),
        headers=_headers(token),
        method="POST",
    )
    try:
        with urlopen(request, timeout=DEFAULT_TIMEOUT_SECONDS) as response:
            status = getattr(response, "status", None) or getattr(response, "code", None)
            body = response.read().decode("utf-8", errors="replace").strip()
    except HTTPError as exc:
        body = _read_error_body(exc)
        message = f"GitHub workflow_dispatch failed: HTTP {exc.code} {exc.reason}"
        if body:
            message = f"{message}: {body}"
        raise WorkflowDispatchError(message) from exc
    except URLError as exc:
        raise WorkflowDispatchError(f"GitHub workflow_dispatch request failed: {exc.reason}") from exc

    if status != 204:
        message = f"GitHub workflow_dispatch failed: HTTP {status}"
        if body:
            message = f"{message}: {body}"
        raise WorkflowDispatchError(message)

    return {
        **plan,
        "dry_run": False,
        "status": 204,
        "token": {
            "env": token_env,
            "resolved_env": resolved_env,
            "available": True,
        },
        "message": "workflow_dispatch accepted by GitHub",
    }


def check_workflow_status(
    *,
    repo: str = DEFAULT_REPO,
    workflow: str = DEFAULT_WORKFLOW,
    ref: str = DEFAULT_REF,
    token_env: str = "GITHUB_TOKEN",
    urlopen: Callable[..., Any] = urllib_urlopen,
) -> dict[str, Any]:
    """Fetch recent workflow runs for the configured ref."""

    token, resolved_env = _token_from_env(token_env)
    if token is None:
        raise MissingTokenError(_missing_token_message(token_env))

    url = _runs_url(repo, workflow, ref)
    request = Request(url, headers=_headers(token), method="GET")
    try:
        with urlopen(request, timeout=DEFAULT_TIMEOUT_SECONDS) as response:
            status = getattr(response, "status", None) or getattr(response, "code", None)
            payload = _read_json_response(response)
    except HTTPError as exc:
        body = _read_error_body(exc)
        message = f"GitHub workflow status check failed: HTTP {exc.code} {exc.reason}"
        if body:
            message = f"{message}: {body}"
        raise WorkflowDispatchError(message) from exc
    except URLError as exc:
        raise WorkflowDispatchError(f"GitHub workflow status check failed: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise WorkflowDispatchError(f"GitHub workflow status response was not valid JSON: {exc}") from exc

    if status != 200:
        raise WorkflowDispatchError(f"GitHub workflow status check failed: HTTP {status}")
    if not isinstance(payload, dict):
        raise WorkflowDispatchError("GitHub workflow status response must be a JSON object")

    runs = payload.get("workflow_runs", [])
    if not isinstance(runs, list):
        raise WorkflowDispatchError("GitHub workflow status response workflow_runs must be a list")
    return {
        "ok": True,
        "mode": "status",
        "repo": repo,
        "workflow": workflow,
        "ref": ref,
        "status": 200,
        "request": {
            "method": "GET",
            "url": url,
        },
        "token": {
            "env": token_env,
            "resolved_env": resolved_env,
            "available": True,
        },
        "workflow_runs": runs,
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _print_payload(payload: dict[str, Any], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    if payload.get("ok"):
        if payload.get("mode") == "status":
            print(f"GitHub release publication workflow status fetched for {payload['ref']}.")
            print(f"runs={len(payload['workflow_runs'])}")
            return
        mode = "dry-run plan" if payload.get("dry_run") else "dispatch"
        print(f"GitHub release publication workflow {mode} complete.")
        print(f"repo={payload['repo']} workflow={payload['workflow']} ref={payload['ref']}")
        print(f"status_check={payload['status_check']['url']}")
        return
    print(f"ERROR: {payload['error']}", file=sys.stderr)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Dispatch the GitHub Release publication workflow.",
    )
    parser.add_argument("--repo", default=DEFAULT_REPO, help=f"GitHub repo, default: {DEFAULT_REPO}")
    parser.add_argument(
        "--workflow",
        default=DEFAULT_WORKFLOW,
        help=f"Workflow file name or id, default: {DEFAULT_WORKFLOW}",
    )
    parser.add_argument("--ref", default=DEFAULT_REF, help=f"Git ref to dispatch, default: {DEFAULT_REF}")
    parser.add_argument(
        "--replace-existing",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Send inputs.replace_existing as true/false.",
    )
    parser.add_argument(
        "--promote-manifest",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Send inputs.promote_manifest as true/false.",
    )
    parser.add_argument(
        "--token-env",
        default="GITHUB_TOKEN",
        help="Environment variable containing the GitHub token. GITHUB_TOKEN falls back to GH_TOKEN.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print/write the request plan without network calls.")
    parser.add_argument("--status", action="store_true", help="Fetch recent workflow runs for the selected ref.")
    parser.add_argument("--json", action="store_true", help="Print JSON output for automation evidence.")
    parser.add_argument("--out", type=Path, help="Write JSON output to this path.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.status and not args.dry_run:
            payload = check_workflow_status(
                repo=args.repo,
                workflow=args.workflow,
                ref=args.ref,
                token_env=args.token_env,
            )
        else:
            payload = dispatch_workflow(
                repo=args.repo,
                workflow=args.workflow,
                ref=args.ref,
                replace_existing=args.replace_existing,
                promote_manifest=args.promote_manifest,
                token_env=args.token_env,
                dry_run=args.dry_run,
            )
    except MissingTokenError as exc:
        payload = {"ok": False, "error": str(exc)}
        if args.out:
            _write_json(args.out, payload)
        _print_payload(payload, as_json=args.json)
        return 2
    except WorkflowDispatchError as exc:
        payload = {"ok": False, "error": str(exc)}
        if args.out:
            _write_json(args.out, payload)
        _print_payload(payload, as_json=args.json)
        return 1

    if args.out:
        _write_json(args.out, payload)
    _print_payload(payload, as_json=args.json or args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
