from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parent.parent
WRAPPER = ROOT / "scripts" / "ai-worker-kiro.sh"
RUN_WRAPPER = ROOT / "scripts" / "ai-run-kiro-design.sh"


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _make_executable(path: Path, text: str) -> Path:
    _write(path, text)
    path.chmod(path.stat().st_mode | 0o755)
    return path


def _prompt(path: Path) -> Path:
    return _write(
        path,
        "You are Kiro running as a design-only architect on model `opus-4.8`.\n"
        "Do not edit files. Do not claim readiness closure.\n",
    )


def test_kiro_wrapper_records_automatic_opus48_prelaunch_check(tmp_path: Path) -> None:
    prompt = _prompt(tmp_path / "kiro_design.md")
    receipt = tmp_path / "kiro_design.kiro-launch.json"
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
        "exit 2\n",
    )
    env = os.environ.copy()
    env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")

    result = subprocess.run(
        [str(WRAPPER), str(prompt), str(receipt)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    assert payload["kiro_model_target"] == "opus-4.8"
    assert payload["kiro_chat_instruction_contains_model_target"] is True
    assert payload["kiro_chat_instruction_requires_model_confirmation"] is True
    assert payload["wrapper_enforced_model_confirmation"] is True
    assert payload["wrapper_validation_mode"] == "automatic_prelaunch_before_kiro_chat"
    assert payload["wrapper_prelaunch_check_passed"] is True
    assert payload["wrapper_validation_passed"] is True
    assert payload["prompt_validation"]["model_line_verified"] is True
    assert payload["prompt_validation"]["design_only_boundary_verified"] is True
    assert payload["prompt_validation"]["readiness_closure_claim_forbidden"] is True
    assert payload["kiro_chat_launch_attempted"] is True
    assert payload["kiro_chat_launch_passed"] is True
    assert payload["headless_stdout_capture"] is True
    assert payload["headless_stdout_capture_wired"] is True
    assert payload["codex_consumable_design_output"] is True
    assert payload["design_output_contains_required_sections"] is True
    assert payload["design_output_path"] == str(
        tmp_path / "kiro_design.kiro-design.md"
    )
    assert (tmp_path / "kiro_design.kiro-design.md").is_file()
    assert payload["design_output_sha256"].startswith("sha256:")
    assert payload["equivalent_prompt_check_command"] == [
        "scripts/ai-worker-kiro.sh",
        "--check",
        str(prompt),
    ]


def test_kiro_run_wrapper_checks_prompt_before_launch(tmp_path: Path) -> None:
    prompt = _prompt(tmp_path / "kiro_design.md")
    receipt = tmp_path / "kiro_design.kiro-launch.json"
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
        "exit 2\n",
    )
    env = os.environ.copy()
    env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")

    result = subprocess.run(
        [str(RUN_WRAPPER), str(prompt), str(receipt)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "prompt validation passed for opus-4.8" in result.stdout
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    assert payload["kiro_model_target"] == "opus-4.8"
    assert payload["wrapper_prelaunch_check_passed"] is True
    assert payload["kiro_chat_launch_passed"] is True
    assert payload["headless_stdout_capture"] is True
    assert payload["codex_consumable_design_output"] is True
    assert payload["design_output_path"] == str(
        tmp_path / "kiro_design.kiro-design.md"
    )


def test_kiro_wrapper_writes_validation_receipt_when_chat_command_is_unavailable(
    tmp_path: Path,
) -> None:
    prompt = _prompt(tmp_path / "kiro_design.md")
    receipt = tmp_path / "kiro_design.kiro-launch.json"
    bin_dir = tmp_path / "bin"
    _make_executable(
        bin_dir / "kiro",
        "#!/usr/bin/env bash\n"
        "echo 'chat unavailable' >&2\n"
        "exit 2\n",
    )
    env = os.environ.copy()
    env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")

    result = subprocess.run(
        [str(WRAPPER), str(prompt), str(receipt)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    assert payload["kiro_cli_found"] is True
    assert payload["kiro_chat_command_available"] is False
    assert payload["kiro_chat_launch_attempted"] is False
    assert payload["kiro_chat_launch_passed"] is False
    assert payload["wrapper_prelaunch_check_passed"] is True
    assert payload["kiro_model_target"] == "opus-4.8"
