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
DEFAULT_OPENCODE_MODEL = "opencode-go/minimax-m3"
OPENCODE_DEEPSEEK_V4_PRO_MODEL = "opencode-go/deepseek-v4-pro"
OPENCODE_MINIMAX_M3_MODEL = "opencode-go/minimax-m3"
OPENCODE_GLM52_MODEL = "opencode-go/glm-5.2"
DEFAULT_OPENCODE_XDG_DATA_HOME = Path("/tmp/codex-opencode-xdg-data")
DEFAULT_OPENCODE_GO_MIRROR_XDG_DATA_HOME = Path("/tmp/codex-opencode-go-xdg-data")
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


def _run(command: list[str], *, env: dict[str, str] | None = None) -> tuple[bool, str]:
    try:
        result = subprocess.run(command, check=False, text=True, capture_output=True, env=env)
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


def _opencode_data_home_writable(path: Path) -> bool:
    try:
        log_dir = path / "opencode" / "log"
        log_dir.mkdir(parents=True, exist_ok=True)
        probe = log_dir / ".codex-write-test"
        probe.write_text("", encoding="utf-8")
        probe.unlink(missing_ok=True)
    except Exception:
        return False
    return True


def _opencode_go_source_data_home() -> Path | None:
    candidates: list[Path] = []
    override = os.environ.get("AI_WORKER_OPENCODE_GO_SOURCE_DATA_HOME")
    if override:
        candidates.append(Path(override))
    current_xdg = os.environ.get("XDG_DATA_HOME")
    if current_xdg:
        candidates.append(Path(current_xdg))
    home = Path.home()
    candidates.append(home / "snap" / "code" / "247" / ".local" / "share")
    candidates.append(home / ".local" / "share")
    snap_code_root = home / "snap" / "code"
    if snap_code_root.exists():
        candidates.extend(sorted(snap_code_root.glob("*/.local/share")))
    for candidate in candidates:
        if (candidate / "opencode" / "auth.json").is_file() and (
            candidate / "opencode" / "account.json"
        ).is_file():
            return candidate
    return None


def _ensure_symlink(source: Path, link: Path) -> bool:
    if link.is_symlink():
        if Path(os.readlink(link)) == source:
            return True
        link.unlink()
    elif link.exists():
        return False
    link.symlink_to(source)
    return True


def _prepare_opencode_go_mirror_data_home() -> str | None:
    source_home = _opencode_go_source_data_home()
    if source_home is None:
        return None
    mirror_home = Path(
        os.environ.get(
            "AI_WORKER_OPENCODE_GO_MIRROR_XDG_DATA_HOME",
            str(
                Path(os.environ.get("TMPDIR", str(DEFAULT_OPENCODE_GO_MIRROR_XDG_DATA_HOME.parent)))
                / "codex-opencode-go-xdg-data"
            ),
        )
    )
    opencode_dir = mirror_home / "opencode"
    (opencode_dir / "log").mkdir(parents=True, exist_ok=True)
    try:
        mirror_home.chmod(0o700)
        opencode_dir.chmod(0o700)
    except OSError:
        pass
    if not _ensure_symlink(source_home / "opencode" / "auth.json", opencode_dir / "auth.json"):
        return None
    if not _ensure_symlink(source_home / "opencode" / "account.json", opencode_dir / "account.json"):
        return None
    return str(mirror_home)


def _opencode_worker_env() -> tuple[dict[str, str], str]:
    xdg_data_home = os.environ.get("AI_WORKER_OPENCODE_XDG_DATA_HOME")
    if not xdg_data_home:
        current_xdg = os.environ.get("XDG_DATA_HOME")
        if current_xdg and _opencode_data_home_writable(Path(current_xdg)):
            xdg_data_home = current_xdg
        elif _configured_opencode_model().startswith("opencode-go/"):
            xdg_data_home = _prepare_opencode_go_mirror_data_home()
        else:
            xdg_data_home = str(
                Path(os.environ.get("TMPDIR", str(DEFAULT_OPENCODE_XDG_DATA_HOME.parent)))
                / "codex-opencode-xdg-data"
            )
    if not xdg_data_home:
        xdg_data_home = str(
            Path(os.environ.get("TMPDIR", str(DEFAULT_OPENCODE_XDG_DATA_HOME.parent)))
            / "codex-opencode-xdg-data"
        )
    Path(xdg_data_home, "opencode", "log").mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["PATH"] = _augmented_path()
    env["XDG_DATA_HOME"] = xdg_data_home
    return env, xdg_data_home


