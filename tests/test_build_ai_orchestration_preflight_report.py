from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "build_ai_orchestration_preflight_report.py"
SPEC = importlib.util.spec_from_file_location("build_ai_orchestration_preflight_report", SCRIPT_PATH)
assert SPEC is not None
build_preflight_module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(build_preflight_module)


def _write(path: Path, text: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _make_executable(path: Path, text: str) -> Path:
    _write(path, text)
    path.chmod(path.stat().st_mode | 0o755)
    return path


def _seed_orchestration_files(tmp_path: Path) -> None:
    for path in build_preflight_module.REQUIRED_FILES:
        _write(tmp_path / path, "{}\n" if path.name == "opencode.json" else "ok\n")
    for path in build_preflight_module.WRAPPER_SCRIPTS:
        _make_executable(tmp_path / path, "#!/usr/bin/env bash\nset -euo pipefail\n")
    _write(
        tmp_path / "docs" / "ai" / "prompts" / "kiro_design_slice.md",
        "You are Kiro running as a design-only architect on model `opus-4.8`.\n"
        "Do not edit files. Do not claim readiness closure.\n",
    )
    _make_executable(
        tmp_path / "scripts" / "ai-worker-kiro.sh",
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "required_kiro_model=\"opus-4.8\"\n"
        "wrapper_validation_mode=\"automatic_prelaunch_before_kiro_chat\"\n"
        "instruction=\"Confirm the prompt's ${required_kiro_model} target\"\n"
        "validate_kiro_prompt() {\n"
        "  grep -Fq -- \"model \\`${required_kiro_model}\\`\" \"$1\"\n"
        "  grep -Fq -- 'Do not edit files' \"$1\"\n"
        "  grep -Fq -- 'Do not claim readiness closure' \"$1\"\n"
        "}\n"
        "write_launch_receipt() { echo wrapper_prelaunch_check_passed wrapper_enforced_model_confirmation headless_stdout_capture_wired design_output_path codex_consumable_design_output; }\n"
        "if [ \"${1:-}\" = '--check' ]; then\n"
        "  validate_kiro_prompt \"$2\"\n"
        "  echo \"kiro worker: prompt validation passed for ${required_kiro_model}\"\n"
        "  exit 0\n"
        "fi\n"
    )
    _make_executable(
        tmp_path / "scripts" / "ai-run-kiro-design.sh",
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "prompt_file=\"$1\"\n"
        "./scripts/ai-worker-kiro.sh --check \"$prompt_file\"\n"
        "exec ./scripts/ai-worker-kiro.sh \"$prompt_file\"\n",
    )


def _seed_worker_clis(tmp_path: Path, *, model_rows: list[str]) -> Path:
    bin_dir = tmp_path / "bin"
    _make_executable(bin_dir / "cursor-agent", "#!/usr/bin/env bash\necho cursor-agent\n")
    _make_executable(
        bin_dir / "kiro",
        "#!/usr/bin/env bash\n"
        "if [ \"${1:-}\" = 'chat' ] && [ \"${2:-}\" = '--help' ]; then\n"
        "  echo 'Usage: kiro chat [options] [prompt]'\n"
        "  exit 0\n"
        "fi\n"
        "echo 'unexpected kiro args' >&2\n"
        "exit 2\n",
    )
    models_output = "\\n".join(model_rows)
    _make_executable(
        bin_dir / "opencode",
        "#!/usr/bin/env bash\n"
        "case \"${1:-}\" in\n"
        "  --version) echo '1.17.7' ;;\n"
        f"  models) printf '%b\\n' '{models_output}' ;;\n"
        "  *) echo 'unexpected opencode args' >&2; exit 2 ;;\n"
        "esac\n",
    )
    return bin_dir


def _prepend_path(bin_dir: Path) -> str:
    return str(bin_dir) + os.pathsep + "/usr/bin:/bin"


def test_preflight_passes_when_configured_opencode_model_is_registered(tmp_path: Path, monkeypatch) -> None:
    _seed_orchestration_files(tmp_path)
    bin_dir = _seed_worker_clis(tmp_path, model_rows=["opencode-go/minimax-m3", "opencode/big-pickle"])
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("PATH", _prepend_path(bin_dir))
    monkeypatch.setenv("AI_WORKER_OPENCODE_MODEL", "opencode-go/minimax-m3")
    monkeypatch.setenv("AI_WORKER_OPENCODE_XDG_DATA_HOME", str(tmp_path / "xdg"))

    payload = build_preflight_module.build_report()

    assert payload["contract_pass"] is True
    assert payload["checks"]["opencode_worker_configured_model_available"] is True
    assert payload["summary"]["opencode_configured_model"] == "opencode-go/minimax-m3"
    assert payload["summary"]["opencode_configured_model_available"] is True
    assert payload["summary"]["opencode_assignment_routed_to_cursor"] is True
    assert payload["summary"]["opencode_assignment_cursor_model"] == "composer-2.5"
    assert payload["checks"]["code_improvement_design_stage_configured"] is True
    assert payload["checks"]["code_improvement_implementation_stage_configured"] is True
    assert payload["checks"]["code_improvement_verification_stage_configured"] is True
    assert payload["summary"]["kiro_design_model"] == "opus-4.8"
    assert payload["summary"]["cursor_implementation_model"] == "composer-2.5"
    assert payload["summary"]["codex_verification_model"] == "gpt-5.5"
    assert payload["summary"]["codex_verification_reasoning_effort"] == "xhigh"
    assert payload["summary"]["code_improvement_pipeline"] == [
        {
            "stage": "kiro",
            "model": "opus-4.8",
            "responsibility": "compact_design_only",
            "prompt_template": "docs/ai/prompts/kiro_design_slice.md",
            "run_wrapper": "scripts/ai-run-kiro-design.sh",
        },
        {
            "stage": "cursor",
            "model": "composer-2.5",
            "responsibility": "scoped_implementation",
            "prompt_template": "docs/ai/prompts/cursor_worker_slice.md",
        },
        {
            "stage": "codex",
            "model": "gpt-5.5",
            "reasoning_effort": "xhigh",
            "responsibility": "diff_evidence_claim_boundary_review",
        },
    ]
    assert payload["summary"]["cursor_remote_api_host"] == "api2.cursor.sh"
    assert payload["summary"]["cursor_host_bridge_ready"] is False
    assert payload["summary"]["cursor_dns_permission_owner"] == "host_or_codex_session_configuration"
    assert payload["summary"]["cursor_dns_permission_grantable_from_codex"] is False
    assert payload["checks"]["cursor_dns_permission_grantable_from_codex"] is False
    assert payload["checks"]["kiro_cli_present"] is True
    assert payload["checks"]["kiro_chat_command_present"] is True
    assert payload["checks"]["kiro_worker_wrapper_present"] is True
    assert payload["checks"]["kiro_worker_wrapper_verifies_opus48"] is True
    assert payload["checks"]["kiro_worker_wrapper_runs_automatic_prelaunch_check"] is True
    assert payload["checks"]["kiro_worker_wrapper_enforces_opus48_confirmation"] is True
    assert payload["checks"]["kiro_design_template_validates_with_wrapper"] is True
    assert payload["checks"]["kiro_headless_stdout_capture_wired"] is True
    assert payload["summary"]["kiro_cli"] == "kiro"
    assert payload["summary"]["kiro_chat_command_available"] is True
    assert payload["summary"]["kiro_design_invocation_mode"] == "kiro_checked_run_wrapper_launch"
    assert payload["checks"]["kiro_design_run_wrapper_present"] is True
    assert payload["checks"]["kiro_design_run_wrapper_checks_before_launch"] is True
    assert payload["summary"]["kiro_design_run_wrapper"] == "scripts/ai-run-kiro-design.sh"
    assert payload["summary"]["kiro_design_run_wrapper_present"] is True
    assert payload["summary"]["kiro_design_run_wrapper_checks_before_launch"] is True
    assert payload["summary"]["kiro_worker_wrapper_present"] is True
    assert payload["summary"]["kiro_worker_wrapper_verifies_opus48"] is True
    assert payload["summary"]["kiro_worker_wrapper_runs_automatic_prelaunch_check"] is True
    assert payload["summary"]["kiro_worker_wrapper_enforces_opus48_confirmation"] is True
    assert payload["summary"]["kiro_design_template_validates_with_wrapper"] is True
    assert payload["summary"]["kiro_headless_stdout_capture_wired"] is True
    assert "start_host_bridge_from_network_enabled_host_terminal" in payload["summary"][
        "cursor_dns_failure_fallbacks"
    ]
    assert payload["summary"]["cursor_failure_internal_subagent_fallback_agent_type"] == "worker"
    assert payload["summary"]["cursor_failure_internal_subagent_fallback_model"] == "gpt-5.4-mini"
    assert payload["summary"]["cursor_failure_internal_subagent_fallback_reasoning_effort"] == "xhigh"
    assert payload["checks"]["internal_subagent_fallback_agent_type_configured"] is True
    assert payload["checks"]["internal_subagent_fallback_model_configured"] is True
    assert payload["checks"]["internal_subagent_fallback_reasoning_effort_configured"] is True
    assert payload["diagnostics"]["opencode_model_rows"] == [
        "opencode-go/minimax-m3",
        "opencode/big-pickle",
    ]


def test_preflight_blocks_when_kiro_template_fails_wrapper_validation(
    tmp_path: Path, monkeypatch
) -> None:
    _seed_orchestration_files(tmp_path)
    _write(
        tmp_path / "docs" / "ai" / "prompts" / "kiro_design_slice.md",
        "You are Kiro running as a design-only architect on model `opus-4.8`.\n"
        "Do not edit files.\n",
    )
    bin_dir = _seed_worker_clis(tmp_path, model_rows=["opencode-go/minimax-m3"])
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("PATH", _prepend_path(bin_dir))
    monkeypatch.setenv("AI_WORKER_OPENCODE_MODEL", "opencode-go/minimax-m3")
    monkeypatch.setenv("AI_WORKER_OPENCODE_XDG_DATA_HOME", str(tmp_path / "xdg"))

    payload = build_preflight_module.build_report()

    assert payload["contract_pass"] is False
    assert payload["checks"]["kiro_design_template_validates_with_wrapper"] is False
    assert "kiro_design_template_wrapper_validation_failed" in payload["blockers"]


def test_preflight_blocks_when_kiro_wrapper_lacks_automatic_prelaunch_check(
    tmp_path: Path, monkeypatch
) -> None:
    _seed_orchestration_files(tmp_path)
    _make_executable(
        tmp_path / "scripts" / "ai-worker-kiro.sh",
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "required_kiro_model=\"opus-4.8\"\n"
        "validate_kiro_prompt() {\n"
        "  grep -Fq -- \"model \\`${required_kiro_model}\\`\" \"$1\"\n"
        "  grep -Fq -- 'Do not edit files' \"$1\"\n"
        "  grep -Fq -- 'Do not claim readiness closure' \"$1\"\n"
        "}\n"
        "if [ \"${1:-}\" = '--check' ]; then\n"
        "  validate_kiro_prompt \"$2\"\n"
        "  exit 0\n"
        "fi\n",
    )
    bin_dir = _seed_worker_clis(tmp_path, model_rows=["opencode-go/minimax-m3"])
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("PATH", _prepend_path(bin_dir))
    monkeypatch.setenv("AI_WORKER_OPENCODE_MODEL", "opencode-go/minimax-m3")
    monkeypatch.setenv("AI_WORKER_OPENCODE_XDG_DATA_HOME", str(tmp_path / "xdg"))

    payload = build_preflight_module.build_report()

    assert payload["contract_pass"] is False
    assert payload["checks"]["kiro_worker_wrapper_runs_automatic_prelaunch_check"] is False
    assert "kiro_worker_wrapper_automatic_prelaunch_check_missing" in payload["blockers"]


def test_preflight_blocks_when_kiro_run_wrapper_lacks_check_before_launch(
    tmp_path: Path, monkeypatch
) -> None:
    _seed_orchestration_files(tmp_path)
    _make_executable(
        tmp_path / "scripts" / "ai-run-kiro-design.sh",
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "prompt_file=\"$1\"\n"
        "exec ./scripts/ai-worker-kiro.sh \"$prompt_file\"\n",
    )
    bin_dir = _seed_worker_clis(tmp_path, model_rows=["opencode-go/minimax-m3"])
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("PATH", _prepend_path(bin_dir))
    monkeypatch.setenv("AI_WORKER_OPENCODE_MODEL", "opencode-go/minimax-m3")
    monkeypatch.setenv("AI_WORKER_OPENCODE_XDG_DATA_HOME", str(tmp_path / "xdg"))

    payload = build_preflight_module.build_report()

    assert payload["contract_pass"] is False
    assert payload["checks"]["kiro_design_run_wrapper_checks_before_launch"] is False
    assert "kiro_design_run_wrapper_check_before_launch_missing" in payload["blockers"]


def test_preflight_normalizes_minimax_m3_alias_to_registered_opencode_model(
    tmp_path: Path, monkeypatch
) -> None:
    _seed_orchestration_files(tmp_path)
    bin_dir = _seed_worker_clis(tmp_path, model_rows=["opencode-go/minimax-m3"])
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("PATH", _prepend_path(bin_dir))
    monkeypatch.setenv("AI_WORKER_OPENCODE_MODEL", "minimax 3")
    monkeypatch.setenv("AI_WORKER_OPENCODE_XDG_DATA_HOME", str(tmp_path / "xdg"))

    payload = build_preflight_module.build_report()

    assert payload["contract_pass"] is True
    assert payload["summary"]["opencode_configured_model"] == "opencode-go/minimax-m3"


def test_preflight_normalizes_glm52_alias_to_glm52_model(tmp_path: Path, monkeypatch) -> None:
    _seed_orchestration_files(tmp_path)
    bin_dir = _seed_worker_clis(tmp_path, model_rows=["opencode-go/glm-5.2"])
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("PATH", _prepend_path(bin_dir))
    monkeypatch.setenv("AI_WORKER_OPENCODE_MODEL", "glm 5.2")
    monkeypatch.setenv("AI_WORKER_OPENCODE_XDG_DATA_HOME", str(tmp_path / "xdg"))

    payload = build_preflight_module.build_report()

    assert payload["contract_pass"] is True
    assert payload["summary"]["opencode_configured_model"] == "opencode-go/glm-5.2"


def test_preflight_blocks_when_configured_opencode_model_is_not_registered(
    tmp_path: Path, monkeypatch
) -> None:
    _seed_orchestration_files(tmp_path)
    bin_dir = _seed_worker_clis(tmp_path, model_rows=["opencode/big-pickle"])
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("PATH", _prepend_path(bin_dir))
    monkeypatch.setenv("AI_WORKER_OPENCODE_MODEL", "opencode-go/minimax-m3")
    monkeypatch.setenv("AI_WORKER_OPENCODE_XDG_DATA_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("AI_WORKER_OPENCODE_ASSIGNMENT_MODE", "opencode")

    payload = build_preflight_module.build_report()

    assert payload["contract_pass"] is False
    assert payload["reason_code"] == "BLOCKED"
    assert "opencode_worker_configured_model_unavailable" in payload["blockers"]
    assert payload["checks"]["opencode_model_registry_query_pass"] is True
    assert payload["checks"]["opencode_worker_configured_model_available"] is False
    assert payload["summary"]["opencode_configured_model"] == "opencode-go/minimax-m3"
    assert payload["summary"]["opencode_model_count"] == 1


def test_preflight_uses_deepseek_v4_pro_as_default_model(tmp_path: Path, monkeypatch) -> None:
    _seed_orchestration_files(tmp_path)
    bin_dir = _seed_worker_clis(tmp_path, model_rows=["opencode-go/deepseek-v4-pro"])
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("PATH", _prepend_path(bin_dir))
    monkeypatch.delenv("OPENCODE_MODEL", raising=False)
    monkeypatch.delenv("AI_WORKER_OPENCODE_MODEL", raising=False)
    monkeypatch.setenv("AI_WORKER_OPENCODE_XDG_DATA_HOME", str(tmp_path / "xdg"))

    payload = build_preflight_module.build_report()

    assert payload["summary"]["opencode_configured_model"] == "opencode-go/deepseek-v4-pro"
    assert payload["contract_pass"] is True


def test_preflight_uses_opencode_go_mirror_when_account_store_is_read_only(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _seed_orchestration_files(tmp_path)
    bin_dir = _seed_worker_clis(tmp_path, model_rows=["opencode-go/deepseek-v4-pro"])
    source_home = tmp_path / "snap" / "code" / "247" / ".local" / "share"
    _write(source_home / "opencode" / "auth.json", "{}\n")
    _write(source_home / "opencode" / "account.json", "{}\n")
    tmp_dir = tmp_path / "tmp"
    tmp_dir.mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("PATH", _prepend_path(bin_dir))
    monkeypatch.setenv("XDG_DATA_HOME", str(source_home))
    monkeypatch.setenv("TMPDIR", str(tmp_dir))
    monkeypatch.delenv("AI_WORKER_OPENCODE_XDG_DATA_HOME", raising=False)
    monkeypatch.delenv("OPENCODE_MODEL", raising=False)
    monkeypatch.delenv("AI_WORKER_OPENCODE_MODEL", raising=False)
    monkeypatch.setattr(build_preflight_module, "_opencode_data_home_writable", lambda _path: False)

    payload = build_preflight_module.build_report()

    mirror_home = tmp_dir / "codex-opencode-go-xdg-data"
    assert payload["contract_pass"] is True
    assert payload["summary"]["opencode_configured_model"] == "opencode-go/deepseek-v4-pro"
    assert payload["summary"]["opencode_xdg_data_home"] == str(mirror_home)
    assert (mirror_home / "opencode" / "auth.json").is_symlink()
    assert (mirror_home / "opencode" / "account.json").is_symlink()
    assert os.readlink(mirror_home / "opencode" / "auth.json") == str(source_home / "opencode" / "auth.json")
    assert os.readlink(mirror_home / "opencode" / "account.json") == str(
        source_home / "opencode" / "account.json"
    )


def test_preflight_reports_cursor_host_bridge_when_ready(tmp_path: Path, monkeypatch) -> None:
    _seed_orchestration_files(tmp_path)
    bin_dir = _seed_worker_clis(tmp_path, model_rows=["opencode-go/deepseek-v4-pro"])
    bridge_dir = tmp_path / "cursor-bridge"
    (bridge_dir / "jobs").mkdir(parents=True)
    (bridge_dir / "done").mkdir()
    _write(bridge_dir / "host-bridge.ready", "12345\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("PATH", _prepend_path(bin_dir))
    monkeypatch.setenv("AI_WORKER_OPENCODE_XDG_DATA_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("AI_WORKER_CURSOR_HOST_BRIDGE_DIR", str(bridge_dir))

    payload = build_preflight_module.build_report()

    assert payload["contract_pass"] is True
    assert payload["checks"]["cursor_host_bridge_ready"] is True
    assert payload["summary"]["cursor_host_bridge_ready"] is True
    assert payload["summary"]["cursor_host_bridge_dir"] == str(bridge_dir)
    assert payload["diagnostics"]["cursor_host_bridge_ready_file"] == str(
        bridge_dir / "host-bridge.ready"
    )


def test_kiro_run_wrapper_performs_opus48_check_before_launch(
    tmp_path: Path, monkeypatch
) -> None:
    prompt = _write(
        tmp_path / "kiro_design_slice.md",
        "# Kiro Design Slice\n\n"
        "You are Kiro running as a design-only architect on model `opus-4.8`.\n"
        "Do not edit files. Do not claim readiness closure.\n",
    )
    receipt = tmp_path / "kiro-launch.json"
    bin_dir = tmp_path / "bin"
    _make_executable(
        bin_dir / "kiro",
        "#!/usr/bin/env bash\n"
        "if [ \"${1:-}\" = 'chat' ] && [ \"${2:-}\" = '--help' ]; then\n"
        "  echo 'Usage: kiro chat [options] [prompt]'\n"
        "  exit 0\n"
        "fi\n"
        "if [ \"${1:-}\" = 'chat' ] && [ \"${2:-}\" = '--mode' ]; then\n"
        "  printf '%s\\n' 'Design summary' 'Implementation order' 'Candidate files' 'Verification plan' 'Risks and claim boundary' 'Cursor handoff prompt'\n"
        "  exit 0\n"
        "fi\n"
        "echo 'unexpected kiro args' >&2\n"
        "exit 2\n",
    )
    monkeypatch.setenv("PATH", _prepend_path(bin_dir))

    result = subprocess.run(
        [
            str(SCRIPT_PATH.parent / "ai-run-kiro-design.sh"),
            str(prompt),
            str(receipt),
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    assert "kiro worker: prompt validation passed for opus-4.8" in result.stdout
    assert "kiro worker: wrapper prelaunch validation passed for opus-4.8" in result.stdout
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    assert payload["kiro_model_target"] == "opus-4.8"
    assert payload["model_target_source"] == "ai-worker-kiro.sh required_kiro_model"
    assert payload["wrapper_validation_mode"] == "automatic_prelaunch_before_kiro_chat"
    assert payload["wrapper_prelaunch_check_passed"] is True
    assert payload["wrapper_enforced_model_confirmation"] is True
    assert payload["kiro_chat_instruction_requires_model_confirmation"] is True
    assert payload["kiro_chat_launch_passed"] is True
    assert payload["headless_stdout_capture"] is True
    assert payload["headless_stdout_capture_wired"] is True
    assert payload["codex_consumable_design_output"] is True
    assert payload["design_output_path"] == str(tmp_path / "kiro-launch.design.md")
    assert (tmp_path / "kiro-launch.design.md").is_file()
    assert payload["design_output_contains_required_sections"] is True
    assert payload["prompt_validation"]["model_line_verified"] is True
    assert payload["equivalent_prompt_check_command"] == [
        "scripts/ai-worker-kiro.sh",
        "--check",
        str(prompt),
    ]
