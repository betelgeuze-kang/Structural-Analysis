#!/usr/bin/env python3
"""Build a direct Phase 6 platform replay receipt on the executing OS."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform as platform_module
import subprocess
import sys
import tempfile
import time
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from release_evidence_metadata import file_sha256, release_evidence_metadata  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
PHASE3_REPRO_BUNDLE = (
    PRODUCTIZATION / "phase3_benchmark_factory_seed_reproducibility_bundle.json"
)
SCHEMA_VERSION = "phase6-linux-windows-platform-replay-receipt.v1"
DEFAULT_OUT_BY_PLATFORM = {
    "linux": PRODUCTIZATION / "phase6_linux_platform_replay_receipt.json",
    "windows": PRODUCTIZATION / "phase6_windows_platform_replay_receipt.json",
}
SUPPORTED_PLATFORMS = tuple(DEFAULT_OUT_BY_PLATFORM)


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _load_json(repo_root: Path, path: Path) -> dict[str, Any]:
    resolved = path if path.is_absolute() else repo_root / path
    if not resolved.exists():
        return {}
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _phase3_expectations(repro_bundle: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    expected_scorecard = (
        repro_bundle.get("expected_scorecard")
        if isinstance(repro_bundle.get("expected_scorecard"), dict)
        else {}
    )
    stable_artifact_checksums = (
        repro_bundle.get("stable_artifact_checksums")
        if isinstance(repro_bundle.get("stable_artifact_checksums"), dict)
        else {}
    )
    return expected_scorecard, stable_artifact_checksums


def _actual_platform() -> str:
    system = platform_module.system().lower()
    if system.startswith("win"):
        return "windows"
    if system.startswith("linux"):
        return "linux"
    return system or "unknown"


def _git_head(repo_root: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return ""


def _git_dirty_paths(repo_root: Path) -> list[str]:
    try:
        output = subprocess.check_output(
            ["git", "status", "--short", "--untracked-files=normal"],
            cwd=repo_root,
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        return ["git_status_unavailable"]
    return [line.rstrip() for line in output.splitlines() if line.strip()]


def _node_version() -> str:
    try:
        return subprocess.check_output(
            ["node", "--version"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return "not_available"


def _command_env(replay_root: Path) -> dict[str, str]:
    env = dict(os.environ)
    src_path = str(replay_root / "src")
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = src_path if not existing else src_path + os.pathsep + existing
    return env


def _run_command(argv: list[str], *, cwd: Path, env: dict[str, str]) -> dict[str, Any]:
    started = time.monotonic()
    try:
        completed = subprocess.run(
            argv,
            cwd=cwd,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        elapsed = time.monotonic() - started
        return {
            "command": " ".join(argv),
            "argv": argv,
            "cwd": cwd.as_posix(),
            "return_code": int(completed.returncode),
            "elapsed_seconds": round(elapsed, 3),
            "stdout_excerpt": completed.stdout[-4000:],
            "stderr_excerpt": completed.stderr[-4000:],
        }
    except Exception as exc:
        elapsed = time.monotonic() - started
        return {
            "command": " ".join(argv),
            "argv": argv,
            "cwd": cwd.as_posix(),
            "return_code": 127,
            "elapsed_seconds": round(elapsed, 3),
            "stdout_excerpt": "",
            "stderr_excerpt": f"{exc.__class__.__name__}: {exc}",
        }


def _commands_return_code_zero(commands: list[dict[str, Any]]) -> bool:
    return bool(commands) and all(int(row.get("return_code", 1)) == 0 for row in commands)


def _output_checksums(paths: dict[str, Path]) -> dict[str, str]:
    return {
        key: file_sha256(path)
        for key, path in sorted(paths.items())
        if path.exists() and path.is_file()
    }


def _run_replay_commands(
    *,
    repo_root: Path,
    source_commit_sha: str,
) -> tuple[list[dict[str, Any]], dict[str, str], str, list[str], list[str]]:
    commands: list[dict[str, Any]] = []
    replay_environment = "current_checkout"
    setup_blockers: list[str] = []
    current_head = _git_head(repo_root)
    temp_dir: tempfile.TemporaryDirectory[str] | None = None
    replay_root = repo_root
    if source_commit_sha and current_head and current_head != source_commit_sha:
        temp_dir = tempfile.TemporaryDirectory(prefix="phase6-platform-replay-")
        replay_root = Path(temp_dir.name) / "source"
        add_result = _run_command(
            ["git", "worktree", "add", "--detach", replay_root.as_posix(), source_commit_sha],
            cwd=repo_root,
            env=dict(os.environ),
        )
        commands.append(add_result)
        if int(add_result["return_code"]) != 0:
            setup_blockers.append("replay_source_worktree_checkout_failed")
            if temp_dir is not None:
                temp_dir.cleanup()
            return commands, {}, "temporary_git_worktree_checkout_failed", [], setup_blockers
        replay_environment = "temporary_git_worktree_at_phase3_source_commit"
    try:
        with tempfile.TemporaryDirectory(prefix="phase3-seed-replay-") as out_dir:
            out_root = Path(out_dir)
            generated_paths = {
                "manifest": out_root / "phase3_seed_manifest.json",
                "scorecard": out_root / "phase3_seed_scorecard.json",
                "summary": out_root / "phase3_seed_runner_summary.json",
            }
            env = _command_env(replay_root)
            commands.extend(
                [
                    _run_command(
                        [
                            sys.executable,
                            "scripts/build_phase3_benchmark_factory_artifacts.py",
                            "--check",
                        ],
                        cwd=replay_root,
                        env=env,
                    ),
                    _run_command(
                        [
                            sys.executable,
                            "-m",
                            "structural_analysis.benchmark.cli",
                            "--manifest-out",
                            generated_paths["manifest"].as_posix(),
                            "--scorecard-out",
                            generated_paths["scorecard"].as_posix(),
                            "--summary-out",
                            generated_paths["summary"].as_posix(),
                            "--fail-blocked",
                        ],
                        cwd=replay_root,
                        env=env,
                    ),
                ]
            )
            generated_checksums = _output_checksums(generated_paths)
        dirty_paths = _git_dirty_paths(replay_root)
        return commands, generated_checksums, replay_environment, dirty_paths, setup_blockers
    finally:
        if temp_dir is not None:
            _run_command(
                ["git", "worktree", "remove", "--force", replay_root.as_posix()],
                cwd=repo_root,
                env=dict(os.environ),
            )
            temp_dir.cleanup()


def build_phase6_platform_replay_receipt(
    *,
    repo_root: Path = ROOT,
    platform_name: str,
    actual_platform: str | None = None,
    dirty_paths: list[str] | None = None,
    command_results: list[dict[str, Any]] | None = None,
    generated_output_checksums: dict[str, str] | None = None,
    replay_environment: str | None = None,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    requested_platform = platform_name.lower()
    actual = (actual_platform or _actual_platform()).lower()
    repro_bundle = _load_json(repo_root, PHASE3_REPRO_BUNDLE)
    expected_scorecard, stable_artifact_checksums = _phase3_expectations(repro_bundle)
    source_commit_sha = str(repro_bundle.get("source_commit_sha", ""))
    setup_blockers: list[str] = []
    if command_results is None:
        (
            commands,
            generated_checksums,
            replay_env,
            replay_dirty_paths,
            setup_blockers,
        ) = _run_replay_commands(
            repo_root=repo_root,
            source_commit_sha=source_commit_sha,
        )
    else:
        commands = command_results
        generated_checksums = generated_output_checksums or {}
        replay_env = replay_environment or "unit_test_injected_replay"
        replay_dirty_paths = dirty_paths if dirty_paths is not None else []
    if dirty_paths is not None:
        replay_dirty_paths = dirty_paths
    commands_zero = _commands_return_code_zero(commands)
    blockers: list[str] = []
    if requested_platform not in SUPPORTED_PLATFORMS:
        blockers.append(f"unsupported_platform:{requested_platform}")
    if actual != requested_platform:
        blockers.append(f"actual_platform_mismatch:{actual}!={requested_platform}")
    if not source_commit_sha:
        blockers.append("phase3_reproducibility_bundle_source_commit_missing")
    if not expected_scorecard:
        blockers.append("phase3_reproducibility_bundle_expected_scorecard_missing")
    if not stable_artifact_checksums:
        blockers.append("phase3_reproducibility_bundle_stable_checksums_missing")
    blockers.extend(setup_blockers)
    if not commands:
        blockers.append("replay_commands_not_executed")
    if not commands_zero:
        blockers.append("replay_command_return_code_nonzero")
    if replay_dirty_paths:
        blockers.append(f"replay_worktree_dirty_path_count={len(replay_dirty_paths)}")
    contract_pass = not blockers
    metadata = release_evidence_metadata(
        input_paths=[
            PHASE3_REPRO_BUNDLE,
            Path("scripts/build_phase6_platform_replay_receipt.py"),
            Path("scripts/build_phase6_linux_windows_parity_status.py"),
        ],
        reused_evidence=False,
        reuse_policy="phase6_platform_replay_receipt_runs_phase3_seed_replay_commands",
        repo_root=repo_root,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        **metadata,
        "receipt_builder_source_commit_sha": metadata.get("source_commit_sha", ""),
        "platform": requested_platform,
        "actual_platform": actual,
        "os_name": platform_module.system(),
        "os_version": platform_module.platform(),
        "python_version": platform_module.python_version(),
        "node_version": _node_version(),
        "source_commit_sha": source_commit_sha,
        "platform_identity": {
            "platform": requested_platform,
            "os_name": platform_module.system(),
            "os_version": platform_module.platform(),
            "python_version": platform_module.python_version(),
            "replay_environment": replay_env,
            "receipt_origin": "scripts/build_phase6_platform_replay_receipt.py",
            "source_commit_sha": source_commit_sha,
            "commands_return_code_zero": commands_zero,
        },
        "working_tree_clean": not replay_dirty_paths,
        "working_tree_clean_scope": replay_env,
        "local_dirty_inputs": replay_dirty_paths,
        "local_dirty_inputs_scope": replay_env,
        "commands": commands,
        "generated_output_checksums": generated_checksums,
        "stable_artifact_checksums": stable_artifact_checksums,
        "expected_scorecard": expected_scorecard,
        "contract_pass": contract_pass,
        "blockers": blockers,
        "developer_preview_release_candidate_claim": False,
        "claim_boundary": (
            "This platform replay receipt is valid only for the OS that executed "
            "the replay commands. It cannot be copied across platforms, cannot "
            "close Linux/Windows parity alone, and does not promote Developer "
            "Preview RC readiness until the aggregate parity status passes."
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", required=True, choices=SUPPORTED_PLATFORMS)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    parser.add_argument(
        "--allow-platform-mismatch",
        action="store_true",
        help="Write a blocked diagnostic receipt even when the executing OS differs.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    actual = _actual_platform()
    if actual != args.platform and not args.allow_platform_mismatch:
        print(
            f"Refusing to write {args.platform} receipt on actual platform {actual}.",
            file=sys.stderr,
        )
        return 2
    out = args.out or DEFAULT_OUT_BY_PLATFORM[args.platform]
    payload = build_phase6_platform_replay_receipt(
        repo_root=ROOT,
        platform_name=args.platform,
        actual_platform=actual,
    )
    resolved = out if out.is_absolute() else ROOT / out
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(_json_text(payload), encoding="utf-8")
    if args.json:
        print(_json_text(payload), end="")
    else:
        print(
            "Phase 6 platform replay receipt: "
            f"{payload['platform']} | "
            f"{'PASS' if payload['contract_pass'] else 'BLOCKED'}"
        )
    if args.fail_blocked and not payload["contract_pass"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
