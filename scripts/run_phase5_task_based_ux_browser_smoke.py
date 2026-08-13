#!/usr/bin/env python3
"""Run the Phase 5 task-based browser smoke and write an execution receipt."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
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
NATIVE_CMD = [
    "cargo",
    "run",
    "--quiet",
    "--locked",
    "--manifest-path",
    "native/Cargo.toml",
    "-p",
    "structural-frontend-contract",
    "--",
    "phase5-task-browser-smoke",
    "--root",
    ".",
]
PLAYWRIGHT_CMD = [
    "node",
    "node_modules/@playwright/test/cli.js",
    "test",
    TASK_BASED_UX_TEST.as_posix(),
    "--reporter=line",
]
PREVIEW_LOOPBACK_BIND_BLOCKER = "preview_server_loopback_bind_permission_blocked"
PREVIEW_LOOPBACK_BIND_REASON_CODE = "listen_eperm_127_0_0_1"
NATIVE_RECEIPT_KEYS = frozenset(
    {
        "schema_version",
        "action",
        "execution_mode",
        "status",
        "source_map_sha256",
        "frontend_contract_receipt_hash",
        "build_skipped",
        "build_disposition",
        "frontend_build_receipt_hash",
        "delivery_receipt_hash",
        "specification",
        "playwright_cli_sha256",
        "playwright_command",
        "dist_directory",
        "spa_fallback_entry",
        "base_url_environment",
        "required_workflow_steps",
        "runtime_requirements",
        "loopback_listener_count",
        "loopback_port",
        "direct_processes_spawned",
        "successful_exit_codes",
        "request_error_count",
        "external_network_access_accounting",
        "deterministic_receipt",
        "claim_boundary",
        "receipt_hash",
    }
)
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


def _strict_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_nonfinite_json(value: str) -> Any:
    raise ValueError(f"non-finite JSON number: {value}")


def _json_objects_from_last_line(stdout: str) -> list[dict[str, Any]]:
    objects: list[dict[str, Any]] = []
    for line in reversed(stdout.splitlines()):
        try:
            payload = json.loads(
                line,
                object_pairs_hook=_strict_json_object,
                parse_constant=_reject_nonfinite_json,
            )
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(payload, dict):
            objects.append(payload)
    return objects


def _is_sha256_identity(value: Any) -> bool:
    text = str(value or "")
    digest = text.removeprefix("sha256:")
    return bool(
        text.startswith("sha256:")
        and len(digest) == 64
        and all(character in "0123456789abcdef" for character in digest)
    )


def _native_receipt(stdout: str, *, skip_build: bool) -> dict[str, Any]:
    for payload in _json_objects_from_last_line(stdout):
        specification = payload.get("specification")
        build_hash = payload.get("frontend_build_receipt_hash")
        expected_exit_codes = [0] if skip_build else [0, 0, 0]
        expected_process_count = 1 if skip_build else 3
        if (
            set(payload) != NATIVE_RECEIPT_KEYS
            or payload.get("schema_version")
            != "structural-native-phase5-task-browser-smoke-receipt.v1"
            or payload.get("action") != "phase5_task_browser_smoke"
            or payload.get("execution_mode") != "execute"
            or payload.get("status") != "passed"
            or payload.get("build_skipped") is not skip_build
            or payload.get("build_disposition")
            != ("skipped_existing_delivery" if skip_build else "executed")
            or (build_hash is not None if skip_build else not _is_sha256_identity(build_hash))
            or not _is_sha256_identity(payload.get("source_map_sha256"))
            or not _is_sha256_identity(payload.get("frontend_contract_receipt_hash"))
            or not _is_sha256_identity(payload.get("delivery_receipt_hash"))
            or not _is_sha256_identity(payload.get("playwright_cli_sha256"))
            or not isinstance(specification, dict)
            or set(specification) != {"path", "byte_length", "sha256"}
            or specification.get("path") != TASK_BASED_UX_TEST.as_posix()
            or not isinstance(specification.get("byte_length"), int)
            or isinstance(specification.get("byte_length"), bool)
            or int(specification["byte_length"]) <= 0
            or not _is_sha256_identity(specification.get("sha256"))
            or payload.get("playwright_command") != PLAYWRIGHT_CMD
            or payload.get("dist_directory") != "dist"
            or payload.get("spa_fallback_entry") != "index.html"
            or payload.get("base_url_environment") != "DEVELOPER_PREVIEW_BASE_URL"
            or payload.get("required_workflow_steps") != WORKFLOW_STEPS
            or payload.get("runtime_requirements")
            != {"node_required": True, "browser_required": True}
            or payload.get("loopback_listener_count") != 1
            or payload.get("loopback_port") != 4173
            or payload.get("direct_processes_spawned") != expected_process_count
            or payload.get("successful_exit_codes") != expected_exit_codes
            or payload.get("request_error_count") != 0
            or payload.get("external_network_access_accounting")
            != "not_instrumented_frontend_build_and_browser_page_requests"
            or payload.get("deterministic_receipt") is not False
            or not str(payload.get("claim_boundary") or "").strip()
            or not _is_sha256_identity(payload.get("receipt_hash"))
        ):
            continue
        unsigned = dict(payload)
        expected_hash = str(unsigned.pop("receipt_hash"))
        canonical = json.dumps(
            unsigned,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        if "sha256:" + hashlib.sha256(canonical).hexdigest() == expected_hash:
            return payload
    return {}


def _native_error(stdout: str) -> dict[str, str]:
    for payload in _json_objects_from_last_line(stdout):
        if (
            set(payload) == {"schema_version", "code", "detail"}
            and payload.get("schema_version") == "structural-frontend-contract-error.v1"
            and isinstance(payload.get("code"), str)
            and isinstance(payload.get("detail"), str)
        ):
            return {"code": payload["code"], "detail": payload["detail"]}
    return {"code": "", "detail": ""}


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
    blocker_category: str | None = None,
    blocker_reason_code: str | None = None,
    environment_blocker: bool = False,
    blocker_evidence: dict[str, Any] | None = None,
    source_commit_sha: str | None = None,
) -> dict[str, Any]:
    payload = _base_payload(repo_root=repo_root, source_commit_sha=source_commit_sha)
    payload.update(
        {
            "status": "blocked",
            "contract_pass": False,
            "failed_phase": phase,
            "blocker": blocker,
            "blocker_category": blocker_category,
            "blocker_reason_code": blocker_reason_code,
            "environment_blocker": environment_blocker,
            "blocker_evidence": blocker_evidence or {},
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
    native_command = [*NATIVE_CMD]
    if skip_build:
        native_command.append("--skip-build")
    try:
        result = subprocess.run(
            native_command,
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=360,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        output = _clip_output(str(exc))
        commands = {
            "native": {
                "argv": native_command,
                "exit_code": None,
                "output_excerpt": output,
            },
            "preview": {
                "argv": ["structural-frontend-contract", "phase5-task-browser-smoke"],
                "base_url": BASE_URL,
                "ready": False,
                "output_excerpt": output,
            },
        }
        return _blocked_payload(
            repo_root=repo_root,
            source_commit_sha=source_commit_sha,
            phase="native_browser_execution",
            blocker="native_phase5_task_browser_smoke_timeout",
            blocker_category="native_browser_execution_timeout",
            blocker_reason_code="native_command_timeout",
            commands=commands,
        )
    except OSError as exc:
        output = _clip_output(f"{exc.__class__.__name__}: {exc}")
        commands = {
            "native": {
                "argv": native_command,
                "exit_code": None,
                "output_excerpt": output,
            },
            "preview": {
                "argv": ["structural-frontend-contract", "phase5-task-browser-smoke"],
                "base_url": BASE_URL,
                "ready": False,
                "output_excerpt": output,
            },
        }
        return _blocked_payload(
            repo_root=repo_root,
            source_commit_sha=source_commit_sha,
            phase="native_browser_execution",
            blocker="native_phase5_task_browser_smoke_launch_failed",
            blocker_category="native_command_launch_failure",
            blocker_reason_code="native_command_launch_failed",
            commands=commands,
        )

    output = _completed_output(result)
    commands: dict[str, Any] = {
        "native": {
            "argv": native_command,
            "exit_code": result.returncode,
            "output_excerpt": output,
        },
        "preview": {
            "argv": ["structural-frontend-contract", "phase5-task-browser-smoke"],
            "base_url": BASE_URL,
            "ready": result.returncode == 0,
            "output_excerpt": output,
        },
    }
    if result.returncode != 0:
        error = _native_error((result.stdout or "") + "\n" + (result.stderr or ""))
        code = error["code"]
        detail = error["detail"]
        if code.startswith("frontend_build_") or code.startswith(
            "phase5_task_browser_smoke_build_"
        ):
            return _blocked_payload(
                repo_root=repo_root,
                source_commit_sha=source_commit_sha,
                phase="build",
                blocker="frontend_build_failed",
                blocker_category="native_frontend_build_failure",
                blocker_reason_code=code or "frontend_build_failed",
                commands=commands,
            )
        if code == "phase5_task_browser_smoke_bind_failed":
            normalized = detail.lower()
            permission_blocked = any(
                marker in normalized
                for marker in ("operation not permitted", "permission denied", "os error 1")
            )
            return _blocked_payload(
                repo_root=repo_root,
                source_commit_sha=source_commit_sha,
                phase="preview_server_start",
                blocker=(
                    PREVIEW_LOOPBACK_BIND_BLOCKER
                    if permission_blocked
                    else "preview_server_failed_before_browser_execution"
                ),
                blocker_category=(
                    "environment_loopback_bind_permission"
                    if permission_blocked
                    else "preview_server_start_failure"
                ),
                blocker_reason_code=(
                    PREVIEW_LOOPBACK_BIND_REASON_CODE
                    if permission_blocked
                    else "preview_server_start_failed"
                ),
                environment_blocker=permission_blocked,
                blocker_evidence=(
                    {
                        "syscall": "listen",
                        "code": "EPERM",
                        "address": "127.0.0.1",
                        "port": 4173,
                    }
                    if permission_blocked
                    else {}
                ),
                commands=commands,
            )
        return _blocked_payload(
            repo_root=repo_root,
            source_commit_sha=source_commit_sha,
            phase="playwright_browser_execution",
            blocker="playwright_task_based_browser_smoke_failed",
            blocker_category="native_playwright_execution_failure",
            blocker_reason_code=code or "native_phase5_task_browser_smoke_failed",
            commands=commands,
        )

    receipt = _native_receipt(result.stdout or "", skip_build=skip_build)
    if not receipt:
        return _blocked_payload(
            repo_root=repo_root,
            source_commit_sha=source_commit_sha,
            phase="native_receipt_validation",
            blocker="native_phase5_task_browser_receipt_invalid",
            blocker_category="native_receipt_validation_failure",
            blocker_reason_code="native_receipt_missing_or_invalid",
            commands=commands,
        )
    commands["native"]["receipt_hash"] = receipt["receipt_hash"]
    commands["build"] = {
        "owned_by": "structural-frontend-contract",
        "skipped": skip_build,
        "receipt_hash": receipt["frontend_build_receipt_hash"],
        "delivery_receipt_hash": receipt["delivery_receipt_hash"],
    }
    commands["preview"].update(
        {
            "owned_by": "structural-frontend-contract",
            "listener_count": receipt["loopback_listener_count"],
            "port": receipt["loopback_port"],
            "request_error_count": receipt["request_error_count"],
        }
    )
    commands["playwright"] = {
        "owned_by": "structural-frontend-contract",
        "argv": receipt["playwright_command"],
        "exit_code": receipt["successful_exit_codes"][-1],
        "cli_sha256": receipt["playwright_cli_sha256"],
    }
    return _passed_payload(
        repo_root=repo_root,
        source_commit_sha=source_commit_sha,
        commands=commands,
    )


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
