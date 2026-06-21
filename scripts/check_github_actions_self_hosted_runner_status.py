#!/usr/bin/env python3
"""Check live/self-reported GitHub Actions self-hosted runner readiness."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any


SCHEMA_VERSION = "github-actions-self-hosted-runner-status.v1"
ENGINE_VERSION = "structural-optimization-workbench@1.0.0"
DEFAULT_REPO = "betelgeuze-kang/Structural-Analysis"
DEFAULT_OUT = Path(
    "implementation/phase1/release_evidence/productization/"
    "github_actions_self_hosted_runner_status.json"
)
DEFAULT_REQUIRED_LABELS = ("self-hosted", "linux", "x64")


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _git_head() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).resolve().parent.parent,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return ""


def _gh_env() -> dict[str, str]:
    env = os.environ.copy()
    env.pop("GH_DEBUG", None)
    return env


def _clean_message(message: str) -> str:
    return "\n".join(
        line.strip()
        for line in message.splitlines()
        if line.strip() and not line.strip().startswith("* Request")
    ) or "gh command failed"


def _labels(row: dict[str, Any]) -> list[str]:
    raw_labels = row.get("labels", [])
    labels: list[str] = []
    for label in raw_labels if isinstance(raw_labels, list) else []:
        if isinstance(label, dict):
            value = str(label.get("name", "") or "").strip()
        else:
            value = str(label).strip()
        if value:
            labels.append(value)
    return labels


def _load_runner_rows(path: Path) -> tuple[list[dict[str, Any]], str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [], f"runner evidence JSON load failed: {exc}"
    if isinstance(payload, dict):
        rows = payload.get("runners", payload.get("rows", []))
    else:
        rows = payload
    if not isinstance(rows, list):
        return [], "runner evidence JSON did not contain a runners array"
    return [row for row in rows if isinstance(row, dict)], ""


def _query_runner_rows(repo: str) -> tuple[list[dict[str, Any]], str]:
    try:
        completed = subprocess.run(
            ["gh", "api", f"repos/{repo}/actions/runners?per_page=100"],
            check=False,
            capture_output=True,
            text=True,
            env=_gh_env(),
        )
    except FileNotFoundError:
        return [], "gh CLI not found"
    if completed.returncode != 0:
        return [], _clean_message(completed.stderr or completed.stdout)
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        return [], f"gh api returned invalid JSON: {exc}"
    rows = payload.get("runners") if isinstance(payload, dict) else []
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else [], ""


def build_status(
    *,
    repo: str = DEFAULT_REPO,
    required_labels: tuple[str, ...] = DEFAULT_REQUIRED_LABELS,
    runner_rows: list[dict[str, Any]] | None = None,
    query_error: str = "",
) -> dict[str, Any]:
    required = {label.lower() for label in required_labels}
    rows: list[dict[str, Any]] = []
    for row in runner_rows or []:
        labels = _labels(row)
        label_set = {label.lower() for label in labels}
        missing_labels = sorted(required - label_set)
        status = str(row.get("status", "") or "").lower()
        busy = bool(row.get("busy"))
        matches_required_labels = not missing_labels
        online = status == "online"
        idle = not busy
        rows.append(
            {
                "id": row.get("id"),
                "name": str(row.get("name", "") or ""),
                "os": str(row.get("os", "") or ""),
                "status": status,
                "busy": busy,
                "labels": labels,
                "matches_required_labels": matches_required_labels,
                "missing_required_labels": missing_labels,
                "online": online,
                "idle": idle,
                "ready": bool(matches_required_labels and online and idle),
            }
        )
    matching = [row for row in rows if row["matches_required_labels"]]
    online_matching = [row for row in matching if row["online"]]
    ready = [row for row in online_matching if row["idle"]]
    blockers = [
        *(["github_actions_self_hosted_runner_query_failed"] if query_error else []),
        *(["self_hosted_runner_matching_labels_missing"] if not matching else []),
        *(["self_hosted_runner_matching_labels_not_online"] if matching and not online_matching else []),
        *(["self_hosted_runner_matching_labels_all_busy"] if online_matching and not ready else []),
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now_utc_iso(),
        "source_commit_sha": _git_head(),
        "engine_version": ENGINE_VERSION,
        "reused_evidence": False,
        "repo": repo,
        "required_labels": list(required_labels),
        "contract_pass": not blockers,
        "status": "ready" if not blockers else "blocked",
        "query_error": query_error,
        "runner_count": len(rows),
        "matching_runner_count": len(matching),
        "online_matching_runner_count": len(online_matching),
        "ready_runner_count": len(ready),
        "rows": rows,
        "blockers": blockers,
        "claim_boundary": (
            "This is read-only GitHub Actions self-hosted runner metadata. PASS only means "
            "at least one runner with the required labels is online and idle at collection time; "
            "it does not create CI streak evidence, mutate billing, or register a runner."
        ),
    }


def _parse_labels(value: str) -> tuple[str, ...]:
    labels = tuple(label.strip() for label in value.split(",") if label.strip())
    return labels or DEFAULT_REQUIRED_LABELS


def _strip_volatile_for_compare(payload: Any, path: tuple[str, ...] = ()) -> Any:
    if isinstance(payload, dict):
        return {
            key: _strip_volatile_for_compare(value, (*path, key))
            for key, value in payload.items()
            if key != "generated_at"
            and not (path == () and key == "source_commit_sha")
        }
    if isinstance(payload, list):
        return [_strip_volatile_for_compare(item, path) for item in payload]
    return payload


def _differing_paths(existing: Any, generated: Any, prefix: str = "") -> list[str]:
    if existing == generated:
        return []
    if isinstance(existing, dict) and isinstance(generated, dict):
        paths: list[str] = []
        for key in sorted(set(existing) | set(generated)):
            sub_prefix = f"{prefix}.{key}" if prefix else str(key)
            paths.extend(
                _differing_paths(
                    existing.get(key),
                    generated.get(key),
                    sub_prefix,
                )
            )
        return paths
    if isinstance(existing, list) and isinstance(generated, list):
        if len(existing) != len(generated):
            return [f"{prefix}.length" if prefix else "length"]
        paths: list[str] = []
        for index, (existing_item, generated_item) in enumerate(zip(existing, generated)):
            sub_prefix = f"{prefix}[{index}]" if prefix else f"[{index}]"
            paths.extend(_differing_paths(existing_item, generated_item, sub_prefix))
        return paths
    return [prefix or "<root>"]


def check_status_consistency(
    *,
    out_path: Path,
    repo: str = DEFAULT_REPO,
    required_labels: tuple[str, ...] = DEFAULT_REQUIRED_LABELS,
    runner_rows: list[dict[str, Any]] | None = None,
    query_error: str = "",
) -> tuple[bool, str, dict[str, Any] | None]:
    if not out_path.exists():
        return False, f"runner_status_missing:{out_path.as_posix()}", None
    try:
        existing = json.loads(out_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return (
            False,
            f"runner_status_unreadable:{out_path.as_posix()}:{exc.__class__.__name__}",
            None,
        )
    if not isinstance(existing, dict):
        return False, f"runner_status_invalid_object:{out_path.as_posix()}", None

    generated = build_status(
        repo=repo,
        required_labels=required_labels,
        runner_rows=runner_rows,
        query_error=query_error,
    )
    if query_error:
        return False, "runner_status_live_query_failed", generated
    existing_normalized = _strip_volatile_for_compare(existing)
    generated_normalized = _strip_volatile_for_compare(generated)
    if existing_normalized == generated_normalized:
        return True, "runner_status_consistent", generated
    differences = _differing_paths(existing_normalized, generated_normalized)
    return (
        False,
        "runner_status_semantic_mismatch:" + ",".join(differences),
        generated,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--required-labels", default=",".join(DEFAULT_REQUIRED_LABELS))
    parser.add_argument("--input-json", type=Path)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    parser.add_argument(
        "--write-query-error-evidence",
        action="store_true",
        help=(
            "Allow a live gh api query failure to overwrite an existing runner-status "
            "evidence file. The default preserves the last evidence on query failure."
        ),
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help=(
            "Non-mutating: compare the existing --out status with a freshly computed "
            "status, ignoring generated_at and the top-level source_commit_sha wrapper. "
            "Exit non-zero if the stored status is missing, unreadable, semantically "
            "stale, or blocked with --fail-blocked."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    required_labels = _parse_labels(args.required_labels)
    if args.input_json is not None:
        runner_rows, query_error = _load_runner_rows(args.input_json)
    else:
        runner_rows, query_error = _query_runner_rows(args.repo)
    if args.check:
        ok, message, generated = check_status_consistency(
            out_path=args.out,
            repo=args.repo,
            required_labels=required_labels,
            runner_rows=runner_rows,
            query_error=query_error,
        )
        if not ok:
            print(f"GitHub Actions self-hosted runner status check FAILED: {message}", file=sys.stderr)
            return 2
        if args.fail_blocked and generated is not None and not generated["contract_pass"]:
            print(
                "GitHub Actions self-hosted runner status check FAILED: runner_status_consistent_but_blocked",
                file=sys.stderr,
            )
            return 1
        if args.json and generated is not None:
            print(json.dumps(generated, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print(f"GitHub Actions self-hosted runner status check: {message}")
        return 0
    if (
        args.input_json is None
        and query_error
        and args.out.exists()
        and not args.write_query_error_evidence
    ):
        print(
            "GitHub Actions self-hosted runner status: preserving existing evidence "
            f"after live query failure: {query_error}",
            file=sys.stderr,
        )
        return 2
    payload = build_status(
        repo=args.repo,
        required_labels=required_labels,
        runner_rows=runner_rows,
        query_error=query_error,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"GitHub Actions self-hosted runner status: {payload['status']}")
    return 1 if args.fail_blocked and not payload["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
