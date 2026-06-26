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
DEFAULT_OPENCODE_MODEL = "opencode-go/deepseek-v4-pro"
OPENCODE_DEEPSEEK_V4_PRO_MODEL = "opencode-go/deepseek-v4-pro"
OPENCODE_MINIMAX_M3_MODEL = "opencode-go/minimax-m3"
OPENCODE_GLM52_MODEL = "opencode-go/glm-5.2"
DEFAULT_OPENCODE_ASSIGNMENT_CURSOR_MODEL = "composer-2.5"
DEFAULT_OPENCODE_XDG_DATA_HOME = Path("/tmp/codex-opencode-xdg-data")
DEFAULT_OPENCODE_GO_MIRROR_XDG_DATA_HOME = Path("/tmp/codex-opencode-go-xdg-data")
DEFAULT_DESIGN_STAGE = "kiro"
DEFAULT_DESIGN_MODEL = "opus-4.8"
DEFAULT_IMPLEMENTATION_STAGE = "cursor"
DEFAULT_IMPLEMENTATION_MODEL = "composer-2.5"
DEFAULT_VERIFICATION_STAGE = "codex"
DEFAULT_VERIFICATION_MODEL = "gpt-5.5"
DEFAULT_VERIFICATION_REASONING_EFFORT = "xhigh"
INTERNAL_SUBAGENT_FALLBACK_AGENT_TYPE = "worker"
INTERNAL_SUBAGENT_FALLBACK_MODEL = "gpt-5.4-mini"
INTERNAL_SUBAGENT_FALLBACK_REASONING_EFFORT = "xhigh"
CURSOR_REMOTE_API_HOST = "api2.cursor.sh"
DEFAULT_CURSOR_HOST_BRIDGE_DIR = Path(".betelgeuze/cursor_worker_bridge")
REQUIRED_FILES = [
    Path("AGENTS.md"),
    Path(".cursor/rules/project.mdc"),
    Path("docs/ai/ORCHESTRATION.md"),
    Path("docs/ai/prompts/codex_goal_start.md"),
    Path("docs/ai/prompts/kiro_design_slice.md"),
    Path("docs/ai/prompts/cursor_worker_slice.md"),
    Path("docs/ai/prompts/opencode_worker_slice.md"),
    Path("docs/ai/checklists/ai-agent-security.md"),
    Path("docs/ai/checklists/pre-review.md"),
    Path("docs/ai/checklists/pre-merge.md"),
    Path("opencode.json"),
]
WRAPPER_SCRIPTS = [
    Path("scripts/ai-dangerous-command-check.sh"),
    Path("scripts/ai-run-kiro-design.sh"),
    Path("scripts/ai-worker-kiro.sh"),
    Path("scripts/ai-worker-cursor.sh"),
    Path("scripts/ai-worker-cursor-host-bridge.sh"),
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


def _cursor_host_bridge_dir() -> Path:
    return Path(os.environ.get("AI_WORKER_CURSOR_HOST_BRIDGE_DIR", str(DEFAULT_CURSOR_HOST_BRIDGE_DIR)))


def _cursor_host_bridge_ready(path: Path) -> bool:
    return (
        (path / "host-bridge.ready").is_file()
        and (path / "jobs").is_dir()
        and (path / "done").is_dir()
    )


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


def _opencode_assignment_routed_to_cursor() -> bool:
    return os.environ.get("AI_WORKER_OPENCODE_ASSIGNMENT_MODE", "cursor-composer-2.5") != "opencode"


def _opencode_assignment_cursor_model() -> str:
    return os.environ.get(
        "AI_WORKER_OPENCODE_ASSIGNMENT_CURSOR_MODEL",
        DEFAULT_OPENCODE_ASSIGNMENT_CURSOR_MODEL,
    )


def _model_rows(output: str) -> list[str]:
    return [line.strip() for line in output.splitlines() if line.strip() and not line.startswith("\x1b")]


def build_report() -> dict[str, Any]:
    missing_files = [str(path) for path in REQUIRED_FILES if not path.exists()]
    missing_wrappers = [str(path) for path in WRAPPER_SCRIPTS if not path.exists()]
    executable_wrappers = [str(path) for path in WRAPPER_SCRIPTS if path.exists() and path.stat().st_mode & 0o111]
    syntax_pass, syntax_output = _run(["bash", "-n", *[str(path) for path in WRAPPER_SCRIPTS]])
    json_pass, json_output = _run(["python3", "-m", "json.tool", "opencode.json"])
    cursor_name, cursor_path = _which("cursor-agent", "cursor")
    kiro_name, kiro_path = _which("kiro")
    kiro_chat_help_pass = False
    kiro_chat_help_output = ""
    if kiro_path:
        kiro_chat_help_pass, kiro_chat_help_output = _run([kiro_path, "chat", "--help"])
    kiro_worker_wrapper = Path("scripts/ai-worker-kiro.sh")
    kiro_worker_wrapper_text = (
        kiro_worker_wrapper.read_text(encoding="utf-8")
        if kiro_worker_wrapper.exists()
        else ""
    )
    kiro_run_wrapper = Path("scripts/ai-run-kiro-design.sh")
    kiro_run_wrapper_text = (
        kiro_run_wrapper.read_text(encoding="utf-8") if kiro_run_wrapper.exists() else ""
    )
    kiro_prompt_template = Path("docs/ai/prompts/kiro_design_slice.md")
    kiro_prompt_template_validation_pass = False
    kiro_prompt_template_validation_output = ""
    if kiro_worker_wrapper.exists() and kiro_prompt_template.exists():
        kiro_prompt_template_validation_pass, kiro_prompt_template_validation_output = _run(
            [str(kiro_worker_wrapper), "--check", str(kiro_prompt_template)]
        )
    cursor_host_bridge_dir = _cursor_host_bridge_dir()
    cursor_host_bridge_ready = _cursor_host_bridge_ready(cursor_host_bridge_dir)
    opencode_name, opencode_path = _which("opencode")
    opencode_version = ""
    opencode_model = _configured_opencode_model()
    opencode_assignment_routed_to_cursor = _opencode_assignment_routed_to_cursor()
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
        "kiro_cli_present": bool(kiro_path),
        "kiro_chat_command_present": bool(kiro_path and kiro_chat_help_pass),
        "kiro_worker_wrapper_present": kiro_worker_wrapper.exists(),
        "kiro_worker_wrapper_verifies_opus48": "required_kiro_model=\"opus-4.8\""
        in kiro_worker_wrapper_text
        and "validate_kiro_prompt" in kiro_worker_wrapper_text,
        "kiro_worker_wrapper_runs_automatic_prelaunch_check": "wrapper_prelaunch_check_passed"
        in kiro_worker_wrapper_text
        and "automatic_prelaunch_before_kiro_chat" in kiro_worker_wrapper_text,
        "kiro_worker_wrapper_enforces_opus48_confirmation": "wrapper_enforced_model_confirmation"
        in kiro_worker_wrapper_text
        and "Confirm the prompt's ${required_kiro_model} target" in kiro_worker_wrapper_text,
        "kiro_design_run_wrapper_present": kiro_run_wrapper.exists(),
        "kiro_design_run_wrapper_checks_before_launch": 'ai-worker-kiro.sh --check "$prompt_file"'
        in kiro_run_wrapper_text
        and 'ai-worker-kiro.sh "$prompt_file"' in kiro_run_wrapper_text,
        "kiro_design_template_validates_with_wrapper": kiro_prompt_template_validation_pass,
        "kiro_headless_stdout_capture_wired": "headless_stdout_capture_wired"
        in kiro_worker_wrapper_text
        and "design_output_path" in kiro_worker_wrapper_text
        and "codex_consumable_design_output" in kiro_worker_wrapper_text,
        "cursor_host_bridge_ready": cursor_host_bridge_ready,
        "cursor_dns_permission_grantable_from_codex": False,
        "opencode_worker_cli_present": bool(opencode_path),
        "opencode_model_registry_query_pass": bool(opencode_path and opencode_models_pass),
        "opencode_worker_configured_model_available": opencode_configured_model_available,
        "opencode_assignment_routed_to_cursor": opencode_assignment_routed_to_cursor,
        "code_improvement_design_stage_configured": DEFAULT_DESIGN_STAGE == "kiro"
        and DEFAULT_DESIGN_MODEL == "opus-4.8",
        "code_improvement_implementation_stage_configured": (
            DEFAULT_IMPLEMENTATION_STAGE == "cursor"
            and DEFAULT_IMPLEMENTATION_MODEL == DEFAULT_OPENCODE_ASSIGNMENT_CURSOR_MODEL
        ),
        "code_improvement_verification_stage_configured": (
            DEFAULT_VERIFICATION_STAGE == "codex"
            and DEFAULT_VERIFICATION_MODEL == "gpt-5.5"
            and DEFAULT_VERIFICATION_REASONING_EFFORT == "xhigh"
        ),
        "internal_subagent_fallback_agent_type_configured": INTERNAL_SUBAGENT_FALLBACK_AGENT_TYPE == "worker",
        "internal_subagent_fallback_model_configured": INTERNAL_SUBAGENT_FALLBACK_MODEL == "gpt-5.4-mini",
        "internal_subagent_fallback_reasoning_effort_configured": (
            INTERNAL_SUBAGENT_FALLBACK_REASONING_EFFORT == "xhigh"
        ),
    }
    blockers = [
        *(["required_orchestration_files_missing"] if not checks["required_files_present"] else []),
        *(["worker_wrappers_missing"] if not checks["worker_wrappers_present"] else []),
        *(["worker_wrappers_not_executable"] if not checks["worker_wrappers_executable"] else []),
        *(["worker_shell_syntax_failed"] if not checks["worker_shell_syntax_pass"] else []),
        *(["opencode_json_invalid"] if not checks["opencode_json_valid"] else []),
        *(["cursor_worker_cli_missing"] if not checks["cursor_worker_cli_present"] else []),
        *(
            ["opencode_worker_cli_missing"]
            if not opencode_assignment_routed_to_cursor and not checks["opencode_worker_cli_present"]
            else []
        ),
        *(
            ["opencode_model_registry_query_failed"]
            if not opencode_assignment_routed_to_cursor
            and checks["opencode_worker_cli_present"]
            and not checks["opencode_model_registry_query_pass"]
            else []
        ),
        *(
            ["opencode_worker_configured_model_unavailable"]
            if not opencode_assignment_routed_to_cursor
            and checks["opencode_worker_cli_present"]
            and checks["opencode_model_registry_query_pass"]
            and not checks["opencode_worker_configured_model_available"]
            else []
        ),
        *(
            ["code_improvement_design_stage_misconfigured"]
            if not checks["code_improvement_design_stage_configured"]
            else []
        ),
        *(
            ["kiro_worker_wrapper_missing"]
            if not checks["kiro_worker_wrapper_present"]
            else []
        ),
        *(
            ["kiro_worker_wrapper_opus48_check_missing"]
            if checks["kiro_worker_wrapper_present"]
            and not checks["kiro_worker_wrapper_verifies_opus48"]
            else []
        ),
        *(
            ["kiro_worker_wrapper_automatic_prelaunch_check_missing"]
            if checks["kiro_worker_wrapper_present"]
            and not checks["kiro_worker_wrapper_runs_automatic_prelaunch_check"]
            else []
        ),
        *(
            ["kiro_worker_wrapper_opus48_confirmation_missing"]
            if checks["kiro_worker_wrapper_present"]
            and not checks["kiro_worker_wrapper_enforces_opus48_confirmation"]
            else []
        ),
        *(
            ["kiro_design_run_wrapper_missing"]
            if not checks["kiro_design_run_wrapper_present"]
            else []
        ),
        *(
            ["kiro_design_run_wrapper_check_before_launch_missing"]
            if checks["kiro_design_run_wrapper_present"]
            and not checks["kiro_design_run_wrapper_checks_before_launch"]
            else []
        ),
        *(
            ["kiro_design_template_wrapper_validation_failed"]
            if not checks["kiro_design_template_validates_with_wrapper"]
            else []
        ),
        *(
            ["code_improvement_implementation_stage_misconfigured"]
            if not checks["code_improvement_implementation_stage_configured"]
            else []
        ),
        *(
            ["code_improvement_verification_stage_misconfigured"]
            if not checks["code_improvement_verification_stage_configured"]
            else []
        ),
        *(
            ["internal_subagent_fallback_agent_type_misconfigured"]
            if not checks["internal_subagent_fallback_agent_type_configured"]
            else []
        ),
        *(
            ["internal_subagent_fallback_model_misconfigured"]
            if not checks["internal_subagent_fallback_model_configured"]
            else []
        ),
        *(
            ["internal_subagent_fallback_reasoning_effort_misconfigured"]
            if not checks["internal_subagent_fallback_reasoning_effort_configured"]
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
            "cursor_remote_api_host": CURSOR_REMOTE_API_HOST,
            "kiro_cli": kiro_name or "missing",
            "kiro_cli_path": kiro_path,
            "kiro_chat_command_available": bool(kiro_path and kiro_chat_help_pass),
            "kiro_design_invocation_mode": (
                "kiro_checked_run_wrapper_launch"
                if kiro_run_wrapper.exists()
                else "kiro_chat_wrapper_launch"
                if kiro_worker_wrapper.exists()
                else "prompt_file_only"
            ),
            "kiro_design_run_wrapper": str(kiro_run_wrapper),
            "kiro_design_run_wrapper_present": checks["kiro_design_run_wrapper_present"],
            "kiro_design_run_wrapper_checks_before_launch": checks[
                "kiro_design_run_wrapper_checks_before_launch"
            ],
            "kiro_worker_wrapper": str(kiro_worker_wrapper),
            "kiro_worker_wrapper_present": kiro_worker_wrapper.exists(),
            "kiro_worker_wrapper_verifies_opus48": checks["kiro_worker_wrapper_verifies_opus48"],
            "kiro_worker_wrapper_runs_automatic_prelaunch_check": checks[
                "kiro_worker_wrapper_runs_automatic_prelaunch_check"
            ],
            "kiro_worker_wrapper_enforces_opus48_confirmation": checks[
                "kiro_worker_wrapper_enforces_opus48_confirmation"
            ],
            "kiro_design_template_validates_with_wrapper": checks[
                "kiro_design_template_validates_with_wrapper"
            ],
            "kiro_headless_stdout_capture_wired": checks[
                "kiro_headless_stdout_capture_wired"
            ],
            "kiro_headless_stdout_capture_note": (
                "The wrapper captures Kiro stdout into a design-output file when "
                "the Kiro CLI emits stdout. Each launch receipt must still show "
                "headless_stdout_capture=true before Codex treats the design as "
                "machine-captured."
            ),
            "cursor_host_bridge_dir": str(cursor_host_bridge_dir),
            "cursor_host_bridge_ready": cursor_host_bridge_ready,
            "cursor_dns_permission_owner": "host_or_codex_session_configuration",
            "cursor_dns_permission_grantable_from_codex": False,
            "cursor_dns_failure_fallbacks": [
                "start_host_bridge_from_network_enabled_host_terminal",
                "run_worker_wrapper_from_cursor_or_host_terminal_with_outbound_dns",
                "start_a_codex_session_with_terminal_network_enabled",
                "use_internal_codex_subagent_for_scoped_local_work",
            ],
            "opencode_worker_cli": opencode_name or "missing",
            "opencode_worker_cli_path": opencode_path,
            "opencode_version": opencode_version.strip(),
            "opencode_configured_model": opencode_model,
            "opencode_configured_model_available": opencode_configured_model_available,
            "opencode_assignment_routed_to_cursor": opencode_assignment_routed_to_cursor,
            "opencode_assignment_cursor_model": _opencode_assignment_cursor_model(),
            "code_improvement_pipeline": [
                {
                    "stage": DEFAULT_DESIGN_STAGE,
                    "model": DEFAULT_DESIGN_MODEL,
                    "responsibility": "compact_design_only",
                    "prompt_template": "docs/ai/prompts/kiro_design_slice.md",
                    "run_wrapper": "scripts/ai-run-kiro-design.sh",
                },
                {
                    "stage": DEFAULT_IMPLEMENTATION_STAGE,
                    "model": DEFAULT_IMPLEMENTATION_MODEL,
                    "responsibility": "scoped_implementation",
                    "prompt_template": "docs/ai/prompts/cursor_worker_slice.md",
                },
                {
                    "stage": DEFAULT_VERIFICATION_STAGE,
                    "model": DEFAULT_VERIFICATION_MODEL,
                    "reasoning_effort": DEFAULT_VERIFICATION_REASONING_EFFORT,
                    "responsibility": "diff_evidence_claim_boundary_review",
                },
            ],
            "kiro_design_model": DEFAULT_DESIGN_MODEL,
            "cursor_implementation_model": DEFAULT_IMPLEMENTATION_MODEL,
            "codex_verification_model": DEFAULT_VERIFICATION_MODEL,
            "codex_verification_reasoning_effort": DEFAULT_VERIFICATION_REASONING_EFFORT,
            "cursor_failure_internal_subagent_fallback_agent_type": INTERNAL_SUBAGENT_FALLBACK_AGENT_TYPE,
            "cursor_failure_internal_subagent_fallback_model": INTERNAL_SUBAGENT_FALLBACK_MODEL,
            "cursor_failure_internal_subagent_fallback_reasoning_effort": (
                INTERNAL_SUBAGENT_FALLBACK_REASONING_EFFORT
            ),
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
            "cursor_host_bridge_ready_file": str(cursor_host_bridge_dir / "host-bridge.ready"),
            "kiro_chat_help_output": kiro_chat_help_output,
            "kiro_prompt_template_validation_output": kiro_prompt_template_validation_output,
            "opencode_models_output": opencode_models_output,
            "opencode_model_rows": opencode_model_rows,
        },
        "claim_boundary": (
            "This report verifies Cursor/OpenCode worker bridge readiness and local OpenCode model-registry "
            "availability when OpenCode assignment mode is enabled, plus the current routing of OpenCode-assigned "
            "slices to Cursor and the configured internal Codex subagent fallback model for Cursor-unavailable "
            "implementation slices. It also records the default code-improvement handoff policy: Kiro design, "
            "Cursor implementation, then Codex verification. Kiro design slices should be launched through "
            "scripts/ai-run-kiro-design.sh, which first calls the Kiro worker prompt check and then delegates "
            "the launch to scripts/ai-worker-kiro.sh. The Kiro worker is expected to run an automatic "
            "prelaunch prompt validation that confirms the opus-4.8, no-edit, and no-readiness-closure boundaries "
            "before each Kiro chat launch. The wrapper also instructs Kiro to confirm the "
            "opus-4.8 target in its answer. Kiro design is currently prompt-file configured; "
            "this report proves only that stdout capture is wired in the wrapper. A specific launch receipt "
            "must still show headless_stdout_capture=true and design_output_path before Codex can claim it "
            "consumed Kiro's design. Cursor API DNS/network permission is recorded as owned by the host or Codex "
            "session configuration, not something this repository can grant from inside a restricted terminal. "
            "It does not prove remote model credentials, successful inference, worker execution, subagent "
            "execution, or release readiness. Codex still owns goal tracking, diff review, verification, and "
            "final acceptance."
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
