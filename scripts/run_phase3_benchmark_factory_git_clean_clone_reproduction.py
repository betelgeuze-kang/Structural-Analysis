#!/usr/bin/env python3
"""Run Phase 3 benchmark factory seed commands from a real local git clone."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
for candidate in (SCRIPT_DIR, SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from build_phase3_benchmark_factory_artifacts import _stable_payload_checksum  # noqa: E402
from phase3_benchmark_reproduction_contract import (  # noqa: E402
    GIT_CLEAN_CLONE_REQUIRED_INPUTS,
    PRODUCTIZATION,
)
from release_evidence_metadata import git_head, input_checksums  # noqa: E402


DEFAULT_BUNDLE = PRODUCTIZATION / "phase3_benchmark_factory_seed_reproducibility_bundle.json"
DEFAULT_OUT = PRODUCTIZATION / "phase3_benchmark_factory_seed_git_clean_clone_reproduction.json"
SCHEMA_VERSION = "phase3-benchmark-factory-git-clean-clone-reproduction.v1"

PATH_ROLE_SOURCE_INPUT_REPORT = "source_input_report"
PATH_ROLE_GENERATED_PRODUCTIZATION_EVIDENCE = "generated_productization_evidence"
PATH_ROLE_REPRODUCTION_BUILD_SCRIPT = "reproduction_build_script"
PATH_ROLE_PACKAGE_CONFIG_CORE_PACKAGE = "package_config_core_package"
PATH_ROLE_VIEWER_GUI_TRACEABILITY_CONTRACT = "viewer_gui_traceability_contract"
PATH_ROLE_FOCUSED_TEST = "focused_test"
REQUIRED_PATH_ROLES = (
    PATH_ROLE_SOURCE_INPUT_REPORT,
    PATH_ROLE_GENERATED_PRODUCTIZATION_EVIDENCE,
    PATH_ROLE_REPRODUCTION_BUILD_SCRIPT,
    PATH_ROLE_PACKAGE_CONFIG_CORE_PACKAGE,
    PATH_ROLE_VIEWER_GUI_TRACEABILITY_CONTRACT,
    PATH_ROLE_FOCUSED_TEST,
)

REQUIRED_GIT_CLEAN_CLONE_INPUTS = GIT_CLEAN_CLONE_REQUIRED_INPUTS


def _required_path_role(path: Path) -> str:
    key = path.as_posix()
    if key.startswith("tests/") and key.endswith(".py"):
        return PATH_ROLE_FOCUSED_TEST
    if key.startswith("scripts/") and key.endswith(".py"):
        return PATH_ROLE_REPRODUCTION_BUILD_SCRIPT
    if key in {"package.json", "pyproject.toml", "pytest.ini", "setup.cfg"}:
        return PATH_ROLE_PACKAGE_CONFIG_CORE_PACKAGE
    if key == "src/structural_analysis" or key.startswith("src/structural_analysis/"):
        return PATH_ROLE_PACKAGE_CONFIG_CORE_PACKAGE
    if key.startswith("src/structure-viewer/") and key.endswith(".js"):
        return PATH_ROLE_VIEWER_GUI_TRACEABILITY_CONTRACT
    productization_prefix = f"{PRODUCTIZATION.as_posix()}/"
    if key.startswith(productization_prefix):
        return PATH_ROLE_GENERATED_PRODUCTIZATION_EVIDENCE
    if key.startswith("implementation/phase1/open_data/"):
        return PATH_ROLE_SOURCE_INPUT_REPORT
    if key.startswith("implementation/phase1/"):
        return PATH_ROLE_SOURCE_INPUT_REPORT
    raise ValueError(f"unclassified_required_git_clean_clone_input:{key}")


def _required_path_roles(required_paths: list[Path]) -> dict[str, str]:
    return {path.as_posix(): _required_path_role(path) for path in required_paths}


def _required_path_blocker_summary_by_role(
    preflight: dict[str, Any],
    path_roles: dict[str, str],
) -> dict[str, dict[str, Any]]:
    summary = {
        role: {
            "untracked_or_missing_paths": [],
            "dirty_paths": [],
            "blocker_count": 0,
        }
        for role in REQUIRED_PATH_ROLES
    }
    for path in preflight.get("untracked_or_missing_paths") or []:
        role = path_roles[path]
        summary[role]["untracked_or_missing_paths"].append(path)
        summary[role]["blocker_count"] += 1
    for path in preflight.get("dirty_paths") or []:
        role = path_roles[path]
        summary[role]["dirty_paths"].append(path)
        summary[role]["blocker_count"] += 1
    for role in summary.values():
        role["untracked_or_missing_paths"] = sorted(role["untracked_or_missing_paths"])
        role["dirty_paths"] = sorted(role["dirty_paths"])
    return summary


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object.")
    return payload


def _strip_volatile(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {
            key: _strip_volatile(value)
            for key, value in payload.items()
            if key
            not in {
                "clone_checkout_path",
                "elapsed_seconds",
                "generated_at",
                "stdout_excerpt",
                "stderr_excerpt",
            }
        }
    if isinstance(payload, list):
        return [_strip_volatile(item) for item in payload]
    return payload


def _run_git(args: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True, check=False)


def _run_command(command: list[str], *, cwd: Path) -> dict[str, Any]:
    started = time.monotonic()
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{cwd / 'src'}{os.pathsep}{env.get('PYTHONPATH', '')}".rstrip(os.pathsep)
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    return {
        "command": " ".join(command),
        "return_code": completed.returncode,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "stdout_excerpt": completed.stdout[-4000:],
        "stderr_excerpt": completed.stderr[-4000:],
    }


def _repo_relative(path: Path, *, repo_root: Path) -> Path | None:
    resolved = path if path.is_absolute() else repo_root / path
    try:
        return resolved.resolve().relative_to(repo_root.resolve())
    except ValueError:
        return path if not path.is_absolute() else None


def _path_has_tracked_files(repo_root: Path, path: Path) -> bool:
    if (repo_root / path).is_file():
        result = _run_git(["ls-files", "--error-unmatch", path.as_posix()], cwd=repo_root)
        return result.returncode == 0
    result = _run_git(["ls-files", "--", path.as_posix()], cwd=repo_root)
    return bool(result.stdout.strip())


def _status_short(repo_root: Path, path: Path) -> list[str]:
    result = _run_git(["status", "--short", "--", path.as_posix()], cwd=repo_root)
    if result.returncode != 0:
        return [f"git_status_failed:{result.stderr.strip()}"]
    return [line for line in result.stdout.splitlines() if line.strip()]


def _required_paths(bundle_path: Path, *, repo_root: Path) -> list[Path]:
    paths = list(REQUIRED_GIT_CLEAN_CLONE_INPUTS)
    bundle_relative = _repo_relative(bundle_path, repo_root=repo_root)
    if bundle_relative is not None and bundle_relative not in paths:
        paths.append(bundle_relative)
    return sorted(paths, key=lambda item: item.as_posix())


def _preflight_git_clean_clone(repo_root: Path, required_paths: list[Path]) -> dict[str, Any]:
    blockers: list[str] = []
    tracked_paths: list[str] = []
    untracked_or_missing_paths: list[str] = []
    dirty_paths: list[str] = []
    path_status: dict[str, dict[str, Any]] = {}

    inside = _run_git(["rev-parse", "--is-inside-work-tree"], cwd=repo_root)
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        return {
            "pass": False,
            "tracked_paths": [],
            "untracked_or_missing_paths": [],
            "dirty_paths": [],
            "path_status": {},
            "blockers": ["source_repo_not_git_worktree"],
        }

    for path in required_paths:
        key = path.as_posix()
        tracked = _path_has_tracked_files(repo_root, path)
        status_lines = _status_short(repo_root, path)
        dirty = tracked and bool(status_lines)
        if tracked:
            tracked_paths.append(key)
        else:
            untracked_or_missing_paths.append(key)
            blockers.append(f"required_path_not_tracked:{key}")
        if dirty:
            dirty_paths.append(key)
            blockers.append(f"required_path_has_uncommitted_changes:{key}")
        path_status[key] = {
            "path_role": _required_path_role(path),
            "tracked": tracked,
            "status_short": status_lines,
        }

    return {
        "pass": not blockers,
        "tracked_paths": tracked_paths,
        "untracked_or_missing_paths": untracked_or_missing_paths,
        "dirty_paths": dirty_paths,
        "path_status": path_status,
        "blockers": blockers,
    }


def _role_rows(paths: list[str]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in paths:
        rows.append({"path": path, "role": _required_path_role(Path(path))})
    return rows


def _role_counts(rows: list[dict[str, str]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        role = row["role"]
        counts[role] = counts.get(role, 0) + 1
    return dict(sorted(counts.items()))


def _preflight_action_summary(preflight: dict[str, Any]) -> dict[str, Any]:
    untracked_or_missing = list(preflight.get("untracked_or_missing_paths") or [])
    dirty_tracked = list(preflight.get("dirty_paths") or [])
    untracked_or_missing_roles = _role_rows(untracked_or_missing)
    dirty_tracked_roles = _role_rows(dirty_tracked)
    return {
        "required_commit_or_add_path_count": len(untracked_or_missing),
        "required_commit_or_add_paths": untracked_or_missing,
        "required_commit_or_add_role_counts": _role_counts(untracked_or_missing_roles),
        "required_commit_or_add_path_roles": untracked_or_missing_roles,
        "required_dirty_tracked_path_count": len(dirty_tracked),
        "required_dirty_tracked_paths": dirty_tracked,
        "required_dirty_tracked_role_counts": _role_counts(dirty_tracked_roles),
        "required_dirty_tracked_path_roles": dirty_tracked_roles,
        "can_replay_from_git_head_without_local_worktree": (
            not untracked_or_missing and not dirty_tracked
        ),
        "next_action": (
            "track_or_commit_required_inputs_then_rerun"
            if untracked_or_missing
            else (
                "resolve_or_commit_dirty_required_inputs_then_rerun"
                if dirty_tracked
                else "rerun_git_clean_clone_reproduction"
            )
        ),
    }


def _release_control_cleanup_plan(
    preflight: dict[str, Any],
    blocker_summary_by_role: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    untracked_or_missing = list(preflight.get("untracked_or_missing_paths") or [])
    dirty_tracked = list(preflight.get("dirty_paths") or [])
    return {
        "status": "blocked" if untracked_or_missing or dirty_tracked else "ready",
        "codex_commit_or_push_performed": False,
        "human_git_action_required": bool(untracked_or_missing or dirty_tracked),
        "git_clean_clone_gate_can_pass_after_cleanup": bool(
            not untracked_or_missing and not dirty_tracked
        ),
        "candidate_release_control_commit_set": sorted(
            {*untracked_or_missing, *dirty_tracked}
        ),
        "candidate_release_control_commit_set_count": len(
            {*untracked_or_missing, *dirty_tracked}
        ),
        "track_or_add_required_paths": untracked_or_missing,
        "resolve_or_commit_dirty_tracked_paths": dirty_tracked,
        "blocker_summary_by_role": blocker_summary_by_role,
        "next_verification_commands": [
            "python3 scripts/build_phase3_benchmark_factory_artifacts.py --check",
            "python3 scripts/run_phase3_benchmark_factory_clean_checkout_reproduction.py --check",
            "python3 scripts/run_phase3_benchmark_factory_git_clean_clone_reproduction.py --check",
        ],
        "claim_boundary": (
            "This plan identifies local Git cleanup needed before the Phase 3 seed artifacts "
            "can replay from a real Git HEAD clone. Codex did not commit, push, release, or "
            "promote readiness. The gate remains blocked until every required input is tracked "
            "and clean in Git."
        ),
    }


def _run_git_clean_clone_replay(
    *,
    repo_root: Path,
    source_commit: str,
    replay_source_commit: str,
    keep_checkout: bool,
) -> dict[str, Any]:
    clone_parent = Path(tempfile.mkdtemp(prefix="phase3-benchmark-git-clean-clone-", dir="/tmp"))
    checkout_root = clone_parent / "checkout"
    command_results: list[dict[str, Any]] = []
    generated_artifact_checksums: dict[str, str] = {}
    blockers: list[str] = []
    retained_path = ""
    try:
        clone_result = _run_command(["git", "clone", "--no-local", "--quiet", str(repo_root), str(checkout_root)], cwd=clone_parent)
        command_results.append(clone_result)
        if clone_result["return_code"] == 0:
            commands = [
                [
                    "python3",
                    "scripts/build_phase3_buildingsmart_ifc_acquisition_receipt.py",
                    "--source-commit-sha",
                    replay_source_commit,
                ],
                [
                    "python3",
                    "scripts/build_phase3_buildingsmart_ifc_acquisition_receipt.py",
                    "--check",
                    "--source-commit-sha",
                    replay_source_commit,
                ],
                [
                    "python3",
                    "scripts/build_phase3_buildingsmart_dirty_ifc_acquisition_receipt.py",
                    "--source-commit-sha",
                    replay_source_commit,
                ],
                [
                    "python3",
                    "scripts/build_phase3_buildingsmart_dirty_ifc_acquisition_receipt.py",
                    "--check",
                    "--source-commit-sha",
                    replay_source_commit,
                ],
                [
                    "python3",
                    "scripts/build_phase3_ifc_source_license_receipt.py",
                    "--source-commit-sha",
                    replay_source_commit,
                ],
                [
                    "python3",
                    "scripts/build_phase3_ifc_source_license_receipt.py",
                    "--check",
                    "--source-commit-sha",
                    replay_source_commit,
                ],
                [
                    "python3",
                    "scripts/build_phase3_ifc_import_health_execution_receipt.py",
                    "--source-commit-sha",
                    replay_source_commit,
                ],
                [
                    "python3",
                    "scripts/build_phase3_ifc_import_health_execution_receipt.py",
                    "--check",
                    "--source-commit-sha",
                    replay_source_commit,
                ],
                [
                    "python3",
                    "scripts/build_phase3_opensees_source_license_receipt.py",
                    "--source-commit-sha",
                    replay_source_commit,
                ],
                [
                    "python3",
                    "scripts/build_phase3_opensees_source_license_receipt.py",
                    "--check",
                    "--source-commit-sha",
                    replay_source_commit,
                ],
                [
                    "python3",
                    "scripts/build_phase4_commercial_comparison_import_template.py",
                    "--source-commit-sha",
                    replay_source_commit,
                ],
                [
                    "python3",
                    "scripts/build_phase4_commercial_comparison_import_template.py",
                    "--check",
                    "--source-commit-sha",
                    replay_source_commit,
                ],
                [
                    "python3",
                    "scripts/build_phase4_analytic_physical_fallback_scorecard.py",
                    "--source-commit-sha",
                    replay_source_commit,
                ],
                [
                    "python3",
                    "scripts/build_phase4_analytic_physical_fallback_scorecard.py",
                    "--check",
                    "--source-commit-sha",
                    replay_source_commit,
                ],
                [
                    "python3",
                    "scripts/build_phase4_commercial_operator_reference_contract.py",
                    "--source-commit-sha",
                    replay_source_commit,
                ],
                [
                    "python3",
                    "scripts/build_phase4_commercial_operator_reference_contract.py",
                    "--check",
                    "--source-commit-sha",
                    replay_source_commit,
                ],
                [
                    "python3",
                    "scripts/build_phase4_commercial_operator_reference_ingest_validator.py",
                    "--source-commit-sha",
                    replay_source_commit,
                ],
                [
                    "python3",
                    "scripts/build_phase4_commercial_operator_reference_ingest_validator.py",
                    "--check",
                    "--source-commit-sha",
                    replay_source_commit,
                ],
                [
                    "python3",
                    "scripts/build_phase3_benchmark_acquisition_artifacts.py",
                    "--source-commit-sha",
                    replay_source_commit,
                ],
                [
                    "python3",
                    "scripts/build_phase3_benchmark_factory_artifacts.py",
                    "--source-commit-sha",
                    replay_source_commit,
                ],
                [
                    "python3",
                    "scripts/build_phase3_benchmark_acquisition_artifacts.py",
                    "--check",
                    "--source-commit-sha",
                    replay_source_commit,
                ],
                [
                    "python3",
                    "scripts/build_phase3_benchmark_factory_artifacts.py",
                    "--check",
                    "--source-commit-sha",
                    replay_source_commit,
                ],
                [
                    "python3",
                    "scripts/run_phase3_benchmark_factory_clean_checkout_reproduction.py",
                    "--source-commit-sha",
                    replay_source_commit,
                ],
                [
                    "python3",
                    "-m",
                    "pytest",
                    "-q",
                    "tests/test_build_phase3_benchmark_acquisition_artifacts.py",
                    "tests/test_build_phase3_benchmark_factory_artifacts.py",
                    "tests/test_build_phase3_buildingsmart_ifc_acquisition_receipt.py",
                    "tests/test_build_phase3_buildingsmart_dirty_ifc_acquisition_receipt.py",
                    "tests/test_build_phase3_ifc_source_license_receipt.py",
                    "tests/test_build_phase3_ifc_import_health_execution_receipt.py",
                    "tests/test_build_phase3_opensees_source_license_receipt.py",
                    "tests/test_build_phase4_commercial_comparison_import_template.py",
                    "tests/test_build_phase4_analytic_physical_fallback_scorecard.py",
                    "tests/test_build_phase4_commercial_operator_reference_contract.py",
                    "tests/test_build_phase4_commercial_operator_reference_ingest_validator.py",
                ],
                [
                    "python3",
                    "-m",
                    "ruff",
                    "check",
                    "src/structural_analysis/benchmark/acquisition.py",
                    "src/structural_analysis/benchmark/factory.py",
                    "scripts/build_phase3_benchmark_acquisition_artifacts.py",
                    "scripts/build_phase3_benchmark_factory_artifacts.py",
                    "scripts/build_phase3_buildingsmart_ifc_acquisition_receipt.py",
                    "scripts/build_phase3_buildingsmart_dirty_ifc_acquisition_receipt.py",
                    "scripts/build_phase3_ifc_source_license_receipt.py",
                    "scripts/build_phase3_ifc_import_health_execution_receipt.py",
                    "scripts/build_phase3_ifc_query_gui_readiness_receipt.py",
                    "scripts/build_phase3_medium_model_scorecard_readiness_receipt.py",
                    "scripts/build_phase3_large_model_runner_readiness_receipt.py",
                    "scripts/build_phase3_opensees_source_license_receipt.py",
                    "scripts/build_phase4_commercial_comparison_import_template.py",
                    "scripts/build_phase4_commercial_cross_solver_readiness_receipt.py",
                    "scripts/build_phase4_analytic_physical_fallback_scorecard.py",
                    "scripts/build_phase4_commercial_operator_reference_contract.py",
                    "scripts/build_phase4_commercial_operator_reference_ingest_validator.py",
                    "scripts/phase3_benchmark_reproduction_contract.py",
                    "scripts/run_phase3_benchmark_factory_clean_checkout_reproduction.py",
                    "scripts/run_phase3_benchmark_factory_git_clean_clone_reproduction.py",
                    "tests/test_build_phase3_benchmark_acquisition_artifacts.py",
                    "tests/test_build_phase3_benchmark_factory_artifacts.py",
                    "tests/test_build_phase3_buildingsmart_ifc_acquisition_receipt.py",
                    "tests/test_build_phase3_buildingsmart_dirty_ifc_acquisition_receipt.py",
                    "tests/test_build_phase3_ifc_source_license_receipt.py",
                    "tests/test_build_phase3_ifc_import_health_execution_receipt.py",
                    "tests/test_build_phase3_opensees_source_license_receipt.py",
                    "tests/test_build_phase4_commercial_comparison_import_template.py",
                    "tests/test_build_phase4_analytic_physical_fallback_scorecard.py",
                    "tests/test_build_phase4_commercial_operator_reference_contract.py",
                    "tests/test_build_phase4_commercial_operator_reference_ingest_validator.py",
                    "tests/test_run_phase3_benchmark_factory_clean_checkout_reproduction.py",
                    "tests/test_run_phase3_benchmark_factory_git_clean_clone_reproduction.py",
                ],
                [
                    "python3",
                    "scripts/build_phase3_benchmark_factory_artifacts.py",
                    "--check",
                    "--source-commit-sha",
                    replay_source_commit,
                ],
            ]
            for command in commands:
                result = _run_command(command, cwd=checkout_root)
                command_results.append(result)
                if result["return_code"] != 0:
                    blockers.append(f"command_failed:{result['command']}")
                    break
        else:
            blockers.append("git_clone_failed")

        artifact_paths = {
            "manifest": checkout_root / PRODUCTIZATION / "phase3_benchmark_factory_seed_manifest.json",
            "acquisition_plan": checkout_root / PRODUCTIZATION / "phase3_benchmark_acquisition_plan.json",
            "buildingsmart_ifc_acquisition_receipt": (
                checkout_root / PRODUCTIZATION / "phase3_buildingsmart_ifc_acquisition_receipt.json"
            ),
            "buildingsmart_dirty_ifc_acquisition_receipt": (
                checkout_root / PRODUCTIZATION / "phase3_buildingsmart_dirty_ifc_acquisition_receipt.json"
            ),
            "ifc_source_license_receipt": (
                checkout_root / PRODUCTIZATION / "phase3_ifc_source_license_receipt.json"
            ),
            "ifc_import_health_execution_receipt": (
                checkout_root / PRODUCTIZATION / "phase3_ifc_import_health_execution_receipt.json"
            ),
            "opensees_source_license_receipt": (
                checkout_root / PRODUCTIZATION / "phase3_opensees_medium_source_license_receipt.json"
            ),
            "commercial_comparison_import_template": (
                checkout_root / PRODUCTIZATION / "phase4_commercial_comparison_import_template.json"
            ),
            "phase4_analytic_physical_fallback_scorecard": (
                checkout_root / PRODUCTIZATION / "phase4_analytic_physical_fallback_scorecard.json"
            ),
            "commercial_operator_reference_contract": (
                checkout_root / PRODUCTIZATION / "phase4_commercial_operator_reference_contract.json"
            ),
            "commercial_operator_reference_ingest_validator": (
                checkout_root / PRODUCTIZATION / "phase4_commercial_operator_reference_ingest_validator.json"
            ),
            "scorecard": checkout_root / PRODUCTIZATION / "phase3_benchmark_factory_seed_scorecard.json",
            "summary": checkout_root / PRODUCTIZATION / "phase3_benchmark_factory_seed_summary.json",
        }
        for key, path in artifact_paths.items():
            if not path.exists():
                blockers.append(f"generated_artifact_missing:{key}")
                continue
            generated_artifact_checksums[key] = _stable_payload_checksum(_load_json(path))
    finally:
        if keep_checkout:
            retained_path = str(checkout_root)
        else:
            shutil.rmtree(clone_parent, ignore_errors=True)
    return {
        "command_results": command_results,
        "generated_stable_artifact_checksums": generated_artifact_checksums,
        "blockers": blockers,
        "clone_checkout_path": retained_path,
    }


def build_phase3_git_clean_clone_reproduction(
    *,
    repo_root: Path = ROOT,
    bundle_path: Path = DEFAULT_BUNDLE,
    source_commit_sha: str | None = None,
    keep_checkout: bool = False,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    source_commit = source_commit_sha if source_commit_sha is not None else git_head(repo_root)
    resolved_bundle = bundle_path if bundle_path.is_absolute() else repo_root / bundle_path
    required_paths = _required_paths(bundle_path, repo_root=repo_root)
    path_roles = _required_path_roles(required_paths)
    preflight = _preflight_git_clean_clone(repo_root, required_paths)
    preflight_action_summary = _preflight_action_summary(preflight)
    blocker_summary_by_role = _required_path_blocker_summary_by_role(preflight, path_roles)
    release_control_cleanup_plan = _release_control_cleanup_plan(
        preflight,
        blocker_summary_by_role,
    )

    expected_checksums: dict[str, Any] = {}
    replay_source_commit = source_commit
    bundle_status = "missing"
    if resolved_bundle.exists():
        bundle = _load_json(resolved_bundle)
        expected = bundle.get("stable_artifact_checksums", {})
        expected_checksums = expected if isinstance(expected, dict) else {}
        bundle_source_commit = bundle.get("source_commit_sha")
        if isinstance(bundle_source_commit, str) and bundle_source_commit:
            replay_source_commit = bundle_source_commit
        bundle_status = "present"

    command_results: list[dict[str, Any]] = []
    generated_checksums: dict[str, str] = {}
    clone_checkout_path = ""
    blockers = list(preflight["blockers"])
    if bundle_status != "present":
        blockers.append(f"bundle_missing:{bundle_path}")

    if preflight["pass"] and bundle_status == "present":
        replay = _run_git_clean_clone_replay(
            repo_root=repo_root,
            source_commit=source_commit,
            replay_source_commit=replay_source_commit,
            keep_checkout=keep_checkout,
        )
        command_results = replay["command_results"]
        generated_checksums = replay["generated_stable_artifact_checksums"]
        clone_checkout_path = replay["clone_checkout_path"]
        blockers.extend(replay["blockers"])
        if generated_checksums != expected_checksums:
            blockers.append("stable_artifact_checksum_mismatch")

    command_pass = bool(command_results) and all(row["return_code"] == 0 for row in command_results)
    checksum_match = bool(generated_checksums) and generated_checksums == expected_checksums
    contract_pass = bool(preflight["pass"] and command_pass and checksum_match and not blockers)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit_sha": source_commit,
        "replay_source_commit_sha": replay_source_commit,
        "source_repo_path": str(repo_root),
        "status": "pass" if contract_pass else "blocked",
        "contract_pass": contract_pass,
        "git_clean_clone_preflight_pass": bool(preflight["pass"]),
        "git_clean_clone_executed": bool(command_results),
        "git_clean_clone_execution_mode": "local_git_clone_no_local" if command_results else "not_executed",
        "git_clean_clone_retained": keep_checkout,
        "clone_checkout_path": clone_checkout_path,
        "phase3_closure_claim": False,
        "developer_preview_release_candidate_claim": False,
        "bundle_path": str(bundle_path),
        "bundle_status": bundle_status,
        "required_git_clean_clone_inputs": [path.as_posix() for path in required_paths],
        "required_input_path_roles": path_roles,
        "required_path_blocker_summary_by_role": blocker_summary_by_role,
        "release_control_cleanup_plan": release_control_cleanup_plan,
        "tracked_required_inputs": preflight["tracked_paths"],
        "untracked_or_missing_required_inputs": preflight["untracked_or_missing_paths"],
        "dirty_required_inputs": preflight["dirty_paths"],
        "required_input_git_status": preflight["path_status"],
        "preflight_action_summary": preflight_action_summary,
        "input_checksums": input_checksums(required_paths, repo_root=repo_root),
        "expected_stable_artifact_checksums": expected_checksums,
        "generated_stable_artifact_checksums": generated_checksums,
        "stable_artifact_checksums_match": checksum_match,
        "command_results": command_results,
        "blockers": blockers,
        "claim_boundary": (
            "This receipt is the authoritative Phase 3 seed git-clean-clone reproduction gate. "
            "When blocked, it proves the exact tracked/dirty-input reason a real clone cannot yet "
            "replay the seed benchmark artifacts from Git HEAD. When passing, it proves only a "
            "local git clone replay of generated analytic-small and element-patch seed artifacts. "
            "It is not Linux/Windows parity and does not prove Developer Preview Release Candidate closure, "
            "OpenSees, buildingSMART IFC, commercial-cross-solver, large-model, and is not full Phase 3 closure."
        ),
    }


def check_phase3_git_clean_clone_reproduction(
    *,
    repo_root: Path = ROOT,
    out_path: Path = DEFAULT_OUT,
    bundle_path: Path = DEFAULT_BUNDLE,
    source_commit_sha: str | None = None,
) -> tuple[bool, str]:
    expected = build_phase3_git_clean_clone_reproduction(
        repo_root=repo_root,
        bundle_path=bundle_path,
        source_commit_sha=source_commit_sha,
    )
    resolved = out_path if out_path.is_absolute() else repo_root / out_path
    if not resolved.exists():
        return False, f"phase3_git_clean_clone_reproduction_missing:{out_path.as_posix()}"
    try:
        existing = _load_json(resolved)
    except Exception as exc:
        return False, (
            f"phase3_git_clean_clone_reproduction_unreadable:{out_path.as_posix()}:"
            f"{exc.__class__.__name__}"
        )
    if _strip_volatile(existing) != _strip_volatile(expected):
        return False, "phase3_git_clean_clone_reproduction_mismatch"
    return True, "phase3_git_clean_clone_reproduction_consistent"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    parser.add_argument("--source-commit-sha", default=None)
    parser.add_argument("--keep-checkout", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.check:
        ok, message = check_phase3_git_clean_clone_reproduction(
            out_path=args.out,
            bundle_path=args.bundle,
            source_commit_sha=args.source_commit_sha,
        )
        print(f"Phase 3 git clean clone reproduction check: {message}")
        return 0 if ok else 1

    payload = build_phase3_git_clean_clone_reproduction(
        repo_root=ROOT,
        bundle_path=args.bundle,
        source_commit_sha=args.source_commit_sha,
        keep_checkout=args.keep_checkout,
    )
    out = args.out if args.out.is_absolute() else ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(_json_text(payload), encoding="utf-8")
    if args.json:
        print(_json_text(payload), end="")
    else:
        print(
            "Phase 3 git clean clone reproduction: "
            f"{payload['status']} | preflight={payload['git_clean_clone_preflight_pass']} | "
            f"executed={payload['git_clean_clone_executed']} | blockers={len(payload['blockers'])}"
        )
    return 2 if args.fail_blocked and not payload["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
