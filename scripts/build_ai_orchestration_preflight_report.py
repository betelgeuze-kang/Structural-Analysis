#!/usr/bin/env python3
"""Write Cursor/OpenCode orchestration preflight evidence as JSON."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any


DEFAULT_OUT = Path("implementation/phase1/release_evidence/productization/ai_orchestration_preflight_report.json")
REQUIRED_FILES = [
    Path("AGENTS.md"),
    Path(".cursor/rules/project.mdc"),
    Path("docs/ai/ORCHESTRATION.md"),
    Path("docs/ai/prompts/codex_goal_start.md"),
    Path("docs/ai/prompts/cursor_worker_slice.md"),
    Path("docs/ai/prompts/opencode_worker_slice.md"),
    Path("docs/ai/checklists/ai-agent-security.md"),
    Path("docs/ai/checklists/pre-review.md"),
    Path("docs/ai/checklists/pre-merge.md"),
    Path("opencode.json"),
]
WRAPPER_SCRIPTS = [
    Path("scripts/ai-dangerous-command-check.sh"),
    Path("scripts/ai-worker-cursor.sh"),
    Path("scripts/ai-worker-opencode.sh"),
    Path("scripts/ai-preflight.sh"),
    Path("scripts/ai-verify.sh"),
]


def _run(command: list[str]) -> tuple[bool, str]:
    try:
        result = subprocess.run(command, check=False, text=True, capture_output=True)
    except Exception as exc:
        return False, str(exc)
    output = "\n".join(part for part in (result.stdout.strip(), result.stderr.strip()) if part)
    return result.returncode == 0, output


def _augmented_path() -> str:
    entries = [str(Path.home() / ".local" / "bin")]
    npm = shutil.which("npm")
    if npm:
        ok, output = _run([npm, "prefix", "-g"])
        if ok and output.strip():
            entries.append(str(Path(output.strip()) / "bin"))
    entries.append(os.environ.get("PATH", ""))
    return os.pathsep.join(entries)


def _which(*names: str) -> tuple[str, str]:
    path = _augmented_path()
    for name in names:
        found = shutil.which(name, path=path)
        if found:
            return name, found
    return "", ""


def build_report() -> dict[str, Any]:
    missing_files = [str(path) for path in REQUIRED_FILES if not path.exists()]
    missing_wrappers = [str(path) for path in WRAPPER_SCRIPTS if not path.exists()]
    executable_wrappers = [str(path) for path in WRAPPER_SCRIPTS if path.exists() and path.stat().st_mode & 0o111]
    syntax_pass, syntax_output = _run(["bash", "-n", *[str(path) for path in WRAPPER_SCRIPTS]])
    json_pass, json_output = _run(["python3", "-m", "json.tool", "opencode.json"])
    cursor_name, cursor_path = _which("cursor-agent", "cursor")
    opencode_name, opencode_path = _which("opencode")
    opencode_version = ""
    if opencode_path:
        _, opencode_version = _run([opencode_path, "--version"])

    checks = {
        "required_files_present": not missing_files,
        "worker_wrappers_present": not missing_wrappers,
        "worker_wrappers_executable": len(executable_wrappers) == len(WRAPPER_SCRIPTS),
        "worker_shell_syntax_pass": syntax_pass,
        "opencode_json_valid": json_pass,
        "cursor_worker_cli_present": bool(cursor_path),
        "opencode_worker_cli_present": bool(opencode_path),
    }
    blockers = [
        *(["required_orchestration_files_missing"] if not checks["required_files_present"] else []),
        *(["worker_wrappers_missing"] if not checks["worker_wrappers_present"] else []),
        *(["worker_wrappers_not_executable"] if not checks["worker_wrappers_executable"] else []),
        *(["worker_shell_syntax_failed"] if not checks["worker_shell_syntax_pass"] else []),
        *(["opencode_json_invalid"] if not checks["opencode_json_valid"] else []),
        *(["cursor_worker_cli_missing"] if not checks["cursor_worker_cli_present"] else []),
        *(["opencode_worker_cli_missing"] if not checks["opencode_worker_cli_present"] else []),
    ]
    return {
        "schema_version": "ai-orchestration-preflight-report.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contract_pass": not blockers,
        "reason_code": "PASS" if not blockers else "BLOCKED",
        "blockers": blockers,
        "checks": checks,
        "summary": {
            "cursor_worker_cli": cursor_name or "missing",
            "cursor_worker_cli_path": cursor_path,
            "opencode_worker_cli": opencode_name or "missing",
            "opencode_worker_cli_path": opencode_path,
            "opencode_version": opencode_version.strip(),
            "required_file_count": len(REQUIRED_FILES),
            "wrapper_count": len(WRAPPER_SCRIPTS),
        },
        "diagnostics": {
            "missing_files": missing_files,
            "missing_wrappers": missing_wrappers,
            "wrapper_syntax_output": syntax_output,
            "opencode_json_output": json_output,
        },
        "claim_boundary": (
            "This report verifies Cursor/OpenCode worker bridge readiness only. Codex still owns goal tracking, "
            "diff review, verification, and final acceptance."
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_report()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) if args.json else payload["reason_code"])
    return 0 if payload["contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
