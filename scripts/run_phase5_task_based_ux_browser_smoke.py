#!/usr/bin/env python3
"""Run the Phase 5 task-based browser smoke and write an execution receipt."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
for candidate in (SCRIPT_DIR, SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from release_evidence_metadata import git_head, input_checksums  # noqa: E402
from structural_analysis import ANALYSIS_ENGINE_VERSION, CLAIM_BOUNDARY_VERSION  # noqa: E402


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_OUT = PRODUCTIZATION / "phase5_task_based_ux_browser_execution_receipt.json"
TASK_BASED_UX_TEST = Path("tests/frontend/developer-preview-workflow.spec.ts")
APP_SURFACE = Path("src/App.tsx")
WORKFLOW_PANEL = Path("src/workbench/DeveloperPreviewWorkflowPanel.tsx")
WORKFLOW_MODEL = Path("src/workbench/developerPreviewWorkflow.ts")
WORKFLOW_STATE_MODEL = Path("src/workbench/developerPreviewWorkflowState.ts")
WORKFLOW_WORKER = Path("src/workbench/developerPreviewWorkflow.worker.ts")

WORKFLOW_STEPS = [
    "import",
    "model_health",
    "analysis_setup",
    "run_monitor",
    "compare_report",
]
BASE_URL = "http://127.0.0.1:4173"
BUILD_CMD = ["npm", "run", "build"]
PREVIEW_CMD = ["npm", "run", "preview", "--", "--host", "127.0.0.1", "--port", "4173"]
PLAYWRIGHT_CMD = ["npx", "playwright", "test", TASK_BASED_UX_TEST.as_posix()]
INPUTS = (
    APP_SURFACE,
    WORKFLOW_PANEL,
    WORKFLOW_MODEL,
    WORKFLOW_STATE_MODEL,
    WORKFLOW_WORKER,
    TASK_BASED_UX_TEST,
    Path("package.json"),
    Path("scripts/run_phase5_task_based_ux_browser_smoke.py"),
)


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _clip_output(value: str, *, limit: int = 2400) -> str:
    sanitized = value.replace(str(ROOT), "<repo>")
    if len(sanitized) <= limit:
        return sanitized
    return sanitized[:limit] + "\n...[truncated]"


def _completed_output(result: subprocess.CompletedProcess[str]) -> str:
    return _clip_output((result.stdout or "") + (result.stderr or ""))


def _base_payload(*, repo_root: Path = ROOT, source_commit_sha: str | None = None) -> dict[str, Any]:
    return {
        "schema_version": "phase5-task-based-ux-browser-execution.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit_sha": source_commit_sha or git_head(repo_root),
        "engine_version": ANALYSIS_ENGINE_VERSION,
        "claim_boundary_version": CLAIM_BOUNDARY_VERSION,
        "input_checksums": input_checksums(INPUTS, repo_root=repo_root),
        "base_url": BASE_URL,
        "test_path": TASK_BASED_UX_TEST.as_posix(),
        "required_workflow_steps": WORKFLOW_STEPS,
        "browser_execution_passed": False,
        "executed_workflow_steps": [],
        "blocked_workflow_steps": WORKFLOW_STEPS,
        "claim_boundary": (
            "This receipt records an actual local attempt to run the Phase 5 task-based "
            "Playwright browser smoke. It proves browser execution only when the "
            "Playwright command exits 0 against a served app."
        ),
    }


def _blocked_payload(
    *,
    repo_root: Path,
    phase: str,
    blocker: str,
    commands: dict[str, Any],
    source_commit_sha: str | None = None,
) -> dict[str, Any]:
    payload = _base_payload(repo_root=repo_root, source_commit_sha=source_commit_sha)
    payload.update(
        {
            "status": "blocked",
            "contract_pass": False,
            "failed_phase": phase,
            "blocker": blocker,
            "commands": commands,
            "summary_line": (
                "Phase 5 task-based UX browser execution: BLOCKED | "
                f"phase={phase} | blocker={blocker}"
            ),
        }
    )
    return payload


def _passed_payload(
    *,
    repo_root: Path,
    commands: dict[str, Any],
    source_commit_sha: str | None = None,
) -> dict[str, Any]:
    payload = _base_payload(repo_root=repo_root, source_commit_sha=source_commit_sha)
    payload.update(
        {
            "status": "ready",
            "contract_pass": True,
            "failed_phase": None,
            "blocker": None,
            "browser_execution_passed": True,
            "executed_workflow_steps": WORKFLOW_STEPS,
            "blocked_workflow_steps": [],
            "commands": commands,
            "summary_line": (
                "Phase 5 task-based UX browser execution: READY | "
                f"executed={len(WORKFLOW_STEPS)}/{len(WORKFLOW_STEPS)}"
            ),
        }
    )
    return payload


def run_phase5_task_based_ux_browser_smoke(
    *,
    repo_root: Path = ROOT,
    source_commit_sha: str | None = None,
    skip_build: bool = False,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    commands: dict[str, Any] = {}
    if not skip_build:
        build_result = subprocess.run(
            BUILD_CMD,
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        commands["build"] = {
            "argv": BUILD_CMD,
            "exit_code": build_result.returncode,
            "output_excerpt": _completed_output(build_result),
        }
        if build_result.returncode != 0:
            return _blocked_payload(
                repo_root=repo_root,
                source_commit_sha=source_commit_sha,
                phase="build",
                blocker="frontend_build_failed",
                commands=commands,
            )

    preview = subprocess.Popen(
        PREVIEW_CMD,
        cwd=repo_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    time.sleep(2)
    preview_output = ""
    if preview.poll() is not None:
        if preview.stdout is not None:
            preview_output = preview.stdout.read()
        commands["preview"] = {
            "argv": PREVIEW_CMD,
            "exit_code": preview.returncode,
            "output_excerpt": _clip_output(preview_output),
        }
        return _blocked_payload(
            repo_root=repo_root,
            source_commit_sha=source_commit_sha,
            phase="preview_server_start",
            blocker="preview_server_failed_before_browser_execution",
            commands=commands,
        )

    try:
        env = os.environ.copy()
        env["DEVELOPER_PREVIEW_BASE_URL"] = BASE_URL
        playwright_result = subprocess.run(
            PLAYWRIGHT_CMD,
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
            env=env,
        )
        commands["playwright"] = {
            "argv": PLAYWRIGHT_CMD,
            "exit_code": playwright_result.returncode,
            "output_excerpt": _completed_output(playwright_result),
        }
        if playwright_result.returncode != 0:
            return _blocked_payload(
                repo_root=repo_root,
                source_commit_sha=source_commit_sha,
                phase="playwright_browser_execution",
                blocker="playwright_task_based_browser_smoke_failed",
                commands=commands,
            )
        return _passed_payload(
            repo_root=repo_root,
            source_commit_sha=source_commit_sha,
            commands=commands,
        )
    finally:
        preview.terminate()
        try:
            preview.wait(timeout=5)
        except subprocess.TimeoutExpired:
            preview.kill()
            preview.wait(timeout=5)


def write_phase5_task_based_ux_browser_smoke_receipt(
    *,
    repo_root: Path = ROOT,
    out_path: Path = DEFAULT_OUT,
    source_commit_sha: str | None = None,
    skip_build: bool = False,
) -> dict[str, Any]:
    payload = run_phase5_task_based_ux_browser_smoke(
        repo_root=repo_root,
        source_commit_sha=source_commit_sha,
        skip_build=skip_build,
    )
    resolved = out_path if out_path.is_absolute() else repo_root / out_path
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(_json_text(payload), encoding="utf-8")
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--source-commit-sha", default=None)
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = write_phase5_task_based_ux_browser_smoke_receipt(
        out_path=args.out,
        source_commit_sha=args.source_commit_sha,
        skip_build=args.skip_build,
    )
    if args.json:
        print(_json_text(payload), end="")
    else:
        print(payload["summary_line"])
    return 0 if payload["contract_pass"] is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