def _normalize_opencode_model(model: str) -> str:
    aliases = {
        "minimax/m3": OPENCODE_MINIMAX_M3_MODEL,
        "minimax-m3": OPENCODE_MINIMAX_M3_MODEL,
        "minimaxm3": OPENCODE_MINIMAX_M3_MODEL,
        "minimax3": OPENCODE_MINIMAX_M3_MODEL,
        "minimax m3": OPENCODE_MINIMAX_M3_MODEL,
        "minimax 3": OPENCODE_MINIMAX_M3_MODEL,
        "m3": OPENCODE_MINIMAX_M3_MODEL,
        "glm/5.2": OPENCODE_GLM52_MODEL,
        "glm-5.2": OPENCODE_GLM52_MODEL,
        "glm5.2": OPENCODE_GLM52_MODEL,
        "glm 5.2": OPENCODE_GLM52_MODEL,
        "kimi/k2.7": OPENCODE_GLM52_MODEL,
        "kimi-k2.7": OPENCODE_GLM52_MODEL,
        "k2.7": OPENCODE_GLM52_MODEL,
        "kimi-k2.7-code": OPENCODE_GLM52_MODEL,
        "deepseek/v4/pro": OPENCODE_DEEPSEEK_V4_PRO_MODEL,
        "deepseek-v4-pro": OPENCODE_DEEPSEEK_V4_PRO_MODEL,
        "deepseekv4pro": OPENCODE_DEEPSEEK_V4_PRO_MODEL,
        "deepseek v4 pro": OPENCODE_DEEPSEEK_V4_PRO_MODEL,
        "v4-pro": OPENCODE_DEEPSEEK_V4_PRO_MODEL,
    }
    return aliases.get(model, model)


def _configured_opencode_model() -> str:
    requested = os.environ.get("OPENCODE_MODEL") or os.environ.get("AI_WORKER_OPENCODE_MODEL") or DEFAULT_OPENCODE_MODEL
    return _normalize_opencode_model(requested)


def _model_rows(output: str) -> list[str]:
    return [line.strip() for line in output.splitlines() if line.strip() and not line.startswith("\x1b")]


def build_report() -> dict[str, Any]:
    missing_files = [str(path) for path in REQUIRED_FILES if not path.exists()]
    missing_wrappers = [str(path) for path in WRAPPER_SCRIPTS if not path.exists()]
    executable_wrappers = [str(path) for path in WRAPPER_SCRIPTS if path.exists() and path.stat().st_mode & 0o111]
    syntax_pass, syntax_output = _run(["bash", "-n", *[str(path) for path in WRAPPER_SCRIPTS]])
    json_pass, json_output = _run(["python3", "-m", "json.tool", "opencode.json"])
    cursor_name, cursor_path = _which("cursor-agent", "cursor")
    opencode_name, opencode_path = _which("opencode")
    opencode_version = ""
    opencode_model = _configured_opencode_model()
    opencode_worker_env, opencode_xdg_data_home = _opencode_worker_env()
    opencode_models_pass = False
    opencode_models_output = ""
    opencode_model_rows: list[str] = []
    if opencode_path:
        _, opencode_version = _run([opencode_path, "--version"], env=opencode_worker_env)
        opencode_models_pass, opencode_models_output = _run([opencode_path, "models"], env=opencode_worker_env)
        opencode_model_rows = _model_rows(opencode_models_output)
    opencode_configured_model_available = bool(opencode_model and opencode_model in opencode_model_rows)

    checks = {
        "required_files_present": not missing_files,
        "worker_wrappers_present": not missing_wrappers,
        "worker_wrappers_executable": len(executable_wrappers) == len(WRAPPER_SCRIPTS),
        "worker_shell_syntax_pass": syntax_pass,
        "opencode_json_valid": json_pass,
        "cursor_worker_cli_present": bool(cursor_path),
        "opencode_worker_cli_present": bool(opencode_path),
        "opencode_model_registry_query_pass": bool(opencode_path and opencode_models_pass),
        "opencode_worker_configured_model_available": opencode_configured_model_available,
    }
    blockers = [
        *(["required_orchestration_files_missing"] if not checks["required_files_present"] else []),
        *(["worker_wrappers_missing"] if not checks["worker_wrappers_present"] else []),
        *(["worker_wrappers_not_executable"] if not checks["worker_wrappers_executable"] else []),
        *(["worker_shell_syntax_failed"] if not checks["worker_shell_syntax_pass"] else []),
        *(["opencode_json_invalid"] if not checks["opencode_json_valid"] else []),
        *(["cursor_worker_cli_missing"] if not checks["cursor_worker_cli_present"] else []),
        *(["opencode_worker_cli_missing"] if not checks["opencode_worker_cli_present"] else []),
        *(
            ["opencode_model_registry_query_failed"]
            if checks["opencode_worker_cli_present"] and not checks["opencode_model_registry_query_pass"]
            else []
        ),
        *(
            ["opencode_worker_configured_model_unavailable"]
            if checks["opencode_worker_cli_present"]
            and checks["opencode_model_registry_query_pass"]
            and not checks["opencode_worker_configured_model_available"]
            else []
        ),
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
            "opencode_configured_model": opencode_model,
            "opencode_configured_model_available": opencode_configured_model_available,
            "opencode_xdg_data_home": opencode_xdg_data_home,
            "opencode_model_count": len(opencode_model_rows),
            "required_file_count": len(REQUIRED_FILES),
            "wrapper_count": len(WRAPPER_SCRIPTS),
        },
        "diagnostics": {
            "missing_files": missing_files,
            "missing_wrappers": missing_wrappers,
            "wrapper_syntax_output": syntax_output,
            "opencode_json_output": json_output,
            "opencode_models_output": opencode_models_output,
            "opencode_model_rows": opencode_model_rows,
        },
        "claim_boundary": (
            "This report verifies Cursor/OpenCode worker bridge readiness and local OpenCode model-registry "
            "availability for the configured worker model. It does not prove remote model credentials, successful "
            "inference, or release readiness. Codex still owns goal tracking, diff review, verification, and final "
            "acceptance."
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
